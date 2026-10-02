"""User management API (identity-auth §12) through the real study app.

The auth-kit mounts `/api/v1/me/*` and `/api/v1/admin/*` via `install()`
— no study API code — so these tests exercise the endpoints against the
`StudyUserStore` / `StudySessionStore` adapters: activity counts,
promote/demote with guard rails, deactivation, reset-password,
force-logout, sessions list/revoke, self-serve password change, cascade
account delete, and §4.5 instance transition refusals.

Non-GET requests carry the `X-CSRF-Token` echo (§10); the
profile-independent `/api/v1/me` + `/api/v1/admin` paths need no
`X-Profile-Id` (§15).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from conftest import AnonymousTestClient, mint_session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.stores import StudyInstanceStore, StudyUserStore
from app.domain.models import AuditEvent as AuditEventRow
from app.domain.models import Course, Note, Profile, User

FIXTURE_PASSWORD = "fixture-password-study"
ADMIN_EMAIL = "session@study.local"
SECOND_EMAIL = "b@study.local"
PLAIN_EMAIL = "plain@study.local"
PLAIN_PASSWORD = "plain-password-1"
CHANGER_EMAIL = "changer@study.local"
CHANGER_PASSWORD = "old-password-123"
NEW_PASSWORD = "new-password-456"
GONER_EMAIL = "goner@study.local"
GONER_PASSWORD = "goner-password-1"
ADMIN_KEYS = {"id", "email", "full_name", "is_admin", "is_active", "created_at", "activity_count"}
SESSION_KEYS = {"id", "client_label", "created_at", "expires_at", "revoked_at", "current"}


def echo(client: TestClient) -> dict[str, str]:
    """CSRF double-submit echo (§10) for either client flavour: jar
    clients expose the `nx_csrf` cookie, minted sessions travel as a
    default `X-CSRF-Token` header."""
    jar_token = client.cookies.get("nx_csrf")
    if jar_token:
        return {"X-CSRF-Token": jar_token}
    return {"X-CSRF-Token": str(client.headers.get("X-CSRF-Token"))}


def audit_actions(app: FastAPI) -> set[str]:
    with app.state.session_factory() as session:
        return {row.action for row in session.scalars(select(AuditEventRow))}


def user_id_by_email(client: TestClient, email: str) -> str:
    listed = client.get("/api/v1/admin/users")
    assert listed.status_code == 200
    rows = {row["email"]: row for row in listed.json()}
    return str(rows[email]["id"])


def register_plain(app: FastAPI) -> TestClient:
    plain = AnonymousTestClient(app)
    created = plain.post(
        "/api/v1/auth/register", json={"email": PLAIN_EMAIL, "password": PLAIN_PASSWORD}
    )
    assert created.status_code == 201
    return plain


@pytest.mark.contract  # §18.7 — non-admin on /admin/users ⇒ 403
def test_admin_users_list_merges_activity_counts(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    factory = app.state.session_factory
    _cookie, _csrf, other_profile = mint_session(app, email=SECOND_EMAIL)
    admin_profile = str(client.headers["X-Profile-Id"])
    with factory() as session:
        course = Course(profile_id=admin_profile, title="Alpha course")
        session.add(course)
        session.flush()
        session.add(Note(profile_id=admin_profile, course_id=course.id, title="n", body=[]))
        session.add(Course(profile_id=admin_profile, title="Second course"))
        session.add(Course(profile_id=other_profile, title="Beta course"))
        session.commit()
    listed = client.get("/api/v1/admin/users")
    assert listed.status_code == 200
    rows = {row["email"]: row for row in listed.json()}
    assert set(rows) == {ADMIN_EMAIL, SECOND_EMAIL}
    for row in rows.values():
        assert set(row) == ADMIN_KEYS
        assert row["created_at"] is not None
    assert rows[ADMIN_EMAIL]["activity_count"] == 3  # 2 courses + 1 note
    assert rows[ADMIN_EMAIL]["is_admin"] is True
    assert rows[SECOND_EMAIL]["activity_count"] == 1
    # profile-independent admin path works with no X-Profile-Id (§15)
    plain = register_plain(app)
    assert plain.get("/api/v1/admin/users").status_code == 403


@pytest.mark.contract  # §18.7 — last-admin guard rails hold
def test_admin_promote_demote_and_guard_rails(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    plain = register_plain(app)
    mint_session(app, email=SECOND_EMAIL)
    admin_id = user_id_by_email(client, ADMIN_EMAIL)
    second_id = user_id_by_email(client, SECOND_EMAIL)
    plain_id = user_id_by_email(client, PLAIN_EMAIL)
    # unknown targets hide existence (§7)
    unknown = client.patch(
        f"/api/v1/admin/users/{uuid4()}",
        json={"is_active": False},
        headers=echo(client),
    )
    assert unknown.status_code == 404
    # no self-demotion, no self-deactivation (§12)
    for payload in ({"is_admin": False}, {"is_active": False}):
        denied = client.patch(f"/api/v1/admin/users/{admin_id}", json=payload, headers=echo(client))
        assert denied.status_code == 403
    # promote a plain user — effective change kills their tokens (`ver`)
    promoted = client.patch(
        f"/api/v1/admin/users/{plain_id}",
        json={"is_admin": True},
        headers=echo(client),
    )
    assert promoted.status_code == 200
    assert promoted.json()["is_admin"] is True
    assert set(promoted.json()) == ADMIN_KEYS
    assert plain.get("/api/v1/auth/me").status_code == 401
    # demote the other admin (two admins — not the last one)
    demoted = client.patch(
        f"/api/v1/admin/users/{second_id}",
        json={"is_admin": False},
        headers=echo(client),
    )
    assert demoted.status_code == 200
    assert demoted.json()["is_admin"] is False
    # the caller is now the last admin: never removable (§12 guard rails)
    for payload in ({"is_admin": False}, {"is_active": False}):
        denied = client.patch(f"/api/v1/admin/users/{admin_id}", json=payload, headers=echo(client))
        assert denied.status_code == 403
    row = {r["id"]: r for r in client.get("/api/v1/admin/users").json()}[admin_id]
    assert row["is_admin"] is True and row["is_active"] is True
    assert "admin.user_update" in audit_actions(app)


@pytest.mark.contract  # §18.9 — is_active=false ⇒ 401 on the next request
def test_admin_disable_user_next_request_401(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    cookie, csrf, _profile = mint_session(app, email=SECOND_EMAIL)
    second = AnonymousTestClient(app, headers={"Cookie": cookie, "X-CSRF-Token": csrf})
    assert second.get("/api/v1/auth/me").status_code == 200
    second_id = user_id_by_email(client, SECOND_EMAIL)
    disabled = client.patch(
        f"/api/v1/admin/users/{second_id}",
        json={"is_active": False},
        headers=echo(client),
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    # is_active=false ⇒ 401 everywhere (§18.9)
    assert second.get("/api/v1/auth/me").status_code == 401


def test_admin_reset_password(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    cookie, csrf, _profile = mint_session(app, email=SECOND_EMAIL)
    second = AnonymousTestClient(app, headers={"Cookie": cookie, "X-CSRF-Token": csrf})
    second_id = user_id_by_email(client, SECOND_EMAIL)
    unknown = client.post(
        f"/api/v1/admin/users/{uuid4()}/reset-password",
        json={"new_password": NEW_PASSWORD},
        headers=echo(client),
    )
    assert unknown.status_code == 404
    short = client.post(
        f"/api/v1/admin/users/{second_id}/reset-password",
        json={"new_password": "short"},
        headers=echo(client),
    )
    assert short.status_code == 422
    done = client.post(
        f"/api/v1/admin/users/{second_id}/reset-password",
        json={"new_password": NEW_PASSWORD},
        headers=echo(client),
    )
    assert done.status_code == 204
    # the reset bumped `ver`: the minted session is dead
    assert second.get("/api/v1/auth/me").status_code == 401
    # old password fails afterwards, the new one works
    fresh = AnonymousTestClient(app)
    old_login = fresh.post(
        "/api/v1/auth/login",
        json={"email": SECOND_EMAIL, "password": FIXTURE_PASSWORD},
    )
    assert old_login.status_code == 401
    new_login = fresh.post(
        "/api/v1/auth/login", json={"email": SECOND_EMAIL, "password": NEW_PASSWORD}
    )
    assert new_login.status_code == 200
    assert "admin.password_reset" in audit_actions(app)


def test_admin_force_logout_kills_target_session(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    cookie, csrf, _profile = mint_session(app, email=SECOND_EMAIL)
    second = AnonymousTestClient(app, headers={"Cookie": cookie, "X-CSRF-Token": csrf})
    assert second.get("/api/v1/auth/me").status_code == 200
    second_id = user_id_by_email(client, SECOND_EMAIL)
    unknown = client.post(f"/api/v1/admin/users/{uuid4()}/force-logout", headers=echo(client))
    assert unknown.status_code == 404
    done = client.post(f"/api/v1/admin/users/{second_id}/force-logout", headers=echo(client))
    assert done.status_code == 204
    assert second.get("/api/v1/auth/me").status_code == 401
    assert "admin.force_logout" in audit_actions(app)


def test_me_sessions_list_revoke_other_and_current(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    first = AnonymousTestClient(app)
    created = first.post(
        "/api/v1/auth/register",
        json={"email": CHANGER_EMAIL, "password": CHANGER_PASSWORD},
    )
    assert created.status_code == 201
    second = AnonymousTestClient(app)
    assert (
        second.post(
            "/api/v1/auth/login",
            json={"email": CHANGER_EMAIL, "password": CHANGER_PASSWORD},
        ).status_code
        == 200
    )
    listed = first.get("/api/v1/me/sessions")
    assert listed.status_code == 200
    rows: list[dict[str, Any]] = listed.json()
    assert len(rows) == 2
    for row in rows:
        assert set(row) == SESSION_KEYS
        assert row["created_at"] is not None
    assert sum(1 for row in rows if row["current"]) == 1
    # foreign + unknown families hide behind 404 (§7)
    solo = AnonymousTestClient(app)
    assert (
        solo.post(
            "/api/v1/auth/register", json={"email": GONER_EMAIL, "password": GONER_PASSWORD}
        ).status_code
        == 201
    )
    solo_rows = solo.get("/api/v1/me/sessions").json()
    hidden = first.request(
        "DELETE", f"/api/v1/me/sessions/{solo_rows[0]['id']}", json={}, headers=echo(first)
    )
    assert hidden.status_code == 404
    unknown = first.request(
        "DELETE", f"/api/v1/me/sessions/{uuid4()}", json={}, headers=echo(first)
    )
    assert unknown.status_code == 404
    # revoke the other device's family
    other = next(row for row in rows if not row["current"])
    revoked = first.request(
        "DELETE", f"/api/v1/me/sessions/{other['id']}", json={}, headers=echo(first)
    )
    assert revoked.status_code == 204
    assert second.get("/api/v1/auth/me").status_code == 200  # access lives (§5)
    # … and the caller's own family, which clears the cookies
    current = next(row for row in rows if row["current"])
    revoked_current = first.request(
        "DELETE",
        f"/api/v1/me/sessions/{current['id']}",
        json={},
        headers=echo(first),
    )
    assert revoked_current.status_code == 204
    assert first.cookies.get("nx_access") is None
    assert first.get("/api/v1/auth/me").status_code == 401


def test_me_password_change_kills_other_sessions(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    first = AnonymousTestClient(app)
    assert (
        first.post(
            "/api/v1/auth/register",
            json={"email": CHANGER_EMAIL, "password": CHANGER_PASSWORD},
        ).status_code
        == 201
    )
    second = AnonymousTestClient(app)
    assert (
        second.post(
            "/api/v1/auth/login",
            json={"email": CHANGER_EMAIL, "password": CHANGER_PASSWORD},
        ).status_code
        == 200
    )
    wrong = first.patch(
        "/api/v1/me/password",
        json={"current_password": "wrong-password-999", "new_password": NEW_PASSWORD},
        headers=echo(first),
    )
    assert wrong.status_code == 403
    short = first.patch(
        "/api/v1/me/password",
        json={"current_password": CHANGER_PASSWORD, "new_password": "short"},
        headers=echo(first),
    )
    assert short.status_code == 422
    changed = first.patch(
        "/api/v1/me/password",
        json={"current_password": CHANGER_PASSWORD, "new_password": NEW_PASSWORD},
        headers=echo(first),
    )
    assert changed.status_code == 200
    # the caller stays signed in on the fresh cookies …
    assert first.get("/api/v1/auth/me").status_code == 200
    # … while every other session died with the `ver` bump
    assert second.get("/api/v1/auth/me").status_code == 401
    fresh = AnonymousTestClient(app)
    assert (
        fresh.post(
            "/api/v1/auth/login",
            json={"email": CHANGER_EMAIL, "password": CHANGER_PASSWORD},
        ).status_code
        == 401
    )
    assert (
        fresh.post(
            "/api/v1/auth/login", json={"email": CHANGER_EMAIL, "password": NEW_PASSWORD}
        ).status_code
        == 200
    )
    assert "auth.password_change" in audit_actions(app)


@pytest.mark.contract  # §18.9 — account deletion cascades fully
def test_delete_me_cascades_profiles_and_content(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    factory = app.state.session_factory
    deleter = AnonymousTestClient(app)
    created = deleter.post(
        "/api/v1/auth/register",
        json={"email": GONER_EMAIL, "password": GONER_PASSWORD},
    )
    assert created.status_code == 201
    goner_id = str(created.json()["id"])
    profiles = deleter.get("/api/v1/profiles")
    assert profiles.status_code == 200
    profile_id = str(profiles.json()[0]["id"])
    with factory() as session:
        session.add(Course(profile_id=profile_id, title="Doomed course"))
        session.commit()
    denied = deleter.request(
        "DELETE",
        "/api/v1/me",
        json={"password": "wrong-password-999"},
        headers=echo(deleter),
    )
    assert denied.status_code == 403
    deleted = deleter.request(
        "DELETE",
        "/api/v1/me",
        json={"password": GONER_PASSWORD},
        headers=echo(deleter),
    )
    assert deleted.status_code == 204
    assert deleter.cookies.get("nx_access") is None
    with factory() as session:
        assert session.get(User, goner_id) is None
        assert session.scalars(select(Profile).where(Profile.user_id == goner_id)).all() == []
        assert session.scalars(select(Course).where(Course.profile_id == profile_id)).all() == []
    # the admin account is untouched
    assert client.get("/api/v1/auth/me").status_code == 200
    assert "auth.account_delete" in audit_actions(app)


@pytest.mark.contract  # §18.6 — server instance refuses to run open
def test_admin_instance_server_refuses_open(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    plain = register_plain(app)
    # non-admins never reach the endpoint (require_admin)
    assert (
        plain.patch(
            "/api/v1/admin/instance",
            json={"auth_mode": "open", "password": PLAIN_PASSWORD},
            headers=echo(plain),
        ).status_code
        == 403
    )
    wrong = client.patch(
        "/api/v1/admin/instance",
        json={"auth_mode": "open", "password": "wrong-password-999"},
        headers=echo(client),
    )
    assert wrong.status_code == 403
    assert wrong.json()["detail"] == "Invalid password"
    # a server entrypoint never runs `open` (§4.4)
    refused = client.patch(
        "/api/v1/admin/instance",
        json={"auth_mode": "open", "password": FIXTURE_PASSWORD},
        headers=echo(client),
    )
    assert refused.status_code == 403
    # same-mode request is a no-op that reports the instance state
    state = client.patch(
        "/api/v1/admin/instance",
        json={"auth_mode": "authenticated", "password": FIXTURE_PASSWORD},
        headers=echo(client),
    )
    assert state.status_code == 200
    assert state.json() == {"auth_mode": "authenticated", "demo_mode": False}


@pytest.mark.contract  # §18.6 — authenticated→open refused (other users / wrong password)
def test_admin_instance_transition_refusal_paths(desktop_client: TestClient) -> None:
    app = desktop_client.app
    assert isinstance(app, FastAPI)
    factory = app.state.session_factory
    plain = AnonymousTestClient(app, headers={"X-Shell-Token": "test-shell-secret"})
    # §11.3: an open instance mounts no self-signup — /register answers 404
    # there and 201 once the instance is authenticated.
    assert (
        plain.post(
            "/api/v1/auth/register", json={"email": PLAIN_EMAIL, "password": PLAIN_PASSWORD}
        ).status_code
        == 404
    )
    wrong = desktop_client.patch(
        "/api/v1/admin/instance",
        json={"auth_mode": "authenticated", "password": "wrong-password-999"},
        headers=echo(desktop_client),
    )
    assert wrong.status_code == 403
    # open → authenticated with the owner's credentials already set
    flipped = desktop_client.patch(
        "/api/v1/admin/instance",
        json={"auth_mode": "authenticated", "password": FIXTURE_PASSWORD},
        headers=echo(desktop_client),
    )
    assert flipped.status_code == 200
    assert flipped.json() == {"auth_mode": "authenticated", "demo_mode": False}
    assert StudyInstanceStore(factory).get("auth_mode") == "authenticated"
    assert (
        plain.post(
            "/api/v1/auth/register", json={"email": PLAIN_EMAIL, "password": PLAIN_PASSWORD}
        ).status_code
        == 201
    )
    # authenticated → open is refused while other user rows exist (§4.5)
    refused = desktop_client.patch(
        "/api/v1/admin/instance",
        json={"auth_mode": "open", "password": FIXTURE_PASSWORD},
        headers=echo(desktop_client),
    )
    assert refused.status_code == 403
    assert "other user accounts exist" in refused.json()["detail"]
    assert StudyInstanceStore(factory).get("auth_mode") == "authenticated"
    assert "admin.instance_transition" in audit_actions(app)


@pytest.mark.contract  # §18.5 — CSRF enforced on cookie-authenticated POSTs
def test_me_admin_require_session_and_csrf(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    anonymous = AnonymousTestClient(app)
    assert anonymous.get("/api/v1/me/sessions").status_code == 401
    assert anonymous.get("/api/v1/admin/users").status_code == 401
    # cookie-authenticated non-GET without the double-submit echo (§10)
    missing = client.patch(
        "/api/v1/me/password",
        json={"current_password": FIXTURE_PASSWORD, "new_password": NEW_PASSWORD},
        headers={"X-CSRF-Token": ""},
    )
    assert missing.status_code == 403
    # the user store adapter backs the admin surface
    assert isinstance(StudyUserStore(app.state.session_factory).count_admins(), int)
