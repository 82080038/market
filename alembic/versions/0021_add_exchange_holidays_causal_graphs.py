"""Add exchange_holidays + causal_graphs tables for global market AI engines.

Tables:
  exchange_holidays — Holiday calendar for global stock exchanges
  causal_graphs     — Persisted causal discovery results between tickers

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exchange_holidays",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("mic_code", sa.String(10), nullable=False),  # XIDX, XNYS, XNSE, etc.
        sa.Column("holiday_date", sa.Date, nullable=False),
        sa.Column("holiday_name", sa.String(200), nullable=False),
        sa.Column("is_half_day", sa.Boolean, default=False),
        sa.UniqueConstraint("mic_code", "holiday_date", name="uq_exchange_holidays_mic_date"),
    )
    op.create_index("ix_exchange_holidays_mic_code", "exchange_holidays", ["mic_code"])
    op.create_index("ix_exchange_holidays_date", "exchange_holidays", ["holiday_date"])

    op.create_table(
        "causal_graphs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.Date, nullable=False),
        sa.Column("window_end", sa.Date, nullable=False),
        sa.Column("max_lag", sa.Integer, nullable=False),
        sa.Column("tickers", sa.Text, nullable=False),  # JSON array of tickers
        sa.Column("graph_json", sa.Text, nullable=False),  # JSON: links + strength matrix
        sa.Column("total_links", sa.Integer, default=0),
        sa.Column("avg_strength", sa.Float, default=0.0),
    )
    op.create_index("ix_causal_graphs_computed_at", "causal_graphs", ["computed_at"])


def downgrade() -> None:
    op.drop_index("ix_causal_graphs_computed_at", table_name="causal_graphs")
    op.drop_table("causal_graphs")
    op.drop_index("ix_exchange_holidays_date", table_name="exchange_holidays")
    op.drop_index("ix_exchange_holidays_mic_code", table_name="exchange_holidays")
    op.drop_table("exchange_holidays")
