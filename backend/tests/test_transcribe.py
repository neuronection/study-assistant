import base64
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway

from app.ai.gateway import LLMGateway, ProviderError, TaskUnassigned
from app.ai.transcribe import TranscriptionResult, audio_extension
from app.core.config import Settings
from app.domain.models import AiInteraction, AiModel, Provider, TaskAssignment
from app.main import create_app


def make_gateway(
    transport: httpx.BaseTransport, retry_attempts: int = 2, retry_wait: float = 0.01
) -> LLMGateway:
    return LLMGateway(
        session_factory=None,
        transport=transport,
        retry_attempts=retry_attempts,
        retry_wait=retry_wait,
    )


def resolved(provider_type: str, external_id: str = "whisper-1") -> Any:
    from app.ai.gateway import ResolvedModel

    return ResolvedModel(
        provider_id=1,
        provider_type=provider_type,
        base_url="https://provider.test/v1"
        if provider_type == "openai_compatible"
        else "https://provider.test",
        external_id=external_id,
        label=external_id,
        caps=["audio"],
        api_key="KEY",
    )


def test_openai_compatible_multipart_request_shape() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = request.content
        captured["content_type"] = request.headers.get("Content-Type")
        return httpx.Response(
            200,
            json={"text": "  hello dictation ", "usage": {"input_tokens": 30, "output_tokens": 4}},
        )

    gateway = make_gateway(httpx.MockTransport(handler))
    result = gateway.transcribe(
        b"RIFFfakeaudio", "audio/webm", language="en", model=resolved("openai_compatible")
    )
    assert result.text == "hello dictation"
    assert result.model == "whisper-1"
    assert captured["url"] == "https://provider.test/v1/audio/transcriptions"
    assert captured["auth"] == "Bearer KEY"
    assert "multipart/form-data" in captured["content_type"]
    body = captured["body"]
    assert b'name="model"\r\n\r\nwhisper-1' in body
    assert b'name="response_format"\r\n\r\njson' in body
    assert b'name="language"\r\n\r\nen' in body
    assert b'name="file"; filename="audio.webm"' in body
    assert b"RIFFfakeaudio" in body


def test_google_inline_audio_request_shape_and_usage() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "transcribed words"}]}}
                ],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 5},
            },
        )

    gateway = make_gateway(httpx.MockTransport(handler))
    result = gateway.transcribe(
        b"RIFFfakeaudio",
        "audio/webm",
        instruction="Verbatim please.",
        model=resolved("google", "gemini-2.5-flash"),
    )
    assert result.text == "transcribed words"
    assert result.model == "gemini-2.5-flash"
    assert captured["url"].startswith(
        "https://provider.test/v1beta/models/gemini-2.5-flash:generateContent"
    )
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "Verbatim please."
    parts = captured["body"]["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "audio/webm"
    assert parts[0]["inlineData"]["data"] == base64.b64encode(b"RIFFfakeaudio").decode()
    assert parts[1] == {"text": "Transcribe this audio."}


def test_anthropic_provider_is_unsupported() -> None:
    gateway = make_gateway(httpx.MockTransport(lambda request: httpx.Response(200)))
    with pytest.raises(ProviderError) as exc_info:
        gateway.transcribe(b"audio", "audio/webm", model=resolved("anthropic"))
    assert "does not offer speech-to-text" in str(exc_info.value)


def _migrated_factory(tmp_path: object, slug: str) -> Any:
    from alembic.config import Config

    from alembic import command

    root = Path(str(tmp_path)) / slug
    root.mkdir(exist_ok=True)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{root / 'st.db'}")
    command.upgrade(config, "head")

    from app.storage.db import make_engine, make_session_factory

    return make_session_factory(make_engine(root / "st.db"))


def test_server_error_falls_back_to_fallback_model(tmp_path: object) -> None:
    factory = _migrated_factory(tmp_path, "st-fallback")
    with factory() as session:
        provider = Provider(
            name="p", type="openai_compatible", base_url="http://x/v1", keyring_ref="provider:1"
        )
        session.add(provider)
        session.flush()
        primary = AiModel(
            provider_id=provider.id,
            external_id="primary",
            label="primary",
            caps=["audio"],
            enabled=True,
        )
        fallback = AiModel(
            provider_id=provider.id,
            external_id="fallback",
            label="fallback",
            caps=["audio"],
            enabled=True,
        )
        session.add_all([primary, fallback])
        session.flush()
        session.add(
            TaskAssignment(
                task="transcribe", model_id=primary.id, fallback_model_id=fallback.id
            )
        )
        session.commit()

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("latin-1")
        calls.append("primary" if "primary" in body else "fallback")
        if "primary" in body:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"text": "fallback text"})

    gateway = LLMGateway(factory, transport=httpx.MockTransport(handler), retry_attempts=1)
    result = gateway.transcribe(b"audio", "audio/webm")
    assert result.text == "fallback text"
    assert calls == ["primary", "fallback"]

    with factory() as session:
        row = session.scalars(
            select(AiInteraction).where(AiInteraction.task == "transcribe")
        ).one()
        assert row.context_type == "gateway"
        assert row.model == "fallback"
        assert row.input_tokens >= 1


