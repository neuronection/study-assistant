"""Plan 51 Q3c2b2: golden-query sets, compare, bad matches and the quality gate."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.vocab import JobType
from app.domain.models import (
    AuditEvent,
    Chunk,
    Course,
    Extraction,
    Job,
    Material,
    VectorSpace,
)
from app.jobs.runner import JobError
from app.pipelines.retrieval_ops import (
    make_vector_cutover_handler,
    make_vector_reindex_handler,
)
from app.services.retrieval import lifecycle, quality, reads
from app.storage import retrieval_ops as ops

BASE = "/api/v1/admin/retrieval"
DIM = 4
SECRET = "SECRET-GOLDEN-QUERY-TEXT"


class MappingEmbedder:
    """Deterministic text → unit vector; the model label is explicit."""

    def __init__(
        self, vectors: dict[str, list[float]], model: str = "fake-embed"
    ) -> None:
        self.vectors = vectors
        self.model = model

    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return (self.model, [self.vectors[text] for text in texts])


def _stop_worker(client: TestClient) -> None:
    cast(Any, client.app).state.jobs.stop()


def _key(name: str) -> dict[str, str]:
    return {"Idempotency-Key": name}


def _seed_materials(
    session: Session, profile_id: str, texts: Sequence[str]
) -> tuple[list[str], list[str]]:
    """One material per text, one chunk each; returns (material ids, chunk ids)."""
    course = Course(profile_id=profile_id, title="Quality")
    session.add(course)
    session.flush()
    material_ids: list[str] = []
    chunk_ids: list[str] = []
    for index, text in enumerate(texts):
        material = Material(
            profile_id=profile_id,
            course_id=course.id,
            kind="md",
            title=f"Notes {index}",
            filename=f"notes-{index}.md",
            status="ready",
        )
        session.add(material)
        session.flush()
        extraction = Extraction(
            material_id=material.id,
            extractor="test",
            blocks=[{"type": "text", "md": text}],
            markdown=text,
        )
        session.add(extraction)
        session.flush()
        chunk = Chunk(extraction_id=extraction.id, ordinal=0, text=text)
        session.add(chunk)
        session.flush()
        material_ids.append(str(material.id))
        chunk_ids.append(str(chunk.id))
    session.commit()
    return material_ids, chunk_ids


def _backfill(session: Session, embed: MappingEmbedder, *, space_id: str | None = None) -> Job:
    payload: dict[str, Any] = {"limit": 50, "batch_size": 8}
    if space_id is not None:
        payload["space_id"] = space_id
    job = Job(
        type=JobType.VECTOR_REINDEX.value,
        payload=payload,
        status="running",
        progress=0,
    )
    session.add(job)
    session.commit()
    make_vector_reindex_handler(embed.embed)(session, job, lambda *_: None)
    return job


def _build_candidate(session: Session, *, name: str = "content-v2") -> VectorSpace:
    built, _changed = lifecycle.build_space(
        session,
        name=name,
        provider="fake",
        model="fake-embed-v2",
        dim=DIM,
        composer_version="1",
    )
    session.commit()
    row = session.get(VectorSpace, built.space_id)
    assert row is not None
    return row


def _golden(
    space: VectorSpace,
    *,
    expected: Sequence[Sequence[str]],
    k: int = 5,
    set_version: int = 1,
) -> ops.GoldenQuerySet:
    queries = tuple(
        ops.GoldenQueryFixture(
            query_id=f"q-{index}",
            query=f"{SECRET}-{index}",
            expected_document_ids=tuple(ids),
            k=k,
        )
        for index, ids in enumerate(expected)
    )
    return ops.GoldenQuerySet(
        space_id=str(space.id),
        set_version=set_version,
        k=k,
        queries=queries,
    )


def _stub_embedder(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, embedder: MappingEmbedder
) -> None:
    cast(Any, client.app).state.embedder = embedder


# ---------------------------------------------------------------------------
# loader / selector
# ---------------------------------------------------------------------------


def test_missing_fixture_is_an_honest_empty_install(tmp_path: Path) -> None:
    assert quality.load_golden_sets(tmp_path / "missing.json") == ()


def test_malformed_fixture_fails_loudly(tmp_path: Path) -> None:
    target = tmp_path / "golden.json"
    target.write_text('{"sets": [{"spaceId": "content", "setVersion": 1}]}', encoding="utf-8")
    with pytest.raises((KeyError, ValueError)):
        quality.load_golden_sets(target)


def test_loader_normalizes_ids_and_selector_prefers_id_then_version(
    tmp_path: Path,
) -> None:
    hex_id = "ab" * 16
    target = tmp_path / "golden.json"
    target.write_text(
        json.dumps(
            {
                "sets": [
                    {
                        "spaceId": "content",
                        "setVersion": 1,
                        "k": 5,
                        "queries": [
                            {
                                "queryId": "q-1",
                                "query": SECRET,
                                "expectedDocumentIds": [hex_id],
                                "k": 5,
                            }
                        ],
                    },
                    {
                        "spaceId": "space-exact",
                        "setVersion": 2,
                        "k": 5,
                        "queries": [
                            {
                                "queryId": "q-2",
                                "query": SECRET,
                                "expectedDocumentIds": ["doc-a"],
                                "k": 5,
                            }
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    sets = quality.load_golden_sets(target)
    assert len(sets) == 2
    normalized = sets[0].queries[0].expected_document_ids[0]
    assert normalized == "abababab-abab-abab-abab-abababababab"

    space = VectorSpace(
        id="space-exact",
        name="content",
        provider="fake",
        model="fake-embed",
        dim=DIM,
        status="building",
    )
    selected = quality.select_golden_set(space, sets)
    assert selected is not None
    assert selected.space_id == "space-exact"
    assert selected.set_version == 2


def test_shipped_fixture_is_valid_and_empty() -> None:
    sets = quality.load_golden_sets()
    assert sets == ()
    payload = json.loads(quality.golden_query_path().read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == 1


# ---------------------------------------------------------------------------
# compare / bad matches
# ---------------------------------------------------------------------------


def _two_space_setup(
    session: Session, profile_id: str
) -> tuple[VectorSpace, VectorSpace, tuple[str, str], MappingEmbedder]:
    materials, _chunks = _seed_materials(session, profile_id, ["alpha", "beta"])
    material_a, material_b = materials
    embed = MappingEmbedder(
        {
            "alpha": [1.0, 0.0, 0.0, 0.0],
            "beta": [0.0, 1.0, 0.0, 0.0],
            f"{SECRET}-0": [1.0, 0.0, 0.0, 0.0],
            f"{SECRET}-1": [0.0, 1.0, 0.0, 0.0],
        }
    )
    _backfill(session, embed)
    active = lifecycle.active_space_row(session)
    assert active is not None
    candidate = _build_candidate(session)
    _backfill(
        session,
        MappingEmbedder(embed.vectors, model="fake-embed-v2"),
        space_id=str(candidate.id),
    )
    return active, candidate, (material_a, material_b), embed


def test_compare_scores_pass_recall_and_precision(
    db_session: Session, profile_id: str
) -> None:
    active, candidate, (material_a, material_b), embed = _two_space_setup(
        db_session, profile_id
    )
    golden = _golden(candidate, expected=([material_a], [material_b]))
    outcome = quality.compare_spaces(
        db_session, active, candidate, embed=embed.embed, golden_sets=(golden,)
    )
    assert outcome.passed is True
    assert outcome.compare.new_recall_at_k == pytest.approx(1.0)
    assert outcome.compare.new_precision_at_k == pytest.approx(1.0)
    assert outcome.compare.old_recall_at_k == pytest.approx(1.0)
    assert outcome.bad_matches == ()
    payload = outcome.to_dict()
    assert payload["gate"] == "pass"
    assert SECRET not in json.dumps(payload)
    ops.assert_no_raw_text(payload)


def test_compare_below_floor_reports_bad_match_ids_and_scores(
    db_session: Session, profile_id: str
) -> None:
    active, candidate, (_material_a, material_b), embed = _two_space_setup(
        db_session, profile_id
    )
    # q-0 asks for material B but embeds the alpha vector; q-1 is a clean hit.
    golden = ops.GoldenQuerySet(
        space_id=str(candidate.id),
        set_version=1,
        k=1,
        queries=(
            ops.GoldenQueryFixture(
                query_id="q-0",
                query=SECRET,
                expected_document_ids=(material_b,),
                k=1,
            ),
            ops.GoldenQueryFixture(
                query_id="q-1",
                query=f"{SECRET}-1",
                expected_document_ids=(material_b,),
                k=1,
            ),
        ),
    )
    embed.vectors[SECRET] = [1.0, 0.0, 0.0, 0.0]
    outcome = quality.compare_spaces(
        db_session, active, candidate, embed=embed.embed, golden_sets=(golden,)
    )
    assert outcome.passed is False
    assert outcome.compare.new_recall_at_k == pytest.approx(0.5)
    assert outcome.compare.new_precision_at_k == pytest.approx(0.5)
    assert outcome.compare.queries[0].missing_document_ids == (material_b,)
    assert outcome.bad_matches
    detail = outcome.bad_matches[0]
    assert detail["query_id"] == "q-0"
    assert detail["space_id"] == str(candidate.id)
    assert detail["missing_document_ids"] == [material_b]
    assert detail["hits"]
    hit = detail["hits"][0]
    assert set(hit) == {"chunk_id", "document_id", "view", "distance", "score"}
    assert hit["view"] == "body"
    assert isinstance(hit["distance"], float)
    payload = json.dumps(outcome.to_dict())
    assert SECRET not in payload
    assert "alpha" not in payload and "beta" not in payload


def test_compare_without_a_golden_set_refuses(db_session: Session, profile_id: str) -> None:
    active, candidate, _ids, embed = _two_space_setup(db_session, profile_id)
    with pytest.raises(quality.GoldenSetMissing):
        quality.compare_spaces(
            db_session, active, candidate, embed=embed.embed, golden_sets=()
        )


def test_compare_blocked_when_the_embedder_is_unassigned(
    db_session: Session, profile_id: str
) -> None:
    active, candidate, _ids, _embed = _two_space_setup(db_session, profile_id)
    golden = _golden(candidate, expected=([_ids[0]],))
    with pytest.raises(quality.QualitySetupBlocked):
        quality.compare_spaces(
            db_session,
            active,
            candidate,
            embed=lambda _texts: None,
            golden_sets=(golden,),
        )


def test_compare_without_a_baseline_scores_the_candidate_alone(
    db_session: Session, profile_id: str
) -> None:
    materials, _chunks = _seed_materials(db_session, profile_id, ["alpha", "beta"])
    candidate = _build_candidate(db_session)
    embed = MappingEmbedder(
        {
            "alpha": [1.0, 0.0, 0.0, 0.0],
            "beta": [0.0, 1.0, 0.0, 0.0],
            SECRET: [1.0, 0.0, 0.0, 0.0],
            f"{SECRET}-0": [1.0, 0.0, 0.0, 0.0],
        }
    )
    _backfill(
        db_session,
        MappingEmbedder(embed.vectors, model="fake-embed-v2"),
        space_id=str(candidate.id),
    )
    golden = _golden(candidate, expected=([materials[0]],))
    outcome = quality.compare_spaces(
        db_session, None, candidate, embed=embed.embed, golden_sets=(golden,)
    )
    assert outcome.no_baseline is True
    assert outcome.compare.old_space_id == outcome.compare.new_space_id
    assert outcome.passed is True


def test_persisted_payload_round_trips_without_text(
    db_session: Session, profile_id: str
) -> None:
    active, candidate, (material_a, material_b), embed = _two_space_setup(
        db_session, profile_id
    )
    golden = _golden(candidate, expected=([material_a], [material_b]))
    outcome = quality.compare_spaces(
        db_session, active, candidate, embed=embed.embed, golden_sets=(golden,)
    )
    stored = quality.persisted_compare_payload(outcome, new_space=candidate)
    assert SECRET not in json.dumps(stored)
    parsed = quality.parse_persisted_compare(stored)
    assert parsed is not None
    assert parsed.new_space_id == str(candidate.id)
    assert parsed.passed is True
    assert quality.parse_persisted_compare({"quality": {"query": SECRET}}) is None


# ---------------------------------------------------------------------------
# read surface
# ---------------------------------------------------------------------------


def test_quality_read_states_are_honest(
    db_session: Session, profile_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_materials(db_session, profile_id, ["alpha", "beta"])
    _backfill(
        db_session,
        MappingEmbedder(
            {"alpha": [1.0, 0.0, 0.0, 0.0], "beta": [0.0, 1.0, 0.0, 0.0]}
        ),
    )
    active = lifecycle.active_space_row(db_session)
    assert active is not None

    missing = reads.quality_evidence(db_session)
    assert missing["state"] == "no_golden_set"
    assert missing["sampled"] is False
    assert missing["activation_gate"] == "unknown"

    golden = ops.GoldenQuerySet(
        space_id=str(active.id),
        set_version=1,
        k=5,
        queries=(
            ops.GoldenQueryFixture(
                query_id="q-0",
                query=SECRET,
                expected_document_ids=("doc-a",),
                k=5,
            ),
        ),
    )
    monkeypatch.setattr(quality, "load_golden_sets", lambda: (golden,))
    not_sampled = reads.quality_evidence(db_session)
    assert not_sampled["state"] == "not_sampled"
    assert not_sampled["set"]["set_version"] == 1
    assert not_sampled["quality"] is None
    assert SECRET not in json.dumps(not_sampled)

    compare = ops.QualityCompareDTO(
        old_space_id=str(active.id),
        new_space_id=str(active.id),
        set_version=1,
        k=5,
        old_recall_at_k=0.5,
        old_precision_at_k=0.5,
        new_recall_at_k=0.5,
        new_precision_at_k=0.5,
        passed=False,
        queries=(
            ops.QualityQueryResultDTO(
                query_id="q-0",
                expected_document_ids=("doc-a",),
                retrieved_document_ids=("doc-b",),
                recall_at_k=0.0,
                precision_at_k=0.0,
                missing_document_ids=("doc-a",),
                passed=False,
            ),
        ),
    )
    db_session.add(
        Job(
            type=JobType.VECTOR_CUTOVER.value,
            status="done",
            payload={"action": "quality_compare", "space_id": str(active.id)},
            result={
                "quality": compare.to_dict(),
                "bad_matches": [
                    {
                        "space_id": str(active.id),
                        "query_id": "q-0",
                        "missing_document_ids": ["doc-a"],
                        "hits": [
                            {
                                "chunk_id": "chunk-1",
                                "document_id": "doc-b",
                                "view": "body",
                                "distance": 0.4,
                                "score": 0.6,
                            }
                        ],
                    }
                ],
            },
        )
    )
    db_session.commit()

    sampled = reads.quality_evidence(db_session)
    assert sampled["state"] == "sampled"
    assert sampled["quality"]["passed"] is False
    assert sampled["activation_gate"] == "fail"
    assert sampled["bad_matches"][0]["hits"][0]["chunk_id"] == "chunk-1"
    assert SECRET not in json.dumps(sampled)

    spaces = reads.list_spaces(db_session)
    row = next(item for item in spaces["spaces"] if item["space_id"] == str(active.id))
    assert row["quality_state"] == "sampled"
    assert row["quality_gate"] == "fail"


# ---------------------------------------------------------------------------
# HTTP compare endpoint
# ---------------------------------------------------------------------------


def test_quality_compare_endpoint_persists_and_replays(
    client: TestClient,
    db_session: Session,
    profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stop_worker(client)
    active, candidate, (material_a, material_b), embed = _two_space_setup(
        db_session, profile_id
    )
    golden = _golden(candidate, expected=([material_a], [material_b]))
    monkeypatch.setattr(quality, "load_golden_sets", lambda: (golden,))
    _stub_embedder(monkeypatch, client, embed)

    body = {"space_id": str(candidate.id), "compare_space_id": str(active.id)}
    first = client.post(f"{BASE}/quality/compare", json=body, headers=_key("compare-0001"))
    assert first.status_code == 200, first.text
    payload = first.json()
    assert payload["action"] == "quality_compare"
    assert payload["gate"] == "pass"
    assert payload["quality"]["passed"] is True
    assert payload["quality_compare"]["new_space_id"] == str(candidate.id)
    assert payload["quality_state"] == "sampled"
    assert SECRET not in first.text

    run = db_session.get(Job, payload["run_id"])
    assert run is not None
    assert run.status == "done"
    stored = cast(dict[str, Any], run.result)
    assert stored["quality"]["new_space_id"] == str(candidate.id)
    assert stored["bad_matches"] == []

    replay = client.post(
        f"{BASE}/quality/compare", json=body, headers=_key("compare-0001")
    )
    assert replay.status_code == 200
    assert replay.json()["deduplicated"] is True
    assert replay.json()["run_id"] == payload["run_id"]

    read = client.get(f"{BASE}/quality?space={candidate.id}")
    assert read.status_code == 200
    read_body = read.json()
    assert read_body["state"] == "sampled"
    assert read_body["compare_run_id"] == payload["run_id"]
    assert read_body["quality"]["passed"] is True
    assert SECRET not in read.text


def test_quality_compare_endpoint_refuses_a_missing_set(
    client: TestClient,
    db_session: Session,
    profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stop_worker(client)
    active, candidate, _ids, embed = _two_space_setup(db_session, profile_id)
    monkeypatch.setattr(quality, "load_golden_sets", lambda: ())
    _stub_embedder(monkeypatch, client, embed)
    response = client.post(
        f"{BASE}/quality/compare",
        json={"space_id": str(candidate.id), "compare_space_id": str(active.id)},
        headers=_key("compare-missing"),
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["reason"] == "quality_no_golden_set"
    assert detail["quality_state"] == "not_sampled"
    assert detail["gate"] == "fail"
    assert SECRET not in response.text


# ---------------------------------------------------------------------------
# activation and cutover gates
# ---------------------------------------------------------------------------


def _activate(client: TestClient, space_id: str, key: str) -> tuple[int, dict[str, Any]]:
    response = client.post(f"{BASE}/spaces/{space_id}/activate", headers=_key(key))
    return response.status_code, cast(dict[str, Any], response.json())


def test_activation_requires_and_passes_coverage_and_quality(
    client: TestClient,
    db_session: Session,
    profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stop_worker(client)
    active, candidate, (material_a, material_b), embed = _two_space_setup(
        db_session, profile_id
    )
    golden = _golden(candidate, expected=([material_a], [material_b]))
    monkeypatch.setattr(quality, "load_golden_sets", lambda: (golden,))
    _stub_embedder(monkeypatch, client, embed)

    status, body = _activate(client, str(candidate.id), "activate-quality-pass")
    assert status == 200, body
    assert body["quality_state"] == "sampled"
    assert body["quality"]["passed"] is True
    assert body["quality_compare"]["passed"] is True
    assert body["gate"] == "pass"
    assert body["activation_gate"]["coverage_status"] == "pass"
    assert body["activation_gate"]["quality"] == "pass"
    assert body["activation_gate"]["allowed"] is True

    db_session.expire_all()
    assert db_session.get(VectorSpace, str(candidate.id)).status == "active"  # type: ignore[union-attr]
    assert db_session.get(VectorSpace, str(active.id)).status == "retired"  # type: ignore[union-attr]
    assert "vector.space.activated" in list(
        db_session.scalars(select(AuditEvent.action))
    )
    assert SECRET not in json.dumps(body)

    replay_status, replay = _activate(
        client, str(candidate.id), "activate-quality-pass-replay"
    )
    assert replay_status == 200
    assert replay["already_active"] is True
    assert replay["quality"] is None
    assert replay["quality_state"] == "already_active"


def test_activation_refuses_below_the_quality_floor_and_persists_evidence(
    client: TestClient,
    db_session: Session,
    profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stop_worker(client)
    _active, candidate, (_material_a, material_b), embed = _two_space_setup(
        db_session, profile_id
    )
    golden = ops.GoldenQuerySet(
        space_id=str(candidate.id),
        set_version=1,
        k=1,
        queries=(
            ops.GoldenQueryFixture(
                query_id="q-0",
                query=SECRET,
                expected_document_ids=(material_b,),
                k=1,
            ),
            ops.GoldenQueryFixture(
                query_id="q-1",
                query=SECRET,
                expected_document_ids=(material_b,),
                k=1,
            ),
        ),
    )
    embed.vectors[SECRET] = [1.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(quality, "load_golden_sets", lambda: (golden,))
    _stub_embedder(monkeypatch, client, embed)

    status, body = _activate(client, str(candidate.id), "activate-quality-fail")
    assert status == 409, body
    detail = body["detail"]
    assert detail["reason"] == "quality_gate_failed"
    assert detail["quality_state"] == "sampled"
    assert detail["quality"]["passed"] is False
    assert detail["activation_gate"]["quality"] == "fail"
    assert detail["activation_gate"]["allowed"] is False
    assert "quality_below_floor" in detail["activation_gate"]["reasons"]
    assert detail["bad_matches"]
    assert SECRET not in json.dumps(body)

    db_session.expire_all()
    assert db_session.get(VectorSpace, str(candidate.id)).status == "building"  # type: ignore[union-attr]
    run = db_session.scalars(
        select(Job).where(Job.idempotency_key == "activate-quality-fail")
    ).first()
    assert run is not None and run.status == "failed"
    refusal = cast(dict[str, Any], run.result)["refusal"]
    assert refusal["reason"] == "quality_gate_failed"
    assert refusal["quality_state"] == "sampled"
    assert refusal["activation_gate"]["quality"] == "fail"


def test_activation_refuses_without_a_golden_set(
    client: TestClient,
    db_session: Session,
    profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stop_worker(client)
    _active, candidate, _ids, embed = _two_space_setup(db_session, profile_id)
    monkeypatch.setattr(quality, "load_golden_sets", lambda: ())
    _stub_embedder(monkeypatch, client, embed)

    status, body = _activate(client, str(candidate.id), "activate-no-golden")
    assert status == 409
    detail = body["detail"]
    assert detail["reason"] == "quality_gate_failed"
    assert detail["quality_state"] == "not_sampled"
    assert detail["quality"] is None
    assert "quality_no_golden_set" in detail["activation_gate"]["reasons"]


def test_activation_still_requires_coverage(
    client: TestClient,
    db_session: Session,
    profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stop_worker(client)
    _seed_materials(db_session, profile_id, ["alpha", "beta"])
    candidate = _build_candidate(db_session, name="content-empty")
    golden = ops.GoldenQuerySet(
        space_id=str(candidate.id),
        set_version=1,
        k=5,
        queries=(
            ops.GoldenQueryFixture(
                query_id="q-0",
                query=SECRET,
                expected_document_ids=("doc-a",),
                k=5,
            ),
        ),
    )
    monkeypatch.setattr(quality, "load_golden_sets", lambda: (golden,))
    _stub_embedder(
        monkeypatch,
        client,
        MappingEmbedder({SECRET: [1.0, 0.0, 0.0, 0.0]}),
    )
    status, body = _activate(client, str(candidate.id), "activate-no-coverage")
    assert status == 409
    detail = body["detail"]
    assert "coverage_unknown" in detail["activation_gate"]["reasons"]
    assert detail["quality_state"] == "sampled"


def test_cutover_requires_quality_and_refuses_below_floor(
    client: TestClient,
    db_session: Session,
    profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stop_worker(client)
    active, candidate, (_material_a, material_b), embed = _two_space_setup(
        db_session, profile_id
    )
    golden = ops.GoldenQuerySet(
        space_id=str(candidate.id),
        set_version=1,
        k=1,
        queries=(
            ops.GoldenQueryFixture(
                query_id="q-0",
                query=SECRET,
                expected_document_ids=(material_b,),
                k=1,
            ),
            ops.GoldenQueryFixture(
                query_id="q-1",
                query=SECRET,
                expected_document_ids=(material_b,),
                k=1,
            ),
        ),
    )
    embed.vectors[SECRET] = [1.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(quality, "load_golden_sets", lambda: (golden,))
    accepted = client.post(
        f"{BASE}/cutover",
        json={"space_id": str(candidate.id), "limit": 50},
        headers=_key("cutover-quality-fail"),
    )
    assert accepted.status_code == 202, accepted.text
    run_id = accepted.json()["run_id"]
    db_session.expire_all()
    run = db_session.get(Job, run_id)
    assert run is not None
    with pytest.raises(JobError):
        make_vector_cutover_handler(embed.embed)(db_session, run, lambda *_: None)
    db_session.expire_all()
    run = db_session.get(Job, run_id)
    assert run is not None
    result = cast(dict[str, Any], run.result)
    assert result["gate"] == "fail"
    assert result["quality"]["passed"] is False
    assert result["quality_state"] == "sampled"
    assert result["bad_matches"]
    assert db_session.get(VectorSpace, str(candidate.id)).status == "building"  # type: ignore[union-attr]
    assert db_session.get(VectorSpace, str(active.id)).status == "active"  # type: ignore[union-attr]


def test_cutover_passes_quality_and_records_the_gate(
    client: TestClient,
    db_session: Session,
    profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stop_worker(client)
    active, candidate, (material_a, material_b), embed = _two_space_setup(
        db_session, profile_id
    )
    golden = _golden(candidate, expected=([material_a], [material_b]))
    monkeypatch.setattr(quality, "load_golden_sets", lambda: (golden,))
    accepted = client.post(
        f"{BASE}/cutover",
        json={"space_id": str(candidate.id), "limit": 50},
        headers=_key("cutover-quality-pass"),
    )
    assert accepted.status_code == 202, accepted.text
    run_id = accepted.json()["run_id"]
    db_session.expire_all()
    run = db_session.get(Job, run_id)
    assert run is not None
    make_vector_cutover_handler(embed.embed)(db_session, run, lambda *_: None)
    result = cast(dict[str, Any], run.result)
    assert result["gate"] == "pass"
    assert result["quality"]["passed"] is True
    assert result["quality_state"] == "sampled"
    assert result["activation_gate"]["quality"] == "pass"
    db_session.expire_all()
    assert db_session.get(VectorSpace, str(candidate.id)).status == "active"  # type: ignore[union-attr]
    assert db_session.get(VectorSpace, str(active.id)).status == "retired"  # type: ignore[union-attr]


def test_quality_compare_requires_admin(raw_client: TestClient) -> None:
    response = raw_client.post(
        f"{BASE}/quality/compare",
        json={"space_id": "a", "compare_space_id": "b"},
        headers=_key("admin-compare"),
    )
    assert response.status_code in (401, 403)


def test_activation_is_not_a_pass_without_quality(
    client: TestClient, db_session: Session, profile_id: str
) -> None:
    """The old ``quality=not_sampled`` success path is gone."""
    _stop_worker(client)
    _seed_materials(db_session, profile_id, ["alpha"])
    candidate = _build_candidate(db_session, name="content-legacy-check")
    _backfill(
        db_session,
        MappingEmbedder({"alpha": [1.0, 0.0, 0.0, 0.0]}, model="fake-embed-v2"),
        space_id=str(candidate.id),
    )
    status, body = _activate(client, str(candidate.id), "activate-no-quality-set")
    assert status == 409
    assert body["detail"]["quality_state"] == "not_sampled"
    assert body["detail"]["quality"] is None
    assert body["detail"]["gate"] != "pass"
