from fastapi.testclient import TestClient
from test_extraction_edit import upload_txt
from test_notes_api import create_note, make_client


def test_note_version_diff_lines_and_stats() -> None:
    client = make_client([])
    with client:
        note_id = create_note(client, "Diff note", "line one\nline two\n")
        client.patch(
            f"/api/v1/notes/{note_id}",
            json={
                "body_md": "line one\nline two changed\nline three\n",
                "force_version": True,
            },
        )
        client.patch(
            f"/api/v1/notes/{note_id}", json={"body_md": "final\n", "force_version": True}
        )
        versions = client.get(f"/api/v1/notes/{note_id}/versions").json()
        assert len(versions) >= 2
        oldest, newest = versions[-1]["version_id"], versions[0]["version_id"]

        result = client.get(
            f"/api/v1/notes/{note_id}/versions/diff",
            params={"from": oldest, "to": newest},
        )
        assert result.status_code == 200
        body = result.json()
        assert body["base"] == str(oldest)
        assert body["target"] == str(newest)
        assert body["additions"] >= 2
        assert body["deletions"] >= 1
        assert "-line two" in body["diff"]
        assert "+line two changed" in body["diff"]
        assert "+line three" in body["diff"]


def test_note_version_diff_current_alias_and_errors() -> None:
    client = make_client([])
    with client:
        note_id = create_note(client, "Current diff", "alpha\n")
        client.patch(
            f"/api/v1/notes/{note_id}", json={"body_md": "alpha\nbeta\n", "force_version": True}
        )
        ok = client.get(
            f"/api/v1/notes/{note_id}/versions/diff",
            params={"from": "current", "to": "current"},
        )
        assert ok.status_code == 200
        assert ok.json()["diff"] == ""
        assert ok.json()["additions"] == 0

        missing = client.get(
            f"/api/v1/notes/{note_id}/versions/diff",
            params={"from": 99999, "to": "current"},
        )
        assert missing.status_code == 404

        bad = client.get(
            f"/api/v1/notes/{note_id}/versions/diff",
            params={"from": "not-a-version", "to": "current"},
        )
        assert bad.status_code == 422


def test_extraction_version_diff_lines_stats_and_current(client: TestClient) -> None:
    material_id = upload_txt(client, b"original body", "diff-source.txt")

    client.patch(
        f"/api/v1/materials/{material_id}/extraction",
        json={"markdown": "original body\nedited line\n"},
    )

    versions = client.get(f"/api/v1/materials/{material_id}/extractions").json()
    assert len(versions) >= 2
    oldest = versions[-1]["version"]
    latest = versions[0]["version"]

    result = client.get(
        f"/api/v1/materials/{material_id}/extractions/diff",
        params={"from": oldest, "to": "current"},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["additions"] >= 1
    assert "+edited line" in body["diff"]
    assert f"v{oldest}" in body["diff"]

    same = client.get(
        f"/api/v1/materials/{material_id}/extractions/diff",
        params={"from": latest, "to": latest},
    )
    assert same.status_code == 200
    assert same.json()["diff"] == ""

    missing = client.get(
        f"/api/v1/materials/{material_id}/extractions/diff",
        params={"from": 999, "to": "current"},
    )
    assert missing.status_code == 404
