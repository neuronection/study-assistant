"""Study's guarded fetch adapter — the production fetch crosses the family
polite perimeter (plan 37 §8 / 4.8; the 2026-10-18 evaluation's H2 class:
"wall tests a boundary production traffic does not cross").

Before this module ``provider.perform_fetch`` was raw ``httpx`` with
``follow_redirects=True``: no SSRF guard, no per-hop revalidation, no size
cap. The vendored runtime (:mod:`app.extensions.polite_http`) was executed
only by its own fixture wall. This adapter puts the REAL path on that
runtime:

* **resolve-then-connect pinning** — every hop is resolved and checked by
  the vendored guard, and the checked address is pinned into the request
  URL (``polite_http.pinned_request_parts``: original ``Host`` header +
  ``sni_hostname`` extension, so TLS still validates the real name). httpx
  never re-resolves at connect — the DNS-rebind TOCTOU is closed.
* **resolution failure fails CLOSED for a fetch.** The vendored guard's
  best-effort allow on a failed lookup is a PRE-CHECK semantic (air-gapped
  runs, synthetic test hosts); sending by name here is exactly the
  rebinding window the pin exists to close, so an empty resolution raises
  ``unreachable`` instead of pinning nothing.
* **per-hop redirect revalidation** — ``polite_get`` walks redirects
  itself (the client is built ``follow_redirects=False``), re-running the
  full guard + pin + rate check on every target.
* **streaming size cap** (``max_response_bytes``) — a hostile body is
  bounded while it is read, never after it is materialized.
* **conditional GET** — cached ``etag`` / ``last_modified`` state becomes
  ``If-None-Match`` / ``If-Modified-Since``; a ``304`` is returned as a
  result with ``not_modified`` set (callers decide the cache policy).
* full-jitter retry with RFC 7231 Retry-After, and a per-host token bucket
  shared process-wide.

Robots is deliberate OFF for this seam: ``perform_fetch`` is a
user-directed single-document retrieval (the assistant fetching a result
the student picked, or a URL the student pasted) — a navigation, not a
crawl. Applying the crawler exclusion protocol would turn a third-party
``robots.txt`` into an import failure for content the user explicitly
asked for. The rate bucket, retries, guard, pin, redirect and size policy
all still apply.

Error model: the vendored :class:`polite_http.PoliteHttpError` (charter
typed codes) leaves this module; :func:`app.extensions.search.provider.perform_fetch`
projects it onto the ADR-0035 ``SearchError`` kinds at the product
boundary. No network in tests: pass an ``httpx.MockTransport`` + a
deterministic ``resolver``/``clock``/``sleep``/``rng``.
"""

from __future__ import annotations

import asyncio
import socket
import time
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx

from ..polite_http import (
    HostRateLimiter,
    NetGuardConfig,
    PoliteHttpConfig,
    PoliteHttpError,
    Resolver,
    conditional_headers,
    polite_get,
)

__all__ = [
    "FETCH_MAX_BYTES",
    "FetchResult",
    "fetch_config",
    "fetch_document",
    "reset_fetch_runtime",
    "system_resolver",
]

# The old per-fetch client budget (connect 1.5 s, read 10 s) is kept: the
# fetch tool is interactive, so a slow host must not hold a chat turn.
FETCH_CONNECT_TIMEOUT = 1.5
FETCH_READ_TIMEOUT = 10.0
# A document fetch only needs enough text for the answer/import; 2 MiB
# bounds parsing and markdown conversion as well as the socket read.
FETCH_MAX_BYTES = 2 * 1024 * 1024
FETCH_MAX_REDIRECTS = 5
FETCH_MAX_RETRIES = 2
FETCH_REQUESTS_PER_MINUTE = 30
FETCH_USER_AGENT = (
    "Mozilla/5.0 (compatible; NeuronectionStudyFetch/1.0; "
    "+https://neuronection.dev)"
)

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class FetchResult:
    """One guarded fetch's normalized result."""

    url: str
    status: int
    text: str
    content_type: str = ""
    etag: str | None = None
    last_modified: str | None = None
    truncated: bool = False

    @property
    def not_modified(self) -> bool:
        return self.status == 304


def system_resolver(host: str) -> list[str]:
    """OS resolver for the guard (de-duplicated address strings).

    Module-level so tests can substitute it wholesale (the ``resolver``
    keyword is the finer seam); it exists only to feed
    ``polite_http.check_url`` — the decision to allow/deny is the vendored
    guard's, never this function's.
    """
    infos = socket.getaddrinfo(host, None)
    seen: list[str] = []
    for *_, sockaddr in infos:
        address = str(sockaddr[0])
        if address not in seen:
            seen.append(address)
    return seen


class _ResolutionFailed(Exception):
    """Raised by :func:`_fail_closed_resolver`.

    Deliberately NOT an ``OSError``/``socket.gaierror``: the vendored
    guard translates those into its best-effort allow (empty address
    list), which is the by-name connection this seam must not make. This
    relies on ``polite_http.check_url`` only swallowing resolver
    ``OSError`` — pinned by
    ``test_production_fetch_fails_closed_when_resolution_fails`` so a
    vendored change to that policy fails the wall instead of silently
    reopening the rebind window.
    """

    def __init__(self, host: str) -> None:
        self.host = host
        super().__init__(host)


def _fail_closed_resolver(inner: Resolver) -> Resolver:
    def resolve(host: str) -> list[str]:
        try:
            addresses = inner(host)
        except (socket.gaierror, OSError) as exc:
            raise _ResolutionFailed(host) from exc
        if not addresses:
            raise _ResolutionFailed(host)
        return addresses

    return resolve


