import base64
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import __version__
from ..ai.gateway import ProviderError, TaskUnassigned
from ..core.vocab import AttemptMode
from ..domain.models import (
    Activity,
    AiInteraction,
    Answer,
    Attempt,
    Concept,
    ItemStat,
    Mistake,
    Question,
    QuizHelpEvent,
)
from ..ocr.notes_ocr import NotesOcrEngine
from ..pipelines.qpkg import build_qpkg, read_qpkg
from ..pipelines.quizgen import (
    QUESTION_TYPES,
    QuizgenError,
    QuizgenService,
    validate_question,
)
from ..services.knowledge.context import (
    ContextBundle,
    ContextError,
    ContextParams,
    ContextResolver,
)
from ..services.knowledge.tree import TreeError, TreeService
from ..services.platform.chat import ChatService
from ..services.platform.profiles import ensure_default_profile
from ..services.study.grading import grade
from ..services.study.inbox import InboxService
from ..services.study.patterns import ErrorPatternService
from ..services.study.tutor import TutorError, TutorService
from .deps import get_session

router = APIRouter(prefix="/quiz", tags=["quiz"])


class GenerateIn(ContextParams):
    course_id: int
    node_id: int | None = None
    concept_id: int | None = None
    count: int = Field(default=8, ge=1, le=30)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    topic: str | None = Field(default=None, max_length=300)
    skill: str | None = Field(default=None, max_length=20)
    question_types: list[str] | None = None
    shuffle: bool = False


class QuestionOut(BaseModel):
    id: int
    type: str
    stem: list[dict[str, Any]]
    options: list[dict[str, Any]] | None
    difficulty: float | None
    bloom: str | None
    skill: str | None
    expected_time_sec: int | None
    flag: str


class ActivityOut(BaseModel):
    id: int
    title: str
    type: str
    course_id: int | None
    node_id: int | None
    question_count: int


class AnswerIn(BaseModel):
    question_id: int
    response: Any
    time_ms: int | None = None
    input_mode: str | None = None
    strokes: list[dict[str, Any]] | None = None


class FeedbackOut(BaseModel):
    correct: bool
    partial_credit: float
    graded_by: str | None
    feedback: list[dict[str, Any]]
    error_tags: list[str]
    explanation: list[dict[str, Any]]


class AttemptOut(BaseModel):
    id: int
    activity_id: int
    mode: str
    started_at: str
    finished_at: str | None
    score: float | None


def _activity_out(activity: Activity, question_count: int) -> ActivityOut:
    return ActivityOut(
        id=activity.id,
        title=activity.title,
        type=activity.type,
        course_id=activity.course_id,
        node_id=activity.node_id,
        question_count=question_count,
    )


def _question_out(question: Question) -> QuestionOut:
    return QuestionOut(
        id=question.id,
        type=question.type,
        stem=question.stem,
        options=question.options,
        difficulty=question.difficulty,
        bloom=question.bloom,
        skill=question.skill,
        expected_time_sec=question.expected_time_sec,
        flag=question.flag,
    )


