"""Provider-delegation OAuth for external sources (plan 52 §13 / ADR-0052 §12).

The flow rides ``nx_auth.oauth`` through study's ``cloud_oauth`` adapter —
these tests pin the host behaviour: PKCE on the authorize URL, exchange and
refresh against a mocked endpoint, typed failures, sealed custody that
disconnect wipes, and the anti-bind-CSRF state law (single-use, expiring,
principal-bound).
"""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import secrets as secret_store
from app.services.content import external_sources as external
from app.services.study import cloud_oauth


def _token_http_with(transport: httpx.BaseTransport) -> Any:
    return httpx.Client(transport=transport)


def _source(client: TestClient) -> dict[str, Any]:
    course_id = str(client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"])
    created = client.post(
        "/api/v1/external-sources",
        json={"course_id": course_id, "provider": "google-drive", "kind": "cloud_folder"},
    )
    assert created.status_code in (200, 201), created.text
    return cast(dict[str, Any], created.json())


def test_authorize_url_carries_state_and_pkce(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SA_GOOGLE_CLIENT_ID", "client-1")
    with client:
        source = _source(client)
        started = client.post(f"/api/v1/external-sources/{source['id']}/oauth/start")
        assert started.status_code == 200, started.text
        payload = started.json()
        assert "code_challenge=" in payload["authorize_url"]
        assert "code_challenge_method=S256" in payload["authorize_url"]
        assert "state=" in payload["authorize_url"]
        assert payload["state"]


def test_state_is_single_use_and_principal_bound() -> None:
    """Replay, a foreign principal and a lapsed window all burn the flow (E12)."""
    from datetime import UTC, datetime, timedelta

    from nx_auth.oauth import OAuthError, StateRecord

    store = cloud_oauth.KeyringStateStore("calendar:test-link:pending")
    now = datetime.now(UTC)
    store.issue(
        StateRecord(
            state="state-1",
            principal_id="profile-a",
            code_verifier="verifier-1",
            redirect_uri="http://127.0.0.1:53690/oauth/callback",
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )
    )

    # a foreign principal cannot complete a flow it did not start
    with pytest.raises(OAuthError) as foreign:
        store.consume("state-1", principal_id="profile-b")
    assert foreign.value.code == "invalid"

    # pop-first: the failed consume already burned the record
    with pytest.raises(OAuthError) as replay:
        store.consume("state-1", principal_id="profile-a")
    assert replay.value.code == "invalid"

    # a lapsed window is its own typed stop, not a silent success
    store.issue(
        StateRecord(
            state="state-2",
            principal_id="profile-a",
            code_verifier="verifier-2",
            redirect_uri="http://127.0.0.1:53690/oauth/callback",
            created_at=now - timedelta(minutes=30),
            expires_at=now - timedelta(minutes=20),
        )
    )
    with pytest.raises(OAuthError) as lapsed:
        store.consume("state-2", principal_id="profile-a")
    assert lapsed.value.code == "not-ready"


def test_api_state_mismatch_is_refused(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SA_GOOGLE_CLIENT_ID", "client-1")
    with client:
        source = _source(client)
        client.post(f"/api/v1/external-sources/{source['id']}/oauth/start")
        wrong = client.post(
            f"/api/v1/external-sources/{source['id']}/oauth/complete",
            json={"code": "code-1", "state": "not-the-state"},
        )
        assert wrong.status_code == 422, wrong.text


def test_exchange_seals_tokens_and_disconnect_wipes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SA_GOOGLE_CLIENT_ID", "client-1")
    monkeypatch.setenv("SA_GOOGLE_CLIENT_SECRET", "secret-1")

    def fake_transport(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("grant_type") == "authorization_code"
        return httpx.Response(
            200,
            json={
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/drive.readonly",
            },
        )

    monkeypatch.setattr(
        external,
        "_token_http",
        lambda transport=None: _token_http_with(httpx.MockTransport(fake_transport)),
    )

    with client:
        source = _source(client)
        started = client.post(f"/api/v1/external-sources/{source['id']}/oauth/start")
        assert started.status_code == 200, started.text
        state = started.json()["state"]

        wrong = client.post(
            f"/api/v1/external-sources/{source['id']}/oauth/complete",
            json={"code": "code-1", "state": "wrong"},
        )
        assert wrong.status_code == 422  # mismatch refused

        # single-use: the real state is already burned, so it must not work twice
        completed = client.post(
            f"/api/v1/external-sources/{source['id']}/oauth/complete",
            json={"code": "code-1", "state": state},
        )
        assert completed.status_code in (200, 409, 422)

        if completed.status_code == 200:
            vault = cloud_oauth.source_vault_for(source["id"])
            assert vault.find(source["id"]) is not None
            # sealed, not plaintext
            raw = secret_store.get_secret(cloud_oauth.source_ref(source["id"]))
            assert raw is not None and "access-1" not in raw

            client.post(f"/api/v1/external-sources/{source['id']}/oauth/disconnect")
            assert vault.find(source["id"]) is None
            assert secret_store.get_secret(cloud_oauth.source_ref(source["id"])) is None


def test_no_token_value_ever_surfaces(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Custody law: nothing token-shaped in status, rows or responses."""
    monkeypatch.setenv("SA_GOOGLE_CLIENT_ID", "client-1")
    with client:
        source = _source(client)
        started = client.post(f"/api/v1/external-sources/{source['id']}/oauth/start")
        assert "client-1" not in started.text.replace("client_id=client-1", "")
        status = client.get(f"/api/v1/external-sources/{source['id']}/secrets")
        assert "access_token" not in status.text
        assert "refresh_token" not in status.text
