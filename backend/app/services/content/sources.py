import hashlib
import mimetypes
import os
import posixpath
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...core.vocab import MaterialStatus, SourcePreset
from ...domain.models import (
    Blob,
    Course,
    Material,
    MaterialFolder,
    MaterialSource,
    Note,
    NoteLink,
    utcnow,
)
from .drawings import blocks_md, md_to_blocks, note_search_text
from .materials import UnsupportedMaterialError, detect_kind
from .notes import normalize_tags, save_note_body

DEFAULT_GLOBS = (
    "*.pdf",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.webp",
    "*.md",
    "*.markdown",
    "*.txt",
    "*.docx",
    "*.pptx",
    "*.epub",
    "*.html",
    "*.htm",
    "*.mp3",
    "*.m4a",
    "*.wav",
    "*.ogg",
    "*.opus",
    "*.mpga",
    "*.webm",
    "*.mp4",
    "*.mpeg",
)

MAX_BROWSE_DEPTH = 32


class SourcesError(ValueError):
    pass


@dataclass
class ScanReport:
    stats: dict[str, int]
    skipped: list[str] = field(default_factory=list)
    new_relpaths: list[str] = field(default_factory=list)


def _iter_files(root: Path, recursive: bool, globs: list[str]) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    allowed = {glob.lower() for glob in globs}
    files: list[Path] = []
    for path in sorted(root.glob(pattern)):
        if not path.is_file():
            continue
        if (
            allowed
            and path.name.lower() not in allowed
            and not any(path.match(glob) for glob in globs)
        ):
            continue
        files.append(path)
    return files


def _source_relpath(source: MaterialSource, path: Path) -> str:
    return path.relative_to(Path(source.path)).as_posix()


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


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


def _parse_tag_list(value: str) -> list[str]:
    text = value.strip().strip("[]")
    return [part.strip().strip("\"'") for part in text.split(",") if part.strip()]


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if end is None:
        return {}, text
    meta: dict[str, Any] = {}
    key = ""
    for line in lines[1:end]:
        stripped = line.strip()
        if stripped.startswith("- ") and key == "tags":
            meta.setdefault("tags", []).append(stripped[2:].strip().strip("\"'"))
            continue
        if ":" not in line:
            continue
        name, _colon, raw = line.partition(":")
        key = name.strip().lower()
        value = raw.strip()
        if key == "tags":
            meta["tags"] = _parse_tag_list(value) if value else []
        elif key == "title":
            meta["title"] = value.strip("\"'")
    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return meta, body


def _vault_title(meta: dict[str, Any], body: str, path: Path) -> str:
    title = str(meta.get("title") or "").strip()
    if title:
        return title
    for line in body.splitlines():
        if line.startswith("# "):
            heading = line[2:].strip()
            if heading:
                return heading
    return path.stem


def _vault_tags(meta: dict[str, Any]) -> list[str]:
    tags = meta.get("tags")
    if isinstance(tags, list):
        return [str(tag) for tag in tags]
    return []


