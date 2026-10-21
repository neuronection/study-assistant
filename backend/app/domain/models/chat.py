from ...core.vocab import ChatProposalStatus, ProposalAnchorOp, ProposalTargetKind, QuizVerdict
from ..documents import DOCUMENT_SCHEMA_VERSION as DOCUMENT_SCHEMA_VERSION
from ..documents import validate_document as validate_document
from ..payloads import (
    BlockList,
    ChatSessionContext,
    ChatTrace,
    CitationList,
    MentionList,
    MentionRegistryList,
    ProposalPayload,
    ProposalResult,
    ReadList,
    StringList,
    ToolCallList,
    WidgetStateMap,
)
from ..proposal_contract import (
    PAYLOAD_SCHEMA_VERSION as PAYLOAD_SCHEMA_VERSION,
)
from ..proposal_contract import (
    RESULT_SCHEMA_VERSION as RESULT_SCHEMA_VERSION,
)
from ..proposal_contract import (
    validate_proposal_payload as validate_proposal_payload,
)
from ..proposal_contract import (
    validate_proposal_result as validate_proposal_result,
)
from ..schema_contract import vocab_check as vocab_check
from .core import (
    _UUID as _UUID,
)
from .core import (
    JSON as JSON,
)
from .core import (
    Any as Any,
)
from .core import (
    Base as Base,
)
from .core import (
    Boolean as Boolean,
)
from .core import (
    DateTime as DateTime,
)
from .core import (
    ForeignKey as ForeignKey,
)
from .core import (
    ForeignKeyConstraint as ForeignKeyConstraint,
)
from .core import (
    Index as Index,
)
from .core import (
    Integer as Integer,
)
from .core import (
    Mapped as Mapped,
)
from .core import (
    String as String,
)
from .core import (
    Text as Text,
)
from .core import (
    datetime as datetime,
)
from .core import (
    mapped_column as mapped_column,
)
from .core import (
    new_uuid as new_uuid,
)
from .core import (
    relationship as relationship,
)
from .core import (
    text as text,
)
from .core import (
    utcnow as utcnow,
)
from .core import (
    uuid4 as uuid4,
)
from .core import (
    validates as validates,
)


class ChatSession(Base):
    """One chat conversation; ``quiz_pending_row`` is the at-most-one quiz card."""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str | None] = mapped_column(
        _UUID, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str | None] = mapped_column(_UUID)
    title: Mapped[str] = mapped_column(String(300), default="New chat")
    use_embeddings: Mapped[bool | None] = mapped_column(Boolean)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid4())
    )
    context: Mapped[ChatSessionContext | None] = mapped_column(JSON)
    mention_registry: Mapped[MentionRegistryList | None] = mapped_column(JSON)
    active_root_id: Mapped[str | None] = mapped_column(_UUID)
    quizme: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    quiz_pending_row: Mapped["ChatQuizPending | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )


class ChatQuizPending(Base):
    """The one quiz card a quiz-me session may have open (plan 81 D)."""

    __tablename__ = "chat_quiz_pendings"
    __table_args__ = (vocab_check("verdict", QuizVerdict, nullable=True),)

    session_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("chat_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    question: Mapped[str] = mapped_column(Text)
    choices: Mapped[StringList | None] = mapped_column(JSON)
    expected_index: Mapped[int | None] = mapped_column(Integer)
    expected_latex: Mapped[str | None] = mapped_column(String(500))
    expected_text: Mapped[str | None] = mapped_column(String(500))
    accept: Mapped[StringList | None] = mapped_column(JSON)
    awaiting_answer: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    verdict: Mapped[str | None] = mapped_column(String(20))
    verdict_detail: Mapped[str | None] = mapped_column(String(500))
    student_answer: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[ChatSession] = relationship(back_populates="quiz_pending_row")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(_UUID, index=True)
    active_child_id: Mapped[str | None] = mapped_column(_UUID)
    role: Mapped[str] = mapped_column(String(20))
    blocks: Mapped[BlockList] = mapped_column(JSON)
    blocks_schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    citations: Mapped[CitationList | None] = mapped_column(JSON)
    mentions: Mapped[MentionList | None] = mapped_column(JSON)
    reads: Mapped[ReadList | None] = mapped_column(JSON)
    tool_calls: Mapped[ToolCallList | None] = mapped_column(JSON)
    grounded: Mapped[bool | None] = mapped_column(Boolean)
    state: Mapped[WidgetStateMap | None] = mapped_column(JSON)
    warnings: Mapped[StringList | None] = mapped_column(JSON)
    trace: Mapped[ChatTrace | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @validates("blocks")
    def _validate_blocks(self, key: str, value: Any) -> Any:
        self.blocks_schema_version = DOCUMENT_SCHEMA_VERSION
        return validate_document("chat_messages.blocks", value)


class ChatProposal(Base):
    __tablename__ = "chat_proposals"
    __table_args__ = (
        vocab_check("status", ChatProposalStatus),
        vocab_check("target_kind", ProposalTargetKind, nullable=True),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    message_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(50))
    target_kind: Mapped[str | None] = mapped_column(String(20))
    target_name: Mapped[str | None] = mapped_column(String(300))
    target_node_id: Mapped[str | None] = mapped_column(
        _UUID, ForeignKey("tree_nodes.id", ondelete="SET NULL")
    )
    target_node_path: Mapped[StringList | None] = mapped_column(JSON)
    original_md: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[ProposalPayload] = mapped_column(JSON)
    payload_schema_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1")
    )
    status: Mapped[str] = mapped_column(String(20), default=ChatProposalStatus.PROPOSED.value)
    result: Mapped[ProposalResult | None] = mapped_column(JSON)
    result_schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    anchors: Mapped[list["ChatProposalAnchor"]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
        order_by="ChatProposalAnchor.position",
    )

    @validates("action", "payload")
    def _validate_payload(self, key: str, value: Any) -> Any:
        if key == "payload":
            self.payload_schema_version = PAYLOAD_SCHEMA_VERSION
        action = value if key == "action" else self.__dict__.get("action")
        payload = value if key == "payload" else self.__dict__.get("payload")
        if isinstance(action, str) and isinstance(payload, dict):
            validate_proposal_payload(action, payload)
        return value

    @validates("result")
    def _validate_result(self, key: str, value: Any) -> Any:
        self.result_schema_version = RESULT_SCHEMA_VERSION
        if value is None:
            return None
        return validate_proposal_result(value)


class ChatProposalAnchor(Base):
    """One ordered anchored text edit stored with a proposal (plan 81 D)."""

    __tablename__ = "chat_proposal_anchors"
    __table_args__ = (
        Index("ix_chat_proposal_anchors_proposal", "proposal_id", "position"),
        vocab_check("op", ProposalAnchorOp),
    )

    proposal_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("chat_proposals.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    op: Mapped[str] = mapped_column(String(10))
    find_text: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, default="")

    proposal: Mapped[ChatProposal] = relationship(back_populates="anchors")


class QuizmeAnswer(Base):
    __tablename__ = "quizme_answers"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
