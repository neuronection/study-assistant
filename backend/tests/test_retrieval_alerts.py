"""Plan 51 Q3c3a: the ten bounded retrieval alerts through the one funnel."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.vocab import NotificationKind
from app.domain.models import (
    AiModel,
    Job,
    Notification,
    Provider,
    RetrievalCoverageSnapshot,
    RetrievalQueryRollup,
    TaskAssignment,
    User,
    VectorSpace,
)
from app.jobs.payloads import JobResult
from app.services.platform.notifications import admin_recipients
from app.services.retrieval import alerts, reads
from app.services.retrieval.legacy import LEGACY_KIND, LEGACY_SPACE_ID
from app.services.retrieval.telemetry import _histogram_for
from app.storage import retrieval_ops as ops

FORBIDDEN_KEYS = {
    "prompt",
    "query",
    "query_text",
    "document_text",
    "content",
    "body",
    "text",
    "output",
}


def _admin(session: Session, email: str = "alerts-admin@test.local") -> User:
    row = session.scalars(select(User).where(User.email == email)).first()
    if row is not None:
        return row
    row = User(email=email, password_hash=None, is_admin=True, is_active=True)
    session.add(row)
    session.commit()
    return row


def _space(
    session: Session,
    space_id: str = "space-a",
    *,
    name: str = "content-a",
    status: str = "active",
    retired_at: datetime | None = None,
    index_table: str | None = None,
) -> VectorSpace:
    row = VectorSpace(
        id=space_id,
        name=name,
        provider="p",
        model="m",
        dim=4,
        index_table=index_table,
        status=status,
        retired_at=retired_at,
    )
    session.add(row)
    session.commit()
    return row


def _snapshot(
    session: Session,
    space_id: str,
    *,
    embedded: int,
    total: int = 100,
    as_of: datetime | None = None,
) -> RetrievalCoverageSnapshot:
    moment = as_of or datetime.now(UTC)
    row = RetrievalCoverageSnapshot(
        space_id=space_id,
        kind=LEGACY_KIND,
        as_of=moment,
        total=total,
        embedded=embedded,
        missing=max(total - embedded, 0),
    )
    session.add(row)
    session.commit()
    return row


def _evaluate(session: Session, now: datetime | None = None) -> dict[str, Any]:
    return alerts.evaluate_retrieval_alerts(session, now=now)


def _rows(session: Session, kind: str) -> list[Notification]:
    session.expire_all()
    return list(
        session.scalars(
            select(Notification)
            .where(Notification.kind == kind)
            .order_by(Notification.created_at, Notification.id)
        )
    )


def _assert_no_raw_text(payload: dict[str, Any]) -> None:
    assert not (set(payload) & FORBIDDEN_KEYS)
    assert "SECRET" not in json.dumps(payload)


def test_coverage_low_emits_dedups_recovers_and_fans_out_to_admins(
    db_session: Session,
) -> None:
    admin = _admin(db_session)
    _admin(db_session, "second-admin@test.local")
    db_session.add(User(email="student@test.local", password_hash=None, is_active=True))
    db_session.commit()
    _space(db_session, LEGACY_SPACE_ID, name="content")
    now = datetime.now(UTC)
    _snapshot(db_session, LEGACY_SPACE_ID, embedded=90, as_of=now - timedelta(minutes=5))

    summary = _evaluate(db_session, now)
    assert summary["kinds"][NotificationKind.RETRIEVAL_COVERAGE_LOW.value]["emitted"] == 1
    row = _rows(db_session, NotificationKind.RETRIEVAL_COVERAGE_LOW.value)[-1]
    assert row.dedup_key is not None
    assert set(row.recipients) == set(admin_recipients(db_session))
    assert str(admin.id) in row.recipients
    assert "student@test.local" not in row.recipients
    assert row.payload["link"] == "/settings?tab=tools&section=indexing"
    _assert_no_raw_text(dict(row.payload))

    # Same condition: dedup suppresses a second event.
    assert (
        _evaluate(db_session, now + timedelta(minutes=1))["kinds"][
            NotificationKind.RETRIEVAL_COVERAGE_LOW.value
        ]["emitted"]
        == 0
    )
    assert len(_rows(db_session, NotificationKind.RETRIEVAL_COVERAGE_LOW.value)) == 1

    # Recovery releases the key; a later recurrence is a new alert.
    _snapshot(
        db_session,
        LEGACY_SPACE_ID,
        embedded=100,
        as_of=now + timedelta(minutes=2),
    )
    recovered = _evaluate(db_session, now + timedelta(minutes=3))
    assert recovered["kinds"][NotificationKind.RETRIEVAL_COVERAGE_LOW.value]["released"] == 1
    assert _rows(db_session, NotificationKind.RETRIEVAL_COVERAGE_LOW.value)[-1].dedup_key is None

    _snapshot(
        db_session,
        LEGACY_SPACE_ID,
        embedded=80,
        as_of=now + timedelta(minutes=4),
    )
    assert (
        _evaluate(db_session, now + timedelta(minutes=5))["kinds"][
            NotificationKind.RETRIEVAL_COVERAGE_LOW.value
        ]["emitted"]
        == 1
    )


def test_reindex_failed_recovers_on_next_success(db_session: Session) -> None:
    _admin(db_session)
    _space(db_session, LEGACY_SPACE_ID, name="content")
    now = datetime.now(UTC)
    failed = Job(
        type="VECTOR_REINDEX",
        payload={"space_id": LEGACY_SPACE_ID, "kind": "material"},
        status="failed",
        result={"scanned": 4, "embedded": 2, "failed": 2},
        created_at=now - timedelta(minutes=10),
    )
    db_session.add(failed)
    db_session.commit()

    summary = _evaluate(db_session, now)
    assert summary["kinds"][NotificationKind.RETRIEVAL_REINDEX_FAILED.value]["emitted"] == 1
    row = _rows(db_session, NotificationKind.RETRIEVAL_REINDEX_FAILED.value)[-1]
    assert row.payload["run_id"] == failed.id
    assert row.payload["link"].startswith("/settings?tab=tools&section=indexing")
    assert f"detail={failed.id}" in row.payload["link"]
    _assert_no_raw_text(dict(row.payload))

    done = Job(
        type="VECTOR_REINDEX",
        payload={"space_id": LEGACY_SPACE_ID, "kind": "material"},
        status="done",
        result={"scanned": 4, "embedded": 4, "failed": 0},
        created_at=now - timedelta(minutes=1),
    )
    db_session.add(done)
    db_session.commit()
    recovered = _evaluate(db_session, now + timedelta(minutes=1))
    assert recovered["kinds"][NotificationKind.RETRIEVAL_REINDEX_FAILED.value]["released"] == 1
    assert _rows(db_session, NotificationKind.RETRIEVAL_REINDEX_FAILED.value)[-1].dedup_key is None


def test_reindex_stalled_recovers_when_progress_resumes(db_session: Session) -> None:
    _admin(db_session)
    _space(db_session, LEGACY_SPACE_ID, name="content")
    now = datetime.now(UTC)
    running = Job(
        type="VECTOR_REINDEX",
        payload={"space_id": LEGACY_SPACE_ID, "kind": "material"},
        status="running",
        progress=40,
        stage="embedding",
        heartbeat_at=now - timedelta(minutes=20),
        created_at=now - timedelta(minutes=30),
    )
    db_session.add(running)
    db_session.commit()

    summary = _evaluate(db_session, now)
    assert summary["kinds"][NotificationKind.RETRIEVAL_REINDEX_STALLED.value]["emitted"] == 1
    row = _rows(db_session, NotificationKind.RETRIEVAL_REINDEX_STALLED.value)[-1]
    assert row.payload["run_id"] == running.id
    assert row.payload["stale_minutes"] == 15
    _assert_no_raw_text(dict(row.payload))

    running.heartbeat_at = now + timedelta(minutes=1)
    db_session.commit()
    recovered = _evaluate(db_session, now + timedelta(minutes=2))
    assert recovered["kinds"][NotificationKind.RETRIEVAL_REINDEX_STALLED.value]["released"] == 1


def test_quality_gate_emits_on_below_floor_and_recovers_on_pass(db_session: Session) -> None:
    _admin(db_session)
    space = _space(db_session, LEGACY_SPACE_ID, name="content")
    now = datetime.now(UTC)

    def _compare(passed: bool) -> dict[str, Any]:
        return ops.QualityCompareDTO(
            old_space_id=LEGACY_SPACE_ID,
            new_space_id=str(space.id),
            set_version=1,
            k=5,
            old_recall_at_k=1.0,
            old_precision_at_k=1.0,
            new_recall_at_k=0.4 if not passed else 0.9,
            new_precision_at_k=0.4 if not passed else 0.6,
            passed=passed,
        ).to_dict()

    job = Job(
        type="VECTOR_CUTOVER",
        payload={"action": "quality_compare", "space_id": str(space.id)},
        status="done",
        result={"quality": _compare(False), "bad_matches": []},
        created_at=now - timedelta(minutes=5),
    )
    db_session.add(job)
    db_session.commit()

    summary = _evaluate(db_session, now)
    assert summary["kinds"][NotificationKind.RETRIEVAL_QUALITY_GATE.value]["emitted"] == 1
    row = _rows(db_session, NotificationKind.RETRIEVAL_QUALITY_GATE.value)[-1]
    assert row.payload["recall_at_k"] == 0.4
    assert row.payload["link"] == "/settings?tab=tools&section=indexing"
    _assert_no_raw_text(dict(row.payload))
    assert "SECRET-GOLDEN" not in json.dumps(dict(row.payload))

    job.result = cast(JobResult, {"quality": _compare(True), "bad_matches": []})
    db_session.commit()
    recovered = _evaluate(db_session, now + timedelta(minutes=1))
    assert recovered["kinds"][NotificationKind.RETRIEVAL_QUALITY_GATE.value]["released"] == 1
    assert _rows(db_session, NotificationKind.RETRIEVAL_QUALITY_GATE.value)[-1].dedup_key is None


def test_query_slo_emits_and_recovers_below_budget(db_session: Session) -> None:
    _admin(db_session)
    _space(db_session, LEGACY_SPACE_ID, name="content")
    now = datetime.now(UTC)
    row = RetrievalQueryRollup(
        space_id=LEGACY_SPACE_ID,
        kind=LEGACY_KIND,
        bucket_start=now - timedelta(minutes=2),
        bucket_width=300,
        count=4,
        zero_results=0,
        candidates_sum=10,
        latency_histogram=_histogram_for(2000),
    )
    db_session.add(row)
    db_session.commit()

    summary = _evaluate(db_session, now)
    assert summary["kinds"][NotificationKind.RETRIEVAL_QUERY_SLO.value]["emitted"] == 1
    event = _rows(db_session, NotificationKind.RETRIEVAL_QUERY_SLO.value)[-1]
    assert event.payload["p95_ms"] > 1500
    _assert_no_raw_text(dict(event.payload))

    db_session.execute(
        update(RetrievalQueryRollup)
        .where(RetrievalQueryRollup.id == row.id)
        .values(latency_histogram=_histogram_for(100))
    )
    db_session.commit()
    db_session.expire_all()
    recovered = _evaluate(db_session, now + timedelta(minutes=1))
    assert recovered["kinds"][NotificationKind.RETRIEVAL_QUERY_SLO.value]["released"] == 1


def test_degraded_rate_emits_per_reason_and_recovers(db_session: Session) -> None:
    _admin(db_session)
    _space(db_session, LEGACY_SPACE_ID, name="content")
    now = datetime.now(UTC)
    degraded = RetrievalQueryRollup(
        space_id=LEGACY_SPACE_ID,
        kind=LEGACY_KIND,
        degraded_reason="provider_unassigned",
        bucket_start=now - timedelta(minutes=2),
        bucket_width=300,
        count=1,
        zero_results=0,
        candidates_sum=0,
        latency_histogram=_histogram_for(100),
    )
    normal = RetrievalQueryRollup(
        space_id=LEGACY_SPACE_ID,
        kind=LEGACY_KIND,
        bucket_start=now - timedelta(minutes=2),
        bucket_width=300,
        count=9,
        zero_results=0,
        candidates_sum=20,
        latency_histogram=_histogram_for(100),
    )
    db_session.add_all([degraded, normal])
    db_session.commit()

    summary = _evaluate(db_session, now)
    assert summary["kinds"][NotificationKind.RETRIEVAL_DEGRADED_RATE.value]["emitted"] == 1
    event = _rows(db_session, NotificationKind.RETRIEVAL_DEGRADED_RATE.value)[-1]
    assert event.payload["reason"] == "provider_unassigned"
    assert event.payload["rate"] == 0.1
    _assert_no_raw_text(dict(event.payload))

    db_session.delete(degraded)
    db_session.commit()
    recovered = _evaluate(db_session, now + timedelta(minutes=1))
    assert recovered["kinds"][NotificationKind.RETRIEVAL_DEGRADED_RATE.value]["released"] == 1


def test_provider_unassigned_is_singleton_and_hits_the_daily_cap(db_session: Session) -> None:
    _admin(db_session)
    now = datetime.now(UTC)
    summary = _evaluate(db_session, now)
    assert summary["kinds"][NotificationKind.RETRIEVAL_PROVIDER_UNASSIGNED.value]["emitted"] == 1
    event = _rows(db_session, NotificationKind.RETRIEVAL_PROVIDER_UNASSIGNED.value)[-1]
    assert event.dedup_key == "retrieval.provider_unassigned:singleton"
    assert event.payload["link"] == "/settings?tab=ai&section=tasks"
    _assert_no_raw_text(dict(event.payload))

    provider = Provider(
        name="p", type="openai_compatible", base_url="http://x/v1", keyring_ref="provider:1"
    )
    db_session.add(provider)
    db_session.flush()
    model = AiModel(
        provider_id=provider.id,
        external_id="embed",
        label="embed",
        caps=["embeddings"],
        enabled=True,
    )
    db_session.add(model)
    db_session.flush()
    assignment = TaskAssignment(task="embeddings", model_id=model.id)
    db_session.add(assignment)
    db_session.commit()
    recovered = _evaluate(db_session, now + timedelta(minutes=1))
    assert recovered["kinds"][NotificationKind.RETRIEVAL_PROVIDER_UNASSIGNED.value]["released"] == 1

    db_session.delete(assignment)
    db_session.commit()
    capped = _evaluate(db_session, now + timedelta(minutes=2))
    assert capped["kinds"][NotificationKind.RETRIEVAL_PROVIDER_UNASSIGNED.value]["active"] == 1
    assert capped["kinds"][NotificationKind.RETRIEVAL_PROVIDER_UNASSIGNED.value]["emitted"] == 0
    assert len(_rows(db_session, NotificationKind.RETRIEVAL_PROVIDER_UNASSIGNED.value)) == 1


def test_index_missing_is_pg_only_and_recovers_on_provision(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _admin(db_session)
    _space(db_session, "space-pg", name="content", index_table="vec_abcdef12")
    now = datetime.now(UTC)

    monkeypatch.setattr(alerts, "_is_postgres", lambda _session: True)
    monkeypatch.setattr(alerts, "pg_index_state", lambda _session, _table: (False, False))
    summary = _evaluate(db_session, now)
    assert summary["kinds"][NotificationKind.RETRIEVAL_INDEX_MISSING.value]["emitted"] == 1
    event = _rows(db_session, NotificationKind.RETRIEVAL_INDEX_MISSING.value)[-1]
    assert event.payload["index_table"] == "vec_abcdef12"
    assert event.payload["extension_present"] is False
    _assert_no_raw_text(dict(event.payload))

    monkeypatch.setattr(alerts, "pg_index_state", lambda _session, _table: (True, True))
    recovered = _evaluate(db_session, now + timedelta(minutes=1))
    assert recovered["kinds"][NotificationKind.RETRIEVAL_INDEX_MISSING.value]["released"] == 1


def test_budget_exhausted_reports_the_honest_gap(db_session: Session) -> None:
    _admin(db_session)
    summary = _evaluate(db_session)
    entry = summary["kinds"][NotificationKind.RETRIEVAL_BUDGET_EXHAUSTED.value]
    assert entry["state"] == "unavailable"
    assert entry["reason"] == "no_token_budget"
    assert _rows(db_session, NotificationKind.RETRIEVAL_BUDGET_EXHAUSTED.value) == []


def test_space_drop_pending_past_grace_and_recovers_on_drop(db_session: Session) -> None:
    _admin(db_session)
    now = datetime.now(UTC)
    space = _space(
        db_session,
        "space-retired",
        name="old-content",
        status="retired",
        retired_at=now - timedelta(days=8),
    )
    summary = _evaluate(db_session, now)
    assert summary["kinds"][NotificationKind.RETRIEVAL_SPACE_DROP_PENDING.value]["emitted"] == 1
    event = _rows(db_session, NotificationKind.RETRIEVAL_SPACE_DROP_PENDING.value)[-1]
    assert event.payload["space_id"] == space.id
    assert event.payload["days_retired"] >= 7
    _assert_no_raw_text(dict(event.payload))

    db_session.delete(space)
    db_session.commit()
    recovered = _evaluate(db_session, now + timedelta(minutes=1))
    assert recovered["kinds"][NotificationKind.RETRIEVAL_SPACE_DROP_PENDING.value]["released"] == 1


def test_empty_and_cold_instances_emit_nothing(db_session: Session) -> None:
    _admin(db_session)
    summary = _evaluate(db_session)
    assert summary["state"] == "ok"
    for kind, result in summary["kinds"].items():
        expected = 1 if kind == NotificationKind.RETRIEVAL_PROVIDER_UNASSIGNED.value else 0
        assert result["active"] == expected
        assert result["emitted"] == expected
    for kind in summary["kinds"]:
        if kind == NotificationKind.RETRIEVAL_PROVIDER_UNASSIGNED.value:
            continue
        assert _rows(db_session, kind) == []


def test_usage_exposes_day_space_kind_without_prompt_or_fabricated_errors(
    db_session: Session,
) -> None:
    _admin(db_session)
    now = datetime.now(UTC)
    from app.domain.models import AiInteraction

    db_session.add_all(
        [
            AiInteraction(
                context_type="gateway",
                task="embeddings",
                model="embed",
                input_tokens=10,
                output_tokens=0,
                metadata_json={
                    "space_id": LEGACY_SPACE_ID,
                    "kind": "material",
                    "view": "body",
                    "chunk_index": 0,
                },
                created_at=now,
            ),
            AiInteraction(
                context_type="gateway",
                task="embeddings",
                model="embed",
                input_tokens=None,
                output_tokens=None,
                metadata_json={"space_id": LEGACY_SPACE_ID, "kind": "query"},
                created_at=now,
            ),
        ]
    )
    db_session.commit()

    payload = reads.usage(db_session, window="24h")
    assert payload["errors_available"] is False
    assert payload["tokens_available"] is True
    assert payload["budget"] is None
    keys = {(row["space_id"], row["kind"]) for row in payload["rows"]}
    assert (LEGACY_SPACE_ID, "material") in keys
    assert (LEGACY_SPACE_ID, "query") in keys
    dumped = json.dumps(payload)
    assert "prompt" not in dumped
    assert "input text" not in dumped
    assert any("token-denominated" in note for note in payload["notes"])
