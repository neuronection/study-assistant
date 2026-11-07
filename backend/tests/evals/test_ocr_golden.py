"""Golden OCR/extraction regression gate (plan 84 C, ADR-210).

The default run is deterministic and offline: it exercises the per-page hybrid
routing (``plan_pages``/``score_page``), native PDF text extraction
(``extract_pdf_text``) and hybrid assembly (``assemble_hybrid_markdown``) and
scores the result against recorded expectations with per-fixture thresholds
(``ocr_thresholds.json``). The owner's real scans drop into
``tests/fixtures/golden/`` and are picked up automatically; until then the
synthetic fixtures generated below prove the gate mechanics — the routing,
assembly and quality metrics are real even though the pixels are synthetic.

The vision half is opt-in (``SA_EVAL_LIVE=1``) and never runs in the default
suite — it would need a live provider, which the family test-isolation rules
forbid.
"""

import difflib
import io
import json
import os
import re
from pathlib import Path
from typing import Any, cast

import fitz
import pytest
from PIL import Image

from app.pipelines.ingest import extract_pdf_text
from app.pipelines.pdf_pages import assemble_hybrid_markdown, plan_pages

EVALS = Path(__file__).parent
GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "golden"

NATIVE_CLEAN_TEXT = """Chain rule

The chain rule states that dy/dx = dy/du * du/dx for composite functions.

Worked example: differentiate y = (3x + 1)^5.
Answer: dy/dx = 5(3x + 1)^4 * 3 = 15(3x + 1)^4.
"""

GARBAGE_NATIVE_TEXT = (
    "(cid:12)(cid:34)(cid:56)(cid:78)(cid:90)(cid:11)(cid:22)(cid:33)"
    "(cid:44)(cid:55)(cid:66)(cid:77)(cid:88)(cid:99)(cid:10)(cid:21)"
)

SCANNED_OCR_MARKDOWN = """Chain rule

The chain rule states that dy/dx = dy/du * du/dx for composite functions.

Worked example: differentiate y = (3x + 1)^5.
Answer: dy/dx = 15(3x + 1)^4.
"""

FIGURE_NATIVE_TEXT = (
    "Figure 1 shows the derivative of a composite function plotted against the "
    "inner function; the shaded band marks the region where the chain rule "
    "applies and the tangent line touches at a single point."
)

FIGURE_OCR_MARKDOWN = """Figure 1 — composite function derivative

The shaded band marks the region where the chain rule applies; the tangent
line touches the curve at exactly one point (the point of tangency)."""

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_INLINE_MATH_RE = re.compile(r"(?<!\$)\$([^$\n]+)\$(?!\$)")
_DISPLAY_MATH_RE = re.compile(r"\$\$([^$]+)\$\$")

SYNTHETIC_NAMES = {
    "synthetic-native-clean",
    "synthetic-scanned-garbage",
    "synthetic-figure-dominant",
}


def load_manifest() -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads((EVALS / "ocr_thresholds.json").read_text(encoding="utf-8"))
    return parsed


def fixture_thresholds(name: str) -> dict[str, float]:
    manifest = load_manifest()
    for fixture in manifest["fixtures"]:
        if fixture["name"] == name:
            return cast(dict[str, float], fixture["thresholds"])
    raise AssertionError(f"no manifest entry for fixture {name!r}")


def _pdf_with_text(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(72, 72, 500, 700), text, fontsize=12)
    return bytes(doc.tobytes())


def _png(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (120, 120), color).save(buffer, format="PNG")
    return buffer.getvalue()


def native_clean_pdf() -> tuple[bytes, str]:
    return _pdf_with_text(NATIVE_CLEAN_TEXT), NATIVE_CLEAN_TEXT


def garbage_glyph_pdf() -> tuple[bytes, str]:
    return _pdf_with_text(GARBAGE_NATIVE_TEXT), GARBAGE_NATIVE_TEXT


