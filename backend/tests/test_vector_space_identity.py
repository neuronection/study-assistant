"""Stored space-key identity (plan 52 T5b1).

A space's key is a value the row owns: created once, returned verbatim by
``space_key_for``/``ContentSpace``/status reads, and compared by the
build/activation paths. A changed key pre-image (the tokenizer/chunker fold in
T5b2) must never make an existing row look like a different live space.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.domain.models import VectorDocument, VectorRecord, VectorSpace
from app.services.retrieval import lifecycle
from app.storage import vector_contract as vc
from app.storage.vector_store import StudyVectorStore, content_space_for

DIM = 4
NAME = "identity"


def _v1(dim: int = DIM) -> str:
    return vc.space_key("openai", "text-embedding-3-small", dim, True, None, None, "1", "1")


def _insert(
    session: Session,
    *,
    name: str | None = None,
    status: str = "building",
    index_table: str | None = None,
) -> VectorSpace:
    row = VectorSpace(
        id=str(uuid.uuid4()),
        name=name or f"identity-{uuid.uuid4().hex[:8]}",
        provider="openai",
        model="text-embedding-3-small",
        dim=DIM,
        normalize=True,
        chunker_version="1",
        composer_version="1",
        index_table=index_table,
        status=status,
    )
    session.add(row)
    session.commit()
    return row


def test_direct_insert_stamps_the_v1_key(db_session: Session) -> None:
    row = _insert(db_session)
    assert row.space_key == _v1()


def test_new_build_persists_the_v1_key(db_session: Session) -> None:
    result, _changed = lifecycle.build_space(
        db_session,
        name=NAME,
        provider="openai",
        model="text-embedding-3-small",
        dim=DIM,
    )
    row = db_session.get(VectorSpace, result.space_id)
    assert row is not None
    assert row.space_key == _v1()
    assert result.space_key == row.space_key


def test_building_match_uses_the_stored_key(db_session: Session) -> None:
    first, _changed = lifecycle.build_space(
        db_session,
        name=NAME,
        provider="openai",
        model="text-embedding-3-small",
        dim=DIM,
    )
    again, _changed = lifecycle.build_space(
        db_session,
        name=NAME,
        provider="openai",
        model="text-embedding-3-small",
        dim=DIM,
    )
    assert again.space_id == first.space_id
    assert again.space_key == first.space_key

    row = db_session.get(VectorSpace, first.space_id)
    assert row is not None
    row.space_key = "a" * 64
    db_session.commit()
    with pytest.raises(lifecycle.SpaceStateError, match="stored identity"):
        lifecycle.build_space(
            db_session,
            name=NAME,
            provider="openai",
            model="text-embedding-3-small",
            dim=DIM,
        )


def test_active_comparison_uses_the_stored_key(db_session: Session) -> None:
    active = _insert(db_session, name="active-space", status="active")
    active.space_key = _v1()
    db_session.commit()

    _result, changed = lifecycle.build_space(
        db_session,
        name="candidate-same",
        provider="openai",
        model="text-embedding-3-small",
        dim=DIM,
    )
    assert changed is False

    active.space_key = "b" * 64
    db_session.commit()
    _result, changed = lifecycle.build_space(
        db_session,
        name="candidate-different",
        provider="openai",
        model="text-embedding-3-small",
        dim=DIM,
    )
    assert changed is True


def test_stored_key_wins_over_the_preimage(db_session: Session) -> None:
    row = _insert(db_session, name="stored-wins", status="active")
    stored = "c" * 64
    row.space_key = stored
    db_session.commit()

    assert lifecycle.space_key_for(row) == stored
    store = StudyVectorStore(db_session, space_id=str(row.id))
    space = store.content_space()
    assert space is not None
    assert space.key == stored
    assert space.as_contract().key == stored
    assert content_space_for(db_session).key == stored  # type: ignore[union-attr]
    status_space, _physical = lifecycle.space_status_dto(db_session, row)
    assert status_space is not None
    assert status_space.key == stored


def test_direct_insert_refuses_to_guess_a_v2_key(db_session: Session) -> None:
    row = VectorSpace(
        id=str(uuid.uuid4()),
        name=f"v2-guard-{uuid.uuid4().hex[:8]}",
        provider="openai",
        model="text-embedding-3-small",
        dim=DIM,
        normalize=True,
        chunker_version="2",
        composer_version="1",
        tokenizer_kind="tiktoken",
        tokenizer_identifier="cl100k_base",
        tokenizer_artifact_sha256="d" * 64,
        tokenizer_exact=True,
        max_input_tokens=8191,
        chunk_max_tokens=64,
        chunk_overlap_tokens=8,
        chunk_max_chars=400,
        status="building",
    )
    db_session.add(row)
    with pytest.raises(StatementError, match="v2 space_key explicitly"):
        db_session.flush()
    db_session.rollback()


def _token_columns(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "tokenizer_kind": "tiktoken",
        "tokenizer_identifier": "cl100k_base",
        "tokenizer_artifact_sha256": "e" * 64,
        "tokenizer_exact": True,
        "max_input_tokens": 8191,
        "chunk_max_tokens": 64,
        "chunk_overlap_tokens": 8,
        "chunk_max_chars": 400,
    }
    values.update(overrides)
    return values


def test_half_configured_space_is_rejected(db_session: Session) -> None:
    row = VectorSpace(
        id=str(uuid.uuid4()),
        name=f"half-{uuid.uuid4().hex[:8]}",
        provider="openai",
        model="text-embedding-3-small",
        dim=DIM,
        normalize=True,
        chunker_version="2",
        composer_version="1",
        space_key="f" * 64,
        status="building",
        tokenizer_kind="tiktoken",
        tokenizer_identifier="cl100k_base",
        tokenizer_exact=True,
        max_input_tokens=8191,
    )
    db_session.add(row)
    with pytest.raises(IntegrityError, match="tokenizer_group_all_or_none"):
        db_session.flush()
    db_session.rollback()


def test_v2_columns_require_chunker_v2(db_session: Session) -> None:
    row = VectorSpace(
        id=str(uuid.uuid4()),
        name=f"chunker-{uuid.uuid4().hex[:8]}",
        provider="openai",
        model="text-embedding-3-small",
        dim=DIM,
        normalize=True,
        chunker_version="1",
        composer_version="1",
        space_key="a" * 64,
        status="building",
        **_token_columns(),
    )
    db_session.add(row)
    with pytest.raises(IntegrityError, match="tokenizer_requires_chunker_v2"):
        db_session.flush()
    db_session.rollback()


def _record_space(session: Session) -> tuple[VectorSpace, VectorDocument]:
    space = _insert(session)
    document = VectorDocument(
        id=str(uuid.uuid4()),
        space_id=space.id,
        kind="material",
        source_id=str(uuid.uuid4()),
        profile_id=None,
        source_hash="",
        schema_version=0,
    )
    session.add(document)
    session.commit()
    return space, document


def _record(space: VectorSpace, document: VectorDocument, **tokens: int) -> VectorRecord:
    return VectorRecord(
        id=str(uuid.uuid4()),
        document_id=document.id,
        space_id=space.id,
        chunk_id=str(uuid.uuid4()),
        view="body",
        chunk_index=0,
        content_hash="",
        **tokens,
    )


def test_token_offsets_are_all_or_none(db_session: Session) -> None:
    space, document = _record_space(db_session)
    db_session.add(_record(space, document, token_count=4))
    with pytest.raises(IntegrityError, match="token_fields_consistent"):
        db_session.flush()
    db_session.rollback()


def test_token_offsets_must_be_ordered_and_consistent(db_session: Session) -> None:
    space, document = _record_space(db_session)
    db_session.add(_record(space, document, token_count=4, token_start=5, token_end=4))
    with pytest.raises(IntegrityError, match=r"token_range_ordered|token_fields_consistent"):
        db_session.flush()
    db_session.rollback()

    space, document = _record_space(db_session)
    db_session.add(_record(space, document, token_count=4, token_start=0, token_end=5))
    with pytest.raises(IntegrityError, match="token_fields_consistent"):
        db_session.flush()
    db_session.rollback()

    space, document = _record_space(db_session)
    db_session.add(_record(space, document, token_count=5, token_start=0, token_end=5))
    db_session.commit()
    stored = db_session.scalars(
        select(VectorRecord).where(VectorRecord.document_id == document.id)
    ).one()
    assert (stored.token_count, stored.token_start, stored.token_end) == (5, 0, 5)
