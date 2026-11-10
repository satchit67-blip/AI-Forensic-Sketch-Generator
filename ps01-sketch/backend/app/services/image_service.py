"""
services/image_service.py
--------------------------
Zero-budget AI image generation and inpainting pipeline for forensic sketches.

THREE-TIER ARCHITECTURE
=======================

  Tier 1 — HF_API (IMAGE_MODE=hf_api)
      No GPU required.  Uses Hugging Face Inference API free tier.
      Generate : FLUX.1-schnell  (4 steps, forensic sketch quality)
      Inpaint  : stable-diffusion-2-inpainting  (mask-guided edits)
      Requires: HF_TOKEN in .env  (free at huggingface.co/settings/tokens)

  Tier 2 — LOCAL (IMAGE_MODE=local)
      Requires CUDA GPU with 6-8 GB VRAM.
      Generate : FLUX.1-schnell via diffusers  (bfloat16, ~18 GB model)
      Inpaint  : SDXL-inpainting-0.1           (float16, ~6 GB model)
      Models are downloaded on first use and cached in ~/.cache/huggingface.

  Tier 3 — DISABLED (IMAGE_MODE=disabled)
      No image generated.  Endpoint returns traits only.
      Frontend continues with the procedural SVG sketch (FaceSketch.jsx).

GEMINI PROMPT REFINEMENT
========================
Before calling FLUX/SD every generation and inpainting request passes through
Gemini to produce:
  1. An optimised forensic-sketch style generation prompt from SketchTraits.
  2. Per-disguise inpainting prompt modifiers with negative prompts.

This two-model pipeline (Gemini → FLUX/SD) gives much higher quality than
naive keyword concatenation.

INPAINTING MASKS
================
Each disguise type maps to a PIL mask that targets the correct facial region.
Mask coordinates are derived from the FaceSketch.jsx SVG viewport (300×360)
and scaled to the generated image resolution.

  Full Beard       → lower face ellipse  (y 55–87 %)
  Mustache         → narrow band above mouth (y 62–72 %)
  Wire-Rim Glasses → horizontal band across eyes (y 37–52 %)
  Sunglasses       → wider eye band with dark fill (y 35–54 %)
  Long Hair        → left, right and top fringe regions
  Bald             → top cranium ellipse (y 5–35 %)
  Scar/Mark        → narrow right-cheek strip (x 55–70 %, y 28–65 %)
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import os
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
from fastapi import HTTPException, status

from google import genai
from google.genai import types as genai_types

from app.core.config import settings
from app.schemas import SketchTraits

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums & constants
# ---------------------------------------------------------------------------
class ImageMode(str, Enum):
    HF_API   = "hf_api"
    LOCAL    = "local"
    DISABLED = "disabled"


_MODE = ImageMode(settings.IMAGE_MODE)

# Hugging Face Inference API base
import socket
try:
    import dns.resolver
    _dns_resolver = dns.resolver.Resolver(configure=False)
    _dns_resolver.nameservers = ["8.8.8.8", "1.1.1.1", "172.16.1.1"]
    _dns_cache: dict[str, list[str]] = {}
    _orig_getaddrinfo = socket.getaddrinfo

    def _custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if isinstance(host, str) and ("huggingface.co" in host):
            target_host = "router.huggingface.co" if host == "api-inference.huggingface.co" else host
            if target_host not in _dns_cache:
                try:
                    answers = _dns_resolver.resolve(target_host, "A")
                    _dns_cache[target_host] = [r.address for r in answers]
                    logger.info("Custom DNS resolved %s -> %s", target_host, _dns_cache[target_host])
                except Exception as exc:
                    logger.warning("Custom DNS failed for %s (%s); falling back to system", target_host, exc)
            if target_host in _dns_cache and _dns_cache[target_host]:
                ip = _dns_cache[target_host][0]
                return _orig_getaddrinfo(ip, port, family, type, proto, flags)
        return _orig_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = _custom_getaddrinfo
    logger.info("Custom DNS monkey-patch active for Hugging Face endpoints.")
except Exception as exc:
    logger.warning("Could not initialize dnspython custom resolver: %s", exc)

# Hugging Face Inference API base (using official router endpoint)
_HF_BASE = "https://router.huggingface.co/hf-inference/models"

# Photorealistic ID-badge and official forensic identification portrait tokens
_STYLE_POSITIVE = (
    "photorealistic portrait photograph, high-resolution headshot, ID badge photo style, "
    "natural studio lighting, soft neutral background, highly detailed skin texture, pores, "
    "individual hair strands, sharp focus, professional photography"
)
_STYLE_NEGATIVE = (
    "cartoon, illustration, 3d render, anime, painting, vector art, sketch, drawing, "
    "low quality, deformed, blurry"
)

# Hair colour hex → English description (for prompt building)
_HEX_TO_COLOUR: dict[str, str] = {
    "#1c1c20": "jet black",
    "#2b2b2f": "dark",
    "#4a3426": "dark brown",
    "#6b4c35": "light brown",
    "#b9a06a": "blonde",
    "#8a8a90": "grey",
    "#8a3b22": "red",
    "#d4d4d4": "white",
}

# ---------------------------------------------------------------------------
# Gemini prompt model (small, dedicated instance)
# ---------------------------------------------------------------------------
_gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)

_PROMPT_MODEL_CONFIG = genai_types.GenerateContentConfig(
    system_instruction=(
        "You are an expert photographic portrait prompt engineer specialising in "
        "hyper-realistic identification headshots and official ID-style photography. "
        "Output ONLY the refined prompt text requesting a photorealistic portrait photograph, "
        "natural studio lighting, soft neutral background, realistic skin pores, detailed eyes, "
        "and authentic hair with sharp focus. "
        "Never use cartoon, illustration, anime, painting, sketch, or vector styles. No markdown, under 200 tokens."
    ),
    temperature=0.2,
    max_output_tokens=256,
)

# ---------------------------------------------------------------------------
# Local pipeline singletons (lazy-loaded on first use)
# ---------------------------------------------------------------------------
_local_gen_pipe   = None   # FluxPipeline
_local_inpaint_pipe = None # AutoPipelineForInpainting


def _get_local_gen_pipe():
    global _local_gen_pipe
    if _local_gen_pipe is None:
        try:
            import torch
            from diffusers import FluxPipeline
            logger.info("Loading FLUX.1-schnell local pipeline …")
            _local_gen_pipe = FluxPipeline.from_pretrained(
                settings.HF_GENERATE_MODEL,
                torch_dtype=torch.bfloat16,
            ).to("cuda")
            _local_gen_pipe.enable_attention_slicing()
            logger.info("FLUX local pipeline ready.")
        except Exception as exc:
            logger.error("Failed to load local generation pipeline: %s", exc)
            raise
    return _local_gen_pipe


def _get_local_inpaint_pipe():
    global _local_inpaint_pipe
    if _local_inpaint_pipe is None:
        try:
            import torch
            from diffusers import AutoPipelineForInpainting
            logger.info("Loading SDXL inpainting local pipeline …")
            _local_inpaint_pipe = AutoPipelineForInpainting.from_pretrained(
                settings.HF_INPAINT_MODEL,
                torch_dtype=torch.float16,
                variant="fp16",
            ).to("cuda")
            _local_inpaint_pipe.enable_attention_slicing()
            logger.info("SDXL inpaint pipeline ready.")
        except Exception as exc:
            logger.error("Failed to load local inpainting pipeline: %s", exc)
            raise
    return _local_inpaint_pipe


# ---------------------------------------------------------------------------
# PIL mask generators
# Masks are generated at IMAGE_WIDTH × IMAGE_HEIGHT (default 512×640).
# White (255) = area to inpaint | Black (0) = area to PRESERVE.
# Coordinates are derived from FaceSketch.jsx SVG viewport (300×360).
# ---------------------------------------------------------------------------

def _blank_mask(w: int, h: int) -> Image.Image:
    return Image.new("L", (w, h), 0)


def _beard_mask(w: int, h: int) -> Image.Image:
    """Lower face ellipse covering mouth → chin → jaw sides."""
    m = _blank_mask(w, h)
    d = ImageDraw.Draw(m)
    # Centre ellipse on lower 55–87 % of height
    x0, y0 = int(w * 0.18), int(h * 0.55)
    x1, y1 = int(w * 0.82), int(h * 0.88)
    d.ellipse([x0, y0, x1, y1], fill=255)
    return m.filter(ImageFilter.GaussianBlur(radius=12))


def _mustache_mask(w: int, h: int) -> Image.Image:
    """Narrow horizontal band just above the mouth."""
    m = _blank_mask(w, h)
    d = ImageDraw.Draw(m)
    x0, y0 = int(w * 0.28), int(h * 0.62)
    x1, y1 = int(w * 0.72), int(h * 0.72)
    d.ellipse([x0, y0, x1, y1], fill=255)
    return m.filter(ImageFilter.GaussianBlur(radius=8))


def _glasses_mask(w: int, h: int) -> Image.Image:
    """Horizontal band spanning both eye positions."""
    m = _blank_mask(w, h)
    d = ImageDraw.Draw(m)
    x0, y0 = int(w * 0.10), int(h * 0.37)
    x1, y1 = int(w * 0.90), int(h * 0.52)
    d.rectangle([x0, y0, x1, y1], fill=255)
    return m.filter(ImageFilter.GaussianBlur(radius=10))


def _sunglasses_mask(w: int, h: int) -> Image.Image:
    """Slightly wider/taller variant of the glasses mask."""
    m = _blank_mask(w, h)
    d = ImageDraw.Draw(m)
    x0, y0 = int(w * 0.08), int(h * 0.35)
    x1, y1 = int(w * 0.92), int(h * 0.54)
    d.rectangle([x0, y0, x1, y1], fill=255)
    return m.filter(ImageFilter.GaussianBlur(radius=10))


def _long_hair_mask(w: int, h: int) -> Image.Image:
    """Left shoulder, right shoulder, and top-fringe regions."""
    m = _blank_mask(w, h)
    d = ImageDraw.Draw(m)
    # Left side
    d.rectangle([0, int(h * 0.15), int(w * 0.22), h], fill=255)
    # Right side
    d.rectangle([int(w * 0.78), int(h * 0.15), w, h], fill=255)
    # Top fringe
    d.rectangle([int(w * 0.1), 0, int(w * 0.9), int(h * 0.22)], fill=255)
    return m.filter(ImageFilter.GaussianBlur(radius=14))


def _bald_mask(w: int, h: int) -> Image.Image:
    """Top cranium ellipse — removes hair and reveals scalp."""
    m = _blank_mask(w, h)
    d = ImageDraw.Draw(m)
    x0, y0 = int(w * 0.12), int(h * 0.03)
    x1, y1 = int(w * 0.88), int(h * 0.38)
    d.ellipse([x0, y0, x1, y1], fill=255)
    return m.filter(ImageFilter.GaussianBlur(radius=14))


def _scar_mask(w: int, h: int) -> Image.Image:
    """Narrow diagonal strip on the right cheek."""
    m = _blank_mask(w, h)
    d = ImageDraw.Draw(m)
    x0, y0 = int(w * 0.54), int(h * 0.27)
    x1, y1 = int(w * 0.70), int(h * 0.65)
    d.rectangle([x0, y0, x1, y1], fill=255)
    return m.filter(ImageFilter.GaussianBlur(radius=6))


# Map disguise name → mask function
DISGUISE_MASKS: dict[str, callable] = {
    "Full Beard":          _beard_mask,
    "Mustache":            _mustache_mask,
    "Wire-Rimmed Glasses": _glasses_mask,
    "Sunglasses":          _sunglasses_mask,
    "Long Hair":           _long_hair_mask,
    "Bald":                _bald_mask,
    "Scar/Mark":           _scar_mask,
}

# Per-disguise inpainting prompt additions (positive, negative)
DISGUISE_PROMPT_MODIFIERS: dict[str, tuple[str, str]] = {
    "Full Beard": (
        "photorealistic thick full beard, natural facial hair stubble, realistic skin texture and lighting",
        "clean shaven, no beard, smooth chin, cartoon, drawing",
    ),
    "Mustache": (
        "photorealistic neat mustache, authentic facial hair above upper lip, fine hair strands",
        "no mustache, clean upper lip, cartoon, drawing",
    ),
    "Wire-Rimmed Glasses": (
        "photorealistic wire-rimmed eyeglasses, thin metal frame, authentic optical reflections, clear glass lenses",
        "no glasses, sunglasses, cartoon, drawing",
    ),
    "Sunglasses": (
        "photorealistic dark sunglasses, acetate frame, subtle studio reflections, authentic tinted lenses",
        "no sunglasses, cartoon, drawing",
    ),
    "Long Hair": (
        "photorealistic long hair past shoulders, detailed individual hair strands, natural volume and shine",
        "short hair, bald, cartoon, drawing",
    ),
    "Bald": (
        "photorealistic clean shaved bald head, smooth scalp, natural skin texture and studio highlights",
        "hair, long hair, short hair, cartoon, drawing",
    ),
    "Scar/Mark": (
        "photorealistic subtle facial scar mark on cheek, authentic healed scar tissue texture",
        "smooth skin, no scar, cartoon, drawing",
    ),
}

# Removal modifiers — used when active=False (removing a disguise)
DISGUISE_REMOVAL_MODIFIERS: dict[str, tuple[str, str]] = {
    "Full Beard":          ("clean-shaven smooth chin, no beard, photorealistic skin", "beard, stubble, cartoon"),
    "Mustache":            ("clean upper lip, no mustache, photorealistic skin",       "mustache, cartoon"),
    "Wire-Rimmed Glasses": ("no glasses, bare eyes, photorealistic eye detail",        "glasses, spectacles, cartoon"),
    "Sunglasses":          ("no sunglasses, visible eyes, natural studio lighting",     "sunglasses, shades, cartoon"),
    "Long Hair":           ("neat short cropped hair, natural hair texture",           "long hair, flowing hair, cartoon"),
    "Bald":                ("short hair, natural hairline, realistic hair follicles",   "bald, shaved, cartoon"),
    "Scar/Mark":           ("smooth healthy skin, no scar, natural skin pores",       "scar, mark, cartoon"),
}


# ---------------------------------------------------------------------------
# Gemini prompt builders
# ---------------------------------------------------------------------------
def _colour_name(hex_val: str) -> str:
    return _HEX_TO_COLOUR.get(hex_val.lower(), "dark")


def _traits_to_base_prompt(traits: SketchTraits, description: str = "") -> str:
    """Build a readable prompt fragment from SketchTraits with explicit ethnic & facial descriptors."""
    parts: list[str] = [_STYLE_POSITIVE]

    # Explicit ethnic & complexion descriptors (default: authentic South Asian forensic profile, or witness-specific)
    desc_lower = (description or "").lower()
    if any(k in desc_lower for k in ["south asian", "indian", "desi", "brown", "tan", "wheatish", "asian"]):
        ethnic_profile = "South Asian male, medium-tan complexion, dark brown almond eyes, authentic Indian male facial structure"
    elif any(k in desc_lower for k in ["black", "african", "dark skin"]):
        ethnic_profile = "African / Black male, rich dark complexion, prominent brown eyes, authentic facial features"
    elif any(k in desc_lower for k in ["caucasian", "white", "fair", "european"]):
        ethnic_profile = "Caucasian male, fair complexion, detailed facial structure"
    elif any(k in desc_lower for k in ["east asian", "chinese", "japanese", "korean"]):
        ethnic_profile = "East Asian male, medium complexion, characteristic almond eye shape"
    elif any(k in desc_lower for k in ["hispanic", "latino"]):
        ethnic_profile = "Hispanic / Latino male, olive-tan complexion, dark eyes"
    else:
        # Default per requirement: "South Asian male, medium-tan complexion, dark brown almond eyes"
        ethnic_profile = "South Asian male, medium-tan complexion, dark brown almond eyes, authentic South Asian facial bone structure"

    parts.append(ethnic_profile)

    jaw_desc = "sharp angular jawline, chiseled defined jaw" if traits.jaw == "sharp" else "soft rounded jawline, oval lower face"
    parts.append(jaw_desc)

    if traits.hair == "bald":
        parts.append("completely bald, clean shaved head, visible scalp contours")
    else:
        colour = _colour_name(traits.hair_color)
        length = "short cropped" if traits.hair == "short" else "long flowing"
        parts.append(f"{colour} {length} textured hair")

    face_desc = (
        "wide broad face, strong cheekbones" if traits.face >= 1.08
        else "narrow thin face, slender gaunt cheeks" if traits.face <= 0.92
        else "proportional balanced face shape"
    )
    parts.append(face_desc)

    # Active modifications / disguises explicitly concatenated
    for d in traits.disguises:
        pos, _ = DISGUISE_PROMPT_MODIFIERS.get(d, (d.lower(), ""))
        parts.append(f"with {d.lower()} ({pos})")

    if description:
        # Append sanitized witness description
        parts.append(f"witness statement: {description[:200]}")

    return ", ".join(parts)


async def _gemini_enhance_prompt(base_prompt: str, context: str) -> str:
    """
    Ask Gemini to refine a raw keyword prompt into a photorealistic forensic-art description.
    Falls back to base_prompt if Gemini is unavailable.
    """
    query = (
        f"Refine this Stable Diffusion / FLUX prompt for a professional, hyper-realistic photographic portrait headshot. "
        f"Style: photorealistic portrait photograph, high-resolution headshot, ID badge photo style, natural studio lighting, "
        f"soft neutral background, highly detailed skin texture, pores, individual hair strands, sharp focus, professional photography. "
        f"Context: {context}\n\n"
        f"Base prompt: {base_prompt}"
    )
    try:
        resp = await _gemini_client.aio.models.generate_content(
            model="gemini-1.5-flash",
            contents=query,
            config=_PROMPT_MODEL_CONFIG,
        )
        enhanced = resp.text.strip()
        logger.debug("Gemini enhanced prompt: %s", enhanced[:100])
        return enhanced if enhanced else base_prompt
    except Exception as exc:
        logger.warning("Gemini prompt enhancement failed (%s); using base prompt", exc)
        return base_prompt


async def _gemini_inpaint_prompt(
    disguise_name: str,
    traits: SketchTraits,
    active: bool,
) -> tuple[str, str]:
    """
    Ask Gemini to generate a precise inpainting prompt for a specific disguise toggle.

    Returns (positive_prompt, negative_prompt).
    """
    if active:
        pos_base, neg_base = DISGUISE_PROMPT_MODIFIERS.get(
            disguise_name, (disguise_name.lower(), "")
        )
        direction = f"ADD '{disguise_name}' to this forensic sketch"
    else:
        pos_base, neg_base = DISGUISE_REMOVAL_MODIFIERS.get(
            disguise_name, (f"no {disguise_name.lower()}", disguise_name.lower())
        )
        direction = f"REMOVE '{disguise_name}' from this forensic sketch"

    query = (
        f"Generate a Stable Diffusion inpainting prompt to {direction}. "
        f"Current traits: jaw={traits.jaw}, hair={traits.hair}, hair_color={traits.hair_color}. "
        f"Return two lines only:\n"
        f"POSITIVE: <positive prompt>\n"
        f"NEGATIVE: <negative prompt>"
    )
    try:
        resp = await _gemini_client.aio.models.generate_content(
            model="gemini-1.5-flash",
            contents=query,
            config=_PROMPT_MODEL_CONFIG,
        )
        lines = [ln.strip() for ln in resp.text.strip().splitlines() if ln.strip()]
        pos = next((l.split(":", 1)[1].strip() for l in lines if l.upper().startswith("POSITIVE")), pos_base)
        neg = next((l.split(":", 1)[1].strip() for l in lines if l.upper().startswith("NEGATIVE")), neg_base)
        return f"{_STYLE_POSITIVE}, {pos}", f"{_STYLE_NEGATIVE}, {neg}"
    except Exception as exc:
        logger.warning("Gemini inpaint prompt failed (%s); using default modifier", exc)
        return f"{_STYLE_POSITIVE}, {pos_base}", f"{_STYLE_NEGATIVE}, {neg_base}"


# ---------------------------------------------------------------------------
# Image encode / decode helpers
# ---------------------------------------------------------------------------
def _pil_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _pil_to_b64(img: Image.Image, fmt: str = "PNG") -> str:
    return base64.b64encode(_pil_to_bytes(img, fmt)).decode()


def _bytes_to_pil(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def _b64_to_pil(b64: str) -> Image.Image:
    return _bytes_to_pil(base64.b64decode(b64))


_MASTER_SKETCH_PATH = Path(__file__).resolve().parent.parent / "static" / "forensic_master.png"
_CACHED_MASTER_B64: str | None = None

FALLBACK_SVG_STRING = (
    '<svg viewBox="0 0 300 360" xmlns="http://www.w3.org/2000/svg" width="100%" height="100%">'
    '<defs>'
    '<linearGradient id="parchment" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0%" stop-color="#f0ebe0"/>'
    '<stop offset="100%" stop-color="#dfd6c5"/>'
    '</linearGradient>'
    '<pattern id="charcoalHatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
    '<line x1="0" y1="0" x2="0" y2="4" stroke="#222" stroke-width="0.8" opacity="0.18"/>'
    '</pattern>'
    '<filter id="paperNoise">'
    '<feTurbulence baseFrequency="0.04" numOctaves="3" result="noise"/>'
    '<feColorMatrix type="matrix" values="0.33 0.33 0.33 0 0  0.33 0.33 0.33 0 0  0.33 0.33 0.33 0 0  0 0 0 0.08 0"/>'
    '<feBlend in="SourceGraphic" in2="noise" mode="multiply"/>'
    '</filter>'
    '</defs>'
    '<rect width="300" height="360" fill="url(#parchment)"/>'
    '<rect width="300" height="360" fill="url(#charcoalHatch)"/>'
    '<g filter="url(#paperNoise)">'
    # Neck and collar
    '<path d="M110 260 L90 340 L210 340 L190 260Z" fill="#cfc1ae" stroke="#222" stroke-width="1.8"/>'
    # Head and jawline
    '<path d="M96 140 C96 65 204 65 204 140 L200 235 L174 290 L126 290 L100 235Z" fill="#decab4" stroke="#222" stroke-width="2.2" stroke-linejoin="round"/>'
    # Shading overlay
    '<path d="M96 140 C96 65 204 65 204 140 L200 235 L174 290 L126 290 L100 235Z" fill="url(#charcoalHatch)"/>'
    # Realistic hair
    '<path d="M90 145 C78 60 222 60 210 145 C202 100 188 85 150 85 C112 85 98 100 90 145Z" fill="#242226"/>'
    # Brow line and eye sockets
    '<path d="M106 135 Q125 125 142 133 M158 133 Q175 125 194 135" stroke="#1f1e22" stroke-width="2.6" fill="none" stroke-linecap="round"/>'
    # Eyes with pupils & highlights
    '<ellipse cx="124" cy="153" rx="12" ry="6" fill="#fff" stroke="#1f1e22" stroke-width="1.6"/>'
    '<circle cx="124" cy="153" r="3.4" fill="#1f1e22"/>'
    '<circle cx="125" cy="152" r="1" fill="#fff"/>'
    '<ellipse cx="176" cy="153" rx="12" ry="6" fill="#fff" stroke="#1f1e22" stroke-width="1.6"/>'
    '<circle cx="176" cy="153" r="3.4" fill="#1f1e22"/>'
    '<circle cx="177" cy="152" r="1" fill="#fff"/>'
    # Nose structure
    '<path d="M150 142 L143 202 Q150 210 157 202" stroke="#1f1e22" stroke-width="2" fill="none" stroke-linecap="round"/>'
    # Lips with chiaroscuro depth
    '<path d="M132 245 Q150 252 168 245" stroke="#1f1e22" stroke-width="2" fill="none"/>'
    '<path d="M136 248 Q150 258 164 248" stroke="#1f1e22" stroke-width="1.4" fill="none"/>'
    '</g>'
    '<text x="14" y="348" font-family="monospace" font-size="8.5" fill="#444" font-weight="bold">METROPOLITAN POLICE · FORENSIC SKETCH COMPOSITE · #HACK26-451</text>'
    '</svg>'
)


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 6:
        try:
            return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return (40, 38, 42)


def generate_dynamic_forensic_sketch(
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
    return buf.getvalue()

def get_fallback_sketch_b64(traits: SketchTraits | None = None, description: str = "") -> str:
    """Generate dynamic, input-sensitive forensic sketch art tailored to traits and witness description."""
    safe_traits = traits or SketchTraits()
    raw_bytes = generate_dynamic_forensic_sketch(
        description=description,
        jaw=safe_traits.jaw,
        hair=safe_traits.hair,
        hair_color=safe_traits.hair_color,
        face_scale=safe_traits.face,
        disguises=list(safe_traits.disguises),
    )
    return base64.b64encode(raw_bytes).decode("utf-8")


def get_fallback_sketch_data_uri(traits: SketchTraits | None = None, description: str = "") -> str:
    """Return a strictly valid, fully-formed data URI string starting with data:image/jpeg;base64,..."""
    raw_b64 = get_fallback_sketch_b64(traits=traits, description=description)
    return f"data:image/jpeg;base64,{raw_b64}"


def _save_image(img_bytes: bytes, case_id: str, label: str) -> str:
    """Persist image to IMAGE_STORE_PATH; return relative path."""
    store = Path(settings.IMAGE_STORE_PATH)
    store.mkdir(parents=True, exist_ok=True)
    filename = f"{case_id}_{label}.png"
    path = store / filename
    path.write_bytes(img_bytes)
    return str(path)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Stable deterministic seed generation & in-memory image cache
# ---------------------------------------------------------------------------
_IMAGE_CACHE: dict[str, bytes] = {}


def get_deterministic_seed(base_text: str) -> int:
    """
    Derive a stable, deterministic integer seed from the base witness description text.
    Ensures the exact same suspect description always anchors the exact same base face.
    Formula: int(hashlib.md5(base_description.encode()).hexdigest(), 16) % 1000000
    """
    import hashlib
    clean = (base_text or "").strip().lower()
    if not clean:
        clean = "suspect portrait"
    return int(hashlib.md5(clean.encode("utf-8")).hexdigest(), 16) % 1000000

# HF Inference API calls  (async httpx)
# ---------------------------------------------------------------------------
def _hf_headers() -> dict[str, str]:
    token = settings.HF_TOKEN
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _pollinations_generate(prompt: str, seed: int | None = None) -> bytes:
    """
    Primary image generator via Pollinations.ai (free, zero-token API).
    Uses a deterministic seed derived from the base witness description so that
    identical prompt and seed pairs generate a consistent, stable base face.
    """
    import urllib.parse
    import re

    # Stable deterministic seed derived from prompt if not explicitly passed
    current_seed = seed if seed is not None else get_deterministic_seed(prompt)
    cache_key = f"{prompt.strip()}_{current_seed}"

    # Return cached image for exact identical prompt & seed
    if cache_key in _IMAGE_CACHE:
        logger.info("Returning cached deterministic image for key: %s (size=%d bytes)", cache_key[:60], len(_IMAGE_CACHE[cache_key]))
        return _IMAGE_CACHE[cache_key]

    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true&seed={current_seed}"

    async with httpx.AsyncClient(
        timeout=120.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    ) as client:
        for attempt in range(4):
            logger.info("Pollinations generate GET (attempt %d/4, seed=%d) -> %s", attempt + 1, current_seed, url[:120])
            try:
                resp = await client.get(url)
            except Exception as net_err:
                logger.warning("Pollinations network error on attempt %d: %s", attempt + 1, net_err)
                if attempt < 3:
                    await asyncio.sleep(3)
                    continue
                raise HTTPException(status_code=503, detail=f"Pollinations network error: {net_err}")

            logger.info("Pollinations response code: %d, size: %d bytes (seed=%d)", resp.status_code, len(resp.content), current_seed)
            if resp.status_code == 200 and len(resp.content) > 1000:
                _IMAGE_CACHE[cache_key] = resp.content
                return resp.content

            # Handle 1 image every 45s rate limit gracefully
            if resp.status_code == 402 and "FREE_LIMIT" in resp.text:
                match = re.search(r"Retry after (\d+)s", resp.text)
                wait_sec = int(match.group(1)) + 2 if match else 20
                logger.warning("Pollinations rate limit hit. Waiting %ds before retry attempt %d...", wait_sec, attempt + 1)
                await asyncio.sleep(min(wait_sec, 45))
                continue

            # Handle transient upstream 500, 502, 503, 504 errors
            if resp.status_code in (500, 502, 503, 504) and attempt < 3:
                logger.warning("Pollinations returned transient %d, waiting 4s before retry...", resp.status_code)
                await asyncio.sleep(4)
                continue

            err_body = resp.text[:200]
            raise HTTPException(
                status_code=resp.status_code if resp.status_code != 200 else 502,
                detail=f"Pollinations API error {resp.status_code}: {err_body}",
            )

        raise HTTPException(
            status_code=503,
            detail="Pollinations API temporarily unavailable after retries.",
        )


async def _hf_generate(prompt: str) -> bytes:
    """
    Secondary: Hugging Face inference API.
    Tries Pollinations first; HF is kept as named function for inpainting callers.
    """
    url = f"{_HF_BASE}/{settings.HF_GENERATE_MODEL}"
    payload = {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": 25,
            "guidance_scale": 7.5,
            "width": settings.IMAGE_WIDTH,
            "height": settings.IMAGE_HEIGHT,
            "negative_prompt": _STYLE_NEGATIVE,
        },
    }
    logger.info("HF generate POST -> %s", url)
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(url, headers=_hf_headers(), json=payload)
        logger.info("HF response code: %d", resp.status_code)
        if resp.status_code == 200:
            return resp.content
        err_body = resp.text[:400]
        logger.error("Hugging Face API error %d: %s", resp.status_code, err_body)
        raise RuntimeError(
            f"Hugging Face API ({settings.HF_GENERATE_MODEL}) returned HTTP {resp.status_code}: {err_body}"
        )



async def _hf_inpaint(
    image: Image.Image,
    mask: Image.Image,
    positive_prompt: str,
    negative_prompt: str,
) -> bytes:
    """
    Inpaint the masked region via HF Inference API using SD2-inpainting.
    Mask: white = repaint, black = preserve (standard SD convention).
    Returns raw PNG bytes.
    """
    url = f"{_HF_BASE}/{settings.HF_INPAINT_MODEL}"

    # Resize inputs to 512×512 (SD2 native resolution)
    target = (512, 512)
    image_rs  = image.resize(target, Image.LANCZOS)
    mask_rs   = mask.resize(target, Image.NEAREST)

    # Encode as base64 strings for JSON transport
    img_b64  = _pil_to_b64(image_rs)
    mask_b64 = _pil_to_b64(mask_rs.convert("RGB"))

    payload = {
        "inputs": positive_prompt,
        "image":       img_b64,
        "mask_image":  mask_b64,
        "parameters": {
            "negative_prompt":      negative_prompt,
            "num_inference_steps":  25,
            "guidance_scale":       8.5,
            "strength":             0.92,   # high = more edit, low = more preservation
            "width":  512,
            "height": 512,
        },
    }
    logger.info("HF inpaint request → %s", settings.HF_INPAINT_MODEL)
    async with httpx.AsyncClient(timeout=240.0) as client:
        for attempt in range(3):
            resp = await client.post(url, headers=_hf_headers(), json=payload)
            if resp.status_code == 200:
                # Upscale back to original resolution
                result = _bytes_to_pil(resp.content).resize(
                    (settings.IMAGE_WIDTH, settings.IMAGE_HEIGHT), Image.LANCZOS
                )
                return _pil_to_bytes(result)
            if resp.status_code == 503:
                wait = int(resp.headers.get("X-Wait-For-Model", "25"))
                logger.warning("HF inpaint model loading; retrying in %ds", wait)
                await asyncio.sleep(min(wait, 40))
                continue
            if resp.status_code == 429:
                raise HTTPException(status_code=429, detail="HF API rate limit.")
            raise HTTPException(
                status_code=502,
                detail=f"HF inpaint API error {resp.status_code}: {resp.text[:200]}",
            )
    raise HTTPException(status_code=503, detail="HF inpaint model unavailable after retries.")


# ---------------------------------------------------------------------------
# Local diffusers calls (wrapped in asyncio.to_thread to avoid blocking loop)
# ---------------------------------------------------------------------------
def _local_generate_sync(prompt: str) -> bytes:
    import torch
    pipe = _get_local_gen_pipe()
    with torch.inference_mode():
        result = pipe(
            prompt=prompt,
            num_inference_steps=4,
            guidance_scale=0.0,
            width=settings.IMAGE_WIDTH,
            height=settings.IMAGE_HEIGHT,
        )
    return _pil_to_bytes(result.images[0])


def _local_inpaint_sync(
    image: Image.Image,
    mask: Image.Image,
    positive_prompt: str,
    negative_prompt: str,
) -> bytes:
    import torch
    pipe = _get_local_inpaint_pipe()
    target = (512, 512)
    image_rs = image.resize(target, Image.LANCZOS)
    mask_rs  = mask.resize(target, Image.NEAREST)
    with torch.inference_mode():
        result = pipe(
            prompt=positive_prompt,
            negative_prompt=negative_prompt,
            image=image_rs,
            mask_image=mask_rs,
            num_inference_steps=25,
            guidance_scale=8.5,
            strength=0.90,
            width=512,
            height=512,
        )
    output = result.images[0].resize(
        (settings.IMAGE_WIDTH, settings.IMAGE_HEIGHT), Image.LANCZOS
    )
    return _pil_to_bytes(output)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def build_strict_prompt(traits: SketchTraits, description: str = "") -> str:
    """
    Build a strictly structured forensic composite prompt from witness traits & disguises.
    Template:
    'Forensic composite sketch portrait of a [age]-year-old individual, [hair description],
    featuring a [mustache description] and [beard description], [disguise toggles like sunglasses/glasses],
    highly detailed facial features, consistent mugshot style, black and white or sharp line art.'
    """
    # 1. Age extraction
    age = "30"
    for note in (traits.notes or []) + ([description] if description else []):
        if not note:
            continue
        m = re.search(r"\b(\d{1,2})(?:['’]?s)?\b", note)
        if m:
            val = int(m.group(1))
            if 10 <= val <= 99:
                age = str(val)
                break

    # 2. Hair description
    active_disguises = set(traits.disguises or [])
    if traits.hair == "bald" or "Bald" in active_disguises:
        hair_desc = "bald head with visible scalp contours"
    else:
        colour_name = _colour_name(getattr(traits, "hair_color", "#2b2b2f"))
        length = "long flowing hair" if (traits.hair == "long" or "Long Hair" in active_disguises) else "short cropped hair"
        hair_desc = f"{colour_name} {length}"

    # 3. Mustache description
    if "Mustache" in active_disguises:
        mustache_desc = "distinct mustache above the upper lip"
    else:
        mustache_desc = "no mustache"

    # 4. Beard description
    if "Full Beard" in active_disguises:
        beard_desc = "full facial beard along the jawline"
    else:
        beard_desc = "clean shaven jaw and chin"

    # 5. Disguise toggles (glasses, sunglasses, scars)
    other_disguises = []
    if "Sunglasses" in active_disguises:
        other_disguises.append("dark tinted sunglasses covering eyes")
    if "Wire-Rimmed Glasses" in active_disguises:
        other_disguises.append("wire-rimmed eyeglasses")
    if "Scar/Mark" in active_disguises:
        other_disguises.append("prominent facial scar")

    disguise_str = ", ".join(other_disguises) if other_disguises else "no eyewear"

    return (
        f"Forensic composite sketch portrait of a {age}-year-old individual, {hair_desc}, "
        f"featuring a {mustache_desc} and {beard_desc}, {disguise_str}, "
        f"highly detailed facial features, consistent mugshot style, black and white or sharp line art."
    )


def deterministic_seed_from_traits(traits: SketchTraits) -> int:
    """
    Derive a stable, deterministic integer seed from base facial traits and active disguise modifiers.
    Keeps core facial features stable while dynamically adapting to disguise toggle additions.
    """
    base_identity = f"jaw:{traits.jaw}|hair:{traits.hair}|color:{traits.hair_color}|face:{round(traits.face, 2)}"
    active_disguises = sorted(list(set(traits.disguises or [])))
    disguise_str = ",".join(active_disguises)
    seed_str = f"{base_identity}#{disguise_str}"
    return int(hashlib.md5(seed_str.encode("utf-8")).hexdigest(), 16) % 1000000


async def generate_sketch_image(
    traits: SketchTraits,
    description: str,
    case_id: str,
    seed: int | None = None,
) -> tuple[str, str]:
    """
    Generate sketch image directly from dynamic textual prompt with stable deterministic seed.
    Passes prompt cleanly to Pollinations.ai without hardcoded 3D style prefixes.
    """
    # Build a strict forensic prompt based on the full trait set
    strict_prompt = build_strict_prompt(traits, description=description)
    # Compute deterministic seed from traits (ignores any supplied seed)
    deterministic_seed = deterministic_seed_from_traits(traits)
    logger.info(
        "Generating sketch - prompt: %s | seed: %s (original seed ignored)",
        strict_prompt,
        deterministic_seed,
    )
    img_bytes = await _pollinations_generate(strict_prompt, seed=deterministic_seed)
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return b64, strict_prompt



async def refine_sketch_image(
    image_b64: str,
    traits: SketchTraits,
    disguise_name: str,
    active: bool,
    case_id: str,
) -> tuple[str, str, str]:
    """
    Apply or remove a disguise overlay using inpainting.

    Parameters
    ----------
    image_b64    : base64-encoded current sketch image
    traits       : current SketchTraits (used for prompt context)
    disguise_name: one of the 7 DISGUISES from face.js
    active       : True = add disguise, False = remove
    case_id      : for storage naming

    Returns
    -------
    (refined_image_b64, positive_prompt_used, negative_prompt_used)

    Raises
    ------
    HTTP 400 — unknown disguise name
    HTTP 503 — generation backend unavailable
    """
    if _MODE == ImageMode.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image mode is 'disabled'. Set IMAGE_MODE=hf_api or local in .env.",
        )

    if disguise_name not in DISGUISE_MASKS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown disguise '{disguise_name}'. "
                f"Valid options: {list(DISGUISE_MASKS.keys())}"
            ),
        )

    # 1. Decode the input image
    source_img = _b64_to_pil(image_b64)

    # 2. Generate the appropriate mask
    mask_fn = DISGUISE_MASKS[disguise_name]
    mask = mask_fn(settings.IMAGE_WIDTH, settings.IMAGE_HEIGHT)

    # 3. Ask Gemini to build precise inpainting prompts
    pos_prompt, neg_prompt = await _gemini_inpaint_prompt(disguise_name, traits, active)

    logger.info(
        "Inpainting [%s %s] | pos: %s… | neg: %s…",
        "ADD" if active else "REMOVE",
        disguise_name,
        pos_prompt[:60],
        neg_prompt[:40],
    )

    # 4. Run inpainting
    try:
        if _MODE == ImageMode.HF_API:
            refined_bytes = await _hf_inpaint(source_img, mask, pos_prompt, neg_prompt)
        else:  # LOCAL
            refined_bytes = await asyncio.to_thread(
                _local_inpaint_sync, source_img, mask, pos_prompt, neg_prompt
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Inpainting backend error: %s", exc)
        raise HTTPException(status_code=503, detail=f"Inpainting failed: {exc}")

    # 5. Optional: save to disk
    verb = "add" if active else "rem"
    label = f"{verb}_{disguise_name.lower().replace(' ', '_').replace('/', '')}"
    try:
        _save_image(refined_bytes, case_id, label)
    except Exception:
        pass

    b64_out = base64.b64encode(refined_bytes).decode()
    return b64_out, pos_prompt, neg_prompt
