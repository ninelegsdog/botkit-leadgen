"""Alembic environment for botkit-leadgen.

Runs migrations against the configured SQLite database. The database URL is
read from the environment variable DATABASE_URL or falls back to the path
used by the application.
"""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Ensure the src package is importable when alembic runs from repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.migrations import SCHEMA  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Prefer DATABASE_URL env var, fallback to alembic.ini sqlalchemy.url,
# fallback to the app default.
target_url = (
    os.getenv("DATABASE_URL")
    or config.get_main_option("sqlalchemy.url")
    or "sqlite+aiosqlite:///./data/leads.db"
)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine, though an
    Engine is acceptable here as well. By skipping the Engine creation we don't
    need a DBAPI to be available.
    """
    context.configure(
        url=target_url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    """Execute migrations within a sync connection context.

    Alembic's context is synchronous, so we bridge the async connection via
    run_sync. The actual schema is defined in src.core.migrations.SCHEMA.
    """
    context.configure(
        connection=connection,
        target_metadata=None,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        for statement in SCHEMA.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                connection.execute(text(stmt))


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    connectable = create_async_engine(
        target_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
