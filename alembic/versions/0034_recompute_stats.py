"""Add recompute statistics columns to recompute_dependencies.

Tracks per-function runtime statistics so the system can estimate
how long a recompute will take and how many rows it will produce
before actually running it.

Also adds recompute_run_stats table for per-run historical tracking.
"""

from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add statistics columns to recompute_dependencies
    op.add_column("recompute_dependencies", sa.Column(
        "last_run_at", sa.DateTime(timezone=True), nullable=True,
        comment="When this function was last executed",
    ))
    op.add_column("recompute_dependencies", sa.Column(
        "last_duration_seconds", sa.Float(), nullable=True,
        comment="Duration of last execution in seconds",
    ))
    op.add_column("recompute_dependencies", sa.Column(
        "last_rows_affected", sa.Integer(), nullable=True,
        comment="Number of rows produced/updated in last execution",
    ))
    op.add_column("recompute_dependencies", sa.Column(
        "avg_duration_seconds", sa.Float(), nullable=True,
        comment="Rolling average duration over last 10 runs",
    ))
    op.add_column("recompute_dependencies", sa.Column(
        "avg_rows_affected", sa.Float(), nullable=True,
        comment="Rolling average rows over last 10 runs",
    ))
    op.add_column("recompute_dependencies", sa.Column(
        "run_count", sa.Integer(), nullable=False, server_default="0",
        comment="Total number of times this function has been executed",
    ))
    op.add_column("recompute_dependencies", sa.Column(
        "last_data_seen", sa.DateTime(timezone=True), nullable=True,
        comment="Timestamp of newest data observed in last run (for freshness check)",
    ))

    # Per-run stats table for historical tracking
    op.create_table(
        "recompute_run_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("function_name", sa.Text(), nullable=False, index=True),
        sa.Column("trigger_id", sa.Integer(), nullable=True,
                  comment="FK to recompute_triggers.id if part of selective recompute"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("rows_affected", sa.Integer(), nullable=True),
        sa.Column("tickers_processed", sa.Integer(), nullable=True),
        sa.Column("tickers_skipped", sa.Integer(), nullable=True),
        sa.Column("incremental", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("data_freshness_seconds", sa.Float(), nullable=True,
                  comment="How stale the input data was (seconds since last update)"),
        sa.Column("status", sa.Text(), nullable=False, server_default="completed",
                  comment="completed, failed, skipped"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_run_stats_function", "recompute_run_stats", ["function_name"])
    op.create_index("ix_run_stats_started", "recompute_run_stats", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_run_stats_started", table_name="recompute_run_stats")
    op.drop_index("ix_run_stats_function", table_name="recompute_run_stats")
    op.drop_table("recompute_run_stats")

    op.drop_column("recompute_dependencies", "last_data_seen")
    op.drop_column("recompute_dependencies", "run_count")
    op.drop_column("recompute_dependencies", "avg_rows_affected")
    op.drop_column("recompute_dependencies", "avg_duration_seconds")
    op.drop_column("recompute_dependencies", "last_rows_affected")
    op.drop_column("recompute_dependencies", "last_duration_seconds")
    op.drop_column("recompute_dependencies", "last_run_at")
