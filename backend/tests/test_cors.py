from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_cors_off_by_default(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_only_configured_origins(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        cors_origins="http://localhost:3200",
    )
    app = create_app(settings)
    with TestClient(app) as configured:
        allowed = configured.get("/api/v1/health", headers={"origin": "http://localhost:3200"})
        assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3200"
        denied = configured.get("/api/v1/health", headers={"origin": "http://evil.example"})
        assert "access-control-allow-origin" not in denied.headers
