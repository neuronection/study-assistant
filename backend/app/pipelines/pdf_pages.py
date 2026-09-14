import re
from dataclasses import dataclass

import fitz

MIN_TEXT_CHARS_PER_PAGE = 50
GARBAGE_CHARACTER_RATIO = 0.01
FIGURE_COVERAGE_THRESHOLD = 0.5
FIGURE_TEXT_CEILING = 200

_CID_MARKER_RE = re.compile(r"\(cid:\d+\)")
_REPLACEMENT_CHAR = "\ufffd"

RID_TEXT_OK = "text-ok"
RID_THIN_TEXT = "thin-text"
RID_GARBAGE_GLYPHS = "garbage-glyphs"
RID_FIGURE_DOMINANT = "figure-dominant"


@dataclass(frozen=True)
class PageDecision:
    ordinal: int
    use_text: bool
    reason: str


def page_image_coverage(page: fitz.Page) -> float:
    page_area = float(abs(page.rect))
    if page_area <= 0:
        return 0.0
    covered = 0.0
    for info in page.get_image_info():
        x0, y0, x1, y1 = (float(value) for value in info["bbox"])
        covered += max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return float(min(1.0, covered / page_area))


def garbage_ratio(text: str) -> float:
    if not text:
        return 0.0
    garbage = sum(len(marker) for marker in _CID_MARKER_RE.findall(text))
    garbage += text.count(_REPLACEMENT_CHAR)
    if garbage == 0:
        return 0.0
    return garbage / len(text)


def score_page(text: str, image_coverage: float, ordinal: int = 0) -> PageDecision:
    stripped = text.strip()
    if garbage_ratio(stripped) > GARBAGE_CHARACTER_RATIO:
        return PageDecision(ordinal, False, RID_GARBAGE_GLYPHS)
    if len(stripped) < MIN_TEXT_CHARS_PER_PAGE:
        return PageDecision(ordinal, False, RID_THIN_TEXT)
    if (
        image_coverage >= FIGURE_COVERAGE_THRESHOLD
        and len(stripped) < FIGURE_TEXT_CEILING
    ):
        return PageDecision(ordinal, False, RID_FIGURE_DOMINANT)
    return PageDecision(ordinal, True, RID_TEXT_OK)


def plan_pages(doc: fitz.Document) -> list[tuple[PageDecision, str]]:
    planned: list[tuple[PageDecision, str]] = []
    for ordinal, page in enumerate(doc):
        text = page.get_text("text")
        decision = score_page(text, page_image_coverage(page), ordinal)
        planned.append((decision, text))
    return planned
