"""The study vector-store adapter (plan 50 P3a, plan 51 Q3c2a/Q3c2b1).

One seam owns the portable metadata layer (``vector_spaces`` /
``vector_documents`` / ``vector_records``) **and** the physical vector index.
Search, embedding writes, purge paths and the retrieval-operations reads call
this adapter instead of issuing vector SQL themselves.

Q3c2a moved the ``content`` space onto a real family backend; Q3c2b1 adds the
space lifecycle. A store can now address any persisted space explicitly
(``StudyVectorStore(session, space_id=...)``) or, by default, the one active
space. A building space is written through the same writer as the active one:
its records carry a deterministic id and a ``chunk_id`` handle, so two spaces
can coexist without sharing primary keys.

``chunk_vecs`` remains the compatibility store. It is dual-written only while
the legacy ``content`` space is active, and it is never dropped by this
adapter — the audited drop of the retired legacy space is the explicit
retirement step.
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
    rowid_for,
)
from .vector_contract import IndexHit, IndexRecord, ScopeSpec, content_hash, space_key
from .vector_contract import VectorSpace as ContractSpace
from .vector_provisioning import (
    SpaceProvision,
    SpaceStatus,
    VectorProvisioningError,
    VectorSpaceRowMissing,
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
    """The adapter's honest view of one space (metadata + legacy meta)."""

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


def _record_id_for(space_id: str, chunk_id: str) -> str:
    """Deterministic space-local record id (never a global chunk id collision)."""
    try:
        namespace = uuid.UUID(str(space_id))
    except (TypeError, ValueError):
        namespace = uuid.NAMESPACE_URL
        name = f"study:{space_id}:{chunk_id}"
    else:
        name = f"study:{chunk_id}"
    return str(uuid.uuid5(namespace, name))


