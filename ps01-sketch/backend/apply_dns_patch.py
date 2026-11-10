import sys
from pathlib import Path

target = Path("app/services/image_service.py")
content = target.read_text(encoding="utf-8")

# 1. Add DNS patch and update _HF_BASE
dns_block = '''import socket
try:
    import dns.resolver
    _dns_resolver = dns.resolver.Resolver(configure=False)
    _dns_resolver.nameservers = ["8.8.8.8", "1.1.1.1", "172.16.1.1"]
    _dns_cache: dict[str, list[str]] = {}
    _orig_getaddrinfo = socket.getaddrinfo

    def _custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if isinstance(host, str) and ("huggingface.co" in host):
            target_host = "router.huggingface.co" if host == "api-inference.huggingface.co" else host
            if target_host not in _dns_cache:
                try:
                    answers = _dns_resolver.resolve(target_host, "A")
                    _dns_cache[target_host] = [r.address for r in answers]
                    logger.info("Custom DNS resolved %s -> %s", target_host, _dns_cache[target_host])
                except Exception as exc:
                    logger.warning("Custom DNS failed for %s (%s); falling back to system", target_host, exc)
            if target_host in _dns_cache and _dns_cache[target_host]:
                ip = _dns_cache[target_host][0]
                return _orig_getaddrinfo(ip, port, family, type, proto, flags)
        return _orig_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = _custom_getaddrinfo
    logger.info("Custom DNS monkey-patch active for Hugging Face endpoints.")
except Exception as exc:
    logger.warning("Could not initialize dnspython custom resolver: %s", exc)
'''

# Replace _HF_BASE and insert DNS resolver
old_hf_base = '_HF_BASE = "https://api-inference.huggingface.co/models"'
new_hf_base = (
    dns_block
    + '\n# Hugging Face Inference API base (using official router endpoint)\n'
    + '_HF_BASE = "https://router.huggingface.co/hf-inference/models"'
)

if old_hf_base in content:
    content = content.replace(old_hf_base, new_hf_base, 1)
    print("Replaced _HF_BASE and added DNS patch")
elif '_HF_BASE = "https://router.huggingface.co/hf-inference/models"' in content:
    print("_HF_BASE already updated")
else:
    print("Warning: _HF_BASE pattern not found")

# 2. Clean up _hf_generate
hf_gen_code = '''async def _hf_generate(prompt: str) -> bytes:
    """
    Generate an image via Hugging Face Inference API using FLUX.1-schnell.
    Returns raw PNG/JPEG bytes.
    """
    url = f"{_HF_BASE}/{settings.HF_GENERATE_MODEL}"
    full_prompt = (
        f"{prompt}, {_STYLE_POSITIVE}. Official identification headshot portrait photograph."
    )
    payload = {
        "inputs": full_prompt,
        "parameters": {
            "num_inference_steps": 4,      # FLUX schnell is optimised for 1-4 steps
            "guidance_scale": 0.0,         # FLUX doesn't use CFG
            "width": settings.IMAGE_WIDTH,
            "height": settings.IMAGE_HEIGHT,
            "negative_prompt": _STYLE_NEGATIVE,
        },
    }
    logger.info("HF generate request -> %s (%dx%d)", settings.HF_GENERATE_MODEL,
                settings.IMAGE_WIDTH, settings.IMAGE_HEIGHT)
    async with httpx.AsyncClient(timeout=180.0) as client:
        for attempt in range(3):
            logger.info("HF generate attempt %d/3 -> %s", attempt + 1, url)
            resp = await client.post(url, headers=_hf_headers(), json=payload)
            if resp.status_code == 200:
                logger.info("HF generate succeeded, received %d bytes", len(resp.content))
                return resp.content
            if resp.status_code == 503:
                wait = int(resp.headers.get("X-Wait-For-Model", "20"))
                logger.warning("HF model loading; retrying in %ds (attempt %d)", wait, attempt + 1)
                await asyncio.sleep(min(wait, 30))
                continue
            if resp.status_code == 429:
                logger.error("HF rate limit reached: %s", resp.text)
                raise HTTPException(status_code=429, detail="HF API rate limit reached.")
            if resp.status_code in (401, 403):
                logger.error("HF authentication error (%d): %s", resp.status_code, resp.text)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Hugging Face authentication failed ({resp.status_code}): {resp.text}",
                )
            logger.error("HF generate API error %d: %s", resp.status_code, resp.text[:200])
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"HF generate API error {resp.status_code}: {resp.text[:200]}",
            )
    raise HTTPException(status_code=503, detail="HF model unavailable after retries.")
'''

# Find _hf_generate and replace up to _hf_inpaint
import re
gen_pattern = re.compile(r"async def _hf_generate\(prompt: str\) -> bytes:.*?(?=\nasync def _hf_inpaint)", re.DOTALL)
if gen_pattern.search(content):
    content = gen_pattern.sub(hf_gen_code + "\n\n", content)
    print("Replaced _hf_generate cleanly")
else:
    print("Warning: _hf_generate pattern not matched")

target.write_text(content, encoding="utf-8")
print("Target saved successfully")

import py_compile
py_compile.compile(str(target), doraise=True)
print("Syntax compiled OK")
