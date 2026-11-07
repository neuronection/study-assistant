from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..storage.tokenizer_contract import (
    ChunkConfig,
    TokenizerKind,
    TokenizerSpec,
    heuristic_token_count,
)

if TYPE_CHECKING:
    from ..ai.tokenizers.service import TokenizerService

MAX_CHUNK_CHARS = 1200

TOKEN_SAFETY_MARGIN = 16


class InputTooLong(RuntimeError):
    """A single embeddable item cannot fit the model input (write failure).

    This is never a query-time degradation and never triggers a retry loop:
    the writer records the item as failed with ``reason`` and moves on.
    """

    reason = "input_too_long"

    def __init__(
        self,
        *,
        tokens: int | None = None,
        limit: int | None = None,
        detail: str = "",
    ) -> None:
        self.tokens = tokens
        self.limit = limit
        self.detail = detail
        parts = ["input too long"]
        if tokens is not None:
            parts.append(f"tokens={tokens}")
        if limit is not None:
            parts.append(f"limit={limit}")
        if detail:
            parts.append(detail)
        super().__init__(" ".join(parts))


@dataclass(frozen=True)
class TokenWindow:
    """One token window of a source text: exact chars plus token offsets."""

    text: str
    char_start: int
    char_end: int
    token_start: int
    token_end: int
    token_count: int


def split_paragraphs(markdown: str) -> list[str]:
    return [part.strip() for part in markdown.split("\n\n") if part.strip()]


def _hard_split(text: str, limit: int) -> list[str]:
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def chunk_markdown(markdown: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    chunks: list[str] = []
    current = ""
    for paragraph in split_paragraphs(markdown):
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(paragraph, max_chars))
            continue
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks


def _trimmed_window(text: str, char_start: int, char_end: int) -> tuple[str, int, int] | None:
    """Trim a character window and return it with exact adjusted offsets."""
    window = text[char_start:char_end]
    stripped = window.strip()
    if not stripped:
        return None
    leading = len(window) - len(window.lstrip())
    trailing = len(window.rstrip())
    return stripped, char_start + leading, char_start + trailing


def _token_budget(
    tokenizer: TokenizerSpec,
    chunk: ChunkConfig,
    *,
    document_prefix: str | None,
    service: "TokenizerService | None",
) -> int:
    if service is None:
        from ..ai.tokenizers.service import get_tokenizer_service

        service = get_tokenizer_service()
    prefix_tokens = service.count(tokenizer, document_prefix) if document_prefix else 0
    budget = tokenizer.max_input_tokens - prefix_tokens - TOKEN_SAFETY_MARGIN
    limit = min(chunk.max_chunk_tokens, budget)
    if limit < 1:
        raise InputTooLong(
            tokens=chunk.max_chunk_tokens,
            limit=tokenizer.max_input_tokens,
            detail=f"prefix={prefix_tokens} margin={TOKEN_SAFETY_MARGIN}",
        )
    return limit


def _heuristic_windows(
    text: str,
    *,
    chunk: ChunkConfig,
    limit: int,
) -> list[TokenWindow]:
    """Conservative split for a labelled heuristic tokenizer (no token ids).

    There is no encoding to slice, so windows are cut by character length
    under both the configured char ceiling and the conservative token
    estimate. The token offsets are estimates and only as exact as the
    space's ``exact=false`` tokenizer.
    """
    windows: list[TokenWindow] = []
    start = 0
    token_cursor = 0
    total = len(text)
    while start < total:
        max_length = min(chunk.max_chars, total - start)
        if max_length < 1:
            raise InputTooLong(tokens=1, limit=limit, detail="no character fits")
        if heuristic_token_count(text[start : start + max_length]) > limit:
            low, high = 1, max_length
            while low < high:
                middle = (low + high + 1) // 2
                if heuristic_token_count(text[start : start + middle]) <= limit:
                    low = middle
                else:
                    high = middle - 1
            max_length = low
        end = start + max_length
        trimmed = _trimmed_window(text, start, end)
        if trimmed is None:
            if end >= total:
                break
            start = end
            continue
        piece, char_start, char_end = trimmed
        count = heuristic_token_count(piece)
        token_start = 0 if not windows else max(token_cursor - chunk.overlap_tokens, 0)
        token_end = token_start + count
        windows.append(
            TokenWindow(
                text=piece,
                char_start=char_start,
                char_end=char_end,
                token_start=token_start,
                token_end=token_end,
                token_count=count,
            )
        )
        token_cursor = token_end
        if end >= total:
            break
        overlap_chars = min(
            int(max_length * chunk.overlap_tokens / max(chunk.max_chunk_tokens, 1)),
            max(max_length - 1, 0),
        )
        next_start = end - overlap_chars
        start = next_start if next_start > start else end
    return windows


def chunk_tokens(
    text: str,
    *,
    tokenizer: TokenizerSpec,
    chunk: ChunkConfig,
    service: "TokenizerService | None" = None,
    document_prefix: str | None = None,
) -> list[TokenWindow]:
    """Split one text into overlapping token windows with exact char offsets.

    The model input budget is ``max_chunk_tokens`` **and** the model's
    ``max_input_tokens`` minus the document-prefix tokens and a small safety
    margin. ``max_chars`` is a ceiling: a window is narrowed until it fits,
    and a single item that still cannot fit raises :class:`InputTooLong`
    instead of being truncated. The heuristic tokenizer has no ids and uses
    the conservative character split (labelled approximate by its space).
    """
    if not (text or "").strip():
        return []
    limit = _token_budget(
        tokenizer,
        chunk,
        document_prefix=document_prefix,
        service=service,
    )
    if tokenizer.kind is TokenizerKind.HEURISTIC:
        return _heuristic_windows(text, chunk=chunk, limit=limit)
    if service is None:
        from ..ai.tokenizers.service import get_tokenizer_service

        service = get_tokenizer_service()

    ids, spans = service.encode_with_offsets(tokenizer, text)
    total = len(ids)
    if total < 1:
        return []
    overlap = min(chunk.overlap_tokens, max((limit - 1) // 2, 0))

    def _window(start: int, end: int) -> tuple[str, int, int] | None:
        return _trimmed_window(text, spans[start][0], spans[end - 1][1])

    windows: list[TokenWindow] = []
    start = 0
    while start < total:
        end = min(start + limit, total)
        trimmed = _window(start, end)
        while (trimmed is None or len(trimmed[0]) > chunk.max_chars) and end > start + 1:
            end -= 1
            trimmed = _window(start, end)
        if trimmed is None:
            if end >= total:
                break
            start = max(end - overlap, start + 1)
            continue
        piece, char_start, char_end = trimmed
        if len(piece) > chunk.max_chars:
            raise InputTooLong(
                tokens=end - start,
                limit=chunk.max_chars,
                detail="a single token window exceeds max_chars",
            )
        windows.append(
            TokenWindow(
                text=piece,
                char_start=char_start,
                char_end=char_end,
                token_start=start,
                token_end=end,
                token_count=end - start,
            )
        )
        if end >= total:
            break
        start = max(end - overlap, start + 1)
    return windows
