"""The versioned envelope for canonical content documents (ADR-200).

Document-shaped JSON (`notes.body`, `chat_messages.blocks`, drawing strokes
and OCR blocks, `extractions.blocks`) keeps its extensible list shape; the
contract lives beside it in a `<column>_schema_version` sibling and every
write is validated here.  These are the *canonical content* formats (core
principle 4) — they are open by design, so the validator checks the shape a
reader relies on, never the full block catalogue.
"""

from typing import Any

DOCUMENT_SCHEMA_VERSION = 1

BLOCK_DOCUMENT = "block"
STROKE_DOCUMENT = "stroke"

DOCUMENT_KINDS: dict[str, str] = {
    "chat_messages.blocks": BLOCK_DOCUMENT,
    "extractions.blocks": BLOCK_DOCUMENT,
    "material_drawings.ocr_blocks": BLOCK_DOCUMENT,
    "material_drawings.strokes": STROKE_DOCUMENT,
    "note_drawings.ocr_blocks": BLOCK_DOCUMENT,
    "note_drawings.strokes": STROKE_DOCUMENT,
    "note_versions.body": BLOCK_DOCUMENT,
    "notes.body": BLOCK_DOCUMENT,
}

VERSION_SIBLINGS: dict[str, str] = {
    "chat_messages.blocks": "blocks_schema_version",
    "extractions.blocks": "blocks_schema_version",
    "material_drawings.ocr_blocks": "ocr_blocks_schema_version",
    "material_drawings.strokes": "strokes_schema_version",
    "note_drawings.ocr_blocks": "ocr_blocks_schema_version",
    "note_drawings.strokes": "strokes_schema_version",
    "note_versions.body": "body_schema_version",
    "notes.body": "body_schema_version",
}

_BLOCK_REQUIRED_FIELD: dict[str, str] = {
    "text": "md",
    "drawing": "drawing_id",
    "image_ref": "image_id",
    "chart": "plotly",
    "widget": "widget",
}


class DocumentShapeError(ValueError):
    """A JSON document does not satisfy its declared content contract."""


def validate_blocks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise DocumentShapeError("blocks must be a list of block objects")
    for index, block in enumerate(value):
        if not isinstance(block, dict):
            raise DocumentShapeError(f"block #{index + 1} is not an object")
        block_type = block.get("type")
        if not isinstance(block_type, str) or block_type not in _BLOCK_REQUIRED_FIELD:
            raise DocumentShapeError(f"block #{index + 1} has no known 'type'")
        if block_type == "widget":
            if not isinstance(block.get("widget"), str) or not block.get("widget"):
                raise DocumentShapeError(f"widget block #{index + 1} has no widget name")
            continue
        required = _BLOCK_REQUIRED_FIELD[block_type]
        if block.get(required) is None:
            raise DocumentShapeError(
                f"block #{index + 1} of type '{block_type}' is missing '{required}'"
            )
    return value


def validate_strokes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise DocumentShapeError("strokes must be a list of stroke objects")
    for index, stroke in enumerate(value):
        if not isinstance(stroke, dict):
            raise DocumentShapeError(f"stroke #{index + 1} is not an object")
        points = stroke.get("points")
        if not isinstance(points, list) or not points:
            raise DocumentShapeError(f"stroke #{index + 1} has no points")
        for point in points:
            if (
                not isinstance(point, list)
                or len(point) != 2
                or not all(isinstance(value, (int, float)) for value in point)
            ):
                raise DocumentShapeError(
                    f"stroke #{index + 1} has a point that is not an [x, y] pair"
                )
        if stroke.get("width") is not None and not isinstance(stroke["width"], (int, float)):
            raise DocumentShapeError(f"stroke #{index + 1} has a non-numeric width")
        if stroke.get("color") is not None and not isinstance(stroke["color"], str):
            raise DocumentShapeError(f"stroke #{index + 1} has a non-string color")
    return value


def validate_document(key: str, value: Any) -> list[dict[str, Any]]:
    kind = DOCUMENT_KINDS.get(key)
    if kind is None:
        raise DocumentShapeError(f"{key} is not a versioned content document")
    if kind == BLOCK_DOCUMENT:
        return validate_blocks(value)
    return validate_strokes(value)
