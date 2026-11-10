from PIL import Image, ImageDraw, ImageFilter
from pathlib import Path
import io, base64

def draw_disguises(img: Image.Image, disguises: list[str]) -> Image.Image:
    if not disguises:
        return img
    
    rgba = img.convert("RGBA")
    w, h = rgba.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # 1. Full Beard
    if "Full Beard" in disguises:
        # Beard contour covering lower jaw and chin
        d.chord([160, 390, 352, 540], start=0, end=180, fill=(28, 26, 30, 215))
        # Stippled sideburns connecting to jaw
        d.polygon([(160, 350), (180, 450), (160, 480)], fill=(32, 30, 34, 190))
        d.polygon([(352, 350), (332, 450), (352, 480)], fill=(32, 30, 34, 190))

    # 2. Mustache
    if "Mustache" in disguises or "Full Beard" in disguises:
        d.chord([205, 398, 307, 432], start=0, end=180, fill=(25, 23, 27, 235))

    # 3. Sunglasses
    if "Sunglasses" in disguises:
        # Dark tinted lenses
        d.rounded_rectangle([152, 268, 242, 322], radius=10, fill=(18, 18, 20, 245), outline=(10, 10, 12, 255), width=3)
        d.rounded_rectangle([270, 268, 360, 322], radius=10, fill=(18, 18, 20, 245), outline=(10, 10, 12, 255), width=3)
        # Bridge
        d.line([(242, 288), (270, 288)], fill=(12, 12, 14, 255), width=4)
        # Temples
        d.line([(152, 284), (112, 272)], fill=(12, 12, 14, 255), width=3)
        d.line([(360, 284), (400, 272)], fill=(12, 12, 14, 255), width=3)
        # Specular white reflection lines
        d.line([(165, 276), (185, 286)], fill=(255, 255, 255, 90), width=2)
        d.line([(283, 276), (303, 286)], fill=(255, 255, 255, 90), width=2)

    # 4. Wire-Rimmed Glasses
    elif "Wire-Rimmed Glasses" in disguises:
        d.ellipse([156, 266, 242, 324], outline=(38, 36, 40, 230), width=3)
        d.ellipse([270, 266, 356, 324], outline=(38, 36, 40, 230), width=3)
        d.line([(242, 290), (270, 290)], fill=(38, 36, 40, 240), width=3)
        d.line([(156, 285), (112, 274)], fill=(38, 36, 40, 230), width=2)
        d.line([(356, 285), (400, 274)], fill=(38, 36, 40, 230), width=2)

    # 5. Scar/Mark
    if "Scar/Mark" in disguises:
        d.line([(318, 325), (328, 365), (322, 410)], fill=(80, 35, 35, 220), width=3)
        d.line([(314, 345), (326, 343)], fill=(160, 120, 120, 180), width=1)
        d.line([(324, 385), (334, 383)], fill=(160, 120, 120, 180), width=1)

    # 6. Long Hair
    if "Long Hair" in disguises:
        d.rectangle([110, 220, 155, 520], fill=(28, 26, 30, 210))
        d.rectangle([357, 220, 402, 520], fill=(28, 26, 30, 210))

    # Soften overlay slightly for charcoal sketch integration
    overlay_blurred = overlay.filter(ImageFilter.GaussianBlur(radius=0.6))
    return Image.alpha_composite(rgba, overlay_blurred).convert("RGB")

# Test with forensic_master.png
master_path = Path("app/static/forensic_master.png")
if master_path.exists():
    im = Image.open(master_path)
    res = draw_disguises(im, ["Full Beard", "Sunglasses", "Scar/Mark"])
    print("Overlay test passed successfully. Dimensions:", res.size)
else:
    print("Master path does not exist yet")
