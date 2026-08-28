import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture
from sqlalchemy import select
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, add_material, make_course

from app.core.config import Settings
from app.domain.models import Material, MaterialLink
from app.main import create_app

LONG_DOC = (
    "# Chain rule study guide\n\n"
    "The chain rule differentiates composite functions. If $f$ and $g$ are "
    "differentiable, then $(f \\circ g)'(x) = f'(g(x)) \\cdot g'(x)$.\n\n"
    "## Worked example\n\nDifferentiate $\\sin(x^2)$: set $u = x^2$, so "
    "$du = 2x\\,dx$, giving $2x\\cos(x^2)$.\n\n"
    "## Common mistakes\n\n- Forgetting the inner derivative.\n"
    "- Mixing up the order of multiplication.\n\n"
    "Practice each pattern until it is automatic; the outer function stays "
    "unchanged while the inner function is differentiated."
)


def wait_ready(client: TestClient, material_id: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        material = client.get(f"/api/v1/materials/{material_id}").json()
        if material.get("material", {}).get("status") == "ready":
            return
        time.sleep(0.05)
    raise AssertionError("composed material never became ready")


@fixture
def gateway() -> ScriptedGateway:
    return ScriptedGateway([])


@fixture
def client(
    tmp_path: Path, gateway: ScriptedGateway
) -> Iterator[tuple[TestClient, ScriptedGateway, FastAPI]]:
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=gateway,
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, gateway, app


def make_node(client: TestClient, course_id: int, title: str) -> int:
    tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
    root_id = int(tree[0]["id"])
    created = client.post(
        f"/api/v1/courses/{course_id}/nodes",
        json={"course_id": course_id, "parent_id": root_id, "title": title},
    )
    return int(created.json()["id"])


def test_compose_creates_indexed_assigned_material(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "src.txt", "chain rule source", course_id)
        node_id = make_node(test_client, course_id, "Ch3")
        linked = test_client.post(
            f"/api/v1/nodes/{node_id}/materials", json={"material_id": material_id}
        )
        assert linked.status_code < 400, linked.text
        gateway.responses.append(LONG_DOC)
        composed = test_client.post(
            "/api/v1/materials/compose",
            json={
                "course_id": course_id,
                "node_id": node_id,
                "kind": "study_guide",
                "title": "Chain rule guide",
            },
        )
        assert composed.status_code == 200, composed.text
        body = composed.json()
        new_id = body["material"]["id"]
        assert body["material"]["provenance"]["source"] == "ai-composed"
        assert body["material"]["provenance"]["kind"] == "study_guide"
        assert body["job_id"] is not None
        wait_ready(test_client, new_id)
        stored = _app.state.session_factory()
        link = stored.scalars(
            select(MaterialLink).where(
                MaterialLink.node_id == node_id, MaterialLink.material_id == new_id
            )
        ).first()
        stored.close()
        assert link is not None
        assert "AI-composed" in (link.rationale or "")
        prompt = "\n".join(str(message.content) for message in gateway.calls[0])
        assert "Compose a study guide" in prompt
        assert f"[M{material_id}]" in prompt


def test_compose_excludes_prior_compositions_from_context(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "src.txt", "real source material", course_id)
        gateway.responses.append(LONG_DOC)
        first = test_client.post(
            "/api/v1/materials/compose",
            json={"course_id": course_id, "kind": "summary_sheet", "title": "First"},
        )
        assert first.status_code == 200, first.text
        first_id = first.json()["material"]["id"]
        gateway.responses.append(LONG_DOC)
        second = test_client.post(
            "/api/v1/materials/compose",
            json={"course_id": course_id, "kind": "study_guide", "title": "Second"},
        )
        assert second.status_code == 200, second.text
        second_prompt = "\n".join(
            str(message.content) for message in gateway.calls[-1]
        )
        assert f"[M{first_id}]" not in second_prompt
        assert "First" not in second_prompt.split("Compose")[1].split("Title")[0]


def test_compose_validator_rejects_short_document(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "src.txt", "source", course_id)
        gateway.responses.append("too short")
        gateway.responses.append("still too short")
        gateway.responses.append("still too short")
        composed = test_client.post(
            "/api/v1/materials/compose",
            json={"course_id": course_id, "kind": "study_guide", "title": "X"},
        )
        assert composed.status_code == 422, composed.text
        assert "too short" in composed.json()["detail"]
        stored = _app.state.session_factory()
        count = len(
            stored.scalars(
                select(Material).where(Material.provenance.is_not(None))
            ).all()
        )
        stored.close()
        assert count == 0


def test_compose_rejects_unknown_kind(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        composed = test_client.post(
            "/api/v1/materials/compose",
            json={"course_id": course_id, "kind": "detective_novel", "title": "X"},
        )
        assert composed.status_code == 422
        assert "detective_novel" in composed.json()["detail"]


MINDMAP_DOC = (
    "# Limits\n\n"
    "## Definition\n\n"
    "- Epsilon-delta definition\n"
    "- One-sided limits\n"
    "- Infinite limits\n\n"
    "## Limit laws\n\n"
    "- Sum and difference laws\n"
    "- Product and quotient laws\n"
    "- Squeeze theorem\n\n"
    "## Techniques\n\n"
    "- Factoring and cancellation\n"
    "- Rationalizing numerators\n"
    "- L'Hopital's rule\n\n"
    "## Continuity\n\n"
    "- Intermediate value theorem\n"
    "- Extreme value theorem\n\n"
    "## Key idea\n\n"
    "- A limit captures where a function is heading as its input approaches a point\n"
    "- The epsilon-delta definition makes the heading precise\n"
    "- Limit laws compute new limits from known ones without returning to the definition"
)


def test_compose_mindmap_kind(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "src.txt", "limits content", course_id)
        gateway.responses.append(MINDMAP_DOC)
        composed = test_client.post(
            "/api/v1/materials/compose",
            json={"course_id": course_id, "kind": "mindmap", "title": "Limits map"},
        )
        assert composed.status_code == 200, composed.text
        body = composed.json()
        assert body["material"]["provenance"]["source"] == "ai-composed"
        assert body["material"]["provenance"]["kind"] == "mindmap"
        prompt = "\n".join(str(message.content) for message in gateway.calls[-1])
        assert "mindmap" in prompt.lower()
        assert "markdown outline" in prompt.lower()


def test_mindmap_edit_rewrites_the_outline(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "src.txt", "limits content", course_id)
        gateway.responses.append("# Limits\n\n- Expanded\n  - detail\n")
        edited = test_client.post(
            f"/api/v1/materials/{material_id}/mindmap-edit",
            json={"mode": "expand", "focus_node": "Definition"},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["markdown"].startswith("# ")
        prompt = "\n".join(str(message.content) for message in gateway.calls[-1])
        assert "Current mindmap" in prompt
        assert 'Focus the edit on the node "Definition"' in prompt


def test_mindmap_edit_rejects_missing_material(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        edited = test_client.post(
            "/api/v1/materials/9999/mindmap-edit", json={"mode": "expand"}
        )
        assert edited.status_code == 404


def test_extraction_version_history_roundtrip(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        material_id = add_material(test_client, "src.txt", "limits content", course_id)
        before = test_client.get(f"/api/v1/materials/{material_id}/extractions").json()
        assert len(before) >= 1
        latest_version = before[0]["version"]

        edited = test_client.patch(
            f"/api/v1/materials/{material_id}/extraction",
            json={"markdown": "# edited outline\n\n- changed\n"},
        )
        assert edited.status_code == 200, edited.text
        edited_version = edited.json()["version"]

        after = test_client.get(f"/api/v1/materials/{material_id}/extractions").json()
        assert after[0]["version"] == edited_version
        assert after[0]["version"] > latest_version

        fetched = test_client.get(
            f"/api/v1/materials/{material_id}/extractions/{latest_version}"
        )
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["markdown"] != "# edited outline\n\n- changed\n"

        missing = test_client.get(
            f"/api/v1/materials/{material_id}/extractions/99999"
        )
        assert missing.status_code == 404


COMPOSE_PROPOSAL = (
    "```proposal\n"
    + json.dumps(
        {
            "action": "compose_material",
            "kind": "summary_sheet",
            "title": "Limits cheat sheet",
            "instructions": "compact formulas only",
        }
    )
    + "\n```"
)


def test_compose_via_chat_proposal(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "src.txt", "limits content", course_id)
        gateway.responses.append(f"Here is an overview [1].\n\n{COMPOSE_PROPOSAL}")
        gateway.responses.append(LONG_DOC)
        session = test_client.post(
            "/api/v1/chat/sessions", json={"course_id": course_id}
        ).json()
        test_client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "give me a cheat sheet"},
        )
        deadline = time.monotonic() + 5
        proposal: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            messages = test_client.get(
                f"/api/v1/chat/sessions/{session['id']}/messages"
            ).json()
            if messages and messages[-1]["role"] == "assistant":
                proposals = messages[-1]["proposals"]
                if proposals:
                    proposal = proposals[0]
                    break
            time.sleep(0.05)
        assert proposal is not None
        assert proposal["action"] == "compose_material"
        approved = test_client.post(f"/api/v1/chat/proposals/{proposal['id']}/approve")
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["status"] == "executed"
        assert body["result"]["material_id"]
