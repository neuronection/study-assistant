from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from ..ai.gateway import ProviderError, TaskUnassigned
from ..domain.models import (
    Exercise,
    Extraction,
    FsrsState,
    Mistake,
    Note,
    Question,
    ReviewLog,
    utcnow,
)
from ..pipelines.anki import export_apkg, import_apkg
from ..pipelines.flashcards import FlashcardsError, FlashcardsService, validate_card
from ..scheduling import fsrs
from ..services.knowledge.context import ContextError, ContextParams, ContextResolver
from ..services.knowledge.tree import TreeError, TreeService
from ..services.platform.profiles import ensure_default_profile
from ..services.study.cards import (
    card_parts,
    card_source,
    create_card_exercise,
)
from ..services.study.exercise_kinds import CARD_KINDS
from .deps import get_session

router = APIRouter(prefix="/flashcards", tags=["flashcards"])

SOURCES = ("note", "material", "mistakes")


class GenerateIn(ContextParams):
    source: str = "note"
    note_id: int | None = None
    material_id: int | None = None
    course_id: int
    node_id: int | None = None
    count: int = Field(default=8, ge=1, le=30)


class CardIn(BaseModel):
    kind: str = "basic"
    front_md: str = Field(min_length=1, max_length=2000)
    back_md: str = Field(min_length=1, max_length=2000)
    course_id: int
    node_id: int | None = None


class CardOut(BaseModel):
    id: int
    kind: str
    front: list[dict[str, Any]]
    back: list[dict[str, Any]]
    source: str
    source_ref: str | None
    node_id: int | None
    due_at: str | None
    state: str | None


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=4)


class ReviewOut(BaseModel):
    interval_days: int
    due_at: str
    state: str


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _card_out(card: Exercise, state: FsrsState | None) -> CardOut:
    parts = card_parts(card)
    source, source_ref = card_source(card)
    return CardOut(
        id=card.id,
        kind=parts["kind"] if parts else "basic",
        front=parts["front"] if parts else [],
        back=parts["back"] if parts else [],
        source=source,
        source_ref=source_ref,
        node_id=card.node_id,
        due_at=state.due_at.isoformat() if state else None,
        state=state.state if state else None,
    )


def _load_card(db: Session, card_id: int, profile_id: int) -> Exercise:
    card = db.scalar(
        select(Exercise)
        .options(selectinload(Exercise.steps), selectinload(Exercise.fsrs_state))
        .where(
            Exercise.id == card_id,
            Exercise.profile_id == profile_id,
            Exercise.kind.in_(CARD_KINDS),
        )
    )
    if card is None:
        raise HTTPException(status_code=404, detail="card not found")
    return card


def _source_content(session: Session, profile_id: int, body: GenerateIn) -> str:
    if body.source == "note":
        if body.note_id is None:
            raise HTTPException(status_code=422, detail="note_id required for source=note")
        note = session.get(Note, body.note_id)
        if note is None or note.profile_id != profile_id:
            raise HTTPException(status_code=404, detail="note not found")
        parts: list[str] = []
        for block in note.body:
            if block.get("md"):
                parts.append(str(block["md"]))
        for drawing in note.drawings:
            if drawing.ocr_markdown:
                parts.append(drawing.ocr_markdown)
        return "\n\n".join(parts)
    if body.source == "material":
        if body.material_id is None:
            raise HTTPException(
                status_code=422, detail="material_id required for source=material"
            )
        extraction = session.scalars(
            select(Extraction)
            .where(Extraction.material_id == body.material_id)
            .order_by(Extraction.version.desc())
            .limit(1)
        ).first()
        if extraction is None:
            raise HTTPException(status_code=404, detail="material has no extraction")
        return extraction.markdown
    rows = session.execute(
        select(Question.stem, Question.explanation, Mistake.error_tags)
        .join(Question, Mistake.question_id == Question.id)
        .where(Mistake.profile_id == profile_id)
        .order_by(Mistake.id.desc())
        .limit(20)
    ).all()
    lines = []
    for stem, explanation, tags in rows:
        stem_text = stem[0].get("md", "") if stem else ""
        explanation_text = (
            explanation[0].get("md", "") if explanation else ""
        )
        lines.append(
            f"Question: {stem_text}\nCorrect: {explanation_text}\nErrors: "
            f"{', '.join(tags or [])}"
        )
    if not lines:
        raise HTTPException(status_code=422, detail="no mistakes to build cards from")
    return "\n\n".join(lines)


