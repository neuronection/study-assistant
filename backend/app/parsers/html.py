import re

import httpx

from ..search.provider import SearchError, perform_fetch
from .base import ParsedDocument, ParserError


class HtmlParser:
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def matches(self, url: str) -> bool:
        return url.startswith(("http://", "https://"))

    def fetch(self, url: str) -> ParsedDocument:
        from urllib.parse import urlparse

        try:
            markdown = perform_fetch(url, transport=self._transport)
        except SearchError as error:
            raise ParserError(str(error)) from error
        parsed = urlparse(url)
        host = parsed.netloc.split(":")[0]
        slug = parsed.path.rstrip("/").rsplit("/", 1)[-1] or host
        title = re.sub(r"[-_]+", " ", slug).strip() or host
        return ParsedDocument(
            title=title[:300],
            markdown=markdown,
            metadata={"source": "web", "url": url},
            kind_hint=None,
            blob=None,
        )
