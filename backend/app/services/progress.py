"""Progress callback contract and the bounded live-indexing detail (plan 52 T5c).

Every background handler reports through one callback shape,
``report(value, stage)``. Vector jobs pass an optional third argument: a small
counters document written in the *same* ``jobs`` UPDATE as ``progress``/
``stage`` — never a second per-document write.

The detail is a closed, bounded shape: integers, a phase label and booleans
only. It never carries source ids, document text or arbitrary payloads, so a
leaked progress row cannot expose content. Callers that do not supply a
detail keep the existing two-argument semantics (the column is left alone).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any, Protocol

from app.storage.retrieval_ops import RUN_PROGRESS_PHASES

logger = logging.getLogger(__name__)

MAX_PROGRESS_COUNTER = 2_147_483_647
MAX_PROGRESS_PHASE = 40
MAX_PROGRESS_DETAIL_BYTES = 2048

_COUNTER_KEYS = (
    "processed_documents",
    "total_documents",
    "processed_chunks",
    "pending_chunks",
    "embedded_chunks",
    "skipped_chunks",
    "failed_chunks",
    "embedded_documents",
    "skipped_documents",
    "failed_documents",
    "embed_calls",
)
_OPTIONAL_COUNTER_KEYS = ("total_chunks", "tokens")
_FLAG_KEYS = ("chunks_estimated", "tokens_estimated", "exact_tokenizer", "done")

#: The carry subset a continued run resumes from (no phase/done flags).
PROGRESS_CARRY_FIELDS = (
    "processed_documents",
    "total_documents",
    "processed_chunks",
    "embedded_chunks",
    "skipped_chunks",
    "failed_chunks",
    "embedded_documents",
    "skipped_documents",
    "failed_documents",
    "embed_calls",
)

PROGRESS_DETAIL_KEYS = frozenset({"phase", *_COUNTER_KEYS, *_OPTIONAL_COUNTER_KEYS, *_FLAG_KEYS})


class ProgressCb(Protocol):
    """The vector handler progress seam; the detail may be ``None``."""

    def __call__(self, value: int, stage: str, detail: dict[str, Any] | None) -> None: ...


def _counter(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, min(value, MAX_PROGRESS_COUNTER))


def _optional_counter(value: Any) -> int | None:
    if value is None:
        return None
    return _counter(value)


def bound_progress_detail(detail: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Validate and bound a progress detail; ``None`` when it cannot be stored.

    Unknown keys are dropped (never persisted), counters are clamped to a
    non-negative 32-bit-ish range and the phase is a short closed value. The
    encoded document is capped; a caller that trips the cap gets ``None``
    rather than a write amplification bug.
    """
    if detail is None:
        return None
    if not isinstance(detail, Mapping):
        return None
    phase = str(detail.get("phase") or "queued").strip()[:MAX_PROGRESS_PHASE]
    if phase not in RUN_PROGRESS_PHASES:
        phase = "queued"
    bounded: dict[str, Any] = {"phase": phase}
    for key in _COUNTER_KEYS:
        bounded[key] = _counter(detail.get(key, 0))
    for key in _OPTIONAL_COUNTER_KEYS:
        bounded[key] = _optional_counter(detail.get(key))
    for key in _FLAG_KEYS:
        bounded[key] = bool(detail.get(key, False))
    if len(json.dumps(bounded, separators=(",", ":")).encode("utf-8")) > MAX_PROGRESS_DETAIL_BYTES:
        logger.warning("progress detail exceeded %s bytes; dropping it", MAX_PROGRESS_DETAIL_BYTES)
        return None
    return bounded


def parse_progress_carry(value: Any) -> dict[str, Any]:
    """Payload ``progress_carry`` → bounded cumulative live counters.

    This is the continuation carry: a retried/continued run resumes the bar
    with the parent's processed/total documents and chunk/token counters
    instead of resetting. Unknown keys are ignored; every counter is clamped
    and optional values stay optional (``tokens`` is ``None`` until measured).
    """
    if value in (None, "", {}):
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("progress_carry must be an object")
    carried: dict[str, Any] = {}
    for name in PROGRESS_CARRY_FIELDS:
        carried[name] = max(0, min(int(value.get(name) or 0), MAX_PROGRESS_COUNTER))
    tokens = value.get("tokens")
    carried["tokens"] = (
        min(int(tokens), MAX_PROGRESS_COUNTER)
        if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0
        else None
    )
    exact = value.get("tokens_exact")
    if exact is None:
        exact = value.get("exact_tokenizer")
    carried["tokens_exact"] = bool(exact)
    return carried


def carry_from_detail(detail: Mapping[str, Any] | None) -> dict[str, Any]:
    """The bounded carry subset of a stored detail (empty when absent)."""
    if not isinstance(detail, Mapping):
        return {}
    return parse_progress_carry(detail)


__all__ = [
    "MAX_PROGRESS_COUNTER",
    "MAX_PROGRESS_DETAIL_BYTES",
    "PROGRESS_CARRY_FIELDS",
    "PROGRESS_DETAIL_KEYS",
    "ProgressCb",
    "bound_progress_detail",
    "carry_from_detail",
    "parse_progress_carry",
]
