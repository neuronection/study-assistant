from typing import Any

from app.math.regions import grade_regions, region_tolerance, validate_region_answer

ANSWER: dict[str, Any] = {
    "domain": {"min": -10, "max": 10},
    "points": [],
    "intervals": [{"lo": 2, "hi": 5, "lo_closed": True, "hi_closed": True}],
}


def interval(
    lo: float, hi: float, lo_closed: bool = False, hi_closed: bool = False
) -> dict[str, Any]:
    return {"lo": lo, "hi": hi, "lo_closed": lo_closed, "hi_closed": hi_closed}


def answer(**overrides: Any) -> dict[str, Any]:
    base = {**ANSWER, **overrides}
    for key, value in list(base.items()):
        if key in ("points", "intervals") and isinstance(value, list):
            base[key] = [
                {"value": entry} if not isinstance(entry, dict) else entry for entry in value
            ]
    return base


class TestValidation:
    def test_valid_answer_passes(self) -> None:
        assert validate_region_answer(answer()) == []

    def test_domain_required(self) -> None:
        problems = validate_region_answer({"points": [], "intervals": []})
        assert any("domain" in problem for problem in problems)

    def test_domain_bounds_enforced(self) -> None:
        problems = validate_region_answer(
            answer(
                points=[{"value": 11}],
                intervals=[{"lo": -12, "hi": -5, "lo_closed": False, "hi_closed": False}],
            )
        )
        assert any("outside the domain" in problem for problem in problems)

    def test_interval_ordering_enforced(self) -> None:
        problems = validate_region_answer(answer(intervals=[interval(5, 2)]))
        assert any("lo must be less than hi" in problem for problem in problems)

    def test_at_least_one_marker_required(self) -> None:
        problems = validate_region_answer(answer(points=[], intervals=[]))
        assert any("at least one" in problem for problem in problems)

    def test_boundary_flags_must_be_boolean(self) -> None:
        problems = validate_region_answer(
            answer(intervals=[{"lo": 2, "hi": 5, "lo_closed": "yes", "hi_closed": True}])
        )
        assert any("lo_closed" in problem for problem in problems)

    def test_tolerance_must_be_non_negative(self) -> None:
        problems = validate_region_answer(answer(tolerance=-1))
        assert any("tolerance" in problem for problem in problems)


class TestTolerance:
    def test_default_is_fraction_of_range(self) -> None:
        assert region_tolerance(answer()) == 0.1

    def test_explicit_tolerance_wins(self) -> None:
        assert region_tolerance(answer(tolerance=0.5)) == 0.5


class TestGrading:
    def test_exact_match_is_correct(self) -> None:
        result = grade_regions(answer(), {"points": [], "intervals": [interval(2, 5, True, True)]})
        assert result.correct
        assert result.partial_credit == 1.0
        assert result.error_tags == []

    def test_boundary_flip_is_not_correct(self) -> None:
        result = grade_regions(answer(), {"points": [], "intervals": [interval(2, 5)]})
        assert not result.correct
        assert result.partial_credit == 0.0
        assert "boundary_kind" in result.error_tags
        assert any("wrong boundary type" in line for line in result.feedback)

    def test_partial_overlap_earns_partial_credit(self) -> None:
        result = grade_regions(
            answer(intervals=[interval(2, 8, True, True)]),
            {"points": [], "intervals": [interval(2, 5, True, True)]},
        )
        assert not result.correct
        assert result.partial_credit == round(2 * 3 / (6 + 3), 4)
        assert "missed_region" in result.error_tags

    def test_extra_region_penalized(self) -> None:
        result = grade_regions(
            answer(), {"points": [], "intervals": [interval(2, 5, True, True), interval(7, 8)]}
        )
        assert not result.correct
        assert result.partial_credit == round(2 * 3 / (3 + 4), 4)
        assert "extra_region" in result.error_tags

    def test_disjoint_is_zero(self) -> None:
        result = grade_regions(answer(), {"points": [], "intervals": [interval(7, 8)]})
        assert not result.correct
        assert result.partial_credit == 0.0

    def test_points_match_within_tolerance(self) -> None:
        graded = grade_regions(
            answer(intervals=[], points=[{"value": 2}]),
            {"points": [{"value": 2.04}], "intervals": []},
        )
        assert graded.correct
        assert graded.partial_credit == 1.0

    def test_points_outside_tolerance_missed(self) -> None:
        graded = grade_regions(
            answer(intervals=[], points=[{"value": 2}]),
            {"points": [{"value": 2.2}], "intervals": []},
        )
        assert not graded.correct
        assert "missed_point" in graded.error_tags
        assert "extra_point" in graded.error_tags
        assert graded.partial_credit == 0.0

    def test_mixed_points_and_intervals(self) -> None:
        expected = answer(intervals=[interval(4, 6)], points=[{"value": 1}])
        result = grade_regions(
            expected, {"points": [{"value": 9}], "intervals": [interval(4, 6)]}
        )
        assert not result.correct
        assert result.partial_credit == round(2 * 2 / (3 + 3), 4)
        assert "missed_point" in result.error_tags
        assert "extra_point" in result.error_tags

    def test_multiple_expected_regions_partial(self) -> None:
        expected = answer(intervals=[interval(2, 5), interval(6, 8)])
        result = grade_regions(expected, {"points": [], "intervals": [interval(2, 5)]})
        assert not result.correct
        assert result.partial_credit == round(2 * 3 / (5 + 3), 4)
        assert "missed_region" in result.error_tags

    def test_overlapping_actual_regions_merge(self) -> None:
        result = grade_regions(
            answer(intervals=[interval(2, 8)]),
            {"points": [], "intervals": [interval(2, 5), interval(4, 8)]},
        )
        assert not result.correct
        assert result.partial_credit == round(2 * 6 / (6 + 7), 4)

    def test_malformed_response_is_zero(self) -> None:
        for response in ("hello", None, {"points": "no"}, {"intervals": [{"lo": 1}]}):
            result = grade_regions(answer(), response)
            assert not result.correct
            assert result.partial_credit == 0.0
            assert any("not a valid numberline payload" in line for line in result.feedback)

    def test_empty_response_is_zero(self) -> None:
        result = grade_regions(answer(), {"points": [], "intervals": []})
        assert not result.correct
        assert result.partial_credit == 0.0
