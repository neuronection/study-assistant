from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.profile_context import active_profile_id
from ..domain.models import Profile


def ensure_default_profile(session: Session) -> Profile:
    requested = active_profile_id()
    if requested is not None:
        profile = session.get(Profile, requested)
        if profile is not None:
            return profile
    profile = session.scalars(select(Profile).order_by(Profile.id).limit(1)).first()
    if profile is not None:
        return profile
    profile = Profile(name="Default")
    session.add(profile)
    session.commit()
    return profile


def get_profile(session: Session, profile_id: int | None) -> Profile | None:
    if profile_id is None:
        return ensure_default_profile(session)
    return session.get(Profile, profile_id)


def list_profiles(session: Session) -> list[Profile]:
    return list(session.scalars(select(Profile).order_by(Profile.id)))


def create_profile(session: Session, name: str, color: str | None = None) -> Profile:
    profile = Profile(name=name.strip() or "Profile", color=color)
    session.add(profile)
    session.flush()
    return profile
