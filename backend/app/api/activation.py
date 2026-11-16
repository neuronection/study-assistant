from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..core.vocab import ActivationEvent, ActivationStep, ActivationSurface
from ..domain.models import ActivationEventRow, utcnow
from ..domain.payloads import ActivationProps
from ..services.platform.profiles import ensure_default_profile
from .deps import get_session

router = APIRouter(prefix="/activation", tags=["activation"])

ActivationValue = Annotated[int | float, Field(ge=0, le=1_000_000)]


class ActivationPropsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    step: ActivationStep | None = None
    surface: ActivationSurface | None = None
    value: ActivationValue | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _numeric_value(cls, value: object) -> object:
        if isinstance(value, (bool, str)):
            raise ValueError("value must be a number")
        return value


class ActivationIn(BaseModel):
    event: str = Field(min_length=1, max_length=40)
    props: ActivationPropsIn | None = None


class ActivationOut(BaseModel):
    id: str
    event: str
    at: datetime
    props: dict[str, Any] | None


class ActivationCountOut(BaseModel):
    event: str
    count: int


class ActivationSummaryOut(BaseModel):
    total: int
    first_at: datetime | None
    last_at: datetime | None
    counts: list[ActivationCountOut]
    recent: list[ActivationOut]


class ActivationExportOut(BaseModel):
    events: list[ActivationOut]
    summary: ActivationSummaryOut


def _out(row: ActivationEventRow) -> ActivationOut:
    return ActivationOut(
        id=row.id,
        event=row.event,
        at=row.at,
        props=dict(row.props or {}) or None,
    )


def _stored_props(body: ActivationPropsIn | None) -> ActivationProps | None:
    if body is None:
        return None
    stored: ActivationProps = {"schema_version": body.schema_version}
    if body.step is not None:
        stored["step"] = body.step
    if body.surface is not None:
        stored["surface"] = body.surface
    if body.value is not None:
        stored["value"] = body.value
    return stored


def _summary(session: Session, profile_id: str) -> ActivationSummaryOut:
    rows = list(
        session.scalars(
            select(ActivationEventRow)
            .where(ActivationEventRow.profile_id == profile_id)
            .order_by(ActivationEventRow.at, ActivationEventRow.id)
        )
    )
    counts = session.execute(
        select(ActivationEventRow.event, func.count())
        .where(ActivationEventRow.profile_id == profile_id)
        .group_by(ActivationEventRow.event)
        .order_by(ActivationEventRow.event)
    ).all()
    return ActivationSummaryOut(
        total=len(rows),
        first_at=rows[0].at if rows else None,
        last_at=rows[-1].at if rows else None,
        counts=[ActivationCountOut(event=str(event), count=int(count)) for event, count in counts],
        recent=[_out(row) for row in rows[-20:]][::-1],
    )


@router.post("/events", response_model=ActivationOut, status_code=201)
def record_activation(body: ActivationIn, session: Session = Depends(get_session)) -> ActivationOut:
    profile = ensure_default_profile(session)
    allowed = {member.value for member in ActivationEvent}
    if body.event not in allowed:
        raise HTTPException(status_code=422, detail="unknown activation event")
    row = ActivationEventRow(
        profile_id=profile.id,
        event=body.event,
        at=utcnow(),
        props=_stored_props(body.props),
    )
    session.add(row)
    session.commit()
    return _out(row)


@router.get("/summary", response_model=ActivationSummaryOut)
def activation_summary(session: Session = Depends(get_session)) -> ActivationSummaryOut:
    profile = ensure_default_profile(session)
    return _summary(session, profile.id)


@router.get("/export", response_model=ActivationExportOut)
def export_activation(session: Session = Depends(get_session)) -> ActivationExportOut:
    profile = ensure_default_profile(session)
    rows = list(
        session.scalars(
            select(ActivationEventRow)
            .where(ActivationEventRow.profile_id == profile.id)
            .order_by(ActivationEventRow.at, ActivationEventRow.id)
        )
    )
    return ActivationExportOut(
        events=[_out(row) for row in rows],
        summary=_summary(session, profile.id),
    )


@router.delete("", status_code=204)
def clear_activation(session: Session = Depends(get_session)) -> None:
    profile = ensure_default_profile(session)
    session.execute(delete(ActivationEventRow).where(ActivationEventRow.profile_id == profile.id))
    session.commit()
