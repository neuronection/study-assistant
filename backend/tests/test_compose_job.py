import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture, raises
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, add_material, make_course
from test_compose_coverage import LONG_DOC

from app.core.config import Settings
from app.domain.models import Job, Material
from app.jobs.cancellation import JobCancelled, is_cancel_requested, request_cancel
from app.main import create_app
from app.pipelines.compose import make_compose_handler
from app.storage.blobs import BlobStore


def wait_job(
    client: TestClient, job_id: int, timeout: float = 60.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in ("done", "failed", "cancelled"):
            return last
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} never finished; last state: {last}")


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


@fixture
def gateway() -> ScriptedGateway:
    return ScriptedGateway([LONG_DOC])


def test_compose_async_endpoint_queues_and_persists(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "src.txt", "chain rule source", course_id)
        queued = test_client.post(
            "/api/v1/materials/compose/async",
            json={
                "course_id": course_id,
                "kind": "study_guide",
                "title": "Async guide",
            },
        )
        assert queued.status_code == 200, queued.text
        job_id = queued.json()["job_id"]
        job = wait_job(test_client, job_id)
        assert job["status"] == "done", job
        assert job["progress"] == 100
        material_id = job["material_id"]
        assert material_id is not None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            material = test_client.get(f"/api/v1/materials/{material_id}").json()
            if material["material"]["status"] == "ready":
                break
            time.sleep(0.05)
        else:
            raise AssertionError(
                f"material {material_id} never ready: {material['material']['status']}"
            )
        provenance = material["material"]["provenance"]
        assert provenance["source"] == "ai-composed"
        assert provenance["kind"] == "study_guide"


