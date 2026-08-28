from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.domain.models import Course, Extraction, Material, Profile
from app.storage.blobs import BlobStore


def test_all_phase1_tables_exist(db_session: Session) -> None:
    inspector = inspect(db_session.get_bind())
    tables = set(inspector.get_table_names())
    expected = {
        "profiles",
        "courses",
        "blobs",
        "material_groups",
        "materials",
        "extractions",
        "chunks",
        "material_index_cards",
        "jobs",
        "material_fts",
    }
    assert expected <= tables


def test_fts_is_queryable_and_empty(db_session: Session) -> None:
    rows = db_session.execute(text("SELECT count(*) FROM material_fts")).scalar_one()
    assert rows == 0


def test_material_lifecycle_roundtrip(db_session: Session, tmp_path: Path) -> None:
    profile = Profile(name="Ilias")
    db_session.add(profile)
    db_session.flush()

    store = BlobStore(tmp_path / "blobs")
    stored = store.put(b"%PDF-1.7 fake", mime="application/pdf", session=db_session)

    course = Course(profile_id=profile.id, title="Schema course")
    db_session.add(course)
    db_session.flush()

    material = Material(
        profile_id=profile.id,
        course_id=course.id,
        kind="pdf",
        title="Lecture 1",
        filename="lecture1.pdf",
        mime="application/pdf",
        status="ready",
        content_hash=stored.sha256,
        blob_sha=stored.sha256,
    )
    db_session.add(material)
    db_session.flush()

    extraction = Extraction(
        material_id=material.id,
        version=1,
        extractor="pymupdf",
        blocks=[{"type": "text", "md": "chain rule"}],
        markdown="chain rule",
    )
    db_session.add(extraction)
    db_session.commit()

    loaded = db_session.get(Material, material.id)
    assert loaded is not None
    assert loaded.extractions[0].markdown == "chain rule"
    assert loaded.profile_id == profile.id


def test_profile_scoping_on_courses(db_session: Session) -> None:
    p1 = Profile(name="a")
    p2 = Profile(name="b")
    db_session.add_all([p1, p2])
    db_session.flush()
    db_session.add(Course(profile_id=p1.id, title="Calc"))
    db_session.commit()
    mine = db_session.query(Course).filter(Course.profile_id == p1.id).count()
    theirs = db_session.query(Course).filter(Course.profile_id == p2.id).count()
    assert (mine, theirs) == (1, 0)
