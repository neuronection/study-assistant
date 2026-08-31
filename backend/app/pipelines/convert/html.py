import base64
import re
from collections.abc import Callable

import html2text

_MATH_BLOCK_RE = re.compile(r"<math\b.*?</math\s*>", re.DOTALL | re.IGNORECASE)

_MATH_PLACEHOLDER = "\n\n[math-block]\n\n"

_DATA_URI_RE = re.compile(r'src="data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=]+)"')


def _drop_math_blocks(html: str) -> str:
    return _MATH_BLOCK_RE.sub(_MATH_PLACEHOLDER, html)


def _normalize_whitespace(markdown: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", markdown).strip() + "\n"


def _make_converter() -> html2text.HTML2Text:
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_images = False
    converter.ignore_links = False
    converter.ignore_tables = False
    converter.ignore_emphasis = False
    converter.single_line_break = False
    converter.pad_tables = True
    converter.mark_code = True
    return converter


_CONVERTER = _make_converter()


def html_to_markdown(html: str) -> str:
    """Convert an HTML fragment or document into canonical house markdown.

    MathML blocks are replaced with a ``[math-block]`` placeholder token:
    no pure-Python converter handles MathML faithfully, and the extraction
    QA editor is the correction surface (same policy as OCR).
    """
    prepared = _drop_math_blocks(html)
    markdown = _CONVERTER.handle(prepared)
    return _normalize_whitespace(markdown)


def convert_html_document(
    data: bytes, store_image: Callable[[bytes, str | None], int]
) -> str:
    """Convert an uploaded HTML material. Data-URI images are stored via
    ``store_image`` and replaced with ``ca-image://`` refs; external image
    URLs pass through untouched."""
    html = data.decode("utf-8", errors="replace")

    def embed(match: re.Match[str]) -> str:
        mime = match.group(1)
        try:
            payload = base64.b64decode(match.group(2))
        except (ValueError, TypeError):
            return match.group(0)
        image_id = store_image(payload, mime)
        return f'src="ca-image://{image_id}"'

    rewritten = _DATA_URI_RE.sub(embed, html)
    return html_to_markdown(rewritten)
