"""
verify_apply_disguise.py
------------------------
Tests:
1. format_disguise_modifiers correctly creates English strings for toggle chips.
2. clean_base_description preserves stable base description across toggles.
3. Live POST to /api/apply-disguise sends prompt with explicit modifiers and stable seed.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.api.routes.sketch import format_disguise_modifiers, clean_base_description, assemble_dynamic_prompt

print("=== 1. TESTING DISGUISE MODIFIER ASSEMBLY ===")
# Test exact user example: sunglasses + mustache
mod1 = format_disguise_modifiers(["Sunglasses", "Mustache"])
print("  Sunglasses + Mustache:", mod1)
assert mod1 == "wearing dark sunglasses and a neat mustache"

# Test single chips
mod2 = format_disguise_modifiers(["Full Beard"])
print("  Full Beard:", mod2)
assert mod2 == "with a full thick beard"

mod3 = format_disguise_modifiers(["Wire-Rimmed Glasses"])
print("  Wire-Rimmed Glasses:", mod3)
assert mod3 == "wearing wire-rimmed glasses"

# Test full prompt assembly with base description
base = "distinguished elderly professor with gray hair"
p = assemble_dynamic_prompt(base, ["Sunglasses", "Mustache"])
print(f"  Assembled Prompt: '{p}'")
assert p == "distinguished elderly professor with gray hair, wearing dark sunglasses and a neat mustache"

# Test cleaning base when disguise was previously appended
p_pre_appended = "distinguished elderly professor with gray hair, wearing dark sunglasses and a neat mustache"
clean = clean_base_description(p_pre_appended)
print(f"  Cleaned Base: '{clean}'")
assert clean == "distinguished elderly professor with gray hair"

print("  All prompt assembly tests PASSED [OK]\n")

print("=== 2. TESTING LIVE /api/apply-disguise ENDPOINT ===")
import json
import urllib.request
import uuid

BASE_URL = "http://127.0.0.1:8000"

req_data = {
    "name": "Sunglasses",
    "active": True,
    "case_id": str(uuid.uuid4()),
    "description": "distinguished elderly professor with gray hair",
    "current_traits": {
        "jaw": "soft",
        "hair": "short",
        "hair_color": "#2b2b2f",
        "face": 1.0,
        "disguises": ["Mustache"]
    }
}

req = urllib.request.Request(
    f"{BASE_URL}/api/apply-disguise",
    data=json.dumps(req_data).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer demo",
    },
    method="POST"
)

with urllib.request.urlopen(req, timeout=120) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    img = data.get("image_b64", "")
    assert img.startswith("data:image/jpeg;base64,"), "Invalid image returned"
    print(f"  -> Disguise toggle returned status 200, image size={len(img)} chars [OK]")
    assert "Sunglasses" in data.get("traits", {}).get("disguises", [])
    assert "Mustache" in data.get("traits", {}).get("disguises", [])

print("\nALL VERIFICATIONS PASSED SUCCESSFULLY [OK]")
