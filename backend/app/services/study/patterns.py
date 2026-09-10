from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain.models import (
    Activity,
    Course,
    ErrorPattern,
    Exercise,
    ExerciseSession,
    Mistake,
    Question,
    StepAttempt,
    utcnow,
)
from ...math.equivalence import equivalent


class PatternError(ValueError):
    pass


def _detection_matches(
    detection: dict[str, Any] | None, response: str, expected: str
) -> bool:
    if not detection or not response or not expected:
        return False
    kind = detection.get("type")
    if kind == "negated":
        return equivalent(response, f"-({expected})").equivalent
    if kind == "factor":
        for factor in detection.get("factors", []):
            try:
                float(factor)
            except (TypeError, ValueError):
                continue
            if equivalent(response, f"{factor}*({expected})").equivalent:
                return True
    return False


class ErrorPatternService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def course_type_id(self, course_id: int) -> int | None:
        course = self._session.get(Course, course_id)
        return course.course_type_id if course is not None else None

    def resolve(self, course_id: int) -> list[ErrorPattern]:
        course_type_id = self.course_type_id(course_id)
        stmt = select(ErrorPattern).where(ErrorPattern.is_active.is_(True))
        if course_type_id is None:
            stmt = stmt.where(ErrorPattern.course_type_id.is_(None))
        else:
            stmt = stmt.where(
                (ErrorPattern.course_type_id == course_type_id)
                | (ErrorPattern.course_type_id.is_(None))
            )
        return list(
            self._session.scalars(stmt.order_by(ErrorPattern.order_idx, ErrorPattern.id))
        )

    def get(self, key: str) -> ErrorPattern | None:
        return self._session.scalars(
            select(ErrorPattern).where(ErrorPattern.key == key)
        ).first()

    def counts(self, course_id: int) -> dict[str, int]:
        rows = self._session.execute(
            select(Mistake.error_tags)
            .join(Question, Question.id == Mistake.question_id)
            .join(Activity, Activity.id == Question.activity_id)
            .where(Activity.course_id == course_id)
        )
        resolved = {pattern.key for pattern in self.resolve(course_id)}
        counts: dict[str, int] = {}
        for (tags,) in rows:
            for tag in tags or []:
                if tag in resolved:
                    counts[tag] = counts.get(tag, 0) + 1
        return counts

    def detect(self, course_id: int, response: str, expected: str) -> list[str]:
        return [
            pattern.key
            for pattern in self.resolve(course_id)
            if _detection_matches(pattern.detection, response, expected)
        ]

    def spotted_counts(self, course_id: int) -> dict[str, int]:
        rows = self._session.execute(
            select(Exercise.created_from, StepAttempt.correct)
            .join(ExerciseSession, ExerciseSession.exercise_id == Exercise.id)
            .join(StepAttempt, StepAttempt.session_id == ExerciseSession.id)
            .where(Exercise.course_id == course_id, Exercise.kind == "error_spot")
        )
        counts: dict[str, int] = {}
        for created_from, correct in rows:
            if not correct or not isinstance(created_from, dict):
                continue
            key = created_from.get("pattern")
            if isinstance(key, str) and key:
                counts[key] = counts.get(key, 0) + 1
        return counts

    def create_discovered(
        self,
        course_id: int,
        *,
        key: str,
        name: str,
        description: str,
        example: str | None,
    ) -> ErrorPattern:
        if self.get(key) is not None:
            raise PatternError("an error pattern with this key already exists")
        pattern = ErrorPattern(
            key=key,
            course_type_id=self.course_type_id(course_id),
            name=name,
            description=description,
            example=example,
            is_system=False,
            is_active=True,
            created_at=utcnow(),
        )
        self._session.add(pattern)
        self._session.flush()
        return pattern
