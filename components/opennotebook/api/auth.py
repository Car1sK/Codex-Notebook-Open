import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from open_notebook.auth_context import (
    DEFAULT_OWNER_ID,
    AuthenticatedUser,
    reset_current_user,
    set_current_user,
)
from open_notebook.utils.encryption import get_secret_from_env

TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _owner_id_for_username(username: str) -> str:
    normalized = username.strip().lower()
    if normalized == DEFAULT_OWNER_ID:
        return DEFAULT_OWNER_ID
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"user_{digest}"


def _token_secret() -> str:
    return (
        get_secret_from_env("OPEN_NOTEBOOK_AUTH_SECRET")
        or get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEY")
        or get_secret_from_env("OPEN_NOTEBOOK_PASSWORD")
        or "open-notebook-development-token-secret"
    )


def _parse_users_from_json(raw: str) -> Dict[str, str]:
    data = json.loads(raw)
    if isinstance(data, dict):
        users: Dict[str, str] = {}
        for username, value in data.items():
            if isinstance(value, str):
                users[str(username)] = value
            elif isinstance(value, dict) and isinstance(value.get("password"), str):
                users[str(username)] = value["password"]
        return users
    if isinstance(data, list):
        users = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            username = item.get("username")
            password = item.get("password")
            if isinstance(username, str) and isinstance(password, str):
                users[username] = password
        return users
    return {}


def configured_users() -> Dict[str, str]:
    """
    Load PaaS-friendly user credentials.

    OPEN_NOTEBOOK_USERS supports either JSON:
      {"alice":"password","bob":{"password":"password"}}
    or newline/comma-separated pairs:
      alice:password,bob:password
    The _FILE variant is supported through get_secret_from_env().
    """
    raw = get_secret_from_env("OPEN_NOTEBOOK_USERS")
    if not raw:
        return {}

    raw = raw.strip()
    if not raw:
        return {}

    if raw.startswith("{") or raw.startswith("["):
        return _parse_users_from_json(raw)

    users: Dict[str, str] = {}
    for item in raw.replace("\n", ",").split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        username, password = item.split(":", 1)
        username = username.strip()
        if username:
            users[username] = password.strip()
    return users


def auth_mode() -> str:
    if configured_users():
        return "multi_user"
    if get_secret_from_env("OPEN_NOTEBOOK_PASSWORD"):
        return "password"
    return "disabled"


def create_access_token(user: AuthenticatedUser) -> str:
    now = int(time.time())
    payload = {
        "sub": user.owner_id,
        "username": user.username,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    body = _b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        _token_secret().encode("utf-8"), body.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{body}.{_b64encode(signature)}"


def _verify_access_token(token: str) -> Optional[AuthenticatedUser]:
    if "." not in token:
        return None
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(
            _token_secret().encode("utf-8"), body.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64decode(signature), expected):
            return None
        payload = json.loads(_b64decode(body).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        username = str(payload.get("username") or payload.get("sub") or "")
        owner_id = str(payload.get("sub") or "")
        if not username or not owner_id:
            return None
        users = configured_users()
        if users:
            if username not in users:
                return None
            if owner_id != _owner_id_for_username(username):
                return None
        return AuthenticatedUser(username=username, owner_id=owner_id)
    except Exception:
        return None


def authenticate_login(
    username: Optional[str], password: str
) -> Optional[AuthenticatedUser]:
    users = configured_users()
    if users:
        if not username:
            return None
        expected = users.get(username)
        if expected and secrets.compare_digest(password, expected):
            return AuthenticatedUser(
                username=username, owner_id=_owner_id_for_username(username)
            )
        return None

    legacy_password = get_secret_from_env("OPEN_NOTEBOOK_PASSWORD")
    if legacy_password and secrets.compare_digest(password, legacy_password):
        return AuthenticatedUser(username=DEFAULT_OWNER_ID, owner_id=DEFAULT_OWNER_ID)

    if not legacy_password:
        return AuthenticatedUser(username=DEFAULT_OWNER_ID, owner_id=DEFAULT_OWNER_ID)

    return None


def authenticate_bearer(credentials: str) -> Optional[AuthenticatedUser]:
    token_user = _verify_access_token(credentials)
    if token_user:
        return token_user

    if configured_users():
        return None

    legacy_password = get_secret_from_env("OPEN_NOTEBOOK_PASSWORD")
    if legacy_password and secrets.compare_digest(credentials, legacy_password):
        return AuthenticatedUser(username=DEFAULT_OWNER_ID, owner_id=DEFAULT_OWNER_ID)

    return None


class PasswordAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to check password authentication for all API requests.
    Always active with default password if OPEN_NOTEBOOK_PASSWORD is not set.
    Supports Docker secrets via OPEN_NOTEBOOK_PASSWORD_FILE.
    """

    def __init__(self, app, excluded_paths: Optional[list] = None):
        super().__init__(app)
        self.excluded_paths = excluded_paths or [
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]

    async def dispatch(self, request: Request, call_next):
        mode = auth_mode()

        # Skip authentication if no password is set
        if mode == "disabled":
            token = set_current_user(
                AuthenticatedUser(username=DEFAULT_OWNER_ID, owner_id=DEFAULT_OWNER_ID)
            )
            try:
                return await call_next(request)
            finally:
                reset_current_user(token)

        # Skip authentication for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        # Skip authentication for CORS preflight requests (OPTIONS)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Expected format: "Bearer {password}"
        try:
            scheme, credentials = auth_header.split(" ", 1)
            if scheme.lower() != "bearer":
                raise ValueError("Invalid authentication scheme")
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authorization header format"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check password
        user = authenticate_bearer(credentials)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid credentials"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        request.state.user = user
        token = set_current_user(user)
        try:
            response = await call_next(request)
            return response
        finally:
            reset_current_user(token)


# Optional: HTTPBearer security scheme for OpenAPI documentation
security = HTTPBearer(auto_error=False)


def check_api_password(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> bool:
    """
    Utility function to check API password.
    Can be used as a dependency in individual routes if needed.
    Supports Docker secrets via OPEN_NOTEBOOK_PASSWORD_FILE.
    Returns True without checking credentials if OPEN_NOTEBOOK_PASSWORD is not configured.
    Raises 401 if credentials are missing or don't match the configured password.
    """
    mode = auth_mode()

    # No password configured - skip authentication
    if mode == "disabled":
        return True

    # No credentials provided
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check password
    if not authenticate_bearer(credentials.credentials):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True


def get_request_user(request: Request) -> AuthenticatedUser:
    user = getattr(request.state, "user", None)
    if user:
        return user
    return AuthenticatedUser(username=DEFAULT_OWNER_ID, owner_id=DEFAULT_OWNER_ID)


def require_default_owner_user(request: Request) -> AuthenticatedUser:
    user = get_request_user(request)
    if user.owner_id != DEFAULT_OWNER_ID:
        raise HTTPException(
            status_code=403,
            detail="This endpoint is restricted to the default administrator account",
        )
    return user


def record_owner_id(record: Any) -> Optional[str]:
    if isinstance(record, dict):
        return record.get("owner_id")
    return getattr(record, "owner_id", None)


def ensure_user_owns(record: Any, user: AuthenticatedUser) -> None:
    owner_id = record_owner_id(record)
    if owner_id == user.owner_id:
        return
    if user.owner_id == DEFAULT_OWNER_ID and not owner_id:
        return
    raise HTTPException(status_code=404, detail="Resource not found")
