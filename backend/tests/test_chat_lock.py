from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.domain.models import ChatMessage, ChatSession
from app.services.platform.chat import ChatService
from app.services.platform.profiles import ensure_default_profile


class NoEmbedder:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return None


class LockCheckGateway(LLMGateway):
    def __init__(self, bind: Any) -> None:
        super().__init__(session_factory=None)
        self._factory = sessionmaker(bind=bind, expire_on_commit=False)
        self.session_id: int | None = None

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
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
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> Any:
        from app.ai.gateway import StreamChunk

        assert self.session_id is not None
        with self._factory() as other:
            row = other.get(ChatSession, self.session_id)
            assert row is not None
            assert row.mention_registry is not None, (
                "chat turn held an uncommitted mention-registry write across "
                "the model stream — a second connection cannot commit (SQLite "
                "write lock), so the gateway ledger stalls for busy_timeout"
            )
        yield StreamChunk("text", "ok")


def test_chat_turn_commits_pre_stream_writes_before_streaming(
    db_session: Session,
) -> None:
    profile = ensure_default_profile(db_session)
    session_row = ChatSession(profile_id=profile.id, title="t")
    db_session.add(session_row)
    db_session.flush()
    db_session.add(
        ChatMessage(
            session_id=session_row.id,
            role="user",
            blocks=[{"type": "md", "md": "test"}],
        )
    )
    db_session.commit()

    gateway = LockCheckGateway(db_session.bind)
    gateway.session_id = session_row.id
    service = ChatService(db_session, gateway, NoEmbedder())
    messages = service.messages(session_row.id)
    service.answer_streaming(session_row, messages[-1], lambda _event: None)
