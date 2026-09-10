from fastapi.testclient import TestClient


def test_ws_ping_pong(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_ws_subscribe_and_receive(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "subscribe", "topic": "jobs:1"})
        assert ws.receive_json() == {"type": "subscribed", "topic": "jobs:1"}
        ws.send_json({"type": "publish", "topic": "jobs:1", "payload": {"stage": "ocr"}})
        assert ws.receive_json() == {"topic": "jobs:1", "payload": {"stage": "ocr"}}


def test_ws_isolated_topics(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "subscribe", "topic": "jobs:1"})
        assert ws.receive_json() == {"type": "subscribed", "topic": "jobs:1"}
        ws.send_json({"type": "publish", "topic": "jobs:2", "payload": {"stage": "ocr"}})
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_ws_unknown_message(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "nonsense"})
        assert ws.receive_json() == {"type": "error", "error": "unknown_message"}


def test_ws_unsubscribe(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "subscribe", "topic": "jobs:1"})
        assert ws.receive_json() == {"type": "subscribed", "topic": "jobs:1"}
        ws.send_json({"type": "unsubscribe", "topic": "jobs:1"})
        assert ws.receive_json() == {"type": "unsubscribed", "topic": "jobs:1"}
        ws.send_json({"type": "publish", "topic": "jobs:1", "payload": {}})
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
