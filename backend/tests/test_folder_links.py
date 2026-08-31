import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.domain.models import Course, Material, MaterialFolder, TreeNode
from app.services.study import organizer


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


def make_node(client: TestClient, course_id: int, title: str) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    root_id = tree[0]["id"]
    created = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root_id, "title": title},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def make_folder(client: TestClient, course_id: int, name: str, parent_id: int | None = None) -> int:
    created = client.post(
        "/api/v1/folders",
        json={"name": name, "course_id": course_id, "parent_id": parent_id},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def add_material(
    client: TestClient, filename: str, course_id: int, folder_id: int | None = None
) -> int:
    body = f"calculus notes {filename} about limits and continuity".encode()
    params: dict[str, Any] = {"course_id": course_id}
    if folder_id is not None:
        params["folder_id"] = folder_id
    upload = client.post(
        "/api/v1/materials",
        params=params,
        files={"file": (filename, body, "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    material_id: int = upload.json()["material"]["id"]
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        == "ready"
    )
    return material_id


def workspace_of(client: TestClient, node_id: int) -> dict[str, Any]:
    response = client.get(f"/api/v1/nodes/{node_id}/workspace")
    assert response.status_code == 200, response.text
    payload: dict[str, Any] = response.json()
    return payload


def test_folder_assignment_resolves_in_workspace(client: TestClient) -> None:
    course_id = make_course(client, "Folder assign")
    folder_id = make_folder(client, course_id, "Lectures")
    subfolder_id = make_folder(client, course_id, "Week 1", parent_id=folder_id)
    in_folder = add_material(client, "a.md", course_id, folder_id=folder_id)
    in_subfolder = add_material(client, "b.md", course_id, folder_id=subfolder_id)
    node_id = make_node(client, course_id, "Limits")

    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials",
        json={"folder_id": folder_id, "rationale": "whole lecture set"},
    )
    assert assigned.status_code == 201, assigned.text
    assert assigned.json() == {"node_id": node_id, "folder_id": folder_id}

    workspace = workspace_of(client, node_id)
    assert workspace["materials"] == []
    assert workspace["folder_material_ids"] == sorted([in_folder, in_subfolder])
    folders = workspace["folders"]
    assert len(folders) == 1
    assert folders[0] == {
        "folder_id": folder_id,
        "name": "Lectures",
        "source_id": None,
        "member_count": 2,
        "rationale": "whole lecture set",
        "auto_assigned": False,
    }

    late = add_material(client, "late.md", course_id, folder_id=folder_id)
    workspace = workspace_of(client, node_id)
    assert workspace["folder_material_ids"] == sorted([in_folder, in_subfolder, late])
    assert workspace["folders"][0]["member_count"] == 3


def test_folder_assignment_direct_link_wins(client: TestClient) -> None:
    course_id = make_course(client, "Direct wins")
    folder_id = make_folder(client, course_id, "Docs")
    material_id = add_material(client, "a.md", course_id, folder_id=folder_id)
    node_id = make_node(client, course_id, "Node")

    direct = client.post(
        f"/api/v1/nodes/{node_id}/materials", json={"material_id": material_id}
    )
    assert direct.status_code == 201
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert assigned.status_code == 201

    workspace = workspace_of(client, node_id)
    entries = list(workspace["materials"])
    assert len(entries) == 1
    assert entries[0]["via_folder_id"] is None
    assert entries[0]["rationale"] is None


def test_folder_assignment_idempotent_updates_rationale(client: TestClient) -> None:
    course_id = make_course(client, "Idempotent")
    folder_id = make_folder(client, course_id, "Docs")
    node_id = make_node(client, course_id, "Node")

    first = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials",
        json={"folder_id": folder_id, "rationale": "first"},
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials",
        json={"folder_id": folder_id, "rationale": "second"},
    )
    assert second.status_code == 201
    workspace = workspace_of(client, node_id)
    assert len(workspace["folders"]) == 1
    assert workspace["folders"][0]["rationale"] == "second"


def test_folder_assignment_validation_errors(client: TestClient) -> None:
    course_id = make_course(client, "Validation")
    other_course_id = make_course(client, "Other")
    folder_id = make_folder(client, course_id, "Docs")
    node_id = make_node(client, course_id, "Node")

    unknown_node = client.post(
        "/api/v1/nodes/999999/folder-materials", json={"folder_id": folder_id}
    )
    assert unknown_node.status_code == 404
    unknown_folder = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": 999999}
    )
    assert unknown_folder.status_code == 422
    foreign_node = make_node(client, other_course_id, "Foreign")
    cross_course = client.post(
        f"/api/v1/nodes/{foreign_node}/folder-materials", json={"folder_id": folder_id}
    )
    assert cross_course.status_code == 422


