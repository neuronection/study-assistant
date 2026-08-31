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
    Integer as Integer,
)
from .core import (
    Mapped as Mapped,
)
from .core import (
    String as String,
)
from .core import (
    datetime as datetime,
)
from .core import (
    mapped_column as mapped_column,
)
from .core import (
    utcnow as utcnow,
)
from .core import (
    uuid4 as uuid4,
)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["node_id", "course_id"], ["tree_nodes.id", "tree_nodes.course_id"]
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), index=True)
    node_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300), default="New chat")
    use_embeddings: Mapped[bool | None] = mapped_column(Boolean)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid4())
    )
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    mention_registry: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    active_root_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, index=True)
    active_child_id: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    mentions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    reads: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    grounded: Mapped[bool | None] = mapped_column(Boolean)
    state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    warnings: Mapped[list[str] | None] = mapped_column(JSON)
    trace: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ChatProposal(Base):
    __tablename__ = "chat_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id"), index=True
    )
    action: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
