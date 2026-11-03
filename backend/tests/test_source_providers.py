"""Plan 86 source-provider framework: catalog, adapters, acceptance and degradation."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.extensions.builtin.external_sources as extconn
import app.extensions.builtin.external_sources.engine as engine
from app.core import secrets as secret_store
from app.domain.models import (
    ExternalReviewEvent,
    ExternalSource,
    FsrsState,
    Material,
    MaterialSuggestion,
)
from app.extensions.builtin.external_sources import providers as provider_catalog
from app.extensions.builtin.external_sources.adapters.anki import AnkiAdapter
from app.extensions.builtin.external_sources.adapters.google_drive import (
    GOOGLE_NATIVE_EXPORTS,
    GoogleDriveAdapter,
)
from app.extensions.builtin.external_sources.adapters.webdav import WebDavAdapter
from app.extensions.builtin.external_sources.adapters.zotero import ZoteroAdapter
from app.extensions.builtin.external_sources.providers import (
    Provider,
    ProviderCatalog,
)
from app.services.content import external_sources as ext
from app.services.platform.backup import build_backup, database_is_healthy, read_archive
from app.services.study.cards import create_card_exercise

PROPFIND_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/remote.php/dav/files/me/notes/</d:href>
    <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/me/notes/lecture.pdf</d:href>
    <d:propstat><d:prop>
      <d:getcontenttype>application/pdf</d:getcontenttype>
      <d:getcontentlength>2048</d:getcontentlength>
      <d:getlastmodified>Mon, 20 Oct 2026 10:00:00 GMT</d:getlastmodified>
      <d:getetag>"v1"</d:getetag>
    </d:prop></d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/me/notes/notes.md</d:href>
    <d:propstat><d:prop>
      <d:getcontenttype>text/markdown</d:getcontenttype>
      <d:getcontentlength>120</d:getcontentlength>
      <d:getlastmodified>Mon, 20 Oct 2026 10:05:00 GMT</d:getlastmodified>
      <d:getetag>"v2"</d:getetag>
    </d:prop></d:propstat>
  </d:response>
</d:multistatus>"""

NOTES_BLOCK = b"""  <d:response>
    <d:href>/remote.php/dav/files/me/notes/notes.md</d:href>
    <d:propstat><d:prop>
      <d:getcontenttype>text/markdown</d:getcontenttype>
      <d:getcontentlength>120</d:getcontentlength>
      <d:getlastmodified>Mon, 20 Oct 2026 10:05:00 GMT</d:getlastmodified>
      <d:getetag>"v2"</d:getetag>
    </d:prop></d:propstat>
  </d:response>
"""

RSS_WITH_ENCLOSURES = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Lectures</title>
<item>
  <title>Limits lecture</title>
  <link>https://math.example/limits</link>
  <guid>limits-1</guid>
  <enclosure url="https://math.example/limits.mp3" type="audio/mpeg" length="1024"/>
</item>
<item>
  <title>Huge recording</title>
  <link>https://math.example/huge</link>
  <guid>huge-1</guid>
  <enclosure url="https://math.example/huge.mp4" type="video/mp4" length="999999999"/>
</item>
<item>
  <title>Zip archive</title>
  <link>https://math.example/zip</link>
  <guid>zip-1</guid>
  <enclosure url="https://math.example/notes.zip" type="application/zip" length="10"/>
