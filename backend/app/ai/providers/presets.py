from typing import Any

from .presets_data import KEY_PREFIX_HINTS as _KEY_PREFIX_HINT_DATA
from .presets_data import PRESET_ORDER as _PRESET_ORDER
from .presets_data import PRESETS as _PRESET_DATA

PRESET_ORDER: tuple[str, ...] = tuple(_PRESET_ORDER)

LOCAL_BASE_URL_OVERRIDES: dict[str, str] = {
    "gemini": "https://generativelanguage.googleapis.com",
}

_PRESET_FIELDS = (
    "name",
    "wire_type",
    "base_url",
    "fixed_base",
    "local",
    "key_url",
    "preferred_model",
    "curated_models",
    "stt_model",
    "decision_models",
    "decision_default",
    "provisional",
    "steps",
    "free_tier_note",
)


def _build(key: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row["name"],
        "type": row["wire_type"],
        "base_url": LOCAL_BASE_URL_OVERRIDES.get(key, row["base_url"]),
        "fixed_base": row["fixed_base"],
        "local": row["local"],
        "key_url": row["key_url"],
        "preferred_model": row["preferred_model"],
        "curated_models": row["curated_models"],
        "stt_model": row["stt_model"],
        "decision_models": row["decision_models"],
        "decision_default": row["decision_default"],
        "provisional": row["provisional"],
        "steps": row["steps"],
        "free_tier_note": row["free_tier_note"],
    }


ALL_PRESETS: dict[str, dict[str, Any]] = {
    key: _build(key, row) for key, row in _PRESET_DATA.items()
}

SETUP_PRESETS: dict[str, dict[str, Any]] = {
    key: ALL_PRESETS[key] for key in _PRESET_ORDER if key in ALL_PRESETS
}

PRESETS: dict[str, dict[str, Any]] = SETUP_PRESETS

KEY_PREFIX_HINTS: tuple[dict[str, str], ...] = tuple(_KEY_PREFIX_HINT_DATA)


def is_preset_key(key: str) -> bool:
    return key in SETUP_PRESETS


def is_any_preset_key(key: str) -> bool:
    return key in ALL_PRESETS


def guess_preset_for_key(api_key: str | None) -> str | None:
    trimmed = (api_key or "").strip()
    if not trimmed:
        return None
    for hint in KEY_PREFIX_HINTS:
        if trimmed.startswith(hint["prefix"]):
            return hint["preset"]
    return None


def decision_models_for_preset(key: str) -> list[dict[str, Any]]:
    models = ALL_PRESETS.get(key, {}).get("decision_models")
    if not models:
        return []
    return [dict(entry) for entry in models]
