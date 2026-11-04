"""Versioned admin-authored golden-query sets and the pre-cutover compare.

Plan 51 Q3c2b2. The Quality evidence reads one versioned set per space from a
repo-local fixture — never from user traffic. Query text is lawful **only** in
that fixture; every retrieval DTO carries query ids, expected/retrieved
document ids and scores, never the input text.

The compare runs the same bounded vector search the live path uses
(:class:`StudyVectorStore.search_scored`) against the active (old) and
candidate (building) space. The study content space indexes chunks, so the
scored document ids are the chunks' material ids: ``expectedDocumentIds`` in
the fixture are material ids, and the bad-match detail carries the chunk ids
plus the distance/view evidence. No document text is read.

The shipped file is empty by default: a fresh install has no admin-authored
set, so activation refuses rather than fabricating a quality pass.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...ai.embeddings import embed_with_tags
from ...domain.models import Chunk, Extraction, Job, Material, VectorSpace
from ...storage.retrieval_ops import (
    GateStatus,
    GoldenQueryFixture,
    GoldenQuerySet,
    QualityCompareDTO,
    QualityDTO,
    assert_no_raw_text,
    evaluate_quality_compare,
    evaluate_quality_set,
)
from ...storage.vector_store import StudyVectorStore

GOLDEN_QUERY_SET_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "retrieval" / "golden_queries.json"
)

EmbedFn = Callable[[list[str]], tuple[str, list[list[float]]] | None]
RetrievedByQuery = Mapping[str, Sequence[str]]
OVERSAMPLE = 3
MAX_HITS = 300


class GoldenSetMissing(RuntimeError):
    """No versioned golden-query set exists for the space (quality is required)."""


class QualitySetupBlocked(RuntimeError):
    """The golden set exists but the query embedding could not be produced."""


def golden_query_path() -> Path:
    """The runtime golden-query fixture path (packaged with ``app/data``)."""
    return GOLDEN_QUERY_SET_PATH


def _canonical(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return str(value)


def _normalize_fixture(query: GoldenQueryFixture) -> GoldenQueryFixture:
    ids = tuple(_canonical(value) for value in query.expected_document_ids)
    if ids == query.expected_document_ids:
        return query
    return replace(query, expected_document_ids=ids)


def load_golden_sets(path: Path | None = None) -> tuple[GoldenQuerySet, ...]:
    """Load the versioned sets, validating each through the family contract.

    A missing file is an honest empty install (no set). A malformed file
    raises ``ValueError`` — an admin fixture that does not validate must fail
    loudly, never degrade to a fabricated score. UUID-shaped document ids are
    normalized so a hex-form fixture still matches the stored material ids.
    """
    target = path or GOLDEN_QUERY_SET_PATH
    if not target.is_file():
        return ()
    document = json.loads(target.read_text(encoding="utf-8"))
    rows = document.get("sets") or []
    sets = tuple(GoldenQuerySet.from_fixture(row) for row in rows)
    return tuple(
        replace(golden, queries=tuple(_normalize_fixture(query) for query in golden.queries))
        for golden in sets
    )


def select_golden_set(
    space: VectorSpace,
    golden_sets: Sequence[GoldenQuerySet],
) -> GoldenQuerySet | None:
    """The newest set for this space: an exact id beats a name match."""
    exact = [item for item in golden_sets if item.space_id == str(space.id)]
    named = [item for item in golden_sets if item.space_id == space.name]
    candidates = exact or named
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.set_version)


def golden_set_summary(golden: GoldenQuerySet) -> dict[str, Any]:
    """The versioned set without query text (ids, k and floors only)."""
    return {
        "space_id": golden.space_id,
        "set_version": golden.set_version,
        "k": golden.k,
        "floor_recall": golden.floor_recall,
        "floor_precision": golden.floor_precision,
        "query_count": len(golden.queries),
        "query_ids": [query.query_id for query in golden.queries],
        "revision_key": golden.revision_key,
    }


def _iso(moment: datetime | None = None) -> str:
    value = moment or datetime.now(UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _documents_for_chunks(session: Session, chunk_ids: Sequence[str]) -> dict[str, str]:
    """``chunk id -> material id`` for the retrieved hits (bounded by ``k``)."""
    wanted = [str(chunk_id) for chunk_id in chunk_ids if str(chunk_id)]
    if not wanted:
        return {}
    rows = session.execute(
        select(Chunk.id, Material.id)
        .join(Extraction, Extraction.id == Chunk.extraction_id)
        .join(Material, Material.id == Extraction.material_id)
        .where(Chunk.id.in_(wanted))
    )
    return {
        _canonical(str(chunk_id)): _canonical(str(material_id))
        for chunk_id, material_id in rows
    }


@dataclass(frozen=True)
class _SpaceRetrieval:
    documents: dict[str, list[str]]
    hits: dict[str, list[dict[str, Any]]]
    degraded: str | None = None
    blocked: str | None = None


def _hit_limit(k: int) -> int:
    return min(MAX_HITS, max(int(k) * OVERSAMPLE, int(k)))


def _retrieve(
    session: Session,
    space: VectorSpace,
    golden: GoldenQuerySet,
    *,
    embed: EmbedFn,
) -> _SpaceRetrieval:
    """Run the golden queries against one space (by id, active or building)."""
    store = StudyVectorStore(session, space_id=str(space.id))
    documents: dict[str, list[str]] = {}
    hits: dict[str, list[dict[str, Any]]] = {}
    degraded: str | None = None
    blocked: str | None = None
    limit = _hit_limit(golden.k)
    tags = {"space_id": str(space.id), "kind": "query", "view": "body"}
    for query in golden.queries:
        try:
            embedded = embed_with_tags(embed, [query.query], tags)
        except Exception:
            degraded = degraded or "embed_failed"
            blocked = blocked or "embed_failed"
            documents[query.query_id] = []
            hits[query.query_id] = []
            continue
        if embedded is None or not embedded[1]:
            degraded = degraded or "provider_unassigned"
            blocked = blocked or "provider_unassigned"
            documents[query.query_id] = []
            hits[query.query_id] = []
            continue
        _model, batch = embedded
        scored = store.search_scored(batch[0], limit=limit)
        document_for_chunk = _documents_for_chunks(
            session, [hit.chunk_id for hit in scored]
        )
        ordered: list[str] = []
        for hit in scored:
            document_id = document_for_chunk.get(_canonical(hit.chunk_id))
            if document_id is None or document_id in ordered:
                continue
            ordered.append(document_id)
        documents[query.query_id] = ordered[: golden.k]
        hits[query.query_id] = [
            {
                "chunk_id": hit.chunk_id,
                "document_id": document_for_chunk[_canonical(hit.chunk_id)],
                "view": hit.view,
                "distance": round(hit.distance, 6),
                "score": round(hit.score, 6),
            }
            for hit in scored
            if _canonical(hit.chunk_id) in document_for_chunk
        ][: max(golden.k, limit)]
    return _SpaceRetrieval(
        documents=documents,
        hits=hits,
        degraded=degraded,
        blocked=blocked,
    )


def quality_from_compare(
    compare: QualityCompareDTO, *, space_id: str | None = None
) -> QualityDTO:
    """The candidate's own score block behind a persisted compare."""
    return QualityDTO(
        space_id=space_id or compare.new_space_id,
        set_version=compare.set_version,
        k=compare.k,
        recall_at_k=compare.new_recall_at_k,
        precision_at_k=compare.new_precision_at_k,
        passed=compare.passed,
        queries=compare.queries,
        floor_recall=compare.floor_recall,
        floor_precision=compare.floor_precision,
        generated_at=compare.generated_at,
    )


