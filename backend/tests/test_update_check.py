"""Update-check endpoint (plan 87 F; plan 48 W6 moved the law into the
synced family contract ``version_check.py`` — GitHub Releases polling and
the crude version tuples are gone, the endpoint is a caching wrapper)."""

from typing import Any

import pytest

from app import __version__
from app.api import instance
from app.services.platform import version_check


def make_doc(latest_stable: str, latest_beta: str | None = None) -> dict[str, Any]:
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


@pytest.fixture(autouse=True)
def reset_cache() -> None:
    instance._UPDATE_CACHE = None
    instance._UPDATE_CACHE_AT = None


def test_newer_release_is_an_available_update(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_fetch(url: str) -> dict[str, Any]:
        calls.append(url)
        return make_doc("99.0.0")

    monkeypatch.setattr(version_check, "_default_fetch_json", fake_fetch)
    payload = instance.update_check()
    assert payload["current_version"] == __version__
    assert payload["latest_version"] == "v99.0.0"
    assert payload["update_available"] is True
    assert str(payload["release_url"]).endswith("v99.0.0")

    again = instance.update_check()
    assert again == payload
    assert len(calls) == 1


def test_same_or_older_release_is_not_an_update(monkeypatch: pytest.MonkeyPatch) -> None:
    for version in (__version__, "0.0.1"):
        instance._UPDATE_CACHE = None
        instance._UPDATE_CACHE_AT = None
        monkeypatch.setattr(
            version_check, "_default_fetch_json", lambda url, version=version: make_doc(version)
        )
        payload = instance.update_check()
        assert payload["update_available"] is False
        assert payload["latest_version"] == f"v{version}"


def test_stable_channel_ignores_a_newer_prerelease(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        version_check, "_default_fetch_json", lambda url: make_doc(__version__, "99.0.0-rc.1")
    )
    payload = instance.update_check()
    assert payload["update_available"] is False
    assert payload["error"] is None


def test_invalid_document_is_skipped_not_trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(version_check, "_default_fetch_json", lambda url: {"schemaVersion": 2})
    payload = instance.update_check()
    assert payload["update_available"] is False
    assert "invalid version API document" in str(payload["error"])


def test_network_failure_is_honest_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(url: str) -> dict[str, Any]:
        raise RuntimeError("offline")

    monkeypatch.setattr(version_check, "_default_fetch_json", fake_fetch)
    payload = instance.update_check()
    assert payload["update_available"] is False
    assert payload["latest_version"] is None
    assert payload["error"]
