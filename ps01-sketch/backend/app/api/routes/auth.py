"""
api/routes/auth.py
------------------
Authentication endpoints.

  POST /auth/register   Create a new officer/analyst/admin account
  POST /auth/login      Exchange credentials for a JWT (OAuth2 form OR JSON)
  GET  /auth/me         Return the current authenticated user's profile
  POST /auth/logout     Client-side token discard (server-stateless; audit only)

Security notes
--------------
- Passwords are bcrypt-hashed (passlib) before storage; the plain text is
  never persisted or logged.
- The JWT contains {sub: user_id, username, role} — no password data.
- /auth/login accepts both application/json and application/x-www-form-urlencoded
  (OAuth2PasswordRequestForm) so the FastAPI /docs 'Authorize' button works.
- /auth/register is intentionally open (no prior token needed). In production
  add an admin-invite flow or rate-limit this endpoint at the gateway level.

Local-DB note
-------------
Works with the local SQLite database (nexus.db) that is auto-created on startup.
No Supabase connection required for development.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_active_user, get_current_user_or_demo, get_db_optional
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User, UserRole
from app.schemas import LoginRequest, TokenResponse, UserCreate, UserPublic, UserRead

router = APIRouter(tags=["Auth"])


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------
@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    body: UserCreate,
    db: AsyncSession | None = Depends(get_db_optional),
) -> UserPublic:
    """
    Create a new user account.

    - Username must be unique (3–80 chars, alphanumeric / _ / -).
    - Password is bcrypt-hashed before storage.
    - Default role is 'officer'; pass role='admin' to elevate (lock this down in prod).
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable — cannot register users right now.",
        )

    # Uniqueness check
    existing = await db.execute(select(User).where(User.username == body.username.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{body.username}' is already taken.",
        )

    user = User(
        username=body.username.lower(),
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    await db.flush()   # assigns user.id without committing yet
    return UserPublic.model_validate(user)


# ---------------------------------------------------------------------------
# POST /auth/login  (JSON body)
# ---------------------------------------------------------------------------
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive a JWT access token (JSON body)",
)
async def login_json(
    body: LoginRequest,
    db: AsyncSession | None = Depends(get_db_optional),
) -> TokenResponse:
    """
    Accepts `{"username": "...", "password": "..."}` and returns a Bearer JWT.
    Use this from the React frontend (fetch / axios).
    """
    return await _authenticate(body.username, body.password, db)


# ---------------------------------------------------------------------------
# POST /auth/login/form  (OAuth2 form — used by /docs Authorize button)
# ---------------------------------------------------------------------------
@router.post(
    "/login/form",
    response_model=TokenResponse,
    summary="Login via OAuth2 form (used by Swagger /docs)",
    include_in_schema=True,
)
async def login_form(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession | None = Depends(get_db_optional),
) -> TokenResponse:
    """
    Accepts standard OAuth2 form data.  The FastAPI /docs 'Authorize' button
    posts to this endpoint so you can test protected routes interactively.
    """
    return await _authenticate(form.username, form.password, db)


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------
@router.get(
    "/me",
    response_model=UserRead,
    summary="Return the currently authenticated user",
)
async def me(
    current_user: User = Depends(get_current_user_or_demo),
) -> UserRead:
    """Decode the Bearer token and return the user's profile."""
    return UserRead.model_validate(current_user)


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------
@router.post(
    "/logout",
    summary="Logout (client-side token discard)",
    description=(
        "The server is stateless (no token blacklist). "
        "Instruct the client to delete the stored JWT. "
        "This endpoint exists solely for audit logging."
    ),
)
async def logout(
    current_user: User = Depends(get_current_user_or_demo),
) -> dict[str, str]:
    # AuditMiddleware logs 'User Logout' via the route map in middleware.py
    return {"message": f"Goodbye, {current_user.username}. Discard your token client-side."}


# ---------------------------------------------------------------------------
# Private helper
# ---------------------------------------------------------------------------
async def _authenticate(username: str, password: str, db: AsyncSession | None) -> TokenResponse:
    """Shared credential verification used by both login endpoints."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable — cannot authenticate right now.",
        )

    result = await db.execute(select(User).where(User.username == username.lower()))
    user: User | None = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expire_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role.value},
        expires_delta=expire_delta,
    )
    return TokenResponse(
        access_token=token,
        expires_in=int(expire_delta.total_seconds()),
    )
