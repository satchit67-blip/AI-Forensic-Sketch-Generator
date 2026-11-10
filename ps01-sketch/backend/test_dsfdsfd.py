import urllib.request, urllib.error, json

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/generate-sketch',
    data=json.dumps({'description': 'dsfdsfd'}).encode(),
    headers={'Content-Type': 'application/json'},
)

print('Sending request with description=dsfdsfd ...')
try:
    with urllib.request.urlopen(req, timeout=40) as r:
        print('HTTP Status:', r.status)
        data = json.loads(r.read().decode())
        img = data.get('image_b64', '')
        print('Image prefix:', img[:50])
        print('Image length:', len(img))
except urllib.error.HTTPError as e:
    print('HTTP ERROR', e.code)
    print('Error Body:', e.read().decode())
except Exception as e:
    print('Exception:', e)
