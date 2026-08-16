"""Add instrument_behavior_profiles table (catatan.md TAHAP 2 — Prompt 2.1).

Comprehensive per-instrument behavior profile: volatility regime, momentum vs
mean-reversion, liquidity, correlation/sensitivity, seasonality, event
response, and trading-style suitability scores. Persisted so signal generators
and position sizers can query it without recomputing every run.

Schema source: catatan.md L504-L553.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instrument_behavior_profiles",
        sa.Column("ticker", sa.String(10), primary_key=True),
        sa.Column("asset_class", sa.String(30), nullable=True),
        sa.Column("sector", sa.String(50), nullable=True),
        # Volatility Profile
        sa.Column("avg_daily_volatility", sa.Numeric(8, 6), nullable=True),
        sa.Column("volatility_regime", sa.String(20), nullable=True),
        sa.Column("volatility_clustering_coefficient", sa.Numeric(6, 4), nullable=True),
        # Momentum & Mean Reversion
        sa.Column("momentum_strength", sa.Numeric(6, 4), nullable=True),
        sa.Column("optimal_momentum_lookback", sa.Integer, nullable=True),
        sa.Column("mean_reversion_halflife", sa.Numeric(8, 2), nullable=True),
        # Liquidity Profile
        sa.Column("avg_daily_volume", sa.BigInteger, nullable=True),
        sa.Column("avg_spread_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("liquidity_score", sa.Numeric(4, 2), nullable=True),
        sa.Column("optimal_position_size_pct", sa.Numeric(6, 4), nullable=True),
        # Correlation & Sensitivity
        sa.Column("beta_to_ihsg", sa.Numeric(6, 4), nullable=True),
        sa.Column("correlation_to_sector", sa.Numeric(6, 4), nullable=True),
        sa.Column("sensitivity_to_usd", sa.Numeric(6, 4), nullable=True),
        sa.Column("sensitivity_to_rates", sa.Numeric(6, 4), nullable=True),
        # Seasonality (JSONB — PostgreSQL only; SQLite fallback via Text)
        sa.Column("best_months", sa.JSON, nullable=True),
        sa.Column("worst_months", sa.JSON, nullable=True),
        sa.Column("day_of_week_effect", sa.JSON, nullable=True),
        # Event Response
        sa.Column("earnings_drift_days", sa.Integer, nullable=True),
        sa.Column("earnings_avg_move", sa.Numeric(6, 4), nullable=True),
        sa.Column("dividend_ex_date_effect", sa.Numeric(6, 4), nullable=True),
        # Trading Style Suitability (1-10)
        sa.Column("intraday_suitability", sa.Numeric(4, 2), nullable=True),
        sa.Column("swing_suitability", sa.Numeric(4, 2), nullable=True),
        sa.Column("investing_suitability", sa.Numeric(4, 2), nullable=True),
        # Metadata
        sa.Column("profile_confidence", sa.Numeric(4, 2), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_points_used", sa.Integer, nullable=True),
    )
    op.create_index(
        "ix_ibp_asset_class", "instrument_behavior_profiles", ["asset_class"]
    )
    op.create_index(
        "ix_ibp_volatility_regime", "instrument_behavior_profiles", ["volatility_regime"]
    )


def downgrade() -> None:
    op.drop_index("ix_ibp_volatility_regime", table_name="instrument_behavior_profiles")
    op.drop_index("ix_ibp_asset_class", table_name="instrument_behavior_profiles")
    op.drop_table("instrument_behavior_profiles")
