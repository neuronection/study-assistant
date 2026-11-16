"""Storage bootstrap for the family object-storage contract (ADR-0057).

`Settings` is the single source of truth: `.env`/OS env values populate the
canonical `SA_*` fields, and this module maps those resolved values into the
contract's environment mapping. The contract never needs to read
`os.environ` itself (which would miss `.env`-only values).
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.config import Settings
from ..core.limits import MAX_UPLOAD_MB
from .object_storage import (
    ENTRYPOINT_DESKTOP,
    ENTRYPOINT_SERVER,
    ObjectStore,
    StorageConfig,
    StorageError,
    build_store,
)

logger = logging.getLogger(__name__)

_ENV_FIELDS = {
    "CLOUD_PROFILE": "cloud_profile",
    "OBJECT_STORAGE_BACKEND": "object_storage_backend",
    "OBJECT_STORAGE_REQUIRED": "object_storage_required",
    "OBJECT_STORAGE_LOCAL_ROOT": "object_storage_local_root",
    "OBJECT_STORAGE_MAX_MB": "object_storage_max_mb",
    "OBJECT_STORAGE_PRESIGN_TTL": "object_storage_presign_ttl",
    "S3_BUCKET": "s3_bucket",
    "S3_REGION": "s3_region",
    "S3_ENDPOINT_URL": "s3_endpoint_url",
    "S3_ACCESS_KEY_ID": "s3_access_key_id",
    "S3_SECRET_ACCESS_KEY": "s3_secret_access_key",
    "S3_SESSION_TOKEN": "s3_session_token",
    "S3_PATH_STYLE": "s3_path_style",
    "S3_SSE": "s3_sse",
    "S3_KMS_KEY_ID": "s3_kms_key_id",
    "S3_PREFIX": "s3_prefix",
    "S3_VERIFY_TLS": "s3_verify_tls",
    "S3_CONNECT_TIMEOUT": "s3_connect_timeout",
    "S3_READ_TIMEOUT": "s3_read_timeout",
    "S3_MAX_ATTEMPTS": "s3_max_attempts",
    "AZURE_STORAGE_CONTAINER": "azure_storage_container",
    "AZURE_STORAGE_CONNECTION_STRING": "azure_storage_connection_string",
    "AZURE_STORAGE_ACCOUNT_URL": "azure_storage_account_url",
    "AZURE_STORAGE_ACCOUNT_NAME": "azure_storage_account_name",
    "AZURE_STORAGE_CREDENTIAL": "azure_storage_credential",
    "AZURE_STORAGE_PREFIX": "azure_storage_prefix",
    "AZURE_CONNECT_TIMEOUT": "azure_connect_timeout",
    "AZURE_READ_TIMEOUT": "azure_read_timeout",
    "AZURE_MAX_ATTEMPTS": "azure_max_attempts",
}


def storage_entrypoint(settings: Settings) -> str:
    mode = getattr(settings.identity_mode, "value", settings.identity_mode)
    return ENTRYPOINT_DESKTOP if str(mode) == "desktop" else ENTRYPOINT_SERVER


def _env_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    return text or None


def storage_env(settings: Settings) -> dict[str, str]:
    """The contract's ``SA_*`` mapping from the resolved Settings values."""
    env: dict[str, str] = {}
    for name, field in _ENV_FIELDS.items():
        value = _env_value(getattr(settings, field, None))
        if value is not None:
            env[f"SA_{name}"] = value
    return env


def _host_max_upload_mb() -> int:
    """Study's host upload ceiling as the default object-size cap."""
    return MAX_UPLOAD_MB


def resolve_storage_config(settings: Settings) -> StorageConfig:
    """Validate the deployment storage configuration (raises at boot)."""
    env = storage_env(settings)
    env.setdefault("SA_OBJECT_STORAGE_MAX_MB", str(_host_max_upload_mb()))
    return StorageConfig.from_env(
        env,
        "SA",
        entrypoint=storage_entrypoint(settings),
        default_local_root=settings.blobs_dir,
    )


def storage_target(config: StorageConfig) -> str:
    """The bucket/container name, or the local root for the filesystem backend."""
    if config.s3 is not None:
        return config.s3.bucket
    if config.azure_blob is not None:
        return config.azure_blob.container
    return str(config.local_root or "")


def storage_sse(config: StorageConfig) -> str:
    """The encryption mode the store applies; Azure encrypts provider-side."""
    if config.s3 is not None:
        return config.s3.sse
    if config.azure_blob is not None:
        return "provider-managed"
    return "n/a"


def log_storage_boot(config: StorageConfig) -> None:
    """Log one redacted storage boot line: no credentials, no endpoints."""
    logger.info(
        "object storage: backend=%s bucket/container=%s prefix=%s sse=%s",
        config.backend,
        storage_target(config),
        config.key_prefix or "-",
        storage_sse(config),
    )


def open_configured_store(settings: Settings) -> tuple[StorageConfig, ObjectStore]:
    """Build and health-probe the configured store; close it on probe failure."""
    config = resolve_storage_config(settings)
    store = build_store(config)
    try:
        store.health()
    except StorageError:
        store.close()
        raise
    log_storage_boot(config)
    return config, store
