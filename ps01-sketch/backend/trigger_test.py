"""
HF API connectivity test — full CNAME-following DNS resolver + httpx with patched socket.
"""
import asyncio, socket, struct, os, httpx

HF_HOST  = "api-inference.huggingface.co"
HF_TOKEN = os.environ.get("HF_TOKEN", "")
MODEL    = "black-forest-labs/FLUX.1-schnell"
URL      = f"https://{HF_HOST}/models/{MODEL}"

def decode_name(resp, pos):
    """Decode a DNS name (with pointer compression support). Returns (name, new_pos)."""
    parts, jumped, jump_pos = [], False, 0
    while True:
        length = resp[pos]
        if length & 0xC0 == 0xC0:           # pointer
            if not jumped: jump_pos = pos + 2
            pos = ((length & 0x3F) << 8) | resp[pos + 1]
            jumped = True
        elif length == 0:                   # end of name
            if not jumped: pos += 1
            break
        else:
            pos += 1
            parts.append(resp[pos:pos + length].decode("ascii", errors="replace"))
            pos += length
    return ".".join(parts), (jump_pos if jumped else pos)

def raw_dns_resolve_full(hostname, dns_ip, timeout=5.0):
    """Resolve hostname via UDP DNS to dns_ip, following CNAME chains. Returns list of IPs."""
    qid = os.getpid() & 0xFFFF
    header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(p)]) + p.encode() for p in hostname.split(".")) + b"\x00"
    packet = header + qname + struct.pack(">HH", 1, 1)   # QTYPE=A, QCLASS=IN

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(packet, (dns_ip, 53))
        resp = sock.recv(4096)
    finally:
        sock.close()

    # Skip header
    qdcount = struct.unpack(">H", resp[4:6])[0]
    ancount = struct.unpack(">H", resp[6:8])[0]
    pos = 12
    # Skip question section
    for _ in range(qdcount):
        _, pos = decode_name(resp, pos)
        pos += 4   # QTYPE + QCLASS

    ips = []
    for _ in range(ancount):
        _, pos = decode_name(resp, pos)
        rtype, rclass, ttl, rdlen = struct.unpack(">HHIH", resp[pos:pos+10]); pos += 10
        rdata = resp[pos:pos+rdlen]; pos += rdlen
        if rtype == 1 and rdlen == 4:                         # A record
            ips.append(".".join(str(b) for b in rdata))
        elif rtype == 5:                                       # CNAME
            cname, _ = decode_name(resp, pos - rdlen)
    return ips


DNS_SERVERS = ["8.8.8.8", "1.1.1.1", "172.16.1.1", "10.10.0.1"]

print(f"Resolving {HF_HOST} (with CNAME following) ...")
resolved_ips, working_dns = [], None
for dns in DNS_SERVERS:
    try:
        ips = raw_dns_resolve_full(HF_HOST, dns, timeout=4.0)
        print(f"  {dns} -> {ips if ips else 'no A records'}")
        if ips and not resolved_ips:
            resolved_ips, working_dns = ips, dns
    except Exception as e:
        print(f"  {dns} -> ERROR: {type(e).__name__}: {e}")

if not resolved_ips:
    print("\nAll DNS servers returned no A records. Trying system resolver ...")
    try:
        info = socket.getaddrinfo(HF_HOST, 443, proto=socket.IPPROTO_TCP)
        resolved_ips = list({i[4][0] for i in info})
        print(f"  System -> {resolved_ips}")
    except Exception as e:
        print(f"  System -> FAILED: {e}")

if not resolved_ips:
    print("\nNo DNS resolution possible. Cannot reach HF API.")
    raise SystemExit(1)

print(f"\nIP resolved: {resolved_ips} (via {working_dns or 'system'})")

# Patch getaddrinfo so httpx uses the resolved IP
_orig = socket.getaddrinfo
def _patched(host, port, *a, **kw):
    if host == HF_HOST:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved_ips[0], port or 443))]
    return _orig(host, port, *a, **kw)
socket.getaddrinfo = _patched

async def main():
    print(f"\nPOST {URL}  (routed to {resolved_ips[0]})")
    print(f"Token : {HF_TOKEN[:12]}...{HF_TOKEN[-4:]}")
    print("-" * 60)
    payload = {
        "inputs": "photorealistic portrait, South Asian male, sharp jaw",
        "parameters": {"num_inference_steps": 1, "guidance_scale": 0.0, "width": 64, "height": 64},
    }
    hdrs = {"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            resp = await client.post(URL, headers=hdrs, json=payload)
        print(f"Status  : {resp.status_code}")
        print(f"Headers : {dict(resp.headers)}")
        if resp.status_code == 200:
            print(f"\nSUCCESS! {len(resp.content)} bytes of image data received.")
        elif resp.status_code == 503:
            print(f"Body: {resp.text[:400]}")
            print("\n503 - Model loading. Network + auth are OK.")
        else:
            print(f"Body: {resp.text[:800]}")
    except Exception as e:
        print(f"\n{type(e).__name__}: {e}")

asyncio.run(main())
