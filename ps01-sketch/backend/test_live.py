"""
End-to-end live test of the generate-sketch endpoint via Pollinations.ai.
Exit code 0 = PASS, 1 = FAIL.
"""
import json
import sys
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"


def post(endpoint, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}/api{endpoint}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer demo",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def run():
    passed = 0
    failed = 0

    case_id_1 = str(uuid.uuid4())
    case_id_2 = str(uuid.uuid4())
    case_id_3 = str(uuid.uuid4())

    # -- Test 1: basic description --------------------------------------------
    print("Test 1: POST /api/generate-sketch  description='dsfdsfd'")
    img1 = ""
    try:
        body = post("/generate-sketch", {
            "description": "dsfdsfd",
            "case_id": case_id_1,
            "disguises": []
        })
        img1 = body.get("image_b64", "")
        assert img1.startswith("data:image"), f"Expected data URI, got: {img1[:80]}"
        assert len(img1) > 5000, f"Image too small: {len(img1)} chars"
        print(f"  PASS  image_b64 length: {len(img1)} chars")
        passed += 1
    except Exception as e:
        print(f"  FAIL  {e}")
        failed += 1

    # -- Test 2: different description -> different image ---------------------
    print("Test 2: different description -> different image bytes")
    try:
        body2 = post("/generate-sketch", {
            "description": "tall man with red hair and sharp jaw",
            "case_id": case_id_2,
            "disguises": []
        })
        img2 = body2.get("image_b64", "")
        assert img2.startswith("data:image"), f"Expected data URI, got: {img2[:80]}"
        assert len(img2) > 5000, f"Image too small: {len(img2)} chars"
        assert img2 != img1, "Images must differ for different descriptions!"
        print(f"  PASS  images differ (len1={len(img1)}, len2={len(img2)})")
        passed += 1
    except Exception as e:
        print(f"  FAIL  {e}")
        failed += 1

    # -- Test 3: disguise toggle ----------------------------------------------
    print("Test 3: apply-disguise Mustache -> image updated")
    try:
        body3 = post("/apply-disguise", {
            "name": "Mustache",
            "active": True,
            "case_id": case_id_3,
            "description": "dsfdsfd",
            "current_traits": {
                "jaw": "soft",
                "hair": "short",
                "hair_color": "#2b2b2f",
                "face": 1.0,
                "disguises": []
            },
        })
        img3 = body3.get("image_b64", "")
        assert img3.startswith("data:image"), f"Expected data URI, got: {img3[:80]}"
        assert len(img3) > 5000, f"Image too small: {len(img3)} chars"
        print(f"  PASS  disguise image_b64 length: {len(img3)} chars")
        passed += 1
    except Exception as e:
        print(f"  FAIL  {e}")
        failed += 1

    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    if failed > 0:
        sys.exit(1)
    else:
        print("ALL TESTS PASSED  Live Pollinations.ai image generation working!")
        sys.exit(0)


if __name__ == "__main__":
    run()
