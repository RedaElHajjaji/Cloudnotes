"""End-to-end API tests for the notes CRUD flow.

Runs the real application against the real migrated database. The ``client``
fixture (``tests/conftest.py``) overrides ``get_db`` to bind request sessions
to the test engine; ``auth_headers``/``other_auth_headers`` provide
authenticated users. Skipped unless ``CLOUDNOTES_TEST_DATABASE_URL`` is set.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models.note import Note

pytestmark = [pytest.mark.db]

NOTE_URL = "/api/v1/notes"
SAMPLE_NOTE = {"title": "Groceries", "content": "Milk, eggs, coffee"}


def _unique_note(**overrides: str) -> dict[str, str]:
    payload = dict(SAMPLE_NOTE)
    payload["title"] = f"{SAMPLE_NOTE['title']} {uuid.uuid4().hex[:8]}"
    payload.update(overrides)
    return payload


# --- create ---


def test_create_note_returns_201_and_body(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(NOTE_URL, json=SAMPLE_NOTE, headers=auth_headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == SAMPLE_NOTE["title"]
    assert body["content"] == SAMPLE_NOTE["content"]
    assert body["id"] and body["user_id"] and body["created_at"] and body["updated_at"]


def test_create_note_rejects_empty_title(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(NOTE_URL, json={"title": "", "content": "x"}, headers=auth_headers)
    assert response.status_code == 422


def test_create_note_rejects_overlong_title(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(NOTE_URL, json={"title": "x" * 201, "content": ""}, headers=auth_headers)
    assert response.status_code == 422


# --- retrieve ---


def test_retrieve_note(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(NOTE_URL, json=SAMPLE_NOTE, headers=auth_headers).json()
    response = client.get(f"{NOTE_URL}/{created['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["title"] == SAMPLE_NOTE["title"]


def test_nonexistent_note_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    random_id = str(uuid.uuid4())
    for method, url in (
        ("get", f"{NOTE_URL}/{random_id}"),
        ("put", f"{NOTE_URL}/{random_id}"),
        ("delete", f"{NOTE_URL}/{random_id}"),
    ):
        kwargs: dict[str, object] = {"headers": auth_headers}
        if method == "put":
            kwargs["json"] = {"title": "x"}
        response = getattr(client, method)(url, **kwargs)
        assert response.status_code == 404, f"{method} {url}: {response.text}"


def test_nonexistent_note_id_shape(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Malformed (non-UUID) ids are rejected by routing with 422."""
    response = client.get(f"{NOTE_URL}/not-a-uuid", headers=auth_headers)
    assert response.status_code == 422


# --- list ---


