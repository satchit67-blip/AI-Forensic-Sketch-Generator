"""
patch_prompt_assembly.py
------------------------
Implements user requirement:
1. Ensure raw witness description from user text box is passed cleanly as primary subject base.
2. Dynamically collect all active toggle chips (Mustache, Full Beard, Wire-Rimmed Glasses,
   Sunglasses, Long Hair, Bald, Scar/Mark) and cleanly append explicit modifiers
   (e.g. ", sporting a defined mustache", ", wearing wire-rimmed glasses") to the prompt.
3. Remove any hardcoded style prefixes that force generic 3D rendering so that output
   strictly mirrors the detailed textual description provided by the user.
"""

from pathlib import Path
import re
import py_compile
import sys

BACKEND_DIR = Path(__file__).resolve().parent
SKETCH_ROUTES = BACKEND_DIR / "app" / "api" / "routes" / "sketch.py"
IMAGE_SERVICE = BACKEND_DIR / "app" / "services" / "image_service.py"

# ==============================================================================
# Update app/api/routes/sketch.py
# ==============================================================================
routes_code = SKETCH_ROUTES.read_text(encoding="utf-8")

# Add DISGUISE_MODIFIERS and assemble_dynamic_prompt helper if not present
prompt_builder_code = '''
# ---------------------------------------------------------------------------
# Dynamic prompt assembly for witness descriptions & disguise toggle chips
# ---------------------------------------------------------------------------
DISGUISE_MODIFIERS: dict[str, str] = {
    "Mustache": "sporting a defined mustache",
    "Full Beard": "sporting a full thick beard",
    "Wire-Rimmed Glasses": "wearing wire-rimmed glasses",
    "Sunglasses": "wearing dark sunglasses",
    "Long Hair": "with long flowing hair",
    "Bald": "completely bald with a clean-shaven head",
    "Scar/Mark": "with a visible facial scar mark on the cheek",
}


def assemble_dynamic_prompt(raw_description: str, disguises: list[str]) -> str:
    """
    Constructs a clean, dynamic prompt where the raw witness description is the
    primary subject base, followed by explicit modifiers for active disguise chips.
    Removes hardcoded prefixes (e.g. 'A forensic police sketch portrait of') that
    force generic 3D styling.
    """
    import re
    desc = (raw_description or "").strip()

    # Strip any hardcoded legacy prefixes
    for prefix in [
        "A forensic police sketch portrait of ",
        "a forensic police sketch portrait of ",
        "Forensic sketch of ",
        "forensic sketch of ",
        "A police sketch of ",
        "a police sketch of ",
    ]:
        if desc.startswith(prefix):
            desc = desc[len(prefix):].strip()

    # Strip any pre-concatenated disguise fragments from frontend
    legacy_phrases = [
        r"with full thick beard", r"sporting a full thick beard", r"with full beard", r"wearing full beard",
        r"with neat mustache", r"sporting a defined mustache", r"with mustache", r"wearing mustache",
        r"wearing wire-rimmed glasses", r"with wire-rimmed glasses",
        r"wearing dark sunglasses", r"with sunglasses", r"wearing sunglasses",
        r"with long flowing hair", r"with long hair",
        r"completely bald with shaved head", r"completely bald with a clean-shaven head", r"completely bald",
        r"with visible facial scar mark on cheek", r"with visible facial scar mark on the cheek",
    ]
    for lp in legacy_phrases:
        desc = re.sub(r",?\\s*" + lp, "", desc, flags=re.IGNORECASE).strip()

    desc = desc.rstrip(",. ")

    # Map active disguises to natural, explicit descriptive modifiers
    modifiers = []
    for d in disguises:
        mod = DISGUISE_MODIFIERS.get(d, f"with {d.lower()}")
        if mod not in modifiers:
            modifiers.append(mod)

    if desc and modifiers:
        return f"{desc}, {', '.join(modifiers)}"
    elif desc:
        return desc
    elif modifiers:
        return f"portrait of a person, {', '.join(modifiers)}"
    return "portrait of a person"
'''

# Check if assemble_dynamic_prompt is already in routes_code
if "def assemble_dynamic_prompt" not in routes_code:
    # Insert before router definitions
    routes_code = re.sub(
        r'(router = APIRouter\(tags=\["Sketch AI Pipeline"\]\))',
        lambda m: prompt_builder_code + '\n\n' + m.group(1),
        routes_code
    )

