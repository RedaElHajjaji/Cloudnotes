"""End-to-end API tests for the authentication flow.

These tests run the real application against the real migrated database so
the full path is exercised: routing → schemas → service → repository →
PostgreSQL. The ``get_db`` dependency is overridden to bind sessions to the
test engine. Skipped unless ``CLOUDNOTES_TEST_DATABASE_URL`` is set.
"""

import uuid
from collections.abc import AsyncGenerator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.session import get_db
from app.main import create_app
from app.models.user import User

pytestmark = [pytest.mark.auth, pytest.mark.db]


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


@pytest.fixture
def client(migrated_engine: AsyncEngine) -> Iterator[TestClient]:
    """Test client whose requests use sessions on the migrated test database."""
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


def test_register_creates_user_with_hashed_password(client: TestClient) -> None:
    email = _unique_email()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Sup3r-Secret"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == email
    assert "password" not in body
    assert "password_hash" not in body
    assert body["id"] and body["created_at"]


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    email = _unique_email()
    payload = {"email": email, "password": "Sup3r-Secret"}
    first = client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]


def test_register_rejects_weak_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": _unique_email(), "password": "weak"},
    )
    assert response.status_code == 422


def test_register_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "definitely-not-an-email", "password": "Sup3r-Secret"},
    )
    assert response.status_code == 422


def test_login_returns_bearer_token(client: TestClient) -> None:
    email = _unique_email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "Sup3r-Secret"})

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Sup3r-Secret"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"].count(".") == 2  # header.payload.signature


def test_login_rejects_wrong_password(client: TestClient) -> None:
    email = _unique_email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "Sup3r-Secret"})

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Wrong-Password-1"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_login_rejects_unknown_email_with_same_message(client: TestClient) -> None:
    ghost = client.post(
        "/api/v1/auth/login",
        json={"email": _unique_email(), "password": "Whatever-123"},
    )
    known_email = _unique_email()
    client.post("/api/v1/auth/register", json={"email": known_email, "password": "Sup3r-Secret"})
    known = client.post(
        "/api/v1/auth/login",
        json={"email": known_email, "password": "Wrong-Password-1"},
    )
    assert ghost.status_code == 401
    assert known.status_code == 401
    assert ghost.json() == known.json()  # no user enumeration


def test_me_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_rejects_invalid_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_returns_current_user_with_valid_token(client: TestClient) -> None:
    email = _unique_email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "Sup3r-Secret"})
    token = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Sup3r-Secret"},
    ).json()["access_token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == email
    assert "password_hash" not in body


def test_expired_token_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.core.security import create_access_token

    monkeypatch.setenv("CLOUDNOTES_JWT_ACCESS_TOKEN_EXPIRE_SECONDS", "-10")
    get_settings.cache_clear()
    try:
        stale_token = create_access_token(str(uuid.uuid4()))
    finally:
        monkeypatch.undo()  # restore env BEFORE re-caching settings
        get_settings.cache_clear()

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {stale_token}"},
    )
    assert response.status_code == 401


async def test_password_is_stored_hashed_never_plaintext(
    client: TestClient,
    migrated_engine: AsyncEngine,
) -> None:
    """Stored value is an Argon2id hash; the plaintext never reaches the DB."""
    email = _unique_email()
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Sup3r-Secret"},
    )
    assert register.status_code == 201

    async with migrated_engine.connect() as connection:
        stored_hash = await connection.scalar(select(User.password_hash).where(User.email == email))
    assert stored_hash is not None
    assert stored_hash.startswith("$argon2id$")
    assert "Sup3r-Secret" not in stored_hash
