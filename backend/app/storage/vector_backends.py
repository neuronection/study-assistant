"""Study's app-side vector backend adapters (plan 50 §4, plan 51 Q3c2a).

The shared contract (DTOs, protocol, cosine, capabilities) is the vendored
``storage/vector_contract`` module. This module owns the SQL for study's
three engines over the P3a metadata layer:

* :class:`LinearBackend` — exact cosine over ``vector_records.embedding``;
* :class:`PgVectorBackend` — one HNSW ``vec_<8hex>`` table per space, scope
  joined into the ANN query;
* :class:`SqliteVecBackend` — a ``vec0`` table keyed by the study rowid rule
  (``vector_records.rowid`` is the rowid map), over-fetch then bounded
  post-filter.

Unlike career's store, study's adapter shares the caller's session: search,
ingest and purge run inside the request/job transaction, so a backend method
never opens a second transaction or commits behind the caller's back. The
store owns metadata and transaction boundaries; the backends own physical
index DDL/DML only.

The factory never fakes ANN. If the extension/driver is absent the linear
backend is returned and publishes ``ann=False``; the v1 ``chunk_vecs``
path stays the store's explicit compatibility fallback.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from array import array
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from sqlalchemy import bindparam, false, func, select, text
from sqlalchemy.orm import Session

from ..domain.models import VectorDocument, VectorRecord
from .vector_contract import (
    BACKEND_CAPS,
    BACKEND_LINEAR,
    BACKEND_PGVECTOR,
    BACKEND_SQLITE_VEC,
    CANDIDATE_MULTIPLIER,
    EF_SEARCH_DEFAULT,
    EXACT_SCAN_THRESHOLD,
    BackendCaps,
    BackendHealth,
    IndexHit,
    IndexRecord,
    ScopeSpec,
    VectorBackend,
    VectorSpace,
    cosine,
)
from .vector_schema import validate_index_table

logger = logging.getLogger(__name__)

SCOPE_ALL = "all"
SCOPE_DOCUMENTS = "documents"
SCOPE_FILTERS = "filters"

_SCOPE_COLUMNS = {
    "document_ids": VectorRecord.document_id,
    "kinds": VectorDocument.kind,
    "source_ids": VectorDocument.source_id,
    "profile_ids": VectorDocument.profile_id,
}
_SCOPE_SQL = {
    "document_ids": "r.document_id",
    "kinds": "d.kind",
    "source_ids": "d.source_id",
    "profile_ids": "d.profile_id",
}
_UUID_FILTERS = {"document_ids", "profile_ids"}

_ROWID_MASK = 0x7FFF_FFFF_FFFF_FFFF


class VectorBackendError(RuntimeError):
    """Base failure for the storage adapters."""


class VectorIndexMissing(VectorBackendError):
    """The physical index (or its extension/driver) is absent or unusable."""


class VectorSpaceMismatch(VectorBackendError, ValueError):
    """A record's embedding configuration does not match the target space."""


class VectorBackendOverCap(VectorBackendError):
    """The scoped candidate count exceeds the backend's honest row cap."""


def rowid_for(record_id: str | uuid.UUID, *, salt: int = 0) -> int:
    """Stable 63-bit rowid for a record id (the study rowid rule).

    UUID ids are hashed in their 32-character hex form, exactly like
    ``storage.vectors.rowid_for`` for chunk ids, so a computed rowid always
    agrees with the v1 ``chunk_vec_ids`` map.
    """
    try:
        payload = uuid.UUID(str(record_id)).hex.encode("utf-8")
    except (TypeError, ValueError):
        payload = str(record_id).encode("utf-8")
    if salt:
        payload += f":{salt}".encode()
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big") & _ROWID_MASK


def _canonical(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return str(value)


def _pack(embedding: Sequence[float]) -> bytes:
    return array("f", (float(value) for value in embedding)).tobytes()


def _unpack(blob: bytes | None) -> tuple[float, ...]:
    if not blob:
        return ()
    values = array("f")
    values.frombytes(bytes(blob))
    return tuple(values)


def _vector_literal(embedding: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(value)) for value in embedding) + "]"


def document_scope(document_ids: Collection[str]) -> ScopeSpec:
    """A hard filter admitting exactly ``document_ids`` (an empty set admits none)."""
    if isinstance(document_ids, (str, bytes)):
        raise ValueError("document_scope takes a collection of ids, not a single string")
    return ScopeSpec(kind=SCOPE_DOCUMENTS, predicate=frozenset(_canonical(v) for v in document_ids))


