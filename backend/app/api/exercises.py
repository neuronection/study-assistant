import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..ai.gateway import ProviderError, TaskUnassigned
from ..ai.parsing import blocks_to_md as _blocks_to_md
from ..domain.models import (
    Activity,
    ChatSession,
    Course,
    Exercise,
    ExerciseSession,
    ExerciseStep,
    ReviewLog,
    StepAttempt,
)
from ..math.regions import grade_regions
from ..pipelines.exgen import ExgenError, ExgenService
from ..services.knowledge.context import ContextBundle, ContextError, ContextParams, ContextResolver
from ..services.knowledge.tree import TreeError, TreeService
from ..services.platform.chat import ChatService
from ..services.platform.profiles import ensure_default_profile
from ..services.study.exercise_kinds import GENERATABLE_KINDS
from ..services.study.exercise_rubric import (
    RUBRIC_KINDS,
    RubricError,
    RubricGrader,
    rubric_deterministic_check,
    rubric_public_input,
)
from ..services.study.exercise_structs import STRUCT_KINDS, check_structural, public_input
from ..services.study.patterns import ErrorPatternService, PatternError
from ..services.study.tutor import TutorError, TutorService
from .deps import get_session

router = APIRouter(prefix="/exercises", tags=["exercises"])


class StepIn(BaseModel):
    prompt_md: str = Field(min_length=1)
    expected: dict[str, Any] | None = None


class ExerciseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    course_id: int
    node_id: int | None = None
    context_md: str | None = None
    difficulty: float | None = None
    steps: list[StepIn] = Field(min_length=1, max_length=20)


class ExerciseOut(BaseModel):
    id: int
    title: str
    course_id: int | None
    node_id: int | None
    kind: str = "multi_step"
    deck_ref: str | None = None
    difficulty: float | None
    step_count: int


class StepOut(BaseModel):
    id: int
    order_idx: int
    prompt: list[dict[str, Any]]
    has_expected: bool
    kind: str | None = None
    input: dict[str, Any] | None = None


class SessionOut(BaseModel):
    id: int
    exercise_id: int
    current_step_idx: int
    status: str
    socratic: bool
    independence_score: float | None


class CheckOut(BaseModel):
    correct: bool
    stage: str
    error_class: str | None
    advanced: bool
    session: SessionOut


class HintIn(BaseModel):
    level: int = Field(ge=1, le=5)
    last_response: str | None = None


class HintOut(BaseModel):
    level: int
    markdown: str
    violations: str | None


class AskIn(BaseModel):
    pending_answer: str | None = Field(default=None, max_length=4000)


class AskOut(BaseModel):
    chat_session_id: int
    public_id: str


class GenerateIn(ContextParams):
    course_id: int
    node_id: int | None = None
    topic: str | None = Field(default=None, max_length=500)
    difficulty: float | None = Field(default=None, ge=1, le=5)
    step_count: int = Field(default=4, ge=1, le=8)
    kind: str = "multi_step"


class DrillIn(BaseModel):
    pattern: str = Field(min_length=1, max_length=60)
    course_id: int


class PatternOut(BaseModel):
    pattern: str
    name: str
    description: str
    example: str | None = None
    source: str = "seeded"
    occurrences: int
    spotted: int = 0


class PatternProposalOut(BaseModel):
    key: str
    name: str
    description: str
    example: str | None = None


class PatternProposeIn(BaseModel):
    course_id: int


