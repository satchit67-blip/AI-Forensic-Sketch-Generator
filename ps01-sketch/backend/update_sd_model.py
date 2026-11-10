from pathlib import Path
import re

target = Path("app/services/image_service.py")
content = target.read_text(encoding="utf-8")

new_hf_code = '''def _hf_headers() -> dict[str, str]:
    token = settings.HF_TOKEN
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _hf_generate(prompt: str) -> bytes:
    """
    Generate an image via Hugging Face Inference API using Stable Diffusion.
    Returns raw JPEG bytes.
    """
    url = f"{_HF_BASE}/{settings.HF_GENERATE_MODEL}"
    full_prompt = (
        f"{prompt}, {_STYLE_POSITIVE}. Official identification headshot portrait photograph."
    )
    payload = {
        "inputs": full_prompt,
        "parameters": {
            "num_inference_steps": 25,
            "guidance_scale": 7.5,
            "width": settings.IMAGE_WIDTH,
            "height": settings.IMAGE_HEIGHT,
            "negative_prompt": _STYLE_NEGATIVE,
        },
    }
    logger.info("HF generate request -> %s (%dx%d)", settings.HF_GENERATE_MODEL,
                settings.IMAGE_WIDTH, settings.IMAGE_HEIGHT)

    # 1. Attempt direct HTTP request to Hugging Face router
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=_hf_headers(), json=payload)
            if resp.status_code == 200:
                logger.info("HF direct generate succeeded (%d bytes)", len(resp.content))
                return resp.content
            logger.warning("HF direct returned %d: %s", resp.status_code, resp.text[:120])
    except Exception as exc:
        logger.warning("HF direct HTTP attempt failed: %s", exc)

    # 2. Attempt InferenceClient
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(api_key=settings.HF_TOKEN)
        img = await asyncio.to_thread(client.text_to_image, full_prompt, model=settings.HF_GENERATE_MODEL)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        logger.info("HuggingFace InferenceClient generated image successfully")
        return buf.getvalue()
    except Exception as exc:
        logger.warning("HF InferenceClient attempt failed: %s", exc)
        raise
'''

gen_pattern = re.compile(r"def _hf_inference_client_sync\(prompt: str\) -> bytes:.*?(?=\nasync def _hf_inpaint)", re.DOTALL)
if gen_pattern.search(content):
    content = gen_pattern.sub(new_hf_code + "\n\n", content)
    print("Replaced _hf_generate cleanly")
else:
    print("Warning: _hf_inference_client_sync pattern not found")

target.write_text(content, encoding="utf-8")
print("Target saved successfully")

import py_compile
py_compile.compile(str(target), doraise=True)
print("Syntax compiled OK")
