"""Secrets at rest — the thin study adapter over ``nx_auth.secrets``.

Storage, backend selection and sealing are family code (plan 60 D2,
ADR-0027/ADR-0028); this module keeps only study's frozen policy: the
keyring service name, the sealed-file location and the failure text the
deployment tests and call sites already speak.

Values are sealed with the auth-kit ``SecretCipher`` built from study's §8
``KeyRing`` data key (``SA_DATA_KEY``, plus ``SA_DATA_KEY_PREVIOUS`` for
decryption-only rotation) and stored as ``enc::<fernet-token>``, so a
storage dump alone never exposes the plaintext.

**Storage is deployment-selected** (plan 52 web/desktop fix):

* **OS keyring** — the desktop default (``service="StudyAssistant"``).
* **Sealed file** (``<data_dir>/secrets.json``, 0600) — the server/Docker
  default, where no keyring exists. Same cipher, so the file is useless
  without ``SA_DATA_KEY``.

The keyring is used **only if it round-trips a probe write**; a null backend
accepts writes and silently discards them, so a backend that does not
round-trip is rejected outright and the sealed file takes over. (The
keyring library's own ``PYTHON_KEYRING_BACKEND`` knob selects which backend
it resolves — headless tests pin it — but the probe is what decides trust.)
If neither works, writes **fail closed** — no plaintext fallback, ever. The
sealed file is also a read fallback when the keyring is selected, so a host
that switched backends still resolves its previous entries.

Reads are plaintext-tolerant by design (plan 19 D4): study's values are
keyring/file-held — there is no DB ciphertext surface — so pre-adoption
plaintext entries return verbatim and no backfill is required. Ciphertext
that does not verify under the key ring yields ``None`` — never a guess.

Reads are also **lazy about key material**: a missing slot and an unsealed
plaintext entry resolve without the cipher ever being constructed, so a
host with no (or unwritable) key material keeps answering them exactly as
before adoption. Only an ``enc::`` value reaches for the ring; when the
ring cannot be resolved there (no/partial ``SA_*_KEY`` pins, an unwritable
config dir) that read fails closed with ``None`` — never a crash, never a
guess. Writes stay eager: ``set_secret`` without key material still fails
closed.

Two semantic deltas from the pre-adoption backend: a stored empty value
(``""``) resolves to ``None``, and ``set_secret("")`` /
``delete_secret("")`` raise ``ValueError`` (the pre-adoption backend stored
under the empty ref / silently did nothing) — call sites use non-empty
refs.

``SA_DATA_KEY_PREVIOUS`` (comma-separated) holds prior keys for
decryption-only rotation — new writes always seal under ``SA_DATA_KEY``
(runbook: docs/dev/security.md "Rotating the at-rest key").
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import cast

import nx_auth.secrets as kit_secrets
from nx_auth.secrets import SecretCipher, SecretStoreUnavailable

from app.core.keys import data_key_previous
from app.core.keys import keyring as key_ring

SERVICE = "StudyAssistant"

#: The pre-adoption fail-closed message; deployment tests and operator
#: docs match on "fail closed".
_UNAVAILABLE = (
    "no usable secret store: the OS keyring is unavailable and the sealed "
    "file could not be written — refusing to store the credential anywhere "
    "else (fail closed, no plaintext fallback)"
)


def _store_path() -> Path:
    """The sealed-file location, resolved per call (tests swap ``data_dir``)."""
    from app.core.config import get_settings

    return Path(get_settings().data_dir) / "secrets.json"


@lru_cache(maxsize=1)
def _cipher() -> SecretCipher:
    """Rotation-aware cipher over the KeyRing data_key (+ prior keys).

    Built once and cached: key derivation on every ``get_secret`` /
    ``set_secret`` is a per-request cost. ``reset_secret_caches`` drops it
    when tests swap key material.
    """
    return kit_secrets.cipher(
        data_key=key_ring().data_key,
        previous=data_key_previous(),
    )


def cipher() -> SecretCipher:
    """The at-rest cipher, for callers that seal their own envelopes.

    ``nx_auth.oauth``'s ``TokenVault`` wraps each binding's token set in a
    ``context="oauth:<binding-id>"`` envelope (ADR-0052 §2) before storage —
    it needs the same rotation-aware key ring this module uses. Exposed so
    the vault never reaches for a second key source.
    """
    return _cipher()


def reset_secret_caches() -> None:
    """Drop the cached cipher and the kit's backend selection."""
    _cipher.cache_clear()
    kit_secrets.reset_caches()


