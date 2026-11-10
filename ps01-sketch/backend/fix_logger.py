from pathlib import Path

p = Path("app/api/routes/sketch.py")
text = p.read_text(encoding="utf-8")

old_imports = """import uuid

from fastapi import APIRouter, Depends, HTTPException, status"""

new_imports = """import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

logger = logging.getLogger(__name__)"""

if old_imports in text:
    text = text.replace(old_imports, new_imports)
    p.write_text(text, encoding="utf-8")
    print("Added logging and logger to sketch.py")
else:
    print("Old imports not found")