def test_course_level_folder_assignment(client: TestClient) -> None:
    course_id = make_course(client, "Course level")
    folder_id = make_folder(client, course_id, "All")
    material_id = add_material(client, "a.md", course_id, folder_id=folder_id)

    assigned = client.post(
        f"/api/v1/courses/{course_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert assigned.status_code == 201
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    root = tree[0]
    assert root["counts"]["materials"] == 1
    assert root["folder_links"] == [{"folder_id": folder_id, "name": "All", "source_id": None}]

    listing = client.get(f"/api/v1/courses/{course_id}/materials").json()
    assert listing == [
        {
            "node_id": root["id"],
            "node_title": root["title"],
            "node_is_root": True,
            "material_id": material_id,
            "title": "a",
            "rationale": None,
            "auto_assigned": False,
            "confidence": None,
            "via_folder": {"id": folder_id, "name": "All"},
        }
    ]

    removed = client.delete(
        f"/api/v1/courses/{course_id}/folder-materials/{folder_id}"
    )
    assert removed.status_code == 204
    assert client.get(f"/api/v1/courses/{course_id}/materials").json() == []


def test_unassign_via_folder_material_refused(client: TestClient) -> None:
    course_id = make_course(client, "Unassign guard")
    folder_id = make_folder(client, course_id, "Docs")
    material_id = add_material(client, "a.md", course_id, folder_id=folder_id)
    node_id = make_node(client, course_id, "Node")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert assigned.status_code == 201

    refused = client.delete(f"/api/v1/nodes/{node_id}/materials/{material_id}")
    assert refused.status_code == 422
    assert "via folder" in refused.json()["detail"]

    unassigned = client.delete(
        f"/api/v1/nodes/{node_id}/folder-materials/{folder_id}"
    )
    assert unassigned.status_code == 204
    assert workspace_of(client, node_id)["materials"] == []
    after = client.delete(f"/api/v1/nodes/{node_id}/materials/{material_id}")
    assert after.status_code == 204


def test_folder_delete_refused_while_assigned(client: TestClient) -> None:
    course_id = make_course(client, "Delete guard")
    folder_id = make_folder(client, course_id, "Docs")
    node_id = make_node(client, course_id, "Node")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert assigned.status_code == 201

    refused = client.delete(f"/api/v1/folders/{folder_id}")
    assert refused.status_code == 422
    assert "assigned to nodes" in refused.json()["detail"]

    unassigned = client.delete(
        f"/api/v1/nodes/{node_id}/folder-materials/{folder_id}"
    )
    assert unassigned.status_code == 204
    deleted = client.delete(f"/api/v1/folders/{folder_id}")
    assert deleted.status_code == 204


def test_folder_delete_info_reports_subtree_and_links(client: TestClient) -> None:
    course_id = make_course(client, "Delete info")
    parent_id = make_folder(client, course_id, "Parent")
    folder_id = make_folder(client, course_id, "Docs", parent_id)
    make_folder(client, course_id, "Sub", folder_id)
    material_id = add_material(client, "a.md", course_id, folder_id=folder_id)
    node_id = make_node(client, course_id, "Node")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert assigned.status_code == 201
    second_node = make_node(client, course_id, "Second")
    client.post(
        f"/api/v1/nodes/{second_node}/materials", json={"material_id": material_id}
    )

    info = client.get(f"/api/v1/folders/{folder_id}/delete-info")
    assert info.status_code == 200
    body = info.json()
    assert body["subfolders"] == 1
    assert body["materials"] == 1
    by_node = {entry["node_id"]: entry for entry in body["node_links"]}
    assert set(by_node) == {node_id, second_node}
    assert by_node[node_id]["folder_count"] == 1
    assert by_node[node_id]["material_count"] == 0
    assert by_node[second_node]["material_count"] == 1
    assert by_node[node_id]["breadcrumb"][-1]["title"] == "Node"

    missing = client.get("/api/v1/folders/99999/delete-info")
    assert missing.status_code == 404


def test_folder_force_delete_cascades_subtree(client: TestClient) -> None:
    course_id = make_course(client, "Cascade")
    parent_id = make_folder(client, course_id, "Parent")
    folder_id = make_folder(client, course_id, "Docs", parent_id)
    sub_id = make_folder(client, course_id, "Sub", folder_id)
    material_id = add_material(client, "a.md", course_id, folder_id=sub_id)
    node_id = make_node(client, course_id, "Node")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": sub_id}
    )
    assert assigned.status_code == 201

    refused = client.delete(f"/api/v1/folders/{folder_id}")
    assert refused.status_code == 422

    forced = client.delete(f"/api/v1/folders/{folder_id}?force=true")
    assert forced.status_code == 204

    assert client.get(f"/api/v1/materials/{material_id}").status_code == 404
    folders = client.get("/api/v1/folders", params={"course_id": course_id}).json()
    assert [entry["path"] for entry in folders] == ["Parent"]
    workspace = workspace_of(client, node_id)
    assert workspace["materials"] == []
    assert workspace["folders"] == []


