"""Database integration tests.

These tests run against a real PostgreSQL instance (migrated via Alembic)
and are skipped unless ``CLOUDNOTES_TEST_DATABASE_URL`` is set. See
``docs/database.md`` for how to spin up a database.
"""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import User

pytestmark = pytest.mark.db


async def test_users_table_exists_after_migrations(migrated_engine: AsyncEngine) -> None:
    async with migrated_engine.connect() as connection:
        tables = await connection.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    assert "users" in tables


async def test_user_roundtrip_and_timestamps(db_session: AsyncSession) -> None:
    user = User(email="roundtrip@example.com", password_hash="hash-abc")
    db_session.add(user)
    await db_session.flush()

    assert user.id is not None
    assert user.created_at is not None
    assert user.updated_at is not None

    loaded = await db_session.get(User, user.id)
    assert loaded is not None
    assert loaded.email == "roundtrip@example.com"
    assert loaded.password_hash == "hash-abc"


async def test_duplicate_email_rejected_by_unique_index(db_session: AsyncSession) -> None:
    db_session.add(User(email="dupe@example.com", password_hash="x"))
    await db_session.flush()

    db_session.add(User(email="dupe@example.com", password_hash="y"))
    with pytest.raises(IntegrityError, match="ix_users_email"):
        await db_session.flush()
    await db_session.rollback()  # clear the aborted transaction


async def test_email_unique_index_exists(migrated_engine: AsyncEngine) -> None:
    def _indexes(sync_conn):  # type: ignore[no-untyped-def]
        return {ix["name"]: ix["unique"] for ix in inspect(sync_conn).get_indexes("users")}

    async with migrated_engine.connect() as connection:
        indexes = await connection.run_sync(_indexes)
    assert indexes.get("ix_users_email") is True


async def test_select_one_probe(migrated_engine: AsyncEngine) -> None:
    async with migrated_engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
