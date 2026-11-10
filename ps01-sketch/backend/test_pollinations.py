"""Quick test of Pollinations.ai image generation endpoint."""
import asyncio
import hashlib
import sys
import urllib.parse

import httpx


async def test_pollinations():
    prompt = "forensic portrait, South Asian male, dsfdsfd description"
    encoded = urllib.parse.quote(prompt, safe="")
    seed = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16) % 2147483647
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=512&height=640&model=turbo&nologo=true&seed={seed}"
    )
    print(f"Testing Pollinations.ai turbo model...")
    print(f"URL: {url[:120]}")
    async with httpx.AsyncClient(
        timeout=90.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ForensicSketch/1.0)"},
    ) as client:
        resp = await client.get(url)
    print(f"Status: {resp.status_code}")
    print(f"Content-Length: {len(resp.content)} bytes")
    ct = resp.headers.get("content-type", "unknown")
    print(f"Content-Type: {ct}")
    if resp.status_code == 200 and len(resp.content) > 1000:
        print("SUCCESS: Pollinations returned a valid image!")
        return True
    else:
        print(f"FAILED: {resp.text[:300]}")
        return False


async def test_dynamic_fallback():
    """Test the dynamic forensic sketch synthesizer directly."""
    import sys
    sys.path.insert(0, ".")
    # We need to mock settings minimally
    import os
    os.environ.setdefault("IMAGE_MODE", "hf_api")
    os.environ.setdefault("HF_TOKEN", os.environ.get("HF_TOKEN", "mock_hf_token"))
    os.environ.setdefault("GEMINI_API_KEY", "dummy")
    os.environ.setdefault("HF_GENERATE_MODEL", "stabilityai/stable-diffusion-2-1")
    os.environ.setdefault("HF_INPAINT_MODEL", "stabilityai/stable-diffusion-2-inpainting")
    os.environ.setdefault("IMAGE_WIDTH", "512")
    os.environ.setdefault("IMAGE_HEIGHT", "640")
    os.environ.setdefault("IMAGE_STORE_PATH", "/tmp/sketches")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    os.environ.setdefault("JWT_SECRET", "test-secret")

    from app.services.image_service import generate_dynamic_forensic_sketch
    b1 = generate_dynamic_forensic_sketch(description="dsfdsfd", jaw="soft", hair="short",
                                           hair_color="#2b2b2f", face_scale=1.0, disguises=[])
    b2 = generate_dynamic_forensic_sketch(description="tall man with beard", jaw="sharp", hair="long",
                                           hair_color="#4a3426", face_scale=1.0, disguises=["Full Beard"])
    b3 = generate_dynamic_forensic_sketch(description="dsfdsfd", jaw="soft", hair="short",
                                           hair_color="#2b2b2f", face_scale=1.0, disguises=["Sunglasses"])
    print(f"\nDynamic fallback test:")
    print(f"  b1 (dsfdsfd clean):   {len(b1)} bytes")
    print(f"  b2 (beard tall man):  {len(b2)} bytes")
    print(f"  b3 (dsfdsfd + shades):{len(b3)} bytes")
    assert b1 != b2, "b1 and b2 must differ!"
    assert b1 != b3, "b1 and b3 must differ!"
    print("  All distinct: OK")
    return True


if __name__ == "__main__":
    poll_ok = asyncio.run(test_pollinations())
    dyn_ok = asyncio.run(test_dynamic_fallback())
    print(f"\n=== Results ===")
    print(f"  Pollinations.ai: {'PASS' if poll_ok else 'FAIL (will use dynamic fallback)'}")
    print(f"  Dynamic fallback: {'PASS' if dyn_ok else 'FAIL'}")
    sys.exit(0 if dyn_ok else 1)
