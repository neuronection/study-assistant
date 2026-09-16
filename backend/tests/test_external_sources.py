import json
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.services.content.external_sources as ext
from app.domain.models import ExternalSource, MaterialSuggestion, Profile

RSS_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Math Feed</title>
<link>https://math.example/feed</link>
<description>feed</description>
<item>
  <title>Chain rule &amp; <b>basics</b></title>
  <link>https://math.example/chain-rule?utm_source=feed</link>
  <guid>chain-1</guid>
  <description>&lt;p&gt;The chain rule, &lt;script&gt;evil()&lt;/script&gt;
  explained.&lt;/p&gt;</description>
</item>
<item>
  <title>Full calculus course</title>
  <link>https://math.example/course</link>
  <guid>course-1</guid>
  <category>Course</category>
  <enclosure url="https://math.example/course.mp4" type="video/mp4" length="1"/>
</item>
</channel></rss>"""


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


@pytest.fixture()
def course_id(client: TestClient) -> int:
    with client:
        return int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )


def _create_source(client: TestClient, **overrides: object) -> dict[str, Any]:
    body: dict[str, object] = {
        "course_id": 1,
        "kind": "rss",
        "url": "https://math.example/feed",
        "label": "Math Feed",
    }
    body.update(overrides)
    response = client.post("/api/v1/external-sources", json=body)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


def test_external_source_crud_and_validation(
    client: TestClient, course_id: int
) -> None:
    with client:
        created = _create_source(client, course_id=course_id)
        assert created["kind"] == "rss"
        assert created["enabled"] is True
        assert created["options"] == {}

        listed = client.get("/api/v1/external-sources").json()
        assert [row["id"] for row in listed] == [created["id"]]

        bad_kind = client.post(
            "/api/v1/external-sources",
            json={"course_id": course_id, "kind": "instagram", "url": "https://x"},
        )
        assert bad_kind.status_code == 422

        bad_host = client.post(
            "/api/v1/external-sources",
            json={
                "course_id": course_id,
                "kind": "youtube_channel",
                "url": "https://vimeo.com/channel/x",
            },
        )
        assert bad_host.status_code == 422

        missing_query = client.post(
            "/api/v1/external-sources",
            json={
                "course_id": course_id,
                "kind": "site_search",
                "url": "https://khanacademy.org",
                "options": {},
            },
        )
        assert missing_query.status_code == 422

        short_interval = client.post(
            "/api/v1/external-sources",
            json={
                "course_id": course_id,
                "kind": "rss",
                "url": "https://math.example/other",
                "scan_interval_sec": 60,
            },
        )
        assert short_interval.status_code == 422

        patched = client.patch(
            f"/api/v1/external-sources/{created['id']}",
            json={"enabled": False, "scan_interval_sec": 3600},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["enabled"] is False
        assert patched.json()["scan_interval_sec"] == 3600

        assert (
            client.delete(f"/api/v1/external-sources/{created['id']}").status_code
            == 204
        )
        assert (
            client.delete(f"/api/v1/external-sources/{created['id']}").status_code
            == 404
        )


def test_rss_scan_lands_sanitized_suggestions(
    db_session: Session,
    client: TestClient,
    course_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch(url: str, headers: dict[str, str] | None = None) -> FakeResponse:
        return FakeResponse(200, content=RSS_FEED)

    monkeypatch.setattr(ext, "fetch_url", fake_fetch)
    with client:
        source = _create_source(client, course_id=course_id)
        stats = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert stats.status_code == 200, stats.text
        assert stats.json() == {"new": 2, "updated": 0}

        detail = client.get("/api/v1/external-sources").json()
        assert detail[0]["last_scan_error"] is None
        assert detail[0]["last_scanned_at"] is not None

    rows = list(db_session.scalars(select(MaterialSuggestion)))
    assert len(rows) == 2
    chain = next(row for row in rows if "chain" in row.url)
    assert chain.status == "suggested"
    assert chain.title == "Chain rule & basics"
    assert "<b>" not in chain.title
    assert "evil()" not in (chain.snippet or "")
    assert "explained" in (chain.snippet or "")
    assert chain.kind == "article"
    assert chain.provider == "rss:Math Feed"
    assert chain.url_norm == "https://math.example/chain-rule"
    assert chain.course_id == course_id
    course_row = next(row for row in rows if "course" in row.url)
    assert course_row.kind == "video"


def test_rss_cursor_prevents_resurfacing(
    db_session: Session,
    client: TestClient,
    course_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_feeds = iter([RSS_FEED, RSS_FEED])

    def fake_fetch(url: str, headers: dict[str, str] | None = None) -> FakeResponse:
        return FakeResponse(200, content=next(seen_feeds))

    monkeypatch.setattr(ext, "fetch_url", fake_fetch)
    with client:
        source = _create_source(client, course_id=course_id)
        first = client.post(f"/api/v1/external-sources/{source['id']}/scan").json()
        assert first["new"] == 2
        again = client.post(f"/api/v1/external-sources/{source['id']}/scan").json()
        assert again["new"] == 0
        assert again["updated"] == 0

    row = db_session.get(ExternalSource, int(source["id"]))
    assert row is not None
    assert isinstance(row.cursor, dict)
    assert "chain-1" in row.cursor["seen"]
    assert len(row.cursor["seen"]) <= ext.MAX_SEEN_IDS


def test_rss_304_short_circuits(
    client: TestClient, course_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_fetch(url: str, headers: dict[str, str] | None = None) -> FakeResponse:
        calls.append(url)
        return FakeResponse(304)

    monkeypatch.setattr(ext, "fetch_url", fake_fetch)
    with client:
        source = _create_source(client, course_id=course_id)
        stats = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert stats.status_code == 200, stats.text
    assert stats.json() == {"new": 0, "updated": 0}
    assert len(calls) == 1


def test_youtube_scan_records_video_suggestions(
    db_session: Session,
    client: TestClient,
    course_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_entries(url: str) -> list[dict[str, object]]:
        return [
            {
                "id": "vid1",
                "title": "Integration by parts",
                "duration": 754,
                "channel": "Math Academy",
            },
            {"id": "vid2", "url": "https://youtube.com/watch?v=vid2", "title": "x"},
            {"title": "no id, no url"},
        ]

    monkeypatch.setattr(ext, "extract_flat_entries", fake_entries)
    with client:
        source = _create_source(
            client,
            course_id=course_id,
            kind="youtube_playlist",
            url="https://youtube.com/playlist?list=PL123",
            label="Calc playlist",
        )
        stats = client.post(f"/api/v1/external-sources/{source['id']}/scan").json()
        assert stats["new"] == 2

    rows = list(db_session.scalars(select(MaterialSuggestion)))
    assert len(rows) == 2
    one = next(row for row in rows if "vid1" in row.url)
    assert one.url == "https://www.youtube.com/watch?v=vid1"
    assert one.kind == "video"
    assert (one.meta or {}).get("duration") == "12:34"
    assert (one.meta or {}).get("channel") == "Math Academy"
    assert one.provider == "youtube:Calc playlist"

    row = db_session.get(ExternalSource, int(source["id"]))
    assert row is not None
    assert row.cursor == {"seen": ["vid1", "vid2"]}


def test_saved_suggestion_is_never_resurfaced(
    db_session: Session,
    client: TestClient,
    course_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch(url: str, headers: dict[str, str] | None = None) -> FakeResponse:
        return FakeResponse(200, content=RSS_FEED)

    monkeypatch.setattr(ext, "fetch_url", fake_fetch)
    with client:
        saved = client.post(
            "/api/v1/discovery/suggestions",
            json={
                "provider": "web",
                "url": "https://math.example/chain-rule",
                "title": "Saved earlier",
            },
        )
        assert saved.status_code == 200
        saved_title = saved.json()["suggestion"]["title"]

        source = _create_source(client, course_id=course_id)
        stats = client.post(f"/api/v1/external-sources/{source['id']}/scan").json()
        assert stats == {"new": 1, "updated": 0}

    rows = list(db_session.scalars(select(MaterialSuggestion)))
    assert len(rows) == 2
    kept = next(row for row in rows if row.title == "Saved earlier")
    assert kept.status == "saved"
    assert kept.title == saved_title


def test_site_search_scan_uses_provider_and_site_filter(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen_queries: list[str] = []

    def fake_search(
        base_url: str, flavor: str, query: str, api_key: str
    ) -> list[dict[str, str]]:
        seen_queries.append(query)
        return [
            {
                "title": "Limits walkthrough",
                "url": "https://khanacademy.org/math/limits",
                "content": "How limits work.",
            }
        ]

    monkeypatch.setattr(ext, "_perform_site_search", fake_search)

    profile = Profile(
        name="p",
        preferences={
            "search_provider": {
                "base_url": "https://searxng.example",
                "flavor": "searxng",
            }
        },
    )
    db_session.add(profile)
    db_session.commit()

    from app.domain.models import Course

    course = Course(profile_id=int(profile.id), title="Calc")
    db_session.add(course)
    db_session.commit()

    source = ExternalSource(
        profile_id=int(profile.id),
        course_id=int(course.id),
        kind="site_search",
        url="https://khanacademy.org",
        label="Khan",
        options={"query": "calculus", "site": "khanacademy.org"},
    )
    db_session.add(source)
    db_session.commit()

    stats = ext.run_scan(db_session, source)
    assert stats == {"new": 1, "updated": 0}
    assert seen_queries == ["calculus site:khanacademy.org"]
    row = db_session.scalars(select(MaterialSuggestion)).first()
    assert row is not None
    assert row.provider == "site:khanacademy.org"
    assert row.status == "suggested"
    assert source.last_scan_error is None
    assert source.last_scanned_at is not None


def test_scan_failure_is_isolated_and_recorded(
    db_session: Session,
    client: TestClient,
    course_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_fetch(url: str, headers: dict[str, str] | None = None) -> FakeResponse:
        raise OSError("network unreachable")

    monkeypatch.setattr(ext, "fetch_url", failing_fetch)
    with client:
        source = _create_source(client, course_id=course_id)
        response = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert response.status_code == 502
        assert "network unreachable" in response.json()["detail"]

    row = db_session.get(ExternalSource, int(source["id"]))
    assert row is not None
    assert "network unreachable" in (row.last_scan_error or "")
    assert row.enabled is True


def test_course_purge_cascades_external_sources(client: TestClient) -> None:
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )
        _create_source(client, course_id=course_id)
        deleted = client.delete(
            f"/api/v1/courses/{course_id}", params={"confirmed_backup": "true"}
        )
        assert deleted.status_code == 200
        assert client.get("/api/v1/external-sources").json() == []


def test_external_sources_ride_course_bundles(client: TestClient) -> None:
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )
        _create_source(
            client,
            course_id=course_id,
            kind="youtube_channel",
            url="https://youtube.com/@3blue1brown",
            label=None,
            options={"max_items": 5},
            scan_interval_sec=3600,
        )
        export_response = client.get(f"/api/v1/courses/{course_id}/export")
        assert export_response.status_code == 200, export_response.text
        data = export_response.content

    archive = zipfile.ZipFile(BytesIO(data))
    assert "external-sources.json" in archive.namelist()
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["counts"]["external_sources"] == 1
    payload = json.loads(archive.read("external-sources.json"))
    assert payload == [
        {
            "kind": "youtube_channel",
            "url": "https://youtube.com/@3blue1brown",
            "label": None,
            "options": {"max_items": 5},
            "enabled": True,
            "scan_interval_sec": 3600,
        }
    ]


def test_bundle_import_recreates_sources_with_fresh_cursors(
    client: TestClient,
) -> None:
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )
        _create_source(client, course_id=course_id)
        export_response = client.get(f"/api/v1/courses/{course_id}/export")
        assert export_response.status_code == 200
        data = export_response.content

        imported = client.post("/api/v1/courses/import?dry_run=false", content=data)
        assert imported.status_code == 200, imported.text
        imported_course_id = imported.json()["imported"]["course_id"]
        rows = client.get(
            "/api/v1/external-sources", params={"course_id": imported_course_id}
        ).json()
        assert len(rows) == 1
        assert rows[0]["kind"] == "rss"
        assert rows[0]["url"] == "https://math.example/feed"
        assert rows[0]["last_scanned_at"] is None
        assert rows[0]["last_scan_error"] is None


def _publisher(
    sink: list[tuple[str, dict[str, object]]],
) -> Callable[[str, dict[str, object]], None]:
    def publish(topic: str, payload: dict[str, object]) -> None:
        sink.append((topic, payload))

    return publish


def _scheduler_app(tmp_path: Path) -> Any:
    from alembic.config import Config

    from alembic import command
    from app.core.config import Settings
    from app.main import create_app

    db_path = tmp_path / "extsched.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")

    settings = Settings(data_dir=tmp_path, log_level="WARNING")
    return create_app(settings)


def test_scheduler_due_logic_overlap_guard_and_error_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.platform.external_source_scheduler import ExternalSourceScheduler

    app = _scheduler_app(tmp_path)

    published: list[tuple[str, dict[str, object]]] = []
    scheduler = ExternalSourceScheduler(
        app.state.session_factory,
        _publisher(published),
        startup_delay_sec=0,
    )

    with app.state.session_factory() as session:
        profile = Profile(name="extsched")
        session.add(profile)
        session.flush()
        from app.domain.models import Course

        course = Course(profile_id=int(profile.id), title="Ext")
        session.add(course)
        session.flush()
        source = ExternalSource(
            profile_id=int(profile.id),
            course_id=int(course.id),
            kind="rss",
            url="https://broken.example/feed",
            label="Broken",
        )
        session.add(source)
        session.commit()
        source_id = int(source.id)

    def failing_fetch(url: str, headers: dict[str, str] | None = None) -> FakeResponse:
        raise OSError("network unreachable")

    monkeypatch.setattr(ext, "fetch_url", failing_fetch)

    assert scheduler._scan_one(source_id) is None
    with app.state.session_factory() as session:
        row = session.get(ExternalSource, source_id)
        assert row is not None
        assert "network unreachable" in (row.last_scan_error or "")
        assert row.enabled is True

    events = [event for _, event in published]
    assert any(event.get("event") == "scan_failed" for event in events)

    scanned_at = row.last_scanned_at
    assert scanned_at is not None
    assert scheduler.scan_all(now=scanned_at + timedelta(seconds=60)) == {}

    scheduler._in_flight.add(source_id)
    try:
        assert scheduler.scan_all(
            now=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30)
        ) == {}
    finally:
        scheduler._in_flight.discard(source_id)
