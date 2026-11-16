import base64
import stat
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend

from app.core import keys, secrets
from app.core.config import Settings, get_settings

# 32 key bytes in the auth-kit token form (43 chars, unpadded).
DATA_TOKEN = base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode()[:-1]
NEW_DATA_TOKEN = base64.urlsafe_b64encode(b"fedcba9876543210fedcba9876543210").decode()[:-1]
SESSION_TOKEN = "s" + "0123456789abcdef" * 3
REFRESH_TOKEN = "r" + "0123456789abcdef" * 3

# Sealed by the pre-adoption backend under DATA_TOKEN: the `enc::` shape and
# the cipher are unchanged by the auth-kit adoption, so this must read back.
LEGACY_SEALED = (
    "enc::gAAAAABq9hEaU7Npu_-3kv5I40k_GgdzkzNiELNRerHEtw6cjS09lqzZeKWhZYwErS5SX"
    "0DklpZZaK2vyuRzOqFVMRNr3GDVV4fgHFRGatmWQPlrEphAboo="
)


class FakeKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self._store.pop((service, username), None)


def install_fake_keyring(monkeypatch: pytest.MonkeyPatch) -> FakeKeyring:
    fake = FakeKeyring()
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)
    return fake


def pin_data_key(monkeypatch: pytest.MonkeyPatch, data: str, previous: str | None = None) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "session_key", SESSION_TOKEN)
    monkeypatch.setattr(settings, "refresh_key", REFRESH_TOKEN)
    monkeypatch.setattr(settings, "data_key", data)
    monkeypatch.setattr(settings, "data_key_previous", previous)
    keys.reset_keyring_cache()
    secrets.reset_secret_caches()


def pin_partial_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only ``SA_DATA_KEY`` pinned: the §8 ring refuses to resolve."""
    settings = get_settings()
    monkeypatch.setattr(settings, "session_key", None)
    monkeypatch.setattr(settings, "refresh_key", None)
    monkeypatch.setattr(settings, "data_key", DATA_TOKEN)
    monkeypatch.setattr(settings, "data_key_previous", None)
    keys.reset_keyring_cache()
    secrets.reset_secret_caches()


def forbid_cipher(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if a read builds the at-rest cipher."""

    def _boom() -> None:
        raise AssertionError("a missing/plaintext read must not build the cipher")

    monkeypatch.setattr(secrets, "_cipher", _boom)


def test_secret_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeKeyring()
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)

    assert secrets.get_secret("provider:1") is None
    secrets.set_secret("provider:1", "sk-test")
    assert secrets.store_backend() == "keyring"
    assert secrets.get_secret("provider:1") == "sk-test"
    secrets.delete_secret("provider:1")
    assert secrets.get_secret("provider:1") is None


