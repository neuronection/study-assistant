"""Study's adapters for the family auth-kit protocols (plan 16 S4/S2b).

Study owns its identity models (`app.domain/models/identity.py`) so its
single metadata/registry stays self-contained — the kit's *stores* are
the reference implementation, these adapters are the contract-correct
port. Profile provisioning is wired (S2b): user creation provisions the
Default profile in the same transaction (identity-auth §6).
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime

from nx_auth.audit import AuditEvent, AuditSink
from nx_auth.lockout import ensure_aware
from nx_auth.protocols import EmailAlreadyExists, SessionRecord, UserRecord
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.models import AuditEvent as AuditEventRow
from app.domain.models import AuthSession as AuthSessionRow
from app.domain.models import Course as CourseRow
from app.domain.models import InstanceSetting as InstanceSettingRow
from app.domain.models import Material as MaterialRow
from app.domain.models import Note as NoteRow
from app.domain.models import Profile as ProfileRow
from app.domain.models import User as UserRow

_EPOCH: datetime = datetime(1970, 1, 1, tzinfo=UTC)


def _record(row: UserRow) -> UserRecord:
    return UserRecord(
        id=str(row.id),
        email=str(row.email),
        password_hash=row.password_hash,
        full_name=row.full_name,
        is_active=bool(row.is_active),
        is_admin=bool(row.is_admin),
        failed_login_attempts=int(row.failed_login_attempts),
        locked_until=ensure_aware(row.locked_until),
        token_version=int(row.token_version),
        created_at=ensure_aware(row.created_at),
    )


def _session(row: AuthSessionRow) -> SessionRecord:
    return SessionRecord(
        id=str(row.id),
        user_id=str(row.user_id),
        refresh_jti_hash=str(row.refresh_jti_hash),
        expires_at=ensure_aware(row.expires_at) or _EPOCH,
        absolute_expires_at=ensure_aware(row.absolute_expires_at) or _EPOCH,
        revoked_at=ensure_aware(row.revoked_at),
        client_label=row.client_label,
        created_at=ensure_aware(row.created_at),
    )


class StudyUserStore:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory
        self._create_lock = threading.Lock()

    def get(self, user_id: str) -> UserRecord | None:
        with self._factory() as session:
            row = session.get(UserRow, user_id)
            return _record(row) if row is not None else None

    def get_by_email(self, email: str) -> UserRecord | None:
        with self._factory() as session:
            row = session.scalar(select(UserRow).where(UserRow.email == email.lower()))
            return _record(row) if row is not None else None

    def count(self) -> int:
        with self._factory() as session:
            return int(session.scalar(select(func.count()).select_from(UserRow)) or 0)

    def create(
        self,
        *,
        email: str,
        password_hash: str | None,
        full_name: str = "",
        is_admin: bool = False,
        user_id: str | None = None,
    ) -> UserRecord:
        normalized = email.lower().strip()
        with self._create_lock, self._factory() as session:
            if session.scalar(select(UserRow.id).where(UserRow.email == normalized)):
                raise EmailAlreadyExists(normalized)
            first = session.scalar(select(func.count()).select_from(UserRow)) or 0
            row = UserRow(
                id=user_id if user_id is not None else str(uuid.uuid4()),
                email=normalized,
                password_hash=password_hash,
                full_name=full_name,
                is_admin=is_admin or int(first) == 0,
            )
            session.add(row)
            session.flush()  # the profile FK needs the user row visible
            # identity-auth §6: Default profile in the same transaction —
            # a user is never without a profile.
            session.add(
                ProfileRow(id=str(uuid.uuid4()), user_id=row.id, name="Default", is_default=True)
            )
            session.commit()
            session.refresh(row)
            return _record(row)

    def set_login_failures(
        self, user_id: str, failed: int, locked_until: datetime | None
    ) -> None:
        with self._factory() as session:
            row = session.get(UserRow, user_id)
            if row is not None:
                row.failed_login_attempts = failed
                row.locked_until = locked_until
                row.updated_at = datetime.now(UTC)
                session.commit()

    def reset_login_failures(self, user_id: str) -> None:
        self.set_login_failures(user_id, 0, None)

    def bump_token_version(self, user_id: str) -> int:
        with self._factory() as session:
            row = session.get(UserRow, user_id)
            if row is None:
                return 0
            updated = int(row.token_version) + 1
            row.token_version = updated
            row.updated_at = datetime.now(UTC)
            session.commit()
            return updated

    def set_password(self, user_id: str, password_hash: str) -> None:
        with self._factory() as session:
            row = session.get(UserRow, user_id)
            if row is not None:
                row.password_hash = password_hash
                row.updated_at = datetime.now(UTC)
                session.commit()

    def list(self) -> list[UserRecord]:
        with self._factory() as session:
            rows = session.scalars(
                select(UserRow).order_by(UserRow.created_at.asc(), UserRow.id.asc())
            ).all()
            return [_record(row) for row in rows]

    def set_active(self, user_id: str, is_active: bool) -> None:
        with self._factory() as session:
            row = session.get(UserRow, user_id)
            if row is not None:
                row.is_active = is_active
                row.updated_at = datetime.now(UTC)
                session.commit()

    def set_admin(self, user_id: str, is_admin: bool) -> None:
        with self._factory() as session:
            row = session.get(UserRow, user_id)
            if row is not None:
                row.is_admin = is_admin
                row.updated_at = datetime.now(UTC)
                session.commit()

    def count_admins(self) -> int:
        with self._factory() as session:
            return int(
                session.scalar(
                    select(func.count()).select_from(UserRow).where(UserRow.is_admin.is_(True))
                )
                or 0
            )

    def delete(self, user_id: str) -> None:
        # identity-auth §12 "cascade delete (DB-level ON DELETE)" — the
        # engine runs with `PRAGMA foreign_keys=ON` (storage/db.py), so
        # profiles, auth_sessions, and profile-scoped content follow the
        # user row through the FK cascades.
        with self._factory() as session:
            row = session.get(UserRow, user_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def activity_counts(self) -> dict[str, int]:
        """Product-defined activity (identity-auth §12): profile-scoped
        content rows (courses + materials + notes) per user — three
        grouped index scans joined through `profiles.user_id`."""
        counts: dict[str, int] = {}
        with self._factory() as session:
            for model in (CourseRow, MaterialRow, NoteRow):
                rows = session.execute(
                    select(ProfileRow.user_id, func.count())
                    .select_from(ProfileRow)
                    .join(model, model.profile_id == ProfileRow.id)
                    .group_by(ProfileRow.user_id)
                ).all()
                for user_id, count in rows:
                    key = str(user_id)
                    counts[key] = counts.get(key, 0) + int(count)
        return counts


class StudyProfileStore:
    """`nx_auth.protocols.ProfileStore` adapter (kit-side provisioning)."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def create(
        self,
        *,
        user_id: str,
        name: str,
        is_default: bool,
        preferences: dict[str, object] | None = None,
    ) -> str:
        with self._factory() as session:
            row = ProfileRow(
                user_id=user_id,
                name=name,
                is_default=is_default,
                preferences=dict(preferences) if preferences else None,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return str(row.id)

    def count_for(self, user_id: str) -> int:
        with self._factory() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(ProfileRow)
                    .where(ProfileRow.user_id == user_id)
                )
                or 0
            )


