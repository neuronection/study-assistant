from fastapi.testclient import TestClient

from app.api.activation import ActivationPropsIn
from app.core.vocab import ActivationEvent, ActivationStep, ActivationSurface
from app.domain.payloads import ActivationProps

SHIPPED_EVENTS = {
    "onboarding_step",
    "first_file_ingested",
    "first_review",
    "first_quiz",
    "first_ai_call",
    "first_capture",
    "update_installed",
    "highlight_to_card",
    "brief_played_50pct",
    "solve_completed",
    "paper_sat",
    "device_linked",
    "feature_opened",
    "tip_dismissed",
}

SHIPPED_STEPS = {
    "complete",
    "materials",
    "review",
    "exam",
    "practice",
    "provider",
    "library-split-view",
    "review-buttons",
    "practice-segments",
}

SHIPPED_SURFACES = {
    "home",
    "course",
    "review",
    "quiz",
    "quick_capture",
    "problem_desk",
    "lecture_moment",
    "lecture_moment_batch",
    "home_coach",
    "one_time_tip",
}


def _second_profile(client: TestClient) -> dict[str, str]:
    created = client.post("/api/v1/profiles", json={"name": "Other learner"})
    assert created.status_code == 201, created.text
    return {"X-Profile-Id": str(created.json()["id"])}


def test_activation_vocabularies_match_the_shipped_inventory() -> None:
    assert set(ActivationEvent.values()) == SHIPPED_EVENTS
    assert set(ActivationStep.values()) == SHIPPED_STEPS
    assert set(ActivationSurface.values()) == SHIPPED_SURFACES


def test_activation_props_typed_dict_and_model_do_not_drift() -> None:
    assert set(ActivationProps.__annotations__) == set(ActivationPropsIn.model_fields)
    assert ActivationProps.__annotations__["step"] is ActivationStep
    assert ActivationProps.__annotations__["surface"] is ActivationSurface


def test_activation_events_summary_export_and_clear(client: TestClient) -> None:
    with client:
        first = client.post(
            "/api/v1/activation/events",
            json={
                "event": "first_file_ingested",
                "props": {"step": "complete", "surface": "home", "value": 3},
            },
        )
        assert first.status_code == 201, first.text
        assert first.json()["event"] == "first_file_ingested"
        assert first.json()["props"] == {
            "schema_version": 1,
            "step": "complete",
            "surface": "home",
            "value": 3,
        }
        client.post("/api/v1/activation/events", json={"event": "first_review"})

        summary = client.get("/api/v1/activation/summary")
        assert summary.status_code == 200
        payload = summary.json()
        assert payload["total"] == 2
        assert {row["event"]: row["count"] for row in payload["counts"]} == {
            "first_file_ingested": 1,
            "first_review": 1,
        }
        assert payload["first_at"] is not None

        exported = client.get("/api/v1/activation/export")
        assert exported.status_code == 200
        assert len(exported.json()["events"]) == 2

        assert client.delete("/api/v1/activation").status_code == 204
        assert client.get("/api/v1/activation/summary").json()["total"] == 0


def test_activation_rejects_unknown_events(client: TestClient) -> None:
    with client:
        response = client.post(
            "/api/v1/activation/events", json={"event": "not-a-real-event"}
        )
        assert response.status_code == 422


def test_activation_rejects_unknown_prop_keys(client: TestClient) -> None:
    with client:
        response = client.post(
            "/api/v1/activation/events",
            json={"event": "first_review", "props": {"note": "private text"}},
        )
        assert response.status_code == 422


def test_activation_rejects_out_of_vocabulary_step_and_surface(
    client: TestClient,
) -> None:
    with client:
        step = client.post(
            "/api/v1/activation/events",
            json={"event": "first_review", "props": {"step": "not-a-step"}},
        )
        assert step.status_code == 422
        surface = client.post(
            "/api/v1/activation/events",
            json={"event": "first_review", "props": {"surface": "not-a-surface"}},
        )
        assert surface.status_code == 422


def test_activation_value_boundaries(client: TestClient) -> None:
    with client:
        for value in (0, 1_000_000, 12.5, None):
            response = client.post(
                "/api/v1/activation/events",
                json={"event": "solve_completed", "props": {"value": value}},
            )
            assert response.status_code == 201, (value, response.text)
        for invalid in (1_000_001, -1, True, False, "3"):
            response = client.post(
                "/api/v1/activation/events",
                json={"event": "solve_completed", "props": {"value": invalid}},
            )
            assert response.status_code == 422, (invalid, response.text)


def test_activation_is_scoped_to_the_bound_profile(client: TestClient) -> None:
    with client:
        assert (
            client.post(
                "/api/v1/activation/events", json={"event": "first_review"}
            ).status_code
            == 201
        )
        other = _second_profile(client)
        assert (
            client.post(
                "/api/v1/activation/events",
                json={"event": "first_review"},
                headers=other,
            ).status_code
            == 201
        )

        assert client.get("/api/v1/activation/summary").json()["total"] == 1
        other_summary = client.get("/api/v1/activation/summary", headers=other)
        assert other_summary.json()["total"] == 1

        other_export = client.get("/api/v1/activation/export", headers=other)
        assert other_export.status_code == 200
        assert [row["event"] for row in other_export.json()["events"]] == [
            "first_review"
        ]

        assert client.delete("/api/v1/activation", headers=other).status_code == 204
        assert client.get("/api/v1/activation/summary").json()["total"] == 1
        assert (
            client.get("/api/v1/activation/summary", headers=other).json()["total"]
            == 0
        )
