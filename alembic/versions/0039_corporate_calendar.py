"""corporate_calendar table for IDX corporate events (RUPS, buyback, dividend, etc.).

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    exists = conn.execute(
        sa.text("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'corporate_calendar')")
    ).scalar()
    if not exists:
        op.create_table(
            "corporate_calendar",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("ticker", sa.String(20), nullable=False),
            sa.Column("event_date", sa.Date(), nullable=False),
            sa.Column("event_type", sa.String(50), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("agenda", sa.String(500), nullable=True),
            sa.Column("location", sa.Text(), nullable=True),
            sa.Column("step", sa.String(100), nullable=True),
            sa.Column("tgl_rups", sa.DateTime(timezone=True), nullable=True),
            sa.Column("tgl_pe", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source", sa.String(50), server_default="idx_co_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint(
                "ticker", "event_date", "event_type",
                name="corporate_calendar_ticker_event_date_event_type_key",
            ),
        )
        op.create_index("ix_cc_ticker", "corporate_calendar", ["ticker"])
        op.create_index("ix_cc_date", "corporate_calendar", ["event_date"])
        op.create_index("ix_cc_type", "corporate_calendar", ["event_type"])


def downgrade() -> None:
    op.drop_table("corporate_calendar")
