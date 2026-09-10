from datetime import UTC, datetime, timedelta

import pytest

from app.scheduling import fsrs


def now() -> datetime:
    return datetime(2026, 8, 19, 12, 0, 0, tzinfo=UTC)


def test_first_review_initializes_stability_by_rating() -> None:
    again = fsrs.review(fsrs.FsrsCard(None, None, 0, 0, None), fsrs.RATING_AGAIN, now())
    good = fsrs.review(fsrs.FsrsCard(None, None, 0, 0, None), fsrs.RATING_GOOD, now())
    easy = fsrs.review(fsrs.FsrsCard(None, None, 0, 0, None), fsrs.RATING_EASY, now())
    assert again.interval_days == 1
    assert good.interval_days > again.interval_days
    assert easy.interval_days > good.interval_days
    assert easy.stability > good.stability > again.stability
    assert all(outcome.state == "learning" for outcome in (again, good, easy))


def test_success_grows_stability_and_interval() -> None:
    first = fsrs.review(fsrs.FsrsCard(None, None, 0, 0, None), fsrs.RATING_GOOD, now())
    later = now() + timedelta(days=first.interval_days)
    second = fsrs.review(
        fsrs.FsrsCard(first.stability, first.difficulty, 1, 0, now()),
        fsrs.RATING_GOOD,
        later,
    )
    assert second.stability > first.stability
    assert second.interval_days > first.interval_days
    assert second.state == "review"


def test_failure_drops_stability_and_lapses_to_short_interval() -> None:
    first = fsrs.review(fsrs.FsrsCard(None, None, 0, 0, None), fsrs.RATING_GOOD, now())
    later = now() + timedelta(days=first.interval_days)
    failed = fsrs.review(
        fsrs.FsrsCard(first.stability, first.difficulty, 1, 0, now()),
        fsrs.RATING_AGAIN,
        later,
    )
    assert failed.stability < first.stability
    assert failed.interval_days == 1
    assert failed.state == "relearning"


def test_difficulty_follows_rating_and_stays_in_range() -> None:
    first = fsrs.review(fsrs.FsrsCard(None, None, 0, 0, None), fsrs.RATING_GOOD, now())
    harder = fsrs.review(
        fsrs.FsrsCard(first.stability, first.difficulty, 1, 0, now()),
        fsrs.RATING_HARD,
        now() + timedelta(days=1),
    )
    assert 1.0 <= harder.difficulty <= 10.0


def test_invalid_rating_rejected() -> None:
    with pytest.raises(ValueError):
        fsrs.review(fsrs.FsrsCard(None, None, 0, 0, None), 5, now())


def test_due_date_matches_interval() -> None:
    moment = now()
    assert fsrs.due_date(moment, 3) == moment + timedelta(days=3)
