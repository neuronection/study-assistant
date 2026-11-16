from typing import Any, cast

from ..core.vocab import AnchorKind
from .payloads import AnchorPayload


class AnchorPayloadError(ValueError):
    pass


ANCHOR_PAYLOAD_KEYS: dict[AnchorKind, frozenset[str]] = {
    AnchorKind.TEXT_RANGE: frozenset({"version_id", "start", "end", "occurrence"}),
    AnchorKind.PDF_QUAD: frozenset({"page", "x", "y", "w", "h"}),
    AnchorKind.IMAGE_REGION: frozenset({"shape", "x", "y", "w", "h", "points"}),
    AnchorKind.TIME_RANGE: frozenset({"start_ms", "end_ms"}),
    AnchorKind.TRANSCRIPT_SPAN: frozenset({"segment_ids"}),
    AnchorKind.CARD_REF: frozenset({"exercise_id"}),
}


def _require(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise AnchorPayloadError(f"anchor payload is missing '{key}'")
    return payload[key]


def _number(payload: dict[str, Any], key: str, *, low: float, high: float | None = None) -> float:
    value = _require(payload, key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnchorPayloadError(f"anchor payload '{key}' must be a number")
    number = float(value)
    if number < low:
        raise AnchorPayloadError(f"anchor payload '{key}' is out of range")
    if high is not None and number > high:
        raise AnchorPayloadError(f"anchor payload '{key}' is out of range")
    return number


def validate_anchor(kind: AnchorKind, payload: dict[str, Any]) -> AnchorPayload:
    allowed = ANCHOR_PAYLOAD_KEYS[kind]
    unknown = set(payload) - allowed
    if unknown:
        raise AnchorPayloadError(
            f"unknown anchor payload keys for {kind.value}: {', '.join(sorted(unknown))}"
        )
    if kind is AnchorKind.TEXT_RANGE:
        version_id = _require(payload, "version_id")
        if not isinstance(version_id, str) or not version_id:
            raise AnchorPayloadError("anchor payload 'version_id' must be a string")
        start = _require(payload, "start")
        end = _require(payload, "end")
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
        ):
            raise AnchorPayloadError("anchor text range is invalid")
        occurrence = payload.get("occurrence", 0)
        if isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence < 0:
            raise AnchorPayloadError("anchor payload 'occurrence' is invalid")
    elif kind is AnchorKind.PDF_QUAD:
        page = _require(payload, "page")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise AnchorPayloadError("anchor payload 'page' is invalid")
        x = _number(payload, "x", low=0, high=1)
        y = _number(payload, "y", low=0, high=1)
        w = _number(payload, "w", low=0)
        h = _number(payload, "h", low=0)
        if w <= 0 or h <= 0 or x + w > 1.0001 or y + h > 1.0001:
            raise AnchorPayloadError("anchor quad is outside the page")
    elif kind is AnchorKind.IMAGE_REGION:
        shape = _require(payload, "shape")
        if shape not in ("rect", "ellipse", "polygon"):
            raise AnchorPayloadError("anchor payload 'shape' is invalid")
        if shape == "polygon":
            points = _require(payload, "points")
            if not isinstance(points, list) or len(points) < 3:
                raise AnchorPayloadError("anchor polygon needs at least three points")
            for point in points:
                if (
                    not isinstance(point, list)
                    or len(point) != 2
                    or any(
                        isinstance(value, bool) or not isinstance(value, (int, float))
                        for value in point
                    )
                ):
                    raise AnchorPayloadError("anchor polygon point is invalid")
                if any(float(value) < 0 or float(value) > 1 for value in point):
                    raise AnchorPayloadError("anchor polygon point is outside the image")
        else:
            x = _number(payload, "x", low=0, high=1)
            y = _number(payload, "y", low=0, high=1)
            w = _number(payload, "w", low=0)
            h = _number(payload, "h", low=0)
            if w <= 0 or h <= 0 or x + w > 1.0001 or y + h > 1.0001:
                raise AnchorPayloadError("anchor region is outside the image")
    elif kind is AnchorKind.TIME_RANGE:
        start_ms = _require(payload, "start_ms")
        end_ms = _require(payload, "end_ms")
        if (
            isinstance(start_ms, bool)
            or isinstance(end_ms, bool)
            or not isinstance(start_ms, int)
            or not isinstance(end_ms, int)
            or start_ms < 0
            or end_ms <= start_ms
        ):
            raise AnchorPayloadError("anchor time range is invalid")
    elif kind is AnchorKind.TRANSCRIPT_SPAN:
        segment_ids = _require(payload, "segment_ids")
        if (
            not isinstance(segment_ids, list)
            or not segment_ids
            or any(not isinstance(entry, str) or not entry for entry in segment_ids)
        ):
            raise AnchorPayloadError("anchor transcript span is invalid")
    elif kind is AnchorKind.CARD_REF:
        exercise_id = _require(payload, "exercise_id")
        if not isinstance(exercise_id, str) or not exercise_id:
            raise AnchorPayloadError("anchor card reference is invalid")
    return cast(AnchorPayload, payload)


def normalize_quote(value: str) -> str:
    return " ".join(value.split())
