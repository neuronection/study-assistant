"""Deployment-mode correctness: web/server vs desktop (plan 52 fix).

Two failures that only appear when the app runs somewhere other than a
developer's desktop, and that fail *silently* if unguarded:

1. **Custody.** The OS keyring is desktop-only. Python's
   ``keyring.backends.null`` accepts writes and discards them — a token
   would be "stored" and never readable. The store must fall back to the
   sealed file and must NEVER silently no-op.
2. **OAuth redirect.** A loopback redirect only works when the browser and
   the app share a machine. A web deployment needs the server callback
   route, or the provider redirects to the user's own localhost.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import secrets
from app.core.config import Settings


def _reinit_keyring() -> None:
    """keyring caches its backend at import — force a re-resolve."""
    import keyring

    keyring.core.init_backend()


def test_headless_keyring_falls_back_to_the_sealed_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No OS keyring -> sealed file; the token must survive the round trip."""
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")
    _reinit_keyring()
    monkeypatch.setattr("app.core.config.get_settings", lambda: Settings(data_dir=tmp_path))
    secrets.reset_secret_caches()

    try:
        secrets.set_secret("calendar:web-mode:oauth", '{"access_token":"SECRET-TOKEN"}')
        back = secrets.get_secret("calendar:web-mode:oauth")
        assert back is not None and "SECRET-TOKEN" in back, "token silently lost headless"
        assert secrets.store_backend() == "file"
    finally:
        secrets.reset_secret_caches()


def test_sealed_file_is_not_plaintext(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The server fallback must be cipher-sealed, not a readable blob."""
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")
    _reinit_keyring()
    monkeypatch.setattr("app.core.config.get_settings", lambda: Settings(data_dir=tmp_path))
    secrets.reset_secret_caches()
    try:
        secrets.set_secret("calendar:web-mode:token", "SUPER-SECRET")
        stored = (tmp_path / "secrets.json").read_text(encoding="utf-8")
        assert "SUPER-SECRET" not in stored, "plaintext credential on disk"
    finally:
        secrets.reset_secret_caches()


def test_no_usable_store_fails_closed_never_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neither backend usable -> refuse. A silent no-op would lose the token."""
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")
    _reinit_keyring()
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(data_dir=Path("/proc/definitely-not-writable")),
    )
    secrets.reset_secret_caches()
    try:
        assert secrets.store_backend() == "none"
        with pytest.raises(RuntimeError, match="fail closed"):
            secrets.set_secret("calendar:web-mode:never", "x")
        # and the read path reports nothing rather than a phantom value
        assert secrets.get_secret("calendar:web-mode:never") is None
    finally:
        secrets.reset_secret_caches()


def test_redirect_is_loopback_on_desktop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Desktop/local: RFC 8252 loopback — browser and app share a machine."""
    from app.services.study import calendar_sync

    monkeypatch.delenv("SA_APP_URL", raising=False)
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: type("S", (), {"app_url": None})(),
    )
    uri = calendar_sync._redirect_uri()
    assert uri.startswith("http://127.0.0.1:"), uri
    assert uri.endswith("/oauth/callback")
    assert calendar_sync.is_web_oauth() is False


def test_redirect_is_the_server_route_on_the_web(monkeypatch: pytest.MonkeyPatch) -> None:
    """Web/server: the provider must hit US, not the user's own localhost."""
    from app.services.study import calendar_sync

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: type("S", (), {"app_url": "https://study.example.com"})(),
    )
    uri = calendar_sync._redirect_uri()
    assert uri == "https://study.example.com/api/v1/calendar/oauth/callback"
    assert calendar_sync.is_web_oauth() is True


def test_state_carries_a_non_secret_link_prefix() -> None:
    """A server callback must be able to find the binding from `state` alone."""
    from app.services.study import calendar_sync

    assert calendar_sync.link_id_from_state("abc-123.nonce-half") == "abc-123"
    assert calendar_sync.link_id_from_state("malformed") is None
    assert calendar_sync.link_id_from_state("") is None


def test_web_callback_route_is_registered() -> None:
    """The route exists and is reachable (its security is the state law)."""
    from app.api.calendar import router

    paths = [getattr(r, "path", "") for r in router.routes]
    assert any(p.endswith("/oauth/callback") for p in paths), f"callback route missing: {paths}"
