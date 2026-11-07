"""Process-local tokenizer registry and counting service (plan 52 T5a).

Three paths:

* **exact** ``tiktoken`` for the curated OpenAI embedding models. The BPE
  asset is bundled in ``app/data/tokenizers`` and checksum-verified; the
  service never calls ``tiktoken.get_encoding`` and never lets tiktoken
  fetch a file from the network.
* **exact** ``hf_tokenizers`` is an *interface only* in study today: the
  spec helper exists so a later plan-52 wave can pin a ``tokenizer.json``
  without a contract break, but no loader ships until study has a concrete
  Hugging Face model mapping. A spec of that kind degrades visibly to the
  heuristic rather than pretending to be exact.
* **heuristic** UTF-8/codepoint fallback from the family contract, always
  ``exact=False``. It is the only path for an unknown model, a missing
  asset, or a tokenizer family that is reserved but not shipped.

Only packaged assets are loaded; there is no request-time download, no
``tiktoken_ext`` import and no remote code. Plan 52 T5a uses the service as
the local accounting source for existing chunk/context counts; token-aware
chunk writes and the v2 space identity remain T5b/T5c.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import threading
from bisect import bisect_left as _bisect_left
from bisect import bisect_right as _bisect_right
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.storage.tokenizer_contract import (
    TokenizerKind,
    TokenizerSource,
    TokenizerSpec,
    heuristic_token_count,
)

CL100K_BASE = "cl100k_base"

# tiktoken's canonical cl100k_base BPE assets (tiktoken_ext.openai_public).
# The pattern and special-token table are constants, not code: constructing
# ``tiktoken.Encoding`` directly is what keeps the load offline.
CL100K_BASE_PAT_STR = (
    r"""'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+"""
    r"""| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s"""
)
CL100K_BASE_SPECIAL_TOKENS = {
    "<|endoftext|>": 100257,
    "<|fim_prefix|>": 100258,
    "<|fim_middle|>": 100259,
    "<|fim_suffix|>": 100260,
    "<|endofprompt|>": 100276,
}
CL100K_BASE_BPE_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"

# The packaged container is gzip so the repo carries ~0.8 MB instead of
# ~1.7 MB; its own hash is pinned too, so a swapped container fails before
# decompression.
CL100K_BASE_ASSET = "cl100k_base.tiktoken.gz"
CL100K_BASE_ASSET_SHA256 = "e97e9286f7089b64da301dec3b07bda1f270cb737153e3bff256f8aeb03e4a9a"

DEFAULT_ASSET_DIR = Path(__file__).resolve().parents[2] / "data" / "tokenizers"

# The instance-local cache is where a later HF wave may pre-seed verified
# ``tokenizer.json`` assets (``<cache>/<sha256>/tokenizer.json``). Nothing
# here ever downloads.
HF_CACHE_SUBDIR = "tokenizers"
HF_TOKENIZER_FILENAME = "tokenizer.json"
MAX_TOKENIZER_JSON_BYTES = 32 * 1024 * 1024

# Unknown/mock models get a conservative, visibly approximate limit; plan 52
# T5b/T5c owns model profiles and any write-path limit enforcement.
FALLBACK_MAX_INPUT_TOKENS = 2048
FALLBACK_IDENTIFIER = "utf8-heuristic-v1"

OPENAI_EMBEDDING_MAX_INPUT_TOKENS = 8191


