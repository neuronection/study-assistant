"""Per-user profile services (identity-auth §5/§6/§12).

Auto-provisioning rule (§6): a user is never without a profile — user
creation provisions Default in the same transaction, and deleting the
last profile re-provisions it. Exactly one `is_default` per user.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.profile_context import active_profile_id, active_user_id
from ...domain.models import Profile


def _norm(value: str | None) -> str | None:
    """Canonicalize a uuid string (storage is dash-stripped; rows read
    back dashed) so id comparisons never depend on input formatting."""
    if value is None:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def create_profile(
    session: Session,
    user_id: str,
    name: str,
    color: str | None = None,
    *,
    is_default: bool = False,
) -> Profile:
    profile = Profile(
        user_id=user_id,
        name=name.strip() or "Profile",
        color=color,
        is_default=is_default,
    )
    session.add(profile)
    session.flush()
    return profile


def get_owned_profile(session: Session, user_id: str, profile_id: str) -> Profile | None:
    profile = session.get(Profile, _norm(profile_id) or profile_id)
    if profile is None or _norm(profile.user_id) != _norm(user_id):
        return None
    return profile


def list_profiles(session: Session, user_id: str) -> list[Profile]:
    return list(
        session.scalars(
            select(Profile)
            .where(Profile.user_id == user_id)
            .order_by(Profile.created_at, Profile.id)
        )
    )


def get_or_create_default(session: Session, user_id: str) -> Profile:
    profile = session.scalars(
        select(Profile)
        .where(Profile.user_id == user_id, Profile.is_default.is_(True))
        .limit(1)
    ).first()
    if profile is not None:
        return profile
    owned = session.scalars(
        select(Profile)
        .where(Profile.user_id == user_id)
        .order_by(Profile.created_at, Profile.id)
        .limit(1)
    ).first()
    if owned is not None:
        owned.is_default = True
        session.commit()
        return owned
    profile = create_profile(session, user_id, "Default", is_default=True)
    session.commit()
    return profile


def ensure_default_profile(session: Session, user_id: str | None = None) -> Profile:
    """The request's active profile (bound per §15 by the profile
    middleware), else the user's auto-provisioned Default profile.

    Background jobs run outside request context and pass the owning
    user explicitly; with neither, fall back to the oldest profile
    (single-user desktop instances have exactly one).
    """
    owner = _norm(user_id) or _norm(active_user_id())
    requested = _norm(active_profile_id())
    if requested is not None:
        profile = session.get(Profile, requested)
        if profile is not None and (owner is None or _norm(profile.user_id) == owner):
            return profile
    if owner is not None:
        return get_or_create_default(session, owner)
    profile = session.scalars(
        select(Profile).order_by(Profile.created_at, Profile.id).limit(1)
    ).first()
    if profile is not None:
        return profile
    raise RuntimeError("no profile exists — profiles are provisioned with their user")


def set_default_profile(session: Session, user_id: str, profile_id: str) -> Profile | None:
    profile = get_owned_profile(session, user_id, profile_id)
    if profile is None:
        return None
    for other in list_profiles(session, user_id):
        other.is_default = other.id == profile.id
    session.flush()
    return profile


def delete_profile(session: Session, user_id: str, profile_id: str) -> Profile | None:
    """Delete an owned profile (profile-scoped rows cascade — §12).

    Deleting the last profile re-provisions Default (§6); losing the
    default promotes the oldest remaining one. Returns None when the
    profile is unknown or outside the user's ownership (hidden-404).
    """
    profile = get_owned_profile(session, user_id, profile_id)
    if profile is None:
        return None
    was_default = bool(profile.is_default)
    session.delete(profile)
    session.flush()
    remaining = list_profiles(session, user_id)
    if not remaining:
        create_profile(session, user_id, "Default", is_default=True)
    elif was_default:
        remaining[0].is_default = True
    session.commit()
    return profile


def touch_last_used(session: Session, profile_id: str) -> None:
    from datetime import UTC, datetime

    profile = session.get(Profile, _norm(profile_id) or profile_id)
    if profile is not None:
        profile.last_used_at = datetime.now(UTC)
        session.commit()


def last_used_profile(session: Session, user_id: str) -> Profile | None:
    """Desktop fallback (§15): the user's most recently used profile."""
    return session.scalars(
        select(Profile)
        .where(Profile.user_id == user_id)
        .order_by(Profile.last_used_at.desc().nulls_last(), Profile.created_at, Profile.id)
        .limit(1)
    ).first()
