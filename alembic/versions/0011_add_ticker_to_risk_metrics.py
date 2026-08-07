"""Add ticker column to daily_risk_metrics for per-ticker risk tracking.

The original schema was portfolio-level only. ML needs per-ticker VaR/CVaR/
max_drawdown/annualized_volatility for position sizing and risk management.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-07
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "daily_risk_metrics",
        sa.Column("ticker", sa.String(30), nullable=True),
    )
    op.create_index(
        "ix_daily_risk_metrics_ticker_date",
        "daily_risk_metrics",
        ["ticker", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_daily_risk_metrics_ticker_date", table_name="daily_risk_metrics")
    op.drop_column("daily_risk_metrics", "ticker")
