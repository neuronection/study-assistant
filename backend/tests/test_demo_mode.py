"""Demo mode (S8, identity-auth §13) through the real study surface.

The seeder (`scripts/seed-demo.py`) must refuse anything that is not a
demo target *and* a demo instance — loudly, non-zero — seed idempotent
synthetic-only content, and land rows nowhere but the demo instance.
The public `GET /api/v1/instance/config` endpoint (product-owned) feeds
the SPA's "Demo — synthetic data" badge before login, and the kit's
demo rules hold through study's real app: the `demo` principal only on
demo instances, `demo` tokens rejected elsewhere (§18.11).
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import AnonymousTestClient
from fastapi.testclient import TestClient
from nx_auth.cookies import cookie_names
from nx_auth.tokens import AuthMode, TokenKind, mint_token
from pytest import MonkeyPatch

from app.auth.stores import StudyUserStore
from app.core.config import Settings
from app.main import create_app

# §18.11 demo contract: seeder refusal matrix + `demo` principal/token rules
# through study's real app (identity-auth §13).
pytestmark = pytest.mark.contract

REPO_ROOT = Path(__file__).resolve().parents[2]
SEEDER = REPO_ROOT / "scripts" / "seed-demo.py"
DEMO_PRINCIPAL_ID = "00000000-0000-4000-8000-00000000d0e0"
SEED_DOMAIN = "@demo.study.local"


def run_seeder(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SEEDER), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=180,
    )


def app_settings(data_dir: Path, **overrides: Any) -> Settings:
    return Settings(
        data_dir=data_dir,
        config_dir=data_dir / "config",
        spa_dist=data_dir / "no-spa",
        log_level="WARNING",
        **overrides,
    )


def db_counts(data_dir: Path) -> dict[str, int]:
    connection = sqlite3.connect(data_dir / "study.sqlite3")
    try:
        counts: dict[str, int] = {}
        for table in ("users", "profiles", "courses", "materials", "notes", "exercises"):
            counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        demo_flag = connection.execute(
            "SELECT value FROM instance_settings WHERE key = 'demo_mode'"
        ).fetchone()
        counts["demo_mode"] = 1 if demo_flag is not None and demo_flag[0] == "true" else 0
        return counts
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Guard rails — the seeder refuses anything that is not a demo instance.
# ---------------------------------------------------------------------------


def test_seeder_refuses_non_demo_targets(tmp_path: Path) -> None:
    postgres = run_seeder(
        "--database-url", "postgresql+psycopg://u:p@localhost:5432/neuro_study"
    )
    assert postgres.returncode != 0
    assert postgres.returncode == 2
    assert "REFUSED" in postgres.stderr
    assert "_demo" in postgres.stderr

    sqlite_plain = run_seeder("--database-url", f"sqlite:///{tmp_path}/study.sqlite3")
    assert sqlite_plain.returncode == 2
    assert "REFUSED" in sqlite_plain.stderr
    assert "--demo-dir" in sqlite_plain.stderr

    outside = run_seeder(
        "--database-url",
        f"sqlite:///{tmp_path}/outside.sqlite3",
        "--demo-dir",
        str(tmp_path / "demo-data"),
    )
    assert outside.returncode == 2
    assert "REFUSED" in outside.stderr

    unannounced = run_seeder("--demo-dir", str(tmp_path / "fresh-demo"))
    assert unannounced.returncode == 2
    assert "REFUSED" in unannounced.stderr
    assert "--init-demo" in unannounced.stderr


def test_seeder_refuses_non_demo_instance(tmp_path: Path) -> None:
    demo_dir = tmp_path / "demo-workspace"
    app = create_app(app_settings(demo_dir))
    app.state.engine.dispose()
    assert db_counts(demo_dir)["demo_mode"] == 0

    refused = run_seeder("--demo-dir", str(demo_dir))
    assert refused.returncode == 2
    assert "REFUSED" in refused.stderr
    assert "demo_mode" in refused.stderr

    init_refused = run_seeder("--demo-dir", str(demo_dir), "--init-demo")
    assert init_refused.returncode == 2
    assert "REFUSED" in init_refused.stderr
    assert "EMPTY" in init_refused.stderr

    after = db_counts(demo_dir)
    assert after["users"] == 0
    assert after["courses"] == 0
    assert after["demo_mode"] == 0


# ---------------------------------------------------------------------------
# Idempotent, synthetic-only seeding — into the demo instance and nowhere else.
# ---------------------------------------------------------------------------


def test_seeder_seeds_demo_workspace_idempotently_only_in_the_demo_instance(
    tmp_path: Path,
) -> None:
    demo_dir = tmp_path / "demo-workspace"
    first = run_seeder("--demo-dir", str(demo_dir), "--init-demo")
    assert first.returncode == 0, first.stderr
    assert "synthetic" in first.stdout.lower()

    seeded = db_counts(demo_dir)
    assert seeded["users"] == 3
    assert seeded["profiles"] == 9
    assert seeded["courses"] == 9
    assert seeded["materials"] == 11
    assert seeded["notes"] == 10
    assert seeded["exercises"] == 27
    assert seeded["demo_mode"] == 1

    second = run_seeder("--demo-dir", str(demo_dir))
    assert second.returncode == 0, second.stderr
    assert "(0 created this run)" in second.stdout
    assert db_counts(demo_dir) == seeded

    third = run_seeder("--demo-dir", str(demo_dir), "--reset")
    assert third.returncode == 0, third.stderr
    assert "reset: removed" in third.stdout
    assert db_counts(demo_dir) == seeded

    connection = sqlite3.connect(demo_dir / "study.sqlite3")
    try:
        emails = {
            row[0] for row in connection.execute("SELECT email FROM users")
        }
        assert emails == {
            f"ava.lindqvist{SEED_DOMAIN}",
            f"marco.ferreira{SEED_DOMAIN}",
            f"nora.okafor{SEED_DOMAIN}",
        }
        card_sources = {
            row[0]
            for row in connection.execute(
                "SELECT json_extract(created_from, '$.source') FROM exercises"
            )
        }
        assert card_sources == {"demo"}
    finally:
        connection.close()

    other_dir = tmp_path / "real-workspace"
    other_app = create_app(app_settings(other_dir))
    other_app.state.engine.dispose()
    untouched = db_counts(other_dir)
    assert untouched["users"] == 0
    assert untouched["courses"] == 0
    assert untouched["materials"] == 0
    assert untouched["notes"] == 0
    assert untouched["exercises"] == 0
    assert untouched["demo_mode"] == 0


# ---------------------------------------------------------------------------
# Public instance config (the badge must render before login).
# ---------------------------------------------------------------------------


def test_instance_config_is_public_and_profile_exempt(raw_client: TestClient) -> None:
    response = raw_client.get("/api/v1/instance/config")
    assert response.status_code == 200
    assert response.json() == {
        "demo_mode": False,
        "auth_mode": "authenticated",
        "registration_enabled": True,
    }


def test_instance_config_reports_demo_mode(tmp_path: Path) -> None:
    app = create_app(app_settings(tmp_path, demo_mode=True))
    with AnonymousTestClient(app) as anonymous:
        response = anonymous.get("/api/v1/instance/config")
    assert response.status_code == 200
    assert response.json()["demo_mode"] is True


def test_instance_config_reports_registration_flag(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setenv("SA_REGISTRATION_ENABLED", "false")
    app = create_app(app_settings(tmp_path))
    with AnonymousTestClient(app) as anonymous:
        response = anonymous.get("/api/v1/instance/config")
    assert response.status_code == 200
    assert response.json()["registration_enabled"] is False


# ---------------------------------------------------------------------------
# The kit's demo rules through study's real app (§18.11).
# ---------------------------------------------------------------------------


def test_demo_principal_only_on_demo_instances(tmp_path: Path) -> None:
    app = create_app(app_settings(tmp_path / "plain"))
    with AnonymousTestClient(app) as anonymous:
        assert anonymous.post("/api/v1/auth/demo").status_code == 404

    demo_app = create_app(app_settings(tmp_path / "demo", demo_mode=True))
    with AnonymousTestClient(demo_app) as anonymous:
        login = anonymous.post("/api/v1/auth/demo")
        assert login.status_code == 200
        me = anonymous.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["id"] == DEMO_PRINCIPAL_ID


def test_demo_token_rejected_on_non_demo_instance(tmp_path: Path) -> None:
    app = create_app(app_settings(tmp_path))
    users = StudyUserStore(app.state.session_factory)
    user = users.create(email="demo-token@study.local", password_hash=None)
    kit = app.state.auth
    token = mint_token(
        kit.ring,
        kit.config,
        kind=TokenKind.SESSION,
        sub=user.id,
        ver=user.token_version,
        auth_mode=AuthMode.DEMO,
    )
    access_name = cookie_names(kit.config).access
    with AnonymousTestClient(app) as anonymous:
        response = anonymous.get(
            "/api/v1/auth/me", headers={"Cookie": f"{access_name}={token}"}
        )
    assert response.status_code == 401
