"""Content-keyed bibliography parser (plan 85 B, ADR-212).

BibTeX/RIS are uploaded files, not URLs: the URL registry never sees them.
This parser registers into the content-match registry (`build_content_registry`)
and delegates the format work to the content service.
"""

from typing import Any

from ..services.content.bibliography import (
    BibliographyError,
    detect_format,
    parse_bibliography,
)


class BibliographyParser:
    id = "bibliography"

    def matches(self, filename: str, text: str) -> bool:
        try:
            detect_format(filename, text)
        except BibliographyError:
            return False
        return True

    def parse(self, text: str) -> list[Any]:
        fmt = detect_format("", text)
        return list(parse_bibliography(text, fmt))
