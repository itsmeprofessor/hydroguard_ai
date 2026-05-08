"""Drift and calibration state tables.

Revision ID: 004_drift_calibration
Revises: 003_v2_models
Create Date: 2026-05-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision      = "004_drift_calibration"
down_revision = "003_v2_models"
branch_labels = None
depends_on    = None


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("drift_state"):
        op.create_table(
            "drift_state",
            sa.Column("id",                sa.String(36),  primary_key=True),
            sa.Column("city_slug",         sa.String(64),  nullable=False, index=True),
            sa.Column("checked_at",        sa.DateTime(timezone=True), nullable=False),
            sa.Column("window_size",       sa.Integer(),   nullable=False),
            sa.Column("reference_rows",    sa.Integer(),   nullable=False),
            sa.Column("psi_scores",        sa.JSON(),      nullable=False),
            sa.Column("max_psi",           sa.Float(),     nullable=False, index=True),
            sa.Column("drift_level",       sa.String(16),  nullable=False),
            sa.Column("retrain_triggered", sa.Boolean(),   server_default=sa.text("0")),
            sa.Column("created_at",        sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )

    if not _table_exists("calibration_state"):
        op.create_table(
            "calibration_state",
            sa.Column("id",               sa.String(36),  primary_key=True),
            sa.Column("city_slug",        sa.String(64),  nullable=False, index=True),
            sa.Column("model_version",    sa.String(64),  nullable=False),
            sa.Column("calibrated_at",    sa.DateTime(timezone=True), nullable=False),
            sa.Column("is_active",        sa.Boolean(),   server_default=sa.text("0"), index=True),
            sa.Column("n_calibration_samples", sa.Integer()),
            sa.Column("brier_score_before",    sa.Float()),
            sa.Column("brier_score_after",     sa.Float()),
            sa.Column("ece_before",            sa.Float()),
            sa.Column("ece_after",             sa.Float()),
            sa.Column("artifact_path",    sa.Text(),      nullable=False),
            sa.Column("created_at",       sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )


def downgrade() -> None:
    for tbl in ("calibration_state", "drift_state"):
        if _table_exists(tbl):
            op.drop_table(tbl)
