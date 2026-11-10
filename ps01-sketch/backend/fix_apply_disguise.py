from pathlib import Path
p = Path("app/api/routes/sketch.py")
text = p.read_text(encoding="utf-8")

old = """        # Build dynamic prompt with updated disguise set
    desc = (body.description or "").strip()
    active_disguises = list(current_traits.disguises)
    if active_disguises:
        final_prompt = f"A forensic police sketch portrait of {desc} wearing {', '.join(active_disguises)}"
    else:
        final_prompt = f"A forensic police sketch portrait of {desc}" """

# Let's normalize newlines to check
lines = text.splitlines()
idx_start = -1
for i, line in enumerate(lines):
    if "Build dynamic prompt with updated disguise set" in line:
        idx_start = i
        break

if idx_start != -1:
    # replace lines idx_start to idx_start + 6
    replacement = [
        "    # Build dynamic prompt with raw description as base and active chips as modifiers",
        "    raw_desc = (body.description or \"\").strip()",
        "    final_prompt = assemble_dynamic_prompt(raw_desc, current_traits.disguises)"
    ]
    # find where raw_b64 starts
    idx_end = idx_start
    while idx_end < len(lines) and "raw_b64" not in lines[idx_end]:
        idx_end += 1
    new_lines = lines[:idx_start] + replacement + lines[idx_end:]
    p.write_text("\n".join(new_lines), encoding="utf-8")
    print(f"Replaced lines {idx_start} to {idx_end} successfully!")
else:
    print("Could not find line 'Build dynamic prompt with updated disguise set'")
