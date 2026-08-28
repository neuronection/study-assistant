from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..domain.models import AiModel, Course, DefaultTaskAssignment, Material, Provider
from ..pipelines.chunking import chunk_markdown
from ..pipelines.ingest import _store_extraction
from ..services.materials import detect_kind
from ..services.profiles import ensure_default_profile
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


@router.get("/state")
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


@router.post("/sample", status_code=201)
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
    session.commit()
    return {"course_id": course.id, "materials": created, "created": True}
