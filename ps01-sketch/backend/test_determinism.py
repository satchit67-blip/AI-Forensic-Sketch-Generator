"""
test_determinism.py
-------------------
Tests:
1. get_deterministic_seed stability and consistency.
2. Identical description requests produce 100% byte-identical images (determinism).
3. Disguise toggles preserve the base seed while modifying prompt layer.
4. Repeated disguise calls yield identical results.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import hashlib
import json
import urllib.request
import uuid

# 1. Test get_deterministic_seed directly
from app.services.image_service import get_deterministic_seed

print("=== 1. TESTING DETERMINISTIC SEED DERIVATION ===")
seed1 = get_deterministic_seed("athletic male suspect with sharp jaw")
seed2 = get_deterministic_seed("athletic male suspect with sharp jaw")
seed3 = get_deterministic_seed("  Athletic Male Suspect with Sharp Jaw  ")
seed4 = get_deterministic_seed("elderly woman with gray hair")

print(f"  Seed for 'athletic male suspect with sharp jaw': {seed1}")
print(f"  Seed for 'elderly woman with gray hair':        {seed4}")

assert seed1 == seed2, f"Seed must be repeatable: {seed1} != {seed2}"
assert seed1 == seed3, f"Seed must be normalized: {seed1} != {seed3}"
assert seed1 != seed4, f"Different descriptions must yield different seeds: {seed1} == {seed4}"
expected_formula = int(hashlib.md5("athletic male suspect with sharp jaw".encode("utf-8")).hexdigest(), 16) % 1000000
assert seed1 == expected_formula, f"Formula match failed: {seed1} != {expected_formula}"
print("  Deterministic seed derivation PASSED [OK]\n")

# 2. Test live backend determinism
print("=== 2. TESTING REPEATABLE BACKEND GENERATION ===")
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

desc = "athletic male suspect with sharp jaw"

print(f"1st Generation for: '{desc}'...")
res1 = post_json("/api/generate-sketch", {
    "description": desc,
    "case_id": str(uuid.uuid4()),
    "disguises": []
})
img1 = res1.get("image_b64", "")
hash1 = hashlib.sha256(img1.encode()).hexdigest()
print(f"  -> Image 1 SHA256: {hash1[:16]}... (length={len(img1)})")

print(f"\n2nd Generation for IDENTICAL prompt: '{desc}'...")
res2 = post_json("/api/generate-sketch", {
    "description": desc,
    "case_id": str(uuid.uuid4()),
    "disguises": []
})
img2 = res2.get("image_b64", "")
hash2 = hashlib.sha256(img2.encode()).hexdigest()
print(f"  -> Image 2 SHA256: {hash2[:16]}... (length={len(img2)})")

assert hash1 == hash2, f"FAILED: Identical descriptions must produce identical images!\nhash1={hash1}\nhash2={hash2}"
print("  -> DETERMINISM CONFIRMED: Image 1 and Image 2 are 100% byte-for-byte IDENTICAL! [OK]\n")

# 3. Test disguise toggle
print("=== 3. TESTING DISGUISE TOGGLE WITH ANCHORED SEED ===")
print("Applying disguise 'Mustache' to suspect...")
res_disguise_1 = post_json("/api/apply-disguise", {
    "name": "Mustache",
    "active": True,
    "case_id": str(uuid.uuid4()),
    "description": desc,
    "current_traits": res1.get("traits") or {"jaw": "sharp", "hair": "short", "hair_color": "#2b2b2f", "face": 1.0, "disguises": []}
})
img_d1 = res_disguise_1.get("image_b64", "")
hash_d1 = hashlib.sha256(img_d1.encode()).hexdigest()
print(f"  -> Disguise Image SHA256: {hash_d1[:16]}... (length={len(img_d1)})")
assert hash_d1 != hash1, "Disguise image must reflect the new facial modifier"

print("\nRe-requesting same disguise to verify stability...")
res_disguise_2 = post_json("/api/apply-disguise", {
    "name": "Mustache",
    "active": True,
    "case_id": str(uuid.uuid4()),
    "description": desc,
    "current_traits": res1.get("traits") or {"jaw": "sharp", "hair": "short", "hair_color": "#2b2b2f", "face": 1.0, "disguises": []}
})
img_d2 = res_disguise_2.get("image_b64", "")
hash_d2 = hashlib.sha256(img_d2.encode()).hexdigest()
print(f"  -> Re-requested Disguise SHA256: {hash_d2[:16]}... (length={len(img_d2)})")
assert hash_d1 == hash_d2, "Disguise generation must also be 100% repeatable!"

print("\n========================================================")
print("ALL DETERMINISM & REPEATABILITY TESTS PASSED! (Exit 0)")
print("========================================================")
sys.exit(0)