def figure_dominant_pdf() -> tuple[bytes, str]:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(0, 0, 600, 700), stream=_png((210, 210, 210)))
    page.insert_textbox(fitz.Rect(10, 10, 590, 90), FIGURE_NATIVE_TEXT, fontsize=10)
    return doc.tobytes(), FIGURE_NATIVE_TEXT


def _line_signature(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("#"):
        return "heading"
    if stripped.startswith("```") or stripped.startswith("~~~"):
        return "fence"
    if stripped.startswith("$$") or stripped.startswith("$"):
        return "math"
    if stripped.startswith("|"):
        return "table"
    if stripped.startswith(("- ", "* ", "+ ")) or re.match(r"^\d+\.\s", stripped):
        return "list"
    return "paragraph"


def block_structure_similarity(expected: str, actual: str) -> float:
    expected_sig = [_line_signature(line) for line in expected.splitlines() if line.strip()]
    actual_sig = [_line_signature(line) for line in actual.splitlines() if line.strip()]
    if not expected_sig and not actual_sig:
        return 1.0
    return difflib.SequenceMatcher(None, expected_sig, actual_sig).ratio()


def math_fence_integrity(expected: str, actual: str) -> float:
    spans = _DISPLAY_MATH_RE.findall(expected) + _INLINE_MATH_RE.findall(expected)
    if not spans:
        return 1.0
    found = sum(1 for span in spans if span in actual)
    return found / len(spans)


def numeric_fidelity(expected: str, actual: str) -> float:
    numbers = _NUMBER_RE.findall(expected)
    if not numbers:
        return 1.0
    found = sum(1 for number in numbers if number in actual)
    return found / len(numbers)


def assert_quality(name: str, expected: str, actual: str) -> None:
    thresholds = fixture_thresholds(name)
    scores = {
        "block_structure": block_structure_similarity(expected, actual),
        "math_fence": math_fence_integrity(expected, actual),
        "numeric_fidelity": numeric_fidelity(expected, actual),
    }
    failures = [
        f"{metric}={score:.3f} < threshold {thresholds[metric]:.3f}"
        for metric, score in scores.items()
        if score < thresholds[metric]
    ]
    if failures:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(), actual.splitlines(), "expected", "actual", lineterm=""
            )
        )
        raise AssertionError(
            f"fixture {name!r} below threshold:\n  "
            + "\n  ".join(failures)
            + f"\n--- diff ---\n{diff}"
        )


def _open_pdf(data: bytes) -> fitz.Document:
    return fitz.open(stream=data, filetype="pdf")


def test_native_clean_pdf_routes_to_text_and_matches_expected() -> None:
    data, expected = native_clean_pdf()
    planned = plan_pages(_open_pdf(data))
    assert [decision.reason for decision, _ in planned] == ["text-ok"]
    markdown, pages = extract_pdf_text(data)
    assert pages == 1
    assert_quality("synthetic-native-clean", expected, markdown)


def test_garbage_glyph_pdf_routes_to_ocr_and_assembles() -> None:
    data, _native = garbage_glyph_pdf()
    planned = plan_pages(_open_pdf(data))
    assert [decision.reason for decision, _ in planned] == ["garbage-glyphs"]
    markdown = assemble_hybrid_markdown(planned, {0: SCANNED_OCR_MARKDOWN})
    assert_quality("synthetic-scanned-garbage", SCANNED_OCR_MARKDOWN, markdown)


def test_figure_dominant_pdf_routes_to_ocr_and_assembles() -> None:
    data, _native = figure_dominant_pdf()
    planned = plan_pages(_open_pdf(data))
    assert [decision.reason for decision, _ in planned] == ["figure-dominant"]
    markdown = assemble_hybrid_markdown(planned, {0: FIGURE_OCR_MARKDOWN})
    assert_quality("synthetic-figure-dominant", FIGURE_OCR_MARKDOWN, markdown)


def test_dropped_ocr_fallback_fails_the_gate() -> None:
    data, _native = garbage_glyph_pdf()
    planned = plan_pages(_open_pdf(data))
    degraded = assemble_hybrid_markdown(planned, {})
    with pytest.raises(AssertionError):
        assert_quality("synthetic-scanned-garbage", SCANNED_OCR_MARKDOWN, degraded)


