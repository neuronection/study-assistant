import re
from typing import Any

from .gateway import LLMGateway, Message, TaskUnassigned

DESCRIPTION_TASK = "description"

DESCRIBE_SYSTEM_PROMPT = (
    "You summarize study material. Given a material title and its extracted text, respond "
    "with ONLY a JSON object: {\"summary\": str (2-3 sentences), \"topics\": [str] (3-8), "
    "\"key_terms\": [str] (3-10), \"difficulty\": int (1-5)}. No markdown fences, no commentary."
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class GatewayDescriber:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def describe(
        self, title: str, markdown: str, course_id: int | None = None
    ) -> dict[str, Any] | None:
        try:
            resolved = self._gateway.resolve(DESCRIPTION_TASK, course_id)
        except TaskUnassigned:
            return None
        text = self._gateway.generate(
            DESCRIPTION_TASK,
            [
                Message(role="system", content=DESCRIBE_SYSTEM_PROMPT),
                Message(
                    role="user",
                    content=f"Title: {title}\n\nExcerpt:\n{markdown[:12000]}",
                ),
            ],
            model=resolved,
            course_id=course_id,
        )
        match = _JSON_RE.search(text)
        if match is None:
            return None
        try:
            import json

            parsed = json.loads(match.group(0))
        except ValueError:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed
