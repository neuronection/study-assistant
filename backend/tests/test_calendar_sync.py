"""Cloud calendar links: mapping, custody and sync (ADR-0052 / plan 52).

Provider calls are faked at the transport seam — no network, no real token.
The shared engine's own fixtures run in dev; these tests pin study's host
contract: plan-item mapping, pull acceptance, idempotency and credential
custody.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace as dc_replace
from datetime import date
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import CalendarEventLink, CalendarLink, PlanItem
from app.extensions.cloud import cloud_calendar as cc
from app.services.study import calendar_sync as service


class FakeTransport:
    writable = True

    def __init__(self, events: list[cc.CalendarEvent] | None = None) -> None:
        self.events = list(events or [])
        self.put: list[cc.CalendarEvent] = []
        self.deleted: list[cc.CalendarEvent] = []
        self._counter = 0

    async def list_events(
        self,
        start: date,
        end: date,
        *,
        page_token: str | None = None,
        sync_token: str | None = None,
    ) -> cc.CalendarPage:
        return cc.CalendarPage(events=list(self.events))

    async def put_event(self, event: cc.CalendarEvent) -> cc.CalendarEvent:
        self._counter += 1
        written = dc_replace(
            event,
            uid=event.remote_id or f"remote-{self._counter}",
            remote_id=event.remote_id or f"remote-{self._counter}",
            etag=f"etag-{self._counter}",
        )
        self.put.append(written)
        return written

    async def delete_event(self, event: cc.CalendarEvent) -> None:
        self.deleted.append(event)

    async def aclose(self) -> None:
        return


class _NoopClient:
    async def aclose(self) -> None:
        return


def _course(client: TestClient, title: str = "Physiology") -> str:
    response = client.post("/api/v1/courses", json={"title": title})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _item(client: TestClient, course_id: str, *, title: str, due: str, kind: str) -> str:
    response = client.post(
        f"/api/v1/courses/{course_id}/plan",
        json={"title": title, "due_date": due, "kind": kind},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _link(client: TestClient, course_id: str, **overrides: Any) -> dict[str, Any]:
    body = {
        "course_id": course_id,
        "provider": "caldav",
        "label": "University calendar",
        "direction": "push",
        "base_url": "https://cloud.example.com",
        "calendar_url": "https://cloud.example.com/cal/study/",
        "username": "ilias",
        "secret": "app-password-value",
    }
    body.update(overrides)
    response = client.post("/api/v1/calendar/links", json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


def _sync(client: TestClient, link_id: str) -> dict[str, Any]:
    response = client.post(f"/api/v1/calendar/links/{link_id}/sync")
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_catalog_lists_calendar_providers(client: TestClient) -> None:
    with client:
        response = client.get("/api/v1/calendar/providers")
        assert response.status_code == 200
        payload = response.json()
        ids = {row["id"] for row in payload["providers"]}
        assert {"google", "microsoft", "nextcloud", "caldav", "ics"} <= ids
        assert "keyring" in payload["secret_disclosure"]
        google = next(row for row in payload["providers"] if row["id"] == "google")
        assert google["auth_kinds"] == ["oauth2"]
        assert any("calendar.readonly" in scope for scope in google["scope_presets"]["read"])


def test_credentials_never_enter_the_row_or_response(
    client: TestClient, db_session: Session
) -> None:
    with client:
        course_id = _course(client)
        link = _link(client, course_id)
        assert "app-password-value" not in str(link)
        assert link["secret_configured"] is True
        db_session.expire_all()
        row = db_session.get(CalendarLink, link["id"])
        assert row is not None
        assert row.secret_ref == f"calendar:{link['id']}:password"
        assert "app-password-value" not in str(row.__dict__)


def test_guarded_client_denies_a_host_outside_the_catalog() -> None:
    """A Google binding may only reach the catalog's declared domains."""
    link = type("Link", (), {"provider": "google", "base_url": None, "calendar_url": None})()
    client = service._guarded_client(link, service.provider("google"), timeout=1.0)

    async def run() -> None:
        try:
            await client.get("https://evil.example/steal")
        finally:
            await client.aclose()

    with pytest.raises(service.CalendarSyncError) as error:
        asyncio.run(run())
    assert error.value.code == "net-denied"


