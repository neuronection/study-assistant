from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import MaterialSuggestion


def _save(client: TestClient, url: str, **overrides: object) -> dict[str, Any]:
    body: dict[str, object] = {
        "provider": "web",
        "url": url,
        "title": "Chain rule — Wikipedia",
        "snippet": "The chain rule differentiates compositions.",
        "kind": "article",
    }
    body.update(overrides)
    response = client.post("/api/v1/discovery/suggestions", json=body)
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


def test_save_and_upsert_on_normalized_url(client: TestClient) -> None:
    with client:
        first = _save(client, "https://en.wikipedia.org/wiki/Chain_rule?utm_source=x")
        assert first["created"] is True
        row = first["suggestion"]
        assert row["status"] == "saved"
        assert row["url"] == "https://en.wikipedia.org/wiki/Chain_rule?utm_source=x"
        assert row["url_norm"] == "https://en.wikipedia.org/wiki/Chain_rule"
        assert row["kind"] == "article"
        assert row["course_id"] is None

        second = _save(
            client,
            "https://en.wikipedia.org/wiki/Chain_rule",
            title="Chain rule (updated)",
            provider="youtube",
            kind="video",
        )
        assert second["created"] is False
        assert second["suggestion"]["id"] == row["id"]
        assert second["suggestion"]["title"] == "Chain rule (updated)"
        assert second["suggestion"]["kind"] == "video"

        listing = client.get("/api/v1/discovery/suggestions").json()
        assert len(listing["items"]) == 1


def test_save_validates_url_kind_and_placement(client: TestClient) -> None:
    with client:
        bad_url = client.post(
            "/api/v1/discovery/suggestions",
            json={"provider": "web", "url": "ftp://x", "title": "t"},
        )
        assert bad_url.status_code == 422

        bad_kind = client.post(
            "/api/v1/discovery/suggestions",
            json={"provider": "web", "url": "https://x.example/a", "title": "t",
                  "kind": "lecture"},
        )
        assert bad_kind.status_code == 422

        node_only = client.post(
            "/api/v1/discovery/suggestions",
            json={"provider": "web", "url": "https://x.example/a", "title": "t",
                  "node_id": 1},
        )
        assert node_only.status_code == 422

        foreign_node = client.post(
            "/api/v1/discovery/suggestions",
            json={"provider": "web", "url": "https://x.example/a", "title": "t",
                  "course_id": 9999},
        )
        assert foreign_node.status_code == 422


def test_list_filters_and_cursor_pagination(client: TestClient) -> None:
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )
        _save(client, "https://a.example/1")
        _save(client, "https://b.example/2", kind="video")
        _save(
            client,
            "https://c.example/3",
            course_id=course_id,
            kind="video",
        )

        all_rows = client.get("/api/v1/discovery/suggestions").json()
        assert len(all_rows["items"]) == 3
        assert all_rows["next_cursor"] is None

        videos = client.get(
            "/api/v1/discovery/suggestions", params={"kind": "video"}
        ).json()
        assert len(videos["items"]) == 2

        scoped = client.get(
            "/api/v1/discovery/suggestions", params={"course_id": course_id}
        ).json()
        assert [row["url"] for row in scoped["items"]] == ["https://c.example/3"]

        page1 = client.get(
            "/api/v1/discovery/suggestions", params={"limit": 2}
        ).json()
        assert len(page1["items"]) == 2
        assert page1["next_cursor"] is not None
        page2 = client.get(
            "/api/v1/discovery/suggestions",
            params={"limit": 2, "cursor": page1["next_cursor"]},
        ).json()
        all_ids = [row["id"] for row in page1["items"]] + [
            row["id"] for row in page2["items"]
        ]
        assert len(all_ids) == 3
        assert len(set(all_ids)) == 3

        bad_status = client.get(
            "/api/v1/discovery/suggestions", params={"status": "archived"}
        )
        assert bad_status.status_code == 422