# Replace generate_sketch endpoint in sketch.py
new_generate_sketch = '''@router.post(
    "/generate-sketch",
    response_model=GenerateSketchResponse,
    summary="Parse witness description -> structured facial traits & generate image",
)
async def generate_sketch(
    body: GenerateSketchRequest,
    user: User = Depends(get_current_user_or_demo),
    db: AsyncSession | None = Depends(get_db_optional),
    audit: AuditRecorder = Depends(get_audit_recorder_safe),
) -> GenerateSketchResponse:
    """
    Step 1 of the AI pipeline:
    Extracts raw witness description as primary subject base.
    Cleanly appends active disguise toggle chips as explicit modifiers.
    Fetches real dynamic image directly from Pollinations.ai.
    """
    traits, raw_output = await ai_service.parse_description(body.description)

    # 1. Cleanly extract raw witness description as primary subject base
    raw_desc = (body.description or "").strip()

    # 2. Dynamically collect all active toggle chips from request & traits
    active_disguises: list[str] = []
    valid_disguises = {
        "Full Beard", "Mustache", "Wire-Rimmed Glasses",
        "Sunglasses", "Long Hair", "Bald", "Scar/Mark",
    }
    if body.disguises:
        for d in body.disguises:
            if d in valid_disguises and d not in active_disguises:
                active_disguises.append(d)
    if traits and traits.disguises:
        for d in traits.disguises:
            if d in valid_disguises and d not in active_disguises:
                active_disguises.append(d)

    # Synchronize disguises and hair on traits
    traits.disguises = sorted(set(active_disguises))
    if "Bald" in traits.disguises:
        traits.hair = "bald"
    elif "Long Hair" in traits.disguises:
        traits.hair = "long"

    # 3. Assemble dynamic prompt without rigid 3D style prefixes
    final_prompt = assemble_dynamic_prompt(raw_desc, traits.disguises)

    # 4. Generate dynamic sketch directly
    raw_b64, prompt_used = await image_service.generate_sketch_image(
        traits=traits,
        description=final_prompt,
        case_id=str(body.case_id) if body.case_id else "default",
    )
    data_uri = f"data:image/jpeg;base64,{raw_b64}" if not raw_b64.startswith("data:") else raw_b64

    return GenerateSketchResponse(
        traits=traits,
        raw_gemini_output=raw_output,
        case_id=body.case_id,
        image_b64=data_uri,
        sketch_url=data_uri,
        sketch_data=data_uri,
        url=data_uri,
        data=data_uri,
    )'''

routes_code = re.sub(
    r'@router\.post\(\s*"/generate-sketch".*?(?=@router\.post\(\s*"/refine-sketch")',
    lambda m: new_generate_sketch + '\n\n# ---------------------------------------------------------------------------\n',
    routes_code,
    flags=re.DOTALL
)

# Update apply_disguise to use assemble_dynamic_prompt
new_apply_disguise_block = '''    # Build dynamic prompt with raw description as base and active chips as modifiers
    raw_desc = (body.description or "").strip()
    final_prompt = assemble_dynamic_prompt(raw_desc, current_traits.disguises)

    raw_b64, _ = await image_service.generate_sketch_image(
        traits=current_traits,
        description=final_prompt,
        case_id=str(body.case_id) if body.case_id else "default",
    )
    data_uri = f'data:image/jpeg;base64,{raw_b64}' if not raw_b64.startswith('data:') else raw_b64'''

routes_code = re.sub(
    r'# Build dynamic prompt with raw description as base.*?data_uri = f[\'"]data:image/jpeg;base64,\{raw_b64\}[\'"] if not raw_b64\.startswith\([\'"]data:[\'"]\) else raw_b64',
    lambda m: new_apply_disguise_block,
    routes_code,
    flags=re.DOTALL
)

SKETCH_ROUTES.write_text(routes_code, encoding="utf-8")
print("[OK] Updated app/api/routes/sketch.py")

# ==============================================================================
# Update app/services/image_service.py
# ==============================================================================
service_code = IMAGE_SERVICE.read_text(encoding="utf-8")

# Ensure generate_sketch_image does not inject any static 3D prefixes
new_generate_image_func = '''async def generate_sketch_image(
    traits: SketchTraits,
    description: str,
    case_id: str,
) -> tuple[str, str]:
    """
    Generate sketch image directly from the dynamic textual prompt.
    Passes prompt cleanly to Pollinations.ai without hardcoded 3D style prefixes.
    """
    final_prompt = description.strip()
    logger.info("Generating dynamic sketch for final prompt: %s", final_prompt)
    img_bytes = await _pollinations_generate(final_prompt)
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return b64, final_prompt'''

service_code = re.sub(
    r'async def generate_sketch_image\(.*?(?=\nasync def refine_sketch_image)',
    lambda m: new_generate_image_func + '\n\n\n',
    service_code,
    flags=re.DOTALL
)

IMAGE_SERVICE.write_text(service_code, encoding="utf-8")
print("[OK] Updated app/services/image_service.py")

# ==============================================================================
# Syntax verification
# ==============================================================================
py_compile.compile(str(SKETCH_ROUTES), doraise=True)
print("[OK] Syntax verified: sketch.py")
py_compile.compile(str(IMAGE_SERVICE), doraise=True)
print("[OK] Syntax verified: image_service.py")
