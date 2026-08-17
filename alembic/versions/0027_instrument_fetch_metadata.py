"""Add fetch metadata columns to instruments table.

Database-as-source-of-truth: every module/engine must query DB before working.
These columns tell the fetch pipeline:
  - data_layer: which fetch layer owns this instrument
      (idx_equity, global_index, commodity, fx, macro_rate, etf, fund)
  - fetch_frequency: how often to fetch (EOD, INTRADAY_15M, WEEKLY, MONTHLY)
  - last_fetch_at: timestamp of last successful fetch
  - next_fetch_at: when the next fetch should happen
  - fetch_status: OK, STALE, FAILED, PAUSED, NEVER_FETCHED
  - fetch_source: data source (yahoo_finance, bps, world_bank, noaa, etc.)

Also normalizes asset_class values (lowercase 'fx' → 'FX', 'etf' → 'ETF')
and marks dead/delisted commodity tickers as inactive.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add fetch metadata columns to instruments
    op.add_column("instruments", sa.Column("data_layer", sa.String(20), nullable=True))
    op.add_column("instruments", sa.Column("fetch_frequency", sa.String(20), nullable=True))
    op.add_column("instruments", sa.Column("last_fetch_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("instruments", sa.Column("next_fetch_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("instruments", sa.Column("fetch_status", sa.String(20), nullable=True, server_default="NEVER_FETCHED"))
    op.add_column("instruments", sa.Column("fetch_source", sa.String(30), nullable=True))

    # 2. Index for fetch scheduling queries
    op.create_index("idx_instruments_data_layer", "instruments", ["data_layer"])
    op.create_index("idx_instruments_fetch_status", "instruments", ["fetch_status"])
    op.create_index("idx_instruments_next_fetch", "instruments", ["next_fetch_at"])

    # 3. Seed data_layer based on existing asset_class + exchange_mic
    op.execute("""
        UPDATE instruments SET data_layer = 'idx_equity'
        WHERE asset_class = 'EQUITY_INDIVIDUAL' AND exchange_mic = 'XIDX';
    """)
    op.execute("""
        UPDATE instruments SET data_layer = 'global_index'
        WHERE asset_class = 'INDEX_COMPOSITE' AND exchange_mic != 'XIDX';
    """)
    op.execute("""
        UPDATE instruments SET data_layer = 'idx_index'
        WHERE asset_class = 'INDEX_COMPOSITE' AND exchange_mic = 'XIDX';
    """)
    op.execute("""
        UPDATE instruments SET data_layer = 'commodity'
        WHERE asset_class = 'COMMODITY_FUTURES';
    """)
    op.execute("""
        UPDATE instruments SET data_layer = 'fx'
        WHERE asset_class IN ('FX', 'fx');
    """)
    op.execute("""
        UPDATE instruments SET data_layer = 'macro_rate'
        WHERE ticker IN ('^TNX', '^VIX', 'DX-Y.NYB');
    """)
    op.execute("""
        UPDATE instruments SET data_layer = 'etf'
        WHERE asset_class IN ('ETF', 'etf');
    """)
    op.execute("""
        UPDATE instruments SET data_layer = 'fund'
        WHERE asset_class = 'fund';
    """)
    op.execute("""
        UPDATE instruments SET data_layer = 'volatility'
        WHERE asset_class = 'VOLATILITY_RATE';
    """)

    # 4. Seed fetch_frequency based on data_layer
    op.execute("""
        UPDATE instruments SET fetch_frequency = 'EOD'
        WHERE data_layer IN ('idx_equity', 'global_index', 'commodity', 'fx', 'macro_rate', 'etf', 'volatility');
    """)
    op.execute("""
        UPDATE instruments SET fetch_frequency = 'WEEKLY'
        WHERE data_layer = 'idx_index';
    """)
    op.execute("""
        UPDATE instruments SET fetch_frequency = 'MONTHLY'
        WHERE data_layer = 'fund';
    """)

    # 5. Seed fetch_source
    op.execute("""
        UPDATE instruments SET fetch_source = 'yahoo_finance'
        WHERE data_layer IN ('idx_equity', 'global_index', 'commodity', 'fx', 'macro_rate', 'etf', 'volatility', 'idx_index');
    """)
    op.execute("""
        UPDATE instruments SET fetch_source = 'yahoo_finance'
        WHERE data_layer = 'fund';
    """)

    # 6. Normalize asset_class casing
    op.execute("UPDATE instruments SET asset_class = 'FX' WHERE asset_class = 'fx';")
    op.execute("UPDATE instruments SET asset_class = 'ETF' WHERE asset_class = 'etf';")

    # 7. Mark dead/delisted commodity tickers as inactive
    op.execute("""
        UPDATE instruments SET is_active = false, fetch_status = 'PAUSED'
        WHERE ticker IN ('FCPO=F', 'COAL=F', 'MTF=F', 'NI=F', 'TIN=F')
          AND asset_class = 'COMMODITY_FUTURES';
    """)

    # 8. Set fetch_status = 'NEVER_FETCHED' for all active instruments (default)
    op.execute("""
        UPDATE instruments SET fetch_status = 'NEVER_FETCHED'
        WHERE is_active = true AND fetch_status IS NULL;
    """)

    # 9. Update last_fetch_at from stock_prices for instruments that have data
    op.execute("""
        UPDATE instruments i
        SET last_fetch_at = sub.max_ts,
            fetch_status = 'OK'
        FROM (
            SELECT ticker, max(timestamp) as max_ts
            FROM stock_prices
            WHERE timeframe = '1d'
            GROUP BY ticker
        ) sub
        WHERE i.ticker = sub.ticker AND i.is_active = true;
    """)

    # 10. Set next_fetch_at = last_fetch_at + 1 day for OK instruments
    op.execute("""
        UPDATE instruments
        SET next_fetch_at = last_fetch_at + interval '1 day'
        WHERE fetch_status = 'OK' AND last_fetch_at IS NOT NULL;
    """)

    # 11. Mark stale: last_fetch_at older than 3 days
    op.execute("""
        UPDATE instruments
        SET fetch_status = 'STALE'
        WHERE fetch_status = 'OK'
          AND last_fetch_at IS NOT NULL
          AND last_fetch_at < now() - interval '3 days';
    """)


def downgrade() -> None:
    op.drop_index("idx_instruments_next_fetch", table_name="instruments")
    op.drop_index("idx_instruments_fetch_status", table_name="instruments")
    op.drop_index("idx_instruments_data_layer", table_name="instruments")
    op.drop_column("instruments", "fetch_source")
    op.drop_column("instruments", "fetch_status")
    op.drop_column("instruments", "next_fetch_at")
    op.drop_column("instruments", "last_fetch_at")
    op.drop_column("instruments", "fetch_frequency")
    op.drop_column("instruments", "data_layer")
