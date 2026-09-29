from contextvars import ContextVar, Token

_active_profile_id: ContextVar[str | None] = ContextVar("active_profile_id", default=None)
_active_user_id: ContextVar[str | None] = ContextVar("active_user_id", default=None)


def set_active_profile(profile_id: str | None) -> Token[str | None]:
    return _active_profile_id.set(profile_id)


def reset_active_profile(token: Token[str | None]) -> None:
    _active_profile_id.reset(token)


def active_profile_id() -> str | None:
    return _active_profile_id.get()


def set_active_user(user_id: str | None) -> Token[str | None]:
    return _active_user_id.set(user_id)


def reset_active_user(token: Token[str | None]) -> None:
    _active_user_id.reset(token)


def active_user_id() -> str | None:
    return _active_user_id.get()
