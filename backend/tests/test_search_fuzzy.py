import time
from collections.abc import Callable
from pathlib import Path

import fitz
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from alembic import command
from app.domain.models import Chunk, Course, Extraction, Material, Profile
from app.services.search import retrieve_chunks
from app.storage.fts import sync_material_fts


def make_text_pdf(lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 14
    return bytes(doc.tobytes())


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


def make_course(client: TestClient, title: str = "Calculus") -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


FILLER = (
    "This document exists so the extractor keeps its native text layer. "
    "It carries no further meaning for the assertions below."
)


def upload_pdf(
    client: TestClient, lines: list[str], filename: str, course_id: int
) -> int:
    content = [*lines, FILLER]
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (filename, make_text_pdf(content), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    material_id = int(response.json()["material"]["id"])
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"][
            "status"
        ]
        == "ready"
    )
    return material_id


def hit_ids(client: TestClient, q: str, course_id: int | None = None) -> list[int]:
    params: dict[str, int | str] = {"q": q}
    if course_id is not None:
        params["course_id"] = course_id
    search = client.get("/api/v1/search", params=params).json()
    return [int(hit["material_id"]) for hit in search["hits"]]


def test_search_finds_misspelled_title(client: TestClient) -> None:
    course_id = make_course(client)
    material_id = upload_pdf(
        client, ["Integration by Parts", "The formula for integration."], "a.pdf", course_id
    )
    assert material_id in hit_ids(client, "integraton by parts")


def test_search_finds_misspelled_content_word(client: TestClient) -> None:
    course_id = make_course(client)
    material_id = upload_pdf(
        client,
        ["Limits", "Calculus studies continuous change."],
        "b.pdf",
        course_id,
    )
    assert material_id in hit_ids(client, "calclus")


def test_search_finds_transposed_letters(client: TestClient) -> None:
    course_id = make_course(client)
    material_id = upload_pdf(
        client, ["Limits describe the behavior of functions."], "c.pdf", course_id
    )
    assert material_id in hit_ids(client, "limts")


def test_exact_matches_outrank_fuzzy_ones(client: TestClient) -> None:
    course_id = make_course(client)
    exact = upload_pdf(
        client, ["Limits", "Limits describe the behavior of functions."], "d.pdf", course_id
    )
    upload_pdf(client, ["Thermodynamics", "Entropy and energy."], "e.pdf", course_id)
    ids = hit_ids(client, "limits")
    assert ids[0] == exact


def test_search_respects_course_scope(client: TestClient) -> None:
    course_a = make_course(client, "A")
    course_b = make_course(client, "B")
    material_a = upload_pdf(
        client, ["Integration by Parts", "The formula for integration."], "f.pdf", course_a
    )
    upload_pdf(
        client, ["Integration by Parts", "The formula for integration."], "g.pdf", course_b
    )
    assert hit_ids(client, "integraton by parts", course_id=course_a) == [material_a]
    assert hit_ids(client, "integraton by parts", course_id=course_b) != [material_a]


def test_unmatched_query_returns_no_hits(client: TestClient) -> None:
    course_id = make_course(client)
    upload_pdf(client, ["Limits describe the behavior of functions."], "h.pdf", course_id)
    assert hit_ids(client, "xylophone") == []


def test_retrieve_chunks_fuzzy_fallback(db_session: Session) -> None:
    profile = Profile(name="p")
    db_session.add(profile)
    db_session.flush()
    course = Course(profile_id=profile.id, title="C")
    db_session.add(course)
    db_session.flush()
    material = Material(
        profile_id=profile.id,
        course_id=course.id,
        kind="pdf",
        title="Integration",
        filename="integration.pdf",
        status="ready",
    )
    db_session.add(material)
    db_session.flush()
    extraction = Extraction(
        material_id=material.id, extractor="test", markdown="integration", blocks=[]
    )
    db_session.add(extraction)
    db_session.flush()
    db_session.add(
        Chunk(
            extraction_id=extraction.id,
            ordinal=0,
            text="integration by parts moves the derivative onto one factor",
        )
    )
    sync_material_fts(
        db_session, material, "integration by parts moves the derivative onto one factor"
    )
    db_session.commit()

    def embed(query: str) -> tuple[str, list[list[float]]] | None:
        return None

    exact = retrieve_chunks(db_session, "derivative", embed, limit=5)
    assert [row["text"] for row in exact]
    fuzzy = retrieve_chunks(db_session, "derivatve", embed, limit=5)
    assert fuzzy == exact
    assert retrieve_chunks(db_session, "xylophone", embed, limit=5) == []


def _run_migrations(db_path: Path, target: str | None = None) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(config, target or "head")


def test_migration_backfills_trigram_index(tmp_path: Path) -> None:
    import sqlite3

    db_path = tmp_path / "legacy.db"
    _run_migrations(db_path, "0044_chat_branches")

    raw = sqlite3.connect(db_path)
    raw.execute(
        "INSERT INTO material_fts (title, markdown, description, topics, material_id) "
        "VALUES ('Thermodynamics', 'entropy and energy', '', '', 1)"
    )
    raw.commit()
    raw.close()

    _run_migrations(db_path)

    check = sqlite3.connect(db_path)
    try:
        rows = check.execute(
            "SELECT material_id FROM material_fts_trigram "
            "WHERE material_fts_trigram MATCH '\"ody\"'"
        ).fetchall()
    finally:
        check.close()
    assert rows == [(1,)]

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.downgrade(config, "0044_chat_branches")
    check = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        check.close()
    assert "material_fts_trigram" not in tables
