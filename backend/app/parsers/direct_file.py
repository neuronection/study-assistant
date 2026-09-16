from urllib.parse import urlparse

import httpx

from .base import DOWNLOADABLE_SUFFIXES, ParsedDocument, ParserError

MAX_BYTES = 200 * 1024 * 1024

MIME_BY_SUFFIX: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".epub": "application/epub+zip",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".webm": "video/webm",
}


class DirectFileParser:
    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        max_bytes: int = MAX_BYTES,
    ) -> None:
        self._transport = transport
        self._max_bytes = max_bytes

    def matches(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        path = parsed.path.lower()
        return any(path.endswith(suffix) for suffix in DOWNLOADABLE_SUFFIXES)

    def fetch(self, url: str) -> ParsedDocument:
        parsed = urlparse(url)
        path = parsed.path.lower()
        kind_hint = next(
            (
                kind
                for suffix, kind in DOWNLOADABLE_SUFFIXES.items()
                if path.endswith(suffix)
            ),
            None,
        )
        try:
            with httpx.Client(
                transport=self._transport,
                follow_redirects=True,
                timeout=120.0,
            ) as client, client.stream("GET", url) as response:
                    if response.status_code != 200:
                        raise ParserError(
                            f"download returned {response.status_code} for {url}"
                        )
                    content_type = response.headers.get("content-type", "")
                    if "text/html" in content_type.lower():
                        raise ParserError(
                            f"URL returned an HTML page instead of a file: {url}"
                        )
                    declared = response.headers.get("content-length")
                    if declared and int(declared) > self._max_bytes:
                        raise ParserError("file exceeds upload size limit")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > self._max_bytes:
                            raise ParserError("file exceeds upload size limit")
                        chunks.append(chunk)
        except httpx.HTTPError as error:
            raise ParserError(f"download failed: {error}") from error
        blob = b"".join(chunks)
        if not blob:
            raise ParserError(f"downloaded file is empty: {url}")
        filename = path.rsplit("/", 1)[-1] or "download"
        mime = MIME_BY_SUFFIX.get(path.rsplit(".", 1)[-1].join((".", "")))
        return ParsedDocument(
            title=filename[:300],
            markdown=None,
            metadata={"source": "download", "url": url},
            kind_hint=kind_hint,
            blob=blob,
            mime=mime,
        )
