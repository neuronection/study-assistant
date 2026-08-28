import keyring
import pytest
from keyring.backend import KeyringBackend

from app.core import secrets


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


def test_get_secret_migrates_legacy_service_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeKeyring()
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)

    fake.set_password(secrets.LEGACY_SERVICE, "provider:7", "sk-legacy")

    assert secrets.get_secret("provider:7") == "sk-legacy"
    assert fake.get_password(secrets.SERVICE, "provider:7") == "sk-legacy"
    assert fake.get_password(secrets.LEGACY_SERVICE, "provider:7") == "sk-legacy"


def test_get_secret_prefers_current_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeKeyring()
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)

    fake.set_password(secrets.SERVICE, "provider:7", "sk-current")
    fake.set_password(secrets.LEGACY_SERVICE, "provider:7", "sk-legacy")

    assert secrets.get_secret("provider:7") == "sk-current"
    assert fake.get_password(secrets.LEGACY_SERVICE, "provider:7") == "sk-legacy"


def test_set_and_delete_secret_target_current_service_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeKeyring()
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)

    fake.set_password(secrets.LEGACY_SERVICE, "provider:7", "sk-legacy")

    secrets.set_secret("provider:7", "sk-new")
    assert fake.get_password(secrets.LEGACY_SERVICE, "provider:7") == "sk-legacy"

    secrets.delete_secret("provider:7")
    assert fake.get_password(secrets.SERVICE, "provider:7") is None
    assert fake.get_password(secrets.LEGACY_SERVICE, "provider:7") == "sk-legacy"
