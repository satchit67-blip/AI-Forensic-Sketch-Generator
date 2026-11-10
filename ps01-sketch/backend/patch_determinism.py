"""
patch_determinism.py
--------------------
Applies user's exact specification:
1. Removes random cache-busting seed / timestamp.
2. Implements stable, deterministic seed derived from hashlib.md5 of base witness description:
   seed = int(hashlib.md5(base_description.encode()).hexdigest(), 16) % 1000000
3. Anchors the base face using this seed while appending active disguise chips to the prompt
   modification layer.
4. Adds in-memory image cache for identical (prompt, seed) calls to ensure absolute determinism.
"""

from pathlib import Path
import re
import py_compile
import sys

BACKEND_DIR = Path(__file__).resolve().parent
SKETCH_ROUTES = BACKEND_DIR / "app" / "api" / "routes" / "sketch.py"
IMAGE_SERVICE = BACKEND_DIR / "app" / "services" / "image_service.py"

# ==============================================================================
# 1. Update app/services/image_service.py
# ==============================================================================
service_code = IMAGE_SERVICE.read_text(encoding="utf-8")

# Add _IMAGE_CACHE and get_deterministic_seed helper
deterministic_seed_helper = '''
# ---------------------------------------------------------------------------
# Stable deterministic seed generation & in-memory image cache
# ---------------------------------------------------------------------------
_IMAGE_CACHE: dict[str, bytes] = {}


def get_deterministic_seed(base_text: str) -> int:
    """
    Derive a stable, deterministic integer seed from the base witness description text.
    Ensures the exact same suspect description always anchors the exact same base face.
    Formula: int(hashlib.md5(base_description.encode()).hexdigest(), 16) % 1000000
    """
    import hashlib
    clean = (base_text or "").strip().lower()
    if not clean:
        clean = "suspect portrait"
    return int(hashlib.md5(clean.encode("utf-8")).hexdigest(), 16) % 1000000
'''

if "def get_deterministic_seed" not in service_code:
    service_code = re.sub(
        r'(\n# HF Inference API calls)',
        deterministic_seed_helper + r'\1',
        service_code
    )

# Replace _pollinations_generate with clean deterministic implementation (no random seed, no timestamp)
new_pollinations_func = '''async def _pollinations_generate(prompt: str, seed: int | None = None) -> bytes:
    """
    Primary image generator via Pollinations.ai (free, zero-token API).
    Uses a deterministic seed derived from the base witness description so that
    identical prompt and seed pairs generate a consistent, stable base face.
    """
    import urllib.parse
    import re

    # Stable deterministic seed derived from prompt if not explicitly passed
    current_seed = seed if seed is not None else get_deterministic_seed(prompt)
    cache_key = f"{prompt.strip()}_{current_seed}"

    # Return cached image for exact identical prompt & seed
    if cache_key in _IMAGE_CACHE:
        logger.info("Returning cached deterministic image for key: %s (size=%d bytes)", cache_key[:60], len(_IMAGE_CACHE[cache_key]))
        return _IMAGE_CACHE[cache_key]

    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true&seed={current_seed}"

    async with httpx.AsyncClient(
        timeout=120.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    ) as client:
        for attempt in range(4):
            logger.info("Pollinations generate GET (attempt %d/4, seed=%d) -> %s", attempt + 1, current_seed, url[:120])
            try:
                resp = await client.get(url)
            except Exception as net_err:
                logger.warning("Pollinations network error on attempt %d: %s", attempt + 1, net_err)
                if attempt < 3:
                    await asyncio.sleep(3)
                    continue
                raise HTTPException(status_code=503, detail=f"Pollinations network error: {net_err}")

            logger.info("Pollinations response code: %d, size: %d bytes (seed=%d)", resp.status_code, len(resp.content), current_seed)
            if resp.status_code == 200 and len(resp.content) > 1000:
                _IMAGE_CACHE[cache_key] = resp.content
                return resp.content

            # Handle 1 image every 45s rate limit gracefully
            if resp.status_code == 402 and "FREE_LIMIT" in resp.text:
                match = re.search(r"Retry after (\\d+)s", resp.text)
                wait_sec = int(match.group(1)) + 2 if match else 20
                logger.warning("Pollinations rate limit hit. Waiting %ds before retry attempt %d...", wait_sec, attempt + 1)
                await asyncio.sleep(min(wait_sec, 45))
                continue

            # Handle transient upstream 500, 502, 503, 504 errors
            if resp.status_code in (500, 502, 503, 504) and attempt < 3:
                logger.warning("Pollinations returned transient %d, waiting 4s before retry...", resp.status_code)
                await asyncio.sleep(4)
                continue

            err_body = resp.text[:200]
            raise HTTPException(
                status_code=resp.status_code if resp.status_code != 200 else 502,
                detail=f"Pollinations API error {resp.status_code}: {err_body}",
            )

        raise HTTPException(
            status_code=503,
            detail="Pollinations API temporarily unavailable after retries.",
        )'''

