"""
Shared FastAPI dependencies.
"""

from typing import Optional

from fastapi import Header, HTTPException

from app.core.config import ADMIN_TOKEN


def require_admin(x_admin_token: Optional[str] = Header(None)) -> None:
    """Dependency: reject requests without a valid admin token."""
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token.")
