from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import app.api.ai_settings as ai_settings_module
import app.core.secrets as secrets_module
from app.ai import providers as providers_module
from app.ai.chat_models import CaChatOpenAI, build_chat_model
from app.ai.providers import (
    DETECT_TARGETS,
    PRESETS,
    ProvidersService,
    detect_local_engines,
)
from app.ai.types import ResolvedModel


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers_module,
        "fetch_remote_models",
        lambda provider_type, base_url, api_key, transport=None: [],
    )


def _openai_models_response(model_ids: list[str]) -> httpx.Response:
    return httpx.Response(200, json={"data": [{"id": model_id} for model_id in model_ids]})


def _empty_models_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"data": []})


def test_local_presets_registered() -> None:
    assert PRESETS["llama_cpp"] == {
        "name": "llama.cpp (local)",
        "type": "openai_compatible",
        "base_url": "http://localhost:8080/v1",
    }
    assert PRESETS["lm_studio"] == {
        "name": "LM Studio (local)",
        "type": "openai_compatible",
        "base_url": "http://localhost:1234/v1",
    }
    assert PRESETS["ollama"]["type"] == "openai_compatible"
    assert set(DETECT_TARGETS) == {"ollama", "llama_cpp", "lm_studio"}
    assert DETECT_TARGETS["llama_cpp"] == (
        "http://localhost:8080/v1",
        "http://localhost:8081/v1",
    )


def test_detect_hit_validates_openai_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "localhost"
        if request.url.port == 11434:
            return _openai_models_response(["qwen3:8b", "nomic-embed-text"])
        raise httpx.ConnectError("refused", request=request)

    transport = httpx.MockTransport(handler)
    hits = detect_local_engines(transport=transport)
    assert len(hits) == 1
    assert hits[0].preset_id == "ollama"
    assert hits[0].name == "Ollama (local)"
    assert hits[0].base_url == "http://localhost:11434/v1"
    assert hits[0].models == ("qwen3:8b", "nomic-embed-text")


def test_detect_rejects_non_openai_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})

    assert detect_local_engines(transport=httpx.MockTransport(handler)) == []


def test_detect_rejects_error_status_and_garbage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(404, json={"error": "nope"})
        raise AssertionError("unexpected path")

    assert detect_local_engines(transport=httpx.MockTransport(handler)) == []


def test_detect_ignores_connection_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert detect_local_engines(transport=httpx.MockTransport(handler)) == []


def test_detect_falls_back_to_second_port() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        port = request.url.port
        if port in (11434, 1234, 8080):
            raise httpx.ConnectError("refused", request=request)
        assert port == 8081
        return _openai_models_response(["qwen3-32b"])

    hits = detect_local_engines(transport=httpx.MockTransport(handler))
    assert [(hit.preset_id, hit.base_url) for hit in hits] == [
        ("llama_cpp", "http://localhost:8081/v1")
    ]


def test_detect_skips_configured_base_urls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.port not in (11434, 1234), "configured engines must not be probed"
        raise httpx.ConnectError("refused", request=request)

    hits = detect_local_engines(
        transport=httpx.MockTransport(handler),
        configured_base_urls={"http://localhost:11434/v1", "http://localhost:1234/v1"},
    )
    assert hits == []


def test_detect_all_engines_simultaneously() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        port = request.url.port
        if port == 11434:
            return _openai_models_response(["qwen3:8b"])
        if port == 8080:
            return _openai_models_response(["qwen3-32b"])
        if port == 1234:
            return _openai_models_response(["text-embedding-nomic"])
        raise AssertionError("unexpected port")

    hits = detect_local_engines(transport=httpx.MockTransport(handler))
    assert [hit.preset_id for hit in hits] == ["ollama", "llama_cpp", "lm_studio"]


def test_api_detect_local_returns_hits_and_skips_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_response = client.post(
        "/api/v1/providers",
        json={"name": "Ollama (local)", "type": "openai_compatible", "base_url": "http://localhost:11434/v1"},
    )
    assert create_response.status_code == 201, create_response.text
    seen_kwargs: dict[str, Any] = {}

    def fake_probe(**kwargs: Any) -> list[Any]:
        seen_kwargs.update(kwargs)
        return []

    monkeypatch.setattr(ai_settings_module, "probe_local_engines", fake_probe)
    response = client.get("/api/v1/providers/detect-local")
    assert response.status_code == 200
    assert response.json() == []
    assert seen_kwargs["configured_base_urls"] == {"http://localhost:11434/v1"}


def test_create_local_provider_without_api_key_needs_no_keyring(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_writes: list[tuple[str, str]] = []
    monkeypatch.setattr(
        secrets_module, "set_secret", lambda ref, key: secret_writes.append((ref, key))
    )
    response = client.post(
        "/api/v1/providers",
        json={
            "name": "llama.cpp (local)",
            "type": "openai_compatible",
            "base_url": "http://localhost:8080/v1",
            "api_key": None,
        },
    )
    assert response.status_code == 201, response.text
    provider = response.json()
    assert provider["masked_key"] is None
    assert secret_writes == []


def test_blank_key_resolves_to_keyless_chat_model() -> None:
    resolved = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost:8080/v1",
        external_id="qwen3-32b",
        label="qwen3-32b",
        caps=["text"],
        api_key=None,
    )
    model = build_chat_model(
        resolved, transport=httpx.MockTransport(_empty_models_handler), timeout=5.0
    )
    assert isinstance(model, CaChatOpenAI)
    assert isinstance(model.openai_api_key, SecretStr)
    assert model.openai_api_key.get_secret_value() == "EMPTY"


def test_service_create_blank_key_skips_secret_write(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_writes: list[tuple[str, str]] = []
    monkeypatch.setattr(
        secrets_module, "set_secret", lambda ref, key: secret_writes.append((ref, key))
    )
    service = ProvidersService(db_session)
    provider = service.create(
        name="LM Studio (local)",
        provider_type="openai_compatible",
        base_url="http://localhost:1234/v1",
        api_key="",
    )
    assert provider.keyring_ref == f"provider:{provider.id}"
    assert secret_writes == []
