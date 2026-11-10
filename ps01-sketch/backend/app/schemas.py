"""
schemas.py
----------
Pydantic v2 schemas for request validation and response serialisation.

Organisation:
  - Auth      → TokenResponse, LoginRequest
  - User      → UserCreate, UserRead, UserPublic
  - Case      → CaseCreate, CaseUpdate, CaseRead
  - AuditLog  → AuditLogCreate, AuditLogRead
  - Sketch    → GenerateSketchRequest, SketchTraits, GenerateSketchResponse
               → RefineSketchRequest,  RefineSketchResponse
               → ApplyDisguiseRequest, ApplyDisguiseResponse
  - Image     → ImageGenerateRequest, ImageGenerateResponse
               → ImageRefineRequest,   ImageRefineResponse
               → ImageStatusResponse
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import UserRole


# ===========================================================================
# Shared / primitives
# ===========================================================================
# Accept both UUID objects and plain strings (SQLite stores UUIDs as strings)
UUIDStr = Annotated[str, Field(description="UUID v4 identifier")]


# ===========================================================================
# Auth Schemas
# ===========================================================================
class LoginRequest(BaseModel):
    """Credentials sent to POST /auth/login."""

    username: str = Field(..., min_length=3, max_length=80, examples=["officer_singh"])
    password: str = Field(..., min_length=6, examples=["securePass123"])


class TokenResponse(BaseModel):
    """JWT access token returned after successful login."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(..., description="Token lifetime in seconds")


# ===========================================================================
# User Schemas
# ===========================================================================
class UserCreate(BaseModel):
    """Request body for POST /auth/register."""

    username: str = Field(..., min_length=3, max_length=80)
    password: str = Field(..., min_length=6, max_length=128)
    role: UserRole = UserRole.officer

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not all(c.isalnum() or c in ("_", "-") for c in v):
            raise ValueError("Username may only contain letters, digits, _ or -")
        return v.lower()


class UserRead(BaseModel):
    """Full user record – returned to admins only."""

    id: UUIDStr
    username: str
    role: UserRole
    created_at: datetime

    model_config = {"from_attributes": True}


class UserPublic(BaseModel):
    """Minimal user info embedded in other responses."""

    id: UUIDStr
    username: str
    role: UserRole

    model_config = {"from_attributes": True}


# ===========================================================================
# Case Schemas
# ===========================================================================
class CaseCreate(BaseModel):
    """Request body for POST /cases."""

    case_number: str = Field(
        ...,
        min_length=3,
        max_length=40,
        examples=["#HACK26-451"],
        description="Unique alphanumeric case reference",
    )
    title: str = Field(..., min_length=3, max_length=200, examples=["Suspect composite – Downtown robbery"])
    description: str | None = Field(
        None,
        max_length=5000,
        examples=["Witness described a tall male with a sharp jaw…"],
    )


class CaseUpdate(BaseModel):
    """Request body for PATCH /cases/{case_id}. All fields are optional."""

    title: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = Field(None, max_length=5000)


class CaseRead(BaseModel):
    """Full case record returned by the API."""

    id: UUIDStr
    case_number: str
    title: str
    description: str | None
    created_by: UUIDStr | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ===========================================================================
# Audit Log Schemas
# ===========================================================================
class AuditLogCreate(BaseModel):
    """
    Internal schema used by the audit middleware to write a log entry.
    Not exposed directly to frontend clients.
    """

    user_id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None
    action: str = Field(..., max_length=500)


class AuditLogRead(BaseModel):
    """
    Single audit entry – matches the columns rendered by AuditLog.jsx:
      ts (timestamp) · user · caseId · action
    """

    id: UUIDStr
    user_id: UUIDStr | None
    case_id: UUIDStr | None
    action: str
    timestamp: datetime
    # Denormalised fields for the frontend table
    username: str | None = Field(None, description="Resolved from user_id")
    case_number: str | None = Field(None, description="Resolved from case_id")

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    """Paginated list of audit entries."""

    total: int
    entries: list[AuditLogRead]


# ===========================================================================
# Sketch / AI Pipeline Schemas
# ===========================================================================

