from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..domain.models import (
    Activity,
    AiModel,
    Concept,
    Course,
    DefaultTaskAssignment,
    FsrsState,
    Material,
    NodeConcept,
    Provider,
    Question,
    utcnow,
)
from ..pipelines.chunking import chunk_markdown
from ..pipelines.ingest import _store_extraction
from ..services.content.materials import detect_kind
from ..services.knowledge.tree import TreeError, TreeService
from ..services.platform.profiles import ensure_default_profile
from ..services.study.cards import create_card_exercise
from ..storage.blobs import BlobStore
from ..storage.fts import sync_material_fts
from .deps import get_session

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

SAMPLE_COURSE_TITLE = "Calculus I (sample)"

SAMPLE_MATERIALS: list[tuple[str, str]] = [
    (
        "01 — Derivatives basics.md",
        (
            "# Derivatives basics\n\n"
            "The derivative measures instantaneous change. For $f(x) = x^n$ the "
            "**power rule** gives $f'(x) = n x^{n-1}$.\n\n"
            "## Rules to know\n\n"
            "- Sum rule: $(f + g)' = f' + g'$\n"
            "- Product rule: $(fg)' = f'g + fg'$\n"
            "- Quotient rule: $\\left(\\frac{f}{g}\\right)' = \\frac{f'g - fg'}{g^2}$\n"
            "- Chain rule: $(f \\circ g)'(x) = f'(g(x))\\,g'(x)$\n\n"
            "## Worked example\n\n"
            "Differentiate $f(x) = x^2 \\sin x$. By the product rule:\n\n"
            "$$f'(x) = 2x\\sin x + x^2\\cos x$$\n"
        ),
    ),
    (
        "02 — Limits and continuity.md",
        (
            "# Limits and continuity\n\n"
            "A limit $\\lim_{x \\to a} f(x) = L$ means values approach $L$ as $x$ "
            "approaches $a$. Continuity at $a$ requires the limit to exist, equal "
            "$f(a)$, and $f$ to be defined there.\n\n"
            "## Common technique\n\n"
            "For $\\lim_{x \\to 0} \\frac{\\sin x}{x}$, direct substitution gives "
            "$0/0$; the standard result is $1$.\n\n"
            "## Pitfall\n\n"
            "A function can be *defined* at a point yet fail to be continuous there "
            "— definition alone does not guarantee the limit exists.\n"
        ),
    ),
    (
        "03 — Integration intro.md",
        (
            "# Integration intro\n\n"
            "The indefinite integral reverses differentiation: "
            "$\\int x^n\\,dx = \\frac{x^{n+1}}{n+1} + C$ for $n \\neq -1$.\n\n"
            "## The constant matters\n\n"
            "Every antiderivative family differs by $C$. Forgetting $+C$ is the "
            "classic error — both $x^2$ and $x^2 + 7$ differentiate to $2x$.\n\n"
            "## Substitution\n\n"
            "For $\\int f(g(x))g'(x)\\,dx$, set $u = g(x)$ so the integral becomes "
            "$\\int f(u)\\,du$ — and in definite integrals, transform the bounds too.\n"
        ),
    ),
]


class OnboardingStateOut(BaseModel):
    has_provider: bool
    has_enabled_model: bool
    defaults_set: list[str]
    has_course: bool
    has_material: bool


@router.get("/state", response_model=OnboardingStateOut)
def get_onboarding_state(session: Session = Depends(get_session)) -> dict[str, Any]:
    has_provider = session.query(Provider.id).first() is not None
    has_enabled_model = (
        session.query(AiModel.id).filter(AiModel.enabled.is_(True)).first() is not None
    )
    defaults_set = [
        row.requires
        for row in session.query(DefaultTaskAssignment)
        .filter(DefaultTaskAssignment.model_id.isnot(None))
        .all()
    ]
    has_course = session.query(Course.id).first() is not None
    has_material = session.query(Material.id).first() is not None
    return {
        "has_provider": has_provider,
        "has_enabled_model": has_enabled_model,
        "defaults_set": sorted(defaults_set),
        "has_course": has_course,
        "has_material": has_material,
    }


class SampleCourseOut(BaseModel):
    course_id: int
    materials: int
    created: bool
    flashcards: int = 0
    quiz_questions: int = 0


SAMPLE_QUESTIONS: list[dict[str, Any]] = [
    {
        "type": "single",
        "stem": [{"type": "text", "md": "Which rule gives $(fg)' = f'g + fg'$?"}],
        "options": [
            {"type": "text", "md": "Product rule"},
            {"type": "text", "md": "Quotient rule"},
            {"type": "text", "md": "Chain rule"},
            {"type": "text", "md": "Power rule"},
        ],
        "answer": {"index": 0},
        "explanation": [{"type": "text", "md": "That identity **is** the product rule."}],
        "difficulty": 1,
        "bloom": "remember",
        "skill": "conceptual",
        "expected_time_sec": 30,
    },
    {
        "type": "numeric",
        "stem": [{"type": "text", "md": "Differentiate $f(x) = x^3$ and evaluate at $x = 2$."}],
        "answer": {"value": "12"},
        "explanation": [
            {"type": "text", "md": "Power rule: $f'(x) = 3x^2$, so $f'(2) = 12$."}
        ],
        "difficulty": 2,
        "bloom": "apply",
        "skill": "procedural",
        "expected_time_sec": 45,
    },
    {
        "type": "truefalse",
        "stem": [
            {"type": "text", "md": "True or false: $\\lim_{x \\to 0} \\frac{\\sin x}{x} = 1$."}
        ],
        "answer": {"value": True},
        "explanation": [
            {"type": "text", "md": "The standard limit; direct substitution gives $0/0$."}
        ],
        "difficulty": 2,
        "bloom": "remember",
        "skill": "conceptual",
        "expected_time_sec": 30,
    },
]

