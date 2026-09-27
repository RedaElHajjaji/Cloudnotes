"""Shared pytest fixtures for the CloudNotes test suite."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Yield an HTTP test client bound to a fresh application instance."""
    with TestClient(create_app()) as test_client:
        yield test_client
