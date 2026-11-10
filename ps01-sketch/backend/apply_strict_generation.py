from pathlib import Path
import re

# -------------------------------------------------------------
# 1. Update image_service.py
# -------------------------------------------------------------
img_file = Path("app/services/image_service.py")
img_src = img_file.read_text(encoding="utf-8")

# Replace _hf_generate with strict implementation that raises on any error
new_hf_generate = '''def _hf_headers() -> dict[str, str]:
    token = settings.HF_TOKEN
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _hf_generate(prompt: str) -> bytes:
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
        )
'''

gen_pattern = re.compile(r"def _hf_headers\(\) -> dict\[str, str\]:.*?(?=\nasync def _hf_inpaint)", re.DOTALL)
if gen_pattern.search(img_src):
    img_src = gen_pattern.sub(new_hf_generate + "\n\n", img_src)
    print("Replaced _hf_generate in image_service.py with strict version")
else:
    print("Warning: _hf_headers pattern not found in image_service.py")

# Replace generate_sketch_image to strictly call _hf_generate without fallback
new_gen_sketch_img = '''async def generate_sketch_image(
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
    return b64, prompt
'''

gen_img_pattern = re.compile(r"async def generate_sketch_image\(.*?(?=\nasync def refine_sketch_image)", re.DOTALL)
if gen_img_pattern.search(img_src):
    img_src = gen_img_pattern.sub(new_gen_sketch_img + "\n\n", img_src)
    print("Replaced generate_sketch_image in image_service.py with strict version")
else:
    print("Warning: generate_sketch_image pattern not found in image_service.py")

img_file.write_text(img_src, encoding="utf-8")

# -------------------------------------------------------------
# 2. Update sketch.py
# -------------------------------------------------------------
sketch_file = Path("app/api/routes/sketch.py")
sketch_src = sketch_file.read_text(encoding="utf-8")

# In generate_sketch: strictly invoke image_service.generate_sketch_image and raise on error
old_route_pattern = re.compile(
    r"@router\.post\(\s*\"/generate-sketch\".*?return GenerateSketchResponse\(.*?\)\s*except Exception as exc:.*?(?=\n# ---|\n@router\.post)",
    re.DOTALL
)

new_route_code = '''@router.post(
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
    Step 1 of the AI pipeline — initial sketch synthesis.
    Strictly invokes Hugging Face inference. If generation fails, raises the actual error.
    """
    traits, raw_output = await ai_service.parse_description(body.description)

    # Incorporate any explicit active disguise chips sent from frontend
    if body.disguises:
        active_set = set(traits.disguises)
        valid_disguises = {
            "Full Beard", "Mustache", "Wire-Rimmed Glasses",
            "Sunglasses", "Long Hair", "Bald", "Scar/Mark",
        }
        for d in body.disguises:
            if d in valid_disguises:
                active_set.add(d)
        if "Bald" in active_set:
            active_set.discard("Long Hair")
            traits.hair = "bald"
        elif "Long Hair" in active_set:
            traits.hair = "long"
        traits.disguises = sorted(active_set)

    # Combine description and active disguise chips
    full_description = body.description or ""
    if traits.disguises:
        active_str = ", ".join(traits.disguises)
        if not any(d.lower() in full_description.lower() for d in traits.disguises):
            full_description = f"{full_description.rstrip('.')} with {active_str}."

    # STRICT CLOUD INFERENCE: call generate_sketch_image directly
    raw_b64, prompt_used = await image_service.generate_sketch_image(
        traits=traits,
        description=full_description,
        case_id=body.case_id,
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

if old_route_pattern.search(sketch_src):
    sketch_src = old_route_pattern.sub(new_route_code, sketch_src)
    print("Replaced generate_sketch route in sketch.py with strict version")
else:
    print("Warning: old_route_pattern not found in sketch.py")

sketch_file.write_text(sketch_src, encoding="utf-8")

# Check compilation
import py_compile
py_compile.compile(str(img_file), doraise=True)
print("image_service.py compiled OK")
py_compile.compile(str(sketch_file), doraise=True)
print("sketch.py compiled OK")
