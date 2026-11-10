from PIL import Image, ImageDraw, ImageFilter
from pathlib import Path
import io, base64

master_path = Path("app/static/forensic_master.png")
if not master_path.exists():
    print("Master does not exist")
    exit(1)

im = Image.open(master_path).convert("RGBA")
w, h = im.size
print(f"Master image size: {w}x{h}")

# Test overlaying sunglasses
overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)

# Eye level in 512x680: roughly y=260-310, x=150-360
# Sunglasses:
# Left lens
draw.rounded_rectangle([150, 260, 240, 315], radius=12, fill=(20, 20, 22, 235), outline=(10, 10, 10, 255), width=3)
# Right lens
draw.rounded_rectangle([272, 260, 362, 315], radius=12, fill=(20, 20, 22, 235), outline=(10, 10, 10, 255), width=3)
# Bridge
draw.line([(240, 280), (272, 280)], fill=(15, 15, 15, 255), width=4)
# Temples
draw.line([(150, 275), (110, 265)], fill=(15, 15, 15, 255), width=3)
draw.line([(362, 275), (402, 265)], fill=(15, 15, 15, 255), width=3)

# Composite
composite = Image.alpha_composite(im, overlay).convert("RGB")
print("Composite successfully created!")
