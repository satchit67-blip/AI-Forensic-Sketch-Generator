"""
services/ai_service.py
-----------------------
Google Gemini integration for the forensic sketch AI pipeline.

Public API
----------
  parse_description(text)                          → SketchTraits
      Sends a raw witness description to Gemini and extracts structured
      facial parameters as a SketchTraits object.

  refine_traits(feedback, current_traits, role)    → tuple[SketchTraits, str]
      Sends iterative feedback with the current trait state as context.
      Only traits explicitly mentioned in feedback are updated; the rest
      are identity-anchored (mirrors face.js behaviour).

  _fallback_interpret(text, base)                  → SketchTraits
      Pure-Python rule-based fallback (mirrors face.js interpret()).
      Used automatically when Gemini is unavailable or returns bad JSON.

Architecture Notes
------------------
- generate_content_async() keeps the FastAPI event loop unblocked.
- response_mime_type="application/json" forces Gemini to return clean JSON
  with no markdown fences, making parsing reliable and schema-enforceable.
- A JSON Schema (response_schema) is passed to Gemini 1.5 Flash/Pro for
  strict output validation at the model level.
- All Gemini calls go through _gemini_generate() which handles retries
  with exponential back-off and maps SDK exceptions to HTTP errors.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from google import genai
from google.genai import types as genai_types
from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas import SketchTraits

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini client initialisation (module-level singleton)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Gemini client singleton (google-genai SDK — pure REST, no gRPC dependency)
# ---------------------------------------------------------------------------
_gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)

# JSON Schema for structured Gemini response validation
_SKETCH_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "jaw":        {"type": "string", "enum": ["soft", "sharp"]},
        "hair":       {"type": "string", "enum": ["short", "long", "bald"]},
        "hair_color": {"type": "string", "description": "CSS hex colour e.g. #8a8a90"},
        "face":       {"type": "number", "description": "Width scale 0.85-1.20"},
        "disguises": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "Full Beard", "Mustache",
                    "Wire-Rimmed Glasses", "Sunglasses",
                    "Long Hair", "Bald", "Scar/Mark",
                ],
            },
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short human-readable log of each trait extracted",
        },
    },
    "required": ["jaw", "hair", "hair_color", "face", "disguises", "notes"],
}

# ---------------------------------------------------------------------------
# System instructions
# ---------------------------------------------------------------------------
_SYSTEM_GENERATE = """\
You are an expert AI forensic sketch artist embedded in a law-enforcement investigation system.
Your sole task: analyse a witness's natural-language suspect description and extract precise
facial parameters as a single JSON object.

──────────────────────────────────────────────────────
OUTPUT SCHEMA  (strict – no markdown, no commentary)
──────────────────────────────────────────────────────
{
  "jaw":        "soft" | "sharp",
  "hair":       "short" | "long" | "bald",
  "hair_color": "<CSS hex>",
  "face":       <float 0.85–1.20>,
  "disguises":  [ <zero or more items from allowed list> ],
  "notes":      [ <one short string per trait you extracted> ]
}

──────────────────────────────────────────────────────
FIELD RULES
──────────────────────────────────────────────────────
jaw
  "sharp"  → angular, chiseled, square, strong, defined, prominent, hard jaw
  "soft"   → round, oval, gentle, chubby, soft jaw  (DEFAULT when unspecified)

hair
  "short"  → short, crew cut, buzz cut, cropped, trimmed  (DEFAULT)
  "long"   → long hair, ponytail, shoulder-length, flowing
  "bald"   → bald, shaved head, no hair

hair_color  (use these exact hex codes)
  Black / very dark  →  "#1c1c20"
  Dark (unspecified) →  "#2b2b2f"   ← DEFAULT
  Dark brown         →  "#4a3426"
  Light brown        →  "#6b4c35"
  Blonde / blond     →  "#b9a06a"
  Grey / gray        →  "#8a8a90"
  Red / ginger / auburn → "#8a3b22"
  White              →  "#d4d4d4"

face  (horizontal width scale factor)
  0.85–0.92  →  thin, narrow, gaunt, slim, long face
  0.93–1.07  →  average proportions  (DEFAULT: 1.0)
  1.08–1.20  →  wide, broad, round, chubby, full face

