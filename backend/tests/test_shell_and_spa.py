import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.shell import find_free_port

main = importlib.import_module("studyassistant.__main__")
resolve_mode = main.resolve_mode


def test_find_free_port() -> None:
    port = find_free_port()
    assert 0 < port < 65536


def test_resolve_mode_defaults_to_app() -> None:
    assert resolve_mode([]) == "app"
    assert resolve_mode(["studyassistant"]) == "app"


def test_resolve_mode_accepts_app_and_web() -> None:
    assert resolve_mode(["studyassistant", "app"]) == "app"
    assert resolve_mode(["studyassistant", "web"]) == "web"
    assert resolve_mode(["studyassistant", "mcp"]) == "mcp"


def test_resolve_mode_rejects_unknown() -> None:
    with pytest.raises(SystemExit, match="unknown mode: desktop"):
        resolve_mode(["studyassistant", "desktop"])


def test_spa_served_when_built(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>spa</body></html>")
    settings = Settings(data_dir=tmp_path / "data", spa_dist=dist, log_level="WARNING")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "spa" in response.text


def test_spa_deep_link_serves_index_html(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>spa</body></html>")
    settings = Settings(data_dir=tmp_path / "data", spa_dist=dist, log_level="WARNING")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/courses/3/sections/9")
        assert response.status_code == 200
        assert "spa" in response.text


def test_spa_fallback_does_not_shadow_api_404(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>spa</body></html>")
    settings = Settings(data_dir=tmp_path / "data", spa_dist=dist, log_level="WARNING")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/v1/no-such-endpoint")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")


def test_root_hint_when_not_built(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, spa_dist=tmp_path / "missing-dist", log_level="WARNING")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["detail"].startswith("frontend not built")


def test_explicit_spa_dist_without_index_not_served(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    settings = Settings(data_dir=tmp_path, spa_dist=empty, log_level="WARNING")
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/").json()["detail"].startswith("frontend not built")


def test_shell_rendered_beacon_sets_state(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, spa_dist=tmp_path / "missing-dist", log_level="WARNING")
    app = create_app(settings)
    assert getattr(app.state, "spa_rendered", False) is False
    with TestClient(app) as client:
        response = client.post("/api/v1/shell/rendered")
    assert response.status_code == 204
    assert app.state.spa_rendered is True
