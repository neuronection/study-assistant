"""Owner/app DSN separation (ADR-0064) — compose contract + tri-state.

Two roles, two credentials: the owner DSN (`SA_MIGRATIONS_DATABASE_URL`,
`SA_DB_OWNER_PASSWORD`) lives **only** in the one-shot `migrate` service;
the `app` service carries the app DSN alone and the entrypoint refuses a
serving env that gains the owner DSN. Migrate mode resolves the ADR-0064
§4 tri-state (split / unsplit warning / broken refusal).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from app.ops.migrations import (
    BrokenSplitError,
    ProvisioningError,
    _ident,
    resolve_plan,
)

REPO = Path(__file__).resolve().parents[2]
PROD_COMPOSE = REPO / "docker" / "docker-compose.prod.yml"
STANDALONE_COMPOSE = REPO / "docker" / "docker-compose.standalone.yml"
ENTRYPOINT = REPO / "docker" / "entrypoint.sh"
INIT_DB = REPO / "docker" / "init-db.sh"


def _compose(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@pytest.fixture(scope="module")
def prod() -> dict[str, Any]:
    return _compose(PROD_COMPOSE)


@pytest.fixture(scope="module")
def standalone() -> dict[str, Any]:
    return _compose(STANDALONE_COMPOSE)


def _env(doc: dict[str, Any], service: str) -> dict[str, Any]:
    return doc["services"][service].get("environment") or {}


# --- the app service never sees the owner credential ----------------------


@pytest.mark.parametrize("doc_name", ["prod", "standalone"])
def test_app_env_has_no_owner_dsn_or_owner_password(
    request: pytest.FixtureRequest, doc_name: str
) -> None:
    doc: dict[str, Any] = request.getfixturevalue(doc_name)
    env = _env(doc, "app")
    assert all("MIGRATIONS" not in key for key in env), sorted(env)
    assert all("OWNER" not in key for key in env), sorted(env)
    joined = " ".join(str(value) for value in env.values())
    assert "study_owner" not in joined, "app DSN must connect as the app role"
    assert "OWNER_PASSWORD" not in joined


@pytest.mark.parametrize("doc_name", ["prod", "standalone"])
def test_app_env_is_the_app_role_dsn(request: pytest.FixtureRequest, doc_name: str) -> None:
    doc: dict[str, Any] = request.getfixturevalue(doc_name)
    env = _env(doc, "app")
    assert "study_app" in str(env["SA_DATABASE_URL"])
    assert env["SA_DB_USER"] == "neuronection_study_app"


# --- migrate owns the owner credential + the split marker -----------------


@pytest.mark.parametrize("doc_name", ["prod", "standalone"])
def test_migrate_env_has_split_marker_and_owner_dsn(
    request: pytest.FixtureRequest, doc_name: str
) -> None:
    doc: dict[str, Any] = request.getfixturevalue(doc_name)
    env = _env(doc, "migrate")
    assert env["SA_DB_SPLIT"] == "1", "split marker (ADR-0064 §4)"
    owner_dsn = str(env["SA_MIGRATIONS_DATABASE_URL"])
    assert "study_owner" in owner_dsn
    assert "SA_DB_OWNER_PASSWORD" in owner_dsn
    assert env["SA_DB_APP_PASSWORD"] == "${SA_DB_PASSWORD}", (
        "migrate needs the app role's secret to bootstrap/sync the role"
    )


@pytest.mark.parametrize("doc_name", ["prod", "standalone"])
def test_db_bootstraps_distinct_passwords(request: pytest.FixtureRequest, doc_name: str) -> None:
    doc: dict[str, Any] = request.getfixturevalue(doc_name)
    env = _env(doc, "db")
    owner_guard = env["POSTGRES_PASSWORD"]
    app_guard = env["SA_DB_APP_PASSWORD"]
    assert "SA_DB_OWNER_PASSWORD" in str(owner_guard)
    assert "SA_DB_OWNER_PASSWORD" not in str(app_guard)
    assert "SA_DB_PASSWORD" in str(app_guard)
    assert ":?" in str(owner_guard) and ":?" in str(app_guard), (
        "fresh stacks must refuse to boot without both secrets"
    )


@pytest.mark.parametrize("doc_name", ["prod", "standalone"])
def test_backup_sidecar_dumps_as_owner(request: pytest.FixtureRequest, doc_name: str) -> None:
    doc: dict[str, Any] = request.getfixturevalue(doc_name)
    env = _env(doc, "backup")
    assert env["PGPASSWORD"] == "${SA_DB_OWNER_PASSWORD}"


def test_cookie_proxy_env_present_and_never_static_true(
    prod: dict[str, Any], standalone: dict[str, Any]
) -> None:
    for doc in (prod, standalone):
        env = _env(doc, "app")
        assert "SA_COOKIE_SECURE" in env, "derive, never hardcode"
        assert env["SA_COOKIE_SECURE"] == "${SA_COOKIE_SECURE:-}"
        assert env["SA_PUBLIC_URL"] == "${SA_PUBLIC_URL:-}"
        assert env["SA_TLS"] == "${SA_TLS:-}"
        assert "SA_TRUSTED_PROXY_COUNT" in env
        for key in ("SA_COOKIE_SECURE", "SA_TLS"):
            assert str(env[key]) != "true"


# --- entrypoint + init-db tripwires ----------------------------------------


def test_entrypoint_serving_branch_refuses_owner_dsn() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "REFUSING to serve" in text
    assert "SA_MIGRATIONS_DATABASE_URL" in text


def test_init_db_creates_the_app_role_with_its_own_password() -> None:
    text = INIT_DB.read_text(encoding="utf-8")
    assert "SA_DB_APP_PASSWORD" in text
    assert "DML-only" in text


# --- ADR-0064 §4: the tri-state (pure resolution) --------------------------


def test_split_state_resolves_owner_url() -> None:
    plan = resolve_plan(
        {
            "SA_DB_SPLIT": "1",
            "SA_MIGRATIONS_DATABASE_URL": "postgresql://owner@db/study",
            "SA_DATABASE_URL": "postgresql://app@db/study",
        }
    )
    assert plan.state == "split"
    assert plan.owner_url == "postgresql://owner@db/study"
    assert plan.warning is None


def test_broken_state_refuses_to_boot() -> None:
    with pytest.raises(BrokenSplitError):
        resolve_plan({"SA_DB_SPLIT": "1", "SA_DATABASE_URL": "postgresql://app@db/study"})


def test_unsplit_state_warns_loud() -> None:
    plan = resolve_plan({"SA_DATABASE_URL": "postgresql://app@db/study"})
    assert plan.state == "unsplit"
    assert plan.warning is not None
    assert "NOT managed-ready" in plan.warning
    assert plan.owner_url == "postgresql://app@db/study"


def test_migrations_url_without_marker_still_splits_with_a_nudge() -> None:
    plan = resolve_plan({"SA_MIGRATIONS_DATABASE_URL": "postgresql://owner@db/study"})
    assert plan.state == "split"
    assert plan.warning is not None
    assert "SA_DB_SPLIT" in plan.warning


# --- the migrate command's fail-closed paths --------------------------------


def test_main_returns_2_on_broken_split(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.ops import migrations

    monkeypatch.setenv("SA_DB_SPLIT", "1")
    monkeypatch.delenv("SA_MIGRATIONS_DATABASE_URL", raising=False)
    assert migrations.main() == 2
    assert "REFUSING" in capsys.readouterr().err


def test_main_requires_app_password_in_split(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.ops import migrations

    monkeypatch.setenv("SA_DB_SPLIT", "1")
    monkeypatch.setenv("SA_MIGRATIONS_DATABASE_URL", "postgresql://owner@db/study")
    monkeypatch.delenv("SA_DB_APP_PASSWORD", raising=False)
    assert migrations.main() == 2
    assert "SA_DB_APP_PASSWORD" in capsys.readouterr().err


# --- provisioning helpers ----------------------------------------------------


def test_identifiers_are_validated_before_ddl() -> None:
    assert _ident("neuronection_study_app") == "neuronection_study_app"
    with pytest.raises(ProvisioningError):
        _ident("app); DROP SCHEMA public; --")
    with pytest.raises(ProvisioningError):
        _ident("")
