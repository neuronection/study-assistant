"""The product capability-showcase wall (family plan 43): the repo's
``docs/capabilities.json`` validates against the vendored
``contracts/product-capabilities.schema.json`` copy and passes the
semantic checks JSON Schema cannot express — capability ids unique,
matrix rows unique, the project slug matches this repo, and every
declared ``shot`` resolves to a real file under ``docs/``.

The schema copy must stay byte-identical to the dev canonical
(``dev/contracts/product-capabilities.schema.json``); validation rides
the same vendored stdlib draft-2020-12 validator the extension walls
use (``app.extensions.contract``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.extensions import contract

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"
CAPABILITIES = DOCS_DIR / "capabilities.json"
SCHEMA = REPO_ROOT / "contracts" / "product-capabilities.schema.json"
PROJECT = "study"

FAILURE_MESSAGE = (
    "docs/capabilities.json must be updated in the same change as a shipped "
    "feature (family contract: contracts/product-capabilities.schema.json)"
)

SCHEMA_DOC = json.loads(SCHEMA.read_text(encoding="utf-8"))


def _load_capabilities() -> dict[str, Any]:
    doc: dict[str, Any]
    try:
        doc = json.loads(CAPABILITIES.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{FAILURE_MESSAGE} — does not parse: {exc}") from exc
    return doc


def test_capabilities_json_validates_against_the_contract() -> None:
    doc = _load_capabilities()
    err = contract.validate(SCHEMA_DOC, doc, SCHEMA_DOC)
    assert err is None, f"{FAILURE_MESSAGE}\n{err}"


def test_capabilities_project_matches_the_repo() -> None:
    doc = _load_capabilities()
    assert doc.get("project") == PROJECT, FAILURE_MESSAGE


def test_capability_ids_are_unique() -> None:
    doc = _load_capabilities()
    ids = [cap["id"] for cap in doc.get("capabilities", [])]
    dupes = sorted({cap_id for cap_id in ids if ids.count(cap_id) > 1})
    assert not dupes, f"{FAILURE_MESSAGE}\nduplicate capability ids {dupes}"


def test_matrix_rows_are_unique() -> None:
    doc = _load_capabilities()
    rows = [row["row"] for row in doc.get("matrix", [])]
    dupes = sorted({row_id for row_id in rows if rows.count(row_id) > 1})
    assert not dupes, f"{FAILURE_MESSAGE}\nduplicate matrix rows {dupes}"


def test_declared_shots_resolve_under_docs() -> None:
    doc = _load_capabilities()
    for cap in doc.get("capabilities", []):
        shot = cap.get("shot")
        if not shot:
            continue
        resolved = (DOCS_DIR / shot).resolve()
        assert resolved.is_file(), (
            f"{FAILURE_MESSAGE}\ncapability {cap['id']!r} declares shot "
            f"{shot!r} which does not resolve"
        )
        assert REPO_ROOT in resolved.parents, (
            f"{FAILURE_MESSAGE}\ncapability {cap['id']!r} shot {shot!r} escapes the repo"
        )


# ------------------------------------------------------- contract semantics


def _semantic_problems(doc: dict, expected_project: str) -> list[str]:
    problems: list[str] = []
    if doc.get("project") != expected_project:
        problems.append(f"project must be {expected_project!r}")
    ids = [cap.get("id") for cap in doc.get("capabilities", [])]
    problems += [f"duplicate capability id {i!r}" for i in sorted(set(ids)) if ids.count(i) > 1]
    rows = [row.get("row") for row in doc.get("matrix", [])]
    problems += [f"duplicate matrix row {r!r}" for r in sorted(set(rows)) if rows.count(r) > 1]
    for cap in doc.get("capabilities", []):
        if cap.get("status") != "shipped" and (cap.get("proofs") or cap.get("metric")):
            problems.append(
                f"capability {cap.get('id')!r} is {cap.get('status')!r} and must not claim "
                f"proofs or a metric (shipped only)"
            )
        shot = cap.get("shot")
        if isinstance(shot, str) and (
            shot.startswith("/") or "\\" in shot or ".." in shot.split("/")
        ):
            problems.append(f"capability {cap.get('id')!r} shot escapes the manifest directory: {shot!r}")
    return problems


def test_semantics_hold_for_the_real_manifest() -> None:
    doc = _load_capabilities()
    problems = _semantic_problems(doc, "study")
    assert not problems, f"{FAILURE_MESSAGE}\n" + "; ".join(problems)


def test_contract_fixtures_stay_honest() -> None:
    fixtures_path = REPO_ROOT.parent / "dev" / "contracts" / "product-capabilities.fixtures.json"
    if not fixtures_path.is_file():
        pytest.skip("family dev repo not present beside this checkout")
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    schema = json.loads(
        (REPO_ROOT / "contracts" / "product-capabilities.schema.json").read_text(encoding="utf-8")
    )
    for case in fixtures["valid"]:
        assert contract.validate(schema, case["doc"], schema) is None, (
            f"fixture {case['name']!r} must stay valid against the contract"
        )
        assert not _semantic_problems(case["doc"], case["doc"].get("project", "")), (
            f"fixture {case['name']!r} must stay semantically clean"
        )
    for case in fixtures["invalid"]:
        rejected = contract.validate(schema, case["doc"], schema) is not None or bool(
            _semantic_problems(case["doc"], case.get("expectProject", case["doc"].get("project", "")))
        )
        assert rejected, f"fixture {case['name']!r} must stay invalid against the contract"
