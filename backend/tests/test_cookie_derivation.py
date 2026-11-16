"""Cookie `Secure` derives from the public scheme (plan 64 §1.6).

`SA_COOKIE_SECURE` may still pin a value, but the default is no longer a
static compose constant: the public scheme (`SA_PUBLIC_URL`, falling back
to `SA_APP_URL`) or the explicit `SA_TLS` flag decides — so LAN/VPN logins
over plain HTTP keep working, while a public https:// deployment gets
Secure cookies without extra config.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "data_dir": Path(__file__).parent / "_cookie-derivation-unused",
        "config_dir": Path(__file__).parent / "_cookie-derivation-unused-config",
        "app_env": "test",
        "log_level": "WARNING",
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def test_default_is_insecure_http() -> None:
    assert _settings().effective_cookie_secure is False


def test_public_https_url_derives_secure() -> None:
    settings = _settings(public_url="https://study.example.com")
    assert settings.effective_cookie_secure is True


def test_public_http_url_keeps_login_working_over_lan() -> None:
    settings = _settings(public_url="http://study.lan:8080")
    assert settings.effective_cookie_secure is False


def test_tls_flag_derives_secure() -> None:
    assert _settings(tls=True).effective_cookie_secure is True


def test_tls_false_overrides_a_https_public_url() -> None:
    """`SA_TLS=0` says TLS terminates elsewhere — the operator's word wins."""
    settings = _settings(public_url="https://study.example.com", tls=False)
    assert settings.effective_cookie_secure is False


def test_explicit_cookie_secure_wins_over_everything() -> None:
    assert _settings(public_url="http://x", cookie_secure=True).effective_cookie_secure is True
    assert _settings(public_url="https://x", cookie_secure=False).effective_cookie_secure is False


def test_app_url_is_the_scheme_fallback() -> None:
    assert _settings(app_url="https://study.example.com").effective_cookie_secure is True
    assert _settings(app_url="http://study.lan").effective_cookie_secure is False


def test_schemeless_public_url_falls_through_to_app_url() -> None:
    settings = _settings(public_url="study.example.com", app_url="https://study.example.com")
    assert settings.effective_cookie_secure is True


def test_compose_empty_strings_are_unset() -> None:
    """Compose passes `${VAR:-}` as empty string — treat it as unset."""
    settings = _settings(public_url="", tls="", cookie_secure="")
    assert settings.effective_cookie_secure is False


def test_kit_receives_the_derived_value() -> None:
    """`install_identity` routes the derived value into the auth kit —
    never None (which would silently re-apply the family default)."""
    from app.auth.install import _settings_knob

    https = _settings(public_url="https://study.example.com")
    assert _settings_knob(https, "SA_COOKIE_SECURE") is True
    http = _settings(public_url="http://study.lan")
    assert _settings_knob(http, "SA_COOKIE_SECURE") is False


def test_desktop_defaults_are_unchanged() -> None:
    """Desktop (`python -m studyassistant`) sets none of the new vars and
    must behave exactly as before: cookies insecure, `app` the default
    mode (plan 64 §3.3 desktop regression)."""
    from studyassistant.__main__ import resolve_mode

    settings = _settings()
    assert settings.public_url is None
    assert settings.tls is None
    assert settings.cookie_secure is None
    assert settings.effective_cookie_secure is False
    assert resolve_mode([]) == "app"
