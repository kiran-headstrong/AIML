"""
Database connection and session management.

Provides an async SQLAlchemy 2.x engine (backed by the asyncpg driver), an
``async_sessionmaker`` session factory, and a FastAPI-compatible ``get_db``
dependency that yields an :class:`~sqlalchemy.ext.asyncio.AsyncSession`.

The database URL is read from the application settings
(:attr:`backend.config.Settings.database_url`), which uses the
``postgresql+asyncpg://`` scheme.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

try:  # package mode: ``import backend.database`` (Alembic, tests)
    from .config import settings
    from .models import Base
except ImportError:  # direct mode: ``main.py`` inserts backend dir on sys.path
    from config import settings
    from models import Base

__all__ = [
    "Base",
    "engine",
    "AsyncSessionLocal",
    "get_db",
]


# ---------------------------------------------------------------------------
# Engine and session factory
# ---------------------------------------------------------------------------

#: The async engine. ``echo`` mirrors the application debug flag so SQL is
#: logged during development. ``pool_pre_ping`` guards against stale
#: connections being handed out from the pool.
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    future=True,
)

#: Session factory. ``expire_on_commit=False`` keeps ORM attributes loaded
#: after a commit, which is important for async request handlers that return
#: ORM objects after committing a transaction.
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for the duration of a request.

    Usage in a FastAPI route::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...

    The session is closed automatically when the request completes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
