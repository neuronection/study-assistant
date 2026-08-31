from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...domain.models import (
    Blob,
    Chunk,
    Course,
    Extraction,
    Material,
    MaterialDrawing,
    MaterialFolder,
    MaterialIndexCard,
    MaterialLink,
    MaterialStudyState,
    TreeNode,
)
from ...jobs.cancellation import cancel_jobs_for_material
from ...jobs.runner import JobRunner
from ...pipelines.chunking import chunk_markdown
from ...storage import vectors
from ...storage.blobs import BlobStore
from ...storage.fts import delete_material_fts, sync_material_fts
from .drawings import drawing_ref_ids, md_to_blocks, remap_drawing_refs

KIND_BY_SUFFIX: dict[str, str] = {
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".md": "md",
    ".markdown": "md",
    ".txt": "txt",
}

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def detect_kind(filename: str) -> str:
    suffix = PurePosixPath(filename.lower()).suffix
    return KIND_BY_SUFFIX.get(suffix, "doc")


def purge_material(session: Session, material: Material) -> None:
    cancel_jobs_for_material(session, material.id)
    extraction_ids = list(
        session.scalars(
            select(Extraction.id).where(Extraction.material_id == material.id)
        )
    )
    chunk_ids = list(
        session.scalars(
            select(Chunk.id).where(Chunk.extraction_id.in_(extraction_ids))
        )
    ) if extraction_ids else []
    if chunk_ids:
        vectors.delete_for_extraction(session, chunk_ids)
    if extraction_ids:
        session.execute(delete(Chunk).where(Chunk.extraction_id.in_(extraction_ids)))
        session.execute(delete(Extraction).where(Extraction.id.in_(extraction_ids)))
    session.execute(
        delete(MaterialIndexCard).where(MaterialIndexCard.material_id == material.id)
    )
    session.execute(
        delete(MaterialStudyState).where(MaterialStudyState.material_id == material.id)
    )
    session.execute(
        delete(MaterialLink).where(MaterialLink.material_id == material.id)
    )
    session.execute(
        delete(MaterialDrawing).where(MaterialDrawing.material_id == material.id)
    )
    delete_material_fts(session, material.id)
    session.delete(material)


