"""The study vector-store adapter (plan 50 P3a, plan 51 Q3c2a).

One seam owns the portable metadata layer (``vector_spaces`` /
``vector_documents`` / ``vector_records``) **and** the physical vector index.
Search, embedding writes, purge paths and the retrieval-operations reads call
this adapter instead of issuing vector SQL themselves.

Q3c2a moves the ``content`` space onto a real family backend: a provisioned
``vec_<8hex>`` table (pgvector + HNSW cosine, or sqlite-vec ``vec0``) is
created by :mod:`storage.vector_provisioning` and addressed through
:mod:`storage.vector_backends`. ``chunk_vecs`` is still dual-written as the
compatibility store — it is the honest read fallback until a later cutover
retires it, and it is never dropped here.

Metadata mapping:

* document = a material (``kind='material'``, ``source_id`` = material id);
* record = one chunk's ``body`` view, carrying its content hash and the
  63-bit study rowid (the sqlite-vec rowid map);
* space = the one ``content`` space, id ``legacy-chunk-vecs`` (the id Q3a/
  Q3b already write into rollups/snapshots), model/dim read from ``vec_meta``.

A model/dimension change is **not** applied in place: :func:`vectors.store`
raises :class:`VectorSpaceChangeRequired` and the old table stays readable
until the explicit new-space/cutover handoff runs. There is no fake coverage:
metadata counts are real row counts and coverage still comes only from a
``retrieval_coverage_snapshots`` row.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.embeddings import EMBEDDINGS_TASK
from ..domain.models import (
    AiModel,
    Chunk,
    DefaultTaskAssignment,
    Extraction,
    Material,
    Provider,
    TaskAssignment,
    VectorDocument,
    VectorRecord,
    VectorSpace,
)
from . import vectors
from .vector_backends import (
    SCOPE_ALL,
    LinearBackend,
    SessionVectorBackend,
    VectorBackendError,
    choose_backend,
    document_scope,
    filter_scope,
)
from .vector_contract import IndexRecord, ScopeSpec, content_hash, space_key
from .vector_contract import VectorSpace as ContractSpace
from .vector_provisioning import (
    SpaceProvision,
    SpaceStatus,
    VectorProvisioningError,
    backfill_from_legacy,
    provision_space,
    space_status,
)

logger = logging.getLogger(__name__)

CONTENT_SPACE_ID = "legacy-chunk-vecs"
CONTENT_SPACE_NAME = "content"
CONTENT_SPACE_KIND = "material"
CONTENT_VIEW = "body"
LEGACY_INDEX_TABLE = "chunk_vecs"


@dataclass(frozen=True)
class EmbeddingAssignment:
    provider: str
    model: str
    dim: int | None


@dataclass(frozen=True)
class ContentSpace:
    """The adapter's honest view of the active space (metadata + legacy meta)."""

    space_id: str
    name: str
    provider: str
    model: str
    dim: int
    backend: str
    index_table: str
    status: str
    key: str
    metadata_row: bool

    def as_contract(self) -> ContractSpace:
        return ContractSpace(
            name=self.name,
            provider=self.provider,
            model=self.model,
            dim=self.dim,
            space_id=self.space_id,
            index_table=self.index_table,
        )


@dataclass(frozen=True)
class MetadataBackfill:
    documents: int
    records: int
    scanned: int


@dataclass(frozen=True)
class StoreHealth:
    """The backend/table truth the admin read surface reports."""

    ok: bool
    detail: str
    backend: str
    index_table: str | None
    records: int
    legacy_rows: int
    provisioned: bool


def backend_for(session: Session) -> str:
    return "pgvector" if session.get_bind().dialect.name == "postgresql" else "sqlite_vec"


def backend_label(backend: str) -> str:
    if backend == "pgvector":
        return "PostgreSQL pgvector/HNSW"
    if backend == "sqlite_vec":
        return "SQLite sqlite-vec"
    return "Linear fallback — desktop scale"


def embedding_assignment(session: Session) -> EmbeddingAssignment:
    assignment = session.get(TaskAssignment, EMBEDDINGS_TASK)
    model_id = assignment.model_id if assignment is not None else None
    if model_id is None:
        default = session.get(DefaultTaskAssignment, EMBEDDINGS_TASK)
        model_id = default.model_id if default is not None else None
    if model_id is None:
        return EmbeddingAssignment(provider="unassigned", model="unassigned", dim=None)
    model = session.get(AiModel, model_id)
    if model is None:
        return EmbeddingAssignment(provider="unassigned", model="unassigned", dim=None)
    provider = session.get(Provider, model.provider_id)
    label = provider.name if provider is not None else "unknown"
    return EmbeddingAssignment(provider=label, model=model.external_id, dim=None)


