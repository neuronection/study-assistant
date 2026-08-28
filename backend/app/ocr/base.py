from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class OcrPageResult:
    markdown: str
    raw_text: str


class OcrEngine(ABC):
    @abstractmethod
    def ocr_image(self, data: bytes, mime: str, *, context: str = "") -> OcrPageResult:
        raise NotImplementedError
