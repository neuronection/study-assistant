import re

from sqlalchemy.orm import Session

from ..ai.gateway import ImagePart, LLMGateway, Message, TextPart
from ..ai.skills import NOTES_OCR_SYSTEM
from ..services.platform.skills import SkillService
from .imaging import ocr_image_max_edge, prepare_ocr_image

NOTES_OCR_TASK = "notes_ocr"
NOTES_OCR_SKILL = "notes.transcribe"

_FENCE_RE = re.compile(r"^```(?:markdown|md|latex)?\s*\n(.*)\n```\s*$", re.DOTALL)


def _strip_outer_fence(text: str) -> str:
    match = _FENCE_RE.match(text.strip())
    return match.group(1).strip() if match else text.strip()


class NotesOcrEngine:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def transcribe(self, data: bytes, mime: str, session: Session | None = None) -> str:
        payload, payload_mime = prepare_ocr_image(
            data, mime, ocr_image_max_edge(session)
        )
        system = NOTES_OCR_SYSTEM
        if session is not None:
            skills = SkillService(session)
            version = skills.resolve(NOTES_OCR_SKILL, course_id=None)
            if version is not None:
                rendered, _user = skills.render(version, {})
                system = rendered
        text = self._gateway.generate(
            NOTES_OCR_TASK,
            [
                Message(role="system", content=system),
                Message(
                    role="user",
                    content=[
                        TextPart(text="Transcribe this handwritten work."),
                        ImagePart(data=payload, mime=payload_mime),
                    ],
                ),
            ],
        )
        return _strip_outer_fence(text)
