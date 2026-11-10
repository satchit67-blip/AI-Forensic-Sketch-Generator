"""
apply_disguise_refactor.py
--------------------------
Refactors disguise toggle logic in app/api/routes/sketch.py:
1. Enhances format_disguise_modifiers to generate natural, grammatically correct
   phrasing like: ", wearing dark sunglasses and a neat mustache", ", with a full thick beard", etc.
2. Cleans base witness description to isolate the pure subject base.
3. Anchors seed to the stable base description.
4. Updates apply_disguise route handler to strictly append active modifiers to the prompt.
"""

from pathlib import Path
import re
import py_compile
import sys

BACKEND_DIR = Path(__file__).resolve().parent
SKETCH_ROUTES = BACKEND_DIR / "app" / "api" / "routes" / "sketch.py"

content = SKETCH_ROUTES.read_text(encoding="utf-8")

# Replacement for the helper block
new_helper_block = '''# ---------------------------------------------------------------------------
# Dynamic prompt assembly for witness descriptions & disguise toggle chips
# ---------------------------------------------------------------------------
def format_disguise_modifiers(disguises: list[str]) -> str:
    """
    Format active toggle chips into natural English modifiers.
    Example: ['Sunglasses', 'Mustache'] -> 'wearing dark sunglasses and a neat mustache'
    """
    if not disguises:
        return ""

    eyewear = (
        "dark sunglasses" if "Sunglasses" in disguises
        else ("wire-rimmed glasses" if "Wire-Rimmed Glasses" in disguises else None)
    )

    facial_hair = []
    if "Full Beard" in disguises:
        facial_hair.append("a full thick beard")
    if "Mustache" in disguises:
        facial_hair.append("a neat mustache")

    other = []
    if "Long Hair" in disguises and "Bald" not in disguises:
        other.append("with long flowing hair")
    elif "Bald" in disguises:
        other.append("completely bald with a clean-shaven head")
    if "Scar/Mark" in disguises:
        other.append("with a visible facial scar on the cheek")

    parts = []
    fh_str = " and ".join(facial_hair) if facial_hair else ""

    if eyewear and fh_str:
        if len(facial_hair) > 1:
            parts.append(f"wearing {eyewear}, with {fh_str}")
        else:
            parts.append(f"wearing {eyewear} and {fh_str}")
    elif eyewear:
        parts.append(f"wearing {eyewear}")
    elif fh_str:
        parts.append(f"with {fh_str}")

    parts.extend(other)
    return ", ".join(parts)


def clean_base_description(desc: str) -> str:
    """
    Isolates the clean base witness description by stripping any hardcoded prefixes
    or previously appended disguise fragments.
    """
    import re
    text = (desc or "").strip()

    # Strip legacy prefixes
    for prefix in [
        "A forensic police sketch portrait of ",
        "a forensic police sketch portrait of ",
        "Forensic sketch of ",
        "forensic sketch of ",
        "A police sketch of ",
        "a police sketch of ",
    ]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    # Strip previously appended disguise phrases to keep the base face clean and stable
    fragments = [
        r"wearing dark sunglasses and a neat mustache",
        r"wearing dark sunglasses and a full thick beard",
        r"wearing wire-rimmed glasses and a neat mustache",
        r"wearing wire-rimmed glasses and a full thick beard",
        r"with a full thick beard and a neat mustache",
        r"wearing dark sunglasses",
        r"wearing wire-rimmed glasses",
        r"with a full thick beard",
        r"with a neat mustache",
        r"sporting a prominent full beard",
        r"sporting a full thick beard",
        r"sporting a defined mustache",
        r"with long flowing hair",
        r"completely bald with a clean-shaven head",
        r"completely bald with shaved head",
        r"completely bald",
        r"with a visible facial scar on the cheek",
        r"with visible facial scar mark on cheek",
        r"with full thick beard",
        r"with neat mustache",
        r"wearing sunglasses",
        r"wearing glasses",
    ]
    for frag in fragments:
        text = re.sub(r",?\\s*" + frag, "", text, flags=re.IGNORECASE).strip()

    return text.rstrip(",. ")


def assemble_dynamic_prompt(raw_description: str, disguises: list[str]) -> str:
    """
    Constructs a clean dynamic prompt:
    <base_description>, <natural_disguise_modifiers>
    """
    clean_base = clean_base_description(raw_description)
    modifiers = format_disguise_modifiers(disguises)

    if clean_base and modifiers:
        return f"{clean_base}, {modifiers}"
    elif clean_base:
        return clean_base
    elif modifiers:
        return f"portrait of a person, {modifiers}"
    return "portrait of a person"'''

