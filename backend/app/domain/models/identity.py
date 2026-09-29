from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ...storage.db import Base as Base
from .core import utcnow as utcnow

_UUID = Uuid(as_uuid=False)
_JSON = JSON().with_variant(JSONB(), "postgresql")


class User(Base):
    """Family-normative `users` (identity-auth §5)."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("oidc_issuer", "oidc_subject"),)

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    oidc_issuer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AuthSession(Base):
    """Family-normative `auth_sessions` — refresh families."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    refresh_jti_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    client_label: Mapped[str] = mapped_column(String(200), default="")
    # Product-added column (identity-auth §5 allows additions): the
    # device list (§12 `GET /api/v1/me/sessions`) shows when each family
    # was created. Nullable — rows predating migration 0067 have none.
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=utcnow
    )


class InstanceSetting(Base):
    """Family-normative `instance_settings` — auth_mode / demo_mode."""

    __tablename__ = "instance_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AuditEvent(Base):
    """Family-normative `audit_events` — append-only to the app role."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=lambda: str(uuid4()))
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource: Mapped[str] = mapped_column(String(500), default="")
    tenant_id: Mapped[str | None] = mapped_column(_UUID, nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


__all__ = ["Any", "AuditEvent", "AuthSession", "InstanceSetting", "User"]