def test_oauth_start_returns_the_api_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The service payload is the API schema (snake_case), not JS casing.

    Regression: an early draft returned ``authorizeUrl``/``redirectUri`` and
    FastAPI rejected the response before the browser ever opened.
    """
    monkeypatch.setenv("SA_GOOGLE_CLIENT_ID", "test-client-id")
    with client:
        course_id = _course(client)
        response = client.post(
            "/api/v1/calendar/links",
            json={
                "course_id": course_id,
                "provider": "google",
                "label": "Google calendar",
                "direction": "push",
            },
        )
        assert response.status_code == 201, response.text
        link_id = response.json()["id"]
        started = client.post(f"/api/v1/calendar/links/{link_id}/oauth/start")
        assert started.status_code == 200, started.text
        payload = started.json()
        assert payload["authorize_url"].startswith("https://accounts.google.com/")
        assert payload["redirect_uri"].startswith("http://127.0.0.1:")
        assert payload["state"]


def test_private_ics_url_is_a_keyring_secret(client: TestClient, db_session: Session) -> None:
    """A private feed URL carries a bearer token; it never lands in the row."""
    with client:
        course_id = _course(client)
        response = client.post(
            "/api/v1/calendar/links",
            json={
                "course_id": course_id,
                "provider": "ics",
                "label": "Private feed",
                "direction": "pull",
                "calendar_url": "https://feed.example/private.ics?token=top-secret-token",
            },
        )
        assert response.status_code == 201, response.text
        link = response.json()
        assert "top-secret-token" not in str(link)
        assert link["auth_kind"] == "token"
        assert link["calendar_url"] == "https://feed.example/private.ics"

        db_session.expire_all()
        row = db_session.get(CalendarLink, link["id"])
        assert row is not None
        assert "top-secret-token" not in str(row.calendar_url)
        assert row.secret_ref == f"calendar:{link['id']}:token"

        from app.core import secrets as secret_store

        # C4 custody: the FULL URL (token included) lives only in the keyring;
        # the row keeps scheme + host + path.
        assert (
            secret_store.get_secret(row.secret_ref)
            == "https://feed.example/private.ics?token=top-secret-token"
        )

        provider_row = service.provider("ics")
        transport = service._transport(row, provider_row, _NoopClient())  # type: ignore[arg-type]
        assert isinstance(transport, cc.IcsCalendarTransport)
        assert transport.url.endswith("?token=top-secret-token")


def test_push_maps_exam_and_is_idempotent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    with client:
        course_id = _course(client)
        item_id = _item(client, course_id, title="Midterm exam", due="2026-11-20", kind="exam")
        link = _link(client, course_id)
        fake = FakeTransport()
        monkeypatch.setattr(service, "_transport", lambda *args: fake)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _NoopClient())

        first = _sync(client, link["id"])
        assert first["status"] == "ok", first
        assert first["created_remote"] == 1
        assert len(fake.put) == 1
        pushed = fake.put[0]
        assert pushed.all_day is True
        assert pushed.start == date(2026, 11, 20)
        assert pushed.end == date(2026, 11, 21)  # canonical all-day end is exclusive
        assert pushed.categories == ("NEURONECTION", "EXAM")  # E8: marker + kind
        assert pushed.summary == "Midterm exam"

        db_session.expire_all()
        item = db_session.get(PlanItem, item_id)
        assert item is not None
        assert item.external_uid == pushed.uid

        second = _sync(client, link["id"])
        assert second["created_remote"] == 0
        assert len(fake.put) == 1  # no duplicate write


def test_course_exam_date_projects_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    with client:
        course_id = _course(client, "Organic Chemistry")
        client.patch(f"/api/v1/courses/{course_id}", json={"exam_date": "2026-12-15"})
        link = _link(client, course_id)
        fake = FakeTransport()
        monkeypatch.setattr(service, "_transport", lambda *args: fake)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _NoopClient())

        first = _sync(client, link["id"])
        assert first["created_remote"] == 1
        assert fake.put[0].summary == "Exam: Organic Chemistry"
        assert fake.put[0].categories == ("EXAM",)
        assert fake.put[0].start == date(2026, 12, 15)

        second = _sync(client, link["id"])
        assert second["created_remote"] == 0


def test_pull_only_accepts_study_events(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    with client:
        course_id = _course(client)
        # E8: attributable — carries the family marker.
        marked = cc.CalendarEvent(
            uid="remote-exam",
            start=date(2026, 11, 30),
            end=date(2026, 12, 1),
            all_day=True,
            summary="Final exam",
            categories=("NEURONECTION", "EXAM"),
            remote_id="remote-exam",
        )
        # Bare EXAM category, no marker — a USER must have picked this
        # category on the link; by default it is only a suggestion.
        bare = cc.CalendarEvent(
            uid="remote-bare",
            start=date(2026, 11, 28),
            end=date(2026, 11, 29),
            all_day=True,
            summary="Midterm",
            categories=("EXAM",),
            remote_id="remote-bare",
        )
        personal = cc.CalendarEvent(
            uid="remote-dentist",
            start=date(2026, 11, 25),
            end=date(2026, 11, 26),
            all_day=True,
            summary="Dentist",
            remote_id="remote-dentist",
        )
        link = _link(client, course_id, direction="pull")
        fake = FakeTransport([marked, bare, personal])
        monkeypatch.setattr(service, "_transport", lambda *args: fake)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _NoopClient())

        report = _sync(client, link["id"])
        assert report["created_local"] == 1, report
        # the bare-category event is a DRAFT suggestion, not a record
        assert report["suggested"] == 1, report

        db_session.expire_all()
        items = list(db_session.scalars(select(PlanItem).where(PlanItem.course_id == course_id)))
        by_uid = {item.external_uid: item for item in items}
        assert by_uid["remote-exam"].origin == "calendar"
        assert by_uid["remote-exam"].kind == "exam"
        assert by_uid["remote-bare"].origin == "draft"  # keep/discard, never silent
        assert "remote-dentist" not in by_uid  # personal calendar is never imported

        again = _sync(client, link["id"])
        assert again["created_local"] == 0
        assert again["suggested"] == 0  # idempotent, no duplicate suggestions


def test_keyword_lookalike_is_a_suggestion_not_a_record(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    """A title that merely looks like an exam never becomes a record (E8)."""
    with client:
        course_id = _course(client)
        lookalike = cc.CalendarEvent(
            uid="remote-test",
            start=date(2026, 11, 26),
            end=date(2026, 11, 27),
            all_day=True,
            summary="Test the projector",
            remote_id="remote-test",
        )
        link = _link(client, course_id, direction="pull")
        fake = FakeTransport([lookalike])
        monkeypatch.setattr(service, "_transport", lambda *args: fake)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _NoopClient())

        report = _sync(client, link["id"])
        assert report["created_local"] == 0, report
        assert report["suggested"] == 1, report

        db_session.expire_all()
        items = list(db_session.scalars(select(PlanItem).where(PlanItem.course_id == course_id)))
        assert len(items) == 1
        assert items[0].origin == "draft"
        assert items[0].title == "Test the projector"


def test_marker_category_round_trips_attribution(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What we push is attributable when it comes back (E8 storage)."""
    with client:
        course_id = _course(client)
        item_id = _item(client, course_id, title="Midterm exam", due="2026-11-20", kind="exam")
        link = _link(client, course_id)
        fake = FakeTransport()
        monkeypatch.setattr(service, "_transport", lambda *args: fake)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _NoopClient())
        _sync(client, link["id"])

        pushed = fake.put[0]
        assert "NEURONECTION" in pushed.categories
        assert cc.is_attributable(pushed, namespaces=("study:",)) is True
        # a foreign event with no marker is not attributable
        foreign = cc.CalendarEvent(
            uid="f1",
            start=date(2026, 11, 2),
            end=date(2026, 11, 3),
            all_day=True,
            summary="Exam",
        )
        assert cc.is_attributable(foreign, namespaces=("study:",)) is False
        assert item_id  # the projection that produced it