class _LazySealer:
    """Read-path sealer — the key ring is touched only when a value must open.

    ``nx_auth.secrets.get`` invokes the sealer only for a stored ``enc::``
    value, so a missing slot and an unsealed plaintext entry never construct a
    cipher. Study's pre-adoption reader had that same shape; the adoption's
    eager ``sealer=_cipher()`` made every read — including one for an absent
    slot — depend on resolvable key material.

    Only ``decrypt_raw`` is implemented: a read-only sealer is never used to
    seal. Unresolvable key material becomes ``ValueError`` so the kit's read
    path answers ``None`` (its documented fail-closed branch) instead of
    propagating a key-ring error out of a lookup.
    """

    def decrypt_raw(self, token: str) -> str:
        try:
            ring_cipher = _cipher()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(
                "the at-rest data key is unavailable, so a sealed secret "
                "cannot be opened on this host"
            ) from exc
        return ring_cipher.decrypt_raw(token)


# The kit types ``sealer`` as ``SecretCipher``; this proxy carries only the
# ``decrypt_raw`` surface ``get`` uses, and deferring that resolution is the
# whole point (see ``_LazySealer``).
_READ_SEALER = cast("SecretCipher", _LazySealer())


def store_backend() -> str:
    """Which writable backend is live (``keyring`` | ``file`` | ``none``).

    Diagnostics only, never a secret. There is no environment source in
    study (``env_prefix=None``), so ``env`` is never reported.
    """
    return kit_secrets.backend_name(service=SERVICE, store_path=_store_path())


def get_secret(ref: str) -> str | None:
    """Resolve ``ref`` from the keyring, then the sealed file.

    Decrypts an ``enc::`` envelope, returns an unsealed plaintext entry
    verbatim, and answers ``None`` for a missing value, an envelope the key
    ring cannot open, or a sealed value on a host whose key material cannot
    be resolved. A stored empty value resolves to ``None``. Key material is
    resolved only for an ``enc::`` value, so missing and plaintext slots
    never depend on it.
    """
    return kit_secrets.get(
        ref,
        service=SERVICE,
        env_prefix=None,
        store_path=_store_path(),
        sealer=_READ_SEALER,
    )


def set_secret(ref: str, value: str) -> None:
    """Seal ``value`` and store it in the best writable backend."""
    try:
        kit_secrets.set(
            ref,
            value,
            service=SERVICE,
            env_prefix=None,
            store_path=_store_path(),
            sealer=_cipher(),
        )
    except SecretStoreUnavailable as exc:
        raise RuntimeError(_UNAVAILABLE) from exc


def delete_secret(ref: str) -> None:
    """Remove ``ref`` from the selected backend and the sealed file.

    Fails closed when no writable backend exists: a revocation that
    silently did nothing would leave a credential live. The check is
    explicit because the kit also targets the sealed-file path — an absent
    slot on an unwritable host would otherwise be an effective no-op.
    """
    if store_backend() == "none":
        raise RuntimeError(_UNAVAILABLE)
    try:
        kit_secrets.delete(
            ref,
            service=SERVICE,
            env_prefix=None,
            store_path=_store_path(),
        )
    except SecretStoreUnavailable as exc:
        raise RuntimeError(_UNAVAILABLE) from exc
