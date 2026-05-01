from .anomaly_repo import AnomalyRepository
from .training_repo import TrainingRepository

__all__ = ["AnomalyRepository", "TrainingRepository"]
# UserRepository is intentionally NOT imported here to break the circular:
#   db/__init__ → user_repo → app.auth.models → app/auth/__init__ → auth.router → user_repo
# Import UserRepository directly: from app.db.repositories.user_repo import UserRepository
