import re

from sqlalchemy.orm import Session

from ..ai.gateway import ImagePart, LLMGateway, Message, TextPart
from ..ai.skills import OCR_PAGE_SYSTEM
from .base import OcrEngine, OcrPageResult
from .imaging import ocr_image_max_edge, prepare_ocr_image

OCR_TASK = "ocr"

_FENCE_RE = re.compile(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", re.DOTALL)


def _strip_outer_fence(text: str) -> str:
    match = _FENCE_RE.match(text.strip())
    return match.group(1).strip() if match else text.strip()


class GatewayOcr(OcrEngine):
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def ocr_image(
        self,
        data: bytes,
        mime: str,
        *,
        context: str = "",
        instruction: str | None = None,
        session: Session | None = None,
    ) -> OcrPageResult:
        payload, payload_mime = prepare_ocr_image(
            data, mime, ocr_image_max_edge(session)
        )
        prompt = f"Transcribe this page. {context}".strip() if context else "Transcribe this page."
        text = self._gateway.generate(
            OCR_TASK,
            [
                Message(role="system", content=instruction or OCR_PAGE_SYSTEM),
                Message(
                    role="user",
                    content=[
                        TextPart(text=prompt),
                        ImagePart(data=payload, mime=payload_mime),
                    ],
                ),
            ],
        )
        markdown = _strip_outer_fence(text)
        return OcrPageResult(markdown=markdown, raw_text=text)
