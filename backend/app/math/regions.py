from dataclasses import dataclass, field
from typing import Any

MAX_POINTS = 12
MAX_INTERVALS = 6
DEFAULT_TOLERANCE_FRACTION = 0.005

Interval = tuple[float, float, bool, bool]
IntervalSpan = tuple[float, float]


@dataclass(frozen=True)
class RegionGrade:
    correct: bool
    partial_credit: float
    feedback: list[str] = field(default_factory=list)
    error_tags: list[str] = field(default_factory=list)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_float(value: Any) -> float | None:
    return float(value) if _is_number(value) else None


def _clean_number(value: float) -> str:
    return f"{value:.6g}"


def _normalize_interval(raw: Any, index: int, problems: list[str]) -> None:
    if not isinstance(raw, dict):
        problems.append(f"interval {index}: not an object")
        return
    lo = _as_float(raw.get("lo"))
    hi = _as_float(raw.get("hi"))
    if lo is None or hi is None:
        problems.append(f"interval {index}: lo and hi must be numbers")
        return
    if lo >= hi:
        problems.append(f"interval {index}: lo must be less than hi")
    for key in ("lo_closed", "hi_closed"):
        value = raw.get(key, False)
        if not isinstance(value, bool):
            problems.append(f"interval {index}: {key} must be a boolean")


