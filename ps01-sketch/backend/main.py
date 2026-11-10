"""
main.py
-------
AI NEXUS – Forensic Sketch Synthesizer · FastAPI application entry-point.

┌─────────────────────────────────────────────────────────────────────┐
│  QUICK START                                                        │
│                                                                     │
│  1. cp .env.example .env  and fill in every value                  │
│  2. pip install -r requirements.txt                                 │
│  3. uvicorn main:app --reload --port 8000                           │
│  4. Open http://localhost:8000/docs  for the interactive API UI     │
└─────────────────────────────────────────────────────────────────────┘

Middleware execution order (outermost → innermost)
───────────────────────────────────────────────────
  CORSMiddleware   ← always first; handles pre-flight OPTIONS
  AuditMiddleware  ← intercepts every request, writes chain-of-custody log

Router prefix map
─────────────────
  /auth/*          → api/routes/auth.py     (register, login, me, logout)
  /cases/*         → api/routes/cases.py    (CRUD)
  /audit-logs/*    → api/routes/audit.py    (read-only log queries)
  /generate-sketch → api/routes/sketch.py   (Gemini text → traits)
  /refine-sketch   → api/routes/sketch.py   (iterative text refinement)
  /apply-disguise  → api/routes/sketch.py   (trait-level toggle)
  /export          → api/routes/sketch.py   (audit-log the export event)
  /reset           → api/routes/sketch.py   (audit-log canvas reset)
  /image/*         → api/routes/image.py    (FLUX/SD image generation)
  /healthz         → inline probe
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.middleware import AuditMiddleware

# ── Routers ───────────────────────────────────────────────────────────────
from app.api.routes.auth   import router as auth_router
from app.api.routes.cases  import router as cases_router
from app.api.routes.audit  import router as audit_router
from app.api.routes.sketch import router as sketch_router
from app.api.routes.image  import router as image_router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nexus")


# ---------------------------------------------------------------------------
# Lifespan: startup → serve → shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup tasks run before the first request is served.
    Shutdown tasks run after the last request completes.
    """
    # ── Startup ─────────────────────────────────────────────────────────
    logger.info("═══ AI NEXUS backend starting (mode=%s) ═══", settings.IMAGE_MODE)

    # Verify the DB is reachable before accepting traffic
    try:
        from app.database import engine
        async with engine.connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        logger.info("✓ Supabase PostgreSQL connection verified")
    except Exception as exc:
        logger.warning("✗ DB connection check failed: %s (continuing anyway)", exc)

    # Optionally auto-create tables in development
    # (use Alembic migrations in production — see README)
    if settings.DEBUG:
        try:
            from app.database import engine, Base
            import app.models  # noqa: F401 — ensures all models are registered
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("✓ Tables verified / created (DEBUG mode)")
        except Exception as exc:
            logger.warning("Table auto-create skipped: %s", exc)

    # ── Seed default accounts (works for both DEBUG and prod) ────────────
    try:
        from app.database import AsyncSessionLocal
        from app.services.seed import seed_defaults
        async with AsyncSessionLocal() as db:
            await seed_defaults(db)
    except Exception as exc:
        logger.warning("DB seed skipped: %s", exc)
    else:
        # Always create tables (safe — create_all is idempotent)
        try:
            from app.database import engine, Base
            import app.models  # noqa: F401
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("✓ Tables verified / created")
        except Exception as exc:
            logger.warning("Table auto-create skipped: %s", exc)

    # ── Seed default accounts ────────────────────────────────────────────
    try:
        from app.database import AsyncSessionLocal
        from app.services.seed import seed_defaults
        async with AsyncSessionLocal() as db:
            await seed_defaults(db)
    except Exception as exc:
        logger.warning("DB seed skipped: %s", exc)

    yield  # ← server is live here

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("AI NEXUS backend shutting down.")
    from app.database import engine
    await engine.dispose()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "**AI NEXUS — Forensic Sketch Synthesizer** backend.\n\n"
        "Accepts unstructured witness descriptions, parses them with "
        "**Google Gemini** into structured facial traits, renders them via "
        "a procedural SVG pipeline, and optionally generates photo-realistic "
        "sketches using **FLUX.1-schnell** (Hugging Face Inference API).\n\n"
        "Every protected action is automatically written to an immutable "
        "**chain-of-custody audit log** in Supabase PostgreSQL."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    # Disable docs in production — set DEBUG=false in .env
    # docs_url=None if not settings.DEBUG else "/docs",
)


