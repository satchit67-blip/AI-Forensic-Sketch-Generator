"""
Patch _hf_generate() in image_service.py:
  - Removes the outer try/except so raw exceptions surface in the terminal
  - Adds print() debug lines before/after every HTTP call
"""
import re
from pathlib import Path

f = Path("app/services/image_service.py")
src = f.read_text(encoding="utf-8")

pattern = re.compile(
    r"async def _hf_generate\(prompt: str\) -> bytes:.*?"
    r"raise HTTPException\(status_code=503, detail=\"HF model unavailable after retries\.\"\)",
    re.DOTALL,
)

replacement = (
    'async def _hf_generate(prompt: str) -> bytes:\n'
    '    """\n'
    '    Generate an image via Hugging Face Inference API using FLUX.1-schnell.\n'
    '    Returns raw PNG bytes.\n'
    '    DEBUG MODE: try/except removed so raw errors surface in the terminal.\n'
    '    """\n'
    '    url = f"{_HF_BASE}/{settings.HF_GENERATE_MODEL}"\n'
    '    full_prompt = (\n'
    '        f"{prompt}, {_STYLE_POSITIVE}. Official identification headshot portrait photograph."\n'
    '    )\n'
    '    payload = {\n'
    '        "inputs": full_prompt,\n'
    '        "parameters": {\n'
    '            "num_inference_steps": 4,\n'
    '            "guidance_scale": 0.0,\n'
    '            "width": settings.IMAGE_WIDTH,\n'
    '            "height": settings.IMAGE_HEIGHT,\n'
    '            "negative_prompt": _STYLE_NEGATIVE,\n'
    '        },\n'
    '    }\n'
    '    tok = settings.HF_TOKEN or ""\n'
    '    masked_tok = tok[:12] + "..." + tok[-4:] if len(tok) > 16 else repr(tok)\n'
    '    sep = "=" * 70\n'
    '    print(f"\\n{sep}")\n'
    '    print(f"[HF DEBUG] URL        : {url}")\n'
    '    print(f"[HF DEBUG] TOKEN      : {masked_tok}")\n'
    '    print(f"[HF DEBUG] PROMPT     : {full_prompt[:200]}")\n'
    '    print(f"[HF DEBUG] SIZE       : {settings.IMAGE_WIDTH}x{settings.IMAGE_HEIGHT}")\n'
    '    print(f"{sep}\\n")\n'
    '    logger.info("HF generate request -> %s (%dx%d)", settings.HF_GENERATE_MODEL,\n'
    '                settings.IMAGE_WIDTH, settings.IMAGE_HEIGHT)\n'
    '    # NO try/except - let every exception crash visibly into the terminal\n'
    '    async with httpx.AsyncClient(timeout=180.0) as client:\n'
    '        for attempt in range(3):\n'
    '            print(f"[HF DEBUG] Attempt {attempt + 1}/3 - POST {url}")\n'
    '            resp = await client.post(url, headers=_hf_headers(), json=payload)\n'
    '            print(f"[HF DEBUG] Status  : {resp.status_code}")\n'
    '            print(f"[HF DEBUG] Headers : {dict(resp.headers)}")\n'
    '            print(f"[HF DEBUG] Body    : {resp.text[:512]!r}")\n'
    '            print()\n'
    '            if resp.status_code == 200:\n'
    '                print(f"[HF DEBUG] SUCCESS - {len(resp.content)} bytes received")\n'
    '                return resp.content\n'
    '            if resp.status_code == 503:\n'
    '                wait = int(resp.headers.get("X-Wait-For-Model", "20"))\n'
    '                print(f"[HF DEBUG] 503 model loading - sleeping {min(wait, 30)}s")\n'
    '                logger.warning("HF model loading; retrying in %ds (attempt %d)", wait, attempt + 1)\n'
    '                await asyncio.sleep(min(wait, 30))\n'
    '                continue\n'
    '            raise RuntimeError(\n'
    '                f"[HF DEBUG] FATAL status={resp.status_code}\\n"\n'
    '                f"Headers: {dict(resp.headers)}\\n"\n'
    '                f"Body: {resp.text}"\n'
    '            )\n'
    '    raise RuntimeError("[HF DEBUG] FATAL - model unavailable after 3 retries")'
)

new_src, n = pattern.subn(replacement, src)
if n == 0:
    print("ERROR: pattern not found - no changes made")
else:
    f.write_text(new_src, encoding="utf-8")
    print(f"OK: patched {n} occurrence(s) of _hf_generate()")
