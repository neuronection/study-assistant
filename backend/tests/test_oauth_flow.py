"""Plan 86 B: OAuth2 loopback/PKCE state machine and sealed token lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import oauth as oauth_core
from app.core import secrets as secret_store


def _config() -> oauth_core.OAuthConfig:
    return oauth_core.OAuthConfig(
        provider_id="google-drive",
        authorize_url="https://accounts.example/authorize",
        token_url="https://accounts.example/token",
        scopes=("drive.readonly",),
        redirect_port=53682,
        client_id="client-1",
        client_secret="secret-1",
    )


def _token_transport(payloads: list[dict[str, object]]) -> httpx.MockTransport:
    remaining = list(payloads)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://accounts.example/token"
        body = request.content.decode()
        assert "code_verifier=" in body or "refresh_token=" in body
        return httpx.Response(200, json=remaining.pop(0))

    return httpx.MockTransport(handler)


def test_authorize_url_carries_state_and_pkce() -> None:
    config = _config()
    verifier = oauth_core.pkce_verifier()
    url = oauth_core.build_authorize_url(config, "state-1", verifier)
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert params["state"] == ["state-1"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://127.0.0.1:53682/oauth/callback"]
    assert params["code_challenge"] == [oauth_core.pkce_challenge(verifier)]
    assert "client_secret" not in params


def test_exchange_and_refresh_round_trip_against_mocked_endpoint() -> None:
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    transport = _token_transport(
        [
            {
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "drive.readonly",
            },
            {
                "access_token": "access-2",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        ]
    )
    tokens = oauth_core.exchange_code(
        _config(), "code-1", "verifier-1", transport=transport, now=now
    )
    assert tokens.access_token == "access-1"
    assert tokens.refresh_token == "refresh-1"
    assert not tokens.expired(now=now + timedelta(minutes=10))
    assert tokens.expired(now=now + timedelta(hours=2))

    fresh = oauth_core.refresh_tokens(_config(), tokens, transport=transport, now=now)
    assert fresh.access_token == "access-2"
    assert fresh.refresh_token == "refresh-1"


def test_refresh_rejection_is_a_typed_auth_error() -> None:
    config = _config()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            400, json={"error": "invalid_grant", "error_description": "expired"}
        )
    )
    tokens = oauth_core.OAuthTokens(
        access_token="old",
        refresh_token="refresh-1",
        token_type="Bearer",
        expires_at=None,
    )
    with pytest.raises(oauth_core.OAuthError) as error:
        oauth_core.refresh_tokens(config, tokens, transport=transport)
    assert error.value.code == "auth"


def test_tokens_are_sealed_and_disconnect_wipes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SA_GOOGLE_CLIENT_ID", "client-1")
    monkeypatch.setenv("SA_GOOGLE_CLIENT_SECRET", "secret-1")
    with client:
        course_id = str(client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"])
        source = client.post(
            "/api/v1/external-sources",
            json={
                "course_id": course_id,
                "provider": "google-drive",
                "kind": "cloud_folder",
            },
        ).json()
        started = client.post(f"/api/v1/external-sources/{source['id']}/oauth/start")
        assert started.status_code == 200, started.text
        state = started.json()["state"]
        assert "code_challenge=" in started.json()["authorize_url"]

        wrong = client.post(
            f"/api/v1/external-sources/{source['id']}/oauth/complete",
            json={"code": "code-1", "state": "wrong"},
        )
        assert wrong.status_code == 422

        client.post(f"/api/v1/external-sources/{source['id']}/oauth/start")
        state = client.post(f"/api/v1/external-sources/{source['id']}/oauth/start").json()["state"]

        def fake_exchange(config: object, code: str, verifier: str) -> oauth_core.OAuthTokens:
            return oauth_core.OAuthTokens(
                access_token="access-1",
                refresh_token="refresh-1",
                token_type="Bearer",
                expires_at=None,
            )

        monkeypatch.setattr(oauth_core, "exchange_code", fake_exchange)
        completed = client.post(
            f"/api/v1/external-sources/{source['id']}/oauth/complete",
            json={"code": "code-1", "state": state},
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "ok"

    slot = oauth_core.token_slot(source["id"])
    assert oauth_core.load_tokens(slot) is not None
    assert secret_store.get_secret(slot) is not None

    with client:
        disconnected = client.post(f"/api/v1/external-sources/{source['id']}/oauth/disconnect")
        assert disconnected.status_code == 200
        assert disconnected.json()["status"] == "needs-config"
    assert oauth_core.load_tokens(slot) is None
    assert secret_store.get_secret(slot) is None
