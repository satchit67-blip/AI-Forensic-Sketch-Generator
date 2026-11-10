import urllib.request, json

req = urllib.request.Request("http://127.0.0.1:8000/openapi.json", method="GET")
with urllib.request.urlopen(req, timeout=10) as resp:
    api = json.loads(resp.read())

schemas = api.get("components", {}).get("schemas", {})
for name in schemas:
    if "Generate" in name and "Request" in name:
        print(f"\n{name}:")
        print(json.dumps(schemas[name], indent=2)[:1000])
