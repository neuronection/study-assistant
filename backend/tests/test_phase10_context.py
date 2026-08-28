import json
import sqlite3
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pytest import fixture
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway

from app.ai.gateway import Message, ResolvedModel
from app.core.config import Settings
from app.main import create_app


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


@fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=ScriptedGateway(["{}"]),
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client


class ProbeGateway(ScriptedGateway):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(responses)
        self.calls: list[list[Message]] = []

    def resolve(
        self,
        task: str,
        course_id: int | None = None,
    ) -> ResolvedModel:
        return ResolvedModel(
            provider_id=1,
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="probe",
            label="probe",
            caps=["text"],
            api_key=None,
        )

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: int | None = None,
    ) -> str:
        self.calls.append(messages)
        return super().generate(task, messages, model)


QUIZ_JSON = json.dumps(
    {
        "questions": [
            {
                "type": "truefalse",
                "stem_md": "probe",
                "answer": {"value": True},
                "explanation_md": "ok",
                "concepts": ["probe"],
                "skill": "conceptual",
                "bloom": "remember",
                "difficulty": 1,
                "expected_time_sec": 30,
            }
        ]
    }
)

EXERCISE_JSON = json.dumps(
    {
        "title": "probe",
        "context_md": "probe",
        "difficulty": 2,
        "steps": [
            {
                "prompt_md": "compute",
                "expected_kind": "numeric",
                "expected_value": "3",
            }
        ],
    }
)


def make_gateway(responses: list[str]) -> ProbeGateway:
    return ProbeGateway(responses)


def upload_txt(client: TestClient, filename: str, course_id: int, content: bytes) -> int:
    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (filename, content, "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    material_id = int(upload.json()["material"]["id"])
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        == "ready"
    )
    return material_id


def root_node(client: TestClient, course_id: int) -> int:
    return int(client.get(f"/api/v1/courses/{course_id}/tree").json()[0]["id"])


def make_node(client: TestClient, course_id: int, parent_id: int, title: str) -> int:
    created = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": parent_id, "title": title},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def link_material(client: TestClient, node_id: int, material_id: int) -> None:
    linked = client.post(
        f"/api/v1/nodes/{node_id}/materials", json={"material_id": material_id}
    )
    assert linked.status_code == 201, linked.text


