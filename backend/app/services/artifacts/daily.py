from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ...core.vocab import ArtifactKind, CourseOrigin
from ...domain.models import Artifact, Course, Profile
from ..knowledge.tree import TreeService
from .narration import create_audio_brief
from .spec import ArtifactError


def _due_time(prefs: Mapping[str, Any]) -> str | None:
    raw = prefs.get("daily_brief")
    if not isinstance(raw, dict) or not raw.get("enabled"):
        return None
    time = str(raw.get("time") or "07:00")
    return time if len(time) == 5 else "07:00"


def _already_today(session: Session, profile_id: str, today: str) -> bool:
    rows = session.scalars(
        select(Artifact).where(
            Artifact.profile_id == profile_id,
            Artifact.kind == ArtifactKind.AUDIO_BRIEF.value,
        )
    )
    for row in rows:
        created = row.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created.astimezone().date().isoformat() == today:
            return True
    return False


def run_daily_briefs(session_factory: sessionmaker[Session]) -> int:
    now = datetime.now()
    today = now.date().isoformat()
    created = 0
    with session_factory() as session:
        profiles = list(session.scalars(select(Profile)))
        for profile in profiles:
            prefs = dict(profile.preferences or {})
            due = _due_time(prefs)
            if due is None or now.strftime("%H:%M") < due:
                continue
            if _already_today(session, profile.id, today):
                continue
            course = session.scalars(
                select(Course)
                .where(
                    Course.profile_id == profile.id,
                    Course.origin != CourseOrigin.SCRATCH.value,
                )
                .order_by(Course.created_at.desc())
                .limit(1)
            ).first()
            if course is None:
                continue
            root = TreeService(session).ensure_root(course.id)
            candidate = prefs.get("daily_brief")
            raw = candidate if isinstance(candidate, dict) else {}
            try:
                create_audio_brief(
                    session,
                    profile_id=profile.id,
                    course_id=course.id,
                    node_id=root.id,
                    title=f"Daily brief — {today}",
                    length_minutes=int(raw.get("length_minutes") or 5),
                    voice=(str(raw["voice"]) if raw.get("voice") else None),
                    regenerate=True,
                )
                session.commit()
                created += 1
            except (ArtifactError, ValueError):
                session.rollback()
                continue
    return created