class TokenizerUnavailable(RuntimeError):
    """A structured load/use failure — the caller may fall back, visibly."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


@dataclass(frozen=True)
class TokenCount:
    """One measured count plus the tokenizer that actually produced it."""

    tokens: int
    exact: bool
    tokenizer: TokenizerSpec
    degraded_reason: str | None = None


def fallback_spec(max_input_tokens: int = FALLBACK_MAX_INPUT_TOKENS) -> TokenizerSpec:
    """The conservative fallback selection, always ``exact=False``."""
    return TokenizerSpec(
        kind=TokenizerKind.HEURISTIC,
        identifier=FALLBACK_IDENTIFIER,
        max_input_tokens=max_input_tokens,
        source=TokenizerSource.FALLBACK,
    )


def tiktoken_spec(
    identifier: str = CL100K_BASE,
    *,
    max_input_tokens: int = OPENAI_EMBEDDING_MAX_INPUT_TOKENS,
    source: TokenizerSource = TokenizerSource.PROVIDER,
    artifact_sha256: str | None = CL100K_BASE_BPE_SHA256,
) -> TokenizerSpec:
    """A pinned exact tiktoken selection (only cl100k_base is bundled today)."""
    if identifier != CL100K_BASE:
        raise TokenizerUnavailable("unsupported_encoding", identifier)
    return TokenizerSpec(
        kind=TokenizerKind.TIKTOKEN,
        identifier=CL100K_BASE,
        max_input_tokens=max_input_tokens,
        source=source,
        artifact_sha256=artifact_sha256,
    )


def hf_tokenizer_spec(
    *,
    identifier: str,
    revision: str,
    artifact_sha256: str,
    max_input_tokens: int,
    source: TokenizerSource = TokenizerSource.CURATED,
) -> TokenizerSpec:
    """A pinned Hugging Face ``tokenizer.json`` selection (interface only).

    Study has no concrete HF mapping in plan 52 T5a, so the service cannot
    load this kind yet; the spec still validates and reports ``exact=true``
    because a *loaded* HF tokenizer is exact. :meth:`TokenizerService.count`
    degrades it visibly with ``unsupported_tokenizer_kind``.
    """
    return TokenizerSpec(
        kind=TokenizerKind.HF_TOKENIZERS,
        identifier=identifier,
        revision=revision,
        artifact_sha256=artifact_sha256,
        max_input_tokens=max_input_tokens,
        source=source,
    )


def default_cache_dir() -> Path:
    """The instance-local tokenizer cache (``<data_dir>/tokenizers``)."""
    from app.core.config import get_settings

    return Path(get_settings().data_dir).expanduser() / HF_CACHE_SUBDIR


def provider_class(provider_type: str | None) -> str:
    """Normalize a resolved provider type to the curated mapping key."""
    value = str(provider_type or "").strip().lower()
    if value in ("openai", "openai_compatible"):
        return "openai"
    if value == "google":
        return "google"
    if value == "anthropic":
        return "anthropic"
    if value == "decision":
        return "decision"
    if value == "mock":
        return "mock"
    return value or "unknown"


def _read_bpe_asset(
    path: Path, *, expected_gzip_sha: str, expected_bpe_sha: str
) -> dict[bytes, int]:
    try:
        container = path.read_bytes()
    except OSError as exc:
        raise TokenizerUnavailable("asset_missing", path.name) from exc
    if hashlib.sha256(container).hexdigest() != expected_gzip_sha:
        raise TokenizerUnavailable("asset_corrupt", f"{path.name}: container checksum")
    try:
        payload = gzip.decompress(container)
    except OSError as exc:
        raise TokenizerUnavailable("asset_corrupt", f"{path.name}: gzip") from exc
    if hashlib.sha256(payload).hexdigest() != expected_bpe_sha:
        raise TokenizerUnavailable("asset_corrupt", f"{path.name}: bpe checksum")
    ranks: dict[bytes, int] = {}
    for line in payload.splitlines():
        if not line:
            continue
        try:
            token, rank = line.split()
            ranks[base64.b64decode(token)] = int(rank)
        except (ValueError, TypeError) as exc:  # pragma: no cover - pinned asset
            raise TokenizerUnavailable("asset_corrupt", f"{path.name}: row") from exc
    return ranks


class TokenizerService:
    """Bounded, thread-safe process-local tokenizer cache.

    Cache identity is :attr:`TokenizerSpec.cache_key`; at most
    ``max_cached`` encoders stay resident (LRU). Loading is synchronous and
    side-effect free: packaged assets only, no network, no remote code.
    """

    def __init__(
        self,
        *,
        asset_dir: Path | None = None,
        cache_dir: Path | None = None,
        max_cached: int = 4,
    ) -> None:
        if max_cached < 1:
            raise ValueError("max_cached must be >= 1")
        self._asset_dir = Path(asset_dir) if asset_dir is not None else DEFAULT_ASSET_DIR
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._max_cached = max_cached
        self._encoders: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def cache_dir(self) -> Path:
        """The content-addressed cache directory (resolved lazily)."""
        return self._cache_dir if self._cache_dir is not None else default_cache_dir()

    @property
    def cached_count(self) -> int:
        """How many exact encoders are currently loaded (test/observability)."""
        with self._lock:
            return len(self._encoders)

    def available(self, spec: TokenizerSpec) -> bool:
        """Whether ``spec`` can be served exactly right now."""
        try:
            self._encoder(spec)
        except TokenizerUnavailable:
            return False
        return True

    def effective_spec(self, spec: TokenizerSpec) -> tuple[TokenizerSpec, str | None]:
        """The spec that will actually count, plus a degraded reason when it is not exact."""
        if spec.kind is TokenizerKind.HEURISTIC:
            return spec, None
        try:
            self._encoder(spec)
        except TokenizerUnavailable as exc:
            return fallback_spec(spec.max_input_tokens), exc.reason
        return spec, None

    def count(self, spec: TokenizerSpec, text: str) -> int:
        """Count tokens; raises :class:`TokenizerUnavailable` for a broken exact spec."""
        if spec.kind is TokenizerKind.HEURISTIC:
            return heuristic_token_count(text)
        return len(self.encode(spec, text))

    def count_or_fallback(self, spec: TokenizerSpec, text: str) -> TokenCount:
        """Count with the exact spec when possible, else the labelled fallback."""
        try:
            if spec.kind is TokenizerKind.HEURISTIC:
                return TokenCount(
                    tokens=heuristic_token_count(text),
                    exact=False,
                    tokenizer=spec,
                )
            return TokenCount(
                tokens=len(self.encode(spec, text)),
                exact=True,
                tokenizer=spec,
            )
        except TokenizerUnavailable as exc:
            return TokenCount(
                tokens=heuristic_token_count(text),
                exact=False,
                tokenizer=fallback_spec(spec.max_input_tokens),
                degraded_reason=exc.reason,
            )

    def encode(self, spec: TokenizerSpec, text: str) -> list[int]:
        """Token ids for a chunk-splitting caller (plan 52 T5b); exact specs only."""
        if spec.kind is TokenizerKind.HEURISTIC:
            raise TokenizerUnavailable("heuristic_has_no_encoding", spec.identifier)
        encoder = self._encoder(spec)
        return list(encoder.encode(text, disallowed_special=()))

    def decode(self, spec: TokenizerSpec, ids: list[int]) -> str:
        """Decode token ids back to text (round-trip proof, plan 52 T5b)."""
        if spec.kind is TokenizerKind.HEURISTIC:
            raise TokenizerUnavailable("heuristic_has_no_encoding", spec.identifier)
        return str(self._encoder(spec).decode(ids))

    def encode_with_offsets(
        self, spec: TokenizerSpec, text: str
    ) -> tuple[list[int], list[tuple[int, int]]]:
        """Encode ``text`` and return ids plus one character span per token.

        Spans are inclusive-start/exclusive-end offsets into the **input**
        text. tiktoken is a byte-level BPE whose tokens can split a
        multi-byte codepoint, so a token's byte span is widened to the whole
        codepoints it touches. A window may therefore repeat an edge
        character rather than silently dropping part of it; the composer
        writes the exact input slice.
        """
        if spec.kind is TokenizerKind.HEURISTIC:
            raise TokenizerUnavailable("heuristic_has_no_encoding", spec.identifier)
        encoder = self._encoder(spec)
        ids = list(encoder.encode(text, disallowed_special=()))
        pieces = encoder.decode_tokens_bytes(ids)
        char_offsets = [0]
        for character in text:
            char_offsets.append(char_offsets[-1] + len(character.encode("utf-8")))
        spans: list[tuple[int, int]] = []
        byte_start = 0
        for piece in pieces:
            byte_end = byte_start + len(piece)
            start = max(_bisect_right(char_offsets, byte_start) - 1, 0)
            end = min(_bisect_left(char_offsets, byte_end), len(text))
            spans.append((start, max(end, start)))
            byte_start = byte_end
        return ids, spans

    def _encoder(self, spec: TokenizerSpec) -> Any:
        key = spec.cache_key
        with self._lock:
            cached = self._encoders.get(key)
            if cached is not None:
                self._encoders.move_to_end(key)
                return cached
        encoder = self._load(spec)
        with self._lock:
            self._encoders[key] = encoder
            self._encoders.move_to_end(key)
            while len(self._encoders) > self._max_cached:
                self._encoders.popitem(last=False)
        return encoder

    def _load(self, spec: TokenizerSpec) -> Any:
        if spec.kind is TokenizerKind.HF_TOKENIZERS:
            raise TokenizerUnavailable(
                "unsupported_tokenizer_kind",
                "hf_tokenizers (interface only; no curated study mapping yet)",
            )
        if spec.kind is TokenizerKind.SENTENCEPIECE:
            raise TokenizerUnavailable(
                "unsupported_tokenizer_kind", "sentencepiece (reserved, not shipped)"
            )
        if spec.kind is not TokenizerKind.TIKTOKEN:
            raise TokenizerUnavailable("unsupported_tokenizer_kind", spec.kind.value)
        if spec.identifier != CL100K_BASE:
            raise TokenizerUnavailable("unsupported_encoding", spec.identifier)
        expected_bpe_sha = spec.artifact_sha256 or CL100K_BASE_BPE_SHA256
        path = self._asset_dir / CL100K_BASE_ASSET
        ranks = _read_bpe_asset(
            path,
            expected_gzip_sha=CL100K_BASE_ASSET_SHA256,
            expected_bpe_sha=expected_bpe_sha,
        )
        try:
            import tiktoken
        except ImportError as exc:  # pragma: no cover - direct dependency
            raise TokenizerUnavailable("tiktoken_missing", "tiktoken not installed") from exc
        try:
            return tiktoken.Encoding(
                name=CL100K_BASE,
                pat_str=CL100K_BASE_PAT_STR,
                mergeable_ranks=ranks,
                special_tokens=dict(CL100K_BASE_SPECIAL_TOKENS),
            )
        except Exception as exc:  # pragma: no cover - pinned asset
            raise TokenizerUnavailable("asset_corrupt", type(exc).__name__) from exc


_DEFAULT_SERVICE: TokenizerService | None = None
_DEFAULT_LOCK = threading.Lock()


def get_tokenizer_service() -> TokenizerService:
    """The process-wide service (its cache makes repeated counts cheap)."""
    global _DEFAULT_SERVICE
    with _DEFAULT_LOCK:
        if _DEFAULT_SERVICE is None:
            _DEFAULT_SERVICE = TokenizerService()
        return _DEFAULT_SERVICE


__all__ = [
    "CL100K_BASE",
    "CL100K_BASE_BPE_SHA256",
    "DEFAULT_ASSET_DIR",
    "FALLBACK_IDENTIFIER",
    "FALLBACK_MAX_INPUT_TOKENS",
    "HF_CACHE_SUBDIR",
    "HF_TOKENIZER_FILENAME",
    "MAX_TOKENIZER_JSON_BYTES",
    "OPENAI_EMBEDDING_MAX_INPUT_TOKENS",
    "TokenCount",
    "TokenizerService",
    "TokenizerUnavailable",
    "default_cache_dir",
    "fallback_spec",
    "get_tokenizer_service",
    "hf_tokenizer_spec",
    "provider_class",
    "tiktoken_spec",
]
