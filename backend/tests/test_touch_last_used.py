"""`touch_last_used` middleware write hygiene (2026-10-13 incident).

The profile touch is a per-request cosmetic write: it must be throttled
(once a minute is plenty for last-used ordering) and fail-soft (a busy
database never 500s an unrelated request). SQLite returns naive
datetimes; stored values are UTC.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.domain.models import Profile
from app.services.platform.profiles import touch_last_used


def _profile(db_session: Session, owner: Any) -> Profile:
    profile = Profile(user_id=owner.id, name="Default", is_default=True)
    db_session.add(profile)
    db_session.commit()
    return profile


def test_touch_writes_when_stale_or_unset(db_session: Session, owner: Any) -> None:
    profile = _profile(db_session, owner)

    touch_last_used(db_session, profile.id)
    db_session.refresh(profile)
    first = profile.last_used_at
    assert first is not None

    profile.last_used_at = datetime.now(UTC) - timedelta(hours=2)
    db_session.commit()
    touch_last_used(db_session, profile.id)
    db_session.refresh(profile)
    assert profile.last_used_at is not None
    stored = profile.last_used_at
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=UTC)
    assert stored > (first.replace(tzinfo=UTC) if first.tzinfo is None else first)


def test_touch_is_throttled_within_the_interval(db_session: Session, owner: Any) -> None:
    profile = _profile(db_session, owner)
    pinned = datetime.now(UTC) - timedelta(seconds=10)
    profile.last_used_at = pinned
    db_session.commit()

    touch_last_used(db_session, profile.id)
    db_session.refresh(profile)

    stored = profile.last_used_at
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=UTC)
    assert abs((stored - pinned).total_seconds()) < 1


def test_touch_treats_naive_stored_values_as_utc(db_session: Session, owner: Any) -> None:
    profile = _profile(db_session, owner)
    naive_recent = datetime.utcnow() - timedelta(seconds=5)
    profile.last_used_at = naive_recent
    db_session.commit()

    touch_last_used(db_session, profile.id)
    db_session.refresh(profile)

    stored = profile.last_used_at
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=UTC)
    assert (stored - naive_recent.replace(tzinfo=UTC)).total_seconds() < 60


def test_touch_fails_soft_when_the_database_is_busy(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _profile(db_session, owner)
    profile.last_used_at = None
    db_session.commit()

    def busy_commit(self: Any) -> None:
        raise OperationalError("UPDATE profiles", {}, Exception("database is locked"))

    monkeypatch.setattr(Session, "commit", busy_commit)

    touch_last_used(db_session, profile.id)

    monkeypatch.undo()
    db_session.rollback()
    fresh = db_session.get(Profile, profile.id)
    assert fresh is not None and fresh.last_used_at is None


def test_touch_ignores_unknown_profile(db_session: Session) -> None:
    touch_last_used(db_session, "00000000-0000-0000-0000-000000000000")
