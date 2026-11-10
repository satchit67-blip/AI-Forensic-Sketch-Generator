"""
models.py
---------
SQLAlchemy ORM models for:
  - users       → authentication & role management
  - cases       → forensic case records
  - audit_logs  → immutable chain-of-custody log

Compatible with BOTH SQLite (local dev) and PostgreSQL (Supabase/prod).
UUIDs are stored as plain String(36) so they work on any backend.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class UserRole(str, enum.Enum):
    officer = "officer"
    analyst = "analyst"
    admin   = "admin"


# ---------------------------------------------------------------------------
# Helper: generate a UUID string (works on any DB)
# ---------------------------------------------------------------------------
def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class User(Base):
    """
    Stores system users (officers, analysts, admins).
    Passwords are stored as bcrypt hashes — never plain text.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    username: Mapped[str] = mapped_column(
        String(80), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"),
        nullable=False,
        default=UserRole.officer,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    cases: Mapped[list["Case"]] = relationship(
        "Case", back_populates="creator", lazy="select"
    )
    audit_entries: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="user", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role}>"


# ---------------------------------------------------------------------------
# Case
# ---------------------------------------------------------------------------
class Case(Base):
    """
    Represents a single forensic investigation case.
    Each case is owned by one officer (created_by → users.id).
    """

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    case_number: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Foreign key → users
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    creator: Mapped["User"] = relationship(
        "User", back_populates="cases", lazy="select"
    )
    audit_entries: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="case", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Case id={self.id} case_number={self.case_number!r}>"


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------
class AuditLog(Base):
    """
    Immutable append-only chain-of-custody log.
    Written by the audit middleware on every protected action.
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )

    # Foreign key → users (nullable so system-level events can be logged)
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Foreign key → cases (nullable for auth-level events)
    case_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    action: Mapped[str] = mapped_column(String(500), nullable=False)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    user: Mapped["User"] = relationship(
        "User", back_populates="audit_entries", lazy="select"
    )
    case: Mapped["Case"] = relationship(
        "Case", back_populates="audit_entries", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} user_id={self.user_id} "
            f"case_id={self.case_id} action={self.action!r}>"
        )
