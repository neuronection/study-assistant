from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nx_auth import AuthConfig
from nx_auth.testing import csrf_headers, make_test_keyring
from nx_auth.tokens import AuthMode, TokenKind, mint_token
from sqlalchemy import select

from app.auth.stores import StudyInstanceStore, StudyUserStore
from app.core.config import Settings
from app.domain.models import AuditEvent as AuditEventRow
from app.main import create_app


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        **overrides,  # type: ignore[arg-type]
    )


@pytest.mark.contract  # §18.2 — login + refresh path recovers over the real adapters
def test_register_login_refresh_me_over_study_adapters(raw_client: TestClient) -> None:
    created = raw_client.post(
        "/api/v1/auth/register",
        json={"email": "First@Example.com", "password": "correct-horse-battery"},
    )
    assert created.status_code == 201
    assert created.json()["is_admin"] is True
    assert created.json()["email"] == "first@example.com"
    me = raw_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == created.json()["id"]
    rotated = raw_client.post("/api/v1/auth/refresh", headers=csrf_headers(raw_client))
    assert rotated.status_code == 200
    out = raw_client.post("/api/v1/auth/logout", headers=csrf_headers(raw_client))
    assert out.status_code == 200
    assert raw_client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.contract  # §18.6 — server entrypoint is authenticated, DB-authoritative
def test_server_instance_boots_authenticated(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    factory = app.state.session_factory
    assert StudyInstanceStore(factory).get("auth_mode") == "authenticated"


@pytest.mark.contract  # §18.6 — open desktop exchange exists only here, mints local-boot
def test_desktop_instance_boots_open_and_exchange_provisions_owner(
    desktop_client: TestClient,
) -> None:
    app = desktop_client.app
    assert isinstance(app, FastAPI)
    factory = app.state.session_factory
    assert StudyInstanceStore(factory).get("auth_mode") == "open"
    exchanged = desktop_client.post(
        "/api/v1/auth/desktop/exchange", headers={"X-Shell-Token": "test-shell-secret"}
    )
    assert exchanged.status_code == 200
    body = exchanged.json()
    assert body["is_admin"] is True
    user = StudyUserStore(factory).get(body["id"])
    assert user is not None
    assert user.password_hash is None
    assert desktop_client.get("/api/v1/auth/me").status_code == 200


@pytest.mark.contract  # §18.6 — the exchange/Dim surface is shell-secret gated
def test_desktop_api_requires_shell_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # SA_SHELL=1 = the shell.py attachment flag (§11 gate arms only for
    # shell-attached processes; ADR-0023).
    monkeypatch.setenv("SA_SHELL", "1")
    app = create_app(
        _settings(
            tmp_path,
            identity_mode="desktop",
            shell_secret="test-shell-secret",
        )
    )
    with TestClient(app) as unauthenticated:
        assert unauthenticated.get("/api/v1/health").status_code == 403
        wrong = unauthenticated.get(
            "/api/v1/health", headers={"X-Shell-Token": "nope"}
        )
        assert wrong.status_code == 403
        ok = unauthenticated.get(
            "/api/v1/health", headers={"X-Shell-Token": "test-shell-secret"}
        )
        assert ok.status_code == 200


@pytest.mark.contract  # ADR-0023 — shell-less desktop dev leaves the gate open
def test_shell_less_desktop_dev_does_not_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desktop identity WITHOUT an attached shell (`run-dev.sh`: uvicorn +
    vite — no SA_SHELL=1, no `?shell=` carrier) must not arm the §11 gate,
    or the dev SPA could never authenticate."""
    monkeypatch.delenv("SA_SHELL", raising=False)
    app = create_app(_settings(tmp_path, identity_mode="desktop"))
    with TestClient(app) as unauthenticated:
        assert unauthenticated.get("/api/v1/health").status_code == 200
        assert (
            unauthenticated.get("/api/v1/auth/me").status_code != 403
        ), "shell-less desktop dev must not gate the API"


@pytest.mark.contract  # §18.6 — env flip cannot change auth_mode after init
def test_auth_mode_is_init_only(tmp_path: Path) -> None:
    first = create_app(_settings(tmp_path, auth_mode="open"))
    with TestClient(first):
        pass
    first_factory = first.state.session_factory
    assert StudyInstanceStore(first_factory).get("auth_mode") == "open"
    second = create_app(_settings(tmp_path, auth_mode="authenticated"))
    second_factory = second.state.session_factory
    assert StudyInstanceStore(second_factory).get("auth_mode") == "open"


@pytest.mark.contract  # §18.6 — local-boot token on an authenticated instance ⇒ 401
def test_local_boot_token_rejected_on_authenticated_instance(
    raw_client: TestClient,
) -> None:
    from nx_auth.cookies import cookie_names

    app = raw_client.app
    assert isinstance(app, FastAPI)
    kit = app.state.auth
    token = mint_token(
        make_test_keyring(),
        AuthConfig(iss="study"),
        kind=TokenKind.SESSION,
        sub="someone",
        ver=1,
        auth_mode=AuthMode.LOCAL_BOOT,
    )
    response = raw_client.get(
        "/api/v1/auth/me", headers={"Cookie": f"{cookie_names(kit.config).access}={token}"}
    )
    assert response.status_code == 401


def test_audit_trail_written(raw_client: TestClient) -> None:
    created = raw_client.post(
        "/api/v1/auth/register",
        json={"email": "audited@example.com", "password": "correct-horse-battery"},
    )
    assert created.status_code == 201
    app = raw_client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as session:
        actions = {row.action for row in session.scalars(select(AuditEventRow)).all()}
    assert "auth.register" in actions


def test_domain_api_requires_session(raw_client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    assert raw_client.get("/api/v1/fs/dirs").status_code == 401
    assert raw_client.get("/api/v1/health").status_code == 200
    with pytest.raises(WebSocketDisconnect), raw_client.websocket_connect("/ws"):
        pass