@router.post("/generate", response_model=list[CardOut], status_code=201)
def generate_cards(
    body: GenerateIn,
    request: Request,
    session: Session = Depends(get_session),
) -> list[CardOut]:
    if body.source not in SOURCES:
        raise HTTPException(status_code=422, detail="source must be one of {SOURCES}")
    profile = ensure_default_profile(session)
    try:
        node_id = TreeService(session).placement_node(body.course_id, body.node_id)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    content = _source_content(session, profile.id, body)
    try:
        context = ContextResolver(session, request.app.state.embedder.embed).resolve(
            body.to_spec(course_id=body.course_id, node_id=node_id, max_chunks=0)
        )
    except ContextError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        service = FlashcardsService(session, request.app.state.gateway)
        cards, _problems = service.generate(
            profile.id,
            course_id=body.course_id,
            node_id=node_id,
            count=body.count,
            source=body.source,
            source_ref=(
                f"note:{body.note_id}"
                if body.source == "note"
                else f"material:{body.material_id}"
                if body.source == "material"
                else None
            ),
            content=content,
            context=context,
        )
    except (FlashcardsError, TaskUnassigned, ProviderError) as error:
        session.rollback()
        raise HTTPException(
            status_code=502 if isinstance(error, (TaskUnassigned, ProviderError)) else 422,
            detail=str(error),
        ) from error
    session.commit()
    return [
        _card_out(
            card,
            session.scalar(select(FsrsState).where(FsrsState.card_id == card.id)),
        )
        for card in cards
    ]


@router.post("", response_model=CardOut, status_code=201)
def create_card(
    body: CardIn, session: Session = Depends(get_session)
) -> CardOut:
    profile = ensure_default_profile(session)
    draft = {"kind": body.kind, "front_md": body.front_md, "back_md": body.back_md}
    problems = validate_card(draft, 0)
    if problems:
        raise HTTPException(status_code=422, detail="; ".join(problems))
    try:
        node_id = TreeService(session).placement_node(body.course_id, body.node_id)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    card = create_card_exercise(
        session,
        profile_id=profile.id,
        course_id=body.course_id,
        node_id=node_id,
        kind=body.kind,
        front=[{"type": "text", "md": body.front_md}],
        back=[{"type": "text", "md": body.back_md}],
        source="manual",
    )
    session.commit()
    return _card_out(card, None)


@router.get("", response_model=list[CardOut])
def list_cards(
    course_id: int | None = None,
    node_id: int | None = None,
    include_children: bool = True,
    session: Session = Depends(get_session),
) -> list[CardOut]:
    profile = ensure_default_profile(session)
    statement = select(Exercise, FsrsState)
    statement = statement.outerjoin(FsrsState, FsrsState.card_id == Exercise.id)
    statement = statement.where(
        Exercise.profile_id == profile.id, Exercise.kind.in_(CARD_KINDS)
    )
    if node_id is not None:
        scope_ids = TreeService(session).scoped_node_ids(node_id, include_children)
        statement = statement.where(Exercise.node_id.in_(scope_ids))
    elif course_id is not None:
        statement = statement.where(Exercise.course_id == course_id)
    statement = (
        statement.options(selectinload(Exercise.steps))
        .order_by(Exercise.id.desc())
        .limit(200)
    )
    return [
        _card_out(card, state) for card, state in session.execute(statement).all()
    ]


