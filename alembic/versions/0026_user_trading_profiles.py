"""Add user_trading_profiles + trading_style_recommendations + reasons
(catatan.md TAHAP 4 — Prompt 4.1).

Single-user app — user_id default 'default'. Tables support multiple users
for future extensibility but current usage is single-user.

Schema source: catatan.md L629-L642.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. user_trading_profiles
    op.create_table(
        "user_trading_profiles",
        sa.Column("user_id", sa.String(50), primary_key=True),
        sa.Column("capital", sa.Numeric(18, 2), nullable=False),
        sa.Column("risk_tolerance", sa.String(20), nullable=False),
        # CONSERVATIVE/MODERATE/AGGRESSIVE
        sa.Column("time_availability", sa.String(20), nullable=False),
        # FULL_TIME/PART_TIME/EVENINGS
        sa.Column("experience_level", sa.String(20), nullable=False),
        # BEGINNER/INTERMEDIATE/ADVANCED/EXPERT
        sa.Column("max_loss_per_trade_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("max_portfolio_drawdown_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("preferred_styles", sa.JSON, nullable=True),  # list[str]
        sa.Column("preferred_sectors", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. trading_style_recommendations
    op.create_table(
        "trading_style_recommendations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.String(50),
            sa.ForeignKey("user_trading_profiles.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recommended_style", sa.String(30), nullable=False),  # intraday/swing/investing
        sa.Column("allocation_pct", sa.Numeric(6, 2), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 2), nullable=True),
        sa.Column("reasoning_summary", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tsr_user", "trading_style_recommendations", ["user_id"])

    # 3. style_recommendation_reasons
    op.create_table(
        "style_recommendation_reasons",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "recommendation_id", sa.Integer,
            sa.ForeignKey("trading_style_recommendations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # capital_match/risk_match/time_match/experience_match
        sa.Column("reason_type", sa.String(50), nullable=False),
        sa.Column("reason_text", sa.Text, nullable=False),
        sa.Column("supporting_data", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_srr_rec", "style_recommendation_reasons", ["recommendation_id"])


def downgrade() -> None:
    op.drop_index("ix_srr_rec", table_name="style_recommendation_reasons")
    op.drop_table("style_recommendation_reasons")
    op.drop_index("ix_tsr_user", table_name="trading_style_recommendations")
    op.drop_table("trading_style_recommendations")
    op.drop_table("user_trading_profiles")