def test_accept_categories_is_an_explicit_user_pick(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    """Listing categories on the link is user attribution — it accepts."""
    with client:
        course_id = _course(client)
        bare = cc.CalendarEvent(
            uid="remote-bare",
            start=date(2026, 11, 28),
            end=date(2026, 11, 29),
            all_day=True,
            summary="Midterm",
            categories=("EXAM",),
            remote_id="remote-bare",
        )
        link = _link(
            client,
            course_id,
            direction="pull",
            options={"acceptCategories": ["EXAM"]},
        )
        fake = FakeTransport([bare])
        monkeypatch.setattr(service, "_transport", lambda *args: fake)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _NoopClient())

        report = _sync(client, link["id"])
        assert report["created_local"] == 1, report
        assert report["suggested"] == 0, report


def test_update_link_direction_and_disable(client: TestClient) -> None:
    with client:
        course_id = _course(client)
        link = _link(client, course_id)
        response = client.patch(
            f"/api/v1/calendar/links/{link['id']}",
            json={"direction": "two-way", "enabled": False, "label": "Renamed"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["direction"] == "two-way"
        assert body["enabled"] is False
        assert body["label"] == "Renamed"


def test_unknown_provider_is_a_typed_422(client: TestClient) -> None:
    with client:
        course_id = _course(client)
        response = client.post(
            "/api/v1/calendar/links",
            json={
                "course_id": course_id,
                "provider": "not-a-provider",
                "label": "nope",
                "direction": "push",
            },
        )
        assert response.status_code == 422
        assert "invalid" in response.json()["detail"]


def test_reconcile_link_rows_carry_no_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    with client:
        course_id = _course(client)
        _item(client, course_id, title="Essay", due="2026-11-10", kind="deadline")
        link = _link(client, course_id)
        fake = FakeTransport()
        monkeypatch.setattr(service, "_transport", lambda *args: fake)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _NoopClient())
        _sync(client, link["id"])
        db_session.expire_all()
        rows = list(db_session.scalars(select(CalendarEventLink)))
        assert len(rows) == 1
        assert rows[0].uid.startswith("remote-")
        assert "app-password-value" not in str(rows[0].__dict__)


def test_delete_link_wipes_the_secret(client: TestClient) -> None:
    from app.core import secrets as secret_store

    with client:
        course_id = _course(client)
        link = _link(client, course_id)
        assert secret_store.get_secret(f"calendar:{link['id']}:password") == "app-password-value"
        response = client.delete(f"/api/v1/calendar/links/{link['id']}")
        assert response.status_code == 204
        assert secret_store.get_secret(f"calendar:{link['id']}:password") is None


# ---------------------------------------------------------------------------
# Contract-law pins on the host side (plan 52 §10 E3/E4/E5, §9 C4)
# ---------------------------------------------------------------------------


def _linked_row(db_session: Session) -> CalendarEventLink:
    rows = list(db_session.scalars(select(CalendarEventLink)))
    assert len(rows) == 1
    return rows[0]


def test_link_row_pins_each_side_separately(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    """E3: the identity map carries local_hash AND remote_hash pins."""
    with client:
        course_id = _course(client)
        _item(client, course_id, title="Midterm exam", due="2026-11-20", kind="exam")
        link = _link(client, course_id)
        fake = FakeTransport()
        monkeypatch.setattr(service, "_transport", lambda *args: fake)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _NoopClient())

        first = _sync(client, link["id"])
        assert first["created_remote"] == 1
        db_session.expire_all()
        row = _linked_row(db_session)
        assert row.local_hash is not None
        assert row.remote_hash is not None
        assert row.local_hash == row.remote_hash == cc.event_hash(fake.put[0])

        # Steady state: the provider still serves what we pushed and nothing
        # changed anywhere -> skipped, no rewrite.
        fake.events = [fake.put[0]]
        before = (row.local_hash, row.remote_hash, row.updated_at)
        second = _sync(client, link["id"])
        assert second["created_remote"] == 0
        assert second["updated_remote"] == 0
        assert second["skipped"] >= 1
        db_session.expire_all()
        row = _linked_row(db_session)
        assert (row.local_hash, row.remote_hash, row.updated_at) == before


def test_conflict_default_is_skip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    """C2/E4: both sides changed with the default policy -> conflict surfaced,
    no clock-based winner, no remote write."""
    from datetime import UTC, datetime

    with client:
        course_id = _course(client)
        item_id = _item(client, course_id, title="Midterm exam", due="2026-11-20", kind="exam")
        link = _link(client, course_id)
        fake = FakeTransport()
        monkeypatch.setattr(service, "_transport", lambda *args: fake)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _NoopClient())

        _sync(client, link["id"])
        db_session.expire_all()
        row = _linked_row(db_session)
        pinned = (row.local_hash, row.remote_hash)

        # Both sides drift: the local title changes AND the provider returns a
        # rewritten event under the same uid.
        item = db_session.get(PlanItem, item_id)
        assert item is not None
        item.title = "Midterm exam (room B)"
        item.updated_at = datetime.now(UTC)
        db_session.commit()
        drifted = dc_replace(fake.put[0], summary="Moved by hand")
        fake.events = [drifted]

        report = _sync(client, link["id"])
        assert report["conflicts"] == 1, report
        assert report["updated_remote"] == 0
        assert report["updated_local"] == 0
        assert len(fake.put) == 1  # the conflict was surfaced, not written
        db_session.expire_all()
        row = _linked_row(db_session)
        assert (row.local_hash, row.remote_hash) == pinned