class PatternCreateIn(BaseModel):
    course_id: int
    key: str = Field(min_length=3, max_length=60, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    example: str | None = Field(default=None, max_length=1000)


class TranscriptEntry(BaseModel):
    step_idx: int
    kind: str
    response: str | None
    correct: bool | None
    hint_level_used: int | None
    error_class: str | None
    markdown: str | None
    created_at: str


def _run_exgen(
    request: Request,
    session: Session,
    profile_id: int,
    *,
    course_id: int | None,
    node_id: int | None,
    topic: str | None,
    difficulty: float | None,
    step_count: int,
    context: ContextBundle | None,
    source: Exercise | None = None,
    pattern: str | None = None,
    pattern_description: str | None = None,
    pattern_example: str | None = None,
    subject: str | None = None,
    kind: str = "multi_step",
) -> Exercise:
    try:
        service = ExgenService(session, request.app.state.gateway)
        exercise, _problems = service.generate(
            profile_id,
            course_id=course_id,
            node_id=node_id,
            topic=topic,
            difficulty=difficulty,
            step_count=step_count,
            kind=kind,
            context=context,
            source=source,
            pattern=pattern,
            pattern_description=pattern_description,
            pattern_example=pattern_example,
            subject=subject,
        )
    except (ExgenError, TaskUnassigned, ProviderError) as error:
        session.rollback()
        raise HTTPException(
            status_code=502 if isinstance(error, (TaskUnassigned, ProviderError)) else 422,
            detail=str(error),
        ) from error
    return exercise


def _recent_wrong_answers(
    session: Session, course_id: int, profile_id: int, limit: int = 30
) -> list[dict[str, Any]]:
    from ..domain.models import Answer
    from ..domain.models import Question as _Question

    rows = session.execute(
        select(Answer, _Question)
        .join(_Question, _Question.id == Answer.question_id)
        .join(Activity, Activity.id == _Question.activity_id)
        .where(
            Activity.course_id == course_id,
            Activity.profile_id == profile_id,
            Answer.correct.is_(False),
        )
        .order_by(Answer.created_at.desc())
        .limit(limit)
    )
    entries: list[dict[str, Any]] = []
    for answer, question in rows:
        expected = ""
        if question.answer:
            value = question.answer.get("value")
            if value is not None:
                expected = str(value)
        response = (
            answer.response.get("value")
            if isinstance(answer.response, dict)
            else None
        )
        entries.append(
            {
                "stem": _blocks_to_md(question.stem or [])[:240],
                "response": str(response) if response is not None else "",
                "expected": expected,
                "tags": answer.error_tags or [],
            }
        )
    return entries


def _run_pattern_discover(
    request: Request,
    session: Session,
    course_id: int,
    entries: list[dict[str, Any]],
    existing: list[Any],
) -> list[PatternProposalOut]:
    from ..ai.runner import AuditRef, TaskRunner
    from ..ai.skills import PATTERN_DISCOVER_SYSTEM
    from ..ai.structured import ItemsOut

    existing_keys = {entry.key for entry in existing}
    digest = "\n".join(
        f"- Q: {entry['stem']}\n  Your answer: {entry['response']}\n  "
        f"Expected: {entry['expected']}\n  Tags: {entry['tags']}"
        for entry in entries
    )
    prompt = (
        "Recent wrong answers from the student's course:\n\n"
        f"{digest}\n\n"
        "Existing error patterns (do not propose these or near-duplicates): "
        + (", ".join(sorted(existing_keys)) if existing_keys else "none")
        + "\n\nPropose new error patterns as JSON."
    )

    def validate(draft: dict[str, Any]) -> list[str]:
        problems: list[str] = []
        proposals = draft.get("proposals")
        if not isinstance(proposals, list) or not proposals:
            return ["proposals list is required"]
        if len(proposals) > 5:
            problems.append("more than 5 proposals")
        seen: set[str] = set()
        for index, item in enumerate(proposals):
            label = f"proposal {index}"
            if not isinstance(item, dict):
                problems.append(f"{label}: not an object")
                continue
            key = str(item.get("key", ""))
            if not re.fullmatch(r"[a-z][a-z0-9_]*", key) or not 3 <= len(key) <= 60:
                problems.append(f"{label}: invalid key {key!r}")
            if key in existing_keys:
                problems.append(f"{label}: key {key} already exists")
            if key in seen:
                problems.append(f"{label}: duplicate key {key}")
            seen.add(key)
            if not str(item.get("name", "")).strip():
                problems.append(f"{label}: empty name")
            if not str(item.get("description", "")).strip():
                problems.append(f"{label}: empty description")
        return problems

    runner = TaskRunner(session, request.app.state.gateway)
    result = runner.run_json(
        task="description",
        prompt=prompt,
        validate=validate,
        fallback_system=PATTERN_DISCOVER_SYSTEM,
        skill_key="pattern.discover",
        course_id=course_id,
        max_rounds=2,
        audit=AuditRef("drills", course_id, "pattern discovery"),
        schema=ItemsOut,
    )
    if result.problems:
        raise ValueError(
            "pattern discovery did not pass validation: "
            + "; ".join(result.problems[:6])
        )
    return [
        PatternProposalOut(
            key=str(item["key"]),
            name=str(item["name"]).strip(),
            description=str(item["description"]).strip(),
            example=str(item.get("example") or "").strip() or None,
        )
        for item in result.draft["proposals"]
    ]


@router.post("/generate", response_model=ExerciseOut, status_code=201)
def generate_exercise(
    body: GenerateIn,
    request: Request,
    session: Session = Depends(get_session),
) -> ExerciseOut:
    profile = ensure_default_profile(session)
    try:
        placement_node_id = TreeService(session).placement_node(
            body.course_id, body.node_id
        )
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        context = ContextResolver(session, request.app.state.embedder.embed).resolve(
            body.to_spec(
                course_id=body.course_id, node_id=placement_node_id, query=body.topic
            )
        )
    except ContextError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if body.kind not in GENERATABLE_KINDS:
        raise HTTPException(
            status_code=422, detail=f"kind must be one of {GENERATABLE_KINDS}"
        )
    exercise = _run_exgen(
        request,
        session,
        profile.id,
        course_id=body.course_id,
        node_id=placement_node_id,
        topic=body.topic,
        difficulty=body.difficulty,
        step_count=body.step_count,
        kind=body.kind,
        context=context,
    )
    session.commit()
    return _exercise_out(exercise, len(exercise.steps))


@router.post("/{exercise_id}/similar", response_model=ExerciseOut, status_code=201)
def similar_exercise(
    exercise_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> ExerciseOut:
    profile = ensure_default_profile(session)
    source = session.get(Exercise, exercise_id)
    if source is None or source.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="exercise not found")
    try:
        service = ExgenService(session, request.app.state.gateway)
        exercise, _problems = service.generate(profile.id, source=source)
    except (ExgenError, TaskUnassigned, ProviderError) as error:
        session.rollback()
        raise HTTPException(
            status_code=502 if isinstance(error, (TaskUnassigned, ProviderError)) else 422,
            detail=str(error),
        ) from error
    session.commit()
    return _exercise_out(exercise, len(exercise.steps))


@router.get("/drills/patterns", response_model=list[PatternOut])
def drill_patterns(
    course_id: int, session: Session = Depends(get_session)
) -> list[PatternOut]:
    ensure_default_profile(session)
    service = ErrorPatternService(session)
    patterns = service.resolve(course_id)
    counts = service.counts(course_id)
    spotted = service.spotted_counts(course_id)
    return [
        PatternOut(
            pattern=pattern.key,
            name=pattern.name,
            description=pattern.description,
            example=pattern.example,
            source="seeded" if pattern.is_system else "discovered",
            occurrences=counts.get(pattern.key, 0),
            spotted=spotted.get(pattern.key, 0),
        )
        for pattern in patterns
    ]


@router.post("/drills/patterns", response_model=PatternOut, status_code=201)
def create_pattern(
    body: PatternCreateIn, session: Session = Depends(get_session)
) -> PatternOut:
    ensure_default_profile(session)
    service = ErrorPatternService(session)
    try:
        pattern = service.create_discovered(
            body.course_id,
            key=body.key,
            name=body.name,
            description=body.description,
            example=body.example,
        )
    except PatternError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    counts = service.counts(body.course_id)
    return PatternOut(
        pattern=pattern.key,
        name=pattern.name,
        description=pattern.description,
        example=pattern.example,
        source="discovered",
        occurrences=counts.get(pattern.key, 0),
    )


@router.post("/drills/propose", response_model=list[PatternProposalOut])
def propose_patterns(
    body: PatternProposeIn,
    request: Request,
    session: Session = Depends(get_session),
) -> list[PatternProposalOut]:
    profile = ensure_default_profile(session)
    service = ErrorPatternService(session)
    mistakes = _recent_wrong_answers(session, body.course_id, profile.id)
    if not mistakes:
        return []
    existing = service.resolve(body.course_id)
    try:
        proposals = _run_pattern_discover(
            request, session, body.course_id, mistakes, existing
        )
    except (TaskUnassigned, ProviderError) as error:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return proposals


@router.post("/drills", response_model=ExerciseOut, status_code=201)
def start_drill(
    body: DrillIn,
    request: Request,
    session: Session = Depends(get_session),
) -> ExerciseOut:
    profile = ensure_default_profile(session)
    service = ErrorPatternService(session)
    pattern = service.get(body.pattern)
    resolved = {entry.key for entry in service.resolve(body.course_id)}
    if pattern is None or not pattern.is_active or pattern.key not in resolved:
        raise HTTPException(status_code=422, detail="unknown error pattern")
    course = session.get(Course, body.course_id)
    try:
        exgen = ExgenService(session, request.app.state.gateway)
        exercise = exgen.generate_error_spot_drill(
            profile.id,
            course_id=body.course_id,
            node_id=None,
            pattern=pattern.key,
            pattern_description=pattern.description,
            pattern_example=pattern.example,
            subject=course.subject if course is not None else None,
            detection=pattern.detection,
        )
    except (ExgenError, TaskUnassigned, ProviderError) as error:
        session.rollback()
        raise HTTPException(
            status_code=502 if isinstance(error, (TaskUnassigned, ProviderError)) else 422,
            detail=str(error),
        ) from error
    session.commit()
    return _exercise_out(exercise, len(exercise.steps))


def _exercise_out(exercise: Exercise, step_count: int) -> ExerciseOut:
    return ExerciseOut(
        id=exercise.id,
        title=exercise.title,
        course_id=exercise.course_id,
        node_id=exercise.node_id,
        kind=exercise.kind,
        deck_ref=exercise.deck_ref,
        difficulty=exercise.difficulty,
        step_count=step_count,
    )


def _session_out(session_row: ExerciseSession) -> SessionOut:
    return SessionOut(
        id=session_row.id,
        exercise_id=session_row.exercise_id,
        current_step_idx=session_row.current_step_idx,
        status=session_row.status,
        socratic=session_row.socratic,
        independence_score=session_row.independence_score,
    )


@router.post("", response_model=ExerciseOut, status_code=201)
def create_exercise(
    body: ExerciseCreate, session: Session = Depends(get_session)
) -> ExerciseOut:
    profile = ensure_default_profile(session)
    try:
        node_id = TreeService(session).placement_node(body.course_id, body.node_id)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    exercise = Exercise(
        profile_id=profile.id,
        course_id=body.course_id,
        node_id=node_id,
        title=body.title.strip(),
        context=[{"type": "text", "md": body.context_md}] if body.context_md else None,
        difficulty=body.difficulty,
        created_from={"source": "manual"},
    )
    session.add(exercise)
    session.flush()
    for index, step in enumerate(body.steps):
        session.add(
            ExerciseStep(
                exercise_id=exercise.id,
                order_idx=index,
                prompt=[{"type": "text", "md": step.prompt_md}],
                expected=step.expected,
            )
        )
    session.commit()
    return _exercise_out(exercise, len(body.steps))


class ExerciseRename(BaseModel):
    title: str = Field(min_length=1, max_length=300)


@router.patch("/{exercise_id}", response_model=ExerciseOut)
def rename_exercise(
    exercise_id: int, body: ExerciseRename, session: Session = Depends(get_session)
) -> ExerciseOut:
    exercise = session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    exercise.title = body.title.strip()[:300] or exercise.title
    session.commit()
    count = len(
        session.scalars(
            select(ExerciseStep.id).where(ExerciseStep.exercise_id == exercise.id)
        ).all()
    )
    return _exercise_out(exercise, count)


class ExerciseMove(BaseModel):
    node_id: int | None = None


@router.patch("/{exercise_id}/move", response_model=ExerciseOut)
def move_exercise(
    exercise_id: int, body: ExerciseMove, session: Session = Depends(get_session)
) -> ExerciseOut:
    exercise = session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    try:
        exercise.node_id = TreeService(session).placement_node(
            exercise.course_id, body.node_id
        )
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    count = len(
        session.scalars(
            select(ExerciseStep.id).where(ExerciseStep.exercise_id == exercise.id)
        ).all()
    )
    return _exercise_out(exercise, count)


class SummaryNoteOut(BaseModel):
    note_id: int
    node_title: str | None


class ExerciseDeletedOut(BaseModel):
    deleted_item_id: int


@router.delete("/{exercise_id}", response_model=ExerciseDeletedOut)
def delete_exercise(
    exercise_id: int, session: Session = Depends(get_session)
) -> dict[str, Any]:
    exercise = session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    from ..services.platform import trash

    deleted_item_id = trash.snapshot(
        session, "exercise", exercise.id, exercise.title, exercise.profile_id
    )
    session.execute(delete(ReviewLog).where(ReviewLog.card_id == exercise.id))
    session.delete(exercise)
    session.commit()
    return {"deleted_item_id": deleted_item_id}


@router.get("", response_model=list[ExerciseOut])
def list_exercises(
    course_id: int | None = None,
    node_id: int | None = None,
    include_children: bool = True,
    session: Session = Depends(get_session),
) -> list[ExerciseOut]:
    profile = ensure_default_profile(session)
    statement = select(Exercise).where(
        Exercise.profile_id == profile.id, Exercise.kind.not_like("card_%")
    )
    if node_id is not None:
        scope_ids = TreeService(session).scoped_node_ids(node_id, include_children)
        statement = statement.where(Exercise.node_id.in_(scope_ids))
    elif course_id is not None:
        statement = statement.where(Exercise.course_id == course_id)
    exercises = session.scalars(statement.order_by(Exercise.id.desc()).limit(50))
    result = []
    for exercise in exercises:
        count = len(
            session.scalars(
                select(ExerciseStep.id).where(ExerciseStep.exercise_id == exercise.id)
            ).all()
        )
        result.append(_exercise_out(exercise, count))
    return result


@router.get("/{exercise_id}", response_model=ExerciseOut)
def get_exercise(exercise_id: int, session: Session = Depends(get_session)) -> ExerciseOut:
    exercise = session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    count = len(
        session.scalars(
            select(ExerciseStep.id).where(ExerciseStep.exercise_id == exercise.id)
        ).all()
    )
    return _exercise_out(exercise, count)


def _numberline_input(spec: dict[str, Any]) -> dict[str, Any] | None:
    value = spec.get("value")
    domain = value.get("domain") if isinstance(value, dict) else None
    if not isinstance(domain, dict):
        return None
    dmin = domain.get("min")
    dmax = domain.get("max")
    if not isinstance(dmin, (int, float)) or not isinstance(dmax, (int, float)):
        return None
    return {"widget": "numberline", "min": dmin, "max": dmax}


@router.get("/{exercise_id}/steps", response_model=list[StepOut])
def exercise_steps(
    exercise_id: int, session: Session = Depends(get_session)
) -> list[StepOut]:
    steps = session.scalars(
        select(ExerciseStep)
        .where(ExerciseStep.exercise_id == exercise_id)
        .order_by(ExerciseStep.order_idx)
    )
    result: list[StepOut] = []
    for step in steps:
        spec = step.expected or {}
        kind = spec.get("kind")
        if isinstance(kind, str) and kind in STRUCT_KINDS:
            widget: dict[str, Any] | None = public_input(kind, spec, step.id)
        elif isinstance(kind, str) and kind in RUBRIC_KINDS:
            widget = rubric_public_input(kind, spec)
        elif isinstance(kind, str) and kind == "numberline":
            widget = _numberline_input(spec)
        else:
            widget = None
        result.append(
            StepOut(
                id=step.id,
                order_idx=step.order_idx,
                prompt=step.prompt,
                has_expected=step.expected is not None,
                kind=kind if isinstance(kind, str) else None,
                input=widget,
            )
        )
    return result


@router.post("/{exercise_id}/sessions", response_model=SessionOut, status_code=201)
def start_session(
    exercise_id: int,
    socratic: bool = False,
    session: Session = Depends(get_session),
) -> SessionOut:
    profile = ensure_default_profile(session)
    exercise = session.get(Exercise, exercise_id)
    if exercise is None or exercise.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="exercise not found")
    exercise_session = ExerciseSession(exercise_id=exercise_id, socratic=socratic)
    session.add(exercise_session)
    session.commit()
    return _session_out(exercise_session)


