"""Password hashing and JWT authentication for the dashboard."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError

from .config import Settings

ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, role: str, settings: Settings) -> str:
    expires = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": str(user_id), "role": role, "exp": expires},
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str, settings: Settings) -> dict[str, object] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except InvalidTokenError:
        return None


def current_user_dependency(settings: Settings, store):
    async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> dict[str, object]:
        if not settings.dashboard_auth_enabled:
            user = await store.get_user_by_username(settings.admin_username)
            if user is None or not user["is_active"]:
                raise HTTPException(status_code=503, detail="Demo administrator is unavailable")
            return user
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        payload = decode_access_token(token, settings)
        if payload is None or not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = await store.get_user_by_id(int(str(payload["sub"])))
        if user is None or not user["is_active"]:
            raise HTTPException(status_code=401, detail="Account is unavailable")
        return user

    return get_current_user
