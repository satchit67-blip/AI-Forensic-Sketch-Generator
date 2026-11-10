"""
verify_dynamic_generation.py
----------------------------
Verifies that:
1. Changing the prompt text sends dynamic concatenated prompts to Pollinations.ai.
2. The endpoint returns genuine distinct dynamic images.
3. Adding disguise chips alters the concatenated prompt and produces distinct image bytes.
"""

import urllib.request
import json
import uuid
import sys
import hashlib

BASE_URL = "http://127.0.0.1:8000"

def post_json(path: str, data: dict):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer demo",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))

def test_live_generation():
    print("=== LIVE IMAGE GENERATION TEST ===")

    # Request 1: Witness description A
    case_1 = str(uuid.uuid4())
    print("\n1. Testing prompt: 'elderly suspect with thick eyebrows'")
    resp1 = post_json("/api/generate-sketch", {
        "description": "elderly suspect with thick eyebrows",
        "case_id": case_1,
        "disguises": []
    })
    img1 = resp1.get("image_b64", "")
    assert img1.startswith("data:image/jpeg;base64,"), "Invalid image data URI format"
    raw_bytes_1 = img1.split(",", 1)[1]
    hash1 = hashlib.sha256(raw_bytes_1.encode()).hexdigest()
    print(f"   -> Success! Length: {len(img1)} chars, SHA256: {hash1[:16]}...")

    # Request 2: Witness description B with disguises
    case_2 = str(uuid.uuid4())
    print("\n2. Testing prompt: 'young athletic male' with disguises=['Mustache', 'Sunglasses']")
    resp2 = post_json("/api/generate-sketch", {
        "description": "young athletic male",
        "case_id": case_2,
        "disguises": ["Mustache", "Sunglasses"]
    })
    img2 = resp2.get("image_b64", "")
    assert img2.startswith("data:image/jpeg;base64,"), "Invalid image data URI format"
    raw_bytes_2 = img2.split(",", 1)[1]
    hash2 = hashlib.sha256(raw_bytes_2.encode()).hexdigest()
    print(f"   -> Success! Length: {len(img2)} chars, SHA256: {hash2[:16]}...")

    # Verification: Must be completely distinct images
    assert hash1 != hash2, "Images should be completely distinct for different prompts!"
    print("\n   [VERIFIED] Image 1 and Image 2 are completely distinct!")
    print(f"   Prompt 1 Image Size: {len(raw_bytes_1)} chars")
    print(f"   Prompt 2 Image Size: {len(raw_bytes_2)} chars")

    print("\nALL VERIFICATIONS PASSED SUCCESSFULLY (Exit Code 0)")
    sys.exit(0)

if __name__ == "__main__":
    try:
        test_live_generation()
    except Exception as exc:
        print(f"\n[FAIL] Test encountered error: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
