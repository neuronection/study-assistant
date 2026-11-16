from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...core.vocab import AnchorKind, AnchorSource
from ..payloads import AnchorPayload
from ..schema_contract import vocab_check
from .core import _UUID, JSON, Base, new_uuid, utcnow


class DocumentAnchor(Base):
    __tablename__ = "document_anchors"
    __table_args__ = (
        Index("ix_document_anchors_material_page", "material_id", "page"),
        Index("ix_document_anchors_profile_created", "profile_id", "created_at"),
        vocab_check("anchor_kind", AnchorKind),
        vocab_check("source", AnchorSource),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    material_id: Mapped[str | None] = mapped_column(
        _UUID, ForeignKey("materials.id", ondelete="CASCADE"), index=True
    )
    anchor_kind: Mapped[str] = mapped_column(String(20))
    page: Mapped[int | None] = mapped_column(Integer)
    quote: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[AnchorPayload] = mapped_column(JSON)
    color: Mapped[str] = mapped_column(String(20), default="yellow")
    note_md: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default=AnchorSource.USER.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    orphaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