def test_out_of_window_links_are_not_unlinked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    """E5: the remote list is window-bounded — an out-of-window event is
    ABSENT, not deleted. Unlinking it would resurrect duplicates."""
    from datetime import date, timedelta

    with client:
        course_id = _course(client)
        _item(
            client,
            course_id,
            title="Far-future exam",
            due=(date.today() + timedelta(days=500)).isoformat(),
            kind="exam",
        )
        link = _link(client, course_id)
        fake = FakeTransport()
        monkeypatch.setattr(service, "_transport", lambda *args: fake)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _NoopClient())

        first = _sync(client, link["id"])
        assert first["created_remote"] == 1

        # The next listing window does not contain the event at all.
        fake.events = []
        second = _sync(client, link["id"])
        assert second["unlinked"] == 0, second
        assert second["skipped"] >= 1
        assert len(fake.put) == 1  # no resurrect write either

        db_session.expire_all()
        assert _linked_row(db_session) is not None


# ---------------------------------------------------------------------------
# Calendar discovery (M1) — the bind form's picker
# ---------------------------------------------------------------------------


def test_chosen_auth_kind_is_honored(client: TestClient, db_session: Session) -> None:
    """The descriptor's auth-kind selector is law: a token bind binds as token."""
    from app.core import secrets as secret_store

    with client:
        course_id = _course(client)
        link = _link(client, course_id, auth_kind="token", username=None)
        assert link["auth_kind"] == "token"
        db_session.expire_all()
        row = db_session.get(CalendarLink, link["id"])
        assert row is not None
        assert row.secret_ref == f"calendar:{link['id']}:token"
        assert secret_store.get_secret(row.secret_ref) == "app-password-value"

        response = client.post(
            "/api/v1/calendar/links",
            json={
                "course_id": course_id,
                "provider": "caldav",
                "label": "nope",
                "auth_kind": "oauth2",  # not an auth kind of generic CalDAV
                "base_url": "https://cloud.example.com",
                "calendar_url": "https://cloud.example.com/cal/x/",
                "secret": "v",
            },
        )
        assert response.status_code == 422
        assert "not an auth kind" in response.json()["detail"]


