"""Feature store tables: feature_snapshots and weather_snapshots.

Revision ID: 002_feature_store
Revises: 001_initial
Create Date: 2026-05-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision      = "002_feature_store"
down_revision = "001_initial"
branch_labels = None
depends_on    = None


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("feature_snapshots"):
        op.create_table(
            "feature_snapshots",
            sa.Column("id",          sa.String(36), primary_key=True),
            sa.Column("city_slug",   sa.String(64), nullable=False, index=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("data_source", sa.String(20), nullable=False),
            # Raw inputs
            sa.Column("prcp",        sa.Float()),
            sa.Column("humidity",    sa.Float()),
            sa.Column("pressure",    sa.Float()),
            sa.Column("cloud_cover", sa.Float()),
            sa.Column("tmin",        sa.Float()),
            sa.Column("tmax",        sa.Float()),
            sa.Column("tavg",        sa.Float()),
            sa.Column("temp_range",  sa.Float()),
            sa.Column("dew_point",   sa.Float()),
            sa.Column("wspd",        sa.Float()),
            # Derived features
            sa.Column("pressure_delta_3h",    sa.Float()),
            sa.Column("pressure_delta_6h",    sa.Float()),
            sa.Column("humidity_delta_3h",    sa.Float()),
            sa.Column("rain_rate_1h",         sa.Float()),
            sa.Column("rain_accumulation_3h", sa.Float()),
            sa.Column("rain_accumulation_6h", sa.Float()),
            sa.Column("tdew_spread",          sa.Float()),
            sa.Column("moisture_flux",        sa.Float()),
            sa.Column("cloud_jump_3h",        sa.Float()),
            # Climatological
            sa.Column("prcp_climo_pct",     sa.Float()),
            sa.Column("pressure_climo_z",   sa.Float()),
            sa.Column("humidity_climo_pct", sa.Float()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _table_exists("weather_snapshots"):
        op.create_table(
            "weather_snapshots",
            sa.Column("id",                sa.String(36), primary_key=True),
            sa.Column("city_slug",         sa.String(64), nullable=False, index=True),
            sa.Column("fetched_at",        sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("provider",          sa.String(16), server_default="weatherapi"),
            sa.Column("api_response_hash", sa.String(64)),
            sa.Column("temp_c",            sa.Float()),
            sa.Column("feelslike_c",       sa.Float()),
            sa.Column("humidity",          sa.Float()),
            sa.Column("pressure_mb",       sa.Float()),
            sa.Column("precip_mm",         sa.Float()),
            sa.Column("cloud",             sa.Float()),
            sa.Column("wind_kph",          sa.Float()),
            sa.Column("dew_point_c",       sa.Float()),
            sa.Column("vis_km",            sa.Float()),
            sa.Column("uv_index",          sa.Float()),
            sa.Column("condition_code",    sa.Integer()),
            sa.Column("precip_mm_1h",      sa.Float()),
            sa.Column("precip_mm_3h",      sa.Float()),
            sa.Column("precip_mm_6h",      sa.Float()),
            sa.Column("pressure_delta_3h", sa.Float()),
            sa.Column("pressure_delta_6h", sa.Float()),
            sa.Column("humidity_delta_3h", sa.Float()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    for tbl in ("weather_snapshots", "feature_snapshots"):
        if _table_exists(tbl):
            op.drop_table(tbl)
