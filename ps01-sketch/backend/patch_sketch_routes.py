from pathlib import Path
import re

# 1. Update sketch.py
sketch_file = Path("app/api/routes/sketch.py")
sketch_src = sketch_file.read_text(encoding="utf-8")

old_gen_hook = '''        img_b64 = None
        if settings.IMAGE_MODE != 'disabled':
            try:
                raw_b64, _ = await image_service.generate_sketch_image(
                    traits=traits,
                    description=body.description,
                    case_id=body.case_id,
                )
                if raw_b64:
                    img_b64 = f'data:image/jpeg;base64,{raw_b64}' if not raw_b64.startswith('data:') else raw_b64
            except Exception as gen_err:
                import logging
                logging.getLogger(__name__).warning('Cloud sketch generation failed: %s; falling back to dynamic procedural', gen_err)

        data_uri = img_b64 or image_service.get_fallback_sketch_data_uri(traits=traits, description=body.description)'''

new_gen_hook = '''        full_description = body.description or ""
        if traits.disguises:
            active_str = ", ".join(traits.disguises)
            if not any(d.lower() in full_description.lower() for d in traits.disguises):
                full_description = f"{full_description.rstrip('.')} with {active_str}."

        img_b64 = None
        if settings.IMAGE_MODE != 'disabled':
            try:
                raw_b64, _ = await image_service.generate_sketch_image(
                    traits=traits,
                    description=full_description,
                    case_id=body.case_id,
                )
                if raw_b64:
                    img_b64 = f'data:image/jpeg;base64,{raw_b64}' if not raw_b64.startswith('data:') else raw_b64
            except Exception as gen_err:
                import logging
                logging.getLogger(__name__).warning('Cloud sketch generation failed: %s; falling back to dynamic procedural', gen_err)

        data_uri = img_b64 or image_service.get_fallback_sketch_data_uri(traits=traits, description=full_description)'''

if old_gen_hook in sketch_src:
    sketch_src = sketch_src.replace(old_gen_hook, new_gen_hook, 1)
    print("Updated generate_sketch in sketch.py")
else:
    print("Warning: old_gen_hook not found in sketch.py")

old_apply_hook = '''    data_uri = image_service.get_fallback_sketch_data_uri(
        traits=current_traits,
        description=body.description or "",
    )'''

new_apply_hook = '''    full_description = body.description or ""
    if current_traits.disguises:
        active_str = ", ".join(current_traits.disguises)
        if not any(d.lower() in full_description.lower() for d in current_traits.disguises):
            full_description = f"{full_description.rstrip('.')} with {active_str}."

    img_b64 = None
    if settings.IMAGE_MODE != 'disabled':
        try:
            raw_b64, _ = await image_service.generate_sketch_image(
                traits=current_traits,
                description=full_description,
                case_id=body.case_id,
            )
            if raw_b64:
                img_b64 = f'data:image/jpeg;base64,{raw_b64}' if not raw_b64.startswith('data:') else raw_b64
        except Exception as exc:
            pass

    data_uri = img_b64 or image_service.get_fallback_sketch_data_uri(
        traits=current_traits,
        description=full_description,
    )'''

if old_apply_hook in sketch_src:
    sketch_src = sketch_src.replace(old_apply_hook, new_apply_hook, 1)
    print("Updated apply_disguise in sketch.py")
else:
    print("Warning: old_apply_hook not found in sketch.py")

sketch_file.write_text(sketch_src, encoding="utf-8")
print("Saved sketch.py")

import py_compile
py_compile.compile(str(sketch_file), doraise=True)
print("sketch.py compiled OK")