def test_provider_rows_carry_setup_fields_and_discovery(client: TestClient) -> None:
    """Rev 4: the bind form renders from a descriptor, never a provider name."""
    with client:
        response = client.get("/api/v1/calendar/providers")
        assert response.status_code == 200
        providers = {row["id"]: row for row in response.json()["providers"]}

        google = providers["google"]
        assert google["supports_discovery"] is True
        assert [(field["key"], field["kind"]) for field in google["setup_fields"]] == [
            ("calendar", "calendar")
        ]

        caldav = providers["caldav"]
        keys = [field["key"] for field in caldav["setup_fields"]]
        assert keys == ["base_url", "username", "secret", "secret", "calendar"]
        auth_kinds = [field["auth_kind"] for field in caldav["setup_fields"]]
        assert auth_kinds == [None, "app-password", "app-password", "token", None]
        base_field = caldav["setup_fields"][0]
        assert base_field["required"] is True
        assert base_field["label_key"] == "baseUrl"

        ics = providers["ics"]
        assert ics["supports_discovery"] is False
        assert [(field["key"], field["required"]) for field in ics["setup_fields"]] == [
            ("calendar_url", True),
            ("secret", True),
        ]
        nextcloud = providers["nextcloud"]
        assert nextcloud["setup_fields"][0]["required"] is True  # baseUrlRequired
        icloud = providers["icloud"]
        assert icloud["setup_fields"][0]["required"] is False  # apiBase carries it


