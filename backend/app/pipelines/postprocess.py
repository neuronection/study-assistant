from collections.abc import Callable
from typing import Any, cast

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.embeddings import embed_with_tags
from ..ai.gateway import ProviderError
from ..domain.models import Chunk, Extraction, Material, MaterialIndexCard
from ..jobs.cancellation import ensure_target_exists
from ..jobs.payloads import PostprocessPayload
from ..jobs.runner import JobError, JobHandler, ProgressReporter
from ..pipelines.chunking import InputTooLong
from ..services.retrieval.chunk_profile import (
    ChunkProfile,
    batch_window_specs,
    profile_for_space,
    window_specs_for_chunk,
)
from ..storage.vector_store import (
    CONTENT_SPACE_ID,
    CONTENT_SPACE_KIND,
    CONTENT_VIEW,
    StudyVectorStore,
    VectorRecordSpec,
)

logger = structlog.get_logger(__name__)

Embedder = Callable[[list[str]], tuple[str, list[list[float]]] | None]
Describer = Callable[[str, str, str | None], dict[str, Any] | None]

EMBED_BATCH = 32


def _latest_extraction(session: Session, extraction_id: str | None, material_id: str) -> Extraction:
    if extraction_id is not None:
        extraction = session.get(Extraction, extraction_id)
        if extraction is not None:
            return extraction
    extraction = session.scalars(
        select(Extraction)
        .where(Extraction.material_id == material_id)
        .order_by(Extraction.version.desc())
        .limit(1)
    ).first()
    if extraction is None:
        raise JobError(f"no extraction for material {material_id}")
    return extraction


def embed_extraction(session: Session, extraction: Extraction, embedder: Embedder) -> int:
    chunks = list(
        session.scalars(
            select(Chunk).where(Chunk.extraction_id == extraction.id).order_by(Chunk.ordinal)
        )
    )
    if not chunks:
        return 0
    store = StudyVectorStore(session)
    space = store.content_space()
    space_id = space.space_id if space is not None else CONTENT_SPACE_ID
    profile = profile_for_space(session, space_id)
    if profile is not None:
        return _embed_token_extraction(session, store, chunks, embedder, profile, space_id)
    embedded = 0
    for start in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[start : start + EMBED_BATCH]
        tags: dict[str, object] = {
            "space_id": space_id,
            "kind": CONTENT_SPACE_KIND,
            "view": CONTENT_VIEW,
        }
        if len(batch) == 1:
            tags["chunk_index"] = int(batch[0].ordinal)
        result = embed_with_tags(embedder, [chunk.text for chunk in batch], tags)
        if result is None:
            return embedded
        model, vectors_batch = result
        if not vectors_batch or len(vectors_batch[0]) == 0:
            return embedded
        store.store([chunk.id for chunk in batch], vectors_batch, model)
        session.commit()
        embedded += len(batch)
    return embedded


def _embed_token_extraction(
    session: Session,
    store: StudyVectorStore,
    chunks: list[Chunk],
    embedder: Embedder,
    profile: ChunkProfile,
    space_id: str,
) -> int:
    windows = []
    for chunk in chunks:
        try:
            windows.extend(window_specs_for_chunk(chunk, profile))
        except InputTooLong as error:
            logger.warning(
                "embedding_input_too_long",
                chunk_id=str(chunk.id),
                tokens=error.tokens,
                limit=error.limit,
            )
    embedded_chunks: set[str] = set()
    for batch in batch_window_specs(windows, profile):
        tags: dict[str, object] = {
            "space_id": space_id,
            "kind": CONTENT_SPACE_KIND,
            "view": CONTENT_VIEW,
        }
        chunk_ids = {spec.chunk_id for spec in batch}
        if len(chunk_ids) == 1:
            tags["chunk_index"] = int(batch[0].window_index)
        result = embed_with_tags(embedder, [spec.text for spec in batch], tags)
        if result is None:
            return len(embedded_chunks)
        model, vectors_batch = result
        if not vectors_batch or len(vectors_batch[0]) == 0:
            return len(embedded_chunks)
        store.store_specs(
            [
                VectorRecordSpec(
                    chunk_id=spec.chunk_id,
                    text=spec.text,
                    chunk_index=spec.window_index,
                    char_start=spec.char_start,
                    char_end=spec.char_end,
                    token_count=spec.token_count,
                    token_start=spec.token_start,
                    token_end=spec.token_end,
                )
                for spec in batch
            ],
            vectors_batch,
            model,
        )
        session.commit()
        embedded_chunks.update(spec.chunk_id for spec in batch)
    return len(embedded_chunks)


def describe_material(
    session: Session, material: Material, extraction: Extraction, describer: Describer
) -> bool:
    result = describer(material.title, extraction.markdown, material.course_id)
    if result is None:
        return False
    summary = result.get("summary")
    card = session.get(MaterialIndexCard, material.id)
    if card is None:
        card = MaterialIndexCard(material_id=material.id)
        session.add(card)
    if isinstance(summary, str) and summary.strip():
        card.summary = summary.strip()
    topics = result.get("topics")
    if isinstance(topics, list):
        card.topics = [str(topic) for topic in topics if str(topic).strip()][:12]
    key_terms = result.get("key_terms")
    if isinstance(key_terms, list):
        card.key_terms = [str(term) for term in key_terms if str(term).strip()][:20]
    difficulty = result.get("difficulty")
    if isinstance(difficulty, (int, float)) and 1 <= difficulty <= 5:
        card.difficulty = int(difficulty)
    session.flush()
    return True


def make_postprocess_handler(embedder: Embedder, describer: Describer) -> JobHandler:
    def handler(session: Session, job: Any, report: ProgressReporter) -> None:
        payload = cast(PostprocessPayload, job.payload or {})
        material = session.get(Material, payload.get("material_id"))
        if material is None:
            raise JobError("material not found")
        replaced_chunk_ids = payload.get("replaced_chunk_ids") or []
        if replaced_chunk_ids:
            StudyVectorStore(session).delete_for_extraction(
                [str(chunk_id) for chunk_id in replaced_chunk_ids]
            )
        extraction = _latest_extraction(session, payload.get("extraction_id"), material.id)
        report(20, "embedding")
        try:
            embedded = embed_extraction(session, extraction, embedder)
        except ProviderError as error:
            logger.warning("embeddings_failed", material_id=material.id, reason=str(error))
            session.rollback()
            extraction = _latest_extraction(session, payload.get("extraction_id"), material.id)
            embedded = 0
        except Exception:
            logger.warning("embeddings_failed", material_id=material.id, reason="unknown")
            session.rollback()
            extraction = _latest_extraction(session, payload.get("extraction_id"), material.id)
            embedded = 0
        session.commit()
        report(70, "index card")
        ensure_target_exists(session, Material, material.id, "material")
        try:
            described = describe_material(session, material, extraction, describer)
        except ProviderError as error:
            logger.warning("describe_failed", material_id=material.id, reason=str(error))
            session.rollback()
            described = False
        except Exception:
            logger.warning("describe_failed", material_id=material.id, reason="unknown")
            session.rollback()
            described = False
        session.commit()
        report(100, "done" if embedded or described else "skipped")

    return handler
