"""
Authentication module for STLC Platform API.
Supports JWT tokens and API key authentication.
Disabled by default — enable via STLC_AUTH_ENABLED=true.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Lazy imports for optional deps
_jwt = None
_passlib_ctx = None


def _ensure_jwt():
    global _jwt
    if _jwt is None:
        try:
            import jwt

            _jwt = jwt
        except ImportError:
            raise ImportError(
                "PyJWT required when auth is enabled: pip install PyJWT"
            )
    return _jwt


def _ensure_passlib():
    global _passlib_ctx
    if _passlib_ctx is None:
        try:
            from passlib.context import CryptContext

            _passlib_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        except ImportError:
            raise ImportError(
                "passlib required when auth is enabled: pip install passlib[bcrypt]"
            )
    return _passlib_ctx


# Configuration
AUTH_ENABLED = os.environ.get("STLC_AUTH_ENABLED", "false").lower() == "true"
JWT_SECRET = os.environ.get(
    "STLC_JWT_SECRET", "stlc-dev-secret-change-in-production"
)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_SECONDS = int(os.environ.get("STLC_JWT_EXPIRE_SECONDS", "3600"))
API_KEYS = set(filter(None, os.environ.get("STLC_API_KEYS", "").split(",")))
ADMIN_USER = os.environ.get("STLC_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("STLC_ADMIN_PASSWORD", "admin")


@dataclass
class AuthUser:
    username: str
    role: str = "user"


security = HTTPBearer(auto_error=False)


def create_token(username: str, role: str = "user") -> str:
    """Create a signed JWT token for the given user."""
    jwt_mod = _ensure_jwt()
    payload = {
        "sub": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRE_SECONDS,
    }
    return str(jwt_mod.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM))


def verify_token(token: str) -> AuthUser:
    """Decode and validate a JWT token, returning the AuthUser."""
    jwt_mod = _ensure_jwt()
    try:
        payload = jwt_mod.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return AuthUser(
            username=payload["sub"], role=payload.get("role", "user")
        )
    except jwt_mod.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        )
    except jwt_mod.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


def verify_password(plain: str, username: str) -> bool:
    """Simple username/password check against env vars."""
    return username == ADMIN_USER and plain == ADMIN_PASSWORD


def authenticate_user(username: str, password: str) -> Optional[AuthUser]:
    """Authenticate a user by username and password."""
    if verify_password(password, username):
        return AuthUser(username=username, role="admin")
    return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[AuthUser]:
    """FastAPI dependency: returns AuthUser if auth enabled, None if disabled."""
    if not AUTH_ENABLED:
        return AuthUser(username="anonymous", role="admin")

    # Check API key header first
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key in API_KEYS:
        return AuthUser(username="api-key-user", role="admin")

    # Check Bearer token
    if credentials and credentials.credentials:
        return verify_token(credentials.credentials)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
