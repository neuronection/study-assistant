import hashlib
import re
from datetime import timedelta
from typing import Any, cast

import fitz
from fastapi.testclient import TestClient

from app.core.vocab import CaptureScope
from app.domain.models import CaptureStaging, CaptureToken, utcnow
from app.services.capture import (
    authenticate_capture_token,
    issue_capture_token,
    revoke_capture_token,
)

# A token minted by the pre-adoption code (``token_urlsafe(32)``) and its
# SHA-256 digest: the adoption must not change the stored form.
PRE_CHANGE_CAPTURE_TOKEN = "Zx4q0J7m2n8V1c3b5R7t9Y2u4I6o8P0aS2d4F6g8H0K"
PRE_CHANGE_CAPTURE_DIGEST = "05c213619f92790e1d97eaeb1af32136c0cc18b31323a9b72ecd856809ecb3e1"


def make_pdf(text: str = "Capture kernel test") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return bytes(doc.tobytes())


def make_course(client: TestClient) -> str:
    created = client.post("/api/v1/courses", json={"title": "Capture"})
    assert created.status_code == 201
    return str(created.json()["id"])


def stage(client: TestClient, data: bytes, name: str = "page.pdf") -> dict[str, Any]:
    response = client.post(
        "/api/v1/capture",
        data={"source_kind": "camera"},
        files=[("files", (name, data, "application/pdf"))],
    )
    assert response.status_code == 201, response.text
    rows = response.json()
    assert len(rows) == 1
    return cast(dict[str, Any], rows[0])


def test_stage_commit_list_and_discard(client: TestClient) -> None:
    course_id = make_course(client)
    staged = stage(client, make_pdf())
    assert staged["status"] == "staged"
    assert staged["source_kind"] == "camera"
    assert staged["material_id"] is None
    assert staged["byte_size"] > 0

    listed = client.get("/api/v1/capture")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [staged["id"]]

    committed = client.post(
        f"/api/v1/capture/{staged['id']}/commit",
        json={"course_id": course_id, "title": "Lecture photo"},
    )
    assert committed.status_code == 200, committed.text
    body = committed.json()
    assert body["capture_id"] == staged["id"]
    assert body["deduped"] is False
    assert body["job_id"] is not None

    material = client.get(f"/api/v1/materials/{body['material_id']}")
    assert material.status_code == 200
    assert material.json()["material"]["title"] == "Lecture photo"

    assert client.get("/api/v1/capture").json() == []
    again = client.post(f"/api/v1/capture/{staged['id']}/commit", json={"course_id": course_id})
    assert again.status_code == 409

    discarded = stage(client, make_pdf("Discard me"), "discard.pdf")
    removed = client.delete(f"/api/v1/capture/{discarded['id']}")
    assert removed.status_code == 200
    assert removed.json()["status"] == "discarded"
    assert client.get("/api/v1/capture").json() == []


def test_committing_the_same_bytes_dedupes_to_one_material(client: TestClient) -> None:
    course_id = make_course(client)
    data = make_pdf("Same bytes")

    first = stage(client, data, "first.pdf")
    first_commit = client.post(
        f"/api/v1/capture/{first['id']}/commit", json={"course_id": course_id}
    ).json()

    second = stage(client, data, "second.pdf")
    second_commit = client.post(
        f"/api/v1/capture/{second['id']}/commit", json={"course_id": course_id}
    ).json()

    assert second_commit["deduped"] is True
    assert second_commit["job_id"] is None
    assert second_commit["material_id"] == first_commit["material_id"]


def test_client_op_id_is_idempotent_and_profile_scoped(client: TestClient) -> None:
    data = make_pdf("op one")
    response = client.post(
        "/api/v1/capture",
        data={"source_kind": "upload", "client_op_id": "op-1"},
        files=[("files", ("one.pdf", data, "application/pdf"))],
    )
    assert response.status_code == 201
    row = response.json()[0]
    assert row["status"] == "staged"

    duplicate = client.post(
        "/api/v1/capture",
        data={"source_kind": "upload", "client_op_id": "op-1"},
        files=[("files", ("one.pdf", data, "application/pdf"))],
    )
    assert duplicate.status_code == 201
    assert duplicate.json()[0]["id"] == row["id"]

    reused = client.post(
        "/api/v1/capture",
        data={"source_kind": "upload", "client_op_id": "op-1"},
        files=[("files", ("other.pdf", make_pdf("different"), "application/pdf"))],
    )
    assert reused.status_code == 422


def test_expired_captures_leave_the_staged_inbox(client: TestClient) -> None:
    staged = stage(client, make_pdf("Expire me"), "expire.pdf")
    factory = cast(Any, client.app).state.session_factory
    with factory() as session:
        row = session.get(CaptureStaging, staged["id"])
        assert row is not None
        row.expires_at = utcnow() - timedelta(days=1)
        session.commit()

    assert client.get("/api/v1/capture").json() == []
    expired = client.get("/api/v1/capture", params={"status": "expired"})
    assert [row["id"] for row in expired.json()] == [staged["id"]]


