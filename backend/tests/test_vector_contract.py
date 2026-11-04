"""Family vector-contract wall (ADR-0051 / plan 50 P3a).

Runs the canonical fixture table against the vendored contract copy in
``app/storage/vector_contract.py`` — the same checks as dev's
``scripts/check-vector-contract.py``. The vendored pair is byte-identical
to the dev canonical; when the dev worktree is present next to this
checkout the test also asserts that identity, and skips it otherwise (CI and
public clones only carry the vendored copy).
"""

from __future__ import annotations

import ast
import json
import math
import os
from pathlib import Path
from typing import Any, cast

import pytest

from app.storage import vector_contract as vc

CONTRACT = Path(vc.__file__)
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vector_contract.fixtures.json"

ALLOWED_IMPORTS = {
    "__future__",
    "collections",
    "dataclasses",
    "enum",
    "hashlib",
    "math",
    "typing",
}

GROUPS = (
    "cosine",
    "normalize",
    "textHash",
    "spaceKeyStability",
    "spaceKeyPinned",
    "rrfMerge",
    "fusedOrder",
    "maxsim",
    "topMean",
    "defaults",
    "vocabularies",
    "backendCaps",
    "degradation",
    "invalidArgs",
)

META = {"schema", "adr", "plan", "description"}


def _fixtures() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(FIXTURES.read_text(encoding="utf-8")))


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12)


def _space(row: dict[str, Any]) -> vc.VectorSpace:
    return vc.VectorSpace(
        name="fixture",
        provider=row["provider"],
        model=row["model"],
        dim=row["dim"],
        normalize=row["normalize"],
        query_prefix=row.get("queryPrefix"),
        document_prefix=row.get("documentPrefix"),
        chunker_version=row["chunkerVersion"],
        composer_version=row["composerVersion"],
    )


def test_fixture_meta_and_group_inventory() -> None:
    fixtures = _fixtures()
    assert fixtures["schema"] == 1
    assert "ADR-0051" in str(fixtures["adr"])
    assert fixtures["plan"] == 50
    present = set(fixtures) - META
    assert present == set(GROUPS), (
        f"missing {sorted(set(GROUPS) - present)}, extra {sorted(present - set(GROUPS))}"
    )
    for group in GROUPS:
        assert fixtures[group], f"{group} is empty"