def make_note(
    client: TestClient, course_id: int, node_id: int, title: str, body_md: str
) -> int:
    created = client.post(
        "/api/v1/notes",
        json={
            "title": title,
            "body_md": body_md,
            "course_id": course_id,
            "node_id": node_id,
        },
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def test_quiz_generate_provider_error_maps_to_502(tmp_path: Path) -> None:
    from app.ai.gateway import ProviderError as GatewayProviderError

    class FailingGateway(ScriptedGateway):
        def generate(
            self,
            task: str,
            messages: list[Message],
            model: Any = None,
            course_id: int | None = None,
        ) -> str:
            raise GatewayProviderError(
                ResolvedModel(
                    provider_id=1,
                    provider_type="openai_compatible",
                    base_url="https://api.openai.com/v1",
                    external_id="gpt-test",
                    label="gpt-test",
                    caps=["text"],
                    api_key="bad",
                ),
                "HTTP 401 Incorrect API key provided",
            )

    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=FailingGateway([]),
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
        generated = client.post(
            "/api/v1/quiz/generate",
            json={"course_id": course_id, "count": 1},
        )
        assert generated.status_code == 502, generated.text
        assert "gpt-test" in generated.json()["detail"]
        assert "check the API key" in generated.json()["detail"]


def test_ai_tools_catalog(client: TestClient) -> None:
    body = client.get("/api/v1/ai/tools")
    assert body.status_code == 200, body.text
    tools = body.json()["tools"]
    assert [tool["name"] for tool in tools] == [
        "CALC",
        "SYMPY",
        "READ",
        "STATE",
        "PLOT",
        "COURSES",
        "NODE_OVERVIEW",
        "NODE_QUIZZES",
        "NODE_EXERCISES",
        "NODE_NOTES",
    ]
    calc = tools[0]
    assert calc["arguments"][0]["name"] == "expression"
    assert calc["arguments"][0]["required"] is True
    assert calc["response"]
    assert calc["scope"]

    mcp = client.get("/api/v1/ai/mcp")
    assert mcp.status_code == 200, mcp.text
    mcp_body = mcp.json()
    assert mcp_body["command"] == "python -m studyassistant mcp"
    assert [tool["name"] for tool in mcp_body["tools"]] == [
        "list_courses",
        "get_node_overview",
        "get_node_materials",
        "get_node_concepts",
        "get_node_exercises",
        "get_node_quizzes",
        "get_node_notes",
        "get_node_context",
    ]
    materials = mcp_body["tools"][2]
    by_name = {argument["name"]: argument for argument in materials["arguments"]}
    assert by_name["node_id"]["required"] is True
    assert by_name["node_id"]["type"] == "integer"
    assert by_name["include_children"]["required"] is False
    assert by_name["profile_id"]["required"] is False
    node_context = mcp_body["tools"][7]
    context_args = {argument["name"]: argument for argument in node_context["arguments"]}
    assert context_args["node_id"]["required"] is True
    assert context_args["scope"]["required"] is False
    assert context_args["max_chunks"]["type"] == "integer"


def test_preview_scope_node_vs_subtree(client: TestClient) -> None:
    course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
    root = root_node(client, course_id)
    chapter = make_node(client, course_id, root, "Ch")
    section = make_node(client, course_id, chapter, "Sec")

    direct = upload_txt(client, "direct.txt", course_id, b"antiderivative direct note")
    nested = upload_txt(client, "nested.txt", course_id, b"antiderivative nested note")
    link_material(client, chapter, direct)
    link_material(client, section, nested)

    node_scope = client.post(
        "/api/v1/ai/context/preview",
        json={"course_id": course_id, "node_id": chapter, "scope": "node"},
    )
    assert node_scope.status_code == 200, node_scope.text
    titles = [entry["title"] for entry in node_scope.json()["stats"]["materials"]]
    assert titles == ["direct"]

    subtree_scope = client.post(
        "/api/v1/ai/context/preview",
        json={"course_id": course_id, "node_id": chapter, "scope": "subtree"},
    )
    titles = [entry["title"] for entry in subtree_scope.json()["stats"]["materials"]]
    assert titles == ["direct", "nested"]

    course_scope = client.post(
        "/api/v1/ai/context/preview",
        json={"course_id": course_id, "node_id": root, "scope": "subtree"},
    )
    titles = [entry["title"] for entry in course_scope.json()["stats"]["materials"]]
    assert titles == ["direct", "nested"]


def test_preview_include_exclude_materials(client: TestClient) -> None:
    course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
    root = root_node(client, course_id)
    chapter = make_node(client, course_id, root, "Ch")

    linked = upload_txt(client, "linked.txt", course_id, b"antiderivative linked note")
    extra = upload_txt(client, "extra.txt", course_id, b"antiderivative extra note")
    link_material(client, chapter, linked)

    excluded = client.post(
        "/api/v1/ai/context/preview",
        json={
            "course_id": course_id,
            "node_id": chapter,
            "exclude_material_ids": [linked],
        },
    )
    titles = [entry["title"] for entry in excluded.json()["stats"]["materials"]]
    assert titles == []

    included = client.post(
        "/api/v1/ai/context/preview",
        json={
            "course_id": course_id,
            "node_id": chapter,
            "include_material_ids": [extra],
        },
    )
    titles = [entry["title"] for entry in included.json()["stats"]["materials"]]
    assert titles == ["linked", "extra"]

    foreign_course = int(client.post("/api/v1/courses", json={"title": "D"}).json()["id"])
    foreign = upload_txt(client, "foreign.txt", foreign_course, b"antiderivative foreign")
    cross = client.post(
        "/api/v1/ai/context/preview",
        json={
            "course_id": course_id,
            "node_id": chapter,
            "include_material_ids": [foreign],
        },
    )
    assert cross.status_code == 422


def test_preview_notes_concepts_and_hints(client: TestClient) -> None:
    course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
    root = root_node(client, course_id)
    chapter = make_node(client, course_id, root, "Ch")
    note_id = make_note(client, course_id, chapter, "My note", "u-substitution recap")

    committed = client.post(
        f"/api/v1/courses/{course_id}/concepts/commit",
        json={
            "concepts": [
                {"name": "chain rule", "description": "composite derivatives", "aliases": []}
            ],
            "links": [],
            "nodes": [],
        },
    )
    assert committed.status_code == 200
    concept_id = int(
        client.get(f"/api/v1/courses/{course_id}/concepts").json()["concepts"][0]["id"]
    )

    patched_root = client.patch(f"/api/v1/nodes/{root}", json={"ai_hint": "use greek letters"})
    assert patched_root.status_code == 200, patched_root.text
    patched_chapter = client.patch(
        f"/api/v1/nodes/{chapter}", json={"ai_hint": "focus on u-substitution"}
    )
    assert patched_chapter.status_code == 200

    preview = client.post(
        "/api/v1/ai/context/preview",
        json={
            "course_id": course_id,
            "node_id": chapter,
            "note_ids": [note_id],
            "concept_ids": [concept_id],
            "context_hint": "prefer numeric answers",
        },
    )
    assert preview.status_code == 200, preview.text
    stats = preview.json()["stats"]
    rendered = preview.json()["rendered"]
    assert [entry["title"] for entry in stats["notes"]] == ["My note"]
    assert [entry["name"] for entry in stats["concepts"]] == ["chain rule"]
    assert stats["hints"] == 3
    assert "u-substitution recap" in rendered
    assert "composite derivatives" in rendered
    assert "[Course guidance] use greek letters" in rendered
    assert "[Node 'Ch'] focus on u-substitution" in rendered
    assert "[For this request] prefer numeric answers" in rendered
    assert "Study scope: C > Ch" in rendered


def test_root_hint_only_patch_and_tree_payload(client: TestClient) -> None:
    course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
    root = root_node(client, course_id)
    refused = client.patch(f"/api/v1/nodes/{root}", json={"title": "new title"})
    assert refused.status_code == 422
    patched = client.patch(f"/api/v1/nodes/{root}", json={"ai_hint": "course hint"})
    assert patched.status_code == 200
    assert patched.json()["ai_hint"] == "course hint"

    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    assert tree[0]["ai_hint"] == "course hint"
    workspace = client.get(f"/api/v1/nodes/{root}/workspace").json()
    assert workspace["node"]["ai_hint"] == "course hint"

    cleared = client.patch(f"/api/v1/nodes/{root}", json={"ai_hint": ""})
    assert cleared.status_code == 200
    assert cleared.json()["ai_hint"] is None


def test_quiz_generate_receives_context(tmp_path: Path) -> None:
    gateway = make_gateway([QUIZ_JSON])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
        root = root_node(client, course_id)
        chapter = make_node(client, course_id, root, "Ch")
        kept = upload_txt(
            client, "kept.txt", course_id, b"antiderivative of x squared material"
        )
        dropped = upload_txt(
            client, "dropped.txt", course_id, b"antiderivative dice game material"
        )
        link_material(client, chapter, kept)
        link_material(client, chapter, dropped)
        note_id = make_note(client, course_id, chapter, "Note", "remember plus C")
        client.patch(f"/api/v1/nodes/{chapter}", json={"ai_hint": "focus hard"})

        generated = client.post(
            "/api/v1/quiz/generate",
            json={
                "course_id": course_id,
                "node_id": chapter,
                "count": 1,
                "topic": "antiderivative",
                "exclude_material_ids": [dropped],
                "note_ids": [note_id],
                "context_hint": "one-time instruction",
            },
        )
        assert generated.status_code == 201, generated.text

    prompt = " ".join(
        message.content
        for call in gateway.calls
        for message in call
        if isinstance(message.content, str)
    )
    assert "(kept)" in prompt
    assert "(dropped)" not in prompt
    assert "remember plus C" in prompt
    assert "[Node 'Ch'] focus hard" in prompt
    assert "[For this request] one-time instruction" in prompt


def test_quiz_generate_cross_course_note_rejected(tmp_path: Path) -> None:
    gateway = make_gateway([QUIZ_JSON])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        first = int(client.post("/api/v1/courses", json={"title": "A"}).json()["id"])
        second = int(client.post("/api/v1/courses", json={"title": "B"}).json()["id"])
        root_b = root_node(client, second)
        note_id = make_note(client, second, root_b, "foreign", "content")
        generated = client.post(
            "/api/v1/quiz/generate",
            json={
                "course_id": first,
                "count": 1,
                "note_ids": [note_id],
            },
        )
        assert generated.status_code == 422, generated.text


def test_exercise_generate_receives_notes(tmp_path: Path) -> None:
    gateway = make_gateway([EXERCISE_JSON])
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
        root = root_node(client, course_id)
        chapter = make_node(client, course_id, root, "Ch")
        note_id = make_note(client, course_id, chapter, "Hint note", "integration by parts")
        generated = client.post(
            "/api/v1/exercises/generate",
            json={
                "course_id": course_id,
                "node_id": chapter,
                "note_ids": [note_id],
                "context_hint": "make it gentle",
            },
        )
        assert generated.status_code == 201, generated.text

    prompt = " ".join(
        message.content
        for call in gateway.calls
        for message in call
        if isinstance(message.content, str)
    )
    assert "integration by parts" in prompt
    assert "[For this request] make it gentle" in prompt


def test_hybrid_retrieval_uses_vector_hits(tmp_path: Path, monkeypatch: Any) -> None:
    from app.storage import vectors as vectors_module

    gateway = make_gateway([])
    embedder = _FakeVectorEmbedder()
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=embedder,  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        course_id = int(client.post("/api/v1/courses", json={"title": "C"}).json()["id"])
        root = root_node(client, course_id)
        chapter = make_node(client, course_id, root, "Ch")
        target = upload_txt(client, "target.txt", course_id, b"obscure syllabus content")
        link_material(client, chapter, target)

        raw = sqlite3.connect(tmp_path / "app.db")
        chunk_row = raw.execute(
            "SELECT c.id FROM chunks c JOIN extractions e ON e.id = c.extraction_id "
            "WHERE e.material_id = ? LIMIT 1",
            (target,),
        ).fetchone()
        assert chunk_row is not None
        chunk_id = int(chunk_row[0])
        raw.close()

        monkeypatch.setattr(
            vectors_module, "search", lambda session, qv, limit=24: [(chunk_id, 0.01)]
        )
        preview = client.post(
            "/api/v1/ai/context/preview",
            json={
                "course_id": course_id,
                "node_id": chapter,
                "query": "zzzqqq unmatched",
            },
        )
        assert preview.status_code == 200, preview.text
        chunk_titles = [entry["title"] for entry in preview.json()["stats"]["chunks"]]
        assert "target" in chunk_titles


class _FakeVectorEmbedder:
    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]]:
        return ("fake-embed", [[0.1, 0.2, 0.3]])
