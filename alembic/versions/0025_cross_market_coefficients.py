"""Add cross_market_coefficients table (catatan.md TAHAP 3 — Prompt 3.1).

Stores Granger-causality-derived coefficients from global indices to target
tickers (e.g. S&P500 → IHSG, HSI → IHSG, Nikkei → IHSG), including asymmetric
up/down behavior and market regime (BULL/BEAR/SIDEWAYS). Updated weekly.

Schema source: catatan.md L612-L623.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cross_market_coefficients",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_index", sa.String(20), nullable=False),
        sa.Column("target_ticker", sa.String(20), nullable=False),
        sa.Column("lag_days", sa.Integer, nullable=False),
        sa.Column("coefficient", sa.Numeric(8, 4), nullable=True),
        sa.Column("p_value", sa.Numeric(8, 4), nullable=True),
        sa.Column("f_statistic", sa.Numeric(10, 4), nullable=True),
        sa.Column("asymmetric_up", sa.Numeric(8, 4), nullable=True),
        sa.Column("asymmetric_down", sa.Numeric(8, 4), nullable=True),
        sa.Column("regime", sa.String(20), nullable=True),  # BULL/BEAR/SIDEWAYS
        sa.Column("sample_size", sa.Integer, nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "source_index", "target_ticker", "lag_days",
            name="uq_cmc_source_target_lag",
        ),
    )
    op.create_index(
        "ix_cmc_source", "cross_market_coefficients", ["source_index"]
    )
    op.create_index(
        "ix_cmc_target", "cross_market_coefficients", ["target_ticker"]
    )


def downgrade() -> None:
    op.drop_index("ix_cmc_target", table_name="cross_market_coefficients")
    op.drop_index("ix_cmc_source", table_name="cross_market_coefficients")
    op.drop_table("cross_market_coefficients")
