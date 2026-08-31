import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


def make_course(client: TestClient, title: str) -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


def add_source(client: TestClient, course_id: int, root: Path, label: str) -> int:
    created = client.post(
        "/api/v1/sources",
        json={"label": label, "path": str(root), "course_id": course_id},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def folders_in(client: TestClient, course_id: int) -> list[dict[str, Any]]:
    listing: list[dict[str, Any]] = client.get(
        "/api/v1/folders", params={"course_id": course_id}
    ).json()
    return listing


def test_source_create_makes_link_node_and_unlink_keeps_materials(
    client: TestClient, tmp_path: Path
) -> None:
    course_id = make_course(client, "Linked")
    target = tmp_path / "lectures"
    (target / "sub").mkdir(parents=True)
    (target / "week1.md").write_text("# Week 1\n\nPower rule content.")

    source_id = add_source(client, course_id, target, "My/Lectures")
    nodes = folders_in(client, course_id)
    assert [node["name"] for node in nodes] == ["My-Lectures"]
    assert nodes[0]["source_id"] == source_id

    scanned = client.post(f"/api/v1/sources/{source_id}/scan").json()
    assert scanned["stats"]["new"] == 1
    listing = client.get(
        "/api/v1/materials", params={"course_id": course_id, "unfiled": "true"}
    ).json()
    assert listing == []
    browse = client.get(f"/api/v1/sources/{source_id}/browse").json()
    assert [d["name"] for d in browse["subdirs"]] == ["sub"]
    assert len(browse["materials"]) == 1

    node_id = nodes[0]["id"]
    unlinked = client.post(f"/api/v1/folders/{node_id}/unlink")
    assert unlinked.status_code == 204
    assert folders_in(client, course_id) == []
    after = client.get(
        "/api/v1/materials", params={"course_id": course_id, "unfiled": "true"}
    ).json()
    assert len(after) == 1
    material = after[0]
    detail = client.get(f"/api/v1/materials/{material['id']}").json()["material"]
    assert detail["folder_id"] is None
    sources = client.get("/api/v1/sources").json()
    assert sources == []


def test_browse_lists_pending_files_and_ingest(client: TestClient, tmp_path: Path) -> None:
    course_id = make_course(client, "Browse")
    target = tmp_path / "docs"
    (target / "inner").mkdir(parents=True)
    (target / "a.txt").write_text("alpha content")
    (target / "inner" / "b.txt").write_text("beta content")
    (target / "ignored.bin").write_bytes(b"\x00\x01")

    source_id = add_source(client, course_id, target, "Docs")

    root_view = client.get(f"/api/v1/sources/{source_id}/browse").json()
    assert root_view["missing_target"] is False
    assert [d["name"] for d in root_view["subdirs"]] == ["inner"]
    assert [f["name"] for f in root_view["uningested"]] == ["a.txt"]
    assert root_view["materials"] == []

    inner_view = client.get(
        f"/api/v1/sources/{source_id}/browse", params={"subdir": "inner"}
    ).json()
    assert [f["name"] for f in inner_view["uningested"]] == ["b.txt"]

    ingest = client.post(
        f"/api/v1/sources/{source_id}/ingest", json={"relpath": "a.txt"}
    )
    assert ingest.status_code == 201, ingest.text
    material_id = ingest.json()["material_id"]
    assert ingest.json()["deduped"] is False
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        == "ready"
    )

    root_view = client.get(f"/api/v1/sources/{source_id}/browse").json()
    assert root_view["uningested"] == []
    assert [m["relpath"] for m in root_view["materials"]] == ["a.txt"]

    duplicate = client.post(
        f"/api/v1/sources/{source_id}/ingest", json={"relpath": "a.txt"}
    ).json()
    assert duplicate["material_id"] == material_id

    escape = client.post(
        f"/api/v1/sources/{source_id}/ingest", json={"relpath": "../outside.txt"}
    )
    assert escape.status_code == 422
    traversal = client.get(
        f"/api/v1/sources/{source_id}/browse", params={"subdir": "../../etc"}
    )
    assert traversal.status_code == 422
    missing = client.get(
        f"/api/v1/sources/{source_id}/browse", params={"subdir": "nope"}
    )
    assert missing.status_code == 422

    upload_into_link = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": ("x.txt", b"x", "text/plain")},
    )
    assert upload_into_link.status_code == 200