def bad_matches(
    *,
    space_id: str,
    golden: GoldenQuerySet,
    quality: QualityDTO,
    retrieval: _SpaceRetrieval,
) -> tuple[dict[str, Any], ...]:
    """Per-query misses with chunk ids and score evidence (no raw text)."""
    failed = {row.query_id: row for row in quality.queries if not row.passed}
    details: list[dict[str, Any]] = []
    for query in golden.queries:
        row = failed.get(query.query_id)
        if row is None:
            continue
        details.append(
            {
                "space_id": space_id,
                "query_id": query.query_id,
                "missing_document_ids": list(row.missing_document_ids),
                "hits": list(retrieval.hits.get(query.query_id, [])),
            }
        )
    return tuple(details)


@dataclass(frozen=True)
class QualityCompareOutcome:
    """A compare plus the two spaces' structured degradation states."""

    compare: QualityCompareDTO
    set_version: int
    k: int
    old_degraded: str | None = None
    new_degraded: str | None = None
    no_baseline: bool = False
    bad_matches: tuple[dict[str, Any], ...] = ()

    @property
    def passed(self) -> bool:
        return bool(self.compare.passed)

    @property
    def gate(self) -> GateStatus:
        return GateStatus.PASS if self.passed else GateStatus.FAIL

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "quality": self.compare.to_dict(),
            "set_version": self.set_version,
            "k": self.k,
            "old_degraded": self.old_degraded,
            "new_degraded": self.new_degraded,
            "no_baseline": self.no_baseline,
            "bad_matches": list(self.bad_matches),
            "gate": self.gate.value,
        }
        return cast(dict[str, Any], assert_no_raw_text(payload))