def fetch_config(*, max_response_bytes: int = FETCH_MAX_BYTES) -> PoliteHttpConfig:
    """The fetch policy. Guard defaults are the secure ones: private,
    loopback, link-local (cloud metadata), reserved and numeric-literal
    hosts are refused; declared-domain scope is empty because this seam
    fetches arbitrary user-picked destinations (the guard is the gate)."""
    return PoliteHttpConfig(
        guard=NetGuardConfig(),
        domains=frozenset(),
        requests_per_minute=FETCH_REQUESTS_PER_MINUTE,
        max_response_bytes=max(1, int(max_response_bytes)),
        connect_timeout=FETCH_CONNECT_TIMEOUT,
        read_timeout=FETCH_READ_TIMEOUT,
        max_retries=FETCH_MAX_RETRIES,
        max_redirects=FETCH_MAX_REDIRECTS,
        user_agent=FETCH_USER_AGENT,
        # See the module docstring: a user-directed navigation is not a
        # crawl, so the crawler exclusion protocol does not apply here.
        respect_robots=False,
        pin_resolved_address=True,
    )


# One bucket per process: politeness must hold ACROSS fetches, not only
# within one polite_get call.
_limiter: HostRateLimiter | None = None


def _default_limiter() -> HostRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = HostRateLimiter(requests_per_minute=FETCH_REQUESTS_PER_MINUTE)
    return _limiter


def reset_fetch_runtime() -> None:
    """Test hook: drop the shared per-host bucket."""
    global _limiter
    _limiter = None


class _SyncTransportAdapter(httpx.AsyncBaseTransport):
    """Drive a sync ``httpx.BaseTransport`` (the tests' ``MockTransport``)
    from the async runtime. The borrowed transport is never closed — the
    caller owns it."""

    def __init__(self, transport: httpx.BaseTransport) -> None:
        self._transport = transport

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await asyncio.to_thread(self._transport.handle_request, request)

    async def aclose(self) -> None:  # pragma: no cover — no-op by design
        return None


class _BorrowedTransport(httpx.AsyncBaseTransport):
    """Async transport passthrough that does not take ownership (no close)."""

    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        self._transport = transport

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self._transport.handle_async_request(request)

    async def aclose(self) -> None:  # pragma: no cover — no-op by design
        return None


def _async_transport(
    transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None,
) -> httpx.AsyncBaseTransport | None:
    if transport is None:
        return None
    if isinstance(transport, httpx.AsyncBaseTransport):
        return _BorrowedTransport(transport)
    return _SyncTransportAdapter(transport)


async def _fetch(
    url: str,
    *,
    transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None,
    state: Mapping[str, object] | None,
    resolver: Resolver | None,
    rate: HostRateLimiter | None,
    sleep: Sleep | None,
    clock: Callable[[], float] | None,
    rng: Callable[[float], float] | None,
    config: PoliteHttpConfig | None,
) -> FetchResult:
    cfg = config or fetch_config()
    timeout = httpx.Timeout(
        connect=cfg.connect_timeout,
        read=cfg.read_timeout,
        write=cfg.read_timeout,
        pool=cfg.connect_timeout,
    )
    async with httpx.AsyncClient(
        transport=_async_transport(transport),
        timeout=timeout,
        # polite_get walks redirects itself so every hop is re-guarded.
        follow_redirects=False,
    ) as client:
        try:
            response = await polite_get(
                url,
                client=client,
                config=cfg,
                headers=conditional_headers(state),
                resolver=_fail_closed_resolver(resolver or system_resolver),
                rate=rate or _default_limiter(),
                sleep=sleep or asyncio.sleep,
                clock=clock or time.monotonic,
                rng=rng,
            )
        except _ResolutionFailed as exc:
            raise PoliteHttpError(
                "unreachable",
                f"could not resolve {exc.host} — failing closed (no pin)",
            ) from exc
        except (ValueError, httpx.InvalidURL) as exc:
            # urlparse/httpx reject an invalid IPv6 literal or a port
            # outside 0-65535 before a request exists; a user-supplied URL
            # must become a typed refusal, never a raw traceback (F22).
            raise PoliteHttpError(
                "net-denied", "malformed URL (invalid host or port)"
            ) from exc

    headers = {key.lower(): value for key, value in response.headers.items()}
    return FetchResult(
        url=response.url,
        status=response.status,
        text=response.body,
        content_type=headers.get("content-type", ""),
        etag=response.etag,
        last_modified=response.last_modified,
        truncated=response.truncated,
    )


def fetch_document(
    url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    state: Mapping[str, object] | None = None,
    resolver: Resolver | None = None,
    rate: HostRateLimiter | None = None,
    sleep: Sleep | None = None,
    clock: Callable[[], float] | None = None,
    rng: Callable[[float], float] | None = None,
    config: PoliteHttpConfig | None = None,
) -> FetchResult:
    """Run one guarded (sync-facing) fetch.

    Study's fetch call sites are sync (URL import route, parser, chat
    tool); the vendored runtime is async. A sync caller with no running
    loop gets a private loop; a caller that somehow IS on a loop (an async
    handler) gets a worker thread instead of an ``asyncio.run`` crash.
    """

    def run() -> FetchResult:
        return asyncio.run(
            _fetch(
                url,
                transport=transport,
                state=state,
                resolver=resolver,
                rate=rate,
                sleep=sleep,
                clock=clock,
                rng=rng,
                config=config,
            )
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return run()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="study-fetch") as pool:
        return pool.submit(run).result()
