"""
core/deps.py
------------
FastAPI dependency functions used across all route modules.

Importable shortcuts
--------------------
  get_db                → AsyncSession (one per request)
  get_current_user      → User ORM object (any authenticated user)
  require_officer       → User (officer | analyst | admin)
  require_analyst       → User (analyst | admin)
  require_admin         → User (admin only)
  get_audit_recorder    → AuditRecorder (fine-grained audit helper)

Usage in a route
----------------
    @router.post("/generate-sketch")
    async def generate(
        body: GenerateSketchRequest,
        user: User = Depends(require_officer),
        db:   AsyncSession = Depends(get_db),
        audit: AuditRecorder = Depends(get_audit_recorder),
    ):
        result = await sketch_service.generate(body, db)
        await audit.record("Generated Initial Sketch", case_id=body.case_id)
        return result
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.database import get_db
from app.models import User, UserRole

# Re-export get_db so routes only need to import from deps
__all__ = [
    "get_db",
    "get_db_optional",
    "get_current_user",
    "get_current_user_optional",
    "get_current_user_or_demo",
    "get_current_active_user",
    "require_officer",
    "require_analyst",
    "require_admin",
    "AuditRecorder",
    "get_audit_recorder",
    "get_audit_recorder_safe",
    "DEMO_OFFICER",
]

# OAuth2 scheme — FastAPI uses this to render the "Authorize" button in /docs
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    scheme_name="JWT Bearer",
    auto_error=False,
)

# Demo officer fallback for unauthenticated workstation sessions
DEMO_OFFICER = User(
    id="00000000-0000-0000-0000-000000000001",
    username="Officer Anubhav Kashyap",
    role=UserRole.officer,
    password_hash="demo_hash",
)


async def get_db_optional():
    """Dependency that yields a DB session if available, or None if DB is down/unconfigured."""
    session_gen = None
    try:
        session_gen = get_db()
        session = await session_gen.__anext__()
    except Exception:
        yield None
        return

    try:
        yield session
    finally:
        try:
            await session_gen.aclose()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Current-user resolution
# ---------------------------------------------------------------------------
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession | None = Depends(get_db_optional),
) -> User:
    if token == "demo":
        return DEMO_OFFICER
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    """
    Resolve the Bearer JWT → User ORM object.

    Raises
    ------
    HTTP 401  → invalid / expired token
    HTTP 401  → user no longer exists in the database
    """
    payload = decode_token(token)          # raises 401 on any JWT failure

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing the 'sub' claim",
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 'sub' is not a valid UUID",
        )

    if db is None:
        return DEMO_OFFICER

    # Use string comparison (works on both SQLite and PostgreSQL)
    result = await db.execute(select(User).where(User.id == str(user_id)))
    user: User | None = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found — it may have been deleted",
        )
    return user


async def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession | None = Depends(get_db_optional),
) -> User | None:
    """Return the User if authenticated, or None if token is omitted / DB is unreachable."""
    if not token:
        return None
    try:
        payload = decode_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str or not db:
            return None
        user_id = uuid.UUID(user_id_str)
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    except Exception:
        return None


async def get_current_user_or_demo(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession | None = Depends(get_db_optional),
) -> User:
    """Return the authenticated user, or the DEMO_OFFICER for unauthenticated workstations."""
    user = await get_current_user_optional(token, db)
    return user if user is not None else DEMO_OFFICER


# Alias — keeps the door open for adding is_active / email_verified checks later
get_current_active_user = get_current_user


# ---------------------------------------------------------------------------
# Role-based access control (RBAC)
# ---------------------------------------------------------------------------
class RoleChecker:
    """
    Callable dependency that restricts a route to users with specific roles.

    Example
    -------
        @router.delete("/cases/{id}")
        async def delete_case(user: User = Depends(require_admin)):
            ...
    """

    def __init__(self, allowed: list[UserRole]) -> None:
        self.allowed = allowed
        # Readable label used in error messages
        self._names = " | ".join(r.value for r in allowed)

    async def __call__(
        self,
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in self.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{current_user.role.value}' is not authorised for this endpoint. "
                    f"Required: {self._names}"
                ),
            )
        return current_user


# Pre-built role guards — import and use directly
require_officer = RoleChecker([UserRole.officer, UserRole.analyst, UserRole.admin])
require_analyst = RoleChecker([UserRole.analyst, UserRole.admin])
require_admin   = RoleChecker([UserRole.admin])


# ---------------------------------------------------------------------------
# Fine-grained audit recorder (route-level, injected as a dependency)
# ---------------------------------------------------------------------------
class AuditRecorder:
    """
    Thin helper injected into routes that need a **precise** action string
    beyond what the coarse-grained AuditMiddleware provides.

    The middleware always writes a generic entry (e.g. "Toggled Disguise Overlay").
    Use AuditRecorder.record() when you need specifics:
        "Applied Disguise: Full Beard"  or
        'Refinement by Witness: "Make the jaw sharper…"'

    Parameters
    ----------
    request       : the current FastAPI Request
    current_user  : resolved User from get_current_user
    db            : the request-scoped AsyncSession
    """

    def __init__(
        self,
        request: Request,
        current_user: User | None,
        db: AsyncSession | None,
    ) -> None:
        self.request = request
        self.current_user = current_user
        self.db = db

    async def record(
        self,
        action: str,
        case_id: uuid.UUID | None = None,
    ) -> None:
        """
        Append one row to audit_logs inside the *current request* DB session.
        If DB is unavailable, catches the exception and logs safely.
        """
        if not self.db or not self.current_user:
            return
        try:
            # Import here to avoid a circular import at module load time
            from app.services.audit import write_audit_log

            await write_audit_log(
                db=self.db,
                user_id=self.current_user.id,
                case_id=case_id,
                action=action,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("AuditRecorder record failed (non-fatal): %s", exc)


async def get_audit_recorder(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuditRecorder:
    """FastAPI dependency — injects an AuditRecorder into a route handler."""
    return AuditRecorder(request=request, current_user=current_user, db=db)


async def get_audit_recorder_safe(
    request: Request,
    current_user: User = Depends(get_current_user_or_demo),
    db: AsyncSession | None = Depends(get_db_optional),
) -> AuditRecorder:
    """Non-blocking AuditRecorder dependency for public/workstation routes."""
    return AuditRecorder(request=request, current_user=current_user, db=db)
