"""Unit tests for the readiness endpoint (no real database required)."""

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import __version__
from app.api.v1.ready import router as ready_router
from app.db.health import check_database_connection


class _FakeResult:
    def scalar_one(self) -> int:
        return 1


class FakeConnection:
    """Minimal AsyncConnection stand-in recording executed statements."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.executed: list[Any] = []

    async def execute(self, statement: Any) -> _FakeResult:
        self.executed.append(statement)
        if self.fail:
            raise RuntimeError("database exploded")
        return _FakeResult()


class _FakeConnectContext:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self._connection

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeEngine:
    """Minimal AsyncEngine stand-in yielding a pre-built connection."""

    def __init__(
        self, connection: FakeConnection | None = None, *, connect_fails: bool = False
    ) -> None:
        self._connection = connection
        self._connect_fails = connect_fails

    def connect(self) -> _FakeConnectContext:
        if self._connect_fails:
            raise RuntimeError("connection refused")
        assert self._connection is not None
        return _FakeConnectContext(self._connection)


def make_ready_app(engine: FakeEngine) -> FastAPI:
    """Build a minimal app exposing /ready at the root and under /api/v1."""
    app = FastAPI()
    app.include_router(ready_router)
    app.include_router(ready_router, prefix="/api/v1")
    app.state.engine = engine
    return app


async def test_check_database_connection_executes_probe() -> None:
    connection = FakeConnection()
    probe = await check_database_connection(connection)
    assert probe == {"probe": "SELECT 1", "result": 1}
    assert len(connection.executed) == 1
    assert str(connection.executed[0]) == str(text("SELECT 1"))


def test_ready_ok_at_root_and_api_v1() -> None:
    engine = FakeEngine(FakeConnection())
    with TestClient(make_ready_app(engine)) as client:
        for url in ("/ready", "/api/v1/ready"):
            response = client.get(url)
            assert response.status_code == 200
            assert response.json() == {
                "status": "ok",
                "database": True,
                "version": __version__,
            }


def test_ready_returns_503_when_database_unreachable() -> None:
    engine = FakeEngine(FakeConnection(fail=True))
    with TestClient(make_ready_app(engine)) as client:
        for url in ("/ready", "/api/v1/ready"):
            response = client.get(url)
            assert response.status_code == 503
            assert response.json() == {
                "status": "unavailable",
                "database": False,
                "version": __version__,
            }


def test_ready_returns_503_when_connection_cannot_be_acquired() -> None:
    """Covers the failure mode where engine.connect() itself raises."""
    engine = FakeEngine(connect_fails=True)
    with TestClient(make_ready_app(engine)) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "unavailable",
            "database": False,
            "version": __version__,
        }


def test_ready_registered_in_openapi(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/ready" in schema["paths"]
    assert "/api/v1/ready" in schema["paths"]