@router.post("/generate", response_model=ActivityOut, status_code=201)
def generate_quiz(
    body: GenerateIn,
    request: Request,
    session: Session = Depends(get_session),
) -> ActivityOut:
    profile = ensure_default_profile(session)
    if body.question_types:
        unknown = [t for t in body.question_types if t not in QUESTION_TYPES]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"unknown question type(s): {', '.join(unknown)}",
            )
    node = None
    try:
        placement_node_id = TreeService(session).placement_node(
            body.course_id, body.node_id
        )
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if placement_node_id is not None:
        body.node_id = placement_node_id
        node = TreeService(session).get(placement_node_id)
        body.course_id = node.course_id
    if body.concept_id is not None:
        concept = session.get(Concept, body.concept_id)
        if concept is None:
            raise HTTPException(status_code=404, detail="concept not found")
        if concept.course_id != body.course_id:
            raise HTTPException(
                status_code=422, detail="concept belongs to a different course"
            )
        body.topic = concept.name
    scope_context: ContextBundle | None = None
    try:
        scope_context = ContextResolver(
            session, request.app.state.embedder.embed
        ).resolve(body.to_spec(course_id=body.course_id, node_id=body.node_id, query=body.topic))
    except ContextError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    title_topic = body.topic
    if title_topic is None and node is not None and not node.is_root:
        title_topic = node.title
    activity = Activity(
        profile_id=profile.id,
        course_id=body.course_id,
        node_id=body.node_id,
        type="quiz",
        title=(
            f"{title_topic} · {time.strftime('%Y-%m-%d %H:%M')}"
            if title_topic
            else f"Quiz · {time.strftime('%Y-%m-%d %H:%M')}"
        ),
        config={
            "count": body.count,
            "difficulty": body.difficulty,
            **({"topic": body.topic} if body.topic else {}),
            **({"skill": body.skill} if body.skill else {}),
            **({"question_types": body.question_types} if body.question_types else {}),
            **({"shuffle": True} if body.shuffle else {}),
        },
    )
    session.add(activity)
    session.commit()
    try:
        service = QuizgenService(session, request.app.state.gateway)
        questions, _problems = service.generate(
            activity,
            count=body.count,
            difficulty=body.difficulty,
            context=scope_context,
            topic=body.topic,
            skill=body.skill,
            question_types=body.question_types,
            shuffle=body.shuffle,
        )
    except QuizgenError as error:
        session.delete(activity)
        session.commit()
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (TaskUnassigned, ProviderError) as error:
        session.delete(activity)
        session.commit()
        raise HTTPException(status_code=502, detail=str(error)) from error
    session.commit()
    return _activity_out(activity, len(questions))


@router.get("/attempts")
def list_attempts(
    course_id: int | None = None, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    statement = (
        select(Attempt, Activity)
        .join(Activity, Attempt.activity_id == Activity.id)
        .where(Activity.profile_id == profile.id)
    )
    if course_id is not None:
        statement = statement.where(Activity.course_id == course_id)
    rows = session.execute(statement.order_by(Attempt.id.desc()).limit(50)).all()
    return [
        {
            "id": attempt.id,
            "activity_id": attempt.activity_id,
            "title": activity.title,
            "mode": attempt.mode,
            "started_at": attempt.started_at.isoformat(),
            "finished_at": (
                attempt.finished_at.isoformat() if attempt.finished_at else None
            ),
            "score": attempt.score,
        }
        for attempt, activity in rows
    ]


@router.get("/mistakes")
def list_mistakes(
    course_id: int | None = None, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    statement = (
        select(Mistake, Question, Activity)
        .join(Question, Mistake.question_id == Question.id)
        .join(Activity, Question.activity_id == Activity.id)
        .where(Mistake.profile_id == profile.id)
    )
    if course_id is not None:
        statement = statement.where(Activity.course_id == course_id)
    rows = session.execute(statement.order_by(Mistake.id.desc()).limit(100)).all()
    return [
        {
            "id": mistake.id,
            "question_id": mistake.question_id,
            "activity_id": activity.id,
            "activity_title": activity.title,
            "stem_excerpt": (
                question.stem[0].get("md", "")[:100] if question.stem else ""
            ),
            "error_tags": mistake.error_tags or [],
            "created_at": mistake.created_at.isoformat(),
        }
        for mistake, question, activity in rows
    ]


def _blocks_to_md(blocks: list[dict[str, Any]] | None) -> str:
    if not blocks:
        return ""
    parts: list[str] = []
    for block in blocks:
        if block.get("type") == "text" and block.get("md"):
            parts.append(str(block["md"]))
        elif block.get("latex"):
            parts.append(f"$${block['latex']}$$")
    return "\n\n".join(parts)


def _answer_to_caq(qtype: str, answer: dict[str, Any]) -> Any:
    if qtype == "single":
        return answer.get("index")
    if qtype == "multi":
        return answer.get("indices")
    return answer.get("value")


def _caq_document(activity: Activity, questions: list[Question]) -> dict[str, Any]:
    return {
        "$schema": "caq/v1",
        "title": activity.title,
        "questions": [
            {
                "id": f"q{index}",
                "type": question.type,
                "stem_md": _blocks_to_md(question.stem),
                **(
                    {"options_md": [_blocks_to_md([option]) for option in question.options]}
                    if question.options
                    else {}
                ),
                "answer": _answer_to_caq(question.type, question.answer or {}),
                "explanation_md": _blocks_to_md(question.explanation),
                "concepts": question.tags or [],
                **({"skill": question.skill} if question.skill else {}),
                **({"bloom": question.bloom} if question.bloom else {}),
                **({"difficulty": question.difficulty} if question.difficulty else {}),
                **(
                    {"expected_time_sec": question.expected_time_sec}
                    if question.expected_time_sec
                    else {}
                ),
                **(
                    {"misconceptions": question.distractor_misconceptions}
                    if question.distractor_misconceptions
                    else {}
                ),
                **({"sympy_check": question.sympy_check} if question.sympy_check else {}),
            }
            for index, question in enumerate(questions, start=1)
        ],
    }


@router.get("/activities/{activity_id}/export")
def export_caq(activity_id: int, session: Session = Depends(get_session)) -> Response:
    profile = ensure_default_profile(session)
    activity = session.get(Activity, activity_id)
    if activity is None or activity.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="quiz not found")
    questions = list(
        session.scalars(
            select(Question).where(Question.activity_id == activity_id).order_by(Question.id)
        )
    )
    document = _caq_document(activity, questions)
    return Response(
        content=json.dumps(document, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="quiz-{activity_id}.caq.json"'},
    )


@router.get("/activities/{activity_id}/export-qpkg")
def export_qpkg(activity_id: int, session: Session = Depends(get_session)) -> Response:
    profile = ensure_default_profile(session)
    activity = session.get(Activity, activity_id)
    if activity is None or activity.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="quiz not found")
    questions = list(
        session.scalars(
            select(Question).where(Question.activity_id == activity_id).order_by(Question.id)
        )
    )
    package = build_qpkg(_caq_document(activity, questions), f"Study Assistant {__version__}")
    return Response(
        content=package,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="quiz-{activity_id}.qpkg"'
        },
    )


