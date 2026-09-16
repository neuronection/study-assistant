import json
from pathlib import Path
from typing import Any

from pytest import fixture
from sqlalchemy.orm import Session
from test_chat_api import ScriptedGateway

from app.domain.models import (
    Course,
    Material,
    MaterialLink,
    Profile,
    TreeNode,
)
from app.pipelines.compose import (
    ComposeError,
    ComposeService,
    _render_practice_set,
    _validate_practice_draft,
)
from app.services.knowledge.context import (
    COVERAGE_GATE,
    COVERAGE_MIN_MATERIALS,
    ContextBundle,
    ContextResolver,
    ContextScope,
    ContextSpec,
    coverage_report,
)
from app.storage.blobs import BlobStore

LONG_DOC = (
    "# Study guide\n\n"
    "This guide walks through the study material step by step. It opens with "
    "the core definitions, then works through two fully explained examples "
    "before listing the common mistakes students make on this topic. Each "
    "section closes with a short recap so the document can be revised quickly "
    "the night before an exam. Read the definitions first, then attempt the "
    "examples on your own before comparing them with the worked solutions "
    "below, and finally skim the recap list to confirm nothing was missed."
)

SPEC = ContextSpec(course_id=1, node_id=2, scope=ContextScope.node)


def bundle_with(
    materials: list[dict[str, Any]], chunks: list[dict[str, Any]]
) -> ContextBundle:
    return ContextBundle(
        SPEC,
        node=None,
        breadcrumb=[],
        material_ids=[int(entry["id"]) for entry in materials],
        materials=materials,
        chunks=chunks,
        notes=[],
        concepts=[],
        hints=[],
    )


def chunk(material_id: int, chunk_id: int) -> dict[str, Any]:
    return {"chunk_id": chunk_id, "material_id": material_id, "title": "t", "text": "x"}


def test_coverage_report_splits_covered_and_missing() -> None:
    materials = [{"id": 1}, {"id": 2}, {"id": 3}]
    report = coverage_report(materials, [chunk(1, 10), chunk(1, 11), chunk(3, 12)])
    assert report == {"total": 3, "covered": 2, "missing_ids": [2]}


def test_coverage_report_empty_scope() -> None:
    assert coverage_report([], [chunk(1, 10)]) == {
        "total": 0,
        "covered": 0,
        "missing_ids": [],
    }


def test_bundle_coverage_property_and_stats() -> None:
    bundle = bundle_with(
        [{"id": 5, "title": "a"}, {"id": 6, "title": "b"}], [chunk(5, 1)]
    )
    assert bundle.coverage == {"total": 2, "covered": 1, "missing_ids": [6]}
    assert bundle.stats()["coverage"] == bundle.coverage


