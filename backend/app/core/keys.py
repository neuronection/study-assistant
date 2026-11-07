"""Per-instance key material: the identity-auth §8 KeyRing family.

One resolution shape for the three per-purpose secrets — the kit's
``KeyRing.load_for`` (ADR-0028 §5): Settings-backed pins
(``SA_SESSION_KEY``/``SA_REFRESH_KEY``/``SA_DATA_KEY``, all three or
none, from env or the deployment `.env`) > the generated 0600
``auth_keys.json`` in the config dir > generate.

``session_key`` signs session JWTs, ``refresh_key`` signs refresh JWTs,
``data_key`` seals secrets at rest (``app.core.secrets``, cipher
``nx_auth.atrest``) and never signs anything. **No key is derived from
another.** ``install_identity`` resolves the signing ring from the same
``load_for`` inputs; both read the same ``auth_keys.json``.
"""

from __future__ import annotations

from functools import lru_cache

from nx_auth import KeyRing

from app.core.config import Settings, get_settings


@lru_cache(maxsize=1)
def keyring() -> KeyRing:
    """The at-rest KeyRing (cached — one ring per process).

    Resolves the key material ``app.core.secrets`` seals under; the
    auth-kit install reads the same config-dir key file for signing.
    Partial pins fail closed (the kit's §8 error).
    """
    settings = get_settings()
    return KeyRing.load_for(
        "SA",
        settings.config_dir,
        pinned=(settings.session_key, settings.refresh_key, settings.data_key),
    )


def data_key_previous(settings: Settings | None = None) -> list[str]:
    """Prior DATA_KEY values for decryption-only rotation
    (`SA_DATA_KEY_PREVIOUS`, comma-separated).

    Empty entries are dropped. New writes always seal under the primary
    `SA_DATA_KEY`; the rotation runbook lives in docs/dev/security.md.
    """
    source = settings if settings is not None else get_settings()
    raw = source.data_key_previous or ""
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def reset_keyring_cache() -> None:
    """Drop the cached ring (tests swap key material between cases)."""
    keyring.cache_clear()
