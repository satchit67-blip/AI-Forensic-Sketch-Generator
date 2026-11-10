"""
api/routes/image.py
-------------------
FastAPI route controller for AI image generation and disguise inpainting.

Endpoints
---------
  GET  /image/status       Report the active image mode and available models
  POST /image/generate     Generate initial forensic sketch image (FLUX/SD)
  POST /image/refine       Apply / remove a disguise via inpainting (SD2-inpainting)

Pipeline flow
-------------

  ┌─────────────────────────────────────────────────────────────────────┐
  │  POST /image/generate                                               │
  │                                                                     │
  │  1. Validate JWT + require_officer                                  │
  │  2. Receive: description + traits (from /generate-sketch) + case_id │
  │  3. image_service.generate_sketch_image()                           │
  │        a. _traits_to_base_prompt()  → keyword prompt               │
  │        b. Gemini enhances prompt    → coherent forensic description │
  │        c. FLUX.1-schnell via HF API → PNG bytes                    │
  │  4. Write precise audit log: "Generated AI Sketch Image"            │
  │  5. Return base64 PNG + prompt_used                                 │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │  POST /image/refine                                                 │
  │                                                                     │
  │  1. Validate JWT + require_officer                                  │
  │  2. Receive: image_b64 + current_traits + disguise_name + active   │
  │  3. image_service.refine_sketch_image()                             │
  │        a. Decode base64 image → PIL                                 │
  │        b. Generate PIL mask for the disguise region                 │
  │        c. Gemini builds precise inpainting prompts (+/-)            │
  │        d. SD2-inpainting via HF API → refined PNG bytes            │
  │  4. Write precise audit log: "Applied/Removed Disguise: Full Beard  │
  │     (AI inpainting)"                                                │
  │  5. Return refined base64 PNG + prompts used                        │
  └─────────────────────────────────────────────────────────────────────┘

Note: The AuditMiddleware also writes a coarse entry automatically.
Both entries appear in the audit log — the middleware's generic string
and the route's precise string with the disguise name.

Frontend integration
--------------------
After calling /image/generate, store image_b64 in React state.
For each disguise toggle, call /image/refine with the current image_b64.
Render the returned image_b64 as: <img src={`data:image/png;base64,${image_b64}`} />
alongside (or replacing) the SVG procedural sketch.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import (
    AuditRecorder,
    get_audit_recorder_safe,
    get_current_user_or_demo,
    get_db_optional,
)
from app.models import User
from app.schemas import (
    ImageGenerateRequest,
    ImageGenerateResponse,
    ImageRefineRequest,
    ImageRefineResponse,
    ImageStatusResponse,
)
from app.services import image_service
from app.services.image_service import DISGUISE_MASKS, ImageMode, _MODE

router = APIRouter(prefix="/image", tags=["Image Generation & Inpainting"])


# ---------------------------------------------------------------------------
# GET /image/status
# ---------------------------------------------------------------------------
@router.get(
    "/status",
    response_model=ImageStatusResponse,
    summary="Report active image generation mode",
    description=(
        "Returns which image mode is active (hf_api / local / disabled), "
        "which models are configured, and whether HF_TOKEN is set."
    ),
)
async def image_status(
    _user: User = Depends(get_current_user_or_demo),
) -> ImageStatusResponse:
    return ImageStatusResponse(
        image_mode=settings.IMAGE_MODE,
        generate_model=settings.HF_GENERATE_MODEL,
        inpaint_model=settings.HF_INPAINT_MODEL,
        hf_token_set=bool(settings.HF_TOKEN and not settings.HF_TOKEN.startswith("hf_placeholder")),
        available_disguises=list(DISGUISE_MASKS.keys()),
    )


# ---------------------------------------------------------------------------
# POST /image/generate
# ---------------------------------------------------------------------------
@router.post(
    "/generate",
    response_model=ImageGenerateResponse,
    summary="Generate an initial AI forensic sketch image",
    description=(
        "Accepts parsed SketchTraits (from /generate-sketch) and the original "
        "witness description.  Gemini refines the prompt and FLUX.1-schnell "
        "generates a forensic pencil-sketch style image.  "
        "Returns the image as a base64 PNG string for direct use in an <img> tag.  "
        "If IMAGE_MODE=disabled, image_b64 is null and the frontend uses the SVG sketch."
    ),
)
async def generate_image(
    body: ImageGenerateRequest,
    user: User = Depends(get_current_user_or_demo),
    db: AsyncSession | None = Depends(get_db_optional),
    audit: AuditRecorder = Depends(get_audit_recorder_safe),
) -> ImageGenerateResponse:
    """
    Full generation pipeline: traits → Gemini prompt → FLUX → PNG.
    """
    try:
        image_b64, prompt_used = await image_service.generate_sketch_image(
            traits=body.traits,
            description=body.description,
            case_id=str(body.case_id) if body.case_id else None,
        )

        # Determine which model was used for the response label
        if _MODE == ImageMode.DISABLED:
            model_label = "disabled"
        elif _MODE == ImageMode.HF_API:
            model_label = settings.HF_GENERATE_MODEL.split("/")[-1]
        else:
            model_label = f"local:{settings.HF_GENERATE_MODEL.split('/')[-1]}"

        # Fine-grained audit
        action = (
            f"Generated AI Sketch Image via {model_label}"
            if image_b64
            else "Generated AI Sketch Image (image generation disabled — SVG fallback)"
        )
        try:
            await audit.record(action=action, case_id=body.case_id)
        except Exception:
            pass

        if not image_b64:
            data_uri = image_service.get_fallback_sketch_data_uri()
        elif str(image_b64).startswith("data:image"):
            data_uri = str(image_b64)
        else:
            data_uri = f"data:image/png;base64,{image_b64}"

        return ImageGenerateResponse(
            image_b64=data_uri,
            sketch_url=data_uri,
            sketch_data=image_service.FALLBACK_SVG_STRING,
            url=data_uri,
            data=data_uri,
            prompt_used=prompt_used or "Forensic sketch template",
            model_used=model_label,
            case_id=body.case_id,
            image_mode=settings.IMAGE_MODE,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Image generation failed: {exc}",
        )


# ---------------------------------------------------------------------------
# POST /image/refine
# ---------------------------------------------------------------------------
@router.post(
    "/refine",
    response_model=ImageRefineResponse,
    summary="Apply or remove a disguise via AI inpainting",
    description=(
        "Accepts the current sketch image (base64 PNG), the active SketchTraits, "
        "and the disguise to toggle.  "
        "The pipeline: (1) generates a facial-region mask for the disguise, "
        "(2) asks Gemini to write precise SD inpainting prompts, "
        "(3) runs SD2-inpainting via HF API on the masked region only — "
        "preserving all unmasked areas (core facial identity).  "
        "Every call writes a precise audit log entry."
    ),
)
async def refine_image(
    body: ImageRefineRequest,
    user: User = Depends(get_current_user_or_demo),
    db: AsyncSession | None = Depends(get_db_optional),
    audit: AuditRecorder = Depends(get_audit_recorder_safe),
) -> ImageRefineResponse:
    """
    Inpainting pipeline: image + mask + Gemini prompts → refined image.
    """
    try:
        refined_b64, pos_prompt, neg_prompt = await image_service.refine_sketch_image(
            image_b64=body.image_b64,
            traits=body.current_traits,
            disguise_name=body.disguise_name,
            active=body.active,
            case_id=str(body.case_id),
        )

        direction = "Applied" if body.active else "Removed"
        action = f"{direction} Disguise via AI inpainting: {body.disguise_name}"
        try:
            await audit.record(action=action, case_id=body.case_id)
        except Exception:
            pass

        if not refined_b64:
            data_uri = image_service.get_fallback_sketch_data_uri()
        elif str(refined_b64).startswith("data:image"):
            data_uri = str(refined_b64)
        else:
            data_uri = f"data:image/png;base64,{refined_b64}"

        return ImageRefineResponse(
            image_b64=data_uri,
            sketch_url=data_uri,
            sketch_data=image_service.FALLBACK_SVG_STRING,
            url=data_uri,
            data=data_uri,
            prompt_used=pos_prompt,
            negative_prompt_used=neg_prompt,
            disguise_name=body.disguise_name,
            case_id=body.case_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Image inpainting failed: {exc}",
        )
