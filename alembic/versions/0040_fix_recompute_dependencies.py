"""Fix recompute_dependencies: remove 3 phantom deps, add 5 missing deps.

Audit found discrepancies between dependency graph registered in DB
(migration 0033) and actual code dependencies:

PHANTOM (registered but not read by code):
- recompute_scores → fundamental_quarterly (code only reads fundamental_data)
- recompute_scores → macro_data (macro engine uses hard-coded global tickers, not macro_data table)
- recompute_stock_personality → technical_indicators_wide (code only reads OHLCV)

MISSING (read by code but not registered):
- recompute_fear_greed → recompute_watermark (incremental recompute)
- recompute_ml_labels → recompute_watermark (incremental recompute)
- recompute_market_regimes → recompute_watermark (incremental recompute)
- recompute_stock_personality → instruments (ticker list via _load_all_idx_tickers)
- recompute_weights → instruments (ticker list via _load_all_idx_tickers)

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Remove PHANTOM dependencies (registered but not read by code) ──
    op.execute("""
        DELETE FROM recompute_dependencies
        WHERE function_name = 'recompute_scores' AND data_source = 'fundamental_quarterly'
    """)
    op.execute("""
        DELETE FROM recompute_dependencies
        WHERE function_name = 'recompute_scores' AND data_source = 'macro_data'
    """)
    op.execute("""
        DELETE FROM recompute_dependencies
        WHERE function_name = 'recompute_stock_personality' AND data_source = 'technical_indicators_wide'
    """)

    # ── Add MISSING dependencies (read by code but not registered) ──
    # Use ON CONFLICT to be idempotent (unique constraint: function_name + data_source)
    op.execute("""
        INSERT INTO recompute_dependencies (function_name, data_source, source_type, is_required, description)
        VALUES
        ('recompute_fear_greed', 'recompute_watermark', 'table', false,
         'Watermark for incremental recompute (fallback to full if missing)'),
        ('recompute_ml_labels', 'recompute_watermark', 'table', false,
         'Watermark for incremental recompute (fallback to full if missing)'),
        ('recompute_market_regimes', 'recompute_watermark', 'table', false,
         'Watermark for incremental recompute (fallback to full if missing)'),
        ('recompute_stock_personality', 'instruments', 'table', true,
         'Ticker list via _load_all_idx_tickers'),
        ('recompute_weights', 'instruments', 'table', true,
         'Ticker list for sampling via _load_all_idx_tickers')
        ON CONFLICT (function_name, data_source) DO NOTHING
    """)


def downgrade() -> None:
    # Re-add phantom dependencies
    op.execute("""
        INSERT INTO recompute_dependencies (function_name, data_source, source_type, is_required, description)
        VALUES
        ('recompute_scores', 'fundamental_quarterly', 'table', false, 'Quarterly fundamentals'),
        ('recompute_scores', 'macro_data', 'table', false, 'Macro indicators for macro score'),
        ('recompute_stock_personality', 'technical_indicators_wide', 'table', false, 'Pre-computed indicators')
        ON CONFLICT (function_name, data_source) DO NOTHING
    """)

    # Remove added missing dependencies
    op.execute("""
        DELETE FROM recompute_dependencies
        WHERE function_name = 'recompute_fear_greed' AND data_source = 'recompute_watermark'
    """)
    op.execute("""
        DELETE FROM recompute_dependencies
        WHERE function_name = 'recompute_ml_labels' AND data_source = 'recompute_watermark'
    """)
    op.execute("""
        DELETE FROM recompute_dependencies
        WHERE function_name = 'recompute_market_regimes' AND data_source = 'recompute_watermark'
    """)
    op.execute("""
        DELETE FROM recompute_dependencies
        WHERE function_name = 'recompute_stock_personality' AND data_source = 'instruments'
    """)
    op.execute("""
        DELETE FROM recompute_dependencies
        WHERE function_name = 'recompute_weights' AND data_source = 'instruments'
    """)
