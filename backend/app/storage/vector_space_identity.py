"""Reconstruct a persisted tokenizer/chunk pair from a vector-space row.

Plan 52 T5b2 persists the flattened pair on ``vector_spaces``; readers (the
store adapter, the lifecycle build result and the admin DTOs) must see the
same selection the write path used. Reconstruction never re-resolves a model
name and never guesses an exactness label.
"""

from __future__ import annotations

from typing import Any

from ..storage.tokenizer_contract import (
    ChunkConfig,
    TokenizerKind,
    TokenizerSource,
    TokenizerSpec,
)


def tokenizer_from_row(row: Any) -> TokenizerSpec | None:
    if row is None or getattr(row, "tokenizer_kind", None) is None:
        return None
    kind = TokenizerKind(str(row.tokenizer_kind))
    source = (
        TokenizerSource.FALLBACK
        if kind is TokenizerKind.HEURISTIC
        else TokenizerSource.CURATED
    )
    return TokenizerSpec(
        kind=kind,
        identifier=str(row.tokenizer_identifier or ""),
        revision=row.tokenizer_revision,
        artifact_sha256=row.tokenizer_artifact_sha256,
        exact=bool(row.tokenizer_exact),
        max_input_tokens=int(row.max_input_tokens or 1),
        source=source,
    )


def chunk_from_row(row: Any) -> ChunkConfig | None:
    if row is None or getattr(row, "tokenizer_kind", None) is None:
        return None
    return ChunkConfig(
        max_chunk_tokens=int(row.chunk_max_tokens or 0),
        overlap_tokens=int(row.chunk_overlap_tokens or 0),
        max_chars=int(row.chunk_max_chars or 0),
    )


def tokenizer_dict(row: Any) -> dict[str, Any] | None:
    tokenizer = tokenizer_from_row(row)
    if tokenizer is None:
        return None
    return {
        "kind": tokenizer.kind.value,
        "identifier": tokenizer.identifier,
        "revision": tokenizer.revision,
        "artifact_sha256": tokenizer.artifact_sha256,
        "exact": tokenizer.exact,
        "max_input_tokens": tokenizer.max_input_tokens,
    }


def chunk_dict(row: Any) -> dict[str, Any] | None:
    chunk = chunk_from_row(row)
    if chunk is None:
        return None
    return {
        "max_chunk_tokens": chunk.max_chunk_tokens,
        "overlap_tokens": chunk.overlap_tokens,
        "max_chars": chunk.max_chars,
    }


__all__ = [
    "chunk_dict",
    "chunk_from_row",
    "tokenizer_dict",
    "tokenizer_from_row",
]
