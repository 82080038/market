"""Create signal_attribution_log table for per-engine signal attribution.

Records what each analysis engine predicted on each day for each ticker,
so we can answer: "When price moved X%, which engines predicted it correctly?"

This is NOT a signal log (runtime). It is a historical attribution record
that persists per-engine predictions and their directional accuracy vs
actual forward returns.

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_attribution_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("as_of_date", sa.Date, nullable=False, index=True),
        sa.Column("ticker", sa.String(20), nullable=False, index=True),
        sa.Column("engine_name", sa.String(50), nullable=False, index=True),
        sa.Column("signal_value", sa.Float, nullable=False),
        sa.Column("signal_direction", sa.String(10), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=True),
        sa.Column("fwd_return_1d", sa.Float, nullable=True),
        sa.Column("fwd_return_3d", sa.Float, nullable=True),
        sa.Column("fwd_return_5d", sa.Float, nullable=True),
        sa.Column("fwd_return_10d", sa.Float, nullable=True),
        sa.Column("direction_correct_1d", sa.Boolean, nullable=True),
        sa.Column("direction_correct_3d", sa.Boolean, nullable=True),
        sa.Column("direction_correct_5d", sa.Boolean, nullable=True),
        sa.Column("direction_correct_10d", sa.Boolean, nullable=True),
        sa.Column("backtest_filled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "as_of_date", "ticker", "engine_name",
            name="uq_signal_attr_date_ticker_engine",
        ),
    )
    op.create_index(
        "ix_signal_attr_engine_date",
        "signal_attribution_log",
        ["engine_name", "as_of_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_signal_attr_engine_date", table_name="signal_attribution_log")
    op.drop_table("signal_attribution_log")
