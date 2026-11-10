"""
core/config.py
--------------
Centralised settings loaded from environment variables / .env file.
All other modules import from here — never os.getenv() directly.
"""

from functools import lru_cache

from pydantic import AnyUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────
    APP_NAME: str = "AI NEXUS – Forensic Sketch Synthesizer"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Database ─────────────────────────────────────────────────────────
    # Example: postgresql+asyncpg://postgres:password@db.supabase.co:5432/postgres
    DATABASE_URL: str
    DB_ECHO: bool = False           # set True in dev to log SQL

    # ── JWT ──────────────────────────────────────────────────────────────
    SECRET_KEY: str                 # openssl rand -hex 32
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── Google Gemini ─────────────────────────────────────────────────────
    GEMINI_API_KEY: str

    # ── Image Generation ──────────────────────────────────────────────────
    # Mode: "hf_api" = Hugging Face Inference API (free tier, zero-budget)
    #       "local"  = local diffusers pipeline (requires 6-8 GB VRAM)
    #       "disabled" = no image generation; SVG sketch only
    IMAGE_MODE: str = "hf_api"

    # Hugging Face token (get free at huggingface.co/settings/tokens)
    HF_TOKEN: str = ""

    # Models used (override to swap in alternatives)
    HF_GENERATE_MODEL: str = "black-forest-labs/FLUX.1-schnell"
    HF_INPAINT_MODEL: str = "stabilityai/stable-diffusion-2-inpainting"

    # Image dimensions for generation (keep multiples of 64 for SD)
    IMAGE_WIDTH: int = 512
    IMAGE_HEIGHT: int = 640

    # Folder for saving generated images (relative to project root)
    IMAGE_STORE_PATH: str = "./generated_images"

    # ── CORS ─────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins, e.g. "http://localhost:5173,https://yourdomain.com"
    CORS_ORIGINS: str = "http://localhost:5173"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _ensure_async_driver(cls, v: str) -> str:
        """Auto-upgrade plain postgresql:// to the asyncpg driver."""
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton — safe to call from any module."""
    return Settings()  # type: ignore[call-arg]


# Module-level singleton for convenience
settings = get_settings()