def test_folder_delete_without_links_cascades(client: TestClient) -> None:
    course_id = make_course(client, "Plain cascade")
    parent_id = make_folder(client, course_id, "Parent")
    folder_id = make_folder(client, course_id, "Docs", parent_id)
    make_folder(client, course_id, "Sub", folder_id)
    material_id = add_material(client, "a.md", course_id, folder_id=folder_id)

    deleted = client.delete(f"/api/v1/folders/{folder_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/materials/{material_id}").status_code == 404
    folders = client.get("/api/v1/folders", params={"course_id": course_id}).json()
    assert [entry["path"] for entry in folders] == ["Parent"]


def test_folder_rename_and_move_keep_resolution(client: TestClient) -> None:
    course_id = make_course(client, "Rename")
    folder_id = make_folder(client, course_id, "Docs")
    material_id = add_material(client, "a.md", course_id, folder_id=folder_id)
    node_id = make_node(client, course_id, "Node")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert assigned.status_code == 201

    renamed = client.patch(f"/api/v1/folders/{folder_id}/rename", json={"name": "Notes"})
    assert renamed.status_code == 200
    workspace = workspace_of(client, node_id)
    assert workspace["folders"][0]["name"] == "Notes"
    assert workspace["folders"][0]["member_count"] == 1

    parent_id = make_folder(client, course_id, "Parent")
    moved = client.patch(
        f"/api/v1/folders/{folder_id}/move", json={"parent_id": parent_id}
    )
    assert moved.status_code == 200
    workspace = workspace_of(client, node_id)
    assert workspace["materials"] == []
    assert workspace["folder_material_ids"] == [material_id]


def test_linked_source_folder_assignment(client: TestClient, tmp_path: Path) -> None:
    course_id = make_course(client, "Source assign")
    target = tmp_path / "lectures"
    (target / "sub").mkdir(parents=True)
    (target / "week1.md").write_text("# Week 1\n\nPower rule content.")
    (target / "sub" / "week2.md").write_text("# Week 2\n\nChain rule content.")

    source = client.post(
        "/api/v1/sources",
        json={"label": "Lectures", "path": str(target), "course_id": course_id},
    )
    assert source.status_code == 201, source.text
    source_id = int(source.json()["id"])
    scanned = client.post(f"/api/v1/sources/{source_id}/scan")
    assert scanned.status_code == 200
    folders = client.get("/api/v1/folders", params={"course_id": course_id}).json()
    link_folder = folders[0]
    assert link_folder["source_id"] == source_id

    materials = client.get(
        "/api/v1/materials", params={"course_id": course_id}
    ).json()
    assert len(materials) == 2

    node_id = make_node(client, course_id, "Rules")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials",
        json={"folder_id": link_folder["id"]},
    )
    assert assigned.status_code == 201, assigned.text

    workspace = workspace_of(client, node_id)
    assert workspace["materials"] == []
    assert len(workspace["folder_material_ids"]) == 2
    assert workspace["folders"][0]["source_id"] == source_id
    assert workspace["folders"][0]["member_count"] == 2

    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    node_entry = tree[0]["children"][0]
    assert node_entry["counts"]["materials"] == 2

    unlink = client.post(f"/api/v1/folders/{link_folder['id']}/unlink")
    assert unlink.status_code == 422


