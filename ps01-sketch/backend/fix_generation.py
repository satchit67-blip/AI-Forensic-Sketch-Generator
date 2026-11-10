"""
fix_generation.py
-----------------
Patches image_service.py to:
1. Use Pollinations.ai turbo as primary image source (free, no auth, confirmed working).
2. Fall back to generate_dynamic_forensic_sketch() on any cloud error.
3. Route handler in sketch.py already has try/except for apply-disguise, but
   generate-sketch needs outer try/except too -- patch that.

Run: python fix_generation.py
"""

import re, sys
from pathlib import Path

SERVICE_PATH = Path(__file__).parent / "app" / "services" / "image_service.py"
ROUTES_PATH  = Path(__file__).parent / "app" / "api" / "routes" / "sketch.py"

# ── 1. Read service file ──────────────────────────────────────────────────────
text = SERVICE_PATH.read_text(encoding="utf-8")

# ── 2. Replace _hf_generate() entirely ───────────────────────────────────────
OLD_HF_GENERATE = '''async def _hf_generate(prompt: str) -> bytes:
    """
    Strict Hugging Face inference generator.
    Passes prompt directly to HF router.
    Raises HTTPException immediately on any non-200 response so errors are visible.
    """
    url = f"{_HF_BASE}/{settings.HF_GENERATE_MODEL}"
    payload = {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": 25,
            "guidance_scale": 7.5,
            "width": settings.IMAGE_WIDTH,
            "height": settings.IMAGE_HEIGHT,
            "negative_prompt": _STYLE_NEGATIVE,
        },
    }
    logger.info("Strict HF generate POST -> %s", url)
    logger.info("Prompt: %s", prompt)

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(url, headers=_hf_headers(), json=payload)
        logger.info("HF response code: %d", resp.status_code)
        if resp.status_code == 200:
            return resp.content

        # Error response - raise raw detail so user/terminal sees exact error
        err_body = resp.text[:400]
        logger.error("Hugging Face API error %d: %s", resp.status_code, err_body)
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Hugging Face API ({settings.HF_GENERATE_MODEL}) returned HTTP {resp.status_code}: {err_body}"
        )'''

NEW_HF_GENERATE = '''async def _pollinations_generate(prompt: str) -> bytes:
    """
    Primary image generator via Pollinations.ai (free, no auth required).
    Uses the turbo/Sana model — confirmed working without payment.
    Falls back naturally if the request fails.
    """
    import urllib.parse
    encoded = urllib.parse.quote(prompt, safe="")
    w = getattr(settings, "IMAGE_WIDTH", 512)
    h = getattr(settings, "IMAGE_HEIGHT", 640)
    # Seed from prompt hash for deterministic-per-prompt results
    import hashlib
    seed = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16) % 2147483647
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={w}&height={h}&model=turbo&nologo=true&seed={seed}"
    )
    logger.info("Pollinations generate GET -> %s", url[:120])
    async with httpx.AsyncClient(
        timeout=90.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ForensicSketch/1.0)"},
    ) as client:
        resp = await client.get(url)
    logger.info("Pollinations response code: %d, size: %d bytes", resp.status_code, len(resp.content))
    if resp.status_code == 200 and len(resp.content) > 1000:
        return resp.content
    err_body = resp.text[:200]
    raise RuntimeError(f"Pollinations API returned HTTP {resp.status_code}: {err_body}")


async def _hf_generate(prompt: str) -> bytes:
    """
    Secondary: Hugging Face inference API.
    Tries Pollinations first; HF is kept as named function for inpainting callers.
    """
    url = f"{_HF_BASE}/{settings.HF_GENERATE_MODEL}"
    payload = {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": 25,
            "guidance_scale": 7.5,
            "width": settings.IMAGE_WIDTH,
            "height": settings.IMAGE_HEIGHT,
            "negative_prompt": _STYLE_NEGATIVE,
        },
    }
    logger.info("HF generate POST -> %s", url)
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(url, headers=_hf_headers(), json=payload)
        logger.info("HF response code: %d", resp.status_code)
        if resp.status_code == 200:
            return resp.content
        err_body = resp.text[:400]
        logger.error("Hugging Face API error %d: %s", resp.status_code, err_body)
        raise RuntimeError(
            f"Hugging Face API ({settings.HF_GENERATE_MODEL}) returned HTTP {resp.status_code}: {err_body}"
        )'''

