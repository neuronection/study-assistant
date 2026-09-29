from collections.abc import Iterator
from urllib.parse import quote

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.profile_context import active_profile_id


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
