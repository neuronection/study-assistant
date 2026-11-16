"""Legacy content-addressed blob trees remain readable through the store.

The family layout for new content is ``sha256/aa/bb/<sha>``, but study's
desktop data directories already contain the legacy ``<aa>/<bb>/<sha>``
tree. P1 preserves that layout: a copy into a fresh ``BlobStore`` keeps the
same key and verifies on read.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.storage.blobs import BlobStore, blob_key


def _legacy_tree(root: Path, payloads: list[bytes]) -> dict[str, bytes]:
    expected: dict[str, bytes] = {}
    for data in payloads:
        sha = hashlib.sha256(data).hexdigest()
        path = root / sha[:2] / sha[2:4] / sha
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        expected[sha] = data
    return expected


def test_legacy_tree_copies_into_store_with_same_sha_and_key(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    expected = _legacy_tree(legacy, [b"first blob", b"second blob", b"first blob"])

    store = BlobStore(tmp_path / "new")
    for path in sorted(legacy.rglob("*")):
        if not path.is_file():
            continue
        stored = store.put(path.read_bytes())
        assert stored.sha256 == path.name
        assert stored.rel_path == Path(blob_key(path.name))
        assert stored.created is True

    for sha, data in expected.items():
        assert store.has(sha)
        assert store.get(sha) == data
        assert b"".join(store.stream(sha, chunk_size=3)) == data
        with store.materialize(sha) as materialized:
            assert materialized.read_bytes() == data
            assert materialized.stat().st_mode & 0o777 == 0o600
        assert not materialized.exists()


def test_legacy_layout_is_content_addressed(tmp_path: Path) -> None:
    data = b"layout"
    sha = hashlib.sha256(data).hexdigest()
    store = BlobStore(tmp_path / "blobs")
    stored = store.put(data)
    assert stored.rel_path.parts == (sha[:2], sha[2:4], sha)
    assert store.path(sha).read_bytes() == data
    assert store.root == tmp_path / "blobs"


def test_delete_removes_object_and_is_idempotent(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    stored = store.put(b"delete me")
    assert store.delete(stored.sha256) is True
    assert not store.has(stored.sha256)
    assert store.delete(stored.sha256) is False


def test_path_refuses_an_object_backend(tmp_path: Path) -> None:
    from object_store_stub import UnavailableObjectStore

    from app.storage.object_storage import UnsupportedOperation

    store = BlobStore(UnavailableObjectStore())
    with pytest.raises(UnsupportedOperation):
        store.path("0" * 64)
    with pytest.raises(UnsupportedOperation):
        store.local_root()
