from collections.abc import Iterator
from urllib.parse import quote

from fastapi import Depends, Header, HTTPException, Request
from nx_auth.deps import get_current_user
from nx_auth.principal import Principal
from sqlalchemy.orm import Session

from ..core.profile_context import active_profile_id
from ..storage.object_storage import (
    InvalidObjectKey,
    ObjectNotFound,
    ObjectTooLarge,
    StorageAuthError,
    StorageConfigError,
    StorageError,
    StorageUnavailable,
    UnsupportedOperation,
)


def require_admin(user: Principal = Depends(get_current_user)) -> Principal:
    """Admin-only surfaces (destructive ops) — desktop's owner is admin."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin access required")
    return user


def storage_http_exception(error: StorageError) -> HTTPException:
    """Map a contract error to the host HTTP surface (never a bare 500)."""
    if isinstance(error, ObjectTooLarge):
        status = 413
    elif isinstance(error, ObjectNotFound):
        status = 404
    elif isinstance(error, UnsupportedOperation):
        status = 409
    elif isinstance(error, StorageUnavailable):
        status = 503
    elif isinstance(error, (StorageAuthError, StorageConfigError, InvalidObjectKey)):
        status = 500
    else:
        status = 500
    return HTTPException(status_code=status, detail=str(error))


def require_local_blob_storage(request: Request) -> None:
    """Desktop/local-filesystem backup & restore are not object-storage features.

    A cloud profile has no mounted blob tree to archive or restore into; the
    provider owns durability. Refuse clearly instead of producing an archive
    with an empty ``blobs/`` section.
    """
    blobs = getattr(request.app.state, "blobs", None)
    if blobs is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "backup/restore is unavailable: blob storage is not initialized for this process"
            ),
        )
    try:
        blobs.local_root()
    except UnsupportedOperation as error:
        raise HTTPException(
            status_code=409,
            detail=(
                "backup/restore is a desktop/local-filesystem feature; "
                "object storage is provider-durable and cannot be archived here"
            ),
        ) from error


def content_disposition(filename: str, kind: str = "attachment") -> str:
    safe = filename.replace('"', "'").replace("\r", " ").replace("\n", " ")
    try:
        safe.encode("latin-1")
    except UnicodeEncodeError:
        fallback = safe.encode("ascii", "ignore").decode("ascii") or "file"
        return f"{kind}; filename=\"{fallback}\"; filename*=UTF-8''{quote(safe)}"
    return f'{kind}; filename="{safe}"'


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    with factory() as session:
        yield session


def get_profile_id(
    request: Request,
    x_profile_id: str | None = Header(default=None),
) -> str:
    """The request's bound profile (identity-auth §15).

    `ProfileBindingMiddleware` validated ownership already — trust its
    context, never the raw header.
    """
    del request, x_profile_id
    profile_id = active_profile_id()
    if profile_id is None:
        raise HTTPException(status_code=400, detail="X-Profile-Id required")
    return profile_id