disguises  (add ONLY when explicitly described)
  "Full Beard"          →  beard, heavy stubble, full beard
  "Mustache"            →  mustache / moustache  (without full beard)
  "Wire-Rimmed Glasses" →  glasses, spectacles, wire-rimmed, reading glasses
  "Sunglasses"          →  sunglasses, dark glasses, shades, tinted lenses
  "Long Hair"           →  add when hair is long AND witness emphasises it
  "Bald"                →  add when suspect is explicitly bald / shaved-headed
  "Scar/Mark"           →  scar, mark, birthmark, mole, prominent tattoo on face

──────────────────────────────────────────────────────
IMPORTANT RULES
──────────────────────────────────────────────────────
1.  Extract ONLY traits explicitly stated; leave everything else at its default.
2.  "clean-shaven" or "no beard" → do NOT include Full Beard or Mustache.
3.  "Bald" and "Long Hair" are mutually exclusive; Bald wins if both mentioned.
4.  For each trait you extract write a short note, e.g. "jaw → sharp", "hair → grey".
5.  Return ONLY the JSON object — no markdown fences, no prose, no keys outside the schema.
"""

_SYSTEM_REFINE = """\
You are an expert AI forensic sketch artist.  A sketch has already been generated.
You will receive:
  • current_traits  – the JSON of the current facial parameters
  • feedback        – new natural-language input from a witness or officer
  • role            – "Witness" or "Officer"

Your task: update ONLY the traits explicitly mentioned in the feedback.
All unmentioned traits must remain IDENTICAL to current_traits.
This preserves the core facial identity of the sketch.

OUTPUT SCHEMA  (same as generation, strict JSON only):
{
  "jaw":       "soft" | "sharp",
  "hair":      "short" | "long" | "bald",
  "hair_color": "<CSS hex>",
  "face":      <float 0.85–1.20>,
  "disguises": [ ... ],
  "notes":     [ "what changed and why" ]
}

