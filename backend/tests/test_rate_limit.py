"""App-level rate limiting (plan 21 Phase 3 — new coverage).

Study previously had NO limits above the auth surface (kit auth limiters
only). These cases pin the mounted family limiter over the §16 knobs:
R1 burst ⇒ 429 + Retry-After, R2/R3 trusted-proxy identity, R5 ceiling 0
disables, R6 independent buckets, R7 `.env`-only ceilings, plus the
enabled kill-switch. Contract cases 19 + 22.

Probes ride session-exempt routes (the login POST and the health GET):
the limiter sits outside session enforcement, so anonymous traffic ticks
the buckets exactly like authenticated traffic.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.middleware import api_bucket_for, client_identity

pytestmark = pytest.mark.contract  # identity-auth §18 cases 19 + 22 (plan 21)

LOGIN = "/api/v1/auth/login"
HEALTH = "/api/v1/health"


def _make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    return Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        app_env="test",
        **overrides,
    )


@contextmanager
def _anon_client(tmp_path: Path, **overrides: Any) -> Iterator[TestClient]:
    app = create_app(_make_settings(tmp_path, **overrides))
    with TestClient(app) as client:
        yield client


@pytest.fixture
def burst(tmp_path: Path) -> Iterator[TestClient]:
    """Anonymous client with a tight AUTH window for burst probes."""
    with _anon_client(tmp_path, ratelimit_auth=3, ratelimit_default=3) as client:
        yield client


def _login(client: TestClient, **extra: Any) -> Any:
    return client.post(
        LOGIN, json={"email": "nobody@example.com", "password": "wrong-wrong"}, **extra
    )


# --------------------------------------------------------------------- routing


def test_api_bucket_routing() -> None:
    assert api_bucket_for({"path": "/api/v1/auth/login"}) == "AUTH"
    assert api_bucket_for({"path": "/api/v1/auth/register"}) == "AUTH"
    assert api_bucket_for({"path": "/api/v1/admin/instance"}) == "AUTH"
    assert api_bucket_for({"path": "/api/v1/me/password"}) == "AUTH"
    assert api_bucket_for({"path": "/api/v1/ai/models"}) == "AI"
    assert api_bucket_for({"path": "/api/v1/chat/sessions"}) == "AI"
    assert api_bucket_for({"path": "/api/v1/materials"}) == "DEFAULT"
    assert api_bucket_for({"path": "/assets/app.js"}) is None
    assert api_bucket_for({"path": "/ws"}) is None


# ------------------------------------------------------------------ R1 (429)


def test_burst_over_ceiling_429_with_retry_after(burst: TestClient) -> None:
    for _ in range(3):
        assert _login(burst).status_code in (401, 423)
    blocked = _login(burst)
    assert blocked.status_code == 429
    assert "retry-after" in blocked.headers
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.json() == {"detail": "Too many requests"}


def test_rate_limit_disabled_lets_everything_through(tmp_path: Path) -> None:
    """The kill-switch stops the mounted limiter (the kit's own auth
    limiters are a separate §7 guard and stay on their defaults)."""
    with _anon_client(tmp_path, ratelimit_enabled=False) as client:
        for _ in range(10):
            assert _login(client).status_code in (401, 423)


def test_zero_ceiling_disables_bucket(tmp_path: Path) -> None:
    """R5 on a general bucket: DEFAULT at 0 disables it. (AUTH/AUTH_EMAIL
    ride the kit's F8 floor `>= 1` — those knobs may tune the auth-flow
    guard, never disable it; the general buckets have no such floor.)"""
    with _anon_client(tmp_path, ratelimit_default=0) as client:
        for _ in range(10):
            assert client.get(HEALTH).status_code == 200


# ------------------------------------------------------------ R2/R3 (identity)


def test_spoofed_forwarded_for_cannot_rotate_buckets(burst: TestClient) -> None:
    """R2: with SA_TRUSTED_PROXY_COUNT=0 (default) the socket address
    keys the window — a rotating spoofed X-Forwarded-For is ignored."""
    for spoof in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
        assert _login(burst, headers={"X-Forwarded-For": spoof}).status_code in (401, 423)
    blocked = _login(burst, headers={"X-Forwarded-For": "9.9.9.9"})
    assert blocked.status_code == 429, "all four keyed on the socket IP"


def test_rightmost_trusted_hop_keys_the_window(tmp_path: Path) -> None:
    """R3: one trusted proxy — nginx's appended hop is the identity;
    attacker-prepended hops to its left fall away."""
    with _anon_client(
        tmp_path, ratelimit_auth=2, ratelimit_default=2, trusted_proxy_count=1
    ) as client:
        assert _login(client, headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.9"}).status_code in (
            401,
            423,
        )
        assert _login(client, headers={"X-Forwarded-For": "7.7.7.7, 203.0.113.9"}).status_code in (
            401,
            423,
        )
        blocked = _login(client, headers={"X-Forwarded-For": "8.8.8.8, 203.0.113.9"})
        assert blocked.status_code == 429, "same real client hop ⇒ same bucket"
        other = _login(client, headers={"X-Forwarded-For": "198.51.100.7"})
        assert other.status_code in (401, 423), "a different real hop has its own budget"


def test_client_identity_trusted_hops_only() -> None:
    class _State:
        settings = _make_settings(Path("/tmp/ratelimit-identity"), trusted_proxy_count=1)

    class _App:
        state = _State()

    scope: dict[str, Any] = {
        "app": _App(),
        "client": ("10.0.0.1", 5),
        "headers": [(b"x-forwarded-for", b"spoof, 203.0.113.9")],
    }
    assert client_identity(scope) == "203.0.113.9"
    scope["headers"] = [(b"x-forwarded-for", b"spoof")]
    assert client_identity(scope) == "spoof", "single hop = the trusted one"


# ------------------------------------------------------------------ R6 (R7)


def test_auth_and_default_buckets_are_independent(burst: TestClient) -> None:
    """R6: exhausting the AUTH window leaves DEFAULT untouched — no
    cross-bucket exhaustion."""
    for _ in range(4):
        _login(burst)
    assert _login(burst).status_code == 429
    # The DEFAULT budget was never spent by the login burst.
    assert burst.get(HEALTH).status_code == 200


def test_env_only_ceilings_are_applied(tmp_path: Path) -> None:
    """R7 (plan 20 B2 class): ceilings set only in the deployment `.env`
    reach the mounted limiter — same values, same behavior as OS env."""
    from settings_factory import settings_from_env_file

    env_file = tmp_path / ".env"
    env_file.write_text("SA_RATELIMIT_AUTH=2\n")
    settings = settings_from_env_file(
        str(env_file),
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        app_env="test",
    )
    assert settings.ratelimit_auth == 2

    with TestClient(create_app(settings)) as client:
        assert _login(client).status_code in (401, 423)
        assert _login(client).status_code in (401, 423)
        assert _login(client).status_code == 429
