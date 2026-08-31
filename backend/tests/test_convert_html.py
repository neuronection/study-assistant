import json
from pathlib import Path

from app.pipelines.convert import html_to_markdown

FIXTURES = Path(__file__).parent / "fixtures" / "convert"


def test_html_fixture_converts_headings_links_and_tables() -> None:
    html = (FIXTURES / "lecture.html").read_text(encoding="utf-8")
    markdown = html_to_markdown(html)

    assert "# Derivatives" in markdown
    assert "## Rules" in markdown
    assert "[power rule](https://en.wikipedia.org/wiki/Derivative)" in markdown
    assert "Function" in markdown and "cos(x)" in markdown
    assert "End of extract." in markdown


def test_html_converter_drops_scripts_and_styles() -> None:
    html = (FIXTURES / "lecture.html").read_text(encoding="utf-8")
    markdown = html_to_markdown(html)

    assert "alert" not in markdown
    assert "console.log" not in markdown
    assert "color: red" not in markdown


def test_html_converter_replaces_mathml_with_placeholder() -> None:
    html = (FIXTURES / "lecture.html").read_text(encoding="utf-8")
    markdown = html_to_markdown(html)

    assert "[math-block]" in markdown
    assert "<math" not in markdown
    assert "<mi>" not in markdown


def test_html_converter_handles_inline_fragments() -> None:
    markdown = html_to_markdown("<p>plain <strong>bold</strong> text</p>")
    assert "plain **bold** text" in markdown


def test_html_converter_keeps_images_as_references() -> None:
    markdown = html_to_markdown('<p>before <img src="fig1.png" alt="Figure 1"> after</p>')
    assert "![Figure 1]" in markdown
    assert "fig1.png" in markdown
    assert json.dumps(markdown)[:1] == '"'
