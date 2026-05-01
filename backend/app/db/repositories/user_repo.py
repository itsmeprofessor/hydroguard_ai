"""UserRepository — CRUD for User model."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.auth.models import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()

    def get_by_username(self, username: str) -> Optional[User]:
        return self.db.query(User).filter(User.username == username).first()

    def create(
        self,
        email: str,
        username: str,
        hashed_pw: str,
        role: str = "USER",
    ) -> User:
        user = User(email=email, username=username, hashed_pw=hashed_pw, role=role)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_refresh_token(self, user: User, token_hash: Optional[str]) -> None:
        user.refresh_token_hash = token_hash
        self.db.commit()

    def update_last_login(self, user: User) -> None:
        from datetime import datetime
        user.last_login = datetime.utcnow()
        self.db.commit()
