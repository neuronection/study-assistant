from collections.abc import Iterator
from urllib.parse import quote

from fastapi import Header, Request
from sqlalchemy.orm import Session

from ..services.platform.profiles import get_profile


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
    x_profile_id: int | None = Header(default=None),
) -> int:
    with request.app.state.session_factory() as session:
        profile = get_profile(session, x_profile_id)
        if profile is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="profile not found")
        return profile.id
