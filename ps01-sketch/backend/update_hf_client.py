from pathlib import Path
import re

target = Path("app/services/image_service.py")
content = target.read_text(encoding="utf-8")

# 1. Update _hf_generate to use InferenceClient
new_hf_code = '''def _hf_inference_client_sync(prompt: str) -> bytes:
    from huggingface_hub import InferenceClient
    client = InferenceClient(api_key=settings.HF_TOKEN)
    full_prompt = (
        f"{prompt}, {_STYLE_POSITIVE}. Official identification headshot portrait photograph."
    )
    img = client.text_to_image(
        full_prompt,
        model=settings.HF_GENERATE_MODEL,
    )
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


async def _hf_generate(prompt: str) -> bytes:
    """
    Generate an image via Hugging Face Inference API using FLUX.1-schnell.
    Returns raw PNG/JPEG bytes.
    """
    logger.info("Calling Hugging Face InferenceClient for model: %s", settings.HF_GENERATE_MODEL)
    return await asyncio.to_thread(_hf_inference_client_sync, prompt)
'''

gen_pattern = re.compile(r"def _hf_headers\(\) -> dict\[str, str\]:.*?(?=\nasync def _hf_inpaint)", re.DOTALL)
if gen_pattern.search(content):
    content = gen_pattern.sub(new_hf_code + "\n\n", content)
    print("Replaced _hf_generate with InferenceClient integration")
else:
    print("Warning: _hf_headers pattern not found")

# 2. Update generate_sketch_image so it gracefully creates dynamic forensic sketch on error
old_try_block = '''    try:
        if _MODE == ImageMode.HF_API:
            img_bytes = await _hf_generate(prompt)
        else:  # LOCAL
            img_bytes = await asyncio.to_thread(_local_generate_sync, prompt)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Image generation backend error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Image generation failed: {exc}",
        )'''

new_try_block = '''    try:
        if _MODE == ImageMode.HF_API:
            img_bytes = await _hf_generate(prompt)
        else:  # LOCAL
            img_bytes = await asyncio.to_thread(_local_generate_sync, prompt)
    except Exception as exc:
        logger.warning("Cloud generation unavailable (%s); generating dynamic forensic portrait composite", exc)
        safe_traits = traits or SketchTraits()
        img_bytes = generate_dynamic_forensic_sketch(
            description=description,
            jaw=safe_traits.jaw,
            hair=safe_traits.hair,
            hair_color=safe_traits.hair_color,
            face_scale=safe_traits.face,
            disguises=list(safe_traits.disguises),
        )'''

if old_try_block in content:
    content = content.replace(old_try_block, new_try_block, 1)
    print("Updated generate_sketch_image try block")
else:
    print("Warning: old_try_block pattern not found")

target.write_text(content, encoding="utf-8")
print("Target saved successfully")

import py_compile
py_compile.compile(str(target), doraise=True)
print("Syntax compiled OK")
