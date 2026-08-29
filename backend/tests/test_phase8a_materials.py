import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command


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


def upload_txt(client: TestClient, filename: str, course_id: int) -> int:
    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (filename, f"content of {filename}".encode(), "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    material_id = int(upload.json()["material"]["id"])
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        == "ready"
    )
    return material_id


def test_migration_moves_legacy_data_to_unsorted(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "0013_skills")

    import sqlite3

    raw = sqlite3.connect(db_path)
    now = "2026-08-19 10:00:00+00:00"
    raw.execute(
        "INSERT INTO profiles (id, name, created_at) VALUES (1, 'legacy', ?)", (now,)
    )
    raw.execute(
        "INSERT INTO courses (id, profile_id, title, created_at, updated_at) "
        "VALUES (10, 1, 'Real course', ?, ?)",
        (now, now),
    )
    raw.execute(
        "INSERT INTO chapters (id, course_id, title, order_idx, created_at) "
        "VALUES (20, 10, 'Chapter', 0, ?)",
        (now,),
    )
    raw.execute(
        "INSERT INTO sections (id, chapter_id, title, order_idx, created_at) "
        "VALUES (30, 20, 'Section', 0, ?)",
        (now,),
    )
    raw.execute(
        "INSERT INTO blobs (sha256, rel_path, size, created_at) VALUES "
        "('aa11', 'aa/11/aa11', 4, ?), ('bb22', 'bb/22/bb22', 4, ?)",
        (now, now),
    )
    raw.execute(
        "INSERT INTO materials (id, profile_id, course_id, kind, title, blob_sha, filename, "
        "status, content_hash, created_at) VALUES "
        "(100, 1, 10, 'txt', 'owned', 'aa11', 'owned.txt', 'ready', 'aa11', ?), "
        "(101, 1, NULL, 'txt', 'orphan', 'bb22', 'orphan.txt', 'ready', 'bb22', ?)",
        (now, now),
    )
    raw.execute(
        "INSERT INTO material_folders (id, profile_id, parent_id, name, path, created_at) VALUES "
        "(40, 1, NULL, 'single', 'single', ?), "
        "(45, 1, NULL, 'mixed', 'mixed', ?)",
        (now, now),
    )
    raw.execute("UPDATE materials SET folder_id = 40 WHERE id = 100")
    raw.execute("UPDATE materials SET folder_id = 45 WHERE id = 101")
    raw.execute(
        "INSERT INTO material_sources (id, profile_id, label, path, recursive, include_globs, "
        "course_id, enabled, created_at) VALUES (50, 1, 'src', '/tmp', 1, NULL, NULL, 1, ?)",
        (now,),
    )
    raw.execute(
        "INSERT INTO section_materials (section_id, material_id, rationale, auto_assigned) "
        "VALUES (30, 100, 'legacy allocation', 1)"
    )
    raw.commit()
    raw.close()

    command.upgrade(alembic_cfg, "head")

    raw = sqlite3.connect(db_path)
    cur = raw.cursor()
    assert (
        cur.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        == "0047_drawing_ocr_jobs"
    )
    unsorted_id = cur.execute(
        "SELECT id FROM courses WHERE title = 'Unsorted' AND profile_id = 1"
    ).fetchone()
    assert unsorted_id is not None
    unsorted_id = unsorted_id[0]
    assert (
        cur.execute("SELECT course_id FROM materials WHERE id = 101").fetchone()[0]
        == unsorted_id
    )
    assert cur.execute("SELECT course_id FROM materials WHERE id = 100").fetchone()[0] == 10
    assert cur.execute("SELECT course_id FROM material_folders WHERE id = 40").fetchone()[0] == 10
    assert (
        cur.execute("SELECT course_id FROM material_folders WHERE id = 45").fetchone()[0]
        == unsorted_id
    )
    assert (
        cur.execute("SELECT course_id FROM material_sources WHERE id = 50").fetchone()[0]
        == unsorted_id
    )
    tables = {row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "section_materials" not in tables
    assert "chapters" not in tables
    assert "sections" not in tables
    nodes = cur.execute(
        "SELECT id, parent_id, depth, is_root, title FROM tree_nodes WHERE course_id = 10 "
        "ORDER BY depth, id"
    ).fetchall()
    root = next(row for row in nodes if row[3] == 1)
    chapter_node = next(row for row in nodes if row[4] == "Chapter")
    section_node = next(row for row in nodes if row[4] == "Section")
    assert root[2] == 0 and chapter_node[2] == 1 and section_node[2] == 2
    assert chapter_node[1] == root[0] and section_node[1] == chapter_node[0]
    links = cur.execute(
        "SELECT course_id, node_id, material_id, rationale FROM material_links"
    ).fetchall()
    assert links == [(10, section_node[0], 100, "legacy allocation")]
    raw.close()


def make_node(client: TestClient, course_id: int, parent_id: int, title: str) -> int:
    created = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": parent_id, "title": title},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def root_node(client: TestClient, course_id: int) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    assert tree and tree[0]["is_root"] is True
    return int(tree[0]["id"])


def test_assign_material_at_all_scopes(client: TestClient) -> None:
    course_id = make_course(client, "Scoped")
    other_id = make_course(client, "Other")
    material_id = upload_txt(client, "scoped.txt", course_id)
    foreign_id = upload_txt(client, "foreign.txt", other_id)

    root = root_node(client, course_id)
    chapter_id = make_node(client, course_id, root, "Ch1")
    section_id = make_node(client, course_id, chapter_id, "S1")

    course_link = client.post(
        f"/api/v1/courses/{course_id}/materials", json={"material_id": material_id}
    )
    assert course_link.status_code == 201
    chapter_link = client.post(
        f"/api/v1/nodes/{chapter_id}/materials", json={"material_id": material_id}
    )
    assert chapter_link.status_code == 201
    section_link = client.post(
        f"/api/v1/nodes/{section_id}/materials", json={"material_id": material_id}
    )
    assert section_link.status_code == 201

    cross = client.post(
        f"/api/v1/nodes/{section_id}/materials", json={"material_id": foreign_id}
    )
    assert cross.status_code == 422
    assert "material not in this course" in cross.json()["detail"]

    listing = client.get(f"/api/v1/courses/{course_id}/materials").json()
    scopes = {row["node_id"] for row in listing}
    assert scopes == {root, chapter_id, section_id}

    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    assert tree[0]["materials"][0]["material_id"] == material_id
    chapter_entry = next(c for c in tree[0]["children"] if c["id"] == chapter_id)
    assert chapter_entry["materials"][0]["material_id"] == material_id
    assert chapter_entry["children"][0]["materials"][0]["material_id"] == material_id

    removed = client.delete(f"/api/v1/nodes/{chapter_id}/materials/{material_id}")
    assert removed.status_code == 204
    listing = client.get(f"/api/v1/courses/{course_id}/materials").json()
    assert chapter_id not in {row["node_id"] for row in listing}
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    chapter_entry = next(c for c in tree[0]["children"] if c["id"] == chapter_id)
    assert chapter_entry["materials"] == []


def test_unlink_keeps_material(client: TestClient) -> None:
    course_id = make_course(client, "Keep")
    material_id = upload_txt(client, "keep.txt", course_id)
    client.post(f"/api/v1/courses/{course_id}/materials", json={"material_id": material_id})
    client.delete(f"/api/v1/courses/{course_id}/materials/{material_id}")
    detail = client.get(f"/api/v1/materials/{material_id}").json()
    assert detail["material"]["id"] == material_id
    assert client.get(f"/api/v1/courses/{course_id}/materials").json() == []


def test_outline_commit_allocates_via_links(client: TestClient) -> None:
    course_id = make_course(client, "Outline")
    material_id = upload_txt(client, "one.txt", course_id)
    commit = client.post(
        f"/api/v1/courses/{course_id}/outline/commit",
        json={
            "chapters": [
                {
                    "title": "Only chapter",
                    "summary": None,
                    "sections": [
                        {
                            "title": "Only section",
                            "objectives": [],
                            "material_ids": [material_id],
                            "rationale": "auto",
                            "confidence": 0.8,
                        }
                    ],
                }
            ]
        },
    )
    assert commit.status_code == 200
    assert commit.json()["allocations"] == 1
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    allocation = tree[0]["children"][0]["children"][0]["materials"][0]
    assert allocation["material_id"] == material_id
    assert allocation["auto_assigned"] is True
    listing = client.get(f"/api/v1/courses/{course_id}/materials").json()
    assert listing[0]["node_is_root"] is False


CAQ_SINGLE: dict[str, Any] = {
    "$schema": "caq/v1",
    "title": "Purge probe",
    "questions": [
        {
            "id": "q1",
            "type": "truefalse",
            "stem_md": "Purge me.",
            "answer": True,
            "explanation_md": "Because.",
            "concepts": ["purging"],
            "skill": "conceptual",
            "bloom": "remember",
            "difficulty": 1,
            "expected_time_sec": 30,
        }
    ],
}


def test_delete_course_purges_content(client: TestClient) -> None:
    course_id = make_course(client, "Doomed")
    material_id = upload_txt(client, "doomed.txt", course_id)
    folder = client.post(
        "/api/v1/folders", json={"name": "Doomed folder", "course_id": course_id}
    )
    assert folder.status_code == 201
    root = root_node(client, course_id)
    chapter_id = make_node(client, course_id, root, "Ch")
    client.post(f"/api/v1/nodes/{chapter_id}/materials", json={"material_id": material_id})
    note = client.post("/api/v1/notes", json={"title": "Doomed note", "course_id": course_id})
    assert note.status_code == 201
    imported = client.post(
        "/api/v1/quiz/import",
        params={"dry_run": "false", "course_id": course_id},
        json=CAQ_SINGLE,
    )
    assert imported.status_code == 200, imported.text
    session = client.post("/api/v1/chat/sessions", json={"course_id": course_id})
    assert session.status_code == 201

    deleted = client.delete(
        f"/api/v1/courses/{course_id}", params={"confirmed_backup": True}
    )
    assert deleted.status_code == 200

    assert client.get(f"/api/v1/materials/{material_id}").status_code == 404
    assert client.get("/api/v1/materials").json() == []
    assert client.get("/api/v1/folders").json() == []
    assert client.get("/api/v1/notes").json()["items"] == []
    assert client.get("/api/v1/quiz/activities").json() == []
    assert client.get("/api/v1/chat/sessions").json() == []
    assert client.get("/api/v1/courses").json() == []
    hits = client.get("/api/v1/search", params={"q": "doomed"}).json()["hits"]
    assert hits == []


def test_material_needs_matching_folder_course(client: TestClient) -> None:
    course_id = make_course(client, "Folders")
    other_id = make_course(client, "Other")
    foreign_folder = client.post(
        "/api/v1/folders", json={"name": "Foreign", "course_id": other_id}
    ).json()
    response = client.post(
        "/api/v1/materials",
        params={"course_id": course_id, "folder_id": foreign_folder["id"]},
        files={"file": ("mismatch.txt", b"mismatch", "text/plain")},
    )
    assert response.status_code == 422
    assert "different course" in response.json()["detail"]


def test_node_workspace_endpoint(client: TestClient) -> None:
    course_id = make_course(client, "Workspace")
    material_id = upload_txt(client, "ws.txt", course_id)
    other_id = upload_txt(client, "other.txt", course_id)
    root = root_node(client, course_id)
    chapter_id = make_node(client, course_id, root, "Derivatives")
    make_node(client, course_id, chapter_id, "Sub")
    section_id = make_node(client, course_id, chapter_id, "Chain rule")
    client.patch(f"/api/v1/nodes/{section_id}", json={"objectives": ["Apply it"]})
    client.post(f"/api/v1/nodes/{chapter_id}/materials", json={"material_id": material_id})
    client.post(f"/api/v1/nodes/{section_id}/materials", json={"material_id": other_id})
    client.put(
        f"/api/v1/materials/{material_id}/study-state", json={"status": "reading", "progress": 0.5}
    )
    note = client.post(
        "/api/v1/notes",
        json={"title": "Section note", "course_id": course_id, "node_id": section_id},
    )
    assert note.status_code == 201, note.text
    outside_note = client.post(
        "/api/v1/notes", json={"title": "Standalone", "course_id": course_id}
    )
    assert outside_note.status_code == 201

    workspace = client.get(f"/api/v1/nodes/{chapter_id}/workspace").json()
    assert workspace["node"]["title"] == "Derivatives"
    assert workspace["node"]["course_id"] == course_id
    assert workspace["node"]["course_title"] == "Workspace"
    assert [entry["title"] for entry in workspace["node"]["breadcrumb"]] == [
        "Workspace",
        "Derivatives",
    ]
    assert [m["material_id"] for m in workspace["materials"]] == [material_id]
    assert workspace["materials"][0]["read_status"] == "reading"
    assert workspace["materials"][0]["progress"] == 0.5
    child_titles = [entry["title"] for entry in workspace["children"]]
    assert child_titles == ["Sub", "Chain rule"]
    assert [m["material_id"] for m in workspace["child_materials"][str(section_id)]] == [other_id]
    assert [n["title"] for n in workspace["notes"]] == ["Section note"]
    assert workspace["counts"]["notes"] == {"direct": 0, "with_children": 1}

    missing = client.get("/api/v1/nodes/99999/workspace")
    assert missing.status_code == 404


def test_unfiled_listing_and_material_links_endpoint(client: TestClient) -> None:
    course_id = make_course(client, "Browse")
    filed_id = upload_txt(client, "filed.txt", course_id)
    loose_id = upload_txt(client, "loose.txt", course_id)

    unfiled = client.get(
        "/api/v1/materials", params={"course_id": course_id, "unfiled": "true"}
    ).json()
    unfiled_ids = {material["id"] for material in unfiled}
    assert loose_id in unfiled_ids
    assert filed_id in unfiled_ids

    folder = client.post(
        "/api/v1/folders", json={"name": "Box", "course_id": course_id}
    ).json()
    filed = client.post(
        "/api/v1/materials",
        params={"course_id": course_id, "folder_id": folder["id"]},
        files={"file": ("in-folder.txt", b"in folder", "text/plain")},
    ).json()
    unfiled_after = client.get(
        "/api/v1/materials", params={"course_id": course_id, "unfiled": "true"}
    ).json()
    after_ids = {material["id"] for material in unfiled_after}
    assert filed["material"]["id"] not in after_ids
    assert filed_id in after_ids

    root = root_node(client, course_id)
    chapter_id = make_node(client, course_id, root, "Ch")
    section_id = make_node(client, course_id, chapter_id, "Sec")
    client.post(f"/api/v1/nodes/{chapter_id}/materials", json={"material_id": filed_id})
    client.post(f"/api/v1/nodes/{section_id}/materials", json={"material_id": loose_id})

    links = client.get(f"/api/v1/materials/{loose_id}/links").json()
    assert links == [
        {
            "node_id": section_id,
            "owner_title": "Sec",
            "breadcrumb": [
                {"id": root, "title": "Browse"},
                {"id": chapter_id, "title": "Ch"},
                {"id": section_id, "title": "Sec"},
            ],
            "is_course_level": False,
            "course_id": course_id,
            "course_title": "Browse",
            "auto_assigned": False,
            "rationale": None,
            "via_folder": None,
        }
    ]

    chapter_links = client.get(f"/api/v1/materials/{filed_id}/links").json()
    assert chapter_links[0]["node_id"] == chapter_id
    assert chapter_links[0]["owner_title"] == "Ch"
    assert chapter_links[0]["course_title"] == "Browse"

    missing = client.get("/api/v1/materials/99999/links")
    assert missing.status_code == 404