def filter_scope(**filters: Collection[str]) -> ScopeSpec:
    """A hard filter over document columns; an empty collection admits nothing.

    Recognized keys: ``document_ids``, ``kinds``, ``source_ids``, ``profile_ids``.
    ``source_ids`` filters the product's own entity ids (study material UUIDs),
    so a caller can bound a search to the material or course it already holds.
    """
    unknown = set(filters) - set(_SCOPE_COLUMNS)
    if unknown:
        raise ValueError(f"unknown scope filter(s): {sorted(unknown)}")
    return ScopeSpec(kind=SCOPE_FILTERS, predicate=dict(filters))


def _as_values(name: str, value: Any) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Collection):
        raise ValueError(f"scope filter {name} must be a collection, not {type(value).__name__}")
    return tuple(value)


def _scope_clauses(scope: ScopeSpec) -> list[Any] | None:
    """Compile the opaque scope into in-scan WHERE clauses (never a post-filter)."""
    if not isinstance(scope, ScopeSpec):
        raise TypeError("scope must be a contract ScopeSpec")
    if scope.kind == SCOPE_ALL:
        if scope.predicate not in (None, {}):
            raise ValueError("the 'all' scope takes no predicate")
        return None
    if scope.kind == SCOPE_DOCUMENTS:
        values = _as_values("document_ids", scope.predicate)
        if not values:
            return [false()]
        return [VectorRecord.document_id.in_([_canonical(value) for value in values])]
    if scope.kind == SCOPE_FILTERS:
        if not isinstance(scope.predicate, Mapping):
            raise ValueError("the 'filters' scope takes a mapping")
        unknown = set(scope.predicate) - set(_SCOPE_COLUMNS)
        if unknown:
            raise ValueError(f"unknown scope filter(s): {sorted(unknown)}")
        clauses: list[Any] = []
        for name, raw in scope.predicate.items():
            values = _as_values(name, raw)
            if not values:
                return [false()]
            bound = (
                [_canonical(value) for value in values]
                if name in _UUID_FILTERS
                else [str(value) for value in values]
            )
            clauses.append(_SCOPE_COLUMNS[name].in_(bound))
        if not clauses:
            raise ValueError("the 'filters' scope must carry at least one filter")
        return clauses
    raise ValueError(f"unsupported scope kind: {scope.kind!r}")


def _scope_sql(scope: ScopeSpec) -> tuple[str, list[Any], dict[str, Any]]:
    """The PostgreSQL form of the scope: SQL text, expanding binds, values."""
    if not isinstance(scope, ScopeSpec):
        raise TypeError("scope must be a contract ScopeSpec")
    if scope.kind == SCOPE_ALL:
        if scope.predicate not in (None, {}):
            raise ValueError("the 'all' scope takes no predicate")
        return "", [], {}
    if scope.kind == SCOPE_DOCUMENTS:
        values = _as_values("document_ids", scope.predicate)
        if not values:
            return "AND 1=0", [], {}
        return (
            "AND r.document_id IN :document_ids",
            [bindparam("document_ids", expanding=True)],
            {"document_ids": [_canonical(value) for value in values]},
        )
    if scope.kind == SCOPE_FILTERS:
        if not isinstance(scope.predicate, Mapping):
            raise ValueError("the 'filters' scope takes a mapping")
        unknown = set(scope.predicate) - set(_SCOPE_SQL)
        if unknown:
            raise ValueError(f"unknown scope filter(s): {sorted(unknown)}")
        fragments: list[str] = []
        params: list[Any] = []
        values_by_name: dict[str, Any] = {}
        for name, raw in scope.predicate.items():
            values = _as_values(name, raw)
            if not values:
                return "AND 1=0", [], {}
            bound = (
                [_canonical(value) for value in values]
                if name in _UUID_FILTERS
                else [str(value) for value in values]
            )
            fragments.append(f"AND {_SCOPE_SQL[name]} IN :{name}")
            params.append(bindparam(name, expanding=True))
            values_by_name[name] = bound
        if not fragments:
            raise ValueError("the 'filters' scope must carry at least one filter")
        return " ".join(fragments), params, values_by_name
    raise ValueError(f"unsupported scope kind: {scope.kind!r}")


class SessionVectorBackend:
    """One backend bound to the caller's session (study-owned transactions)."""

    name: str
    capabilities: BackendCaps

    def __init__(self, session: Session) -> None:
        self.session = session

    def _space_id(self, space: VectorSpace) -> str:
        if space.space_id is None:
            raise VectorBackendError(
                f"vector space {space.name!r} has no space_id — resolve it through StudyVectorStore"
            )
        return str(space.space_id)

    def _index_table(self, space: VectorSpace) -> str:
        if space.index_table is None:
            raise VectorIndexMissing(
                f"space {space.name!r} has no physical index; provision it first"
            )
        return validate_index_table(space.index_table)

    def ensure_space(self, space: VectorSpace) -> None:
        raise NotImplementedError

    def upsert(self, space: VectorSpace, records: Sequence[IndexRecord]) -> None:
        raise NotImplementedError

    def delete_document(self, space: VectorSpace, document_id: str) -> None:
        raise NotImplementedError

    def delete_record_ids(self, space: VectorSpace, record_ids: Sequence[str]) -> None:
        raise NotImplementedError

    def search(
        self,
        space: VectorSpace,
        query: Sequence[float],
        *,
        views: Sequence[str],
        scope: ScopeSpec,
        limit: int,
        ef_search: int | None = None,
    ) -> list[IndexHit]:
        raise NotImplementedError

    def count(self, space: VectorSpace) -> int:
        raise NotImplementedError

    def health(self, space: VectorSpace) -> BackendHealth:
        raise NotImplementedError


