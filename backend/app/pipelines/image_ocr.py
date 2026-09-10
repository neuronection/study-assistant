from typing import Any, cast

from sqlalchemy.orm import Session

from ..ai.gateway import LLMGateway, ProviderError, TaskUnassigned
from ..domain.models import Material, MaterialImage
from ..jobs.cancellation import ensure_target_exists
from ..jobs.payloads import ImageOcrPayload
from ..jobs.runner import JobError, JobHandler, ProgressReporter
from ..ocr.notes_ocr import NotesOcrEngine
from ..services.content.materials import MaterialsService
from ..storage.blobs import BlobStore
from ..storage.fts import sync_material_fts


def make_image_ocr_handler(gateway: LLMGateway, blobs: BlobStore) -> JobHandler:
    def handler(session: Session, job: Any, report: ProgressReporter) -> None:
        payload = cast(ImageOcrPayload, job.payload or {})
        image_id = payload.get("image_id")
        material_id = payload.get("material_id")
        if image_id is None or material_id is None:
            raise JobError(f"invalid image_ocr payload: {payload!r}")

        report(20, "loading image")
        image = session.get(MaterialImage, int(image_id))
        if image is None:
            raise JobError(f"material image {image_id} not found")
        if image.blob_sha is None:
            raise JobError("material image has no stored blob")
        data = blobs.get(image.blob_sha)
        if data is None:
            raise JobError("material image missing from store")

        report(40, "transcribing")
        engine = NotesOcrEngine(gateway)
        try:
            markdown = engine.transcribe(
                data, image.mime or "image/png", session=session
            )
        except (TaskUnassigned, ProviderError) as error:
            raise JobError(str(error)) from error

        ensure_target_exists(session, MaterialImage, int(image_id), "material image")
        image.ocr_version += 1
        image.ocr_markdown = markdown
        image.ocr_job_id = None

        material = session.get(Material, int(material_id))
        if material is None:
            raise JobError(f"material {material_id} not found")
        service = MaterialsService(session, blobs)
        latest = service.latest_extraction(material.id)
        sync_material_fts(
            session,
            material,
            latest.markdown if latest is not None else "",
            service.embedded_ocr_text(material),
        )
        session.commit()
        report(100, "done")

    return handler
