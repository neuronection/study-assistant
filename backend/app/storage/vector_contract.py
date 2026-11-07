# VENDORED FILE — family canonical (ADR-0031 / ADR-0051).
# Synced byte-identically from the family vector-retrieval contract and
# checked by the family wiring verifier; the shared fixture table loads
# alongside it. NEVER edit the vendored copy in-repo — change the family
# canonical, then re-run the sync.
"""Family vector-retrieval contract (ADR-0051, proposed / plan 50) — the shared law.

One logical store, three deployment backends: **pgvector** on web,
**sqlite-vec** on desktop, and a capped **linear** scan when the extension
is unavailable. A *space* is a versioned embedding configuration; a
*document* is a source entity (posting, catalog job, material, skill,
profile); a *record* is one embeddable unit — a named **view** (summary,
requirements, responsibilities, skills, body) or a chunk of one. Source
text stays in the domain tables; records carry a normalized content hash
and a reference, never a second copy of the text.

The contract is pure stdlib — no SQLAlchemy, numpy, or network. SQL
adapters and domain composers stay app-side (ADR-0031); this module is the
DTOs, the backend protocol, the capability vocabulary and the
deterministic math every implementation must share.

**Hard filters are enforced per backend; safety is universal.** A search
must never return a document the caller's :class:`ScopeSpec` excludes —
PostgreSQL joins the predicate *before* the ANN scan (the "no Python
post-filter" property is PostgreSQL-only), sqlite-vec over-fetches then
post-filters (documented recall cost), and the linear backend filters
during its scan.

**Determinism and degenerate input.** ``cosine`` is total: empty,
dimension-mismatched, or zero-vector input scores ``0.0`` and never raises
(the career ``_text_hash``/cosine rules, pinned in the fixtures). Ordering
helpers break ties on the document id ascending. Exact scan is
deterministic by construction; ANN ordering is approximate and never used
as a hard gate.

The fixture table (``contracts/vector-contract.fixtures.json``) is the
cross-product acceptance wall for this module; the bench harness
(``scripts/vector-bench/``) is evidence, not the production benchmark.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

BACKEND_PGVECTOR = "pgvector"
BACKEND_SQLITE_VEC = "sqlite_vec"
BACKEND_LINEAR = "linear"

METRIC_COSINE = "cosine"
METRICS = (METRIC_COSINE,)

RRF_K = 60
EXACT_SCAN_THRESHOLD = 10_000
COVERAGE_GATE = 0.995
CANDIDATE_MULTIPLIER = 4
MAXSIM_CANDIDATE_CAP = 200
RERANK_TOP_N = 20
TOP_MEAN_N = 2
EF_SEARCH_DEFAULT = 40
LINEAR_CAP_ROWS = 50_000
SQLITE_VEC_RECOMMENDED_ROWS = 100_000

V1_VIEWS = ("summary", "requirements", "responsibilities", "skills", "body")

#: The v1 (character-chunked) space identity. A space that carries no
#: tokenizer/chunk configuration keeps exactly this pre-image, forever.
SPACE_KEY_VERSION = "1"
#: The token-aware identity (plan 52 T3b): v1 fields plus the pinned tokenizer
#: kind/identifier/revision/artifact checksum/exact flag and the chunk-config
#: fingerprint, prefixed with this marker. ``space_key`` never emits it by
#: accident — a v2 key requires an explicit tokenizer *and* chunk config.
SPACE_KEY_VERSION_V2 = "2"


class TokenizerIdentity(Protocol):
    """Structural shape of ``tokenizer_contract.TokenizerSpec``.

    ``vector_contract`` stays standalone (it is loaded directly by the dev
    fixture wall), so it never imports the tokenizer module. Anything with
    these attributes is a valid selection; the tokenizer contract owns the
    exactness/checksum rules.
    """

    kind: Any
    identifier: str
    revision: str | None
    artifact_sha256: str | None
    exact: bool
    max_input_tokens: int


class ChunkIdentity(Protocol):
    """Structural shape of ``tokenizer_contract.ChunkConfig``."""

    max_chunk_tokens: int
    overlap_tokens: int
    max_chars: int

    @property
    def fingerprint(self) -> str: ...


class SpaceStatus(StrEnum):
    """Space lifecycle (§3.1): one ``active`` space per name at a time."""

    ACTIVE = "active"
    BUILDING = "building"
    RETIRED = "retired"


class DegradedReason(StrEnum):
    """Structured lexical-fallback reasons (§4.2) — never a silent fallback."""

    PROVIDER_UNASSIGNED = "provider_unassigned"
    EMBED_FAILED = "embed_failed"
    INDEX_MISSING = "index_missing"
    SPACE_MISMATCH = "space_mismatch"
    OVER_CAP = "over_cap"


class ScopeEnforcement(StrEnum):
    """How a backend applies the hard scope filter (§2 rule 3)."""

    PRE_JOIN = "pre_join"
    OVERFETCH_POSTFILTER = "overfetch_postfilter"
    IN_SCAN = "in_scan"


@dataclass(frozen=True)
class BackendCaps:
    """Capability metadata a backend publishes (§4)."""

    ann: bool
    max_dim: int
    max_recommended_rows: int
    scope_enforcement: ScopeEnforcement


BACKEND_CAPS: Mapping[str, BackendCaps] = {
    BACKEND_PGVECTOR: BackendCaps(
        ann=True,
        max_dim=3072,
        max_recommended_rows=10_000_000,
        scope_enforcement=ScopeEnforcement.PRE_JOIN,
    ),
    BACKEND_SQLITE_VEC: BackendCaps(
        ann=True,
        max_dim=3072,
        max_recommended_rows=SQLITE_VEC_RECOMMENDED_ROWS,
        scope_enforcement=ScopeEnforcement.OVERFETCH_POSTFILTER,
    ),
    BACKEND_LINEAR: BackendCaps(
        ann=False,
        max_dim=3072,
        max_recommended_rows=LINEAR_CAP_ROWS,
        scope_enforcement=ScopeEnforcement.IN_SCAN,
    ),
}


def _is_stored_space_key(value: str) -> bool:
    """True when ``value`` is a lowercase hex sha256 (64 characters)."""
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _tokenizer_parts(tokenizer: TokenizerIdentity) -> tuple[str, ...]:
    """The v2 identity component of a tokenizer selection, normalized.

    ``kind`` may be a string or a ``StrEnum``; ``str()`` yields the stable
    value for both. ``revision``/``artifact_sha256`` are optional only where
    the tokenizer contract allows it (tiktoken has no revision; the heuristic
    has neither); this module never re-derives the exactness rules.
    """
    kind = getattr(tokenizer, "kind", None)
    identifier = getattr(tokenizer, "identifier", None)
    exact = getattr(tokenizer, "exact", None)
    if kind is None or not str(kind).strip():
        raise ValueError("VectorSpace.tokenizer.kind must be non-empty")
    if identifier is None or not str(identifier).strip():
        raise ValueError("VectorSpace.tokenizer.identifier must be non-empty")
    if not isinstance(exact, bool):
        raise ValueError("VectorSpace.tokenizer.exact must be a boolean")
    return (
        normalize_text(str(kind)),
        normalize_text(str(identifier)),
        normalize_text(str(getattr(tokenizer, "revision", None) or "")),
        normalize_text(str(getattr(tokenizer, "artifact_sha256", None) or "")),
        "1" if exact else "0",
    )


def _chunk_fingerprint(chunk: ChunkIdentity) -> str:
    fingerprint = getattr(chunk, "fingerprint", None)
    if not isinstance(fingerprint, str) or not _is_stored_space_key(fingerprint):
        raise ValueError("VectorSpace.chunk.fingerprint must be a 64-character sha256")
    return normalize_text(fingerprint)


@dataclass(frozen=True)
class VectorSpace:
    """A versioned embedding space (§3.1) — the only place a model/dim is trusted.

    ``key`` is the stable identity products stamp into derived rows (e.g.
    career's ``mapping_features``) so a cutover can re-enqueue stale
    semantic decisions (§7.2). ``stored_key`` is that identity **persisted on
    the space row when the space is created**: it is the cutover identity and
    is never recomputed across tokenizer/chunker version boundaries. When it
    is present, ``key`` returns it verbatim; only an unstored DTO falls back
    to the pre-image. ``tokenizer``/``chunk`` are both present on a
    token-aware v2 space (plan 52 T3b) and both absent on a v1 space;
    a half-configured space is refused. ``space_id``/``index_table`` are the
    persistence handles: ``index_table`` is ``None`` while the linear backend
    is active.
    """

    name: str
    provider: str
    model: str
    dim: int
    metric: str = METRIC_COSINE
    normalize: bool = True
    query_prefix: str | None = None
    document_prefix: str | None = None
    chunker_version: str = "1"
    composer_version: str = "1"
    status: SpaceStatus = SpaceStatus.ACTIVE
    space_id: str | None = None
    index_table: str | None = None
    stored_key: str | None = None
    tokenizer: TokenizerIdentity | None = None
    chunk: ChunkIdentity | None = None

    def __post_init__(self) -> None:
        for name in ("name", "provider", "model"):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"VectorSpace.{name} must be non-empty")
        if not isinstance(self.dim, int) or isinstance(self.dim, bool) or self.dim < 1:
            raise ValueError("VectorSpace.dim must be a positive integer")
        if self.metric not in METRICS:
            raise ValueError(f"VectorSpace.metric must be one of {METRICS}")
        if str(self.status) not in {member.value for member in SpaceStatus}:
            raise ValueError(f"VectorSpace.status must be one of {tuple(SpaceStatus)}")
        if self.stored_key is not None and not _is_stored_space_key(self.stored_key):
            raise ValueError(
                "VectorSpace.stored_key must be a 64-character lowercase hex sha256"
            )
        if (self.tokenizer is None) != (self.chunk is None):
            raise ValueError(
                "VectorSpace.tokenizer and VectorSpace.chunk must be present together"
            )
        if self.tokenizer is not None:
            if str(self.chunker_version) != SPACE_KEY_VERSION_V2:
                raise ValueError(
                    "a token-aware space requires chunker_version='2'"
                )
            _tokenizer_parts(self.tokenizer)
            _chunk_fingerprint(self.chunk)  # type: ignore[arg-type]

    @property
    def token_aware(self) -> bool:
        """True when this space carries a pinned tokenizer + chunk config."""
        return self.tokenizer is not None and self.chunk is not None

    @property
    def key(self) -> str:
        if self.stored_key is not None:
            return self.stored_key
        if self.token_aware:
            return space_key_token_aware(
                self.provider,
                self.model,
                self.dim,
                self.normalize,
                self.query_prefix,
                self.document_prefix,
                self.chunker_version,
                self.composer_version,
                tokenizer=self.tokenizer,  # type: ignore[arg-type]
                chunk=self.chunk,  # type: ignore[arg-type]
            )
        return space_key(
            self.provider,
            self.model,
            self.dim,
            self.normalize,
            self.query_prefix,
            self.document_prefix,
            self.chunker_version,
            self.composer_version,
        )


@dataclass(frozen=True)
class IndexRecord:
    """One embeddable unit (§3.3): a whole view or a chunk of one."""

    record_id: str
    document_id: str
    view: str
    chunk_index: int
    embedding: tuple[float, ...]
    content_hash: str = ""
    char_start: int | None = None
    char_end: int | None = None
    token_count: int | None = None
    token_start: int | None = None
    token_end: int | None = None

    def __post_init__(self) -> None:
        for name in ("record_id", "document_id", "view"):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"IndexRecord.{name} must be non-empty")
        if not isinstance(self.chunk_index, int) or self.chunk_index < 0:
            raise ValueError("IndexRecord.chunk_index must be a non-negative integer")
        if not self.embedding:
            raise ValueError("IndexRecord.embedding must be non-empty")
        tokens = (self.token_count, self.token_start, self.token_end)
        if any(value is not None for value in tokens) and any(
            value is None for value in tokens
        ):
            raise ValueError(
                "IndexRecord token_count/token_start/token_end must be all present or all None"
            )
        for name, value in (
            ("token_count", self.token_count),
            ("token_start", self.token_start),
            ("token_end", self.token_end),
        ):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"IndexRecord.{name} must be a non-negative integer")
        if (
            self.token_start is not None
            and self.token_end is not None
            and self.token_end < self.token_start
        ):
            raise ValueError("IndexRecord.token_end must be >= token_start")
        if self.token_count is not None and self.token_end is not None and self.token_start is not None:
            if self.token_count != self.token_end - self.token_start:
                raise ValueError(
                    "IndexRecord.token_count must equal token_end - token_start"
                )


@dataclass(frozen=True)
class IndexHit:
    """A raw backend hit (§4): ``distance = 1 - similarity`` (cosine)."""

    record_id: str
    document_id: str
    view: str
    distance: float
    similarity: float
    backend: str


@dataclass(frozen=True)
class ScopeSpec:
    """Opaque product-built hard filter over allowed documents (§4).

    ``kind`` is the product's predicate discriminator; ``predicate`` is the
    opaque payload the product's adapter compiles. The contract never
    inspects or evaluates either. Every backend must enforce it: a search
    may never return a document this spec excludes (the universal safety
    invariant), including after sqlite-vec's bounded over-fetch.
    """

    kind: str
    predicate: Any


@dataclass(frozen=True)
class RetrievalHit:
    """One fused document hit (§6): raw per-view cosine is kept for explainability."""

    document_id: str
    fused_score: float
    per_view: Mapping[str, float] = field(default_factory=dict)
    backend: str = ""


@dataclass(frozen=True)
class RetrievalResult:
    """The read-path result vocabulary (§6): hits plus the degradation reason."""

    hits: tuple[RetrievalHit, ...] = ()
    backend: str = ""
    degraded: DegradedReason | None = None


@dataclass(frozen=True)
class BackendHealth:
    """Per-space backend health (§4) — surfaced by the admin status reads."""

    ok: bool
    detail: str = ""


class VectorBackend(Protocol):
    """The one backend seam (§4): product code never issues dialect SQL outside it.

    ``name`` is one of ``BACKEND_CAPS``; ``capabilities`` publishes the
    engine's limits. Implementations: ``PgVectorBackend`` (filtered ANN,
    HNSW), ``SqliteVecBackend`` (vec0 + rowid map + over-fetch), and
    ``LinearVectorBackend`` (``vector_records.embedding`` + this module's
    cosine).
    """

    name: str
    capabilities: BackendCaps

    def ensure_space(self, space: VectorSpace) -> None: ...

    def upsert(self, space: VectorSpace, records: Sequence[IndexRecord]) -> None: ...

    def delete_document(self, space: VectorSpace, document_id: str) -> None: ...

    def search(
        self,
        space: VectorSpace,
        query: Sequence[float],
        *,
        views: Sequence[str],
        scope: ScopeSpec,
        limit: int,
        ef_search: int | None = None,
    ) -> list[IndexHit]: ...

    def count(self, space: VectorSpace) -> int: ...

    def health(self, space: VectorSpace) -> BackendHealth: ...


def normalize_text(text: str) -> str:
    """Career's ``_text_hash`` normalization: whitespace-fold + lowercase."""
    return " ".join((text or "").split()).lower()


