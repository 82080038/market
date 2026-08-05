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
    delisting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
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
    revenue: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    net_income: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    total_assets: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
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
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


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
        UniqueConstraint("kode", "year", "rating_agency", name="uq_esg_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kode: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    rating_agency: Mapped[str] = mapped_column(String(50), nullable=False)
    rating: Mapped[str | None] = mapped_column(String(30), nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class CorporateGovernance(Base):
    """Corporate governance scores (pustaka/18 §13 D29, pustaka/90 §2)."""

    __tablename__ = "corporate_governance"
    __table_args__ = (
        UniqueConstraint("kode", "year", name="uq_cg_pk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kode: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
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