@router.post("/import-qpkg", status_code=200)
async def import_qpkg(
    file: UploadFile,
    course_id: int,
    dry_run: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    data = await file.read()
    content = read_qpkg(data)
    document = content.document
    if not isinstance(document.get("questions"), list):
        raise HTTPException(status_code=422, detail="quiz.json has no questions list")
    body = CaqDocument(
        title=str(document.get("title", "Imported package")),
        questions=document["questions"],
    )
    return import_caq(body, dry_run=dry_run, course_id=course_id, session=session)


class CaqDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = "Imported quiz"
    questions: list[dict[str, Any]] = Field(min_length=1, max_length=50)


def _normalize_caq_question(raw: dict[str, Any]) -> dict[str, Any]:
    qtype = raw.get("type")
    answer = raw.get("answer")
    if not isinstance(answer, dict):
        if qtype == "single" and isinstance(answer, int) and not isinstance(answer, bool):
            answer = {"index": answer}
        elif qtype == "multi" and isinstance(answer, list):
            answer = {"indices": answer}
        elif (qtype == "truefalse" and isinstance(answer, bool)) or (
            qtype in ("text", "equation") and isinstance(answer, str)
        ):
            answer = {"value": answer}
        elif qtype == "numeric" and isinstance(answer, (int, float)):
            answer = {"value": answer, "tolerance": 1e-6}
        else:
            answer = {}
    draft = dict(raw)
    draft["answer"] = answer
    if "stem_md" not in draft and isinstance(raw.get("stem"), list):
        draft["stem_md"] = _blocks_to_md(raw["stem"])
    if "explanation_md" not in draft and isinstance(raw.get("explanation"), list):
        draft["explanation_md"] = _blocks_to_md(raw["explanation"])
    return draft


def _question_from_draft(
    activity_id: int, draft: dict[str, Any], provenance: dict[str, Any], ok: bool
) -> Question:
    return Question(
        activity_id=activity_id,
        type=draft["type"],
        stem=[{"type": "text", "md": draft.get("stem_md", "")}],
        options=(
            [{"type": "text", "md": option} for option in draft["options_md"]]
            if draft.get("options_md")
            else None
        ),
        answer=draft.get("answer", {}),
        explanation=[{"type": "text", "md": draft.get("explanation_md", "")}],
        difficulty=float(draft.get("difficulty", 3) or 3),
        bloom=draft.get("bloom"),
        skill=draft.get("skill"),
        concept_ids=[],
        expected_time_sec=int(draft.get("expected_time_sec", 60) or 60),
        source_refs=None,
        distractor_misconceptions=draft.get("misconceptions"),
        sympy_check=draft.get("sympy_check"),
        tags=draft.get("concepts"),
        provenance=provenance,
        flag="ok" if ok else "review",
    )


@router.post("/import")
def import_caq(
    body: CaqDocument,
    course_id: int,
    dry_run: bool = True,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    node_id = TreeService(session).ensure_root(course_id).id
    drafts: list[tuple[dict[str, Any], list[str]]] = []
    results: list[dict[str, Any]] = []
    for index, raw in enumerate(body.questions):
        draft = _normalize_caq_question(raw)
        problems = validate_question(draft, index)
        drafts.append((draft, problems))
        results.append({"index": index, "ok": not problems, "problems": problems})
    valid = sum(1 for result in results if result["ok"])
    if dry_run:
        return {"dry_run": True, "results": results, "valid": valid, "total": len(results)}
    activity = Activity(
        profile_id=profile.id,
        course_id=course_id,
        node_id=node_id,
        type="quiz",
        title=body.title.strip() or "Imported quiz",
        config={"imported": True},
        generated_from={"format": "caq/v1"},
    )
    session.add(activity)
    session.flush()
    for draft, problems in drafts:
        session.add(
            _question_from_draft(
                activity.id, draft, {"imported_from": "caq/v1"}, not problems
            )
        )
    session.commit()
    return {
        "dry_run": False,
        "results": results,
        "valid": valid,
        "total": len(results),
        "activity": _activity_out(activity, len(drafts)),
    }


@router.get("/activities", response_model=list[ActivityOut])
def list_quizzes(
    course_id: int | None = None,
    node_id: int | None = None,
    include_children: bool = True,
    session: Session = Depends(get_session),
) -> list[ActivityOut]:
    profile = ensure_default_profile(session)
    statement = select(Activity).where(
        Activity.profile_id == profile.id, Activity.type == "quiz"
    )
    if node_id is not None:
        scope_ids = TreeService(session).scoped_node_ids(node_id, include_children)
        statement = statement.where(Activity.node_id.in_(scope_ids))
    elif course_id is not None:
        statement = statement.where(Activity.course_id == course_id)
    activities = session.scalars(statement.order_by(Activity.id.desc()).limit(50))
    result = []
    for activity in activities:
        count = len(
            session.scalars(
                select(Question.id).where(Question.activity_id == activity.id)
            ).all()
        )
        result.append(_activity_out(activity, count))
    return result


@router.get("/activities/{activity_id}", response_model=ActivityOut)
def get_quiz(activity_id: int, session: Session = Depends(get_session)) -> ActivityOut:
    profile = ensure_default_profile(session)
    activity = session.scalar(
        select(Activity).where(
            Activity.id == activity_id, Activity.profile_id == profile.id
        )
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="quiz not found")
    count = len(
        session.scalars(
            select(Question.id).where(Question.activity_id == activity.id)
        ).all()
    )
    return _activity_out(activity, count)


class QuizRename(BaseModel):
    title: str = Field(min_length=1, max_length=300)


@router.patch("/activities/{activity_id}", response_model=ActivityOut)
def rename_quiz(
    activity_id: int, body: QuizRename, session: Session = Depends(get_session)
) -> ActivityOut:
    profile = ensure_default_profile(session)
    activity = session.scalar(
        select(Activity).where(
            Activity.id == activity_id, Activity.profile_id == profile.id
        )
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="quiz not found")
    activity.title = body.title.strip()[:300] or activity.title
    session.commit()
    count = len(
        session.scalars(
            select(Question.id).where(Question.activity_id == activity.id)
        ).all()
    )
    return _activity_out(activity, count)


class QuizMove(BaseModel):
    node_id: int | None = None


@router.patch("/activities/{activity_id}/move", response_model=ActivityOut)
def move_quiz(
    activity_id: int, body: QuizMove, session: Session = Depends(get_session)
) -> ActivityOut:
    profile = ensure_default_profile(session)
    activity = session.scalar(
        select(Activity).where(
            Activity.id == activity_id, Activity.profile_id == profile.id
        )
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="quiz not found")
    try:
        activity.node_id = TreeService(session).placement_node(
            activity.course_id, body.node_id
        )
    except TreeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    count = len(
        session.scalars(
            select(Question.id).where(Question.activity_id == activity.id)
        ).all()
    )
    return _activity_out(activity, count)


@router.delete("/activities/{activity_id}")
def delete_quiz(activity_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    activity = session.scalar(
        select(Activity).where(
            Activity.id == activity_id, Activity.profile_id == profile.id
        )
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="quiz not found")
    from ..services.platform import trash

    deleted_item_id = trash.snapshot(
        session, "quiz", activity.id, activity.title, profile.id
    )
    attempt_ids = list(
        session.scalars(
            select(Attempt.id).where(Attempt.activity_id == activity.id)
        )
    )
    question_ids = list(
        session.scalars(
            select(Question.id).where(Question.activity_id == activity.id)
        )
    )
    if attempt_ids:
        session.execute(
            delete(QuizHelpEvent).where(QuizHelpEvent.attempt_id.in_(attempt_ids))
        )
        session.execute(delete(Answer).where(Answer.attempt_id.in_(attempt_ids)))
        session.execute(delete(Attempt).where(Attempt.id.in_(attempt_ids)))
    if question_ids:
        session.execute(delete(Mistake).where(Mistake.question_id.in_(question_ids)))
        session.execute(delete(ItemStat).where(ItemStat.question_id.in_(question_ids)))
        session.execute(delete(Question).where(Question.id.in_(question_ids)))
    session.delete(activity)
    session.commit()
    return {"deleted_item_id": deleted_item_id}


@router.get("/activities/{activity_id}/questions", response_model=list[QuestionOut])
def quiz_questions(
    activity_id: int, session: Session = Depends(get_session)
) -> list[QuestionOut]:
    questions = session.scalars(
        select(Question).where(Question.activity_id == activity_id).order_by(Question.id)
    )
    return [_question_out(question) for question in questions]


@router.post("/activities/{activity_id}/attempts", response_model=AttemptOut, status_code=201)
def start_attempt(
    activity_id: int,
    mode: str = AttemptMode.PRACTICE,
    session: Session = Depends(get_session),
) -> AttemptOut:
    profile = ensure_default_profile(session)
    activity = session.get(Activity, activity_id)
    if activity is None or activity.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="quiz not found")
    if mode not in (AttemptMode.PRACTICE, AttemptMode.EXAM):
        raise HTTPException(status_code=422, detail="mode must be practice or exam")
    attempt = Attempt(activity_id=activity_id, mode=mode)
    session.add(attempt)
    session.commit()
    return _attempt_out(attempt)


def _attempt_out(attempt: Attempt) -> AttemptOut:
    return AttemptOut(
        id=attempt.id,
        activity_id=attempt.activity_id,
        mode=attempt.mode,
        started_at=attempt.started_at.isoformat(),
        finished_at=attempt.finished_at.isoformat() if attempt.finished_at else None,
        score=attempt.score,
    )


@router.post("/attempts/{attempt_id}/answers", response_model=FeedbackOut)
def submit_answer(
    attempt_id: int,
    body: AnswerIn,
    request: Request,
    session: Session = Depends(get_session),
) -> FeedbackOut:
    profile = ensure_default_profile(session)
    attempt = session.get(Attempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="attempt not found")
    activity = session.get(Activity, attempt.activity_id)
    if activity is None or activity.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="attempt not found")
    if attempt.finished_at is not None:
        raise HTTPException(status_code=422, detail="attempt already finished")
    question = session.get(Question, body.question_id)
    if question is None or question.activity_id != activity.id:
        raise HTTPException(status_code=404, detail="question not in this quiz")

    result = grade(question, body.response)
    error_tags = list(result.error_tags)
    if not result.correct and question.distractor_misconceptions:
        misconceptions = {
            str(key): value for key, value in question.distractor_misconceptions.items()
        }
        selected: list[Any] = []
        if question.type == "single" and isinstance(body.response, int):
            selected = [body.response]
        elif question.type == "multi" and isinstance(body.response, list):
            selected = body.response
        for choice in selected:
            tag = misconceptions.get(str(choice))
            if tag and tag not in error_tags:
                error_tags.append(tag)
    if not result.correct and question.type in ("equation", "numeric"):
        expected = (question.answer or {}).get("value")
        if expected is not None and isinstance(body.response, str) and body.response.strip():
            for tag in ErrorPatternService(session).detect(
                activity.course_id, body.response, str(expected)
            ):
                if tag not in error_tags:
                    error_tags.append(tag)
    answer = Answer(
        attempt_id=attempt.id,
        question_id=question.id,
        response={
            "value": body.response,
            **({"input_mode": body.input_mode} if body.input_mode else {}),
            **({"strokes": body.strokes} if body.strokes else {}),
        },
        input_mode=body.input_mode,
        correct=result.correct,
        partial_credit=result.partial_credit,
        feedback=result.feedback,
        graded_by=result.graded_by,
        time_ms=body.time_ms,
        error_tags=error_tags or None,
    )
    help_rows = list(
        session.scalars(
            select(QuizHelpEvent)
            .where(
                QuizHelpEvent.attempt_id == attempt.id,
                QuizHelpEvent.question_id == question.id,
            )
            .order_by(QuizHelpEvent.id)
        )
    )
    if help_rows:
        answer.help_events = [
            {
                "type": "hint",
                "level": event.level,
                "at": event.created_at.isoformat(),
            }
            for event in help_rows
        ]
    session.add(answer)
    if not result.correct:
        session.add(
            Mistake(
                profile_id=profile.id,
                question_id=question.id,
                error_tags=error_tags or None,
            )
        )
    session.commit()
    return FeedbackOut(
        correct=result.correct,
        partial_credit=result.partial_credit,
        graded_by=result.graded_by,
        feedback=result.feedback,
        error_tags=error_tags,
        explanation=question.explanation or [],
    )


def _load_attempt_question(
    db: Session, attempt_id: int, profile_id: int, question_id: int
) -> tuple[Attempt, Activity, Question]:
    attempt = db.get(Attempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="attempt not found")
    activity = db.get(Activity, attempt.activity_id)
    if activity is None or activity.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="attempt not found")
    question = db.get(Question, question_id)
    if question is None or question.activity_id != activity.id:
        raise HTTPException(status_code=404, detail="question not in this quiz")
    return attempt, activity, question