class StudyVectorStore:
    """Read/write seam over the metadata layer and one space's backend.

    ``space_id=None`` addresses the active space (the reader/writer default).
    An explicit id addresses that persisted space — the building-space
    backfill uses it so the active space is never touched.
    """

    def __init__(self, session: Session, space_id: str | None = None) -> None:
        self.session = session
        self.space_id = space_id

    @property
    def index_table(self) -> str:
        """The addressed physical index table (legacy while unprovisioned)."""
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
        if space.space_id == CONTENT_SPACE_ID:
            return vectors.vector_count(self.session)
        return 0

    def stored_chunk_ids(self) -> dict[int, str]:
        """``rowid -> chunk id`` for the addressed space."""
        space = self.content_space()
        if space is None:
            return {}
        if space.space_id == CONTENT_SPACE_ID:
            merged = dict(vectors.stored_chunk_ids(self.session))
        else:
            merged = {}
        rows = self.session.execute(
            select(VectorRecord.rowid, VectorRecord.chunk_id).where(
                VectorRecord.space_id == space.space_id,
                VectorRecord.rowid.is_not(None),
                VectorRecord.chunk_id.is_not(None),
            )
        )
        for rowid, chunk_id in rows:
            if rowid is not None and chunk_id is not None:
                merged.setdefault(int(rowid), str(chunk_id))
        return merged

    def stored_chunk_hashes(self) -> dict[str, str]:
        """``chunk id -> content hash`` for the addressed space."""
        space = self.content_space()
        if space is None:
            return {}
        rows = self.session.execute(
            select(VectorRecord.chunk_id, VectorRecord.content_hash).where(
                VectorRecord.space_id == space.space_id,
                VectorRecord.chunk_id.is_not(None),
            )
        )
        return {
            str(chunk_id): str(content or "")
            for chunk_id, content in rows
            if chunk_id is not None
        }

    def orphan_rowids(self, live_chunk_ids: set[str]) -> tuple[list[int], list[int]]:
        space = self.content_space()
        if space is None:
            return ([], [])
        if space.space_id == CONTENT_SPACE_ID:
            dangling, orphan = vectors.orphan_rowids(self.session, live_chunk_ids)
        else:
            dangling, orphan = ([], [])
        records = self.session.execute(
            select(VectorRecord.rowid, VectorRecord.chunk_id).where(
                VectorRecord.space_id == space.space_id,
                VectorRecord.rowid.is_not(None),
            )
        )
        known = set(dangling) | set(orphan)
        for rowid, chunk_id in records:
            if rowid is None or int(rowid) in known:
                continue
            if chunk_id is None or str(chunk_id) not in live_chunk_ids:
                orphan.append(int(rowid))
                known.add(int(rowid))
        return (dangling, orphan)

    def content_space(self) -> ContentSpace | None:
        """The addressed/active space without writing."""
        if self.space_id is not None:
            row = self.session.get(VectorSpace, self.space_id)
            if row is None:
                if self.space_id == CONTENT_SPACE_ID:
                    return self._ephemeral_space()
                return None
            return self._from_row(row)
        row = self._active_row()
        if row is not None:
            return self._from_row(row)
        if self._has_space_rows():
            return None
        return self._ephemeral_space()

    def _active_row(self) -> VectorSpace | None:
        rows = list(
            self.session.scalars(
                select(VectorSpace)
                .where(VectorSpace.status == "active")
                .order_by(VectorSpace.updated_at.desc(), VectorSpace.id)
            )
        )
        if len(rows) > 1:
            logger.warning("multiple active vector spaces: %s", len(rows))
        return rows[0] if rows else None

    def _has_space_rows(self) -> bool:
        return bool(
            self.session.scalar(select(func.count()).select_from(VectorSpace)) or 0
        )

    def _ephemeral_space(self) -> ContentSpace | None:
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

    def _from_row(self, row: VectorSpace) -> ContentSpace:
        assignment = embedding_assignment(self.session)
        if row.id == CONTENT_SPACE_ID:
            meta = vectors.read_meta(self.session)
            raw_dim = meta.get("dim")
            if raw_dim is not None:
                try:
                    meta_dim = int(raw_dim)
                except ValueError:
                    meta_dim = None
                meta_model = meta.get("model")
                if (meta_dim is not None and meta_dim != row.dim) or (
                    meta_model and meta_model != row.model
                ):
                    raise vectors.VectorSpaceChangeRequired(
                        current_model=row.model,
                        current_dim=row.dim,
                        requested_model=meta_model or row.model,
                        requested_dim=meta_dim or row.dim,
                        detail="vector_spaces row disagrees with vec_meta",
                    )
        index_table = row.index_table or vectors.VEC_TABLE
        backend = "linear" if row.index_table is None else backend_for(self.session)
        return self._dto(
            row,
            provider=row.provider or assignment.provider,
            model=row.model,
            dim=row.dim,
            index_table=index_table,
            backend=backend,
            metadata_row=True,
        )

    def ensure_content_space(self, *, provider: str | None = None) -> ContentSpace | None:
        """Create/refresh the legacy content row from ``vec_meta``.

        Called only from a write path (or an explicit backfill), never from a
        status read. A non-legacy active space owns writes; this is the
        compatibility row, not a second active pointer.
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
            active = self._active_row()
            if active is not None and active.id != CONTENT_SPACE_ID:
                raise VectorProvisioningError(
                    "another vector space is active; the legacy compatibility row "
                    "cannot become active again"
                )
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
            backend=backend_for(self.session),
            metadata_row=True,
        )

    def provision(self) -> SpaceProvision | None:
        """Provision the legacy content space's ``vec_<8hex>`` table and backfill."""
        if self.space_id not in (None, CONTENT_SPACE_ID):
            raise VectorProvisioningError("provision() only addresses the legacy content space")
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
        """Top chunks by cosine, scoped before the ANN scan when possible."""
        space = self.content_space()
        if space is None or space.dim != len(query_vector):
            return []
        backend = self._backend(space)
        if backend is None:
            return (
                vectors.search(self.session, list(query_vector), limit=limit)
                if space.space_id == CONTENT_SPACE_ID
                else []
            )
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
        except VectorBackendError as exc:
            logger.warning("vector backend search failed: %s", exc)
            if space.space_id == CONTENT_SPACE_ID:
                return vectors.search(self.session, list(query_vector), limit=limit)
            return []
        return self._chunk_hits(space, hits)

    def _chunk_hits(
        self, space: ContentSpace, hits: Sequence[IndexHit]
    ) -> list[tuple[str, float]]:
        record_ids = [str(hit.record_id) for hit in hits]
        if not record_ids:
            return []
        mapping = {
            str(record_id): str(chunk_id or record_id)
            for record_id, chunk_id in self.session.execute(
                select(VectorRecord.id, VectorRecord.chunk_id).where(
                    VectorRecord.space_id == space.space_id,
                    VectorRecord.id.in_([_canonical_id(value) for value in record_ids]),
                )
            )
        }
        return [
            (mapping.get(str(hit.record_id), str(hit.record_id)), float(hit.distance))
            for hit in hits
        ]

    def store(self, chunk_ids: list[str], vectors_batch: list[list[float]], model: str) -> None:
        """Write physical vectors for the addressed space, then register metadata."""
        if not chunk_ids or not vectors_batch:
            return
        space = self.content_space()
        if space is None:
            if self.space_id not in (None, CONTENT_SPACE_ID):
                raise VectorSpaceRowMissing(f"vector space {self.space_id!r} has no row")
            if self.space_id is None and self._has_space_rows():
                raise VectorProvisioningError(
                    "no active vector space; activate a space before writing"
                )
            vectors.store(self.session, chunk_ids, vectors_batch, model)
            space = self.ensure_content_space()
            if space is None:
                return
            self._store_legacy(space, chunk_ids, vectors_batch, model, write_legacy=False)
            return
        if space.space_id == CONTENT_SPACE_ID:
            self._store_legacy(space, chunk_ids, vectors_batch, model)
            return
        self._store_space(space, chunk_ids, vectors_batch, model)

    def _store_legacy(
        self,
        space: ContentSpace,
        chunk_ids: list[str],
        vectors_batch: list[list[float]],
        model: str,
        *,
        write_legacy: bool = True,
    ) -> None:
        if write_legacy:
            vectors.store(self.session, chunk_ids, vectors_batch, model)
        records = self._sync_records_legacy(chunk_ids)
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

    def _store_space(
        self,
        space: ContentSpace,
        chunk_ids: list[str],
        vectors_batch: list[list[float]],
        model: str,
    ) -> None:
        if model != space.model:
            raise vectors.VectorSpaceChangeRequired(
                current_model=space.model,
                current_dim=space.dim,
                requested_model=model,
                requested_dim=len(vectors_batch[0]) if vectors_batch else 0,
                detail=f"space {space.name!r} owns writes; build a new space to change the model",
            )
        if any(len(vector) != space.dim for vector in vectors_batch):
            raise vectors.VectorSpaceChangeRequired(
                current_model=space.model,
                current_dim=space.dim,
                requested_model=model,
                requested_dim=len(vectors_batch[0]) if vectors_batch else 0,
                detail=f"space {space.name!r} expects dim {space.dim}",
            )
        records = self._sync_records_for_space(space, chunk_ids)
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
        space = self.content_space()
        if space is None:
            return
        wanted = [_canonical_id(value) for value in chunk_ids]
        rows = list(
            self.session.scalars(
                select(VectorRecord).where(
                    VectorRecord.space_id == space.space_id,
                    VectorRecord.chunk_id.in_(wanted),
                )
            )
        )
        backend = self._backend(space)
        if backend is not None and rows:
            backend.delete_record_ids(space.as_contract(), [str(row.id) for row in rows])
        for record in rows:
            self.session.delete(record)
        self.session.flush()
        if space.space_id == CONTENT_SPACE_ID:
            vectors.delete_for_extraction(self.session, chunk_ids)
        self._drop_empty_documents({str(row.document_id) for row in rows})

    def delete_rowids(self, rowids: list[int]) -> int:
        space = self.content_space()
        if space is None or not rowids:
            return 0
        wanted = [int(rowid) for rowid in rowids]
        records = list(
            self.session.scalars(
                select(VectorRecord).where(
                    VectorRecord.space_id == space.space_id,
                    VectorRecord.rowid.in_(wanted),
                )
            )
        )
        backend = self._backend(space)
        if backend is not None and records:
            backend.delete_record_ids(space.as_contract(), [str(row.id) for row in records])
        for record in records:
            self.session.delete(record)
        self.session.flush()
        removed = (
            vectors.delete_rowids(self.session, rowids)
            if space.space_id == CONTENT_SPACE_ID
            else len(records)
        )
        self._drop_empty_documents({str(row.document_id) for row in records})
        return removed

    def unregister_records(self, chunk_ids: Iterable[str]) -> int:
        space = self.content_space()
        if space is None:
            return 0
        wanted = [_canonical_id(value) for value in chunk_ids]
        if not wanted:
            return 0
        records = list(
            self.session.scalars(
                select(VectorRecord).where(
                    VectorRecord.space_id == space.space_id,
                    VectorRecord.chunk_id.in_(wanted),
                )
            )
        )
        for record in records:
            self.session.delete(record)
        self.session.flush()
        self._drop_empty_documents({str(row.document_id) for row in records})
        return len(records)

    def document_count(self, *, kind: str | None = None) -> int:
        space = self.content_space()
        if space is None:
            return 0
        statement = (
            select(func.count())
            .select_from(VectorDocument)
            .where(VectorDocument.space_id == space.space_id)
        )
        if kind is not None:
            statement = statement.where(VectorDocument.kind == kind)
        return int(self.session.scalar(statement) or 0)

    def record_count(self, *, view: str | None = None) -> int:
        space = self.content_space()
        if space is None:
            return 0
        statement = (
            select(func.count())
            .select_from(VectorRecord)
            .where(VectorRecord.space_id == space.space_id)
        )
        if view is not None:
            statement = statement.where(VectorRecord.view == view)
        return int(self.session.scalar(statement) or 0)

    def metadata_complete(self) -> bool:
        """True when the metadata mapping covers every physical vector row."""
        physical = self.vector_count()
        return physical > 0 and self.record_count(view=CONTENT_VIEW) >= physical

    def documents(self, *, limit: int | None = None) -> list[VectorDocument]:
        space = self.content_space()
        if space is None:
            return []
        statement = (
            select(VectorDocument)
            .where(VectorDocument.space_id == space.space_id)
            .order_by(VectorDocument.id)
        )
        if limit is not None:
            statement = statement.limit(int(limit))
        return list(self.session.scalars(statement))

    def records(self, *, limit: int | None = None) -> list[VectorRecord]:
        space = self.content_space()
        if space is None:
            return []
        statement = (
            select(VectorRecord)
            .where(VectorRecord.space_id == space.space_id)
            .order_by(VectorRecord.rowid, VectorRecord.id)
        )
        if limit is not None:
            statement = statement.limit(int(limit))
        return list(self.session.scalars(statement))

    def record_for_rowid(self, rowid: int) -> VectorRecord | None:
        space = self.content_space()
        if space is None:
            return None
        return self.session.scalars(
            select(VectorRecord).where(
                VectorRecord.space_id == space.space_id,
                VectorRecord.rowid == int(rowid),
            )
        ).first()

    def rowid_map(self) -> dict[int, str]:
        """``rowid -> chunk id`` — the sqlite-vec rowid map for this space."""
        return self.stored_chunk_ids()

    def backfill_metadata(self, *, batch_size: int = 500) -> MetadataBackfill:
        """Rebuild/refresh the legacy mapping from the rowid reverse map."""
        self.ensure_content_space()
        mapping = dict(vectors.stored_chunk_ids(self.session))
        chunk_ids = list(mapping.values())
        scanned = 0
        for start in range(0, len(chunk_ids), max(1, batch_size)):
            batch = chunk_ids[start : start + batch_size]
            scanned += len(batch)
            self._sync_records_legacy(batch)
            self.session.flush()
        return MetadataBackfill(
            documents=self.document_count(),
            records=self.record_count(view=CONTENT_VIEW),
            scanned=scanned,
        )

    def _backend(self, space: ContentSpace) -> SessionVectorBackend | None:
        """The backend that answers this space, or ``None`` for the legacy store."""
        if space.index_table is None:
            return LinearBackend(self.session)
        if space.index_table == LEGACY_INDEX_TABLE:
            return None
        if not _is_provisioned(space.index_table):
            return None
        return choose_backend(self.session)

    def _ensure_physical(self, space: ContentSpace) -> ContentSpace:
        """Provision on the write path only; a failure keeps the legacy store."""
        if _is_provisioned(space.index_table):
            return space
        if space.space_id != CONTENT_SPACE_ID:
            savepoint = self.session.begin_nested()
            try:
                provision_space(self.session, space.space_id)
            except VectorProvisioningError as exc:
                savepoint.rollback()
                logger.warning(
                    "vector_space_provision_deferred space_id=%s reason=%s",
                    space.space_id,
                    exc,
                )
                return space
            savepoint.commit()
            return self.content_space() or space
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
        backend: str,
        metadata_row: bool,
    ) -> ContentSpace:
        return ContentSpace(
            space_id=str(row.id),
            name=str(row.name),
            provider=provider,
            model=model,
            dim=dim,
            backend=backend,
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

    def _document_for(
        self, *, space_id: str, source_id: str, profile_id: str | None
    ) -> VectorDocument:
        candidates = {source_id}
        with contextlib.suppress(TypeError, ValueError):
            candidates.add(uuid.UUID(source_id).hex)
        document = self.session.scalars(
            select(VectorDocument).where(
                VectorDocument.space_id == space_id,
                VectorDocument.kind == CONTENT_SPACE_KIND,
                VectorDocument.source_id.in_(candidates),
            )
        ).first()
        if document is None:
            document = VectorDocument(
                id=str(uuid.uuid4()),
                space_id=space_id,
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

    def _chunk_rows(
        self, chunk_ids: Sequence[str]
    ) -> list[tuple[str, int, str, str, str | None, str]]:
        wanted = [str(chunk_id) for chunk_id in chunk_ids]
        if not wanted:
            return []
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
        return [
            (str(chunk_id), int(ordinal), str(text), str(material_id), profile_id, markdown or "")
            for chunk_id, ordinal, text, material_id, profile_id, markdown in rows
        ]

    def _sync_records_legacy(self, chunk_ids: Sequence[str]) -> dict[str, VectorRecord]:
        """Register/refresh legacy metadata; record id = chunk id."""
        registered: dict[str, VectorRecord] = {}
        by_material: dict[str, list[tuple[str, int, str, str, str | None, str]]] = {}
        for row in self._chunk_rows(chunk_ids):
            by_material.setdefault(row[3], []).append(row)
        for material_id, chunks in by_material.items():
            source_id = _canonical_id(material_id)
            document = self._document_for(
                space_id=CONTENT_SPACE_ID,
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
                        chunk_id=canonical_chunk,
                        view=CONTENT_VIEW,
                        chunk_index=next_index,
                        rowid=rowid,
                        content_hash=content_hash(text),
                    )
                    self.session.add(record)
                    existing[rowid] = record
                    next_index += 1
                else:
                    record.chunk_id = canonical_chunk
                    record.content_hash = content_hash(text)
                registered[canonical_chunk] = record
            self.session.flush()
        return registered

    def _sync_records_for_space(
        self, space: ContentSpace, chunk_ids: Sequence[str]
    ) -> dict[str, VectorRecord]:
        """Register/refresh records under a non-legacy space.

        The record id is deterministic per ``(space, chunk)``; the rowid is the
        sqlite-vec rowid rule over that record id. ``chunk_id`` keeps the
        chunk hydration handle explicit, so a search hit maps back without a
        second physical table.
        """
        registered: dict[str, VectorRecord] = {}
        by_material: dict[str, list[tuple[str, int, str, str, str | None, str]]] = {}
        for row in self._chunk_rows(chunk_ids):
            by_material.setdefault(row[3], []).append(row)
        for material_id, chunks in by_material.items():
            source_id = _canonical_id(material_id)
            document = self._document_for(
                space_id=space.space_id,
                source_id=source_id,
                profile_id=_canonical_id(chunks[0][4]) if chunks[0][4] else None,
            )
            document.source_hash = content_hash(chunks[0][5])
            document_records = list(
                self.session.scalars(
                    select(VectorRecord).where(
                        VectorRecord.space_id == space.space_id,
                        VectorRecord.document_id == document.id,
                    )
                )
            )
            existing = {
                str(record.chunk_id): record
                for record in document_records
                if record.chunk_id is not None
            }
            next_index = max(
                (int(record.chunk_index) for record in document_records), default=-1
            ) + 1
            for chunk_id, _ordinal, text, _material, _profile, _markdown in chunks:
                canonical_chunk = _canonical_id(chunk_id)
                record = existing.get(canonical_chunk)
                if record is None:
                    record_id = _record_id_for(space.space_id, canonical_chunk)
                    record = VectorRecord(
                        id=record_id,
                        document_id=document.id,
                        space_id=space.space_id,
                        chunk_id=canonical_chunk,
                        view=CONTENT_VIEW,
                        chunk_index=next_index,
                        rowid=self._allocate_rowid(record_id),
                        content_hash=content_hash(text),
                    )
                    self.session.add(record)
                    existing[canonical_chunk] = record
                    next_index += 1
                else:
                    record.content_hash = content_hash(text)
                registered[canonical_chunk] = record
            self.session.flush()
        return registered

    def _allocate_rowid(self, record_id: str) -> int:
        salt = 0
        while True:
            candidate = rowid_for(record_id, salt=salt)
            owner = self.session.scalar(
                select(VectorRecord.id).where(VectorRecord.rowid == candidate)
            )
            if owner is None or str(owner) == _canonical_id(record_id):
                return candidate
            salt += 1

    def _drop_empty_documents(self, document_ids: set[str]) -> None:
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

    def _drop_records(self, rowids: Sequence[int]) -> int:
        space = self.content_space()
        if space is None or not rowids:
            return 0
        wanted = [int(rowid) for rowid in rowids]
        records = list(
            self.session.scalars(
                select(VectorRecord).where(
                    VectorRecord.space_id == space.space_id,
                    VectorRecord.rowid.in_(wanted),
                )
            )
        )
        for record in records:
            self.session.delete(record)
        self.session.flush()
        self._drop_empty_documents({str(record.document_id) for record in records})
        return len(records)


def content_space_for(session: Session) -> ContentSpace | None:
    """Module-level read helper for call sites that only need the identity."""
    return StudyVectorStore(session).content_space()


def space_for(session: Session, space_id: str) -> ContentSpace | None:
    """Module-level read helper for one explicit persisted space."""
    return StudyVectorStore(session, space_id=space_id).content_space()


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
    "space_for",
]
