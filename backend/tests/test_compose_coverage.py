from pathlib import Path
from typing import Any

from pytest import fixture
from sqlalchemy.orm import Session

from app.domain.models import Course, Material, Profile, TreeNode
from app.pipelines.compose import ComposeService
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
from test_chat_api import ScriptedGateway

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