class QuizHintIn(BaseModel):
    level: int = Field(ge=1, le=5)
    last_response: Any = None


class QuizHintOut(BaseModel):
    level: int
    markdown: str
    violations: str | None


@router.post(
    "/attempts/{attempt_id}/questions/{question_id}/hint", response_model=QuizHintOut
)
def request_quiz_hint(
    attempt_id: int,
    question_id: int,
    body: QuizHintIn,
    request: Request,
    session: Session = Depends(get_session),
) -> QuizHintOut:
    profile = ensure_default_profile(session)
    attempt, _activity, question = _load_attempt_question(
        session, attempt_id, profile.id, question_id
    )
    if attempt.mode == AttemptMode.EXAM:
        raise HTTPException(status_code=422, detail="help is disabled in exam mode")
    if attempt.finished_at is not None:
        raise HTTPException(status_code=422, detail="attempt already finished")
    prior_levels = list(
        session.scalars(
            select(QuizHelpEvent.level).where(
                QuizHelpEvent.attempt_id == attempt.id,
                QuizHelpEvent.question_id == question.id,
            )
        )
    )
    highest = max(prior_levels, default=0)
    answered = (
        session.scalars(
            select(Answer.id).where(
                Answer.attempt_id == attempt.id, Answer.question_id == question.id
            )
        ).first()
        is not None
    )
    gated = not answered and attempt.finished_at is None
    if gated:
        if body.level > highest + 1:
            raise HTTPException(
                status_code=422,
                detail="the ladder does not skip levels — request the next level first",
            )
        if body.level == 5:
            raise HTTPException(
                status_code=422,
                detail="level 5 is available after you submit your answer",
            )
    tutor = TutorService(session, request.app.state.gateway)
    try:
        hint = tutor.quiz_hint(attempt, question, body.level, body.last_response)
    except TutorError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.add(
        QuizHelpEvent(
            attempt_id=attempt.id,
            question_id=question.id,
            level=body.level,
            markdown=hint["markdown"],
            violations=hint["violations"],
        )
    )
    session.commit()
    return QuizHintOut(
        level=hint["level"], markdown=hint["markdown"], violations=hint["violations"]
    )


