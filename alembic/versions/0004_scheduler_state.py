"""Add scheduler_state table for persistent scheduler.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduler_state",
        sa.Column("task_id", sa.String(50), primary_key=True),
        sa.Column("last_run", sa.DateTime, nullable=True),
        sa.Column("last_status", sa.String(20), server_default="pending"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("run_count", sa.Integer, server_default="0"),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("scheduler_state")
