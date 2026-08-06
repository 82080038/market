"""Add ml_labels and market_regimes tables for AI/ML pipeline.

ml_labels: Triple-barrier labels (López de Prado) for ML training.
market_regimes: Daily market regime classification (bull/bear/sideways/crisis).

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ml_labels",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False, index=True),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("horizon", sa.Integer, nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("barrier_hit", sa.String(20), nullable=True),
        sa.Column("return_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("vol_adjusted_return", sa.Numeric(10, 4), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("ticker", "date", "horizon", name="uq_mllabel_pk"),
    )
    op.create_index("ix_mllabel_ticker_date", "ml_labels", ["ticker", "date"])

    op.create_table(
        "market_regimes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("regime", sa.String(30), nullable=True),
        sa.Column("vix_level", sa.String(20), nullable=True),
        sa.Column("fear_greed_label", sa.String(30), nullable=True),
        sa.Column("foreign_flow_trend", sa.String(20), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("date", name="uq_regime_pk"),
    )


def downgrade() -> None:
    op.drop_table("market_regimes")
    op.drop_index("ix_mllabel_ticker_date", table_name="ml_labels")
    op.drop_table("ml_labels")
