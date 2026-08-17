"""Market Influence Knowledge Base — central table for influence mapping.

Consolidates data from 4 scattered tables into one queryable knowledge base:
  - cross_market_coefficients (Granger causality global→IDX)
  - causal_relationships (Granger causality per-ticker)
  - commodity_to_stock_map (commodity sensitivity per stock)
  - pustaka/102 sector-global link engine (sector→driver mapping)

The table answers: "What influences ticker X, from which source, in what
direction, with what lag, through what mechanism, and how strong?"

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_influence_kb",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        # What is influenced
        sa.Column("target_ticker", sa.String(30), nullable=False, index=True),
        sa.Column("target_sector", sa.String(50), nullable=True),
        # What influences it
        sa.Column("source_ticker", sa.String(30), nullable=False, index=True),
        sa.Column("source_name", sa.String(100), nullable=True),
        sa.Column("source_layer", sa.String(20), nullable=True),
        # Relationship
        sa.Column("influence_type", sa.String(30), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("lag_days", sa.Integer, nullable=True),
        sa.Column("strength", sa.Numeric(5, 4), nullable=True),
        sa.Column("p_value", sa.Numeric(8, 5), nullable=True),
        sa.Column("mechanism", sa.Text, nullable=True),
        # Metadata
        sa.Column("regime", sa.String(10), nullable=True),
        sa.Column("source_table", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("target_ticker", "source_ticker", "lag_days", "influence_type",
                            name="uq_mikb_target_source_lag_type"),
    )

    op.create_index("idx_mikb_target", "market_influence_kb", ["target_ticker"])
    op.create_index("idx_mikb_source", "market_influence_kb", ["source_ticker"])
    op.create_index("idx_mikb_sector", "market_influence_kb", ["target_sector"])
    op.create_index("idx_mikb_type", "market_influence_kb", ["influence_type"])

    # 1. Seed from pustaka/102 sector-global link engine mapping
    # These are THEORETICAL mappings from the pustaka — sector → global driver
    op.execute("""
        INSERT INTO market_influence_kb (target_ticker, target_sector, source_ticker, source_name, source_layer, influence_type, direction, lag_days, strength, mechanism, source_table, is_active)
        SELECT
            i.ticker,
            i.sector,
            d.source_ticker,
            d.source_name,
            d.source_layer,
            'sector_global_link',
            d.direction,
            d.lag_days,
            0.5,
            d.mechanism,
            'pustaka_102',
            true
        FROM instruments i
        JOIN (
            -- Energy sector
            SELECT 'Energy' as sector, 'CL=F' as source_ticker, 'Crude Oil (NYMEX)' as source_name, 'commodity' as source_layer, 'positive' as direction, 1 as lag_days, 'Revenue driver: oil price → energy sector earnings' as mechanism
            UNION ALL SELECT 'Energy', '^GSPC', 'S&P 500', 'global_index', 'positive', 1, 'Sentiment: global risk appetite → energy stocks'
            -- Basic Materials
            UNION ALL SELECT 'Basic Materials', 'GC=F', 'Gold (COMEX)', 'commodity', 'mixed', 1, 'Commodity price: gold → mining revenue'
            UNION ALL SELECT 'Basic Materials', '000001.SS', 'Shanghai Composite', 'global_index', 'positive', 0, 'China demand: industrial cycle → basic materials'
            -- Financial Services
            UNION ALL SELECT 'Financial Services', '^TNX', 'US 10Y Treasury Yield', 'macro_rate', 'negative', 1, 'Rate sensitivity: yield↑ → bank margins compressed'
            UNION ALL SELECT 'Financial Services', '^GSPC', 'S&P 500', 'global_index', 'positive', 1, 'Sentiment: global risk appetite → financial stocks'
            -- Consumer Defensive
            UNION ALL SELECT 'Consumer Defensive', 'IDR=X', 'USD/IDR Exchange Rate', 'fx', 'negative', 1, 'Import cost: weak IDR → consumer goods cost↑'
            UNION ALL SELECT 'Consumer Defensive', '^GSPC', 'S&P 500', 'global_index', 'positive', 1, 'Risk appetite: global sentiment → defensive stocks'
            -- Consumer Cyclical
            UNION ALL SELECT 'Consumer Cyclical', '^IXIC', 'Nasdaq Composite', 'global_index', 'positive', 1, 'Risk appetite: discretionary spending → cyclical stocks'
            UNION ALL SELECT 'Consumer Cyclical', '^GSPC', 'S&P 500', 'global_index', 'positive', 1, 'Sentiment: global risk appetite → cyclical stocks'
            -- Communication Services
            UNION ALL SELECT 'Communication Services', '^IXIC', 'Nasdaq Composite', 'global_index', 'positive', 1, 'Global tech sentiment → telecom/media stocks'
            -- Industrials
            UNION ALL SELECT 'Industrials', '000001.SS', 'Shanghai Composite', 'global_index', 'positive', 0, 'China demand: industrial cycle → industrials'
            UNION ALL SELECT 'Industrials', '^GSPC', 'S&P 500', 'global_index', 'positive', 1, 'Global industrial cycle → industrials'
            -- Real Estate
            UNION ALL SELECT 'Real Estate', '^TNX', 'US 10Y Treasury Yield', 'macro_rate', 'negative', 1, 'Rate sensitivity: yield↑ → property financing cost↑'
            -- Technology
            UNION ALL SELECT 'Technology', '^IXIC', 'Nasdaq Composite', 'global_index', 'positive', 1, 'Global tech benchmark → tech stocks'
            -- Healthcare
            UNION ALL SELECT 'Healthcare', '^GSPC', 'S&P 500', 'global_index', 'positive', 1, 'Defensive global sentiment → healthcare stocks'
            -- Utilities
            UNION ALL SELECT 'Utilities', '^TNX', 'US 10Y Treasury Yield', 'macro_rate', 'negative', 1, 'Rate sensitivity: bond proxy → yield↑ → utilities↓'
        ) d ON i.sector = d.sector
        WHERE i.is_active = true AND i.data_layer = 'idx_equity'
        ON CONFLICT DO NOTHING;
    """)

    # 2. Seed from commodity_to_stock_map (empirical sensitivity)
    op.execute("""
        INSERT INTO market_influence_kb (target_ticker, target_sector, source_ticker, source_name, source_layer, influence_type, direction, lag_days, strength, mechanism, source_table, is_active)
        SELECT
            c.ticker,
            c.sector,
            CASE c.commodity_series
                WHEN 'CRUDE_OIL' THEN 'CL=F'
                WHEN 'GOLD' THEN 'GC=F'
                WHEN 'COPPER' THEN 'HG=F'
                WHEN 'CPO' THEN 'CPO=F'
                WHEN 'NEWCASTLE_COAL' THEN 'CL=F'
                WHEN 'NICKEL' THEN 'NICK.L'
                WHEN 'TIN' THEN 'TIN.L'
                ELSE c.commodity_series
            END,
            c.commodity_series,
            'commodity',
            'commodity_sensitivity',
            'positive',
            1,
            c.sensitivity,
            'Commodity price directly affects revenue/earnings',
            'commodity_to_stock_map',
            true
        FROM commodity_to_stock_map c
        ON CONFLICT DO NOTHING;
    """)

    # 3. Seed from causal_relationships (Granger causality, p<0.05 only)
    op.execute("""
        INSERT INTO market_influence_kb (target_ticker, source_ticker, source_layer, influence_type, direction, lag_days, strength, p_value, mechanism, source_table, is_active)
        SELECT
            cr.effect_ticker,
            cr.cause_ticker,
            CASE
                WHEN cr.cause_ticker LIKE '^%' THEN 'global_index'
                WHEN cr.cause_ticker LIKE '%=X' THEN 'fx'
                WHEN cr.cause_ticker LIKE '%.F' THEN 'commodity'
                WHEN cr.cause_ticker LIKE '%.L' THEN 'commodity'
                WHEN cr.cause_ticker LIKE 'CL%' OR cr.cause_ticker LIKE 'GC%' OR cr.cause_ticker LIKE 'HG%' OR cr.cause_ticker LIKE 'SI%' THEN 'commodity'
                WHEN cr.cause_ticker LIKE 'CPO%' THEN 'commodity'
                WHEN cr.cause_ticker LIKE 'MTF%' THEN 'commodity'
                ELSE 'idx_equity'
            END,
            'granger_causality',
            cr.direction,
            cr.lag_days,
            NULL,
            cr.p_value,
            'Granger causality test: source returns predict target returns',
            'causal_relationships',
            true
        FROM causal_relationships cr
        WHERE cr.p_value < 0.05
        ON CONFLICT DO NOTHING;
    """)

    # 4. Seed from cross_market_coefficients (global index → ^JKSE)
    op.execute("""
        INSERT INTO market_influence_kb (target_ticker, target_sector, source_ticker, source_name, source_layer, influence_type, direction, lag_days, strength, p_value, regime, mechanism, source_table, is_active)
        SELECT
            cmc.target_ticker,
            'INDEX',
            cmc.source_index,
            cmc.source_index,
            'global_index',
            'cross_market_coefficient',
            CASE WHEN cmc.coefficient > 0 THEN 'positive' WHEN cmc.coefficient < 0 THEN 'negative' ELSE 'neutral' END,
            cmc.lag_days,
            ABS(cmc.coefficient),
            cmc.p_value,
            cmc.regime,
            'Granger causality with asymmetric up/down coefficients',
            'cross_market_coefficients',
            true
        FROM cross_market_coefficients cmc
        WHERE cmc.p_value < 0.05
        ON CONFLICT DO NOTHING;
    """)

    # 5. Add macro_data series as influence sources
    # BI Rate → all IDX (monetary policy)
    op.execute("""
        INSERT INTO market_influence_kb (target_ticker, target_sector, source_ticker, source_name, source_layer, influence_type, direction, lag_days, strength, mechanism, source_table, is_active)
        SELECT i.ticker, i.sector, 'BI_7DAY_REPO_RATE', 'BI 7-Day Repo Rate', 'macro_data', 'macro_policy', 'negative', 0, 0.7,
               'BI Rate↑ → liquidity tightening → equity valuation↓',
               'macro_data',
               true
        FROM instruments i
        WHERE i.is_active = true AND i.data_layer = 'idx_equity'
          AND i.sector IN ('Financial Services', 'Real Estate', 'Utilities', 'Consumer Cyclical', 'Consumer Defensive')
        ON CONFLICT DO NOTHING;
    """)
    # USD/IDR → all IDX (foreign flow)
    op.execute("""
        INSERT INTO market_influence_kb (target_ticker, target_sector, source_ticker, source_name, source_layer, influence_type, direction, lag_days, strength, mechanism, source_table, is_active)
        SELECT i.ticker, i.sector, 'USD_IDR', 'USD/IDR Exchange Rate', 'macro_data', 'fx_flow', 'negative', 1, 0.6,
               'USD/IDR↑ → foreign outflow → IDX↓',
               'macro_data',
               true
        FROM instruments i
        WHERE i.is_active = true AND i.data_layer = 'idx_equity'
        ON CONFLICT DO NOTHING;
    """)
    # VIX → all IDX (risk sentiment)
    op.execute("""
        INSERT INTO market_influence_kb (target_ticker, target_sector, source_ticker, source_name, source_layer, influence_type, direction, lag_days, strength, mechanism, source_table, is_active)
        SELECT i.ticker, i.sector, 'VIX', 'CBOE Volatility Index', 'macro_data', 'risk_sentiment', 'negative', 1, 0.5,
               'VIX↑ → risk-off → EM equity outflow → IDX↓',
               'macro_data',
               true
        FROM instruments i
        WHERE i.is_active = true AND i.data_layer = 'idx_equity'
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_index("idx_mikb_type", table_name="market_influence_kb")
    op.drop_index("idx_mikb_sector", table_name="market_influence_kb")
    op.drop_index("idx_mikb_source", table_name="market_influence_kb")
    op.drop_index("idx_mikb_target", table_name="market_influence_kb")
    op.drop_table("market_influence_kb")