# ── Shared trait model (mirrors face.js defaultTraits) ────────────────────
VALID_JAW = Literal["soft", "sharp"]
VALID_HAIR = Literal["short", "long", "bald"]
VALID_DISGUISES = Literal[
    "Full Beard",
    "Mustache",
    "Wire-Rimmed Glasses",
    "Sunglasses",
    "Long Hair",
    "Bald",
    "Scar/Mark",
]


class SketchTraits(BaseModel):
    """
    Structured facial parameters parsed by Gemini and consumed by the
    SVG renderer (FaceSketch.jsx).  Mirrors face.js `defaultTraits`.
    """

    jaw: VALID_JAW = Field("soft", description="Jaw shape extracted from description")
    hair: VALID_HAIR = Field("short", description="Hair length")
    hair_color: str = Field(
        "#2b2b2f",
        pattern=r"^#[0-9a-fA-F]{6}$",
        description="CSS hex colour for hair / beard",
        examples=["#8a8a90", "#b9a06a", "#1c1c20"],
    )
    face: float = Field(
        1.0,
        ge=0.85,
        le=1.20,
        description="Horizontal face-width scale factor (0.9 = narrow, 1.12 = wide)",
    )
    disguises: list[VALID_DISGUISES] = Field(
        default_factory=list,
        description="Active disguise / modification overlays",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Human-readable summary of trait changes made",
    )


# ── Generate Initial Sketch ───────────────────────────────────────────────
class GenerateSketchRequest(BaseModel):
    """POST /generate-sketch"""

    description: str = Field(
        ...,
        min_length=2,
        max_length=3000,
        examples=["Man in his 40s, sharp jaw, short grey hair, thin face"],
    )
    case_id: uuid.UUID | None = Field(None, description="Case this sketch belongs to (optional)")
    disguises: list[str] = Field(default_factory=list, description="Active disguise modifications")
    traits: SketchTraits | None = Field(None, description="Current traits if already available")


class GenerateSketchResponse(BaseModel):
    """Structured traits returned to the frontend after Gemini parsing."""

    traits: SketchTraits
    raw_gemini_output: str = Field(
        "", description="Raw JSON string from Gemini (for debugging)"
    )
    case_id: uuid.UUID | None = None
    image_b64: str | None = Field(None, description="Data URI or base64 PNG")
    sketch_url: str | None = Field(None, description="Data URL or direct URL to sketch image")
    url: str | None = Field(None, description="Direct URL alias for sketch")
    sketch_data: str | None = Field(None, description="Vector SVG or base64 sketch data")
    data: str | None = Field(None, description="Direct data payload alias")


# ── Iterative Refinement ──────────────────────────────────────────────────
class RefineSketchRequest(BaseModel):
    """POST /refine-sketch"""

    feedback: str = Field(
        ...,
        min_length=2,
        max_length=1000,
        examples=["Make the jaw sharper and add a beard"],
    )
    role: str = Field(
        "Witness", description="Who is providing the feedback ('Witness' or 'Officer')"
    )
    current_traits: SketchTraits = Field(
        ..., description="Current trait state from the frontend"
    )
    case_id: uuid.UUID | None = None
    description: str | None = Field(None, description="Optional cumulative witness statement")

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v: str) -> str:
        if isinstance(v, str):
            v_lower = v.strip().lower()
            if v_lower == "officer":
                return "Officer"
            return "Witness"
        return "Witness"


class RefineSketchResponse(BaseModel):
    """Updated traits after applying the feedback delta."""

    traits: SketchTraits
    summary: str = Field(..., description="What changed, e.g. 'jaw sharpened, beard added'")
    case_id: uuid.UUID | None = None
    image_b64: str | None = Field(None, description="Updated base64 data URI image")
    sketch_url: str | None = Field(None, description="Updated sketch image URL")
    url: str | None = Field(None, description="Direct image URL alias")
    sketch_data: str | None = Field(None, description="Updated vector or raster data")
    data: str | None = Field(None, description="Direct payload alias")


# ── Disguise Toggle ───────────────────────────────────────────────────────
class ApplyDisguiseRequest(BaseModel):
    """POST /apply-disguise"""

    name: VALID_DISGUISES
    active: bool = Field(..., description="True = add disguise, False = remove")
    case_id: uuid.UUID | None = None
    current_traits: SketchTraits | None = Field(None, description="Current traits before toggle")
    description: str | None = Field(None, description="Optional cumulative witness statement")

    @model_validator(mode="after")
    def mutual_exclusion(self) -> "ApplyDisguiseRequest":
        """Bald and Long Hair are mutually exclusive (mirrors toggleSet in face.js)."""
        return self


