"""Add tracking columns to recompute_dependencies and data_watermark.

Adds next_run_at, previous_run_at, last_data_changed_at, recommendation
columns to recompute_dependencies so the system knows when each function
was last run, when the input data last changed, when it should run again,
and what action is recommended.

Adds previous_updated, next_check_at, change_detected columns to
data_watermark so per-table freshness tracking includes the previous
update timestamp, when to check again, and whether a change was detected.

These columns enable smart skip logic: modules don't need to recompute
from scratch if data hasn't changed since last run.
"""

from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"


def upgrade() -> None:
    # recompute_dependencies: add scheduling & recommendation columns
    op.add_column(
        "recompute_dependencies",
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "recompute_dependencies",
        sa.Column("previous_run_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "recompute_dependencies",
        sa.Column("last_data_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "recompute_dependencies",
        sa.Column("recommendation", sa.Text, nullable=True),
    )
    op.add_column(
        "recompute_dependencies",
        sa.Column("recommendation_reason", sa.Text, nullable=True),
    )

    # data_watermark: add change tracking columns
    op.add_column(
        "data_watermark",
        sa.Column("previous_updated", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "data_watermark",
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "data_watermark",
        sa.Column("change_detected", sa.Boolean, nullable=True, default=False),
    )


def downgrade() -> None:
    op.drop_column("data_watermark", "change_detected")
    op.drop_column("data_watermark", "next_check_at")
    op.drop_column("data_watermark", "previous_updated")

    op.drop_column("recompute_dependencies", "recommendation_reason")
    op.drop_column("recompute_dependencies", "recommendation")
    op.drop_column("recompute_dependencies", "last_data_changed_at")
    op.drop_column("recompute_dependencies", "previous_run_at")
    op.drop_column("recompute_dependencies", "next_run_at")
