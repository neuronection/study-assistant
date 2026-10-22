import math
from dataclasses import dataclass

import cv2
import numpy as np

BORDER_FRACTION = 0.02
LOW_CONTRAST_RANGE = 72.0
SKEW_THRESHOLD_DEG = 1.5
BORDER_THRESHOLD = 0.03
CLAHE_CLIP = 2.0
CLAHE_TILES = (8, 8)
CROP_MARGIN_PX = 24


@dataclass(frozen=True)
class ImageQuality:
    contrast_range: float
    skew_deg: float
    border_ratio: float
    score: float
    reasons: tuple[str, ...]

    @property
    def needs_preprocessing(self) -> bool:
        return bool(self.reasons)


def _decode(data: bytes) -> np.ndarray | None:
    buffer = np.frombuffer(data, dtype=np.uint8)
    if buffer.size == 0:
        return None
    return cv2.imdecode(buffer, cv2.IMREAD_COLOR)


def _gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _contrast_range(gray: np.ndarray) -> float:
    low, high = np.percentile(gray, (5, 95))
    return float(high - low)


def _skew_deg(gray: np.ndarray) -> float:
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        1,
        math.pi / 180,
        threshold=80,
        minLineLength=max(40, gray.shape[1] // 10),
        maxLineGap=20,
    )
    if lines is None:
        return 0.0
    angles: list[float] = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        if x2 == x1:
            continue
        angle = math.degrees(math.atan2(float(y2 - y1), float(x2 - x1)))
        if abs(angle) <= 20:
            angles.append(angle)
    if not angles:
        return 0.0
    return float(np.median(angles))


def _foreground_ratio(gray: np.ndarray) -> float:
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return float(np.mean(mask > 0))


def _stretch_contrast(gray: np.ndarray) -> np.ndarray:
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    foreground = gray[mask > 0]
    background = gray[mask == 0]
    if foreground.size and background.size:
        low = float(np.median(foreground))
        high = float(np.median(background))
    else:
        low, high = (float(value) for value in np.percentile(gray, (1, 99)))
    if high - low < 10:
        return gray
    stretched = (gray.astype(np.float32) - low) * (255.0 / (high - low))
    result: np.ndarray = np.clip(stretched, 0, 255).astype(np.uint8)
    return result


def _border_ratio(gray: np.ndarray) -> float:
    height, width = gray.shape
    margin_y = max(1, int(height * BORDER_FRACTION))
    margin_x = max(1, int(width * BORDER_FRACTION))
    border = np.concatenate(
        [
            gray[:margin_y, :].reshape(-1),
            gray[-margin_y:, :].reshape(-1),
            gray[:, :margin_x].reshape(-1),
            gray[:, -margin_x:].reshape(-1),
        ]
    )
    if border.size == 0:
        return 0.0
    return float(np.mean(border < 160))


def assess_image(data: bytes) -> ImageQuality | None:
    image = _decode(data)
    if image is None:
        return None
    gray = _gray(image)
    contrast = _contrast_range(gray)
    skew = _skew_deg(gray)
    border = _border_ratio(gray)
    if contrast < 12 or _foreground_ratio(gray) < 0.002:
        return ImageQuality(
            contrast_range=round(contrast, 2),
            skew_deg=round(skew, 3),
            border_ratio=round(border, 4),
            score=1.0,
            reasons=(),
        )
    reasons: list[str] = []
    if contrast < LOW_CONTRAST_RANGE:
        reasons.append("low_contrast")
    if abs(skew) >= SKEW_THRESHOLD_DEG:
        reasons.append("skewed")
    if border > BORDER_THRESHOLD:
        reasons.append("border")
    contrast_score = min(1.0, contrast / 120.0)
    skew_score = max(0.0, 1.0 - abs(skew) / 5.0)
    border_score = max(0.0, 1.0 - border / 0.15)
    score = round(0.5 * contrast_score + 0.3 * skew_score + 0.2 * border_score, 3)
    return ImageQuality(
        contrast_range=round(contrast, 2),
        skew_deg=round(skew, 3),
        border_ratio=round(border, 4),
        score=score,
        reasons=tuple(reasons),
    )


def _deskew(gray: np.ndarray, angle: float) -> np.ndarray:
    height, width = gray.shape
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    bound_w = int(height * sin + width * cos)
    bound_h = int(height * cos + width * sin)
    matrix[0, 2] += bound_w / 2.0 - center[0]
    matrix[1, 2] += bound_h / 2.0 - center[1]
    warped: np.ndarray = cv2.warpAffine(
        gray,
        matrix,
        (bound_w, bound_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )
    return warped


def _crop_border(gray: np.ndarray) -> np.ndarray:
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    image_h, image_w = gray.shape
    row_dark = mask.mean(axis=1) / 255.0
    col_dark = mask.mean(axis=0) / 255.0
    top = 0
    while top < image_h and row_dark[top] > 0.85:
        top += 1
    bottom = image_h
    while bottom > top and row_dark[bottom - 1] > 0.85:
        bottom -= 1
    left = 0
    while left < image_w and col_dark[left] > 0.85:
        left += 1
    right = image_w
    while right > left and col_dark[right - 1] > 0.85:
        right -= 1
    work = gray[top:bottom, left:right]
    if work.size == 0:
        return gray
    points = cv2.findNonZero(mask[top:bottom, left:right])
    if points is None:
        return work
    x, y, width, height = cv2.boundingRect(points)
    work_h, work_w = work.shape
    crop_left = max(0, x - CROP_MARGIN_PX)
    crop_top = max(0, y - CROP_MARGIN_PX)
    crop_right = min(work_w, x + width + CROP_MARGIN_PX)
    crop_bottom = min(work_h, y + height + CROP_MARGIN_PX)
    if crop_right - crop_left < work_w * 0.5 or crop_bottom - crop_top < work_h * 0.5:
        return work
    return work[crop_top:crop_bottom, crop_left:crop_right]


def preprocess_ocr_image(data: bytes) -> bytes | None:
    image = _decode(data)
    if image is None:
        return None
    gray = _gray(image)
    quality = assess_image(data)
    if quality is None or not quality.needs_preprocessing:
        return None
    work = gray
    if "low_contrast" in quality.reasons:
        work = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=CLAHE_TILES).apply(work)
        work = _stretch_contrast(work)
    if "skewed" in quality.reasons:
        work = _deskew(work, quality.skew_deg)
    if "border" in quality.reasons:
        work = _crop_border(work)
    success, encoded = cv2.imencode(".png", work)
    if not success:
        return None
    return bytes(encoded.tobytes())