def _load_session(
    db: Session, session_id: int, profile_id: int
) -> tuple[ExerciseSession, Exercise]:
    exercise_session = db.get(ExerciseSession, session_id)
    if exercise_session is None:
        raise HTTPException(status_code=404, detail="session not found")
    exercise = db.get(Exercise, exercise_session.exercise_id)
    if exercise is None or exercise.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="session not found")
    return exercise_session, exercise


class AnswerIn(BaseModel):
    response: Any
    state: dict[str, Any] | None = None


@router.post("/sessions/{session_id}/answer", response_model=CheckOut)
def submit_step_answer(
    session_id: int,
    body: AnswerIn,
    request: Request,
    session: Session = Depends(get_session),
) -> CheckOut:
    profile = ensure_default_profile(session)
    exercise_session, _exercise = _load_session(session, session_id, profile.id)
    if exercise_session.status != "active":
        raise HTTPException(status_code=422, detail="session is not active")
    step = session.scalars(
        select(ExerciseStep)
        .where(
            ExerciseStep.exercise_id == exercise_session.exercise_id,
            ExerciseStep.order_idx == exercise_session.current_step_idx,
        )
    ).first()
    if step is None:
        raise HTTPException(status_code=422, detail="no step at current index")

    spec = step.expected or {}
    rubric_assessment: dict[str, Any] | None = None
    if isinstance(spec.get("kind"), str) and spec["kind"] in STRUCT_KINDS:
        correct, stage = check_structural(spec["kind"], spec, body.response)
        error_class = None
    elif isinstance(spec.get("kind"), str) and spec["kind"] == "numberline":
        value = spec.get("value")
        if not isinstance(value, dict):
            raise HTTPException(status_code=422, detail="step has no numberline answer")
        expected = dict(value)
        if spec.get("tolerance") is not None:
            expected["tolerance"] = spec["tolerance"]
        result = grade_regions(expected, body.response)
        correct = result.correct
        stage = (
            "numberline: correct"
            if correct
            else "numberline: " + "; ".join(result.feedback)
        )
        error_class = None
    elif isinstance(spec.get("kind"), str) and spec["kind"] in RUBRIC_KINDS:
        if not isinstance(body.response, str) or not body.response.strip():
            raise HTTPException(status_code=422, detail="string response required")
        response = body.response.strip()
        deterministic = rubric_deterministic_check(spec["kind"], spec, response)
        if deterministic is not None:
            correct, stage = deterministic
        else:
            grader = RubricGrader(session, request.app.state.gateway)
            try:
                rubric_assessment = grader.grade(
                    step, spec, response, course_id=_exercise.course_id
                )
            except (RubricError, TaskUnassigned, ProviderError) as error:
                session.rollback()
                raise HTTPException(
                    status_code=502
                    if isinstance(error, (TaskUnassigned, ProviderError))
                    else 422,
                    detail=str(error),
                ) from error
            correct = rubric_assessment["verdict"] == "correct"
            stage = f"{spec['kind']}: {rubric_assessment['verdict']} (AI-graded)"
        error_class = None
    else:
        if not isinstance(body.response, str) or not body.response.strip():
            raise HTTPException(status_code=422, detail="string response required")
        tutor = TutorService(session, request.app.state.gateway)
        try:
            correct, stage, error_class = tutor.check_step(step, body.response.strip())
        except TutorError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    previous_hints = list(
        session.scalars(
            select(StepAttempt.hint_level_used).where(
                StepAttempt.session_id == session_id,
                StepAttempt.step_idx == exercise_session.current_step_idx,
            )
        )
    )
    hint_level = max((level or 0 for level in previous_hints), default=0) or None
    feedback_blocks: list[dict[str, Any]] = [{"type": "text", "md": stage}]
    if rubric_assessment is not None:
        for row in rubric_assessment.get("rationale", []):
            feedback_blocks.append(
                {
                    "type": "text",
                    "md": f"- **{row.get('rubric_id', '')}**: {row.get('reason', '')}",
                }
            )
    attempt = StepAttempt(
        session_id=session_id,
        step_idx=exercise_session.current_step_idx,
        response=(
            {"value": body.response.strip()}
            if isinstance(body.response, str)
            else {"structured": body.response}
        ),
        correct=correct,
        hint_level_used=hint_level,
        error_class=error_class or None,
        feedback=feedback_blocks,
        state=body.state,
    )
    session.add(attempt)
    if correct:
        step_count = len(
            session.scalars(
                select(ExerciseStep.id).where(
                    ExerciseStep.exercise_id == exercise_session.exercise_id
                )
            ).all()
        )
        if exercise_session.current_step_idx + 1 >= step_count:
            exercise_session.status = "completed"
            from ..domain.models import utcnow

            exercise_session.finished_at = utcnow()
            attempts = list(
                session.scalars(
                    select(StepAttempt).where(StepAttempt.session_id == session_id)
                )
            )
            exercise_session.independence_score = TutorService.independence_score(attempts)
        else:
            exercise_session.current_step_idx += 1
    session.commit()
    return CheckOut(
        correct=correct,
        stage=stage,
        error_class=error_class,
        advanced=correct and exercise_session.status != "completed",
        session=_session_out(exercise_session),
    )