# Replace from "# Dynamic prompt assembly" down to "router = APIRouter"
content = re.sub(
    r'# -+\s*# Dynamic prompt assembly for witness descriptions.*?router = APIRouter\(tags=\["Sketch AI Pipeline"\]\)',
    lambda m: new_helper_block + '\n\nrouter = APIRouter(tags=["Sketch AI Pipeline"])',
    content,
    flags=re.DOTALL
)

# Update apply_disguise route handler
apply_disguise_pattern = r'async def apply_disguise\(.*?return ApplyDisguiseResponse\(.*?\n    \)'
new_apply_disguise = '''async def apply_disguise(
    body: ApplyDisguiseRequest,
    user: User = Depends(get_current_user_or_demo),
    db: AsyncSession | None = Depends(get_db_optional),
    audit: AuditRecorder = Depends(get_audit_recorder_safe),
) -> ApplyDisguiseResponse:
    """
    Disguise toggle:
    1. Collects and updates active disguise chips.
    2. Isolates the stable base witness description to anchor the face seed.
    3. Explicitly appends active modifiers (e.g., ', wearing dark sunglasses and a neat mustache').
    4. Generates/fetches the updated dynamic image.
    """
    verb = "Applied" if body.active else "Removed"

    warning: str | None = None
    if body.active and body.name == "Bald":
        warning = "Long Hair will be overridden by Bald."
    elif body.active and body.name == "Long Hair":
        warning = "Bald will be overridden by Long Hair."

    # Update disguise state on current traits
    current_traits = body.current_traits or SketchTraits()
    disguise_set = set(current_traits.disguises)
    if body.active:
        disguise_set.add(body.name)
        if body.name == "Bald":
            disguise_set.discard("Long Hair")
            current_traits.hair = "bald"
        elif body.name == "Long Hair":
            disguise_set.discard("Bald")
            current_traits.hair = "long"
    else:
        disguise_set.discard(body.name)
    current_traits.disguises = sorted(disguise_set)

    try:
        await audit.record(
            action=f"{verb} Disguise: {body.name}",
            case_id=body.case_id,
        )
    except Exception:
        pass

    msg = f"{verb} {body.name}. Core facial structure unchanged."
    if warning:
        msg += f" Note: {warning}"

    # 1. Cleanly isolate stable base description
    raw_desc = (body.description or "").strip()
    clean_base = clean_base_description(raw_desc) or raw_desc

    # 2. Derive stable, deterministic seed from clean base description
    stable_seed = image_service.get_deterministic_seed(clean_base)

    # 3. Assemble final prompt: base description + explicit disguise modifiers
    final_prompt = assemble_dynamic_prompt(clean_base, current_traits.disguises)
    logger.info("apply_disguise final prompt: '%s' (seed=%d)", final_prompt, stable_seed)

    try:
        raw_b64, _ = await image_service.generate_sketch_image(
            traits=current_traits,
            description=final_prompt,
            case_id=str(body.case_id) if body.case_id else "default",
            seed=stable_seed,
        )
        data_uri = f"data:image/jpeg;base64,{raw_b64}" if not raw_b64.startswith("data:") else raw_b64
    except Exception as exc:
        logger.warning("apply_disguise live generation encountered: %s; using dynamic fallback", exc)
        data_uri = image_service.get_fallback_sketch_data_uri(
            traits=current_traits,
            description=final_prompt,
        )

    return ApplyDisguiseResponse(
        name=body.name,
        active=body.active,
        case_id=body.case_id,
        message=msg,
        traits=current_traits,
        image_b64=data_uri,
        sketch_url=data_uri,
        url=data_uri,
        sketch_data=image_service.FALLBACK_SVG_STRING,
        data=data_uri,
    )'''

content = re.sub(apply_disguise_pattern, lambda m: new_apply_disguise, content, flags=re.DOTALL)

SKETCH_ROUTES.write_text(content, encoding="utf-8")
print("[OK] sketch.py updated successfully.")

py_compile.compile(str(SKETCH_ROUTES), doraise=True)
print("[OK] Syntax check passed for sketch.py")
