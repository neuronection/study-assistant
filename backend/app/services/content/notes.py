from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...domain.models import Note, NoteDrawing, NoteVersion, utcnow
from .drawings import md_to_blocks, note_search_text

NOTE_VERSION_CAP = 50
NOTE_VERSION_COALESCE_SECONDS = 600


class NoteBodyError(ValueError):
    pass


def utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def snapshot_note(
    session: Session, note: Note, cause: str, force: bool = False
) -> None:
    latest = (
        session.execute(
            select(NoteVersion)
            .where(NoteVersion.note_id == note.id)
            .order_by(NoteVersion.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if not force and latest is not None:
        latest_at = utc_naive(latest.created_at)
        if (utcnow().replace(tzinfo=None) - latest_at).total_seconds() < (
            NOTE_VERSION_COALESCE_SECONDS
        ):
            return
    session.add(
        NoteVersion(
            note_id=note.id,
            profile_id=note.profile_id,
            title=note.title,
            tags=note.tags,
            body=note.body,
            cause=cause,
        )
    )
    session.flush()
    stale = (
        session.execute(
            select(NoteVersion.id)
            .where(NoteVersion.note_id == note.id)
            .order_by(NoteVersion.id.desc())
            .offset(NOTE_VERSION_CAP)
        )
        .scalars()
        .all()
    )
    if stale:
        session.execute(delete(NoteVersion).where(NoteVersion.id.in_(stale)))


def normalize_tags(tags: list[str] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in tags or []:
        tag = raw.strip().lower()[:60]
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def validate_note_drawing_blocks(session: Session, note: Note) -> None:
    ids = {
        int(block["drawing_id"])
        for block in note.body or []
        if block.get("type") == "drawing"
    }
    if not ids:
        return
    valid = set(
        session.scalars(
            select(NoteDrawing.id).where(
                NoteDrawing.note_id == note.id, NoteDrawing.id.in_(ids)
            )
        )
    )
    unknown = ids - valid
    if unknown:
        raise NoteBodyError(
            f"unknown drawing reference(s): {sorted(unknown)}"
        )


def save_note_body(
    session: Session, note: Note, body_md: str, *, cause: str, force: bool = False
) -> None:
    snapshot_note(session, note, cause, force=force)
    note.body = md_to_blocks(body_md)
    validate_note_drawing_blocks(session, note)
    note.search_text = note_search_text(note)
    session.flush()
