import base64
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


def pin_data_key(
    monkeypatch: pytest.MonkeyPatch, data: str, previous: str | None = None
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "session_key", SESSION_TOKEN)
    monkeypatch.setattr(settings, "refresh_key", REFRESH_TOKEN)
    monkeypatch.setattr(settings, "data_key", data)
    monkeypatch.setattr(settings, "data_key_previous", previous)
    keys.reset_keyring_cache()
    secrets.reset_secret_caches()


def test_secret_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeKeyring()
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)

    assert secrets.get_secret("provider:1") is None
    secrets.set_secret("provider:1", "sk-test")
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
    fake.set_password(secrets.SERVICE, "search", "tvly-legacy")

    assert secrets.get_secret("search") == "tvly-legacy"


def test_undecryptable_value_yields_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_keyring(monkeypatch)
    pin_data_key(monkeypatch, DATA_TOKEN)
    fake.set_password(secrets.SERVICE, "provider:2", "enc::gAAAAA-not-a-real-token")

    assert secrets.get_secret("provider:2") is None


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


def test_boot_guard_receives_previous_ring(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
