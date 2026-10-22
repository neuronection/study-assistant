import httpx
import pytest

from app import __version__
from app.api import instance


class FakeResponse:
    def __init__(self, payload: dict[str, object], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.invalid")
            raise httpx.HTTPStatusError(
                "boom",
                request=request,
                response=httpx.Response(500, request=request),
            )

    def json(self) -> dict[str, object]:
        return self._payload


@pytest.fixture(autouse=True)
def reset_cache() -> None:
    instance._UPDATE_CACHE = None
    instance._UPDATE_CACHE_AT = None


def test_newer_release_is_an_available_update(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append(url)
        return FakeResponse(
            {
                "tag_name": "v99.0.0",
                "html_url": "https://github.com/neuronection/study-assistant/releases/tag/v99.0.0",
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    payload = instance.update_check()
    assert payload["current_version"] == __version__
    assert payload["latest_version"] == "v99.0.0"
    assert payload["update_available"] is True
    assert str(payload["release_url"]).endswith("v99.0.0")

    again = instance.update_check()
    assert again == payload
    assert len(calls) == 1


def test_same_or_older_release_is_not_an_update(monkeypatch: pytest.MonkeyPatch) -> None:
    for tag in (f"v{__version__}", "v0.0.1"):
        instance._UPDATE_CACHE = None
        instance._UPDATE_CACHE_AT = None
        monkeypatch.setattr(
            httpx,
            "get",
            lambda url, tag=tag, **kwargs: FakeResponse({"tag_name": tag}),
        )
        payload = instance.update_check()
        assert payload["update_available"] is False
        assert payload["latest_version"] == tag


def test_network_failure_is_honest_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", fake_get)
    payload = instance.update_check()
    assert payload["update_available"] is False
    assert payload["latest_version"] is None
    assert payload["error"]


def test_version_tuple_handles_prefixes_and_suffixes() -> None:
    assert instance._version_tuple("v1.2.3") == (1, 2, 3)
    assert instance._version_tuple("1.2") == (1, 2, 0)
    assert instance._version_tuple("1.2.3-rc.1") == (1, 2, 3)
    assert instance._version_tuple("nope") is None
