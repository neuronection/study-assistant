from sqlalchemy.orm import Session

from ...domain.models import MaterialImage
from ...storage.blobs import BlobStore


class ImageStore:
    """Stores images extracted from converted documents as `material_images`
    rows and records their ids so the caller can enqueue `image_ocr` jobs
    after the extraction is committed."""

    def __init__(self, session: Session, blobs: BlobStore, material_id: int) -> None:
        self._session = session
        self._blobs = blobs
        self._material_id = material_id
        self._position = 0
        self.image_ids: list[int] = []

    def store(self, data: bytes, mime: str | None = None) -> int:
        resolved_mime = mime or "image/png"
        stored = self._blobs.put(data, mime=resolved_mime, session=self._session)
        image = MaterialImage(
            material_id=self._material_id,
            position=self._position,
            blob_sha=stored.sha256,
            mime=resolved_mime,
        )
        self._position += 1
        self._session.add(image)
        self._session.flush()
        self.image_ids.append(image.id)
        return image.id

    def enqueue_ocr_jobs(self, runner_session: Session) -> int:
        from ...jobs.runner import JobRunner

        for image_id in self.image_ids:
            JobRunner.enqueue(
                runner_session,
                "image_ocr",
                {"image_id": image_id, "material_id": self._material_id},
            )
        return len(self.image_ids)