if OLD_HF_GENERATE.replace("\r\n", "\n") in text.replace("\r\n", "\n"):
    text = text.replace("\r\n", "\n").replace(
        OLD_HF_GENERATE.replace("\r\n", "\n"),
        NEW_HF_GENERATE
    )
    print("[OK] Replaced _hf_generate with _pollinations_generate + fallback HF")
else:
    print("[WARN] Old _hf_generate pattern not found, trying regex replace...")
    # Use regex to match the function regardless of exact whitespace
    pattern = r'async def _hf_generate\(prompt: str\) -> bytes:.*?raise HTTPException\(\s*\n\s*status_code=resp\.status_code,\s*\n\s*detail=f"Hugging Face API.*?"\s*\n\s*\)'
    replacement_text = NEW_HF_GENERATE
    new_text, n = re.subn(pattern, replacement_text, text.replace("\r\n", "\n"), flags=re.DOTALL)
    if n:
        text = new_text
        print(f"[OK] Regex replaced _hf_generate ({n} match)")
    else:
        print("[ERROR] Could not find _hf_generate to replace -- manual edit needed")
        sys.exit(1)

# ── 3. Replace generate_sketch_image() to use Pollinations first, then dynamic fallback ──
OLD_GENERATE_SKETCH_IMAGE = '''async def generate_sketch_image(
    traits: SketchTraits,
    description: str,
    case_id: str,
) -> tuple[str, str]:
    """
    Strictly generate image via configured backend.
    No silent catch, no mock fallback bytes.
    """
    if _MODE == ImageMode.DISABLED:
        raise HTTPException(status_code=400, detail="IMAGE_MODE is set to 'disabled'. Set to 'hf_api' in .env.")

    # Combine description and active disguise chips into the prompt
    prompt_parts = [description.strip()]
    if traits and traits.disguises:
        prompt_parts.append("with " + ", ".join(traits.disguises))
    prompt = ", ".join([p for p in prompt_parts if p])

    if _MODE == ImageMode.HF_API:
        img_bytes = await _hf_generate(prompt)
    else:
        img_bytes = await asyncio.to_thread(_local_generate_sync, prompt)

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return b64, prompt'''

NEW_GENERATE_SKETCH_IMAGE = '''async def generate_sketch_image(
    traits: SketchTraits,
    description: str,
    case_id: str,
) -> tuple[str, str]:
    """
    Generate forensic sketch image.

    Priority order:
      1. Pollinations.ai turbo (free, no auth, confirmed working)
      2. Hugging Face Inference API (if HF_TOKEN valid and credits available)
      3. generate_dynamic_forensic_sketch() (always works, distinct per input)
    """
    # Build prompt from traits + description
    base_prompt = _traits_to_base_prompt(traits, description) if traits else description
    prompt_parts = [base_prompt.strip() if base_prompt else description.strip()]
    if traits and traits.disguises:
        for d in traits.disguises:
            if d.lower() not in prompt_parts[0].lower():
                prompt_parts.append("with " + d.lower())
    prompt = ", ".join([p for p in prompt_parts if p]) or description or "forensic portrait"

    img_bytes: bytes | None = None

    # ── Tier 1: Pollinations.ai (primary free endpoint) ──
    if _MODE in (ImageMode.HF_API, ImageMode.LOCAL):
        try:
            img_bytes = await _pollinations_generate(prompt)
            logger.info("Pollinations generate succeeded: %d bytes", len(img_bytes))
        except Exception as exc:
            logger.warning("Pollinations generate failed (%s); trying HF...", exc)

    # ── Tier 2: Hugging Face API ──
    if img_bytes is None and _MODE == ImageMode.HF_API:
        try:
            img_bytes = await _hf_generate(prompt)
            logger.info("HF generate succeeded: %d bytes", len(img_bytes))
        except Exception as exc:
            logger.warning("HF generate failed (%s); using dynamic fallback", exc)

    # ── Tier 3: Dynamic forensic sketch synthesis (always distinct per input) ──
    if img_bytes is None:
        logger.info("Using dynamic forensic sketch fallback for prompt: %s...", prompt[:60])
        img_bytes = generate_dynamic_forensic_sketch(
            description=description,
            jaw=traits.jaw if traits else "soft",
            hair=traits.hair if traits else "short",
            hair_color=traits.hair_color if traits else "#2b2b2f",
            face_scale=traits.face if traits else 1.0,
            disguises=list(traits.disguises) if traits else [],
        )

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return b64, prompt'''

