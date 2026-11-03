# VENDORED FILE — family canonical (ADR-0031 / ADR-0048). Source of truth:
# dev/contracts/version_check.py; synced byte-identical to
# backend/app/core/version_check.py in career-assistant and
# backend/app/services/platform/version_check.py in study-assistant by
# dev/scripts/sync-version-check.sh, sha-checked by
# dev/scripts/verify-wiring.sh, accepted by the shared fixture table
# (dev/contracts/version_check.fixtures.json — vendored alongside, loaded
# by every repo's version-check contract test). NEVER edit the vendored
# copy in-repo — change the dev canonical, then re-run the sync (contract
# changes = one dev commit + one sync run, never per-repo edits).
"""Family version-check core (ADR-0048 / plan 48) — the shared Python law.

One canonical implementation of the update-check rules for the Python
desktop products (study-assistant, career-assistant; health stays
discovery-only — Docker pulls are its updater):

* **Channels come from the semver prerelease suffix** (ADR-0048 clause 2):
  ``stable`` = bare ``X.Y.Z``; ``beta`` = ``-rc.N`` / ``-beta.N``. A stable
  client is never offered a prerelease; a beta client follows plain semver
  (the final release supersedes its rcs); downgrades are never offered.
* **Consumers validate before use** and treat any validation failure,
  non-200 or timeout as "skip this check" — ``check_update`` never raises
  and an update check never blocks startup.
* **No telemetry**: the check is a plain GET of a static file on
  neuronection.com and identifies nobody.

The JavaScript (hub site) and TypeScript (desktop-assistant) counterparts
implement the same law; the shared fixture table is the cross-language
acceptance wall. The endpoint response shape matches the original
study-assistant ``UpdateCheckOut`` (plan 87 F) so both products expose an
identical surface.
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

VERSION_API_BASE = "https://neuronection.com/api/v1/versions"
FETCH_TIMEOUT_SECONDS = 10.0
HISTORY_MAX = 100
CHECK_INTERVAL_MIN = 900
CHECK_INTERVAL_MAX = 86_400

UpdateChannel = Literal["stable", "beta"]

FetchJson = Callable[[str], dict[str, Any]]

_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?$"
)


@dataclass(frozen=True)
class SemVer:
    """A parsed version — semver.org §11 ordering via :func:`compare_semver`."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...]


def parse_semver(text: str) -> SemVer | None:
    """Parse ``X.Y.Z`` with optional prerelease (leading ``v`` tolerated)."""
    match = _SEMVER.match(text.lstrip("vV"))
    if match is None:
        return None
    return SemVer(
        major=int(match.group(1)),
        minor=int(match.group(2)),
        patch=int(match.group(3)),
        prerelease=tuple(match.group(4).split(".")) if match.group(4) else (),
    )


def compare_semver(a: SemVer, b: SemVer) -> int:
    """Return ``-1``/``0``/``1`` per semver.org §11 (prerelease < release)."""
    for field in ("major", "minor", "patch"):
        if getattr(a, field) != getattr(b, field):
            return -1 if getattr(a, field) < getattr(b, field) else 1
    return _compare_prerelease(a.prerelease, b.prerelease)