class MaterialsService:
    def __init__(self, session: Session, blobs: BlobStore) -> None:
        self._session = session
        self._blobs = blobs

    def upload(
        self,
        *,
        profile_id: int,
        filename: str,
        data: bytes,
        mime: str | None,
        course_id: int,
        group_id: int | None = None,
        folder_id: int | None = None,
        dedup_exclude_id: int | None = None,
    ) -> tuple[Material, bool]:
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("file exceeds upload size limit")
        if not data:
            raise ValueError("empty file")
        course = self._session.get(Course, course_id)
        if course is None or course.profile_id != profile_id:
            raise ValueError("course not found")
        if folder_id is not None:
            folder = self._session.get(MaterialFolder, folder_id)
            if folder is None or folder.profile_id != profile_id:
                raise ValueError("folder not found")
            if folder.course_id != course_id:
                raise ValueError("folder belongs to a different course")
            if folder.source_id is not None:
                raise ValueError("cannot upload into a linked folder")
        sha256 = self._blobs.put(data, mime=mime, session=self._session)
        existing = self._find_duplicate(
            profile_id, course_id, sha256.sha256, exclude_id=dedup_exclude_id
        )
        if existing is not None:
            return existing, True
        material = Material(
            profile_id=profile_id,
            course_id=course_id,
            group_id=group_id,
            folder_id=folder_id,
            kind=detect_kind(filename),
            title=PurePosixPath(filename).stem or filename,
            blob_sha=sha256.sha256,
            filename=filename,
            mime=mime,
            status="pending",
            content_hash=sha256.sha256,
        )
        self._session.add(material)
        self._session.flush()
        return material, False

    def create_text(
        self,
        *,
        profile_id: int,
        course_id: int,
        filename: str,
        content: str,
        folder_id: int | None = None,
        dedup_exclude_id: int | None = None,
    ) -> tuple[Material, bool]:
        name = filename.strip()
        if not name:
            raise ValueError("filename is required")
        if "/" in name or "\\" in name:
            raise ValueError("filename cannot contain path separators")
        if not name.lower().endswith((".txt", ".md", ".markdown")):
            name = f"{name}.txt"
        return self.upload(
            profile_id=profile_id,
            filename=name,
            data=content.encode("utf-8"),
            mime="text/plain" if name.lower().endswith(".txt") else "text/markdown",
            course_id=course_id,
            folder_id=folder_id,
            dedup_exclude_id=dedup_exclude_id,
        )

    def rename(self, material: Material, title: str) -> Material:
        title = title.strip()
        if not title:
            raise ValueError("title cannot be empty")
        material.title = title[:300]
        self._session.flush()
        return material

    def _validated_target_folder(
        self, material: Material, folder_id: int | None
    ) -> None:
        if folder_id is None:
            return
        folder = self._session.get(MaterialFolder, folder_id)
        if folder is None or folder.profile_id != material.profile_id:
            raise ValueError("folder not found")
        if folder.course_id != material.course_id:
            raise ValueError("folder belongs to a different course")
        if folder.source_id is not None:
            raise ValueError("cannot move into a linked folder")

    def move(self, material: Material, folder_id: int | None) -> Material:
        self._validated_target_folder(material, folder_id)
        material.folder_id = folder_id
        self._session.flush()
        return material

    def _unique_title(
        self, base_title: str, label: str, folder_id: int | None, course_id: int
    ) -> str:
        taken = set(
            self._session.scalars(
                select(Material.title).where(
                    Material.course_id == course_id,
                    Material.folder_id == folder_id,
                )
            )
        )
        counter = 1
        while True:
            tail = f" {counter}" if counter > 1 else ""
            candidate = f"{base_title[: 300 - len(label) - len(tail) - 3]} ({label}{tail})"
            if candidate not in taken:
                return candidate
            counter += 1

    def _copy_title(self, base_title: str, folder_id: int | None, course_id: int) -> str:
        return self._unique_title(base_title, "copy", folder_id, course_id)

    def copy(
        self, material: Material, folder_id: int | None, runner: JobRunner
    ) -> Material:
        self._validated_target_folder(material, folder_id)
        copy = Material(
            profile_id=material.profile_id,
            course_id=material.course_id,
            group_id=material.group_id,
            folder_id=folder_id,
            kind=material.kind,
            title=self._copy_title(material.title, folder_id, material.course_id),
            blob_sha=material.blob_sha,
            filename=material.filename,
            mime=material.mime,
            pages=material.pages,
            language=material.language,
            status=material.status,
            provenance=material.provenance,
            content_hash=material.content_hash,
        )
        self._session.add(copy)
        self._session.flush()
        extraction = self.latest_extraction(material.id)
        if extraction is not None:
            row = Extraction(
                material_id=copy.id,
                version=1,
                extractor=extraction.extractor,
                model=extraction.model,
                blocks=extraction.blocks,
                markdown=extraction.markdown,
                language=extraction.language,
                reviewed=extraction.reviewed,
            )
            self._session.add(row)
            self._session.flush()
            for chunk in self._session.scalars(
                select(Chunk)
                .where(Chunk.extraction_id == extraction.id)
                .order_by(Chunk.ordinal)
            ):
                self._session.add(
                    Chunk(
                        extraction_id=row.id,
                        ordinal=chunk.ordinal,
                        text=chunk.text,
                        token_count=chunk.token_count,
                    )
                )
            sync_material_fts(self._session, copy, extraction.markdown)
        card = self._session.get(MaterialIndexCard, material.id)
        if card is not None:
            self._session.add(
                MaterialIndexCard(
                    material_id=copy.id,
                    summary=card.summary,
                    topics=card.topics,
                    key_terms=card.key_terms,
                    reading_minutes=card.reading_minutes,
                    difficulty=card.difficulty,
                )
            )
        if extraction is not None:
            JobRunner.enqueue(
                self._session, "postprocess", {"material_id": copy.id}
            )
            runner.wake()
        self._session.flush()
        return copy

    def derive(
        self, material: Material, folder_id: int | None, node_id: int | None = None
    ) -> tuple[Material, bool]:
        extraction = self.latest_extraction(material.id)
        if extraction is None or not extraction.markdown.strip():
            raise ValueError("material has no extraction to derive")
        if folder_id is not None:
            self._validated_target_folder(material, folder_id)
        elif material.folder_id is not None:
            folder = self._session.get(MaterialFolder, material.folder_id)
            if folder is not None and folder.source_id is None:
                folder_id = material.folder_id
        target_node_ids: set[int] = set()
        if node_id is not None:
            node = self._session.get(TreeNode, node_id)
            if node is None:
                raise ValueError("node not found")
            if node.course_id != material.course_id:
                raise ValueError("node belongs to a different course")
            target_node_ids.add(node_id)
        base_title = material.title.replace("/", "-").replace("\\", "-").strip() or "material"
        title = self._unique_title(base_title, "extracted", folder_id, material.course_id)
        derived, deduped = self.create_text(
            profile_id=material.profile_id,
            course_id=material.course_id,
            filename=f"{title}.md",
            content=extraction.markdown,
            folder_id=folder_id,
            dedup_exclude_id=material.id,
        )
        if deduped:
            return derived, True
        source_drawings = list(material.drawings)
        if source_drawings:
            mapping: dict[int, int] = {}
            for source_drawing in source_drawings:
                new_drawing = MaterialDrawing(
                    material_id=derived.id,
                    strokes=source_drawing.strokes,
                    png_sha=source_drawing.png_sha,
                    view=source_drawing.view,
                    ocr_version=source_drawing.ocr_version,
                    ocr_blocks=source_drawing.ocr_blocks,
                    ocr_markdown=source_drawing.ocr_markdown,
                )
                self._session.add(new_drawing)
                self._session.flush()
                mapping[source_drawing.id] = new_drawing.id
            remapped = remap_drawing_refs(extraction.markdown, mapping)
            stored = self._blobs.put(
                remapped.encode("utf-8"), mime="text/markdown", session=self._session
            )
            derived.blob_sha = stored.sha256
            derived.content_hash = stored.sha256
            self._session.flush()
        derived.provenance = {
            "source": "derived",
            "from_material_id": material.id,
            "from_version": extraction.version,
        }
        for link in self._session.scalars(
            select(MaterialLink).where(MaterialLink.material_id == material.id)
        ):
            target_node_ids.add(link.node_id)
        rationale = f"Derived from {material.title}"
        for target_node_id in sorted(target_node_ids):
            self._session.add(
                MaterialLink(
                    course_id=material.course_id,
                    node_id=target_node_id,
                    material_id=derived.id,
                    rationale=rationale,
                )
            )
        self._session.flush()
        return derived, False

    def _find_duplicate(
        self,
        profile_id: int,
        course_id: int,
        content_hash: str,
        exclude_id: int | None = None,
    ) -> Material | None:
        query = select(Material).where(
            Material.profile_id == profile_id,
            Material.course_id == course_id,
            Material.content_hash == content_hash,
            Material.status != "failed",
        )
        if exclude_id is not None:
            query = query.where(Material.id != exclude_id)
        return self._session.scalars(query.order_by(Material.id)).first()

    def queue_ingest(self, material: Material, runner: JobRunner) -> int:
        job = JobRunner.enqueue(
            self._session, "ingest", {"material_id": material.id, "blob_sha": material.blob_sha}
        )
        runner.wake()
        return job.id

    def list_materials(
        self,
        *,
        profile_id: int,
        course_id: int | None = None,
        folder_id: int | None = None,
        unfiled: bool = False,
    ) -> list[Material]:
        query = select(Material).where(Material.profile_id == profile_id)
        if course_id is not None:
            query = query.where(Material.course_id == course_id)
        if folder_id is not None:
            query = query.where(Material.folder_id == folder_id)
        elif unfiled:
            query = query.where(
                Material.folder_id.is_(None), Material.source_id.is_(None)
            )
        return list(self._session.scalars(query.order_by(Material.created_at.desc())))

    def get(self, material_id: int, *, profile_id: int) -> Material | None:
        material = self._session.get(Material, material_id)
        if material is None or material.profile_id != profile_id:
            return None
        return material

    def latest_extraction(self, material_id: int) -> Extraction | None:
        return self._session.scalars(
            select(Extraction)
            .where(Extraction.material_id == material_id)
            .order_by(Extraction.version.desc())
            .limit(1)
        ).first()

    def edit_extraction(
        self, material: Material, markdown: str
    ) -> tuple[Extraction, list[int]]:
        markdown = markdown.strip()
        if not markdown:
            raise ValueError("extraction markdown cannot be empty")
        unknown = drawing_ref_ids(markdown) - {
            drawing.id for drawing in material.drawings
        }
        if unknown:
            raise ValueError(f"unknown drawing reference(s): {sorted(unknown)}")
        latest = self.latest_extraction(material.id)
        version = (latest.version + 1) if latest is not None else 1
        previous_chunk_ids: list[int] = []
        if latest is not None:
            previous_chunk_ids = list(
                self._session.scalars(
                    select(Chunk.id).where(Chunk.extraction_id == latest.id)
                )
            )
        extraction = Extraction(
            material_id=material.id,
            version=version,
            extractor=latest.extractor if latest is not None else "manual",
            blocks=extraction_to_blocks(markdown),
            markdown=markdown,
            reviewed=True,
            edited_by_user=True,
        )
        self._session.add(extraction)
        self._session.flush()
        ocr = self.drawing_ocr_text(material)
        chunk_source = f"{markdown}\n\n{ocr}" if ocr else markdown
        for ordinal, chunk_text in enumerate(chunk_markdown(chunk_source)):
            self._session.add(
                Chunk(
                    extraction_id=extraction.id,
                    ordinal=ordinal,
                    text=chunk_text,
                    token_count=max(1, len(chunk_text) // 4),
                )
            )
        words = len(markdown.split())
        self._session.merge(
            MaterialIndexCard(
                material_id=material.id,
                summary=None,
                topics=[],
                key_terms=[],
                reading_minutes=max(1, words // 220),
                difficulty=None,
            )
        )
        sync_material_fts(self._session, material, markdown, self.drawing_ocr_text(material))
        self._session.flush()
        return extraction, previous_chunk_ids

    def drawing_ocr_text(self, material: Material) -> str:
        parts = [
            drawing.ocr_markdown
            for drawing in material.drawings
            if drawing.ocr_markdown
        ]
        return "\n".join(parts)

    def blob_bytes(self, material: Material) -> bytes | None:
        if material.blob_sha is None:
            return None
        return self._blobs.get(material.blob_sha)

    def index_card(self, material_id: int) -> MaterialIndexCard | None:
        return self._session.get(MaterialIndexCard, material_id)

    def blob_row(self, sha: str) -> Blob | None:
        return self._session.get(Blob, sha)


def _split_top_level(markdown: str) -> list[str]:
    segments: list[list[str]] = []
    current: list[str] = []
    fence_marker = ""
    for line in markdown.split("\n"):
        stripped = line.lstrip(" \t")
        if not fence_marker:
            for marker in ("```", "~~~"):
                if stripped.startswith(marker):
                    fence_marker = marker
                    break
        elif stripped.startswith(fence_marker):
            fence_marker = ""
        if line.strip() == "" and not fence_marker:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(line)
    if current:
        segments.append(current)
    return ["\n".join(segment).strip() for segment in segments]


def extraction_to_blocks(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for part in _split_top_level(markdown):
        if not part:
            continue
        blocks.extend(md_to_blocks(part))
    return blocks
