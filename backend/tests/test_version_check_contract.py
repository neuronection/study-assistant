"""Version-check contract wall — the shared fixture table is the
cross-language acceptance law (ADR-0048 / plan 48): the vendored
``version_check.py`` must satisfy the same rows as the hub site's JS and
desktop-assistant's TS implementations."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.platform.version_check import (
    channel_of,
    compare_semver,
    parse_semver,
    resolve_update,
    validate_doc,
)

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "version_check.fixtures.json").read_text()
)


def make_doc(latest_stable: str, latest_beta: str | None) -> dict[str, Any]:
    def release(version: str) -> dict[str, Any]:
        return {
            "version": version,
            "tag": f"v{version}",
            "channel": "beta" if "-" in version else "stable",
            "publishedAt": "2026-10-30T00:00:00Z",
            "url": f"https://github.com/neuronection/study-assistant/releases/tag/v{version}",
        }

    return {
        "schemaVersion": 1,
        "project": "study-assistant",
        "repo": "neuronection/study-assistant",
        "generatedAt": "2026-10-30T04:40:11Z",
        "checkIntervalSec": 21600,
        "latestStable": release(latest_stable),
        "latestBeta": release(latest_beta) if latest_beta else None,
        "history": [],
    }


@pytest.mark.parametrize("row", FIXTURES["semverCompare"], ids=lambda r: r["name"])
def test_semver_compare(row: Any) -> None:
    left = parse_semver(row["a"])
    right = parse_semver(row["b"])
    assert left is not None and right is not None
    assert compare_semver(left, right) == row["expected"]


@pytest.mark.parametrize("row", FIXTURES["channelOf"], ids=lambda r: r["name"])
def test_channel_of(row: Any) -> None:
    assert channel_of(row["version"]) == row["expected"]


@pytest.mark.parametrize("row", FIXTURES["resolveUpdate"], ids=lambda r: r["name"])
def test_resolve_update(row: Any) -> None:
    doc = make_doc(row["latestStable"], row["latestBeta"])
    offer = resolve_update(row["current"], row["channel"], doc)
    got = None if offer is None else {"version": offer.version, "channel": offer.channel}
    assert got == row["expected"]


@pytest.mark.parametrize("row", FIXTURES["validateDoc"], ids=lambda r: r["name"])
def test_validate_doc(row: Any) -> None:
    issues = validate_doc(row["doc"])
    assert (not issues) == row["valid"]
    if row.get("issueContains"):
        assert any(row["issueContains"] in issue for issue in issues)
