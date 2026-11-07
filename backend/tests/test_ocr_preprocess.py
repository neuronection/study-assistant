import io

import cv2
import numpy as np
from PIL import Image, ImageDraw

from app.ocr.imaging import prepare_ocr_image
from app.ocr.preprocess import assess_image, preprocess_ocr_image


def whiteboard(
    *, angle: float = 0.0, ink: int = 190, border: bool = False, width: int = 900, height: int = 600
) -> bytes:
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


def test_quality_score_flags_skewed_low_contrast_and_border() -> None:
    data = whiteboard(angle=7.0, ink=190, border=True)
    quality = assess_image(data)
    assert quality is not None
    assert quality.reasons == ("low_contrast", "skewed", "border")
    assert quality.score < 0.6


def test_auto_straightens_boosts_contrast_and_crops_the_border() -> None:
    data = whiteboard(angle=7.0, ink=190, border=True)
    before = assess_image(data)
    assert before is not None
    processed = preprocess_ocr_image(data)
    assert processed is not None
    after = assess_image(processed)
    assert after is not None
    assert abs(after.skew_deg) < 1.5
    assert after.contrast_range > before.contrast_range + 100
    assert after.border_ratio == 0.0
    assert after.reasons == ()
    assert after.score > before.score + 0.3


def test_clean_photo_is_left_untouched() -> None:
    data = whiteboard(ink=20)
    quality = assess_image(data)
    assert quality is not None
    assert quality.reasons == ()
    assert preprocess_ocr_image(data) is None


def test_off_path_matches_the_v1_pipeline_byte_for_byte() -> None:
    data = whiteboard(angle=7.0, ink=190)
    auto_payload, auto_mime = prepare_ocr_image(data, "image/png", 1568, preprocess="auto")
    off_payload, off_mime = prepare_ocr_image(data, "image/png", 1568, preprocess="off")
    assert auto_payload != off_payload
    assert auto_mime == "image/webp"
    assert off_mime in ("image/png", "image/webp")

    clean = whiteboard(ink=20)
    assert prepare_ocr_image(clean, "image/png", 1568, preprocess="auto") == (
        prepare_ocr_image(clean, "image/png", 1568, preprocess="off")
    )


def test_undecodable_bytes_pass_through_preprocessing() -> None:
    junk = b"\x89PNG\r\n\x1a\nnot-really-an-image"
    assert assess_image(junk) is None
    assert preprocess_ocr_image(junk) is None
    assert prepare_ocr_image(junk, "image/png", 1568, preprocess="auto") == (junk, "image/png")


def test_output_is_deterministic() -> None:
    data = whiteboard(angle=4.0, ink=200)
    first = preprocess_ocr_image(data)
    second = preprocess_ocr_image(data)
    assert first == second
    assert first is not None
    with Image.open(io.BytesIO(first)) as image:
        assert image.mode == "L"