def test_set_secret_seals_under_data_key(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_keyring(monkeypatch)
    pin_data_key(monkeypatch, DATA_TOKEN)

    secrets.set_secret("provider:1", "sk-test")

    stored = fake.get_password(secrets.SERVICE, "provider:1")
    assert stored is not None
    assert stored.startswith("enc::")
    assert "sk-test" not in stored


def test_get_secret_reads_pre_adoption_plaintext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_keyring(monkeypatch)
    pin_data_key(monkeypatch, DATA_TOKEN)
    fake.set_password(secrets.SERVICE, "search", "tvly-v1")

    assert secrets.get_secret("search") == "tvly-v1"


def test_get_secret_reads_a_pre_adoption_sealed_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adoption keeps the same ``enc::`` shape and data key."""
    fake = install_fake_keyring(monkeypatch)
    pin_data_key(monkeypatch, DATA_TOKEN)
    fake.set_password(secrets.SERVICE, "legacy", LEGACY_SEALED)

    assert secrets.get_secret("legacy") == "legacy-sealed-value"


def test_no_environment_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Study's adapter passes ``env_prefix=None`` — env never supplies a value."""
    install_fake_keyring(monkeypatch)
    pin_data_key(monkeypatch, DATA_TOKEN)
    monkeypatch.setenv("STUDYASSISTANT_NO_ENV_PROBE", "env-secret")
    monkeypatch.setenv("SA_NO_ENV_PROBE", "env-secret")

    assert secrets.get_secret("no-env-probe") is None


def test_generated_auth_keys_file_seals_and_opens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No pins: the generated 0600 ``auth_keys.json`` backs the cipher."""
    fake = install_fake_keyring(monkeypatch)
    settings = Settings(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        session_key=None,
        refresh_key=None,
        data_key=None,
        data_key_previous=None,
    )
    monkeypatch.setattr(keys, "get_settings", lambda: settings)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    keys.reset_keyring_cache()
    secrets.reset_secret_caches()
    try:
        secrets.set_secret("generated:1", "generated-value")

        assert secrets.get_secret("generated:1") == "generated-value"
        key_file = tmp_path / "config" / "auth_keys.json"
        assert key_file.is_file()
        assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
        stored = fake.get_password(secrets.SERVICE, "generated:1")
        assert stored is not None and stored.startswith("enc::")
    finally:
        keys.reset_keyring_cache()
        secrets.reset_secret_caches()


def test_undecryptable_value_yields_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_keyring(monkeypatch)
    pin_data_key(monkeypatch, DATA_TOKEN)
    fake.set_password(secrets.SERVICE, "provider:2", "enc::gAAAAA-not-a-real-token")

    assert secrets.get_secret("provider:2") is None


def test_missing_slot_resolves_without_key_material(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No key material (unwritable config dir) must not fail an absent read."""
    install_fake_keyring(monkeypatch)
    settings = Settings(
        config_dir=Path("/proc/definitely-not-writable/config"),
        data_dir=tmp_path,
        session_key=None,
        refresh_key=None,
        data_key=None,
        data_key_previous=None,
    )
    monkeypatch.setattr(keys, "get_settings", lambda: settings)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    keys.reset_keyring_cache()
    secrets.reset_secret_caches()
    try:
        assert secrets.get_secret("provider:missing") is None
    finally:
        keys.reset_keyring_cache()
        secrets.reset_secret_caches()


def test_plaintext_slot_resolves_without_key_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-adoption plaintext reads verbatim even when the ring cannot resolve."""
    fake = install_fake_keyring(monkeypatch)
    pin_partial_key_material(monkeypatch)
    forbid_cipher(monkeypatch)
    fake.set_password(secrets.SERVICE, "search", "tvly-v1")

    assert secrets.get_secret("search") == "tvly-v1"


def test_encrypted_slot_without_key_material_yields_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sealed value fails closed (``None``, never a crash) without keys."""
    fake = install_fake_keyring(monkeypatch)
    pin_partial_key_material(monkeypatch)
    fake.set_password(secrets.SERVICE, "legacy", LEGACY_SEALED)

    assert secrets.get_secret("legacy") is None


def test_encrypted_slot_decrypts_again_after_reset_secret_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed/wrong key resolution is not cached — resets re-resolve."""
    fake = install_fake_keyring(monkeypatch)
    fake.set_password(secrets.SERVICE, "legacy", LEGACY_SEALED)
    pin_partial_key_material(monkeypatch)
    assert secrets.get_secret("legacy") is None

    pin_data_key(monkeypatch, DATA_TOKEN)
    assert secrets.get_secret("legacy") == "legacy-sealed-value"

    pin_partial_key_material(monkeypatch)
    assert secrets.get_secret("legacy") is None
    secrets.reset_secret_caches()
    assert secrets.get_secret("legacy") is None


def test_set_secret_still_fails_closed_without_key_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only reads went lazy: sealing still demands a resolvable ring."""
    install_fake_keyring(monkeypatch)
    pin_partial_key_material(monkeypatch)

    with pytest.raises(ValueError, match="partial key pin"):
        secrets.set_secret("provider:1", "sk-test")


def test_stored_empty_value_resolves_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adoption delta 1: a stored ``""`` reads as ``None`` (was ``""``)."""
    fake = install_fake_keyring(monkeypatch)
    pin_data_key(monkeypatch, DATA_TOKEN)
    fake.set_password(secrets.SERVICE, "empty", "")

    assert secrets.get_secret("empty") is None


def test_empty_ref_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adoption delta 2: empty refs are refused (was store-under-``""``)."""
    install_fake_keyring(monkeypatch)
    pin_data_key(monkeypatch, DATA_TOKEN)

    with pytest.raises(ValueError):
        secrets.set_secret("", "value")
    with pytest.raises(ValueError):
        secrets.delete_secret("")


def test_rotation_previous_key_decrypts_then_reseals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_keyring(monkeypatch)
    pin_data_key(monkeypatch, DATA_TOKEN)
    secrets.set_secret("provider:3", "sk-rotate")
    secrets.set_secret("provider:4", "sk-orphan")
    sealed_under_old = fake.get_password(secrets.SERVICE, "provider:3")

    pin_data_key(monkeypatch, NEW_DATA_TOKEN, previous=DATA_TOKEN)
    assert secrets.get_secret("provider:3") == "sk-rotate"

    secrets.set_secret("provider:3", "sk-rotate")
    resealed = fake.get_password(secrets.SERVICE, "provider:3")
    assert resealed is not None
    assert resealed != sealed_under_old

    pin_data_key(monkeypatch, NEW_DATA_TOKEN)
    assert secrets.get_secret("provider:3") == "sk-rotate"
    assert secrets.get_secret("provider:4") is None


def test_data_key_previous_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "data_key_previous", " a ,, b ")
    assert keys.data_key_previous() == ["a", "b"]
    assert keys.data_key_previous(Settings(data_key_previous=None)) == []


def test_boot_guard_receives_previous_ring(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import nx_auth.boot as kit_boot

    from app.main import create_app

    captured: dict[str, object] = {}

    def fake_validate(**kwargs: object) -> list[str]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(kit_boot, "validate_boot_config", fake_validate)
    settings = Settings(
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=None,
        log_level="WARNING",
        app_env="test",
        data_key_previous="k-one, k-two",
    )
    create_app(settings)
    assert captured["data_key_previous"] == ["k-one", "k-two"]
