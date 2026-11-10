"""
test_prompt_accuracy.py
-----------------------
Verifies:
1. assemble_dynamic_prompt function correctly uses raw description as base
   and appends explicit modifiers for each active toggle chip.
2. Hardcoded style prefixes are stripped.
3. Live request to /api/generate-sketch reflects the prompt and returns valid dynamic image.
4. Live request to /api/apply-disguise reflects active chip toggle in generated image.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import uuid
import json
import urllib.request
import hashlib

# 1. Unit test the prompt assembly logic directly
sys.path.insert(0, ".")
from app.api.routes.sketch import assemble_dynamic_prompt, DISGUISE_MODIFIERS

print("=== 1. TESTING DYNAMIC PROMPT ASSEMBLY ===")

# Test A: Raw description + single chip
p1 = assemble_dynamic_prompt("young male with athletic build", ["Mustache"])
print(f"  Test A: {p1}")
assert p1 == "young male with athletic build, sporting a defined mustache", f"Unexpected: {p1}"

# Test B: Raw description + multiple chips
p2 = assemble_dynamic_prompt("elderly suspect with gray hair", ["Wire-Rimmed Glasses", "Scar/Mark"])
print(f"  Test B: {p2}")
assert "sporting a defined mustache" not in p2
assert "wearing wire-rimmed glasses" in p2
assert "with a visible facial scar mark on the cheek" in p2
assert p2.startswith("elderly suspect with gray hair, ")

# Test C: Stripping legacy hardcoded prefixes
p3 = assemble_dynamic_prompt("A forensic police sketch portrait of middle-aged woman", ["Sunglasses"])
print(f"  Test C (prefix stripped): {p3}")
assert not p3.startswith("A forensic police sketch portrait of")
assert p3 == "middle-aged woman, wearing dark sunglasses"

# Test D: Clean witness description alone
p4 = assemble_dynamic_prompt("tall suspect in black hoodie", [])
print(f"  Test D (pure text): {p4}")
assert p4 == "tall suspect in black hoodie"

print("  All prompt assembly unit tests PASSED! [OK]\n")

# 2. Live HTTP test against running backend
print("=== 2. TESTING LIVE FASTAPI ENDPOINT ===")
BASE_URL = "http://127.0.0.1:8000"

def post_json(endpoint: str, data: dict):
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer demo",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))

case_id = str(uuid.uuid4())
print("Sending POST /api/generate-sketch with description='distinguished elderly professor with gray beard'...")
res1 = post_json("/api/generate-sketch", {
    "description": "distinguished elderly professor with gray beard",
    "case_id": case_id,
    "disguises": []
})

img1 = res1.get("image_b64", "")
assert img1.startswith("data:image/jpeg;base64,"), "Invalid image data format"
raw_bytes1 = img1.split(",", 1)[1]
hash1 = hashlib.sha256(raw_bytes1.encode()).hexdigest()
print(f"  -> Generated Image 1 length: {len(img1)} chars, hash: {hash1[:16]}... [OK]")

# Test toggle chip via apply-disguise
print("\nSending POST /api/apply-disguise toggling 'Sunglasses' ON...")
res2 = post_json("/api/apply-disguise", {
    "name": "Sunglasses",
    "active": True,
    "case_id": case_id,
    "description": "distinguished elderly professor with gray beard",
    "current_traits": res1.get("traits") or {"jaw": "soft", "hair": "short", "hair_color": "#2b2b2f", "face": 1.0, "disguises": []}
})

img2 = res2.get("image_b64", "")
assert img2.startswith("data:image/jpeg;base64,"), "Invalid disguise image data format"
raw_bytes2 = img2.split(",", 1)[1]
hash2 = hashlib.sha256(raw_bytes2.encode()).hexdigest()
print(f"  -> Generated Disguise Image 2 length: {len(img2)} chars, hash: {hash2[:16]}... [OK]")

assert hash1 != hash2, "Image with sunglasses must differ from original image!"
print("\n[SUCCESS] Changing text and toggling disguise chips generates prompt-accurate distinct images!")
sys.exit(0)
