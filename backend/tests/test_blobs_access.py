"""Blob access over browser *navigations* (identity-auth §15/§10).

PDF iframe documents and <img> subresources cannot carry the
X-Profile-Id header — the route is profile-bind exempt and owner-scopes
the sha itself. Regression: web mode used to answer 400
"X-Profile-Id required" to every iframe PDF open.
"""

from typing import Any, cast

from conftest import AnonymousTestClient, mint_session
from fastapi.testclient import TestClient


def _upload_material(client: Any, title: str) -> str:
    course_id = client.post("/api/v1/courses", json={"title": title}).json()["id"]
    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("doc.pdf", b"%PDF-1.4 fake body", "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    return str(upload.json()["material"]["blob_sha"])


def _navigator(app: Any, cookie: str) -> Any:
    """Navigation-shaped client: cookies only — no custom headers."""
    return AnonymousTestClient(app, headers={"Cookie": cookie})


def test_navigation_without_profile_header_serves_owned_blob(client: TestClient) -> None:
    sha = _upload_material(client, "Blob nav")
    response = _navigator(client.app, cast(Any, client).session_cookie).get(f"/api/v1/blobs/{sha}")
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == "inline"
    assert response.content == b"%PDF-1.4 fake body"


def test_img_subresource_without_profile_header_serves_owned_blob(
    client: TestClient,
) -> None:
    sha = _upload_material(client, "Blob img")
    response = _navigator(client.app, cast(Any, client).session_cookie).get(f"/api/v1/blobs/{sha}")
    assert response.status_code == 200


def test_foreign_blob_is_indistinguishable_from_missing(client: TestClient) -> None:
    app = cast(Any, client.app)
    other_cookie, other_csrf, other_profile = mint_session(app, "other-blobs@study.local")
    other = AnonymousTestClient(
        app,
        headers={"Cookie": other_cookie, "X-CSRF-Token": other_csrf, "X-Profile-Id": other_profile},
    )
    foreign_sha = _upload_material(other, "Other user blob")

    nav = _navigator(app, cast(Any, client).session_cookie)
    assert nav.get(f"/api/v1/blobs/{foreign_sha}").status_code == 404
    assert nav.get(f"/api/v1/blobs/{'0' * 64}").status_code == 404


def test_unreferenced_blob_is_not_served(client: TestClient) -> None:
    app = cast(Any, client.app)
    with app.state.session_factory() as db:
        stored = app.state.blobs.put(b"orphan bytes", mime="application/octet-stream", session=db)
        sha = str(stored.sha256)
    nav = _navigator(app, cast(Any, client).session_cookie)
    assert nav.get(f"/api/v1/blobs/{sha}").status_code == 404


def test_invalid_sha_is_422_and_anonymous_is_401(client: TestClient) -> None:
    app = cast(Any, client.app)
    nav = _navigator(app, cast(Any, client).session_cookie)
    assert nav.get("/api/v1/blobs/not-a-sha").status_code == 422
    assert AnonymousTestClient(app).get(f"/api/v1/blobs/{'a' * 64}").status_code == 401


def test_desktop_shell_gate_exempts_navigations(desktop_client: TestClient) -> None:
    """Shell-attached desktop: the navigation carries cookies but no
    X-Shell-Token — the route serves it (ADR-0024) while non-exempt
    routes stay behind the shell gate."""
    client = cast(Any, desktop_client)
    app = client.app
    sha = _upload_material(client, "Desktop nav blob")
    nav = _navigator(app, client.session_cookie)
    response = nav.get(f"/api/v1/blobs/{sha}")
    assert response.status_code == 200, response.text
    # the shell gate still arms the rest of the API
    assert nav.get("/api/v1/chat/sessions").status_code == 403