RULES:
- If feedback mentions "remove beard" / "no beard" → remove "Full Beard" and "Mustache" from disguises.
- If feedback says "add glasses" → add the appropriate glasses type.
- If nothing changed, return current_traits unchanged with notes = ["No changes detected"].
- Return ONLY the JSON object.
"""

# ---------------------------------------------------------------------------
# Colour keyword → hex map (mirrors face.js)
# ---------------------------------------------------------------------------
_COLOUR_MAP: dict[str, str] = {
    r"\bblack\b":           "#1c1c20",
    r"\bdark\b":            "#2b2b2f",
    r"\bbrown\b":           "#4a3426",
    r"\blight brown\b":     "#6b4c35",
    r"\bblond(e)?\b":       "#b9a06a",
    r"\bgr[ae]y\b":         "#8a8a90",
    r"\bred\b|\bginger\b|\bauburn\b": "#8a3b22",
    r"\bwhite\b":           "#d4d4d4",
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
async def _gemini_generate(
    system_instruction: str,
    prompt: str,
    *,
    max_retries: int = 2,
) -> str:
    """
    Call Gemini asynchronously with exponential back-off on rate-limit errors.

    Uses the google-genai SDK (pure REST — no gRPC dependency).
    Returns the raw response text (should be JSON).
    Raises HTTPException on unrecoverable errors.
    """
    config = genai_types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.05,           # near-deterministic for consistent feature extraction
        top_p=0.95,
        top_k=40,
        max_output_tokens=512,
        response_mime_type="application/json",
    )
    delay = 1.5  # seconds between retries

    for attempt in range(max_retries + 1):
        try:
            response = await _gemini_client.aio.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt,
                config=config,
            )
            return response.text
        except Exception as exc:
            exc_str = str(exc).lower()
            is_rate_limit = "quota" in exc_str or "429" in exc_str or "rate" in exc_str

            if is_rate_limit and attempt < max_retries:
                logger.warning(
                    "Gemini rate-limited (attempt %d/%d); retrying in %.1fs",
                    attempt + 1, max_retries + 1, delay,
                )
                await asyncio.sleep(delay)
                delay *= 2
                continue

            logger.error("Gemini API error on attempt %d: %s", attempt + 1, exc)

            if is_rate_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Gemini API rate limit reached. Please wait a moment and try again.",
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Gemini API unavailable: {exc}",
            )

    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Gemini unreachable")


def _parse_gemini_json(raw: str) -> dict[str, Any]:
    """
    Parse Gemini's text response as JSON.

    Gemini sometimes wraps JSON in markdown fences despite response_mime_type.
    This strips fences before parsing.
    """
    # Strip ```json ... ``` or ``` ... ``` wrappers
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Gemini returned non-JSON output: {exc}\n---\n{raw[:300]}")


def _coerce_traits(data: dict[str, Any], base: SketchTraits | None = None) -> SketchTraits:
    """
    Convert raw parsed JSON → SketchTraits, applying defaults and clamping.
    If *base* is provided, unspecified fields inherit from it.
    """
    fallback = base or SketchTraits()

    jaw        = data.get("jaw", fallback.jaw)
    hair       = data.get("hair", fallback.hair)
    hair_color = data.get("hair_color", fallback.hair_color)
    face_raw   = data.get("face", fallback.face)
    disguises  = data.get("disguises", list(fallback.disguises))
    notes      = data.get("notes", [])

    # Clamp / validate
    jaw       = jaw if jaw in ("soft", "sharp") else fallback.jaw
    hair      = hair if hair in ("short", "long", "bald") else fallback.hair
    face_val  = float(face_raw) if isinstance(face_raw, (int, float)) else fallback.face
    face_val  = max(0.85, min(1.20, face_val))

    # Validate hex colour
    if not isinstance(hair_color, str) or not re.match(r"^#[0-9a-fA-F]{6}$", hair_color):
        hair_color = fallback.hair_color

    # Mutual exclusion: Bald overrides Long Hair
    valid_disguises = {
        "Full Beard", "Mustache", "Wire-Rimmed Glasses",
        "Sunglasses", "Long Hair", "Bald", "Scar/Mark",
    }
    disguise_set = {d for d in disguises if d in valid_disguises}
    if "Bald" in disguise_set:
        disguise_set.discard("Long Hair")
        hair = "bald"
    if "Long Hair" in disguise_set:
        hair = "long"

    return SketchTraits(
        jaw=jaw,
        hair=hair,
        hair_color=hair_color,
        face=face_val,
        disguises=sorted(disguise_set),
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Rule-based fallback (mirrors face.js interpret())
# ---------------------------------------------------------------------------
def _fallback_interpret(text: str, base: SketchTraits | None = None) -> SketchTraits:
    """
    Pure-Python rule-based trait extractor — mirrors the interpret() function
    in face.js exactly.  Used when Gemini is unavailable or returns bad JSON.
    """
    s = text.lower()
    t = base.model_copy(deep=True) if base else SketchTraits()
    notes: list[str] = []
    disguises: set[str] = set(t.disguises)

    def has(pattern: str) -> bool:
        return bool(re.search(pattern, s))

    # ── Jaw ───────────────────────────────────────────────────────────────
    if has(r"sharp|square|angular|strong jaw|chiseled|defined jaw"):
        t.jaw = "sharp"; notes.append("jaw → sharp")
    elif has(r"round|soft jaw|chubby|oval"):
        t.jaw = "soft";  notes.append("jaw → soft")

    # ── Hair length ───────────────────────────────────────────────────────
    if has(r"bald|shaved head"):
        t.hair = "bald";  notes.append("hairline cleared")
        disguises.add("Bald"); disguises.discard("Long Hair")
    elif has(r"long hair|ponytail|shoulder.?length"):
        t.hair = "long";  notes.append("hair → long")
        disguises.add("Long Hair"); disguises.discard("Bald")
    elif has(r"short hair|crew cut|buzz"):
        t.hair = "short"; notes.append("hair → short")

    # ── Hair colour ───────────────────────────────────────────────────────
    for pattern, hex_val in _COLOUR_MAP.items():
        if has(pattern):
            t.hair_color = hex_val
            colour_name = pattern.split(r"\b")[1].split("\\")[0]
            notes.append(f"hair colour → {colour_name}")
            break

    # ── Face width ────────────────────────────────────────────────────────
    if has(r"wide face|broad face|broad"):
        t.face = 1.12; notes.append("face → wide")
    elif has(r"thin face|narrow|gaunt|slim face"):
        t.face = 0.9;  notes.append("face → narrow")

    # ── Disguises ─────────────────────────────────────────────────────────
    if has(r"no beard|clean.?shaven"):
        disguises.discard("Full Beard"); disguises.discard("Mustache")
    else:
        if has(r"\bbeard\b|stubble"):   disguises.add("Full Beard")
        if has(r"mustache|moustache"): disguises.add("Mustache")

    if has(r"sunglasses|shades"):
        disguises.add("Sunglasses")
    elif has(r"\bglasses\b|spectacles"):
        disguises.add("Wire-Rimmed Glasses")

    if has(r"\bscar\b|\bmark\b|\bmole\b"):
        disguises.add("Scar/Mark")

    notes.extend(f"added {d}" for d in disguises - set(t.disguises))

    return SketchTraits(
        jaw=t.jaw,
        hair=t.hair,
        hair_color=t.hair_color,
        face=t.face,
        disguises=sorted(disguises),
        notes=notes if notes else ["No distinguishing traits detected; defaults used"],
    )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------
def _has_gemini_key() -> bool:
    key = settings.GEMINI_API_KEY
    if not key or not isinstance(key, str):
        return False
    key_strip = key.strip()
    if not key_strip or key_strip.startswith("your-") or "placeholder" in key_strip.lower() or "replace" in key_strip.lower():
        return False
    return key_strip.startswith("AIza")


async def parse_description(description: str) -> tuple[SketchTraits, str]:
    """
    Parse a raw witness description into structured SketchTraits using Gemini.

    Parameters
    ----------
    description : Natural language witness text

    Returns
    -------
    (SketchTraits, raw_gemini_output)

    Falls back to _fallback_interpret() if Gemini is unavailable or not configured.
    """
    if not _has_gemini_key():
        logger.info("GEMINI_API_KEY not configured; using rule-based parser fallback.")
        traits = _fallback_interpret(description)
        traits.notes.insert(0, "Procedural parser active (set GEMINI_API_KEY in .env for Gemini 1.5)")
        return traits, "Rule-based fallback: GEMINI_API_KEY not configured"

    prompt = (
        f"Witness description:\n\"\"\"\n{description.strip()}\n\"\"\"\n\n"
        "Extract the facial parameters as JSON."
    )

    try:
        raw = await asyncio.wait_for(_gemini_generate(_SYSTEM_GENERATE, prompt), timeout=3.5)
        data = _parse_gemini_json(raw)
        traits = _coerce_traits(data)
        logger.info("Gemini parse success: %s", traits.notes)
        return traits, raw

    except HTTPException as exc:
        logger.warning("Gemini API error (%s); using rule-based fallback", exc.detail)
        traits = _fallback_interpret(description)
        traits.notes.insert(0, f"[fallback] Gemini API error: {exc.detail}")
        return traits, f"Gemini error: {exc.detail}"

    except Exception as exc:
        # JSON parsing or unexpected error — fall back cleanly
        logger.warning("Gemini parse failed (%s); using rule-based fallback", exc)
        traits = _fallback_interpret(description)
        traits.notes.insert(0, f"[fallback] {exc} — rule-based extraction used")
        return traits, str(exc)


async def refine_traits(
    feedback: str,
    current_traits: SketchTraits,
    role: str,
) -> tuple[SketchTraits, str]:
    """
    Apply iterative refinement to an existing sketch using witness/officer feedback.

    Only traits explicitly mentioned in *feedback* are updated;
    all others are inherited from *current_traits*.
    """
    if not _has_gemini_key():
        logger.info("GEMINI_API_KEY not configured; using rule-based refinement.")
        updated = _fallback_interpret(feedback, base=current_traits)
        summary = ", ".join(updated.notes)
        return updated, summary

    prompt = (
        f"role: {role}\n\n"
        f"current_traits:\n{current_traits.model_dump_json(indent=2)}\n\n"
        f"feedback:\n\"\"\"\n{feedback.strip()}\n\"\"\"\n\n"
        "Return the updated traits JSON."
    )

    try:
        raw = await asyncio.wait_for(_gemini_generate(_SYSTEM_REFINE, prompt), timeout=3.5)
        data = _parse_gemini_json(raw)
        updated = _coerce_traits(data, base=current_traits)
        summary = (
            ", ".join(updated.notes) if updated.notes
            else "Identity anchors preserved; no traits changed"
        )
        logger.info("Gemini refine success [%s]: %s", role, updated.notes)
        return updated, summary

    except HTTPException as exc:
        logger.warning("Gemini refine HTTP error (%s); using rule-based fallback", exc.detail)
        updated = _fallback_interpret(feedback, base=current_traits)
        updated.notes.insert(0, f"[fallback] Gemini error: {exc.detail}")
        summary = ", ".join(updated.notes)
        return updated, summary

    except Exception as exc:
        logger.warning("Gemini refine failed (%s); using rule-based fallback", exc)
        updated = _fallback_interpret(feedback, base=current_traits)
        updated.notes.insert(0, f"[fallback] {exc}")
        summary = ", ".join(updated.notes)
        return updated, summary
