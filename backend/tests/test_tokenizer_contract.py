"""Family tokenizer/chunk-config contract wall (ADR-0051 / plan 52 T5a).

Runs the canonical fixture table against the vendored contract copy in
``app/storage/tokenizer_contract.py`` — the same checks as dev's
``scripts/check-tokenizer-contract.py``. The vendored pair is byte-identical
to the dev canonical; when the dev worktree is present next to this checkout
the test also asserts that identity, and skips it otherwise (CI and public
clones only carry the vendored copy).
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from app.storage import tokenizer_contract as tc

CONTRACT = Path(tc.__file__)
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tokenizer_contract.fixtures.json"

ALLOWED_IMPORTS = {
    "__future__",
    "collections",
    "enum",
    "hashlib",
    "typing",
}

GROUPS = (
    "vocabularies",
    "versions",
    "defaults",
    "specs",
    "invalidSpecs",
    "chunkConfigs",
    "invalidChunkConfigs",
    "heuristic",
)

META = {"schema", "adr", "plan", "contract", "contractVersion", "description"}


def _fixtures() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_fixture_meta_and_group_inventory():
    fixtures = _fixtures()
    assert fixtures["schema"] == 1
    assert "ADR-0051" in str(fixtures["adr"])
    assert fixtures["plan"] == 52
    assert fixtures["contract"] == "tokenizer"
    assert fixtures["contractVersion"] == tc.TOKENIZER_CONTRACT_VERSION
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


def test_closed_vocabularies():
    data = _fixtures()["vocabularies"]
    expected = {
        "kinds": [member.value for member in tc.TokenizerKind],
        "reservedKinds": [member.value for member in tc.RESERVED_TOKENIZER_KINDS],
        "sources": [member.value for member in tc.TokenizerSource],
    }
    assert set(data) == set(expected)
    for key, value in expected.items():
        assert data[key] == value, key
    assert "sentencepiece" in data["kinds"]
    assert data["reservedKinds"] == ["sentencepiece"]


def test_versions_and_defaults_are_pinned():
    fixtures = _fixtures()
    assert fixtures["versions"] == {
        "contract": tc.TOKENIZER_CONTRACT_VERSION,
        "schema": tc.TOKENIZER_SCHEMA_VERSION,
    }
    mapping = {
        "minMaxChunkTokens": "MIN_MAX_CHUNK_TOKENS",
        "minMaxChars": "MIN_MAX_CHARS",
        "heuristicBytesPerToken": "HEURISTIC_BYTES_PER_TOKEN",
        "heuristicCodepointDivisor": "HEURISTIC_CODEPOINT_DIVISOR",
    }
    assert set(fixtures["defaults"]) == set(mapping)
    for key, attribute in mapping.items():
        assert getattr(tc, attribute) == fixtures["defaults"][key], attribute


def test_spec_round_trip_and_stable_keys():
    for row in _fixtures()["specs"]:
        spec = tc.TokenizerSpec.from_dict(row["spec"])
        assert spec.to_dict() == row["spec"], row["name"]
        assert spec.cache_key == row["expectedCacheKey"], row["name"]
        assert spec.identity == row["identity"], row["name"]
        assert tc.TokenizerSpec.from_dict(spec.to_dict()) == spec, row["name"]


def test_invalid_specs_raise():
    for row in _fixtures()["invalidSpecs"]:
        with pytest.raises(ValueError):
            tc.TokenizerSpec.from_dict(row["spec"])


def test_chunk_config_bounds_and_fit_rule():
    for row in _fixtures()["chunkConfigs"]:
        config = tc.ChunkConfig.from_dict(row["config"])
        assert config.to_dict() == row["config"], row["name"]
        assert config.fingerprint == row["expectedFingerprint"], row["name"]
        for case in row["fits"]:
            actual = config.fits(
                case["maxInputTokens"],
                prefix_tokens=case["prefixTokens"],
                safety_margin=case["safetyMargin"],
            )
            assert actual is case["expected"], f"{row['name']}: {case}"
            if case["expected"]:
                config.assert_fits(
                    case["maxInputTokens"],
                    prefix_tokens=case["prefixTokens"],
                    safety_margin=case["safetyMargin"],
                )
            else:
                with pytest.raises(ValueError):
                    config.assert_fits(
                        case["maxInputTokens"],
                        prefix_tokens=case["prefixTokens"],
                        safety_margin=case["safetyMargin"],
                    )


def test_invalid_chunk_configs_raise():
    for row in _fixtures()["invalidChunkConfigs"]:
        with pytest.raises(ValueError):
            tc.ChunkConfig.from_dict(row["config"])


def test_heuristic_counts_are_pinned_per_language():
    for row in _fixtures()["heuristic"]:
        assert tc.heuristic_token_count(row["text"]) == row["expectedTokens"], row["name"]


def _dev_canonical() -> Path | None:
    override = os.environ.get("STUDY_TOKENIZER_CONTRACT_CANONICAL")
    candidates = ([Path(override)] if override else []) + [
        Path(__file__).resolve().parents[3] / "dev-vector-p0" / "contracts",
        Path(__file__).resolve().parents[3] / "dev" / "contracts",
    ]
    return next((path for path in candidates if (path / "tokenizer_contract.py").is_file()), None)


def test_vendored_files_are_byte_identical_to_the_dev_canonical():
    canonical = _dev_canonical()
    if canonical is None:
        pytest.skip("dev canonical not present (CI/public clone) — vendored copy only")
    assert CONTRACT.read_bytes() == (canonical / "tokenizer_contract.py").read_bytes()
    assert FIXTURES.read_bytes() == (canonical / "tokenizer-contract.fixtures.json").read_bytes()
