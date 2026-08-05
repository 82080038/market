"""Complete schema: 15 missing tables + 4 table column additions.

Adds tables required by pustaka/18 §13 that were missing from the initial
schema, plus columns missing from existing tables (compared to parquet global
archive).

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Column additions to existing tables ──────────────────────────────

    # instrument_master: add board, free_float, market_cap
    with op.batch_alter_table("instrument_master") as batch:
        batch.add_column(sa.Column("board", sa.String(20), nullable=True))
        batch.add_column(sa.Column("free_float", sa.Numeric(10, 4), nullable=True))
        batch.add_column(sa.Column("market_cap", sa.Numeric(20, 2), nullable=True))

    # corporate_actions: add unit
    with op.batch_alter_table("corporate_actions") as batch:
        batch.add_column(sa.Column("unit", sa.String(20), nullable=True))

    # fundamental_data: add book_value_per_share, total_liabilities, cash_flow, fiscal_year, quarter
    with op.batch_alter_table("fundamental_data") as batch:
        batch.add_column(sa.Column("book_value_per_share", sa.Numeric(20, 4), nullable=True))
        batch.add_column(sa.Column("total_liabilities", sa.Numeric(20, 2), nullable=True))
        batch.add_column(sa.Column("cash_flow", sa.Numeric(20, 2), nullable=True))
        batch.add_column(sa.Column("fiscal_year", sa.Integer, nullable=True))
        batch.add_column(sa.Column("quarter", sa.String(10), nullable=True))

    # stock_personality: add 17 columns
    with op.batch_alter_table("stock_personality") as batch:
        batch.add_column(sa.Column("avg_volume", sa.Numeric(20, 2), nullable=True))
        batch.add_column(sa.Column("avg_daily_volatility", sa.Numeric(10, 4), nullable=True))
        batch.add_column(sa.Column("volume_consistency", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("trend_strength", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("correlation_ihsg", sa.Numeric(10, 4), nullable=True))
        batch.add_column(sa.Column("net_distribution_score", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("best_pattern", sa.String(50), nullable=True))
        batch.add_column(sa.Column("best_pattern_winrate", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("worst_pattern", sa.String(50), nullable=True))
        batch.add_column(sa.Column("worst_pattern_winrate", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("total_patterns_detected", sa.Integer, nullable=True))
        batch.add_column(sa.Column("total_patterns_success", sa.Integer, nullable=True))
        batch.add_column(sa.Column("overall_pattern_winrate", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("avg_uptrend_streak", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("avg_downtrend_streak", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("profile_date", sa.Date, nullable=True))

    # ── 15 new tables ─────────────────────────────────────────────────────

    op.create_table(
        "news",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("news_id", sa.String(500), nullable=False, index=True),
        sa.Column("headline", sa.Text, nullable=True),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("published_at", sa.String(100), nullable=True),
        sa.Column("source", sa.String(200), nullable=True),
        sa.Column("entities", sa.Text, nullable=True),
        sa.Column("topic", sa.String(100), nullable=True),
        sa.Column("sentiment", sa.Numeric(5, 2), nullable=True),
        sa.Column("impact", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("news_id", name="uq_news_pk"),
    )

    op.create_table(
        "broker_flow",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False, index=True),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("broker", sa.String(20), nullable=False),
        sa.Column("buy_volume", sa.Numeric(20, 2), nullable=True),
        sa.Column("buy_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("sell_volume", sa.Numeric(20, 2), nullable=True),
        sa.Column("sell_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("net_volume", sa.Numeric(20, 2), nullable=True),
        sa.Column("net_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("source", sa.String(50), server_default="idx_scraper"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("ticker", "date", "broker", "source", name="uq_bf_pk"),
    )

    op.create_table(
        "policy_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tanggal", sa.Date, nullable=False, index=True),
        sa.Column("kategori", sa.String(50), nullable=True),
        sa.Column("judul", sa.String(500), nullable=True),
        sa.Column("instansi", sa.String(200), nullable=True),
        sa.Column("dampak", sa.String(30), nullable=True),
        sa.Column("sektor", sa.String(200), nullable=True),
        sa.Column("deskripsi", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "external_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tanggal", sa.Date, nullable=False, index=True),
        sa.Column("kategori", sa.String(50), nullable=True),
        sa.Column("judul", sa.String(500), nullable=True),
        sa.Column("lokasi", sa.String(200), nullable=True),
        sa.Column("dampak_market", sa.String(30), nullable=True),
        sa.Column("sektor", sa.String(200), nullable=True),
        sa.Column("deskripsi", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "pattern_analysis",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False, index=True),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("pattern_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("direction", sa.String(20), nullable=True),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("source", sa.String(50), server_default="technical_compute"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("ticker", "date", "pattern_type", name="uq_pa_pk"),
    )

    op.create_table(
        "trading_suspensions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False, index=True),
        sa.Column("suspend_date", sa.Date, nullable=True),
        sa.Column("resume_date", sa.Date, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("suspension_type", sa.String(50), nullable=True),
        sa.Column("source", sa.String(50), server_default="manual"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "render_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("table_name", sa.String(50), nullable=False),
        sa.Column("last_rendered", sa.DateTime, server_default=sa.func.now()),
        sa.Column("rows_rendered", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("ticker", "table_name", name="uq_rl_pk"),
    )

    op.create_table(
        "valuation_cache",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False, index=True),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("method", sa.String(30), nullable=False),
        sa.Column("intrinsic_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("market_price", sa.Numeric(20, 2), nullable=True),
        sa.Column("upside_pct", sa.Numeric(10, 2), nullable=True),
        sa.Column("assumptions", sa.Text, nullable=True),
        sa.Column("source", sa.String(50), server_default="computed"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("ticker", "date", "method", "source", name="uq_vc_pk"),
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False, index=True),
        sa.Column("quantity", sa.Numeric(20, 4), nullable=False, server_default="0"),
        sa.Column("avg_entry_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("current_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("status", sa.String(20), server_default="OPEN"),
        sa.Column("stop_loss", sa.Numeric(20, 4), nullable=True),
        sa.Column("take_profit", sa.Numeric(20, 4), nullable=True),
        sa.Column("trailing_stop_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("highest_price_since_entry", sa.Numeric(20, 4), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(20, 2), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(20, 2), nullable=True),
        sa.Column("return_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("opened_at", sa.DateTime, nullable=True),
        sa.Column("closed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False, index=True),
        sa.Column("order_type", sa.String(10), nullable=False),
        sa.Column("order_style", sa.String(20), server_default="MARKET"),
        sa.Column("quantity", sa.Numeric(20, 4), nullable=False),
        sa.Column("price", sa.Numeric(20, 4), nullable=True),
        sa.Column("total_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("fee", sa.Numeric(20, 2), nullable=True),
        sa.Column("slippage", sa.Numeric(10, 4), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(20, 2), nullable=True),
        sa.Column("status", sa.String(20), server_default="PENDING"),
        sa.Column("trigger", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "equity_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("equity", sa.Numeric(20, 2), nullable=True),
        sa.Column("cash", sa.Numeric(20, 2), nullable=True),
        sa.Column("positions_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(20, 2), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(20, 2), nullable=True),
        sa.Column("total_return_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "daily_risk_metrics",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("var_95", sa.Numeric(10, 4), nullable=True),
        sa.Column("var_99", sa.Numeric(10, 4), nullable=True),
        sa.Column("cvar_95", sa.Numeric(10, 4), nullable=True),
        sa.Column("cvar_99", sa.Numeric(10, 4), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(10, 4), nullable=True),
        sa.Column("annualized_volatility", sa.Numeric(10, 4), nullable=True),
        sa.Column("portfolio_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "trade_journal",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=True, index=True),
        sa.Column("entry_date", sa.Date, nullable=True),
        sa.Column("exit_date", sa.Date, nullable=True),
        sa.Column("entry_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("exit_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("quantity", sa.Numeric(20, 4), nullable=True),
        sa.Column("side", sa.String(10), nullable=True),
        sa.Column("pnl", sa.Numeric(20, 2), nullable=True),
        sa.Column("return_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("strategy", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("tags", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "ai_weights",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=True, index=True),
        sa.Column("weights_json", sa.Text, nullable=False),
        sa.Column("r2_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("n_samples", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "system_state",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in [
        "system_state", "ai_weights", "trade_journal", "daily_risk_metrics",
        "equity_snapshots", "orders", "positions", "valuation_cache",
        "render_log", "trading_suspensions", "pattern_analysis",
        "external_events", "policy_events", "broker_flow", "news",
    ]:
        op.drop_table(table)

    with op.batch_alter_table("stock_personality") as batch:
        for col in [
            "profile_date", "avg_downtrend_streak", "avg_uptrend_streak",
            "overall_pattern_winrate", "total_patterns_success",
            "total_patterns_detected", "worst_pattern_winrate", "worst_pattern",
            "best_pattern_winrate", "best_pattern", "net_distribution_score",
            "correlation_ihsg", "trend_strength", "volume_consistency",
            "avg_daily_volatility", "avg_volume",
        ]:
            batch.drop_column(col)

    with op.batch_alter_table("fundamental_data") as batch:
        for col in ["quarter", "fiscal_year", "cash_flow", "total_liabilities", "book_value_per_share"]:
            batch.drop_column(col)

    with op.batch_alter_table("corporate_actions") as batch:
        batch.drop_column("unit")

    with op.batch_alter_table("instrument_master") as batch:
        batch.drop_column("market_cap")
        batch.drop_column("free_float")
        batch.drop_column("board")