@router.get("/attempts/{attempt_id}/questions/{question_id}/help")
def list_quiz_help(
    attempt_id: int,
    question_id: int,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    profile = ensure_default_profile(session)
    attempt, _activity, _question = _load_attempt_question(
        session, attempt_id, profile.id, question_id
    )
    events = list(
        session.scalars(
            select(QuizHelpEvent)
            .where(
                QuizHelpEvent.attempt_id == attempt.id,
                QuizHelpEvent.question_id == question_id,
            )
            .order_by(QuizHelpEvent.id)
        )
    )
    return [
        {
            "level": event.level,
            "markdown": event.markdown,
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]


class AskOut(BaseModel):
    chat_session_id: int
    public_id: str


class RecognizeIn(BaseModel):
    png_base64: str = Field(min_length=1)


class RecognizeOut(BaseModel):
    markdown: str
    latex_candidates: list[str]


@router.post("/recognize", response_model=RecognizeOut)
def recognize_handwriting(
    body: RecognizeIn,
    request: Request,
    session: Session = Depends(get_session),
) -> RecognizeOut:
    ensure_default_profile(session)
    try:
        png = base64.b64decode(body.png_base64, validate=True)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="invalid png_base64") from error
    engine = NotesOcrEngine(request.app.state.gateway)
    try:
        markdown = engine.transcribe(png, "image/png", session=session)
    except (TaskUnassigned, ProviderError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    from ..math.leak_guard import extract_math

    candidates = [entry for entry in extract_math(markdown) if entry.strip()]
    session.add(
        AiInteraction(
            context_type="notes_ocr",
            direction="quiz answer recognition",
            model=None,
            input_tokens=max(1, len(markdown) // 4),
            output_tokens=max(1, len(markdown) // 4),
            latency_ms=None,
        )
    )
    session.commit()
    return RecognizeOut(markdown=markdown, latex_candidates=candidates[-3:])


@router.post(
    "/attempts/{attempt_id}/questions/{question_id}/ask",
    response_model=AskOut,
    status_code=201,
)
def ask_about_question(
    attempt_id: int,
    question_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> AskOut:
    profile = ensure_default_profile(session)
    attempt, activity, question = _load_attempt_question(
        session, attempt_id, profile.id, question_id
    )
    if attempt.mode == AttemptMode.EXAM and attempt.finished_at is None:
        raise HTTPException(status_code=422, detail="help is disabled in exam mode")
    service = ChatService(session, request.app.state.gateway, request.app.state.embedder)
    chat_session = service.create_session(
        profile.id,
        course_id=activity.course_id,
        title=f"Quiz question {question.id}",
        context={"quiz_attempt_id": attempt.id, "question_id": question.id},
    )
    seed_lines = [
        "I am working on this quiz question:",
        "",
        _blocks_to_md(question.stem),
    ]
    if question.options:
        for index, option in enumerate(question.options):
            seed_lines.append(f"{chr(65 + index)}. {_blocks_to_md([option])}")
    service.add_message(chat_session.id, "user", "\n".join(seed_lines))
    session.commit()
    return AskOut(chat_session_id=chat_session.id, public_id=chat_session.public_id)


@router.post("/attempts/{attempt_id}/finish", response_model=AttemptOut)
def finish_attempt(
    attempt_id: int, session: Session = Depends(get_session)
) -> AttemptOut:
    profile = ensure_default_profile(session)
    attempt = session.get(Attempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="attempt not found")
    activity = session.get(Activity, attempt.activity_id)
    if activity is None or activity.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="attempt not found")
    if attempt.finished_at is not None:
        return _attempt_out(attempt)
    answers = list(
        session.scalars(select(Answer).where(Answer.attempt_id == attempt.id))
    )
    total = len(
        session.scalars(select(Question.id).where(Question.activity_id == activity.id)).all()
    )
    score = 0.0
    for answer in answers:
        score += answer.partial_credit or 0.0
    attempt.score = round(score / total, 4) if total else 0.0
    from ..domain.models import utcnow

    attempt.finished_at = utcnow()
    session.commit()
    return _attempt_out(attempt)


@router.get("/attempts/{attempt_id}/report")
def attempt_report(
    attempt_id: int, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    attempt = session.get(Attempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="attempt not found")
    activity = session.get(Activity, attempt.activity_id)
    if activity is None or activity.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="attempt not found")
    answers = list(
        session.scalars(
            select(Answer).where(Answer.attempt_id == attempt.id).order_by(Answer.id)
        )
    )
    rows = []
    for answer in answers:
        question = session.get(Question, answer.question_id)
        rows.append(
            {
                "question_id": answer.question_id,
                "correct": answer.correct,
                "partial_credit": answer.partial_credit,
                "error_tags": answer.error_tags or [],
                "stem_excerpt": (
                    question.stem[0].get("md", "")[:80] if question and question.stem else ""
                ),
            }
        )
    return {
        "attempt": _attempt_out(attempt),
        "answers": rows,
    }


class InboxEntryOut(BaseModel):
    filename: str
    kind: str
    title: str
    ok: bool
    problems: list[str]
    question_count: int


def _inbox(request: Request) -> InboxService:
    return InboxService(request.app.state.settings.inbox_dir)


@router.get("/inbox", response_model=list[InboxEntryOut])
def inbox_scan(request: Request) -> list[InboxEntryOut]:
    _inbox(request).ensure_root()
    return [
        InboxEntryOut(
            filename=entry.filename,
            kind=entry.kind,
            title=entry.title,
            ok=entry.ok,
            problems=entry.problems,
            question_count=entry.question_count,
        )
        for entry in _inbox(request).scan()
    ]


@router.get("/inbox/path")
def inbox_path(request: Request) -> dict[str, str]:
    return {"path": str(_inbox(request).ensure_root())}


@router.post("/inbox/{filename}/import")
def inbox_import(
    filename: str,
    request: Request,
    session: Session = Depends(get_session),
    course_id: int = 0,
) -> dict[str, Any]:
    if course_id <= 0:
        raise HTTPException(status_code=422, detail="course_id is required")
    service = _inbox(request)
    try:
        document = service.load_document(filename)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="file not in inbox") from error
    except ValueError as error:
        service.mark(filename, "rejected", str(error))
        raise HTTPException(status_code=422, detail=str(error)) from error
    questions = document.get("questions")
    if not isinstance(questions, list):
        service.mark(filename, "rejected", "no questions list")
        raise HTTPException(status_code=422, detail="no questions list")
    body = CaqDocument(
        title=str(document.get("title", filename)), questions=questions
    )
    result = import_caq(body, course_id=course_id, dry_run=False, session=session)
    if result["valid"] > 0:
        service.mark(filename, "imported")
    else:
        service.mark(filename, "rejected", "; ".join(result["results"][0]["problems"]))
    return result
