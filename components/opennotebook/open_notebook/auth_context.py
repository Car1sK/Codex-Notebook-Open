from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

DEFAULT_OWNER_ID = "default"


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    owner_id: str


_current_user: ContextVar[Optional[AuthenticatedUser]] = ContextVar(
    "current_open_notebook_user", default=None
)


def set_current_user(user: Optional[AuthenticatedUser]):
    return _current_user.set(user)


def reset_current_user(token) -> None:
    _current_user.reset(token)


def get_current_user() -> Optional[AuthenticatedUser]:
    return _current_user.get()


def get_current_owner_id() -> Optional[str]:
    user = get_current_user()
    return user.owner_id if user else None


def is_owner_allowed(record_owner_id: Optional[str], owner_id: Optional[str]) -> bool:
    if owner_id is None:
        return True
    if record_owner_id == owner_id:
        return True
    return owner_id == DEFAULT_OWNER_ID and not record_owner_id
