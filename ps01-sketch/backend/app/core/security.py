"""
core/security.py
----------------
All cryptographic primitives in one place.

Public API
----------
  hash_password(plain)            → bcrypt hash string
  verify_password(plain, hashed)  → bool
  create_access_token(data, ...)  → signed JWT string
  decode_token(token)             → payload dict  [raises HTTP 401 on failure]
  decode_token_silent(token)      → payload dict | None  [middleware-safe, no raise]
  get_token_from_header(header)   → raw token str | None
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, ExpiredSignatureError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ---------------------------------------------------------------------------
# Password hashing  (bcrypt, cost-factor 12 by default)
# ---------------------------------------------------------------------------
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return a one-way bcrypt hash of *plain*.  Store this, never the original."""
    # bcrypt truncates at 72 bytes — trim silently to avoid passlib errors
    return _pwd_ctx.hash(plain[:72])


def verify_password(plain: str, hashed: str) -> bool:
    """
    Constant-time comparison of *plain* against the stored *hashed* value.
    Returns True only when they match.
    """
    return _pwd_ctx.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """
    Encode *data* as a signed HS256 JWT.

    Always injects:
        sub  → data["sub"]   (the user UUID as a string)
        iat  → issued-at timestamp (UTC)
        exp  → expiry timestamp (UTC)

    Example
    -------
        token = create_access_token({"sub": str(user.id), "role": user.role})
    """
    payload = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload.update({"iat": now, "exp": expire})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and cryptographically verify a JWT.

    Raises
    ------
    HTTP 401  — invalid signature, expired token, missing 'sub' claim, etc.

    Use this in FastAPI route *dependencies* where a hard failure is correct.
    """
    _creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    _expired_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token has expired — please log in again",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        if payload.get("sub") is None:
            raise _creds_exc
        return payload
    except ExpiredSignatureError:
        raise _expired_exc
    except JWTError:
        raise _creds_exc


def decode_token_silent(token: str) -> dict[str, Any] | None:
    """
    Decode a JWT without raising exceptions.

    Returns the payload dict on success, or None on any failure
    (bad signature, expired, malformed, missing sub).

    Use this in *middleware* which must never block a request due to
    an auth failure — the route handler enforces auth separately.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload if payload.get("sub") else None
    except JWTError:
        return None


def get_token_from_header(authorization: str | None) -> str | None:
    """
    Parse an "Authorization: Bearer <token>" header.

    Returns the raw token string, or None if the header is absent or
    does not follow the Bearer scheme.
    """
    if not authorization:
        return None
    parts = authorization.split(maxsplit=1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None