def compare_spaces(
    session: Session,
    old_space: VectorSpace | None,
    new_space: VectorSpace,
    *,
    embed: EmbedFn,
    golden_sets: Sequence[GoldenQuerySet] | None = None,
) -> QualityCompareOutcome:
    """Score the versioned golden set on the old and new space.

    ``old_space=None`` is the first activation: the candidate is scored on its
    own and the compare reports no baseline (the two score columns match).
    A missing golden set raises :class:`GoldenSetMissing`; a provider failure
    raises :class:`QualitySetupBlocked`; the caller refuses instead of
    inventing a score. Query text never leaves this function.
    """
    sets = tuple(golden_sets) if golden_sets is not None else load_golden_sets()
    golden = select_golden_set(new_space, sets) or (
        select_golden_set(old_space, sets) if old_space is not None else None
    )
    if golden is None:
        raise GoldenSetMissing(
            f"no versioned golden-query set for space {new_space.name!r}; "
            "quality is required for activation"
        )
    generated_at = _iso()
    new_retrieval = _retrieve(session, new_space, golden, embed=embed)
    if new_retrieval.blocked is not None:
        raise QualitySetupBlocked(
            f"the quality compare for space {new_space.name!r} could not embed "
            f"the golden queries ({new_retrieval.blocked})"
        )
    if old_space is None or str(old_space.id) == str(new_space.id):
        new_quality = evaluate_quality_set(
            golden, new_retrieval.documents, generated_at=generated_at
        )
        compare = QualityCompareDTO(
            old_space_id=str(new_space.id),
            new_space_id=str(new_space.id),
            set_version=golden.set_version,
            k=golden.k,
            old_recall_at_k=new_quality.recall_at_k,
            old_precision_at_k=new_quality.precision_at_k,
            new_recall_at_k=new_quality.recall_at_k,
            new_precision_at_k=new_quality.precision_at_k,
            passed=new_quality.passed,
            floor_recall=new_quality.floor_recall,
            floor_precision=new_quality.floor_precision,
            queries=new_quality.queries,
            generated_at=generated_at,
        )
        outcome = QualityCompareOutcome(
            compare=compare,
            set_version=golden.set_version,
            k=golden.k,
            old_degraded=new_retrieval.degraded,
            new_degraded=new_retrieval.degraded,
            no_baseline=True,
            bad_matches=bad_matches(
                space_id=str(new_space.id),
                golden=golden,
                quality=new_quality,
                retrieval=new_retrieval,
            ),
        )
        assert_no_raw_text(outcome.to_dict())
        return outcome

    old_retrieval = _retrieve(session, old_space, golden, embed=embed)
    if old_retrieval.blocked is not None:
        raise QualitySetupBlocked(
            f"the quality compare for space {old_space.name!r} could not embed "
            f"the golden queries ({old_retrieval.blocked})"
        )
    compare = evaluate_quality_compare(
        str(old_space.id),
        str(new_space.id),
        golden.set_version,
        golden.queries,
        old_retrieval.documents,
        new_retrieval.documents,
        k=golden.k,
        generated_at=generated_at,
    )
    outcome = QualityCompareOutcome(
        compare=compare,
        set_version=golden.set_version,
        k=golden.k,
        old_degraded=old_retrieval.degraded,
        new_degraded=new_retrieval.degraded,
        bad_matches=bad_matches(
            space_id=str(new_space.id),
            golden=golden,
            quality=quality_from_compare(compare),
            retrieval=new_retrieval,
        ),
    )
    assert_no_raw_text(outcome.to_dict())
    return outcome