def test_patch_status_transitions_and_attach_material(client: TestClient) -> None:
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )
        saved = _save(client, "https://x.example/video", course_id=course_id)
        sid = saved["suggestion"]["id"]

        dismissed = client.patch(
            f"/api/v1/discovery/suggestions/{sid}", json={"status": "dismissed"}
        )
        assert dismissed.status_code == 200, dismissed.text
        assert dismissed.json()["status"] == "dismissed"

        restored = client.patch(
            f"/api/v1/discovery/suggestions/{sid}", json={"status": "suggested"}
        )
        assert restored.json()["status"] == "suggested"

        linked = client.post(
            "/api/v1/materials/link",
            json={"course_id": course_id, "url": "https://x.example/video"},
        )
        assert linked.status_code == 200, linked.text
        material_id = int(linked.json()["material"]["id"])

        attached = client.patch(
            f"/api/v1/discovery/suggestions/{sid}",
            json={"material_id": material_id},
        )
        assert attached.status_code == 200, attached.text
        body = attached.json()
        assert body["status"] == "saved"
        assert body["material_id"] == material_id

        other_course = int(
            client.post("/api/v1/courses", json={"title": "Algebra"}).json()["id"]
        )
        foreign = client.post(
            "/api/v1/materials/link",
            json={"course_id": other_course, "url": "https://y.example/other"},
        )
        foreign_id = int(foreign.json()["material"]["id"])
        mismatch = client.patch(
            f"/api/v1/discovery/suggestions/{sid}",
            json={"material_id": foreign_id},
        )
        assert mismatch.status_code == 422

        tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
        root_id = int(tree[0]["id"])
        node = client.post(
            f"/api/v1/courses/{course_id}/nodes",
            json={"course_id": course_id, "parent_id": root_id, "title": "Derivatives"},
        )
        assert node.status_code == 201, node.text
        node_id = int(node.json()["id"])
        repointed = client.patch(
            f"/api/v1/discovery/suggestions/{sid}", json={"node_id": node_id}
        )
        assert repointed.status_code == 200, repointed.text
        assert repointed.json()["node_id"] == node_id

        bad_transition = client.patch(
            f"/api/v1/discovery/suggestions/{sid}", json={"status": "archived"}
        )
        assert bad_transition.status_code == 422


def test_forget_then_rediscover_creates_fresh(client: TestClient) -> None:
    with client:
        saved = _save(client, "https://x.example/1")
        sid = saved["suggestion"]["id"]
        assert (
            client.delete(f"/api/v1/discovery/suggestions/{sid}").status_code == 204
        )
        assert (
            client.delete(f"/api/v1/discovery/suggestions/{sid}").status_code == 404
        )
        again = _save(client, "https://x.example/1")
        assert again["created"] is True
        listing = client.get("/api/v1/discovery/suggestions").json()
        assert len(listing["items"]) == 1
        assert listing["items"][0]["status"] == "saved"


def test_material_purge_reverts_saved_suggestion(
    client: TestClient, db_session: Session
) -> None:
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )
        linked = client.post(
            "/api/v1/materials/link",
            json={"course_id": course_id, "url": "https://x.example/1"},
        )
        material_id = int(linked.json()["material"]["id"])
        saved = _save(client, "https://x.example/1", course_id=course_id)
        sid = saved["suggestion"]["id"]
        attached = client.patch(
            f"/api/v1/discovery/suggestions/{sid}",
            json={"material_id": material_id},
        )
        assert attached.json()["material_id"] == material_id

        deleted = client.delete(f"/api/v1/materials/{material_id}")
        assert deleted.status_code == 200, deleted.text

    row = db_session.get(MaterialSuggestion, sid)
    assert row is not None
    assert row.status == "suggested"
    assert row.material_id is None


def test_course_purge_cascades_but_scratchpad_survives(
    client: TestClient, db_session: Session
) -> None:
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )
        _save(client, "https://x.example/course-owned", course_id=course_id)
        scratch_saved = _save(client, "https://x.example/scratch")
        scratch_id = scratch_saved["suggestion"]["id"]

        deleted = client.delete(
            f"/api/v1/courses/{course_id}", params={"confirmed_backup": "true"}
        )
        assert deleted.status_code == 200, deleted.text

    rows = list(
        db_session.scalars(select(MaterialSuggestion).order_by(MaterialSuggestion.id))
    )
    assert [row.id for row in rows] == [scratch_id]
    assert rows[0].course_id is None


