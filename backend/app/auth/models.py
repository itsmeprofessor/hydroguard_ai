"""
Backward-compat shim.
The canonical User model is now at app.db.models.user.
This module re-exports it so existing imports (from app.auth.models import User) continue to work.
"""
from app.db.models.user import User  # noqa: F401

__all__ = ["User"]
