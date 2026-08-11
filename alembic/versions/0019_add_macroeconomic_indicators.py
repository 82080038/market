"""Add macroeconomic_indicators table for global & domestic macro causal analysis.

Stores time-series readings of macro indicators that drive the "WHY" dimension
(Dimensi 1) of the domino-effect causal framework:
  - FED_RATE      — US Federal Funds Rate
  - BI_RATE       — Bank Indonesia 7-Day Reverse Repo Rate
  - USD_IDR       — Nilai tukar USD/IDR (yfinance: IDR=X)
  - VIX_INDEX     — CBOE Volatility Index / Indeks Ketakutan (yfinance: ^VIX)
  - BRENT_CRUDE   — Harga minyak mentah Brent (yfinance: BZ=F)
  - GOLD_PRICE    — Harga emas dunia (yfinance: GC=F)
  - US_INFLATION  — US CPI Inflasi (FRED)
  - ID_INFLATION  — Indonesia CPI Inflasi (FRED)

All recorded_at stored as TIMESTAMPTZ (UTC anchor) per AGENTS.md §2.
Integrated into v_domino_timeline view via UNION ALL (MACRO_INDICATOR branch).

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "macroeconomic_indicators",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("indicator_code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("region", sa.String(50), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(20, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("indicator_code", "recorded_at",
                            name="uq_macro_indicator"),
        sa.CheckConstraint(
            "region IN ('US','ID','GLOBAL','EU','ASIA','CN','JP','HK')",
            name="chk_macro_region"),
    )
    op.create_index(
        "idx_macro_indicator_code_time",
        "macroeconomic_indicators",
        [sa.text("indicator_code"), sa.text("recorded_at DESC")],
    )
    op.create_index("idx_macro_recorded_at",
                    "macroeconomic_indicators", ["recorded_at"])
    op.create_index("idx_macro_region",
                    "macroeconomic_indicators", ["region"])


def downgrade() -> None:
    op.drop_table("macroeconomic_indicators")
