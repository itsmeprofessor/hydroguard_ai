"""
Shared pytest configuration for HydroGuard-AI tests.
Sets required env vars BEFORE any app module is imported.
"""
import os
import sys
import types
from pathlib import Path

# Must happen before any app.* import (pytest loads conftest first)
os.environ.setdefault("JWT_SECRET_KEY",  "test-jwt-secret-key-32chars-abc")
os.environ.setdefault("REDIS_URL",       "redis://localhost:6379/0")
os.environ.setdefault("DATABASE_URL",    "sqlite:///./test_hydroguard.db")
os.environ.setdefault("DEBUG",           "true")
os.environ.setdefault("WEATHERAPI_KEY",  "")   # empty — no live weather in tests

# Patch dotenv so it doesn't overwrite the env vars we just set
dotenv_mod = types.ModuleType("dotenv")
dotenv_mod.load_dotenv = lambda *a, **k: None
sys.modules["dotenv"] = dotenv_mod

# Add backend to path
BACKEND = Path(__file__).parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