def test_compose_async_fast_fails_on_unknown_node(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        response = test_client.post(
            "/api/v1/materials/compose/async",
            json={"course_id": course_id, "node_id": 987654, "kind": "study_guide"},
        )
        assert response.status_code == 422
        assert "different course" in response.json()["detail"]


def test_compose_async_preserves_409_at_enqueue(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "src.txt", "chain rule source", course_id)
        tree = test_client.get(f"/api/v1/courses/{course_id}/tree").json()
        root_id = int(tree[0]["id"])
        gateway.responses.append(LONG_DOC)
        first = test_client.post(
            "/api/v1/materials/compose",
            json={
                "course_id": course_id,
                "node_id": root_id,
                "kind": "study_guide",
                "title": "First",
            },
        )
        assert first.status_code == 200, first.text
        second = test_client.post(
            "/api/v1/materials/compose/async",
            json={
                "course_id": course_id,
                "node_id": root_id,
                "kind": "study_guide",
                "title": "Second",
            },
        )
        assert second.status_code == 409
        assert "already exists" in second.json()["detail"]


def test_single_job_get_returns_status_and_404(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "src.txt", "chain rule source", course_id)
        gateway.responses.append(LONG_DOC)
        queued = test_client.post(
            "/api/v1/materials/compose/async",
            json={"course_id": course_id, "kind": "summary_sheet", "title": "S"},
        )
        job_id = queued.json()["job_id"]
        job = wait_job(test_client, job_id)
        assert job["id"] == job_id
        assert job["type"] == "compose"
        missing = test_client.get("/api/v1/jobs/999999")
        assert missing.status_code == 404


def test_cancel_endpoint_cancels_queued_compose(
    client: tuple[TestClient, ScriptedGateway, FastAPI],
) -> None:
    test_client, _gateway, _app = client
    with test_client:
        course_id = make_course(test_client)
        add_material(test_client, "src.txt", "chain rule source", course_id)
        queued = test_client.post(
            "/api/v1/materials/compose/async",
            json={
                "course_id": course_id,
                "kind": "study_guide",
                "title": "Cancel me",
            },
        )
        job_id = queued.json()["job_id"]
        cancelled = test_client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        job = wait_job(test_client, job_id)
        assert job["status"] == "cancelled"
        stored = test_client.get(f"/api/v1/materials?course_id={course_id}").json()
        composed = [
            entry
            for entry in stored
            if (entry.get("provenance") or {}).get("source") == "ai-composed"
        ]
        assert composed == []
        rerun = test_client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert rerun.status_code == 409


def _compose_job(course_id: int, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "course_id": course_id,
        "kind": "study_guide",
        "title": "Guide",
    }
    payload.update(extra)
    return payload


def test_handler_runs_through_progress_checkpoints(
    db_session: Session, tmp_path: Path
) -> None:
    profile = _profile(db_session)
    course = _course(db_session, profile.id)
    job = Job(type="compose", payload=_compose_job(int(course.id)), status="running")
    db_session.add(job)
    db_session.flush()
    reports: list[tuple[int, str]] = []
    handler = make_compose_handler(
        ScriptedGateway([LONG_DOC]), BlobStore(tmp_path), lambda query: None
    )
    handler(db_session, job, lambda progress, stage: reports.append((progress, stage)))
    assert [progress for progress, _stage in reports] == [10, 30, 90, 100]
    material = db_session.scalars(
        select(Material).where(Material.provenance.is_not(None))
    ).first()
    assert material is not None
    assert job.payload is not None
    assert job.payload["material_id"] == material.id
    ingest_jobs = list(
        db_session.scalars(select(Job).where(Job.type == "ingest"))
    )
    assert len(ingest_jobs) == 1


def test_handler_fails_honestly_when_live_artifact_appeared(
    db_session: Session, tmp_path: Path
) -> None:
    from app.domain.models import TreeNode
    from app.pipelines.compose import ComposeService

    profile = _profile(db_session)
    course = _course(db_session, profile.id)
    node = TreeNode(
        course_id=course.id,
        title="Ch1",
        depth=1,
        path=f"/{course.id}/1",
        sort_path="/",
    )
    db_session.add(node)
    db_session.flush()
    gateway = ScriptedGateway([LONG_DOC])
    service = ComposeService(db_session, gateway)
    live = service.compose(
        profile_id=profile.id,
        course_id=course.id,
        node_id=node.id,
        kind="study_guide",
        title="Guide",
        context_bundle=None,
        blobs=BlobStore(tmp_path),
    )
    job = Job(
        type="compose",
        payload=_compose_job(int(course.id), node_id=node.id, regenerate=False),
        status="running",
    )
    db_session.add(job)
    db_session.flush()
    handler = make_compose_handler(
        ScriptedGateway([LONG_DOC]), BlobStore(tmp_path), lambda query: None
    )
    from app.jobs.runner import JobError

    with raises(JobError, match="already exists"):
        handler(db_session, job, lambda progress, stage: None)
    assert live.id


def test_handler_honors_cancel_before_persist(
    db_session: Session, tmp_path: Path
) -> None:
    profile = _profile(db_session)
    course = _course(db_session, profile.id)
    job = Job(type="compose", payload=_compose_job(int(course.id)), status="running")
    db_session.add(job)
    db_session.flush()
    request_cancel(job.id)
    handler = make_compose_handler(
        ScriptedGateway([LONG_DOC]), BlobStore(tmp_path), lambda query: None
    )
    with raises(JobCancelled):
        handler(db_session, job, lambda progress, stage: None)
    assert db_session.scalars(select(Material)).first() is None


def _profile(db_session: Session) -> Any:
    from app.domain.models import Profile

    profile = Profile(name="p")
    db_session.add(profile)
    db_session.flush()
    return profile


def _course(db_session: Session, profile_id: int) -> Any:
    from app.domain.models import Course, TreeNode

    course = Course(profile_id=profile_id, title="Calc")
    db_session.add(course)
    db_session.flush()
    db_session.add(
        TreeNode(
            course_id=course.id,
            title="Calc",
            is_root=True,
            depth=0,
            path=f"/{course.id}",
            sort_path="/",
        )
    )
    db_session.flush()
    return course


def test_stale_cancel_flag_cleared_on_claim(db_session: Session) -> None:
    from app.core.events import EventBus
    from app.jobs.runner import JobRunner

    request_cancel(1)
    job = Job(type="ingest", payload={"material_id": 1}, status="queued")
    db_session.add(job)
    db_session.commit()
    assert job.id == 1
    assert is_cancel_requested(job.id)

    runner = JobRunner(
        sessionmaker(bind=db_session.get_bind()),
        EventBus(),
        handlers={},
    )
    claimed = runner._claim_next()
    assert claimed is not None
    assert claimed.id == 1
    assert not is_cancel_requested(claimed.id)
