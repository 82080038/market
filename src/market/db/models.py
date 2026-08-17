"""SQLAlchemy ORM models for the Market application.

Models are organized following pustaka/18 §13 (Database Schema) and
pustaka/92 §3 (Market & Asset Class Registry).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Registry tables ──────────────────────────────────────────────────────


# NOTE: MarketRegistry and InstrumentMaster tables were merged into exchanges/instruments
# in migration 0022. Compatibility views remain in PG for backward compatibility.
# Use Exchange and Instrument models below for new code.


class InstrumentMaster(Base):
    """Compatibility view — delegates to instruments table (migration 0022).

    The original instrument_master table was merged into instruments.
    A view with the old column names is maintained for backward compatibility.
    New code should use the Instrument model instead.
    """

    __tablename__ = "instrument_master"

    ticker: Mapped[str] = mapped_column(String(30), primary_key=True)
    market_mic: Mapped[str | None] = mapped_column(String(10), nullable=True)
    asset_class: Mapped[str | None] = mapped_column(String(30), nullable=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    base_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    reporting_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    lot_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tick_size: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[str | None] = mapped_column(Text, nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subsector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    underlying_ticker: Mapped[str | None] = mapped_column(String(30), nullable=True)
    listing_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    delisting_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    board: Mapped[str | None] = mapped_column(String(20), nullable=True)
    free_float: Mapped[str | None] = mapped_column(Text, nullable=True)
    market_cap: Mapped[str | None] = mapped_column(Text, nullable=True)
    listed_shares: Mapped[str | None] = mapped_column(Text, nullable=True)
    tradeable_shares: Mapped[str | None] = mapped_column(Text, nullable=True)
    delisting_risk_score: Mapped[str | None] = mapped_column(Text, nullable=True)
    delisting_risk_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    former_ticker: Mapped[str | None] = mapped_column(String(30), nullable=True)
    former_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    index_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    region: Mapped[str | None] = mapped_column(String(10), nullable=True)
    suspension_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    trading_status: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── Market data tables ───────────────────────────────────────────────────


class OHLCV(Base):
    """OHLCV price data — compatibility view over stock_prices (PG schema).

    In PostgreSQL, `ohlcv` is a view: SELECT ticker, exchange_mic, timestamp,
    timeframe, open, high, low, close, volume, vwap, adjusted_close, source,
    created_at FROM stock_prices. It does NOT have `id` or `data_quality_score`.
    The composite PK (ticker, timestamp, timeframe) matches the unique constraint
    on the underlying stock_prices table.
    """

    __tablename__ = "ohlcv"
    __table_args__ = (
        # Composite PK matches uq_stock_prices_ticker_ts_tf on stock_prices
        PrimaryKeyConstraint("ticker", "timestamp", "timeframe", name="uq_ohlcv_pk"),
        Index("ix_ohlcv_ticker_ts", "ticker", "timestamp"),
    )

    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    exchange_mic: Mapped[str | None] = mapped_column(String(10), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False, default="1d")
    open: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vwap: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="yahoo_finance")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CorporateAction(Base):
    """Corporate actions (pustaka/18 §13 #6)."""

    __tablename__ = "corporate_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    ex_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    record_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    announced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_direction: Mapped[str] = mapped_column(String(20), default="NEUTRAL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Calendar & FX ────────────────────────────────────────────────────────


class MarketCalendar(Base):
    """Compatibility view — delegates to exchange_holidays (migration 0023).

    The original market_calendar table was merged into exchange_holidays.
    A view remains for backward compatibility. Only holiday rows are visible
    (is_trading_day=false). New code should query exchange_holidays directly.
    """

    __tablename__ = "market_calendar"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)
    is_trading_day: Mapped[bool] = mapped_column(Boolean, default=False)
    holiday_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    half_day: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SignalWeight(Base):
    """Dynamic signal weights for MarketContext and DecisionEngine.

    Scope: 'market_context' or 'decision_engine'.
    Sector: sector-specific override or 'DEFAULT'.
    Allows runtime weight updates without code changes.
    """

    __tablename__ = "signal_weights"
    __table_args__ = (
        UniqueConstraint("scope", "sector", "signal_name", name="uq_signal_weights_scope_sector_signal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sector: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    signal_name: Mapped[str] = mapped_column(String(50), nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    optimized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    optimization_score: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    optimization_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RecomputeDependency(Base):
    """Maps recompute functions to their input data sources.

    When a data source is updated, only functions that depend on it
    are triggered for recompute — avoiding unnecessary full recompute.

    Also tracks per-function runtime statistics for duration/row estimation.
    """

    __tablename__ = "recompute_dependencies"
    __table_args__ = (
        UniqueConstraint("function_name", "data_source", name="uq_recompute_dep_fn_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    function_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    data_source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="table")
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Runtime statistics
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    last_rows_affected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    avg_rows_affected: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_data_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RecomputeRunStats(Base):
    """Per-run statistics for each recompute function execution.

    Tracks duration, rows, tickers processed/skipped, and data freshness
    for historical analysis and future estimation.
    """

    __tablename__ = "recompute_run_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    function_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    trigger_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    rows_affected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tickers_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tickers_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    incremental: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_freshness_seconds: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RecomputePrediction(Base):
    """Pre-computed duration/row predictions for recompute functions.

    Generated by RecomputeAnalyzer from historical run stats.
    Read by RecomputeEstimator to provide estimates before running.
    Includes a feedback loop: actual vs predicted is tracked.
    """

    __tablename__ = "recompute_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    function_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    predicted_duration_s: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    predicted_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_tickers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0.0)
    # Factors
    ticker_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_volume_mb: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    incremental: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    time_of_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Accuracy tracking
    actual_duration_s: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    actual_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_error_pct: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    rows_error_pct: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    was_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Metadata
    analysis_method: Mapped[str] = mapped_column(String(50), nullable=False, default="rolling_avg")
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RecomputeTrigger(Base):
    """Logs data update events and which recomputes were triggered.

    Tracks selective recompute execution for audit and debugging.
    """

    __tablename__ = "recompute_triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False)
    data_source_updated: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    functions_triggered: Mapped[str] = mapped_column(Text, nullable=False, comment="JSON list")
    functions_skipped: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON list")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    rows_affected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Infrastructure tables ────────────────────────────────────────────────


class SourceHealth(Base):
    """Data source health tracking (pustaka/18 §13 #2)."""

    __tablename__ = "source_health"

    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    total_fetches: Mapped[int] = mapped_column(Integer, default=0)
    total_failures: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class AuditLog(Base):
    """Append-only audit log (pustaka/18 §13 #3)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(50), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class DataWatermark(Base):
    """Data watermark for staleness tracking (pustaka/18 §13 #16)."""

    __tablename__ = "data_watermark"
    __table_args__ = (
        UniqueConstraint("ticker", "table_name", name="uq_wm_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
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
    roe: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    der: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    eps: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    revenue: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    net_income: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    total_assets: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    total_debt: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    shares_outstanding: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    free_float: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    beta: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    profit_margin: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    operating_margin: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    current_ratio: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    quick_ratio: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    book_value_per_share: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    cash_per_share: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    debt_to_equity: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    return_on_assets: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    return_on_equity: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    revenue_growth: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    earnings_growth: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    npl_ratio: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    car: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    loan_to_deposit: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    nim: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_liabilities: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    cash_flow: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="yfinance")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ModelPerformanceHistory(Base):
    """Persisted model performance records per ticker per evaluation."""

    __tablename__ = "model_performance_history"
    __table_args__ = (
        UniqueConstraint("ticker", "model_id", "evaluated_at",
                         name="uq_model_perf_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    sharpe_ratio: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    mae: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    directional_accuracy: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    is_degraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    degradation_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_adjustment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class StrategyAssignment(Base):
    """Best strategy assignment per ticker — richer than stock_personality.best_pattern."""

    __tablename__ = "strategy_assignment"

    ticker: Mapped[str] = mapped_column(String(30), primary_key=True)
    best_strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    strategy_class: Mapped[str] = mapped_column(String(50), nullable=False)
    strategy_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    in_sample_sharpe: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    in_sample_max_dd: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    in_sample_winrate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    oos_sharpe: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    oos_max_dd: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    oos_winrate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MacroeconomicIndicator(Base):
    """Macroeconomic indicators — global & domestic causal drivers (Dimensi 1 "WHY").

    Stores time-series readings of macro indicators (Fed Rate, BI Rate, USD/IDR,
    VIX, Brent, Gold, inflation) on a universal UTC timeline for correlation &
    causality analysis against stock price movements.

    Integrated into ``v_domino_timeline`` via UNION ALL (MACRO_INDICATOR branch).
    See ``scripts/macroeconomic_indicators_integration.sql`` and
    ``pustaka/99-indikator-makroekonomi-korelasi.md``.
    """

    __tablename__ = "macroeconomic_indicators"
    __table_args__ = (
        UniqueConstraint("indicator_code", "recorded_at",
                         name="uq_macro_indicator"),
        Index("idx_macro_indicator_code_time",
              "indicator_code",
              text("recorded_at DESC")),
        Index("idx_macro_recorded_at", "recorded_at"),
        Index("idx_macro_region", "region"),
        CheckConstraint(
            "region IN ('US','ID','GLOBAL','EU','ASIA','CN','JP','HK')",
            name="chk_macro_region"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    indicator_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow)


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
    foreign_volume_buy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    foreign_volume_sell: Mapped[int | None] = mapped_column(Integer, nullable=True)
    domestic_buy: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    domestic_sell: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    domestic_net: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    domestic_volume_buy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    domestic_volume_sell: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="idx_scraper")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class StockPersonality(Base):
    """Stock personality classification (pustaka/18 §13 D30).

    Prediction columns were moved to stock_prediction in migration 0022
    to reduce write amplification (personality = weekly profile,
    prediction = daily forecast).
    """

    __tablename__ = "stock_personality"

    ticker: Mapped[str] = mapped_column(String(30), primary_key=True)
    volatility_regime: Mapped[str | None] = mapped_column(String(30), nullable=True)
    trend_bias: Mapped[str | None] = mapped_column(String(30), nullable=True)
    beta_vs_ihsg: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    liquidity_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    personality_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    prediction_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    value: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    label: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), default="cnn")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Watchlist(Base):
    """User watchlist (pustaka/18 §13 #12)."""

    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class NewsSentiment(Base):
    """NLP-processed news sentiment (PostgreSQL news_sentiment table)."""

    __tablename__ = "news_sentiment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Instrument(Base):
    """Instrument master — merged with instrument_master in migration 0022."""

    __tablename__ = "instruments"

    ticker: Mapped[str] = mapped_column(String(30), primary_key=True)
    exchange_mic: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    asset_class: Mapped[str] = mapped_column(String(30), nullable=False, default="EQUITY")
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="IDR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Columns merged from instrument_master (migration 0022)
    reporting_currency: Mapped[str] = mapped_column(String(3), default="IDR")
    lot_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tick_size: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    subsector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    underlying_ticker: Mapped[str | None] = mapped_column(String(30), nullable=True)
    suspension_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delisting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    board: Mapped[str | None] = mapped_column(String(20), nullable=True)
    free_float: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    listed_shares: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    tradeable_shares: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    delisting_risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True, default=0)
    delisting_risk_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    former_ticker: Mapped[str | None] = mapped_column(String(30), nullable=True)
    former_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    index_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    region: Mapped[str | None] = mapped_column(String(10), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Fetch metadata (migration 0027) — DB as source of truth for fetch scheduling
    data_layer: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fetch_frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetch_status: Mapped[str | None] = mapped_column(String(20), nullable=True, default="NEVER_FETCHED")
    # Data source metadata (migration 0028-0029) — WHERE & HOW to fetch data
    data_source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    data_source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    data_source_fallback: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fetch_adapter: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data_source_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    delisting_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    merged_to_ticker: Mapped[str | None] = mapped_column(String(30), nullable=True)


class StockPrice(Base):
    """Stock price data matching PG stock_prices partitioned table."""

    __tablename__ = "stock_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    exchange_mic: Mapped[str] = mapped_column(String(10), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False, default="1d")
    open: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    high: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    low: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    close: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vwap: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    adjusted_close: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    bid: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    bid_volume: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    ask: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    ask_volume: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    trade_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="yahoo_finance")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Exchange(Base):
    """Exchange registry — merged with market_registry in migration 0022."""

    __tablename__ = "exchanges"

    mic_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    tick_size: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0.01)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Columns merged from market_registry (migration 0022)
    trading_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    supports_dst: Mapped[bool] = mapped_column(Boolean, default=False)
    settlement_cycle: Mapped[int] = mapped_column(Integer, default=2)
    tick_size_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_suffix: Mapped[str | None] = mapped_column(String(10), nullable=True)
    trading_status: Mapped[str] = mapped_column(String(20), default="active")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Data source metadata (migration 0029) — exchange-level fetch routing
    primary_data_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    data_source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    data_source_fallback: Mapped[str | None] = mapped_column(String(30), nullable=True)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RenderLog(Base):
    """Render log for cache tracking (pustaka/18 §13 #15)."""

    __tablename__ = "render_log"
    __table_args__ = (
        UniqueConstraint("ticker", "table_name", name="uq_rl_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_rendered: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    rows_rendered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AIWeight(Base):
    """AI weight optimization results (pustaka/18 §13 #13)."""

    __tablename__ = "ai_weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    weights_json: Mapped[str] = mapped_column(Text, nullable=False)
    r2_score: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    n_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    ihsg_trend: Mapped[str | None] = mapped_column(String(20), nullable=True)
    volatility_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    breadth_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SystemState(Base):
    """System state key-value store (pustaka/18 §13 #10)."""

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class SchedulerState(Base):
    """Persistent scheduler state for catch-up of missed tasks.

    Stores last_run timestamp and last_status per task so the scheduler
    can resume after application restart and catch up on missed executions.
    Also tracks next_run_at (pre-computed), is_stale (missed runs),
    data_dependencies (what DB data the task needs), and data_ready
    (whether pre-loaded data is available).
    """

    __tablename__ = "scheduler_state"

    task_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(20), default="pending")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    data_dependencies: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    data_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    last_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_catchup: Mapped[bool] = mapped_column(Boolean, default=False)
    last_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


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
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


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
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_partitions_written: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# NOTE: Broker and BrokerBursa tables were dropped in migration 0022.
# The `brokers` table (migration 0013) is the canonical broker registry.


class Broker(Base):
    """Securities broker — canonical broker registry (brokers table)."""

    __tablename__ = "brokers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    exchange_mic: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("exchanges.mic_code", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TransaksiInvestor(Base):
    """Transaksi Investor — investor transaction records."""

    __tablename__ = "transaksi_investor"

    id_transaksi: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tanggal_transaksi: Mapped[date] = mapped_column(Date, nullable=False)
    id_instrumen: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrumen.id_instrumen", ondelete="RESTRICT"), nullable=False
    )
    id_broker: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("brokers.id", ondelete="SET NULL"), nullable=True
    )
    tipe_transaksi: Mapped[str] = mapped_column(String(20), nullable=False)
    jumlah_lot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    harga_per_saham: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    biaya_broker: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True, default=0)
    pajak_pph_final: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True, default=0)
    status_eksekusi: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AppNotification(Base):
    """App Notifications — internal notification for the application backend."""

    __tablename__ = "app_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNREAD")