def test_material_links_chip_marks_via_folder(client: TestClient) -> None:
    course_id = make_course(client, "Chips")
    folder_id = make_folder(client, course_id, "Docs")
    material_id = add_material(client, "a.md", course_id, folder_id=folder_id)
    node_id = make_node(client, course_id, "Node")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert assigned.status_code == 201

    links = client.get(f"/api/v1/materials/{material_id}/links").json()
    assert len(links) == 1
    assert links[0]["node_id"] == node_id
    assert links[0]["via_folder"] == {"id": folder_id, "name": "Docs"}


def test_context_preview_includes_folder_members(client: TestClient) -> None:
    course_id = make_course(client, "Context")
    folder_id = make_folder(client, course_id, "Docs")
    material_id = add_material(client, "a.md", course_id, folder_id=folder_id)
    add_material(client, "outside.md", course_id)
    node_id = make_node(client, course_id, "Node")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert assigned.status_code == 201

    preview = client.post(
        "/api/v1/ai/context/preview",
        json={"course_id": course_id, "node_id": node_id, "scope": "node"},
    )
    assert preview.status_code == 200, preview.text
    stats = preview.json()["stats"]
    assert [entry["id"] for entry in stats["materials"]] == [material_id]

    subtree = client.post(
        "/api/v1/ai/context/preview",
        json={"course_id": course_id, "node_id": node_id, "scope": "subtree"},
    )
    assert subtree.status_code == 200
    assert [entry["id"] for entry in subtree.json()["stats"]["materials"]] == [material_id]


def test_node_delete_merges_and_dedups_folder_links(client: TestClient) -> None:
    course_id = make_course(client, "Merge")
    folder_id = make_folder(client, course_id, "Docs")
    node_id = make_node(client, course_id, "Node")
    parent_id = make_node(client, course_id, "Parent")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert assigned.status_code == 201
    parent_assigned = client.post(
        f"/api/v1/nodes/{parent_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert parent_assigned.status_code == 201

    deleted = client.delete(f"/api/v1/nodes/{node_id}")
    assert deleted.status_code == 200

    workspace = workspace_of(client, parent_id)
    assert len(workspace["folders"]) == 1


def test_restore_node_restores_folder_links(client: TestClient) -> None:
    course_id = make_course(client, "Restore")
    folder_id = make_folder(client, course_id, "Docs")
    add_material(client, "a.md", course_id, folder_id=folder_id)
    node_id = make_node(client, course_id, "Node")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert assigned.status_code == 201

    deleted = client.delete(f"/api/v1/nodes/{node_id}", params={"snapshot": "true"})
    assert deleted.status_code == 200
    token = deleted.json()["undo_token"]
    restored = client.post("/api/v1/nodes/restore", json={"undo_token": token})
    assert restored.status_code == 200, restored.text
    new_node_id = restored.json()["id"]
    workspace = workspace_of(client, new_node_id)
    assert len(workspace["folders"]) == 1
    assert len(workspace["folder_material_ids"]) == 1
    assert workspace["materials"] == []


def test_course_export_import_round_trips_folders(client: TestClient) -> None:
    course_id = make_course(client, "Bundle")
    folder_id = make_folder(client, course_id, "Lectures")
    subfolder_id = make_folder(client, course_id, "Week 1", parent_id=folder_id)
    add_material(client, "a.md", course_id, folder_id=folder_id)
    add_material(client, "b.md", course_id, folder_id=subfolder_id)
    node_id = make_node(client, course_id, "Limits")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials",
        json={"folder_id": folder_id, "rationale": "lectures"},
    )
    assert assigned.status_code == 201

    exported = client.get(f"/api/v1/courses/{course_id}/export")
    assert exported.status_code == 200
    imported = client.post(
        "/api/v1/courses/import?dry_run=false", content=exported.content
    )
    assert imported.status_code == 200, imported.text
    new_course_id = int(imported.json()["imported"]["course_id"])

    folders = client.get("/api/v1/folders", params={"course_id": new_course_id}).json()
    by_name = {folder["name"]: folder for folder in folders}
    assert {"Lectures", "Week 1"} <= set(by_name)
    assert by_name["Week 1"]["parent_id"] == by_name["Lectures"]["id"]

    materials = client.get(
        "/api/v1/materials", params={"course_id": new_course_id}
    ).json()
    by_title = {material["title"]: material for material in materials}
    assert by_title["a"]["folder_id"] == by_name["Lectures"]["id"]
    assert by_title["b"]["folder_id"] == by_name["Week 1"]["id"]

    tree = client.get(f"/api/v1/courses/{new_course_id}/tree").json()
    limits = tree[0]["children"][0]
    assert limits["folder_links"] == [
        {"folder_id": by_name["Lectures"]["id"], "name": "Lectures", "source_id": None}
    ]
    assert limits["counts"]["materials"] == 2


