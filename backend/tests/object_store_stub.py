"""Typed in-memory object-store stub for guard tests.

Implements the full ``ObjectStore`` protocol so tests can exercise the
object-backend refusal paths without an SDK or a network.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from app.storage.object_storage import (
    BACKEND_S3,
    ObjectInfo,
    S3Config,
    StorageConfig,
    UnsupportedOperation,
)


class UnavailableObjectStore:
    backend = BACKEND_S3
    config = StorageConfig(backend=BACKEND_S3, s3=S3Config(bucket="bucket1"))

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ObjectInfo:
        raise UnsupportedOperation("read-only test stub")

    def get(self, key: str) -> bytes | None:
        return None

    def stream(self, key: str, chunk_size: int = 1024) -> Iterator[bytes]:
        return iter(())

    def exists(self, key: str) -> bool:
        return False

    def stat(self, key: str) -> ObjectInfo | None:
        return None

    def delete(self, key: str) -> bool:
        return False

    def list(self, prefix: str = "") -> Iterator[ObjectInfo]:
        return iter(())

    def presign_get(
        self,
        key: str,
        ttl_seconds: int | None = None,
        *,
        download_filename: str | None = None,
        inline: bool = False,
    ) -> str:
        raise UnsupportedOperation("read-only test stub")

    def health(self) -> None:
        return None

    def close(self) -> None:
        return None
