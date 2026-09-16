import tempfile
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from ..domain.models import Material
from ..jobs.cancellation import JobCancelled, is_cancel_requested
from ..jobs.payloads import IngestPayload, UrlImportPayload
from ..jobs.runner import JobError, JobHandler, JobRunner, ProgressReporter
from ..parsers import build_registry, resolve_parser
from ..services.content.materials import MaterialsService
from ..storage.blobs import BlobStore


def make_url_import_handler(
    blobs: BlobStore,
    transport_provider: Any = None,
) -> JobHandler:
    def handler(session: Session, job: Any, report: ProgressReporter) -> None:
        payload = cast(UrlImportPayload, job.payload or {})
        raw_material_id = payload.get("material_id")
        if raw_material_id is None:
            raise JobError("url_import payload missing material_id")
        material = session.get(Material, int(raw_material_id))
        if material is None:
            raise JobError(f"material {raw_material_id} not found")
        if material.source_url is None:
            raise JobError("material has no source URL")
        if is_cancel_requested(job.id):
            raise JobCancelled()
        source_url = material.source_url
        action = str(payload.get("action") or "parse")
        if action == "transcribe_audio":
            _transcribe_audio(session, blobs, material, job, report)
            return
        report(20, "fetch")
        transport = (
            transport_provider() if transport_provider is not None else None
        )
        registry = build_registry(transport, language=material.language)
        parser = resolve_parser(registry, source_url)
        if parser is None:
            raise JobError(
                f"no parser for this URL: {source_url} — the link stays "
                "as a reference"
            )
        report(40, "download")
        parsed = parser.fetch(source_url)
        if is_cancel_requested(job.id):
            raise JobCancelled()
        report(80, "import")
        if parsed.blob is not None:
            stored = blobs.put(parsed.blob, mime=parsed.mime, session=session)
            material.blob_sha = stored.sha256
            material.mime = parsed.mime
            material.kind = parsed.kind_hint or material.kind
            material.status = "pending"
            session.commit()
            JobRunner.enqueue(
                session,
                "ingest",
                IngestPayload(material_id=material.id, blob_sha=material.blob_sha),
            )
            session.commit()
            report(100, "done")
            return
        markdown = parsed.markdown
        if not markdown or not markdown.strip():
            if parsed.metadata.get("parse_note"):
                provenance = dict(material.provenance or {})
                provenance.update(parsed.metadata)
                material.provenance = provenance
                if parsed.title:
                    material.title = parsed.title[:300] or material.title
                session.commit()
                report(100, "done")
                return
            raise JobError(f"parser returned no content for {source_url}")
        provenance = dict(material.provenance or {})
        provenance.update(parsed.metadata)
        material.provenance = provenance
        if parsed.title:
            material.title = parsed.title[:300] or material.title
        service = MaterialsService(session, blobs)
        service.edit_extraction(material, markdown.strip())
        session.commit()
        report(100, "done")

    return handler


def _transcribe_audio(
    session: Session,
    blobs: BlobStore,
    material: Material,
    job: Any,
    report: ProgressReporter,
) -> None:
    source_url = material.source_url
    if source_url is None:
        raise JobError("material has no source URL")
    report(30, "download")
    from app.parsers.youtube import download_audio

    with tempfile.TemporaryDirectory(prefix="sa-audio-") as target_dir:
        try:
            path, _title = download_audio(source_url, target_dir)
        except Exception as error:
            raise JobError(
                f"audio download failed for {source_url} ({error}). "
                "YouTube may have changed; try updating yt-dlp."
            ) from error
        if is_cancel_requested(job.id):
            raise JobCancelled()
        report(80, "transcribe-queue")
        data = Path(path).read_bytes()
        suffix = Path(path).suffix.lower() or ".m4a"
        mime = {
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".opus": "audio/opus",
            ".webm": "video/webm",
        }.get(suffix, "audio/mp4")
        stored = blobs.put(data, mime=mime, session=session)
        material.blob_sha = stored.sha256
        material.kind = "audio"
        material.mime = mime
        material.status = "pending"
        session.commit()
        JobRunner.enqueue(
            session,
            "ingest",
            IngestPayload(material_id=material.id, blob_sha=material.blob_sha),
        )
        session.commit()
        report(100, "done")
