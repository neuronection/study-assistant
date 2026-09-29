import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from nx_auth.deps import get_current_user
from nx_auth.principal import Principal
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.vocab import DiscoveryKind
from ..ocr.imaging import ALLOWED_IMAGE_MAX_EDGE, DEFAULT_IMAGE_MAX_EDGE
from ..search.discovery import DEFAULT_ENABLED
from ..services.platform.profiles import (
    create_profile,
    delete_profile,
    ensure_default_profile,
    get_owned_profile,
    list_profiles,
    set_default_profile,
)
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


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=16)
    is_default: bool | None = None


class ProfileOut(BaseModel):
    id: str
    name: str
    color: str | None
    is_default: bool


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


def _out(profile: Any) -> ProfileOut:
    return ProfileOut(
        id=str(profile.id),
        name=profile.name,
        color=profile.color,
        is_default=bool(profile.is_default),
    )


@router.get("", response_model=list[ProfileOut])
def get_profiles(
    user: Principal = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[ProfileOut]:
    return [_out(profile) for profile in list_profiles(session, user.user_id)]


@router.post("", response_model=ProfileOut, status_code=201)
def add_profile(
    body: ProfileIn,
    user: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProfileOut:
    profile = create_profile(session, user.user_id, body.name, body.color)
    session.commit()
    return _out(profile)


@router.patch("/{profile_id}", response_model=ProfileOut)
def patch_profile(
    profile_id: str,
    body: ProfilePatch,
    user: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProfileOut:
    profile = get_owned_profile(session, user.user_id, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    if body.name is not None:
        profile.name = body.name.strip() or "Profile"
    if body.color is not None or "color" in body.model_fields_set:
        profile.color = body.color
    if body.is_default:
        set_default_profile(session, user.user_id, profile_id)
    session.commit()
    return _out(profile)


@router.delete("/{profile_id}", status_code=204)
def remove_profile(
    profile_id: str,
    user: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    """Delete an owned profile (identity-auth §12): profile-scoped rows
    cascade; deleting the last profile re-provisions Default."""
    if delete_profile(session, user.user_id, profile_id) is None:
        raise HTTPException(status_code=404, detail="profile not found")
