"""Family retrieval-operations contract wall (ADR-0051 / plan 51 Q3a).

Runs the canonical fixture table against the vendored contract copy in
``app/storage/retrieval_ops.py`` — the same walls as dev's
``scripts/check-retrieval-ops-contract.py``. The vendored pair is
byte-identical to the dev canonical; when the dev worktree is present next to
this checkout the test also asserts that identity, and skips it otherwise (CI
and public clones only carry the vendored copy).
"""

from __future__ import annotations

import ast
import json
import math
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from app.storage import retrieval_ops as ops

CONTRACT = Path(ops.__file__)
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "retrieval_ops.fixtures.json"

ALLOWED_IMPORTS = {
    "__future__",
    "collections",
    "dataclasses",
    "enum",
    "math",
    "typing",
}

GROUPS = (
    "vocabularies",
    "spaces",
    "coverage",
    "runResults",
    "runs",
    "runDetails",
    "failures",
    "queryHealth",
    "usage",
    "quality",
    "actions",
    "alerts",
    "dataSeams",
    "dtoSafety",
    "invalidArgs",
)

META = {"schema", "adr", "plan", "contract", "contractVersion", "description"}


def _fixtures() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def _close(actual: float | None, expected: float | None) -> bool:
    if actual is None or expected is None:
        return actual is expected
    return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12)


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _has_key(payload, names: set[str]) -> bool:
    if isinstance(payload, dict):
        return any(str(key) in names or _has_key(value, names) for key, value in payload.items())
    if isinstance(payload, (list, tuple)):
        return any(_has_key(item, names) for item in payload)
    return False


def _build(name: str, payload: dict):
    return getattr(ops, name)(**payload)


def test_fixture_meta_and_group_inventory():
    fixtures = _fixtures()
    assert fixtures["schema"] == 1
    assert "ADR-0051" in str(fixtures["adr"])
    assert fixtures["plan"] == 51
    assert fixtures["contract"] == "retrieval-ops"
    assert fixtures["contractVersion"] == ops.RETRIEVAL_CONTRACT_VERSION
    present = set(fixtures) - META
    assert present == set(GROUPS), (
        f"missing {sorted(set(GROUPS) - present)}, extra {sorted(present - set(GROUPS))}"
    )
    for group in GROUPS:
        assert fixtures[group], f"{group} is empty"


