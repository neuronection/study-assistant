"""Cross-repo family parity runner for the retrieval-operations contract.

Plan 51 Q3c2b2. Career is the reference adopter (Q1/Q2); study is the second
adopter (Q3). This runner proves both repos consume the same contract wall —
the closed status/cold/degraded/gate/quality/run vocabulary, the quality
fixture cases and the DTO shape — by comparing the vendored copies and running
the shared fixture through the vendored scorer. It also records the sha and
sync-gate status.

``strict=True`` is reserved for the full family gate: every check passes **and**
the canonical settings map/ledger record study as adopted. Until that happens
the runner reports ``strict=False`` with the exact blockers; it never claims a
strict pass the family ledger has not recorded.

Development-only: it reads sibling checkouts and is never imported by the app
runtime. Missing sibling repos are a recorded ``skip``, not a failure.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...storage import retrieval_ops as ops

CONTRACT_RELATIVE = Path("backend/app/storage/retrieval_ops.py")
FIXTURE_RELATIVE = Path("backend/tests/fixtures/retrieval_ops.fixtures.json")

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ParityCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class ParityReport:
    study_repo: str
    career_repo: str | None
    dev_repo: str | None
    checks: tuple[ParityCheck, ...]
    shas: dict[str, str]
    strict: bool
    strict_blockers: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return all(check.status != "fail" for check in self.checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "study_repo": self.study_repo,
            "career_repo": self.career_repo,
            "dev_repo": self.dev_repo,
            "ok": self.ok,
            "strict": self.strict,
            "strict_blockers": list(self.strict_blockers),
            "shas": dict(self.shas),
            "checks": [
                {"name": check.name, "status": check.status, "detail": check.detail}
                for check in self.checks
            ],
        }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(name: str, condition: bool, detail: str) -> ParityCheck:
    return ParityCheck(name=name, status="pass" if condition else "fail", detail=detail)


def _skip(name: str, detail: str) -> ParityCheck:
    return ParityCheck(name=name, status="skip", detail=detail)


def _env_path(name: str, default: Path) -> Path | None:
    override = os.environ.get(name)
    if override:
        return Path(override)
    return default if default.exists() else None


def _repo_paths() -> tuple[Path | None, Path | None]:
    career = _env_path("STUDY_RETRIEVAL_CAREER_REPO", REPO_ROOT.parent / "career-assistant")
    dev = _env_path("STUDY_RETRIEVAL_DEV_ROOT", REPO_ROOT.parent / "dev-vector-p0") or _env_path(
        "STUDY_RETRIEVAL_DEV_ROOT", REPO_ROOT.parent / "dev"
    )
    return career, dev


def _fixture(study_repo: Path) -> dict[str, Any]:
    path = study_repo / FIXTURE_RELATIVE
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _vocab_check(fixture: Mapping[str, Any]) -> ParityCheck:
    vocab = fixture["vocabularies"]
    mismatches: list[str] = []
    groups: tuple[tuple[str, Sequence[str], Sequence[str]], ...] = (
        (
            "spaceStatuses",
            tuple(member.value for member in ops.SpaceStatus),
            vocab["spaceStatuses"],
        ),
        ("runStatuses", tuple(member.value for member in ops.RunStatus), vocab["runStatuses"]),
        ("gateStatuses", tuple(member.value for member in ops.GateStatus), vocab["gateStatuses"]),
        (
            "degradedReasons",
            tuple(member.value for member in ops.DegradedReason),
            vocab["degradedReasons"],
        ),
        ("failureKinds", tuple(member.value for member in ops.FailureKind), vocab["failureKinds"]),
        (
            "maintenanceActions",
            tuple(member.value for member in ops.MaintenanceAction),
            vocab["maintenanceActions"],
        ),
        (
            "actions",
            tuple(member.value for member in ops.RetrievalAction),
            vocab["actions"],
        ),
        ("jobTypes", ops.VECTOR_JOB_TYPES, vocab["jobTypes"]),
        ("auditEvents", ops.VECTOR_AUDIT_EVENTS, vocab["auditEvents"]),
        ("backends", ops.BACKENDS, vocab["backends"]),
    )
    for name, study_values, fixture_values in groups:
        if list(study_values) != list(fixture_values):
            mismatches.append(name)
    return _check(
        "contract-vocabulary",
        not mismatches,
        "study enums match the shared fixture"
        if not mismatches
        else f"mismatched groups: {mismatches}",
    )


def _quality_floor_check(fixture: Mapping[str, Any]) -> ParityCheck:
    floor = fixture["quality"]["floor"]
    actual = {
        "recall": ops.QUALITY_FLOOR_RECALL,
        "precision": ops.QUALITY_FLOOR_PRECISION,
        "k": ops.QUALITY_K_DEFAULT,
    }
    expected = {"recall": floor["recall"], "precision": floor["precision"], "k": floor["k"]}
    return _check(
        "quality-floor",
        actual == expected,
        f"recall/precision/k={actual}",
    )


def _quality_case_check(fixture: Mapping[str, Any]) -> ParityCheck:
    quality = fixture["quality"]
    sets = {row["spaceId"]: ops.GoldenQuerySet.from_fixture(row) for row in quality["goldenSets"]}
    failures: list[str] = []
    for case in quality["cases"]:
        golden = sets[case["spaceId"]]
        scored = ops.evaluate_quality_set(
            golden, case["retrieved"], generated_at="2026-11-04T00:00:00Z"
        )
        expect = case["expect"]
        if scored.passed is not expect["passed"]:
            failures.append(f"{case['name']}: passed={scored.passed}")
        if abs(scored.recall_at_k - expect["recall"]) > 1e-9:
            failures.append(f"{case['name']}: recall={scored.recall_at_k}")
        if abs(scored.precision_at_k - expect["precision"]) > 1e-9:
            failures.append(f"{case['name']}: precision={scored.precision_at_k}")
    for case in quality["compare"]:
        golden = sets[case["newSpaceId"]]
        compare = ops.evaluate_quality_compare(
            case["oldSpaceId"],
            case["newSpaceId"],
            case["setVersion"],
            golden.queries,
            case["oldRetrieved"],
            case["newRetrieved"],
            k=case["k"],
            generated_at="2026-11-04T00:00:00Z",
        )
        expect = case["expect"]
        if compare.passed is not expect["passed"]:
            failures.append(f"{case['name']}: passed={compare.passed}")
        if abs(compare.new_recall_at_k - expect["newRecall"]) > 1e-9:
            failures.append(f"{case['name']}: new recall={compare.new_recall_at_k}")
        if abs(compare.recall_delta - expect["recallDelta"]) > 1e-9:
            failures.append(f"{case['name']}: delta={compare.recall_delta}")
    return _check(
        "quality-fixture-cases",
        not failures,
        "every golden/compare case scores as the shared fixture declares"
        if not failures
        else "; ".join(failures),
    )


def _dto_shape_check(fixture: Mapping[str, Any]) -> ParityCheck:
    quality_fields = set(ops.QualityDTO.__dataclass_fields__)
    compare_fields = set(ops.QualityCompareDTO.__dataclass_fields__)
    gate_fields = set(ops.ActivationGateDTO.__dataclass_fields__)
    expected_quality = {"space_id", "set_version", "k", "recall_at_k", "precision_at_k", "passed"}
    expected_compare = {
        "old_space_id",
        "new_space_id",
        "set_version",
        "k",
        "old_recall_at_k",
        "old_precision_at_k",
        "new_recall_at_k",
        "new_precision_at_k",
        "passed",
        "required_for_activation",
    }
    expected_gate = {"space_id", "coverage", "quality", "allowed", "reasons"}
    allowed = fixture["dtoSafety"]["allowed"]
    quality_payload = next(row for row in allowed if row["name"] == "quality-result")
    rebuilt = ops.QualityDTO(**quality_payload["payload"])
    no_text = not any(
        key in {str(item).lower() for item in rebuilt.to_dict()}
        for key in ("query", "prompt", "document_text")
    )
    ok = (
        expected_quality <= quality_fields
        and expected_compare <= compare_fields
        and expected_gate <= gate_fields
        and rebuilt.passed is True
        and no_text
        and fixture["dataSeams"]["quality"]["compareRequiredForActivation"] is True
    )
    return _check(
        "dto-shape",
        ok,
        "QualityDTO/QualityCompareDTO/ActivationGateDTO shapes match the fixture wall",
    )


def _vendored_copy_checks(
    study_repo: Path, career_repo: Path | None, dev_repo: Path | None
) -> tuple[list[ParityCheck], dict[str, str]]:
    checks: list[ParityCheck] = []
    shas: dict[str, str] = {}
    study_contract = study_repo / CONTRACT_RELATIVE
    study_fixture = study_repo / FIXTURE_RELATIVE
    shas["study:contract"] = _sha(study_contract)
    shas["study:fixtures"] = _sha(study_fixture)

    if career_repo is None:
        checks.append(_skip("career-copy", "career checkout not present"))
    else:
        career_contract = career_repo / CONTRACT_RELATIVE
        career_fixture = career_repo / FIXTURE_RELATIVE
        checks.append(
            _check(
                "career-contract-byte-identity",
                study_contract.read_bytes() == career_contract.read_bytes(),
                "study retrieval_ops.py is byte-identical to career's copy",
            )
        )
        checks.append(
            _check(
                "career-fixture-byte-identity",
                study_fixture.read_bytes() == career_fixture.read_bytes(),
                "study fixture wall is byte-identical to career's copy",
            )
        )
        shas["career:contract"] = _sha(career_contract)
        shas["career:fixtures"] = _sha(career_fixture)

    if dev_repo is None:
        checks.append(_skip("dev-canonical", "dev canonical checkout not present"))
        return checks, shas
    canonical_contract = dev_repo / "contracts" / "retrieval_ops.py"
    canonical_fixture = dev_repo / "contracts" / "retrieval-ops.fixtures.json"
    if not canonical_contract.is_file() or not canonical_fixture.is_file():
        checks.append(_skip("dev-canonical", "canonical contract files not found"))
        return checks, shas
    checks.append(
        _check(
            "dev-canonical-contract-byte-identity",
            study_contract.read_bytes() == canonical_contract.read_bytes(),
            "study retrieval_ops.py is byte-identical to the dev canonical",
        )
    )
    checks.append(
        _check(
            "dev-canonical-fixture-byte-identity",
            study_fixture.read_bytes() == canonical_fixture.read_bytes(),
            "study fixture wall is byte-identical to the dev canonical",
        )
    )
    shas["dev:contract"] = _sha(canonical_contract)
    shas["dev:fixtures"] = _sha(canonical_fixture)
    return checks, shas


def _sync_gate(
    study_repo: Path, dev_repo: Path | None
) -> tuple[list[ParityCheck], list[str], dict[str, str]]:
    checks: list[ParityCheck] = []
    blockers: list[str] = []
    shas: dict[str, str] = {}
    if dev_repo is None:
        checks.append(_skip("sync-gate", "dev canonical/ledger not present"))
        blockers.append("dev-canonical-missing")
        return checks, blockers, shas

    ledger = dev_repo / "contracts" / "retrieval-ops.sync.json"
    study_contract_sha = _sha(study_repo / CONTRACT_RELATIVE)
    adopted = False
    if ledger.is_file():
        entries = {
            line.split(":", 2)[0] + ":" + line.split(":", 2)[1]: line.rsplit(":", 1)[-1].strip()
            for line in ledger.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#") and line.count(":") >= 2
        }
        key = "study-assistant:backend/app/storage/retrieval_ops.py"
        recorded = entries.get(key)
        shas["ledger:study-assistant"] = recorded or ""
        adopted = recorded == study_contract_sha
        checks.append(
            _check(
                "sync-ledger",
                adopted,
                "study is recorded as synced in the family ledger",
            )
            if adopted
            else _skip(
                "sync-ledger",
                "study is not recorded in contracts/retrieval-ops.sync.json (pending)",
            )
        )
        if not adopted:
            blockers.append("sync-ledger:study-assistant")
    else:
        checks.append(_skip("sync-ledger", "contracts/retrieval-ops.sync.json not found"))
        blockers.append("sync-ledger:missing")

    settings_map = dev_repo / "contracts" / "settings-map.json"
    canonical_aligned = False
    if settings_map.is_file():
        document = json.loads(settings_map.read_text(encoding="utf-8"))
        domains = document.get("domains", [])
        retrieval = next(
            (
                row
                for row in domains
                if isinstance(row, Mapping) and row.get("id") == "tools.retrieval"
            ),
            None,
        )
        adopter = str((retrieval or {}).get("adopters", {}).get("study-assistant", ""))
        canonical_aligned = adopter == "aligned"
        checks.append(
            _check(
                "settings-map-adopter",
                canonical_aligned,
                f"canonical tools.retrieval study adopter = {adopter!r}",
            )
            if canonical_aligned
            else _skip(
                "settings-map-adopter",
                f"canonical tools.retrieval study adopter = {adopter!r} (pending)",
            )
        )
        if not canonical_aligned:
            blockers.append("settings-map:canonical-study-pending")
    else:
        checks.append(_skip("settings-map-adopter", "canonical settings map not found"))
        blockers.append("settings-map:missing")

    if adopted and canonical_aligned:
        blockers.clear()
    return checks, blockers, shas


def run_family_parity(study_repo: Path | None = None) -> ParityReport:
    """Run every parity check over the study copy; record sha + gate status."""
    study = (study_repo or REPO_ROOT).resolve()
    career, dev = _repo_paths()
    fixture = _fixture(study)
    checks: list[ParityCheck] = [
        _vocab_check(fixture),
        _quality_floor_check(fixture),
        _quality_case_check(fixture),
        _dto_shape_check(fixture),
    ]
    copy_checks, copy_shas = _vendored_copy_checks(study, career, dev)
    gate_checks, blockers, gate_shas = _sync_gate(study, dev)
    checks.extend(copy_checks)
    checks.extend(gate_checks)
    shas = {**copy_shas, **gate_shas}
    strict = all(check.status == "pass" for check in checks) and not blockers
    return ParityReport(
        study_repo=str(study),
        career_repo=str(career) if career is not None else None,
        dev_repo=str(dev) if dev is not None else None,
        checks=tuple(checks),
        shas=shas,
        strict=strict,
        strict_blockers=tuple(blockers),
    )


__all__ = ["ParityCheck", "ParityReport", "run_family_parity"]
