from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import StudyLeechAction
from ...domain.models import Course, CourseFsrsOverride, FsrsSettings, utcnow
from ...scheduling.fsrs import FsrsParams


@dataclass(frozen=True)
class FsrsValues:
    desired_retention: float = 0.90
    maximum_interval_days: int = 365
    new_per_day: int = 20
    reviews_per_day: int = 200
    leech_threshold: int = 8
    leech_action: str = StudyLeechAction.TAG.value
    bury_siblings: bool = False
    load_balance: bool = True

    def params(self) -> FsrsParams:
        return FsrsParams(
            desired_retention=self.desired_retention,
            maximum_interval_days=self.maximum_interval_days,
        )


DEFAULTS = FsrsValues()
_FIELDS = (
    "desired_retention",
    "maximum_interval_days",
    "new_per_day",
    "reviews_per_day",
    "leech_threshold",
    "leech_action",
    "bury_siblings",
    "load_balance",
)


def _profile_row(session: Session, profile_id: str) -> FsrsSettings | None:
    return session.scalar(select(FsrsSettings).where(FsrsSettings.profile_id == profile_id))


def _course_row(session: Session, course_id: str) -> CourseFsrsOverride | None:
    return session.scalar(
        select(CourseFsrsOverride).where(CourseFsrsOverride.course_id == course_id)
    )


def _values_from(row: FsrsSettings | CourseFsrsOverride | None) -> FsrsValues:
    if row is None:
        return DEFAULTS
    values = DEFAULTS
    for field in _FIELDS:
        value = getattr(row, field)
        if value is not None:
            values = replace(values, **{field: value})
    return values


def get_profile(session: Session, profile_id: str) -> FsrsValues:
    return _values_from(_profile_row(session, profile_id))


def update_profile(
    session: Session,
    profile_id: str,
    *,
    values: dict[str, object],
) -> FsrsValues:
    row = _profile_row(session, profile_id)
    if row is None:
        row = FsrsSettings(profile_id=profile_id)
        session.add(row)
    for field, value in values.items():
        if field in _FIELDS and value is not None:
            setattr(row, field, value)
    row.updated_at = utcnow()
    session.flush()
    return _values_from(row)


def get_course(session: Session, course_id: str) -> FsrsValues:
    return _values_from(_course_row(session, course_id))


def resolve(session: Session, profile_id: str, course_id: str | None = None) -> FsrsValues:
    profile = get_profile(session, profile_id)
    if course_id is None:
        return profile
    row = _course_row(session, course_id)
    return _values_from(row) if row is not None else profile


def set_course(
    session: Session,
    course_id: str,
    *,
    values: dict[str, object],
) -> FsrsValues:
    course = session.get(Course, course_id)
    if course is None:
        raise ValueError("course not found")
    row = _course_row(session, course_id)
    if row is None:
        row = CourseFsrsOverride(course_id=course_id)
        session.add(row)
    for field, value in values.items():
        if field in _FIELDS:
            setattr(row, field, value)
    row.updated_at = utcnow()
    session.flush()
    return _values_from(row)


def clear_course(session: Session, course_id: str) -> None:
    row = _course_row(session, course_id)
    if row is not None:
        session.delete(row)
        session.flush()
