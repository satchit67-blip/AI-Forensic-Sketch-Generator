"""Fix the unclosed raise RuntimeError( at line 739."""
from pathlib import Path
import py_compile, sys

f = Path("app/services/image_service.py")
lines = f.read_text(encoding="utf-8").splitlines(keepends=True)

# Replace lines 739-741 (0-indexed 738-740) with a single clean line
assert "raise RuntimeError(" in lines[738], repr(lines[738])
lines[738] = '            raise RuntimeError("[HF DEBUG] FATAL status=" + str(resp.status_code) + " | Body: " + resp.text[:800])\n'
del lines[739]  # remove '                "[HF DEBUG] FATAL status=..." + str(resp.status_code)\n'
del lines[739]  # remove '                + " | Body: " + resp.text[:800]\n'

f.write_text("".join(lines), encoding="utf-8")
print("Fixed. Verifying syntax ...")
try:
    py_compile.compile(str(f), doraise=True)
    print("Syntax OK!")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
