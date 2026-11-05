# VENDORED FILE — family canonical (ADR-0031 / ADR-0051).
# Synced byte-identically from the family tokenizer contract and
# checked by the family wiring verifier; the shared fixture table loads
# alongside it. NEVER edit the vendored copy in-repo — change the family
# canonical, then re-run the sync.
"""Family tokenizer and chunk-configuration contract (plan 52 T0) — the law.

This module is additive to :mod:`vector_contract` and :mod:`retrieval_ops`:
it pins the vocabulary that a tokenizer selection and a token-aware chunk
configuration must use, **without** changing ``space_key`` or
``IndexRecord``. The space-key fold and the persisted ``token_count``
columns arrive with plan 52 T3; until then a tokenizer is evidence and
configuration, never a write-path identity.

**Exact or labelled.** A :class:`TokenizerSpec` either names a pinned,
checksum-verified tokenizer (``exact=True``) or declares the conservative
heuristic fallback (``exact=False``). There is no silent "characters are
tokens": every consumer must surface the flag and the source.

**No network, no code.** A non-heuristic spec carries an
``artifact_sha256``; consumers load packaged/local assets only and verify
the checksum before use. No spec ever implies an automatic download.

**Chunk bounds.** A :class:`ChunkConfig` is valid only when the overlap
stays below half the chunk size and the chunk budget fits the model input
once prefixes and the safety margin are added. Reference defaults belong
to a model profile (plan 52 T2), not to this module.

Pure stdlib — no SQLAlchemy, provider SDK or network. The fixture table
(``contracts/tokenizer-contract.fixtures.json``) is the cross-product
acceptance wall for this module.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

TOKENIZER_CONTRACT_VERSION = "1"
TOKENIZER_SCHEMA_VERSION = 1

# The conservative fallback: ceil(utf8_bytes / 2) + ceil(codepoints / 8).
# Two bytes per token is roughly twice as conservative as English BPE text
# (~4 bytes/token) and the codepoint term covers scripts that encode to one
# token per character or worse. The estimate is deliberately an upper
# bound, never a promise: callers must keep ``exact=False`` visible.
HEURISTIC_BYTES_PER_TOKEN = 2
HEURISTIC_CODEPOINT_DIVISOR = 8

MIN_MAX_CHUNK_TOKENS = 32
MIN_MAX_CHARS = 1


class TokenizerKind(StrEnum):
    """The tokenizer families the contract can name.

    ``SENTENCEPIECE`` is **reserved**: the vocabulary is closed now so a
    later model that only ships a ``.model`` file needs no contract break,
    but no shipped implementation loads it in plan 52 v1.
    """

    TIKTOKEN = "tiktoken"
    HF_TOKENIZERS = "hf_tokenizers"
    SENTENCEPIECE = "sentencepiece"
    HEURISTIC = "heuristic"


# ``sentencepiece`` is reserved; the other kinds are in force. Whether a
# product has shipped an HF loader yet is a service-level capability, not a
# contract change (Career ships tiktoken + heuristic in plan 52 T1-min).
RESERVED_TOKENIZER_KINDS = (TokenizerKind.SENTENCEPIECE,)


class TokenizerSource(StrEnum):
    """Where the selection came from (resolution order, plan 52 §3.2)."""

    PROVIDER = "provider"
    CURATED = "curated"
    ADMIN = "admin"
    FALLBACK = "fallback"


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _positive_int(value: Any, field: str, *, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _sha256(value: Any, field: str) -> str:
    text = _text(value, field).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{field} must be a 64-character lowercase sha256")
    return text


def _canonical(parts: tuple[str, ...]) -> str:
    return "".join(f"{len(part)}:{part}" for part in parts)


def heuristic_token_count(text: str) -> int:
    """Conservative token estimate for text without an exact tokenizer.

    ``ceil(utf8_bytes / 2) + ceil(codepoints / 8)`` — an upper-bound-style
    estimate that stays above measured ``cl100k_base`` counts for English,
    Greek, German, CJK and code/markdown text (pinned in the fixture
    table). It is never reported as exact.
    """
    if not text:
        return 0
    utf8_bytes = len(text.encode("utf-8"))
    codepoints = len(text)
    return max(
        1,
        -(-utf8_bytes // HEURISTIC_BYTES_PER_TOKEN)
        + -(-codepoints // HEURISTIC_CODEPOINT_DIVISOR),
    )


class TokenizerSpec:
    """One pinned tokenizer selection (plan 52 §3.1).

    ``identifier`` is the encoding/tokenizer name (``cl100k_base``,
    ``org/model``); ``revision`` is a pinned commit/tag for a model
    repository; ``artifact_sha256`` is the checksum of the packaged or
    local tokenizer artifact. ``max_input_tokens`` is the model input
    limit this selection is valid for, duplicated here because it travels
    with the tokenizer in every space/report DTO.
    """

    __slots__ = (
        "artifact_sha256",
        "exact",
        "identifier",
        "kind",
        "max_input_tokens",
        "revision",
        "source",
    )

    def __init__(
        self,
        *,
        kind: TokenizerKind | str,
        identifier: str,
        max_input_tokens: int,
        source: TokenizerSource | str = TokenizerSource.FALLBACK,
        exact: bool | None = None,
        revision: str | None = None,
        artifact_sha256: str | None = None,
    ) -> None:
        try:
            resolved_kind = TokenizerKind(str(kind))
        except ValueError:
            raise ValueError(f"kind must be one of {tuple(TokenizerKind)}") from None
        try:
            resolved_source = TokenizerSource(str(source))
        except ValueError:
            raise ValueError(f"source must be one of {tuple(TokenizerSource)}") from None
        resolved_identifier = _text(identifier, "identifier")
        resolved_max = _positive_int(max_input_tokens, "max_input_tokens")
        resolved_revision = _optional_text(revision, "revision")
        resolved_sha = (
            None if artifact_sha256 is None else _sha256(artifact_sha256, "artifact_sha256")
        )
        if exact is None:
            resolved_exact = resolved_kind is not TokenizerKind.HEURISTIC
        else:
            if not isinstance(exact, bool):
                raise ValueError("exact must be a boolean")
            resolved_exact = exact
        if resolved_kind is TokenizerKind.HEURISTIC and resolved_exact:
            raise ValueError("a heuristic tokenizer is always exact=false")
        if resolved_kind is not TokenizerKind.HEURISTIC and not resolved_exact:
            raise ValueError(f"a {resolved_kind.value} tokenizer is always exact=true")
        if resolved_kind is not TokenizerKind.HEURISTIC and resolved_sha is None:
            raise ValueError(f"a {resolved_kind.value} tokenizer needs artifact_sha256")
        if resolved_kind in (TokenizerKind.HF_TOKENIZERS, TokenizerKind.SENTENCEPIECE):
            if resolved_revision is None:
                raise ValueError(f"a {resolved_kind.value} tokenizer needs a pinned revision")
        self.kind = resolved_kind
        self.identifier = resolved_identifier
        self.revision = resolved_revision
        self.artifact_sha256 = resolved_sha
        self.exact = resolved_exact
        self.max_input_tokens = resolved_max
        self.source = resolved_source

    @property
    def cache_key(self) -> str:
        """Stable process-local cache key for the loaded tokenizer object."""
        return hashlib.sha256(
            _canonical(
                (
                    self.kind.value,
                    self.identifier,
                    self.revision or "",
                    self.artifact_sha256 or "",
                    str(self.max_input_tokens),
                    "1" if self.exact else "0",
                    self.source.value,
                )
            ).encode("utf-8")
        ).hexdigest()

    @property
    def identity(self) -> str:
        """Readable identity for reports; never a secret, never raw text."""
        revision = f"@{self.revision}" if self.revision else ""
        checksum = f"#{self.artifact_sha256[:12]}" if self.artifact_sha256 else ""
        return f"{self.kind.value}:{self.identifier}{revision}{checksum}"

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe serialization (the schema version always travels)."""
        return {
            "schema_version": TOKENIZER_SCHEMA_VERSION,
            "kind": self.kind.value,
            "identifier": self.identifier,
            "revision": self.revision,
            "artifact_sha256": self.artifact_sha256,
            "exact": self.exact,
            "max_input_tokens": self.max_input_tokens,
            "source": self.source.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TokenizerSpec:
        if not isinstance(payload, Mapping):
            raise ValueError("tokenizer spec payload must be a mapping")
        version = payload.get("schema_version", TOKENIZER_SCHEMA_VERSION)
        if version != TOKENIZER_SCHEMA_VERSION:
            raise ValueError(
                f"tokenizer spec schema_version {version!r} != {TOKENIZER_SCHEMA_VERSION}"
            )
        known = {
            "schema_version",
            "kind",
            "identifier",
            "revision",
            "artifact_sha256",
            "exact",
            "max_input_tokens",
            "source",
        }
        unknown = set(payload) - known
        if unknown:
            raise ValueError(f"unknown tokenizer spec field(s): {sorted(unknown)}")
        return cls(
            kind=payload.get("kind"),
            identifier=payload.get("identifier"),
            revision=payload.get("revision"),
            artifact_sha256=payload.get("artifact_sha256"),
            exact=payload.get("exact"),
            max_input_tokens=payload.get("max_input_tokens"),
            source=payload.get("source", TokenizerSource.FALLBACK),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TokenizerSpec):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __hash__(self) -> int:
        return hash(self.cache_key)

    def __repr__(self) -> str:
        return f"TokenizerSpec({self.identity!r}, exact={self.exact})"


class ChunkConfig:
    """A token-aware chunk configuration (plan 52 §4).

    ``max_chunk_tokens`` is the split target, ``overlap_tokens`` the
    context carried between windows, ``max_chars`` the safety ceiling for
    pathological input. ``overlap_tokens * 2 < max_chunk_tokens`` keeps
    the split progressing; a config that cannot fit the model input after
    prefixes and the safety margin is rejected by :meth:`assert_fits`.
    """

    __slots__ = ("max_chars", "max_chunk_tokens", "overlap_tokens")

    def __init__(
        self,
        *,
        max_chunk_tokens: int,
        max_chars: int,
        overlap_tokens: int = 0,
    ) -> None:
        resolved_max = _positive_int(
            max_chunk_tokens, "max_chunk_tokens", minimum=MIN_MAX_CHUNK_TOKENS
        )
        resolved_overlap = _positive_int(overlap_tokens, "overlap_tokens", minimum=0)
        resolved_chars = _positive_int(max_chars, "max_chars", minimum=MIN_MAX_CHARS)
        if resolved_overlap * 2 >= resolved_max:
            raise ValueError("overlap_tokens must stay below half of max_chunk_tokens")
        self.max_chunk_tokens = resolved_max
        self.overlap_tokens = resolved_overlap
        self.max_chars = resolved_chars

    @property
    def fingerprint(self) -> str:
        """Stable sha256 of the configuration (T3 folds it into space_key)."""
        return hashlib.sha256(
            _canonical(
                (
                    str(self.max_chunk_tokens),
                    str(self.overlap_tokens),
                    str(self.max_chars),
                )
            ).encode("utf-8")
        ).hexdigest()

    def fits(
        self,
        max_input_tokens: int,
        *,
        prefix_tokens: int = 0,
        safety_margin: int = 0,
    ) -> bool:
        """Whether one chunk plus prefixes/safety stays inside the model input."""
        limit = _positive_int(max_input_tokens, "max_input_tokens")
        prefix = _positive_int(prefix_tokens, "prefix_tokens", minimum=0)
        margin = _positive_int(safety_margin, "safety_margin", minimum=0)
        return self.max_chunk_tokens + prefix + margin <= limit

    def assert_fits(
        self,
        max_input_tokens: int,
        *,
        prefix_tokens: int = 0,
        safety_margin: int = 0,
    ) -> None:
        """Raise when the chunk budget can exceed the model input."""
        if not self.fits(
            max_input_tokens,
            prefix_tokens=prefix_tokens,
            safety_margin=safety_margin,
        ):
            total = self.max_chunk_tokens + prefix_tokens + safety_margin
            raise ValueError(
                f"chunk budget {total} exceeds max_input_tokens {max_input_tokens}"
            )

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe serialization (the schema version always travels)."""
        return {
            "schema_version": TOKENIZER_SCHEMA_VERSION,
            "max_chunk_tokens": self.max_chunk_tokens,
            "overlap_tokens": self.overlap_tokens,
            "max_chars": self.max_chars,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ChunkConfig:
        if not isinstance(payload, Mapping):
            raise ValueError("chunk config payload must be a mapping")
        version = payload.get("schema_version", TOKENIZER_SCHEMA_VERSION)
        if version != TOKENIZER_SCHEMA_VERSION:
            raise ValueError(
                f"chunk config schema_version {version!r} != {TOKENIZER_SCHEMA_VERSION}"
            )
        known = {"schema_version", "max_chunk_tokens", "overlap_tokens", "max_chars"}
        unknown = set(payload) - known
        if unknown:
            raise ValueError(f"unknown chunk config field(s): {sorted(unknown)}")
        return cls(
            max_chunk_tokens=payload.get("max_chunk_tokens"),
            overlap_tokens=payload.get("overlap_tokens", 0),
            max_chars=payload.get("max_chars"),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChunkConfig):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __hash__(self) -> int:
        return hash(self.fingerprint)

    def __repr__(self) -> str:
        return (
            f"ChunkConfig(tokens={self.max_chunk_tokens}, "
            f"overlap={self.overlap_tokens}, chars={self.max_chars})"
        )


__all__ = [
    "HEURISTIC_BYTES_PER_TOKEN",
    "HEURISTIC_CODEPOINT_DIVISOR",
    "MIN_MAX_CHARS",
    "MIN_MAX_CHUNK_TOKENS",
    "RESERVED_TOKENIZER_KINDS",
    "TOKENIZER_CONTRACT_VERSION",
    "TOKENIZER_SCHEMA_VERSION",
    "ChunkConfig",
    "TokenizerKind",
    "TokenizerSource",
    "TokenizerSpec",
    "heuristic_token_count",
]
