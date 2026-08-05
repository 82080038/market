"""Initial schema: all Fase 1 tables.

Revision ID: 0001
Revises:
Create Date: 2026-08-05
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # market_registry
    op.create_table(
        "market_registry",
        sa.Column("mic_code", sa.String(10), primary_key=True),
        sa.Column("country_code", sa.String(3), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False),
        sa.Column("trading_hours", sa.Text, nullable=False),
        sa.Column("supports_dst", sa.Boolean, server_default=sa.text("0")),
        sa.Column("settlement_cycle", sa.Integer, server_default="2"),
        sa.Column("tick_size_rule", sa.Text),
        sa.Column("lot_size", sa.Integer),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("data_suffix", sa.String(10)),
        sa.Column("trading_status", sa.String(20), server_default="active"),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )

    # instrument_master
    op.create_table(
        "instrument_master",
        sa.Column("ticker", sa.String(30), primary_key=True),
        sa.Column(
            "market_mic",
            sa.String(10),
            sa.ForeignKey("market_registry.mic_code"),
            nullable=False,
        ),
        sa.Column("asset_class", sa.String(30), nullable=False, server_default="equity"),
        sa.Column("name", sa.String(200)),
        sa.Column("base_currency", sa.String(3), nullable=False, server_default="IDR"),
        sa.Column("reporting_currency", sa.String(3), nullable=False, server_default="IDR"),
        sa.Column("lot_size", sa.Integer),
        sa.Column("tick_size", sa.Numeric(10, 4)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("1")),
        sa.Column("sector", sa.String(100)),
        sa.Column("subsector", sa.String(100)),
        sa.Column("underlying_ticker", sa.String(30)),
        sa.Column("listing_date", sa.Date),
        sa.Column("delisting_date", sa.Date),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )

    # ohlcv
    op.create_table(
        "ohlcv",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("timestamp", sa.DateTime, nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False, server_default="1d"),
        sa.Column("open", sa.Numeric(20, 4), nullable=False),
        sa.Column("high", sa.Numeric(20, 4), nullable=False),
        sa.Column("low", sa.Numeric(20, 4), nullable=False),
        sa.Column("close", sa.Numeric(20, 4), nullable=False),
        sa.Column("volume", sa.Integer, nullable=False, server_default="0"),
        sa.Column("adjusted_close", sa.Numeric(20, 4)),
        sa.Column("data_quality_score", sa.Numeric(5, 2)),
        sa.Column("source", sa.String(50), server_default="yahoo_finance"),
        sa.Column("created_at", sa.DateTime),
        sa.UniqueConstraint("ticker", "timestamp", "timeframe", name="uq_ohlcv_pk"),
    )
    op.create_index("ix_ohlcv_ticker_ts", "ohlcv", ["ticker", "timestamp"])
    op.create_index("ix_ohlcv_ticker", "ohlcv", ["ticker"])
    op.create_index("ix_ohlcv_timestamp", "ohlcv", ["timestamp"])

    # corporate_actions
    op.create_table(
        "corporate_actions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("announce_date", sa.Date),
        sa.Column("ex_date", sa.Date),
        sa.Column("record_date", sa.Date),
        sa.Column("payment_date", sa.Date),
        sa.Column("value", sa.Numeric(20, 6)),
        sa.Column("currency", sa.String(3), server_default="IDR"),
        sa.Column("description", sa.Text),
        sa.Column("source", sa.String(50), server_default="yahoo_finance"),
        sa.Column("created_at", sa.DateTime),
        sa.UniqueConstraint("ticker", "action_type", "ex_date", name="uq_ca_pk"),
    )
    op.create_index("ix_ca_ticker", "corporate_actions", ["ticker"])

    # dividends
    op.create_table(
        "dividends",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("ex_date", sa.Date, nullable=False),
        sa.Column("record_date", sa.Date),
        sa.Column("payment_date", sa.Date),
        sa.Column("amount", sa.Numeric(20, 6), nullable=False),
        sa.Column("currency", sa.String(3), server_default="IDR"),
        sa.Column("frequency", sa.String(20)),
        sa.Column("source", sa.String(50), server_default="yahoo_finance"),
        sa.Column("created_at", sa.DateTime),
        sa.UniqueConstraint("ticker", "ex_date", "source", name="uq_div_pk"),
    )
    op.create_index("ix_div_ticker", "dividends", ["ticker"])

    # market_calendar
    op.create_table(
        "market_calendar",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("exchange", sa.String(10), nullable=False, server_default="XIDX"),
        sa.Column("is_trading_day", sa.Boolean, server_default=sa.text("1")),
        sa.Column("holiday_name", sa.String(200)),
        sa.Column("half_day", sa.Boolean, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime),
        sa.UniqueConstraint("date", "exchange", name="uq_cal_pk"),
    )
    op.create_index("ix_cal_date", "market_calendar", ["date"])

    # fx_rates
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("base_currency", sa.String(3), nullable=False),
        sa.Column("quote_currency", sa.String(3), nullable=False, server_default="IDR"),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("rate", sa.Numeric(20, 8), nullable=False),
        sa.Column("source", sa.String(50), server_default="yahoo_finance"),
        sa.Column("created_at", sa.DateTime),
        sa.UniqueConstraint("base_currency", "quote_currency", "date", name="uq_fx_pk"),
    )
    op.create_index("ix_fx_base", "fx_rates", ["base_currency"])
    op.create_index("ix_fx_date", "fx_rates", ["date"])

    # scores
    op.create_table(
        "scores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("engine", sa.String(50), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("breakdown", sa.Text),
        sa.Column("as_of", sa.DateTime),
        sa.Column("created_at", sa.DateTime),
        sa.UniqueConstraint("ticker", "engine", "as_of", name="uq_score_pk"),
    )
    op.create_index("ix_score_ticker", "scores", ["ticker"])

    # relationship_matrix
    op.create_table(
        "relationship_matrix",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("asset_a", sa.String(30), nullable=False),
        sa.Column("asset_b", sa.String(30), nullable=False),
        sa.Column("window", sa.Integer, nullable=False),
        sa.Column("correlation", sa.Numeric(10, 6)),
        sa.Column("lag", sa.Integer),
        sa.Column("as_of", sa.DateTime),
        sa.UniqueConstraint("asset_a", "asset_b", "window", name="uq_rel_pk"),
    )
    op.create_index("ix_rel_a", "relationship_matrix", ["asset_a"])
    op.create_index("ix_rel_b", "relationship_matrix", ["asset_b"])

    # source_health
    op.create_table(
        "source_health",
        sa.Column("source", sa.String(50), primary_key=True),
        sa.Column("last_success", sa.DateTime),
        sa.Column("last_error", sa.DateTime),
        sa.Column("last_error_msg", sa.Text),
        sa.Column("status", sa.String(20), server_default="ok"),
        sa.Column("total_fetches", sa.Integer, server_default="0"),
        sa.Column("total_failures", sa.Integer, server_default="0"),
        sa.Column("updated_at", sa.DateTime),
    )

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_payload", sa.Text),
        sa.Column("actor", sa.String(50), server_default="system"),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_audit_type", "audit_log", ["event_type"])
    op.create_index("ix_audit_created", "audit_log", ["created_at"])

    # data_watermark
    op.create_table(
        "data_watermark",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("table_name", sa.String(50), nullable=False),
        sa.Column("last_updated", sa.DateTime),
        sa.Column("row_count", sa.Integer),
        sa.Column("source", sa.String(50), server_default="yahoo_finance"),
        sa.UniqueConstraint("ticker", "table_name", name="uq_wm_pk"),
    )
    op.create_index("ix_wm_ticker", "data_watermark", ["ticker"])

    # fundamental_data
    op.create_table(
        "fundamental_data",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("pe", sa.Numeric(20, 4)),
        sa.Column("pb", sa.Numeric(20, 4)),
        sa.Column("roe", sa.Numeric(10, 4)),
        sa.Column("der", sa.Numeric(20, 4)),
        sa.Column("dividend_yield", sa.Numeric(10, 6)),
        sa.Column("eps", sa.Numeric(20, 4)),
        sa.Column("revenue", sa.Numeric(20, 2)),
        sa.Column("net_income", sa.Numeric(20, 2)),
        sa.Column("total_assets", sa.Numeric(20, 2)),
        sa.Column("market_cap", sa.Numeric(20, 2)),
        sa.Column("source", sa.String(50), server_default="yahoo_finance"),
        sa.Column("created_at", sa.DateTime),
        sa.UniqueConstraint("ticker", "date", "source", name="uq_fund_pk"),
    )
    op.create_index("ix_fund_ticker", "fundamental_data", ["ticker"])
    op.create_index("ix_fund_date", "fundamental_data", ["date"])

    # macro_data
    op.create_table(
        "macro_data",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("series_name", sa.String(50), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("value", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit", sa.String(20)),
        sa.Column("source", sa.String(50), server_default="yahoo_finance"),
        sa.Column("frequency", sa.String(20)),
        sa.Column("created_at", sa.DateTime),
        sa.UniqueConstraint("series_name", "date", "source", name="uq_macro_pk"),
    )
    op.create_index("ix_macro_name", "macro_data", ["series_name"])
    op.create_index("ix_macro_date", "macro_data", ["date"])

    # foreign_flow
    op.create_table(
        "foreign_flow",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("foreign_buy", sa.Numeric(20, 2)),
        sa.Column("foreign_sell", sa.Numeric(20, 2)),
        sa.Column("foreign_net", sa.Numeric(20, 2)),
        sa.Column("domestic_buy", sa.Numeric(20, 2)),
        sa.Column("domestic_sell", sa.Numeric(20, 2)),
        sa.Column("domestic_net", sa.Numeric(20, 2)),
        sa.Column("source", sa.String(50), server_default="idx_scraper"),
        sa.Column("created_at", sa.DateTime),
        sa.UniqueConstraint("ticker", "date", "source", name="uq_ff_pk"),
    )
    op.create_index("ix_ff_ticker", "foreign_flow", ["ticker"])
    op.create_index("ix_ff_date", "foreign_flow", ["date"])

    # technical_indicators
    op.create_table(
        "technical_indicators",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("indicator", sa.String(50), nullable=False),
        sa.Column("value", sa.Numeric(20, 6), nullable=False),
        sa.Column("timeframe", sa.String(10), server_default="1d"),
        sa.Column("source", sa.String(50), server_default="computed"),
        sa.Column("created_at", sa.DateTime),
        sa.UniqueConstraint(
            "ticker", "date", "indicator", "timeframe", "source",
            name="uq_ti_pk",
        ),
    )
    op.create_index("ix_ti_ticker", "technical_indicators", ["ticker"])
    op.create_index("ix_ti_date", "technical_indicators", ["date"])

    # stock_personality
    op.create_table(
        "stock_personality",
        sa.Column("ticker", sa.String(30), primary_key=True),
        sa.Column("volatility_regime", sa.String(30)),
        sa.Column("trend_bias", sa.String(30)),
        sa.Column("beta_vs_ihsg", sa.Numeric(10, 4)),
        sa.Column("liquidity_score", sa.Numeric(5, 2)),
        sa.Column("personality_label", sa.String(50)),
        sa.Column("updated_at", sa.DateTime),
    )

    # sector_master
    op.create_table(
        "sector_master",
        sa.Column("kode", sa.String(10), primary_key=True),
        sa.Column("nama", sa.String(100), nullable=False),
        sa.Column("deskripsi", sa.Text),
    )

    # fear_greed
    op.create_table(
        "fear_greed",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tanggal", sa.Date, nullable=False),
        sa.Column("nilai", sa.Numeric(5, 2), nullable=False),
        sa.Column("label", sa.String(30)),
    )
    op.create_index("ix_fg_date", "fear_greed", ["tanggal"])

    # watchlist
    op.create_table(
        "watchlist",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("is_favorite", sa.Boolean, server_default=sa.text("0")),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_wl_ticker", "watchlist", ["ticker"])


def downgrade() -> None:
    op.drop_table("watchlist")
    op.drop_table("fear_greed")
    op.drop_table("sector_master")
    op.drop_table("stock_personality")
    op.drop_table("technical_indicators")
    op.drop_table("foreign_flow")
    op.drop_table("macro_data")
    op.drop_table("fundamental_data")
    op.drop_table("data_watermark")
    op.drop_table("audit_log")
    op.drop_table("source_health")
    op.drop_table("relationship_matrix")
    op.drop_table("scores")
    op.drop_table("fx_rates")
    op.drop_table("market_calendar")
    op.drop_table("dividends")
    op.drop_table("corporate_actions")
    op.drop_table("ohlcv")
    op.drop_table("instrument_master")
    op.drop_table("market_registry")
