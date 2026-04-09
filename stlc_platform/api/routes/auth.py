"""Auth routes: login and token refresh."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from stlc_platform.api.auth import (
    AUTH_ENABLED,
    JWT_EXPIRE_SECONDS,
    authenticate_user,
    create_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthStatusResponse(BaseModel):
    auth_enabled: bool


@router.get("/status", response_model=AuthStatusResponse)
def auth_status():
    """Return whether authentication is enabled."""
    return AuthStatusResponse(auth_enabled=AUTH_ENABLED)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """Authenticate and return a JWT token."""
    if not AUTH_ENABLED:
        # When auth is disabled, return a viewer-role token (not admin)
        token = create_token("anonymous", "viewer")
        return TokenResponse(access_token=token, expires_in=JWT_EXPIRE_SECONDS)

    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_token(user.username, user.role)
    return TokenResponse(access_token=token, expires_in=JWT_EXPIRE_SECONDS)
