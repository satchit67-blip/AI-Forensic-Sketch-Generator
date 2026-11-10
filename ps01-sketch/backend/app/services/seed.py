"""
services/seed.py
----------------
Seeds the local database with a default admin account on first startup.

Default credentials (change immediately after first login):
  Username : admin
  Password : nexus2026
  Role     : admin

Also seeds a default officer account:
  Username : officer
  Password : nexus2026
  Role     : officer

And the demo case #HACK26-451 is seeded automatically.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import Case, User, UserRole

logger = logging.getLogger("nexus")

# ---------------------------------------------------------------------------
# Seed accounts
# ---------------------------------------------------------------------------
_SEED_USERS = [
    {
        "id": "00000000-0000-0000-0000-000000000002",
        "username": "admin",
        "password": "nexus2026",
        "role": UserRole.admin,
    },
    {
        "id": "00000000-0000-0000-0000-000000000003",
        "username": "officer",
        "password": "nexus2026",
        "role": UserRole.officer,
    },
]

_SEED_CASE = {
    "id": "00000000-0000-0000-0000-000000000010",
    "case_number": "#HACK26-451",
    "title": "Forensic Investigation – Hackfest 2026",
    "description": "Active suspect composite synthesis for case #HACK26-451.",
    "created_by": "00000000-0000-0000-0000-000000000002",
}


async def seed_defaults(db: AsyncSession) -> None:
    """
    Insert default accounts and the demo case if they don't already exist.
    Safe to call multiple times — idempotent.
    """
    changed = False

    # ── Seed users ────────────────────────────────────────────────────────
    for spec in _SEED_USERS:
        existing = await db.execute(
            select(User).where(User.username == spec["username"])
        )
        if existing.scalar_one_or_none() is None:
            user = User(
                id=spec["id"],
                username=spec["username"],
                password_hash=hash_password(spec["password"]),
                role=spec["role"],
            )
            db.add(user)
            changed = True
            logger.info("Seeded account: %s (%s)", spec["username"], spec["role"].value)

    # ── Seed demo case ────────────────────────────────────────────────────
    existing_case = await db.execute(
        select(Case).where(Case.case_number == _SEED_CASE["case_number"])
    )
    if existing_case.scalar_one_or_none() is None:
        case = Case(
            id=_SEED_CASE["id"],
            case_number=_SEED_CASE["case_number"],
            title=_SEED_CASE["title"],
            description=_SEED_CASE["description"],
            created_by=_SEED_CASE["created_by"],
        )
        db.add(case)
        changed = True
        logger.info("Seeded case: %s", _SEED_CASE["case_number"])

    if changed:
        await db.commit()
        logger.info(
            "DB seeding complete. Default credentials → username: admin | password: nexus2026"
        )
