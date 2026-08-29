import io
from typing import cast

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from app.ocr.imaging import (
    DEFAULT_IMAGE_MAX_EDGE,
    ocr_image_max_edge,
    prepare_ocr_image,
)


def make_png(width: int, height: int, color: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def make_jpeg(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), (40, 50, 60))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


def dimensions(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as img:
        return img.size


def test_large_png_is_downscaled_to_the_cap_and_reencoded() -> None:
    data = make_png(2400, 1200)
    payload, mime = prepare_ocr_image(data, "image/png", 1568)
    assert mime == "image/webp"
    assert max(dimensions(payload)) == 1568
    assert len(payload) < len(data)


def test_small_png_keeps_dimensions_and_stays_lossless_when_webp_is_bigger() -> None:
    data = make_png(64, 48, (255, 0, 0))
    payload, mime = prepare_ocr_image(data, "image/png", 1568)
    if mime == "image/webp":
        assert dimensions(payload) == (64, 48)
    else:
        assert (mime, payload) == ("image/png", data)


def test_small_jpeg_passes_through_unchanged() -> None:
    data = make_jpeg(300, 200)
    assert prepare_ocr_image(data, "image/jpeg", 1568) == (data, "image/jpeg")


def test_large_jpeg_is_downscaled() -> None:
    data = make_jpeg(3200, 800)
    payload, mime = prepare_ocr_image(data, "image/jpeg", 1024)
    assert mime == "image/webp"
    assert dimensions(payload) == (1024, 256)


def test_zero_cap_disables_all_preprocessing_except_png_shrink() -> None:
    data = make_jpeg(3000, 2000)
    assert prepare_ocr_image(data, "image/jpeg", 0) == (data, "image/jpeg")


def test_alpha_channel_is_flattened_onto_white() -> None:
    img = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    data = buffer.getvalue()
    payload, mime = prepare_ocr_image(data, "image/png", 1568)
    if mime == "image/webp":
        with Image.open(io.BytesIO(payload)) as result:
            assert result.mode in ("RGB", "RGBA")
            assert result.size == (200, 100)


def test_undecodable_bytes_pass_through() -> None:
    junk = b"\x89PNG\r\n\x1a\nnot-really-an-image"
    assert prepare_ocr_image(junk, "image/png", 1568) == (junk, "image/png")


def test_max_edge_defaults_and_validates_from_preferences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert ocr_image_max_edge(None) == DEFAULT_IMAGE_MAX_EDGE

    import app.ocr.imaging as imaging

    class FakeProfile:
        def __init__(self, prefs: dict[str, int] | None) -> None:
            self.preferences = prefs

    cases: list[tuple[dict[str, int] | None, int]] = [
        ({"ocr_image_max_edge": 1024}, 1024),
        ({"ocr_image_max_edge": 999}, DEFAULT_IMAGE_MAX_EDGE),
        (None, DEFAULT_IMAGE_MAX_EDGE),
    ]
    for prefs, expected in cases:
        monkeypatch.setattr(
            imaging, "ensure_default_profile", lambda session, p=prefs: FakeProfile(p)
        )
        assert ocr_image_max_edge(cast("Session", object())) == expected
