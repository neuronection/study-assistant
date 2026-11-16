from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...core.vocab import CaptureKind, CaptureScope, CaptureStatus
from ..payloads import CaptureMeta
from ..schema_contract import vocab_check
from .core import _UUID, JSON, Base, new_uuid, text, utcnow


class CaptureStaging(Base):
    __tablename__ = "capture_staging"
    __table_args__ = (
        Index("ix_capture_staging_profile_status", "profile_id", "status"),
        Index(
            "uq_capture_staging_client_op",
            "profile_id",
            "client_op_id",
            unique=True,
            sqlite_where=text("client_op_id IS NOT NULL"),
            postgresql_where=text("client_op_id IS NOT NULL"),
        ),
        vocab_check("source_kind", CaptureKind),
        vocab_check("status", CaptureStatus),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    source_kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=CaptureStatus.STAGED.value)
    filename: Mapped[str] = mapped_column(String(500))
    mime: Mapped[str | None] = mapped_column(String(120))
    blob_sha: Mapped[str] = mapped_column(ForeignKey("blobs.sha256", ondelete="RESTRICT"))
    byte_size: Mapped[int] = mapped_column(Integer)
    group_id: Mapped[str | None] = mapped_column(String(64), index=True)
    client_op_id: Mapped[str | None] = mapped_column(String(120))
    meta: Mapped[CaptureMeta | None] = mapped_column(JSON)
    material_id: Mapped[str | None] = mapped_column(
        _UUID, ForeignKey("materials.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CaptureToken(Base):
    __tablename__ = "capture_tokens"
    __table_args__ = (
        Index("uq_capture_tokens_hash", "token_hash", unique=True),
        Index("ix_capture_tokens_profile_revoked", "profile_id", "revoked_at"),
        vocab_check("scope", CaptureScope),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