def content_hash(text: str) -> str:
    """SHA-256 of :func:`normalize_text` — the family content-hash rule (§3.2)."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Pure cosine similarity; empty, mismatched or zero-vector input scores 0.0."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for left, right in zip(a, b, strict=True):
        dot += left * right
        norm_a += left * left
        norm_b += right * right
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / math.sqrt(norm_a * norm_b)


def normalize(vector: Sequence[float]) -> list[float]:
    """L2-normalize; a zero vector stays zeros (unrankable, never an error)."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def rrf_merge(
    ranked_lists: Sequence[Sequence[str]],
    k: int = RRF_K,
    weights: Sequence[float] | None = None,
) -> dict[str, float]:
    """Weighted reciprocal-rank fusion (§6), career's RRF semantics plus weights.

    ``score(d) = Σ over lists  weight / (k + position(d))`` with 1-based
    positions; an item absent from a list earns nothing from it. Weights
    default to ``1.0`` per list and must match ``ranked_lists`` in length.
    """
    if k < 1:
        raise ValueError("rrf_merge: k must be >= 1")
    if weights is not None and len(weights) != len(ranked_lists):
        raise ValueError("rrf_merge: weights must match ranked_lists")
    scores: dict[str, float] = {}
    for index, ranked in enumerate(ranked_lists):
        weight = 1.0 if weights is None else float(weights[index])
        for position, item_id in enumerate(ranked, start=1):
            key = str(item_id)
            scores[key] = scores.get(key, 0.0) + weight / (k + position)
    return scores