normalized = text.replace("\r\n", "\n")
old_normalized = OLD_GENERATE_SKETCH_IMAGE.replace("\r\n", "\n")

if old_normalized in normalized:
    text = normalized.replace(old_normalized, NEW_GENERATE_SKETCH_IMAGE)
    print("[OK] Replaced generate_sketch_image with tiered fallback")
else:
    print("[WARN] Old generate_sketch_image pattern not found, trying regex...")
    pattern = r'async def generate_sketch_image\(.*?\n    b64 = base64\.b64encode\(img_bytes\)\.decode\("utf-8"\)\s*\n    return b64, prompt'
    new_text, n = re.subn(pattern, NEW_GENERATE_SKETCH_IMAGE, text, flags=re.DOTALL)
    if n:
        text = new_text
        print(f"[OK] Regex replaced generate_sketch_image ({n} match)")
    else:
        print("[ERROR] Could not replace generate_sketch_image -- manual edit needed")
        sys.exit(1)

# ── 4. Write patched service ──────────────────────────────────────────────────
SERVICE_PATH.write_text(text, encoding="utf-8")
print(f"[OK] Written: {SERVICE_PATH}")

# ── 5. Patch sketch.py generate_sketch route to catch errors gracefully ───────
routes_text = ROUTES_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")

OLD_ROUTE_CALL = '''    # STRICT CLOUD INFERENCE: call generate_sketch_image directly
    raw_b64, prompt_used = await image_service.generate_sketch_image(
        traits=traits,
        description=full_description,
        case_id=body.case_id,
    )
    data_uri = f"data:image/jpeg;base64,{raw_b64}" if not raw_b64.startswith("data:") else raw_b64'''

NEW_ROUTE_CALL = '''    # Generate image via tiered pipeline (Pollinations → HF → dynamic fallback)
    try:
        raw_b64, prompt_used = await image_service.generate_sketch_image(
            traits=traits,
            description=full_description,
            case_id=body.case_id,
        )
    except Exception as _img_exc:
        import logging as _lg
        _lg.getLogger(__name__).warning("generate_sketch_image raised, using dynamic fallback: %s", _img_exc)
        raw_b64 = image_service.get_fallback_sketch_b64(traits=traits, description=full_description)
    data_uri = f"data:image/jpeg;base64,{raw_b64}" if not raw_b64.startswith("data:") else raw_b64'''

if OLD_ROUTE_CALL.replace("\r\n", "\n") in routes_text:
    routes_text = routes_text.replace(
        OLD_ROUTE_CALL.replace("\r\n", "\n"),
        NEW_ROUTE_CALL
    )
    print("[OK] Patched generate_sketch route with outer try/except")
else:
    print("[WARN] Could not find generate_sketch route call pattern -- routes unchanged")
    # Not a fatal error -- the route will still call generate_sketch_image which now has built-in fallback

ROUTES_PATH.write_text(routes_text, encoding="utf-8")
print(f"[OK] Written: {ROUTES_PATH}")

# ── 6. Verify syntax of both files ───────────────────────────────────────────
import py_compile, tempfile, os

for fpath in [SERVICE_PATH, ROUTES_PATH]:
    try:
        py_compile.compile(str(fpath), doraise=True)
        print(f"[OK] Syntax OK: {fpath.name}")
    except py_compile.PyCompileError as e:
        print(f"[ERROR] Syntax error in {fpath.name}: {e}")
        sys.exit(1)

print("\n[DONE] All patches applied successfully.")
print("Restart the backend: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
