import hashlib
import json
import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import PaperSource, QuestionType
from ...domain.models import (
    Activity,
    Answer,
    Attempt,
    Concept,
    ExamPaper,
    Question,
)
from ...domain.payloads import (
    GradeBand,
    PaperDocument,
    PaperQuestionMark,
    PaperSectionDoc,
)

DEFAULT_GRADE_BANDS: list[GradeBand] = [
    {"label": "A", "min": 90.0},
    {"label": "B", "min": 80.0},
    {"label": "C", "min": 70.0},
    {"label": "D", "min": 60.0},
]


class ExamRoomError(ValueError):
    pass


@dataclass(frozen=True)
class SectionSpec:
    title: str
    marks: int
    count: int
    difficulty: float | None = None
    types: list[str] | None = None


@dataclass
class PaperResult:
    paper: ExamPaper
    activity: Activity
    questions: list[Question] = field(default_factory=list)


def _stable_seed(
    course_id: str,
    title: str,
    duration_min: int,
    sections: list[SectionSpec],
) -> int:
    payload = json.dumps(
        {
            "course": course_id,
            "title": title,
            "duration_min": duration_min,
            "sections": [
                {
                    "title": section.title,
                    "marks": section.marks,
                    "count": section.count,
                    "difficulty": section.difficulty,
                    "types": section.types,
                }
                for section in sections
            ],
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _stem_key(question: Question) -> str:
    return json.dumps(question.stem, sort_keys=True, default=str)


def _validated_sections(sections: list[SectionSpec]) -> None:
    if not 1 <= len(sections) <= 8:
        raise ExamRoomError("a paper needs 1-8 sections")
    allowed_types = {member.value for member in QuestionType}
    for section in sections:
        if not section.title.strip():
            raise ExamRoomError("each section needs a title")
        if section.count < 1 or section.marks < 1:
            raise ExamRoomError("each section needs at least one question and one mark")
        if section.marks < section.count:
            raise ExamRoomError(f"section {section.title!r} needs at least one mark per question")
        if section.types is not None:
            unknown = sorted(set(section.types) - allowed_types)
            if unknown:
                raise ExamRoomError(f"unknown question types: {', '.join(unknown)}")


def _pick(
    candidates: list[Question],
    used_questions: set[str],
    used_stems: set[str],
    spec: SectionSpec,
    rng: random.Random,
) -> list[Question]:
    pool = [
        question
        for question in candidates
        if question.id not in used_questions
        and _stem_key(question) not in used_stems
        and (spec.types is None or question.type in spec.types)
        and (
            spec.difficulty is None
            or question.difficulty is None
            or abs(question.difficulty - spec.difficulty) <= 0.75
        )
    ]
    rng.shuffle(pool)
    return pool[: spec.count]


def assemble_paper(
    session: Session,
    *,
    profile_id: str,
    course_id: str,
    title: str,
    duration_min: int,
    sections: list[SectionSpec],
    instructions_md: str | None = None,
    node_id: str | None = None,
    grade_bands: list[GradeBand] | None = None,
    seed: int | None = None,
) -> PaperResult:
    _validated_sections(sections)
    if not 5 <= duration_min <= 360:
        raise ExamRoomError("duration must be 5-360 minutes")
    if not 1 <= sum(section.marks for section in sections) <= 10000:
        raise ExamRoomError("total marks must be between 1 and 10000")
    bands = grade_bands or DEFAULT_GRADE_BANDS
    labels = [str(band.get("label", "")).strip() for band in bands]
    if any(not label for label in labels) or len(set(labels)) != len(labels):
        raise ExamRoomError("grade bands need unique non-empty labels")
    if any(not 0 <= float(band.get("min", 0)) <= 100 for band in bands):
        raise ExamRoomError("grade band minima must be between 0 and 100")

    candidates = list(
        session.scalars(
            select(Question)
            .join(Activity, Activity.id == Question.activity_id)
            .where(
                Activity.course_id == course_id,
                Activity.type == "quiz",
                Question.parent_id.is_(None),
            )
            .order_by(Question.created_at, Question.id)
        )
    )
    if not candidates:
        raise ExamRoomError("no questions in this course yet — generate a quiz first")

    resolved_seed = (
        seed if seed is not None else _stable_seed(course_id, title, duration_min, sections)
    )
    rng = random.Random(resolved_seed)
    activity = Activity(
        profile_id=profile_id,
        course_id=course_id,
        node_id=node_id,
        title=title[:300],
        type="exam",
        time_limit_sec=duration_min * 60,
        config={"count": sum(section.count for section in sections)},
    )
    session.add(activity)
    session.flush()

    document_sections: list[PaperSectionDoc] = []
    used_questions: set[str] = set()
    used_stems: set[str] = set()
    created: list[Question] = []
    for spec in sections:
        picked = _pick(candidates, used_questions, used_stems, spec, rng)
        if len(picked) < spec.count:
            raise ExamRoomError(
                f"section {spec.title!r} needs {spec.count} questions, only {len(picked)} available"
            )
        base, extra = divmod(spec.marks, len(picked))
        marks = [base + (1 if position < extra else 0) for position in range(len(picked))]
        entries: list[PaperQuestionMark] = []
        for question, question_marks in zip(picked, marks, strict=True):
            used_questions.add(question.id)
            used_stems.add(_stem_key(question))
            copy = Question(
                activity_id=activity.id,
                type=question.type,
                stem=question.stem,
                options=question.options,
                answer=question.answer,
                explanation=question.explanation,
                difficulty=question.difficulty,
                bloom=question.bloom,
                skill=question.skill,
                concept_ids=question.concept_ids,
                expected_time_sec=question.expected_time_sec,
                curriculum_code=question.curriculum_code,
                source_refs=question.source_refs,
                distractor_misconceptions=question.distractor_misconceptions,
                sympy_check=question.sympy_check,
                input_modes=question.input_modes,
                tags=question.tags,
                provenance=question.provenance,
                flag=question.flag,
                stats=None,
            )
            session.add(copy)
            session.flush()
            created.append(copy)
            entries.append(PaperQuestionMark(question_id=copy.id, marks=question_marks))
        document_sections.append(
            PaperSectionDoc(
                id=str(uuid.uuid4()),
                title=spec.title,
                instructions=None,
                marks=spec.marks,
                questions=entries,
            )
        )

    document: PaperDocument = {
        "sections": document_sections,
        "source": PaperSource.BANK.value,
        "seed": resolved_seed,
    }
    paper = ExamPaper(
        profile_id=profile_id,
        course_id=course_id,
        node_id=node_id,
        activity_id=activity.id,
        title=title[:300],
        instructions_md=instructions_md,
        duration_min=duration_min,
        total_marks=sum(section.marks for section in sections),
        grade_bands=bands,
        document=document,
        source=PaperSource.BANK.value,
    )
    session.add(paper)
    session.flush()
    return PaperResult(paper=paper, activity=activity, questions=created)


def _band(percent: float, bands: list[GradeBand] | None) -> str | None:
    label: str | None = None
    floor = -1.0
    for entry in bands or []:
        minimum = float(entry.get("min", 0))
        candidate = entry.get("label")
        if candidate is not None and percent * 100 >= minimum and minimum > floor:
            label = str(candidate)
            floor = minimum
    return label


def latest_attempt(session: Session, paper: ExamPaper) -> Attempt | None:
    return session.scalars(
        select(Attempt)
        .where(
            Attempt.activity_id == paper.activity_id,
            Attempt.finished_at.is_not(None),
        )
        .order_by(Attempt.finished_at.desc())
        .limit(1)
    ).first()


def paper_marks(
    session: Session,
    paper: ExamPaper,
    attempt: Attempt | None,
) -> tuple[float, int, float]:
    credit: dict[str, float] = {}
    if attempt is not None:
        for answer in session.scalars(select(Answer).where(Answer.attempt_id == attempt.id)):
            credit[answer.question_id] = float(answer.partial_credit or 0.0)
    earned = 0.0
    total = 0
    for section in (paper.document or {}).get("sections", []):
        for entry in section.get("questions", []):
            marks = int(entry.get("marks", 0))
            total += marks
            earned += marks * credit.get(str(entry.get("question_id")), 0.0)
    percent = (earned / total) if total else 0.0
    return round(earned, 2), total, round(percent, 4)


def paper_report(
    session: Session,
    paper: ExamPaper,
    attempt_id: str | None = None,
) -> dict[str, Any]:
    attempts = list(
        session.scalars(
            select(Attempt)
            .where(
                Attempt.activity_id == paper.activity_id,
                Attempt.finished_at.is_not(None),
            )
            .order_by(Attempt.finished_at.desc())
        )
    )
    attempt = None
    if attempt_id is not None:
        attempt = next((row for row in attempts if row.id == attempt_id), None)
        if attempt is None:
            raise ExamRoomError("finished attempt not found for this paper")
    elif attempts:
        attempt = attempts[0]

    credit: dict[str, float] = {}
    answered_ids: set[str] = set()
    if attempt is not None:
        for answer in session.scalars(select(Answer).where(Answer.attempt_id == attempt.id)):
            credit[answer.question_id] = float(answer.partial_credit or 0.0)
            answered_ids.add(answer.question_id)

    sections = []
    total = 0
    earned = 0.0
    entries: list[PaperQuestionMark] = []
    for section in (paper.document or {}).get("sections", []):
        section_entries = list(section.get("questions", []))
        entries.extend(section_entries)
        section_earned = 0.0
        for entry in section_entries:
            marks = int(entry.get("marks", 0))
            total += marks
            section_earned += round(marks * credit.get(str(entry.get("question_id")), 0.0), 2)
        earned += section_earned
        sections.append(
            {
                "id": section.get("id"),
                "title": section.get("title"),
                "marks": section.get("marks"),
                "earned": round(section_earned, 2),
            }
        )

    question_ids = [str(entry.get("question_id")) for entry in entries]
    questions = {
        question.id: question
        for question in session.scalars(select(Question).where(Question.id.in_(question_ids)))
    }
    concept_ids = {
        concept_id for question in questions.values() for concept_id in (question.concept_ids or [])
    }
    concepts = {
        concept.id: concept.name
        for concept in session.scalars(select(Concept).where(Concept.id.in_(concept_ids)))
    }
    topic_marks: dict[str, dict[str, float]] = {}
    for entry in entries:
        question = questions.get(str(entry.get("question_id")))
        if question is None:
            continue
        marks = int(entry.get("marks", 0))
        lost = round(marks * (1 - credit.get(question.id, 0.0)), 2)
        for concept_id in question.concept_ids or []:
            row = topic_marks.setdefault(concept_id, {"lost": 0.0, "marks": 0.0})
            row["lost"] += lost
            row["marks"] += marks

    topics: list[dict[str, Any]] = [
        {
            "concept_id": concept_id,
            "name": concepts.get(concept_id, concept_id),
            "lost": round(row["lost"], 2),
            "marks": int(row["marks"]),
        }
        for concept_id, row in topic_marks.items()
        if row["lost"] > 0
    ]
    topics.sort(key=lambda row: (-float(row["lost"]), str(row["name"])))

    percent = (earned / total) if total else 0.0
    return {
        "paper_id": paper.id,
        "attempt_id": attempt.id if attempt is not None else None,
        "finished_at": (
            attempt.finished_at.isoformat() if attempt and attempt.finished_at else None
        ),
        "earned": round(earned, 2),
        "total": total,
        "percent": round(percent, 4),
        "grade": _band(percent, paper.grade_bands),
        "answered": len(answered_ids),
        "question_count": len(entries),
        "sections": sections,
        "topics": topics[:8],
    }


def delete_paper(session: Session, paper: ExamPaper) -> None:
    activity = session.get(Activity, paper.activity_id)
    session.delete(paper)
    if activity is not None:
        session.delete(activity)
    session.flush()
