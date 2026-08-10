"""Parquet migration script (pustaka/90 §5).

Migrates valuable parquet datasets from the global project archive
to the local SQLite database. Source path is read-only.

Usage:
    python -m market.data.migrate_parquet [--dry-run]
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from sqlalchemy import select

from market.config import settings
from market.db.models import (
    OHLCV,
    AuditLog,
    CorporateAction,
    DailyTradingStats,
    Dividend,
    FearGreed,
    ForeignFlow,
    FundamentalData,
    InstrumentMaster,
    MLLabel,
    MacroData,
    MarketCalendar,
    MarketRegime,
    RelationshipMatrix,
    Score,
    SectorMaster,
    SourceHealth,
    StockPersonality,
    TechnicalIndicator,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ARCHIVE_TABLES = Path(settings.parquet_archive_path) / "archive" / "tables"
SQLITE_BACKUP = Path(settings.parquet_archive_path) / "raw" / "sqlite_backup"


def _safe_read_parquet(path: Path) -> pd.DataFrame | None:
    """Read a parquet file safely, returning None on error."""
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        logger.error("Failed to read %s: %s", path, exc)
        return None


# Tables that sync_to_parquet.py writes as Hive-partitioned directories
# (year=YYYY/month=MM/data.parquet) instead of flat .parquet files.
_PARTITIONED_TABLES: frozenset[str] = frozenset({
    "ohlcv", "corporate_actions", "dividends", "market_calendar", "fx_rates",
    "fundamental_data", "macro_data", "foreign_flow", "daily_trading_stats",
    "technical_indicators", "broker_flow", "pattern_analysis", "valuation_cache",
    "ml_labels", "market_regimes", "policy_events", "external_events",
    "fear_greed", "audit_log",
})


def _read_table_parquet(table_name: str) -> pd.DataFrame | None:
    """Read a table's parquet data, auto-detecting Hive-partitioned vs flat.

    sync_to_parquet.py writes time-series tables as Hive-partitioned
    directories (``table/year=YYYY/month=MM/data.parquet``) and reference
    tables as flat files (``table.parquet``). This helper reads either
    format transparently, with fallback to flat file for backward
    compatibility with legacy export_to_parquet.py output.
    """
    # Try Hive-partitioned directory first (for tables in the partitioned set).
    if table_name in _PARTITIONED_TABLES:
        part_root = ARCHIVE_TABLES / table_name
        if part_root.is_dir():
            try:
                import pyarrow.dataset as ds
                dataset = ds.dataset(part_root, format="parquet",
                                     partitioning="hive")
                return dataset.to_table().to_pandas()
            except Exception as exc:
                logger.warning(
                    "Hive read failed for %s, falling back to flat: %s",
                    table_name, exc,
                )
    # Fallback: flat file (legacy export_to_parquet.py output).
    flat_path = ARCHIVE_TABLES / f"{table_name}.parquet"
    return _safe_read_parquet(flat_path)


def _f(row: pd.Series, key: str, default: float = 0.0) -> float | None:
    """Extract a float value from a pandas row, None if NaN."""
    v = row.get(key)
    return float(v) if pd.notna(v) else default


def _s(row: pd.Series, key: str, default: str = "") -> str | None:
    """Extract a string value from a pandas row, None if NaN."""
    v = row.get(key)
    return str(v) if pd.notna(v) else default


def _d(row: pd.Series, key: str) -> date | None:
    """Extract a date from a pandas row."""
    v = row.get(key)
    return pd.Timestamp(v).date() if pd.notna(v) else None


def migrate_ohlcv(session: Session, dry_run: bool = False) -> int:
    """Migrate ohlcv.parquet (2.9M rows) to OHLCV table."""
    path = ARCHIVE_TABLES / "ohlcv.parquet"
    if not path.exists() and not (ARCHIVE_TABLES / "ohlcv").is_dir():
        logger.warning("ohlcv.parquet not found at %s", path)
        return 0

    df = _read_table_parquet("ohlcv")
    if df is None or df.empty:
        return 0

    logger.info("OHLCV parquet: %d rows", len(df))

    if dry_run:
        return len(df)

    count = 0
    skip = 0
    for _, row in df.iterrows():
        ticker = str(row.get("ticker", ""))
        ts = pd.Timestamp(row.get("timestamp")).to_pydatetime()

        close_val = row.get("close")
        if pd.isna(close_val):
            skip += 1
            continue

        existing = session.execute(
            select(OHLCV).where(
                OHLCV.ticker == ticker,
                OHLCV.timestamp == ts,
                OHLCV.timeframe == "1d",
            )
        ).scalar_one_or_none()
        if existing:
            count += 1
            continue
        session.add(
            OHLCV(
                ticker=ticker,
                timestamp=ts,
                timeframe="1d",
                open=float(row.get("open", 0)) if pd.notna(row.get("open")) else 0,
                high=float(row.get("high", 0)) if pd.notna(row.get("high")) else 0,
                low=float(row.get("low", 0)) if pd.notna(row.get("low")) else 0,
                close=float(close_val),
                volume=int(row.get("volume", 0)) if pd.notna(row.get("volume")) else 0,
                adjusted_close=_f(row, "adjusted_close"),
                data_quality_score=_f(row, "data_quality_score"),
                source="parquet_archive",
            )
        )
        count += 1
        if count % 10000 == 0:
            session.commit()
            logger.info("OHLCV migrated: %d/%d (skipped %d)", count, len(df), skip)

    session.commit()
    if skip:
        logger.info("OHLCV skipped %d rows with NaN close", skip)
    return count


def migrate_corporate_actions(session: Session, dry_run: bool = False) -> int:
    """Migrate corporate_actions.parquet."""
    path = ARCHIVE_TABLES / "corporate_actions.parquet"
    if not path.exists() and not (ARCHIVE_TABLES / "corporate_actions").is_dir():
        return 0

    df = _read_table_parquet("corporate_actions")
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        session.add(
            CorporateAction(
                ticker=str(row.get("ticker", "")),
                action_type=str(row.get("action_type", "")),
                ex_date=_d(row, "ex_date"),
                announce_date=_d(row, "announce_date"),
                record_date=_d(row, "record_date"),
                payment_date=_d(row, "payment_date"),
                value=_f(row, "value"),
                source="parquet_archive",
            )
        )
        count += 1

    session.commit()
    return count


def migrate_dividends(session: Session, dry_run: bool = False) -> int:
    """Migrate dividends.parquet."""
    path = ARCHIVE_TABLES / "dividends.parquet"
    if not path.exists() and not (ARCHIVE_TABLES / "dividends").is_dir():
        return 0

    df = _read_table_parquet("dividends")
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        session.add(
            Dividend(
                ticker=str(row.get("ticker", "")),
                ex_date=_d(row, "ex_date") or date.min,
                amount=float(row.get("amount", 0)),
                currency=str(row.get("currency", "IDR")),
                frequency=_s(row, "frequency"),
                source="parquet_archive",
            )
        )
        count += 1

    session.commit()
    return count


def migrate_macro_data(session: Session, dry_run: bool = False) -> int:
    """Migrate macro_data.parquet."""
    path = ARCHIVE_TABLES / "macro_data.parquet"
    if not path.exists() and not (ARCHIVE_TABLES / "macro_data").is_dir():
        return 0

    df = _read_table_parquet("macro_data")
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        session.add(
            MacroData(
                series_name=str(row.get("series_name", "")),
                date=_d(row, "date") or date.min,
                value=float(row.get("value", 0)),
                unit=_s(row, "unit"),
                source=str(row.get("source", "parquet_archive")),
                frequency=_s(row, "frequency"),
            )
        )
        count += 1

    session.commit()
    return count


def migrate_foreign_flow(session: Session, dry_run: bool = False) -> int:
    """Migrate foreign_flow.parquet."""
    path = ARCHIVE_TABLES / "foreign_flow.parquet"
    if not path.exists() and not (ARCHIVE_TABLES / "foreign_flow").is_dir():
        return 0

    df = _read_table_parquet("foreign_flow")
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        session.add(
            ForeignFlow(
                ticker=str(row.get("ticker", "")),
                date=_d(row, "date") or date.min,
                foreign_buy=_f(row, "foreign_buy"),
                foreign_sell=_f(row, "foreign_sell"),
                foreign_net=_f(row, "foreign_net"),
                domestic_buy=_f(row, "domestic_buy"),
                domestic_sell=_f(row, "domestic_sell"),
                domestic_net=_f(row, "domestic_net"),
                source="parquet_archive",
            )
        )
        count += 1
        if count % 5000 == 0:
            session.commit()

    session.commit()
    return count


def migrate_market_calendar(session: Session, dry_run: bool = False) -> int:
    """Migrate market_calendar.parquet."""
    path = ARCHIVE_TABLES / "market_calendar.parquet"
    if not path.exists() and not (ARCHIVE_TABLES / "market_calendar").is_dir():
        return 0

    df = _read_table_parquet("market_calendar")
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        session.add(
            MarketCalendar(
                date=_d(row, "date") or date.min,
                exchange=str(row.get("exchange", "XIDX")),
                is_trading_day=bool(row.get("is_trading_day", True)),
                holiday_name=_s(row, "holiday_name"),
                half_day=bool(row.get("half_day", False)),
            )
        )
        count += 1

    session.commit()
    return count


def migrate_fundamental_data(session: Session, dry_run: bool = False) -> int:
    """Migrate fundamental_data.parquet."""
    path = ARCHIVE_TABLES / "fundamental_data.parquet"
    if not path.exists() and not (ARCHIVE_TABLES / "fundamental_data").is_dir():
        return 0

    df = _read_table_parquet("fundamental_data")
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        session.add(
            FundamentalData(
                ticker=str(row.get("ticker", "")),
                date=_d(row, "date") or date.min,
                pe=_f(row, "PE"),
                pb=_f(row, "PB"),
                roe=_f(row, "ROE"),
                der=_f(row, "DER"),
                dividend_yield=_f(row, "dividend_yield"),
                eps=_f(row, "EPS"),
                revenue=_f(row, "revenue"),
                total_assets=_f(row, "total_assets"),
                market_cap=_f(row, "market_cap"),
                source="parquet_archive",
            )
        )
        count += 1

    session.commit()
    return count


def migrate_stock_personality(session: Session, dry_run: bool = False) -> int:
    """Migrate stock_personality.parquet."""
    path = ARCHIVE_TABLES / "stock_personality.parquet"
    if not path.exists():
        return 0

    df = _safe_read_parquet(path)
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        ticker = str(row.get("kode", row.get("ticker", "")))
        existing = session.get(StockPersonality, ticker)
        if existing is not None:
            existing.volatility_regime = _s(row, "volatility_regime") or existing.volatility_regime
            existing.trend_bias = _s(row, "trend_bias") or existing.trend_bias
            existing.beta_vs_ihsg = _f(row, "beta_vs_ihsg")
            existing.liquidity_score = _f(row, "liquidity_score")
            existing.personality_label = _s(row, "personality_label") or existing.personality_label
        else:
            session.add(
                StockPersonality(
                    ticker=ticker,
                    volatility_regime=_s(row, "volatility_regime"),
                    trend_bias=_s(row, "trend_bias"),
                    beta_vs_ihsg=_f(row, "beta_vs_ihsg"),
                    liquidity_score=_f(row, "liquidity_score"),
                    personality_label=_s(row, "personality_label"),
                )
            )
        count += 1

    session.commit()
    return count


# Exchange code mapping: parquet exchange → MIC code
_EXCHANGE_TO_MIC: dict[str, str] = {
    "IDX": "XIDX",
    "JKT": "XIDX",
    "YHD": "XNYS",
    "SNP": "XNYS",
    "NYB": "XNYS",
    "PCX": "XNAS",
    "SHH": "XIDX",  # SSE — fallback to XIDX for .JK suffix
    "HKG": "XHKG",
    "OSA": "XTSE",
    "MYS": "XSGX",
    "LON": "XLON",
    "GER": "XFRA",
    "CCY": "XIDX",  # Forex — no dedicated market
    "CMX": "XIDX",  # Commodities — no dedicated market
    "NYM": "XNYS",  # NYMEX — fallback
    "DJI": "XNYS",
    "FGI": "XNYS",  # Fear/Greed index
    "NIM": "XNYS",
    "CGI": "XNYS",
    "CXI": "XNYS",
}


def migrate_instrument_master(session: Session, dry_run: bool = False) -> int:
    """Migrate instrument_master.parquet (992 tickers)."""
    path = ARCHIVE_TABLES / "instrument_master.parquet"
    if not path.exists():
        logger.warning("instrument_master.parquet not found")
        return 0

    df = _safe_read_parquet(path)
    if df is None or df.empty:
        return 0

    logger.info("instrument_master parquet: %d rows", len(df))

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        ticker = str(row.get("ticker", ""))
        if not ticker:
            continue

        existing = session.get(InstrumentMaster, ticker)
        exchange = str(row.get("exchange", "IDX"))
        mic = _EXCHANGE_TO_MIC.get(exchange, "XIDX")

        if existing is not None:
            existing.name = _s(row, "name") or existing.name
            existing.sector = _s(row, "sector") or existing.sector
            existing.subsector = _s(row, "subsector") or existing.subsector
            existing.is_active = bool(row.get("is_active", 1))
            existing.listing_date = _d(row, "listing_date")
            existing.delisting_date = _d(row, "delisting_date")
            existing.asset_class = _s(row, "asset_class") or "equity"
            existing.market_mic = mic
        else:
            session.add(
                InstrumentMaster(
                    ticker=ticker,
                    market_mic=mic,
                    asset_class=_s(row, "asset_class") or "equity",
                    name=_s(row, "name"),
                    base_currency="IDR" if mic == "XIDX" else "USD",
                    reporting_currency="IDR",
                    lot_size=100 if mic == "XIDX" else 1,
                    is_active=bool(row.get("is_active", 1)),
                    sector=_s(row, "sector"),
                    subsector=_s(row, "subsector"),
                    listing_date=_d(row, "listing_date"),
                    delisting_date=_d(row, "delisting_date"),
                )
            )
        count += 1

    session.commit()
    return count


def migrate_sector_master(session: Session, dry_run: bool = False) -> int:
    """Migrate sector_master.parquet."""
    path = ARCHIVE_TABLES / "sector_master.parquet"
    if not path.exists():
        logger.warning("sector_master.parquet not found")
        return 0

    df = _safe_read_parquet(path)
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        kode = str(row.get("kode", ""))
        if not kode:
            continue

        existing = session.get(SectorMaster, kode)
        if existing is not None:
            existing.nama = _s(row, "nama") or existing.nama
            existing.deskripsi = _s(row, "deskripsi") or existing.deskripsi
        else:
            session.add(
                SectorMaster(
                    kode=kode,
                    nama=_s(row, "nama") or "",
                    deskripsi=_s(row, "deskripsi"),
                )
            )
        count += 1

    session.commit()
    return count


def migrate_scores(session: Session, dry_run: bool = False) -> int:
    """Migrate scores.parquet (engine scores)."""
    path = ARCHIVE_TABLES / "scores.parquet"
    if not path.exists():
        logger.warning("scores.parquet not found")
        return 0

    df = _safe_read_parquet(path)
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        ticker = str(row.get("ticker", ""))
        engine = str(row.get("engine", ""))
        if not ticker or not engine:
            continue

        as_of_val = row.get("as_of")
        as_of_dt = pd.Timestamp(as_of_val).to_pydatetime() if pd.notna(as_of_val) else None

        existing = session.execute(
            select(Score).where(
                Score.ticker == ticker,
                Score.engine == engine,
                Score.as_of == as_of_dt,
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.score = float(row.get("score", 0))
            existing.breakdown = _s(row, "breakdown")
        else:
            session.add(
                Score(
                    ticker=ticker,
                    engine=engine,
                    score=float(row.get("score", 0)),
                    breakdown=_s(row, "breakdown"),
                    as_of=as_of_dt,
                )
            )
        count += 1

    session.commit()
    return count


def migrate_technical_indicators(session: Session, dry_run: bool = False) -> int:
    """Migrate technical_indicators.parquet."""
    path = ARCHIVE_TABLES / "technical_indicators.parquet"
    if not path.exists() and not (ARCHIVE_TABLES / "technical_indicators").is_dir():
        logger.warning("technical_indicators.parquet not found")
        return 0

    df = _read_table_parquet("technical_indicators")
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        ticker = str(row.get("ticker", ""))
        indicator = str(row.get("indicator", ""))
        if not ticker or not indicator:
            continue

        date_val = _d(row, "date")
        if date_val is None:
            continue

        timeframe = str(row.get("timeframe", "1d"))
        source = str(row.get("source", "computed"))

        existing = session.execute(
            select(TechnicalIndicator).where(
                TechnicalIndicator.ticker == ticker,
                TechnicalIndicator.date == date_val,
                TechnicalIndicator.indicator == indicator,
                TechnicalIndicator.timeframe == timeframe,
                TechnicalIndicator.source == source,
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.value = float(row.get("value", 0))
        else:
            session.add(
                TechnicalIndicator(
                    ticker=ticker,
                    date=date_val,
                    indicator=indicator,
                    value=float(row.get("value", 0)),
                    timeframe=timeframe,
                    source=source,
                )
            )
        count += 1

    session.commit()
    return count


def migrate_relationship_matrix(session: Session, dry_run: bool = False) -> int:
    """Migrate relationship_matrix.parquet."""
    path = ARCHIVE_TABLES / "relationship_matrix.parquet"
    if not path.exists():
        logger.warning("relationship_matrix.parquet not found")
        return 0

    df = _safe_read_parquet(path)
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        asset_a = str(row.get("asset_a", ""))
        asset_b = str(row.get("asset_b", ""))
        window = int(row.get("window", 0))
        if not asset_a or not asset_b or window <= 0:
            continue

        existing = session.execute(
            select(RelationshipMatrix).where(
                RelationshipMatrix.asset_a == asset_a,
                RelationshipMatrix.asset_b == asset_b,
                RelationshipMatrix.window == window,
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.correlation = _f(row, "correlation")
            existing.lag = int(row.get("lag", 0)) if pd.notna(row.get("lag")) else None
        else:
            session.add(
                RelationshipMatrix(
                    asset_a=asset_a,
                    asset_b=asset_b,
                    window=window,
                    correlation=_f(row, "correlation"),
                    lag=int(row.get("lag", 0)) if pd.notna(row.get("lag")) else None,
                )
            )
        count += 1

    session.commit()
    return count


def migrate_fear_greed(session: Session, dry_run: bool = False) -> int:
    """Migrate fear_greed.parquet."""
    path = ARCHIVE_TABLES / "fear_greed.parquet"
    if not path.exists() and not (ARCHIVE_TABLES / "fear_greed").is_dir():
        logger.warning("fear_greed.parquet not found")
        return 0

    df = _read_table_parquet("fear_greed")
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        fg_date = _d(row, "tanggal") or _d(row, "date")
        if fg_date is None:
            continue

        fg_value = float(row.get("nilai", 0) or row.get("value", 0))
        label = _s(row, "label")

        existing = session.execute(
            select(FearGreed).where(FearGreed.date == fg_date)
        ).scalar_one_or_none()

        if existing is not None:
            existing.value = fg_value
            existing.label = label
        else:
            session.add(
                FearGreed(
                    date=fg_date,
                    value=fg_value,
                    label=label,
                )
            )
        count += 1

    session.commit()
    return count


def migrate_source_health(session: Session, dry_run: bool = False) -> int:
    """Migrate source_health.parquet."""
    path = ARCHIVE_TABLES / "source_health.parquet"
    if not path.exists():
        logger.warning("source_health.parquet not found")
        return 0

    df = _safe_read_parquet(path)
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        source = str(row.get("source", ""))
        if not source:
            continue

        existing = session.get(SourceHealth, source)
        last_success = row.get("last_success")
        last_error = row.get("last_error")

        if existing is not None:
            if pd.notna(last_success):
                existing.last_success = pd.Timestamp(last_success).to_pydatetime()
            if pd.notna(last_error):
                existing.last_error = pd.Timestamp(last_error).to_pydatetime()
            existing.status = str(row.get("status", "ok"))
        else:
            ls = (
                pd.Timestamp(last_success).to_pydatetime()
                if pd.notna(last_success)
                else None
            )
            le = (
                pd.Timestamp(last_error).to_pydatetime()
                if pd.notna(last_error)
                else None
            )
            session.add(
                SourceHealth(
                    source=source,
                    last_success=ls,
                    last_error=le,
                    status=str(row.get("status", "ok")),
                )
            )
        count += 1

    session.commit()
    return count


def migrate_daily_trading_stats(session: Session, dry_run: bool = False) -> int:
    """Migrate daily_trading_stats.parquet (Hive-partitioned by year/month).

    Restores IDX daily trading statistics: previous_close, value, frequency,
    offer/bid, listed/tradeable shares, non-regular market, index individual,
    weight for index. Without this table, daily trading context is lost on
    cross-machine restore (pustaka/95 §2.1).
    """
    part_root = ARCHIVE_TABLES / "daily_trading_stats"
    flat_path = ARCHIVE_TABLES / "daily_trading_stats.parquet"
    if not flat_path.exists() and not part_root.is_dir():
        logger.warning("daily_trading_stats not found at %s", ARCHIVE_TABLES)
        return 0

    df = _read_table_parquet("daily_trading_stats")
    if df is None or df.empty:
        return 0

    logger.info("daily_trading_stats parquet: %d rows", len(df))

    if dry_run:
        return len(df)

    count = 0
    skip = 0
    for _, row in df.iterrows():
        ticker = str(row.get("ticker", ""))
        d = _d(row, "date")
        if not ticker or d is None:
            skip += 1
            continue

        # Upsert by (ticker, date, source) — matches uq_dts_pk.
        src = _s(row, "source") or "github_dataset"
        existing = session.execute(
            select(DailyTradingStats).where(
                DailyTradingStats.ticker == ticker,
                DailyTradingStats.date == d,
                DailyTradingStats.source == src,
            )
        ).scalar_one_or_none()

        if existing is not None:
            count += 1
            continue

        session.add(
            DailyTradingStats(
                ticker=ticker,
                date=d,
                previous_close=_f(row, "previous_close"),
                first_trade=_f(row, "first_trade"),
                change=_f(row, "change"),
                value=_f(row, "value"),
                frequency=int(row["frequency"]) if pd.notna(row.get("frequency")) else None,
                index_individual=_f(row, "index_individual"),
                offer=_f(row, "offer"),
                offer_volume=_f(row, "offer_volume"),
                bid=_f(row, "bid"),
                bid_volume=_f(row, "bid_volume"),
                listed_shares=_f(row, "listed_shares"),
                tradeable_shares=_f(row, "tradeable_shares"),
                weight_for_index=_f(row, "weight_for_index"),
                non_regular_volume=_f(row, "non_regular_volume"),
                non_regular_value=_f(row, "non_regular_value"),
                non_regular_frequency=(
                    int(row["non_regular_frequency"])
                    if pd.notna(row.get("non_regular_frequency"))
                    else None
                ),
                source=src,
            )
        )
        count += 1
        if count % 10000 == 0:
            session.commit()
            logger.info("daily_trading_stats migrated: %d/%d (skipped %d)",
                        count, len(df), skip)

    session.commit()
    if skip:
        logger.info("daily_trading_stats skipped %d rows (missing ticker/date)", skip)
    return count


def migrate_ml_labels(session: Session, dry_run: bool = False) -> int:
    """Migrate ml_labels.parquet (Hive-partitioned by year/month).

    Restores triple-barrier labels (ticker, date, horizon, direction,
    barrier_hit, return_pct, vol_adjusted_return). Critical for ML
    training pipeline — without this table, supervised models cannot
    be trained on restored data (pustaka/23 §4, pustaka/95 §2.1).
    """
    part_root = ARCHIVE_TABLES / "ml_labels"
    flat_path = ARCHIVE_TABLES / "ml_labels.parquet"
    if not flat_path.exists() and not part_root.is_dir():
        logger.warning("ml_labels not found at %s", ARCHIVE_TABLES)
        return 0

    df = _read_table_parquet("ml_labels")
    if df is None or df.empty:
        return 0

    logger.info("ml_labels parquet: %d rows", len(df))

    if dry_run:
        return len(df)

    count = 0
    skip = 0
    for _, row in df.iterrows():
        ticker = str(row.get("ticker", ""))
        d = _d(row, "date")
        horizon = row.get("horizon")
        if not ticker or d is None or pd.isna(horizon):
            skip += 1
            continue

        horizon = int(horizon)
        direction = str(row.get("direction", ""))
        if not direction:
            skip += 1
            continue

        # Upsert by (ticker, date, horizon) — matches uq_mllabel_pk.
        existing = session.execute(
            select(MLLabel).where(
                MLLabel.ticker == ticker,
                MLLabel.date == d,
                MLLabel.horizon == horizon,
            )
        ).scalar_one_or_none()

        if existing is not None:
            count += 1
            continue

        session.add(
            MLLabel(
                ticker=ticker,
                date=d,
                horizon=horizon,
                direction=direction,
                barrier_hit=_s(row, "barrier_hit"),
                return_pct=_f(row, "return_pct"),
                vol_adjusted_return=_f(row, "vol_adjusted_return"),
            )
        )
        count += 1
        if count % 10000 == 0:
            session.commit()
            logger.info("ml_labels migrated: %d/%d (skipped %d)",
                        count, len(df), skip)

    session.commit()
    if skip:
        logger.info("ml_labels skipped %d rows (missing ticker/date/horizon/direction)",
                    skip)
    return count


def migrate_market_regimes(session: Session, dry_run: bool = False) -> int:
    """Migrate market_regimes.parquet (Hive-partitioned by year/month).

    Restores daily market regime classification (bull/bear/sideways/crisis),
    vix_level, fear_greed_label, foreign_flow_trend. Required for
    regime-aware ML and market context analysis (pustaka/23 §5,
    pustaka/95 §2.1).
    """
    part_root = ARCHIVE_TABLES / "market_regimes"
    flat_path = ARCHIVE_TABLES / "market_regimes.parquet"
    if not flat_path.exists() and not part_root.is_dir():
        logger.warning("market_regimes not found at %s", ARCHIVE_TABLES)
        return 0

    df = _read_table_parquet("market_regimes")
    if df is None or df.empty:
        return 0

    logger.info("market_regimes parquet: %d rows", len(df))

    if dry_run:
        return len(df)

    count = 0
    skip = 0
    for _, row in df.iterrows():
        d = _d(row, "date")
        if d is None:
            skip += 1
            continue

        # Upsert by date — matches uq_regime_pk.
        existing = session.execute(
            select(MarketRegime).where(MarketRegime.date == d)
        ).scalar_one_or_none()

        if existing is not None:
            count += 1
            continue

        session.add(
            MarketRegime(
                date=d,
                regime=_s(row, "regime"),
                vix_level=_s(row, "vix_level"),
                fear_greed_label=_s(row, "fear_greed_label"),
                foreign_flow_trend=_s(row, "foreign_flow_trend"),
                source=_s(row, "source") or "computed",
            )
        )
        count += 1

    session.commit()
    if skip:
        logger.info("market_regimes skipped %d rows (missing date)", skip)
    return count


def migrate_audit_log(session: Session, dry_run: bool = False) -> int:
    """Migrate audit_log.parquet."""
    path = ARCHIVE_TABLES / "audit_log.parquet"
    if not path.exists() and not (ARCHIVE_TABLES / "audit_log").is_dir():
        logger.warning("audit_log.parquet not found")
        return 0

    df = _read_table_parquet("audit_log")
    if df is None or df.empty:
        return 0

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        event_type = str(row.get("event_type", ""))
        if not event_type:
            continue

        timestamp = row.get("timestamp")
        created_at = pd.Timestamp(timestamp).to_pydatetime() if pd.notna(timestamp) else None

        session.add(
            AuditLog(
                event_type=event_type,
                event_payload=_s(row, "payload"),
                actor=str(row.get("actor", "system")),
                created_at=created_at,
            )
        )
        count += 1

    session.commit()
    return count


def run_all_migrations(session: Session, dry_run: bool = False) -> dict[str, int]:
    """Run all parquet migrations. Returns a summary dict."""
    results: dict[str, int] = {}
    migrations = [
        ("ohlcv", migrate_ohlcv),
        ("corporate_actions", migrate_corporate_actions),
        ("dividends", migrate_dividends),
        ("macro_data", migrate_macro_data),
        ("foreign_flow", migrate_foreign_flow),
        ("market_calendar", migrate_market_calendar),
        ("fundamental_data", migrate_fundamental_data),
        ("stock_personality", migrate_stock_personality),
        ("instrument_master", migrate_instrument_master),
        ("sector_master", migrate_sector_master),
        ("scores", migrate_scores),
        ("technical_indicators", migrate_technical_indicators),
        ("relationship_matrix", migrate_relationship_matrix),
        ("fear_greed", migrate_fear_greed),
        ("source_health", migrate_source_health),
        ("daily_trading_stats", migrate_daily_trading_stats),
        ("ml_labels", migrate_ml_labels),
        ("market_regimes", migrate_market_regimes),
        ("audit_log", migrate_audit_log),
    ]

    for name, func in migrations:
        logger.info("Migrating %s...", name)
        try:
            count = func(session, dry_run=dry_run)
            results[name] = count
            logger.info("  %s: %d rows", name, count)
        except Exception as exc:
            logger.error("  %s FAILED: %s", name, exc)
            results[name] = -1
            session.rollback()

    return results


if __name__ == "__main__":
    import sys

    from market.db.engine import get_sessionmaker

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    dry = "--dry-run" in sys.argv
    session = get_sessionmaker()()
    try:
        summary = run_all_migrations(session, dry_run=dry)
        print("\nMigration summary:")
        for name, count in summary.items():
            status = f"{count} rows" if count >= 0 else "FAILED"
            print(f"  {name}: {status}")
    finally:
        session.close()