def test_device_tokens_hash_scope_and_revoke(client: TestClient, profile_id: str) -> None:
    factory = cast(Any, client.app).state.session_factory
    with factory() as session:
        token, row = issue_capture_token(
            session, profile_id=profile_id, label="phone", scope=CaptureScope.STAGE
        )
        session.commit()
        token_id = row.id

    with factory() as session:
        assert (
            authenticate_capture_token(session, token=token, scope=CaptureScope.STAGE) is not None
        )
        assert authenticate_capture_token(session, token=token, scope=CaptureScope.CLIP) is None
        assert authenticate_capture_token(session, token="nope", scope=CaptureScope.STAGE) is None
        assert revoke_capture_token(session, token_id=token_id, profile_id=profile_id) is True
        session.commit()

    with factory() as session:
        assert authenticate_capture_token(session, token=token, scope=CaptureScope.STAGE) is None


def test_pre_change_device_token_still_verifies(client: TestClient, profile_id: str) -> None:
    """Rows hashed by the pre-adoption code keep authenticating unchanged."""
    factory = cast(Any, client.app).state.session_factory
    with factory() as session:
        row = CaptureToken(
            profile_id=profile_id,
            label="legacy",
            token_hash=PRE_CHANGE_CAPTURE_DIGEST,
            scope=CaptureScope.STAGE.value,
        )
        session.add(row)
        session.commit()
        token_id = row.id

    with factory() as session:
        found = authenticate_capture_token(
            session, token=PRE_CHANGE_CAPTURE_TOKEN, scope=CaptureScope.STAGE
        )
        assert found is not None
        assert found.id == token_id


def test_minted_device_token_is_a_brandless_urlsafe_secret(
    client: TestClient, profile_id: str
) -> None:
    factory = cast(Any, client.app).state.session_factory
    with factory() as session:
        token, row = issue_capture_token(
            session, profile_id=profile_id, label="phone", scope=CaptureScope.STAGE
        )
        session.commit()
        token_hash = row.token_hash

    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
    assert token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
    with factory() as session:
        assert (
            authenticate_capture_token(session, token=token, scope=CaptureScope.STAGE) is not None
        )


def test_malformed_device_tokens_are_refused_without_raising(
    client: TestClient, profile_id: str
) -> None:
    factory = cast(Any, client.app).state.session_factory
    with factory() as session:
        for bad in ("", "   ", "nope", "!", "a/b+c=", "é" * 43):
            assert authenticate_capture_token(session, token=bad, scope=CaptureScope.STAGE) is None


def png_bytes(color: tuple[float, float, float] = (0.9, 0.9, 0.9)) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=40, height=30)
    page.draw_rect(page.rect, color=color, fill=color)
    pixmap = page.get_pixmap()
    return bytes(pixmap.tobytes("png"))


def stage_image(client: TestClient, name: str, data: bytes | None = None) -> dict[str, Any]:
    response = client.post(
        "/api/v1/capture",
        data={"source_kind": "camera"},
        files=[("files", (name, data if data is not None else png_bytes(), "image/png"))],
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json()[0])


def test_assemble_images_into_one_pdf_capture(client: TestClient) -> None:
    course_id = make_course(client)
    first = stage_image(client, "page-1.png")
    second = stage_image(client, "page-2.png")

    combined = client.post(
        "/api/v1/capture/assemble",
        json={
            "items": [
                {"capture_id": first["id"], "rotation": 0},
                {"capture_id": second["id"], "rotation": 90},
            ],
            "title": "Problem set",
        },
    )
    assert combined.status_code == 201, combined.text
    pdf = combined.json()
    assert pdf["mime"] == "application/pdf"
    assert pdf["filename"] == "Problem set.pdf"
    assert pdf["status"] == "staged"

    inbox = client.get("/api/v1/capture").json()
    assert [row["id"] for row in inbox] == [pdf["id"]]

    committed = client.post(f"/api/v1/capture/{pdf['id']}/commit", json={"course_id": course_id})
    assert committed.status_code == 200, committed.text
    material = client.get(f"/api/v1/materials/{committed.json()['material_id']}").json()
    assert material["material"]["kind"] == "pdf"


def test_assemble_requires_two_staged_images(client: TestClient) -> None:
    one = stage_image(client, "only.png")
    response = client.post(
        "/api/v1/capture/assemble",
        json={"items": [{"capture_id": one["id"], "rotation": 0}]},
    )
    assert response.status_code == 422

    pdf = stage(client, make_pdf("not an image"))
    mixed = client.post(
        "/api/v1/capture/assemble",
        json={
            "items": [
                {"capture_id": one["id"], "rotation": 0},
                {"capture_id": pdf["id"], "rotation": 0},
            ]
        },
    )
    assert mixed.status_code == 422
