from pathlib import Path
from typing import Any

import keyring
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend

from app.ai import providers as providers_module
from app.ai.providers import RemoteModel
from app.core.config import Settings
from app.core.secrets import SERVICE
from app.main import create_app


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


FAKE_REMOTE_MODELS = [
    RemoteModel(external_id="gemini-2.5-flash", caps=("text", "vision", "audio", "tools")),
    RemoteModel(external_id="gemini-2.5-pro", caps=("text", "vision", "audio", "tools")),
    RemoteModel(external_id="text-embedding-004", caps=("embeddings",)),
]

@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(
    provider_type: str, base_url: str, api_key: str | None, transport: object = None
) -> list[RemoteModel]:
        return FAKE_REMOTE_MODELS

    monkeypatch.setattr(providers_module, "fetch_remote_models", fake_fetch)


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> FakeKeyring:
    fake = FakeKeyring()
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)
    return fake


def create_provider(client: TestClient, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Test Google",
        "type": "google",
        "api_key": "AIza-supersecret-1234",
    }
    body.update(overrides)
    response = client.post("/api/v1/providers", json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result

def test_create_provider_stores_masked_key_not_plaintext(
    client: TestClient, fake_keyring: FakeKeyring
) -> None:
    provider = create_provider(client)
    assert provider["masked_key"] == "••••1234"
    assert "supersecret" not in str(provider)
    assert fake_keyring.get_password(SERVICE, f"provider:{provider['id']}") == (
        "AIza-supersecret-1234"
    )


def test_update_provider_replaces_key_only_when_given(
    client: TestClient, fake_keyring: FakeKeyring
) -> None:
    provider = create_provider(client)
    response = client.patch(
        f"/api/v1/providers/{provider['id']}", json={"name": "Renamed"}
    )
    assert response.status_code == 200
    assert fake_keyring.get_password(SERVICE, f"provider:{provider['id']}") == (
        "AIza-supersecret-1234"
    )
    client.patch(f"/api/v1/providers/{provider['id']}", json={"api_key": "sk-new-9999"})
    assert (
        fake_keyring.get_password(SERVICE, f"provider:{provider['id']}")
        == "sk-new-9999"
    )


def test_delete_provider_removes_key_and_models(
    client: TestClient, fake_keyring: FakeKeyring
) -> None:
    provider = create_provider(client)
    provider_id = provider["id"]
    client.delete(f"/api/v1/providers/{provider_id}")
    assert fake_keyring.get_password(SERVICE, f"provider:{provider_id}") is None
    assert client.get("/api/v1/models", params={"provider_id": provider_id}).json() == []


def test_task_assignment_requires_vision_for_ocr(
    client: TestClient, fake_keyring: FakeKeyring
) -> None:
    tasks = client.get("/api/v1/tasks").json()
    ocr_task = next(task for task in tasks if task["task"] == "ocr")
    assert ocr_task["requires"] == "vision"

    provider = create_provider(client, type="openai_compatible", base_url="http://localhost:1/v1")
    from app.domain.models import AiModel

    list_response = client.get("/api/v1/providers")
    assert list_response.status_code == 200

    app = client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as session:
        session.add(
            AiModel(
                provider_id=provider["id"],
                external_id="text-only-model",
                label="text-only-model",
                caps=["text"],
                enabled=True,
            )
        )
        vision_model = AiModel(
            provider_id=provider["id"],
            external_id="vision-model",
            label="vision-model",
            caps=["text", "vision"],
            enabled=True,
        )
        session.add(vision_model)
        session.commit()
        vision_model_id = vision_model.id

    rejected = client.put(
        "/api/v1/tasks/ocr", json={"model_id": vision_model_id - 1, "fallback_model_id": None}
    )
    assert rejected.status_code == 422
    assert "vision" in rejected.json()["detail"]

    accepted = client.put("/api/v1/tasks/ocr", json={"model_id": vision_model_id})
    assert accepted.status_code == 200
    tasks = client.get("/api/v1/tasks").json()
    ocr_task = next(task for task in tasks if task["task"] == "ocr")
    assert ocr_task["model_id"] == vision_model_id
    assert ocr_task["model_label"] == "vision-model"


def patch_remote(monkeypatch: pytest.MonkeyPatch, models: list[RemoteModel]) -> None:
    from app.api import ai_settings as ai_settings_module

    monkeypatch.setattr(
        ai_settings_module,
        "fetch_remote_models",
        lambda *args: models,
    )


def test_remote_models_listing_does_not_persist(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_remote(monkeypatch, FAKE_REMOTE_MODELS)
    provider = create_provider(client)
    before = client.get("/api/v1/models", params={"provider_id": provider["id"]}).json()
    listing = client.get(f"/api/v1/providers/{provider['id']}/remote-models")
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert [entry["external_id"] for entry in body] == [
        model.external_id for model in FAKE_REMOTE_MODELS
    ]
    assert body[0]["caps"] == ["text", "vision", "audio", "tools"]
    after = client.get("/api/v1/models", params={"provider_id": provider["id"]}).json()
    assert [model["id"] for model in after] == [model["id"] for model in before]


def test_remote_models_fetch_error_is_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import ai_settings as ai_settings_module

    def boom(*args: object) -> list[RemoteModel]:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(ai_settings_module, "fetch_remote_models", boom)
    provider = create_provider(client)
    listing = client.get(f"/api/v1/providers/{provider['id']}/remote-models")
    assert listing.status_code == 502
    assert "connection refused" in listing.json()["detail"]


def test_manual_model_add_infers_caps_and_is_idempotent(
    client: TestClient, fake_keyring: FakeKeyring
) -> None:
    provider = create_provider(client)
    created = client.post(
        "/api/v1/models",
        json={"provider_id": provider["id"], "external_id": " gemini-9-flash "},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["external_id"] == "gemini-9-flash"
    assert body["caps"] == ["text", "vision", "audio", "tools"]
    assert body["enabled"] is True

    again = client.post(
        "/api/v1/models",
        json={
            "provider_id": provider["id"],
            "external_id": "gemini-9-flash",
            "caps": ["text"],
        },
    )
    assert again.status_code == 200
    assert again.json()["id"] == body["id"]
    assert again.json()["caps"] == ["text"]

    missing = client.post("/api/v1/models", json={"provider_id": 999, "external_id": "x"})
    assert missing.status_code == 404


def test_model_reasoning_effort_round_trip(
    client: TestClient, fake_keyring: FakeKeyring
) -> None:
    provider = create_provider(client)
    created = client.post(
        "/api/v1/models",
        json={
            "provider_id": provider["id"],
            "external_id": "gpt-5.6-luna",
            "reasoning_effort": "none",
        },
    )
    assert created.status_code == 201
    assert created.json()["reasoning_effort"] == "none"

    model = created.json()
    patched = client.patch(
        f"/api/v1/models/{model['id']}", json={"reasoning_effort": "high"}
    )
    assert patched.status_code == 200
    assert patched.json()["reasoning_effort"] == "high"

    cleared = client.patch(
        f"/api/v1/models/{model['id']}", json={"reasoning_effort": "  "}
    )
    assert cleared.status_code == 200
    assert cleared.json()["reasoning_effort"] is None


def test_manual_model_add_rejects_unknown_caps(
    client: TestClient, fake_keyring: FakeKeyring
) -> None:
    provider = create_provider(client)
    bad = client.post(
        "/api/v1/models",
        json={"provider_id": provider["id"], "external_id": "m", "caps": ["telepathy"]},
    )
    assert bad.status_code == 422
    assert "telepathy" in bad.text

    model = client.post(
        "/api/v1/models", json={"provider_id": provider["id"], "external_id": "m"}
    ).json()
    patched = client.patch(f"/api/v1/models/{model['id']}", json={"caps": ["floats"]})
    assert patched.status_code == 422


def test_manual_model_add_accepts_audio_caps(
    client: TestClient, fake_keyring: FakeKeyring
) -> None:
    provider = create_provider(client)
    created = client.post(
        "/api/v1/models",
        json={
            "provider_id": provider["id"],
            "external_id": "whisper-1",
            "caps": ["audio"],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["caps"] == ["audio"]

    patched = client.patch(
        f"/api/v1/models/{created.json()['id']}",
        json={"caps": ["text", "audio"]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["caps"] == ["text", "audio"]


def test_manual_add_revives_missing_model(
    client: TestClient, fake_keyring: FakeKeyring
) -> None:
    provider = create_provider(client)
    model = client.post(
        "/api/v1/models", json={"provider_id": provider["id"], "external_id": "llama-x"}
    ).json()

    from app.domain.models import AiModel

    app = client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as session:
        row = session.get(AiModel, model["id"])
        assert row is not None
        row.missing = True
        session.commit()

    revived = client.post(
        "/api/v1/models", json={"provider_id": provider["id"], "external_id": "llama-x"}
    )
    assert revived.status_code == 200
    assert revived.json()["missing"] is False


def deny_401(*args: object) -> list[RemoteModel]:
    import httpx

    request = httpx.Request("GET", "https://api.openai.com/v1/models")
    response = httpx.Response(401, request=request)
    raise httpx.HTTPStatusError(
        "Client error '401 Unauthorized' for url 'https://api.openai.com/v1/models'",
        request=request,
        response=response,
    )


def test_remote_models_401_explains_missing_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_keyring: FakeKeyring
) -> None:
    from app.api import ai_settings as ai_settings_module

    monkeypatch.setattr(ai_settings_module, "fetch_remote_models", deny_401)
    provider = create_provider(
        client,
        type="openai_compatible",
        base_url="https://api.openai.com/v1",
        api_key=None,
    )
    listing = client.get(f"/api/v1/providers/{provider['id']}/remote-models")
    assert listing.status_code == 502
    assert "no API key is stored" in listing.json()["detail"]
    assert "manually" in listing.json()["detail"]


def test_remote_models_401_explains_rejected_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_keyring: FakeKeyring
) -> None:
    from app.api import ai_settings as ai_settings_module

    monkeypatch.setattr(ai_settings_module, "fetch_remote_models", deny_401)
    provider = create_provider(
        client,
        type="openai_compatible",
        base_url="https://api.openai.com/v1",
        api_key="sk-wrong",
    )
    listing = client.get(f"/api/v1/providers/{provider['id']}/remote-models")
    assert listing.status_code == 502
    assert "stored API key was rejected" in listing.json()["detail"]


def test_readd_model_enables_it(client: TestClient, fake_keyring: FakeKeyring) -> None:
    provider = create_provider(client)
    model = client.post(
        "/api/v1/models", json={"provider_id": provider["id"], "external_id": "m1"}
    ).json()
    disabled = client.patch(f"/api/v1/models/{model['id']}", json={"enabled": False})
    assert disabled.json()["enabled"] is False

    again = client.post(
        "/api/v1/models", json={"provider_id": provider["id"], "external_id": "m1"}
    )
    assert again.status_code == 200
    assert again.json()["enabled"] is True


def test_delete_model_unassigns_tasks(client: TestClient, fake_keyring: FakeKeyring) -> None:
    provider = create_provider(client)
    model = client.post(
        "/api/v1/models",
        json={"provider_id": provider["id"], "external_id": "chat-model", "caps": ["text"]},
    ).json()
    assigned = client.put("/api/v1/tasks/chat", json={"model_id": model["id"]})
    assert assigned.status_code == 200, assigned.text

    deleted = client.delete(f"/api/v1/models/{model['id']}")
    assert deleted.status_code == 204
    tasks = client.get("/api/v1/tasks").json()
    chat = next(task for task in tasks if task["task"] == "chat")
    assert chat["model_id"] is None

    missing = client.delete(f"/api/v1/models/{model['id']}")
    assert missing.status_code == 404


def test_task_defaults_endpoints_and_inheritance(
    client: TestClient, fake_keyring: FakeKeyring
) -> None:
    defaults = client.get("/api/v1/tasks/defaults").json()
    assert [entry["requires"] for entry in defaults] == ["text", "vision", "embeddings", "audio"]
    assert all(entry["model_id"] is None for entry in defaults)

    provider = create_provider(client, type="openai_compatible", base_url="http://localhost:1/v1")
    default_model = client.post(
        "/api/v1/models",
        json={"provider_id": provider["id"], "external_id": "gemini-flash", "caps": ["text"]},
    ).json()
    set_default = client.put(
        "/api/v1/tasks/defaults/text", json={"model_id": default_model["id"]}
    )
    assert set_default.status_code == 200, set_default.text
    assert set_default.json()["model_label"] == "gemini-flash"

    tasks = client.get("/api/v1/tasks").json()
    chat = next(task for task in tasks if task["task"] == "chat")
    assert chat["requires"] == "text"
    assert chat["model_id"] is None
    assert chat["inherits_default"] is True
    assert chat["default_model_label"] == "gemini-flash"

    override = client.post(
        "/api/v1/models",
        json={"provider_id": provider["id"], "external_id": "gpt-mini", "caps": ["text"]},
    ).json()
    assigned = client.put("/api/v1/tasks/chat", json={"model_id": override["id"]})
    assert assigned.status_code == 200, assigned.text
    body = assigned.json()
    assert body["model_id"] == override["id"]
    assert body["inherits_default"] is False

    cleared = client.put("/api/v1/tasks/chat", json={"model_id": None})
    assert cleared.status_code == 200
    assert cleared.json()["model_id"] is None
    assert cleared.json()["inherits_default"] is True

    text_only = client.post(
        "/api/v1/models",
        json={"provider_id": provider["id"], "external_id": "text-model", "caps": ["text"]},
    ).json()
    mismatch = client.put(
        "/api/v1/tasks/defaults/vision", json={"model_id": text_only["id"]}
    )
    assert mismatch.status_code == 422
    assert "vision" in mismatch.json()["detail"]

    unknown = client.put(
        "/api/v1/tasks/defaults/telepathy", json={"model_id": default_model["id"]}
    )
    assert unknown.status_code == 422


def test_delete_model_unassigns_task_defaults(
    client: TestClient, fake_keyring: FakeKeyring
) -> None:
    provider = create_provider(client, type="openai_compatible", base_url="http://localhost:1/v1")
    model = client.post(
        "/api/v1/models",
        json={"provider_id": provider["id"], "external_id": "default-text", "caps": ["text"]},
    ).json()
    client.put("/api/v1/tasks/defaults/text", json={"model_id": model["id"]})

    deleted = client.delete(f"/api/v1/models/{model['id']}")
    assert deleted.status_code == 204
    defaults = client.get("/api/v1/tasks/defaults").json()
    text_default = next(entry for entry in defaults if entry["requires"] == "text")
    assert text_default["model_id"] is None


def test_delete_provider_unassigns_task_defaults(
    client: TestClient, fake_keyring: FakeKeyring
) -> None:
    provider = create_provider(client, type="openai_compatible", base_url="http://localhost:1/v1")
    model = client.post(
        "/api/v1/models",
        json={"provider_id": provider["id"], "external_id": "default-text", "caps": ["text"]},
    ).json()
    client.put("/api/v1/tasks/defaults/text", json={"model_id": model["id"]})

    deleted = client.delete(f"/api/v1/providers/{provider['id']}")
    assert deleted.status_code == 204
    defaults = client.get("/api/v1/tasks/defaults").json()
    text_default = next(entry for entry in defaults if entry["requires"] == "text")
    assert text_default["model_id"] is None


def _assign_text_default(client: TestClient, fake_keyring: FakeKeyring) -> int:
    provider = create_provider(client, type="openai_compatible", base_url="http://localhost:1/v1")
    model = client.post(
        "/api/v1/models",
        json={"provider_id": provider["id"], "external_id": "default-text", "caps": ["text"]},
    ).json()
    response = client.put(
        "/api/v1/tasks/defaults/text", json={"model_id": model["id"]}
    )
    assert response.status_code == 200, response.text
    model_id: int = model["id"]
    return model_id


def test_task_defaults_survive_restart(
    tmp_path: Path, fake_keyring: FakeKeyring
) -> None:
    settings = Settings(data_dir=tmp_path, log_level="WARNING")
    with TestClient(create_app(settings)) as first:
        model_id = _assign_text_default(first, fake_keyring)

    with TestClient(create_app(settings)) as second:
        defaults = second.get("/api/v1/tasks/defaults").json()
        text_default = next(entry for entry in defaults if entry["requires"] == "text")
        assert text_default["model_id"] == model_id


def test_task_defaults_survive_restore(
    tmp_path: Path, fake_keyring: FakeKeyring
) -> None:
    settings = Settings(data_dir=tmp_path, log_level="WARNING")
    with TestClient(create_app(settings)) as client:
        model_id = _assign_text_default(client, fake_keyring)
        exported = client.get("/api/v1/backup/export")
        assert exported.status_code == 200
        package = exported.content

        restored = client.post(
            "/api/v1/backup/restore",
            files={"file": ("backup.zip", package, "application/zip")},
        )
        assert restored.status_code == 200, restored.text

        defaults = client.get("/api/v1/tasks/defaults").json()
        text_default = next(entry for entry in defaults if entry["requires"] == "text")
        assert text_default["model_id"] == model_id
