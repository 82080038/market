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

from market.config import settings
from market.db.models import (
    OHLCV,
    CorporateAction,
    Dividend,
    ForeignFlow,
    FundamentalData,
    MacroData,
    MarketCalendar,
    StockPersonality,
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


def _f(row: pd.Series, key: str, default: float = 0.0) -> float | None:
    """Extract a float value from a pandas row, None if NaN."""
    v = row.get(key)
    return float(v) if pd.notna(v) else default if default else None


def _s(row: pd.Series, key: str, default: str = "") -> str | None:
    """Extract a string value from a pandas row, None if NaN."""
    v = row.get(key)
    return str(v) if pd.notna(v) else default if default else None


def _d(row: pd.Series, key: str) -> date | None:
    """Extract a date from a pandas row."""
    v = row.get(key)
    return pd.Timestamp(v).date() if pd.notna(v) else None


def migrate_ohlcv(session: Session, dry_run: bool = False) -> int:
    """Migrate ohlcv.parquet (2.9M rows) to OHLCV table."""
    path = ARCHIVE_TABLES / "ohlcv.parquet"
    if not path.exists():
        logger.warning("ohlcv.parquet not found at %s", path)
        return 0

    df = _safe_read_parquet(path)
    if df is None or df.empty:
        return 0

    logger.info("OHLCV parquet: %d rows", len(df))

    if dry_run:
        return len(df)

    count = 0
    for _, row in df.iterrows():
        session.add(
            OHLCV(
                ticker=str(row.get("ticker", "")),
                timestamp=pd.Timestamp(
                    row.get("timestamp")
                ).to_pydatetime(),
                timeframe="1d",
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=int(row.get("volume", 0)),
                adjusted_close=_f(row, "adjusted_close"),
                data_quality_score=_f(row, "data_quality_score"),
                source="parquet_archive",
            )
        )
        count += 1
        if count % 10000 == 0:
            session.commit()
            logger.info("OHLCV migrated: %d/%d", count, len(df))

    session.commit()
    return count


def migrate_corporate_actions(session: Session, dry_run: bool = False) -> int:
    """Migrate corporate_actions.parquet."""
    path = ARCHIVE_TABLES / "corporate_actions.parquet"
    if not path.exists():
        return 0

    df = _safe_read_parquet(path)
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
    if not path.exists():
        return 0

    df = _safe_read_parquet(path)
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
    if not path.exists():
        return 0

    df = _safe_read_parquet(path)
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
    if not path.exists():
        return 0

    df = _safe_read_parquet(path)
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
    if not path.exists():
        return 0

    df = _safe_read_parquet(path)
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
    if not path.exists():
        return 0

    df = _safe_read_parquet(path)
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