@router.post("/sessions/{session_id}/hint", response_model=HintOut)
def request_hint(
    session_id: int,
    body: HintIn,
    request: Request,
    session: Session = Depends(get_session),
) -> HintOut:
    profile = ensure_default_profile(session)
    exercise_session, _exercise = _load_session(session, session_id, profile.id)
    if exercise_session.status != "active":
        raise HTTPException(status_code=422, detail="session is not active")
    step = session.scalars(
        select(ExerciseStep)
        .where(
            ExerciseStep.exercise_id == exercise_session.exercise_id,
            ExerciseStep.order_idx == exercise_session.current_step_idx,
        )
    ).first()
    if step is None:
        raise HTTPException(status_code=422, detail="no step at current index")
    tutor = TutorService(session, request.app.state.gateway)
    try:
        hint = tutor.hint(exercise_session, step, body.level, body.last_response)
    except TutorError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.add(
        StepAttempt(
            session_id=session_id,
            step_idx=exercise_session.current_step_idx,
            response=None,
            correct=None,
            hint_level_used=body.level,
            feedback=[{"type": "text", "md": hint["markdown"]}],
        )
    )
    session.commit()
    return HintOut(level=hint["level"], markdown=hint["markdown"], violations=hint["violations"])


@router.post("/sessions/{session_id}/ask", response_model=AskOut, status_code=201)
def ask_about_session(
    session_id: int,
    body: AskIn,
    request: Request,
    session: Session = Depends(get_session),
) -> AskOut:
    profile = ensure_default_profile(session)
    exercise_session, exercise = _load_session(session, session_id, profile.id)
    if exercise_session.status != "active":
        raise HTTPException(status_code=422, detail="session is not active")
    step = session.scalars(
        select(ExerciseStep)
        .where(
            ExerciseStep.exercise_id == exercise_session.exercise_id,
            ExerciseStep.order_idx == exercise_session.current_step_idx,
        )
    ).first()
    if step is None:
        raise HTTPException(status_code=422, detail="no step at current index")
    service = ChatService(session, request.app.state.gateway, request.app.state.embedder)
    pending = (body.pending_answer or "").strip() or None
    existing = next(
        (
            candidate
            for candidate in session.scalars(
                select(ChatSession).where(ChatSession.profile_id == profile.id)
            )
            if (candidate.context or {}).get("exercise_session_id") == session_id
        ),
        None,
    )
    if existing is not None:
        context = dict(existing.context or {})
        context["pending_answer"] = pending
        existing.context = context
        session.commit()
        return AskOut(chat_session_id=existing.id, public_id=existing.public_id)
    try:
        node_id = TreeService(session).placement_node(exercise.course_id, exercise.node_id)
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    chat_session = service.create_session(
        profile.id,
        course_id=exercise.course_id,
        node_id=node_id,
        title=f"Exercise: {exercise.title}"[:300],
        context={"exercise_session_id": session_id, "pending_answer": pending},
    )
    seed_lines = [
        "I am working on this exercise step:",
        "",
        _blocks_to_md(step.prompt),
    ]
    if pending:
        shown = f"$${pending}$$" if not pending.startswith(("{", "[")) else pending
        seed_lines += ["", f"My current answer (not submitted yet):\n{shown}"]
    service.add_message(chat_session.id, "user", "\n".join(seed_lines))
    session.commit()
    return AskOut(chat_session_id=chat_session.id, public_id=chat_session.public_id)


