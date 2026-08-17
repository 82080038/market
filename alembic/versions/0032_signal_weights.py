"""Add signal_weights table for DB-backed dynamic weight configuration.

Stores weights for MarketContext.composite_signal() and DecisionEngine factors
so they can be dynamically updated/optimized without code changes.

Schema:
- scope: 'market_context' or 'decision_engine'
- sector: sector-specific override or 'DEFAULT'
- signal_name: e.g. 'fundamental', 'alpha', 'prediction', 'holiday'
- weight: 0.0 to 1.0
- is_active: enable/disable individual signals
- optimized_at: last optimization timestamp
- optimization_score: accuracy metric from last optimization run
"""

from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_weights",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("scope", sa.Text(), nullable=False, comment="market_context or decision_engine"),
        sa.Column("sector", sa.Text(), nullable=False, server_default="DEFAULT",
                  comment="Sector-specific override or DEFAULT"),
        sa.Column("signal_name", sa.Text(), nullable=False, comment="e.g. fundamental, alpha, prediction"),
        sa.Column("weight", sa.Float(), nullable=False, comment="0.0 to 1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("optimized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimization_score", sa.Float(), nullable=True,
                  comment="Accuracy metric from last optimization"),
        sa.Column("optimization_method", sa.Text(), nullable=True,
                  comment="e.g. grid_search, bayesian, manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("scope", "sector", "signal_name", name="uq_signal_weights_scope_sector_signal"),
    )

    op.create_index("ix_signal_weights_scope", "signal_weights", ["scope"])
    op.create_index("ix_signal_weights_sector", "signal_weights", ["sector"])

    # Seed default MarketContext weights
    op.execute("""
        INSERT INTO signal_weights (scope, sector, signal_name, weight, is_active) VALUES
        ('market_context', 'DEFAULT', 'fundamental', 0.10, true),
        ('market_context', 'DEFAULT', 'macro', 0.08, true),
        ('market_context', 'DEFAULT', 'sentiment', 0.05, true),
        ('market_context', 'DEFAULT', 'flow', 0.07, true),
        ('market_context', 'DEFAULT', 'cross_market', 0.04, true),
        ('market_context', 'DEFAULT', 'ml', 0.10, true),
        ('market_context', 'DEFAULT', 'news', 0.05, true),
        ('market_context', 'DEFAULT', 'commodity', 0.05, true),
        ('market_context', 'DEFAULT', 'global_sentiment', 0.08, true),
        ('market_context', 'DEFAULT', 'governance', 0.04, true),
        ('market_context', 'DEFAULT', 'astronacci', 0.02, true),
        ('market_context', 'DEFAULT', 'holiday', 0.03, true),
        ('market_context', 'DEFAULT', 'alpha', 0.08, true),
        ('market_context', 'DEFAULT', 'policy_event', 0.05, true),
        ('market_context', 'DEFAULT', 'sector_rotation', 0.04, true),
        ('market_context', 'DEFAULT', 'volume', 0.05, true),
        ('market_context', 'DEFAULT', 'seasonal', 0.04, true),
        ('market_context', 'DEFAULT', 'earnings', 0.03, true),
        ('market_context', 'DEFAULT', 'causal', 0.02, true),
        ('market_context', 'DEFAULT', 'meta_label', 0.03, true),
        -- Sector-specific: Basic Materials
        ('market_context', 'Basic Materials', 'commodity', 0.12, true),
        ('market_context', 'Basic Materials', 'macro', 0.06, true),
        ('market_context', 'Basic Materials', 'sentiment', 0.03, true),
        ('market_context', 'Basic Materials', 'alpha', 0.06, true),
        -- Sector-specific: Financial Services
        ('market_context', 'Financial Services', 'macro', 0.14, true),
        ('market_context', 'Financial Services', 'flow', 0.10, true),
        ('market_context', 'Financial Services', 'commodity', 0.0, true),
        ('market_context', 'Financial Services', 'global_sentiment', 0.06, true),
        ('market_context', 'Financial Services', 'governance', 0.06, true),
        ('market_context', 'Financial Services', 'policy_event', 0.07, true),
        -- Sector-specific: Consumer Defensive
        ('market_context', 'Consumer Defensive', 'fundamental', 0.15, true),
        ('market_context', 'Consumer Defensive', 'commodity', 0.03, true),
        ('market_context', 'Consumer Defensive', 'global_sentiment', 0.07, true),
        ('market_context', 'Consumer Defensive', 'governance', 0.06, true),
        ('market_context', 'Consumer Defensive', 'seasonal', 0.05, true),
        -- Sector-specific: Communication Services
        ('market_context', 'Communication Services', 'fundamental', 0.12, true),
        ('market_context', 'Communication Services', 'commodity', 0.0, true),
        ('market_context', 'Communication Services', 'global_sentiment', 0.07, true),
        ('market_context', 'Communication Services', 'governance', 0.06, true),
        ('market_context', 'Communication Services', 'astronacci', 0.03, true),
        -- DecisionEngine default weights
        ('decision_engine', 'DEFAULT', 'technical', 0.14, true),
        ('decision_engine', 'DEFAULT', 'fundamental', 0.16, true),
        ('decision_engine', 'DEFAULT', 'macro', 0.08, true),
        ('decision_engine', 'DEFAULT', 'global', 0.08, true),
        ('decision_engine', 'DEFAULT', 'relationship', 0.06, true),
        ('decision_engine', 'DEFAULT', 'sentiment', 0.16, true),
        ('decision_engine', 'DEFAULT', 'holiday', 0.06, true),
        ('decision_engine', 'DEFAULT', 'prediction', 0.10, true),
        ('decision_engine', 'DEFAULT', 'alpha', 0.06, true),
        ('decision_engine', 'DEFAULT', 'policy_event', 0.04, true),
        ('decision_engine', 'DEFAULT', 'sector_rotation', 0.03, true),
        ('decision_engine', 'DEFAULT', 'seasonal', 0.02, true),
        ('decision_engine', 'DEFAULT', 'earnings', 0.01, true);
    """)


def downgrade() -> None:
    op.drop_index("ix_signal_weights_sector", table_name="signal_weights")
    op.drop_index("ix_signal_weights_scope", table_name="signal_weights")
    op.drop_table("signal_weights")
