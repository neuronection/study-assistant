"""`profiles.preferences` keeps its pass-through JSON shape with a contract.

The document is shared with extension-owned sections (`mcp`, search
providers) that the product does not own, so it stays one JSON column; the
known keys are typed here and validated at the preferences API edge before
a write (ADR-200).
"""

from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict


class DiscoverySitePreference(TypedDict, total=False):
    site: str
    label: str | None
    kind: str


type DiscoveryPreferences = dict[str, Any]


class ProfilePreferences(TypedDict, total=False):
    use_embeddings: bool
    ocr_image_max_edge: int
    discovery: DiscoveryPreferences
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


class PreferencesDocument(BaseModel):
    """Known preference keys; extension-owned sections pass through intact."""

    model_config = ConfigDict(extra="allow")

    use_embeddings: bool | None = None
    ocr_image_max_edge: int | None = None
    discovery: _DiscoveryDocument | None = None


class PreferencesError(ValueError):
    pass


def validate_preferences(document: dict[str, Any]) -> dict[str, Any]:
    try:
        PreferencesDocument.model_validate(document)
    except ValueError as error:
        raise PreferencesError(str(error)) from error
    return document
