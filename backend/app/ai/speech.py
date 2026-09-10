import base64
import struct
from dataclasses import dataclass

import httpx

from .types import ResolvedModel, Usage

DEFAULT_VOICE = "Kore"

MAX_TTS_CHARS = 10_000


class SpeechUnsupported(RuntimeError):
    def __init__(self, provider_type: str) -> None:
        super().__init__(
            f"provider '{provider_type}' does not offer text-to-speech — assign an "
            "OpenAI-compatible (tts-*) or Google TTS model for the tts task"
        )
        self.provider_type = provider_type


@dataclass(frozen=True)
class SpeechResult:
    audio: bytes
    mime: str
    model: str


def speak_with(
    client: httpx.Client,
    resolved: ResolvedModel,
    text: str,
    voice: str | None,
) -> tuple[bytes, str, Usage | None]:
    if resolved.provider_type == "openai_compatible":
        return _speak_openai(client, resolved, text, voice)
    if resolved.provider_type == "google":
        return _speak_google(client, resolved, text, voice)
    raise SpeechUnsupported(resolved.provider_type)


def _speak_openai(
    client: httpx.Client,
    resolved: ResolvedModel,
    text: str,
    voice: str | None,
) -> tuple[bytes, str, Usage | None]:
    response = client.post(
        f"{resolved.base_url}/audio/speech",
        headers={"Authorization": f"Bearer {resolved.api_key}"} if resolved.api_key else {},
        json={
            "model": resolved.external_id,
            "input": text,
            "voice": voice or "alloy",
            "response_format": "mp3",
        },
    )
    response.raise_for_status()
    return response.content, "audio/mpeg", None


def _speak_google(
    client: httpx.Client,
    resolved: ResolvedModel,
    text: str,
    voice: str | None,
) -> tuple[bytes, str, Usage | None]:
    response = client.post(
        f"{resolved.base_url}/v1beta/models/{resolved.external_id}:generateContent",
        params={"key": resolved.api_key},
        json={
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": voice or DEFAULT_VOICE}
                    }
                },
            },
        },
    )
    response.raise_for_status()
    body = response.json()
    parts = body.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    inline = next(
        (part.get("inlineData") for part in parts if part.get("inlineData")), None
    )
    if inline is None:
        raise RuntimeError("google TTS response carried no audio part")
    audio = base64.b64decode(str(inline.get("data", "")))
    mime = str(inline.get("mimeType", "")).lower()
    usage = _usage_from_tokens(body.get("usageMetadata"))
    if mime.startswith("audio/l16") or mime.startswith("audio/pcm"):
        rate = 24000
        for token in mime.replace(";", "|").split("|"):
            if token.startswith("rate="):
                try:
                    rate = int(token.split("=", 1)[1])
                except ValueError:
                    rate = 24000
        return wrap_pcm_as_wav(audio, rate), "audio/wav", usage
    return audio, mime or "audio/wav", usage


def wrap_pcm_as_wav(pcm: bytes, sample_rate: int, channels: int = 1) -> bytes:
    """Wrap raw 16-bit PCM in a minimal 44-byte WAV header (Gemini TTS
    returns mono s16le L16 at 24 kHz)."""
    bits_per_sample = 16
    block_align = channels * bits_per_sample // 8
    byte_rate = sample_rate * block_align
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        len(pcm),
    )
    return header + pcm


def _usage_from_tokens(metadata: object) -> Usage | None:
    if not isinstance(metadata, dict):
        return None
    tokens_in = metadata.get("promptTokenCount")
    tokens_out = metadata.get("candidatesTokenCount")
    if not isinstance(tokens_in, int) or not isinstance(tokens_out, int):
        return None
    return Usage(tokens_in=tokens_in, tokens_out=tokens_out)
