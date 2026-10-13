"""Chat-turn DB lock scope (2026-10-13 incident).

A chat turn whose provider call hangs (or retries for minutes) must not
hold the SQLite write transaction for the whole await: every concurrent
request writes (`touch_last_used` middleware) and a long-held write lock
turns one bad turn into app-wide `database is locked` 500s. The turn's
durable writes commit at their transaction boundaries (before the engine
starts, inside prepare, at finalize) — never across a model await.
"""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway

from app.core.config import Settings
from app.main import create_app

PROBE_TIMEOUT_SEC = 0.3


class BlockingGateway(ScriptedGateway):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(responses)
        self.entered = threading.Event()
        self.release = threading.Event()

    def generate(
        self,
        task: str,
        messages: list[Any],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        self.calls.append(messages)
        self.entered.set()
        assert self.release.wait(timeout=30)
        return self.responses.pop(0)


def _make_app(tmp_path: Path, gateway: ScriptedGateway) -> Any:
    return create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )


@contextmanager
def harness(tmp_path: Path) -> Iterator[tuple[TestClient, BlockingGateway, int]]:
    gateway = BlockingGateway(["final answer"])
    with TestClient(_make_app(tmp_path, gateway)) as client:
        session_id = int(client.post("/api/v1/chat/sessions", json={}).json()["id"])
        yield client, gateway, session_id


def _probe_write_lock(db_path: Path) -> None:
    probe = sqlite3.connect(db_path, timeout=PROBE_TIMEOUT_SEC)
    try:
        probe.execute("BEGIN IMMEDIATE")
        probe.execute("ROLLBACK")
    finally:
        probe.close()


def _assert_lock_free(db_path: Path, while_doing: str) -> None:
    try:
        _probe_write_lock(db_path)
    except sqlite3.OperationalError as error:
        raise AssertionError(
            f"the chat turn holds the SQLite write lock {while_doing}: {error}"
        ) from error


def test_turn_does_not_hold_the_write_lock_across_the_model_call(tmp_path: Path) -> None:
    with harness(tmp_path) as (client, gateway, session_id):
        sent = client.post(
            f"/api/v1/chat/sessions/{session_id}/messages", json={"content": "hello"}
        )
        assert sent.status_code == 200, sent.text
        assert gateway.entered.wait(timeout=30)

        try:
            _assert_lock_free(tmp_path / "study.sqlite3", "while the model call is in flight")
        finally:
            gateway.release.set()

        import time

        messages: list[dict[str, Any]] = []
        stop = time.monotonic() + 30.0
        while time.monotonic() < stop:
            messages = client.get(f"/api/v1/chat/sessions/{session_id}/messages").json()
            if any(m["role"] == "assistant" for m in messages):
                break
            time.sleep(0.05)
        assert any(m["role"] == "assistant" for m in messages), (
            f"assistant message never appeared; last messages: {messages!r}"
        )


def test_turn_does_not_hold_the_write_lock_during_prepare(tmp_path: Path) -> None:
    from app.services.platform.chat import ChatService

    original_prepare = ChatService.prepare_turn_context
    entered = threading.Event()
    release = threading.Event()

    def slow_prepare(self: Any, chat_session: Any, user_message: Any) -> Any:
        prep = original_prepare(self, chat_session, user_message)
        entered.set()
        assert release.wait(timeout=30)
        return prep

    ChatService.prepare_turn_context = slow_prepare  # type: ignore[method-assign]
    gateway = BlockingGateway(["final answer"])
    try:
        with TestClient(_make_app(tmp_path, gateway)) as client:
            session_id = int(client.post("/api/v1/chat/sessions", json={}).json()["id"])
            sent = client.post(
                f"/api/v1/chat/sessions/{session_id}/messages", json={"content": "hello"}
            )
            assert sent.status_code == 200, sent.text
            assert entered.wait(timeout=30)

            try:
                _assert_lock_free(tmp_path / "study.sqlite3", "while turn preparation runs")
            finally:
                release.set()
    finally:
        ChatService.prepare_turn_context = original_prepare  # type: ignore[method-assign]


def test_turn_does_not_hold_the_write_lock_while_retries_run(tmp_path: Path) -> None:
    class FailingGateway(BlockingGateway):
        def generate(
            self,
            task: str,
            messages: list[Any],
            model: Any = None,
            course_id: int | None = None,
        ) -> str:
            self.calls.append(messages)
            self.entered.set()
            assert self.release.wait(timeout=30)
            raise RuntimeError("provider exploded")

    gateway = FailingGateway([])
    with TestClient(_make_app(tmp_path, gateway)) as client:
        session_id = int(client.post("/api/v1/chat/sessions", json={}).json()["id"])
        sent = client.post(
            f"/api/v1/chat/sessions/{session_id}/messages", json={"content": "hello"}
        )
        assert sent.status_code == 200, sent.text
        assert gateway.entered.wait(timeout=30)

        try:
            _assert_lock_free(tmp_path / "study.sqlite3", "across provider retries")
        finally:
            gateway.release.set()