class LinearBackend(SessionVectorBackend, VectorBackend):
    """Exact cosine scan over ``vector_records.embedding`` (plan 50 §2.3).

    The fallback store for deployments without pgvector/sqlite-vec: honest
    about its absence of ANN (``capabilities.ann is False``), capped at
    ``LINEAR_CAP_ROWS`` vectors, deterministic — ties break on
    ``document_id`` then ``record_id``. Scope filters run inside the scan.
    """

    name = BACKEND_LINEAR
    capabilities = BACKEND_CAPS[BACKEND_LINEAR]

    def _assert_linear(self, space: VectorSpace) -> None:
        if space.index_table is not None:
            raise VectorSpaceMismatch(
                f"space {space.name!r} declares physical index {space.index_table!r}; "
                "the linear backend owns no index table"
            )

    def ensure_space(self, space: VectorSpace) -> None:
        self._space_id(space)
        self._assert_linear(space)

    def upsert(self, space: VectorSpace, records: Sequence[IndexRecord]) -> None:
        self._assert_linear(space)
        space_id = self._space_id(space)
        for record in records:
            if len(record.embedding) != space.dim:
                raise VectorSpaceMismatch(
                    f"record {record.record_id} has dim {len(record.embedding)}, "
                    f"space {space.name!r} expects {space.dim}"
                )
        record_ids = [str(record.record_id) for record in records]
        stored = {
            str(row.id): row
            for row in self.session.scalars(
                select(VectorRecord).where(
                    VectorRecord.id.in_(record_ids),
                    VectorRecord.space_id == space_id,
                )
            )
        }
        for record in records:
            row = stored.get(str(record.record_id))
            if row is None:
                raise VectorBackendError(
                    f"record {record.record_id} has no metadata row in space {space.name!r}"
                )
            row.embedding = _pack(record.embedding)

    def delete_document(self, space: VectorSpace, document_id: str) -> None:
        del space, document_id

    def delete_record_ids(self, space: VectorSpace, record_ids: Sequence[str]) -> None:
        del space, record_ids

    def search(
        self,
        space: VectorSpace,
        query: Sequence[float],
        *,
        views: Sequence[str],
        scope: ScopeSpec,
        limit: int,
        ef_search: int | None = None,
    ) -> list[IndexHit]:
        del ef_search
        if limit <= 0 or not views or not query:
            return []
        if len(query) != space.dim:
            logger.warning(
                "linear search query dim %s != space %r dim %s — refusing",
                len(query),
                space.name,
                space.dim,
            )
            return []
        self._assert_linear(space)
        statement = (
            select(VectorRecord, VectorDocument)
            .join(VectorDocument, VectorRecord.document_id == VectorDocument.id)
            .where(
                VectorRecord.space_id == self._space_id(space),
                VectorRecord.view.in_(list(views)),
                VectorRecord.embedding.is_not(None),
            )
        )
        clauses = _scope_clauses(scope)
        if clauses is not None:
            statement = statement.where(*clauses)
        scoped_count = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        if scoped_count > self.capabilities.max_recommended_rows:
            raise VectorBackendOverCap(
                f"{scoped_count} scoped candidates exceed the linear cap "
                f"({self.capabilities.max_recommended_rows}) — serve lexical instead"
            )
        hits: list[IndexHit] = []
        for record, document in self.session.execute(statement):
            stored = _unpack(record.embedding)
            if len(stored) != len(query):
                continue
            similarity = cosine(query, stored)
            hits.append(
                IndexHit(
                    record_id=str(record.id),
                    document_id=str(document.id),
                    view=str(record.view),
                    distance=1.0 - similarity,
                    similarity=similarity,
                    backend=self.name,
                )
            )
        hits.sort(key=lambda hit: (-hit.similarity, hit.document_id, hit.record_id))
        return hits[:limit]

    def count(self, space: VectorSpace) -> int:
        self._assert_linear(space)
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(VectorRecord)
                .where(
                    VectorRecord.space_id == self._space_id(space),
                    VectorRecord.embedding.is_not(None),
                )
            )
            or 0
        )

    def health(self, space: VectorSpace) -> BackendHealth:
        try:
            self._assert_linear(space)
            records = self.count(space)
        except VectorBackendError as exc:
            return BackendHealth(ok=False, detail=str(exc))
        if records > self.capabilities.max_recommended_rows:
            return BackendHealth(
                ok=True,
                detail=(
                    f"over the linear cap: {records} vectors > "
                    f"{self.capabilities.max_recommended_rows} recommended"
                ),
            )
        return BackendHealth(ok=True, detail=f"linear scan, {records} vector(s)")


