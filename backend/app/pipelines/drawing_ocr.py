from typing import Any

from sqlalchemy.orm import Session

from ..ai.gateway import LLMGateway, ProviderError, TaskUnassigned
from ..domain.models import Material, MaterialDrawing, Note, NoteDrawing, utcnow
from ..jobs.cancellation import ensure_target_exists
from ..jobs.runner import JobError, JobHandler, ProgressReporter
from ..ocr.notes_ocr import NotesOcrEngine
from ..services.drawings import note_search_text
from ..services.materials import MaterialsService
from ..storage.blobs import BlobStore
from ..storage.fts import sync_material_fts


def make_drawing_ocr_handler(gateway: LLMGateway, blobs: BlobStore) -> JobHandler:
    def handler(session: Session, job: Any, report: ProgressReporter) -> None:
        payload: dict[str, Any] = job.payload or {}
        kind = payload.get("kind")
        drawing_id = payload.get("drawing_id")
        owner_id = payload.get(f"{kind}_id") if kind in ("note", "material") else None
        if kind not in ("note", "material") or drawing_id is None or owner_id is None:
            raise JobError(f"invalid drawing_ocr payload: {payload!r}")

        report(20, "loading drawing")
        loaded: NoteDrawing | MaterialDrawing | None
        if kind == "note":
            loaded = session.get(NoteDrawing, int(drawing_id))
        else:
            loaded = session.get(MaterialDrawing, int(drawing_id))
        if loaded is None:
            raise JobError(f"drawing {drawing_id} not found")
        drawing = loaded
        if drawing.png_sha is None:
            raise JobError("drawing has no stored image")
        png = blobs.get(drawing.png_sha)
        if png is None:
            raise JobError("drawing image missing from store")

        report(40, "transcribing")
        engine = NotesOcrEngine(gateway)
        try:
            markdown = engine.transcribe(png, "image/png", session=session)
        except (TaskUnassigned, ProviderError) as error:
            raise JobError(str(error)) from error

        model = NoteDrawing if kind == "note" else MaterialDrawing
        ensure_target_exists(session, model, int(drawing_id), "drawing")
        drawing.ocr_version += 1
        drawing.ocr_blocks = [{"type": "text", "md": markdown}]
        drawing.ocr_markdown = markdown
        drawing.ocr_job_id = None

        if kind == "note":
            note = session.get(Note, int(owner_id))
            if note is None:
                raise JobError(f"note {owner_id} not found")
            note.search_text = note_search_text(note)
            note.updated_at = utcnow()
        else:
            material = session.get(Material, int(owner_id))
            if material is None:
                raise JobError(f"material {owner_id} not found")
            service = MaterialsService(session, blobs)
            latest = service.latest_extraction(material.id)
            sync_material_fts(
                session,
                material,
                latest.markdown if latest is not None else "",
                service.drawing_ocr_text(material),
            )
        session.commit()
        report(100, "done")

    return handler