class StudySessionStore:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def create(
        self,
        *,
        user_id: str,
        refresh_jti_hash: str,
        expires_at: datetime,
        absolute_expires_at: datetime,
        client_label: str = "",
    ) -> str:
        row = AuthSessionRow(
            id=str(uuid.uuid4()),
            user_id=user_id,
            refresh_jti_hash=refresh_jti_hash,
            expires_at=expires_at,
            absolute_expires_at=absolute_expires_at,
            client_label=client_label,
        )
        with self._factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return str(row.id)

    def get(self, family_id: str) -> SessionRecord | None:
        with self._factory() as session:
            row = session.get(AuthSessionRow, family_id)
            return _session(row) if row is not None else None

    def rotate(self, family_id: str, refresh_jti_hash: str, expires_at: datetime) -> None:
        with self._factory() as session:
            row = session.get(AuthSessionRow, family_id)
            if row is not None and row.revoked_at is None:
                row.refresh_jti_hash = refresh_jti_hash
                row.expires_at = expires_at
                session.commit()

    def revoke(self, family_id: str) -> None:
        with self._factory() as session:
            row = session.get(AuthSessionRow, family_id)
            if row is not None and row.revoked_at is None:
                row.revoked_at = datetime.now(UTC)
                session.commit()

    def revoke_all_for_user(self, user_id: str) -> int:
        with self._factory() as session:
            rows = session.scalars(
                select(AuthSessionRow).where(
                    AuthSessionRow.user_id == user_id, AuthSessionRow.revoked_at.is_(None)
                )
            ).all()
            for row in rows:
                row.revoked_at = datetime.now(UTC)
            session.commit()
            return len(rows)

    def list_for_user(self, user_id: str) -> list[SessionRecord]:
        with self._factory() as session:
            rows = session.scalars(
                select(AuthSessionRow)
                .where(AuthSessionRow.user_id == user_id)
                .order_by(AuthSessionRow.created_at.desc(), AuthSessionRow.id.desc())
            ).all()
            return [_session(row) for row in rows]


class StudyInstanceStore:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def get(self, key: str) -> str | None:
        with self._factory() as session:
            row = session.get(InstanceSettingRow, key)
            return str(row.value) if row is not None else None

    def set(self, key: str, value: str) -> None:
        with self._factory() as session:
            row = session.get(InstanceSettingRow, key)
            if row is None:
                session.add(InstanceSettingRow(key=key, value=value))
            else:
                row.value = value
                row.updated_at = datetime.now(UTC)
            session.commit()


class StudyAuditSink(AuditSink):
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def record(self, event: AuditEvent) -> None:
        row = AuditEventRow(
            actor=event.actor,
            action=event.action,
            resource=event.resource,
            tenant_id=event.tenant_id,
            outcome=event.outcome,
            created_at=event.timestamp(),
        )
        with self._factory() as session:
            session.add(row)
            session.commit()
