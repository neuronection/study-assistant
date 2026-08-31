import threading
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from test_chat_api import NoEmbedder
from test_chat_branches import harness

from app.ai.gateway import LLMGateway, ResolvedModel, StreamChunk
from app.domain.models import ChatMessage, ChatSession
from app.services.platform.chat import ChatService
from app.services.platform.profiles import ensure_default_profile


class SelfStoppingGateway(LLMGateway):
    """Streams one chunk, then flips the stop flag before the next chunk."""

    def __init__(self) -> None:
        super().__init__(session_factory=None)
        self.stop = threading.Event()

    def resolve(
        self, task: str, course_id: int | None = None
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="fake",
            label="fake",
            caps=["text"],
            api_key=None,
        )

    def stream_events(
        self,
        task: str,
        messages: list[Any],
        model: Any = None,
        course_id: int | None = None,
    ) -> Any:
        yield StreamChunk("text", "prefix ")
        self.stop.set()
        yield StreamChunk("text", "tail [1]")


def test_stop_mid_stream_persists_prefix_and_marks_trace(db_session: Session) -> None:
    profile = ensure_default_profile(db_session)
    session_row = ChatSession(profile_id=profile.id, title="t")
    db_session.add(session_row)
    db_session.flush()
    user_message = ChatMessage(
        session_id=session_row.id,
        role="user",
        blocks=[{"type": "text", "md": "Differentiate x^2"}],
    )
    db_session.add(user_message)
    db_session.commit()

    gateway = SelfStoppingGateway()
    service = ChatService(db_session, gateway, NoEmbedder())
    events: list[dict[str, Any]] = []

    created = service.answer_streaming(
        session_row,
        user_message,
        lambda e: events.append(e),
        stop=gateway.stop,
    )

    assert created.trace is not None
    assert created.trace["stream_interrupted"] is True
    assert "stopped by user" in str(created.trace["interruption"])
    assert any(e["type"] == "stream_interrupted" for e in events)
    assert str(created.blocks[0]["md"]).startswith("prefix")


def test_stop_endpoint_reports_no_active_turn(tmp_path: Path) -> None:
    with harness(tmp_path, []) as h:
        response = h.client.post(f"/api/v1/chat/sessions/{h.session_id}/stop")
        assert response.status_code == 200
        assert response.json() == {"stopped": False}


def test_stop_endpoint_unknown_session_404(tmp_path: Path) -> None:
    with harness(tmp_path, []) as h:
        response = h.client.post("/api/v1/chat/sessions/999999/stop")
        assert response.status_code == 404
