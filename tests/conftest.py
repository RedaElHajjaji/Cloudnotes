"""Shared pytest fixtures for the CloudNotes test suite."""

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

# A test-only JWT secret must exist before any app module loads settings
# (``app.main`` instantiates settings at import time and the secret is
# intentionally required — see ``app/core/config.py``).
os.environ.setdefault("CLOUDNOTES_JWT_SECRET", "unit-test-secret-do-not-use-in-production")

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

from app.db.session import get_db
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
def client(migrated_engine: AsyncEngine) -> Iterator[TestClient]:
    """Test client whose requests use sessions on the migrated test database.

    The ``get_db`` dependency is overridden so the full request path
    (including the transaction-per-request commit) runs against the test
    engine.
    """
    factory = async_sessionmaker(bind=migrated_engine, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _new_credentials() -> tuple[str, str]:
    """Unique (email, password) credentials for one test user."""
    return f"user-{uuid.uuid4().hex[:12]}@example.com", "Sup3r-Secret"


@pytest.fixture
def registered_user(client: TestClient) -> tuple[str, str]:
    """A user registered through the real API: returns (email, password)."""
    email, password = _new_credentials()
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return email, password


@pytest.fixture
def auth_headers(client: TestClient, registered_user: tuple[str, str]) -> dict[str, str]:
    """Bearer auth headers for the primary registered user."""
    email, password = registered_user
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def other_auth_headers(client: TestClient) -> dict[str, str]:
    """Bearer auth headers for a second, independent user (cross-user tests)."""
    email, password = _new_credentials()
    register = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register.status_code == 201, register.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}