def test_numeric_regression_fails_the_gate() -> None:
    expected = SCANNED_OCR_MARKDOWN
    corrupted = expected.replace("15(3x + 1)^4", "5(3x + 1)^4")
    with pytest.raises(AssertionError):
        assert_quality("synthetic-scanned-garbage", expected, corrupted)


def test_manifest_covers_every_synthetic_fixture() -> None:
    manifest = load_manifest()
    names = {fixture["name"] for fixture in manifest["fixtures"]}
    assert names == SYNTHETIC_NAMES
    for fixture in manifest["fixtures"]:
        assert set(fixture["thresholds"]) == {
            "block_structure",
            "math_fence",
            "numeric_fidelity",
        }


def _real_fixtures() -> list[Path]:
    if not GOLDEN.is_dir():
        return []
    return sorted(
        path
        for path in GOLDEN.glob("**/*")
        if path.is_file() and path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}
    )


@pytest.mark.skipif(not _real_fixtures(), reason="owner scans not collected yet")
def test_real_fixture_slots_have_recorded_expectations() -> None:
    for fixture in _real_fixtures():
        expected = GOLDEN / "expected" / f"{fixture.stem}.md"
        assert expected.is_file(), f"missing expected markdown for {fixture.name}"


@pytest.mark.skipif(
    os.environ.get("SA_EVAL_LIVE") != "1",
    reason="live OCR eval is opt-in (SA_EVAL_LIVE=1); the default gate is deterministic",
)
def test_live_ocr_half_is_documented_placeholder() -> None:
    pytest.skip(
        "live OCR quality runs against a configured vision model; wire the owner's "
        "real fixtures here when they land (plan 84 C, ADR-210)"
    )


def _whiteboard(
    *, angle: float = 0.0, ink: int = 190, border: bool = False, width: int = 900, height: int = 600
) -> bytes:
    import cv2
    import numpy as np
    from PIL import ImageDraw

    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    for row in range(8):
        y = 80 + row * 55
        for col in range(5):
            x = 90 + col * 150
            draw.rectangle([x, y, x + 110, y + 18], fill=ink)
    if border:
        draw.rectangle([0, 0, width - 1, height - 1], outline=20, width=8)
    array = np.array(image)
    if angle:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        array = cv2.warpAffine(
            array,
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255,
        )
    return bytes(cv2.imencode(".png", array)[1].tobytes())


def test_preprocess_manifest_records_measured_gains() -> None:
    from app.ocr.preprocess import assess_image, preprocess_ocr_image

    manifest = load_manifest()["preprocess"]
    fixtures = {
        "synthetic-skewed-whiteboard": _whiteboard(angle=7.0, ink=190, border=True),
        "synthetic-low-contrast-whiteboard": _whiteboard(ink=205),
    }
    assert {entry["name"] for entry in manifest["fixtures"]} == set(fixtures)
    for entry in manifest["fixtures"]:
        data = fixtures[entry["name"]]
        before = assess_image(data)
        processed = preprocess_ocr_image(data)
        assert before is not None and processed is not None
        after = assess_image(processed)
        assert after is not None
        assert abs(before.contrast_range - entry["baseline"]["contrast_range"]) <= 2
        assert abs(before.skew_deg - entry["baseline"]["skew_deg"]) <= 0.5
        assert abs(before.score - entry["baseline"]["score"]) <= 0.05
        assert abs(after.contrast_range - entry["after"]["contrast_range"]) <= 2
        assert abs(after.skew_deg - entry["after"]["skew_deg"]) <= 0.5
        assert abs(after.score - entry["after"]["score"]) <= 0.05
        thresholds = entry["thresholds"]
        assert after.contrast_range - before.contrast_range >= thresholds["min_contrast_gain"]
        assert abs(after.skew_deg) <= thresholds["max_residual_skew"]
        assert after.score - before.score >= thresholds["min_score_gain"]
