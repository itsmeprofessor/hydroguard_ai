"""Auth endpoints: /auth/*"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_current_user
from app.core.limiter import limiter
from app.db.database import get_db
from app.db.repositories.user_repo import UserRepository
from .schemas import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserProfile,
)
from . import service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, req: RegisterRequest):
    return service.register(req)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, req: LoginRequest):
    return service.login(req)


@router.post("/refresh", response_model=AccessTokenResponse)
@limiter.limit("20/minute")
async def refresh(request: Request, req: RefreshRequest):
    return service.refresh_tokens(req)


@router.get("/me", response_model=UserProfile)
async def me(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["sub"])
    with get_db() as db:
        user = UserRepository(db).get_by_id(user_id)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found.")
    return UserProfile(
        id         = user.id,
        email      = user.email,
        username   = user.username,
        role       = user.role,
        is_active  = user.is_active,
        created_at = user.created_at.isoformat() if user.created_at else None,
    )


@router.post("/logout", status_code=204)
async def logout(current_user: dict = Depends(get_current_user)):
    service.logout(int(current_user["sub"]))