def test_course_purge_removes_folder_links(client: TestClient) -> None:
    course_id = make_course(client, "Purge")
    folder_id = make_folder(client, course_id, "Docs")
    add_material(client, "a.md", course_id, folder_id=folder_id)
    node_id = make_node(client, course_id, "Node")
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert assigned.status_code == 201

    deleted = client.delete(
        f"/api/v1/courses/{course_id}", params={"confirmed_backup": True}
    )
    assert deleted.status_code == 200


def test_organizer_counts_folder_members_as_assigned(
    db_session: Any, tmp_path: Path
) -> None:
    from app.domain.models import MaterialFolderLink, Profile

    profile = Profile(name="p")
    db_session.add(profile)
    db_session.flush()
    course = Course(profile_id=profile.id, title="Organizer")
    db_session.add(course)
    db_session.flush()
    root = TreeNode(
        course_id=course.id,
        parent_id=None,
        title="Organizer",
        order_idx=0,
        depth=0,
        path="/",
        sort_path="/",
        is_root=True,
    )
    db_session.add(root)
    db_session.flush()
    root.path = f"/{root.id}/"
    node = TreeNode(
        course_id=course.id,
        parent_id=root.id,
        title="Node",
        order_idx=1000,
        depth=1,
        path=f"/{root.id}/{0}/",
        sort_path="/0000010/",
    )
    db_session.add(node)
    db_session.flush()
    node.path = f"/{root.id}/{node.id}/"
    folder = MaterialFolder(
        profile_id=profile.id,
        course_id=course.id,
        parent_id=None,
        name="Docs",
        path="Docs",
    )
    db_session.add(folder)
    db_session.flush()
    material = Material(
        profile_id=profile.id,
        course_id=course.id,
        folder_id=folder.id,
        kind="md",
        title="doc",
        filename="doc.md",
        status="ready",
    )
    db_session.add(material)
    db_session.add(
        MaterialFolderLink(course_id=course.id, node_id=node.id, folder_id=folder.id)
    )
    other = Material(
        profile_id=profile.id,
        course_id=course.id,
        kind="md",
        title="unassigned",
        filename="unassigned.md",
        status="ready",
    )
    db_session.add(other)
    db_session.flush()
    db_session.commit()

    _node, _children, unassigned, _concepts = organizer.node_context(
        db_session, node.id
    )
    assert [entry["title"] for entry in unassigned] == ["unassigned"]


def test_direct_material_link_still_works_alongside_folder(
    client: TestClient,
) -> None:
    course_id = make_course(client, "Mixed")
    folder_id = make_folder(client, course_id, "Docs")
    inside = add_material(client, "inside.md", course_id, folder_id=folder_id)
    outside = add_material(client, "outside.md", course_id)
    node_id = make_node(client, course_id, "Node")
    direct = client.post(
        f"/api/v1/nodes/{node_id}/materials", json={"material_id": outside}
    )
    assert direct.status_code == 201
    assigned = client.post(
        f"/api/v1/nodes/{node_id}/folder-materials", json={"folder_id": folder_id}
    )
    assert assigned.status_code == 201

    workspace = workspace_of(client, node_id)
    assert [entry["material_id"] for entry in workspace["materials"]] == [outside]
    assert workspace["materials"][0]["via_folder_id"] is None
    assert workspace["folder_material_ids"] == [inside]

    removed = client.delete(f"/api/v1/nodes/{node_id}/materials/{outside}")
    assert removed.status_code == 204
    workspace = workspace_of(client, node_id)
    assert workspace["materials"] == []
    assert workspace["folder_material_ids"] == [inside]
