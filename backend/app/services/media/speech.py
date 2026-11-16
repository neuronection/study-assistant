from typing import Any

from ...ai.gateway import LLMGateway


class SpeechPipeline:
    """Provider-agnostic speech orchestration; HTTP stays in the gateway."""

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def transcribe_chunks(
        self,
        chunks: list[tuple[bytes, str]],
        *,
        language: str | None = None,
        course_id: str | None = None,
    ) -> list[str]:
        return [
            self._gateway.transcribe(
                data,
                mime,
                language=language,
                course_id=course_id,
            ).text
            for data, mime in chunks
        ]

    def synthesize(
        self, text: str, *, voice: str | None = None, course_id: str | None = None
    ) -> Any:
        return self._gateway.speak(text, voice=voice, course_id=course_id)
