"""Add astronacci_cycles table for Financial Astrology & Time Cycle integration.

Stores time-cycle events based on Astronacci methodology:
- Mercury Retrograde periods
- Moon Phases (New Moon, Full Moon windows)
- Fibonacci Time Windows

These act as "WHEN" indicators — when price reversals are potentially expected.
Integrated into v_domino_timeline view via UNION ALL.

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "astronacci_cycles",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("cycle_uuid", sa.dialects.postgresql.UUID(as_uuid=True),
                  server_default=sa.func.gen_random_uuid(), unique=True),
        sa.Column("cycle_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("potential_impact", sa.String(20), server_default="HIGH"),
        sa.Column("target_asset_class", sa.String(50), server_default="ALL"),
        sa.Column("expected_reversal", sa.String(20), server_default="NEUTRAL"),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.CheckConstraint("start_at < end_at", name="chk_astronacci_dates"),
        sa.CheckConstraint(
            "potential_impact IN ('CRITICAL','HIGH','MEDIUM','LOW')",
            name="chk_astronacci_impact"),
        sa.CheckConstraint(
            "expected_reversal IN ('BULLISH_REVERSAL','BEARISH_REVERSAL','VOLATILITY','NEUTRAL')",
            name="chk_astronacci_reversal"),
    )
    op.create_index("idx_astronacci_start_at", "astronacci_cycles", ["start_at"])
    op.create_index("idx_astronacci_end_at", "astronacci_cycles", ["end_at"])
    op.create_index("idx_astronacci_cycle_type", "astronacci_cycles", ["cycle_type"])
    op.create_index("idx_astronacci_reversal", "astronacci_cycles", ["expected_reversal"])


def downgrade() -> None:
    op.drop_table("astronacci_cycles")
