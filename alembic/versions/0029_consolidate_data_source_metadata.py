"""Consolidate data source metadata — ensure DB has complete fetch routing.

Fixes:
  1. Set data_source_url for yahoo_finance instruments (yfinance API URL)
  2. Fix idx_index URL: GetStockSummary → GetIndexSummary
  3. Add data_source_fallback column (fallback if primary fails)
  4. Add fetch_adapter column (which adapter module to use)
  5. Reclassify ^TNX as macro_rate (was volatility)
  6. Drop redundant fetch_source column (replaced by data_source_type)
  7. Add data_source_metadata JSONB for adapter-specific config
  8. Add data_source columns to exchanges table

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add new columns to instruments
    op.add_column("instruments", sa.Column("data_source_fallback", sa.String(30), nullable=True))
    op.add_column("instruments", sa.Column("fetch_adapter", sa.String(50), nullable=True))
    op.add_column("instruments", sa.Column("data_source_metadata", sa.JSON, nullable=True))

    # 2. Add data source columns to exchanges
    op.add_column("exchanges", sa.Column("primary_data_source", sa.String(30), nullable=True))
    op.add_column("exchanges", sa.Column("data_source_url", sa.String(500), nullable=True))
    op.add_column("exchanges", sa.Column("data_source_fallback", sa.String(30), nullable=True))

    # 3. Set fetch_adapter based on data_source_type
    op.execute("""
        UPDATE instruments SET fetch_adapter = 'YahooFinanceAdapter'
        WHERE data_source_type = 'yahoo_finance';
    """)
    op.execute("""
        UPDATE instruments SET fetch_adapter = 'IDXOfficialAdapter'
        WHERE data_source_type = 'idx_co_id';
    """)

    # 4. Set data_source_url for yahoo_finance instruments
    op.execute("""
        UPDATE instruments SET data_source_url = 'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
        WHERE data_source_type = 'yahoo_finance' AND data_source_url IS NULL;
    """)

    # 5. Fix idx_index URL — should be GetIndexSummary, not GetStockSummary
    op.execute("""
        UPDATE instruments SET data_source_url = 'https://www.idx.co.id/primary/TradingSummary/GetIndexSummary'
        WHERE data_source_type = 'idx_co_id' AND data_layer = 'idx_index';
    """)
    op.execute("""
        UPDATE instruments SET data_source_url = 'https://www.idx.co.id/primary/TradingSummary/GetStockSummary'
        WHERE data_source_type = 'idx_co_id' AND data_layer = 'idx_equity';
    """)

    # 6. Set fallback sources
    # idx_equity: fallback from yahoo_finance → idx_co_id
    op.execute("""
        UPDATE instruments SET data_source_fallback = 'idx_co_id'
        WHERE data_layer = 'idx_equity' AND data_source_type = 'yahoo_finance';
    """)
    # idx_index: fallback from idx_co_id → yahoo_finance (only for ^JKSE, ^JKLQ45)
    op.execute("""
        UPDATE instruments SET data_source_fallback = 'yahoo_finance'
        WHERE data_layer = 'idx_index' AND data_source_type = 'idx_co_id'
          AND ticker IN ('^JKSE', '^JKLQ45');
    """)
    # global_index, commodity, fx, etf, volatility: no reliable fallback
    # (could add investing.com or sectors.app in future)

    # 7. Reclassify ^TNX as macro_rate (10Y Treasury yield, not volatility)
    op.execute("""
        UPDATE instruments SET data_layer = 'macro_rate'
        WHERE ticker = '^TNX';
    """)
    # ^VIX and DX-Y.NYB stay as volatility

    # 8. Set data_source_metadata for idx_co_id instruments
    # (adapter-specific config: date format, params, etc.)
    op.execute("""
        UPDATE instruments SET data_source_metadata = '{"date_format": "YYYYMMDD", "response_key": "data", "batch_all": true}'::json
        WHERE data_source_type = 'idx_co_id';
    """)
    op.execute("""
        UPDATE instruments SET data_source_metadata = '{"interval": "1d", "period": "5d", "suffix": ".JK"}'::json
        WHERE data_source_type = 'yahoo_finance' AND data_layer = 'idx_equity';
    """)
    op.execute("""
        UPDATE instruments SET data_source_metadata = '{"interval": "1d", "period": "5d"}'::json
        WHERE data_source_type = 'yahoo_finance' AND data_layer IN ('global_index', 'commodity', 'fx', 'etf', 'volatility', 'macro_rate', 'fund');
    """)

    # 9. Set exchange-level data sources
    op.execute("""
        UPDATE exchanges SET
            primary_data_source = 'yahoo_finance',
            data_source_url = 'https://query1.finance.yahoo.com/v8/finance/chart/',
            data_source_fallback = 'idx_co_id'
        WHERE mic_code = 'XIDX';
    """)
    op.execute("""
        UPDATE exchanges SET
            primary_data_source = 'yahoo_finance',
            data_source_url = 'https://query1.finance.yahoo.com/v8/finance/chart/'
        WHERE mic_code IN ('XNYS', 'XNAS', 'XLON', 'XFRA', 'XHKG', 'XKLS', 'XKLSE',
                           'XASX', 'XBOM', 'XKRX', 'XSES', 'XSGX', 'XSHG', 'XTSE', 'XFXS', 'XCEC', 'OFF');
    """)
    op.execute("""
        UPDATE exchanges SET
            primary_data_source = 'idx_co_id',
            data_source_url = 'https://www.idx.co.id/primary/TradingSummary/GetIndexSummary',
            data_source_fallback = 'yahoo_finance'
        WHERE mic_code = 'XIDX' AND primary_data_source IS NULL;
    """)

    # 10. Drop redundant fetch_source column (replaced by data_source_type)
    op.drop_column("instruments", "fetch_source")


def downgrade() -> None:
    op.add_column("instruments", sa.Column("fetch_source", sa.String(30), nullable=True))
    op.execute("UPDATE instruments SET fetch_source = data_source_type;")

    op.drop_column("exchanges", "data_source_fallback")
    op.drop_column("exchanges", "data_source_url")
    op.drop_column("exchanges", "primary_data_source")

    op.drop_column("instruments", "data_source_metadata")
    op.drop_column("instruments", "fetch_adapter")
    op.drop_column("instruments", "data_source_fallback")
