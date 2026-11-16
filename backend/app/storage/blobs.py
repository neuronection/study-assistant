import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.limits import MAX_UPLOAD_MB
from ..domain.models import Blob
from .object_storage import (
    BACKEND_LOCAL,
    ENTRYPOINT_DESKTOP,
    LocalObjectStore,
    ObjectStore,
    StorageConfig,
    UnsupportedOperation,
)
from .object_storage import (
    materialize as materialize_object,
)


def blob_path(root: Path, sha256: str) -> Path:
    return root / sha256[:2] / sha256[2:4] / sha256


def blob_key(sha256: str) -> str:
    """The legacy content-addressed key: ``<aa>/<bb>/<sha256>``."""
    return f"{sha256[:2]}/{sha256[2:4]}/{sha256}"


@dataclass(frozen=True)
class StoredBlob:
    sha256: str
    rel_path: Path
    size: int
    created: bool


class BlobStore:
    """Study's content-addressed blob API over the family ``ObjectStore``.

    The public methods keep the historical ``sha256`` signatures; the
    underlying key layout is still ``<aa>/<bb>/<sha256>`` so existing
    desktop/self-host data directories remain valid. A ``Path`` argument
    preserves the legacy construct-everywhere test/desktop shape and builds
    a local store; an ``ObjectStore`` argument is wrapped as-is.
    """

    def __init__(self, source: Path | ObjectStore) -> None:
        if isinstance(source, (str, os.PathLike)):
            root = Path(source)
            self._store: ObjectStore = LocalObjectStore(
                StorageConfig(
                    backend=BACKEND_LOCAL,
                    entrypoint=ENTRYPOINT_DESKTOP,
                    local_root=root,
                    max_object_mb=MAX_UPLOAD_MB,
                ).validate()
            )
        else:
            self._store = source

    @property
    def root(self) -> Path:
        """The local filesystem root (raises on an object backend)."""
        return self.local_root()

    @property
    def store(self) -> ObjectStore:
        return self._store

    def _key_for(self, sha256: str) -> str:
        return blob_key(sha256)

    def _path_for(self, sha256: str) -> Path:
        return self.local_root() / self._key_for(sha256)

    def local_root(self) -> Path:
        """The local filesystem root, or ``UnsupportedOperation`` on a cloud backend."""
        root = getattr(self._store, "root", None)
        if self._store.backend != BACKEND_LOCAL or root is None:
            raise UnsupportedOperation(
                "local filesystem access is unavailable on an object-storage backend"
            )
        return Path(root)

    def put(
        self, data: bytes, mime: str | None = None, session: Session | None = None
    ) -> StoredBlob:
        sha256 = hashlib.sha256(data).hexdigest()
        key = self._key_for(sha256)
        created = not self._store.exists(key)
        if created:
            self._store.put(key, data, content_type=mime)
        rel_path = Path(key)
        if session is not None and session.get(Blob, sha256) is None:
            session.add(Blob(sha256=sha256, rel_path=str(rel_path), size=len(data), mime=mime))
        return StoredBlob(sha256=sha256, rel_path=rel_path, size=len(data), created=created)

    def path(self, sha256: str) -> Path:
        """A local path for ``sha256``; cloud callers use ``stream``/``materialize``."""
        return self._path_for(sha256)

    def get(self, sha256: str) -> bytes | None:
        return self._store.get(self._key_for(sha256))

    def stream(self, sha256: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        return self._store.stream(self._key_for(sha256), chunk_size=chunk_size)

    @contextmanager
    def materialize(self, sha256: str) -> Iterator[Path]:
        """Yield a private temp file containing the blob (removed on exit)."""
        with materialize_object(self._store, self._key_for(sha256)) as path:
            yield path

    def has(self, sha256: str) -> bool:
        return self._store.exists(self._key_for(sha256))

    def delete(self, sha256: str) -> bool:
        return self._store.delete(self._key_for(sha256))

    def known_shas(self, session: Session) -> set[str]:
        return set(session.scalars(select(Blob.sha256)))