SAMPLE_CARDS: list[tuple[str, str, int]] = [
    ("State the power rule", "$f'(x) = n x^{n-1}$", 0),
    ("State the product rule", "$(fg)' = f'g + fg'$", 0),
    ("State the quotient rule", "$\\left(\\frac{f}{g}\\right)' = \\frac{f'g - fg'}{g^2}$", 3),
    ("State the chain rule", "$(f \\circ g)'(x) = f'(g(x))\\,g'(x)$", 5),
    ("$\\int x^n\\,dx = ?$", "$\\frac{x^{n+1}}{n+1} + C$ for $n \\neq -1$", 8),
    (
        "What does continuity at $a$ require?",
        "The limit exists, equals $f(a)$, and $f$ is defined at $a$",
        12,
    ),
]


def _seed_sample_study_content(session: Session, course: Course) -> tuple[int, int]:
    tree = TreeService(session)
    root = tree.ensure_root(course.id)

    concept = Concept(
        course_id=course.id,
        name="Derivatives",
        description="Rules for differentiating sums, products, quotients and compositions.",
    )
    session.add(concept)
    session.flush()
    session.add(NodeConcept(node_id=root.id, concept_id=concept.id, weight=1.0))

    activity = Activity(
        profile_id=course.profile_id,
        course_id=course.id,
        node_id=root.id,
        type="quiz",
        title="Sample quiz — Derivatives",
    )
    session.add(activity)
    session.flush()
    for draft in SAMPLE_QUESTIONS:
        session.add(
            Question(
                activity_id=activity.id,
                type=str(draft["type"]),
                stem=draft["stem"],
                options=draft.get("options"),
                answer=draft["answer"],
                explanation=draft["explanation"],
                difficulty=draft["difficulty"],
                bloom=draft["bloom"],
                skill=draft["skill"],
                concept_ids=[concept.id],
                expected_time_sec=draft["expected_time_sec"],
                flag="ok",
            )
        )

    now = utcnow()
    for index, (front, back, due_in_days) in enumerate(SAMPLE_CARDS):
        card = create_card_exercise(
            session,
            profile_id=course.profile_id,
            course_id=course.id,
            node_id=root.id,
            kind="basic",
            front=[{"type": "text", "md": front}],
            back=[{"type": "text", "md": back}],
            source="sample",
        )
        session.add(
            FsrsState(
                card_id=card.id,
                state="review",
                stability=2.5,
                difficulty=5.0,
                reps=1,
                lapses=0,
                due_at=now + timedelta(days=due_in_days, minutes=-index),
                last_review_at=now - timedelta(days=1),
            )
        )
    session.flush()
    return len(SAMPLE_CARDS), len(SAMPLE_QUESTIONS)


@router.post("/sample", status_code=201, response_model=SampleCourseOut)
def create_sample_course(
    request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    profile = ensure_default_profile(session)
    existing = session.query(Course).filter(Course.title == SAMPLE_COURSE_TITLE).first()
    if existing is not None:
        return {"course_id": existing.id, "materials": 0, "created": False}

    course = Course(
        profile_id=profile.id,
        title=SAMPLE_COURSE_TITLE,
        subject="Mathematics",
        level="Introductory",
        description="A small sample course so you can try everything immediately.",
        exam_date=date.today() + timedelta(days=14),
    )
    session.add(course)
    session.flush()

    blobs: BlobStore = request.app.state.blobs
    created = 0
    for filename, markdown in SAMPLE_MATERIALS:
        data = markdown.encode("utf-8")
        stored = blobs.put(data, mime="text/markdown", session=session)
        material = Material(
            profile_id=profile.id,
            course_id=course.id,
            kind=detect_kind(filename),
            title=filename.removesuffix(".md"),
            blob_sha=stored.sha256,
            filename=filename,
            mime="text/markdown",
            status="processing",
            content_hash=stored.sha256,
        )
        session.add(material)
        session.flush()
        _store_extraction(
            session, material, extractor="native", markdown=markdown, pages=None
        )
        sync_material_fts(session, material, markdown)
        material.status = "ready"
        _ = chunk_markdown(markdown)
        created += 1
    try:
        flashcards, quiz_questions = _seed_sample_study_content(session, course)
    except TreeError as error:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"sample course incomplete: {error}") from error
    session.commit()
    return {
        "course_id": course.id,
        "materials": created,
        "created": True,
        "flashcards": flashcards,
        "quiz_questions": quiz_questions,
    }