MAX_JOBS = 200


def latest_persisted_compare(
    session: Session,
    *,
    candidate: VectorSpace,
    baseline: VectorSpace | None,
    golden: GoldenQuerySet,
) -> tuple[Job, QualityCompareDTO, list[dict[str, Any]]] | None:
    """The newest stored compare for this candidate, baseline, set and ``k``.

    A standalone ``quality_compare`` run, an activation evaluation or a cutover
    evaluation all persist the compare on the job result; reusing one makes an
    activation reproducible without re-embedding the golden queries.
    """
    expected_baseline = str(baseline.id) if baseline is not None else str(candidate.id)
    rows = session.scalars(
        select(Job)
        .where(
            Job.type == "VECTOR_CUTOVER",
            Job.status == "done",
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(MAX_JOBS)
    ).all()
    for job in rows:
        payload = job.payload if isinstance(job.payload, Mapping) else {}
        if payload.get("action") not in (
            "quality_compare",
            "activate_space",
            "cutover",
        ):
            continue
        compare = parse_persisted_compare(job.result)
        if compare is None:
            continue
        if compare.new_space_id != str(candidate.id):
            continue
        if compare.old_space_id != expected_baseline:
            continue
        if compare.set_version != golden.set_version or compare.k != golden.k:
            continue
        return job, compare, parse_persisted_bad_matches(job.result)
    return None


def persisted_compare_payload(    outcome: QualityCompareOutcome, *, new_space: VectorSpace
) -> dict[str, Any]:
    """The run-result block stored on a ``VECTOR_CUTOVER`` evaluation row."""
    return {
        "space_id": str(new_space.id),
        "quality": outcome.compare.to_dict(),
        "set_version": outcome.set_version,
        "k": outcome.k,
        "old_degraded": outcome.old_degraded,
        "new_degraded": outcome.new_degraded,
        "no_baseline": outcome.no_baseline,
        "bad_matches": list(outcome.bad_matches),
        "gate": outcome.gate.value,
    }


def parse_persisted_compare(payload: Any) -> QualityCompareDTO | None:
    """Rebuild the compare DTO from a stored run result (validated, no text)."""
    if not isinstance(payload, Mapping):
        return None
    raw = payload.get("quality")
    if not isinstance(raw, Mapping):
        response = payload.get("response")
        raw = response.get("quality") if isinstance(response, Mapping) else None
    if not isinstance(raw, Mapping):
        return None
    try:
        return QualityCompareDTO(**dict(raw))
    except (TypeError, ValueError):
        return None


def parse_persisted_bad_matches(payload: Any) -> list[dict[str, Any]]:
    """The stored bad-match detail, validated to be ids/scores only."""
    if not isinstance(payload, Mapping):
        return []
    raw = payload.get("bad_matches")
    if not isinstance(raw, list):
        response = payload.get("response")
        raw = response.get("bad_matches") if isinstance(response, Mapping) else None
    if not isinstance(raw, list):
        return []
    rows = [dict(item) for item in raw if isinstance(item, Mapping)]
    try:
        assert_no_raw_text(rows)
    except ValueError:
        return []
    return rows


__all__ = [
    "GOLDEN_QUERY_SET_PATH",
    "MAX_HITS",
    "OVERSAMPLE",
    "GoldenSetMissing",
    "QualityCompareOutcome",
    "QualitySetupBlocked",
    "compare_spaces",
    "golden_query_path",
    "golden_set_summary",
    "latest_persisted_compare",
    "load_golden_sets",
    "parse_persisted_bad_matches",
    "parse_persisted_compare",
    "persisted_compare_payload",
    "quality_from_compare",
    "select_golden_set",
]
