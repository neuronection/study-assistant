"""Profile binding (identity-auth §15, test-kit case 18.8).

- server: absent `X-Profile-Id` ⇒ 400; malformed, unknown, or
  cross-user ⇒ 403; owned ⇒ 200;
- desktop: absent header falls back to the last-used profile;
- profile-independent surfaces (auth, /me, /profiles, /admin) work
  without the header;
- profile REST resources hide foreign ids behind 404 (§7).
"""
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.models import Profile

# Every test here implements identity-auth §18.8 (profile binding) through
# study's real middleware — the family contract drift gate.
pytestmark = pytest.mark.contract


def test_server_requires_profile_header(client: TestClient) -> None:
    client.headers.pop("X-Profile-Id", None)
    response = client.get("/api/v1/courses")
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "X-Profile-Id required"


def test_server_rejects_malformed_and_unknown_profile(client: TestClient) -> None:
    for value in ("garbage", "9999"):
        client.headers["X-Profile-Id"] = value
        response = client.get("/api/v1/courses")
        assert response.status_code == 403, (value, response.text)
    client.headers["X-Profile-Id"] = "00000000-0000-4000-8000-00000000beef"
    response = client.get("/api/v1/courses")
    assert response.status_code == 403, response.text


def test_server_rejects_foreign_profile(
    client: TestClient, owner: Any, db_session: Session
) -> None:
    foreign = Profile(user_id=owner.id, name="Foreign", is_default=True)
    db_session.add(foreign)
    db_session.commit()
    client.headers["X-Profile-Id"] = str(foreign.id)
    response = client.get("/api/v1/courses")
    assert response.status_code == 403, response.text


def test_exempt_surfaces_work_without_header(client: TestClient) -> None:
    client.headers.pop("X-Profile-Id", None)
    for path in ("/api/v1/profiles", "/api/v1/auth/me"):
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)


def test_owned_profile_header_binds(client: TestClient) -> None:
    response = client.get("/api/v1/courses")
    assert response.status_code == 200, response.text
    created = client.post("/api/v1/profiles", json={"name": "Extra"})
    assert created.status_code == 201, created.text
    client.headers["X-Profile-Id"] = created.json()["id"]
    response = client.get("/api/v1/courses")
    assert response.status_code == 200, response.text


def test_desktop_falls_back_to_last_used_profile(desktop_client: TestClient) -> None:
    desktop_client.headers.pop("X-Profile-Id", None)
    response = desktop_client.get("/api/v1/courses")
    assert response.status_code == 200, response.text
    listed = desktop_client.get("/api/v1/profiles").json()
    assert listed and listed[0]["is_default"] is True


def test_profile_resources_hide_foreign_ids(
    client: TestClient, owner: Any, db_session: Session
) -> None:
    foreign = Profile(user_id=owner.id, name="Foreign", is_default=True)
    db_session.add(foreign)
    db_session.commit()
    patched = client.patch(
        f"/api/v1/profiles/{foreign.id}", json={"name": "Hijacked"}
    )
    assert patched.status_code == 404, patched.text
    deleted = client.delete(f"/api/v1/profiles/{foreign.id}")
    assert deleted.status_code == 404, deleted.text


def test_profile_crud_scoped_to_user(client: TestClient) -> None:
    created = client.post("/api/v1/profiles", json={"name": "Second"})
    assert created.status_code == 201, created.text
    second_id = created.json()["id"]
    listed = client.get("/api/v1/profiles").json()
    assert {entry["name"] for entry in listed} >= {"Default", "Second"}

    patched = client.patch(f"/api/v1/profiles/{second_id}", json={"is_default": True})
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_default"] is True
    refreshed = client.get("/api/v1/profiles").json()
    defaults = [entry["id"] for entry in refreshed if entry["is_default"]]
    assert defaults == [second_id]

    renamed = client.patch(f"/api/v1/profiles/{second_id}", json={"name": "Renamed"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Renamed"
