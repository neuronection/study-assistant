"""Identity-glue contract cases (ADR-0028; plan 20 §5 matrix).

Study-side coverage of S1, S2, S13-S15 — the kit's `CONTRACT_CASES`
checklist is a string list, so product coverage is explicit (plan 20 D9).
S3 (init-only flips) lives in `test_identity_core.py`; S5/B2 knob
routing lives in `test_sec16_env.py`.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.stores import StudyInstanceStore, StudyProfileStore, StudyUserStore
from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.contract

FIXTURE_PASSWORD = "fixture-password-study"  # conftest mint_session hash


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        app_env="test",
        **overrides,  # type: ignore[arg-type]
    )


def _auth_mode(app: FastAPI) -> str | None:
    return StudyInstanceStore(app.state.session_factory).get("auth_mode")


def test_server_open_env_coerces_to_authenticated(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """S1 / §4.4 — `open` on a server entrypoint never seeds."""
    with caplog.at_level("WARNING"):
        app = create_app(_settings(tmp_path, auth_mode="open"))
    assert _auth_mode(app) == "authenticated"
    assert any("SA_AUTH_MODE=open is not legal" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("identity", ["server", "desktop"])
def test_unknown_auth_mode_fails_closed(tmp_path: Path, identity: str) -> None:
    """S2 — junk AUTH_MODE warns and seeds `authenticated` on both rows."""
    app = create_app(_settings(tmp_path, identity_mode=identity, auth_mode="WideOpen"))
    assert _auth_mode(app) == "authenticated"


@pytest.mark.parametrize(
    ("auth_mode", "expected"),
    [("", "open"), ("authenticated", "authenticated")],
)
def test_desktop_init_modes(tmp_path: Path, auth_mode: str, expected: str) -> None:
    """S13 — desktop initializes open by default; authenticated is honored."""
    app = create_app(_settings(tmp_path, identity_mode="desktop", auth_mode=auth_mode))
    assert _auth_mode(app) == expected
    # demo_mode is written explicitly at init either way (§13)
    assert StudyInstanceStore(app.state.session_factory).get("demo_mode") == "false"


def test_admin_instance_transition(tmp_path: Path) -> None:
    """S14 / §4.5 — mode changes are admin + password actions, audited.

    The password-less-owner path (`open → authenticated` setting
    credentials) is kit behavior; here the study adapters back the same
    `PATCH /api/v1/admin/instance` flow with a password-holding admin.
    """
    app = create_app(_settings(tmp_path, identity_mode="desktop"))
    with TestClient(app) as client:
        assert _auth_mode(app) == "open"
        wrong = client.patch(
            "/api/v1/admin/instance",
            json={"auth_mode": "authenticated", "password": "not-the-password"},
        )
        assert wrong.status_code == 403
        assert _auth_mode(app) == "open", "wrong password must not flip the mode"
        ok = client.patch(
            "/api/v1/admin/instance",
            json={"auth_mode": "authenticated", "password": FIXTURE_PASSWORD},
        )
        assert ok.status_code == 200
        assert _auth_mode(app) == "authenticated"


def test_register_provisions_default_profile(tmp_path: Path) -> None:
    """S15 — registration creates the user with its Default profile (§6)."""
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/auth/register",
            json={"email": "newcomer@study.local", "password": "a-long-enough-password"},
        )
        assert created.status_code in (200, 201)
        user = StudyUserStore(app.state.session_factory).get_by_email("newcomer@study.local")
        assert user is not None
        assert StudyProfileStore(app.state.session_factory).count_for(user.id) >= 1


def test_registration_disabled_refuses(tmp_path: Path) -> None:
    """S15 — REGISTRATION_ENABLED=false ⇒ /auth/register answers 403."""
    app = create_app(_settings(tmp_path, registration_enabled=False))
    with TestClient(app) as client:
        refused = client.post(
            "/api/v1/auth/register",
            json={"email": "nope@study.local", "password": "a-long-enough-password"},
        )
        assert refused.status_code == 403
        assert StudyUserStore(app.state.session_factory).get_by_email("nope@study.local") is None
