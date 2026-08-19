"""Add unique constraint on astronacci_cycles (cycle_type, start_at).

The scheduler task _task_compute_astronacci_cycles runs weekly and inserts
cycles for the next 90 days. Without a unique constraint, re-runs produce
duplicate rows. The INSERT ... ON CONFLICT DO NOTHING in the scheduler task
requires a unique constraint to actually deduplicate.

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_astronacci_cycles_type_start",
        "astronacci_cycles",
        ["cycle_type", "start_at"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_astronacci_cycles_type_start",
        "astronacci_cycles",
        type_="unique",
    )
