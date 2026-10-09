"""Secrets at rest — keyring-held values sealed with the family cipher.

The at-rest machinery is shared family code: ``nx_auth.atrest``
(ADR-0027, plan 19) — this module is study's adapter over it. Values
written to the OS keyring (service ``StudyAssistant``) are sealed under
the auth-kit KeyRing ``data_key`` (``SA_DATA_KEY``) as
``enc::<fernet-token>`` strings: the keyring stays the only storage
(never files, env blocks or the database) and a keyring dump alone no
longer exposes the plaintext. ``SA_DATA_KEY_PREVIOUS`` (comma-separated)
holds prior keys for decryption-only rotation — new writes always seal
under ``SA_DATA_KEY`` (runbook: docs/dev/security.md "Rotating the
at-rest key").

Reads are plaintext-tolerant by design (plan 19 D4): study's values are
keyring-held — there is no DB ciphertext surface — so pre-adoption
plaintext entries return verbatim and no backfill is required.
Ciphertext that does not verify under the key ring yields ``None`` —
never a guess.
"""

import contextlib
from functools import lru_cache

import keyring
from nx_auth.atrest import SecretCipher, decrypt_secret, encrypt_secret, is_encrypted

from app.core.keys import data_key_previous
from app.core.keys import keyring as key_ring

SERVICE = "StudyAssistant"


@lru_cache(maxsize=1)
def _cipher() -> SecretCipher:
    """Rotation-aware cipher over the KeyRing data_key (+ prior keys)."""
    return SecretCipher(key_ring().data_key, previous=data_key_previous())


def reset_secret_caches() -> None:
    """Drop the cached cipher (tests swap key material between cases)."""
    _cipher.cache_clear()


def get_secret(ref: str) -> str | None:
    try:
        value = keyring.get_password(SERVICE, ref)
    except Exception:
        return None
    if not value or not is_encrypted(value):
        return value
    try:
        return decrypt_secret(value, _cipher())
    except ValueError:
        return None


def set_secret(ref: str, value: str) -> None:
    sealed = encrypt_secret(value, _cipher())
    assert sealed is not None
    try:
        keyring.set_password(SERVICE, ref, sealed)
    except Exception as error:
        raise RuntimeError(
            "no usable OS keyring backend — the API key cannot be stored locally"
        ) from error


def delete_secret(ref: str) -> None:
    with contextlib.suppress(Exception):
        keyring.delete_password(SERVICE, ref)