</item>
</channel></rss>"""


def _course(client: TestClient, title: str = "Calc") -> str:
    return str(client.post("/api/v1/courses", json={"title": title}).json()["id"])


def _create(client: TestClient, course_id: str, **body: Any) -> dict[str, Any]:
    payload = {"course_id": course_id, **body}
    response = client.post("/api/v1/external-sources", json=payload)
    assert response.status_code == 201, response.text
    return dict(response.json())


def _patch_adapter(monkeypatch: pytest.MonkeyPatch, adapter: Any) -> None:
    monkeypatch.setattr(engine, "build_adapter", lambda provider, transport=None: adapter)
    monkeypatch.setattr(ext, "build_adapter", lambda provider, transport=None: adapter)


def _capture_jobs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    captured: list[tuple[str, dict[str, Any]]] = []
    from app.jobs.runner import JobRunner

    def fake_enqueue(_session: Session, kind: Any, payload: dict[str, Any]) -> Any:
        captured.append((str(kind), dict(payload)))
        return SimpleNamespace(id="job-1")

    monkeypatch.setattr(JobRunner, "enqueue", staticmethod(fake_enqueue))
    return captured


def test_provider_catalog_is_data(client: TestClient) -> None:
    with client:
        response = client.get("/api/v1/external-sources/providers")
    assert response.status_code == 200
    payload = response.json()
    ids = [row["id"] for row in payload["providers"]]
    assert {"webdav", "google-drive", "dropbox", "onedrive", "zotero", "anki"} <= set(ids)
    assert payload["secret_disclosure"].startswith("Secret values are stored only")
    webdav = next(row for row in payload["providers"] if row["id"] == "webdav")
    assert webdav["auth_kind"] == "token"
    assert webdav["secret_slots"][0]["name"] == "password"


def test_unknown_provider_is_a_typed_registration_error(client: TestClient) -> None:
    with client:
        course_id = _course(client)
        response = client.post(
            "/api/v1/external-sources",
            json={
                "course_id": course_id,
                "provider": "not-a-provider",
                "kind": "rss",
                "url": "https://example.com/feed",
            },
        )
    assert response.status_code == 422
    assert "unknown source provider" in response.json()["detail"]


def test_a_new_provider_is_a_catalog_row_plus_adapter_no_migration(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = Provider(
        id="fake",
        label="Fake provider",
        kinds=("rss",),
        default_kind="rss",
        auth_kind="none",
        url_required=False,
        fields=("max_items",),
        supports_backup=False,
        adapter="fake",
    )
    real = provider_catalog.catalog()
    monkeypatch.setattr(
        provider_catalog,
        "catalog",
        lambda: ProviderCatalog(
            providers={**real.providers, "fake": fake_provider},
            order=(*real.order, "fake"),
            secret_disclosure="disclosure",
        ),
    )

    class FakeAdapter:
        provider_id = "fake"
        kinds = ("rss",)
        auth_kind = "none"

        def auth_probe(self, source: Any) -> str:
            return "ok"

        def changes(self, source: Any, cursor: dict[str, Any]) -> Any:
            from app.extensions.builtin.external_sources.adapters.base import (
                ChangeSet,
                RemoteEntry,
            )

            entry = RemoteEntry(
                remote_id="remote-1",
                name="lecture.pdf",
                url="https://fake.example/lecture.pdf",
                mime="application/pdf",
                size=100,
                etag="1",
            )
            return ChangeSet(upserted=[entry], vanished=[], cursor={"known": {}})

    _patch_adapter(monkeypatch, FakeAdapter())
    with client:
        course_id = _course(client)
        source = _create(
            client,
            course_id,
            provider="fake",
            kind="rss",
            url="",
        )
        assert source["provider"] == "fake"
        assert source["auth_kind"] == "none"
        scanned = client.post(f"/api/v1/external-sources/{source['id']}/scan")
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["new"] == 1


def test_webdav_scan_change_detection_and_vanished(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"body": PROPFIND_XML}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PROPFIND":
            return httpx.Response(207, content=state["body"])
        if request.method == "GET":
            return httpx.Response(200, content=b"%PDF-1.4 lecture")
        if request.method == "PUT":
            return httpx.Response(201)
        return httpx.Response(404)

    adapter = WebDavAdapter(transport=httpx.MockTransport(handler))
    _patch_adapter(monkeypatch, adapter)
    with client:
        course_id = _course(client)
        source = _create(
            client,
            course_id,
            provider="webdav",
            kind="webdav_folder",
            url="https://cloud.example/remote.php/dav/files/me/notes/",
            options={"username": "me"},
        )
        stored = client.put(
            f"/api/v1/external-sources/{source['id']}/secret",
            json={"slot": "password", "value": "app-password"},
        )
        assert stored.status_code == 200, stored.text
        assert stored.json()["secrets_configured"] == {"password": True}
        raw = secret_store.get_secret(f"source:{source['id']}:password")
        assert raw == "app-password"

        first = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert first.status_code == 200, first.text
        assert first.json()["new"] == 2
        second = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert second.json()["new"] == 0
        assert second.json()["updated"] == 0

        state["body"] = PROPFIND_XML.replace(b'"v1"', b'"v9"').replace(NOTES_BLOCK, b"")
        third = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert third.json()["updated"] == 1
        assert third.json()["missing"] == 1

    rows = list(db_session.scalars(select(MaterialSuggestion)))
    lecture = next(row for row in rows if "lecture" in row.url)
    assert lecture.kind == "paper"
    assert (lecture.meta or {}).get("material_kind") == "pdf"
    assert (lecture.meta or {}).get("source_id") == source["id"]
    vanished = next(row for row in rows if row.url.endswith("notes.md"))
    assert (vanished.meta or {}).get("remote_state") == "vanished"


def test_webdav_backup_destination_round_trip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PROPFIND":
            body = (
                b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
                b"<d:response><d:href>/dav/</d:href><d:propstat><d:prop>"
                b"<d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat>"
                b"</d:response>"
                b"<d:response><d:href>/dav/manual-20261022-120000.zip</d:href><d:propstat><d:prop>"
                b"<d:getcontentlength>4</d:getcontentlength>"
                b'<d:getetag>"v1"</d:getetag>'
                b"</d:prop></d:propstat></d:response></d:multistatus>"
            )
            return httpx.Response(207, content=body)
        if request.method == "PUT":
            name = request.url.path.rsplit("/", 1)[-1]
            remote[name] = request.content
            return httpx.Response(201)
        if request.method == "GET":
            name = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, content=remote[name])
        return httpx.Response(404)

    adapter = WebDavAdapter(transport=httpx.MockTransport(handler))
    _patch_adapter(monkeypatch, adapter)
    with client:
        course_id = _course(client)
        source = _create(
            client,
            course_id,
            provider="webdav",
            kind="webdav_folder",
            url="https://cloud.example/dav/",
            options={"username": "me"},
        )
        client.put(
            f"/api/v1/external-sources/{source['id']}/secret",
            json={"slot": "password", "value": "pw"},
        )
        listed = client.get(f"/api/v1/external-sources/{source['id']}/backups")
        assert listed.status_code == 200, listed.text
        assert listed.json()["backups"][0]["name"] == "manual-20261022-120000.zip"

    source_obj = _load_source(client, source["id"])
    settings = cast(Any, client.app).state.settings
    package = build_backup(settings.db_path, settings.blobs_dir, database_url=settings.db_url)
    result = ext.upload_backup(source_obj, "manual-20261022-120000.zip", package)
    assert result["location"].endswith("manual-20261022-120000.zip")
    fetched = ext.remote_backup_data(source_obj, "manual-20261022-120000.zip")
    database, _blobs = read_archive(fetched)
    assert database_is_healthy(database)


def _load_source(client: TestClient, source_id: str) -> ExternalSource:
    return _load_source_session(client, source_id)


def _load_source_session(client: TestClient, source_id: str) -> ExternalSource:
    state = cast(Any, client.app).state
    with state.session_factory() as session:
        row = session.get(ExternalSource, source_id)
        assert row is not None
        session.expunge(row)
        return cast(ExternalSource, row)


def test_google_drive_changes_cursor_and_export_mime(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SA_GOOGLE_CLIENT_ID", "test-client")
    calls: list[str] = []
    docx = b"PK-docx-bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        path = request.url.path
        if path.endswith("/changes/startPageToken"):
            return httpx.Response(200, json={"startPageToken": "p1"})
        if path.endswith("/changes"):
            return httpx.Response(
                200,
                json={
                    "changes": [
                        {
                            "fileId": "pdf-2",
                            "file": {
                                "id": "pdf-2",
                                "name": "week2.pdf",
                                "mimeType": "application/pdf",
                                "size": "500",
                                "modifiedTime": "2026-10-22T10:00:00Z",
                                "version": "3",
                            },
                        },
                        {"fileId": "doc-1", "removed": True},
                    ],
                    "newStartPageToken": "p2",
                },
            )
        if path.endswith("/files"):
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "id": "doc-1",
                            "name": "Syllabus",
                            "mimeType": "application/vnd.google-apps.document",
                            "modifiedTime": "2026-10-22T09:00:00Z",
                            "version": "1",
                        },
                        {
                            "id": "pdf-1",
                            "name": "week1.pdf",
                            "mimeType": "application/pdf",
                            "size": "400",
                            "modifiedTime": "2026-10-22T09:30:00Z",
                            "version": "2",
                        },
                    ]
                },
            )
        if path.endswith("/export"):
            assert request.url.params["mimeType"] == (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            return httpx.Response(200, content=docx)
        if path.endswith("/files/pdf-1"):
            return httpx.Response(200, content=b"%PDF week1")
        return httpx.Response(404)

    adapter = GoogleDriveAdapter(transport=httpx.MockTransport(handler))
    _patch_adapter(monkeypatch, adapter)
    with client:
        course_id = _course(client)
        source = _create(
            client,
            course_id,
            provider="google-drive",
            kind="cloud_folder",
            options={"folder_id": "folder-1"},
        )
        from nx_auth.oauth import TokenSet

        from app.services.study import cloud_oauth

        cloud_oauth.source_vault_for(source["id"]).seal(
            source["id"],
            TokenSet(
                access_token="access-1",
                refresh_token="refresh-1",
                expires_at=None,
                scope="https://www.googleapis.com/auth/drive.readonly",
            ),
        )
        first = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert first.status_code == 200, first.text
        assert first.json()["new"] == 2
        second = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert second.json()["new"] == 1
        assert second.json()["missing"] == 1

    entry = next(
        item
        for item in adapter.list(_load_source(client, source["id"]))
        if item.remote_id == "doc-1"
    )
    assert entry.name.endswith(".docx")
    assert (
        entry.meta["export_mime"]
        == GOOGLE_NATIVE_EXPORTS["application/vnd.google-apps.document"][0]
    )
    assert adapter.fetch(_load_source(client, source["id"]), entry) == docx

    rows = list(_suggestions(client))
    doc = next(row for row in rows if "doc-1" in json.dumps(row.meta or {}))
    assert (doc.meta or {})["material_kind"] == "docx"


def _suggestions(client: TestClient) -> list[MaterialSuggestion]:
    state = cast(Any, client.app).state
    with state.session_factory() as session:
        return list(session.scalars(select(MaterialSuggestion)))


def test_zotero_citation_suggestions(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    item = {
        "key": "ABCD1234",
        "version": 7,
        "data": {
            "itemType": "journalArticle",
            "title": "A study of limits",
            "DOI": "10.1000/xyz",
            "date": "2024-03-01",
            "creators": [
                {"firstName": "Ada", "lastName": "Lovelace"},
                {"name": "Bernhard Riemann"},
            ],
            "publicationTitle": "Journal of Calculus",
        },
        "links": {"attachment": {"href": "http://127.0.0.1:23119/attachments/ABCD1234.pdf"}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/collections/CALC/items"):
            return httpx.Response(200, json=[item])
        if request.url.path.endswith("/attachments/ABCD1234.pdf"):
            return httpx.Response(200, content=b"%PDF paper")
        return httpx.Response(404)

    adapter = ZoteroAdapter(transport=httpx.MockTransport(handler))
    _patch_adapter(monkeypatch, adapter)
    with client:
        course_id = _course(client)
        source = _create(
            client,
            course_id,
            provider="zotero",
            kind="zotero_collection",
            options={"collection": "CALC"},
        )
        scanned = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert scanned.status_code == 200, scanned.text
        assert scanned.json()["new"] == 1

    rows = list(_suggestions(client))
    row = rows[0]
    assert row.kind == "paper"
    assert row.url == "https://doi.org/10.1000/xyz"
    meta = row.meta or {}
    assert meta["authors"] == ["Ada Lovelace", "Bernhard Riemann"]
    assert meta["year"] == 2024
    assert meta["citation_kind"] == "article"
    assert meta["container"] == "Journal of Calculus"
    assert meta["material_kind"] == "pdf"


def test_anki_reviews_union_merge_and_recompute(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    reviews = {
        1001: [
            {"id": 1, "ease": 3, "ivl": 2, "lastIvl": 0, "time": 1761100000000},
            {"id": 2, "ease": 4, "ivl": 5, "lastIvl": 2, "time": 1761200000000},
        ],
        2002: [{"id": 3, "ease": 3, "ivl": 1, "lastIvl": 0, "time": 1761150000000}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        action = body["action"]
        if action == "version":
            return httpx.Response(200, json={"result": 6, "error": None})
        if action == "deckNames":
            return httpx.Response(200, json={"result": ["Calc"], "error": None})
        if action == "findCards":
            return httpx.Response(200, json={"result": [1001, 2002], "error": None})
        if action == "getReviewsOfCards":
            return httpx.Response(200, json={"result": reviews, "error": None})
        return httpx.Response(200, json={"result": None, "error": "unknown action"})

    adapter = AnkiAdapter(transport=httpx.MockTransport(handler))
    _patch_adapter(monkeypatch, adapter)
    with client:
        course_id = _course(client)
        source = _create(
            client,
            course_id,
            provider="anki",
            kind="anki_deck",
            options={"decks": ["Calc"]},
        )
        profile_id = str(client.get("/api/v1/profiles").json()[0]["id"])
        card = create_card_exercise(
            db_session,
            profile_id=profile_id,
            course_id=course_id,
            node_id=None,
            kind="card_basic",
            front=[{"type": "text", "md": "Q"}],
            back=[{"type": "text", "md": "A"}],
            source="anki_import",
            deck_ref="Calc",
            external_uid="1001",
        )
        db_session.commit()
        first = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert first.status_code == 200, first.text
        assert first.json()["new"] == 3
        assert first.json()["recomputed"] == 1
        assert first.json()["unmatched"] == 1
        second = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert second.json()["new"] == 0
        assert second.json()["unchanged"] == 3

    events = list(db_session.scalars(select(ExternalReviewEvent)))
    assert len(events) == 3
    state = db_session.scalars(select(FsrsState).where(FsrsState.card_id == card.id)).one()
    assert state.reps == 2
    assert state.last_review_at is not None


def test_closed_local_app_degrades_typed_not_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    adapter = AnkiAdapter(transport=httpx.MockTransport(handler))
    _patch_adapter(monkeypatch, adapter)
    with client:
        course_id = _course(client)
        source = _create(
            client,
            course_id,
            provider="anki",
            kind="anki_deck",
            options={"decks": ["Calc"]},
        )
        failed = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert failed.status_code == 422
        assert "needs-secret" in failed.json()["detail"]
        row = client.get("/api/v1/external-sources").json()[0]
        assert row["status"] == "degraded"
        assert row["consecutive_failures"] == 1
        client.post(f"/api/v1/external-sources/{source['id']}/scan")
        again = client.get("/api/v1/external-sources").json()[0]
        assert again["status"] == "failing"
        assert again["consecutive_failures"] == 2


def test_rss_media_enclosures_classify_and_accept(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_fetch(url: str, headers: dict[str, str] | None = None) -> Any:
        return SimpleNamespace(status_code=200, content=RSS_WITH_ENCLOSURES, headers={})

    monkeypatch.setattr(extconn, "fetch_url", fake_fetch)
    captured = _capture_jobs(monkeypatch)
    with client:
        course_id = _course(client)
        source = _create(
            client, course_id, provider="rss", kind="rss", url="https://math.example/feed"
        )
        scanned = client.post(f"/api/v1/external-sources/{source['id']}/scan")
        assert scanned.status_code == 200, scanned.text
        assert scanned.json()["new"] == 3
        rows = {row.title: row for row in _suggestions(client)}
        lecture = rows["Limits lecture"]
        assert (lecture.meta or {})["material_kind"] == "audio"
        assert (lecture.meta or {})["enclosure_url"].endswith("limits.mp3")
        assert (rows["Huge recording"].meta or {})["enclosure_oversize"] is True
        assert "enclosure_url" not in (rows["Zip archive"].meta or {})
        accepted = client.post(
            f"/api/v1/external-sources/{source['id']}/accept",
            json={"suggestion_id": lecture.id},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["job_kind"] == "url_import"

    material = db_session.scalars(select(Material)).one()
    assert material.kind == "audio"
    assert material.source_url == "https://math.example/limits.mp3"
    assert captured[-1][0] == "url_import"
    assert captured[-1][1]["action"] == "transcribe_audio"
    suggestion = db_session.get(MaterialSuggestion, lecture.id)
    assert suggestion is not None
    assert suggestion.material_id == material.id