def test_transcribe_unassigned_raises(tmp_path: object) -> None:
    factory = _migrated_factory(tmp_path, "st-unassigned")
    gateway = LLMGateway(factory)
    with pytest.raises(TaskUnassigned):
        gateway.transcribe(b"audio", "audio/webm")


def test_audio_extension_mapping() -> None:
    assert audio_extension("audio/webm;codecs=opus") == "webm"
    assert audio_extension("video/webm") == "webm"
    assert audio_extension("audio/mp4") == "m4a"
    assert audio_extension("audio/ogg") == "ogg"
    assert audio_extension("audio/x-mystery") == "webm"


class TranscribeGateway(ScriptedGateway):
    def __init__(self) -> None:
        super().__init__([])
        self.audio_calls: list[tuple[bytes, str, str | None, str | None]] = []
        self.error: Exception | None = None

    def transcribe(
        self,
        data: bytes,
        mime: str,
        *,
        language: str | None = None,
        instruction: str | None = None,
        task: str = "transcribe",
        model: Any = None,
        course_id: int | None = None,
    ) -> TranscriptionResult:
        if self.error is not None:
            raise self.error
        self.audio_calls.append((data, mime, language, instruction))
        return TranscriptionResult(text="hello from dictation", model="whisper-1")


class UnassignedTranscribeGateway(TranscribeGateway):
    def transcribe(
        self,
        data: bytes,
        mime: str,
        *,
        language: str | None = None,
        instruction: str | None = None,
        task: str = "transcribe",
        model: Any = None,
        course_id: int | None = None,
    ) -> TranscriptionResult:
        raise TaskUnassigned(task)


@pytest.fixture
def gateway() -> TranscribeGateway:
    return TranscribeGateway()


@pytest.fixture
def client(
    tmp_path: Path, gateway: TranscribeGateway
) -> Iterator[tuple[TestClient, TranscribeGateway, FastAPI]]:
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, gateway, app


def post_audio(
    test_client: TestClient,
    data: bytes = b"RIFFfakeaudio",
    mime: str = "audio/webm",
    name: str = "dictation.webm",
    language: str | None = None,
) -> Any:
    request_data: dict[str, str] = {"language": language} if language else {}
    return test_client.post(
        "/api/v1/ai/transcribe",
        files={"file": (name, data, mime)},
        data=request_data,
    )


def test_transcribe_task_and_audio_default_seeded(
    client: tuple[TestClient, TranscribeGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        tasks = test_client.get("/api/v1/tasks").json()
        entry = next(item for item in tasks if item["task"] == "transcribe")
        assert entry["requires"] == "audio"
        defaults = test_client.get("/api/v1/tasks/defaults").json()
        assert any(item["requires"] == "audio" for item in defaults)


def test_transcribe_skill_seeded(
    client: tuple[TestClient, TranscribeGateway, FastAPI],
) -> None:
    test_client, _gateway, app = client
    with test_client:
        from app.services.skills import SkillService

        with app.state.session_factory() as session:
            version = SkillService(session).resolve("transcribe.audio")
            assert version is not None
            assert version.skill.task == "transcribe"


def test_transcribe_ok(
    client: tuple[TestClient, TranscribeGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        response = post_audio(test_client, language="en")
        assert response.status_code == 200, response.text
        assert response.json() == {"text": "hello from dictation", "model": "whisper-1"}
        data, mime, language, instruction = gateway.audio_calls[0]
        assert data == b"RIFFfakeaudio"
        assert mime == "audio/webm"
        assert language == "en"
        assert instruction is not None
        assert "speech-to-text" in instruction


def test_transcribe_without_language(
    client: tuple[TestClient, TranscribeGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        response = post_audio(test_client)
        assert response.status_code == 200
        assert gateway.audio_calls[0][2] is None


def test_transcribe_rejects_non_audio(
    client: tuple[TestClient, TranscribeGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        response = post_audio(test_client, mime="text/plain", name="notes.txt")
        assert response.status_code == 422
        response = post_audio(test_client, data=b"")
        assert response.status_code == 422


def test_transcribe_rejects_bad_language(
    client: tuple[TestClient, TranscribeGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        response = post_audio(test_client, language="not a language")
        assert response.status_code == 422


def test_transcribe_rejects_oversize(
    client: tuple[TestClient, TranscribeGateway, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        import app.api.ai as ai_module

        monkeypatch.setattr(ai_module, "MAX_AUDIO_BYTES", 8)
        response = post_audio(test_client, data=b"1234567890")
        assert response.status_code == 413


def test_transcribe_unassigned_409(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=UnassignedTranscribeGateway(),
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        response = post_audio(test_client)
        assert response.status_code == 409
        assert "unassigned" in response.json()["detail"].lower()


def test_transcribe_provider_error_502(
    client: tuple[TestClient, TranscribeGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    gateway.error = ProviderError.__new__(ProviderError)
    gateway.error.args = ("provider request failed: HTTP 500 boom",)
    with test_client:
        response = post_audio(test_client)
        assert response.status_code == 502
