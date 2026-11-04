"""Study/career read-DTO vocabulary parity (plan 51 Q3b).

Both products consume the same family contract fixtures, so a study read
payload is conformant when every status/cold/degraded token it emits is one
the shared fixture table declares. This is the fixture-level parity wall —
not the full family runner (that is Q3c/Q5 work).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from app.domain.models import Job, RetrievalQueryRollup
from app.services.retrieval import reads
from app.services.retrieval.legacy import LEGACY_KIND, LEGACY_SPACE_ID, write_coverage_snapshot

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "retrieval_ops.fixtures.json"


def _fixtures() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(FIXTURES.read_text(encoding="utf-8")))


def test_run_status_vocabulary_matches_the_shared_fixture(db_session: Session) -> None:
    fixture = _fixtures()["vocabularies"]
    db_statuses = ["queued", "running", "done", "failed", "cancelled"]
    for status in db_statuses:
        db_session.add(
            Job(
                type="VECTOR_REINDEX",
                payload={"space_id": LEGACY_SPACE_ID},
                status=status,
                progress=0,
            )
        )
    db_session.commit()

    runs = reads.list_runs(db_session, limit=20)
    emitted = {row["run"]["status"] for row in runs}
    assert emitted == set(fixture["runStatuses"])
    assert emitted <= set(fixture["runStatuses"])
    for row in runs:
        assert row["run"]["job_type"] in fixture["jobTypes"]
        assert row["run"]["space_id"] == LEGACY_SPACE_ID


def test_cold_and_gate_vocabulary_matches_the_shared_fixture(db_session: Session) -> None:
    fixture = _fixtures()
    cold_case = next(case for case in fixture["coverage"] if case["expect"]["cold"])
    envelope = reads.coverage(db_session)
    dto = envelope["coverage"]

    assert envelope["cold"] is True
    assert dto["as_of"] is None
    assert dto["coverage"] is None
    assert dto["gate"] == cold_case["dto"]["gate"]
    assert dto["gate"] in fixture["vocabularies"]["gateStatuses"]
    assert dto["space_id"] == LEGACY_SPACE_ID


def test_degraded_reasons_and_gate_tokens_use_the_shared_vocabulary(
    db_session: Session,
) -> None:
    fixture = _fixtures()
    write_coverage_snapshot(
        db_session,
        total=1000,
        embedded=760,
        missing=240,
        failed=10,
    )
    db_session.add(
        RetrievalQueryRollup(
            space_id=LEGACY_SPACE_ID,
            kind=LEGACY_KIND,
            degraded_reason="provider_unassigned",
            bucket_start=datetime.now(UTC),
            bucket_width=300,
            count=3,
            zero_results=1,
            candidates_sum=0,
            latency_histogram=None,
        )
    )
    db_session.commit()

    coverage = reads.coverage(db_session)["coverage"]
    assert coverage["gate"] == "fail"
    assert coverage["gate"] in fixture["vocabularies"]["gateStatuses"]
    assert coverage["coverage"] == 0.76

    health = reads.query_health(db_session)["health"]
    reasons = set(health["degraded_reasons"])
    assert reasons == {"provider_unassigned"}
    assert reasons <= set(fixture["vocabularies"]["degradedReasons"])
