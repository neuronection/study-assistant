import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.models import Blob


def blob_path(root: Path, sha256: str) -> Path:
    return root / sha256[:2] / sha256[2:4] / sha256


@dataclass(frozen=True)
class StoredBlob:
    sha256: str
    rel_path: Path
    size: int
    created: bool


class BlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path_for(self, sha256: str) -> Path:
        return blob_path(self.root, sha256)

    def put(
        self, data: bytes, mime: str | None = None, session: Session | None = None
    ) -> StoredBlob:
        sha256 = hashlib.sha256(data).hexdigest()
        path = self._path_for(sha256)
        created = not path.exists()
        if created:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        rel_path = path.relative_to(self.root)
        if session is not None and session.get(Blob, sha256) is None:
            session.add(Blob(sha256=sha256, rel_path=str(rel_path), size=len(data), mime=mime))
        return StoredBlob(sha256=sha256, rel_path=rel_path, size=len(data), created=created)

    def path(self, sha256: str) -> Path:
        return self._path_for(sha256)

    def get(self, sha256: str) -> bytes | None:
        path = self._path_for(sha256)
        if not path.is_file():
            return None
        return path.read_bytes()

    def has(self, sha256: str) -> bool:
        return self._path_for(sha256).is_file()

    def known_shas(self, session: Session) -> set[str]:
        return set(session.scalars(select(Blob.sha256)))