def test_resolver_second_round_fires_below_gate(
    db_session: Session, monkeypatch: Any
) -> None:
    _profile_id, course_id, node_id, material_ids = _scoped_course(db_session, 8)
    queries: list[str] = []

    def fake_retrieve(
        session: Session, query: str, embed_query: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        queries.append(query)
        if len(queries) == 1:
            return [chunk(material_ids[0], 1), chunk(material_ids[1], 2)]
        return [
            chunk(material_ids[2], 3),
            chunk(material_ids[0], 1),
            chunk(material_ids[3], 4),
        ]

    monkeypatch.setattr(
        "app.services.knowledge.context.retrieve_chunks_hybrid", fake_retrieve
    )
    resolver = ContextResolver(db_session, lambda query: None)
    bundle = resolver.resolve(
        ContextSpec(
            course_id=course_id,
            node_id=node_id,
            scope=ContextScope.node,
            include_material_ids=material_ids,
            query="limits",
        )
    )
    assert len(queries) == 2
    assert queries[1] != queries[0]
    assert bundle.coverage["total"] == 8
    assert bundle.coverage["covered"] == 4
    assert sorted(bundle.coverage["missing_ids"]) == sorted(material_ids[4:])
    assert len(bundle.chunks) == 4


def test_resolver_second_round_skipped_at_exact_gate(
    db_session: Session, monkeypatch: Any
) -> None:
    _profile_id, course_id, node_id, material_ids = _scoped_course(db_session, 8)
    calls: list[str] = []

    def fake_retrieve(
        session: Session, query: str, embed_query: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        calls.append(query)
        return [
            chunk(material_id, index)
            for index, material_id in enumerate(material_ids[:4])
        ]

    monkeypatch.setattr(
        "app.services.knowledge.context.retrieve_chunks_hybrid", fake_retrieve
    )
    resolver = ContextResolver(db_session, lambda query: None)
    bundle = resolver.resolve(
        ContextSpec(
            course_id=course_id,
            node_id=node_id,
            scope=ContextScope.node,
            include_material_ids=material_ids,
        )
    )
    assert len(calls) == 1
    assert bundle.coverage["covered"] / bundle.coverage["total"] == COVERAGE_GATE


def test_resolver_second_round_skipped_below_material_floor(
    db_session: Session, monkeypatch: Any
) -> None:
    _profile_id, course_id, node_id, material_ids = _scoped_course(
        db_session, COVERAGE_MIN_MATERIALS - 1
    )
    calls: list[str] = []

    def fake_retrieve(
        session: Session, query: str, embed_query: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        calls.append(query)
        return [chunk(material_ids[0], 1)]

    monkeypatch.setattr(
        "app.services.knowledge.context.retrieve_chunks_hybrid", fake_retrieve
    )
    resolver = ContextResolver(db_session, lambda query: None)
    bundle = resolver.resolve(
        ContextSpec(
            course_id=course_id,
            node_id=node_id,
            scope=ContextScope.node,
            include_material_ids=material_ids,
        )
    )
    assert len(calls) == 1
    assert bundle.coverage["covered"] == 1


def test_compose_records_coverage_and_flags_needs_review(
    db_session: Session, tmp_path: Path
) -> None:
    profile_id, course_id, _node_id, material_ids = _scoped_course(db_session, 8)
    materials = [
        {"id": material_id, "title": f"M{index}"}
        for index, material_id in enumerate(material_ids)
    ]
    bundle = bundle_with(
        materials,
        [chunk(material_id, index) for index, material_id in enumerate(material_ids[:2])],
    )
    gateway = ScriptedGateway([LONG_DOC])
    service = ComposeService(db_session, gateway)
    material = service.compose(
        profile_id=profile_id,
        course_id=course_id,
        node_id=None,
        kind="study_guide",
        title="Guide",
        context_bundle=bundle,
        blobs=BlobStore(tmp_path),
    )
    provenance = material.provenance
    assert isinstance(provenance, dict)
    assert provenance["coverage"] == {
        "total": 8,
        "covered": 2,
        "missing_ids": material_ids[2:],
    }
    assert provenance["needs_review"] is True


def test_compose_at_gate_records_coverage_without_flag(
    db_session: Session, tmp_path: Path
) -> None:
    profile_id, course_id, _node_id, material_ids = _scoped_course(db_session, 8)
    materials = [
        {"id": material_id, "title": f"M{index}"}
        for index, material_id in enumerate(material_ids)
    ]
    bundle = bundle_with(
        materials,
        [chunk(material_id, index) for index, material_id in enumerate(material_ids[:4])],
    )
    gateway = ScriptedGateway([LONG_DOC])
    service = ComposeService(db_session, gateway)
    material = service.compose(
        profile_id=profile_id,
        course_id=course_id,
        node_id=None,
        kind="study_guide",
        title="Guide",
        context_bundle=bundle,
        blobs=BlobStore(tmp_path),
    )
    provenance = material.provenance
    assert isinstance(provenance, dict)
    assert provenance["coverage"]["covered"] == 4
    assert "needs_review" not in provenance


def test_compose_regenerate_replaces_stale_flag(
    db_session: Session, tmp_path: Path
) -> None:
    profile_id, course_id, _node_id, material_ids = _scoped_course(db_session, 8)
    materials = [
        {"id": material_id, "title": f"M{index}"}
        for index, material_id in enumerate(material_ids)
    ]
    low = bundle_with(
        materials,
        [chunk(material_id, index) for index, material_id in enumerate(material_ids[:2])],
    )
    gateway = ScriptedGateway([LONG_DOC])
    service = ComposeService(db_session, gateway)
    existing = service.compose(
        profile_id=profile_id,
        course_id=course_id,
        node_id=None,
        kind="study_guide",
        title="Guide",
        context_bundle=low,
        blobs=BlobStore(tmp_path),
    )
    assert existing.provenance is not None
    assert existing.provenance["needs_review"] is True
    covered = bundle_with(
        materials,
        [chunk(material_id, index) for index, material_id in enumerate(material_ids[:5])],
    )
    gateway.responses.append(LONG_DOC)
    updated = service.compose(
        profile_id=profile_id,
        course_id=course_id,
        node_id=None,
        kind="study_guide",
        title="Guide",
        context_bundle=covered,
        blobs=BlobStore(tmp_path),
        existing=existing,
        existing_md=None,
    )
    assert updated.id == existing.id
    provenance = updated.provenance
    assert isinstance(provenance, dict)
    assert provenance["coverage"] == {
        "total": 8,
        "covered": 5,
        "missing_ids": material_ids[5:],
    }
    assert "needs_review" not in provenance


def test_include_unassigned_merges_ready_orphans(
    db_session: Session, monkeypatch: Any
) -> None:
    profile_id, course_id, node_id, material_ids = _scoped_course(db_session, 2)
    for material_id in material_ids:
        db_session.add(
            MaterialLink(
                course_id=course_id,
                node_id=node_id,
                material_id=material_id,
            )
        )
    db_session.flush()
    orphan_ids: list[int] = []
    for index in range(3):
        material = Material(
            profile_id=profile_id,
            course_id=course_id,
            kind="doc",
            title=f"Orphan {index}",
            filename=f"orphan-{index}.txt",
            status="ready",
        )
        db_session.add(material)
        db_session.flush()
        orphan_ids.append(int(material.id))
    db_session.add(
        Material(
            profile_id=profile_id,
            course_id=course_id,
            kind="doc",
            title="Pending orphan",
            filename="pending.txt",
            status="pending",
        )
    )
    db_session.flush()
    captured: dict[str, Any] = {}

    def fake_retrieve(
        session: Session, query: str, embed_query: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        captured["material_ids"] = kwargs.get("material_ids")
        return []

    monkeypatch.setattr(
        "app.services.knowledge.context.retrieve_chunks_hybrid", fake_retrieve
    )
    resolver = ContextResolver(db_session, lambda query: None)
    bundle = resolver.resolve(
        ContextSpec(
            course_id=course_id,
            node_id=node_id,
            scope=ContextScope.node,
            include_unassigned=True,
        )
    )
    assert captured["material_ids"] is not None
    assert sorted(captured["material_ids"]) == sorted(material_ids + orphan_ids)
    titles = {str(entry["title"]) for entry in bundle.materials}
    assert "Orphan 0" in titles
    assert "Pending orphan" not in titles

    bundle_off = resolver.resolve(
        ContextSpec(
            course_id=course_id,
            node_id=node_id,
            scope=ContextScope.node,
        )
    )
    assert captured["material_ids"] == material_ids
    assert len(bundle_off.materials) == 2


@fixture
def gateway() -> ScriptedGateway:
    return ScriptedGateway([LONG_DOC])


def _scoped_course(
    session: Session, count: int
) -> tuple[int, int, int, list[int]]:
    profile = Profile(name="p")
    session.add(profile)
    session.flush()
    course = Course(profile_id=profile.id, title="Calc")
    session.add(course)
    session.flush()
    node = TreeNode(
        course_id=course.id,
        title="Limits",
        depth=1,
        path=f"/{course.id}",
        sort_path="/",
    )
    session.add(node)
    session.flush()
    ids: list[int] = []
    for index in range(count):
        material = Material(
            profile_id=profile.id,
            course_id=course.id,
            kind="doc",
            title=f"Lecture {index}",
            filename=f"lecture-{index}.txt",
            status="ready",
        )
        session.add(material)
        session.flush()
        ids.append(int(material.id))
    return int(profile.id), int(course.id), int(node.id), ids


def _practice_json() -> str:
    return json.dumps(
        {
            "items": [
                {
                    "stem_md": "Compute $2+2$.",
                    "answer_kind": "numeric",
                    "answer": {"value": "4"},
                    "solution_steps": ["Add the numbers.", "$2+2=4$"],
                },
                {
                    "stem_md": "Is the derivative of $x^2$ equal to $2x$?",
                    "answer_kind": "truefalse",
                    "answer": {"value": True},
                },
                {
                    "stem_md": "Which option equals $\\frac{d}{dx}\\sin(x)$?",
                    "answer_kind": "single",
                    "choices": ["$\\cos(x)$", "$-\\sin(x)$", "$\\tan(x)$"],
                    "answer": {"index": 0},
                },
                {
                    "stem_md": "Expand and simplify $(x-3)(x+3)$.",
                    "answer_kind": "equation",
                    "choices": ["$x^2 + 9$", "$(x-3)^2$"],
                    "answer": {"value": "x^2 - 9"},
                    "solution_steps": ["Difference of squares."],
                },
            ]
        }
    )


def test_validate_practice_draft_accepts_the_valid_contract() -> None:
    problems = _validate_practice_draft(json.loads(_practice_json()), [])
    assert problems == []


def test_validate_practice_draft_rejects_bad_items() -> None:
    draft = {
        "items": [
            {"stem_md": "Pick one", "answer_kind": "code", "answer": {}},
            {"stem_md": "", "answer_kind": "truefalse", "answer": {"value": True}},
            {"stem_md": "No answer object", "answer_kind": "numeric"},
            {
                "stem_md": "Unparseable",
                "answer_kind": "equation",
                "answer": {"value": "x ==="},
            },
            {
                "stem_md": "Distractor equals answer",
                "answer_kind": "equation",
                "choices": ["x^2 - 9", "x^2 + 9"],
                "answer": {"value": "x^2-9"},
            },
        ]
    }
    problems = _validate_practice_draft(draft, [])
    joined = "; ".join(problems)
    assert "answer_kind 'code'" in joined
    assert "empty stem" in joined
    assert "missing answer object" in joined
    assert "is not parseable" in joined
    assert "distractor 0 equals the answer" in joined


def test_validate_practice_draft_requires_items_and_caps_count() -> None:
    assert _validate_practice_draft({}, []) == ["response missing items list"]
    assert _validate_practice_draft({"items": []}, []) == [
        "response missing items list"
    ]
    oversized = {
        "items": [
            {
                "stem_md": f"Problem {index}",
                "answer_kind": "numeric",
                "answer": {"value": str(index)},
            }
            for index in range(31)
        ]
    }
    problems = _validate_practice_draft(oversized, [])
    assert any("too many items" in problem for problem in problems)


def test_render_practice_set_keeps_problems_then_answers_contract() -> None:
    markdown = _render_practice_set("Practice", json.loads(_practice_json())["items"])
    problems_at = markdown.index("## Problems")
    answers_at = markdown.index("## Answers")
    assert problems_at < answers_at
    assert "1. Compute $2+2$." in markdown
    assert "a) $\\cos(x)$" in markdown
    assert "— true or false?" in markdown
    assert "1. 4" in markdown
    assert "2. True" in markdown
    assert "3. a) $\\cos(x)$" in markdown
    assert "4. $x^2 - 9$" in markdown
    assert "   - Difference of squares." in markdown


def test_compose_practice_set_persists_markdown_and_provenance(
    db_session: Session, tmp_path: Path
) -> None:
    profile_id, course_id, _node_id, _material_ids = _scoped_course(db_session, 1)
    gateway = ScriptedGateway([_practice_json()])
    service = ComposeService(db_session, gateway)
    blobs = BlobStore(tmp_path)
    material = service.compose(
        profile_id=profile_id,
        course_id=course_id,
        node_id=None,
        kind="practice_set",
        title="Derivatives drill",
        context_bundle=None,
        blobs=blobs,
    )
    sha = material.blob_sha
    assert sha is not None
    stored_bytes = blobs.get(sha)
    assert stored_bytes is not None
    stored = stored_bytes.decode()
    assert stored is not None
    assert "## Problems" in stored
    assert "## Answers" in stored
    provenance = material.provenance
    assert isinstance(provenance, dict)
    items = provenance["practice_items"]
    assert len(items) == 4
    assert items[0]["checks"] == {"shape": True, "parse": True, "distractors": True}
    assert items[2]["choices"][0] == "$\\cos(x)$"


def test_compose_practice_set_repairs_then_succeeds(
    db_session: Session, tmp_path: Path
) -> None:
    profile_id, course_id, _node_id, _material_ids = _scoped_course(db_session, 1)
    bad = json.dumps(
        {
            "items": [
                {
                    "stem_md": "Compute $3\\cdot3$.",
                    "answer_kind": "numeric",
                    "answer": {"value": "nine"},
                }
            ]
        }
    )
    gateway = ScriptedGateway([bad, _practice_json()])
    service = ComposeService(db_session, gateway)
    material = service.compose(
        profile_id=profile_id,
        course_id=course_id,
        node_id=None,
        kind="practice_set",
        title="Drill",
        context_bundle=None,
        blobs=BlobStore(tmp_path),
    )
    assert len(gateway.calls) == 2
    feedback = "\n".join(str(m.content) for m in gateway.calls[1])
    assert "numeric answer needs numeric value" in feedback
    provenance = material.provenance
    assert isinstance(provenance, dict)
    assert len(provenance["practice_items"]) == 4


def test_compose_practice_set_exhausts_repair_and_raises(
    db_session: Session, tmp_path: Path
) -> None:
    profile_id, course_id, _node_id, _material_ids = _scoped_course(db_session, 1)
    bad = json.dumps(
        {
            "items": [
                {
                    "stem_md": "Compute $3\\cdot3$.",
                    "answer_kind": "numeric",
                    "answer": {"value": "nine"},
                }
            ]
        }
    )
    gateway = ScriptedGateway([bad, bad, bad])
    service = ComposeService(db_session, gateway)
    try:
        service.compose(
            profile_id=profile_id,
            course_id=course_id,
            node_id=None,
            kind="practice_set",
            title="Drill",
            context_bundle=None,
            blobs=BlobStore(tmp_path),
        )
    except ComposeError as error:
        assert "did not pass validation" in str(error)
    else:
        raise AssertionError("ComposeError not raised")
