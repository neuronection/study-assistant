"""The study embedding chunk profile (plan 52 T5b2).

One resolver answers the tokenizer and token chunk budget a write should use:
an explicit admin selection when a caller supplies one, the curated OpenAI
embedding mapping, or the labelled conservative fallback. A model name alone
never selects a tokenizer.

A v2 space persists the pair on its ``vector_spaces`` row. An active v2 space
therefore reconstructs its exact profile here (no re-resolution drift), while
a v1 space has no profile and keeps the character chunker byte for
byte. The same module owns the per-item and per-request batching rules so the
write paths share one budget.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ...ai.tokenizers.accounting import accounting_for
from ...ai.tokenizers.service import get_tokenizer_service
from ...domain.models import Chunk, VectorSpace
from ...pipelines.chunking import (
    TOKEN_SAFETY_MARGIN,
    InputTooLong,
    TokenWindow,
    chunk_markdown,
    chunk_tokens,
)
from ...storage.tokenizer_contract import (
    ChunkConfig,
    TokenizerKind,
    TokenizerSpec,
)
from ...storage.vector_contract import content_hash

DEFAULT_MAX_CHUNK_TOKENS = 512
DEFAULT_OVERLAP_TOKENS = 64
DEFAULT_CHUNK_MAX_CHARS = 2400
DEFAULT_BATCH_MAX_ITEMS = 64
DEFAULT_BATCH_MAX_TOKENS = 32_000


@dataclass(frozen=True)
class ChunkProfile:
    """The tokenizer + chunk budget + request limits a write must honour."""

    tokenizer: TokenizerSpec
    chunk: ChunkConfig
    batch_max_items: int = DEFAULT_BATCH_MAX_ITEMS
    batch_max_tokens: int = DEFAULT_BATCH_MAX_TOKENS
    document_prefix: str | None = None

    @property
    def token_aware(self) -> bool:
        return True

    @property
    def exact(self) -> bool:
        return self.tokenizer.kind is not TokenizerKind.HEURISTIC

    def chunk_text(self, text: str) -> list[TokenWindow]:
        return chunk_tokens(
            text,
            tokenizer=self.tokenizer,
            chunk=self.chunk,
            document_prefix=self.document_prefix,
        )


@dataclass(frozen=True)
class WindowSpec:
    """One embeddable token window of a source chunk (before any vector)."""

    chunk_id: str
    window_index: int
    text: str
    char_start: int
    char_end: int
    token_count: int
    token_start: int
    token_end: int

    @property
    def content_hash(self) -> str:
        return content_hash(self.text)


def default_chunk_config(
    tokenizer: TokenizerSpec,
    *,
    max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    document_prefix: str | None = None,
) -> ChunkConfig:
    """A budget that fits the tokenizer's model input, or the nearest safe one."""
    service = get_tokenizer_service()
    prefix_tokens = service.count(tokenizer, document_prefix) if document_prefix else 0
    budget = tokenizer.max_input_tokens - prefix_tokens - TOKEN_SAFETY_MARGIN
    resolved_max = max(32, min(max_chunk_tokens, budget))
    resolved_overlap = min(overlap_tokens, max((resolved_max - 1) // 2, 0))
    return ChunkConfig(
        max_chunk_tokens=resolved_max,
        overlap_tokens=resolved_overlap,
        max_chars=max(max_chars, 1),
    )


def resolve_chunk_profile(
    provider_type: str | None,
    model: str | None,
    *,
    tokenizer: TokenizerSpec | None = None,
    chunk: ChunkConfig | None = None,
    document_prefix: str | None = None,
) -> ChunkProfile:
    """Resolve one effective profile (admin -> curated -> fallback)."""
    if (tokenizer is None) != (chunk is None):
        raise ValueError("tokenizer and chunk must be supplied together")
    if tokenizer is None:
        accounting = accounting_for(provider_type, model)
        tokenizer = accounting.spec
    if chunk is None:
        chunk = default_chunk_config(tokenizer, document_prefix=document_prefix)
    if not chunk.fits(tokenizer.max_input_tokens, safety_margin=TOKEN_SAFETY_MARGIN):
        raise ValueError(
            f"chunk budget {chunk.max_chunk_tokens} does not fit "
            f"max_input_tokens {tokenizer.max_input_tokens}"
        )
    return ChunkProfile(
        tokenizer=tokenizer,
        chunk=chunk,
        document_prefix=document_prefix,
    )


def profile_from_row(row: VectorSpace | None) -> ChunkProfile | None:
    """Reconstruct the persisted pair; ``None`` for a v1 space."""
    from ...storage.vector_space_identity import chunk_from_row, tokenizer_from_row

    tokenizer = tokenizer_from_row(row)
    chunk = chunk_from_row(row)
    if tokenizer is None or chunk is None:
        return None
    return ChunkProfile(
        tokenizer=tokenizer,
        chunk=chunk,
        document_prefix=row.document_prefix if row is not None else None,
    )


def profile_for_space(session: Session, space_id: str | None = None) -> ChunkProfile | None:
    """The persisted profile of one space (default: the active space)."""
    if space_id is None:
        from ...storage.vector_store import StudyVectorStore

        space = StudyVectorStore(session).content_space()
        if space is None:
            return None
        space_id = space.space_id
    row = session.get(VectorSpace, str(space_id))
    return profile_from_row(row)


def assignment_profile(session: Session) -> ChunkProfile:
    """The profile the current embeddings assignment resolves to."""
    from ...ai.tokenizers.accounting import embedding_model_pair

    provider_type, model = embedding_model_pair(session)
    return resolve_chunk_profile(provider_type, model)


def chunk_texts_for_space(session: Session, markdown: str) -> list[tuple[str, int]]:
    """Chunk one source for the active space: v2 tokens, else v1 characters."""
    profile = profile_for_space(session)
    if profile is None:
        from ...ai.tokenizers.accounting import embedding_accounting, token_count

        accounting = embedding_accounting(session)
        return [(text, token_count(text, accounting)) for text in chunk_markdown(markdown)]
    return [(window.text, window.token_count) for window in profile.chunk_text(markdown)]


def window_specs_for_chunk(chunk: Chunk, profile: ChunkProfile) -> list[WindowSpec]:
    """Every token window of one source chunk under ``profile``."""
    text = str(chunk.text or "")
    return [
        WindowSpec(
            chunk_id=str(chunk.id),
            window_index=index,
            text=window.text,
            char_start=window.char_start,
            char_end=window.char_end,
            token_count=window.token_count,
            token_start=window.token_start,
            token_end=window.token_end,
        )
        for index, window in enumerate(profile.chunk_text(text))
    ]


def batch_window_specs(
    specs: list[WindowSpec],
    profile: ChunkProfile,
    *,
    max_items: int | None = None,
) -> list[list[WindowSpec]]:
    """Split windows by the per-request item count and token sum.

    The per-item ``max_input_tokens`` budget (prefix plus safety margin
    included) is checked first and surfaces :class:`InputTooLong`; the batch
    limits only decide where a request ends. ``max_items`` can tighten the
    profile's request bound (the reindex payload's own ``batch_size``).
    """
    service = get_tokenizer_service()
    prefix_tokens = (
        service.count(profile.tokenizer, profile.document_prefix) if profile.document_prefix else 0
    )
    counts: list[int] = []
    for spec in specs:
        count = spec.token_count
        if count + prefix_tokens + TOKEN_SAFETY_MARGIN > profile.tokenizer.max_input_tokens:
            raise InputTooLong(
                tokens=count,
                limit=profile.tokenizer.max_input_tokens,
                detail=f"prefix={prefix_tokens} margin={TOKEN_SAFETY_MARGIN}",
            )
        counts.append(count)
    item_limit = max(profile.batch_max_items, 1)
    if max_items is not None:
        item_limit = max(min(item_limit, int(max_items)), 1)
    batches: list[list[WindowSpec]] = []
    current: list[WindowSpec] = []
    current_tokens = 0
    for spec, count in zip(specs, counts, strict=True):
        cost = count + prefix_tokens
        if current and (
            len(current) >= item_limit or current_tokens + cost > profile.batch_max_tokens
        ):
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(spec)
        current_tokens += cost
    if current:
        batches.append(current)
    return batches


__all__ = [
    "DEFAULT_BATCH_MAX_ITEMS",
    "DEFAULT_BATCH_MAX_TOKENS",
    "DEFAULT_CHUNK_MAX_CHARS",
    "DEFAULT_MAX_CHUNK_TOKENS",
    "DEFAULT_OVERLAP_TOKENS",
    "ChunkProfile",
    "WindowSpec",
    "assignment_profile",
    "batch_window_specs",
    "chunk_texts_for_space",
    "default_chunk_config",
    "profile_for_space",
    "profile_from_row",
    "resolve_chunk_profile",
    "window_specs_for_chunk",
]
