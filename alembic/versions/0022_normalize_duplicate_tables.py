"""Normalize duplicate tables: drop broker/broker_bursa, merge market_registry→exchanges,
merge instrument_master→instruments, drop redundant prediction columns from stock_personality.

Changes:
  1. Drop `broker` table (duplicate of `brokers` — same 20 rows, brokers has UUID + FK)
  2. Drop `broker_bursa` table (junction for old broker, replaced by brokers.exchange_mic)
  3. Merge `market_registry` into `exchanges`: add columns, migrate data, drop, create view
  4. Merge `instrument_master` into `instruments`: add columns, migrate data, drop, create view
  5. Drop redundant prediction columns from `stock_personality` (already in `stock_prediction`)
  6. Add FK constraints for ticker columns to instruments
  7. Add unique constraints on fact tables

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Drop broker + broker_bursa (duplicate of brokers) ────────────────
    # broker_bursa has FK to broker via transaksi_investor.id_broker → broker.id_broker
    # But actual DB has no FK constraints on these tables (verified).
    op.execute("DROP TABLE IF EXISTS broker_bursa CASCADE;")
    op.execute("DROP TABLE IF EXISTS broker CASCADE;")

    # ── 2. Merge market_registry → exchanges ────────────────────────────────
    # Add missing columns to exchanges
    op.add_column("exchanges", sa.Column("trading_hours", sa.Text(), nullable=True))
    op.add_column("exchanges", sa.Column("supports_dst", sa.Boolean(), default=False, server_default=sa.text("false")))
    op.add_column("exchanges", sa.Column("settlement_cycle", sa.Integer(), default=2, server_default=sa.text("2")))
    op.add_column("exchanges", sa.Column("tick_size_rule", sa.Text(), nullable=True))
    op.add_column("exchanges", sa.Column("data_suffix", sa.String(10), nullable=True))
    op.add_column("exchanges", sa.Column("trading_status", sa.String(20), default="active", server_default=sa.text("'active'")))
    op.add_column("exchanges", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    # Migrate data from market_registry to exchanges
    op.execute("""
        UPDATE exchanges e SET
            trading_hours = mr.trading_hours,
            supports_dst = mr.supports_dst,
            settlement_cycle = mr.settlement_cycle,
            tick_size_rule = mr.tick_size_rule,
            data_suffix = mr.data_suffix,
            trading_status = mr.trading_status,
            updated_at = mr.updated_at
        FROM market_registry mr
        WHERE e.mic_code = mr.mic_code;
    """)

    # Drop market_registry, create compatibility view
    op.execute("DROP TABLE IF EXISTS market_registry CASCADE;")
    op.execute("""
        CREATE OR REPLACE VIEW market_registry AS
        SELECT
            e.mic_code,
            e.country_code,
            e.timezone,
            e.trading_hours,
            e.supports_dst,
            e.settlement_cycle,
            e.tick_size_rule,
            e.lot_size,
            e.currency,
            e.data_suffix,
            e.trading_status,
            e.created_at,
            e.updated_at
        FROM exchanges e;
    """)

    # ── 3. Merge instrument_master → instruments ────────────────────────────
    # Add missing columns to instruments
    op.add_column("instruments", sa.Column("reporting_currency", sa.String(3), default="IDR", server_default=sa.text("'IDR'")))
    op.add_column("instruments", sa.Column("lot_size", sa.Integer(), nullable=True))
    op.add_column("instruments", sa.Column("tick_size", sa.Numeric(20, 8), nullable=True))
    op.add_column("instruments", sa.Column("subsector", sa.String(100), nullable=True))
    op.add_column("instruments", sa.Column("underlying_ticker", sa.String(30), nullable=True))
    op.add_column("instruments", sa.Column("suspension_date", sa.Date(), nullable=True))
    op.add_column("instruments", sa.Column("delisting_date", sa.Date(), nullable=True))
    op.add_column("instruments", sa.Column("board", sa.String(20), nullable=True))
    op.add_column("instruments", sa.Column("free_float", sa.Numeric(20, 4), nullable=True))
    op.add_column("instruments", sa.Column("market_cap", sa.Numeric(20, 2), nullable=True))
    op.add_column("instruments", sa.Column("listed_shares", sa.Numeric(20, 2), nullable=True))
    op.add_column("instruments", sa.Column("tradeable_shares", sa.Numeric(20, 2), nullable=True))
    op.add_column("instruments", sa.Column("delisting_risk_score", sa.Numeric(5, 2), nullable=True, server_default=sa.text("0")))
    op.add_column("instruments", sa.Column("delisting_risk_reason", sa.Text(), nullable=True))
    op.add_column("instruments", sa.Column("former_ticker", sa.String(30), nullable=True))
    op.add_column("instruments", sa.Column("former_name", sa.String(200), nullable=True))
    op.add_column("instruments", sa.Column("index_category", sa.String(30), nullable=True))
    op.add_column("instruments", sa.Column("region", sa.String(10), nullable=True))
    op.add_column("instruments", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    # Migrate data from instrument_master to instruments
    # instruments already has: ticker, exchange_mic, name, asset_class, sector, currency, is_active, listed_at, created_at
    # Map: base_currency→currency (already exists), listing_date→listed_at (already exists)
    op.execute("""
        UPDATE instruments i SET
            reporting_currency = im.reporting_currency::text,
            lot_size = im.lot_size::int,
            tick_size = im.tick_size::numeric,
            subsector = im.subsector::text,
            underlying_ticker = im.underlying_ticker::text,
            suspension_date = im.suspension_date::date,
            delisting_date = im.delisting_date::date,
            board = im.board::text,
            free_float = im.free_float::numeric,
            market_cap = im.market_cap::numeric,
            listed_shares = im.listed_shares::numeric,
            tradeable_shares = im.tradeable_shares::numeric,
            delisting_risk_score = COALESCE(im.delisting_risk_score::numeric, 0),
            delisting_risk_reason = im.delisting_risk_reason::text,
            former_ticker = im.former_ticker::text,
            former_name = im.former_name::text,
            index_category = im.index_category::text,
            region = im.region::text,
            updated_at = im.updated_at::timestamptz
        FROM instrument_master im
        WHERE i.ticker = im.ticker::text;
    """)

    # Insert tickers that exist in instrument_master but not in instruments
    op.execute("""
        INSERT INTO instruments (
            ticker, exchange_mic, name, asset_class, currency, is_active,
            reporting_currency, lot_size, tick_size, sector, subsector,
            underlying_ticker, suspension_date, delisting_date, board,
            free_float, market_cap, listed_shares, tradeable_shares,
            delisting_risk_score, delisting_risk_reason, former_ticker,
            former_name, index_category, region, created_at, updated_at
        )
        SELECT
            im.ticker::text,
            im.market_mic::text,
            im.name::text,
            im.asset_class::text,
            im.base_currency::text,
            COALESCE(im.is_active::text, 't')::bool,
            im.reporting_currency::text,
            im.lot_size::int,
            im.tick_size::numeric,
            im.sector::text,
            im.subsector::text,
            im.underlying_ticker::text,
            im.suspension_date::date,
            im.delisting_date::date,
            im.board::text,
            im.free_float::numeric,
            im.market_cap::numeric,
            im.listed_shares::numeric,
            im.tradeable_shares::numeric,
            COALESCE(im.delisting_risk_score::numeric, 0),
            im.delisting_risk_reason::text,
            im.former_ticker::text,
            im.former_name::text,
            im.index_category::text,
            im.region::text,
            COALESCE(im.created_at::timestamptz, now()),
            COALESCE(im.updated_at::timestamptz, now())
        FROM instrument_master im
        WHERE NOT EXISTS (
            SELECT 1 FROM instruments i WHERE i.ticker = im.ticker::text
        );
    """)

    # Drop instrument_master, create compatibility view
    op.execute("DROP TABLE IF EXISTS instrument_master CASCADE;")
    op.execute("""
        CREATE OR REPLACE VIEW instrument_master AS
        SELECT
            i.ticker,
            i.exchange_mic AS market_mic,
            i.asset_class,
            i.name,
            i.currency AS base_currency,
            i.reporting_currency,
            i.lot_size,
            i.tick_size::text AS tick_size,
            i.is_active::text AS is_active,
            i.sector,
            i.subsector,
            i.underlying_ticker,
            i.listed_at::text AS listing_date,
            i.suspension_date::text AS suspension_date,
            i.delisting_date::text AS delisting_date,
            i.created_at::text AS created_at,
            i.updated_at::text AS updated_at,
            i.board,
            i.free_float::text AS free_float,
            i.market_cap::text AS market_cap,
            i.listed_shares::text AS listed_shares,
            i.tradeable_shares::text AS tradeable_shares,
            i.delisting_risk_score::text AS delisting_risk_score,
            i.delisting_risk_reason::text AS delisting_risk_reason,
            i.former_ticker,
            i.former_name,
            i.index_category,
            i.region,
            NULL::text AS trading_status
        FROM instruments i;
    """)

    # ── 4. Drop redundant prediction columns from stock_personality ─────────
    # These columns are already in stock_prediction (intentionally split)
    op.execute("""
        ALTER TABLE stock_personality
        DROP COLUMN IF EXISTS ml_signal,
        DROP COLUMN IF EXISTS multifactor_signal,
        DROP COLUMN IF EXISTS composite_signal,
        DROP COLUMN IF EXISTS factors_summary,
        DROP COLUMN IF EXISTS predicted_direction,
        DROP COLUMN IF EXISTS predicted_price,
        DROP COLUMN IF EXISTS predicted_return_pct,
        DROP COLUMN IF EXISTS prediction_confidence,
        DROP COLUMN IF EXISTS prediction_updated_at;
    """)

    # ── 5. Add FK constraints for ticker columns to instruments ─────────────
    # These are critical for referential integrity
    # NOTE: stock_prices is a partitioned table — PostgreSQL does not support
    # NOT VALID FK on partitioned tables, so it is excluded.
    ticker_tables = [
        "foreign_flow",
        "fundamental_data",
        "technical_indicators",
        "technical_indicators_wide",
        "daily_trading_stats",
        "daily_risk_metrics",
        "scores",
        "dividends",
        "corporate_governance",
        "esg_scores",
        "news_sentiment",
        "pattern_analysis",
        "trading_suspensions",
        "valuation_cache",
        "broker_flow",
        "watchlist",
        "stock_prediction",
    ]
    for tbl in ticker_tables:
        constraint_name = f"fk_{tbl}_ticker"
        op.execute(
            f"ALTER TABLE {tbl} "
            f"ADD CONSTRAINT {constraint_name} "
            f"FOREIGN KEY (ticker) REFERENCES instruments(ticker) "
            f"ON DELETE CASCADE ON UPDATE CASCADE NOT VALID;"
        )

    # ── 6. Add unique constraints where missing ─────────────────────────────
    # PostgreSQL doesn't support ADD CONSTRAINT IF NOT EXISTS, use DO blocks.
    # NOTE: Unique constraints on large tables (daily_risk_metrics 8.9M rows,
    # daily_trading_stats 1M rows) require building indexes which need significant
    # disk space. They are deferred to a future migration when disk space allows.
    # Only add unique constraint on small tables here.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_ns_ticker_date_headline') THEN
                ALTER TABLE news_sentiment ADD CONSTRAINT uq_ns_ticker_date_headline UNIQUE (ticker, date, headline);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Remove unique constraints
    op.execute("ALTER TABLE daily_risk_metrics DROP CONSTRAINT IF EXISTS uq_drm_ticker_date;")
    op.execute("ALTER TABLE news_sentiment DROP CONSTRAINT IF EXISTS uq_ns_ticker_date_headline;")
    op.execute("ALTER TABLE daily_trading_stats DROP CONSTRAINT IF EXISTS uq_dts_ticker_date;")

    # Remove FK constraints
    ticker_tables = [
        "foreign_flow",
        "fundamental_data",
        "technical_indicators",
        "technical_indicators_wide",
        "daily_trading_stats",
        "daily_risk_metrics",
        "scores",
        "dividends",
        "corporate_governance",
        "esg_scores",
        "news_sentiment",
        "pattern_analysis",
        "trading_suspensions",
        "valuation_cache",
        "broker_flow",
        "watchlist",
        "stock_prediction",
    ]
    for tbl in ticker_tables:
        op.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS fk_{tbl}_ticker;")

    # Restore prediction columns to stock_personality
    op.execute("""
        ALTER TABLE stock_personality
        ADD COLUMN IF NOT EXISTS ml_signal numeric(6,4),
        ADD COLUMN IF NOT EXISTS multifactor_signal numeric(6,4),
        ADD COLUMN IF NOT EXISTS composite_signal numeric(6,4),
        ADD COLUMN IF NOT EXISTS factors_summary text,
        ADD COLUMN IF NOT EXISTS predicted_direction varchar(10),
        ADD COLUMN IF NOT EXISTS predicted_price numeric(15,2),
        ADD COLUMN IF NOT EXISTS predicted_return_pct numeric(8,4),
        ADD COLUMN IF NOT EXISTS prediction_confidence numeric(5,3),
        ADD COLUMN IF NOT EXISTS prediction_updated_at timestamptz;
    """)

    # Recreate instrument_master table from view
    op.execute("DROP VIEW IF EXISTS instrument_master;")
    op.execute("""
        CREATE TABLE instrument_master (
            ticker text PRIMARY KEY,
            market_mic text,
            asset_class text,
            name text,
            base_currency text,
            reporting_currency text,
            lot_size int,
            tick_size text,
            is_active text,
            sector text,
            subsector text,
            underlying_ticker text,
            listing_date text,
            delisting_date text,
            created_at text,
            updated_at text,
            board text,
            free_float text,
            market_cap text,
            listed_shares text,
            tradeable_shares text,
            delisting_risk_score text,
            delisting_risk_reason text,
            former_ticker text,
            former_name text,
            index_category text,
            region text,
            suspension_date text,
            trading_status text
        );
    """)

    # Recreate market_registry table from view
    op.execute("DROP VIEW IF EXISTS market_registry;")
    op.execute("""
        CREATE TABLE market_registry (
            mic_code varchar(10) PRIMARY KEY,
            country_code varchar(3) NOT NULL,
            timezone varchar(50) NOT NULL,
            trading_hours text NOT NULL,
            supports_dst boolean DEFAULT false,
            settlement_cycle int DEFAULT 2,
            tick_size_rule text,
            lot_size int,
            currency varchar(3) NOT NULL,
            data_suffix varchar(10),
            trading_status varchar(20) DEFAULT 'active',
            created_at timestamptz,
            updated_at timestamptz
        );
    """)

    # Recreate broker and broker_bursa
    op.execute("""
        CREATE TABLE broker (
            id_broker int PRIMARY KEY,
            nama_broker text NOT NULL,
            created_at timestamptz
        );
    """)
    op.execute("""
        CREATE TABLE broker_bursa (
            id_broker int,
            id_bursa int,
            PRIMARY KEY (id_broker, id_bursa)
        );
    """)

    # Remove added columns from exchanges
    op.execute("""
        ALTER TABLE exchanges
        DROP COLUMN IF EXISTS trading_hours,
        DROP COLUMN IF EXISTS supports_dst,
        DROP COLUMN IF EXISTS settlement_cycle,
        DROP COLUMN IF EXISTS tick_size_rule,
        DROP COLUMN IF EXISTS data_suffix,
        DROP COLUMN IF EXISTS trading_status,
        DROP COLUMN IF EXISTS updated_at;
    """)

    # Remove added columns from instruments
    op.execute("""
        ALTER TABLE instruments
        DROP COLUMN IF EXISTS reporting_currency,
        DROP COLUMN IF EXISTS lot_size,
        DROP COLUMN IF EXISTS tick_size,
        DROP COLUMN IF EXISTS subsector,
        DROP COLUMN IF EXISTS underlying_ticker,
        DROP COLUMN IF EXISTS suspension_date,
        DROP COLUMN IF EXISTS delisting_date,
        DROP COLUMN IF EXISTS board,
        DROP COLUMN IF EXISTS free_float,
        DROP COLUMN IF EXISTS market_cap,
        DROP COLUMN IF EXISTS listed_shares,
        DROP COLUMN IF EXISTS tradeable_shares,
        DROP COLUMN IF EXISTS delisting_risk_score,
        DROP COLUMN IF EXISTS delisting_risk_reason,
        DROP COLUMN IF EXISTS former_ticker,
        DROP COLUMN IF EXISTS former_name,
        DROP COLUMN IF EXISTS index_category,
        DROP COLUMN IF EXISTS region,
        DROP COLUMN IF EXISTS updated_at;
    """)
