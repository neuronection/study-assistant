import hashlib
import mimetypes
import os
import posixpath
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import MaterialStatus
from ...domain.models import (
    Blob,
    Course,
    Material,
    MaterialFolder,
    MaterialSource,
    utcnow,
)
from .materials import detect_kind

DEFAULT_GLOBS = ("*.pdf", "*.png", "*.jpg", "*.jpeg", "*.webp", "*.md", "*.markdown", "*.txt")

MAX_BROWSE_DEPTH = 32


class SourcesError(ValueError):
    pass


def _iter_files(root: Path, recursive: bool, globs: list[str]) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    allowed = {glob.lower() for glob in globs}
    files: list[Path] = []
    for path in sorted(root.glob(pattern)):
        if not path.is_file():
            continue
        if allowed and path.name.lower() not in allowed and not any(
            path.match(glob) for glob in globs
        ):
            continue
        files.append(path)
    return files


def _content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _matches_globs(name: str, globs: list[str]) -> bool:
    from fnmatch import fnmatch

    return any(fnmatch(name.lower(), glob.lower()) for glob in globs)


def _sanitize_label(label: str) -> str:
    cleaned = label.replace("/", "-").replace("\\", "-").strip()
    return cleaned[:200] or "link"


class SourcesService:
    def __init__(self, session: Session, blobs_root: Path) -> None:
        self._session = session
        self._blobs_root = blobs_root

    def _get(self, profile_id: int, source_id: int) -> MaterialSource:
        source = self._session.get(MaterialSource, source_id)
        if source is None or source.profile_id != profile_id:
            raise SourcesError("source not found")
        return source

    def _link_folder(self, source_id: int) -> MaterialFolder | None:
        return self._session.scalars(
            select(MaterialFolder).where(MaterialFolder.source_id == source_id)
        ).first()

    def _create_link_node(self, source: MaterialSource) -> MaterialFolder:
        base = _sanitize_label(source.label)
        taken = {
            folder.name
            for folder in self._session.scalars(
                select(MaterialFolder).where(
                    MaterialFolder.course_id == source.course_id,
                    MaterialFolder.parent_id.is_(None),
                )
            )
        }
        name = base
        index = 2
        while name in taken:
            name = f"{base[:190]} ({index})"
            index += 1
        node = MaterialFolder(
            profile_id=source.profile_id,
            course_id=source.course_id,
            parent_id=None,
            name=name,
            path=name,
            source_id=source.id,
        )
        self._session.add(node)
        self._session.flush()
        return node

    def list_sources(self, profile_id: int) -> list[MaterialSource]:
        return list(
            self._session.scalars(
                select(MaterialSource).where(MaterialSource.profile_id == profile_id)
            )
        )

    def create_source(
        self,
        profile_id: int,
        *,
        label: str,
        path: str,
        recursive: bool = True,
        include_globs: list[str] | None = None,
        course_id: int | None = None,
        scan_interval_sec: int | None = None,
    ) -> MaterialSource:
        if course_id is None:
            raise SourcesError("a course is required for a linked source")
        course = self._session.get(Course, course_id)
        if course is None or course.profile_id != profile_id:
            raise SourcesError("course not found")
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            raise SourcesError(f"not a directory: {resolved}")
        if scan_interval_sec is not None and scan_interval_sec < 15:
            raise SourcesError("scan interval must be at least 15 seconds")
        source = MaterialSource(
            profile_id=profile_id,
            label=_sanitize_label(label) or resolved.name,
            path=str(resolved),
            recursive=recursive,
            include_globs=include_globs or list(DEFAULT_GLOBS),
            course_id=course_id,
            scan_interval_sec=scan_interval_sec,
        )
        self._session.add(source)
        self._session.flush()
        self._create_link_node(source)
        return source

    def delete_source(self, profile_id: int, source_id: int) -> bool:
        source = self._session.get(MaterialSource, source_id)
        if source is None or source.profile_id != profile_id:
            return False
        self._unlink_materials(source_id)
        node = self._link_folder(source_id)
        if node is not None:
            self._session.delete(node)
        self._session.delete(source)
        return True

    def _unlink_materials(self, source_id: int) -> None:
        for material in self._session.scalars(
            select(Material).where(Material.source_id == source_id)
        ):
            material.source_id = None
            material.external_path = None
            material.folder_id = None

    def relink(self, profile_id: int, source_id: int, path: str) -> MaterialSource:
        source = self._get(profile_id, source_id)
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            raise SourcesError(f"not a directory: {resolved}")
        source.path = str(resolved)
        source.enabled = True
        self._session.flush()
        return source

    def reveal(self, profile_id: int, source_id: int) -> None:
        source = self._get(profile_id, source_id)
        opener = (
            "open"
            if sys.platform == "darwin"
            else "explorer" if sys.platform == "win32" else "xdg-open"
        )
        try:
            subprocess.Popen([opener, source.path])
        except OSError as error:
            raise SourcesError(f"could not open file manager: {error}") from error

    def _resolve_subdir(self, source: MaterialSource, subdir: str) -> Path | None:
        root = Path(source.path)
        if not root.is_dir():
            return None
        cleaned = (subdir or "").strip().strip("/")
        if not cleaned:
            return root
        parts = [part for part in cleaned.split("/") if part not in ("", ".")]
        if any(part == ".." for part in parts) or len(parts) > MAX_BROWSE_DEPTH:
            raise SourcesError("invalid subdirectory")
        target = root.joinpath(*parts)
        real_root = os.path.realpath(root)
        real_target = os.path.realpath(target)
        if real_target != real_root and not real_target.startswith(real_root + os.sep):
            raise SourcesError("subdirectory escapes the linked folder")
        if not target.is_dir():
            raise SourcesError("directory not found in linked folder")
        return target

    def browse(
        self, profile_id: int, source_id: int, subdir: str = ""
    ) -> dict[str, Any]:
        source = self._get(profile_id, source_id)
        root = Path(source.path)
        target = self._resolve_subdir(source, subdir)
        result: dict[str, Any] = {
            "source_id": source_id,
            "label": source.label,
            "path": source.path,
            "subdir": (subdir or "").strip().strip("/"),
            "missing_target": target is None,
            "enabled": source.enabled,
            "scan_interval_sec": source.scan_interval_sec,
            "last_scan_error": source.last_scan_error,
            "last_scanned_at": (
                source.last_scanned_at.isoformat()
                if source.last_scanned_at
                else None
            ),
            "subdirs": [],
            "materials": [],
            "uningested": [],
        }
        known = {
            material.external_path: material
            for material in self._session.scalars(
                select(Material).where(
                    Material.profile_id == profile_id,
                    Material.source_id == source.id,
                )
            )
        }
        rel_prefix = result["subdir"] + "/" if result["subdir"] else ""
        seen_relpaths: set[str] = set()
        for external_path, material in known.items():
            if external_path is None:
                continue
            rel = posixpath.relpath(external_path, str(root))
            if rel.startswith(".."):
                continue
            if posixpath.dirname(rel) != result["subdir"]:
                continue
            seen_relpaths.add(rel)
            result["materials"].append(
                {
                    "id": material.id,
                    "title": material.title,
                    "kind": material.kind,
                    "status": material.status,
                    "filename": material.filename,
                    "relpath": rel,
                }
            )
        result["materials"].sort(key=lambda entry: entry["title"].lower())
        if target is None:
            return result
        try:
            entries = sorted(os.scandir(target), key=lambda entry: entry.name.lower())
        except OSError as error:
            raise SourcesError(f"cannot read directory: {error}") from error
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    result["subdirs"].append({"name": entry.name})
                elif entry.is_file():
                    if not _matches_globs(entry.name, list(source.include_globs or DEFAULT_GLOBS)):
                        continue
                    rel = f"{rel_prefix}{entry.name}"
                    if rel in seen_relpaths:
                        continue
                    stat = entry.stat()
                    result["uningested"].append(
                        {
                            "name": entry.name,
                            "relpath": rel,
                            "size_bytes": stat.st_size,
                            "mtime": stat.st_mtime,
                        }
                    )
            except OSError:
                continue
        return result

    def ingest_file(
        self, profile_id: int, source_id: int, relpath: str
    ) -> tuple[Material, bool]:
        source = self._get(profile_id, source_id)
        root = Path(source.path)
        cleaned = (relpath or "").strip().strip("/")
        parts = [part for part in cleaned.split("/") if part not in ("", ".")]
        if not parts or any(part == ".." for part in parts):
            raise SourcesError("invalid file path")
        target = root.joinpath(*parts)
        real_root = os.path.realpath(root)
        real_target = os.path.realpath(target)
        if not real_target.startswith(real_root + os.sep) or real_target == real_root:
            raise SourcesError("file escapes the linked folder")
        if not target.is_file():
            raise SourcesError("file not found in linked folder")
        if not _matches_globs(target.name, list(source.include_globs or DEFAULT_GLOBS)):
            raise SourcesError("file type is excluded by this source's filters")
        content_hash = _content_hash(target)
        duplicate = self._session.scalars(
            select(Material).where(
                Material.profile_id == profile_id,
                Material.course_id == source.course_id,
                Material.content_hash == content_hash,
                Material.status != MaterialStatus.FAILED,
            )
        ).first()
        if duplicate is not None:
            return duplicate, True
        stat = target.stat()
        material = self._create_material(
            profile_id, source, target, stat, content_hash
        )
        return material, False

    def scan(self, profile_id: int, source_id: int) -> dict[str, int]:
        source = self._session.get(MaterialSource, source_id)
        if source is None or source.profile_id != profile_id:
            raise SourcesError("source not found")
        root = Path(source.path)
        if not root.is_dir():
            source.enabled = False
            source.last_scan_error = f"source directory is gone: {root}"
            self._session.flush()
            raise SourcesError(source.last_scan_error)

        known = {
            material.external_path: material
            for material in self._session.scalars(
                select(Material).where(
                    Material.profile_id == profile_id,
                    Material.source_id == source.id,
                )
            )
        }
        stats = {"new": 0, "updated": 0, "unchanged": 0, "missing": 0, "moved": 0}
        globs = list(source.include_globs or DEFAULT_GLOBS)
        seen: set[str] = set()
        for path in _iter_files(root, source.recursive, globs):
            key = str(path)
            seen.add(key)
            stat = path.stat()
            material = known.get(key)
            if material is not None and material.status == "missing":
                material.status = MaterialStatus.PENDING
                material.file_mtime = stat.st_mtime
                material.file_size = stat.st_size
                stats["updated"] += 1
                continue
            if material is not None:
                if (
                    material.file_mtime == stat.st_mtime
                    and material.file_size == stat.st_size
                ):
                    stats["unchanged"] += 1
                    continue
                content_hash = _content_hash(path)
                if content_hash == material.content_hash:
                    material.file_mtime = stat.st_mtime
                    material.file_size = stat.st_size
                    stats["unchanged"] += 1
                    continue
                self._new_version(material, path, stat, content_hash)
                stats["updated"] += 1
                continue

            content_hash = _content_hash(path)
            duplicate = self._session.scalars(
                select(Material).where(
                    Material.profile_id == profile_id,
                    Material.course_id == source.course_id,
                    Material.content_hash == content_hash,
                    Material.status != MaterialStatus.FAILED,
                )
            ).first()
            if duplicate is not None:
                if duplicate.source_id == source.id:
                    duplicate.external_path = str(path)
                    duplicate.filename = path.name
                    duplicate.file_mtime = stat.st_mtime
                    duplicate.file_size = stat.st_size
                    if duplicate.status == "missing":
                        duplicate.status = MaterialStatus.READY
                    stats["moved"] += 1
                else:
                    stats["unchanged"] += 1
                continue
            self._create_material(
                profile_id, source, path, stat, content_hash
            )
            stats["new"] += 1

        for known_path, material in known.items():
            if known_path not in seen and not Path(str(known_path)).is_file():
                material.status = "missing"
                stats["missing"] += 1

        source.last_scanned_at = utcnow()
        source.last_scan_error = None
        self._session.flush()
        return stats

    def _store_blob(self, path: Path) -> str:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        target = self._blobs_root / digest[:2] / digest[2:4] / digest
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        if self._session.get(Blob, digest) is None:
            self._session.add(
                Blob(
                    sha256=digest,
                    rel_path=str(target.relative_to(self._blobs_root)),
                    size=len(data),
                    mime=mimetypes.guess_type(path.name)[0],
                )
            )
        return digest

    def _create_material(
        self,
        profile_id: int,
        source: MaterialSource,
        path: Path,
        stat: Any,
        content_hash: str,
    ) -> Material:
        sha = self._store_blob(path)
        material = Material(
            profile_id=profile_id,
            course_id=source.course_id,
            kind=detect_kind(path.name),
            title=path.stem,
            blob_sha=sha,
            filename=path.name,
            mime=None,
            status=MaterialStatus.PENDING,
            content_hash=content_hash,
            source_id=source.id,
            external_path=str(path),
            file_mtime=stat.st_mtime,
            file_size=stat.st_size,
        )
        self._session.add(material)
        self._session.flush()
        return material

    def _new_version(
        self, material: Material, path: Path, stat: Any, content_hash: str
    ) -> None:
        sha = self._store_blob(path)
        material.blob_sha = sha
        material.content_hash = content_hash
        material.file_mtime = stat.st_mtime
        material.file_size = stat.st_size
        material.status = MaterialStatus.PENDING
        self._session.flush()
