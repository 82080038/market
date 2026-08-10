"""Add NPL ratio for banking stocks, model_performance_history table,
and strategy_assignment table for richer per-ticker strategy selection.

1. NPL ratio: Add npl_ratio and car (Capital Adequacy Ratio) columns to
   fundamental_data — banking-specific metrics that research shows are
   significant predictors for banking stock prices on IDX.

2. model_performance_history: Persist ModelPerformanceTracker records
   to DB instead of in-memory only. Tracks Sharpe, MAE, directional
   accuracy, degradation status per ticker per evaluation.

3. strategy_assignment: Richer strategy selection per ticker. Instead
   of just 3 simple strategies (donchian, rsi_meanrev, ema_envelope),
   track which engine/class is best suited for each ticker based on
   personality profile (pairs_trading, sector_rotation, mean_reversion,
   momentum_breakout, value_dividend, etc.).

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. NPL ratio + CAR for banking stocks in fundamental_data
    op.add_column("fundamental_data",
                  sa.Column("npl_ratio", sa.Numeric(10, 4), nullable=True))
    op.add_column("fundamental_data",
                  sa.Column("car", sa.Numeric(10, 4), nullable=True))
    op.add_column("fundamental_data",
                  sa.Column("loan_to_deposit", sa.Numeric(10, 4), nullable=True))
    op.add_column("fundamental_data",
                  sa.Column("nim", sa.Numeric(10, 4), nullable=True))

    # 2. model_performance_history table
    op.create_table(
        "model_performance_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False, index=True),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("model_type", sa.String(50), nullable=False),
        sa.Column("sharpe_ratio", sa.Numeric(10, 4), nullable=False),
        sa.Column("mae", sa.Numeric(20, 6), nullable=False),
        sa.Column("directional_accuracy", sa.Numeric(5, 2), nullable=False),
        sa.Column("is_degraded", sa.Boolean, default=False, nullable=False),
        sa.Column("degradation_reasons", sa.Text, nullable=True),
        sa.Column("auto_adjustment", sa.String(50), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("ticker", "model_id", "evaluated_at",
                            name="uq_model_perf_pk"),
    )
    op.create_index("ix_mph_ticker", "model_performance_history", ["ticker"])
    op.create_index("ix_mph_evaluated", "model_performance_history", ["evaluated_at"])

    # 3. strategy_assignment table — richer strategy selection per ticker
    op.create_table(
        "strategy_assignment",
        sa.Column("ticker", sa.String(30), primary_key=True),
        sa.Column("best_strategy", sa.String(50), nullable=False),
        sa.Column("strategy_class", sa.String(50), nullable=False),
        sa.Column("strategy_rationale", sa.Text, nullable=True),
        sa.Column("in_sample_sharpe", sa.Numeric(10, 4), nullable=True),
        sa.Column("in_sample_max_dd", sa.Numeric(10, 4), nullable=True),
        sa.Column("in_sample_winrate", sa.Numeric(5, 2), nullable=True),
        sa.Column("oos_sharpe", sa.Numeric(10, 4), nullable=True),
        sa.Column("oos_max_dd", sa.Numeric(10, 4), nullable=True),
        sa.Column("oos_winrate", sa.Numeric(5, 2), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sa_strategy_class", "strategy_assignment", ["strategy_class"])
    op.create_index("ix_sa_active", "strategy_assignment", ["is_active"])


def downgrade() -> None:
    op.drop_table("strategy_assignment")
    op.drop_table("model_performance_history")
    op.drop_column("fundamental_data", "nim")
    op.drop_column("fundamental_data", "loan_to_deposit")
    op.drop_column("fundamental_data", "car")
    op.drop_column("fundamental_data", "npl_ratio")
