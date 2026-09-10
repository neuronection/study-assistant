from typing import Any, cast

import fitz
from sqlalchemy.orm import Session

from ..ai.gateway import LLMGateway, TaskUnassigned
from ..core.vocab import MaterialKind, MaterialStatus, ProvenanceKind
from ..domain.models import Chunk, Extraction, Material, MaterialIndexCard
from ..jobs.cancellation import JobCancelled, ensure_target_exists, is_cancel_requested
from ..jobs.payloads import IngestPayload
from ..jobs.runner import JobError, JobHandler, ProgressReporter
from ..ocr.base import OcrEngine
from ..services.content.materials import extraction_to_blocks
from ..storage.blobs import BlobStore
from ..storage.fts import sync_material_fts
from .chunking import chunk_markdown
from .convert import (
    ImageStore,
    convert_html_document,
    docx_to_markdown,
    epub_to_markdown,
    pptx_to_markdown,
)

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


def _embedded_ocr_text(material: Material) -> str:
    parts = [
        drawing.ocr_markdown
        for drawing in material.drawings
        if drawing.ocr_markdown
    ]
    parts += [image.ocr_markdown for image in material.images if image.ocr_markdown]
    return "\n".join(parts)


def _sync_fts(
    session: Session,
    material: Material,
    markdown: str,
) -> None:
    sync_material_fts(session, material, markdown, _embedded_ocr_text(material))


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

    ocr = _embedded_ocr_text(material)
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


def _format_duration(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def make_ingest_handler(
    blobs: BlobStore, ocr: OcrEngine | None = None, gateway: LLMGateway | None = None
) -> JobHandler:
    def handler(session: Session, job: Any, report: ProgressReporter) -> None:
        payload = cast(IngestPayload, job.payload or {})
        raw_id = payload.get("material_id")
        if raw_id is None:
            raise JobError("ingest payload missing material_id")
        material_id = int(raw_id)
        material = session.get(Material, material_id)
        if material is None:
            raise JobError(f"material {material_id} not found")

        material.status = MaterialStatus.PROCESSING
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
                fresh.status = MaterialStatus.FAILED
                session.commit()

        try:
            markdown: str = ""
            converted_kind: str | None = None
            store: ImageStore | None = None
            if material.kind == MaterialKind.PDF:
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
            elif material.kind in (MaterialKind.MD, MaterialKind.TXT):
                report(60, "building extraction")
                markdown = data.decode("utf-8", errors="replace")
                _store_extraction(
                    session, material, extractor="native", markdown=markdown, pages=None
                )
            elif material.kind == MaterialKind.IMAGE:
                mime = material.mime or "image/png"
                markdown = ocr_images([(data, mime)], 20, 60)
                _store_extraction(session, material, extractor="ocr", markdown=markdown, pages=1)
            elif material.kind == MaterialKind.DOCX:
                converted_kind = "docx"
                report(30, "converting docx")
                store = ImageStore(session, blobs, material.id)
                markdown = docx_to_markdown(data, store.store)
                _store_extraction(
                    session, material, extractor="converted:docx", markdown=markdown, pages=None
                )
            elif material.kind == MaterialKind.PPTX:
                converted_kind = "pptx"
                report(30, "converting pptx")
                store = ImageStore(session, blobs, material.id)
                markdown = pptx_to_markdown(data, store.store)
                _store_extraction(
                    session, material, extractor="converted:pptx", markdown=markdown, pages=None
                )
            elif material.kind == MaterialKind.EPUB:
                converted_kind = "epub"
                report(30, "converting epub")
                store = ImageStore(session, blobs, material.id)
                markdown = epub_to_markdown(data)
                _store_extraction(
                    session, material, extractor="converted:epub", markdown=markdown, pages=None
                )
            elif material.kind == MaterialKind.HTML:
                converted_kind = "html"
                report(30, "converting html")
                store = ImageStore(session, blobs, material.id)
                markdown = convert_html_document(data, store.store)
                _store_extraction(
                    session, material, extractor="converted:html", markdown=markdown, pages=None
                )
            elif material.kind in (MaterialKind.AUDIO, MaterialKind.VIDEO):
                if gateway is None:
                    raise JobError("transcription requires a gateway")
                report(30, "transcribing recording")
                from ..ai.gateway import ProviderError
                from ..services.platform.skills import SkillService

                skill = SkillService(session).resolve("transcribe.audio")
                instruction = skill.system_template if skill is not None else None
                mime = material.mime or "audio/mpeg"
                try:
                    result = gateway.transcribe(data, mime, instruction=instruction)
                except TaskUnassigned as error:
                    raise JobError(str(error)) from error
                except ProviderError as error:
                    raise JobError(str(error)) from error
                header_lines = [
                    f"*Transcript of `{material.filename}`",
                ]
                if material.duration_sec:
                    header_lines.append(f"({_format_duration(material.duration_sec)})")
                header_lines.append(f"— transcribed by {result.model}.*")
                markdown = " ".join(header_lines) + f"\n\n{result.text}"
                material.provenance = {
                    "source": ProvenanceKind.TRANSCRIBED,
                    "model": result.model,
                }
                _store_extraction(
                    session, material, extractor="transcribe", markdown=markdown, pages=None
                )
            else:
                raise JobError(f"unsupported material kind '{material.kind}'")
        except Exception as error:
            fail(error)
            raise

        if converted_kind is not None and store is not None:
            material.provenance = {"source": ProvenanceKind.CONVERTED, "converter": converted_kind}
            store.enqueue_ocr_jobs(session)

        report(80, "indexing")
        _sync_fts(session, material, markdown)
        ensure_target_exists(session, Material, int(material_id), "material")
        material.status = MaterialStatus.READY
        from ..jobs.runner import JobRunner

        JobRunner.enqueue(
            session,
            "postprocess",
            {"material_id": material.id},
        )
        session.commit()
        report(100, "done")

    return handler