@router.get("/sessions/{session_id}/transcript", response_model=list[TranscriptEntry])
def session_transcript(
    session_id: int, session: Session = Depends(get_session)
) -> list[TranscriptEntry]:
    profile = ensure_default_profile(session)
    exercise_session, _exercise = _load_session(session, session_id, profile.id)
    return _transcript_entries(session, exercise_session)


@router.post("/sessions/{session_id}/summary-note", response_model=SummaryNoteOut)
def session_summary_note(
    session_id: int, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    exercise_session, exercise = _load_session(session, session_id, profile.id)
    if exercise_session.status != "completed":
        raise HTTPException(status_code=422, detail="session is not completed yet")
    entries = _transcript_entries(session, exercise_session)
    from ..domain.models import Note, TreeNode

    mistakes: list[str] = []
    hints_used = 0
    for entry in entries:
        if entry.kind == "hint":
            hints_used += 1
        elif entry.correct is False:
            detail = entry.error_class or "wrong answer"
            mistakes.append(
                f"- Step {entry.step_idx + 1}: {detail}"
                + (f" — you answered `{entry.response}`" if entry.response else "")
            )
    lines = [f"# {exercise.title} — session summary", ""]
    lines.append(
        f"Steps: {len({entry.step_idx for entry in entries})} · "
        f"Hints used: {hints_used} · "
        f"Incorrect attempts: {len(mistakes)}"
    )
    if mistakes:
        lines += ["", "## What went wrong", *mistakes]
    correct_steps = sorted(
        {entry.step_idx + 1 for entry in entries if entry.correct is True}
    )
    if correct_steps:
        lines += ["", "## Completed correctly", f"Steps {correct_steps}"]
    node = session.get(TreeNode, exercise.node_id) if exercise.node_id else None
    note = Note(
        profile_id=profile.id,
        course_id=exercise.course_id,
        node_id=exercise.node_id,
        title=f"{exercise.title} — session summary",
        body=[{"type": "text", "md": "\n".join(lines)}],
        tags=["session-summary"],
    )
    note.search_text = f"{note.title}\n{chr(10).join(lines)}"
    session.add(note)
    session.commit()
    return {"note_id": note.id, "node_title": node.title if node else None}


def _transcript_entries(session: Session, exercise_session: Any) -> list[TranscriptEntry]:
    attempts = list(
        session.scalars(
            select(StepAttempt)
            .where(StepAttempt.session_id == exercise_session.id)
            .order_by(StepAttempt.id)
        )
    )
    entries = []
    for attempt in attempts:
        markdown = None
        if attempt.feedback:
            markdown = str(attempt.feedback[0].get("md", "")) or None
        entries.append(
            TranscriptEntry(
                step_idx=attempt.step_idx,
                kind="hint" if attempt.response is None else "answer",
                response=(
                    str(attempt.response.get("value")) if attempt.response else None
                ),
                correct=attempt.correct,
                hint_level_used=attempt.hint_level_used,
                error_class=attempt.error_class,
                markdown=markdown,
                created_at=attempt.created_at.isoformat(),
            )
        )
    return entries
