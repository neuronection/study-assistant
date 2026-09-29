from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_fs_dirs_allows_data_dir_and_caps_parent(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    ok = client.get("/api/v1/fs/dirs", params={"path": str(tmp_path)})
    assert ok.status_code == 200
    payload = ok.json()
    assert payload["path"] == str(tmp_path.resolve())
    assert payload["parent"] is None
    child = client.get("/api/v1/fs/dirs", params={"path": str(tmp_path / "docs")})
    assert child.status_code == 200
    assert child.json()["parent"] == str(tmp_path.resolve())


def test_fs_dirs_rejects_outside_granted_roots(client: TestClient) -> None:
    response = client.get("/api/v1/fs/dirs", params={"path": "/etc"})
    assert response.status_code == 403
    assert response.json()["detail"] == "path outside granted roots"


def test_fs_dirs_rejects_symlink_escape(client: TestClient, tmp_path: Path) -> None:
    link = tmp_path / "escape"
    link.symlink_to("/etc")
    response = client.get("/api/v1/fs/dirs", params={"path": str(link)})
    assert response.status_code == 403


def test_fs_extra_root_via_config(tmp_path: Path) -> None:
    granted = tmp_path / "granted"
    granted.mkdir()
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        fs_roots=str(granted),
    )
    app = create_app(settings)
    with TestClient(app) as configured:
        assert configured.get("/api/v1/fs/dirs", params={"path": str(granted)}).status_code == 200
        assert configured.get("/api/v1/fs/dirs", params={"path": str(tmp_path)}).status_code == 403
