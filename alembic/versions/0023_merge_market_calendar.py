"""Merge market_calendar into exchange_holidays.

market_calendar has 27K rows (7 exchanges, all calendar days: trading + non-trading).
exchange_holidays has 4.6K rows (15 exchanges, holidays only, proper unique constraint).

Strategy:
  1. Migrate holidays from market_calendar → exchange_holidays (map old codes to MIC,
     ON CONFLICT UPDATE to preserve richer holiday names from market_calendar)
  2. Drop market_calendar table
  3. Create compatibility view market_calendar from exchange_holidays

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

# Mapping old market_calendar.exchange codes → exchange_holidays.mic_code
_CODE_MAP = {
    "IDX": "XIDX",
    "XEUC": "XEUC",
    "XHKG": "XHKG",
    "XLON": "XLON",
    "XNAS": "XNAS",
    "XNYS": "XNYS",
    "XTKS": "XTSE",
}


def upgrade() -> None:
    # ── 1. Migrate holidays from market_calendar → exchange_holidays ────────
    # Insert non-trading days from market_calendar that don't exist in exchange_holidays.
    # ON CONFLICT UPDATE to enrich holiday_name (market_calendar has Indonesian names).
    op.execute("""
        INSERT INTO exchange_holidays (mic_code, holiday_date, holiday_name, is_half_day)
        SELECT
            CASE mc.exchange
                WHEN 'IDX'  THEN 'XIDX'
                WHEN 'XEUC' THEN 'XEUC'
                WHEN 'XHKG' THEN 'XHKG'
                WHEN 'XLON' THEN 'XLON'
                WHEN 'XNAS' THEN 'XNAS'
                WHEN 'XNYS' THEN 'XNYS'
                WHEN 'XTKS' THEN 'XTSE'
            END,
            mc.date,
            mc.holiday_name,
            mc.half_day
        FROM market_calendar mc
        WHERE mc.is_trading_day = false
          AND mc.holiday_name IS NOT NULL
        ON CONFLICT (mic_code, holiday_date)
        DO UPDATE SET
            holiday_name = COALESCE(EXCLUDED.holiday_name, exchange_holidays.holiday_name),
            is_half_day = COALESCE(EXCLUDED.is_half_day, exchange_holidays.is_half_day)
        WHERE exchange_holidays.holiday_name = 'Market Holiday'
           OR exchange_holidays.holiday_name IS NULL;
    """)

    # ── 2. Drop market_calendar table ───────────────────────────────────────
    op.execute("DROP TABLE IF EXISTS market_calendar CASCADE;")

    # ── 3. Create compatibility view ────────────────────────────────────────
    # Shows holidays only (is_trading_day=false). Code that needs trading-day
    # checks should use: NOT EXISTS in this view AND EXTRACT(dow) NOT IN (0,6).
    op.execute("""
        CREATE OR REPLACE VIEW market_calendar AS
        SELECT
            eh.holiday_date AS date,
            eh.mic_code AS exchange,
            false AS is_trading_day,
            eh.holiday_name,
            COALESCE(eh.is_half_day, false) AS half_day,
            NULL::timestamp with time zone AS created_at
        FROM exchange_holidays eh;
    """)


def downgrade() -> None:
    # Drop view
    op.execute("DROP VIEW IF EXISTS market_calendar;")

    # Recreate table
    op.create_table(
        "market_calendar",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("exchange", sa.String(10), nullable=False, server_default="XIDX"),
        sa.Column("is_trading_day", sa.Boolean, server_default=sa.text("true")),
        sa.Column("holiday_name", sa.String(200), nullable=True),
        sa.Column("half_day", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("date", "exchange", name="uq_cal_pk"),
    )

    # Migrate holidays back (reverse mapping)
    op.execute("""
        INSERT INTO market_calendar (date, exchange, is_trading_day, holiday_name, half_day)
        SELECT
            eh.holiday_date,
            CASE eh.mic_code
                WHEN 'XIDX' THEN 'IDX'
                ELSE eh.mic_code
            END,
            false,
            eh.holiday_name,
            COALESCE(eh.is_half_day, false)
        FROM exchange_holidays eh
        WHERE eh.mic_code IN ('XIDX', 'XEUC', 'XHKG', 'XLON', 'XNAS', 'XNYS', 'XTSE');
    """)