@router.get("/due", response_model=list[CardOut])
def due_cards(
    limit: int = 20,
    course_id: int | None = None,
    node_id: int | None = None,
    include_children: bool = True,
    session: Session = Depends(get_session),
) -> list[CardOut]:
    profile = ensure_default_profile(session)
    now = utcnow()
    statement = (
        select(Exercise, FsrsState)
        .outerjoin(FsrsState, FsrsState.card_id == Exercise.id)
        .where(Exercise.profile_id == profile.id, Exercise.kind.in_(CARD_KINDS))
    )
    if node_id is not None:
        scope_ids = TreeService(session).scoped_node_ids(node_id, include_children)
        statement = statement.where(Exercise.node_id.in_(scope_ids))
    elif course_id is not None:
        statement = statement.where(Exercise.course_id == course_id)
    statement = statement.where((FsrsState.id.is_(None)) | (FsrsState.due_at <= now))
    statement = statement.options(selectinload(Exercise.steps))
    statement = statement.order_by(FsrsState.due_at.nulls_first(), Exercise.id).limit(
        max(1, min(limit, 100))
    )
    return [
        _card_out(card, state) for card, state in session.execute(statement).all()
    ]


@router.post("/{card_id}/review", response_model=ReviewOut)
def review_card(
    card_id: int,
    body: ReviewIn,
    session: Session = Depends(get_session),
) -> ReviewOut:
    profile = ensure_default_profile(session)
    card = _load_card(session, card_id, profile.id)
    now = utcnow()
    state = (
        session.scalars(
            select(FsrsState).where(FsrsState.card_id == card.id)
        ).first()
    )
    fsrs_card = fsrs.FsrsCard(
        stability=state.stability if state else None,
        difficulty=state.difficulty if state else None,
        reps=state.reps if state else 0,
        lapses=state.lapses if state else 0,
        last_review_at=_aware(state.last_review_at) if state else None,
    )
    outcome = fsrs.review(fsrs_card, body.rating, now)
    if state is None:
        state = FsrsState(card_id=card.id, due_at=now)
        session.add(state)
    state.stability = outcome.stability
    state.difficulty = outcome.difficulty
    state.state = outcome.state
    state.reps = (state.reps or 0) + 1
    if body.rating == fsrs.RATING_AGAIN:
        state.lapses = (state.lapses or 0) + 1
    state.due_at = fsrs.due_date(now, outcome.interval_days)
    state.last_review_at = now
    elapsed = (
        0.0
        if fsrs_card.last_review_at is None
        else (now - fsrs_card.last_review_at).total_seconds() / 86400.0
    )
    session.add(
        ReviewLog(
            card_id=card.id,
            rating=body.rating,
            interval_days=float(outcome.interval_days),
            elapsed_days=elapsed,
        )
    )
    session.commit()
    return ReviewOut(
        interval_days=outcome.interval_days,
        due_at=state.due_at.isoformat(),
        state=outcome.state,
    )


@router.delete("/{card_id}", status_code=204)
def delete_card(card_id: int, session: Session = Depends(get_session)) -> None:
    profile = ensure_default_profile(session)
    card = _load_card(session, card_id, profile.id)
    session.execute(delete(ReviewLog).where(ReviewLog.card_id == card.id))
    session.delete(card)
    session.commit()


class AnkiImportOut(BaseModel):
    imported: int
    skipped: int
    deck_name: str


@router.post("/import-anki", response_model=AnkiImportOut, status_code=201)
async def import_anki(
    file: UploadFile,
    course_id: int,
    session: Session = Depends(get_session),
) -> AnkiImportOut:
    profile = ensure_default_profile(session)
    data = await file.read()
    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="file too large")
    try:
        result = import_apkg(data, session, profile.id, course_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return AnkiImportOut(
        imported=result.imported, skipped=result.skipped, deck_name=result.deck_name
    )


@router.get("/export-anki")
def export_anki(
    course_id: int | None = None,
    session: Session = Depends(get_session),
) -> Response:
    profile = ensure_default_profile(session)
    statement = (
        select(Exercise, FsrsState)
        .outerjoin(FsrsState, FsrsState.card_id == Exercise.id)
        .where(Exercise.profile_id == profile.id, Exercise.kind.in_(CARD_KINDS))
    )
    if course_id is not None:
        statement = statement.where(Exercise.course_id == course_id)
    statement = statement.options(selectinload(Exercise.steps))
    rows = session.execute(statement.order_by(Exercise.id)).all()
    package = export_apkg(
        [(card, state) for card, state in rows], "Study Assistant"
    )
    return Response(
        content=package,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="flashcards.apkg"'},
    )
