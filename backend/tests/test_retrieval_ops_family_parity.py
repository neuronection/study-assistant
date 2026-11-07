"""Cross-repo family parity runner (plan 51 Q3c2b2).

Run against the sibling career checkout (the reference adopter) and the dev
canonical when they are present. A missing checkout is a recorded ``skip``;
a divergence is a failure. The strict family gate is never claimed while the
canonical sync ledger/settings map still records study as pending.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.services.retrieval import parity
from app.storage import retrieval_ops as ops


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_family_parity_runner_reports_every_check() -> None:
    report = parity.run_family_parity()
    assert report.ok is True
    names = {check.name for check in report.checks}
    assert {
        "contract-vocabulary",
        "quality-floor",
        "quality-fixture-cases",
        "dto-shape",
    } <= names
    for check in report.checks:
        assert check.status in {"pass", "skip", "fail"}

    payload = report.as_dict()
    assert payload["ok"] is True
    assert payload["shas"]["study:contract"] == _sha(
        parity.REPO_ROOT / "backend/app/storage/retrieval_ops.py"
    )
    assert payload["shas"]["study:fixtures"] == _sha(
        parity.REPO_ROOT / "backend/tests/fixtures/retrieval_ops.fixtures.json"
    )


def test_career_and_study_quality_dto_semantics_match() -> None:
    report = parity.run_family_parity()
    by_name = {check.name: check for check in report.checks}
    if report.career_repo is None:
        assert by_name["career-copy"].status == "skip"
    else:
        assert by_name["career-contract-byte-identity"].status == "pass"
        assert by_name["career-fixture-byte-identity"].status == "pass"
        assert report.shas["career:contract"] == report.shas["study:contract"]
        assert report.shas["career:fixtures"] == report.shas["study:fixtures"]


def test_strict_gate_is_green_after_study_main_adoption() -> None:
    report = parity.run_family_parity()
    if report.dev_repo is None:
        assert report.strict is False
        assert "dev-canonical-missing" in report.strict_blockers
        return
    checks = {check.name: check for check in report.checks}
    assert checks["dev-canonical-contract-byte-identity"].status == "pass"
    assert checks["dev-canonical-fixture-byte-identity"].status == "pass"
    assert checks["sync-ledger"].status == "pass"
    assert checks["settings-map-adopter"].status == "pass"
    assert checks["study-main-adoption"].status == "pass"
    assert report.strict is True
    assert report.strict_blockers == ()


def test_strict_gate_names_only_the_remaining_main_adoption_blocker() -> None:
    report = parity.run_family_parity()
    checks = {check.name: check for check in report.checks}
    if (
        report.dev_repo is None
        or checks.get("sync-ledger") is None
        or checks.get("settings-map-adopter") is None
        or checks["sync-ledger"].status != "pass"
        or checks["settings-map-adopter"].status != "pass"
        or checks["study-main-adoption"].status == "pass"
    ):
        return
    assert set(report.strict_blockers) <= {
        "adoption:study-main",
        "adoption:study-main-unverified",
    }
    assert len(report.strict_blockers) == 1


def test_fixture_quality_cases_run_through_the_vendored_contract() -> None:
    fixture = json.loads((parity.REPO_ROOT / parity.FIXTURE_RELATIVE).read_text(encoding="utf-8"))
    sets = {
        row["spaceId"]: ops.GoldenQuerySet.from_fixture(row)
        for row in fixture["quality"]["goldenSets"]
    }
    for case in fixture["quality"]["cases"]:
        scored = ops.evaluate_quality_set(sets[case["spaceId"]], case["retrieved"])
        assert scored.passed is case["expect"]["passed"]
        assert "query" not in scored.to_dict()
