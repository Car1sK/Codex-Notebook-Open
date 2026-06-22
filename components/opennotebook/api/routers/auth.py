"""
Authentication router for Open Notebook API.
Provides endpoints to check authentication status.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.auth import (
    auth_mode,
    authenticate_login,
    configured_users,
    create_access_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: Optional[str] = None
    password: str


@router.get("/status")
async def get_auth_status():
    """
    Check if authentication is enabled.
    Returns whether a password is required to access the API.
    Supports Docker secrets via OPEN_NOTEBOOK_PASSWORD_FILE.
    """
    mode = auth_mode()
    auth_enabled = mode != "disabled"

    return {
        "auth_enabled": auth_enabled,
        "auth_mode": mode,
        "multi_user": mode == "multi_user",
        "message": "Authentication is required"
        if auth_enabled
        else "Authentication is disabled",
    }


@router.post("/login")
async def login(request: LoginRequest):
    user = authenticate_login(request.username, request.password)
    if not user:
        users_configured = bool(configured_users())
        detail = "Invalid username or password" if users_configured else "Invalid password"
        raise HTTPException(status_code=401, detail=detail)

    return {
        "token": create_access_token(user),
        "user": {
            "username": user.username,
            "owner_id": user.owner_id,
        },
    }
