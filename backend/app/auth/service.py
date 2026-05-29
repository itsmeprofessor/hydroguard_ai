"""
Auth Service — register, login, refresh, logout logic.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.database import get_db
from app.db.repositories.user_repo import UserRepository
from .schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, AccessTokenResponse


def register(req: RegisterRequest) -> TokenResponse:
    with get_db() as db:
        repo = UserRepository(db)
        if repo.get_by_email(req.email):
            raise HTTPException(status_code=409, detail="Email already registered.")
        if repo.get_by_username(req.username):
            raise HTTPException(status_code=409, detail="Username already taken.")

        # Security: role is ALWAYS "USER" for public registration.
        # Promotion to ANALYST/ADMIN requires a privileged admin workflow.
        user = repo.create(
            email     = req.email,
            username  = req.username,
            hashed_pw = hash_password(req.password),
            role      = "USER",
        )

        access   = create_access_token(user.id, user.role, user.username)
        refresh  = create_refresh_token(user.id)
        role     = user.role
        username = user.username
        repo.update_refresh_token(user, hash_refresh_token(refresh))

    return TokenResponse(
        access_token  = access,
        refresh_token = refresh,
        role          = role,
        username      = username,
    )


def login(req: LoginRequest) -> TokenResponse:
    with get_db() as db:
        repo = UserRepository(db)
        user = repo.get_by_email(req.email)
        if not user or not verify_password(req.password, user.hashed_pw):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account deactivated.")

        access   = create_access_token(user.id, user.role, user.username)
        refresh  = create_refresh_token(user.id)
        role     = user.role
        username = user.username
        repo.update_refresh_token(user, hash_refresh_token(refresh))
        repo.update_last_login(user)

    return TokenResponse(
        access_token  = access,
        refresh_token = refresh,
        role          = role,
        username      = username,
    )


def refresh_tokens(req: RefreshRequest) -> TokenResponse:
    try:
        payload = decode_token(req.refresh_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token.")

    user_id = int(payload["sub"])
    with get_db() as db:
        repo = UserRepository(db)
        user = repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found.")

        expected_hash = hash_refresh_token(req.refresh_token)
        if user.refresh_token_hash != expected_hash:
            # Token reuse detected — invalidate all sessions
            repo.update_refresh_token(user, None)
            raise HTTPException(status_code=401, detail="Refresh token reuse detected. Please log in again.")

        new_access   = create_access_token(user.id, user.role, user.username)
        new_refresh  = create_refresh_token(user.id)
        role         = user.role
        username     = user.username
        # Rotate: store hash of the new token so the old one is invalid on next use
        repo.update_refresh_token(user, hash_refresh_token(new_refresh))

    return TokenResponse(
        access_token  = new_access,
        refresh_token = new_refresh,
        role          = role,
        username      = username,
    )


def logout(user_id: int) -> None:
    with get_db() as db:
        repo = UserRepository(db)
        user = repo.get_by_id(user_id)
        if user:
            repo.update_refresh_token(user, None)
