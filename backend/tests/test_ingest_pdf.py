import fitz
import pytest

from app.jobs.runner import JobError
from app.pipelines.ingest import _open_pdf, extract_pdf_text
from app.pipelines.pdf_pages import (
    RID_GARBAGE_GLYPHS,
    RID_TEXT_OK,
    RID_THIN_TEXT,
    plan_pages,
    score_page,
)


def make_pdf(lines: list[str]) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 14
    return bytes(doc.tobytes())


def test_text_pdf_extracts_markdown_and_page_count() -> None:
    data = make_pdf(
        [
            "Differentiation rules",
            "The derivative of sin(x) with respect to x",
            "is cos(x). This follows from the limit of the",
            "difference quotient applied to the sine function.",
        ]
    )
    markdown, pages = extract_pdf_text(data)
    assert pages == 1
    assert "derivative of sin(x)" in markdown
    assert "cos(x)" in markdown


def test_blank_page_plans_ocr_thin_text() -> None:
    doc = fitz.open()
    doc.new_page()
    planned = plan_pages(doc)
    assert len(planned) == 1
    decision, text = planned[0]
    assert decision.use_text is False
    assert decision.reason == RID_THIN_TEXT
    assert text == ""


def test_score_page_reasons_and_boundaries() -> None:
    good = "This page has a healthy amount of text content on it. " * 2
    decision = score_page(good, 0.0, 0)
    assert decision.use_text and decision.reason == RID_TEXT_OK

    thin = "too short"
    assert score_page(thin, 0.0).use_text is False
    assert score_page(thin, 0.0).reason == RID_THIN_TEXT

    garbage = " ".join(f"(cid:{index})" for index in range(45))
    assert len(garbage) >= 50
    cid_decision = score_page(garbage, 0.0)
    assert cid_decision.use_text is False
    assert cid_decision.reason == RID_GARBAGE_GLYPHS

    figure = (
        "A caption of medium length that clears the thin-page floor but stays short enough "
        "to count as figure-dominated when the image covers most of the page."
    )
    covered = score_page(figure, 0.8)
    assert covered.use_text is False
    assert covered.reason == "figure-dominant"


def test_corrupt_pdf_raises_job_error() -> None:
    with pytest.raises(JobError):
        extract_pdf_text(b"not a pdf at all")
    with pytest.raises(JobError):
        _open_pdf(b"not a pdf at all")


def test_full_page_image_with_long_text_kept_as_text() -> None:
    doc = fitz.open()
    page = doc.new_page()
    lines = [
        "A caption with plenty of surrounding body text: the derivative of a product",
        "follows the product rule, which we derive from the definition of the derivative",
        "and the limit of the difference quotient, and the result is stated below with",
        "its geometric interpretation and a worked example for the students to practice.",
    ]
    paragraph = " ".join(lines)
    assert len(paragraph) >= 200
    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 14
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 4))
    page.insert_image(page.rect, stream=bytes(pix.tobytes("png")))
    planned = plan_pages(doc)
    decision, text = planned[0]
    assert decision.use_text is True, decision.reason
    assert "product" in text
