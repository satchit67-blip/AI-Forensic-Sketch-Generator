"""
api/routes/audit.py
-------------------
Read-only endpoints for querying the chain-of-custody audit log.

  GET /audit-logs/{case_id}   Paginated log for one case (officer+)
  GET /audit-logs             All logs across every case (admin only)

Design notes
------------
- Audit entries are APPEND-ONLY.  There is no POST, PATCH, or DELETE here.
- Every GET request is itself audited by the AuditMiddleware (route map entry).
- Responses include denormalised username and case_number so the AuditLog.jsx
  frontend table can render without additional lookups.
- The AuditLogListResponse wrapper carries a total count for the frontend to
  show "N entries · chain of custody" (mirrors AuditLog.jsx header).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_db_optional, require_admin, require_officer
from app.models import User
from app.schemas import AuditLogListResponse
from app.services.audit import get_all_audit_logs, get_audit_logs_for_case

router = APIRouter(tags=["Audit Logs"])


# ---------------------------------------------------------------------------
# GET /audit-logs/{case_id}
# ---------------------------------------------------------------------------
@router.get(
    "/{case_id}",
    response_model=AuditLogListResponse,
    summary="Get the chain-of-custody audit log for one case",
    description=(
        "Returns all audit entries for a specific case, newest-first. "
        "Includes denormalised username and case_number for the AuditLog.jsx table. "
        "This request itself is logged by the AuditMiddleware."
    ),
)
async def get_case_audit_log(
    case_id: uuid.UUID,
    limit:  int = Query(100, ge=1,  le=500, description="Max entries to return"),
    offset: int = Query(0,   ge=0,          description="Pagination offset"),
    user: User = Depends(require_officer),
    db: AsyncSession | None = Depends(get_db_optional),
) -> AuditLogListResponse:
    if db is not None:
        try:
            total, entries = await get_audit_logs_for_case(
                db=db, case_id=case_id, limit=limit, offset=offset
            )
            return AuditLogListResponse(total=total, entries=entries)
        except Exception:
            pass
    return AuditLogListResponse(total=0, entries=[])


# ---------------------------------------------------------------------------
# GET /audit-logs   (admin-only full view)
# ---------------------------------------------------------------------------
@router.get(
    "",
    response_model=AuditLogListResponse,
    summary="Get all audit logs across every case (admin only)",
    description=(
        "Admin-level view of the complete audit history across all cases "
        "and all users, newest-first. Paginated."
    ),
)
async def get_all_logs(
    limit:  int = Query(200, ge=1,  le=1000, description="Max entries to return"),
    offset: int = Query(0,   ge=0,           description="Pagination offset"),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    total, entries = await get_all_audit_logs(db=db, limit=limit, offset=offset)
    return AuditLogListResponse(total=total, entries=entries)