def test_node_deletion_repoints_suggestion_to_parent(
    client: TestClient, db_session: Session
) -> None:
    with client:
        course_id = int(
            client.post("/api/v1/courses", json={"title": "Calc"}).json()["id"]
        )
        tree = client.get(f"/api/v1/courses/{course_id}/tree").json()
        root_id = int(tree[0]["id"])
        node = client.post(
            f"/api/v1/courses/{course_id}/nodes",
            json={"course_id": course_id, "parent_id": root_id, "title": "Chapter"},
        )
        assert node.status_code == 201, node.text
        node_id = int(node.json()["id"])

        saved = _save(
            client, "https://x.example/1", course_id=course_id, node_id=node_id
        )
        sid = saved["suggestion"]["id"]

        deleted = client.delete(f"/api/v1/nodes/{node_id}")
        assert deleted.status_code == 200, deleted.text

    row = db_session.get(MaterialSuggestion, sid)
    assert row is not None
    assert row.node_id == root_id


def test_search_annotates_known_suggestions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.api.discovery as discovery_api
    from app.search.discovery import DiscoveryResult

    class FakeProvider:
        id = "web"
        label = "Web"

        def search(
            self, query: str, *, cap: int, transport: object | None = None
        ) -> list[DiscoveryResult]:
            return [
                DiscoveryResult(
                    provider="web",
                    title="Known",
                    url="https://x.example/known?utm_source=x",
                    kind="article",
                ),
                DiscoveryResult(
                    provider="web",
                    title="Unknown",
                    url="https://x.example/unknown",
                    kind="article",
                ),
            ]

    monkeypatch.setattr(
        discovery_api, "resolve_providers", lambda *args, **kwargs: [FakeProvider()]
    )

    with client:
        saved = _save(client, "https://x.example/known")
        saved_id = saved["suggestion"]["id"]

        response = client.post(
            "/api/v1/discovery/search", json={"query": "chain rule", "cap": 5}
        )
        assert response.status_code == 200, response.text
        rows = response.json()["results"]
        assert len(rows) == 2
        known = next(row for row in rows if "known" in row["url"])
        unknown = next(row for row in rows if "unknown" in row["url"])
        assert known["suggestion"] == {
            "id": saved_id,
            "status": "saved",
            "material_id": None,
        }
        assert unknown["suggestion"] is None


def test_discovery_preferences_round_trip_and_validation(
    client: TestClient, db_session: Session
) -> None:
    with client:
        defaults = client.get("/api/v1/profiles/preferences").json()
        assert defaults["discovery"]["enabled"] == ["web", "youtube"]
        assert defaults["discovery"]["sites"] == []

        updated = client.put(
            "/api/v1/profiles/preferences",
            json={
                "discovery": {
                    "enabled": ["web", "site:ex.com"],
                    "sites": [
                        {"site": "ex.com", "label": "Example U", "kind": "article"}
                    ],
                }
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["discovery"] == {
            "enabled": ["web", "site:ex.com"],
            "sites": [
                {"site": "ex.com", "label": "Example U", "kind": "article"}
            ],
        }

        partial = client.put(
            "/api/v1/profiles/preferences",
            json={"discovery": {"enabled": ["youtube"]}},
        )
        assert partial.status_code == 200, partial.text
        assert partial.json()["discovery"]["enabled"] == ["youtube"]
        assert partial.json()["discovery"]["sites"] == [
            {"site": "ex.com", "label": "Example U", "kind": "article"}
        ]

        bad_enabled = client.put(
            "/api/v1/profiles/preferences",
            json={"discovery": {"enabled": ["gopher"]}},
        )
        assert bad_enabled.status_code == 422

        bad_kind = client.put(
            "/api/v1/profiles/preferences",
            json={"discovery": {"sites": [{"site": "ex.com", "kind": "lecture"}]}},
        )
        assert bad_kind.status_code == 422

    from app.domain.models import Profile

    profile = db_session.scalars(select(Profile)).first()
    assert profile is not None
    prefs = profile.preferences
    assert isinstance(prefs, dict)
    assert prefs["discovery"]["enabled"] == ["youtube"]
    assert prefs["discovery"]["sites"][0]["site"] == "ex.com"
