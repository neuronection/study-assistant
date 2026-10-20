"""The charter typed-error model (ADR-0040 D4/D18) — study's adoption.

``ExtensionError`` is the one error family the extension surface exchanges:
a closed 15-code enum (``not-ready · needs-secret · invalid · unsupported ·
io · not-found · path-denied · net-denied · auth · rate-limited ·
unreachable · protocol · provider · budget · canceled``) + capped ``detail``
+ a closed ``retryable`` sub-enum, optionally carrying ``retry_after_ms``.
Raw exception strings never cross an extension boundary.

**The vendored SearchError keeps its taxonomy (D18 rider).** The
ADR-0035 web-search trio lives in the vendored copies
(:mod:`app.extensions.search.providers_contract`) whose byte-identity is a
Phase-7 wall pinned through the dev canonical + sync ledger — its 9-kind
error enum is part of that family wire contract (desktop's TS adapters
implement the same cases), so it is NOT renamed here. The D4 mapping lives
app-side instead, as :func:`to_extension_error` — the one-time
re-authoring note, implemented exactly as
``extension-charter.json errors.legacyMappingNote`` records it:

======================  =====================
SearchError.kind        charter code
======================  =====================
``missing_key``         ``needs-secret``
``missing_config``      ``invalid``
``unknown_type``        ``invalid``
``bad_request``         ``invalid``
``auth``                ``auth``
``rate_limit``          ``rate-limited``
``unreachable``         ``unreachable``
``json_disabled``       ``protocol``
``protocol``            ``protocol``
======================  =====================

Converging the canonical enum itself is an ADR-0035-contract decision (it
ripples to the desktop reference implementation and the 12-case fixture
wall) — recorded for the charter owners, not taken in a product commit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.extensions.polite_http import (
    DEFAULT_RETRYABLE,
    ERROR_CODES,
    RETRYABLE_VOCABULARY,
)

if TYPE_CHECKING:
    from app.extensions.search.providers_contract import SearchError

__all__ = [
    "DEFAULT_RETRYABLE",
    "ERROR_CODES",
    "RETRYABLE_VOCABULARY",
    "ExtensionError",
    "to_extension_error",
]


class ExtensionError(Exception):
    """A typed charter error — one of the 15 closed codes + capped detail.

    ``retryable`` defaults per code from the vendored runtime and may not
    leave the closed sub-enum; ``retry_after_ms`` carries a 429
    Retry-After payload when known; ``status`` keeps the upstream HTTP
    status when one was received.
    """

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        retryable: str | None = None,
        retry_after_ms: int | None = None,
        status: int | None = None,
    ) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown charter error code: {code!r}")
        self.code = code
        self.detail = detail[:500]
        self.retryable = retryable or DEFAULT_RETRYABLE[code]
        if self.retryable not in RETRYABLE_VOCABULARY:
            raise ValueError(f"retryable outside the closed sub-enum: {self.retryable!r}")
        self.retry_after_ms = retry_after_ms
        self.status = status
        super().__init__(f"{code}: {self.detail}")

    @classmethod
    def from_polite(cls, exc: Any) -> ExtensionError:
        """Adopt a :class:`polite_http.PoliteHttpError` verbatim (the
        vendored runtime already speaks the charter model)."""
        return cls(
            exc.code,
            exc.detail,
            retryable=exc.retryable,
            retry_after_ms=getattr(exc, "retry_after_ms", None),
            status=getattr(exc, "status", None),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            # 7E wire truth: the serialized detail is the bounded object;
            # the in-process `.detail` stays the capped diagnostic string.
            "detail": {"message": self.detail[:400]},
            "retryable": self.retryable,
        }
        if self.retry_after_ms is not None:
            payload["retryAfterMs"] = self.retry_after_ms
        return payload


_SEARCH_KIND_MAP: dict[str, str] = {
    "missing_key": "needs-secret",
    "missing_config": "invalid",
    "unknown_type": "invalid",
    "bad_request": "invalid",
    "auth": "auth",
    "rate_limit": "rate-limited",
    "unreachable": "unreachable",
    "json_disabled": "protocol",
    "protocol": "protocol",
}

_RETRYABILITY_BY_SEARCH_KIND: dict[str, str] = {
    "missing_key": "after-config-change",
    "auth": "after-config-change",
    "rate_limit": "after-delay",
    "json_disabled": "after-config-change",
}


def to_extension_error(error: SearchError) -> ExtensionError:
    """The D4 projection: an ADR-0035 ``SearchError`` as a charter error."""
    code = _SEARCH_KIND_MAP[error.kind]
    return ExtensionError(
        code,
        error.message,
        retryable=_RETRYABILITY_BY_SEARCH_KIND.get(error.kind),
        status=getattr(error, "http_status", None),
    )
