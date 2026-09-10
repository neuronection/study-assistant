import struct
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from test_chat_api import NoDescriber, NoEmbedder

from app.ai.gateway import BudgetExceeded, LLMGateway, ProviderError, TaskUnassigned
from app.ai.speech import (
    MAX_TTS_CHARS,
    SpeechUnsupported,
    speak_with,
    wrap_pcm_as_wav,
)
from app.ai.types import ResolvedModel
from app.core.config import Settings
from app.main import create_app

AUDIO_BYTES = b"\x00\x01\x02\x03fake-mp3"


class SpeechGateway(LLMGateway):
    def __init__(self, error: Exception | None = None) -> None:
        super().__init__(session_factory=None)
        self.error = error
        self.calls: list[str] = []

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="tts-1",
            label="tts-1",
            caps=["speech"],
            api_key=None,
        )

    def speak(
        self,
        text: str,
        *,
        voice: str | None = None,
        task: str = "tts",
        model: ResolvedModel | None = None,
        course_id: int | None = None,
    ) -> Any:
        del voice, task, model, course_id
        if self.error is not None:
            raise self.error
        self.calls.append(text)
        from app.ai.speech import SpeechResult

        return SpeechResult(audio=AUDIO_BYTES, mime="audio/mpeg", model="tts-1")


@pytest.fixture
def speak_client(tmp_path: Any) -> Iterator[tuple[TestClient, SpeechGateway]]:
    gateway = SpeechGateway()
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, gateway


def test_speak_returns_audio(speak_client: tuple[TestClient, SpeechGateway]) -> None:
    test_client, gateway = speak_client
    response = test_client.post(
        "/api/v1/ai/speak", json={"text": "Read this aloud please."}
    )
    assert response.status_code == 200, response.text
    assert response.content == AUDIO_BYTES
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.headers["x-speech-model"] == "tts-1"
    assert gateway.calls == ["Read this aloud please."]


def test_speak_rejects_oversized_text(
    speak_client: tuple[TestClient, SpeechGateway],
) -> None:
    test_client, _gateway = speak_client
    response = test_client.post(
        "/api/v1/ai/speak", json={"text": "x" * (MAX_TTS_CHARS + 1)}
    )
    assert response.status_code == 422


def test_speak_maps_task_unassigned(tmp_path: Any) -> None:
    gateway = SpeechGateway(error=TaskUnassigned("tts"))
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/ai/speak", json={"text": "hello"})
        assert response.status_code == 409


def test_speak_maps_budget_and_provider_errors(
    speak_client: tuple[TestClient, SpeechGateway],
) -> None:
    test_client, gateway = speak_client
    gateway.error = BudgetExceeded("tts", 5.0, 4.0)
    too_many = test_client.post("/api/v1/ai/speak", json={"text": "hello"})
    assert too_many.status_code == 429
    gateway.error = ProviderError(gateway.resolve("tts"), "boom")
    bad_provider = test_client.post("/api/v1/ai/speak", json={"text": "hello"})
    assert bad_provider.status_code == 502


def test_speak_with_openai_compatible() -> None:
    resolved = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost/v1",
        external_id="tts-1",
        label="tts-1",
        caps=["speech"],
        api_key=None,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/audio/speech")
        body = request.read()
        assert b'"model":"tts-1"' in body.replace(b" ", b"") or b"tts-1" in body
        return httpx.Response(200, content=AUDIO_BYTES)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        audio, mime, usage = speak_with(client, resolved, "hello", None)
    assert audio == AUDIO_BYTES
    assert mime == "audio/mpeg"
    assert usage is None


def test_speak_with_google_pcm_wrapped_as_wav() -> None:
    import base64

    resolved = ResolvedModel(
        provider_id=2,
        provider_type="google",
        base_url="http://localhost",
        external_id="gemini-2.5-flash-preview-tts",
        label="gemini-tts",
        caps=["speech"],
        api_key="k",
    )
    pcm = struct.pack("<4h", 1, -1, 32767, -32768)
    payload = base64.b64encode(pcm).decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "generateContent" in request.url.path
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "audio/L16;rate=24000",
                                        "data": payload,
                                    }
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 7},
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        audio, mime, usage = speak_with(client, resolved, "hello", None)
    assert mime == "audio/wav"
    assert audio == wrap_pcm_as_wav(pcm, 24000)
    assert audio[:4] == b"RIFF"
    assert audio[8:12] == b"WAVE"
    assert struct.unpack("<I", audio[40:44])[0] == len(pcm)
    assert usage is not None and usage.tokens_in == 5 and usage.tokens_out == 7


def test_speak_with_anthropic_unsupported() -> None:
    resolved = ResolvedModel(
        provider_id=3,
        provider_type="anthropic",
        base_url="http://localhost",
        external_id="claude-sonnet",
        label="claude",
        caps=["text"],
        api_key=None,
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, text="nope")
    )
    with httpx.Client(transport=transport) as client, pytest.raises(SpeechUnsupported):
        speak_with(client, resolved, "hello", None)


def test_wrap_pcm_as_wav_header() -> None:
    pcm = b"\x00\x00\x00\x00"
    wav = wrap_pcm_as_wav(pcm, 24000)
    assert len(wav) == 44 + len(pcm)
    riff_size = struct.unpack("<I", wav[4:8])[0]
    assert riff_size == 36 + len(pcm)
    channels = struct.unpack("<H", wav[22:24])[0]
    sample_rate = struct.unpack("<I", wav[24:28])[0]
    bits = struct.unpack("<H", wav[34:36])[0]
    assert (channels, sample_rate, bits) == (1, 24000, 16)


def test_tts_task_registered_and_speech_capability_seeded() -> None:
    from app.ai.tasks import TASKS_BY_NAME
    from app.core.vocab import Capability

    assert "tts" in TASKS_BY_NAME
    assert TASKS_BY_NAME["tts"].requires == Capability.SPEECH.value
