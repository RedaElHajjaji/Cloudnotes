"""Tests for the health check and API documentation endpoints."""

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.core.config import Settings, get_settings


def test_health_at_root_reports_ok_and_version(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_health_under_api_v1_reports_ok_and_version(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_openapi_schema_is_served(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == get_settings().app_name
    assert schema["info"]["version"] == __version__
    assert "/health" in schema["paths"]
    assert "/api/v1/health" in schema["paths"]


def test_settings_can_be_overridden_via_constructor() -> None:
    settings = Settings(app_name="Override", app_env="test")
    assert settings.app_name == "Override"
    assert settings.app_env == "test"


def test_settings_use_cloudnotes_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDNOTES_APP_NAME", "Env Override")
    monkeypatch.setenv("CLOUDNOTES_APP_ENV", "staging")
    settings = Settings()
    assert settings.app_name == "Env Override"
    assert settings.app_env == "staging"
