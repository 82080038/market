"""Add recompute dependency graph tables.

Tracks which recompute functions depend on which data sources (tables),
so when new data arrives from one module, only dependent modules recompute.

Tables:
- recompute_dependencies: maps each recompute function to its input data sources
- recompute_triggers: logs data update events and which recomputes were triggered
"""

from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── recompute_dependencies ──────────────────────────────────────
    op.create_table(
        "recompute_dependencies",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("function_name", sa.Text(), nullable=False,
                  comment="e.g. recompute_scores, recompute_technical_indicators"),
        sa.Column("data_source", sa.Text(), nullable=False,
                  comment="Input table or data source this function depends on"),
        sa.Column("source_type", sa.Text(), nullable=False, server_default="table",
                  comment="table, api, computed, external"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("true"),
                  comment="If true, function cannot run without this source"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("function_name", "data_source", name="uq_recompute_dep_fn_source"),
    )
    op.create_index("ix_recompute_dep_function", "recompute_dependencies", ["function_name"])
    op.create_index("ix_recompute_dep_source", "recompute_dependencies", ["data_source"])

    # ── recompute_triggers ──────────────────────────────────────────
    op.create_table(
        "recompute_triggers",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("triggered_by", sa.Text(), nullable=False,
                  comment="What triggered this: e.g. 'fetch_eod', 'fetch_fundamental', 'manual'"),
        sa.Column("data_source_updated", sa.Text(), nullable=False,
                  comment="Which data source was updated"),
        sa.Column("functions_triggered", sa.JSON(), nullable=False,
                  comment="List of recompute function names that were triggered"),
        sa.Column("functions_skipped", sa.JSON(), nullable=True,
                  comment="List of functions that were skipped (not dependent)"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending",
                  comment="pending, running, completed, failed"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("rows_affected", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_recompute_trigger_source", "recompute_triggers", ["data_source_updated"])
    op.create_index("ix_recompute_trigger_status", "recompute_triggers", ["status"])

    # ── Seed dependency graph ───────────────────────────────────────
    op.execute("""
        INSERT INTO recompute_dependencies (function_name, data_source, source_type, is_required, description) VALUES
        -- recompute_technical_indicators: depends on stock_prices (OHLCV)
        ('recompute_technical_indicators', 'stock_prices', 'table', true, 'OHLCV price data for indicator calculation'),
        ('recompute_technical_indicators', 'instruments', 'table', true, 'Ticker list to process'),

        -- recompute_scores: depends on stock_prices + fundamentals + macro + global + foreign_flow + news + alpha + policy_events + seasonal + earnings
        ('recompute_scores', 'stock_prices', 'table', true, 'OHLCV for technical engine + alpha signals'),
        ('recompute_scores', 'fundamental_data', 'table', false, 'PE/PB/ROE for fundamental score'),
        ('recompute_scores', 'fundamental_quarterly', 'table', false, 'Quarterly fundamentals'),
        ('recompute_scores', 'macro_data', 'table', false, 'Macro indicators for macro score'),
        ('recompute_scores', 'foreign_flow', 'table', false, 'Foreign net flow for sentiment'),
        ('recompute_scores', 'policy_events', 'table', false, 'Policy events for event score'),
        ('recompute_scores', 'external_events', 'table', false, 'External events for event score'),
        ('recompute_scores', 'seasonal_patterns', 'table', false, 'Seasonal patterns for seasonal score'),
        ('recompute_scores', 'earnings_calendar', 'table', false, 'Earnings calendar for earnings score'),
        ('recompute_scores', 'instruments', 'table', true, 'Ticker list'),

        -- recompute_relationship_matrix: depends on stock_prices (global + IDX)
        ('recompute_relationship_matrix', 'stock_prices', 'table', true, 'Price data for correlation matrix'),
        ('recompute_relationship_matrix', 'instruments', 'table', true, 'Ticker list'),

        -- recompute_fear_greed: depends on stock_prices (^VIX, ^GSPC, ^JKSE)
        ('recompute_fear_greed', 'stock_prices', 'table', true, 'VIX, S&P 500, IHSG for F&G calculation'),

        -- recompute_stock_personality: depends on stock_prices + technical_indicators
        ('recompute_stock_personality', 'stock_prices', 'table', true, 'OHLCV for personality profiling'),
        ('recompute_stock_personality', 'technical_indicators_wide', 'table', false, 'Pre-computed indicators'),

        -- recompute_ml_labels: depends on stock_prices
        ('recompute_ml_labels', 'stock_prices', 'table', true, 'OHLCV for ML label generation'),
        ('recompute_ml_labels', 'instruments', 'table', true, 'Ticker list'),

        -- recompute_market_regimes: depends on stock_prices (^JKSE) + fear_greed + foreign_flow
        ('recompute_market_regimes', 'stock_prices', 'table', true, 'IHSG for trend/regime detection'),
        ('recompute_market_regimes', 'fear_greed', 'table', false, 'Fear & Greed for sentiment regime'),
        ('recompute_market_regimes', 'foreign_flow', 'table', false, 'Foreign flow for flow regime'),

        -- recompute_weights: depends on scores (historical accuracy)
        ('recompute_weights', 'scores', 'table', true, 'Historical scores for weight optimization'),
        ('recompute_weights', 'stock_prices', 'table', false, 'Forward returns for accuracy evaluation'),

        -- recompute_cross_market: depends on stock_prices (global tickers)
        ('recompute_cross_market', 'stock_prices', 'table', true, 'Global + IDX price data for cross-market'),

        -- recompute_holiday_effects: depends on exchange_holidays + stock_prices
        ('recompute_holiday_effects', 'exchange_holidays', 'table', true, 'Holiday calendar'),
        ('recompute_holiday_effects', 'stock_prices', 'table', true, 'OHLCV for return calculation around holidays'),

        -- recompute_astronacci_cycles: depends on stock_prices (astronomical data computed)
        ('recompute_astronacci_cycles', 'stock_prices', 'table', false, 'Price data for cycle correlation'),

        -- recompute_instrument_profiles: depends on stock_prices
        ('recompute_instrument_profiles', 'stock_prices', 'table', true, 'OHLCV for behavior profiling'),
        ('recompute_instrument_profiles', 'instruments', 'table', true, 'Ticker list'),

        -- recompute_cross_market_coefficients: depends on stock_prices + causal_relationships
        ('recompute_cross_market_coefficients', 'stock_prices', 'table', true, 'Price data for Granger causality'),
        ('recompute_cross_market_coefficients', 'causal_relationships', 'table', false, 'Pre-computed causality'),

        -- recompute_dcc_garch: depends on stock_prices (global + IDX)
        ('recompute_dcc_garch', 'stock_prices', 'table', true, 'Price data for DCC-GARCH estimation'),

        -- recompute_seasonal_patterns: depends on stock_prices
        ('recompute_seasonal_patterns', 'stock_prices', 'table', true, 'OHLCV for seasonal pattern detection'),

        -- recompute_macro_correlation: depends on macro_data + stock_prices
        ('recompute_macro_correlation', 'macro_data', 'table', true, 'Macro indicators'),
        ('recompute_macro_correlation', 'stock_prices', 'table', true, 'Stock returns for correlation'),

        -- recompute_causal_relationships: depends on stock_prices
        ('recompute_causal_relationships', 'stock_prices', 'table', true, 'Price data for Granger causality test'),

        -- recompute_satellite_correlation: depends on satellite_observations + stock_prices
        ('recompute_satellite_correlation', 'satellite_observations', 'table', true, 'Weather/satellite data'),
        ('recompute_satellite_correlation', 'stock_prices', 'table', true, 'Stock returns for correlation');
    """)


def downgrade() -> None:
    op.drop_index("ix_recompute_trigger_status", table_name="recompute_triggers")
    op.drop_index("ix_recompute_trigger_source", table_name="recompute_triggers")
    op.drop_table("recompute_triggers")
    op.drop_index("ix_recompute_dep_source", table_name="recompute_dependencies")
    op.drop_index("ix_recompute_dep_function", table_name="recompute_dependencies")
    op.drop_table("recompute_dependencies")
