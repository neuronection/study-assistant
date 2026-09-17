import time
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app


class Scripted(LLMGateway):
    def __init__(self) -> None:
        super().__init__(session_factory=None)

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="m",
            label="m",
            caps=["text", "vision"],
            api_key=None,
        )

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        return "ok"


class NoAI:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return None

    def describe(
        self,
        title: str,
    ) -> str:
        return title


def make_client() -> TestClient:
    import tempfile
    from pathlib import Path

    data_dir = Path(tempfile.mkdtemp(prefix="ca-trash-materials-"))
    app = create_app(
        Settings(data_dir=data_dir, log_level="WARNING"),
        gateway=Scripted(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def flatten_tree(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in nodes:
        out.append(entry)
        out.extend(flatten_tree(entry["children"]))
    return out


def make_course(client: TestClient, title: str) -> int:
    return int(client.post("/api/v1/courses", json={"title": title}).json()["id"])


def wait_ready(client: TestClient, material_id: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = client.get(f"/api/v1/materials/{material_id}").json()["material"][
            "status"
        ]
        if status == "ready":
            return
        time.sleep(0.05)
    raise AssertionError("material never became ready")


def upload(client: TestClient, course_id: int, name: str, body: bytes) -> int:
    uploaded = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (name, body, "text/plain")},
    ).json()
    material_id = int(uploaded["material"]["id"])
    wait_ready(client, material_id)
    return material_id


def wait_for_search_hit(client: TestClient, term: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        results = client.get("/api/v1/search", params={"q": term}).json()
        hits = results.get("hits", results) if isinstance(results, dict) else results
        if hits:
            return
        time.sleep(0.05)
    raise AssertionError(f"search never surfaced {term!r}")


def test_material_delete_and_restore_round_trip() -> None:
    client = make_client()
    with client:
        course = make_course(client, "Calc")
        material_id = upload(client, course, "derivatives.txt", b"chain rule notes")
        root = client.get(f"/api/v1/courses/{course}/tree").json()[0]
        node = client.post(
            f"/api/v1/courses/{course}/nodes",
            json={"course_id": course, "parent_id": root["id"], "title": "Ch1"},
        ).json()
        assigned = client.post(
            f"/api/v1/nodes/{node['id']}/materials",
            json={"material_id": material_id},
        )
        assert assigned.status_code == 201, assigned.text

        deleted = client.delete(f"/api/v1/materials/{material_id}")
        assert deleted.status_code == 200, deleted.text
        item_id = deleted.json()["deleted_item_id"]
        assert client.get(f"/api/v1/materials/{material_id}").status_code == 404

        trash_list = client.get("/api/v1/deleted-items").json()
        entry = next(item for item in trash_list if item["id"] == item_id)
        assert entry["entity_type"] == "material"
        assert entry["title"] == "derivatives"

        restored = client.post(f"/api/v1/deleted-items/{item_id}/restore")
        assert restored.status_code == 200, restored.text
        body = restored.json()
        assert body["status"] == "restored"
        assert body["entity_type"] == "material"
        new_id = body["material_id"]
        assert new_id is not None

        detail = client.get(f"/api/v1/materials/{new_id}")
        assert detail.status_code == 200, detail.text
        links = client.get(f"/api/v1/materials/{new_id}/links").json()
        assert links, "node placement should be restored"
        wait_for_search_hit(client, "chain rule")


def test_material_restore_dedupes_when_reuploaded(client: TestClient) -> None:
    client = make_client()
    with client:
        course = client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        material_id = upload(client, course, "dup.txt", b"identical body")
        client.delete(f"/api/v1/materials/{material_id}")
        trash_list = client.get("/api/v1/deleted-items").json()
        item_id = next(
            item["id"]
            for item in trash_list
            if item["entity_type"] == "material"
        )

        reuploaded = upload(client, course, "dup.txt", b"identical body")

        restored = client.post(f"/api/v1/deleted-items/{item_id}/restore")
        assert restored.status_code == 200, restored.text
        body = restored.json()
        assert body["status"] in ("merged", "deduped")
        assert body["material_id"] == reuploaded

        listing = client.get(
            "/api/v1/materials", params={"course_id": course}
        ).json()
        materials = [
            entry for entry in listing if entry["title"].startswith("dup")
        ]
        assert len(materials) == 1


def test_node_subtree_delete_and_restore() -> None:
    client = make_client()
    with client:
        course = client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        root = client.get(f"/api/v1/courses/{course}/tree").json()[0]
        node_a = client.post(
            f"/api/v1/courses/{course}/nodes",
            json={"course_id": course, "parent_id": root["id"], "title": "A"},
        ).json()
        node_b = client.post(
            f"/api/v1/courses/{course}/nodes",
            json={"course_id": course, "parent_id": node_a["id"], "title": "B"},
        ).json()
        material_id = upload(client, course, "linked.txt", b"linked notes")
        assigned = client.post(
            f"/api/v1/nodes/{node_b['id']}/materials",
            json={"material_id": material_id},
        )
        assert assigned.status_code == 201, assigned.text

        deleted = client.delete(f"/api/v1/nodes/{node_a['id']}")
        assert deleted.status_code == 200, deleted.text
        item_id = deleted.json()["deleted_item_id"]

        tree = flatten_tree(client.get(f"/api/v1/courses/{course}/tree").json())
        remaining = {entry["id"] for entry in tree}
        assert node_a["id"] not in remaining
        assert node_b["id"] not in remaining

        restored = client.post(f"/api/v1/deleted-items/{item_id}/restore")
        assert restored.status_code == 200, restored.text
        body = restored.json()
        assert body["entity_type"] == "node"
        new_root = body["node_id"]
        assert new_root is not None

        tree = flatten_tree(client.get(f"/api/v1/courses/{course}/tree").json())
        by_id = {entry["id"]: entry for entry in tree}
        assert new_root in by_id
        assert by_id[new_root]["title"] == "A"
        children = by_id[new_root]["children"]
        assert [child["title"] for child in children] == ["B"]

        links = client.get(f"/api/v1/materials/{material_id}/links").json()
        link_node_ids = {entry["node_id"] for entry in links}
        assert link_node_ids & {child["id"] for child in children}


def test_node_restore_skips_links_whose_material_is_gone() -> None:
    client = make_client()
    with client:
        course = client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        root = client.get(f"/api/v1/courses/{course}/tree").json()[0]
        node_a = client.post(
            f"/api/v1/courses/{course}/nodes",
            json={"course_id": course, "parent_id": root["id"], "title": "A"},
        ).json()
        node_b = client.post(
            f"/api/v1/courses/{course}/nodes",
            json={"course_id": course, "parent_id": node_a["id"], "title": "B"},
        ).json()
        material_id = upload(client, course, "gone.txt", b"soon gone")
        client.post(
            f"/api/v1/nodes/{node_b['id']}/materials",
            json={"material_id": material_id},
        )

        deleted_node = client.delete(f"/api/v1/nodes/{node_a['id']}")
        item_id = deleted_node.json()["deleted_item_id"]

        deleted_material = client.delete(f"/api/v1/materials/{material_id}")
        material_item = deleted_material.json()["deleted_item_id"]
        purged = client.delete(f"/api/v1/deleted-items/{material_item}")
        assert purged.status_code == 204

        restored = client.post(f"/api/v1/deleted-items/{item_id}/restore")
        assert restored.status_code == 200, restored.text
        body = restored.json()
        assert body["node_id"] is not None
        assert body["detail"]["skipped_links"] >= 1


def test_node_restore_respects_depth_cap(client: TestClient) -> None:
    client = make_client()
    assert isinstance(client.app, FastAPI)
    with client:
        course = client.post("/api/v1/courses", json={"title": "Deep"}).json()["id"]
        root = client.get(f"/api/v1/courses/{course}/tree").json()[0]
        node_a = client.post(
            f"/api/v1/courses/{course}/nodes",
            json={"course_id": course, "parent_id": root["id"], "title": "A"},
        ).json()
        client.post(
            f"/api/v1/courses/{course}/nodes",
            json={"course_id": course, "parent_id": node_a["id"], "title": "B"},
        ).json()

        deleted = client.delete(f"/api/v1/nodes/{node_a['id']}")
        item_id = deleted.json()["deleted_item_id"]

        deep = root["id"]
        parent = root["id"]
        for level in range(3):
            created = client.post(
                f"/api/v1/courses/{course}/nodes",
                json={"course_id": course, "parent_id": parent, "title": f"D{level}"},
            ).json()
            parent = created["id"]
            deep = created["id"]

        from app.services.knowledge.tree import TreeService

        item = None
        factory = client.app.state.session_factory
        with factory() as session:
            from app.domain.models import DeletedItem

            item = session.get(DeletedItem, item_id)
            assert item is not None
            payload = dict(item.payload)
            payload["root_parent_id"] = deep
            tree = TreeService(session)
            result = tree.restore_subtree_from_trash(payload)
            session.commit()
        assert result["skipped_deep"] >= 1
        tree_after = flatten_tree(
            client.get(f"/api/v1/courses/{course}/tree").json()
        )
        titles = [entry["title"] for entry in tree_after]
        assert "A" in titles
        assert titles.count("B") == 0
