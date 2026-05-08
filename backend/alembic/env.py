"""
Alembic environment configuration for HydroGuard-AI.
Reads DATABASE_URL from environment (same as app).
Imports all ORM models so their tables are included in autogenerate.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add backend/ to path so app imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env so DATABASE_URL is available
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Import Base and all models so metadata is populated
from app.db.database import Base  # noqa: E402

# Import all models to register them on Base.metadata
from app.db.models.user import User  # noqa: E402, F401
from app.db.database import AnomalyRecord, TrainingRecord  # noqa: E402, F401

alembic_cfg = context.config

# Override sqlalchemy.url with env variable
database_url = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{Path(__file__).parent.parent / 'weather_anomalies.db'}",
)
alembic_cfg.set_main_option("sqlalchemy.url", database_url)

if alembic_cfg.config_file_name is not None:
    fileConfig(alembic_cfg.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = alembic_cfg.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # For SQLite: use StaticPool to avoid threading issues
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    configuration = alembic_cfg.get_section(alembic_cfg.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.StaticPool if database_url.startswith("sqlite") else pool.NullPool,
        connect_args=connect_args,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