def test_list_notes_returns_created_notes(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client.post(NOTE_URL, json=_unique_note(), headers=auth_headers)
    client.post(NOTE_URL, json=_unique_note(), headers=auth_headers)

    response = client.get(NOTE_URL, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    assert len(body["items"]) >= 2
    assert body["limit"] == 20 and body["offset"] == 0


def test_list_notes_pagination_and_newest_first(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    first = client.post(NOTE_URL, json=_unique_note(), headers=auth_headers).json()
    second = client.post(NOTE_URL, json=_unique_note(), headers=auth_headers).json()

    page = client.get(f"{NOTE_URL}?limit=1&offset=0", headers=auth_headers).json()
    assert page["total"] >= 2
    assert len(page["items"]) == 1
    assert page["items"][0]["id"] == second["id"]  # newest first

    second_page = client.get(f"{NOTE_URL}?limit=1&offset=1", headers=auth_headers).json()
    assert second_page["items"][0]["id"] == first["id"]


def test_list_notes_rejects_invalid_pagination(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    assert client.get(f"{NOTE_URL}?limit=0", headers=auth_headers).status_code == 422
    assert client.get(f"{NOTE_URL}?limit=101", headers=auth_headers).status_code == 422
    assert client.get(f"{NOTE_URL}?offset=-1", headers=auth_headers).status_code == 422


# --- update ---


def test_update_note_full_and_partial(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(NOTE_URL, json=SAMPLE_NOTE, headers=auth_headers).json()

    full = client.put(
        f"{NOTE_URL}/{created['id']}",
        json={"title": "Renamed", "content": "New body"},
        headers=auth_headers,
    )
    assert full.status_code == 200, full.text
    assert full.json()["title"] == "Renamed"
    assert full.json()["content"] == "New body"

    partial = client.put(
        f"{NOTE_URL}/{created['id']}",
        json={"title": "Renamed again"},
        headers=auth_headers,
    )
    assert partial.status_code == 200
    assert partial.json()["title"] == "Renamed again"
    assert partial.json()["content"] == "New body"  # untouched by partial update


def test_update_note_rejects_empty_title(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(NOTE_URL, json=SAMPLE_NOTE, headers=auth_headers).json()
    response = client.put(f"{NOTE_URL}/{created['id']}", json={"title": ""}, headers=auth_headers)
    assert response.status_code == 422


# --- delete ---


def test_delete_note_returns_204_and_note_is_gone(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    created = client.post(NOTE_URL, json=SAMPLE_NOTE, headers=auth_headers).json()

    deleted = client.delete(f"{NOTE_URL}/{created['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    assert deleted.content == b""

    fetched = client.get(f"{NOTE_URL}/{created['id']}", headers=auth_headers)
    assert fetched.status_code == 404


# --- unauthorized access ---


def test_all_note_endpoints_require_authentication(client: TestClient) -> None:
    assert client.post(NOTE_URL, json=SAMPLE_NOTE).status_code == 401
    assert client.get(NOTE_URL).status_code == 401
    assert client.get(f"{NOTE_URL}/{uuid.uuid4()}").status_code == 401
    assert client.put(f"{NOTE_URL}/{uuid.uuid4()}", json={"title": "x"}).status_code == 401
    assert client.delete(f"{NOTE_URL}/{uuid.uuid4()}").status_code == 401


def test_note_endpoints_reject_invalid_token(client: TestClient) -> None:
    bad = {"Authorization": "Bearer garbage.token.here"}
    assert client.post(NOTE_URL, json=SAMPLE_NOTE, headers=bad).status_code == 401
    assert client.get(NOTE_URL, headers=bad).status_code == 401


# --- cross-user access ---


def test_cross_user_access_is_impossible(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    """Another user's note is indistinguishable from a nonexistent one (404)."""
    created = client.post(NOTE_URL, json=SAMPLE_NOTE, headers=auth_headers).json()
    foreign_id = created["id"]

    # The other user cannot read, update, or delete it — 404, not 403, so
    # ids are not enumerable across users.
    assert client.get(f"{NOTE_URL}/{foreign_id}", headers=other_auth_headers).status_code == 404
    assert (
        client.put(
            f"{NOTE_URL}/{foreign_id}",
            json={"title": "Hijacked"},
            headers=other_auth_headers,
        ).status_code
        == 404
    )
    assert client.delete(f"{NOTE_URL}/{foreign_id}", headers=other_auth_headers).status_code == 404

    # And it never appears in the other user's list.
    other_page = client.get(NOTE_URL, headers=other_auth_headers).json()
    assert all(item["id"] != foreign_id for item in other_page["items"])

    # The owner can still work with it.
    assert client.get(f"{NOTE_URL}/{foreign_id}", headers=auth_headers).status_code == 200


def test_cross_user_listing_is_isolated(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    client.post(NOTE_URL, json=_unique_note(), headers=auth_headers)
    client.post(NOTE_URL, json=_unique_note(), headers=other_auth_headers)

    mine = client.get(NOTE_URL, headers=auth_headers).json()
    theirs = client.get(NOTE_URL, headers=other_auth_headers).json()
    assert mine["total"] == 1
    assert theirs["total"] == 1
    assert mine["items"][0]["user_id"] != theirs["items"][0]["user_id"]


async def test_deleting_user_cascades_to_notes(
    client: TestClient,
    auth_headers: dict[str, str],
    migrated_engine: AsyncEngine,
) -> None:
    """ON DELETE CASCADE removes the user's notes when the user row is deleted."""
    created = client.post(NOTE_URL, json=SAMPLE_NOTE, headers=auth_headers).json()
    user_id = created["user_id"]

    async with migrated_engine.begin() as connection:
        await connection.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})

    async with migrated_engine.connect() as connection:
        count = await connection.scalar(
            select(func.count()).select_from(Note).where(Note.user_id == user_id)
        )
    assert count == 0
