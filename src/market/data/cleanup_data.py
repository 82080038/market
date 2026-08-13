"""Comprehensive data quality cleanup for market_paper.db.

Addresses 8 audit findings (2026-08-06):
  #1 Ticker suffix inconsistency (instrument_master & foreign_flow missing .JK)
  #2 OHLC anomalies (high<low, high<open/close, low>open/close)
  #3 volume=0 flagging via data_quality_score
  #4 Timestamp normalization (17:00:00 → 00:00:00) + gap backfill from parquet
  #5 sector_master consolidation (remove duplicate 3-letter codes)
  #6 market_calendar backfill 1997-2025 from OHLCV trading days
  #7 fundamental_data re-import with correct column mapping
  #8 esg_scores & corporate_governance import from parquet

All operations are idempotent (safe to re-run).

Usage:
    ENV=paper python -m market.data.cleanup_data [--dry-run] [--skip-fix N]
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from sqlalchemy import text

from market.config import settings
from market.db.engine import get_sessionmaker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ARCHIVE_TABLES = Path(settings.parquet_archive_path) / "archive" / "tables"


# ── Fix #1: Ticker suffix normalization ──────────────────────────────────


def fix_01_ticker_suffix(session: Session, dry_run: bool = False) -> dict:
    """Add .JK suffix to instrument_master and foreign_flow for XIDX equities."""
    stats = {"instrument_master_updated": 0, "foreign_flow_updated": 0,
             "instrument_master_added": 0}
    if dry_run:
        return stats

    # Build suffix map from market_registry
    suffix_map = dict(
        session.execute(
            text("SELECT mic_code, data_suffix FROM market_registry")
        ).fetchall()
    )

    # --- instrument_master: add suffix for XIDX equities/ETFs ---
    # Indices (^LQ45, ^JKSE) and global tickers keep their original form.
    rows = session.execute(
        text(
            "SELECT ticker, market_mic, asset_class FROM instrument_master "
            "WHERE market_mic = 'XIDX' AND asset_class IN ('equity', 'etf') "
            "AND ticker NOT LIKE '%.JK'"
        )
    ).fetchall()
    for ticker, mic, _asset_class in rows:
        suffix = suffix_map.get(mic, "")
        if suffix and not ticker.endswith(suffix):
            new_ticker = f"{ticker}{suffix}"
            # Check if new_ticker already exists (from a prior run)
            exists = session.execute(
                text("SELECT ticker FROM instrument_master WHERE ticker = :t"),
                {"t": new_ticker},
            ).fetchone()
            if exists:
                # Delete the old unsuffixed row (data merged into suffixed one)
                session.execute(
                    text("DELETE FROM instrument_master WHERE ticker = :t"),
                    {"t": ticker},
                )
            else:
                session.execute(
                    text(
                        "UPDATE instrument_master SET ticker = :new WHERE ticker = :old"
                    ),
                    {"new": new_ticker, "old": ticker},
                )
            stats["instrument_master_updated"] += 1

    # --- Add missing OHLCV tickers to instrument_master ---
    ohlcv_tickers = set(
        r[0]
        for r in session.execute(
            text("SELECT DISTINCT ticker FROM ohlcv")
        ).fetchall()
    )
    im_tickers = set(
        r[0]
        for r in session.execute(
            text("SELECT ticker FROM instrument_master")
        ).fetchall()
    )
    missing = ohlcv_tickers - im_tickers
    for ticker in sorted(missing):
        # Determine market_mic and asset_class from ticker pattern
        if ticker.startswith("^") or ticker in ("^JKSE", "^LQ45"):
            mic, asset_class = "XIDX", "index"
        elif ticker.endswith(".JK"):
            mic, asset_class = "XIDX", "equity"
        elif ticker.endswith(".SS"):
            mic, asset_class = "XSHG", "index"
        elif "=F" in ticker:
            mic, asset_class = "XIDX", "futures"
        elif "=X" in ticker:
            mic, asset_class = "XIDX", "fx"
        elif ticker in ("DBA", "XLE", "XIIT"):
            mic, asset_class = "XIDX", "etf"
        else:
            mic, asset_class = "XIDX", "equity"

        # Check if mic exists in market_registry
        mic_exists = session.execute(
            text("SELECT mic_code FROM market_registry WHERE mic_code = :m"),
            {"m": mic},
        ).fetchone()
        if not mic_exists:
            mic = "XIDX"  # fallback

        session.execute(
            text(
                "INSERT OR IGNORE INTO instrument_master "
                "(ticker, market_mic, asset_class, name, base_currency, "
                "reporting_currency, lot_size, is_active, created_at, updated_at) "
                "VALUES (:t, :m, :ac, :n, 'IDR', 'IDR', 100, 1, "
                "datetime('now'), datetime('now'))"
            ),
            {"t": ticker, "m": mic, "ac": asset_class, "n": ticker},
        )
        stats["instrument_master_added"] += 1

    # --- foreign_flow: add .JK suffix ---
    ff_rows = session.execute(
        text(
            "SELECT DISTINCT ticker FROM foreign_flow "
            "WHERE ticker NOT LIKE '%.JK' AND ticker NOT LIKE '%=%' "
            "AND ticker NOT LIKE '^%'"
        )
    ).fetchall()
    for (ticker,) in ff_rows:
        new_ticker = f"{ticker}.JK"
        # Use UPDATE with subquery to avoid unique constraint issues
        session.execute(
            text(
                "UPDATE OR REPLACE foreign_flow SET ticker = :new "
                "WHERE ticker = :old"
            ),
            {"new": new_ticker, "old": ticker},
        )
        stats["foreign_flow_updated"] += 1

    session.commit()
    return stats


# ── Fix #2: OHLC anomalies ───────────────────────────────────────────────


def fix_02_ohlcv_anomalies(session: Session, dry_run: bool = False) -> dict:
    """Fix OHLC inconsistencies: high=max(o,h,c), low=min(o,l,c), swap if needed."""
    stats = {"high_low_swap": 0, "high_fixed": 0, "low_fixed": 0}
    if dry_run:
        return stats

    # Fix high < open or high < close → high = max(open, high, close)
    result = session.execute(
        text(
            "UPDATE ohlcv SET high = MAX(open, high, close) "
            "WHERE high < open OR high < close"
        )
    )
    stats["high_fixed"] = result.rowcount

    # Fix low > open or low > close → low = min(open, low, close)
    result = session.execute(
        text(
            "UPDATE ohlcv SET low = MIN(open, low, close) "
            "WHERE low > open OR low > close"
        )
    )
    stats["low_fixed"] = result.rowcount

    # Fix remaining high < low → swap
    result = session.execute(
        text(
            "UPDATE ohlcv SET high = low, low = high "
            "WHERE high < low"
        )
    )
    stats["high_low_swap"] = result.rowcount

    session.commit()
    return stats


# ── Fix #3: volume=0 flagging ────────────────────────────────────────────


def fix_03_volume_zero_flag(session: Session, dry_run: bool = False) -> dict:
    """Flag volume=0 rows with data_quality_score=0.5 (suspended/illiquid)."""
    stats = {"flagged": 0}
    if dry_run:
        return stats

    # Flag volume=0 rows with dqs=0.3 to distinguish from genuinely bad data (dqs=0)
    result = session.execute(
        text(
            "UPDATE ohlcv SET data_quality_score = 0.3 "
            "WHERE volume = 0 AND data_quality_score = 0"
        )
    )
    stats["flagged"] = result.rowcount
    session.commit()
    return stats


# ── Fix #4: Timestamp normalization + gap backfill ───────────────────────


def fix_04_timestamp_normalize(session: Session, dry_run: bool = False) -> dict:
    """Normalize OHLCV timestamps to 00:00:00 and backfill gaps from parquet."""
    stats = {"timestamps_normalized": 0, "duplicates_merged": 0, "rows_backfilled": 0}
    if dry_run:
        return stats

    # Step 1: Normalize timestamps to date-only (00:00:00)
    # For rows with time component, update to date(timestamp) 00:00:00
    # This may create duplicates — handle with INSERT OR REPLACE logic
    bad_ts = session.execute(
        text(
            "SELECT id, ticker, date(timestamp), timeframe, open, high, low, close, "
            "volume, adjusted_close, data_quality_score, source "
            "FROM ohlcv WHERE time(timestamp) != '00:00:00'"
        )
    ).fetchall()

    for row in bad_ts:
        (id_, ticker, d, tf, o, h, l, c, v, ac, dqs, _src) = row
        new_ts = f"{d} 00:00:00"
        # Check if a row with normalized timestamp already exists
        existing = session.execute(
            text(
                "SELECT id, data_quality_score FROM ohlcv "
                "WHERE ticker = :t AND timestamp = :ts AND timeframe = :tf AND id != :id"
            ),
            {"t": ticker, "ts": new_ts, "tf": tf, "id": id_},
        ).fetchone()

        if existing:
            # Merge: keep the existing row, delete the bad one
            # If the bad row has better quality score, update the existing
            if dqs is not None and (existing[1] is None or dqs > existing[1]):
                session.execute(
                    text(
                        "UPDATE ohlcv SET open=:o, high=:h, low=:l, close=:c, "
                        "volume=:v, adjusted_close=:ac, data_quality_score=:dqs "
                        "WHERE id = :eid"
                    ),
                    {"o": o, "h": h, "l": l, "c": c, "v": v, "ac": ac,
                     "dqs": dqs, "eid": existing[0]},
                )
            session.execute(text("DELETE FROM ohlcv WHERE id = :id"), {"id": id_})
            stats["duplicates_merged"] += 1
        else:
            session.execute(
                text("UPDATE ohlcv SET timestamp = :ts WHERE id = :id"),
                {"ts": new_ts, "id": id_},
            )
            stats["timestamps_normalized"] += 1

        if (stats["timestamps_normalized"] + stats["duplicates_merged"]) % 1000 == 0:
            session.commit()

    session.commit()

    # Step 2: Backfill missing rows from parquet
    parquet_path = ARCHIVE_TABLES / "ohlcv.parquet"
    if not parquet_path.exists():
        logger.warning("ohlcv.parquet not found, skipping backfill")
        return stats

    df = pd.read_parquet(parquet_path)
    # Normalize parquet timestamps to date strings
    df["ts_date"] = df["timestamp"].astype(str).str[:10]
    df["ts_normalized"] = df["ts_date"] + " 00:00:00"

    # Get existing (ticker, timestamp) pairs for quick lookup
    existing_pairs = set(
        (r[0], str(r[1])[:19])
        for r in session.execute(
            text("SELECT ticker, timestamp FROM ohlcv")
        ).fetchall()
    )

    # Group by ticker to process efficiently
    count = 0
    for _, row in df.iterrows():
        ticker = str(row.get("ticker", ""))
        ts = row["ts_normalized"]
        tf = str(row.get("timeframe", "1d"))

        close_val = row.get("close")
        if pd.isna(close_val):
            continue

        key = (ticker, ts)
        if key in existing_pairs:
            continue

        session.execute(
            text(
                "INSERT INTO ohlcv (ticker, timestamp, timeframe, open, high, low, "
                "close, volume, adjusted_close, data_quality_score, source, created_at) "
                "VALUES (:t, :ts, :tf, :o, :h, :l, :c, :v, :ac, :dqs, :src, "
                "datetime('now'))"
            ),
            {
                "t": ticker, "ts": ts, "tf": tf,
                "o": float(row.get("open", 0)) if pd.notna(row.get("open")) else 0,
                "h": float(row.get("high", 0)) if pd.notna(row.get("high")) else 0,
                "l": float(row.get("low", 0)) if pd.notna(row.get("low")) else 0,
                "c": float(close_val),
                "v": int(row.get("volume", 0)) if pd.notna(row.get("volume")) else 0,
                "ac": float(row["adjusted_close"]) if pd.notna(row.get("adjusted_close")) else None,
                "dqs": float(row["data_quality_score"]) if pd.notna(row.get("data_quality_score")) else None,
                "src": "parquet_backfill",
            },
        )
        existing_pairs.add(key)
        count += 1
        if count % 5000 == 0:
            session.commit()
            logger.info("Backfilled %d rows", count)

    session.commit()
    stats["rows_backfilled"] = count
    return stats


# ── Fix #5: sector_master consolidation ──────────────────────────────────


def fix_05_sector_master(session: Session, dry_run: bool = False) -> dict:
    """Remove duplicate 3-letter sector codes, keep 11 long-form IDX sectors."""
    stats = {"removed_short_codes": 0}
    if dry_run:
        return stats

    # The 3-letter codes (FIN, IND, CON, ENE, INF, MIN, AGR, HLT, TEL, TRA, OTH)
    # are redundant with the long-form codes. Remove them.
    short_codes = ("FIN", "IND", "CON", "ENE", "INF", "MIN", "AGR", "HLT",
                   "TEL", "TRA", "OTH")
    placeholders = ",".join(f"'{c}'" for c in short_codes)
    result = session.execute(
        text(f"DELETE FROM sector_master WHERE kode IN ({placeholders})")
    )
    stats["removed_short_codes"] = result.rowcount
    session.commit()
    return stats


# ── Fix #6: market_calendar backfill ─────────────────────────────────────


def fix_06_market_calendar(session: Session, dry_run: bool = False) -> dict:
    """Backfill market_calendar 1997-2025 from OHLCV trading days."""
    stats = {"trading_days_added": 0, "non_trading_days_added": 0}
    if dry_run:
        return stats

    # Get all dates that already exist in calendar
    existing_dates = set(
        str(r[0])
        for r in session.execute(
            text("SELECT date FROM market_calendar WHERE exchange = 'IDX'")
        ).fetchall()
    )

    # Get trading days from OHLCV (.JK tickers only, to exclude global markets)
    trading_days = set(
        str(r[0])
        for r in session.execute(
            text(
                "SELECT DISTINCT date(timestamp) FROM ohlcv "
                "WHERE ticker LIKE '%.JK' AND timeframe = '1d'"
            )
        ).fetchall()
    )

    # Get full date range from OHLCV
    min_date, max_date = session.execute(
        text(
            "SELECT MIN(date(timestamp)), MAX(date(timestamp)) FROM ohlcv "
            "WHERE ticker LIKE '%.JK'"
        )
    ).fetchone()

    if not min_date or not max_date:
        logger.warning("No OHLCV data for calendar backfill")
        return stats

    # Generate all dates in range
    from datetime import datetime, timedelta
    start = datetime.strptime(str(min_date), "%Y-%m-%d").date()
    end = datetime.strptime(str(max_date), "%Y-%m-%d").date()

    current = start
    batch = []
    while current <= end:
        date_str = current.isoformat()
        if date_str not in existing_dates:
            is_trading = date_str in trading_days
            # Determine holiday name for known IDX holidays
            holiday_name = _get_idx_holiday_name(current)
            is_weekend = current.weekday() >= 5  # Sat=5, Sun=6

            if not is_trading and not is_weekend and not holiday_name:
                # Unknown non-trading day (could be special holiday)
                holiday_name = ""

            batch.append({
                "date": date_str,
                "exchange": "IDX",
                "is_trading_day": 1 if is_trading else 0,
                "holiday_name": holiday_name or "",
                "half_day": 0,
            })

            if is_trading:
                stats["trading_days_added"] += 1
            else:
                stats["non_trading_days_added"] += 1

            if len(batch) >= 500:
                _insert_calendar_batch(session, batch)
                batch = []

        current += timedelta(days=1)

    if batch:
        _insert_calendar_batch(session, batch)

    session.commit()
    return stats


def _insert_calendar_batch(session: Session, batch: list[dict]) -> None:
    for item in batch:
        session.execute(
            text(
                "INSERT OR IGNORE INTO market_calendar "
                "(date, exchange, is_trading_day, holiday_name, half_day, created_at) "
                "VALUES (:d, 'IDX', :it, :hn, :hd, datetime('now'))"
            ),
            {"d": item["date"], "it": item["is_trading_day"],
             "hn": item["holiday_name"], "hd": item["half_day"]},
        )


def _get_idx_holiday_name(d: date) -> str | None:
    """Return holiday name for known IDX holidays (fixed-date only)."""
    # Fixed-date Indonesian public holidays (approximate — religious holidays vary)
    fixed_holidays = {
        (1, 1): "Tahun Baru",
        (8, 17): "Hari Kemerdekaan",
        (12, 25): "Natal",
        (12, 26): "Hari Raya Box",
        (1, 1): "Tahun Baru",
        (5, 1): "Hari Buruh",
        (6, 1): "Hari Lahir Pancasila",
    }
    return fixed_holidays.get((d.month, d.day))


# ── Fix #7: fundamental_data re-import ───────────────────────────────────


def fix_07_fundamental_data(session: Session, dry_run: bool = False) -> dict:
    """Re-import fundamental_data from parquet with correct column mapping."""
    stats = {"deleted_old": 0, "imported_new": 0}
    if dry_run:
        return stats

    parquet_path = ARCHIVE_TABLES / "fundamental_data.parquet"
    if not parquet_path.exists():
        logger.warning("fundamental_data.parquet not found")
        return stats

    # Delete existing rows (they have wrong mapping → 0 values)
    result = session.execute(text("DELETE FROM fundamental_data"))
    stats["deleted_old"] = result.rowcount
    session.commit()

    df = pd.read_parquet(parquet_path)
    count = 0
    for _, row in df.iterrows():
        ticker = str(row.get("ticker", ""))
        d = row.get("date")
        if pd.isna(d):
            continue
        date_val = pd.Timestamp(d).date()

        # Correct column mapping:
        # parquet → DB
        # pe_ratio → pe, pb_ratio → pb, debt_to_equity → der
        # earnings_per_share → eps, net_profit → net_income
        # revenue → revenue, total_assets → total_assets
        # dividend_yield → dividend_yield, roe → roe
        def _fv(key):
            v = row.get(key)
            return float(v) if pd.notna(v) else None

        session.execute(
            text(
                "INSERT OR REPLACE INTO fundamental_data "
                "(ticker, date, pe, pb, roe, der, dividend_yield, eps, "
                "revenue, net_income, total_assets, market_cap, source, created_at) "
                "VALUES (:t, :d, :pe, :pb, :roe, :der, :dy, :eps, "
                ":rev, :ni, :ta, :mc, :src, datetime('now'))"
            ),
            {
                "t": ticker, "d": date_val,
                "pe": _fv("pe_ratio"),
                "pb": _fv("pb_ratio"),
                "roe": _fv("roe"),
                "der": _fv("debt_to_equity"),
                "dy": _fv("dividend_yield"),
                "eps": _fv("earnings_per_share"),
                "rev": _fv("revenue"),
                "ni": _fv("net_profit"),
                "ta": _fv("total_assets"),
                "mc": None,  # not in parquet
                "src": "parquet_reimport",
            },
        )
        count += 1
        if count % 200 == 0:
            session.commit()

    session.commit()
    stats["imported_new"] = count
    return stats


# ── Fix #8: ESG scores & corporate governance ────────────────────────────


def fix_08_esg_governance(session: Session, dry_run: bool = False) -> dict:
    """Import esg_scores and corporate_governance from parquet."""
    stats = {"esg_imported": 0, "cg_imported": 0}
    if dry_run:
        return stats

    # ESG scores
    esg_path = ARCHIVE_TABLES / "esg_scores.parquet"
    if esg_path.exists():
        df = pd.read_parquet(esg_path)
        count = 0
        for _, row in df.iterrows():
            kode = str(row.get("kode", ""))
            year = int(row.get("year", 0))
            agency = str(row.get("rating_agency", ""))
            if not kode or not year or not agency:
                continue
            rating = str(row["rating"]) if pd.notna(row.get("rating")) else None
            score = float(row["score"]) if pd.notna(row.get("score")) else None

            session.execute(
                text(
                    "INSERT OR REPLACE INTO esg_scores "
                    "(kode, year, rating_agency, rating, score, created_at) "
                    "VALUES (:k, :y, :ra, :r, :s, datetime('now'))"
                ),
                {"k": kode, "y": year, "ra": agency, "r": rating, "s": score},
            )
            count += 1
        session.commit()
        stats["esg_imported"] = count

    # Corporate governance
    cg_path = ARCHIVE_TABLES / "corporate_governance.parquet"
    if cg_path.exists():
        df = pd.read_parquet(cg_path)
        count = 0
        for _, row in df.iterrows():
            kode = str(row.get("kode", ""))
            year = int(row.get("year", 0))
            if not kode or not year:
                continue

            def _fv(key):
                v = row.get(key)
                return float(v) if pd.notna(v) else None

            def _sv(key):
                v = row.get(key)
                return str(v) if pd.notna(v) else None

            def _bv(key):
                v = row.get(key)
                if pd.isna(v):
                    return None
                return 1 if v else 0

            session.execute(
                text(
                    "INSERT OR REPLACE INTO corporate_governance "
                    "(kode, year, board_commissioners, independent_commissioners, "
                    "board_directors, audit_committee_meetings, gcg_score, "
                    "acgs_score, has_whistleblowing, has_risk_committee, created_at) "
                    "VALUES (:k, :y, :bc, :ic, :bd, :acm, :gcg, :acgs, :hw, :hr, "
                    "datetime('now'))"
                ),
                {
                    "k": kode, "y": year,
                    "bc": _fv("board_commissioners"),
                    "ic": _fv("independent_commissioners"),
                    "bd": _fv("board_directors"),
                    "acm": _fv("audit_committee_meetings"),
                    "gcg": _sv("gcg_score"),
                    "acgs": _sv("acgs_score"),
                    "hw": _bv("has_whistleblowing"),
                    "hr": _bv("has_risk_committee"),
                },
            )
            count += 1
        session.commit()
        stats["cg_imported"] = count

    return stats


# ── Main runner ──────────────────────────────────────────────────────────


FIXES = {
    1: ("Ticker suffix normalization", fix_01_ticker_suffix),
    2: ("OHLCV anomaly fixes", fix_02_ohlcv_anomalies),
    3: ("volume=0 flagging", fix_03_volume_zero_flag),
    4: ("Timestamp normalization + gap backfill", fix_04_timestamp_normalize),
    5: ("sector_master consolidation", fix_05_sector_master),
    6: ("market_calendar backfill 1997-2025", fix_06_market_calendar),
    7: ("fundamental_data re-import", fix_07_fundamental_data),
    8: ("ESG & corporate governance import", fix_08_esg_governance),
}


def run_all(dry_run: bool = False, skip: set[int] | None = None) -> None:
    """Run all cleanup fixes in order."""
    skip = skip or set()
    sessionmaker = get_sessionmaker()
    session = sessionmaker()

    try:
        for fix_num, (name, func) in FIXES.items():
            if fix_num in skip:
                logger.info("Skipping Fix #%d: %s", fix_num, name)
                continue
            logger.info("=" * 60)
            logger.info("Fix #%d: %s %s", fix_num, name,
                        "[DRY RUN]" if dry_run else "")
            logger.info("=" * 60)
            stats = func(session, dry_run=dry_run)
            for k, v in stats.items():
                logger.info("  %s: %s", k, f"{v:,}")
            logger.info("Done Fix #%d", fix_num)
    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser(description="Data quality cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--skip-fix", type=int, action="append", default=[],
                        help="Skip specific fix number (can repeat)")
    args = parser.parse_args()
    run_all(dry_run=args.dry_run, skip=set(args.skip_fix))
