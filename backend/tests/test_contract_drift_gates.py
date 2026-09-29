"""Contract drift gates — the identity-auth §18 cases study did not yet
assert product-side (guideline §18; kit `CONTRACT_CASES` is the checklist).

The kit's own suite proves the reference implementation; these run the
same cases through study's *mounted* app (real ring, real middleware,
real adapters) so wiring drift fails here, in `pytest -m contract`.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nx_auth.cookies import cookie_names
from nx_auth.testing import assert_cookie_flags, forge_token
from nx_auth.tokens import AuthMode, TokenKind, mint_token

from app.auth.stores import StudyUserStore

PASSWORD = "correct-horse-battery"


def _kit(app: TestClient) -> Any:
    """The mounted kit instance (real ring + config) behind a test client."""
    application = app.app
    assert isinstance(application, FastAPI)
    return application.state.auth


def _names(app: TestClient) -> tuple[str, str]:
    names = cookie_names(_kit(app).config)
    return names.access, names.refresh


def _register(client: TestClient, email: str) -> str:
    created = client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


@pytest.mark.contract  # §18.1 — forged / wrong-secret / kind-mismatch ⇒ 401
def test_forged_and_kind_mismatched_tokens_rejected(raw_client: TestClient) -> None:
    kit = _kit(raw_client)
    access, _refresh = _names(raw_client)
    user_id = _register(raw_client, "forge@example.com")

    forged = forge_token(
        "wrong-key-0123456789abcdefghijklmnop",
        {"sub": user_id, "token_kind": "session"},
    )
    assert (
        raw_client.get("/api/v1/auth/me", headers={"Cookie": f"{access}={forged}"})
    ).status_code == 401

    refresh_as_access = mint_token(
        kit.ring,
        kit.config,
        kind=TokenKind.REFRESH,
        sub=user_id,
        ver=1,
        auth_mode=AuthMode.PASSWORD,
    )
    assert (
        raw_client.get(
            "/api/v1/auth/me", headers={"Cookie": f"{access}={refresh_as_access}"}
        )
    ).status_code == 401

    garbage = raw_client.get("/api/v1/auth/me", headers={"Cookie": f"{access}=not-a-jwt"})
    assert garbage.status_code == 401


@pytest.mark.contract  # §18.2 — expired access token ⇒ 401
def test_expired_access_token_is_401(raw_client: TestClient) -> None:
    kit = _kit(raw_client)
    access, _refresh = _names(raw_client)
    user_id = _register(raw_client, "expired@example.com")
    expired = mint_token(
        kit.ring,
        kit.config,
        kind=TokenKind.SESSION,
        sub=user_id,
        ver=1,
        auth_mode=AuthMode.PASSWORD,
        ttl_seconds=-60,
    )
    assert (
        raw_client.get("/api/v1/auth/me", headers={"Cookie": f"{access}={expired}"})
    ).status_code == 401


@pytest.mark.contract  # §18.3 — rotated-refresh replay ⇒ 423, family revoked, ver bump
def test_refresh_replay_revokes_family_and_bumps_ver(raw_client: TestClient) -> None:
    _access, refresh = _names(raw_client)
    user_id = _register(raw_client, "rotate@example.com")
    first = raw_client.cookies.get(refresh)
    assert first

    csrf = raw_client.cookies.get("nx_csrf")
    assert csrf
    rotated = raw_client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert rotated.status_code == 200, rotated.text

    # Replay the rotated-out refresh token (double-submit stays consistent
    # with the post-rotation jar so only the stale jti can fail this).
    csrf = raw_client.cookies.get("nx_csrf")
    assert csrf
    replay = raw_client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"{refresh}={first}; nx_csrf={csrf}", "X-CSRF-Token": csrf},
    )
    assert replay.status_code == 423

    # Family-wide sign-out: the rotated-in access cookie is dead too, and
    # the user's token_version bumped (global revocation, §8).
    assert raw_client.get("/api/v1/auth/me").status_code == 401
    application = raw_client.app
    assert isinstance(application, FastAPI)
    user = StudyUserStore(application.state.session_factory).get(user_id)
    assert user is not None and user.token_version == 2


@pytest.mark.contract  # §18.4 — lockout after N failures ⇒ 423
def test_lockout_after_threshold(raw_client: TestClient) -> None:
    _register(raw_client, "locked@example.com")
    # Anonymous logins: drop the register-issued cookies so the CSRF gate
    # (correctly) stays out of the way of the password-failure counter.
    raw_client.cookies.clear()
    for _ in range(4):
        denied = raw_client.post(
            "/api/v1/auth/login",
            json={"email": "locked@example.com", "password": "wrong-password-xx"},
        )
        assert denied.status_code == 401
    fifth = raw_client.post(
        "/api/v1/auth/login",
        json={"email": "locked@example.com", "password": "wrong-password-xx"},
    )
    assert fifth.status_code == 423
    # The unlock window itself (15 min) is asserted by the kit's suite.


@pytest.mark.contract  # §18.5 — cookie flags exactly as §10
def test_session_cookie_flags_are_exact(raw_client: TestClient) -> None:
    created = raw_client.post(
        "/api/v1/auth/register",
        json={"email": "flags@example.com", "password": PASSWORD},
    )
    assert created.status_code == 201
    lines = created.headers.get_list("set-cookie")
    assert_cookie_flags(lines, "nx_access", http_only=True, secure=False, path="/")
    assert_cookie_flags(
        lines, "nx_refresh", http_only=True, secure=False, path="/api/v1/auth"
    )
    assert_cookie_flags(lines, "nx_csrf", http_only=False, secure=False, path="/")
    same_site = next(line for line in lines if line.startswith("nx_access="))
    assert "samesite=lax" in same_site.lower()


@pytest.mark.contract  # §18.10 — generic login error, no user enumeration
def test_login_failures_are_generic(raw_client: TestClient) -> None:
    _register(raw_client, "real@example.com")
    raw_client.cookies.clear()
    wrong = raw_client.post(
        "/api/v1/auth/login", json={"email": "real@example.com", "password": "nope-nope"}
    )
    unknown = raw_client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "nope-nope"},
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


@pytest.mark.contract  # §18.12 — session token under the refresh key ⇒ rejected
def test_key_separation_wrong_signing_key(raw_client: TestClient) -> None:
    kit = _kit(raw_client)
    access, _refresh = _names(raw_client)
    user_id = _register(raw_client, "keys@example.com")
    wrong_key = mint_token(
        kit.ring,
        kit.config,
        kind=TokenKind.SESSION,
        sub=user_id,
        ver=1,
        auth_mode=AuthMode.PASSWORD,
        key=kit.ring.refresh_key,
    )
    assert (
        raw_client.get("/api/v1/auth/me", headers={"Cookie": f"{access}={wrong_key}"})
    ).status_code == 401
    # DATA_KEY never signs/verifies JWTs — asserted by the kit's suite.
