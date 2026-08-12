"""Add ablation_runs + ablation_scorecards tables for engine ablation persistence.

Stores ablation study results (per-engine scorecards with KEEP/MARGINAL/REMOVE
verdicts) so that historical ablation runs can be queried and compared without
reading JSON files from disk.

Tables:
  ablation_runs       — one row per ablation execution (metadata)
  ablation_scorecards — one row per engine per run (metrics + verdict)

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ablation_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tickers", sa.Text, nullable=False),          # JSON array
        sa.Column("period", sa.String(100), nullable=False),     # e.g. "2024-01-01 to 2026-08-12"
        sa.Column("total_engines", sa.Integer, nullable=False, default=0),
        sa.Column("keep_count", sa.Integer, nullable=False, default=0),
        sa.Column("marginal_count", sa.Integer, nullable=False, default=0),
        sa.Column("remove_count", sa.Integer, nullable=False, default=0),
        sa.Column("bonferroni_alpha", sa.Float, nullable=False),
        sa.Column("multiple_testing_correction", sa.String(50), nullable=False, default="Bonferroni"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_ablation_runs_ts", "ablation_runs", ["run_timestamp"])

    op.create_table(
        "ablation_scorecards",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer,
                  sa.ForeignKey("ablation_runs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("engine_name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(30), nullable=True),          # signal_enhancer / market_context
        sa.Column("signal_type", sa.String(30), nullable=True),        # directional / timing / filter / sizing / context
        sa.Column("verdict", sa.String(10), nullable=False),           # KEEP / MARGINAL / REMOVE
        sa.Column("composite_score", sa.Float, nullable=False, default=0.0),
        sa.Column("delta_sharpe", sa.Float, nullable=False, default=0.0),
        sa.Column("delta_alpha", sa.Float, nullable=False, default=0.0),
        sa.Column("delta_win_rate", sa.Float, nullable=False, default=0.0),
        sa.Column("p_value", sa.Float, nullable=False, default=1.0),
        sa.Column("is_significant", sa.Boolean, nullable=False, default=False),
        sa.Column("n_observations", sa.Integer, nullable=False, default=0),
        sa.Column("isolated_sharpe", sa.Float, nullable=False, default=0.0),
        sa.Column("baseline_sharpe", sa.Float, nullable=False, default=0.0),
        sa.Column("reasons", sa.Text, nullable=True),                 # JSON array
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_ablation_sc_run", "ablation_scorecards", ["run_id"])
    op.create_index("idx_ablation_sc_engine", "ablation_scorecards", ["engine_name"])
    op.create_index("idx_ablation_sc_verdict", "ablation_scorecards", ["verdict"])


def downgrade() -> None:
    op.drop_table("ablation_scorecards")
    op.drop_table("ablation_runs")
