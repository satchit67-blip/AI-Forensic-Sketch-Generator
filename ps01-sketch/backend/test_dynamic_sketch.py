import hashlib
import io, base64
from PIL import Image, ImageDraw, ImageFilter, ImageFont

def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 6:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    return (40, 38, 42)

def generate_dynamic_forensic_sketch(
    description: str,
    jaw: str = "soft",
    hair: str = "short",
    hair_color: str = "#2b2b2f",
    face_scale: float = 1.0,
    disguises: list[str] = None,
) -> bytes:
    if disguises is None:
        disguises = []

    # Deterministic seed from description
    seed_int = int(hashlib.sha256((description or "default").encode()).hexdigest()[:8], 16)
    
    # Dimensions
    w, h = 512, 680
    cx = w // 2
    
    # Variation factors derived from seed
    eye_offset = (seed_int % 11) - 5          # -5 to +5
    nose_len = ((seed_int >> 4) % 15)         # 0 to 14
    lip_width = ((seed_int >> 8) % 13) - 6    # -6 to +6
    brow_tilt = ((seed_int >> 12) % 7) - 3    # -3 to +3
    age_lines = (seed_int >> 16) % 3          # 0 to 2
    
    # Base parchment paper background with noise
    img = Image.new("RGBA", (w, h), (242, 237, 226, 255))
    draw = ImageDraw.Draw(img)
    
    # Paper texture hatching
    for y in range(0, h, 6):
        draw.line([(0, y), (w, y)], fill=(20, 20, 20, 10), width=1)
    for x in range(0, w, 8):
        draw.line([(x, 0), (x, h)], fill=(20, 20, 20, 8), width=1)
        
    # Scale face width
    half_fw = int(105 * face_scale)
    
    # Neck and shoulders
    draw.polygon([
        (cx - 50, 430), (cx - 140, h), (cx + 140, h), (cx + 50, 430)
    ], fill=(215, 204, 188, 255), outline=(32, 30, 35, 255), width=2)
    
    # Head and jawline contour
    top_y = 130
    chin_y = 480
    
    if jaw == "sharp":
        # Chiseled, angular jaw
        head_pts = [
            (cx - half_fw, 220),
            (cx - half_fw + 10, top_y + 40),
            (cx, top_y),
            (cx + half_fw - 10, top_y + 40),
            (cx + half_fw, 220),
            (cx + half_fw - 5, 360),
            (cx + half_fw - 25, 430),  # angular jaw corner
            (cx + 35, chin_y),         # flat chin
            (cx - 35, chin_y),
            (cx - half_fw + 25, 430),
            (cx - half_fw + 5, 360),
        ]
    else:
        # Soft, rounded jaw
        head_pts = [
            (cx - half_fw, 220),
            (cx - half_fw + 15, top_y + 45),
            (cx, top_y),
            (cx + half_fw - 15, top_y + 45),
            (cx + half_fw, 220),
            (cx + half_fw - 5, 360),
            (cx + half_fw - 35, 435),
            (cx + 25, chin_y - 10),
            (cx, chin_y),
            (cx - 25, chin_y - 10),
            (cx - half_fw + 35, 435),
            (cx - half_fw + 5, 360),
        ]
        
    # Draw head
    draw.polygon(head_pts, fill=(232, 219, 202, 255), outline=(35, 32, 38, 255), width=3)
    
    # Ear contours
    ear_w = 16
    draw.ellipse([cx - half_fw - ear_w + 4, 275, cx - half_fw + 6, 355], fill=(225, 210, 192, 255), outline=(35, 32, 38, 255), width=2)
    draw.ellipse([cx + half_fw - 6, 275, cx + half_fw + ear_w - 4, 355], fill=(225, 210, 192, 255), outline=(35, 32, 38, 255), width=2)
    
    # Hair drawing
    hair_rgb = hex_to_rgb(hair_color)
    hair_fill = (*hair_rgb, 240)
    
    if hair == "long" or "Long Hair" in disguises:
        # Long flowing hair
        hair_pts = [
            (cx - half_fw - 30, top_y + 50),
            (cx - half_fw - 10, top_y),
            (cx, top_y - 25),
            (cx + half_fw + 10, top_y),
            (cx + half_fw + 30, top_y + 50),
            (cx + half_fw + 35, 520),
            (cx + half_fw + 5, 530),
            (cx + half_fw - 15, 360),
            (cx + half_fw - 20, 240),
            (cx, top_y + 35),
            (cx - half_fw + 20, 240),
            (cx - half_fw + 15, 360),
            (cx - half_fw - 5, 530),
            (cx - half_fw - 35, 520),
        ]
        draw.polygon(hair_pts, fill=hair_fill, outline=(25, 23, 28, 255), width=2)
    elif hair == "bald" or "Bald" in disguises:
        # Smooth cranium with scalp shading lines
        draw.arc([cx - half_fw + 20, top_y + 20, cx + half_fw - 20, top_y + 90], start=190, end=350, fill=(180, 165, 148, 180), width=2)
    else:
        # Short cropped hair
        hair_pts = [
            (cx - half_fw - 10, top_y + 70),
            (cx - half_fw + 5, top_y + 10),
            (cx - 30, top_y - 20),
            (cx + 30, top_y - 20),
            (cx + half_fw - 5, top_y + 10),
            (cx + half_fw + 10, top_y + 70),
            (cx + half_fw - 15, 210),
            (cx + half_fw - 35, 180),
            (cx + 40, top_y + 30),
            (cx - 40, top_y + 30),
            (cx - half_fw + 35, 180),
            (cx - half_fw + 15, 210),
        ]
        draw.polygon(hair_pts, fill=hair_fill, outline=(25, 23, 28, 255), width=2)

    # Eyebrows
    eyebrow_y = 265
    draw.line([(cx - 75, eyebrow_y + brow_tilt), (cx - 22, eyebrow_y - brow_tilt)], fill=(30, 28, 32, 240), width=4)
    draw.line([(cx + 22, eyebrow_y - brow_tilt), (cx + 75, eyebrow_y + brow_tilt)], fill=(30, 28, 32, 240), width=4)

    # Eyes
    eye_y = 295 + eye_offset
    # Left eye
    draw.ellipse([cx - 72, eye_y - 12, cx - 26, eye_y + 12], fill=(255, 255, 255, 245), outline=(35, 32, 38, 255), width=2)
    draw.ellipse([cx - 56, eye_y - 8, cx - 42, eye_y + 8], fill=(42, 34, 30, 255))
    draw.ellipse([cx - 51, eye_y - 4, cx - 47, eye_y], fill=(255, 255, 255, 240))  # specular highlight
    # Right eye
    draw.ellipse([cx + 26, eye_y - 12, cx + 72, eye_y + 12], fill=(255, 255, 255, 245), outline=(35, 32, 38, 255), width=2)
    draw.ellipse([cx + 42, eye_y - 8, cx + 56, eye_y + 8], fill=(42, 34, 30, 255))
    draw.ellipse([cx + 47, eye_y - 4, cx + 51, eye_y], fill=(255, 255, 255, 240))

    # Eye creases / lids
    draw.arc([cx - 70, eye_y - 18, cx - 28, eye_y - 4], start=190, end=350, fill=(40, 36, 42, 180), width=2)
    draw.arc([cx + 28, eye_y - 18, cx + 70, eye_y - 4], start=190, end=350, fill=(40, 36, 42, 180), width=2)

    # Nose
    nose_tip_y = 365 + nose_len
    draw.line([(cx, eye_y - 10), (cx - 8, nose_tip_y - 5), (cx - 15, nose_tip_y)], fill=(35, 32, 38, 220), width=2)
    draw.arc([cx - 16, nose_tip_y - 8, cx + 16, nose_tip_y + 4], start=20, end=160, fill=(35, 32, 38, 240), width=3)
    draw.line([(cx + 15, nose_tip_y), (cx + 8, nose_tip_y - 5)], fill=(35, 32, 38, 220), width=2)

    # Mouth / Lips
    mouth_y = nose_tip_y + 40
    mw = 35 + lip_width
    draw.line([(cx - mw, mouth_y), (cx - mw//3, mouth_y - 2), (cx + mw//3, mouth_y - 2), (cx + mw, mouth_y)], fill=(35, 32, 38, 240), width=3)
    draw.arc([cx - mw + 5, mouth_y - 4, cx + mw - 5, mouth_y + 12], start=15, end=165, fill=(40, 36, 42, 180), width=2)

    # Disguises
    # 1. Full Beard
    if "Full Beard" in disguises:
        beard_fill = (*hair_rgb, 215)
        draw.chord([cx - half_fw + 10, mouth_y - 15, cx + half_fw - 10, chin_y + 25], start=0, end=180, fill=beard_fill)
        draw.polygon([(cx - half_fw + 10, 320), (cx - half_fw + 30, 440), (cx - half_fw + 10, 470)], fill=beard_fill)
        draw.polygon([(cx + half_fw - 10, 320), (cx + half_fw - 30, 440), (cx + half_fw - 10, 470)], fill=beard_fill)

    # 2. Mustache
    if "Mustache" in disguises or "Full Beard" in disguises:
        mustache_fill = (*hair_rgb, 235)
        draw.chord([cx - 38, mouth_y - 18, cx + 38, mouth_y + 4], start=0, end=180, fill=mustache_fill)

    # 3. Sunglasses
    if "Sunglasses" in disguises:
        sg_y = eye_y - 18
        draw.rounded_rectangle([cx - 80, sg_y, cx - 12, sg_y + 38], radius=8, fill=(16, 16, 18, 245), outline=(10, 10, 12, 255), width=3)
        draw.rounded_rectangle([cx + 12, sg_y, cx + 80, sg_y + 38], radius=8, fill=(16, 16, 18, 245), outline=(10, 10, 12, 255), width=3)
        draw.line([(cx - 12, sg_y + 16), (cx + 12, sg_y + 16)], fill=(12, 12, 14, 255), width=4)
        draw.line([(cx - 80, sg_y + 14), (cx - half_fw, sg_y + 8)], fill=(12, 12, 14, 255), width=3)
        draw.line([(cx + 80, sg_y + 14), (cx + half_fw, sg_y + 8)], fill=(12, 12, 14, 255), width=3)
        draw.line([(cx - 68, sg_y + 8), (cx - 42, sg_y + 20)], fill=(255, 255, 255, 80), width=2)
        draw.line([(cx + 24, sg_y + 8), (cx + 50, sg_y + 20)], fill=(255, 255, 255, 80), width=2)

    # 4. Wire-Rimmed Glasses
    elif "Wire-Rimmed Glasses" in disguises:
        gw_y = eye_y - 18
        draw.ellipse([cx - 76, gw_y, cx - 14, gw_y + 38], outline=(40, 38, 42, 235), width=3)
        draw.ellipse([cx + 14, gw_y, cx + 76, gw_y + 38], outline=(40, 38, 42, 235), width=3)
        draw.line([(cx - 14, gw_y + 18), (cx + 14, gw_y + 18)], fill=(40, 38, 42, 245), width=3)
        draw.line([(cx - 76, gw_y + 16), (cx - half_fw, gw_y + 10)], fill=(40, 38, 42, 235), width=2)
        draw.line([(cx + 76, gw_y + 16), (cx + half_fw, gw_y + 10)], fill=(40, 38, 42, 235), width=2)

    # 5. Scar/Mark
    if "Scar/Mark" in disguises:
        scar_x = cx + half_fw // 2
        draw.line([(scar_x - 5, 320), (scar_x + 8, 360), (scar_x, 405)], fill=(90, 35, 35, 220), width=3)
        draw.line([(scar_x - 7, 340), (scar_x + 6, 338)], fill=(150, 110, 110, 180), width=1)
        draw.line([(scar_x + 2, 380), (scar_x + 12, 378)], fill=(150, 110, 110, 180), width=1)

    # Forensic document header and footer stamp
    draw.rectangle([0, 0, w, 32], fill=(28, 26, 30, 245))
    draw.text((12, 9), f"AI NEXUS // FORENSIC COMPOSITE · ID: #{seed_int:08X}", fill=(225, 225, 225, 255))
    
    draw.rectangle([0, h - 38, w, h], fill=(28, 26, 30, 245))
    traits_info = f"JAW: {jaw.upper()} | HAIR: {hair.upper()} | WIDTH: {face_scale:.2f}x"
    disg_info = f"DISGUISES: {', '.join(disguises) if disguises else 'NONE'}"
    draw.text((12, h - 30), f"{traits_info} · {disg_info}", fill=(34, 227, 214, 255))
    
    # Save to PNG bytes
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()

# Test different seeds and traits
b1 = generate_dynamic_forensic_sketch("dsdsad", jaw="soft", hair="short", face_scale=1.0)
b2 = generate_dynamic_forensic_sketch("Man in his 40s, sharp jaw, short grey hair, thin face", jaw="sharp", hair="short", hair_color="#8a8a90", face_scale=0.9)
b3 = generate_dynamic_forensic_sketch("Man in his 40s, sharp jaw, short grey hair, thin face", jaw="sharp", hair="short", hair_color="#8a8a90", face_scale=0.9, disguises=["Full Beard", "Sunglasses"])

print(f"Sample 1 ('dsdsad') bytes: {len(b1)}")
print(f"Sample 2 ('sharp jaw, grey hair') bytes: {len(b2)}")
print(f"Sample 3 ('with beard, sunglasses') bytes: {len(b3)}")
assert b1 != b2, "Input 'dsdsad' must NOT equal description 2!"
assert b2 != b3, "Description without beard must NOT equal description with beard!"
print("ALL TESTS PASSED! Distinct inputs produce distinct forensic sketches!")