# ── Satellite data tables (pustaka/99-matriks-relevansi-satelit-pasar-modal.md) ──


class SatelliteObservation(Base):
    """Satellite observation data — NDVI from Sentinel-2, weather from NASA POWER.

    Stores raw daily/sparse satellite metrics keyed by geographic location
    and date. Only metrics proven significant in correlation analysis are
    stored: NDVI, T2M, PRECTOTCORR, RH2M, ALLSKY_SFC_SW_DWN.
    """

    __tablename__ = "satellite_observations"
    __table_args__ = (
        UniqueConstraint("location_name", "date", "metric", "source", name="uq_satobs_pk"),
        Index("ix_satobs_location_date", "location_name", "date"),
        Index("ix_satobs_metric", "metric"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    lon: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="nasa_power")
    cloud_cover_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    scene_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SatelliteCorrelationResult(Base):
    """Correlation analysis results between satellite metrics and stock returns.

    Persisted output of the satellite-to-stock correlation pipeline.
    Supports daily, weekly, and monthly frequencies with lag analysis.
    """

    __tablename__ = "satellite_correlation_results"
    __table_args__ = (
        UniqueConstraint(
            "location_name", "satellite_metric", "stock_ticker",
            "frequency", "rolling_window",
            name="uq_satcorr_pk",
        ),
        Index("ix_satcorr_ticker", "stock_ticker"),
        Index("ix_satcorr_metric", "satellite_metric"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    satellite_metric: Mapped[str] = mapped_column(String(30), nullable=False)
    stock_ticker: Mapped[str] = mapped_column(String(30), nullable=False)
    frequency: Mapped[str] = mapped_column(String(10), nullable=False)
    rolling_window: Mapped[int] = mapped_column(Integer, nullable=False)
    optimal_lag: Mapped[int] = mapped_column(Integer, nullable=False)
    optimal_corr: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    optimal_pvalue: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    granger_optimal_pvalue: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    is_significant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lag_unit: Mapped[str] = mapped_column(String(10), nullable=False, default="hari")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SatelliteTickerLocation(Base):
    """Mapping tickers to geographic locations for satellite data fetching.

    Each ticker can have multiple locations (e.g., AALI.JK has plantations
    in Kalimantan and Sumatera). If no explicit mapping exists, the fetcher
    falls back to sector-based defaults (SECTOR_FALLBACK_LOCATIONS).

    This makes satellite data truly global — any ticker from any market
    can be mapped to any location on Earth.
    """

    __tablename__ = "satellite_ticker_locations"
    __table_args__ = (
        UniqueConstraint("ticker", "location_name", name="uq_sattickerloc_pk"),
        Index("ix_sattickerloc_ticker", "ticker"),
        Index("ix_sattickerloc_sector", "sector"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    location_name: Mapped[str] = mapped_column(String(100), nullable=False)
    lat: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    lon: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metrics: Mapped[str] = mapped_column(
        Text, nullable=False,
        default="NDVI,T2M,PRECTOTCORR,RH2M,ALLSKY_SFC_SW_DWN",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class InstrumentBehaviorProfile(Base):
    """Per-instrument behavior profile (catatan.md TAHAP 2 — Prompt 2.1).

    Persisted by ``InstrumentBehaviorProfiler`` so signal generators and
    position sizers can query it without recomputing every run. Updated weekly.
    """

    __tablename__ = "instrument_behavior_profiles"
    __table_args__ = (
        Index("ix_ibp_asset_class", "asset_class"),
        Index("ix_ibp_volatility_regime", "volatility_regime"),
    )

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    asset_class: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Volatility Profile
    avg_daily_volatility: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    volatility_regime: Mapped[str | None] = mapped_column(String(20), nullable=True)
    volatility_clustering_coefficient: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    # Momentum & Mean Reversion
    momentum_strength: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    optimal_momentum_lookback: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mean_reversion_halflife: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    # Liquidity Profile
    avg_daily_volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    avg_spread_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    liquidity_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    optimal_position_size_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    # Correlation & Sensitivity
    beta_to_ihsg: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    correlation_to_sector: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    sensitivity_to_usd: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    sensitivity_to_rates: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    # Seasonality
    best_months: Mapped[list | None] = mapped_column(JSON, nullable=True)
    worst_months: Mapped[list | None] = mapped_column(JSON, nullable=True)
    day_of_week_effect: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Event Response
    earnings_drift_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    earnings_avg_move: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    dividend_ex_date_effect: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    # Trading Style Suitability (1-10)
    intraday_suitability: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    swing_suitability: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    investing_suitability: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    # Metadata
    profile_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_points_used: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CrossMarketCoefficient(Base):
    """Cross-market Granger coefficient (catatan.md TAHAP 3 — Prompt 3.1).

    Persisted by ``CrossMarketCoefficientEngine``. Updated weekly.
    """

    __tablename__ = "cross_market_coefficients"
    __table_args__ = (
        UniqueConstraint(
            "source_index", "target_ticker", "lag_days",
            name="uq_cmc_source_target_lag",
        ),
        Index("ix_cmc_source", "source_index"),
        Index("ix_cmc_target", "target_ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_index: Mapped[str] = mapped_column(String(20), nullable=False)
    target_ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    lag_days: Mapped[int] = mapped_column(Integer, nullable=False)
    coefficient: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    p_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    f_statistic: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    asymmetric_up: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    asymmetric_down: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    regime: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserTradingProfile(Base):
    """User trading profile (catatan.md TAHAP 4 — Prompt 4.1).

    Single-user app — user_id default 'default'.
    """

    __tablename__ = "user_trading_profiles"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    capital: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    risk_tolerance: Mapped[str] = mapped_column(String(20), nullable=False)
    time_availability: Mapped[str] = mapped_column(String(20), nullable=False)
    experience_level: Mapped[str] = mapped_column(String(20), nullable=False)
    max_loss_per_trade_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    max_portfolio_drawdown_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    preferred_styles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    preferred_sectors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TradingStyleRecommendation(Base):
    """Trading style recommendation for a user (catatan.md TAHAP 4)."""

    __tablename__ = "trading_style_recommendations"
    __table_args__ = (Index("ix_tsr_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("user_trading_profiles.user_id", ondelete="CASCADE"), nullable=False,
    )
    recommended_style: Mapped[str] = mapped_column(String(30), nullable=False)
    allocation_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    reasoning_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StyleRecommendationReason(Base):
    """Individual reason supporting a style recommendation (catatan.md TAHAP 4)."""

    __tablename__ = "style_recommendation_reasons"
    __table_args__ = (Index("ix_srr_rec", "recommendation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trading_style_recommendations.id", ondelete="CASCADE"), nullable=False,
    )
    reason_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MarketInfluenceKB(Base):
    """Market Influence Knowledge Base — central influence mapping.

    Consolidates sector-global links, commodity sensitivity, Granger causality,
    cross-market coefficients, and macro policy into one queryable table.
    Migration 0030.
    """

    __tablename__ = "market_influence_kb"
    __table_args__ = (
        UniqueConstraint(
            "target_ticker",
            "source_ticker",
            "lag_days",
            "influence_type",
            name="uq_mikb_target_source_lag_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    target_sector: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_layer: Mapped[str | None] = mapped_column(String(20), nullable=True)
    influence_type: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    lag_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strength: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    p_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 5), nullable=True)
    mechanism: Mapped[str | None] = mapped_column(Text, nullable=True)
    regime: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_table: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )
