"""Shared pytest fixtures for the CloudNotes test suite."""

import asyncio
import os
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.main import create_app

TEST_DATABASE_URL_ENV = "CLOUDNOTES_TEST_DATABASE_URL"
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _make_alembic_config(database_url: str) -> Config:
    """Build an Alembic config targeting the given database URL.

    The URL is passed via ``config.attributes`` (never through ini files or
    the process environment) so programmatic invocations stay isolated.
    """
    alembic_config = Config(str(ALEMBIC_INI))
    alembic_config.set_main_option("script_location", str(ALEMBIC_INI.parent / "migrations"))
    alembic_config.attributes["database_url"] = database_url
    return alembic_config


@pytest.fixture(scope="session")
def database_url() -> str:
    """Database URL for integration tests; skips when not configured."""
    url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not url:
        pytest.skip(
            f"{TEST_DATABASE_URL_ENV} not set; skipping database integration tests "
            "(see .env.example and docs/database.md)"
        )
    return url


def _run_alembic(database_url: str, *args: str) -> None:
    """Run an Alembic command in a worker thread.

    Alembic's ``env.py`` drives migrations with its own event loop
    (``asyncio.run``), so it must not execute inside the pytest-asyncio
    event loop used by the tests.
    """
    asyncio.run(asyncio.to_thread(command.upgrade, _make_alembic_config(database_url), *args))


@pytest.fixture(scope="session")
def migrated_engine(database_url: str) -> Iterator[AsyncEngine]:
    """Migrate the test database to head, yield an engine, then downgrade."""
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        poolclass=NullPool,  # fresh connection per test: pytest-asyncio uses a new loop per test
    )
    try:
        _run_alembic(database_url, "head")
        yield engine
    finally:
        _run_alembic(database_url, "base")
        asyncio.run(engine.dispose())


@pytest.fixture
async def db_session(migrated_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a session whose transaction is always rolled back.

    Each test runs inside a transaction on one connection; everything the
    test writes is undone on teardown, keeping tests isolated and fast.
    """
    async with migrated_engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(bind=connection, expire_on_commit=False)
        async with session_factory() as session:
            yield session
        await transaction.rollback()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Yield an HTTP test client bound to a fresh application instance."""
    with TestClient(create_app()) as test_client:
        yield test_client