def _canonical_id(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return str(value)


def _is_provisioned(index_table: str | None) -> bool:
    return bool(index_table) and str(index_table).startswith("vec_")


class StudyVectorStore:
    """Read/write seam over the metadata layer and the active backend."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @property
    def index_table(self) -> str:
        """The active physical index table (legacy while unprovisioned)."""
        space = self.content_space()
        if space is not None and space.index_table:
            return str(space.index_table)
        return vectors.VEC_TABLE

    @property
    def index_name(self) -> str | None:
        """The backend's index object, when the backend has one."""
        table = self.index_table
        if _is_provisioned(table):
            return (
                f"ix_{table}_hnsw" if self.session.get_bind().dialect.name == "postgresql" else None
            )
        if (
            table == LEGACY_INDEX_TABLE
            and self.session.get_bind().dialect.name == "postgresql"
        ):
            return f"ix_{LEGACY_INDEX_TABLE}_embedding"
        return None

    def read_meta(self) -> dict[str, str]:
        return vectors.read_meta(self.session)

    def table_exists(self) -> bool:
        return vectors.table_exists(self.session)

    def vector_count(self) -> int:
        space = self.content_space()
        if space is None:
            return 0
        backend = self._backend(space)
        if backend is not None:
            try:
                return backend.count(space.as_contract())
            except VectorBackendError as exc:
                logger.warning("vector_count backend failed: %s", exc)
        return vectors.vector_count(self.session)

    def stored_chunk_ids(self) -> dict[int, str]:
        """``rowid -> chunk id`` from the legacy map plus the metadata rows."""
        merged = dict(vectors.stored_chunk_ids(self.session))
        rows = self.session.execute(
            select(VectorRecord.rowid, VectorRecord.id).where(
                VectorRecord.space_id == CONTENT_SPACE_ID,
                VectorRecord.rowid.is_not(None),
            )
        )
        for rowid, record_id in rows:
            if rowid is not None:
                merged.setdefault(int(rowid), str(record_id))
        return merged

    def orphan_rowids(self, live_chunk_ids: set[str]) -> tuple[list[int], list[int]]:
        dangling, orphan = vectors.orphan_rowids(self.session, live_chunk_ids)
        space = self.content_space()
        if space is None:
            return (dangling, orphan)
        records = self.session.execute(
            select(VectorRecord.rowid, VectorRecord.id).where(
                VectorRecord.space_id == space.space_id,
                VectorRecord.rowid.is_not(None),
            )
        )
        known = set(dangling) | set(orphan)
        for rowid, record_id in records:
            if rowid is None or int(rowid) in known:
                continue
            if str(record_id) not in live_chunk_ids:
                orphan.append(int(rowid))
                known.add(int(rowid))
        return (dangling, orphan)

    def content_space(self) -> ContentSpace | None:
        """The active space without writing (a status read never mutates).

        The persisted metadata row is authoritative when present; otherwise an
        ephemeral DTO is derived from ``vec_meta`` so a store that predates
        the metadata migration still reads honestly.
        """
        meta = vectors.read_meta(self.session)
        raw_dim = meta.get("dim")
        if raw_dim is None:
            return None
        try:
            dim = int(raw_dim)
        except ValueError:
            return None
        if dim <= 0:
            return None
        assignment = embedding_assignment(self.session)
        model = meta.get("model") or assignment.model or "unknown"
        row = self.session.get(VectorSpace, CONTENT_SPACE_ID)
        if row is not None:
            if row.dim != dim or (meta.get("model") and row.model != meta.get("model")):
                raise vectors.VectorSpaceChangeRequired(
                    current_model=row.model,
                    current_dim=row.dim,
                    requested_model=model,
                    requested_dim=dim,
                    detail="vector_spaces row disagrees with vec_meta",
                )
            return self._dto(
                row,
                provider=row.provider or assignment.provider,
                model=row.model,
                dim=row.dim,
                index_table=row.index_table or vectors.VEC_TABLE,
                metadata_row=True,
            )
        return ContentSpace(
            space_id=CONTENT_SPACE_ID,
            name=CONTENT_SPACE_NAME,
            provider=assignment.provider,
            model=model,
            dim=dim,
            backend=backend_for(self.session),
            index_table=vectors.VEC_TABLE,
            status="active",
            key=space_key(
                assignment.provider,
                model,
                dim,
                True,
                None,
                None,
                "1",
                "1",
            ),
            metadata_row=False,
        )

    def ensure_content_space(self, *, provider: str | None = None) -> ContentSpace | None:
        """Create/refresh the one metadata row for the active legacy space.

        Called only from a write path (or an explicit backfill), never from a
        status read. ``vec_meta`` remains the trusted model/dim in P3a; a
        disagreement is an explicit error, not an in-place rewrite.
        """
        meta = vectors.read_meta(self.session)
        raw_dim = meta.get("dim")
        if raw_dim is None:
            return None
        try:
            dim = int(raw_dim)
        except ValueError:
            return None
        if dim <= 0:
            return None
        assignment = embedding_assignment(self.session)
        model = meta.get("model") or assignment.model or "unknown"
        resolved_provider = provider or assignment.provider
        row = self.session.get(VectorSpace, CONTENT_SPACE_ID)
        if row is None:
            row = VectorSpace(
                id=CONTENT_SPACE_ID,
                name=CONTENT_SPACE_NAME,
                provider=resolved_provider,
                model=model,
                dim=dim,
                index_table=vectors.VEC_TABLE,
                status="active",
            )
            self.session.add(row)
        else:
            if row.dim != dim or row.model != model:
                raise vectors.VectorSpaceChangeRequired(
                    current_model=row.model,
                    current_dim=row.dim,
                    requested_model=model,
                    requested_dim=dim,
                    detail="vector_spaces row disagrees with vec_meta",
                )
            row.provider = resolved_provider
        self.session.flush()
        return self._dto(
            row,
            provider=resolved_provider,
            model=model,
            dim=dim,
            index_table=row.index_table or vectors.VEC_TABLE,
            metadata_row=True,
        )

    def provision(self) -> SpaceProvision | None:
        """Provision the content space's ``vec_<8hex>`` table and backfill it.

        Off the read path by construction: callers are the one-time migration,
        the ingest/reindex write path, or an explicit ops action. ``chunk_vecs``
        is copied, never replaced or dropped; the index_table switch commits
        with the caller's transaction.
        """
        space = self.ensure_content_space()
        if space is None:
            return None
        if _is_provisioned(space.index_table):
            return None
        self.backfill_metadata()
        space = self.content_space() or space
        result = provision_space(self.session, space.space_id)
        if result.index_table is not None:
            backfill_from_legacy(self.session, space.space_id)
        return result

    def backfill_physical(self) -> int:
        """Copy any legacy rows into an already-provisioned content table."""
        space = self.content_space()
        if space is None or not _is_provisioned(space.index_table):
            return 0
        return backfill_from_legacy(self.session, space.space_id)

    def space_status(self) -> SpaceStatus | None:
        space = self.content_space()
        if space is None:
            return None
        return space_status(self.session, space.space_id)

    def health(self) -> StoreHealth:
        """Backend/table health without creating or repairing anything."""
        space = self.content_space()
        legacy_rows = vectors.vector_count(self.session)
        if space is None:
            return StoreHealth(
                ok=False,
                detail="no vector store is provisioned (vec_meta has no dim)",
                backend=backend_for(self.session),
                index_table=None,
                records=0,
                legacy_rows=legacy_rows,
                provisioned=False,
            )
        backend = self._backend(space)
        if backend is None:
            backend_name = choose_backend(self.session).name
            return StoreHealth(
                ok=vectors.table_exists(self.session),
                detail=f"legacy {vectors.VEC_TABLE} store, {legacy_rows} vector(s)",
                backend=backend_name,
                index_table=space.index_table,
                records=legacy_rows,
                legacy_rows=legacy_rows,
                provisioned=False,
            )
        result = backend.health(space.as_contract())
        try:
            records = backend.count(space.as_contract())
        except VectorBackendError:
            records = 0
        return StoreHealth(
            ok=result.ok,
            detail=result.detail,
            backend=backend.name,
            index_table=space.index_table,
            records=records,
            legacy_rows=legacy_rows,
            provisioned=_is_provisioned(space.index_table),
        )

    def search(
        self,
        query_vector: Sequence[float],
        limit: int = 24,
        *,
        course_id: str | None = None,
        material_ids: Sequence[str] | None = None,
        profile_id: str | None = None,
    ) -> list[tuple[str, float]]:
        """Top chunks by cosine, scoped before the ANN scan when possible.

        Returns the legacy ``(chunk id, distance)`` shape so the FTS/RRF
        fusion and hydration paths stay unchanged. When the provisioned
        backend is unavailable (missing extension/table) the legacy
        ``chunk_vecs`` path answers; a partial backfill never fabricates
        coverage because the migration only switches ``index_table`` after
        verifying its row count.
        """
        space = self.content_space()
        if space is None or space.dim != len(query_vector):
            return []
        backend = self._backend(space)
        if backend is not None:
            try:
                hits = backend.search(
                    space.as_contract(),
                    list(query_vector),
                    views=(CONTENT_VIEW,),
                    scope=self._scope(
                        course_id=course_id,
                        material_ids=material_ids,
                        profile_id=profile_id,
                    ),
                    limit=limit,
                )
                return [(hit.record_id, hit.distance) for hit in hits]
            except VectorBackendError as exc:
                logger.warning("vector backend search failed, using legacy store: %s", exc)
        return vectors.search(self.session, list(query_vector), limit=limit)

    def store(self, chunk_ids: list[str], vectors_batch: list[list[float]], model: str) -> None:
        """Write physical vectors, then register their metadata mapping.

        ``vectors.store`` first enforces the model/dim guard and maintains the
        legacy mirror; only a successful physical write reaches the metadata
        registration and the provisioned backend. A refused change never
        leaves a metadata row or a copied vector behind.
        """
        if not chunk_ids or not vectors_batch:
            return
        vectors.store(self.session, chunk_ids, vectors_batch, model)
        space = self.ensure_content_space()
        records = self._sync_records(chunk_ids)
        if space is None:
            return
        space = self._ensure_physical(space)
        backend = self._backend(space)
        if backend is None:
            return
        index_records = [
            IndexRecord(
                record_id=str(record.id),
                document_id=str(record.document_id),
                view=str(record.view),
                chunk_index=int(record.chunk_index),
                embedding=tuple(float(value) for value in vector),
                content_hash=str(record.content_hash or ""),
            )
            for chunk_id, vector in zip(chunk_ids, vectors_batch, strict=True)
            if (record := records.get(str(chunk_id))) is not None
        ]
        if index_records:
            backend.upsert(space.as_contract(), index_records)

    def delete_for_extraction(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        rowids = [vectors.rowid_for(chunk_id) for chunk_id in chunk_ids]
        space = self.content_space()
        if space is not None:
            backend = self._backend(space)
            if backend is not None:
                backend.delete_record_ids(space.as_contract(), list(chunk_ids))
        vectors.delete_for_extraction(self.session, chunk_ids)
        self._drop_records(rowids)

    def delete_rowids(self, rowids: list[int]) -> int:
        space = self.content_space()
        if space is not None and rowids:
            backend = self._backend(space)
            if backend is not None:
                record_ids = [
                    str(record_id)
                    for (record_id,) in self.session.execute(
                        select(VectorRecord.id).where(
                            VectorRecord.space_id == space.space_id,
                            VectorRecord.rowid.in_([int(rowid) for rowid in rowids]),
                        )
                    )
                ]
                backend.delete_record_ids(space.as_contract(), record_ids)
        removed = vectors.delete_rowids(self.session, rowids)
        self._drop_records(rowids)
        return removed

    def unregister_records(self, chunk_ids: Iterable[str]) -> int:
        rowids = [vectors.rowid_for(chunk_id) for chunk_id in chunk_ids]
        return self._drop_records(rowids)

    def document_count(self, *, kind: str | None = None) -> int:
        statement = (
            select(func.count())
            .select_from(VectorDocument)
            .where(VectorDocument.space_id == CONTENT_SPACE_ID)
        )
        if kind is not None:
            statement = statement.where(VectorDocument.kind == kind)
        return int(self.session.scalar(statement) or 0)

    def record_count(self, *, view: str | None = None) -> int:
        statement = (
            select(func.count())
            .select_from(VectorRecord)
            .where(VectorRecord.space_id == CONTENT_SPACE_ID)
        )
        if view is not None:
            statement = statement.where(VectorRecord.view == view)
        return int(self.session.scalar(statement) or 0)

    def metadata_complete(self) -> bool:
        """True when the metadata mapping covers every physical vector row."""
        physical = self.vector_count()
        return physical > 0 and self.record_count(view=CONTENT_VIEW) >= physical

    def documents(self, *, limit: int | None = None) -> list[VectorDocument]:
        statement = (
            select(VectorDocument)
            .where(VectorDocument.space_id == CONTENT_SPACE_ID)
            .order_by(VectorDocument.id)
        )
        if limit is not None:
            statement = statement.limit(int(limit))
        return list(self.session.scalars(statement))

    def records(self, *, limit: int | None = None) -> list[VectorRecord]:
        statement = (
            select(VectorRecord)
            .where(VectorRecord.space_id == CONTENT_SPACE_ID)
            .order_by(VectorRecord.rowid, VectorRecord.id)
        )
        if limit is not None:
            statement = statement.limit(int(limit))
        return list(self.session.scalars(statement))

    def record_for_rowid(self, rowid: int) -> VectorRecord | None:
        return self.session.scalars(
            select(VectorRecord).where(VectorRecord.rowid == int(rowid))
        ).first()

    def rowid_map(self) -> dict[int, str]:
        """``rowid -> chunk id`` — the sqlite-vec rowid map (P3a legacy map)."""
        return self.stored_chunk_ids()

    def backfill_metadata(self, *, batch_size: int = 500) -> MetadataBackfill:
        """Rebuild/refresh the mapping from the physical rowid reverse map.

        Fills the content hashes and record rows the migration could not
        compute in SQL. Idempotent: existing records are updated in place by
        rowid, never duplicated.
        """
        self.ensure_content_space()
        mapping = self.stored_chunk_ids()
        chunk_ids = list(mapping.values())
        scanned = 0
        for start in range(0, len(chunk_ids), max(1, batch_size)):
            batch = chunk_ids[start : start + batch_size]
            scanned += len(batch)
            self._sync_records(batch)
            self.session.flush()
        return MetadataBackfill(
            documents=self.document_count(),
            records=self.record_count(view=CONTENT_VIEW),
            scanned=scanned,
        )

    def _backend(self, space: ContentSpace) -> SessionVectorBackend | None:
        """The backend that answers this space, or ``None`` for the legacy store."""
        if space.index_table == LEGACY_INDEX_TABLE or not space.index_table:
            if space.index_table is None:
                return LinearBackend(self.session)
            return None
        if not _is_provisioned(space.index_table):
            return None
        return choose_backend(self.session)

    def _ensure_physical(self, space: ContentSpace) -> ContentSpace:
        """Provision on the write path only; a failure keeps the legacy store."""
        if space.index_table != LEGACY_INDEX_TABLE:
            return space
        row = self.session.get(VectorSpace, space.space_id)
        savepoint = self.session.begin_nested()
        try:
            self.provision()
        except VectorProvisioningError as exc:
            savepoint.rollback()
            logger.warning(
                "vector_space_provision_deferred space_id=%s reason=%s",
                space.space_id,
                exc,
            )
            if row is not None:
                self.session.expire(row)
            return space
        savepoint.commit()
        return self.content_space() or space

    def _scope(
        self,
        *,
        course_id: str | None,
        material_ids: Sequence[str] | None,
        profile_id: str | None,
    ) -> ScopeSpec:
        if material_ids is not None:
            return document_scope([_canonical_id(value) for value in material_ids])
        if course_id is not None:
            ids = [
                str(value)
                for value in self.session.scalars(
                    select(Material.id).where(Material.course_id == course_id)
                )
            ]
            return document_scope(ids)
        if profile_id is not None:
            return filter_scope(profile_ids=[profile_id])
        return ScopeSpec(kind=SCOPE_ALL, predicate=None)

    def _dto(
        self,
        row: VectorSpace,
        *,
        provider: str,
        model: str,
        dim: int,
        index_table: str,
        metadata_row: bool,
    ) -> ContentSpace:
        return ContentSpace(
            space_id=str(row.id),
            name=str(row.name),
            provider=provider,
            model=model,
            dim=dim,
            backend=backend_for(self.session),
            index_table=index_table,
            status=str(row.status),
            key=space_key(
                provider,
                model,
                dim,
                bool(row.normalize),
                row.query_prefix,
                row.document_prefix,
                str(row.chunker_version),
                str(row.composer_version),
            ),
            metadata_row=metadata_row,
        )

    def _document_for(self, *, source_id: str, profile_id: str | None) -> VectorDocument:
        candidates = {source_id}
        with contextlib.suppress(TypeError, ValueError):
            candidates.add(uuid.UUID(source_id).hex)
        document = self.session.scalars(
            select(VectorDocument).where(
                VectorDocument.space_id == CONTENT_SPACE_ID,
                VectorDocument.kind == CONTENT_SPACE_KIND,
                VectorDocument.source_id.in_(candidates),
            )
        ).first()
        if document is None:
            document = VectorDocument(
                id=str(uuid.uuid4()),
                space_id=CONTENT_SPACE_ID,
                kind=CONTENT_SPACE_KIND,
                source_id=source_id,
                profile_id=profile_id,
                source_hash="",
                schema_version=0,
            )
            self.session.add(document)
            self.session.flush()
        else:
            document.profile_id = profile_id
            document.source_id = source_id
        return document

    def _sync_records(self, chunk_ids: Sequence[str]) -> dict[str, VectorRecord]:
        """Register/refresh metadata for ``chunk_ids``; record id = chunk id."""
        if not chunk_ids:
            return {}
        wanted = [str(chunk_id) for chunk_id in chunk_ids]
        rows = self.session.execute(
            select(
                Chunk.id,
                Chunk.ordinal,
                Chunk.text,
                Material.id,
                Material.profile_id,
                Extraction.markdown,
            )
            .join(Extraction, Extraction.id == Chunk.extraction_id)
            .join(Material, Material.id == Extraction.material_id)
            .where(Chunk.id.in_(wanted))
            .order_by(Material.id, Extraction.created_at, Chunk.ordinal)
        ).all()
        by_material: dict[str, list[tuple[str, int, str, str, str | None, str]]] = {}
        for chunk_id, ordinal, text, material_id, profile_id, markdown in rows:
            key = str(material_id)
            by_material.setdefault(key, []).append(
                (str(chunk_id), int(ordinal), str(text), key, profile_id, markdown or "")
            )
        registered: dict[str, VectorRecord] = {}
        for material_id, chunks in by_material.items():
            source_id = _canonical_id(material_id)
            document = self._document_for(
                source_id=source_id,
                profile_id=_canonical_id(chunks[0][4]) if chunks[0][4] else None,
            )
            document.source_hash = content_hash(chunks[0][5])
            existing = {
                int(record.rowid): record
                for record in self.session.scalars(
                    select(VectorRecord).where(
                        VectorRecord.document_id == document.id,
                        VectorRecord.view == CONTENT_VIEW,
                    )
                )
                if record.rowid is not None
            }
            next_index = max((record.chunk_index for record in existing.values()), default=-1) + 1
            for chunk_id, _ordinal, text, _material, _profile, _markdown in chunks:
                canonical_chunk = _canonical_id(chunk_id)
                rowid = vectors.rowid_for(canonical_chunk)
                record = existing.get(rowid)
                if record is None:
                    record = VectorRecord(
                        id=canonical_chunk,
                        document_id=document.id,
                        space_id=CONTENT_SPACE_ID,
                        view=CONTENT_VIEW,
                        chunk_index=next_index,
                        rowid=rowid,
                        content_hash=content_hash(text),
                    )
                    self.session.add(record)
                    existing[rowid] = record
                    next_index += 1
                else:
                    record.content_hash = content_hash(text)
                registered[canonical_chunk] = record
            self.session.flush()
        return registered

    def _drop_records(self, rowids: Sequence[int]) -> int:
        wanted = [int(rowid) for rowid in rowids]
        if not wanted:
            return 0
        records = list(
            self.session.scalars(select(VectorRecord).where(VectorRecord.rowid.in_(wanted)))
        )
        if not records:
            return 0
        document_ids = {str(record.document_id) for record in records}
        for record in records:
            self.session.delete(record)
        self.session.flush()
        for document_id in document_ids:
            remaining = self.session.scalar(
                select(func.count())
                .select_from(VectorRecord)
                .where(VectorRecord.document_id == document_id)
            )
            if not remaining:
                document = self.session.get(VectorDocument, document_id)
                if document is not None:
                    self.session.delete(document)
        self.session.flush()
        return len(records)


def content_space_for(session: Session) -> ContentSpace | None:
    """Module-level read helper for call sites that only need the identity."""
    return StudyVectorStore(session).content_space()


__all__ = [
    "CONTENT_SPACE_ID",
    "CONTENT_SPACE_KIND",
    "CONTENT_SPACE_NAME",
    "CONTENT_VIEW",
    "LEGACY_INDEX_TABLE",
    "ContentSpace",
    "EmbeddingAssignment",
    "MetadataBackfill",
    "StoreHealth",
    "StudyVectorStore",
    "backend_for",
    "backend_label",
    "content_space_for",
    "embedding_assignment",
]
