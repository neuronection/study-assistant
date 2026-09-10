from contextvars import ContextVar, Token

_active_profile_id: ContextVar[int | None] = ContextVar("active_profile_id", default=None)


def set_active_profile(profile_id: int | None) -> Token[int | None]:
    return _active_profile_id.set(profile_id)


def reset_active_profile(token: Token[int | None]) -> None:
    _active_profile_id.reset(token)


def active_profile_id() -> int | None:
    return _active_profile_id.get()
