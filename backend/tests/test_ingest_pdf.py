import pytest

from app.jobs.runner import JobError
from app.pipelines.ingest import extract_pdf_text


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
    markdown, pages, has_text = extract_pdf_text(data)
    assert pages == 1
    assert has_text is True
    assert "derivative of sin(x)" in markdown
    assert "cos(x)" in markdown


def test_blank_pdf_reports_no_text_layer() -> None:
    import fitz

    doc = fitz.open()
    doc.new_page()
    markdown, _pages, has_text = extract_pdf_text(doc.tobytes())
    assert has_text is False
    assert markdown == ""


def test_corrupt_pdf_raises_job_error() -> None:
    with pytest.raises(JobError):
        extract_pdf_text(b"not a pdf at all")
