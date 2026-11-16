"""Opt-in S3/MinIO/AWS smoke test for the object-storage contract (plan 55 P1).

Normal PRs and the desktop suite do not need credentials: without
``SA_TEST_S3_BUCKET`` this module skips even when the network opt-out is
unset. The session ``_no_network`` fixture blocks connects by default, so a
real smoke also sets ``SA_TEST_ALLOW_NETWORK=1``. An endpoint is optional:
real AWS S3 uses the regional default, while MinIO/moto need
``SA_TEST_S3_ENDPOINT_URL``. Run it against MinIO/moto like this (bucket and
credentials from your local server):

    SA_TEST_ALLOW_NETWORK=1 SA_TEST_S3_BUCKET=nx-object-storage \\
    SA_TEST_S3_ENDPOINT_URL=http://127.0.0.1:19000 \\
    SA_TEST_S3_ACCESS_KEY_ID=test SA_TEST_S3_SECRET_ACCESS_KEY=test \\
    SA_TEST_S3_REGION=us-east-1 SA_TEST_S3_PATH_STYLE=true \\
    SA_TEST_S3_SSE=none \\
    uv run --directory backend --with boto3 pytest -q tests/test_object_storage_s3.py

Real AWS S3 (credentials via the default chain, e.g. ``AWS_PROFILE``):

    AWS_PROFILE=study-test SA_TEST_ALLOW_NETWORK=1 \\
    SA_TEST_S3_BUCKET=study-assistant-test SA_TEST_S3_REGION=eu-north-1 \\
    SA_TEST_S3_PREFIX=test/ \\
    uv run --directory backend --with boto3 pytest -q tests/test_object_storage_s3.py

The module runs the family conformance wall plus a course
export/import/duplicate round-trip through the real backend. See
docs/dev/storage.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from object_storage_smoke_helpers import NoAI, SmokeGateway, env_values, run_prefix

from app.core.config import Settings
from app.main import create_app
from app.storage.object_storage import (
    BACKEND_S3,
    ENTRYPOINT_SERVER,
    S3Config,
    StorageConfig,
    build_store,
    run_conformance,
)

ENV_PREFIX = "SA_TEST"
REQUIRED = ("S3_BUCKET",)


def _require_backend() -> dict[str, str]:
    env = env_values(ENV_PREFIX)
    missing = [f"{ENV_PREFIX}_{name}" for name in REQUIRED if not env.get(f"{ENV_PREFIX}_{name}")]
    if missing:
        pytest.skip(f"S3 smoke disabled; set {', '.join(missing)}")
    pytest.importorskip("boto3")
    return env


def _config(env: dict[str, str], prefix: str) -> StorageConfig:
    def value(name: str, default: str | None = None) -> str | None:
        return env.get(f"{ENV_PREFIX}_{name}") or default

    endpoint = value("S3_ENDPOINT_URL")
    path_style_raw = value("S3_PATH_STYLE")
    path_style = (path_style_raw or ("true" if endpoint else "false")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    sse = value("S3_SSE", "none" if endpoint else "AES256") or "none"

    return StorageConfig(
        backend=BACKEND_S3,
        entrypoint=ENTRYPOINT_SERVER,
        s3=S3Config(
            bucket=value("S3_BUCKET") or "",
            region=value("S3_REGION"),
            endpoint_url=endpoint,
            access_key_id=value("S3_ACCESS_KEY_ID"),
            secret_access_key=value("S3_SECRET_ACCESS_KEY"),
            session_token=value("S3_SESSION_TOKEN"),
            path_style=path_style,
            sse=sse,
            prefix=prefix,
            verify_tls=(value("S3_VERIFY_TLS", "true") or "true").lower()
            in ("1", "true", "yes", "on"),
        ),
    ).validate()


def test_s3_conformance() -> None:
    env = _require_backend()
    prefix = run_prefix(env.get(f"{ENV_PREFIX}_S3_PREFIX"), "conformance")
    store = build_store(_config(env, prefix))
    try:
        store.health()
        assert run_conformance(store) == []
    finally:
        store.close()


def test_s3_course_export_import_duplicate(tmp_path: Path) -> None:
    env = _require_backend()
    prefix = run_prefix(env.get(f"{ENV_PREFIX}_S3_PREFIX"), "course-smoke")
    config = _config(env, prefix)
    settings = Settings(
        data_dir=tmp_path,
        log_level="WARNING",
        object_storage_backend="s3",
        s3_bucket=config.s3.bucket if config.s3 else "",
        s3_region=config.s3.region if config.s3 else None,
        s3_endpoint_url=config.s3.endpoint_url if config.s3 else None,
        s3_access_key_id=config.s3.access_key_id if config.s3 else None,
        s3_secret_access_key=config.s3.secret_access_key if config.s3 else None,
        s3_session_token=config.s3.session_token if config.s3 else None,
        s3_path_style=config.s3.path_style if config.s3 else True,
        s3_sse=config.s3.sse if config.s3 else "none",
        s3_prefix=prefix,
        s3_verify_tls=config.s3.verify_tls if config.s3 else True,
    )
    app = create_app(
        settings,
        gateway=SmokeGateway(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    try:
        with TestClient(app) as client:
            course = client.post("/api/v1/courses", json={"title": "S3 smoke"})
            assert course.status_code == 201, course.text
            course_id = course.json()["id"]
            payload = b"%PDF-1.4 s3 smoke body"
            uploaded = client.post(
                "/api/v1/materials",
                params={"course_id": course_id},
                files={"file": ("smoke.pdf", payload, "application/pdf")},
            )
            assert uploaded.status_code == 200, uploaded.text
            sha = uploaded.json()["material"]["blob_sha"]
            assert app.state.blobs.get(sha) == payload

            exported = client.get(f"/api/v1/courses/{course_id}/export")
            assert exported.status_code == 200, exported.text
            assert b"blobs/" in exported.content

            imported = client.post("/api/v1/courses/import?dry_run=false", content=exported.content)
            assert imported.status_code == 200, imported.text
            imported_id = imported.json()["imported"]["course_id"]
            imported_materials = client.get(
                "/api/v1/materials", params={"course_id": imported_id}
            ).json()
            assert imported_materials
            imported_sha = imported_materials[0]["blob_sha"]
            assert app.state.blobs.get(imported_sha) == payload

            duplicated = client.post(f"/api/v1/courses/{course_id}/duplicate", json={})
            assert duplicated.status_code == 201, duplicated.text
            duplicate_id = duplicated.json()["course"]["id"]
            duplicate_materials = client.get(
                "/api/v1/materials", params={"course_id": duplicate_id}
            ).json()
            assert duplicate_materials
            assert app.state.blobs.get(duplicate_materials[0]["blob_sha"]) == payload

            for item in list(app.state.objects.list("")):
                app.state.objects.delete(item.key)
    finally:
        app.state.objects.close()
