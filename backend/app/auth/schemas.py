"""Auth Pydantic schemas."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email:    str = Field(..., description="Valid email address")
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    role:     str = Field("USER", pattern="^(ADMIN|ANALYST|USER)$")

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: str) -> str:
        return v.strip().lower()


class LoginRequest(BaseModel):
    email:    str
    password: str

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: str) -> str:
        return v.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    role:          str
    username:      str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"


class UserProfile(BaseModel):
    id:         int
    email:      str
    username:   str
    role:       str
    is_active:  bool
    created_at: Optional[str] = None
