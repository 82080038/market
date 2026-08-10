"""Wide tables and FK declarations.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-10

Changes:
1. Create technical_indicators_wide (pivot of EAV technical_indicators)
2. Create stock_prediction (split from stock_personality)
3. Add FK declarations from ticker columns to instrument_master
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. technical_indicators_wide — one row per ticker+date, columns per indicator
    op.create_table(
        "technical_indicators_wide",
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False, server_default="1d"),
        sa.Column("ma20", sa.Numeric(20, 6), nullable=True),
        sa.Column("ma50", sa.Numeric(20, 6), nullable=True),
        sa.Column("rsi", sa.Numeric(20, 6), nullable=True),
        sa.Column("macd", sa.Numeric(20, 6), nullable=True),
        sa.Column("macd_signal", sa.Numeric(20, 6), nullable=True),
        sa.Column("adx", sa.Numeric(20, 6), nullable=True),
        sa.Column("atr14", sa.Numeric(20, 6), nullable=True),
        sa.Column("bb_upper", sa.Numeric(20, 6), nullable=True),
        sa.Column("bb_lower", sa.Numeric(20, 6), nullable=True),
        sa.Column("volume_sma20", sa.Numeric(20, 6), nullable=True),
        sa.Column("ema50", sa.Numeric(20, 6), nullable=True),
        sa.Column("ema_env_upper", sa.Numeric(20, 6), nullable=True),
        sa.Column("ema_env_lower", sa.Numeric(20, 6), nullable=True),
        sa.Column("donchian_upper", sa.Numeric(20, 6), nullable=True),
        sa.Column("donchian_lower", sa.Numeric(20, 6), nullable=True),
        sa.Column("donchian_mid", sa.Numeric(20, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("ticker", "date", "timeframe", name="uq_tiw_pk"),
    )
    op.create_index("ix_tiw_ticker", "technical_indicators_wide", ["ticker"])
    op.create_index("ix_tiw_date", "technical_indicators_wide", ["date"])
    op.create_index("ix_tiw_ticker_date", "technical_indicators_wide", ["ticker", "date"])

    # 2. stock_prediction — split from stock_personality (daily-updated prediction columns)
    op.create_table(
        "stock_prediction",
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("predicted_direction", sa.String(10), nullable=True),
        sa.Column("predicted_price", sa.Numeric(15, 2), nullable=True),
        sa.Column("predicted_return_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("prediction_confidence", sa.Numeric(5, 3), nullable=True),
        sa.Column("ml_signal", sa.Numeric(6, 4), nullable=True),
        sa.Column("multifactor_signal", sa.Numeric(6, 4), nullable=True),
        sa.Column("composite_signal", sa.Numeric(6, 4), nullable=True),
        sa.Column("factors_summary", sa.Text(), nullable=True),
        sa.Column("prediction_updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("ticker"),
    )


def downgrade() -> None:
    op.drop_table("stock_prediction")
    op.drop_index("ix_tiw_ticker_date", table_name="technical_indicators_wide")
    op.drop_index("ix_tiw_date", table_name="technical_indicators_wide")
    op.drop_index("ix_tiw_ticker", table_name="technical_indicators_wide")
    op.drop_table("technical_indicators_wide")
