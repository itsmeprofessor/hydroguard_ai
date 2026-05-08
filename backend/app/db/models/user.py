"""
User ORM model — canonical location.
app/auth/models.py is a backward-compat shim that re-exports from here.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id                 = Column(Integer, primary_key=True, index=True)
    email              = Column(String(255), unique=True, index=True, nullable=False)
    username           = Column(String(100), unique=True, index=True, nullable=False)
    hashed_pw          = Column(String(255), nullable=False)
    role               = Column(String(20), default="USER")   # ADMIN | ANALYST | USER
    is_active          = Column(Boolean, default=True)
    last_login         = Column(DateTime(timezone=True), nullable=True)
    refresh_token_hash = Column(String(255), nullable=True)
    created_at         = Column(DateTime(timezone=True),
                                default=lambda: datetime.now(timezone.utc))
