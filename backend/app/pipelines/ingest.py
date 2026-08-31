from typing import Any

import fitz
from sqlalchemy.orm import Session

from ..ai.gateway import TaskUnassigned
from ..domain.models import Chunk, Extraction, Material, MaterialIndexCard
from ..jobs.cancellation import JobCancelled, ensure_target_exists, is_cancel_requested
from ..jobs.runner import JobError, JobHandler, ProgressReporter
from ..ocr.base import OcrEngine
from ..services.content.materials import extraction_to_blocks
from ..storage.blobs import BlobStore
from ..storage.fts import sync_material_fts
from .chunking import chunk_markdown

MIN_TEXT_CHARS_PER_PAGE = 50
OCR_RASTER_DPI = 150


def rasterize_pages(data: bytes, dpi: int = OCR_RASTER_DPI) -> list[tuple[bytes, str]]:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as error:
        raise JobError(f"cannot open PDF: {error}") from error
    pages: list[tuple[bytes, str]] = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        pages.append((bytes(pix.tobytes("png")), "image/png"))
    return pages


def extract_pdf_text(data: bytes) -> tuple[str, int, bool]:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as error:
        raise JobError(f"cannot open PDF: {error}") from error
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text("text"))
    total_chars = sum(len(page.strip()) for page in pages)
    has_text_layer = total_chars >= MIN_TEXT_CHARS_PER_PAGE * max(1, len(pages))
    markdown = "\n\n".join(page.strip() for page in pages if page.strip())
    return markdown, len(pages), has_text_layer


def _sync_fts(
    session: Session,
    material: Material,
    markdown: str,
) -> None:
    sync_material_fts(session, material, markdown, _drawing_ocr_text(material))


def _drawing_ocr_text(material: Material) -> str:
    parts = [
        drawing.ocr_markdown
        for drawing in material.drawings
        if drawing.ocr_markdown
    ]
    return "\n".join(parts)


def _store_extraction(
    session: Session,
    material: Material,
    *,
    extractor: str,
    markdown: str,
    pages: int | None,
) -> Extraction:
    material.pages = pages
    version = 1
    latest = (
        session.query(Extraction.version)
        .filter(Extraction.material_id == material.id)
        .order_by(Extraction.version.desc())
        .first()
    )
    if latest is not None:
        version = latest[0] + 1
    extraction = Extraction(
        material_id=material.id,
        version=version,
        extractor=extractor,
        blocks=extraction_to_blocks(markdown),
        markdown=markdown,
    )
    session.add(extraction)
    session.flush()

    ocr = _drawing_ocr_text(material)
    chunk_source = f"{markdown}\n\n{ocr}" if ocr else markdown
    for ordinal, chunk_text in enumerate(chunk_markdown(chunk_source)):
        session.add(
            Chunk(
                extraction_id=extraction.id,
                ordinal=ordinal,
                text=chunk_text,
                token_count=max(1, len(chunk_text) // 4),
            )
        )
    words = len(markdown.split())
    session.merge(
        MaterialIndexCard(
            material_id=material.id,
            summary=None,
            topics=[],
            key_terms=[],
            reading_minutes=max(1, words // 220),
            difficulty=None,
        )
    )
    return extraction


def make_ingest_handler(blobs: BlobStore, ocr: OcrEngine | None = None) -> JobHandler:
    def handler(session: Session, job: Any, report: ProgressReporter) -> None:
        payload: dict[str, Any] = job.payload or {}
        raw_id = payload.get("material_id")
        if raw_id is None:
            raise JobError("ingest payload missing material_id")
        material_id = int(raw_id)
        material = session.get(Material, material_id)
        if material is None:
            raise JobError(f"material {material_id} not found")

        material.status = "processing"
        session.commit()
        report(10, "reading file")

        data = blobs.get(material.blob_sha) if material.blob_sha else None
        if data is None:
            raise JobError("blob content missing from store")

        def ocr_images(images: list[tuple[bytes, str]], base_progress: int, span: int) -> str:
            if ocr is None:
                raise JobError(
                    "OCR task unassigned — connect a provider and assign a vision model in Settings"
                )
            parts: list[str] = []
            for index, (image_data, mime) in enumerate(images):
                try:
                    result = ocr.ocr_image(image_data, mime, session=session)
                except TaskUnassigned as error:
                    raise JobError(str(error)) from error
                parts.append(result.markdown)
                report(
                    base_progress + span * (index + 1) // max(1, len(images)),
                    f"ocr page {index + 1}/{len(images)}",
                )
            return "\n\n".join(part for part in parts if part)

        def fail(error: Exception) -> None:
            session.rollback()
            if isinstance(error, JobCancelled) or is_cancel_requested(job.id):
                return
            fresh = session.get(Material, material_id)
            if fresh is not None:
                fresh.status = "failed"
                session.commit()

        try:
            markdown: str = ""
            if material.kind == "pdf":
                report(30, "extracting pdf text")
                text_markdown, pages, has_text_layer = extract_pdf_text(data)
                if has_text_layer:
                    report(60, "building extraction")
                    markdown = text_markdown
                    _store_extraction(
                        session, material, extractor="pymupdf", markdown=markdown, pages=pages
                    )
                else:
                    material.pages = pages
                    session.commit()
                    markdown = ocr_images(rasterize_pages(data), 30, 50)
                    _store_extraction(
                        session, material, extractor="ocr", markdown=markdown, pages=pages
                    )
            elif material.kind in ("md", "txt"):
                report(60, "building extraction")
                markdown = data.decode("utf-8", errors="replace")
                _store_extraction(
                    session, material, extractor="native", markdown=markdown, pages=None
                )
            elif material.kind == "image":
                mime = material.mime or "image/png"
                markdown = ocr_images([(data, mime)], 20, 60)
                _store_extraction(session, material, extractor="ocr", markdown=markdown, pages=1)
            else:
                raise JobError(f"unsupported material kind '{material.kind}'")
        except Exception as error:
            fail(error)
            raise

        report(80, "indexing")
        _sync_fts(session, material, markdown)
        ensure_target_exists(session, Material, int(material_id), "material")
        material.status = "ready"
        from ..jobs.runner import JobRunner

        JobRunner.enqueue(
            session,
            "postprocess",
            {"material_id": material.id},
        )
        session.commit()
        report(100, "done")

    return handler
