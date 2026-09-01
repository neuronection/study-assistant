import json
from typing import Any

from fastapi.testclient import TestClient

from app.ai.gateway import LLMGateway
from app.core.config import Settings
from app.main import create_app


class Scripted(LLMGateway):
    def __init__(self) -> None:
        super().__init__(session_factory=None)


def make_client(tmp: Any) -> TestClient:
    app = create_app(Settings(data_dir=tmp, log_level="WARNING"), gateway=Scripted())
    return TestClient(app)


def fork_skill(client: TestClient, key: str, template: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/skills/{key}/versions",
        json={
            "scope_type": "system",
            "scope_ref": None,
            "system_template": template,
            "user_template": "",
        },
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def test_export_pack_shape(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        fork = fork_skill(client, "chat.answer", "Custom answer prompt for {{course_title}}")
        assert fork["version"] == 2
        response = client.post("/api/v1/skills/export", json={"keys": ["chat.answer"]})
        assert response.status_code == 200, response.text
        pack = response.json()
        assert pack["format"] == "ca-skills/v1"
        assert len(pack["skills"]) == 1
        entry = pack["skills"][0]
        assert entry["key"] == "chat.answer"
        assert entry["task"] == "chat"
        assert [v["version"] for v in entry["versions"]] == [1, 2]
        assert entry["versions"][1]["system_template"].startswith("Custom answer")
        assert entry["versions"][-1]["is_active"] is True

        missing = client.post("/api/v1/skills/export", json={"keys": ["nope.missing"]})
        assert missing.status_code == 422
        empty = client.post("/api/v1/skills/export", json={"keys": []})
        assert empty.status_code == 422


def test_preview_reports_collision_and_validation_errors(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        fork_skill(client, "chat.answer", "Custom answer prompt")
        pack = client.post("/api/v1/skills/export", json={"keys": ["chat.answer"]}).json()

        preview = client.post("/api/v1/skills/packs/import?dry_run=true", json=pack)
        assert preview.status_code == 200, preview.text
        entry = preview.json()["skills"][0]
        assert entry["key"] == "chat.answer"
        assert entry["collision"] is True
        assert entry["errors"] == []
        assert entry["active_version"] == 2

        bad = {
            "format": "ca-skills/v1",
            "exported_at": "now",
            "skills": [
                {
                    "task": "chat",
                    "key": "chat.answer",
                    "name": "Broken",
                    "versions": [
                        {
                            "version": 1,
                            "system_template": "broken {{ unclosed",
                            "user_template": "",
                            "is_active": True,
                        }
                    ],
                }
            ],
        }
        broken = client.post("/api/v1/skills/packs/import?dry_run=true", json=bad)
        assert broken.status_code == 200
        assert broken.json()["skills"][0]["errors"]

        junk = {"format": "other/v9", "skills": []}
        rejected = client.post("/api/v1/skills/packs/import?dry_run=true", json=junk)
        assert rejected.status_code == 422
        no_task = {
            "format": "ca-skills/v1",
            "skills": [
                {
                    "task": "nonexistent_task",
                    "key": "x.y",
                    "name": "X",
                    "versions": [
                        {
                            "version": 1,
                            "system_template": "s",
                            "user_template": "",
                            "is_active": True,
                        }
                    ],
                }
            ],
        }
        unknown_task = client.post("/api/v1/skills/packs/import?dry_run=true", json=no_task)
        assert unknown_task.status_code == 422


def test_commit_replace_skip_and_rename(tmp_path: Any) -> None:
    client = make_client(tmp_path)
    with client:
        fork_skill(client, "chat.answer", "First fork")
        pack = client.post("/api/v1/skills/export", json={"keys": ["chat.answer"]}).json()

        skipped = client.post(
            "/api/v1/skills/packs/import", params={"dry_run": "false"}, json=pack
        )
        assert skipped.status_code == 200, skipped.text
        assert skipped.json()["skipped"][0]["key"] == "chat.answer"
        assert skipped.json()["replaced"] == []

        replaced = client.post(
            "/api/v1/skills/packs/import",
            params={
                "dry_run": "false",
                "resolutions": json.dumps({"chat.answer": "replace"}),
            },
            json=pack,
        )
        assert replaced.status_code == 200, replaced.text
        assert replaced.json()["replaced"] == ["chat.answer"]
        versions = client.get("/api/v1/skills/chat.answer/versions").json()
        assert [v["version"] for v in versions] == [1, 2, 3, 4]
        assert versions[-1]["is_active"] is True
        assert versions[-1]["system_template"].startswith("First fork")

        renamed = client.post(
            "/api/v1/skills/packs/import",
            params={
                "dry_run": "false",
                "resolutions": json.dumps({"chat.answer": "rename"}),
            },
            json=pack,
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["renamed"][0]["new_key"] == "chat.answer-2"
        assert client.get("/api/v1/skills").json() != []


def test_pack_round_trip_across_machines(tmp_path: Any) -> None:
    source = make_client(tmp_path / "src")
    with source:
        fork_skill(
            source,
            "quiz.generate",
            "Source-custom quiz prompt for {{scope_title}}",
        )
        pack = source.post("/api/v1/skills/export", json={"keys": ["quiz.generate"]}).json()

    target = make_client(tmp_path / "dst")
    with target:
        preview = target.post("/api/v1/skills/packs/import?dry_run=true", json=pack)
        assert preview.status_code == 200
        assert preview.json()["skills"][0]["collision"] is True

        imported = target.post(
            "/api/v1/skills/packs/import",
            params={
                "dry_run": "false",
                "resolutions": json.dumps({"quiz.generate": "replace"}),
            },
            json=pack,
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["replaced"] == ["quiz.generate"]
        versions = target.get("/api/v1/skills/quiz.generate/versions").json()
        assert versions[-1]["system_template"].startswith("Source-custom")
        assert versions[-1]["is_active"] is True

        resolution = target.get("/api/v1/skills/quiz.generate/resolution")
        assert resolution.status_code == 200
        assert resolution.json()["chain"]["system"] == f"v{len(versions)}"
