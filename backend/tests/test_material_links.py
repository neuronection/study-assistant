import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.urls import normalize_url
from app.domain.models import Course, Material, Profile


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://youtube.com/watch?v=abc123&feature=share",
            "https://youtube.com/watch?v=abc123",
        ),
        ("https://youtu.be/abc123", "https://youtube.com/watch?v=abc123"),
        (
            "https://www.youtube.com/shorts/abc123",
            "https://youtube.com/watch?v=abc123",
        ),
        (
            "https://www.youtube.com/embed/abc123",
            "https://youtube.com/watch?v=abc123",
        ),
        ("https://Example.com/Path/", "https://example.com/Path"),
        (
            "https://example.com/page?utm_source=x&id=2&fbclid=y",
            "https://example.com/page?id=2",
        ),
        ("https://example.com:443/page", "https://example.com/page"),
        (
            "https://example.com/page?b=2&a=1",
            "https://example.com/page?a=1&b=2",
        ),
        ("https://example.com/page#section", "https://example.com/page"),
    ],
)
def test_normalize_url_equivalence_classes(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_normalize_url_keeps_distinct_urls_distinct() -> None:
    assert normalize_url("https://example.com/a") != normalize_url(
        "https://example.com/b"
    )


def test_normalize_url_keeps_non_youtube_short_path() -> None:
    assert normalize_url("https://example.com/abc123") != normalize_url(
        "https://youtube.com/watch?v=abc123"
    )


def test_create_link_dedupes_and_places(client: TestClient) -> None:
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )
        tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
        root_id = int(tree[0]["id"])

        first = client.post(
            "/api/v1/materials/link",
            json={
                "course_id": course_id,
                "url": "https://youtu.be/abc123?si=tag",
                "node_id": root_id,
            },
        )
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["deduped"] is False
        assert body["job_id"] is None
        material = body["material"]
        assert material["kind"] == "link"
        assert material["status"] == "ready"
        assert material["blob_sha"] is None
        assert material["source_url"] == "https://youtu.be/abc123?si=tag"
        assert material["provenance"]["source"] == "link"

        duplicate = client.post(
            "/api/v1/materials/link",
            json={
                "course_id": course_id,
                "url": "https://www.youtube.com/watch?v=abc123&feature=share",
            },
        )
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json()["deduped"] is True
        assert duplicate.json()["material"]["id"] == material["id"]

        other_course = int(
            client.post("/api/v1/courses", json={"title": "Algebra"}).json()["id"]
        )
        elsewhere = client.post(
            "/api/v1/materials/link",
            json={"course_id": other_course, "url": "https://youtu.be/abc123"},
        )
        assert elsewhere.status_code == 200
        assert elsewhere.json()["deduped"] is False

        detail = client.get(f"/api/v1/materials/{material['id']}").json()
        assert detail["material"]["source_url"] == "https://youtu.be/abc123?si=tag"


def test_create_link_rejects_non_http(client: TestClient) -> None:
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )
        for bad in ("ftp://example.com/file", "notaurl", "javascript:alert(1)"):
            response = client.post(
                "/api/v1/materials/link",
                json={"course_id": course_id, "url": bad},
            )
            assert response.status_code == 422, f"{bad}: {response.text}"


def test_partial_unique_index_enforces_dedupe(db_session: Session) -> None:
    profile = Profile(name="p")
    db_session.add(profile)
    db_session.flush()
    course = Course(profile_id=profile.id, title="Calc")
    db_session.add(course)
    db_session.flush()
    db_session.add(
        Material(
            profile_id=profile.id,
            course_id=course.id,
            kind="link",
            title="A",
            filename="a",
            status="ready",
            source_url="https://example.com/a",
            source_url_norm="https://example.com/a",
        )
    )
    db_session.flush()
    db_session.add(
        Material(
            profile_id=profile.id,
            course_id=course.id,
            kind="link",
            title="B",
            filename="b",
            status="ready",
            source_url="https://example.com/other",
            source_url_norm="https://example.com/a",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_non_link_rows_are_not_deduped_by_index(db_session: Session) -> None:
    profile = Profile(name="p")
    db_session.add(profile)
    db_session.flush()
    course = Course(profile_id=profile.id, title="Calc")
    db_session.add(course)
    db_session.flush()
    for title in ("one", "two"):
        db_session.add(
            Material(
                profile_id=profile.id,
                course_id=course.id,
                kind="doc",
                title=title,
                filename=title,
                status="ready",
                source_url="https://example.com/same",
                source_url_norm="https://example.com/same",
            )
        )
    db_session.flush()
    rows = list(db_session.scalars(select(Material)).all())
    assert len(rows) == 2


def test_bundle_round_trips_link_material(client: TestClient) -> None:
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )
        linked = client.post(
            "/api/v1/materials/link",
            json={"course_id": course_id, "url": "https://example.com/lecture-1"},
        )
        assert linked.status_code == 200, linked.text

        exported = client.get(f"/api/v1/courses/{course_id}/export")
        assert exported.status_code == 200, exported.text
        package = exported.content

        imported = client.post(
            "/api/v1/courses/import?dry_run=false", content=package
        )
        assert imported.status_code == 200, imported.text
        new_course_id = int(imported.json()["imported"]["course_id"])
        materials = client.get(
            "/api/v1/materials", params={"course_id": new_course_id}
        ).json()
        links = [m for m in materials if m["kind"] == "link"]
        assert len(links) == 1
        assert links[0]["source_url"] == "https://example.com/lecture-1"
        assert links[0]["provenance"]["source"] == "link"