def test_vendored_contract_imports_stdlib_only() -> None:
    tree = ast.parse(CONTRACT.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    assert not found - ALLOWED_IMPORTS, f"non-stdlib imports: {sorted(found - ALLOWED_IMPORTS)}"


def test_cosine_fixtures() -> None:
    for row in _fixtures()["cosine"]:
        actual = vc.cosine(row["a"], row["b"])
        assert _close(actual, row["expected"]), (
            f"{row['name']}: expected {row['expected']}, got {actual}"
        )


def test_normalize_fixtures() -> None:
    for row in _fixtures()["normalize"]:
        actual = vc.normalize(row["vector"])
        assert len(actual) == len(row["expected"]), f"{row['name']}: length changed"
        assert all(_close(a, e) for a, e in zip(actual, row["expected"], strict=True)), (
            f"{row['name']}: expected {row['expected']}, got {actual}"
        )


def test_text_hash_fixtures() -> None:
    for row in _fixtures()["textHash"]:
        assert vc.normalize_text(row["text"]) == row["expectedNormalized"], row["name"]
        assert vc.content_hash(row["text"]) == row["expectedHash"], row["name"]


def test_space_key_stability_fixtures() -> None:
    for row in _fixtures()["spaceKeyStability"]:
        same = _space(row["a"]).key == _space(row["b"]).key
        assert same is row["same"], f"{row['name']}: expected same={row['same']}"


def test_pinned_space_keys() -> None:
    for row in _fixtures()["spaceKeyPinned"]:
        assert _space(row["space"]).key == row["expected"], row["name"]


def test_rrf_merge_fixtures() -> None:
    for row in _fixtures()["rrfMerge"]:
        scores = vc.rrf_merge(row["lists"], k=row["k"], weights=row.get("weights"))
        expected = row["expectedScores"]
        assert set(scores) == set(expected), f"{row['name']}: ids changed"
        for key, value in expected.items():
            assert _close(scores[key], value), f"{row['name']}/{key}"
        assert vc.fused_order(scores) == row["expectedOrder"], row["name"]


def test_fused_order_fixtures() -> None:
    for row in _fixtures()["fusedOrder"]:
        assert vc.fused_order(row["scores"]) == row["expected"], row["name"]


def test_maxsim_fixtures() -> None:
    for row in _fixtures()["maxsim"]:
        actual = vc.maxsim(row["queries"], row["documents"])
        assert _close(actual, row["expected"]), f"{row['name']}: got {actual}"


def test_top_mean_fixtures() -> None:
    for row in _fixtures()["topMean"]:
        actual = vc.top_mean(row["scores"], row["n"])
        assert _close(actual, row["expected"]), f"{row['name']}: got {actual}"


def test_v1_defaults_are_pinned() -> None:
    expected = _fixtures()["defaults"]
    mapping = {
        "rrfK": "RRF_K",
        "exactScanThreshold": "EXACT_SCAN_THRESHOLD",
        "coverageGate": "COVERAGE_GATE",
        "candidateMultiplier": "CANDIDATE_MULTIPLIER",
        "maxsimCandidateCap": "MAXSIM_CANDIDATE_CAP",
        "rerankTopN": "RERANK_TOP_N",
        "topMeanN": "TOP_MEAN_N",
        "efSearchDefault": "EF_SEARCH_DEFAULT",
        "linearCapRows": "LINEAR_CAP_ROWS",
        "sqliteVecRecommendedRows": "SQLITE_VEC_RECOMMENDED_ROWS",
    }
    assert set(expected) == set(mapping)
    for key, attribute in mapping.items():
        assert getattr(vc, attribute) == expected[key], attribute


def test_closed_vocabularies() -> None:
    data = _fixtures()["vocabularies"]
    expected = {
        "backends": [vc.BACKEND_PGVECTOR, vc.BACKEND_SQLITE_VEC, vc.BACKEND_LINEAR],
        "spaceStatuses": [member.value for member in vc.SpaceStatus],
        "degradedReasons": [member.value for member in vc.DegradedReason],
        "views": list(vc.V1_VIEWS),
        "metric": vc.METRIC_COSINE,
    }
    assert set(data) == set(expected)
    for key, value in expected.items():
        assert data[key] == value, key


def test_backend_capabilities() -> None:
    data = _fixtures()["backendCaps"]
    assert set(data) == set(vc.BACKEND_CAPS)
    for backend, row in data.items():
        caps = vc.BACKEND_CAPS[backend]
        assert {
            "ann": caps.ann,
            "maxDim": caps.max_dim,
            "maxRecommendedRows": caps.max_recommended_rows,
            "scopeEnforcement": str(caps.scope_enforcement),
        } == row, backend


def test_degradation_matrix_covers_the_closed_enum() -> None:
    rows = _fixtures()["degradation"]
    reasons = {str(member) for member in vc.DegradedReason}
    assert {row["reason"] for row in rows} == reasons


def test_invalid_arguments_raise_value_error() -> None:
    for row in _fixtures()["invalidArgs"]:
        with pytest.raises(ValueError):
            if row["call"] == "topMean":
                vc.top_mean(row["scores"], row["n"])
            elif row["call"] == "rrfMerge":
                vc.rrf_merge(row["lists"], k=row["k"], weights=row.get("weights"))
            elif row["call"] == "space":
                _space(row["space"])
            else:  # pragma: no cover - a new fixture call must be wired
                pytest.fail(f"unknown invalidArgs call {row['call']}")


def _dev_canonical() -> Path | None:
    override = os.environ.get("STUDY_VECTOR_CONTRACT_CANONICAL")
    candidates = ([Path(override)] if override else []) + [
        Path(__file__).resolve().parents[3] / "dev-vector-p0" / "contracts",
        Path(__file__).resolve().parents[3] / "dev" / "contracts",
    ]
    return next((path for path in candidates if (path / "vector_contract.py").is_file()), None)


def test_vendored_files_are_byte_identical_to_the_dev_canonical() -> None:
    canonical = _dev_canonical()
    if canonical is None:
        pytest.skip("dev canonical not present (CI/public clone) — vendored copy only")
    assert CONTRACT.read_bytes() == (canonical / "vector_contract.py").read_bytes()
    assert FIXTURES.read_bytes() == (canonical / "vector-contract.fixtures.json").read_bytes()
