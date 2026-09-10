
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.search import retrieve_chunks_hybrid


def test_preferences_round_trip(client: TestClient) -> None:
    assert client.get("/api/v1/profiles/preferences").json() == {
        "use_embeddings": True,
        "ocr_image_max_edge": 1568,
    }
    off = client.put(
        "/api/v1/profiles/preferences", json={"use_embeddings": False}
    )
    assert off.status_code == 200
    assert off.json() == {"use_embeddings": False, "ocr_image_max_edge": 1568}
    on = client.put("/api/v1/profiles/preferences", json={"use_embeddings": True})
    assert on.json() == {"use_embeddings": True, "ocr_image_max_edge": 1568}


def test_ocr_image_max_edge_preference_round_trip(client: TestClient) -> None:
    updated = client.put("/api/v1/profiles/preferences", json={"ocr_image_max_edge": 1024})
    assert updated.status_code == 200
    assert updated.json()["ocr_image_max_edge"] == 1024
    assert client.get("/api/v1/profiles/preferences").json()["ocr_image_max_edge"] == 1024

    disabled = client.put("/api/v1/profiles/preferences", json={"ocr_image_max_edge": 0})
    assert disabled.status_code == 200
    assert disabled.json()["ocr_image_max_edge"] == 0

    rejected = client.put("/api/v1/profiles/preferences", json={"ocr_image_max_edge": 999})
    assert rejected.status_code == 422
    assert client.get("/api/v1/profiles/preferences").json()["ocr_image_max_edge"] == 0


def test_chat_session_use_embeddings_round_trip(client: TestClient) -> None:
    created = client.post("/api/v1/chat/sessions", json={}).json()
    assert created["use_embeddings"] is None

    explicit = client.post(
        "/api/v1/chat/sessions", json={"use_embeddings": False}
    ).json()
    assert explicit["use_embeddings"] is False

    patched = client.patch(
        f"/api/v1/chat/sessions/{explicit['id']}", json={"use_embeddings": True}
    )
    assert patched.status_code == 200
    assert patched.json()["use_embeddings"] is True


def test_hybrid_retrieval_skips_embed_when_disabled(db_session: Session) -> None:
    calls: list[str] = []

    def embed(query: str) -> tuple[str, list[list[float]]] | None:
        calls.append(query)
        return None

    result = retrieve_chunks_hybrid(
        db_session, "hello world", embed, use_embeddings=False
    )
    assert result == []
    assert calls == []


def test_hybrid_retrieval_calls_embed_when_enabled(db_session: Session) -> None:
    calls: list[str] = []

    def embed(query: str) -> tuple[str, list[list[float]]] | None:
        calls.append(query)
        return None

    retrieve_chunks_hybrid(db_session, "hello world", embed, use_embeddings=True)
    assert calls  # the query was embedded


def test_chat_turn_uses_per_chat_override(db_session: Session) -> None:
    from app.domain.models import ChatSession, Profile

    profile = Profile(name="p")
    db_session.add(profile)
    db_session.flush()
    db_session.add(
        ChatSession(
            profile_id=profile.id, title="t", use_embeddings=False, public_id="x1"
        )
    )
    db_session.flush()

    from app.ai.gateway import LLMGateway
    from app.services.platform.chat import ChatService

    service = ChatService(db_session, LLMGateway(None), None)
    session = db_session.query(ChatSession).first()
    assert session is not None
    assert service._effective_use_embeddings(session) is False

    session.use_embeddings = None
    profile.preferences = {"use_embeddings": False}
    db_session.flush()
    assert service._effective_use_embeddings(session) is False

    profile.preferences = {"use_embeddings": True}
    db_session.flush()
    assert service._effective_use_embeddings(session) is True


def _make_chat_client(tmp_path: object, gateway: Any, embedder: Any) -> Any:
    import sys

    sys.path.insert(0, "tests")

    from fastapi.testclient import TestClient
    from test_chat_api import NoDescriber

    from app.core.config import Settings
    from app.main import create_app

    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),  # type: ignore[arg-type]
        gateway=gateway,
        embedder=embedder,
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def test_turn_persists_embedding_warning(tmp_path: object) -> None:
    import sys

    sys.path.insert(0, "tests")

    from test_chat_api import NoEmbedder, ScriptedGateway, add_material, wait_for_assistant

    gateway = ScriptedGateway(["The derivative is $2x$. [1]"])
    client = _make_chat_client(tmp_path, gateway, NoEmbedder())
    with client:
        course = client.post("/api/v1/courses", json={"title": "Calc"}).json()
        add_material(client, "rules.txt", "Power rule material.", course["id"])
        session = client.post(
            "/api/v1/chat/sessions", json={"course_id": course["id"]}
        ).json()
        client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages", json={"content": "hi"}
        )
        messages = wait_for_assistant(client, session["id"])
        assistant = messages[-1]
        assert assistant["warnings"]
        assert "Semantic search is on" in assistant["warnings"][0]


def test_turn_no_warning_when_embeddings_disabled(tmp_path: object) -> None:
    import sys

    sys.path.insert(0, "tests")

    from test_chat_api import NoEmbedder, ScriptedGateway, add_material, wait_for_assistant

    gateway = ScriptedGateway(["The answer is $2x$. [1]"])
    client = _make_chat_client(tmp_path, gateway, NoEmbedder())
    with client:
        client.put("/api/v1/profiles/preferences", json={"use_embeddings": False})
        course = client.post("/api/v1/courses", json={"title": "Calc"}).json()
        add_material(client, "rules.txt", "Power rule material.", course["id"])
        session = client.post(
            "/api/v1/chat/sessions", json={"course_id": course["id"]}
        ).json()
        client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages", json={"content": "hi"}
        )
        messages = wait_for_assistant(client, session["id"])
        assistant = messages[-1]
        assert assistant["warnings"] == []
