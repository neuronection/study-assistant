import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.domain.models import Extraction, Material, MaterialFolder, MaterialLink


def make_node(client: TestClient, course_id: int, title: str) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    root_id = int(tree[0]["id"])
    response = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root_id, "title": title},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


def make_course(client: TestClient, title: str = "Derived") -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


def upload_text(
    client: TestClient, content: str, filename: str, course_id: int
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/materials/text",
        json={
            "course_id": course_id,
            "filename": filename,
            "content": content,
        },
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    wait_until(
        lambda: client.get(
            f"/api/v1/materials/{body['material']['id']}"
        ).json()["material"]["status"]
        == "ready"
    )
    return body


def create_folder(
    client: TestClient, name: str, course_id: int
) -> int:
    response = client.post(
        "/api/v1/folders",
        json={"name": name, "course_id": course_id},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def session_factory(client: TestClient) -> Any:
    return cast(Any, client.app).state.session_factory


def test_derive_creates_markdown_material_from_extraction(
    client: TestClient,
) -> None:
    course_id = make_course(client)
    source = upload_text(
        client, "chain rule notes $\\frac{dy}{dx}$", "scan.pdf.txt", course_id
    )
    source_id = source["material"]["id"]
    edited = client.patch(
        f"/api/v1/materials/{source_id}/extraction",
        json={"markdown": "## QA-fixed\n\n| a | b |\n| --- | --- |\n| 1 | 2 |"},
    )
    assert edited.status_code == 200, edited.text

    derived = client.post(f"/api/v1/materials/{source_id}/derive", json={})
    assert derived.status_code == 201, derived.text
    body = derived.json()
    derived_id = body["material"]["id"]
    assert derived_id != source_id
    assert body["material"]["kind"] == "md"
    assert body["material"]["title"] == "scan.pdf (extracted)"
    assert body["material"]["provenance"] == {
        "source": "derived",
        "from_material_id": source_id,
        "from_version": 2,
    }
    assert body["deduped"] is False
    assert body["job_id"] is not None

    wait_until(
        lambda: client.get(
            f"/api/v1/materials/{derived_id}"
        ).json()["material"]["status"]
        == "ready"
    )
    detail = client.get(f"/api/v1/materials/{derived_id}").json()
    assert detail["extraction"]["version"] == 1
    assert detail["extraction"]["extractor"] == "native"
    assert detail["extraction"]["markdown"] == (
        "## QA-fixed\n\n| a | b |\n| --- | --- |\n| 1 | 2 |"
    )

    factory = session_factory(client)
    with factory() as session:
        source_row = session.get(Material, source_id)
        derived_row = session.get(Material, derived_id)
        assert source_row is not None and derived_row is not None
        assert derived_row.blob_sha != source_row.blob_sha
        assert derived_row.folder_id is None

    search = client.get("/api/v1/search", params={"q": "QA-fixed"}).json()
    assert derived_id in [hit["material_id"] for hit in search["hits"]]


def test_derive_is_deduped_when_content_already_exists(client: TestClient) -> None:
    course_id = make_course(client)
    source = upload_text(client, "stable content", "dup.txt", course_id)
    source_id = source["material"]["id"]

    first = client.post(f"/api/v1/materials/{source_id}/derive", json={})
    assert first.status_code == 201
    assert first.json()["deduped"] is False

    second = client.post(f"/api/v1/materials/{source_id}/derive", json={})
    assert second.status_code == 201
    assert second.json()["deduped"] is True
    assert second.json()["material"]["id"] == first.json()["material"]["id"]
    assert second.json()["job_id"] is None


def test_derive_after_edit_creates_distinct_material(client: TestClient) -> None:
    course_id = make_course(client)
    source = upload_text(client, "v1 content", "evolve.txt", course_id)
    source_id = source["material"]["id"]

    first = client.post(f"/api/v1/materials/{source_id}/derive", json={})
    assert first.status_code == 201

    edited = client.patch(
        f"/api/v1/materials/{source_id}/extraction",
        json={"markdown": "v2 content with changes"},
    )
    assert edited.status_code == 200

    second = client.post(f"/api/v1/materials/{source_id}/derive", json={})
    assert second.status_code == 201
    assert second.json()["deduped"] is False
    assert second.json()["material"]["id"] != first.json()["material"]["id"]
    assert second.json()["material"]["title"] == "evolve (extracted 2)"


def test_derive_rejects_unknown_material(client: TestClient) -> None:
    response = client.post("/api/v1/materials/99999/derive", json={})
    assert response.status_code == 404


def test_derive_rejects_material_without_extraction(client: TestClient) -> None:
    course_id = make_course(client)
    factory = session_factory(client)
    with factory() as session:
        from app.domain.models import Profile

        profile = session.scalars(select(Profile)).first()
        assert profile is not None
        material = Material(
            profile_id=profile.id,
            course_id=course_id,
            kind="pdf",
            title="pending",
            filename="pending.pdf",
            status="pending",
        )
        session.add(material)
        session.commit()
        material_id = material.id

    response = client.post(f"/api/v1/materials/{material_id}/derive", json={})
    assert response.status_code == 422
    assert "no extraction" in response.json()["detail"]


def test_derive_inherits_virtual_folder_and_validates_explicit_target(
    client: TestClient,
) -> None:
    course_id = make_course(client)
    folder_id = create_folder(client, "Notes", course_id)
    source = upload_text(client, "filed content", "filed.txt", course_id)
    source_id = source["material"]["id"]
    moved = client.patch(
        f"/api/v1/materials/{source_id}/move", json={"folder_id": folder_id}
    )
    assert moved.status_code == 200

    inherited = client.post(f"/api/v1/materials/{source_id}/derive", json={})
    assert inherited.status_code == 201
    assert inherited.json()["material"]["folder_id"] == folder_id

    foreign = make_course(client, "Other")
    foreign_folder = create_folder(client, "Foreign", foreign)
    rejected = client.post(
        f"/api/v1/materials/{source_id}/derive",
        json={"folder_id": foreign_folder},
    )
    assert rejected.status_code == 422
    assert "different course" in rejected.json()["detail"]


def test_derive_copies_the_originals_node_links(client: TestClient) -> None:
    course_id = make_course(client)
    source = upload_text(client, "assigned content", "assigned.txt", course_id)
    source_id = source["material"]["id"]
    first_node = make_node(client, course_id, "One")
    second_node = make_node(client, course_id, "Two")
    for node_id in (first_node, second_node):
        assigned = client.post(
            f"/api/v1/nodes/{node_id}/materials", json={"material_id": source_id}
        )
        assert assigned.status_code == 201

    derived = client.post(f"/api/v1/materials/{source_id}/derive", json={})
    assert derived.status_code == 201
    derived_id = derived.json()["material"]["id"]

    factory = session_factory(client)
    with factory() as session:
        links = session.scalars(
            select(MaterialLink).where(MaterialLink.material_id == derived_id)
        ).all()
        assert sorted(link.node_id for link in links) == sorted(
            [first_node, second_node]
        )
        assert all(link.course_id == course_id for link in links)
        assert {link.rationale for link in links} == {
            "Derived from assigned"
        }


def test_derive_links_the_requested_node_without_duplicating_copied_links(
    client: TestClient,
) -> None:
    course_id = make_course(client)
    source = upload_text(client, "content", "scoped.txt", course_id)
    source_id = source["material"]["id"]
    linked_node = make_node(client, course_id, "Linked")
    other_node = make_node(client, course_id, "Other")
    assigned = client.post(
        f"/api/v1/nodes/{linked_node}/materials", json={"material_id": source_id}
    )
    assert assigned.status_code == 201

    same_node = client.post(
        f"/api/v1/materials/{source_id}/derive",
        json={"node_id": linked_node},
    )
    assert same_node.status_code == 201

    edited = client.patch(
        f"/api/v1/materials/{source_id}/extraction",
        json={"markdown": "changed content for a second derived file"},
    )
    assert edited.status_code == 200

    merged = client.post(
        f"/api/v1/materials/{source_id}/derive",
        json={"node_id": other_node},
    )
    assert merged.status_code == 201
    merged_id = merged.json()["material"]["id"]

    factory = session_factory(client)
    with factory() as session:
        same_node_links = sorted(
            link.node_id
            for link in session.scalars(
                select(MaterialLink).where(
                    MaterialLink.material_id == same_node.json()["material"]["id"]
                )
            )
        )
        assert same_node_links == [linked_node]
        merged_links = sorted(
            link.node_id
            for link in session.scalars(
                select(MaterialLink).where(MaterialLink.material_id == merged_id)
            )
        )
        assert merged_links == [linked_node, other_node]


def test_derive_rejects_foreign_node(client: TestClient) -> None:
    course_id = make_course(client)
    source = upload_text(client, "content", "home.txt", course_id)
    source_id = source["material"]["id"]
    other_course = make_course(client, "Other")
    foreign_node = make_node(client, other_course, "Foreign")

    response = client.post(
        f"/api/v1/materials/{source_id}/derive",
        json={"node_id": foreign_node},
    )
    assert response.status_code == 422
    assert "different course" in response.json()["detail"]


def test_derive_rejects_unknown_node(client: TestClient) -> None:
    course_id = make_course(client)
    source = upload_text(client, "content", "home.txt", course_id)
    source_id = source["material"]["id"]

    response = client.post(
        f"/api/v1/materials/{source_id}/derive",
        json={"node_id": 99999},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "node not found"


def test_derive_dedup_leaves_the_existing_materials_links_untouched(
    client: TestClient,
) -> None:
    course_id = make_course(client)
    source = upload_text(client, "stable content", "dup.txt", course_id)
    source_id = source["material"]["id"]
    node_id = make_node(client, course_id, "Node")

    first = client.post(
        f"/api/v1/materials/{source_id}/derive", json={"node_id": node_id}
    )
    assert first.status_code == 201
    existing_id = first.json()["material"]["id"]

    second = client.post(
        f"/api/v1/materials/{source_id}/derive", json={"node_id": node_id}
    )
    assert second.status_code == 201
    assert second.json()["deduped"] is True

    factory = session_factory(client)
    with factory() as session:
        links = session.scalars(
            select(MaterialLink).where(MaterialLink.material_id == existing_id)
        ).all()
        assert [link.node_id for link in links] == [node_id]


def test_derive_from_linked_folder_source_lands_at_course_root(
    client: TestClient, tmp_path: Path
) -> None:
    course_id = make_course(client)
    target = tmp_path / "linked"
    target.mkdir()
    (target / "linked.txt").write_text("linked content")
    source = client.post(
        "/api/v1/sources",
        json={"label": "link", "path": str(target), "course_id": course_id},
    )
    assert source.status_code == 201
    scan = client.post(f"/api/v1/sources/{source.json()['id']}/scan")
    assert scan.status_code == 200

    factory = session_factory(client)
    with factory() as session:
        folder = session.scalars(
            select(MaterialFolder).where(
                MaterialFolder.course_id == course_id,
                MaterialFolder.source_id.is_not(None),
            )
        ).first()
        assert folder is not None
        material = session.scalars(
            select(Material).where(Material.course_id == course_id)
        ).first()
        assert material is not None
        material_id = material.id
        assert material.folder_id is None

    wait_until(
        lambda: client.get(
            f"/api/v1/materials/{material_id}"
        ).json()["material"]["status"]
        == "ready"
    )

    derived = client.post(f"/api/v1/materials/{material_id}/derive", json={})
    assert derived.status_code == 201
    assert derived.json()["material"]["folder_id"] is None


def test_derive_sanitizes_path_separators_in_title(client: TestClient) -> None:
    course_id = make_course(client)
    source = upload_text(client, "content", "weird.txt", course_id)
    source_id = source["material"]["id"]
    renamed = client.patch(
        f"/api/v1/materials/{source_id}", json={"title": "a/b\\c"}
    )
    assert renamed.status_code == 200

    derived = client.post(f"/api/v1/materials/{source_id}/derive", json={})
    assert derived.status_code == 201
    assert derived.json()["material"]["title"] == "a-b-c (extracted)"


def test_derived_extraction_is_version_one_with_edited_by_user_unset(
    client: TestClient,
) -> None:
    course_id = make_course(client)
    source = upload_text(client, "content", "flags.txt", course_id)
    source_id = source["material"]["id"]

    derived = client.post(f"/api/v1/materials/{source_id}/derive", json={})
    assert derived.status_code == 201
    derived_id = derived.json()["material"]["id"]
    wait_until(
        lambda: client.get(
            f"/api/v1/materials/{derived_id}"
        ).json()["material"]["status"]
        == "ready"
    )

    factory = session_factory(client)
    with factory() as session:
        extraction = session.scalars(
            select(Extraction).where(Extraction.material_id == derived_id)
        ).first()
        assert extraction is not None
        assert extraction.edited_by_user is False
        assert extraction.version == 1
