from pathlib import Path
from typing import Any

import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backends import fail

from app.core import secrets
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def no_keyring(monkeypatch: pytest.MonkeyPatch) -> fail.Keyring:
    backend = fail.Keyring()  # type: ignore[no-untyped-call]
    monkeypatch.setattr(keyring, "get_password", backend.get_password)
    monkeypatch.setattr(keyring, "set_password", backend.set_password)
    monkeypatch.setattr(keyring, "delete_password", backend.delete_password)
    return backend


def test_get_secret_returns_none_without_backend(no_keyring: Any) -> None:
    assert secrets.get_secret("provider:1") is None


def test_set_secret_falls_back_to_the_sealed_file_without_keyring(
    no_keyring: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No OS keyring is a web/server reality — not a reason to lose the key.

    (Plan 52 web/desktop fix: the sealed file is the server backend.)
    """
    monkeypatch.setattr("app.core.config.get_settings", lambda: Settings(data_dir=tmp_path))
    secrets.reset_secret_caches()
    try:
        secrets.set_secret("provider:1", "k")
        assert secrets.get_secret("provider:1") == "k"
        assert secrets.store_backend() == "file"
    finally:
        secrets.reset_secret_caches()


def test_set_secret_raises_clear_error_without_any_backend(
    no_keyring: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neither keyring nor a writable file -> fail closed, clearly."""
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(data_dir=Path("/proc/definitely-not-writable")),
    )
    secrets.reset_secret_caches()
    try:
        with pytest.raises(RuntimeError, match="fail closed"):
            secrets.set_secret("provider:1", "k")
    finally:
        secrets.reset_secret_caches()


def test_delete_secret_is_best_effort_without_backend(no_keyring: Any) -> None:
    secrets.delete_secret("provider:1")


def test_providers_api_works_without_keyring_backend(no_keyring: Any, tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path, log_level="WARNING"))
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/providers",
            json={"name": "Local engine", "type": "openai_compatible", "base_url": "http://x/v1"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["masked_key"] is None

        listed = client.get("/api/v1/providers")
        assert listed.status_code == 200, listed.text

        keyed = client.post(
            "/api/v1/providers",
            json={
                "name": "Cloud",
                "type": "openai_compatible",
                "base_url": "http://y/v1",
                "api_key": "secret-key",
            },
        )
        # With the sealed-file fallback the key IS storable (plan 52 fix):
        # it is sealed at rest and masked in the response.
        assert keyed.status_code == 201, keyed.text
        assert "secret-key" not in keyed.text
        # the credential is sealed at rest — `test_sealed_file_is_not_plaintext`
        # pins that the on-disk form is ciphertext, not the raw value.
