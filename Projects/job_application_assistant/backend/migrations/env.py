"""
Alembic migration environment (async-enabled).

This configures Alembic to run migrations against the application's async
SQLAlchemy engine (asyncpg driver). The database URL is read from the
application settings rather than from ``alembic.ini`` so there is a single
source of truth.

``target_metadata`` is bound to the models' ``Base.metadata`` so that
``alembic revision --autogenerate`` can detect schema changes.
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Make the project importable.
#
# This file lives at backend/migrations/env.py. We add the directory that
# contains the ``backend`` package (i.e. the repository's project root) to
# sys.path so that ``import backend...`` works regardless of the CWD Alembic
# is invoked from.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.config import settings  # noqa: E402
from backend.models import Base  # noqa: E402

# Alembic Config object, providing access to values in alembic.ini.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the configured URL with the application settings URL so there is a
# single source of truth. Allow an ALEMBIC_DATABASE_URL env override for CI.
_db_url = os.getenv("ALEMBIC_DATABASE_URL", settings.database_url)
config.set_main_option("sqlalchemy.url", _db_url)

# Metadata used for 'autogenerate' support.
target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    """Configure the context with a live connection and run migrations."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine. Calls to
    ``context.execute()`` emit the given string to the script output.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
