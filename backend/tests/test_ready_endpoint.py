"""`/ready` readiness probe (plan 64 §1.4 / ADR-0062 v7 §9).

Hard checks (a failure is a 503): DB reachable **and at this release's
migration head**, required object storage, boot (lifespan) complete.
Soft signals never flip the status — study runs no Redis (in-process
schedulers), and non-required object storage only degrades. Liveness stays
`/api/v1/health`; readiness is the ingress probe at `/ready`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.readiness as readiness
from app.core.config import Settings
from app.main import create_app
from app.storage.health import STATUS_DEGRADED, STATUS_UNAVAILABLE, StorageHealth


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        app_env="test",
    )


def test_ready_is_200_after_boot(tmp_path: Path) -> None:
    """The lifespan startup flips `boot_complete`; /ready follows."""
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"]["boot"]["ok"] is True
        assert body["checks"]["db"]["ok"] is True
        assert body["checks"]["db"]["revision"]  # the stamped head
        assert body["checks"]["storage"]["ok"] is True
        # Soft column: Redis is `none` (in-process schedulers), and soft
        # signals never flip the status.
        assert body["soft"]["redis"].startswith("none")


def test_ready_is_503_before_boot_completes(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    assert app.state.boot_complete is False
    client = TestClient(app)  # lifespan not entered — boot not complete
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not-ready"
    assert body["checks"]["boot"]["ok"] is False


def test_ready_is_503_when_db_unreachable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(_settings(tmp_path))
    app.state.boot_complete = True
    client = TestClient(app)
    monkeypatch.setattr(readiness, "db_revision", lambda engine: None)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["db"]["ok"] is False
    assert "head" in (body["checks"]["db"]["detail"] or "")


def test_ready_is_503_when_db_behind_migration_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(_settings(tmp_path))
    app.state.boot_complete = True
    client = TestClient(app)
    monkeypatch.setattr(readiness, "db_revision", lambda engine: "0001_stale")
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["db"]["revision"] == "0001_stale"


def test_ready_is_503_when_required_storage_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(_settings(tmp_path))
    app.state.boot_complete = True
    client = TestClient(app)
    probe = app.state.storage_health
    monkeypatch.setattr(
        probe,
        "snapshot",
        lambda: StorageHealth(backend="s3", status=STATUS_UNAVAILABLE, required=True),
    )
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["storage"]["ok"] is False
    assert body["checks"]["storage"]["required"] is True


def test_optional_storage_degradation_stays_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Soft signals never flip the status (plan 64 §1.4)."""
    app = create_app(_settings(tmp_path))
    app.state.boot_complete = True
    client = TestClient(app)
    probe = app.state.storage_health
    monkeypatch.setattr(
        probe,
        "snapshot",
        lambda: StorageHealth(backend="s3", status=STATUS_DEGRADED, required=False),
    )
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_liveness_route_unchanged(tmp_path: Path) -> None:
    """/api/v1/health stays the liveness probe (200 in a booted app)."""
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
