import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from app.core.config import Settings
from app.main import create_app


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


def make_course(client: TestClient, title: str) -> int:
    created = client.post("/api/v1/courses", json={"title": title})
    assert created.status_code == 201
    return int(created.json()["id"])


def upload_txt(client: TestClient, filename: str, course_id: int) -> int:
    upload = client.post(
        "/api/v1/materials",
        params={"course_id": course_id},
        files={"file": (filename, f"content of {filename}".encode(), "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    material_id = int(upload.json()["material"]["id"])
    wait_until(
        lambda: client.get(f"/api/v1/materials/{material_id}").json()["material"]["status"]
        == "ready"
    )
    return material_id


def test_migration_0057_adds_and_drops_tags_starred(tmp_path: Path) -> None:
    db_path = tmp_path / "mig.db"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "0057_material_tags_starred")

    import sqlite3

    raw = sqlite3.connect(db_path)
    columns = {
        row[1] for row in raw.execute("PRAGMA table_info(materials)").fetchall()
    }
    indexes = {
        row[1] for row in raw.execute("PRAGMA index_list(materials)").fetchall()
    }
    raw.close()
    assert "tags" in columns
    assert "starred" in columns
    assert "ix_materials_starred" in indexes

    command.downgrade(alembic_cfg, "0056_quizme_answers")
    raw = sqlite3.connect(db_path)
    columns = {
        row[1] for row in raw.execute("PRAGMA table_info(materials)").fetchall()
    }
    indexes = {
        row[1] for row in raw.execute("PRAGMA index_list(materials)").fetchall()
    }
    raw.close()
    assert "tags" not in columns
    assert "starred" not in columns
    assert "ix_materials_starred" not in indexes


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            config_dir=tmp_path / "config",
            spa_dist=tmp_path / "no-spa",
            log_level="WARNING",
        )
    )
    with TestClient(app) as test_client:
        yield test_client


def test_patch_tags_and_starred_round_trip(client: TestClient) -> None:
    test_client = client
    course_id = make_course(test_client, "Tagged course")
    material_id = upload_txt(test_client, "m.txt", course_id)

    patched = test_client.patch(
        f"/api/v1/materials/{material_id}",
        json={"tags": [" Exam-Prep ", "derivatives", "exam-prep"], "starred": True},
    )
    assert patched.status_code < 400, patched.text
    body = test_client.get(f"/api/v1/materials/{material_id}").json()["material"]
    assert body["tags"] == ["exam-prep", "derivatives"]
    assert body["starred"] is True

    unstarred = test_client.patch(
        f"/api/v1/materials/{material_id}", json={"starred": False}
    )
    assert unstarred.status_code < 400, unstarred.text
    body = test_client.get(f"/api/v1/materials/{material_id}").json()["material"]
    assert body["starred"] is False


def test_list_filters_by_tag_and_starred(client: TestClient) -> None:
    test_client = client
    course_id = make_course(test_client, "Filtered course")
    kept = upload_txt(test_client, "keep.txt", course_id)
    dropped = upload_txt(test_client, "drop.txt", course_id)
    starred_only = upload_txt(test_client, "star.txt", course_id)
    assert test_client.patch(
        f"/api/v1/materials/{kept}", json={"tags": ["exam-prep"], "starred": True}
    ).status_code < 400
    assert test_client.patch(
        f"/api/v1/materials/{dropped}", json={"tags": ["background"]}
    ).status_code < 400
    assert test_client.patch(
        f"/api/v1/materials/{starred_only}", json={"starred": True}
    ).status_code < 400

    by_tag = test_client.get(
        "/api/v1/materials", params={"course_id": course_id, "tag": "exam-prep"}
    ).json()
    assert [entry["id"] for entry in by_tag] == [kept]

    by_star = test_client.get(
        "/api/v1/materials", params={"course_id": course_id, "starred": True}
    ).json()
    assert {entry["id"] for entry in by_star} == {kept, starred_only}

    unfiltered = test_client.get(
        "/api/v1/materials", params={"course_id": course_id}
    ).json()
    assert {entry["id"] for entry in unfiltered} == {kept, dropped, starred_only}