class ApplyDisguiseResponse(BaseModel):
    """Confirmed disguise state after toggle."""

    name: str
    active: bool
    case_id: uuid.UUID | None = None
    message: str
    traits: SketchTraits | None = None
    image_b64: str | None = None
    sketch_url: str | None = None
    url: str | None = None
    sketch_data: str | None = None
    data: str | None = None


# ── Export ────────────────────────────────────────────────────────────────
class ExportAuditRequest(BaseModel):
    """POST /export  – frontend sends this to trigger the audit log entry."""

    case_id: uuid.UUID | None = None


class ExportAuditResponse(BaseModel):
    message: str = "Export event logged"
    case_id: uuid.UUID | None = None


# ===========================================================================
# Image Generation & Inpainting Schemas
# ===========================================================================

class ImageGenerateRequest(BaseModel):
    """
    POST /image/generate
    Accepted after an initial /generate-sketch call so traits are already parsed.
    """

    description: str = Field(
        ...,
        min_length=5,
        max_length=3000,
        description="Original witness description (used for Gemini prompt context)",
    )
    traits: SketchTraits = Field(
        default_factory=SketchTraits,
        description="Structured traits from /generate-sketch (Gemini-parsed)",
    )
    case_id: uuid.UUID | None = None


class ImageGenerateResponse(BaseModel):
    """
    Returned after FLUX/SD generates the initial forensic sketch image.
    """

    image_b64: str | None = Field(
        None,
        description="Base64-encoded PNG or data URI of the generated sketch",
    )
    sketch_url: str | None = Field(None, description="Data URL or URL for image preview")
    url: str | None = Field(None, description="Direct URL alias for sketch")
    sketch_data: str | None = Field(None, description="Vector SVG or base64 sketch data")
    data: str | None = Field(None, description="Direct data payload alias")
    prompt_used: str = Field("", description="Exact prompt sent to FLUX / SD")
    model_used: str  = Field("", description="Model identifier (e.g. 'flux-schnell', 'sd2-inpainting')")
    case_id: uuid.UUID | None = None
    image_mode: str  = Field("", description="Active image mode: hf_api | local | disabled")


class ImageRefineRequest(BaseModel):
    """
    POST /image/refine
    Accepts the current rendered image and the disguise to apply/remove.
    The Gemini + SD inpainting pipeline modifies only the masked facial region.
    """

    image_b64: str = Field(
        ...,
        description="Base64-encoded PNG of the current sketch image (from ImageGenerateResponse)",
    )
    current_traits: SketchTraits = Field(
        ...,
        description="Current trait state — used for inpainting prompt context",
    )
    disguise_name: VALID_DISGUISES = Field(
        ...,
        description="The disguise to apply or remove",
    )
    active: bool = Field(
        ...,
        description="True = add the disguise, False = remove it",
    )
    case_id: uuid.UUID | None = None
    use_gemini_prompt: bool = Field(
        True,
        description="Let Gemini refine the inpainting prompt (recommended)",
    )


class ImageRefineResponse(BaseModel):
    """
    Returned after inpainting modifies the sketch for the selected disguise.
    The refined image preserves all unmasked regions (core facial identity).
    """

    image_b64: str | None = Field(
        None,
        description="Base64-encoded PNG of the refined sketch",
    )
    sketch_url: str | None = Field(None, description="Data URL of refined sketch")
    sketch_data: str | None = Field(None, description="Vector SVG or base64 sketch data")
    url: str | None = Field(None, description="Direct URL alias for sketch")
    data: str | None = Field(None, description="Data URI alias for sketch")
    prompt_used: str = Field("", description="Positive inpainting prompt used")
    negative_prompt_used: str = Field("", description="Negative inpainting prompt used")
    disguise_name: str = ""
    case_id: uuid.UUID | None = None
    audit_action: str = Field("", description="Exact string written to audit_logs")


class ImageStatusResponse(BaseModel):
    """GET /image/status — reports the active image generation mode."""

    image_mode: str
    generate_model: str
    inpaint_model: str
    hf_token_set: bool
    available_disguises: list[str]

