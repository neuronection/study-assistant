"""Secrets at rest — sealed with the family cipher, stored by the best
available backend.

The at-rest machinery is shared family code: ``nx_auth.atrest``
(ADR-0027, plan 19) — this module is study's adapter over it. Values are
sealed under the auth-kit KeyRing ``data_key`` (``SA_DATA_KEY``) as
``enc::<fernet-token>`` strings, so a storage dump alone never exposes the
plaintext.

**Storage is deployment-selected** (plan 52 web/desktop fix):

* **OS keyring** — the desktop default (``service ``StudyAssistant``).
* **Sealed file** (``<data_dir>/secrets.json``, 0600) — the server/Docker
  default, where no keyring exists. Same cipher, so the file is useless
  without ``SA_DATA_KEY``.

The keyring is used **only if it round-trips a probe write**. Python's
``keyring.backends.null`` *accepts writes and silently discards them* —
that is silent token loss, so a backend that does not round-trip is
rejected outright and the sealed file takes over. If **neither** works the
module **fails closed**: no plaintext fallback, ever.

``SA_DATA_KEY_PREVIOUS`` (comma-separated) holds prior keys for
decryption-only rotation — new writes always seal under ``SA_DATA_KEY``
(runbook: docs/dev/security.md "Rotating the at-rest key").

Reads are plaintext-tolerant by design (plan 19 D4): study's values are
keyring/file-held — there is no DB ciphertext surface — so pre-adoption
plaintext entries return verbatim and no backfill is required.
Ciphertext that does not verify under the key ring yields ``None`` —
never a guess.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from functools import lru_cache
from pathlib import Path

from nx_auth.atrest import SecretCipher, decrypt_secret, encrypt_secret, is_encrypted

from app.core.keys import data_key_previous
from app.core.keys import keyring as key_ring

SERVICE = "StudyAssistant"
_PROBE_REF = "__backend_probe__"


@lru_cache(maxsize=1)
def _cipher() -> SecretCipher:
    """Rotation-aware cipher over the KeyRing data_key (+ prior keys)."""
    return SecretCipher(key_ring().data_key, previous=data_key_previous())


def cipher() -> SecretCipher:
    """The at-rest cipher, for callers that seal their own envelopes.

    ``nx_auth.oauth``'s ``TokenVault`` wraps each binding's token set in a
    ``context="oauth:<binding-id>"`` envelope (ADR-0052 §2) before storage —
    it needs the same rotation-aware key ring this module uses. Exposed so
    the vault never reaches for a second key source.
    """
    return _cipher()


def reset_secret_caches() -> None:
    """Drop the cached cipher (tests swap key material between cases)."""
    _cipher.cache_clear()
    _store.cache_clear()


# ---------------------------------------------------------------------------
# Storage backends
# ---------------------------------------------------------------------------


class _KeyringStore:
    """The OS keyring — desktop default, only when it actually round-trips."""

    name = "keyring"

    def __init__(self) -> None:
        import keyring

        self._keyring = keyring

    def get(self, ref: str) -> str | None:
        with contextlib.suppress(Exception):
            return self._keyring.get_password(SERVICE, ref)
        return None

    def set(self, ref: str, value: str) -> None:
        self._keyring.set_password(SERVICE, ref, value)

    def delete(self, ref: str) -> None:
        with contextlib.suppress(Exception):
            self._keyring.delete_password(SERVICE, ref)


class _FileStore:
    """A 0600 sealed file under ``data_dir`` — the server/Docker fallback.

    Values are already sealed by the caller (``nx_auth.atrest``), so the
    file is inert without ``SA_DATA_KEY``. Writes are atomic (tmp + replace)
    and serialised under a lock.
    """

    name = "file"

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, str]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return dict(raw) if isinstance(raw, dict) else {}

    def _save(self, data: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._path)

    def get(self, ref: str) -> str | None:
        with self._lock:
            return self._load().get(ref)

    def set(self, ref: str, value: str) -> None:
        with self._lock:
            data = self._load()
            data[ref] = value
            self._save(data)

    def delete(self, ref: str) -> None:
        with self._lock:
            data = self._load()
            if ref in data:
                del data[ref]
                self._save(data)


class _NoStore:
    """Nothing works — every call fails closed. Never a silent no-op."""

    name = "none"

    def get(self, ref: str) -> str | None:
        return None

    def set(self, ref: str, value: str) -> None:
        raise RuntimeError(
            "no usable secret store: the OS keyring is unavailable and the "
            "sealed file could not be written — refusing to store the credential "
            "anywhere else (fail closed, no plaintext fallback)"
        )

    def delete(self, ref: str) -> None:
        return


def _roundtrips(store: object) -> bool:
    """A backend is usable only if a write is actually readable.

    ``keyring.backends.null`` accepts writes and discards them — silently
    losing a token is worse than refusing to store it, so probe before trust.
    The keyring backend itself is selected by the keyring library (its
    ``PYTHON_KEYRING_BACKEND`` knob, or a desktop session vs a headless
    container); whatever it resolves to, THIS probe is what decides trust.
    """
    probe = f"probe-{os.getpid()}"
    try:
        store.set(_PROBE_REF, probe)  # type: ignore[attr-defined]
        back = store.get(_PROBE_REF)  # type: ignore[attr-defined]
    except Exception:
        return False
    finally:
        with contextlib.suppress(Exception):
            store.delete(_PROBE_REF)  # type: ignore[attr-defined]
    return back == probe


@lru_cache(maxsize=1)
def _store() -> object:
    """Pick the storage backend once per process (probe-verified)."""
    try:
        candidate: object = _KeyringStore()
        if _roundtrips(candidate):
            return candidate
    except Exception:
        pass
    try:
        from app.core.config import get_settings

        file_store: object = _FileStore(Path(get_settings().data_dir) / "secrets.json")
        if _roundtrips(file_store):
            return file_store
    except Exception:
        pass
    return _NoStore()


def store_backend() -> str:
    """Which backend is live (``keyring`` | ``file`` | ``none``) — for
    diagnostics and the settings surface. Never a secret."""
    return _store().name  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Public API (unchanged semantics)
# ---------------------------------------------------------------------------


def get_secret(ref: str) -> str | None:
    value = _store().get(ref)  # type: ignore[attr-defined]
    if not value or not is_encrypted(value):
        return value
    try:
        return decrypt_secret(value, _cipher())
    except ValueError:
        return None


def set_secret(ref: str, value: str) -> None:
    sealed = encrypt_secret(value, _cipher())
    assert sealed is not None
    _store().set(ref, sealed)  # type: ignore[attr-defined]


def delete_secret(ref: str) -> None:
    _store().delete(ref)  # type: ignore[attr-defined]
