from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, default_data_dir
from app.core.working_dir import POINTER_FILENAME, read_override, write_override
from app.main import create_app


def make_client(tmp_path: Path, data_dir_name: str = "data") -> TestClient:
    settings = Settings(
        data_dir=tmp_path / data_dir_name,
        config_dir=tmp_path / "config",
        log_level="WARNING",
    )
    return TestClient(create_app(settings))


def test_get_working_dir_fresh_install(client: TestClient, tmp_path: Path) -> None:
    with client:
        body = client.get("/api/v1/config/working-dir").json()
        assert body["path"] == str(tmp_path)
        assert body["custom"] is False
        assert body["restart_pending"] is False
        assert body["default_path"].endswith("StudyAssistant")


def test_validate_rejects_relative_and_current(client: TestClient, tmp_path: Path) -> None:
    with client:
        relative = client.post(
            "/api/v1/config/working-dir/validate", json={"path": "relative/dir"}
        ).json()
        assert relative["valid"] is False
        assert relative["reason"] == "relative_path"

        current = client.post(
            "/api/v1/config/working-dir/validate", json={"path": str(tmp_path)}
        ).json()
        assert current["valid"] is False
        assert current["reason"] == "already_current"

        inside = client.post(
            "/api/v1/config/working-dir/validate",
            json={"path": str(tmp_path / "nested")},
        ).json()
        assert inside["valid"] is False
        assert inside["reason"] == "inside_current"


def test_validate_accepts_empty_and_existing_sa_dirs(tmp_path: Path) -> None:
    empty = tmp_path / "brand-new"
    empty.mkdir()
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "app.db").write_bytes(b"sqlite")
    junk = tmp_path / "junk"
    junk.mkdir()
    (junk / "random.txt").write_text("x")
    with make_client(tmp_path) as client:
        body = client.post(
            "/api/v1/config/working-dir/validate", json={"path": str(empty)}
        ).json()
        assert body["valid"] is True
        assert body["empty"] is True

        body = client.post(
            "/api/v1/config/working-dir/validate", json={"path": str(existing)}
        ).json()
        assert body["valid"] is True
        assert body["has_app_db"] is True

        body = client.post(
            "/api/v1/config/working-dir/validate", json={"path": str(junk)}
        ).json()
        assert body["valid"] is False
        assert body["reason"] == "not_empty"


def test_validate_rejects_unwritable_and_accepts_creatable(tmp_path: Path) -> None:
    unwritable = tmp_path / "locked"
    unwritable.mkdir()
    unwritable.chmod(0o500)
    deep = tmp_path / "a" / "b" / "c"
    with make_client(tmp_path) as client:
        try:
            body = client.post(
                "/api/v1/config/working-dir/validate", json={"path": str(unwritable)}
            ).json()
            assert body["valid"] is False
            assert body["reason"] == "not_writable"
        finally:
            unwritable.chmod(0o755)

        body = client.post(
            "/api/v1/config/working-dir/validate", json={"path": str(deep)}
        ).json()
        assert body["valid"] is True


def test_put_writes_pointer_and_reports_pending(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    with make_client(tmp_path) as client:
        put = client.put("/api/v1/config/working-dir", json={"path": str(target)})
        assert put.status_code == 200, put.text
        assert put.json() == {"path": str(target), "restart_required": True}

        assert read_override(tmp_path / "config") == target

        body = client.get("/api/v1/config/working-dir").json()
        assert body["custom"] is True
        assert body["restart_pending"] is True
        assert body["path"] == str(tmp_path / "data")


def test_put_rejects_current_directory(client: TestClient, tmp_path: Path) -> None:
    with client:
        put = client.put("/api/v1/config/working-dir", json={"path": str(tmp_path)})
        assert put.status_code == 422
        assert "already_current" in put.json()["detail"]


def test_delete_clears_pointer(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    with make_client(tmp_path) as client:
        client.put("/api/v1/config/working-dir", json={"path": str(target)})
        deleted = client.delete("/api/v1/config/working-dir")
        assert deleted.status_code == 200
        assert deleted.json()["restart_required"] is True

        body = client.get("/api/v1/config/working-dir").json()
        assert body["custom"] is False
        assert body["restart_pending"] is False

        deleted_again = client.delete("/api/v1/config/working-dir")
        assert deleted_again.json()["restart_required"] is False


def test_boot_resolution_pointer_then_env_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    target = tmp_path / "moved"
    target.mkdir()
    write_override(config_dir, target)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SA_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("SA_DATA_DIR", raising=False)

    settings = Settings()
    assert settings.data_dir == target

    env_dir = tmp_path / "env-wins"
    monkeypatch.setenv("SA_DATA_DIR", str(env_dir))
    assert Settings().data_dir == env_dir

    monkeypatch.delenv("SA_DATA_DIR")
    (config_dir / POINTER_FILENAME).write_text("relative/path\n", encoding="utf-8")
    assert Settings().data_dir == default_data_dir()