def fused_order(scores: Mapping[str, float]) -> list[str]:
    """Ids by fused score descending; ties break on id ascending (§6)."""
    return sorted(scores, key=lambda item: (-scores[item], item))


def maxsim(
    queries: Sequence[Sequence[float]],
    documents: Sequence[Sequence[float]],
) -> float:
    """Sum over query vectors of the max cosine against the document vectors (§7.2)."""
    if not queries or not documents:
        return 0.0
    total = 0.0
    for query in queries:
        total += max(cosine(query, document) for document in documents)
    return total


def top_mean(scores: Sequence[float], n: int = TOP_MEAN_N) -> float:
    """Mean of the ``n`` highest scores; all of them when ``n`` exceeds the count."""
    if n < 1:
        raise ValueError("top_mean: n must be >= 1")
    if not scores:
        return 0.0
    top = sorted(scores, reverse=True)[:n]
    return sum(top) / len(top)


def _v1_space_key_parts(
    provider: str,
    model: str,
    dim: int,
    normalize: bool,
    query_prefix: str | None,
    document_prefix: str | None,
    chunker_version: str,
    composer_version: str,
) -> tuple[str, ...]:
    return (
        normalize_text(provider),
        normalize_text(model),
        str(int(dim)),
        "1" if normalize else "0",
        normalize_text(query_prefix or ""),
        normalize_text(document_prefix or ""),
        normalize_text(chunker_version),
        normalize_text(composer_version),
    )


