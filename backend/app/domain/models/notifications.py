"""The notification funnel store (plan 51 Q3c3a).

Study's notification center was a computed aggregate (ADR-151); retrieval
operations need durable, deduped alerts that survive a restart and can be
recovered when their condition clears. This module adds only the two tables
that funnel needs — the boot-seeded kind registry and the event rows — so
there is still one delivery path (the existing bell/aggregate), not a second
notification system.

Alert payloads carry ids/counts/scores/reasons only. They never carry
prompt, document, query or generated text.
"""

from ...core.vocab import NotificationKind, NotificationSeverity
from ..payloads import NotificationPayload, NotificationSourceRef, StringList
from ..schema_contract import vocab_check
from .core import (
    _UUID,
    JSON,
    Base,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Mapped,
    String,
    Text,
    datetime,
    mapped_column,
    new_uuid,
    text,
    utcnow,
)


class NotificationKindRow(Base):
    """One boot-seeded alert kind; unknown kinds notify nobody."""

    __tablename__ = "notification_kinds"
    __table_args__ = (
        vocab_check("key", NotificationKind),
        vocab_check("severity", NotificationSeverity),
    )

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    severity: Mapped[str] = mapped_column(
        String(20),
        default=NotificationSeverity.WARNING.value,
        server_default=NotificationSeverity.WARNING.value,
    )
    admin_only: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    default_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    """One deduped alert event; recipients are admin user ids, never text."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_created_at", "created_at"),
        Index("ix_notifications_kind_created", "kind", "created_at"),
        Index(
            "uq_notifications_dedup_key",
            "dedup_key",
            unique=True,
            sqlite_where=text("dedup_key IS NOT NULL"),
            postgresql_where=text("dedup_key IS NOT NULL"),
        ),
        vocab_check("severity", NotificationSeverity),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    kind: Mapped[str] = mapped_column(
        String(80), ForeignKey("notification_kinds.key", ondelete="CASCADE"), index=True
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        default=NotificationSeverity.WARNING.value,
        server_default=NotificationSeverity.WARNING.value,
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    payload: Mapped[NotificationPayload] = mapped_column(JSON, default=dict)
    source_ref: Mapped[NotificationSourceRef | None] = mapped_column(JSON, nullable=True)
    recipients: Mapped[StringList] = mapped_column(JSON, default=list)
    dedup_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dedup_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = ["Notification", "NotificationKindRow"]
