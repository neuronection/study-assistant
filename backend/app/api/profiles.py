import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.vocab import DiscoveryKind
from ..ocr.imaging import ALLOWED_IMAGE_MAX_EDGE, DEFAULT_IMAGE_MAX_EDGE
from ..search.discovery import DEFAULT_ENABLED
from ..services.platform.profiles import create_profile, ensure_default_profile, list_profiles
from .deps import get_session

router = APIRouter(prefix="/profiles", tags=["profiles"])

ENABLED_PROVIDER_PATTERN = r"^(web|youtube|site:.+)$"


class DiscoverySitePreset(BaseModel):
    site: str = Field(min_length=1, max_length=200)
    label: str | None = Field(default=None, max_length=120)
    kind: str = DiscoveryKind.COURSE.value


class DiscoveryPrefsOut(BaseModel):
    enabled: list[str] = Field(default_factory=lambda: list(DEFAULT_ENABLED))
    sites: list[DiscoverySitePreset] = Field(default_factory=list)


class DiscoveryPrefsIn(BaseModel):
    enabled: list[str] | None = None
    sites: list[DiscoverySitePreset] | None = None


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=16)


class ProfileOut(BaseModel):
    id: int
    name: str
    color: str | None


class PreferencesOut(BaseModel):
    use_embeddings: bool = True
    ocr_image_max_edge: int = DEFAULT_IMAGE_MAX_EDGE
    discovery: DiscoveryPrefsOut = Field(default_factory=DiscoveryPrefsOut)


class PreferencesIn(BaseModel):
    use_embeddings: bool | None = None
    ocr_image_max_edge: int | None = None
    discovery: DiscoveryPrefsIn | None = None


def _discovery_prefs(prefs: dict[str, Any]) -> DiscoveryPrefsOut:
    raw = prefs.get("discovery")
    if not isinstance(raw, dict):
        return DiscoveryPrefsOut()
    enabled_raw = raw.get("enabled")
    enabled = (
        [str(entry) for entry in enabled_raw]
        if isinstance(enabled_raw, list)
        else list(DEFAULT_ENABLED)
    )
    sites: list[DiscoverySitePreset] = []
    sites_raw = raw.get("sites")
    if isinstance(sites_raw, list):
        for entry in sites_raw:
            if not isinstance(entry, dict):
                continue
            site = str(entry.get("site", "")).strip()
            if not site:
                continue
            kind = str(entry.get("kind") or DiscoveryKind.COURSE.value)
            if kind not in {item.value for item in DiscoveryKind}:
                kind = DiscoveryKind.COURSE.value
            label = entry.get("label")
            sites.append(
                DiscoverySitePreset(
                    site=site,
                    label=str(label)[:120] if label else None,
                    kind=kind,
                )
            )
    return DiscoveryPrefsOut(enabled=enabled, sites=sites)


def _preferences(profile: Any) -> PreferencesOut:
    prefs = profile.preferences or {}
    max_edge = prefs.get("ocr_image_max_edge", DEFAULT_IMAGE_MAX_EDGE)
    if max_edge not in ALLOWED_IMAGE_MAX_EDGE:
        max_edge = DEFAULT_IMAGE_MAX_EDGE
    return PreferencesOut(
        use_embeddings=bool(prefs.get("use_embeddings", True)),
        ocr_image_max_edge=int(max_edge),
        discovery=_discovery_prefs(prefs),
    )


def _validated_discovery(body: DiscoveryPrefsIn) -> dict[str, Any]:
    section: dict[str, Any] = {}
    if body.enabled is not None:
        for entry in body.enabled:
            if not re.match(ENABLED_PROVIDER_PATTERN, entry):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "discovery enabled entries must be 'web', 'youtube' "
                        f"or 'site:<domain>' — got '{entry}'"
                    ),
                )
        section["enabled"] = list(body.enabled)
    if body.sites is not None:
        allowed_kinds = {item.value for item in DiscoveryKind}
        for preset in body.sites:
            if preset.kind not in allowed_kinds:
                raise HTTPException(
                    status_code=422,
                    detail=f"unknown discovery kind '{preset.kind}'",
                )
        section["sites"] = [
            {
                "site": preset.site.strip(),
                "label": (preset.label or "").strip() or None,
                "kind": preset.kind,
            }
            for preset in body.sites
        ]
    return section


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(session: Session = Depends(get_session)) -> PreferencesOut:
    return _preferences(ensure_default_profile(session))


@router.put("/preferences", response_model=PreferencesOut)
def update_preferences(
    body: PreferencesIn, session: Session = Depends(get_session)
) -> PreferencesOut:
    profile = ensure_default_profile(session)
    prefs = dict(profile.preferences or {})
    if body.use_embeddings is not None:
        prefs["use_embeddings"] = body.use_embeddings
    if body.ocr_image_max_edge is not None:
        if body.ocr_image_max_edge not in ALLOWED_IMAGE_MAX_EDGE:
            allowed = ", ".join(str(value) for value in sorted(ALLOWED_IMAGE_MAX_EDGE))
            raise HTTPException(
                status_code=422,
                detail=f"ocr_image_max_edge must be one of: {allowed}",
            )
        prefs["ocr_image_max_edge"] = body.ocr_image_max_edge
    if body.discovery is not None:
        existing = prefs.get("discovery")
        section: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
        section.update(_validated_discovery(body.discovery))
        prefs["discovery"] = section
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

    from ..services.platform.profiles import list_profiles

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
