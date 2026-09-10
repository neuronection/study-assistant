import hashlib
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.domain.models import Blob
from app.storage.blobs import BlobStore


@pytest.fixture
def store(tmp_path: Path) -> BlobStore:
    return BlobStore(tmp_path / "blobs")


def test_put_returns_sha_and_writes_content_addressed_file(store: BlobStore) -> None:
    data = b"hello studyassistant"
    stored = store.put(data)
    assert stored.sha256 == hashlib.sha256(data).hexdigest()
    assert stored.size == len(data)
    assert stored.created is True
    assert store.get(stored.sha256) == data


def test_put_dedupes_identical_content(store: BlobStore) -> None:
    first = store.put(b"same-bytes")
    second = store.put(b"same-bytes")
    assert first.sha256 == second.sha256
    assert second.created is False


def test_path_layout_uses_sha_prefixes(store: BlobStore) -> None:
    stored = store.put(b"layout-check")
    prefix = stored.sha256[:2]
    sub = stored.sha256[2:4]
    assert store.path(stored.sha256).relative_to(store.root).parts[:2] == (prefix, sub)


def test_get_missing_returns_none(store: BlobStore) -> None:
    assert store.get("0" * 64) is None
    assert not store.has("0" * 64)


def test_put_registers_blob_row_in_session(store: BlobStore, db_session: Session) -> None:
    stored = store.put(b"with-session", mime="application/pdf", session=db_session)
    db_session.commit()
    row = db_session.get(Blob, stored.sha256)
    assert row is not None
    assert row.mime == "application/pdf"
    assert row.size == len(b"with-session")
    assert set(store.known_shas(db_session)) == {stored.sha256}


def test_put_with_session_is_idempotent(store: BlobStore, db_session: Session) -> None:
    store.put(b"idem", session=db_session)
    store.put(b"idem", session=db_session)
    db_session.commit()
    assert len(store.known_shas(db_session)) == 1
