"""Add recompute_watermark table for incremental recompute tracking.

Tracks the last-processed date per ticker per table so that incremental
recompute only loads and processes new data (with a lookback buffer for
indicators that need historical context like MA200 or ATR14).

See RINGKASAN-DATA-ML.md §12 "Incremental Recompute Architecture" for design.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-07
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recompute_watermark",
        sa.Column("ticker", sa.String(20), primary_key=True),
        sa.Column("table_name", sa.String(50), primary_key=True),
        sa.Column("last_processed_date", sa.Date, nullable=True),
        sa.Column("last_ohlcv_date", sa.Date, nullable=True),
        sa.Column("rows_processed", sa.Integer, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_recompute_watermark_table",
        "recompute_watermark",
        ["table_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_recompute_watermark_table", table_name="recompute_watermark")
    op.drop_table("recompute_watermark")