def _payload_problems(payload: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    points = payload.get("points", [])
    intervals = payload.get("intervals", [])
    if not isinstance(points, list):
        problems.append("points must be a list")
        points = []
    if not isinstance(intervals, list):
        problems.append("intervals must be a list")
        intervals = []
    if len(points) > MAX_POINTS:
        problems.append(f"at most {MAX_POINTS} points allowed")
    if len(intervals) > MAX_INTERVALS:
        problems.append(f"at most {MAX_INTERVALS} intervals allowed")
    for index, point in enumerate(points):
        value = point.get("value") if isinstance(point, dict) else point
        if not _is_number(value):
            problems.append(f"point {index}: value must be a number")
    for index, interval in enumerate(intervals):
        _normalize_interval(interval, index, problems)
    return problems


def validate_region_answer(answer: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    domain = answer.get("domain")
    if not isinstance(domain, dict):
        problems.append("domain object required")
        return problems
    dmin = _as_float(domain.get("min"))
    dmax = _as_float(domain.get("max"))
    if dmin is None or dmax is None or dmin >= dmax:
        problems.append("domain needs numeric min < max")
        return problems
    problems.extend(_payload_problems(answer))
    tolerance = answer.get("tolerance")
    if tolerance is not None and (not _is_number(tolerance) or float(tolerance) < 0):
        problems.append("tolerance must be a non-negative number")
    if problems:
        return problems
    for index, point in enumerate(answer.get("points", [])):
        value = _as_float(point.get("value") if isinstance(point, dict) else point)
        if value is not None and not dmin <= value <= dmax:
            problems.append(f"point {index}: value outside the domain")
    for index, interval in enumerate(answer.get("intervals", [])):
        if not isinstance(interval, dict):
            continue
        lo = _as_float(interval.get("lo"))
        hi = _as_float(interval.get("hi"))
        if lo is not None and not dmin <= lo <= dmax:
            problems.append(f"interval {index}: lo outside the domain")
        if hi is not None and not dmin <= hi <= dmax:
            problems.append(f"interval {index}: hi outside the domain")
    if not answer.get("points") and not answer.get("intervals"):
        problems.append("expected answer needs at least one point or interval")
    return problems


def _parse_response(
    response: Any,
) -> tuple[list[float], list[Interval]] | None:
    if not isinstance(response, dict):
        return None
    raw_points = response.get("points", [])
    raw_intervals = response.get("intervals", [])
    if not isinstance(raw_points, list) or not isinstance(raw_intervals, list):
        return None
    points: list[float] = []
    for point in raw_points:
        value = _as_float(point.get("value") if isinstance(point, dict) else point)
        if value is None:
            return None
        points.append(value)
    intervals: list[Interval] = []
    for raw in raw_intervals:
        if not isinstance(raw, dict):
            return None
        lo = _as_float(raw.get("lo"))
        hi = _as_float(raw.get("hi"))
        if lo is None or hi is None or lo >= hi:
            return None
        lo_closed = raw.get("lo_closed", False)
        hi_closed = raw.get("hi_closed", False)
        if not isinstance(lo_closed, bool) or not isinstance(hi_closed, bool):
            return None
        intervals.append((lo, hi, bool(lo_closed), bool(hi_closed)))
    return points, intervals


def _expected_parts(answer: dict[str, Any]) -> tuple[list[float], list[Interval]]:
    points: list[float] = []
    for point in answer.get("points", []):
        value = _as_float(point.get("value") if isinstance(point, dict) else point)
        if value is not None:
            points.append(value)
    intervals: list[Interval] = []
    for raw in answer.get("intervals", []):
        if not isinstance(raw, dict):
            continue
        lo = _as_float(raw.get("lo"))
        hi = _as_float(raw.get("hi"))
        if lo is None or hi is None:
            continue
        intervals.append(
            (lo, hi, bool(raw.get("lo_closed", False)), bool(raw.get("hi_closed", False)))
        )
    return points, intervals


def _merge(intervals: list[IntervalSpan]) -> list[IntervalSpan]:
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for lo, hi in ordered[1:]:
        last_lo, last_hi = merged[-1]
        if lo <= last_hi:
            merged[-1] = (last_lo, max(last_hi, hi))
        else:
            merged.append((lo, hi))
    return merged


def _total_length(intervals: list[IntervalSpan]) -> float:
    return sum(hi - lo for lo, hi in intervals)


def _intersection_length(
    left: list[IntervalSpan], right: list[IntervalSpan]
) -> float:
    total = 0.0
    for lo_l, hi_l in left:
        for lo_r, hi_r in right:
            lo = max(lo_l, lo_r)
            hi = min(hi_l, hi_r)
            if hi > lo:
                total += hi - lo
    return total


def _format_interval(lo: float, hi: float, lo_closed: bool, hi_closed: bool) -> str:
    left = "[" if lo_closed else "("
    right = "]" if hi_closed else ")"
    return f"{left}{_clean_number(lo)}, {_clean_number(hi)}{right}"


def region_tolerance(answer: dict[str, Any]) -> float:
    tolerance = _as_float(answer.get("tolerance"))
    if tolerance is not None and tolerance >= 0:
        return tolerance
    domain = answer.get("domain")
    if isinstance(domain, dict):
        dmin = _as_float(domain.get("min"))
        dmax = _as_float(domain.get("max"))
        if dmin is not None and dmax is not None and dmax > dmin:
            return (dmax - dmin) * DEFAULT_TOLERANCE_FRACTION
    return 1e-6


def grade_regions(expected: dict[str, Any], response: Any) -> RegionGrade:
    tolerance = region_tolerance(expected)
    parsed = _parse_response(response)
    if parsed is None:
        return RegionGrade(
            correct=False,
            partial_credit=0.0,
            feedback=["answer is not a valid numberline payload"],
        )
    actual_points, actual_intervals = parsed
    expected_points, expected_intervals = _expected_parts(expected)
    feedback: list[str] = []
    error_tags: list[str] = []

    used = [False] * len(actual_points)
    matched_points = 0
    for value in expected_points:
        best: int | None = None
        best_distance = tolerance
        for index, actual_value in enumerate(actual_points):
            if used[index]:
                continue
            distance = abs(actual_value - value)
            if distance <= best_distance:
                best = index
                best_distance = distance
        if best is not None:
            used[best] = True
            matched_points += 1
    missed_points = len(expected_points) - matched_points
    extra_points = len(actual_points) - matched_points

    remaining_actual = list(actual_intervals)
    exact_lengths: list[float] = []
    matched_expected_indices: set[int] = set()
    boundary_mismatch = 0
    for index, (lo, hi, lo_closed, hi_closed) in enumerate(expected_intervals):
        match: Interval | None = None
        match_boundaries = False
        for candidate in remaining_actual:
            if abs(candidate[0] - lo) <= tolerance and abs(candidate[1] - hi) <= tolerance:
                match = candidate
                match_boundaries = candidate[2] == lo_closed and candidate[3] == hi_closed
                if match_boundaries:
                    break
        if match is None:
            continue
        remaining_actual.remove(match)
        if match_boundaries:
            matched_expected_indices.add(index)
            exact_lengths.append(hi - lo)
        else:
            boundary_mismatch += 1
            sides: list[str] = []
            if match[2] != lo_closed:
                sides.append(
                    f"{_clean_number(lo)} should be {'closed' if lo_closed else 'open'}"
                )
            if match[3] != hi_closed:
                sides.append(
                    f"{_clean_number(hi)} should be {'closed' if hi_closed else 'open'}"
                )
            feedback.append(
                f"region {_format_interval(lo, hi, lo_closed, hi_closed)}: "
                f"wrong boundary type ({'; '.join(sides)})"
            )
            error_tags.append("boundary_kind")

    leftover_expected = [
        interval
        for index, interval in enumerate(expected_intervals)
        if index not in matched_expected_indices
    ]
    overlap = _intersection_length(
        _merge([(lo, hi) for lo, hi, _, _ in leftover_expected]),
        _merge([(lo, hi) for lo, hi, _, _ in remaining_actual]),
    )
    extra_regions = len(remaining_actual)
    missed_regions = len(leftover_expected)

    expected_mass = (
        _total_length([(lo, hi) for lo, hi, _, _ in expected_intervals])
        + len(expected_points)
    )
    actual_mass = (
        _total_length([(lo, hi) for lo, hi, _, _ in actual_intervals])
        + len(actual_points)
    )
    intersection = overlap + sum(exact_lengths) + matched_points
    denominator = expected_mass + actual_mass
    partial = 2.0 * intersection / denominator if denominator > 0 else 0.0
    partial = round(max(0.0, min(1.0, partial)), 4)

    correct = (
        missed_points == 0
        and extra_points == 0
        and missed_regions == 0
        and extra_regions == 0
        and boundary_mismatch == 0
        and bool(expected_points or expected_intervals)
    )
    if correct:
        return RegionGrade(correct=True, partial_credit=1.0, feedback=["correct"])

    summary_parts = []
    if expected_intervals:
        summary_parts.append(
            f"{len(matched_expected_indices)}/{len(expected_intervals)} regions exact"
        )
    if expected_points:
        summary_parts.append(f"{matched_points}/{len(expected_points)} points correct")
    if summary_parts:
        feedback.insert(0, ", ".join(summary_parts))
    if missed_regions:
        feedback.append(f"{missed_regions} expected region(s) missing or partial")
        error_tags.append("missed_region")
    if extra_regions:
        feedback.append(f"{extra_regions} extra region(s) shaded")
        error_tags.append("extra_region")
    if missed_points:
        feedback.append(f"{missed_points} expected point(s) missing")
        error_tags.append("missed_point")
    if extra_points:
        feedback.append(f"{extra_points} extra point(s) placed")
        error_tags.append("extra_point")
    return RegionGrade(
        correct=False,
        partial_credit=partial,
        feedback=feedback,
        error_tags=error_tags,
    )