class SourcesService:
    def __init__(self, session: Session, blobs_root: Path) -> None:
        self._session = session
        self._blobs_root = blobs_root

    def _get(self, profile_id: str, source_id: str) -> MaterialSource:
        source = self._session.get(MaterialSource, source_id)
        if source is None or source.profile_id != profile_id:
            raise SourcesError("source not found")
        return source

    def _link_folder(self, source_id: str) -> MaterialFolder | None:
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

    def list_sources(self, profile_id: str) -> list[MaterialSource]:
        return list(
            self._session.scalars(
                select(MaterialSource).where(MaterialSource.profile_id == profile_id)
            )
        )

    def create_source(
        self,
        profile_id: str,
        *,
        label: str,
        path: str,
        recursive: bool = True,
        include_globs: list[str] | None = None,
        course_id: str | None = None,
        scan_interval_sec: int | None = None,
        mirror_subdirs: bool = False,
        preset: str = SourcePreset.FOLDER.value,
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
        preset_value = SourcePreset.parse(preset).value
        source = MaterialSource(
            profile_id=profile_id,
            label=_sanitize_label(label) or resolved.name,
            path=str(resolved),
            recursive=recursive,
            include_globs=include_globs or list(DEFAULT_GLOBS),
            course_id=course_id,
            scan_interval_sec=scan_interval_sec,
            mirror_subdirs=mirror_subdirs,
            preset=preset_value,
        )
        self._session.add(source)
        self._session.flush()
        if preset_value == SourcePreset.FOLDER.value:
            self._create_link_node(source)
        return source

    def delete_source(self, profile_id: str, source_id: str) -> bool:
        source = self._session.get(MaterialSource, source_id)
        if source is None or source.profile_id != profile_id:
            return False
        self._unlink_materials(source_id)
        self._unlink_notes(source_id)
        node = self._link_folder(source_id)
        if node is not None:
            self._session.delete(node)
        self._session.delete(source)
        return True

    def _unlink_notes(self, source_id: str) -> None:
        for note in self._session.scalars(select(Note).where(Note.source_id == source_id)):
            note.source_id = None
            note.external_path = None

    def _unlink_materials(self, source_id: str) -> None:
        for material in self._session.scalars(
            select(Material).where(Material.source_id == source_id)
        ):
            material.source_id = None
            material.external_path = None
            material.folder_id = None

    def relink(self, profile_id: str, source_id: str, path: str) -> MaterialSource:
        source = self._get(profile_id, source_id)
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            raise SourcesError(f"not a directory: {resolved}")
        source.path = str(resolved)
        source.enabled = True
        self._session.flush()
        return source

    def reveal(self, profile_id: str, source_id: str) -> None:
        source = self._get(profile_id, source_id)
        opener = (
            "open"
            if sys.platform == "darwin"
            else "explorer"
            if sys.platform == "win32"
            else "xdg-open"
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

    def browse(self, profile_id: str, source_id: str, subdir: str = "") -> dict[str, Any]:
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
            "mirror_subdirs": source.mirror_subdirs,
            "scan_interval_sec": source.scan_interval_sec,
            "last_scan_error": source.last_scan_error,
            "last_scanned_at": (
                source.last_scanned_at.isoformat() if source.last_scanned_at else None
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

    def ingest_file(self, profile_id: str, source_id: str, relpath: str) -> tuple[Material, bool]:
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
        kind = detect_kind(target.name)
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
        material = self._create_material(profile_id, source, target, stat, content_hash, kind=kind)
        return material, False

    def scan(self, profile_id: str, source_id: str) -> ScanReport:
        source = self._session.get(MaterialSource, source_id)
        if source is None or source.profile_id != profile_id:
            raise SourcesError("source not found")
        if source.preset == SourcePreset.VAULT.value:
            return self._scan_vault(source)
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
        stats = {"new": 0, "updated": 0, "unchanged": 0, "missing": 0, "moved": 0, "skipped": 0}
        skipped: list[str] = []
        mirror_map = self.mirror_subdirs(source) if source.mirror_subdirs else {}
        new_relpaths: list[str] = []
        globs = list(source.include_globs or DEFAULT_GLOBS)
        seen: set[str] = set()
        for path in _iter_files(root, source.recursive, globs):
            key = str(path)
            seen.add(key)
            stat = path.stat()
            material = known.get(key)
            if material is None:
                try:
                    detect_kind(path.name)
                except UnsupportedMaterialError as error:
                    stats["skipped"] += 1
                    skipped.append(f"{path.name}: unsupported type ({error.suffix})")
                    continue
            if material is not None and material.status == MaterialStatus.MISSING:
                material.status = MaterialStatus.PENDING
                material.file_mtime = stat.st_mtime
                material.file_size = stat.st_size
                stats["updated"] += 1
                continue
            if material is not None:
                if material.file_mtime == stat.st_mtime and material.file_size == stat.st_size:
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
                    if duplicate.status == MaterialStatus.MISSING:
                        duplicate.status = MaterialStatus.READY
                    stats["moved"] += 1
                else:
                    stats["unchanged"] += 1
                continue
            self._create_material(
                profile_id,
                source,
                path,
                stat,
                content_hash,
                folder_id=mirror_map.get(str(path.parent)),
            )
            stats["new"] += 1
            new_relpaths.append(_source_relpath(source, path))

        for known_path, material in known.items():
            if known_path not in seen and not Path(str(known_path)).is_file():
                material.status = MaterialStatus.MISSING
                stats["missing"] += 1

        source.last_scanned_at = utcnow()
        source.last_scan_error = None
        self._session.flush()
        return ScanReport(stats=stats, skipped=skipped, new_relpaths=new_relpaths[:20])

    def _scan_vault(self, source: MaterialSource) -> ScanReport:
        root = Path(source.path)
        if not root.is_dir():
            source.enabled = False
            source.last_scan_error = f"source directory is gone: {root}"
            self._session.flush()
            raise SourcesError(source.last_scan_error)
        known = {
            str(note.external_path): note
            for note in self._session.scalars(
                select(Note).where(
                    Note.profile_id == source.profile_id,
                    Note.source_id == source.id,
                )
            )
            if note.external_path is not None
        }
        stats = {
            "new": 0,
            "updated": 0,
            "unchanged": 0,
            "missing": 0,
            "moved": 0,
            "skipped": 0,
        }
        skipped: list[str] = []
        seen: set[str] = set()
        for path in _iter_files(root, source.recursive, ["*.md", "*.markdown"]):
            key = str(path)
            seen.add(key)
            stat = path.stat()
            content_hash = _content_hash(path)
            note = known.get(key)
            if note is not None:
                if note.file_mtime == stat.st_mtime and note.file_size == stat.st_size:
                    stats["unchanged"] += 1
                    continue
                if note.content_hash == content_hash:
                    note.file_mtime = stat.st_mtime
                    note.file_size = stat.st_size
                    stats["unchanged"] += 1
                    continue
                self._update_note_from_file(note, path, stat, content_hash)
                stats["updated"] += 1
                continue
            moved = self._session.scalars(
                select(Note).where(
                    Note.profile_id == source.profile_id,
                    Note.source_id == source.id,
                    Note.content_hash == content_hash,
                )
            ).first()
            if moved is not None:
                moved.external_path = key
                moved.file_mtime = stat.st_mtime
                moved.file_size = stat.st_size
                stats["moved"] += 1
                continue
            created = self._create_note_from_file(source, path, stat, content_hash)
            if created is None:
                stats["skipped"] += 1
                skipped.append(f"{path.name}: not UTF-8 text")
                continue
            stats["new"] += 1
        for known_path in known:
            if known_path not in seen and not Path(known_path).is_file():
                stats["missing"] += 1
        self._sync_note_links(source)
        source.last_scanned_at = utcnow()
        source.last_scan_error = None
        self._session.flush()
        return ScanReport(stats=stats, skipped=skipped, new_relpaths=[])

    def _read_vault_file(self, path: Path) -> tuple[dict[str, Any], str] | None:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            return None
        return _parse_frontmatter(text)

    def _create_note_from_file(
        self, source: MaterialSource, path: Path, stat: Any, content_hash: str
    ) -> Note | None:
        parsed = self._read_vault_file(path)
        if parsed is None:
            return None
        meta, body = parsed
        note = Note(
            profile_id=source.profile_id,
            course_id=source.course_id,
            title=_vault_title(meta, body, path)[:300],
            body=md_to_blocks(body),
            tags=normalize_tags(_vault_tags(meta)) or None,
            owner_type="standalone",
            source_id=source.id,
            external_path=str(path),
            file_mtime=stat.st_mtime,
            file_size=stat.st_size,
            content_hash=content_hash,
        )
        note.search_text = note_search_text(note)
        self._session.add(note)
        self._session.flush()
        return note

    def _update_note_from_file(self, note: Note, path: Path, stat: Any, content_hash: str) -> None:
        parsed = self._read_vault_file(path)
        if parsed is None:
            return
        meta, body = parsed
        note.title = _vault_title(meta, body, path)[:300]
        note.tags = normalize_tags(_vault_tags(meta)) or None
        save_note_body(self._session, note, body, cause="source", force=True)
        note.file_mtime = stat.st_mtime
        note.file_size = stat.st_size
        note.content_hash = content_hash

    def _sync_note_links(self, source: MaterialSource) -> None:
        notes = list(
            self._session.scalars(
                select(Note).where(
                    Note.profile_id == source.profile_id,
                    Note.source_id == source.id,
                )
            )
        )
        by_title = {note.title.strip().lower(): note for note in notes if note.title.strip()}
        for note in notes:
            self._session.execute(delete(NoteLink).where(NoteLink.from_note_id == note.id))
            targets: list[str] = []
            for target in WIKILINK_RE.findall(blocks_md(note.body)):
                cleaned = target.strip()
                if cleaned and cleaned.lower() not in {item.lower() for item in targets}:
                    targets.append(cleaned)
            for target in targets:
                linked = by_title.get(target.lower())
                self._session.add(
                    NoteLink(
                        profile_id=note.profile_id,
                        course_id=note.course_id,
                        from_note_id=note.id,
                        to_note_id=linked.id
                        if linked is not None and linked.id != note.id
                        else None,
                        target=target[:300],
                    )
                )

    def mirror_subdirs(self, source: MaterialSource) -> dict[str, str]:
        folder = self._link_folder(source.id)
        if folder is None:
            return {}
        mapping: dict[str, str] = {}
        root_str = str(Path(source.path))

        def child_folders(parent_id: str) -> dict[str, MaterialFolder]:
            return {
                child.name: child
                for child in self._session.scalars(
                    select(MaterialFolder).where(
                        MaterialFolder.parent_id == parent_id,
                        MaterialFolder.source_id.is_(None),
                    )
                )
            }

        def walk(source_dir: Path, folder: MaterialFolder) -> None:
            try:
                entries = sorted(os.scandir(source_dir), key=lambda entry: entry.name.lower())
            except OSError:
                return
            for entry in entries:
                if entry.is_symlink() or not entry.is_dir():
                    continue
                existing = child_folders(folder.id).get(entry.name)
                if existing is None:
                    conflicting = self._session.scalars(
                        select(MaterialFolder.id).where(
                            MaterialFolder.course_id == source.course_id,
                            MaterialFolder.path == f"{folder.path}/{entry.name}",
                        )
                    ).first()
                    if conflicting is not None:
                        continue
                    existing = MaterialFolder(
                        profile_id=source.profile_id,
                        course_id=source.course_id,
                        parent_id=folder.id,
                        name=entry.name,
                        path=f"{folder.path}/{entry.name}",
                        source_id=None,
                    )
                    self._session.add(existing)
                    self._session.flush()
                mapping[str(Path(source_dir) / entry.name)] = existing.id
                walk(Path(entry.path), existing)

        walk(Path(root_str.rstrip(os.sep)), folder)
        return mapping

    def backfill_mirrored_folders(self, profile_id: str, source_id: str) -> dict[str, int]:
        source = self._get(profile_id, source_id)
        root = Path(source.path)
        if not root.is_dir():
            raise SourcesError(f"not a directory: {root}")
        mapping = self.mirror_subdirs(source)
        updated = 0
        for material in self._session.scalars(
            select(Material).where(
                Material.profile_id == profile_id,
                Material.source_id == source.id,
                Material.folder_id.is_(None),
                Material.external_path.is_not(None),
            )
        ):
            path = Path(str(material.external_path))
            if path.parent == root:
                continue
            target = mapping.get(str(path.parent))
            if target is not None:
                material.folder_id = target
                updated += 1
        self._session.flush()
        return {"backfilled": updated, "mirrored_dirs": len(mapping)}

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
        profile_id: str,
        source: MaterialSource,
        path: Path,
        stat: Any,
        content_hash: str,
        kind: str | None = None,
        folder_id: str | None = None,
    ) -> Material:
        if kind is None:
            kind = detect_kind(path.name)
        sha = self._store_blob(path)
        material = Material(
            profile_id=profile_id,
            course_id=source.course_id,
            kind=kind,
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
            folder_id=folder_id,
        )
        self._session.add(material)
        self._session.flush()
        return material

    def _new_version(self, material: Material, path: Path, stat: Any, content_hash: str) -> None:
        sha = self._store_blob(path)
        material.blob_sha = sha
        material.content_hash = content_hash
        material.file_mtime = stat.st_mtime
        material.file_size = stat.st_size
        material.status = MaterialStatus.PENDING
        self._session.flush()
