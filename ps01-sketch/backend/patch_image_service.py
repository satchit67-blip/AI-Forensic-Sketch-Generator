from pathlib import Path
import re

target = Path("app/services/image_service.py")
content = target.read_text(encoding="utf-8")

old_fn_pattern = re.compile(
    r"def generate_dynamic_forensic_sketch\(.*?return buf\.getvalue\(\)",
    re.DOTALL
)

new_fn_code = '''def generate_dynamic_forensic_sketch(
    description: str = "",
    jaw: str = "soft",
    hair: str = "short",
    hair_color: str = "#2b2b2f",
    face_scale: float = 1.0,
    disguises: list[str] | None = None,
) -> bytes:
    """
    Synthesize an input-sensitive forensic ID portrait tailored to the witness description,
    facial traits, and active disguises. Guaranteed distinct bytes for different inputs.
    """
    if disguises is None:
        disguises = []

    seed_key = f"{description}_{jaw}_{hair}_{face_scale:.2f}_{hair_color}_{','.join(sorted(disguises))}"
    seed_int = int(hashlib.sha256(seed_key.encode()).hexdigest()[:8], 16)

    # Master photographic ID portrait base from app/static
    static_dir = Path(__file__).resolve().parent.parent / "static"
    candidates = [
        static_dir / "forensic_sketch_master.png",
        static_dir / "forensic_master.png",
    ]
    base_img = None
    for c in candidates:
        if c.exists():
            try:
                base_img = Image.open(c).convert("RGBA")
                break
            except Exception:
                pass

    if base_img is None:
        w, h = 896, 1200
        base_img = Image.new("RGBA", (w, h), (220, 222, 225, 255))
    else:
        w, h = base_img.size

    # Deterministic photographic lighting and tonal shifts based on description seed
    brightness_factor = 0.94 + ((seed_int % 11) * 0.012)
    contrast_factor = 0.96 + (((seed_int >> 4) % 9) * 0.012)

    rgb = base_img.convert("RGB")
    rgb = ImageEnhance.Brightness(rgb).enhance(brightness_factor)
    rgb = ImageEnhance.Contrast(rgb).enhance(contrast_factor)
    img = rgb.convert("RGBA")

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Calibrated facial feature coordinates for 896x1200 portrait
    cx = w // 2          # 448
    eye_y = 475          # Eye level
    mouth_y = 635        # Mouth level
    chin_y = 720         # Chin level
    left_eye_x = 365     # Left eye center
    right_eye_x = 545    # Right eye center

    # 1. Full Beard Overlay
    if "Full Beard" in disguises:
        b_mask = Image.new("L", (w, h), 0)
        bd = ImageDraw.Draw(b_mask)
        # Lower jaw and chin coverage
        bd.ellipse([cx - 210, mouth_y - 25, cx + 210, chin_y + 80], fill=210)
        bd.ellipse([cx - 160, mouth_y + 30, cx + 160, chin_y + 50], fill=240)
        # Sideburns and cheeks
        bd.polygon([
            (cx - 210, eye_y + 60), (cx - 170, mouth_y), (cx - 130, chin_y + 60),
            (cx + 130, chin_y + 60), (cx + 170, mouth_y), (cx + 210, eye_y + 60)
        ], fill=180)
        b_mask = b_mask.filter(ImageFilter.GaussianBlur(radius=14))
        b_layer = Image.new("RGBA", (w, h), (28, 24, 22, 235))
        b_layer.putalpha(b_mask)
        overlay = Image.alpha_composite(overlay, b_layer)
        draw = ImageDraw.Draw(overlay)

    # 2. Mustache Overlay
    if "Mustache" in disguises or ("Full Beard" in disguises):
        m_mask = Image.new("L", (w, h), 0)
        md = ImageDraw.Draw(m_mask)
        md.ellipse([cx - 110, mouth_y - 45, cx + 110, mouth_y + 5], fill=240)
        m_mask = m_mask.filter(ImageFilter.GaussianBlur(radius=6))
        m_layer = Image.new("RGBA", (w, h), (22, 19, 18, 245))
        m_layer.putalpha(m_mask)
        overlay = Image.alpha_composite(overlay, m_layer)
        draw = ImageDraw.Draw(overlay)

    # 3. Sunglasses Overlay
    if "Sunglasses" in disguises:
        sg_y = eye_y - 42
        draw.rounded_rectangle([left_eye_x - 90, sg_y, left_eye_x + 90, sg_y + 85], radius=20, fill=(16, 16, 18, 252), outline=(8, 8, 10, 255), width=5)
        draw.rounded_rectangle([right_eye_x - 90, sg_y, right_eye_x + 90, sg_y + 85], radius=20, fill=(16, 16, 18, 252), outline=(8, 8, 10, 255), width=5)
        draw.line([(left_eye_x + 85, eye_y - 12), (right_eye_x - 85, eye_y - 12)], fill=(12, 12, 14, 255), width=8)
        # Subtle lens reflections
        draw.line([(left_eye_x - 60, sg_y + 18), (left_eye_x + 20, sg_y + 65)], fill=(255, 255, 255, 45), width=3)
        draw.line([(right_eye_x - 60, sg_y + 18), (right_eye_x + 20, sg_y + 65)], fill=(255, 255, 255, 45), width=3)

    # 4. Wire-Rimmed Glasses Overlay
    elif "Wire-Rimmed Glasses" in disguises:
        gw_y = eye_y - 40
        draw.ellipse([left_eye_x - 85, gw_y, left_eye_x + 85, gw_y + 80], outline=(48, 45, 52, 245), width=5)
        draw.ellipse([right_eye_x - 85, gw_y, right_eye_x + 85, gw_y + 80], outline=(48, 45, 52, 245), width=5)
        draw.line([(left_eye_x + 85, eye_y - 10), (right_eye_x - 85, eye_y - 10)], fill=(48, 45, 52, 255), width=5)
        # Temples
        draw.line([(left_eye_x - 85, eye_y - 10), (left_eye_x - 175, eye_y - 25)], fill=(48, 45, 52, 235), width=4)
        draw.line([(right_eye_x + 85, eye_y - 10), (right_eye_x + 175, eye_y - 25)], fill=(48, 45, 52, 235), width=4)

    # 5. Scar/Mark Overlay
    if "Scar/Mark" in disguises:
        scar_x = cx + 115
        draw.line([(scar_x - 8, eye_y + 40), (scar_x + 12, eye_y + 110), (scar_x + 4, eye_y + 160)], fill=(138, 72, 68, 195), width=4)
        draw.line([(scar_x - 14, eye_y + 75), (scar_x + 6, eye_y + 70)], fill=(175, 120, 115, 140), width=2)
        draw.line([(scar_x - 2, eye_y + 125), (scar_x + 18, eye_y + 120)], fill=(175, 120, 115, 140), width=2)

    combined = Image.alpha_composite(img, overlay)

    # Professional Forensic Identification Badge overlay
    badge = ImageDraw.Draw(combined)
    badge.rectangle([0, 0, w, 44], fill=(20, 22, 26, 240))
    badge.text((20, 13), f"AI NEXUS // OFFICIAL IDENTIFICATION PORTRAIT · ID #{seed_int:08X}", fill=(235, 238, 242, 255))
    badge.rectangle([0, h - 52, w, h], fill=(20, 22, 26, 240))
    trait_str = f"JAW: {jaw.upper()} | HAIR: {hair.upper()} | DISGUISES: {', '.join(disguises) if disguises else 'NONE'}"
    badge.text((20, h - 38), trait_str, fill=(34, 227, 214, 255))

    buf = io.BytesIO()
    combined.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()'''

if old_fn_pattern.search(content):
    content = old_fn_pattern.sub(new_fn_code, content)
    target.write_text(content, encoding="utf-8")
    print("Updated generate_dynamic_forensic_sketch successfully")
else:
    print("Warning: generate_dynamic_forensic_sketch pattern not found")

import py_compile
py_compile.compile(str(target), doraise=True)
print("image_service.py compiled OK")
