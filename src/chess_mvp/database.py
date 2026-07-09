from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from chess_mvp.config import settings

_engine = None
_async_session_factory = None


class Base(DeclarativeBase):
    pass


def get_engine():
    """Create or return the global async engine.

    Lazily initialized so tests can override settings before first use.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=5,
            pool_recycle=settings.DB_MAX_IDLE_SECONDS,
            echo=False,
        )
    return _engine


def get_session_factory():
    """Create or return the global session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session.

    NOTE: Does NOT auto-commit.  Because FastAPI dependency cleanup runs
    *after* the HTTP response is sent, any commit placed after ``yield`` will
    race with the caller's next request: the response may claim "player
    created" while the row still isn't visible to the next read.

    Every endpoint that WRITES data must explicitly call
    ``await session.commit()`` before returning its response.  Read-only
    endpoints don't need to commit.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the global engine (for shutdown)."""
    global _engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
