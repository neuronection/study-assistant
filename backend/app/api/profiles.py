from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..services.profiles import create_profile, ensure_default_profile, list_profiles
from .deps import get_session

router = APIRouter(prefix="/profiles", tags=["profiles"])


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=16)


class ProfileOut(BaseModel):
    id: int
    name: str
    color: str | None


class PreferencesOut(BaseModel):
    use_embeddings: bool = True


class PreferencesIn(BaseModel):
    use_embeddings: bool


def _preferences(profile: Any) -> PreferencesOut:
    prefs = profile.preferences or {}
    return PreferencesOut(use_embeddings=bool(prefs.get("use_embeddings", True)))


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(session: Session = Depends(get_session)) -> PreferencesOut:
    return _preferences(ensure_default_profile(session))


@router.put("/preferences", response_model=PreferencesOut)
def update_preferences(
    body: PreferencesIn, session: Session = Depends(get_session)
) -> PreferencesOut:
    profile = ensure_default_profile(session)
    prefs = dict(profile.preferences or {})
    prefs["use_embeddings"] = body.use_embeddings
    profile.preferences = prefs
    session.commit()
    return _preferences(profile)


@router.get("", response_model=list[ProfileOut])
def get_profiles(session: Session = Depends(get_session)) -> list[ProfileOut]:
    return [
        ProfileOut(id=profile.id, name=profile.name, color=profile.color)
        for profile in list_profiles(session)
    ]


@router.post("", response_model=ProfileOut, status_code=201)
def add_profile(
    body: ProfileIn, session: Session = Depends(get_session)
) -> ProfileOut:
    profile = create_profile(session, body.name, body.color)
    session.commit()
    return ProfileOut(id=profile.id, name=profile.name, color=profile.color)


@router.delete("/{profile_id}", status_code=204)
def remove_profile(profile_id: int, session: Session = Depends(get_session)) -> None:
    from sqlalchemy.exc import IntegrityError

    from ..services.profiles import list_profiles

    profiles = list_profiles(session)
    if len(profiles) <= 1:
        raise HTTPException(status_code=422, detail="cannot delete the last profile")
    profile = next((entry for entry in profiles if entry.id == profile_id), None)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    if profile_id == profiles[0].id and len(profiles) > 1:
        raise HTTPException(status_code=422, detail="cannot delete the default profile")
    try:
        session.delete(profile)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=422,
            detail="profile still has content (courses, notes, cards) — delete those first",
        ) from error
