"""SQLAlchemy ORM models for the Market application.

Models are organized following pustaka/18 §13 (Database Schema) and
pustaka/92 §3 (Market & Asset Class Registry).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Registry tables ──────────────────────────────────────────────────────


class MarketRegistry(Base):
    """ISO 10383 market registry (pustaka/92 §3.1)."""

    __tablename__ = "market_registry"

    mic_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    trading_hours: Mapped[str] = mapped_column(Text, nullable=False)
    supports_dst: Mapped[bool] = mapped_column(Boolean, default=False)
    settlement_cycle: Mapped[int] = mapped_column(Integer, default=2)
    tick_size_rule: Mapped[str] = mapped_column(Text, nullable=True)
    lot_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    data_suffix: Mapped[str | None] = mapped_column(String(10), nullable=True)
    trading_status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class InstrumentMaster(Base):
    """Extended instrument master (pustaka/92 §3.3, pustaka/18 §13 D17)."""

    __tablename__ = "instrument_master"

    ticker: Mapped[str] = mapped_column(String(30), primary_key=True)
    market_mic: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("market_registry.mic_code"),
        nullable=False,
    )
    asset_class: Mapped[str] = mapped_column(String(30), nullable=False, default="equity")
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="IDR")
    reporting_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="IDR")
    lot_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tick_size: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subsector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    underlying_ticker: Mapped[str | None] = mapped_column(String(30), nullable=True)
    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    suspension_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delisting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    board: Mapped[str | None] = mapped_column(String(20), nullable=True)
    free_float: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    listed_shares: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    tradeable_shares: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    delisting_risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True, default=0)
    delisting_risk_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    former_ticker: Mapped[str | None] = mapped_column(String(30), nullable=True)
    former_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    index_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    region: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    market: Mapped[MarketRegistry] = relationship(foreign_keys=[market_mic])


# ── Market data tables ───────────────────────────────────────────────────


class OHLCV(Base):
    """OHLCV price data (pustaka/18 §13 #1)."""

    __tablename__ = "ohlcv"
    __table_args__ = (
        UniqueConstraint("ticker", "timestamp", "timeframe", name="uq_ohlcv_pk"),
        Index("ix_ohlcv_ticker_ts", "ticker", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False, default="1d")
    open: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    data_quality_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="yahoo_finance")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class CorporateAction(Base):
    """Corporate actions (pustaka/18 §13 #6)."""

    __tablename__ = "corporate_actions"
    __table_args__ = (
        UniqueConstraint("ticker", "action_type", "ex_date", name="uq_ca_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    announce_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ex_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    record_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="IDR")
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="yahoo_finance")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Dividend(Base):
    """Dividend history (pustaka/18 §13 D23)."""

    __tablename__ = "dividends"
    __table_args__ = (
        UniqueConstraint("ticker", "ex_date", "source", name="uq_div_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    ex_date: Mapped[date] = mapped_column(Date, nullable=False)
    record_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="IDR")
    frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="yahoo_finance")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── Calendar & FX ────────────────────────────────────────────────────────


class MarketCalendar(Base):
    """Market calendar (pustaka/18 §13 D25)."""

    __tablename__ = "market_calendar"
    __table_args__ = (
        UniqueConstraint("date", "exchange", name="uq_cal_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False, default="XIDX")
    is_trading_day: Mapped[bool] = mapped_column(Boolean, default=True)
    holiday_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    half_day: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class FXRate(Base):
    """FX rates for multi-currency reporting (pustaka/92 §4.3)."""

    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint("base_currency", "quote_currency", "date", name="uq_fx_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="IDR")
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="yahoo_finance")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── Analysis & scores ────────────────────────────────────────────────────


class Score(Base):
    """Engine scores (pustaka/18 §13 #4)."""

    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("ticker", "engine", "as_of", name="uq_score_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    engine: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RelationshipMatrix(Base):
    """Relationship matrix (pustaka/18 §13 #5)."""

    __tablename__ = "relationship_matrix"
    __table_args__ = (
        UniqueConstraint("asset_a", "asset_b", "window", name="uq_rel_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_a: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    asset_b: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    window: Mapped[int] = mapped_column(Integer, nullable=False)
    correlation: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    lag: Mapped[int | None] = mapped_column(Integer, nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── Infrastructure tables ────────────────────────────────────────────────


class SourceHealth(Base):
    """Data source health tracking (pustaka/18 §13 #2)."""

    __tablename__ = "source_health"

    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_success: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    total_fetches: Mapped[int] = mapped_column(Integer, default=0)
    total_failures: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class AuditLog(Base):
    """Append-only audit log (pustaka/18 §13 #3)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(50), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class DataWatermark(Base):
    """Data watermark for staleness tracking (pustaka/18 §13 #16)."""

    __tablename__ = "data_watermark"
    __table_args__ = (
        UniqueConstraint("ticker", "table_name", name="uq_wm_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="yahoo_finance")


# ── Extended data tables ─────────────────────────────────────────────────


class FundamentalData(Base):
    """Fundamental data (pustaka/18 §13 D18)."""

    __tablename__ = "fundamental_data"
    __table_args__ = (
        UniqueConstraint("ticker", "date", "source", name="uq_fund_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    pe: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    pb: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    roe: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    der: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    eps: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    book_value_per_share: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    revenue: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    net_income: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    total_assets: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    total_liabilities: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    cash_flow: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quarter: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="yahoo_finance")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class MacroData(Base):
    """Macro economic data (pustaka/18 §13 D19)."""

    __tablename__ = "macro_data"
    __table_args__ = (
        UniqueConstraint("series_name", "date", "source", name="uq_macro_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    value: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="yahoo_finance")
    frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ForeignFlow(Base):
    """Foreign flow data (pustaka/18 §13 D20)."""

    __tablename__ = "foreign_flow"
    __table_args__ = (
        UniqueConstraint("ticker", "date", "source", name="uq_ff_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    foreign_buy: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    foreign_sell: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    foreign_net: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    domestic_buy: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    domestic_sell: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    domestic_net: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="idx_scraper")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class DailyTradingStats(Base):
    """Daily trading statistics from IDX (pustaka/18 §13 D36).

    Stores per-ticker per-day data from GitHub Dataset-Saham-IDX:
    value, frequency, offer/bid, listed/tradeable shares, non-regular market,
    index individual, weight for index.
    """

    __tablename__ = "daily_trading_stats"
    __table_args__ = (
        UniqueConstraint("ticker", "date", "source", name="uq_dts_pk"),
        Index("ix_dts_ticker_date", "ticker", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    previous_close: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    first_trade: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    change: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    index_individual: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    offer: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    offer_volume: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    bid: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    bid_volume: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    listed_shares: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    tradeable_shares: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    weight_for_index: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    non_regular_volume: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    non_regular_value: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    non_regular_frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="github_dataset")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class TechnicalIndicator(Base):
    """Technical indicators cache (pustaka/18 §13 D34)."""

    __tablename__ = "technical_indicators"
    __table_args__ = (
        UniqueConstraint(
            "ticker", "date", "indicator", "timeframe", "source",
            name="uq_ti_pk",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    indicator: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), default="1d")
    source: Mapped[str] = mapped_column(String(50), default="computed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class StockPersonality(Base):
    """Stock personality classification (pustaka/18 §13 D30)."""

    __tablename__ = "stock_personality"

    ticker: Mapped[str] = mapped_column(String(30), primary_key=True)
    volatility_regime: Mapped[str | None] = mapped_column(String(30), nullable=True)
    trend_bias: Mapped[str | None] = mapped_column(String(30), nullable=True)
    beta_vs_ihsg: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    liquidity_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    personality_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avg_volume: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    avg_daily_volatility: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    volume_consistency: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    trend_strength: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    correlation_ihsg: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    net_distribution_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    best_pattern: Mapped[str | None] = mapped_column(String(50), nullable=True)
    best_pattern_winrate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    worst_pattern: Mapped[str | None] = mapped_column(String(50), nullable=True)
    worst_pattern_winrate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    total_patterns_detected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_patterns_success: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_pattern_winrate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    avg_uptrend_streak: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    avg_downtrend_streak: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    profile_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class TechnicalIndicatorWide(Base):
    """Wide-format technical indicators (pivot of TechnicalIndicator EAV).

    One row per ticker+date with all indicators as columns.
    Reduces 30M EAV rows to ~2.9M wide rows (10x storage savings).
    """

    __tablename__ = "technical_indicators_wide"
    __table_args__ = (
        UniqueConstraint("ticker", "date", "timeframe", name="uq_tiw_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), default="1d")
    ma20: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    ma50: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    rsi: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    macd: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    macd_signal: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    adx: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    atr14: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    bb_upper: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    bb_lower: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    volume_sma20: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    ema50: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    ema_env_upper: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    ema_env_lower: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    donchian_upper: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    donchian_lower: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    donchian_mid: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class StockPrediction(Base):
    """Daily prediction snapshot, split from stock_personality.

    Updated daily by batch_compute_predictions.py and daily_signal_cron.py.
    Separated from stock_personality (weekly profile) to reduce write amplification.
    """

    __tablename__ = "stock_prediction"

    ticker: Mapped[str] = mapped_column(String(30), primary_key=True)
    predicted_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    predicted_price: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    predicted_return_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    prediction_confidence: Mapped[float | None] = mapped_column(Numeric(5, 3), nullable=True)
    ml_signal: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    multifactor_signal: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    composite_signal: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    factors_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    prediction_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SectorMaster(Base):
    """Sector master (pustaka/18 §13 D24)."""

    __tablename__ = "sector_master"

    kode: Mapped[str] = mapped_column(String(10), primary_key=True)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    deskripsi: Mapped[str | None] = mapped_column(Text, nullable=True)


class FearGreed(Base):
    """Fear & Greed index (pustaka/18 §13 D26)."""

    __tablename__ = "fear_greed"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tanggal: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    nilai: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    label: Mapped[str | None] = mapped_column(String(30), nullable=True)


class ESGScore(Base):
    """ESG scores (pustaka/18 §13 D28, pustaka/90 §2)."""

    __tablename__ = "esg_scores"
    __table_args__ = (
        UniqueConstraint("ticker", "year", "rating_agency", name="uq_esg_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    rating_agency: Mapped[str] = mapped_column(String(50), nullable=False)
    rating: Mapped[str | None] = mapped_column(String(30), nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class CorporateGovernance(Base):
    """Corporate governance scores (pustaka/18 §13 D29, pustaka/90 §2)."""

    __tablename__ = "corporate_governance"
    __table_args__ = (
        UniqueConstraint("ticker", "year", name="uq_cg_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    board_commissioners: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    independent_commissioners: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    board_directors: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    audit_committee_meetings: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    gcg_score: Mapped[str | None] = mapped_column(String(50), nullable=True)
    acgs_score: Mapped[str | None] = mapped_column(String(50), nullable=True)
    has_whistleblowing: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_risk_committee: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Watchlist(Base):
    """User watchlist (pustaka/18 §13 #12)."""

    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── Market intelligence tables (pustaka/18 §13 #7, D22, D27, D32, D35) ───


class News(Base):
    """News articles with sentiment (pustaka/18 §13 #7)."""

    __tablename__ = "news"
    __table_args__ = (
        UniqueConstraint("news_id", name="uq_news_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_id: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    entities: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sentiment: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    impact: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class BrokerFlow(Base):
    """Broker flow data (pustaka/18 §13 D21)."""

    __tablename__ = "broker_flow"
    __table_args__ = (
        UniqueConstraint("ticker", "date", "broker", "source", name="uq_bf_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    broker: Mapped[str] = mapped_column(String(20), nullable=False)
    buy_volume: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    buy_value: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    sell_volume: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    sell_value: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    net_volume: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    net_value: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="idx_scraper")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class PolicyEvent(Base):
    """Policy/regulatory events (pustaka/18 §13 D22)."""

    __tablename__ = "policy_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tanggal: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kategori: Mapped[str | None] = mapped_column(String(50), nullable=True)
    judul: Mapped[str | None] = mapped_column(String(500), nullable=True)
    instansi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dampak: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sektor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    deskripsi: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ExternalEvent(Base):
    """External/geopolitical events (pustaka/18 §13 D27)."""

    __tablename__ = "external_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tanggal: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kategori: Mapped[str | None] = mapped_column(String(50), nullable=True)
    judul: Mapped[str | None] = mapped_column(String(500), nullable=True)
    lokasi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dampak_market: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sektor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    deskripsi: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class PatternAnalysis(Base):
    """Chart pattern analysis results (pustaka/18 §13 D32)."""

    __tablename__ = "pattern_analysis"
    __table_args__ = (
        UniqueConstraint("ticker", "date", "pattern_type", name="uq_pa_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    pattern_type: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="technical_compute")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class TradingSuspension(Base):
    """Trading suspensions/delisting (pustaka/18 §13 D35)."""

    __tablename__ = "trading_suspensions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    suspend_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    resume_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suspension_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RenderLog(Base):
    """Render log for cache tracking (pustaka/18 §13 #15)."""

    __tablename__ = "render_log"
    __table_args__ = (
        UniqueConstraint("ticker", "table_name", name="uq_rl_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_rendered: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    rows_rendered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ValuationCache(Base):
    """Valuation cache for DCF/relative (pustaka/18 §13 D33)."""

    __tablename__ = "valuation_cache"
    __table_args__ = (
        UniqueConstraint("ticker", "date", "method", "source", name="uq_vc_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    intrinsic_value: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    market_price: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    upside_pct: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    assumptions: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="computed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── Trading & execution tables (pustaka/18 §13 #8, #9, #11, #13, #14, D31) ─


class Position(Base):
    """Trading positions (pustaka/18 §13 #8)."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    avg_entry_price: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    current_price: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    stop_loss: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    trailing_stop_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    highest_price_since_entry: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    unrealized_pnl: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    return_pct: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Order(Base):
    """Order history (pustaka/18 §13 #9)."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    order_type: Mapped[str] = mapped_column(String(10), nullable=False)
    order_style: Mapped[str] = mapped_column(String(20), default="MARKET")
    quantity: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    total_value: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    fee: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    slippage: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    trigger: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class EquitySnapshot(Base):
    """Equity snapshots for performance tracking (pustaka/18 §13 #11)."""

    __tablename__ = "equity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    equity: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    cash: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    positions_value: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    unrealized_pnl: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    total_return_pct: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class DailyRiskMetric(Base):
    """Daily risk metrics (pustaka/18 §13 #14)."""

    __tablename__ = "daily_risk_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    var_95: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    var_99: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    cvar_95: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    cvar_99: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    annualized_volatility: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    portfolio_value: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class TradeJournal(Base):
    """Trade journal (pustaka/18 §13 D31)."""

    __tablename__ = "trade_journal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    side: Mapped[str | None] = mapped_column(String(10), nullable=True)
    pnl: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    return_pct: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AIWeight(Base):
    """AI weight optimization results (pustaka/18 §13 #13)."""

    __tablename__ = "ai_weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    weights_json: Mapped[str] = mapped_column(Text, nullable=False)
    r2_score: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    n_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class MLLabel(Base):
    """Triple-barrier labels for ML training (pustaka/23 §4, pustaka/84 Stage 6).

    Implements López de Prado's triple-barrier method:
    - Take-profit barrier: +vol_multiple * ATR
    - Stop-loss barrier: -vol_multiple * ATR
    - Time barrier: horizon trading days

    Label is 'up' if TP hit first, 'down' if SL hit first, 'static' if time expired.
    """

    __tablename__ = "ml_labels"
    __table_args__ = (
        UniqueConstraint("ticker", "date", "horizon", name="uq_mllabel_pk"),
        Index("ix_mllabel_ticker_date", "ticker", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    barrier_hit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    return_pct: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    vol_adjusted_return: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class MarketRegime(Base):
    """Market regime labels for regime-aware ML (pustaka/23 §5, pustaka/35 §2).

    Daily regime classification based on HMM states or heuristic rules:
    'bull', 'bear', 'sideways', 'crisis'.
    """

    __tablename__ = "market_regimes"
    __table_args__ = (
        UniqueConstraint("date", name="uq_regime_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    regime: Mapped[str | None] = mapped_column(String(30), nullable=True)
    vix_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fear_greed_label: Mapped[str | None] = mapped_column(String(30), nullable=True)
    foreign_flow_trend: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="computed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class SystemState(Base):
    """System state key-value store (pustaka/18 §13 #10)."""

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class SchedulerState(Base):
    """Persistent scheduler state for catch-up of missed tasks.

    Stores last_run timestamp and last_status per task so the scheduler
    can resume after application restart and catch up on missed executions.
    """

    __tablename__ = "scheduler_state"

    task_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_run: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(20), default="pending")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class RecomputeWatermark(Base):
    """Watermark for incremental recompute — tracks last-processed date per ticker per table.

    When incremental recompute runs, it checks this table to determine
    the cutoff date for each ticker. Only OHLCV data after (last_processed_date - lookback)
    is loaded, and only labels/indicators for dates > last_processed_date are computed.
    """

    __tablename__ = "recompute_watermark"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    table_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_processed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_ohlcv_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rows_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class ParquetSyncState(Base):
    """Incremental sync state for DB → Parquet archive (pustaka/94).

    Tracks the last-synced date per table so that sync_to_parquet.py can
    resume incrementally instead of doing a full export every run.

    - partitioned tables: last_synced_date is the max date_col value synced;
      the next run only rewrites partitions within a safety window after
      last_synced_date.
    - full_rewrite tables: last_synced_date is NULL; the whole file is
      rewritten each run (tables are small / mutable).
    """

    __tablename__ = "parquet_sync_state"

    table_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    sync_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    partition_col: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_synced_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_partitions_written: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


# ── Relational hierarchy tables (migration 0013) ─────────────────────────
# Negara → Regulator → Bursa → Sektor → Emiten → Instrumen
# + Indeks Pasar, Broker, Broker-Bursa, Transaksi Investor, App Notifications


class Regulator(Base):
    """Regulator — top of hierarchy (e.g. OJK/Indonesia, SEC/USA)."""

    __tablename__ = "regulator"

    id_regulator: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nama_regulator: Mapped[str] = mapped_column(String(100), nullable=False)
    negara: Mapped[str] = mapped_column(String(50), nullable=False)


class BursaEfek(Base):
    """Bursa Efak — exchange regulated by a regulator (e.g. BEI/IDX under OJK)."""

    __tablename__ = "bursa_efek"

    id_bursa: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nama_bursa: Mapped[str] = mapped_column(String(100), nullable=False)
    mic_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    id_regulator: Mapped[int] = mapped_column(
        Integer, ForeignKey("regulator.id_regulator", ondelete="RESTRICT"), nullable=False
    )


class Sektor(Base):
    """Sektor — independent sector lookup (e.g. Energy, Financials)."""

    __tablename__ = "sektor"

    id_sektor: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nama_sektor: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)


class Emiten(Base):
    """Emiten — company listed on a bursa, belonging to a sector."""

    __tablename__ = "emiten"

    id_emiten: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kode_ticker: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    nama_perusahaan: Mapped[str | None] = mapped_column(String(200), nullable=True)
    id_bursa: Mapped[int] = mapped_column(
        Integer, ForeignKey("bursa_efek.id_bursa", ondelete="RESTRICT"), nullable=False
    )
    id_sektor: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sektor.id_sektor", ondelete="SET NULL"), nullable=True
    )
    subsektor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Instrumen(Base):
    """Instrumen — financial instrument issued by an emiten."""

    __tablename__ = "instrumen"

    id_instrumen: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_emiten: Mapped[int] = mapped_column(
        Integer, ForeignKey("emiten.id_emiten", ondelete="CASCADE"), nullable=False
    )
    jenis_instrumen: Mapped[str] = mapped_column(String(30), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(30), nullable=False, default="EQUITY_INDIVIDUAL")
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="IDR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class IndeksPasar(Base):
    """Indeks Pasar — market index belonging to a bursa."""

    __tablename__ = "indeks_pasar"

    id_indeks: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kode_indeks: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    nama_indeks: Mapped[str | None] = mapped_column(String(200), nullable=True)
    id_bursa: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bursa_efek.id_bursa", ondelete="SET NULL"), nullable=True
    )
    jenis_indeks: Mapped[str | None] = mapped_column(String(30), nullable=True)
    asset_class: Mapped[str] = mapped_column(String(30), nullable=False, default="INDEX_COMPOSITE")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Broker(Base):
    """Broker — securities broker."""

    __tablename__ = "broker"

    id_broker: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nama_broker: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class BrokerBursa(Base):
    """Broker-Bursa — many-to-many junction (broker ↔ bursa membership)."""

    __tablename__ = "broker_bursa"

    id_broker: Mapped[int] = mapped_column(
        Integer, ForeignKey("broker.id_broker", ondelete="CASCADE"), primary_key=True
    )
    id_bursa: Mapped[int] = mapped_column(
        Integer, ForeignKey("bursa_efek.id_bursa", ondelete="CASCADE"), primary_key=True
    )


class TransaksiInvestor(Base):
    """Transaksi Investor — investor transaction records."""

    __tablename__ = "transaksi_investor"

    id_transaksi: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tanggal_transaksi: Mapped[date] = mapped_column(Date, nullable=False)
    id_instrumen: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrumen.id_instrumen", ondelete="RESTRICT"), nullable=False
    )
    id_broker: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("broker.id_broker", ondelete="SET NULL"), nullable=True
    )
    tipe_transaksi: Mapped[str] = mapped_column(String(20), nullable=False)
    jumlah_lot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    harga_per_saham: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    biaya_broker: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True, default=0)
    pajak_pph_final: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True, default=0)
    status_eksekusi: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AppNotification(Base):
    """App Notifications — internal notification for the application backend."""

    __tablename__ = "app_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNREAD")
