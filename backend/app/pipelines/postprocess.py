from collections.abc import Callable
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.gateway import ProviderError
from ..domain.models import Chunk, Extraction, Material, MaterialIndexCard
from ..jobs.runner import JobError, JobHandler, ProgressReporter
from ..storage import vectors

logger = structlog.get_logger(__name__)

Embedder = Callable[[list[str]], tuple[str, list[list[float]]] | None]
Describer = Callable[[str, str, int | None], dict[str, Any] | None]

EMBED_BATCH = 32


def _latest_extraction(session: Session, extraction_id: int | None, material_id: int) -> Extraction:
    if extraction_id is not None:
        extraction = session.get(Extraction, extraction_id)
        if extraction is not None:
            return extraction
    extraction = (
        session.scalars(
            select(Extraction)
            .where(Extraction.material_id == material_id)
            .order_by(Extraction.version.desc())
            .limit(1)
        ).first()
    )
    if extraction is None:
        raise JobError(f"no extraction for material {material_id}")
    return extraction


def embed_extraction(
    session: Session, extraction: Extraction, embedder: Embedder
) -> int:
    chunks = list(
        session.scalars(
            select(Chunk).where(Chunk.extraction_id == extraction.id).order_by(Chunk.ordinal)
        )
    )
    if not chunks:
        return 0
    embedded = 0
    for start in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[start : start + EMBED_BATCH]
        result = embedder([chunk.text for chunk in batch])
        if result is None:
            return embedded
        model, vectors_batch = result
        if not vectors_batch or len(vectors_batch[0]) == 0:
            return embedded
        vectors.store(
            session, [chunk.id for chunk in batch], vectors_batch, model
        )
        session.commit()
        embedded += len(batch)
    return embedded


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
        payload: dict[str, Any] = job.payload or {}
        material = session.get(Material, payload.get("material_id"))
        if material is None:
            raise JobError("material not found")
        old_chunk_ids = payload.get("old_chunk_ids") or []
        if old_chunk_ids:
            vectors.delete_for_extraction(session, [int(chunk_id) for chunk_id in old_chunk_ids])
        extraction = _latest_extraction(
            session, payload.get("extraction_id"), material.id
        )
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
