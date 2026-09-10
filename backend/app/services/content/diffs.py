"""Unified text diffs between content versions (plan 58).

Pure functions over the version snapshots that already exist (note_versions,
material extractions). Diffs are computed on read — nothing is stored — and
use difflib's unified format so any client can render them.
"""

import difflib
from dataclasses import dataclass


@dataclass(frozen=True)
class VersionDiff:
    additions: int
    deletions: int
    diff: str


def unified_text_diff(
    base_text: str,
    target_text: str,
    base_label: str,
    target_label: str,
) -> VersionDiff:
    base_lines = base_text.splitlines()
    target_lines = target_text.splitlines()
    raw = difflib.unified_diff(
        base_lines,
        target_lines,
        fromfile=base_label,
        tofile=target_label,
        lineterm="",
    )
    diff_lines = list(raw)
    additions = 0
    deletions = 0
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return VersionDiff(
        additions=additions,
        deletions=deletions,
        diff="\n".join(diff_lines),
    )
