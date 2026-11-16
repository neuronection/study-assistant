from dataclasses import dataclass
from typing import Protocol

from ...core.vocab import CaptureKind


class CaptureSource(Protocol):
    @property
    def kind(self) -> CaptureKind: ...

    def accepts(self, filename: str, mime: str | None) -> bool: ...


@dataclass(frozen=True)
class LocalCaptureSource:
    kind: CaptureKind

    def accepts(self, filename: str, mime: str | None) -> bool:
        return bool(filename)


SOURCES: dict[CaptureKind, CaptureSource] = {
    CaptureKind.UPLOAD: LocalCaptureSource(CaptureKind.UPLOAD),
    CaptureKind.CAMERA: LocalCaptureSource(CaptureKind.CAMERA),
    CaptureKind.CLIPBOARD: LocalCaptureSource(CaptureKind.CLIPBOARD),
    CaptureKind.DROP: LocalCaptureSource(CaptureKind.DROP),
}


def source_for(value: str) -> CaptureSource:
    try:
        kind = CaptureKind(value)
    except ValueError:
        raise ValueError(f"unknown capture source '{value}'") from None
    source = SOURCES.get(kind)
    if source is None:
        raise ValueError(f"capture source '{value}' is not available in this build")
    return source