def _hash_parts(parts: Sequence[str]) -> str:
    canonical = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def space_key(
    provider: str,
    model: str,
    dim: int,
    normalize: bool,
    query_prefix: str | None,
    document_prefix: str | None,
    chunker_version: str,
    composer_version: str,
) -> str:
    """Stable identity (SHA-256 hex) of a **v1** embedding configuration.

    The canonical pre-image is the eight fields in this order, each text
    field run through :func:`normalize_text` (so case/whitespace never
    splits a space), prefixes treating ``None`` and ``""`` as "no prefix",
    ``normalize`` as ``1``/``0``, and every part length-prefixed before the
    join — a field containing a separator cannot forge another key. Any
    semantic change (model, dim, prefixes, chunker/composer version)
    yields a different key; a cutover compares keys, never prose.

    This is the frozen v1 law: a persisted v1 key is never recomputed or
    rewritten. A token-aware space uses :func:`space_key_token_aware`.
    """
    return _hash_parts(
        _v1_space_key_parts(
            provider,
            model,
            dim,
            normalize,
            query_prefix,
            document_prefix,
            chunker_version,
            composer_version,
        )
    )


def space_key_token_aware(
    provider: str,
    model: str,
    dim: int,
    normalize: bool,
    query_prefix: str | None,
    document_prefix: str | None,
    chunker_version: str,
    composer_version: str,
    *,
    tokenizer: TokenizerIdentity,
    chunk: ChunkIdentity,
) -> str:
    """Stable identity (SHA-256 hex) of a **token-aware** embedding space.

    The pre-image is a clear :data:`SPACE_KEY_VERSION_V2` marker, then every
    v1 field in its original order, then the tokenizer identity
    (kind/identifier/revision/artifact sha256/exact) and the chunk-config
    fingerprint. A tokenizer or chunk change therefore creates a new space
    and a cutover; an existing v1 key is never re-derived through this
    function.
    """
    parts = (
        SPACE_KEY_VERSION_V2,
        *_v1_space_key_parts(
            provider,
            model,
            dim,
            normalize,
            query_prefix,
            document_prefix,
            chunker_version,
            composer_version,
        ),
        *_tokenizer_parts(tokenizer),
        _chunk_fingerprint(chunk),
    )
    return _hash_parts(parts)
