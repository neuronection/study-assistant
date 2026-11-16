from types import SimpleNamespace
from typing import Any, cast

from fastapi.testclient import TestClient

from app.ai.gateway import TaskUnassigned
from app.domain.models import Artifact, Material
from app.jobs.payloads import ArtifactRenderPayload
from app.services.artifacts.render import make_artifact_render_handler


class NoTtsGateway:
    def speak(self, *args: Any, **kwargs: Any) -> Any:
        raise TaskUnassigned("tts")


def make_course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"title": "Narration"})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_narrate_creates_a_pending_artifact_and_regenerates_in_place(
    client: TestClient,
) -> None:
    with client:
        course_id = make_course(client)
        created = client.post(
            "/api/v1/artifacts/narrate",
            json={"course_id": course_id, "length_minutes": 5},
        )
        assert created.status_code == 201, created.text
        artifact = cast(dict[str, Any], created.json())
        assert artifact["kind"] == "audio_brief"
        assert artifact["status"] == "pending"
        assert artifact["spec"]["script"]
        assert "cards are due now" in artifact["spec"]["script"]
        assert artifact["spec"]["chapters"]
        assert artifact["spec"]["renderer"] == "pending"

        listing = client.get("/api/v1/artifacts", params={"course_id": course_id})
        assert listing.status_code == 200
        assert [row["id"] for row in listing.json()] == [artifact["id"]]

        duplicate = client.post("/api/v1/artifacts/narrate", json={"course_id": course_id})
        assert duplicate.status_code == 409

        again = client.post(
            "/api/v1/artifacts/narrate",
            json={"course_id": course_id, "regenerate": True},
        )
        assert again.status_code == 201, again.text
        assert again.json()["id"] == artifact["id"]


def test_render_handler_falls_back_to_a_browser_script_material(
    client: TestClient,
) -> None:
    with client:
        course_id = make_course(client)
        artifact = client.post("/api/v1/artifacts/narrate", json={"course_id": course_id}).json()
        session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
        job = SimpleNamespace(
            id="artifact-job",
            payload=ArtifactRenderPayload(artifact_id=artifact["id"]),
        )
        handler = make_artifact_render_handler(NoTtsGateway(), client.app.state.blobs)  # type: ignore[attr-defined]
        with session_factory() as session:
            handler(session, cast(Any, job), lambda *args, **kwargs: None)
            rendered = session.get(Artifact, artifact["id"])
            assert rendered is not None
            assert rendered.status == "ready"
            assert rendered.spec["renderer"] == "browser"
            assert rendered.output_material_id is not None
            material = session.get(Material, rendered.output_material_id)
            assert material is not None
            assert material.provenance is not None
            assert material.provenance["source"] == "artifact"


def test_artifact_retry_requires_a_failed_state(client: TestClient) -> None:
    with client:
        course_id = make_course(client)
        artifact = client.post("/api/v1/artifacts/narrate", json={"course_id": course_id}).json()
        response = client.post(f"/api/v1/artifacts/{artifact['id']}/retry")
        assert response.status_code == 422
