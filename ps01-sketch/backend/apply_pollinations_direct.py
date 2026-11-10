"""
apply_pollinations_direct.py
----------------------------
Applies user's exact specification:
1. In sketch.py: generate_sketch extracts description and disguises,
   concatenates into "A forensic police sketch portrait of <description> wearing <disguises>",
   and passes directly to generate_sketch_image without catching and replacing with static/mock bytes.
2. In image_service.py: generate_sketch_image directly passes final_prompt to _pollinations_generate.
   _pollinations_generate URL-encodes final_prompt and calls:
   f"https://image.pollinations.ai/prompt/{urllib.parse.quote(final_prompt)}?width=512&height=512&nologo=true"
   Removes any mock/static fallback bytes so genuinely new image stream is fetched.
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

# Replace _pollinations_generate function
new_pollinations_func = '''async def _pollinations_generate(prompt: str) -> bytes:
    """
    Primary image generator via Pollinations.ai (free, zero-token API).
    URL: https://image.pollinations.ai/prompt/{urllib.parse.quote(final_prompt)}?width=512&height=512&nologo=true
    """
    import urllib.parse
    import re
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
    logger.info("Pollinations generate GET -> %s", url)

    async with httpx.AsyncClient(
        timeout=120.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    ) as client:
        for attempt in range(3):
            resp = await client.get(url)
            logger.info("Pollinations response code: %d, size: %d bytes", resp.status_code, len(resp.content))
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content

            # Handle 1 image every 45s rate limit gracefully
            if resp.status_code == 402 and "FREE_LIMIT" in resp.text:
                match = re.search(r"Retry after (\\d+)s", resp.text)
                wait_sec = int(match.group(1)) + 2 if match else 20
                logger.warning("Pollinations rate limit hit. Waiting %ds before retry attempt %d...", wait_sec, attempt + 1)
                await asyncio.sleep(min(wait_sec, 45))
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

# Replace whatever _pollinations_generate was before using a callable repl to avoid backslash escaping issues
service_code = re.sub(
    r'async def _pollinations_generate\(prompt: str\) -> bytes:.*?(?=\nasync def _hf_generate)',
    lambda m: new_pollinations_func + '\n\n',
    service_code,
    flags=re.DOTALL
)

# Replace generate_sketch_image
new_generate_sketch_image = '''async def generate_sketch_image(
    traits: SketchTraits,
    description: str,
    case_id: str,
) -> tuple[str, str]:
    """
    Generate sketch image directly from the concatenated prompt.
    No fallback mock bytes or static image loaders.
    Fetches genuinely new image stream from Pollinations.ai.
    """
    final_prompt = description.strip()
    logger.info("Generating dynamic sketch for final prompt: %s", final_prompt)
    img_bytes = await _pollinations_generate(final_prompt)
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return b64, final_prompt'''

service_code = re.sub(
    r'async def generate_sketch_image\(.*?(?=\nasync def refine_sketch_image)',
    lambda m: new_generate_sketch_image + '\n\n\n',
    service_code,
    flags=re.DOTALL
)

IMAGE_SERVICE.write_text(service_code, encoding="utf-8")
print("[OK] Updated app/services/image_service.py")

# ==============================================================================
# 2. Update app/api/routes/sketch.py
# ==============================================================================
routes_code = SKETCH_ROUTES.read_text(encoding="utf-8")

# Replace generate_sketch implementation
new_generate_sketch_endpoint = '''@router.post(
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
    Extracts description string and active disguises/modification chips.
    Concatenates them into a single descriptive prompt string.
    Fetches real dynamic image directly from Pollinations.ai.
    """
    traits, raw_output = await ai_service.parse_description(body.description)

    # 1. Extract description and iterate through any active disguises or facial chips
    description = (body.description or "").strip()
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

    # 2. Concatenate into a single descriptive prompt string
    if active_disguises:
        final_prompt = f"A forensic police sketch portrait of {description} wearing {', '.join(active_disguises)}"
    else:
        final_prompt = f"A forensic police sketch portrait of {description}"

    # 3. Call image_service to fetch real dynamic image - no static fallback bytes
    raw_b64, prompt_used = await image_service.generate_sketch_image(
        traits=traits,
        description=final_prompt,
        case_id=str(body.case_id) if body.case_id else "default",
    )
    data_uri = f"data:image/jpeg;base64,{raw_b64}" if not raw_b64.startswith("data:") else raw_b64

    return GenerateSketchResponse(
        traits=traits,
        raw_gemini_output=raw_output,
        case_id=body.case_id,
        image_b64=data_uri,
        sketch_url=data_uri,
        sketch_data=data_uri,
        url=data_uri,
        data=data_uri,
    )'''

routes_code = re.sub(
    r'@router\.post\(\s*"/generate-sketch".*?(?=@router\.post\(\s*"/refine-sketch")',
    lambda m: new_generate_sketch_endpoint + '\n\n# ---------------------------------------------------------------------------\n',
    routes_code,
    flags=re.DOTALL
)

# Also update apply_disguise to use the same clean prompt concatenation & dynamic generation
new_apply_disguise_gen = '''    # Build dynamic prompt with updated disguise set
    desc = (body.description or "").strip()
    active_disguises = list(current_traits.disguises)
    if active_disguises:
        final_prompt = f"A forensic police sketch portrait of {desc} wearing {', '.join(active_disguises)}"
    else:
        final_prompt = f"A forensic police sketch portrait of {desc}"

    raw_b64, _ = await image_service.generate_sketch_image(
        traits=current_traits,
        description=final_prompt,
        case_id=str(body.case_id) if body.case_id else "default",
    )
    data_uri = f'data:image/jpeg;base64,{raw_b64}' if not raw_b64.startswith('data:') else raw_b64'''

routes_code = re.sub(
    r'full_description = body\.description or "".*?data_uri = img_b64 or image_service\.get_fallback_sketch_data_uri\(\s*traits=current_traits,\s*description=full_description,\s*\)',
    lambda m: new_apply_disguise_gen,
    routes_code,
    flags=re.DOTALL
)

SKETCH_ROUTES.write_text(routes_code, encoding="utf-8")
print("[OK] Updated app/api/routes/sketch.py")

# ==============================================================================
# 3. Check syntax of both files
# ==============================================================================
py_compile.compile(str(IMAGE_SERVICE), doraise=True)
print("[OK] Syntax check passed: image_service.py")
py_compile.compile(str(SKETCH_ROUTES), doraise=True)
print("[OK] Syntax check passed: sketch.py")
