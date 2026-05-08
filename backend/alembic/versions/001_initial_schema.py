"""Initial schema with v2 traceability columns.

Revision ID: 001_initial
Revises:
Create Date: 2026-05-04

Baseline tables matching current ORM models + inference_id / model_version
columns on anomaly_records for v2 prediction traceability.

Idempotent: uses IF NOT EXISTS logic so it is safe to run against an
existing database that was created by the old Base.metadata.create_all().
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision      = "001_initial"
down_revision = None
branch_labels = None
depends_on    = None


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    return name in inspect(op.get_bind()).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect
    return column in {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


# ─────────────────────────────────────────────────────────────
#  Upgrade
# ─────────────────────────────────────────────────────────────

def upgrade() -> None:
    # ── users ────────────────────────────────────────────────
    if not _table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id",                 sa.Integer(),            primary_key=True, index=True),
            sa.Column("email",              sa.String(255),          unique=True, nullable=False),
            sa.Column("username",           sa.String(100),          unique=True, nullable=False),
            sa.Column("hashed_pw",          sa.String(255),          nullable=False),
            sa.Column("role",               sa.String(20),           server_default="USER"),
            sa.Column("is_active",          sa.Boolean(),            server_default=sa.text("1")),
            sa.Column("last_login",         sa.DateTime(timezone=True), nullable=True),
            sa.Column("refresh_token_hash", sa.String(255),          nullable=True),
            sa.Column("created_at",         sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )

    # ── anomaly_records ──────────────────────────────────────
    if not _table_exists("anomaly_records"):
        op.create_table(
            "anomaly_records",
            sa.Column("id",          sa.Integer(), primary_key=True, index=True),
            sa.Column("city",        sa.String(100),  index=True),
            sa.Column("region",      sa.String(100),  index=True),
            sa.Column("date",        sa.DateTime(timezone=True), index=True),
            sa.Column("tmin",        sa.Float(), nullable=True),
            sa.Column("tmax",        sa.Float(), nullable=True),
            sa.Column("tavg",        sa.Float(), nullable=True),
            sa.Column("prcp",        sa.Float(), nullable=True),
            sa.Column("wspd",        sa.Float(), nullable=True),
            sa.Column("humidity",    sa.Float(), nullable=True),
            sa.Column("pressure",    sa.Float(), nullable=True),
            sa.Column("dew_point",   sa.Float(), nullable=True),
            sa.Column("cloud_cover", sa.Float(), nullable=True),
            sa.Column("anomaly_score",            sa.Float(), nullable=False),
            sa.Column("threshold",                sa.Float(), nullable=False),
            sa.Column("is_anomaly",               sa.Boolean(), nullable=False),
            sa.Column("risk_level",               sa.String(20),  index=True),
            sa.Column("hri_score",                sa.Integer(), nullable=True),
            sa.Column("hri_label",                sa.String(20), nullable=True),
            sa.Column("cloudburst_risk_score",    sa.Float(), nullable=True),
            sa.Column("cloudburst_risk_category", sa.String(20), nullable=True),
            sa.Column("is_cloudburst_likely",     sa.Boolean(),
                      server_default=sa.text("0")),
            sa.Column("remarks",               sa.Text(),    nullable=True),
            sa.Column("feature_contributions", sa.JSON(),    nullable=True),
            sa.Column("detailed_explanation",  sa.JSON(),    nullable=True),
            sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
            # v2 traceability
            sa.Column("inference_id",  sa.String(36), nullable=True),
            sa.Column("model_version", sa.String(64), nullable=True),
        )
    else:
        # Add v2 columns to existing table if absent
        if not _column_exists("anomaly_records", "inference_id"):
            op.add_column("anomaly_records",
                          sa.Column("inference_id", sa.String(36), nullable=True))
        if not _column_exists("anomaly_records", "model_version"):
            op.add_column("anomaly_records",
                          sa.Column("model_version", sa.String(64), nullable=True))

    # ── training_records ─────────────────────────────────────
    if not _table_exists("training_records"):
        op.create_table(
            "training_records",
            sa.Column("id",                        sa.Integer(), primary_key=True, index=True),
            sa.Column("training_started",          sa.DateTime(timezone=True), nullable=False),
            sa.Column("training_completed",        sa.DateTime(timezone=True), nullable=True),
            sa.Column("training_duration_seconds", sa.Float(), nullable=True),
            sa.Column("total_samples",             sa.Integer()),
            sa.Column("train_samples",             sa.Integer()),
            sa.Column("validation_samples",        sa.Integer()),
            sa.Column("num_cities",                sa.Integer()),
            sa.Column("cities",                    sa.JSON()),
            sa.Column("date_range_start",          sa.DateTime(timezone=True)),
            sa.Column("date_range_end",            sa.DateTime(timezone=True)),
            sa.Column("final_loss",                sa.Float()),
            sa.Column("final_val_loss",            sa.Float()),
            sa.Column("epochs_trained",            sa.Integer()),
            sa.Column("threshold",                 sa.Float()),
            sa.Column("lstm_enabled",              sa.Boolean(),
                      server_default=sa.text("0")),
            sa.Column("lstm_final_loss",           sa.Float(), nullable=True),
            sa.Column("lstm_epochs_trained",       sa.Integer(), nullable=True),
            sa.Column("total_anomalies_detected",  sa.Integer()),
            sa.Column("anomaly_percentage",        sa.Float()),
            sa.Column("status",                    sa.String(50),
                      server_default="completed"),
            sa.Column("error_message",             sa.Text(), nullable=True),
            sa.Column("created_at",                sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )


# ─────────────────────────────────────────────────────────────
#  Downgrade
# ─────────────────────────────────────────────────────────────

def downgrade() -> None:
    for tbl in ("training_records", "anomaly_records", "users"):
        if _table_exists(tbl):
            op.drop_table(tbl)