def _version_tuple(version: str | None) -> tuple[int, ...]:
    if not version:
        return ()
    parts: list[int] = []
    for part in version.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


class PgVectorBackend(SessionVectorBackend, VectorBackend):
    """pgvector/HNSW adapter for a provisioned ``vec_<8hex>`` table.

    The scope predicate is part of the ANN query's WHERE clause (never a
    Python post-filter); ``hnsw.ef_search`` and ``hnsw.iterative_scan`` are
    set per transaction and reset after the scan. At or below
    ``EXACT_SCAN_THRESHOLD`` scoped candidates the scan is forced exact so
    small installs and parity tests stay deterministic.
    """

    name = BACKEND_PGVECTOR
    capabilities = BACKEND_CAPS[BACKEND_PGVECTOR]

    def _require_extension(self) -> str:
        value = self.session.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        if value is None:
            raise VectorIndexMissing(
                "pgvector is not installed — semantic search is unavailable on PostgreSQL"
            )
        return str(value)

    @staticmethod
    def _table_dim(session: Session, table: str) -> int | None:
        declared = session.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) "
                "FROM pg_attribute a "
                "WHERE a.attrelid = CAST(:table AS regclass) "
                "AND a.attname = 'embedding' AND NOT a.attisdropped"
            ),
            {"table": table},
        ).scalar()
        if declared is None:
            return None
        value = str(declared)
        if not value.startswith("vector(") or not value.endswith(")"):
            raise VectorIndexMissing(f"index {table!r} has unexpected embedding type {declared!r}")
        return int(value[len("vector(") : -1])

    def ensure_space(self, space: VectorSpace) -> None:
        table = self._index_table(space)
        self._require_extension()
        if not self.session.execute(
            text("SELECT to_regclass(CAST(:table AS text))"), {"table": table}
        ).scalar():
            raise VectorIndexMissing(f"index table {table!r} does not exist; provision it first")
        declared = self._table_dim(self.session, table)
        if declared != space.dim:
            raise VectorSpaceMismatch(
                f"index {table!r} is vector({declared}), space {space.name!r} expects "
                f"vector({space.dim})"
            )

    def upsert(self, space: VectorSpace, records: Sequence[IndexRecord]) -> None:
        table = self._index_table(space)
        self._require_extension()
        for record in records:
            if len(record.embedding) != space.dim:
                raise VectorSpaceMismatch(
                    f"record {record.record_id} has dim {len(record.embedding)}, "
                    f"space {space.name!r} expects {space.dim}"
                )
        statement = text(
            f"INSERT INTO {table} (record_id, embedding) "
            "VALUES (:record_id, CAST(:embedding AS vector)) "
            "ON CONFLICT (record_id) DO UPDATE SET embedding = EXCLUDED.embedding"
        )
        for record in records:
            self.session.execute(
                statement,
                {
                    "record_id": str(uuid.UUID(str(record.record_id))),
                    "embedding": _vector_literal(record.embedding),
                },
            )

    def delete_document(self, space: VectorSpace, document_id: str) -> None:
        table = self._index_table(space)
        self.session.execute(
            text(
                f"DELETE FROM {table} WHERE record_id IN ("
                "SELECT id FROM vector_records "
                "WHERE document_id = :document_id AND space_id = :space_id)"
            ),
            {"document_id": _canonical(document_id), "space_id": self._space_id(space)},
        )

    def delete_record_ids(self, space: VectorSpace, record_ids: Sequence[str]) -> None:
        if not record_ids:
            return
        table = self._index_table(space)
        self.session.execute(
            text(f"DELETE FROM {table} WHERE record_id IN :record_ids").bindparams(
                bindparam("record_ids", expanding=True)
            ),
            {"record_ids": [_canonical(value) for value in record_ids]},
        )

    def _scoped_count(self, space: VectorSpace, views: Sequence[str], scope: ScopeSpec) -> int:
        statement = (
            select(func.count())
            .select_from(VectorRecord)
            .join(VectorDocument, VectorRecord.document_id == VectorDocument.id)
            .where(
                VectorRecord.space_id == self._space_id(space),
                VectorRecord.view.in_(list(views)),
            )
        )
        clauses = _scope_clauses(scope)
        if clauses is not None:
            statement = statement.where(*clauses)
        return int(self.session.scalar(statement) or 0)

    def search(
        self,
        space: VectorSpace,
        query: Sequence[float],
        *,
        views: Sequence[str],
        scope: ScopeSpec,
        limit: int,
        ef_search: int | None = None,
    ) -> list[IndexHit]:
        if limit <= 0 or not views or not query:
            return []
        if len(query) != space.dim:
            logger.warning(
                "pgvector search query dim %s != space %r dim %s — refusing",
                len(query),
                space.name,
                space.dim,
            )
            return []
        table = self._index_table(space)
        scope_sql, scope_params, scope_values = _scope_sql(scope)
        version = self._require_extension()
        if not self.session.execute(
            text("SELECT to_regclass(CAST(:table AS text))"), {"table": table}
        ).scalar():
            raise VectorIndexMissing(f"index table {table!r} does not exist")
        scoped_count = self._scoped_count(space, views, scope)
        if scoped_count > self.capabilities.max_recommended_rows:
            raise VectorBackendOverCap(
                f"{scoped_count} scoped candidates exceed the pgvector cap "
                f"({self.capabilities.max_recommended_rows}) — serve lexical instead"
            )
        if scoped_count == 0:
            return []
        exact = scoped_count <= EXACT_SCAN_THRESHOLD
        tuning = max(int(ef_search or EF_SEARCH_DEFAULT), 1)
        self.session.execute(
            text("SELECT set_config('hnsw.ef_search', :value, true)"), {"value": str(tuning)}
        )
        if _version_tuple(version) >= (0, 8, 0):
            self.session.execute(
                text("SELECT set_config('hnsw.iterative_scan', 'relaxed_order', true)")
            )
        if exact:
            self.session.execute(text("SET LOCAL enable_indexscan = off"))
            self.session.execute(text("SET LOCAL enable_bitmapscan = off"))
            scan_limit = min(limit, scoped_count)
        else:
            scan_limit = min(max(limit * CANDIDATE_MULTIPLIER, limit), scoped_count)
        statement = text(
            f"""
            SELECT v.record_id AS record_id,
                   r.document_id AS document_id,
                   r.view AS view,
                   (v.embedding <=> CAST(:query AS vector)) AS distance
            FROM {table} v
            JOIN vector_records r ON r.id = v.record_id
            JOIN vector_documents d ON d.id = r.document_id
            WHERE r.space_id = :space_id
              AND r.view IN :views
              {scope_sql}
            ORDER BY distance ASC
            LIMIT :limit
            """
        ).bindparams(bindparam("views", expanding=True), *scope_params)
        rows = self.session.execute(
            statement,
            {
                "query": _vector_literal(query),
                "space_id": self._space_id(space),
                "views": list(views),
                "limit": scan_limit,
                **scope_values,
            },
        ).all()
        if exact:
            self.session.execute(text("RESET enable_indexscan"))
            self.session.execute(text("RESET enable_bitmapscan"))
        hits = [
            IndexHit(
                record_id=str(row.record_id),
                document_id=str(row.document_id),
                view=str(row.view),
                distance=float(row.distance),
                similarity=1.0 - float(row.distance),
                backend=self.name,
            )
            for row in rows
        ]
        hits.sort(key=lambda hit: (hit.distance, hit.document_id, hit.record_id))
        return hits[:limit]

    def count(self, space: VectorSpace) -> int:
        table = self._index_table(space)
        self._require_extension()
        if not self.session.execute(
            text("SELECT to_regclass(CAST(:table AS text))"), {"table": table}
        ).scalar():
            raise VectorIndexMissing(f"index table {table!r} does not exist")
        return int(self.session.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)

    def health(self, space: VectorSpace) -> BackendHealth:
        table = space.index_table
        if table is None:
            return BackendHealth(ok=False, detail="space has no physical index (linear backend)")
        try:
            validate_index_table(table)
            version = self._require_extension()
            if not self.session.execute(
                text("SELECT to_regclass(CAST(:table AS text))"), {"table": table}
            ).scalar():
                return BackendHealth(ok=False, detail=f"index table {table!r} is missing")
            declared = self._table_dim(self.session, table)
            if declared != space.dim:
                return BackendHealth(
                    ok=False,
                    detail=f"index {table!r} is vector({declared}), expected vector({space.dim})",
                )
            index_present = (
                self.session.execute(
                    text(
                        "SELECT 1 FROM pg_indexes WHERE tablename = :table AND indexname = :index"
                    ),
                    {"table": table, "index": f"ix_{table}_hnsw"},
                ).scalar()
                is not None
            )
            rows = int(self.session.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)
            records = int(
                self.session.scalar(
                    select(func.count())
                    .select_from(VectorRecord)
                    .where(VectorRecord.space_id == self._space_id(space))
                )
                or 0
            )
        except VectorBackendError as exc:
            return BackendHealth(ok=False, detail=str(exc))
        except Exception as exc:  # pragma: no cover - a broken DB is not "healthy"
            return BackendHealth(ok=False, detail=f"pgvector health probe failed: {exc}")
        if not index_present:
            return BackendHealth(ok=False, detail=f"index {table!r} has no HNSW cosine index")
        if rows > records:
            return BackendHealth(
                ok=False,
                detail=f"{table}: {rows} physical row(s) but only {records} metadata record(s)",
            )
        if rows < records:
            return BackendHealth(
                ok=True,
                detail=(
                    f"pgvector {version}, {table} vector({space.dim}), {rows} of "
                    f"{records} record(s) indexed (partial)"
                ),
            )
        return BackendHealth(
            ok=True,
            detail=f"pgvector {version}, {table} vector({space.dim}), {rows} row(s)",
        )


