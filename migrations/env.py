"""Alembic migration environment (async).

The database URL always comes from application settings
(``CLOUDNOTES_DATABASE_URL``). Programmatic callers (e.g. the test suite)
may pass an explicit URL via ``config.attributes["database_url"]``. Online
migrations run through an asyncpg engine; offline mode renders SQL using the
sync-driver URL form.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  # imported for side effect: register models on Base.metadata
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the target database URL (attribute override wins)."""
    override: str | None = config.attributes.get("database_url")
    return override or settings.database_url


def _to_offline_url(url: str) -> str:
    """Convert an asyncpg URL to the driver-agnostic offline form."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live database connection."""
    context.configure(
        url=_to_offline_url(_database_url()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations online using an asyncpg engine built from settings."""
    connectable = create_async_engine(
        _database_url(),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
