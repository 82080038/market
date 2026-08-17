"""Upgrade scheduler_state table with next_run_at, stale detection, data dependencies.

Adds columns for:
- next_run_at: pre-computed next scheduled run time (so modules can countdown)
- is_stale: whether task was missed (computer off) and needs catch-up
- data_dependencies: JSONB array of data layers/tables this task needs
- data_ready: whether pre-loaded data is available in DB
- last_result: JSONB summary of last execution (rows fetched, tickers, errors)
- is_catchup: whether last execution was a catch-up run
- last_duration_seconds: how long the task took

Also migrates existing system_state scheduler entries to scheduler_state table.
"""

from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to scheduler_state
    op.add_column("scheduler_state", sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scheduler_state", sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("scheduler_state", sa.Column("data_dependencies", sa.JSON(), nullable=True))
    op.add_column("scheduler_state", sa.Column("data_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("scheduler_state", sa.Column("last_result", sa.JSON(), nullable=True))
    op.add_column("scheduler_state", sa.Column("is_catchup", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("scheduler_state", sa.Column("last_duration_seconds", sa.Float(), nullable=True))

    # Migrate existing scheduler state from system_state to scheduler_state
    op.execute("""
        INSERT INTO scheduler_state (task_id, last_run, last_status, last_error, run_count, updated_at)
        SELECT
            REPLACE(key, 'scheduler:', '') AS task_id,
            (value::json->>'last_run')::timestamptz AS last_run,
            COALESCE(value::json->>'last_status', 'pending') AS last_status,
            COALESCE(value::json->>'last_error', '') AS last_error,
            COALESCE((value::json->>'run_count')::int, 0) AS run_count,
            NOW()
        FROM system_state
        WHERE key LIKE 'scheduler:%'
        ON CONFLICT (task_id) DO UPDATE SET
            last_run = EXCLUDED.last_run,
            last_status = EXCLUDED.last_status,
            last_error = EXCLUDED.last_error,
            run_count = EXCLUDED.run_count,
            updated_at = NOW()
    """)

    # Mark tasks as stale if last_run is older than their expected interval
    op.execute("""
        UPDATE scheduler_state SET is_stale = true
        WHERE last_run IS NOT NULL
          AND last_run::timestamptz < NOW() - INTERVAL '26 hours'
          AND task_id NOT IN ('fetch_intraday', 'startup_catchup')
    """)

    op.execute("""
        UPDATE scheduler_state SET is_stale = true
        WHERE last_run IS NULL
          AND task_id NOT IN ('startup_catchup')
    """)


def downgrade() -> None:
    op.drop_column("scheduler_state", "last_duration_seconds")
    op.drop_column("scheduler_state", "is_catchup")
    op.drop_column("scheduler_state", "last_result")
    op.drop_column("scheduler_state", "data_ready")
    op.drop_column("scheduler_state", "data_dependencies")
    op.drop_column("scheduler_state", "is_stale")
    op.drop_column("scheduler_state", "next_run_at")
