import urllib.request, json, sys

# 1. Health check
try:
    health = urllib.request.urlopen('http://127.0.0.1:8000/healthz').read().decode()
    print('HEALTH:', health)
except Exception as e:
    print('HEALTH FAIL:', e); sys.exit(1)

# 2. Gibberish input
req1 = urllib.request.Request('http://127.0.0.1:8000/api/generate-sketch',
    data=json.dumps({'description': 'dsdsad gibberish'}).encode(),
    headers={'Content-Type': 'application/json'})
d1 = json.loads(urllib.request.urlopen(req1).read().decode())
img1 = d1.get('image_b64', '')
print(f'Input 1 (gibberish): HTTP 200, image_b64 len={len(img1)}, prefix={img1[:35]}')

# 3. Distinctive real description
req2 = urllib.request.Request('http://127.0.0.1:8000/api/generate-sketch',
    data=json.dumps({'description': 'old man sharp jaw full beard sunglasses'}).encode(),
    headers={'Content-Type': 'application/json'})
d2 = json.loads(urllib.request.urlopen(req2).read().decode())
img2 = d2.get('image_b64', '')
print(f'Input 2 (old man beard): HTTP 200, image_b64 len={len(img2)}, prefix={img2[:35]}')

# 4. Assert distinctness
assert img1 and img2, 'Both images must be non-empty!'
assert img1 != img2, 'FAIL: Both inputs returned the same image!'
print('PASS: distinct inputs -> distinct images')

# 5. Check MIME prefix
assert img1.startswith('data:image/jpeg'), f'MIME type mismatch: got {img1[:40]}'
print('PASS: MIME type is data:image/jpeg')

# 6. Apply-disguise endpoint
req3 = urllib.request.Request('http://127.0.0.1:8000/api/apply-disguise',
    data=json.dumps({'description': 'tall man medium build', 'disguise': 'Full Beard', 'disguises': ['Full Beard']}).encode(),
    headers={'Content-Type': 'application/json'})
d3 = json.loads(urllib.request.urlopen(req3).read().decode())
img3 = d3.get('image_b64', '')
print(f'Apply-disguise (Full Beard): HTTP 200, image_b64 len={len(img3)}')
assert img3 and img3 != img1, 'FAIL: Disguise image must differ from base!'
print('PASS: disguise produces distinct image')

print()
print('=== ALL CHECKS PASSED ===')
