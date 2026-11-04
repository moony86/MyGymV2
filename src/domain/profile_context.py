from contextvars import ContextVar

DEFAULT_PROFILE_ID = "00000000-0000-0000-0000-000000000001"

_current_profile_id: ContextVar[str] = ContextVar(
    "current_profile_id", default=DEFAULT_PROFILE_ID
)


def set_current_profile_id(profile_id: str):
    return _current_profile_id.set(profile_id or DEFAULT_PROFILE_ID)


def reset_current_profile_id(token) -> None:
    _current_profile_id.reset(token)


def get_current_profile_id() -> str:
    return _current_profile_id.get()
