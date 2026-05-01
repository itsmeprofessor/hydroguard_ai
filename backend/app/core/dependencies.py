"""Re-exports API dependency factories for use outside the api/ package."""
from app.api.deps import get_current_user, require_role, require_admin

__all__ = ["get_current_user", "require_role", "require_admin"]
