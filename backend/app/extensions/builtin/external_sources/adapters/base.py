"""The SourceAdapter seam (plan 86 A, ADR-214).

One provider-agnostic reconciliation contract: every provider answers
``list``/``changes``/``fetch`` (plus optional ``put`` for the backup
destination verb) and the shared engine owns classification, the suggestion
funnel, acceptance and versioning. Adapters are T1 bundled code; provider
identity is catalog data, never a DB CHECK.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Protocol

from .....core.vocab import DiscoveryKind, MaterialKind


@dataclass(frozen=True)
class RemoteEntry:
    remote_id: str
    name: str
    url: str
    mime: str | None = None
    size: int | None = None
    mtime: str | None = None
    etag: str | None = None
    title: str | None = None
    kind: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        return self.etag or self.mtime or ""


@dataclass(frozen=True)
class ChangeSet:
    upserted: list[RemoteEntry]
    vanished: list[str]
    cursor: dict[str, Any]
    not_modified: bool = False


class SourceAdapter(Protocol):
    provider_id: str
    kinds: tuple[str, ...]
    auth_kind: str

    def list(self, source: Any) -> list[RemoteEntry]: ...

    def changes(self, source: Any, cursor: dict[str, Any]) -> ChangeSet: ...

    def fetch(self, source: Any, entry: RemoteEntry) -> bytes: ...

    def auth_probe(self, source: Any) -> str: ...


MEDIA_MIME_ALLOWLIST = {
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/wav",
    "audio/x-wav",
    "audio/ogg",
    "audio/opus",
    "audio/webm",
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-matroska",
}

MEDIA_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".wav",
    ".ogg",
    ".opus",
    ".mpga",
    ".webm",
    ".mp4",
    ".mpeg",
    ".mov",
    ".mkv",
}

_DISCOVERY_BY_MIME = {
    "application/pdf": DiscoveryKind.PAPER,
    "application/epub+zip": DiscoveryKind.ARTICLE,
    "text/markdown": DiscoveryKind.ARTICLE,
    "text/plain": DiscoveryKind.ARTICLE,
    "text/html": DiscoveryKind.ARTICLE,
}


def _extension(name: str) -> str:
    return PurePosixPath(name).suffix.lower()


def material_kind_for(name: str, mime: str | None) -> str | None:
    from .....services.content.materials import UnsupportedMaterialError, detect_kind

    try:
        return detect_kind(name)
    except UnsupportedMaterialError:
        pass
    if mime:
        guessed = mimetypes.guess_extension(mime.split(";")[0].strip())
        if guessed:
            try:
                return detect_kind(f"file{guessed}")
            except UnsupportedMaterialError:
                return None
    return None


def discovery_kind_for(name: str, mime: str | None) -> str:
    extension = _extension(name)
    media_type = (mime or "").split(";")[0].strip().lower()
    if media_type in MEDIA_MIME_ALLOWLIST or extension in MEDIA_EXTENSIONS:
        if media_type.startswith("audio"):
            return DiscoveryKind.OTHER.value
        return DiscoveryKind.VIDEO.value
    if media_type in _DISCOVERY_BY_MIME:
        return _DISCOVERY_BY_MIME[media_type].value
    material_kind = material_kind_for(name, mime)
    if material_kind in {MaterialKind.AUDIO.value}:
        return DiscoveryKind.OTHER.value
    if material_kind in {MaterialKind.VIDEO.value}:
        return DiscoveryKind.VIDEO.value
    if material_kind in {MaterialKind.PDF.value}:
        return DiscoveryKind.PAPER.value
    return DiscoveryKind.ARTICLE.value


def is_media(name: str, mime: str | None) -> bool:
    media_type = (mime or "").split(";")[0].strip().lower()
    return media_type in MEDIA_MIME_ALLOWLIST or _extension(name) in MEDIA_EXTENSIONS
