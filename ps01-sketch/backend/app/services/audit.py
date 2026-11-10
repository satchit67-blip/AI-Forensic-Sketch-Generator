"""
services/audit.py
-----------------
Business-logic layer for audit_logs.

Functions
---------
  write_audit_log(db, user_id, case_id, action)
      → Append one row (called by AuditRecorder from route handlers)

  get_audit_logs_for_case(db, case_id, limit, offset)
      → (total, [AuditLogRead])  newest-first, for GET /audit-logs/{case_id}

  get_all_audit_logs(db, limit, offset)
      → (total, [AuditLogRead])  admin-only view across all cases
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import AuditLog
from app.schemas import AuditLogRead


async def write_audit_log(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    case_id: uuid.UUID | None,
    action: str,
) -> AuditLog:
    """
    Append one AuditLog entry inside the *caller's* DB session.

    Called from
    -----------
    - AuditRecorder.record()   (fine-grained, from route handlers)
    - AuditMiddleware._write() uses its own session independently

    The entry is flushed (gets a DB-assigned id) but NOT committed;
    the caller's session commit finalises it.
    """
    entry = AuditLog(
        user_id=user_id,
        case_id=case_id,
        action=action,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()   # assigns id without committing yet
    return entry


async def get_audit_logs_for_case(
    db: AsyncSession,
    case_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[AuditLogRead]]:
    """
    Return paginated audit entries for one case, newest-first.
    Denormalises username and case_number for the AuditLog.jsx table.

    Parameters
    ----------
    db        : request-scoped AsyncSession
    case_id   : UUID of the Case to filter by
    limit     : page size  (default 100, max enforced by the route)
    offset    : pagination offset

    Returns
    -------
    (total_count, list_of_AuditLogRead)
    """
    base_stmt = (
        select(AuditLog)
        .where(AuditLog.case_id == case_id)
        .options(
            selectinload(AuditLog.user),
            selectinload(AuditLog.case),
        )
    )

    # Total count
    count_result = await db.execute(
        select(func.count()).select_from(base_stmt.subquery())
    )
    total: int = count_result.scalar_one()

    # Paginated rows
    rows_result = await db.execute(
        base_stmt.order_by(desc(AuditLog.timestamp)).limit(limit).offset(offset)
    )
    rows = rows_result.scalars().all()

    return total, _to_reads(rows)


async def get_all_audit_logs(
    db: AsyncSession,
    limit: int = 200,
    offset: int = 0,
) -> tuple[int, list[AuditLogRead]]:
    """
    Admin-only: paginated view of ALL audit entries across every case.

    Returns
    -------
    (total_count, list_of_AuditLogRead)
    """
    base_stmt = select(AuditLog).options(
        selectinload(AuditLog.user),
        selectinload(AuditLog.case),
    )

    count_result = await db.execute(
        select(func.count()).select_from(base_stmt.subquery())
    )
    total: int = count_result.scalar_one()

    rows_result = await db.execute(
        base_stmt.order_by(desc(AuditLog.timestamp)).limit(limit).offset(offset)
    )
    rows = rows_result.scalars().all()

    return total, _to_reads(rows)


# ---------------------------------------------------------------------------
# Private helper
# ---------------------------------------------------------------------------
def _to_reads(rows: list[AuditLog]) -> list[AuditLogRead]:
    """Convert ORM rows → Pydantic AuditLogRead (with denormalised fields)."""
    return [
        AuditLogRead(
            id=row.id,
            user_id=row.user_id,
            case_id=row.case_id,
            action=row.action,
            timestamp=row.timestamp,
            # Denormalise for frontend table columns
            username=(row.user.username if row.user else None),
            case_number=(row.case.case_number if row.case else None),
        )
        for row in rows
    ]
