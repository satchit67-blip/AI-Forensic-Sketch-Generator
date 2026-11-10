import sys, io, base64
from pathlib import Path
from PIL import Image

src = Path(r"c:\Anubhav\Hackfest 26'\ps01-sketch\backend\app\static\forensic_sketch_master.png")
dst_backend = Path(r"c:\Anubhav\Hackfest 26'\ps01-sketch\backend\app\static\forensic_master.png")
dst_frontend = Path(r"c:\Anubhav\Hackfest 26'\ps01-sketch\ps01-sketch\public\forensic_master.png")

if src.exists():
    im = Image.open(src).convert("RGB")
    im_resized = im.resize((512, 680), Image.LANCZOS)
    im_resized.save(dst_backend, format="PNG", optimize=True)
    im_resized.save(dst_frontend, format="PNG", optimize=True)
    print("Saved optimized forensic_master.png to both backend and frontend!")
else:
    print("Source image not found:", src)
