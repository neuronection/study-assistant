"""Opt-in Azure Blob smoke test for the object-storage contract.

Normal PRs do not need credentials: without ``SA_TEST_AZURE_CONTAINER`` and
either a connection string or a managed-identity account URL this module
skips, even when the network opt-out is unset. The session ``_no_network``
fixture blocks connects by default, so a real smoke also sets
``SA_TEST_ALLOW_NETWORK=1``:

    SA_TEST_ALLOW_NETWORK=1 \\
    SA_TEST_AZURE_CONTAINER=study-data \\
    SA_TEST_AZURE_CONNECTION_STRING='DefaultEndpointsProtocol=https;...' \\
    SA_TEST_AZURE_PREFIX=test/smoke \\
    uv run --directory backend --with azure-storage-blob \\
      pytest -q tests/test_object_storage_azure.py

Managed identity instead of a connection string:

    SA_TEST_ALLOW_NETWORK=1 SA_TEST_AZURE_CONTAINER=study-data \\
    SA_TEST_AZURE_ACCOUNT_URL=https://study.blob.core.windows.net \\
    SA_TEST_AZURE_ACCOUNT_NAME=study \\
    SA_TEST_AZURE_CREDENTIAL=managed_identity \\
    uv run --directory backend --with azure-storage-blob --with azure-identity \\
      pytest -q tests/test_object_storage_azure.py

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
    BACKEND_AZURE_BLOB,
    ENTRYPOINT_SERVER,
    AzureBlobConfig,
    StorageConfig,
    build_store,
    run_conformance,
)

ENV_PREFIX = "SA_TEST"
CONTAINER = f"{ENV_PREFIX}_AZURE_CONTAINER"
CONNECTION_STRING = f"{ENV_PREFIX}_AZURE_CONNECTION_STRING"
ACCOUNT_URL = f"{ENV_PREFIX}_AZURE_ACCOUNT_URL"
ACCOUNT_NAME = f"{ENV_PREFIX}_AZURE_ACCOUNT_NAME"
CREDENTIAL = f"{ENV_PREFIX}_AZURE_CREDENTIAL"
PREFIX = f"{ENV_PREFIX}_AZURE_PREFIX"


def _managed_identity(env: dict[str, str]) -> bool:
    return bool(
        env.get(ACCOUNT_URL) and (env.get(CREDENTIAL) or "").strip().lower() == "managed_identity"
    )


def _require_backend() -> tuple[dict[str, str], bool]:
    env = env_values(ENV_PREFIX)
    if not env.get(CONTAINER):
        pytest.skip(f"Azure smoke disabled; set {CONTAINER}")
    managed = _managed_identity(env)
    if not env.get(CONNECTION_STRING) and not managed:
        pytest.skip(
            "Azure smoke disabled; set "
            f"{CONNECTION_STRING} or {ACCOUNT_URL} + {CREDENTIAL}=managed_identity"
        )
    pytest.importorskip("azure.storage.blob")
    if managed:
        pytest.importorskip("azure.identity")
    return env, managed


def _config(env: dict[str, str], prefix: str, managed: bool) -> StorageConfig:
    return StorageConfig(
        backend=BACKEND_AZURE_BLOB,
        entrypoint=ENTRYPOINT_SERVER,
        cloud_profile="azure",
        required=True,
        azure_blob=AzureBlobConfig(
            container=env[CONTAINER],
            connection_string=None if managed else env.get(CONNECTION_STRING),
            account_url=env.get(ACCOUNT_URL) if managed else None,
            account_name=env.get(ACCOUNT_NAME),
            managed_identity=managed,
            prefix=prefix,
        ),
    ).validate()


def _prefix(env: dict[str, str]) -> str:
    return run_prefix(env.get(PREFIX), "smoke")


def test_azure_conformance() -> None:
    env, managed = _require_backend()
    store = build_store(_config(env, _prefix(env), managed))
    try:
        store.health()
        assert run_conformance(store) == []
    finally:
        try:
            for item in list(store.list("")):
                store.delete(item.key)
        finally:
            store.close()


def test_azure_course_export_import_duplicate(tmp_path: Path) -> None:
    env, managed = _require_backend()
    prefix = _prefix(env)
    config = _config(env, prefix, managed)
    azure = config.azure_blob
    assert azure is not None
    settings = Settings(
        data_dir=tmp_path,
        log_level="WARNING",
        cloud_profile="azure",
        object_storage_backend="azure_blob",
        object_storage_required=True,
        azure_storage_container=azure.container,
        azure_storage_connection_string=azure.connection_string,
        azure_storage_account_url=azure.account_url,
        azure_storage_account_name=azure.account_name,
        azure_storage_credential="managed_identity" if managed else None,
        azure_storage_prefix=prefix,
    )
    app = create_app(
        settings,
        gateway=SmokeGateway(),
        embedder=NoAI(),  # type: ignore[arg-type]
        describer=NoAI(),  # type: ignore[arg-type]
    )
    try:
        with TestClient(app) as client:
            course = client.post("/api/v1/courses", json={"title": "Azure smoke"})
            assert course.status_code == 201, course.text
            course_id = course.json()["id"]
            payload = b"%PDF-1.4 azure smoke body"
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
            assert app.state.blobs.get(imported_materials[0]["blob_sha"]) == payload

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
