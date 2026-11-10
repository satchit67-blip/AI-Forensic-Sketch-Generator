"""
database.py
-----------
SQLAlchemy async engine + session factory.

Priority order for DATABASE_URL:
  1.  If DATABASE_URL in .env starts with postgresql+asyncpg:// → use Supabase/Postgres
  2.  Otherwise → fall back to a local SQLite file  (nexus.db in the backend folder)

This lets the app work offline out of the box while still connecting to
Supabase when a real DATABASE_URL is supplied.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger("nexus")

# ---------------------------------------------------------------------------
# Decide which DB to use
# ---------------------------------------------------------------------------
_raw_url: str = settings.DATABASE_URL

# If the configured URL is a real Postgres connection, use it.
# If it's still the placeholder value, fall back to SQLite.
_use_sqlite = (
    "REPLACE_ME" in _raw_url
    or _raw_url.strip() == ""
    or _raw_url.startswith("sqlite")
)

if _use_sqlite:
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _SQLITE_PATH = os.path.join(_BASE_DIR, "nexus.db")
    DATABASE_URL_EFFECTIVE = f"sqlite+aiosqlite:///{_SQLITE_PATH}"
    logger.info("DB mode: SQLite  (%s)", _SQLITE_PATH)
else:
    DATABASE_URL_EFFECTIVE = _raw_url
    logger.info("DB mode: PostgreSQL / Supabase")

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
_connect_args = {}
if DATABASE_URL_EFFECTIVE.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_async_engine(
    DATABASE_URL_EFFECTIVE,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
    connect_args=_connect_args,
    # SQLite doesn't support pool_size / max_overflow
    **({} if _use_sqlite else {"pool_size": 10, "max_overflow": 20}),
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Declarative base – all models inherit from this
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
async def get_db():
    """
    Yield an AsyncSession per request and close it when the request is done.
    Use as a FastAPI Depends() parameter.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
