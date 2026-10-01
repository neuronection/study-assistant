"""§16 config surface (ADR-0028 / plan 20 B2): every family knob is
routable from the deployment `.env` file as well as the process
environment, and reaches the installed auth-kit config.

Before plan 20 the kit's `AuthConfig.from_env` read `os.environ` only —
`.env`-file values loaded into `Settings` and then died there. These
cases drive the real `create_app` with a `Settings` bound to a temp
`.env` file and assert the values land in `app.state.auth.config` and
the KeyRing. OS environment variables still win over the file.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nx_auth.boot import BootConfigError

from app.core.config import Settings
from app.main import create_app

_KNOB_ENV = (
    "SA_APP_ENV",
    "SA_AUTH_MODE",
    "SA_COOKIE_SECURE",
    "SA_AUTH_ACCESS_TTL_MINUTES",
    "SA_AUTH_REFRESH_TTL_DAYS",
    "SA_AUTH_REFRESH_ABSOLUTE_DAYS",
    "SA_AUTH_LOCKOUT_THRESHOLD",
    "SA_AUTH_LOCKOUT_MINUTES",
    "SA_AUTH_PASSWORD_MIN_LENGTH",
    "SA_TRUSTED_PROXY_COUNT",
    "SA_RATELIMIT_AUTH",
    "SA_RATELIMIT_AUTH_EMAIL",
    "SA_REGISTRATION_ENABLED",
    "SA_SESSION_KEY",
    "SA_REFRESH_KEY",
    "SA_DATA_KEY",
)


def _settings_from_env_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str, **overrides: object
) -> Settings:
    env_file = tmp_path / "env-under-test"
    env_file.write_text(text)
    for var in _KNOB_ENV:
        monkeypatch.delenv(var, raising=False)
    kwargs: dict[str, object] = {
        "data_dir": tmp_path,
        "config_dir": tmp_path / "config",
        "spa_dist": tmp_path / "no-spa",
        "log_level": "WARNING",
        "app_env": "test",
    }
    kwargs.update(overrides)
    return Settings(_env_file=str(env_file), **kwargs)  # type: ignore[arg-type, call-arg]


def _settings_with_env_file(env_file: Path, **overrides: object) -> Settings:
    kwargs: dict[str, object] = {
        "data_dir": env_file.parent,
        "config_dir": env_file.parent / "config",
        "spa_dist": env_file.parent / "no-spa",
        "log_level": "WARNING",
        "app_env": "test",
    }
    kwargs.update(overrides)
    return Settings(_env_file=str(env_file), **kwargs)  # type: ignore[arg-type, call-arg]


def test_dotenv_knobs_reach_kit_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """S5 / §18.14 — `.env` values reach the kit exactly like OS env."""
    fresh = _settings_from_env_text(
        monkeypatch,
        tmp_path,
        "\n".join(
            [
                "SA_COOKIE_SECURE=true",
                "SA_AUTH_ACCESS_TTL_MINUTES=45",
                "SA_AUTH_REFRESH_TTL_DAYS=14",
                "SA_AUTH_REFRESH_ABSOLUTE_DAYS=60",
                "SA_AUTH_LOCKOUT_THRESHOLD=3",
                "SA_AUTH_LOCKOUT_MINUTES=30",
                "SA_AUTH_PASSWORD_MIN_LENGTH=16",
                "SA_TRUSTED_PROXY_COUNT=2",
                "SA_RATELIMIT_AUTH=7",
                "SA_RATELIMIT_AUTH_EMAIL=11",
                "SA_REGISTRATION_ENABLED=false",
            ]
        )
        + "\n",
    )
    app = create_app(fresh)
    config = app.state.auth.config

    assert config.cookie_secure is True
    assert config.access_ttl_minutes == 45
    assert config.refresh_ttl_days == 14
    assert config.refresh_absolute_days == 60
    assert config.lockout_threshold == 3
    assert config.lockout_minutes == 30
    assert config.password_min_length == 16
    assert config.trusted_proxy_count == 2
    assert config.auth_rate_per_minute == 7
    assert config.auth_email_rate_per_minute == 11
    assert config.registration_enabled is False


def test_os_env_beats_dotenv_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fresh = _settings_from_env_text(
        monkeypatch, tmp_path, "SA_AUTH_LOCKOUT_THRESHOLD=3\n"
    )
    assert fresh.auth_lockout_threshold == 3, "file value resolves"

    monkeypatch.setenv("SA_AUTH_LOCKOUT_THRESHOLD", "9")
    os_wins = _settings_with_env_file(tmp_path / "env-under-test")
    assert os_wins.auth_lockout_threshold == 9, "environment beats the file"


def test_key_pins_from_dotenv_reach_the_keyring(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """§8 pins resolve through Settings (KeyRing.load_for `pinned=`)."""
    pins = (
        "s-pin-0123456789abcdefghijklmnopqrstuv",
        "r-pin-0123456789abcdefghijklmnopqrstuv",
        "d-pin-0123456789abcdefghijklmnopqrstuv",
    )
    fresh = _settings_from_env_text(
        monkeypatch,
        tmp_path,
        f"SA_SESSION_KEY={pins[0]}\nSA_REFRESH_KEY={pins[1]}\nSA_DATA_KEY={pins[2]}\n",
    )
    app = create_app(fresh)
    ring = app.state.auth.ring
    assert (ring.session_key, ring.refresh_key, ring.data_key) == pins


def test_partial_key_pin_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fresh = _settings_from_env_text(
        monkeypatch, tmp_path, "SA_SESSION_KEY=only-one-pin-0123456789abcdefghijklmno\n"
    )
    with pytest.raises(ValueError, match="partial key pin"):
        create_app(fresh)


def test_boot_guards_wired_on_production_boot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """S6/S8 wiring — production boots abort on unsafe config."""
    fresh = _settings_from_env_text(
        monkeypatch,
        tmp_path,
        "SA_DEBUG=true\n",
        app_env="production",
    )
    assert fresh.is_production
    with pytest.raises(BootConfigError, match="DEBUG"):
        create_app(fresh)


def test_registration_gate_reads_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """S15 gate — REGISTRATION_ENABLED=false in `.env` refuses signup."""
    fresh = _settings_from_env_text(
        monkeypatch, tmp_path, "SA_REGISTRATION_ENABLED=false\n"
    )
    app = create_app(fresh)
    with TestClient(app) as client:
        refused = client.post(
            "/api/v1/auth/register",
            json={"email": "nope@study.local", "password": "a-long-enough-password"},
        )
        assert refused.status_code == 403