def _compare_prerelease(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    if not a and not b:
        return 0
    if not a:
        return 1
    if not b:
        return -1
    for index in range(max(len(a), len(b))):
        left = a[index] if index < len(a) else None
        right = b[index] if index < len(b) else None
        if left is None:
            return -1
        if right is None:
            return 1
        left_numeric, right_numeric = left.isdigit(), right.isdigit()
        if left_numeric and right_numeric:
            if int(left) != int(right):
                return -1 if int(left) < int(right) else 1
        elif left_numeric:
            return -1
        elif right_numeric:
            return 1
        elif left != right:
            return -1 if left < right else 1
    return 0


def channel_of(version: str) -> UpdateChannel | None:
    """Classify a version by its prerelease suffix (unparseable → ``None``)."""
    parsed = parse_semver(version)
    if parsed is None:
        return None
    return "beta" if parsed.prerelease else "stable"


@dataclass(frozen=True)
class UpdateOffer:
    """The release a client may move to — never a downgrade, never a
    prerelease on the stable channel."""

    version: str
    tag: str
    channel: UpdateChannel
    url: str
    published_at: str


def resolve_update(
    current_version: str, channel: UpdateChannel, doc: dict[str, Any]
) -> UpdateOffer | None:
    """Apply the channel law to a validated version-API document.

    Stable clients consider only ``latestStable``; beta clients take the
    semver-max of ``latestStable`` and ``latestBeta``. Anything at or below
    the current version is ignored (no downgrades).
    """
    current = parse_semver(current_version)
    if channel == "stable":
        candidates = [doc["latestStable"]]
    else:
        candidates = [r for r in (doc.get("latestBeta"), doc["latestStable"]) if r]
    best: UpdateOffer | None = None
    best_parsed: SemVer | None = None
    for entry in candidates:
        parsed = parse_semver(str(entry.get("version", "")))
        if parsed is None:
            continue
        if current is not None and compare_semver(parsed, current) <= 0:
            continue
        if best_parsed is None or compare_semver(parsed, best_parsed) > 0:
            best = UpdateOffer(
                version=str(entry["version"]),
                tag=str(entry["tag"]),
                channel=str(entry["channel"]),  # type: ignore[arg-type]
                url=str(entry["url"]),
                published_at=str(entry["publishedAt"]),
            )
            best_parsed = parsed
    return best


def validate_doc(doc: Any) -> list[str]:
    """Structurally validate a ``productVersions`` document.

    Returns the issue list (empty = valid). This is the Python subset of
    ``contracts/version-api.schema.json`` — enough to never trust a
    malformed payload, without shipping a JSON-Schema engine.
    """
    issues: list[str] = []
    if not isinstance(doc, dict):
        return ["document is not a JSON object"]
    if doc.get("schemaVersion") != 1:
        issues.append("schemaVersion must be 1")
    for field in ("project", "repo", "generatedAt"):
        if not isinstance(doc.get(field), str) or not doc[field]:
            issues.append(f"{field} must be a non-empty string")
    interval = doc.get("checkIntervalSec")
    if not isinstance(interval, int) or not CHECK_INTERVAL_MIN <= interval <= CHECK_INTERVAL_MAX:
        issues.append("checkIntervalSec must be an integer in [900, 86400]")
    _validate_release(doc.get("latestStable"), "stable", "latestStable", issues)
    if doc.get("latestBeta") is not None:
        _validate_release(doc.get("latestBeta"), "beta", "latestBeta", issues)
    history = doc.get("history")
    if not isinstance(history, list):
        issues.append("history must be a list")
    elif len(history) > HISTORY_MAX:
        issues.append(f"history exceeds {HISTORY_MAX} entries")
    else:
        for index, entry in enumerate(history):
            if not isinstance(entry, dict):
                issues.append(f"history[{index}] is not an object")
                continue
            declared = entry.get("channel")
            suffix_channel = channel_of(str(entry.get("version", "")))
            if declared not in ("stable", "beta"):
                issues.append(f"history[{index}].channel must be stable or beta")
            elif suffix_channel is not None and suffix_channel != declared:
                issues.append(
                    f"history[{index}] declares {declared} but its version is {suffix_channel}"
                )
            _validate_release(
                entry,
                declared,  # type: ignore[arg-type]
                f"history[{index}]",
                issues,
            )
    return issues


def _validate_release(entry: Any, expected_channel: str, path: str, issues: list[str]) -> None:
    if not isinstance(entry, dict):
        issues.append(f"{path} must be an object")
        return
    version = entry.get("version")
    if not isinstance(version, str) or _SEMVER.match(version) is None:
        issues.append(f"{path}.version is not a bare semver")
    elif channel_of(version) != expected_channel:
        issues.append(f"{path}.version carries the wrong channel suffix for {expected_channel}")
    tag = entry.get("tag")
    if not isinstance(tag, str) or not tag.startswith("v"):
        issues.append(f"{path}.tag must start with 'v'")
    url = entry.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        issues.append(f"{path}.url must be an https URL")
    if not isinstance(entry.get("publishedAt"), str) or not entry["publishedAt"]:
        issues.append(f"{path}.publishedAt must be a non-empty string")


def check_update(
    product: str,
    current_version: str,
    *,
    channel: UpdateChannel = "stable",
    releases_page_url: str | None = None,
    fetch_json: FetchJson | None = None,
) -> dict[str, Any]:
    """Fetch, validate and resolve — never raises, never blocks (the law).

    Returns the ``UpdateCheckOut`` payload shape: ``current_version``,
    ``latest_version`` (the offered tag when an update exists, else the
    channel's newest), ``update_available``, ``release_url``, ``checked_at``
    and ``error`` (set only when the check failed — which always means
    "not available", never a hard failure).
    """
    fallback_url = releases_page_url or f"https://github.com/neuronection/{product}/releases"
    payload: dict[str, Any] = {
        "current_version": current_version,
        "latest_version": None,
        "update_available": False,
        "release_url": fallback_url,
        "checked_at": datetime.now(UTC).isoformat(),
        "error": None,
    }
    try:
        fetch = fetch_json or _default_fetch_json
        doc = fetch(f"{VERSION_API_BASE}/{product}.json")
        issues = validate_doc(doc)
        if issues:
            payload["error"] = "invalid version API document: " + "; ".join(issues[:3])
            return payload
        offer = resolve_update(current_version, channel, doc)
        reference = offer or _channel_reference(channel, doc)
        if reference is not None:
            payload["latest_version"] = reference.tag
            payload["release_url"] = reference.url
        payload["update_available"] = offer is not None
    except Exception as error:
        payload["error"] = str(error) or error.__class__.__name__
    return payload


def _channel_reference(channel: UpdateChannel, doc: dict[str, Any]) -> UpdateOffer | None:
    entries = [r for r in (doc.get("latestStable"), doc.get("latestBeta")) if r]
    if channel == "stable":
        entries = [doc["latestStable"]]
    best: UpdateOffer | None = None
    best_parsed: SemVer | None = None
    for entry in entries:
        parsed = parse_semver(str(entry.get("version", "")))
        if parsed is None:
            continue
        if best_parsed is None or compare_semver(parsed, best_parsed) > 0:
            best_parsed = parsed
            best = UpdateOffer(
                version=str(entry["version"]),
                tag=str(entry["tag"]),
                channel=str(entry["channel"]),  # type: ignore[arg-type]
                url=str(entry["url"]),
                published_at=str(entry["publishedAt"]),
            )
    return best


def _default_fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "neuronection-version-check"},
    )
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict):
        raise ValueError("version API response is not a JSON object")
    return body
