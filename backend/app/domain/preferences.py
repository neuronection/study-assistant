"""`profiles.preferences` keeps its pass-through JSON shape with a contract.

The document is shared with extension-owned sections (`mcp`, search
providers) that the product does not own, so it stays one JSON column; the
known keys are typed here and validated at the preferences API edge before
a write (ADR-200).
"""

from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class DiscoverySitePreference(TypedDict, total=False):
    site: str
    label: str | None
    kind: str


type DiscoveryPreferences = dict[str, Any]


class PlannerCapacityPreference(TypedDict, total=False):
    minutes: list[int]
    blackout_dates: list[str]
    light_week: bool


class DailyBriefPreference(TypedDict, total=False):
    enabled: bool
    time: str
    length_minutes: int
    voice: str | None


class ProfilePreferences(TypedDict, total=False):
    use_embeddings: bool
    ocr_image_max_edge: int
    discovery: DiscoveryPreferences
    planner_capacity: PlannerCapacityPreference
    daily_brief: DailyBriefPreference
    genesis_task_cap: int
    mcp: dict[str, Any]
    search_providers: list[dict[str, Any]]


class _DiscoverySiteDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    site: str
    label: str | None = None
    kind: str | None = None


class _DiscoveryDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: list[str] | None = None
    sites: list[_DiscoverySiteDocument] | None = None


class _PlannerCapacityDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minutes: list[int] | None = Field(default=None, min_length=7, max_length=7)
    blackout_dates: list[str] | None = None
    light_week: bool | None = None


class _DailyBriefDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    length_minutes: int | None = Field(default=None, ge=1, le=20)
    voice: str | None = Field(default=None, max_length=100)


class PreferencesDocument(BaseModel):
    """Known preference keys; extension-owned sections pass through intact."""

    model_config = ConfigDict(extra="allow")

    use_embeddings: bool | None = None
    ocr_image_max_edge: int | None = None
    discovery: _DiscoveryDocument | None = None
    planner_capacity: _PlannerCapacityDocument | None = None
    daily_brief: _DailyBriefDocument | None = None


class PreferencesError(ValueError):
    pass


def validate_preferences(document: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = PreferencesDocument.model_validate(document)
    except ValueError as error:
        raise PreferencesError(str(error)) from error
    capacity = parsed.planner_capacity
    if (
        capacity is not None
        and capacity.minutes is not None
        and any(minute < 0 or minute > 720 for minute in capacity.minutes)
    ):
        raise PreferencesError("planner minutes must be between 0 and 720")
    return document
