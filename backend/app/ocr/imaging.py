import io

import structlog
from PIL import Image
from sqlalchemy.orm import Session

from ..services.profiles import ensure_default_profile

logger = structlog.get_logger(__name__)

DEFAULT_IMAGE_MAX_EDGE = 1568
ALLOWED_IMAGE_MAX_EDGE = frozenset({0, 1024, 1568, 2048})
_WEBP_QUALITY = 85


def ocr_image_max_edge(session: Session | None) -> int:
    if session is None:
        return DEFAULT_IMAGE_MAX_EDGE
    prefs = ensure_default_profile(session).preferences or {}
    value = prefs.get("ocr_image_max_edge", DEFAULT_IMAGE_MAX_EDGE)
    if isinstance(value, int) and value in ALLOWED_IMAGE_MAX_EDGE:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) in ALLOWED_IMAGE_MAX_EDGE:
        return int(value)
    return DEFAULT_IMAGE_MAX_EDGE


def _flatten_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img
    if "A" in img.mode or img.mode == "P" or img.mode == "LA":
        canvas = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        canvas.paste(rgba, mask=rgba.split()[3])
        return canvas
    return img.convert("RGB")


def _encode(img: Image.Image, fmt: str) -> bytes | None:
    buffer = io.BytesIO()
    try:
        img.save(buffer, format=fmt, quality=_WEBP_QUALITY)
    except Exception as error:
        logger.warning("ocr_image_encode_failed", format=fmt, error=str(error))
        return None
    return buffer.getvalue()


def prepare_ocr_image(data: bytes, mime: str, max_edge: int) -> tuple[bytes, str]:
    if max_edge == 0 and mime != "image/png":
        return data, mime
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            width, height = img.size
            longest = max(width, height)
            needs_resize = 0 < max_edge < longest
            if mime != "image/png" and not needs_resize:
                return data, mime
            work: Image.Image = img
            if needs_resize:
                factor = max_edge / longest
                work = img.resize(
                    (max(1, round(width * factor)), max(1, round(height * factor))),
                    Image.Resampling.LANCZOS,
                )
            webp = _encode(_flatten_rgb(work), "WEBP")
            if webp is not None and (needs_resize or len(webp) < len(data)):
                return webp, "image/webp"
            if needs_resize:
                jpeg = _encode(_flatten_rgb(work), "JPEG")
                if jpeg is not None:
                    return jpeg, "image/jpeg"
            return data, mime
    except Exception as error:
        logger.warning("ocr_image_prepare_failed", error=str(error))
        return data, mime
