"""
FastAPI dependency factories.
Backward-compatible: require_admin still works for legacy callers that pass X-Admin-Token.
New endpoints use require_role() / get_current_user().
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import ADMIN_TOKEN
from app.core.security import decode_token

_bearer = HTTPBearer(auto_error=False)


# ── JWT-based ────────────────────────────────────────────────────────────────

def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> dict:
    if not creds:
        raise HTTPException(status_code=401, detail="Authorization header missing.")
    try:
        payload = decode_token(creds.credentials)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Not an access token.")
    return payload


def require_role(*roles: str):
    """Factory: returns a Depends() that enforces one of the given roles."""
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of roles: {roles}. Your role: {user.get('role')}",
            )
        return user
    return _check


# ── Legacy token-header (kept for backward compat) ──────────────────────────

def require_admin(
    x_admin_token: Optional[str] = Header(None),
    creds: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> None:
    """
    Accept either:
      - Legacy: X-Admin-Token header with the ADMIN_TOKEN value
      - JWT:    Bearer token with role=ADMIN
    """
    # JWT path
    if creds:
        try:
            payload = decode_token(creds.credentials)
            if payload.get("role") == "ADMIN":
                return
        except ValueError:
            pass

    # Legacy header path
    if x_admin_token and x_admin_token == ADMIN_TOKEN:
        return

    raise HTTPException(status_code=401, detail="Admin access required.")
