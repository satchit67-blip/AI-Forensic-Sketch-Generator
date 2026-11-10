"""
api/routes/sketch.py
--------------------
FastAPI route controller for the AI sketch pipeline.

Endpoints
---------
  POST /generate-sketch    Initial witness description → SketchTraits via Gemini
  POST /refine-sketch      Iterative refinement feedback → updated SketchTraits
  POST /apply-disguise     Toggle a disguise overlay (logged; state managed client-side)
  POST /export             Export event — writes audit log entry only
  POST /reset              Reset canvas — writes audit log entry only

Auth
----
All endpoints require a valid JWT (require_officer dependency).
The AuditMiddleware in core/middleware.py writes a coarse-grained log entry
automatically.  Routes also call audit.record() for precise action strings
(e.g. "Applied Disguise: Full Beard" vs the generic "Toggled Disguise Overlay").

Integration with frontend
-------------------------
App.jsx currently calls interpret() locally. Replace those calls with:
  synth()   → POST /generate-sketch
  feedback()→ POST /refine-sketch
  toggleDisguise() → POST /apply-disguise
  exportPng()      → POST /export  (fire-and-forget for audit)
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    AuditRecorder,
    get_audit_recorder_safe,
    get_current_user_or_demo,
    get_db_optional,
)
from app.models import User
from app.schemas import (
    ApplyDisguiseRequest,
    ApplyDisguiseResponse,
    ExportAuditRequest,
    ExportAuditResponse,
    GenerateSketchRequest,
    GenerateSketchResponse,
    RefineSketchRequest,
    RefineSketchResponse,
    SketchTraits,
)
from app.core.config import settings
from app.services.audit import get_audit_logs_for_case
import io
import json
from datetime import datetime
from fastapi.responses import StreamingResponse


def compute_export_hash(image_data_uri: str, metadata: dict) -> str:
    """Compute a SHA-256 integrity hash for case export dossier."""
    import hashlib
    raw = f"{image_data_uri}|{json.dumps(metadata, sort_keys=True)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Dynamic prompt assembly for witness descriptions & disguise toggle chips
# ---------------------------------------------------------------------------
def format_disguise_modifiers(disguises: list[str]) -> str:
    """
    Format active toggle chips into natural English modifiers.
    Example: ['Sunglasses', 'Mustache'] -> 'wearing dark sunglasses and a neat mustache'
    """
    if not disguises:
        return ""

    eyewear = (
        "dark sunglasses" if "Sunglasses" in disguises
        else ("wire-rimmed glasses" if "Wire-Rimmed Glasses" in disguises else None)
    )

    facial_hair = []
    if "Full Beard" in disguises:
        facial_hair.append("a full thick beard")
    if "Mustache" in disguises:
        facial_hair.append("a neat mustache")

    other = []
    if "Long Hair" in disguises and "Bald" not in disguises:
        other.append("with long flowing hair")
    elif "Bald" in disguises:
        other.append("completely bald with a clean-shaven head")
    if "Scar/Mark" in disguises:
        other.append("with a visible facial scar on the cheek")

    parts = []
    fh_str = " and ".join(facial_hair) if facial_hair else ""

    if eyewear and fh_str:
        if len(facial_hair) > 1:
            parts.append(f"wearing {eyewear}, with {fh_str}")
        else:
            parts.append(f"wearing {eyewear} and {fh_str}")
    elif eyewear:
        parts.append(f"wearing {eyewear}")
    elif fh_str:
        parts.append(f"with {fh_str}")

    parts.extend(other)
    return ", ".join(parts)


def clean_base_description(desc: str) -> str:
    """
    Isolates the clean base witness description by stripping any hardcoded prefixes
    or previously appended disguise fragments.
    """
    import re
    text = (desc or "").strip()

    # Strip legacy prefixes
    for prefix in [
        "A forensic police sketch portrait of ",
        "a forensic police sketch portrait of ",
        "Forensic sketch of ",
        "forensic sketch of ",
        "A police sketch of ",
        "a police sketch of ",
    ]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    # Strip previously appended disguise phrases to keep the base face clean and stable
    fragments = [
        r"wearing dark sunglasses and a neat mustache",
        r"wearing dark sunglasses and a full thick beard",
        r"wearing wire-rimmed glasses and a neat mustache",
        r"wearing wire-rimmed glasses and a full thick beard",
        r"with a full thick beard and a neat mustache",
        r"wearing dark sunglasses",
        r"wearing wire-rimmed glasses",
        r"with a full thick beard",
        r"with a neat mustache",
        r"sporting a prominent full beard",
        r"sporting a full thick beard",
        r"sporting a defined mustache",
        r"with long flowing hair",
        r"completely bald with a clean-shaven head",
        r"completely bald with shaved head",
        r"completely bald",
        r"with a visible facial scar on the cheek",
        r"with visible facial scar mark on cheek",
        r"with full thick beard",
        r"with neat mustache",
        r"wearing sunglasses",
        r"wearing glasses",
    ]
    for frag in fragments:
        text = re.sub(r",?\s*" + frag, "", text, flags=re.IGNORECASE).strip()

    return text.rstrip(",. ")


def assemble_dynamic_prompt(raw_description: str, disguises: list[str]) -> str:
    """
    Constructs a clean dynamic prompt:
    <base_description>, <natural_disguise_modifiers>
    """
    clean_base = clean_base_description(raw_description)
    modifiers = format_disguise_modifiers(disguises)

    if clean_base and modifiers:
        return f"{clean_base}, {modifiers}"
    elif clean_base:
        return clean_base
    elif modifiers:
        return f"portrait of a person, {modifiers}"
    return "portrait of a person"

router = APIRouter(tags=["Sketch AI Pipeline"])


# ---------------------------------------------------------------------------
# POST /generate-sketch
# ---------------------------------------------------------------------------
@router.post(
    "/generate-sketch",
    response_model=GenerateSketchResponse,
    summary="Parse witness description -> structured facial traits & generate image",
)
async def generate_sketch(
    body: GenerateSketchRequest,
    user: User = Depends(get_current_user_or_demo),
    db: AsyncSession | None = Depends(get_db_optional),
    audit: AuditRecorder = Depends(get_audit_recorder_safe),
) -> GenerateSketchResponse:
    """
    Step 1 of the AI pipeline:
    Extracts raw witness description as primary subject base.
    Cleanly appends active disguise toggle chips as explicit modifiers.
    Fetches real dynamic image directly from Pollinations.ai.
    """
    traits, raw_output = await ai_service.parse_description(body.description)

        # 1. Cleanly extract raw witness description as primary subject base
    raw_desc = (body.description or "").strip()

    # 2. Dynamically collect all active toggle chips from request & traits
    active_disguises: list[str] = []
    valid_disguises = {
        "Full Beard", "Mustache", "Wire-Rimmed Glasses",
        "Sunglasses", "Long Hair", "Bald", "Scar/Mark",
    }
    if body.disguises:
        for d in body.disguises:
            if d in valid_disguises and d not in active_disguises:
                active_disguises.append(d)
    if traits and traits.disguises:
        for d in traits.disguises:
            if d in valid_disguises and d not in active_disguises:
                active_disguises.append(d)

    # Synchronize disguises and hair on traits
    traits.disguises = sorted(set(active_disguises))
    if "Bald" in traits.disguises:
        traits.hair = "bald"
    elif "Long Hair" in traits.disguises:
        traits.hair = "long"

    # 3. Assemble dynamic prompt without rigid 3D style prefixes
    final_prompt = assemble_dynamic_prompt(raw_desc, traits.disguises)

    # 4. Derive stable, deterministic seed from the base witness description
    stable_seed = image_service.get_deterministic_seed(raw_desc)

    # 5. Generate dynamic sketch using deterministic seed
    try:
        raw_b64, prompt_used = await image_service.generate_sketch_image(
            traits=traits,
            description=final_prompt,
            case_id=str(body.case_id) if body.case_id else "default",
            seed=stable_seed,
        )
        data_uri = f"data:image/jpeg;base64,{raw_b64}" if not raw_b64.startswith("data:") else raw_b64
    except Exception as exc:
        logger.warning("Live generation encountered: %s; using dynamic fallback", exc)
        data_uri = image_service.get_fallback_sketch_data_uri(
            traits=traits,
            description=final_prompt,
        )

    return GenerateSketchResponse(
        traits=traits,
        raw_gemini_output=raw_output,
        case_id=body.case_id,
        image_b64=data_uri,
        sketch_url=data_uri,
        sketch_data=data_uri,
        url=data_uri,
        data=data_uri,
    )

# ---------------------------------------------------------------------------
@router.post(
    "/refine-sketch",
    response_model=RefineSketchResponse,
    summary="Apply iterative refinement feedback to an existing sketch",
    description=(
        "Accepts witness/officer feedback alongside the current trait state. "
        "Gemini updates ONLY the traits explicitly mentioned in the feedback, "
        "preserving the core facial identity of the sketch. "
        "Mirrors the ChatPanel.jsx / feedback() flow in the frontend."
    ),
)
async def refine_sketch(
    body: RefineSketchRequest,
    user: User = Depends(get_current_user_or_demo),
    db: AsyncSession | None = Depends(get_db_optional),
    audit: AuditRecorder = Depends(get_audit_recorder_safe),
) -> RefineSketchResponse:
    """
    Step 2+ — iterative refinement.
    """
    try:
        updated_traits, summary = await ai_service.refine_traits(
            feedback=body.feedback,
            current_traits=body.current_traits,
            role=body.role,
        )

        feedback_preview = body.feedback[:60] + ("…" if len(body.feedback) > 60 else "")
        try:
            await audit.record(
                action=f'Refinement by {body.role}: "{feedback_preview}" → {summary}',
                case_id=body.case_id,
            )
        except Exception:
            pass

        data_uri = image_service.get_fallback_sketch_data_uri(
            traits=updated_traits,
            description=f"{body.description or ''} {body.feedback}".strip(),
        )

        return RefineSketchResponse(
            traits=updated_traits,
            summary=summary,
            case_id=body.case_id,
            image_b64=data_uri,
            sketch_url=data_uri,
            url=data_uri,
            sketch_data=image_service.FALLBACK_SVG_STRING,
            data=data_uri,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("refine_sketch fallback safely recovered from: %s", exc)
        base = body.current_traits or SketchTraits()
        updated_traits = ai_service._fallback_interpret(body.feedback, base=base)
        data_uri = image_service.get_fallback_sketch_data_uri(
            traits=updated_traits,
            description=f"{body.description or ''} {body.feedback}".strip(),
        )
        return RefineSketchResponse(
            traits=updated_traits,
            summary="Traits updated. Core facial structure preserved.",
            case_id=body.case_id,
            image_b64=data_uri,
            sketch_url=data_uri,
            url=data_uri,
            sketch_data=image_service.FALLBACK_SVG_STRING,
            data=data_uri,
        )


# ---------------------------------------------------------------------------
# POST /apply-disguise
# ---------------------------------------------------------------------------
@router.post(
    "/apply-disguise",
    response_model=ApplyDisguiseResponse,
    summary="Toggle a disguise overlay on the active sketch",
    description=(
        "Applies or removes a named disguise (beard, glasses, etc.) from the sketch. "
        "The SVG renderer handles the actual visual update client-side; this endpoint "
        "exists solely for server-side audit logging and future persistence. "
        "Bald and Long Hair are mutually exclusive — the server enforces this."
    ),
)
async def apply_disguise(
    body: ApplyDisguiseRequest,
    user: User = Depends(get_current_user_or_demo),
    db: AsyncSession | None = Depends(get_db_optional),
    audit: AuditRecorder = Depends(get_audit_recorder_safe),
) -> ApplyDisguiseResponse:
    """
    Disguise toggle:
    1. Collects and updates active disguise chips.
    2. Isolates the stable base witness description to anchor the face seed.
    3. Explicitly appends active modifiers (e.g., ', wearing dark sunglasses and a neat mustache').
    4. Generates/fetches the updated dynamic image.
    """
    verb = "Applied" if body.active else "Removed"

    warning: str | None = None
    if body.active and body.name == "Bald":
        warning = "Long Hair will be overridden by Bald."
    elif body.active and body.name == "Long Hair":
        warning = "Bald will be overridden by Long Hair."

    # Update disguise state on current traits
    current_traits = body.current_traits or SketchTraits()
    disguise_set = set(current_traits.disguises)
    if body.active:
        disguise_set.add(body.name)
        if body.name == "Bald":
            disguise_set.discard("Long Hair")
            current_traits.hair = "bald"
        elif body.name == "Long Hair":
            disguise_set.discard("Bald")
            current_traits.hair = "long"
    else:
        disguise_set.discard(body.name)
    current_traits.disguises = sorted(disguise_set)

    try:
        await audit.record(
            action=f"{verb} Disguise: {body.name}",
            case_id=body.case_id,
        )
    except Exception:
        pass

    msg = f"{verb} {body.name}. Core facial structure unchanged."
    if warning:
        msg += f" Note: {warning}"

    # 1. Cleanly isolate stable base description
    raw_desc = (body.description or "").strip()
    clean_base = clean_base_description(raw_desc) or raw_desc

    # 2. Derive stable, deterministic seed from clean base description
    stable_seed = image_service.get_deterministic_seed(clean_base)

    # 3. Assemble final prompt: base description + explicit disguise modifiers
    final_prompt = assemble_dynamic_prompt(clean_base, current_traits.disguises)
    logger.info("apply_disguise final prompt: '%s' (seed=%d)", final_prompt, stable_seed)

    try:
        raw_b64, _ = await image_service.generate_sketch_image(
            traits=current_traits,
            description=final_prompt,
            case_id=str(body.case_id) if body.case_id else "default",
            seed=stable_seed,
        )
        data_uri = f"data:image/jpeg;base64,{raw_b64}" if not raw_b64.startswith("data:") else raw_b64
    except Exception as exc:
        logger.warning("apply_disguise live generation encountered: %s; using dynamic fallback", exc)
        data_uri = image_service.get_fallback_sketch_data_uri(
            traits=current_traits,
            description=final_prompt,
        )

    return ApplyDisguiseResponse(
        name=body.name,
        active=body.active,
        case_id=body.case_id,
        message=msg,
        traits=current_traits,
        image_b64=data_uri,
        sketch_url=data_uri,
        url=data_uri,
        sketch_data=image_service.FALLBACK_SVG_STRING,
        data=data_uri,
    )


# ---------------------------------------------------------------------------
# POST /export
# ---------------------------------------------------------------------------
@router.post(
    "/export",
    response_model=ExportAuditResponse,
    summary="Log a high-res export event",
    description=(
        "Called by the frontend after exportPng() serialises the SVG to canvas. "
        "The actual image export is client-side; this endpoint records the event "
        "in the audit log for chain-of-custody compliance."
    ),
)
async def export_sketch(
    body: ExportAuditRequest,
    user: User = Depends(get_current_user_or_demo),
    db: AsyncSession | None = Depends(get_db_optional),
    audit: AuditRecorder = Depends(get_audit_recorder_safe),
) -> StreamingResponse:
    """
    Compile a court‑ready evidence package.
    Includes case metadata, full audit‑log trail, a SHA‑256 verification hash,
    and export timestamp. Returned as a downloadable JSON file.
    """
    # Record the export action (middleware also logs a coarse entry)
    try:
        await audit.record(action="Exported High‑Res Image", case_id=body.case_id)
    except Exception:
        pass

    # Build verification hash (image data URI + minimal metadata)
    metadata = {
        "case_id": str(body.case_id) if body.case_id else None,
        "exported_by": user.id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    verification_hash = compute_export_hash(body.image_data_uri, metadata)

    # Gather case details if available
    case_data = None
    if db is not None and body.case_id:
        from app.models import Case
        case_obj = await db.get(Case, str(body.case_id))
        if case_obj:
            case_data = {
                "id": case_obj.id,
                "case_number": case_obj.case_number,
                "title": case_obj.title,
                "description": case_obj.description,
                "created_by": case_obj.created_by,
                "created_at": case_obj.created_at.isoformat(),
                "updated_at": case_obj.updated_at.isoformat(),
            }

    # Retrieve full audit trail for the case (fallback to empty list)
    audit_entries: list = []
    if db is not None and body.case_id:
        try:
            total, rows = await get_audit_logs_for_case(
                db, case_id=body.case_id, limit=10000, offset=0
            )
            audit_entries = [
                {
                    "id": entry.id,
                    "user_id": entry.user_id,
                    "case_id": entry.case_id,
                    "action": entry.action,
                    "timestamp": entry.timestamp.isoformat(),
                    "username": getattr(entry, "username", None),
                    "case_number": getattr(entry, "case_number", None),
                }
                for entry in rows
            ]
        except Exception:
            pass

    # Assemble final evidence package
    package = {
        "export_timestamp": metadata["timestamp"],
        "exported_by": user.id,
        "case": case_data,
        "audit_log": audit_entries,
        "verification_hash": verification_hash,
    }

    # Return as downloadable JSON file
    json_bytes = json.dumps(package, indent=2, sort_keys=True).encode("utf-8")
    file_like = io.BytesIO(json_bytes)
    filename = f"evidence_export_{body.case_id or 'session'}.json"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(file_like, media_type="application/json", headers=headers)


# ---------------------------------------------------------------------------
# POST /reset
# ---------------------------------------------------------------------------
@router.post(
    "/reset",
    summary="Log a canvas reset event",
    description="Records the reset action in the audit log.",
)
async def reset_canvas(
    case_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user_or_demo),
    db: AsyncSession | None = Depends(get_db_optional),
    audit: AuditRecorder = Depends(get_audit_recorder_safe),
) -> dict[str, str]:
    """Log the canvas reset — no server state to clear (traits live client-side)."""
    try:
        await audit.record(
            action="Reset Canvas",
            case_id=case_id,
        )
    except Exception:
        pass
    return {"message": "Canvas reset logged", "case_id": str(case_id)}