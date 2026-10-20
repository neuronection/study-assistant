"""Study's host-adapter wall for the production fetch (plan 37 §8 / 4.8).

The 2026-10-18 evaluation's H2 class is "the wall tests a boundary
production traffic does not cross". Study's version: the vendored polite
runtime had its own passing fixture wall while ``perform_fetch`` — the
only production egress — was raw ``httpx`` with ``follow_redirects=True``,
no SSRF guard and no caps.

These tests execute study's REAL path (``perform_fetch`` → the guarded
adapter → ``polite_http.polite_get``), never the vendored module directly,
over an ``httpx.MockTransport`` with a deterministic resolver, clock, sleep
and jitter. No network.
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from app.extensions.polite_http import HostRateLimiter
from app.extensions.search import SearchError, perform_fetch
from app.extensions.search.polite_fetch import FETCH_MAX_BYTES, fetch_document

PUBLIC_IP = "93.184.216.34"
SECOND_PUBLIC_IP = "1.1.1.1"


def public_resolver(host: str) -> list[str]:
    """Deterministic stand-in for DNS: every name is a public address the
    guard accepts (the test transport never connects anywhere)."""
    return [PUBLIC_IP]


@dataclass
class Recorded:
    url: httpx.URL
    host_header: str | None
    sni: str | None
    headers: dict[str, str]


@dataclass
class FakeClock:
    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


Handler = Callable[[httpx.Request], httpx.Response]


class HostAdapter:
    """The host-adapter fixture: drives ``perform_fetch`` exactly as the
    product does (URL import route / chat fetch tool / parser), with the
    network and clock seams pinned."""

    def __init__(self, handler: Handler) -> None:
        self.seen: list[Recorded] = []
        self.clock = FakeClock()
        self.rate = HostRateLimiter(requests_per_minute=30, clock=self.clock)

        def _handler(request: httpx.Request) -> httpx.Response:
            self.seen.append(
                Recorded(
                    url=request.url,
                    host_header=request.headers.get("host"),
                    sni=request.extensions.get("sni_hostname"),
                    headers={key.lower(): value for key, value in request.headers.items()},
                )
            )
            return handler(request)

        self.transport = httpx.MockTransport(_handler)

    def fetch(
        self,
        url: str,
        *,
        resolver: Callable[[str], list[str]] | None = None,
        state: dict[str, object] | None = None,
    ) -> str:
        return perform_fetch(
            url,
            transport=self.transport,
            state=state,
            resolver=resolver or public_resolver,
            rate=self.rate,
            sleep=self.clock.sleep,
            clock=self.clock,
            rng=lambda cap: cap / 2.0,
        )

    def document(self, url: str, **kwargs: Any) -> Any:
        return fetch_document(
            url,
            transport=self.transport,
            resolver=kwargs.pop("resolver", public_resolver),
            rate=self.rate,
            sleep=self.clock.sleep,
            clock=self.clock,
            rng=lambda cap: cap / 2.0,
            **kwargs,
        )


def ok_html(body: str = "<h1>P vs NP</h1><p>Undergraduate theory.</p>") -> Handler:
    return lambda request: httpx.Response(
        200, text=body, headers={"content-type": "text/html; charset=utf-8"}
    )


# --------------------------------------------------------------- the pin


def test_production_fetch_pins_the_guard_checked_address() -> None:
    """The request leaves with the resolved IP in the URL, the original
    Host header and TLS SNI — httpx cannot re-resolve at connect (H2)."""
    host = HostAdapter(ok_html())
    text = host.fetch("https://example.edu/pnp")

    assert "Undergraduate theory" in text
    assert len(host.seen) == 1
    request = host.seen[0]
    assert request.url.host == PUBLIC_IP
    assert str(request.url) == f"https://{PUBLIC_IP}/pnp"
    assert request.host_header == "example.edu"
    assert request.sni == "example.edu"


def test_production_fetch_is_a_navigation_not_a_crawl() -> None:
    """The seam deliberately leaves robots off (a user-directed fetch);
    the pinned decision is visible here so it cannot drift silently."""
    host = HostAdapter(ok_html())
    host.fetch("https://example.edu/pnp")
    assert [record.url.path for record in host.seen] == ["/pnp"]


# ------------------------------------------------------------ the guard


@pytest.mark.parametrize(
    ("url", "resolver"),
    [
        ("http://127.0.0.1/x", None),
        ("http://2130706433/x", None),  # decimal loopback
        ("http://0x7f.0.0.1/x", None),  # hex loopback
        ("http://[::ffff:127.0.0.1]/x", None),  # IPv4-mapped IPv6
        ("http://169.254.169.254/latest/meta-data", None),  # cloud metadata
        ("http://private.test/x", lambda host: ["10.0.0.7"]),
        ("http://private.test/x", lambda host: [PUBLIC_IP, "192.168.1.5"]),
    ],
)
def test_production_fetch_refuses_blocked_targets(
    url: str, resolver: Callable[[str], list[str]] | None
) -> None:
    """A blocked target is a typed refusal BEFORE any request."""
    host = HostAdapter(ok_html())
    with pytest.raises(SearchError) as raised:
        host.fetch(url, resolver=resolver)
    assert raised.value.kind == "bad_request"
    assert host.seen == []


def test_production_fetch_fails_closed_when_resolution_fails() -> None:
    """The vendored guard's best-effort allow is a pre-check semantic; a
    fetch that cannot be pinned must not connect by name."""

    def nxdomain(host: str) -> list[str]:
        raise socket.gaierror(f"NXDOMAIN: {host}")

    host = HostAdapter(ok_html())
    with pytest.raises(SearchError) as raised:
        host.fetch("https://gone.test/x", resolver=nxdomain)
    assert raised.value.kind == "unreachable"
    assert host.seen == []


# --------------------------------------------------------- per-hop policy


def test_production_fetch_revalidates_redirect_targets() -> None:
    """A redirect into a private target is refused on the hop, and the
    target never receives a request."""
    host = HostAdapter(
        lambda request: httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
    )
    with pytest.raises(SearchError) as raised:
        host.fetch("https://example.edu/start")
    assert raised.value.kind == "bad_request"
    assert len(host.seen) == 1
    assert host.seen[0].url.path == "/start"


def test_production_fetch_pins_each_public_redirect_hop() -> None:
    host = HostAdapter(
        lambda request: (
            httpx.Response(308, headers={"location": "https://second.test/b"})
            if request.url.path == "/a"
            else httpx.Response(200, text="second body", headers={"content-type": "text/plain"})
        )
    )

    def resolver(name: str) -> list[str]:
        return [PUBLIC_IP] if name.endswith("example.test") else [SECOND_PUBLIC_IP]

    text = host.fetch("https://first.example.test/a", resolver=resolver)
    assert text == "second body"
    assert [(record.url.host, record.host_header) for record in host.seen] == [
        (PUBLIC_IP, "first.example.test"),
        (SECOND_PUBLIC_IP, "second.test"),
    ]


def test_production_fetch_bounds_the_redirect_chain() -> None:
    host = HostAdapter(lambda request: httpx.Response(302, headers={"location": "/next"}))
    with pytest.raises(SearchError) as raised:
        host.fetch("https://example.edu/0")
    assert raised.value.kind == "protocol"
    assert "too many redirects" in raised.value.message


# ------------------------------------------------------------- the caps


def test_production_fetch_caps_the_response_body() -> None:
    """The runtime bounds the stream, then the product surfaces a typed
    error instead of converting an oversize body."""
    oversize = "x" * (FETCH_MAX_BYTES + 64)
    host = HostAdapter(
        lambda request: httpx.Response(
            200, text=oversize, headers={"content-type": "text/plain"}
        )
    )
    with pytest.raises(SearchError) as raised:
        host.fetch("https://example.edu/huge")
    assert raised.value.kind == "protocol"
    assert "size cap" in raised.value.message


# ------------------------------------------------------ conditional GET


def test_production_fetch_sends_cached_validators_and_reports_304() -> None:
    host = HostAdapter(
        lambda request: httpx.Response(
            304,
            headers={
                "etag": '"v7"',
                "last-modified": "Wed, 21 Oct 2015 07:28:00 GMT",
            },
        )
    )

    result = host.document(
        "https://example.edu/pnp",
        state={"etag": '"v7"', "last_modified": "Wed, 21 Oct 2015 07:28:00 GMT"},
    )
    assert result.status == 304
    assert result.not_modified is True
    assert result.etag == '"v7"'
    assert host.seen[0].headers["if-none-match"] == '"v7"'
    assert host.seen[0].headers["if-modified-since"] == "Wed, 21 Oct 2015 07:28:00 GMT"

    with pytest.raises(SearchError) as raised:
        host.fetch("https://example.edu/pnp", state={"etag": '"v7"'})
    assert raised.value.kind == "protocol"
    assert "304" in raised.value.message


# ------------------------------------------------- retry / typed errors


def test_production_fetch_retries_transient_status_with_deterministic_jitter() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, text="recovered", headers={"content-type": "text/plain"})

    host = HostAdapter(handler)
    assert host.fetch("https://example.edu/flaky") == "recovered"
    # Full-jitter with rng = cap / 2 on attempt 1: 2**1 / 2 = 1.0 s.
    assert host.clock.sleeps == [1.0]
    assert len(host.seen) == 2


def test_production_fetch_uses_the_per_host_bucket_across_calls() -> None:
    host = HostAdapter(ok_html())
    host.rate = HostRateLimiter(requests_per_minute=1, clock=host.clock)

    host.fetch("https://example.edu/one")
    assert host.clock.sleeps == []
    host.fetch("https://example.edu/two")
    assert host.clock.sleeps == [pytest.approx(60.0)]


def test_production_fetch_maps_auth_status_without_raw_text() -> None:
    host = HostAdapter(lambda request: httpx.Response(403, text="nope"))
    with pytest.raises(SearchError) as raised:
        host.fetch("https://example.edu/private")
    assert raised.value.kind == "auth"
    assert raised.value.http_status == 403


def test_production_fetch_does_not_leak_transport_exception_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom token=supersecret", request=request)

    host = HostAdapter(handler)
    with pytest.raises(SearchError) as raised:
        host.fetch("https://example.edu/x")
    assert raised.value.kind == "unreachable"
    assert "supersecret" not in raised.value.message
    assert "could not reach example.edu" in raised.value.message


def test_production_fetch_rejects_non_http_schemes_before_any_guard_work() -> None:
    host = HostAdapter(ok_html())
    with pytest.raises(SearchError) as raised:
        host.fetch("file:///etc/passwd")
    assert raised.value.kind == "bad_request"
    assert host.seen == []


@pytest.mark.parametrize(
    "url",
    [
        "https://[::1/x",  # invalid IPv6 literal
        "http://example.edu:99999/",  # port outside 0-65535
        "http://example.edu:notaport/",  # non-numeric port
    ],
)
def test_production_fetch_types_malformed_urls(url: str) -> None:
    """A malformed user URL is a typed refusal, not a raw ValueError on an
    API surface (F22)."""
    host = HostAdapter(ok_html())
    with pytest.raises(SearchError) as raised:
        host.fetch(url)
    assert raised.value.kind == "bad_request"
    assert "malformed" in raised.value.message
    assert host.seen == []
