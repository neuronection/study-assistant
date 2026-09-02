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


def test_set_secret_raises_clear_error_without_backend(no_keyring: Any) -> None:
    with pytest.raises(RuntimeError, match="keyring"):
        secrets.set_secret("provider:1", "k")


def test_delete_secret_is_best_effort_without_backend(no_keyring: Any) -> None:
    secrets.delete_secret("provider:1")


def test_providers_api_works_without_keyring_backend(
    no_keyring: Any, tmp_path: Path
) -> None:
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
        assert keyed.status_code == 422, keyed.text
        assert "keyring" in keyed.json()["detail"]