def test_browse_missing_target_and_relink(client: TestClient, tmp_path: Path) -> None:
    course_id = make_course(client, "Dangling")
    target = tmp_path / "gone"
    target.mkdir()
    (target / "note.txt").write_text("content here")
    source_id = add_source(client, course_id, target, "Gone")
    client.post(f"/api/v1/sources/{source_id}/scan")
    time.sleep(0.1)
    target.rename(tmp_path / "moved")

    dangling = client.get(f"/api/v1/sources/{source_id}/browse").json()
    assert dangling["missing_target"] is True
    assert dangling["materials"] or dangling["materials"] == []

    relink = client.patch(
        f"/api/v1/sources/{source_id}", json={"path": str(tmp_path / "moved")}
    )
    assert relink.status_code == 200, relink.text
    again = client.get(f"/api/v1/sources/{source_id}/browse").json()
    assert again["missing_target"] is False
    bad_relink = client.patch(
        f"/api/v1/sources/{source_id}", json={"path": "/nonexistent-dir-xyz"}
    )
    assert bad_relink.status_code == 422


def test_text_file_create_rename_delete(client: TestClient) -> None:
    course_id = make_course(client, "Texts")
    created = client.post(
        "/api/v1/materials/text",
        json={
            "course_id": course_id,
            "filename": "quick note",
            "content": "# Quick\n\nSome markdown with $x^2$.",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["material"]["kind"] == "txt"
    assert body["material"]["course_id"] == course_id
    material_id = body["material"]["id"]
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        == "ready"
    )
    detail = client.get(f"/api/v1/materials/{material_id}").json()
    assert "Quick" in detail["extraction"]["markdown"]

    as_md = client.post(
        "/api/v1/materials/text",
        json={"course_id": course_id, "filename": "notes.md", "content": "body"},
    )
    assert as_md.json()["material"]["kind"] == "md"

    renamed = client.patch(
        f"/api/v1/materials/{material_id}", json={"title": "Renamed note"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed note"
    empty = client.patch(f"/api/v1/materials/{material_id}", json={"title": "  "})
    assert empty.status_code == 422

    deleted = client.delete(f"/api/v1/materials/{material_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/materials/{material_id}").status_code == 404
    hits = client.get("/api/v1/search", params={"q": "Quick"}).json()["hits"]
    assert hits == []


def test_blob_served_with_guessed_mime_inline(client: TestClient, tmp_path: Path) -> None:
    from fastapi import FastAPI

    course_id = make_course(client, "Mime")
    target = tmp_path / "files"
    target.mkdir()
    (target / "lecture.txt").write_text("plain lecture text")
    source_id = add_source(client, course_id, target, "Files")
    ingest = client.post(
        f"/api/v1/sources/{source_id}/ingest", json={"relpath": "lecture.txt"}
    )
    material_id = ingest.json()["material_id"]
    detail = client.get(f"/api/v1/materials/{material_id}").json()["material"]
    sha = detail["blob_sha"]

    served = client.get(f"/api/v1/blobs/{sha}")
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("text/plain")
    assert served.headers["content-disposition"] == "inline"

    app = client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as db:
        from app.domain.models import Blob

        blob_row = db.get(Blob, sha)
        assert blob_row is not None
        blob_row.mime = None
        db.commit()

    legacy = client.get(f"/api/v1/blobs/{sha}")
    assert legacy.status_code == 200
    assert legacy.headers["content-type"].startswith("text/plain")
    assert 'filename="lecture.txt"' in legacy.headers["content-disposition"]


def test_blob_served_with_non_ascii_filename(client: TestClient, tmp_path: Path) -> None:
    from fastapi import FastAPI

    course_id = make_course(client, "Greek")
    target = tmp_path / "greek"
    target.mkdir()
    (target / "Σημειώσεις.txt").write_text("διαλέξεις")
    source_id = add_source(client, course_id, target, "Greek files")
    ingest = client.post(
        f"/api/v1/sources/{source_id}/ingest", json={"relpath": "Σημειώσεις.txt"}
    )
    material_id = ingest.json()["material_id"]
    sha = client.get(f"/api/v1/materials/{material_id}").json()["material"]["blob_sha"]

    app = client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as db:
        from app.domain.models import Blob

        blob_row = db.get(Blob, sha)
        assert blob_row is not None
        blob_row.mime = None
        db.commit()

    served = client.get(f"/api/v1/blobs/{sha}")
    assert served.status_code == 200
    disposition = served.headers["content-disposition"]
    assert disposition.startswith("inline")
    assert "filename*=UTF-8''" in disposition
    assert "Σημειώσεις" not in disposition.split("filename*=")[0]


def test_scan_remaps_moved_files_by_content_hash(
    client: TestClient, tmp_path: Path
) -> None:
    course_id = make_course(client, "Moves")
    target = tmp_path / "src"
    (target / "old").mkdir(parents=True)
    (target / "old" / "notes.md").write_text("# Move me\n\nstable content")
    source_id = add_source(client, course_id, target, "Moves")

    first = client.post(f"/api/v1/sources/{source_id}/scan").json()
    assert first["stats"]["new"] == 1
    materials = client.get("/api/v1/materials", params={"course_id": course_id}).json()
    material_id = materials[0]["id"]
    assert materials[0]["status"] != "missing"

    moved_dir = target / "new"
    moved_dir.mkdir()
    (target / "old" / "notes.md").rename(moved_dir / "notes.md")

    second = client.post(f"/api/v1/sources/{source_id}/scan").json()
    assert second["stats"]["moved"] == 1
    assert second["stats"]["new"] == 0
    after = client.get("/api/v1/materials", params={"course_id": course_id}).json()
    assert len(after) == 1
    assert after[0]["id"] == material_id
    assert after[0]["filename"] == "notes.md"


def test_scan_scheduler_cycles_sources(tmp_path: Path) -> None:
    from alembic.config import Config

    from alembic import command
    from app.core.config import Settings
    from app.main import create_app
    from app.services.platform.scan_scheduler import ScanScheduler

    db_path = tmp_path / "sched.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")

    settings = Settings(data_dir=tmp_path, log_level="WARNING")
    app = create_app(settings)
    assert isinstance(app.state.scans, ScanScheduler)

    published: list[tuple[str, dict[str, Any]]] = []
    scans = ScanScheduler(
        app.state.session_factory,
        settings.blobs_dir,
        app.state.jobs,
        lambda topic, payload: published.append((topic, payload)),
        startup_delay_sec=0,
    )
    assert scans.scan_all() == {}

    with app.state.session_factory() as session:
        from app.domain.models import Course, MaterialSource, Profile

        profile = Profile(name="sched")
        session.add(profile)
        session.flush()
        course = Course(profile_id=profile.id, title="Sched")
        session.add(course)
        session.flush()
        session.add(
            MaterialSource(
                profile_id=profile.id,
                label="Gone",
                path=str(tmp_path / "nope"),
                recursive=True,
                include_globs=None,
                course_id=course.id,
            )
        )
        session.commit()

    assert scans.scan_all() == {}
    assert published == []

    scans.start()
    scans.stop()


def test_scan_error_recorded_and_cleared(client: TestClient, tmp_path: Path) -> None:
    course_id = make_course(client, "Errs")
    target = tmp_path / "flaky"
    target.mkdir()
    (target / "a.txt").write_text("alpha")
    source_id = add_source(client, course_id, target, "Flaky")

    ok_scan = client.post(f"/api/v1/sources/{source_id}/scan")
    assert ok_scan.status_code == 200
    browse = client.get(f"/api/v1/sources/{source_id}/browse").json()
    assert browse["last_scan_error"] is None
    assert browse["last_scanned_at"] is not None
    assert browse["enabled"] is True

    target.rename(tmp_path / "flaky-gone")
    broken = client.post(f"/api/v1/sources/{source_id}/scan")
    assert broken.status_code == 422
    listing = client.get("/api/v1/sources").json()
    entry = next(s for s in listing if s["id"] == source_id)
    assert entry["last_scan_error"] is not None
    assert "gone" in entry["last_scan_error"]

    client.patch(f"/api/v1/sources/{source_id}", json={"path": str(tmp_path / "flaky-gone")})
    healed = client.post(f"/api/v1/sources/{source_id}/scan")
    assert healed.status_code == 200
    listing = client.get("/api/v1/sources").json()
    entry = next(s for s in listing if s["id"] == source_id)
    assert entry["last_scan_error"] is None


def test_source_create_validates_scan_interval(client: TestClient, tmp_path: Path) -> None:
    course_id = make_course(client, "Intervals")
    too_small = client.post(
        "/api/v1/sources",
        json={
            "label": "Fast",
            "path": str(tmp_path),
            "course_id": course_id,
            "scan_interval_sec": 5,
        },
    )
    assert too_small.status_code == 422

    created = client.post(
        "/api/v1/sources",
        json={
            "label": "Hourly",
            "path": str(tmp_path),
            "course_id": course_id,
            "scan_interval_sec": 3600,
        },
    )
    assert created.status_code == 201
    assert created.json()["scan_interval_sec"] == 3600


def test_fs_dirs_picker(client: TestClient, tmp_path: Path) -> None:
    scope = tmp_path / "picker"
    scope.mkdir()
    hidden = scope / ".hidden"
    hidden.mkdir()
    visible = scope / "visible"
    visible.mkdir()
    (scope / "file.txt").write_text("not a dir")

    result = client.get("/api/v1/fs/dirs", params={"path": str(scope)}).json()
    assert result["path"] == str(scope)
    assert [d["name"] for d in result["dirs"]] == ["visible"]
    assert result["parent"] == str(scope.parent)
    assert result["home"]

    default = client.get("/api/v1/fs/dirs").json()
    assert default["path"] == default["home"]

    bad = client.get("/api/v1/fs/dirs", params={"path": "/nonexistent-dir-xyz"})
    assert bad.status_code == 422
