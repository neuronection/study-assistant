import base64
from dataclasses import dataclass

import httpx

from .types import ResolvedModel, Usage

EXT_BY_MIME: dict[str, str] = {
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/flac": "flac",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
}

DEFAULT_TRANSCRIBE_INSTRUCTION = (
    "Transcribe the attached audio exactly as spoken. Output ONLY the transcript."
)


class TranscriptionUnsupported(RuntimeError):
    def __init__(self, provider_type: str) -> None:
        super().__init__(
            f"provider '{provider_type}' does not offer speech-to-text — assign an "
            "OpenAI-compatible (Whisper) or Google model for the transcribe task"
        )
        self.provider_type = provider_type


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    model: str


def audio_extension(mime: str) -> str:
    return EXT_BY_MIME.get(mime.split(";")[0].strip().lower(), "webm")


def transcribe_with(
    client: httpx.Client,
    resolved: ResolvedModel,
    data: bytes,
    mime: str,
    language: str | None,
    instruction: str | None,
) -> tuple[str, Usage | None]:
    if mime.startswith("video/") and resolved.provider_type == "google":
        raise TranscriptionUnsupported(
            f"{resolved.provider_type} inline transcription does not accept video "
            "(audio only) — use an OpenAI-compatible provider for video files"
        )
    if resolved.provider_type == "openai_compatible":
        return _transcribe_openai(client, resolved, data, mime, language)
    if resolved.provider_type == "google":
        return _transcribe_google(client, resolved, data, mime, instruction)
    raise TranscriptionUnsupported(resolved.provider_type)


def _transcribe_openai(
    client: httpx.Client,
    resolved: ResolvedModel,
    data: bytes,
    mime: str,
    language: str | None,
) -> tuple[str, Usage | None]:
    form: list[
        tuple[
            str,
            tuple[str | None, bytes | str] | tuple[str | None, bytes | str, str | None],
        ]
    ] = [
        ("model", (None, resolved.external_id)),
        ("response_format", (None, "json")),
        ("file", (f"audio.{audio_extension(mime)}", data, mime or "audio/webm")),
    ]
    if language:
        form.append(("language", (None, language)))
    response = client.post(
        f"{resolved.base_url}/audio/transcriptions",
        headers={"Authorization": f"Bearer {resolved.api_key}"} if resolved.api_key else {},
        files=form,
    )
    response.raise_for_status()
    body = response.json()
    usage = _usage_from_tokens(body.get("usage"))
    return str(body.get("text", "")).strip(), usage


def _transcribe_google(
    client: httpx.Client,
    resolved: ResolvedModel,
    data: bytes,
    mime: str,
    instruction: str | None,
) -> tuple[str, Usage | None]:
    response = client.post(
        f"{resolved.base_url}/v1beta/models/{resolved.external_id}:generateContent",
        params={"key": resolved.api_key},
        json={
            "systemInstruction": {
                "parts": [{"text": instruction or DEFAULT_TRANSCRIBE_INSTRUCTION}]
            },
            "contents": [
                {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime or "audio/webm",
                                "data": base64.b64encode(data).decode("ascii"),
                            }
                        },
                        {"text": "Transcribe this audio."},
                    ]
                }
            ],
            "generationConfig": {"temperature": 0},
        },
    )
    response.raise_for_status()
    body = response.json()
    text = "".join(
        str(part.get("text", ""))
        for part in (body.get("candidates", [{}])[0].get("content", {}).get("parts", []))
    ).strip()
    metadata = body.get("usageMetadata") or {}
    usage = _usage_from_tokens(
        {
            "input_tokens": metadata.get("promptTokenCount"),
            "output_tokens": metadata.get("candidatesTokenCount"),
        }
    )
    return text, usage


def _usage_from_tokens(raw: object) -> Usage | None:
    if not isinstance(raw, dict):
        return None
    tokens_in = raw.get("input_tokens", raw.get("prompt_tokens"))
    tokens_out = raw.get("output_tokens", raw.get("completion_tokens"))
    if not isinstance(tokens_in, int) or not isinstance(tokens_out, int):
        return None
    return Usage(tokens_in=tokens_in, tokens_out=tokens_out)
