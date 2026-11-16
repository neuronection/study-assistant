from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.gateway import ProviderError, TaskUnassigned
from ..ai.tokenizers import embedding_accounting, token_count
from ..domain.models import AiInteraction, SolveEntry
from ..math.leak_guard import extract_math
from ..ocr.notes_ocr import NotesOcrEngine
from ..services.platform.profiles import ensure_default_profile
from ..services.solve.service import (
    SolveError,
    check_variant,
    save_as_note,
    solve_input,
    variants_for,
)
from .deps import get_session

router = APIRouter(prefix="/solve", tags=["solve"])


class SolveIn(BaseModel):
    input_text: str = Field(min_length=1, max_length=4000)
    input_kind: str = Field(default="typed", max_length=20)


class SolveOut(BaseModel):
    id: str
    input_kind: str
    input_text: str
    intent: str
    verified: bool
    result: dict[str, Any]
    note_id: str | None
    created_at: datetime


class SolveVariantOut(BaseModel):
    index: int
    prompt: str
    kind: str


class SolveCheckIn(BaseModel):
    index: int = Field(ge=0)
    response: str = Field(min_length=1, max_length=4000)


class SolveCheckOut(BaseModel):
    correct: bool
    expected: str | None


class SolveNoteOut(BaseModel):
    note_id: str


class SolveRecognizeOut(BaseModel):
    text: str
    latex_candidates: list[str]


def _out(entry: SolveEntry) -> SolveOut:
    return SolveOut(
        id=entry.id,
        input_kind=entry.input_kind,
        input_text=entry.input_text,
        intent=entry.intent,
        verified=entry.verified,
        result=dict(entry.result or {}),
        note_id=entry.note_id,
        created_at=entry.created_at,
    )


def _entry(session: Session, entry_id: str, profile_id: str) -> SolveEntry:
    entry = session.get(SolveEntry, entry_id)
    if entry is None or entry.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="solve entry not found")
    return entry


@router.post("", response_model=SolveOut, status_code=201)
def create_solve(body: SolveIn, session: Session = Depends(get_session)) -> SolveOut:
    profile = ensure_default_profile(session)
    try:
        entry = solve_input(
            session,
            profile_id=profile.id,
            input_text=body.input_text,
            input_kind=body.input_kind,
        )
    except SolveError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _out(entry)


@router.get("/history", response_model=list[SolveOut])
def solve_history(
    limit: int = 20,
    session: Session = Depends(get_session),
) -> list[SolveOut]:
    profile = ensure_default_profile(session)
    rows = session.scalars(
        select(SolveEntry)
        .where(SolveEntry.profile_id == profile.id)
        .order_by(SolveEntry.created_at.desc(), SolveEntry.id.desc())
        .limit(max(1, min(limit, 100)))
    )
    return [_out(entry) for entry in rows]


@router.get("/{entry_id}", response_model=SolveOut)
def get_solve(entry_id: str, session: Session = Depends(get_session)) -> SolveOut:
    profile = ensure_default_profile(session)
    return _out(_entry(session, entry_id, profile.id))


@router.delete("/{entry_id}", status_code=204)
def delete_solve(entry_id: str, session: Session = Depends(get_session)) -> None:
    profile = ensure_default_profile(session)
    entry = _entry(session, entry_id, profile.id)
    session.delete(entry)
    session.commit()


@router.post("/{entry_id}/note", response_model=SolveNoteOut, status_code=201)
def save_solve_note(entry_id: str, session: Session = Depends(get_session)) -> SolveNoteOut:
    profile = ensure_default_profile(session)
    entry = _entry(session, entry_id, profile.id)
    try:
        note = save_as_note(session, entry, profile_id=profile.id)
    except SolveError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return SolveNoteOut(note_id=note.id)


@router.post("/{entry_id}/variants", response_model=list[SolveVariantOut])
def solve_variants(entry_id: str, session: Session = Depends(get_session)) -> list[SolveVariantOut]:
    profile = ensure_default_profile(session)
    entry = _entry(session, entry_id, profile.id)
    return [
        SolveVariantOut(
            index=cast(int, variant["index"]),
            prompt=cast(str, variant["prompt"]),
            kind=cast(str, variant["kind"]),
        )
        for variant in variants_for(entry)
    ]


@router.post("/{entry_id}/variants/check", response_model=SolveCheckOut)
def check_solve_variant(
    entry_id: str,
    body: SolveCheckIn,
    session: Session = Depends(get_session),
) -> SolveCheckOut:
    profile = ensure_default_profile(session)
    entry = _entry(session, entry_id, profile.id)
    try:
        correct, expected = check_variant(entry, body.index, body.response)
    except SolveError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return SolveCheckOut(correct=correct, expected=expected)


@router.post("/recognize", response_model=SolveRecognizeOut)
async def recognize_solve(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> SolveRecognizeOut:
    ensure_default_profile(session)
    data = await file.read()
    if not data or len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="image must be between 1 byte and 20 MB")
    engine = NotesOcrEngine(request.app.state.gateway)
    try:
        markdown = engine.transcribe(
            data, file.content_type or "image/png", session=session, preprocess="auto"
        )
    except (TaskUnassigned, ProviderError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    candidates = [entry for entry in extract_math(markdown) if entry.strip()]
    accounting = embedding_accounting(session)
    session.add(
        AiInteraction(
            context_type="solve_ocr",
            direction="problem desk photo recognition",
            model=None,
            input_tokens=token_count(markdown, accounting),
            output_tokens=token_count(markdown, accounting),
            latency_ms=None,
            metadata_json=accounting.metadata(),
        )
    )
    session.commit()
    return SolveRecognizeOut(text=markdown, latex_candidates=candidates[-5:])
