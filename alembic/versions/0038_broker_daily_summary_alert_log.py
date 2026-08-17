"""broker_daily_summary + alert_log tables.

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # broker_daily_summary
    exists = conn.execute(
        sa.text("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'broker_daily_summary')")
    ).scalar()
    if not exists:
        op.create_table(
            "broker_daily_summary",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("broker_code", sa.String(10), nullable=False),
            sa.Column("broker_name", sa.String(200), nullable=True),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("volume", sa.BigInteger(), server_default="0"),
            sa.Column("value", sa.Numeric(20, 2), server_default="0"),
            sa.Column("frequency", sa.Integer(), server_default="0"),
            sa.Column("source", sa.String(50), server_default="idx_co_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("broker_code", "date", name="uq_bds_broker_date"),
        )
        op.create_index("ix_bds_date", "broker_daily_summary", ["date"])
        op.create_index("ix_bds_broker", "broker_daily_summary", ["broker_code"])

    # alert_log
    exists = conn.execute(
        sa.text("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'alert_log')")
    ).scalar()
    if not exists:
        op.create_table(
            "alert_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("ticker", sa.String(20), nullable=True),
            sa.Column("rule_name", sa.String(50), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("severity", sa.String(20), server_default="info"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_alert_log_ticker", "alert_log", ["ticker"])
        op.create_index("ix_alert_log_created", "alert_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("alert_log")
    op.drop_table("broker_daily_summary")