def test_vendored_contract_imports_stdlib_only():
    tree = ast.parse(CONTRACT.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    assert not found - ALLOWED_IMPORTS, f"non-stdlib imports: {sorted(found - ALLOWED_IMPORTS)}"


def test_closed_vocabularies_match_the_fixture():
    data = _fixtures()["vocabularies"]
    expected = {
        "spaceStatuses": [member.value for member in ops.SpaceStatus],
        "runStatuses": [member.value for member in ops.RunStatus],
        "activeRunStatuses": [member.value for member in ops.VECTOR_RUN_ACTIVE_STATUSES],
        "terminalRunStatuses": [member.value for member in ops.VECTOR_RUN_TERMINAL_STATUSES],
        "jobTypes": list(ops.VECTOR_JOB_TYPES),
        "auditGroup": ops.VECTOR_AUDIT_GROUP,
        "auditEvents": list(ops.VECTOR_AUDIT_EVENTS),
        "views": list(ops.V1_VIEWS),
        "backends": list(ops.BACKENDS),
        "degradedReasons": [member.value for member in ops.DegradedReason],
        "gateStatuses": [member.value for member in ops.GateStatus],
        "failureKinds": [member.value for member in ops.FailureKind],
        "maintenanceActions": [member.value for member in ops.MaintenanceAction],
        "actions": [member.value for member in ops.RetrievalAction],
    }
    assert set(data) == set(expected)
    for key, value in expected.items():
        assert data[key] == value, key


def test_space_fixtures_carry_cold_and_gate_state():
    for case in _fixtures()["spaces"]:
        dto = _build("SpaceDTO", case["dto"])
        expect = case["expect"]
        assert dto.cold is bool(expect["cold"]), case["name"]
        assert str(dto.coverage_gate) == expect["coverageGate"], case["name"]
        assert str(dto.status) == expect["status"], case["name"]
        if str(dto.status) == "retired":
            assert dto.retired_at, f"{case['name']}: a retired space carries retired_at"
        dto.to_dict()


def test_coverage_fixtures_never_invent_a_cold_number():
    for case in _fixtures()["coverage"]:
        dto = _build("CoverageDTO", case["dto"])
        expect = case["expect"]
        assert dto.cold is bool(expect["cold"]), case["name"]
        assert dto.sampled is bool(expect["sampled"]), case["name"]
        if "coverage" in expect:
            assert _close(dto.coverage, expect["coverage"]), case["name"]
        if dto.cold:
            assert dto.coverage is None, f"{case['name']}: cold must not invent coverage"
        dto.to_dict()


def test_run_result_contract_bounds_failed_ids():
    for case in _fixtures()["runResults"]:
        dto = _build("RunResultDTO", case["dto"])
        expect = case["expect"]
        assert len(dto.failed_ids) == expect["failedIdsCount"], case["name"]
        assert dto.failed_ids_truncated is bool(expect["truncated"]), case["name"]
        assert len(dto.failed_ids) <= ops.FAILED_IDS_LIMIT, case["name"]
        dto.to_dict()


def test_run_fixtures_and_lock_key_derivation():
    for case in _fixtures()["runs"]:
        dto = _build("RunDTO", case["dto"])
        expect = case["expect"]
        assert dto.active is bool(expect["active"]), case["name"]
        assert dto.terminal is bool(expect["terminal"]), case["name"]
        if dto.lock_key:
            assert dto.lock_key == ops.run_lock_key(dto.space_id), case["name"]
        dto.to_dict()


def test_run_detail_fixtures_compose_result_and_duration():
    runs = {case["dto"]["run_id"]: _build("RunDTO", case["dto"]) for case in _fixtures()["runs"]}
    for case in _fixtures()["runDetails"]:
        result = _build("RunResultDTO", case["result"]) if case.get("result") else None
        detail = ops.RunDetailDTO(
            run=runs[case["run"]], result=result, duration_seconds=case["durationSeconds"]
        )
        detail.to_dict()


def test_failure_group_fixtures():
    for case in _fixtures()["failures"]:
        dto = _build("FailureGroupDTO", case["dto"])
        assert dto.retryable is bool(case["expect"]["retryable"]), case["name"]
        assert dto.count >= 1, case["name"]
        dto.to_dict()


def test_query_health_fixtures():
    for case in _fixtures()["queryHealth"]:
        dto = _build("QueryHealthDTO", case["dto"])
        expect = case["expect"]
        assert dto.sampled is bool(expect["sampled"]), case["name"]
        assert _close(dto.degraded_rate, expect["degradedRate"]), case["name"]
        dto.to_dict()


def test_usage_fixtures_and_budget_math():
    for case in _fixtures()["usage"]:
        dto = _build("UsageDTO", case["dto"])
        expect = case["expect"]
        if dto.budget is not None:
            assert dto.budget.exhausted is bool(expect["exhausted"]), case["name"]
        assert sum(row.tokens_total for row in dto.rows) == expect["tokensTotal"], case["name"]
        dto.to_dict()


def test_quality_fixtures_score_golden_sets_without_query_text():
    data = _fixtures()["quality"]
    assert _close(data["floor"]["recall"], ops.QUALITY_FLOOR_RECALL)
    assert _close(data["floor"]["precision"], ops.QUALITY_FLOOR_PRECISION)
    assert data["floor"]["k"] == ops.QUALITY_K_DEFAULT

    golden = [ops.GoldenQueryFixture.from_fixture(row) for row in data["goldenQueries"]]
    runner = golden[0].to_runner_dict()
    assert runner["query"], "the admin fixture input is the one lawful query text"

    sets = [ops.GoldenQuerySet.from_fixture(row) for row in data["goldenSets"]]
    assert sets, "at least one versioned per-space set is required"
    for golden_set in sets:
        assert golden_set.revision_key == f"{golden_set.space_id}:v{golden_set.set_version}"
        assert all(query.k == golden_set.k for query in golden_set.queries)

    scored = ops.evaluate_quality_set(
        sets[0], data["cases"][0]["retrieved"], generated_at="2026-11-03T06:00:00Z"
    )
    assert scored.set_version == sets[0].set_version
    assert scored.space_id == sets[0].space_id

    for case in data["cases"]:
        dto = ops.evaluate_quality(
            case["spaceId"],
            case["setVersion"],
            golden,
            case["retrieved"],
            k=case["k"],
            generated_at="2026-11-03T06:00:00Z",
        )
        expect = case["expect"]
        assert dto.passed is bool(expect["passed"]), case["name"]
        assert _close(dto.recall_at_k, expect["recall"]), case["name"]
        assert _close(dto.precision_at_k, expect["precision"]), case["name"]
        payload = dto.to_dict()
        assert not _has_key(payload, {"query", "query_text", "document_text", "prompt"}), (
            f"{case['name']}: QualityDTO must not carry golden-query text"
        )

    for case in data["compare"]:
        dto = ops.evaluate_quality_compare(
            case["oldSpaceId"],
            case["newSpaceId"],
            case["setVersion"],
            golden,
            case["oldRetrieved"],
            case["newRetrieved"],
            k=case["k"],
            generated_at="2026-11-03T06:00:00Z",
        )
        expect = case["expect"]
        assert dto.passed is bool(expect["passed"]), case["name"]
        assert _close(dto.new_recall_at_k, expect["newRecall"]), case["name"]
        assert _close(dto.recall_delta, expect["recallDelta"]), case["name"]
        assert dto.required_for_activation is True, case["name"]
        dto.to_dict()


def test_action_fixtures_validate_idempotency_and_confirmation():
    for case in _fixtures()["actions"]:
        request = _build("RetrievalActionRequest", case["request"])
        response = _build("RetrievalActionResponse", case["response"])
        assert response.action == request.action, case["name"]
        if request.idempotency_key:
            assert response.idempotency_key == request.idempotency_key, case["name"]
        if request.action in (ops.RetrievalAction.DROP_SPACE, ops.RetrievalAction.RETIRE_SPACE):
            assert request.confirm_space_name == request.space_id, case["name"]
        request.to_dict()
        response.to_dict()


def test_alert_defaults_and_manage_urls():
    data = _fixtures()["alerts"]
    expected = [_plain(asdict(alert)) for alert in ops.ALERT_DEFAULTS]
    assert data == expected, "alert defaults drifted from the contract"
    for row in data:
        assert row["manage_url"].startswith("/settings/"), row["kind"]
        assert "redirect" not in row["manage_url"], row["kind"]
        assert row["daily_cap"] >= 1, row["kind"]


def test_data_seam_specs_match_the_fixture():
    data = _fixtures()["dataSeams"]
    assert _plain(asdict(ops.AI_GENERATIONS_METADATA)) == data["aiGenerations"]["metadata"]
    assert (
        _plain(asdict(ops.AI_GENERATIONS_METADATA_SCHEMA_VERSION))
        == data["aiGenerations"]["schemaVersion"]
    )
    assert _plain(asdict(ops.RETRIEVAL_QUERY_ROLLUPS)) == data["queryRollups"]
    assert _plain(asdict(ops.RETRIEVAL_COVERAGE_SNAPSHOTS)) == data["coverageSnapshots"]
    assert _plain(asdict(ops.BACKGROUND_JOB_SEAMS)) == data["backgroundJobs"]
    assert list(ops.DATA_SEAM_INVENTORY) == data["inventory"]
    assert data["quality"]["compareRequiredForActivation"] is True
    assert ops.RETRIEVAL_QUERY_ROLLUPS.ttl_days == 30
    assert ops.RETRIEVAL_COVERAGE_SNAPSHOTS.ttl_days == 90
    assert list(ops.RETRIEVAL_QUERY_ROLLUPS.latency_buckets_ms) == sorted(
        ops.RETRIEVAL_QUERY_ROLLUPS.latency_buckets_ms
    )
    assert ops.HEARTBEAT_STALE_SECONDS == ops.STALL_MINUTES * 60


def test_no_raw_text_rule():
    data = _fixtures()["dtoSafety"]
    for case in data["allowed"]:
        ops.assert_no_raw_text(case["payload"])
    for case in data["forbidden"]:
        with pytest.raises(ValueError):
            ops.assert_no_raw_text(case["payload"])

    allowed_space = ops.SpaceDTO(**data["allowed"][0]["payload"])
    allowed_space.to_dict()
    quality_payload = ops.QualityDTO(**data["allowed"][3]["payload"]).to_dict()
    assert not _has_key(quality_payload, {"query", "query_text", "document_text", "prompt"})


def test_helper_functions():
    assert ops.coverage_ratio(0, 0) is None, "zero total is cold, not 0%"
    assert _close(ops.coverage_ratio(1, 2), 0.5)
    ids, truncated = ops.truncate_failed_ids([f"doc-{index}" for index in range(600)])
    assert len(ids) == ops.FAILED_IDS_LIMIT
    assert truncated is True
    assert ops.run_lock_key("space-content") == "vector_space:space-content"
    assert ops.idempotency_scope("VECTOR_REINDEX", "req-abc12345") == (
        "VECTOR_REINDEX",
        "req-abc12345",
    )
    assert ops.validate_idempotency_key("req-abc12345") == "req-abc12345"


def test_invalid_arguments_raise_value_error():
    for row in _fixtures()["invalidArgs"]:
        call = row["call"]
        payload = dict(row["payload"])
        with pytest.raises(ValueError):
            if call == "idempotency_scope":
                ops.idempotency_scope(**payload)
            elif call == "truncate_failed_ids":
                ops.truncate_failed_ids(**payload)
            else:
                _build(call, payload)


def _dev_canonical() -> Path | None:
    override = os.environ.get("STUDY_RETRIEVAL_OPS_CANONICAL")
    candidates = ([Path(override)] if override else []) + [
        Path(__file__).resolve().parents[3] / "dev-vector-p0" / "contracts",
        Path(__file__).resolve().parents[3] / "dev" / "contracts",
    ]
    return next((path for path in candidates if (path / "retrieval_ops.py").is_file()), None)


def test_vendored_files_are_byte_identical_to_the_dev_canonical():
    canonical = _dev_canonical()
    if canonical is None:
        pytest.skip("dev canonical not present (CI/public clone) — vendored copy only")
    assert CONTRACT.read_bytes() == (canonical / "retrieval_ops.py").read_bytes()
    assert FIXTURES.read_bytes() == (canonical / "retrieval-ops.fixtures.json").read_bytes()
