from fastapi.testclient import TestClient


def test_state_fresh_install_is_all_false(client: TestClient) -> None:
    with client:
        body = client.get("/api/v1/onboarding/state").json()
        assert body == {
            "has_provider": False,
            "has_enabled_model": False,
            "defaults_set": [],
            "has_course": False,
            "has_material": False,
        }


def test_state_reflects_provider_model_defaults_course_material(client: TestClient) -> None:
    with client:
        created = client.post(
            "/api/v1/providers",
            json={
                "name": "Local",
                "type": "openai_compatible",
                "base_url": "http://localhost:11434/v1",
            },
        )
        assert created.status_code == 201, created.text

        body = client.get("/api/v1/onboarding/state").json()
        assert body["has_provider"] is True
        assert body["has_enabled_model"] is False

        model = client.post(
            "/api/v1/models",
            json={"provider_id": created.json()["id"], "external_id": "qwen3", "enabled": True},
        ).json()

        put = client.put(
            "/api/v1/tasks/defaults/text",
            json={"model_id": model["id"], "fallback_model_id": None},
        )
        assert put.status_code == 200, put.text

        body = client.get("/api/v1/onboarding/state").json()
        assert body["has_enabled_model"] is True
        assert body["defaults_set"] == ["text"]

        course = client.post("/api/v1/courses", json={"title": "Calculus I"})
        assert course.status_code == 201, course.text
        body = client.get("/api/v1/onboarding/state").json()
        assert body["has_course"] is True
        assert body["has_material"] is False

        upload = client.post(
            "/api/v1/materials",
            params={"course_id": course.json()["id"]},
            files={"file": ("notes.md", b"# notes", "text/markdown")},
        )
        assert upload.status_code in (200, 201), upload.text
        body = client.get("/api/v1/onboarding/state").json()
        assert body["has_material"] is True
