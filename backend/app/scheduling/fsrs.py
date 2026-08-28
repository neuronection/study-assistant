import math
from dataclasses import dataclass
from datetime import datetime, timedelta

DECAY = -0.5
FACTOR = 19.0 / 81.0
DESIRED_RETENTION = 0.9
MIN_STABILITY = 0.1
MAX_STABILITY = 36500.0

DEFAULT_WEIGHTS: tuple[float, ...] = (
    0.4872,
    1.4003,
    3.7145,
    13.8206,
    5.1618,
    1.2298,
    0.8975,
    0.031,
    1.6474,
    0.1367,
    1.0461,
    2.1072,
    0.0793,
    0.3246,
    1.587,
    0.2272,
    2.8755,
)

RATING_AGAIN = 1
RATING_HARD = 2
RATING_GOOD = 3
RATING_EASY = 4


@dataclass(frozen=True)
class FsrsCard:
    stability: float | None
    difficulty: float | None
    reps: int
    lapses: int
    last_review_at: datetime | None


@dataclass(frozen=True)
class FsrsOutcome:
    stability: float
    difficulty: float
    interval_days: int
    state: str


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _initial_difficulty(rating: int, w: tuple[float, ...]) -> float:
    return _clamp(w[4] - math.exp(w[5] * (rating - 1)) + 1.0, 1.0, 10.0)


def _recall(stability: float, elapsed_days: float) -> float:
    return math.pow(1.0 + FACTOR * elapsed_days / stability, DECAY)


def _next_difficulty(
    difficulty: float, rating: int, w: tuple[float, ...]
) -> float:
    delta = w[6] * (rating - RATING_GOOD)
    reverted = difficulty - delta
    initial = _initial_difficulty(RATING_GOOD, w)
    return _clamp(w[7] * initial + (1.0 - w[7]) * reverted, 1.0, 10.0)


def _stability_after_success(
    difficulty: float, stability: float, recall: float, rating: int, w: tuple[float, ...]
) -> float:
    hard_penalty = w[15] if rating == RATING_HARD else 1.0
    easy_bonus = w[16] if rating == RATING_EASY else 1.0
    growth = (
        1.0
        + math.exp(w[8])
        * (11.0 - difficulty)
        * math.pow(stability, -w[9])
        * (math.exp(w[10] * (1.0 - recall)) - 1.0)
        * hard_penalty
        * easy_bonus
    )
    return _clamp(stability * growth, MIN_STABILITY, MAX_STABILITY)


def _stability_after_failure(
    difficulty: float, stability: float, recall: float, w: tuple[float, ...]
) -> float:
    value = (
        w[11]
        * math.pow(difficulty, -w[12])
        * (math.pow(stability + 1.0, w[13]) - 1.0)
        * math.exp(w[14] * (1.0 - recall))
    )
    return _clamp(value, MIN_STABILITY, MAX_STABILITY)


def _interval(stability: float, retention: float) -> int:
    raw = stability / FACTOR * (math.pow(retention, 1.0 / DECAY) - 1.0)
    return max(1, round(raw))


def review(
    card: FsrsCard,
    rating: int,
    now: datetime,
    weights: tuple[float, ...] = DEFAULT_WEIGHTS,
) -> FsrsOutcome:
    if rating not in (RATING_AGAIN, RATING_HARD, RATING_GOOD, RATING_EASY):
        raise ValueError("rating must be 1-4")
    if card.stability is None or card.difficulty is None or card.last_review_at is None:
        stability = _clamp(weights[rating - 1], MIN_STABILITY, MAX_STABILITY)
        difficulty = _initial_difficulty(rating, weights)
        interval = _interval(stability, DESIRED_RETENTION)
        state = "learning"
        return FsrsOutcome(stability, difficulty, interval, state)

    elapsed_days = max(0.0, (now - card.last_review_at).total_seconds() / 86400.0)
    recall = _recall(card.stability, elapsed_days)
    difficulty = _next_difficulty(card.difficulty, rating, weights)
    if rating == RATING_AGAIN:
        stability = _stability_after_failure(
            card.difficulty, card.stability, recall, weights
        )
        state = "relearning"
        interval = 1
    else:
        stability = _stability_after_success(
            card.difficulty, card.stability, recall, rating, weights
        )
        interval = _interval(stability, DESIRED_RETENTION)
        state = "review"
    return FsrsOutcome(stability, difficulty, interval, state)


def due_date(now: datetime, interval_days: int) -> datetime:
    return now + timedelta(days=interval_days)
