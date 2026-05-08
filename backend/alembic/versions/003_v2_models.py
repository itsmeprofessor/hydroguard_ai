"""v2 model tables: prediction_events, label_events, training_runs, model_registry.

Revision ID: 003_v2_models
Revises: 002_feature_store
Create Date: 2026-05-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision      = "003_v2_models"
down_revision = "002_feature_store"
branch_labels = None
depends_on    = None


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("prediction_events"):
        op.create_table(
            "prediction_events",
            sa.Column("inference_id",            sa.String(36),  primary_key=True),
            sa.Column("city_slug",               sa.String(64),  nullable=False, index=True),
            sa.Column("model_version",           sa.String(64),  nullable=False),
            sa.Column("calibration_version",     sa.String(64),  nullable=False),
            sa.Column("weather_api_snapshot_id", sa.String(36),  nullable=True),
            sa.Column("feature_snapshot_id",     sa.String(36),  nullable=True),
            sa.Column("ae_percentile",           sa.Float(),     nullable=False),
            sa.Column("tcn_percentile",          sa.Float(),     nullable=False),
            sa.Column("ae_variance",             sa.Float()),
            sa.Column("tcn_variance",            sa.Float()),
            sa.Column("model_entropy",           sa.Float()),
            sa.Column("dynamics_snapshot",       sa.JSON()),
            sa.Column("p_event_raw",             sa.Float(),     nullable=False),
            sa.Column("p_event",                 sa.Float(),     nullable=False, index=True),
            sa.Column("ci_lower",                sa.Float(),     nullable=False),
            sa.Column("ci_upper",                sa.Float(),     nullable=False),
            sa.Column("uncertainty",             sa.Float(),     nullable=False),
            sa.Column("risk_band",               sa.String(20),  nullable=False, index=True),
            sa.Column("is_alert",                sa.Boolean(),   nullable=False, index=True),
            sa.Column("alert_threshold",         sa.Float(),     nullable=False),
            sa.Column("shap_values",             sa.JSON()),
            sa.Column("source",                  sa.String(20),  nullable=False),
            sa.Column("request_id",              sa.String(64)),
            sa.Column("inferred_at",             sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at",              sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )

    if not _table_exists("label_events"):
        op.create_table(
            "label_events",
            sa.Column("id",                  sa.String(36),    primary_key=True),
            sa.Column("city_slug",           sa.String(64),    nullable=False, index=True),
            sa.Column("observed_at",         sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("feature_snapshot_id", sa.String(36),    nullable=True),
            sa.Column("weak_label",          sa.SmallInteger(), nullable=False),
            sa.Column("weak_label_conf",     sa.Float(),       nullable=False),
            sa.Column("event_type",          sa.String(32)),
            sa.Column("source",              sa.String(32),    nullable=False),
            sa.Column("source_weight",       sa.Float(),       nullable=False),
            sa.Column("raw_score",           sa.Float()),
            sa.Column("rule_votes",          sa.JSON()),
            sa.Column("is_verified",         sa.Boolean(),     server_default=sa.text("0")),
            sa.Column("verified_by",         sa.String(64)),
            sa.Column("verified_at",         sa.DateTime(timezone=True)),
            sa.Column("notes",               sa.Text()),
            sa.Column("created_at",          sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )

    if not _table_exists("training_runs"):
        op.create_table(
            "training_runs",
            sa.Column("id",                  sa.String(36),  primary_key=True),
            sa.Column("city_slug",           sa.String(64),  nullable=False, index=True),
            sa.Column("triggered_by",        sa.String(32),  nullable=False),
            sa.Column("triggered_by_user",   sa.String(64)),
            sa.Column("status",              sa.String(16),  server_default="queued"),
            sa.Column("error_message",       sa.Text()),
            sa.Column("dataset_hash",        sa.String(64)),
            sa.Column("data_rows",           sa.Integer()),
            sa.Column("data_date_start",     sa.Date()),
            sa.Column("data_date_end",       sa.Date()),
            sa.Column("label_rows_used",     sa.Integer()),
            sa.Column("positive_label_rate", sa.Float()),
            sa.Column("architecture",        sa.JSON()),
            sa.Column("hyperparameters",     sa.JSON()),
            sa.Column("git_commit",          sa.String(40)),
            sa.Column("model_version",       sa.String(64)),
            sa.Column("ae_train_loss",       sa.Float()),
            sa.Column("ae_val_loss",         sa.Float()),
            sa.Column("tcn_train_loss",      sa.Float()),
            sa.Column("tcn_val_loss",        sa.Float()),
            sa.Column("lgbm_val_auc",        sa.Float()),
            sa.Column("lgbm_val_brier",      sa.Float()),
            sa.Column("calibration_ece",     sa.Float()),
            sa.Column("calibration_brier",   sa.Float()),
            sa.Column("started_at",          sa.DateTime(timezone=True)),
            sa.Column("finished_at",         sa.DateTime(timezone=True)),
            sa.Column("duration_seconds",    sa.Float()),
            sa.Column("created_at",          sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )

    if not _table_exists("model_registry"):
        op.create_table(
            "model_registry",
            sa.Column("id",                sa.String(36),  primary_key=True),
            sa.Column("city_slug",         sa.String(64),  nullable=False, index=True),
            sa.Column("model_version",     sa.String(64),  nullable=False, unique=True),
            sa.Column("is_active",         sa.Boolean(),   server_default=sa.text("0"), index=True),
            sa.Column("artifact_path",     sa.Text(),      nullable=False),
            sa.Column("ae_path",           sa.Text()),
            sa.Column("tcn_path",          sa.Text()),
            sa.Column("lgbm_path",         sa.Text()),
            sa.Column("calibrator_path",   sa.Text()),
            sa.Column("preprocessor_path", sa.Text()),
            sa.Column("training_run_id",   sa.String(36)),
            sa.Column("deployed_at",       sa.DateTime(timezone=True)),
            sa.Column("retired_at",        sa.DateTime(timezone=True)),
            sa.Column("created_at",        sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )


def downgrade() -> None:
    for tbl in ("model_registry", "training_runs", "label_events", "prediction_events"):
        if _table_exists(tbl):
            op.drop_table(tbl)