class SqliteVecBackend(SessionVectorBackend, VectorBackend):
    """sqlite-vec ``vec0`` adapter keyed by the study rowid rule.

    ``vector_records.rowid`` is the rowid map: hydration is one indexed
    lookup and the v1 ``chunk_vec_ids`` reverse map agrees for the
    ``content`` space. Scope is over-fetched then post-filtered against
    metadata; the safety invariant holds after truncation because the allowed
    record set comes from SQL, never from the ANN result itself.

    vec0 is a brute-force scan, so it can answer *exactly* when the whole
    index is requested. When the scoped candidate count is at or below
    ``EXACT_SCAN_THRESHOLD`` the adapter asks for all rows and takes the top
    ``limit`` after filtering; above it the bounded over-fetch doubles ``k``
    until the limit is met or the index is exhausted.
    """

    name = BACKEND_SQLITE_VEC
    capabilities = BACKEND_CAPS[BACKEND_SQLITE_VEC]

    @staticmethod
    def _load(session: Session) -> Any:
        try:
            import sqlite_vec
        except ImportError as exc:  # pragma: no cover - desktop extra absent
            raise VectorIndexMissing("sqlite-vec is not installed") from exc
        try:
            raw = session.connection().connection.driver_connection
            if raw is None:
                raise VectorIndexMissing("sqlite connection has no driver connection")
            raw.enable_load_extension(True)
            sqlite_vec.load(raw)
            session.connection().exec_driver_sql("SELECT vec_version()").scalar()
        except Exception as exc:
            raise VectorIndexMissing(f"sqlite-vec could not be loaded: {exc}") from exc
        return sqlite_vec

    @staticmethod
    def _table_dim(session: Session, table: str) -> int | None:
        sql = session.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": table},
        ).scalar()
        if sql is None:
            return None
        marker = "float["
        value = str(sql)
        start = value.find(marker)
        if start < 0:
            raise VectorIndexMissing(f"index {table!r} has no float[dim] embedding column")
        end = value.find("]", start)
        return int(value[start + len(marker) : end])

    def ensure_space(self, space: VectorSpace) -> None:
        table = self._index_table(space)
        self._load(self.session)
        declared = self._table_dim(self.session, table)
        if declared is None:
            raise VectorIndexMissing(f"index table {table!r} does not exist; provision it first")
        if declared != space.dim:
            raise VectorSpaceMismatch(
                f"index {table!r} is float[{declared}], space {space.name!r} expects "
                f"float[{space.dim}]"
            )

    def upsert(self, space: VectorSpace, records: Sequence[IndexRecord]) -> None:
        sqlite_vec = self._load(self.session)
        table = self._index_table(space)
        space_id = self._space_id(space)
        for record in records:
            if len(record.embedding) != space.dim:
                raise VectorSpaceMismatch(
                    f"record {record.record_id} has dim {len(record.embedding)}, "
                    f"space {space.name!r} expects {space.dim}"
                )
            record_id = _canonical(record.record_id)
            row = self.session.scalars(
                select(VectorRecord).where(
                    VectorRecord.id == record_id,
                    VectorRecord.space_id == space_id,
                )
            ).first()
            if row is None:
                raise VectorBackendError(
                    f"record {record_id} has no metadata row in space {space.name!r}"
                )
            rowid = int(row.rowid) if row.rowid is not None else rowid_for(record_id)
            if row.rowid is None:
                row.rowid = rowid
            payload = sqlite_vec.serialize_float32([float(value) for value in record.embedding])
            present = self.session.execute(
                text(f"SELECT 1 FROM {table} WHERE record_rowid = :rowid"), {"rowid": rowid}
            ).scalar()
            if present is None:
                self.session.execute(
                    text(
                        f"INSERT INTO {table} (record_rowid, embedding) VALUES (:rowid, :embedding)"
                    ),
                    {"rowid": rowid, "embedding": payload},
                )
            else:
                self.session.execute(
                    text(f"UPDATE {table} SET embedding = :embedding WHERE record_rowid = :rowid"),
                    {"rowid": rowid, "embedding": payload},
                )

    def _record_rowids(self, space: VectorSpace, record_ids: Sequence[str]) -> list[int]:
        if not record_ids:
            return []
        rows = self.session.execute(
            select(VectorRecord.rowid).where(
                VectorRecord.id.in_([_canonical(value) for value in record_ids]),
                VectorRecord.space_id == self._space_id(space),
                VectorRecord.rowid.is_not(None),
            )
        )
        return [int(value) for (value,) in rows if value is not None]

    def delete_document(self, space: VectorSpace, document_id: str) -> None:
        self._load(self.session)
        table = self._index_table(space)
        record_ids = [
            str(value)
            for value in self.session.scalars(
                select(VectorRecord.id).where(
                    VectorRecord.document_id == _canonical(document_id),
                    VectorRecord.space_id == self._space_id(space),
                )
            )
        ]
        rowids = self._record_rowids(space, record_ids)
        for start in range(0, len(rowids), 500):
            chunk = rowids[start : start + 500]
            self.session.execute(
                text(f"DELETE FROM {table} WHERE record_rowid IN :rowids").bindparams(
                    bindparam("rowids", expanding=True)
                ),
                {"rowids": chunk},
            )

    def delete_record_ids(self, space: VectorSpace, record_ids: Sequence[str]) -> None:
        if not record_ids:
            return
        self._load(self.session)
        table = self._index_table(space)
        rowids = self._record_rowids(space, record_ids)
        for start in range(0, len(rowids), 500):
            chunk = rowids[start : start + 500]
            self.session.execute(
                text(f"DELETE FROM {table} WHERE record_rowid IN :rowids").bindparams(
                    bindparam("rowids", expanding=True)
                ),
                {"rowids": chunk},
            )

    def _scoped_count(self, space: VectorSpace, views: Sequence[str], scope: ScopeSpec) -> int:
        statement = (
            select(func.count())
            .select_from(VectorRecord)
            .join(VectorDocument, VectorRecord.document_id == VectorDocument.id)
            .where(
                VectorRecord.space_id == self._space_id(space),
                VectorRecord.view.in_(list(views)),
            )
        )
        clauses = _scope_clauses(scope)
        if clauses is not None:
            statement = statement.where(*clauses)
        return int(self.session.scalar(statement) or 0)

    def _allowed_records(
        self,
        space: VectorSpace,
        rowids: Sequence[int],
        views: Sequence[str],
        scope: ScopeSpec,
    ) -> dict[int, tuple[str, str, str]]:
        if not rowids:
            return {}
        statement = (
            select(
                VectorRecord.rowid,
                VectorRecord.id,
                VectorRecord.document_id,
                VectorRecord.view,
            )
            .join(VectorDocument, VectorRecord.document_id == VectorDocument.id)
            .where(
                VectorRecord.space_id == self._space_id(space),
                VectorRecord.rowid.in_(list(rowids)),
                VectorRecord.view.in_(list(views)),
            )
        )
        clauses = _scope_clauses(scope)
        if clauses is not None:
            statement = statement.where(*clauses)
        return {
            int(record_rowid): (str(record_id), str(document_id), str(view))
            for record_rowid, record_id, document_id, view in self.session.execute(statement)
            if record_rowid is not None
        }

    def search(
        self,
        space: VectorSpace,
        query: Sequence[float],
        *,
        views: Sequence[str],
        scope: ScopeSpec,
        limit: int,
        ef_search: int | None = None,
    ) -> list[IndexHit]:
        del ef_search  # vec0 has no per-query ef_search knob
        if limit <= 0 or not views or not query:
            return []
        if len(query) != space.dim:
            logger.warning(
                "sqlite-vec search query dim %s != space %r dim %s — refusing",
                len(query),
                space.name,
                space.dim,
            )
            return []
        table = self._index_table(space)
        sqlite_vec = self._load(self.session)
        if self._table_dim(self.session, table) is None:
            raise VectorIndexMissing(f"index table {table!r} does not exist")
        total = int(self.session.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)
        if total == 0:
            return []
        if total > self.capabilities.max_recommended_rows:
            raise VectorBackendOverCap(
                f"{total} vectors exceed the sqlite-vec cap "
                f"({self.capabilities.max_recommended_rows}) — serve lexical instead"
            )
        payload = sqlite_vec.serialize_float32([float(value) for value in query])
        scoped_count = self._scoped_count(space, views, scope)
        if scoped_count == 0:
            return []
        exact = scoped_count <= EXACT_SCAN_THRESHOLD
        k = total if exact else min(max(limit * CANDIDATE_MULTIPLIER, limit), total)
        hits: list[IndexHit] = []
        while True:
            rows = self.session.execute(
                text(
                    f"SELECT record_rowid, distance FROM {table} "
                    "WHERE embedding MATCH :query AND k = :k"
                ),
                {"query": payload, "k": k},
            ).all()
            rowids = [int(row.record_rowid) for row in rows]
            allowed = self._allowed_records(space, rowids, views, scope)
            hits = []
            for row in rows:
                rowid = int(row.record_rowid)
                if rowid not in allowed:
                    continue
                record_id, document_id, view = allowed[rowid]
                distance = float(row.distance)
                hits.append(
                    IndexHit(
                        record_id=record_id,
                        document_id=document_id,
                        view=view,
                        distance=distance,
                        similarity=1.0 - distance,
                        backend=self.name,
                    )
                )
            if len(hits) >= limit or k >= total:
                break
            k = min(k * 2, total)
        if len(hits) < limit and k >= total:
            logger.info(
                "sqlite-vec scope post-filter returned %s of %s requested hit(s) for space %r",
                len(hits),
                limit,
                space.name,
            )
        hits.sort(key=lambda hit: (hit.distance, hit.document_id, hit.record_id))
        return hits[:limit]

    def count(self, space: VectorSpace) -> int:
        table = self._index_table(space)
        self._load(self.session)
        if self._table_dim(self.session, table) is None:
            raise VectorIndexMissing(f"index table {table!r} does not exist")
        return int(self.session.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)

    def health(self, space: VectorSpace) -> BackendHealth:
        table = space.index_table
        if table is None:
            return BackendHealth(ok=False, detail="space has no physical index (linear backend)")
        try:
            validate_index_table(table)
            self._load(self.session)
            declared = self._table_dim(self.session, table)
            if declared is None:
                return BackendHealth(ok=False, detail=f"index table {table!r} is missing")
            if declared != space.dim:
                return BackendHealth(
                    ok=False,
                    detail=f"index {table!r} is float[{declared}], expected float[{space.dim}]",
                )
            rows = int(self.session.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)
            mapped = int(
                self.session.scalar(
                    select(func.count())
                    .select_from(VectorRecord)
                    .where(
                        VectorRecord.space_id == self._space_id(space),
                        VectorRecord.rowid.is_not(None),
                    )
                )
                or 0
            )
            version = self.session.connection().exec_driver_sql("SELECT vec_version()").scalar()
        except VectorBackendError as exc:
            return BackendHealth(ok=False, detail=str(exc))
        except Exception as exc:  # pragma: no cover - a broken DB is not "healthy"
            return BackendHealth(ok=False, detail=f"sqlite-vec health probe failed: {exc}")
        if rows > mapped:
            return BackendHealth(
                ok=False,
                detail=f"{table}: {rows} physical row(s) but only {mapped} rowid mapping(s)",
            )
        if rows < mapped:
            return BackendHealth(
                ok=True,
                detail=(
                    f"sqlite-vec {version}, {table} float[{space.dim}], {rows} of "
                    f"{mapped} record(s) indexed (partial)"
                ),
            )
        return BackendHealth(
            ok=True,
            detail=f"sqlite-vec {version}, {table} float[{space.dim}], {rows} row(s)",
        )