def test_discover_rejects_transient_oauth_and_unknown_links(client: TestClient) -> None:
    with client:
        # OAuth tokens live under a connected link only — transient discovery
        # would need a token in the request, which we never accept.
        response = client.post("/api/v1/calendar/links/discover", json={"provider": "google"})
        assert response.status_code == 422
        assert "connected link" in response.json()["detail"]

        response = client.post(
            "/api/v1/calendar/links/discover", json={"link_id": "does-not-exist"}
        )
        assert response.status_code == 404


def test_discover_calendars_via_existing_link(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The picker: one bounded, credential-free list of the account's calendars."""
    with client:
        course_id = _course(client)
        link = _link(client, course_id)  # generic caldav: app-password + base URL

        async def fake_discover(self: cc.CalDavCalendarTransport) -> list[dict[str, Any]]:
            return [
                {"id": "personal", "name": "Personal", "href": "https://cloud.example.com/cal/personal/"},
                {
                    "id": "leaky",
                    "name": "Leaky",
                    "href": "https://cloud.example.com/cal/leaky/?token=must-not-leak",
                },
            ]

        monkeypatch.setattr(
            cc.CalDavCalendarTransport, "discover_calendars", fake_discover
        )
        response = client.post(
            "/api/v1/calendar/links/discover", json={"link_id": link["id"]}
        )
        assert response.status_code == 200, response.text
        calendars = response.json()["calendars"]
        assert [row["id"] for row in calendars] == ["personal", "leaky"]
        assert calendars[0]["url"] == "https://cloud.example.com/cal/personal/"
        # C4: a query string is a bearer credential — never echoed back.
        assert "must-not-leak" not in response.text
        assert "app-password-value" not in response.text


def test_discover_google_reads_the_calendar_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Google discovery runs on the stored token set of the connected link."""
    from app.core import oauth as oauth_core

    class _Response:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "items": [
                    {"id": "primary", "summary": "Primary", "primary": True},
                    {"id": "seminar@example.com", "summary": "Seminar"},
                ]
            }

    class _DiscoverClient:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

        async def get(self, url: str, headers: dict[str, str] | None = None) -> _Response:
            self.headers = headers or {}
            assert url.endswith("/users/me/calendarList")
            return _Response()

        async def aclose(self) -> None:
            return

    captured: list[_DiscoverClient] = []

    def _fake_client(*args: Any, **kwargs: Any) -> _DiscoverClient:
        client_stub = _DiscoverClient()
        captured.append(client_stub)
        return client_stub

    with client:
        monkeypatch.setenv("SA_GOOGLE_CLIENT_ID", "test-client-id")
        course_id = _course(client)
        created = client.post(
            "/api/v1/calendar/links",
            json={
                "course_id": course_id,
                "provider": "google",
                "label": "Google calendar",
                "direction": "pull",
            },
        )
        link_id = created.json()["id"]
        oauth_core.seal_tokens(
            f"calendar:{link_id}:oauth",
            oauth_core.OAuthTokens(
                access_token="secret-access-token",
                refresh_token=None,
                token_type="Bearer",
                expires_at=None,
            ),
        )
        monkeypatch.setattr(httpx, "AsyncClient", _fake_client)

        response = client.post("/api/v1/calendar/links/discover", json={"link_id": link_id})
        assert response.status_code == 200, response.text
        calendars = response.json()["calendars"]
        assert [row["id"] for row in calendars] == ["primary", "seminar@example.com"]
        assert calendars[0]["primary"] is True
        assert captured[0].headers["Authorization"] == "Bearer secret-access-token"
        assert "secret-access-token" not in response.text


# ---------------------------------------------------------------------------
# OAuth honesty (Rev 3 E12): state is profile-bound and single-use
# ---------------------------------------------------------------------------


def _token_exchange_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "at-1",
                "refresh_token": "rt-1",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    return httpx.MockTransport(handler)


def test_oauth_state_is_profile_bound_and_single_use(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    from app.core import secrets as secret_store

    with client:
        monkeypatch.setenv("SA_GOOGLE_CLIENT_ID", "test-client-id")
        course_id = _course(client)
        created = client.post(
            "/api/v1/calendar/links",
            json={
                "course_id": course_id,
                "provider": "google",
                "label": "Google calendar",
                "direction": "push",
            },
        )
        assert created.status_code == 201, created.text
        link = db_session.get(CalendarLink, created.json()["id"])
        assert link is not None

        started = service.oauth_start(link, profile_id="profile-a")
        state = started["state"]

        # Another profile cannot complete somebody else's bind flow (E12).
        with pytest.raises(service.CalendarSyncError) as error:
            service.oauth_complete(
                db_session,
                link,
                code="code-1",
                state=state,
                profile_id="profile-b",
                transport=_token_exchange_transport(),
            )
        assert "profile" in error.value.detail
        assert secret_store.get_secret(f"calendar:{link.id}:pending") is None

        # The failed attempt consumed the flow — a replay cannot try again.
        with pytest.raises(service.CalendarSyncError) as error:
            service.oauth_complete(
                db_session,
                link,
                code="code-1",
                state=state,
                profile_id="profile-a",
                transport=_token_exchange_transport(),
            )
        assert "no OAuth flow is pending" in error.value.detail

        # A mismatching state is also consumed immediately.
        service.oauth_start(link, profile_id="profile-a")
        with pytest.raises(service.CalendarSyncError) as error:
            service.oauth_complete(
                db_session,
                link,
                code="code-1",
                state="forged-state",
                profile_id="profile-a",
                transport=_token_exchange_transport(),
            )
        assert "state mismatch" in error.value.detail
        assert secret_store.get_secret(f"calendar:{link.id}:pending") is None

        # The honest path completes once; tokens never touch the row.
        started = service.oauth_start(link, profile_id="profile-a")
        done = service.oauth_complete(
            db_session,
            link,
            code="code-2",
            state=started["state"],
            profile_id="profile-a",
            transport=_token_exchange_transport(),
        )
        assert done.status == "ok"
        assert "at-1" not in str(done.__dict__)
        assert secret_store.get_secret(f"calendar:{link.id}:pending") is None
        assert secret_store.get_secret(f"calendar:{link.id}:oauth") is not None
