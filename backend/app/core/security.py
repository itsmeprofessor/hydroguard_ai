"""
HydroGuard-AI — Security Core
==============================
JWT encode/decode + bcrypt password hashing.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import bcrypt as _bcrypt
from jose import JWTError, jwt

# Import the config MODULE (not the value) so any runtime patch to
# config.JWT_SECRET_KEY is picked up at call time rather than import time.
from app.core import config as _cfg


def hash_password(plain: str) -> str:
    # bcrypt 4+ requires bytes; truncate to 72 bytes (bcrypt hard limit)
    return _bcrypt.hashpw(plain.encode()[:72], _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode()[:72], hashed.encode())


def create_access_token(user_id: int, role: str, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_cfg.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub":      str(user_id),
        "role":     role,
        "username": username,
        "exp":      expire,
        "type":     "access",
        "jti":      str(uuid.uuid4()),
    }
    return jwt.encode(payload, _cfg.JWT_SECRET_KEY, algorithm=_cfg.JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=_cfg.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub":  str(user_id),
        "exp":  expire,
        "type": "refresh",
        "jti":  str(uuid.uuid4()),
    }
    return jwt.encode(payload, _cfg.JWT_SECRET_KEY, algorithm=_cfg.JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, _cfg.JWT_SECRET_KEY, algorithms=[_cfg.JWT_ALGORITHM])
    except JWTError as e:
        raise ValueError(f"Invalid or expired token: {e}") from e


def hash_refresh_token(token: str) -> str:
    """SHA-256 fingerprint stored in DB — full token is never persisted."""
    return hashlib.sha256(token.encode()).hexdigest()