# ---------------------------------------------------------------------------
# Middleware  ← IMPORTANT: add_middleware() in reverse execution order.
#               The LAST middleware added executes FIRST on each request.
# ---------------------------------------------------------------------------

# ① CORS — must be the outermost wrapper so pre-flight OPTIONS requests
#           are handled before any auth or audit logic runs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,   # e.g. ["http://localhost:5173"]
    allow_credentials=True,                     # required for Authorization header
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    expose_headers=["X-Request-ID"],
    max_age=600,                                # cache pre-flight for 10 min
)

# ② Audit — intercepts every request AFTER CORS; writes chain-of-custody log.
#    Uses its own DB session so a rolled-back request session never loses an entry.
app.add_middleware(AuditMiddleware)


# ---------------------------------------------------------------------------
# Request ID + response-time header (development visibility)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_metadata_middleware(request: Request, call_next) -> Response:
    """Attach X-Request-ID and X-Process-Time headers to every response."""
    import uuid as _uuid
    request_id = str(_uuid.uuid4())[:8]
    start = time.perf_counter()

    response: Response = await call_next(request)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Request-ID"]   = request_id
    response.headers["X-Process-Time"] = f"{elapsed_ms}ms"
    return response


# ---------------------------------------------------------------------------
# Global exception handler — converts unhandled errors to clean JSON
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Check server logs."},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
# Auth  →  /auth/register  /auth/login  /auth/login/form  /auth/me  /auth/logout
app.include_router(auth_router,   prefix="/auth")
app.include_router(auth_router,   prefix="/api/auth")

# Cases CRUD  →  /cases  /cases/{id}
app.include_router(cases_router,  prefix="/cases")
app.include_router(cases_router,  prefix="/api/cases")

# Audit log queries  →  /audit-logs/{case_id}  /audit-logs
app.include_router(audit_router,  prefix="/audit-logs")
app.include_router(audit_router,  prefix="/api/audit-logs")

# Gemini text pipeline  →  /generate-sketch  /refine-sketch  /apply-disguise  /export  /reset
app.include_router(sketch_router)
app.include_router(sketch_router, prefix="/api")

# Image generation & inpainting  →  /image/status  /image/generate  /image/refine
app.include_router(image_router)
app.include_router(image_router, prefix="/api")


# ---------------------------------------------------------------------------
# Liveness / readiness probes
# ---------------------------------------------------------------------------
@app.get("/healthz", tags=["Health"], summary="Liveness probe — is the process up?")
async def healthz() -> dict:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "image_mode": settings.IMAGE_MODE,
    }


@app.get("/readyz", tags=["Health"], summary="Readiness probe — can the app serve traffic?")
async def readyz() -> dict:
    """Check that the database connection is alive before routing traffic."""
    try:
        from app.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    http_status = 200 if db_ok else 503
    return JSONResponse(
        status_code=http_status,
        content={"status": "ready" if db_ok else "degraded", "database": db_ok},
    )


# ---------------------------------------------------------------------------
# Custom OpenAPI schema — adds JWT Bearer security scheme to /docs
# ---------------------------------------------------------------------------
def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Inject Bearer token security scheme
    schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "Obtain a token via **POST /auth/login**, then paste it here. "
            "Format: `Bearer <token>`"
        ),
    }
    # Apply globally to all operations
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation.setdefault("security", [{"BearerAuth": []}])

    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi  # type: ignore[method-assign]
