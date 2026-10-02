from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.main import create_app

# §18.5 (WebSocket half): handshake rejects missing/wrong Origin.
pytestmark = pytest.mark.contract


def test_ws_rejects_cross_site_origin(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws", headers={"origin": "http://evil.example"}),
    ):
        pass


def test_ws_allows_same_origin(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_ws_allows_configured_origin_and_rejects_others(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        cors_origins="http://localhost:3200",
    )
    app = create_app(settings)
    with TestClient(app) as configured:
        with configured.websocket_connect("/ws", headers={"origin": "http://localhost:3200"}) as ws:
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}
        with (
            pytest.raises(WebSocketDisconnect),
            configured.websocket_connect("/ws", headers={"origin": "http://evil.example"}),
        ):
            pass
