"""Add parquet_sync_state table for incremental DB → Parquet sync.

Tracks last_synced_date per table so sync_to_parquet.py can resume
incrementally (partitioned time-series) or do full rewrites (reference
tables) without re-exporting the entire database each run.

See pustaka/94-sync-db-to-parquet.md for the full design.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parquet_sync_state",
        sa.Column("table_name", sa.String(50), primary_key=True),
        sa.Column("sync_mode", sa.String(20), nullable=False),
        sa.Column("partition_col", sa.String(50), nullable=True),
        sa.Column("last_synced_date", sa.Date, nullable=True),
        sa.Column("last_synced_at", sa.DateTime, nullable=True),
        sa.Column("last_row_count", sa.Integer, nullable=True),
        sa.Column("total_partitions_written", sa.Integer, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("parquet_sync_state")
