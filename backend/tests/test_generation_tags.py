"""Plan 51 Q3c3a: caller-supplied embedding tags through the study paths."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.ai.embeddings import embed_with_tags
from app.domain.models import Chunk, Course, Extraction, Material, Profile, User
from app.pipelines.postprocess import embed_extraction
from app.storage.vector_store import StudyVectorStore


def test_embed_with_tags_keeps_v1_embedders_working() -> None:
    calls: list[list[str]] = []

    def v1(texts: list[str]) -> tuple[str, list[list[float]]]:
        calls.append(texts)
        return ("v1", [[1.0]])

    result = embed_with_tags(v1, ["a"], {"space_id": "s", "kind": "material"})
    assert result == ("v1", [[1.0]])
    assert calls == [["a"]]

    tagged: list[tuple[list[str], dict[str, Any]]] = []

    def modern(
        texts: list[str], *, metadata: dict[str, Any] | None = None
    ) -> tuple[str, list[list[float]]]:
        tagged.append((texts, dict(metadata or {})))
        return ("modern", [[1.0] for _ in texts])

    embed_with_tags(modern, ["b"], {"space_id": "s", "kind": "material"})
    assert tagged == [(["b"], {"space_id": "s", "kind": "material"})]


def test_embed_extraction_passes_space_kind_view_and_chunk_index(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(StudyVectorStore, "store", lambda self, ids, vectors, model: None)

    user = User(email="tags@test.local", password_hash=None)
    db_session.add(user)
    db_session.flush()
    profile = Profile(user_id=user.id, name="Default", is_default=True)
    db_session.add(profile)
    db_session.flush()
    course = Course(profile_id=profile.id, title="Tags")
    db_session.add(course)
    db_session.flush()
    material = Material(
        profile_id=profile.id,
        course_id=course.id,
        kind="md",
        title="Notes",
        filename="notes.md",
        status="ready",
    )
    db_session.add(material)
    db_session.flush()
    extraction = Extraction(
        material_id=material.id, extractor="test", blocks=[], markdown="alpha beta"
    )
    db_session.add(extraction)
    db_session.flush()
    chunks = [
        Chunk(extraction_id=extraction.id, ordinal=0, text="alpha"),
        Chunk(extraction_id=extraction.id, ordinal=1, text="beta"),
    ]
    db_session.add_all(chunks)
    db_session.commit()

    seen: list[dict[str, Any]] = []

    def embedder(
        texts: Sequence[str], *, metadata: dict[str, Any] | None = None
    ) -> tuple[str, list[list[float]]]:
        seen.append(dict(metadata or {}))
        return ("fake", [[1.0, 0.0, 0.0, 0.0] for _ in texts])

    assert embed_extraction(db_session, extraction, embedder) == 2
    assert seen == [
        {
            "space_id": "v1-chunk-vecs",
            "kind": "material",
            "view": "body",
        }
    ]

    single = Extraction(material_id=material.id, extractor="test", blocks=[], markdown="gamma")
    db_session.add(single)
    db_session.flush()
    db_session.add(Chunk(extraction_id=single.id, ordinal=7, text="gamma"))
    db_session.commit()
    assert embed_extraction(db_session, single, embedder) == 1
    assert seen[-1]["chunk_index"] == 7
    assert "text" not in seen[-1]