service_code = re.sub(
    r'async def _pollinations_generate\(prompt: str.*?(?=\nasync def _hf_generate)',
    lambda m: new_pollinations_func + '\n\n',
    service_code,
    flags=re.DOTALL
)

# Replace generate_sketch_image to accept and pass deterministic seed
new_generate_image_func = '''async def generate_sketch_image(
    traits: SketchTraits,
    description: str,
    case_id: str,
    seed: int | None = None,
) -> tuple[str, str]:
    """
    Generate sketch image directly from dynamic textual prompt with stable deterministic seed.
    Passes prompt cleanly to Pollinations.ai without hardcoded 3D style prefixes.
    """
    final_prompt = description.strip()
    logger.info("Generating dynamic sketch for final prompt: %s (seed=%s)", final_prompt, seed)
    img_bytes = await _pollinations_generate(final_prompt, seed=seed)
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return b64, final_prompt'''

service_code = re.sub(
    r'async def generate_sketch_image\(.*?(?=\nasync def refine_sketch_image)',
    lambda m: new_generate_image_func + '\n\n\n',
    service_code,
    flags=re.DOTALL
)

IMAGE_SERVICE.write_text(service_code, encoding="utf-8")
print("[OK] Updated app/services/image_service.py")

# ==============================================================================
# 2. Update app/api/routes/sketch.py
# ==============================================================================
routes_code = SKETCH_ROUTES.read_text(encoding="utf-8")

# In generate_sketch, calculate stable_seed and pass to generate_sketch_image
generate_sketch_target = '''    # 1. Cleanly extract raw witness description as primary subject base
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
        )'''

routes_code = re.sub(
    r'# 1\. Cleanly extract raw witness description as primary subject base.*?data_uri = image_service\.get_fallback_sketch_data_uri\(\s*traits=traits,\s*description=final_prompt,\s*\)',
    lambda m: generate_sketch_target,
    routes_code,
    flags=re.DOTALL
)

# In apply_disguise, derive stable seed from raw_desc and pass to generate_sketch_image
apply_disguise_target = '''    # Build dynamic prompt with raw description as base and active chips as modifiers
    raw_desc = (body.description or "").strip()
    stable_seed = image_service.get_deterministic_seed(raw_desc)
    final_prompt = assemble_dynamic_prompt(raw_desc, current_traits.disguises)
    try:
        raw_b64, _ = await image_service.generate_sketch_image(
            traits=current_traits,
            description=final_prompt,
            case_id=str(body.case_id) if body.case_id else "default",
            seed=stable_seed,
        )
        data_uri = f'data:image/jpeg;base64,{raw_b64}' if not raw_b64.startswith('data:') else raw_b64
    except Exception as exc:
        logger.warning("apply_disguise live generation encountered: %s; using dynamic fallback", exc)
        data_uri = image_service.get_fallback_sketch_data_uri(
            traits=current_traits,
            description=final_prompt,
        )'''

routes_code = re.sub(
    r'# Build dynamic prompt with raw description as base and active chips as modifiers.*?data_uri = image_service\.get_fallback_sketch_data_uri\(\s*traits=current_traits,\s*description=final_prompt,\s*\)',
    lambda m: apply_disguise_target,
    routes_code,
    flags=re.DOTALL
)

# In refine_sketch, also pass deterministic seed
refine_sketch_target = '''        # Build dynamic prompt combining description, feedback and active disguises
        combined_desc = f"{body.description or ''} {body.feedback}".strip()
        stable_seed = image_service.get_deterministic_seed(body.description or combined_desc)
        final_prompt = assemble_dynamic_prompt(combined_desc, updated_traits.disguises)
        try:
            raw_b64, _ = await image_service.generate_sketch_image(
                traits=updated_traits,
                description=final_prompt,
                case_id=str(body.case_id) if body.case_id else "default",
                seed=stable_seed,
            )
            data_uri = f"data:image/jpeg;base64,{raw_b64}" if not raw_b64.startswith("data:") else raw_b64
        except Exception:
            data_uri = image_service.get_fallback_sketch_data_uri(
                traits=updated_traits,
                description=final_prompt,
            )'''

routes_code = re.sub(
    r'# Build dynamic prompt combining description, feedback and active disguises.*?data_uri = image_service\.get_fallback_sketch_data_uri\(\s*traits=updated_traits,\s*description=final_prompt,\s*\)',
    lambda m: refine_sketch_target,
    routes_code,
    flags=re.DOTALL
)

SKETCH_ROUTES.write_text(routes_code, encoding="utf-8")
print("[OK] Updated app/api/routes/sketch.py")

# ==============================================================================
# Syntax verification
# ==============================================================================
py_compile.compile(str(SKETCH_ROUTES), doraise=True)
print("[OK] Syntax check passed: sketch.py")
py_compile.compile(str(IMAGE_SERVICE), doraise=True)
print("[OK] Syntax check passed: image_service.py")
