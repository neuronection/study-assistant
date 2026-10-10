"""Security headers (plan 21 Phase 3 — new coverage).

Study previously served NO response hardening (CORS + the WS-Origin
gate only). These cases pin the kit's `SecurityHeadersMiddleware` with
study's policy: the family baseline on every response (H1), the
web/desktop CSP split gated by the per-boot `?shell=` marker (H2), and
headers on the SPA static mount too (H3). Contract cases 20 + 21.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.contract  # identity-auth §18 cases 20 + 21 (plan 21)

WEB_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline';"
    " script-src 'self'; connect-src 'self'; font-src 'self' data:; object-src 'none';"
    " frame-ancestors 'none'; base-uri 'self'"
)
DESKTOP_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline';"
    " script-src 'self' 'unsafe-eval'; connect-src 'self'; font-src 'self' data:;"
    " object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
)


def _assert_baseline(headers: dict[str, str]) -> None:
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert "object-src 'none'" in headers["content-security-policy"]
    assert "base-uri 'self'" in headers["content-security-policy"]
    # HSTS stays at the nginx layer (ADR-0005) — never app-level here.
    assert "strict-transport-security" not in headers


def test_every_api_response_carries_the_family_baseline(client: TestClient) -> None:
    """H1: any authenticated API response — the middleware runs on the
    whole HTTP surface."""
    response = client.get("/api/v1/profiles")
    assert response.status_code == 200
    _assert_baseline(dict(response.headers))


def test_web_csp_is_strict_and_byte_stable(client: TestClient) -> None:
    """H2 (web half): `script-src 'self'`, no eval — and the byte-exact
    family template (career's rule, family law)."""
    response = client.get("/api/v1/profiles")
    assert response.headers["content-security-policy"] == WEB_CSP
    assert "unsafe-eval" not in response.headers["content-security-policy"]


def test_shell_shaped_query_never_unlocks_eval(client: TestClient) -> None:
    """H2: a marker without the per-boot secret stays on the web CSP."""
    for query in ("?shell=", "?shell=not-the-secret", "?shell=0"):
        response = client.get(f"/api/v1/profiles{query}")
        assert response.headers["content-security-policy"] == WEB_CSP


def test_valid_shell_marker_unlocks_the_desktop_csp(desktop_client: TestClient) -> None:
    """H2 (desktop half): the desktop shell document — carrying the
    valid per-boot `?shell=` token — gets the eval-capable variant for
    the pywebview bridge; every other response stays strict."""
    token = desktop_client.headers["X-Shell-Token"]
    response = desktop_client.get(f"/api/v1/profiles?shell={token}")
    assert response.headers["content-security-policy"] == DESKTOP_CSP
    _assert_baseline(dict(response.headers))
    # Same boot, no marker: strict again.
    strict = desktop_client.get("/api/v1/profiles")
    assert strict.headers["content-security-policy"] == WEB_CSP


def test_headers_present_on_static_mounts_too(tmp_path: Path) -> None:
    """H3: the SPA shell and its assets get the same hardening — the
    middleware wraps the mounted static files, not just API routes
    (static paths sit outside session enforcement, no session needed)."""
    spa = tmp_path / "spa"
    (spa / "assets").mkdir(parents=True)
    (spa / "index.html").write_text("<html><body>study</body></html>")
    (spa / "assets" / "app.js").write_text("console.log('spa')")

    app = create_app(
        Settings(
            data_dir=tmp_path,
            config_dir=tmp_path / "config",
            spa_dist=spa,
            log_level="WARNING",
            app_env="test",
        )
    )
    with TestClient(app) as client:
        for path in ("/", "/assets/app.js"):
            response = client.get(path)
            assert response.status_code == 200, path
            _assert_baseline(dict(response.headers))
            assert response.headers["content-security-policy"] == WEB_CSP, path
