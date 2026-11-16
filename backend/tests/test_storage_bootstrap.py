"""Storage bootstrap, entrypoint law and host-cap wiring (plan 55 P1)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from nx_auth.instance import IdentityMode
from object_store_stub import UnavailableObjectStore
from settings_factory import settings_from_env_file

from app.core.config import Settings
from app.core.limits import MAX_UPLOAD_BYTES
from app.main import create_app
from app.services.platform.backup import boot_integrity_check as real_boot_integrity_check
from app.storage.bootstrap import resolve_storage_config
from app.storage.object_storage import (
    BACKEND_S3,
    ENTRYPOINT_SERVER,
    S3Config,
    StorageConfig,
    StorageConfigError,
)

_STORAGE_ENV = (
    "SA_CLOUD_PROFILE",
    "SA_OBJECT_STORAGE_BACKEND",
    "SA_OBJECT_STORAGE_MAX_MB",
    "SA_OBJECT_STORAGE_LOCAL_ROOT",
    "SA_S3_BUCKET",
    "SA_S3_REGION",
    "SA_S3_ENDPOINT_URL",
    "SA_S3_ACCESS_KEY_ID",
    "SA_S3_SECRET_ACCESS_KEY",
    "SA_S3_SSE",
    "SA_S3_PREFIX",
)


def _clear_storage_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _STORAGE_ENV:
        monkeypatch.delenv(name, raising=False)


def test_desktop_rejects_a_cloud_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_storage_env(monkeypatch)
    settings = Settings(
        data_dir=tmp_path,
        app_env="test",
        identity_mode=IdentityMode.DESKTOP,
        cloud_profile="aws",
        s3_bucket="bucket1",
    )
    with pytest.raises(StorageConfigError, match="desktop"):
        create_app(settings)


def test_desktop_rejects_an_object_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_storage_env(monkeypatch)
    settings = Settings(
        data_dir=tmp_path,
        app_env="test",
        identity_mode=IdentityMode.DESKTOP,
        object_storage_backend="s3",
        s3_bucket="bucket1",
    )
    with pytest.raises(StorageConfigError, match="desktop"):
        create_app(settings)


def test_boot_integrity_check_is_skipped_for_object_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_storage_env(monkeypatch)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("boot_integrity_check must not run on an object backend")

    config = StorageConfig(
        backend=BACKEND_S3,
        entrypoint=ENTRYPOINT_SERVER,
        s3=S3Config(bucket="bucket1"),
    ).validate()
    monkeypatch.setattr("app.main.boot_integrity_check", fail_if_called)
    monkeypatch.setattr(
        "app.main.open_configured_store", lambda _settings: (config, UnavailableObjectStore())
    )
    app = create_app(
        Settings(
            data_dir=tmp_path,
            app_env="test",
            log_level="WARNING",
            object_storage_backend="s3",
            s3_bucket="bucket1",
        )
    )
    assert app.state.backups is None


def test_boot_integrity_check_still_runs_for_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_storage_env(monkeypatch)
    calls: list[tuple[object, ...]] = []

    def recording(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return real_boot_integrity_check(*args, **kwargs)

    monkeypatch.setattr("app.main.boot_integrity_check", recording)
    app = create_app(Settings(data_dir=tmp_path, app_env="test", log_level="WARNING"))
    try:
        assert len(calls) == 1
    finally:
        app.state.objects.close()


def test_env_file_storage_values_reach_the_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_storage_env(monkeypatch)
    env_file = tmp_path / "deployment.env"
    env_file.write_text(
        "\n".join(
            (
                "SA_OBJECT_STORAGE_BACKEND=s3",
                "SA_S3_BUCKET=env-bucket",
                "SA_S3_REGION=eu-central-1",
                "SA_S3_ENDPOINT_URL=https://minio.example.com",
                "SA_S3_ACCESS_KEY_ID=AKIA",
                "SA_S3_SECRET_ACCESS_KEY=secret",
                "SA_OBJECT_STORAGE_MAX_MB=150",
                "",
            )
        ),
        encoding="utf-8",
    )
    settings = settings_from_env_file(env_file, data_dir=tmp_path)
    assert "SA_S3_BUCKET" not in os.environ
    config = resolve_storage_config(settings)
    assert config.backend == "s3"
    assert config.s3 is not None
    assert config.s3.bucket == "env-bucket"
    assert config.s3.region == "eu-central-1"
    assert config.max_object_mb == 150


def test_default_storage_cap_matches_the_host_upload_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_storage_env(monkeypatch)
    config = resolve_storage_config(Settings(data_dir=tmp_path, app_env="test"))
    assert config.max_object_bytes == MAX_UPLOAD_BYTES


def test_reset_reports_a_friendly_cloud_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_storage_env(monkeypatch)
    settings = Settings(
        data_dir=tmp_path,
        app_env="test",
        cloud_profile="aws",
        object_storage_backend="local",
    )
    monkeypatch.setattr("app.reset.get_settings", lambda: settings)
    from app.reset import run_reset

    assert run_reset(include_backups=False, assume_yes=True) is False
