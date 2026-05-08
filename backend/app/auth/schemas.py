"""Auth Pydantic schemas.

SECURITY NOTE: `role` has been intentionally removed from RegisterRequest.
All new accounts receive `role = USER`. Promotion to ANALYST or ADMIN must
be done through a privileged administrative workflow (e.g., admin CLI or
a dedicated /admin/users/{id}/role endpoint requiring ADMIN JWT).
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    email:    str = Field(..., description="Valid email address")
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    # role is NOT accepted here — all registrations default to USER.
    # This prevents privilege escalation via the public registration endpoint.

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("username")
    @classmethod
    def username_clean(cls, v: str) -> str:
        v = v.strip()
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username may only contain letters, numbers, _ and -")
        return v


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


class RoleUpdateRequest(BaseModel):
    """Used by admin-only role-promotion endpoint."""
    role: str = Field(..., pattern="^(ADMIN|ANALYST|USER)$")
