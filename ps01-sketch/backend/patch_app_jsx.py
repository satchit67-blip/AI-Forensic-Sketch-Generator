from pathlib import Path

p = Path("c:/Anubhav/Hackfest 26'/ps01-sketch/ps01-sketch/src/App.jsx")
text = p.read_text(encoding="utf-8")

old_1 = "description: promptPayload,\n              disguises: activeDisguisesList,"
new_1 = "description: trimmed,\n              disguises: activeDisguisesList,"

old_2 = "description: promptText,\n          }),"
new_2 = 'description: (description || "").trim(),\n          }),'

if old_1 in text:
    text = text.replace(old_1, new_1)
    print("Replaced synth payload in App.jsx")

if old_2 in text:
    text = text.replace(old_2, new_2)
    print("Replaced apply-disguise payload in App.jsx")

p.write_text(text, encoding="utf-8")
print("Done updating App.jsx")