def pgvector_available(session: Session) -> bool:
    """True when the connected PostgreSQL instance has the ``vector`` extension."""
    if session.get_bind().dialect.name != "postgresql":
        return False
    try:
        return (
            session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar()
            is not None
        )
    except Exception:  # pragma: no cover - a broken probe means "not available"
        logger.warning("pgvector availability probe failed", exc_info=True)
        return False


def sqlite_vec_available(session: Session) -> bool:
    """True when ``vec_version()`` answers after a defensive extension load."""
    if session.get_bind().dialect.name != "sqlite":
        return False
    try:
        import sqlite_vec

        raw = session.connection().connection.driver_connection
        if raw is None:
            return False
        raw.enable_load_extension(True)
        sqlite_vec.load(raw)
        session.connection().exec_driver_sql("SELECT vec_version()").scalar()
        return True
    except Exception:
        return False


def choose_backend(session: Session) -> SessionVectorBackend:
    """Select the backend honestly, degrading to linear.

    No deployment ever receives an ANN backend whose extension/driver probe
    failed; the linear fallback publishes ``ann=False``.
    """
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql" and pgvector_available(session):
        return PgVectorBackend(session)
    if dialect == "sqlite" and sqlite_vec_available(session):
        return SqliteVecBackend(session)
    return LinearBackend(session)


__all__ = [
    "SCOPE_ALL",
    "SCOPE_DOCUMENTS",
    "SCOPE_FILTERS",
    "LinearBackend",
    "PgVectorBackend",
    "SessionVectorBackend",
    "SqliteVecBackend",
    "VectorBackendError",
    "VectorBackendOverCap",
    "VectorIndexMissing",
    "VectorSpaceMismatch",
    "choose_backend",
    "document_scope",
    "filter_scope",
    "pgvector_available",
    "rowid_for",
    "sqlite_vec_available",
]
