from typing import Any

from .presets_data import KEY_PREFIX_HINTS as _KEY_PREFIX_HINT_DATA
from .presets_data import PRESET_ORDER as _PRESET_ORDER
from .presets_data import PRESETS as _PRESET_DATA

PRESET_ORDER: tuple[str, ...] = tuple(_PRESET_ORDER)

LOCAL_BASE_URL_OVERRIDES: dict[str, str] = {
    "gemini": "https://generativelanguage.googleapis.com",
}

SETUP_PRESETS: dict[str, dict[str, Any]] = {
    key: {
        "name": row["name"],
        "type": row["wire_type"],
        "base_url": LOCAL_BASE_URL_OVERRIDES.get(key, row["base_url"]),
        "fixed_base": row["fixed_base"],
        "local": row["local"],
        "key_url": row["key_url"],
        "preferred_model": row["preferred_model"],
        "curated_models": row["curated_models"],
        "stt_model": row["stt_model"],
        "steps": row["steps"],
        "free_tier_note": row["free_tier_note"],
    }
    for key in _PRESET_ORDER
    for row in (_PRESET_DATA[key],)
}

PRESETS: dict[str, dict[str, Any]] = SETUP_PRESETS

KEY_PREFIX_HINTS: tuple[dict[str, str], ...] = tuple(_KEY_PREFIX_HINT_DATA)


def is_preset_key(key: str) -> bool:
    return key in SETUP_PRESETS


def guess_preset_for_key(api_key: str | None) -> str | None:
    trimmed = (api_key or "").strip()
    if not trimmed:
        return None
    for hint in KEY_PREFIX_HINTS:
        if trimmed.startswith(hint["prefix"]):
            return hint["preset"]
    return None
