"""Add satellite_observations and satellite_correlation_results tables.

Stores satellite data proven significant in correlation analysis:
- NDVI from Sentinel-2 via Microsoft Planetary Computer
- T2M, PRECTOTCORR, RH2M, ALLSKY_SFC_SW_DWN from NASA POWER API

Two tables:
1. satellite_observations — raw daily/sparse satellite metrics per location
2. satellite_correlation_results — persisted correlation analysis output

See pustaka/99-matriks-relevansi-satelit-pasar-modal.md for the relevance
matrix and pipeline results.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. satellite_observations — raw satellite data
    op.create_table(
        "satellite_observations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("location_name", sa.String(100), nullable=False, index=True),
        sa.Column("lat", sa.Numeric(10, 6), nullable=False),
        sa.Column("lon", sa.Numeric(10, 6), nullable=False),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("metric", sa.String(30), nullable=False),
        sa.Column("value", sa.Numeric(20, 6), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="nasa_power"),
        sa.Column("cloud_cover_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("scene_id", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("location_name", "date", "metric", "source",
                            name="uq_satobs_pk"),
    )
    op.create_index("ix_satobs_location_date", "satellite_observations",
                    ["location_name", "date"])
    op.create_index("ix_satobs_metric", "satellite_observations", ["metric"])

    # 2. satellite_correlation_results — analysis output
    op.create_table(
        "satellite_correlation_results",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("location_name", sa.String(100), nullable=False, index=True),
        sa.Column("satellite_metric", sa.String(30), nullable=False),
        sa.Column("stock_ticker", sa.String(30), nullable=False),
        sa.Column("frequency", sa.String(10), nullable=False),
        sa.Column("rolling_window", sa.Integer, nullable=False),
        sa.Column("optimal_lag", sa.Integer, nullable=False),
        sa.Column("optimal_corr", sa.Numeric(10, 6), nullable=False),
        sa.Column("optimal_pvalue", sa.Numeric(10, 6), nullable=False),
        sa.Column("granger_optimal_pvalue", sa.Numeric(10, 6), nullable=True),
        sa.Column("is_significant", sa.Boolean, default=False, nullable=False),
        sa.Column("lag_unit", sa.String(10), nullable=False, server_default="hari"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("location_name", "satellite_metric", "stock_ticker",
                            "frequency", "rolling_window",
                            name="uq_satcorr_pk"),
    )
    op.create_index("ix_satcorr_ticker", "satellite_correlation_results",
                    ["stock_ticker"])
    op.create_index("ix_satcorr_metric", "satellite_correlation_results",
                    ["satellite_metric"])


def downgrade() -> None:
    op.drop_table("satellite_correlation_results")
    op.drop_table("satellite_observations")
