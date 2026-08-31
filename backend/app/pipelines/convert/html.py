import re

import html2text

_MATH_BLOCK_RE = re.compile(r"<math\b.*?</math\s*>", re.DOTALL | re.IGNORECASE)

_MATH_PLACEHOLDER = "\n\n[math-block]\n\n"


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
