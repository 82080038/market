"""Clean up and backfill exchange_holidays table for all 21 exchanges.

Two-phase script:
1. **Cleanup**: Remove weekend entries with empty holiday_name (these are
   not real holidays — just Saturdays/Sundays that got inserted by the
   `holidays` library which includes all public holidays regardless of
   weekday). The `_is_holiday()` check in `market_session.py` already
   handles weekends via `local.weekday() >= 5`.

2. **Backfill**: Populate accurate market holidays from `exchange_calendars`
   (2006-2027) for all 21 exchanges in `MarketSessionManager`. For exchanges
   not in `exchange_calendars` (XNSE, XMTA), use `holidays` library with
   country mapping.

Usage:
    python scripts/backfill_exchange_holidays.py [--dry-run] [--cleanup-only] [--backfill-only]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import exchange_calendars as xcals
import holidays as country_holidays
import pandas as pd
from sqlalchemy import create_engine, text

from market.config import settings

logger = logging.getLogger(__name__)

# ── All 21 exchanges from MarketSessionManager ────────────────────────────
EXCHANGES: dict[str, dict] = {
    "XIDX":  {"xcal": "XIDX",  "country": "ID", "earliest": "1990-04-06"},
    "XNYS":  {"xcal": "XNYS",  "country": "US", "earliest": "1927-12-31"},
    "XNAS":  {"xcal": "XNAS",  "country": "US", "earliest": "1971-02-06"},
    "XTSE":  {"xcal": "XTSE",  "country": "JP", "earliest": "1965-01-05"},
    "XHKG":  {"xcal": "XHKG",  "country": "HK", "earliest": "1986-12-31"},
    "XLON":  {"xcal": "XLON",  "country": "GB", "earliest": "1984-01-03"},
    "XFRA":  {"xcal": "XFRA",  "country": "DE", "earliest": "1987-12-30"},
    "XKRX":  {"xcal": "XKRX",  "country": "KR", "earliest": "2021-08-11"},
    "XSES":  {"xcal": "XSES",  "country": "SG", "earliest": "2021-08-11"},
    "XASX":  {"xcal": "XASX",  "country": "AU", "earliest": "2021-08-11"},
    "XBKK":  {"xcal": "XBKK",  "country": "TH", "earliest": "2021-08-11"},
    "XPHS":  {"xcal": "XPHS",  "country": "PH", "earliest": "2021-08-11"},
    # XNSE not in exchange_calendars — use XBOM (same country, same holidays)
    "XNSE":  {"xcal": "XBOM",  "country": "IN", "earliest": "2021-08-11"},
    "XTAI":  {"xcal": "XTAI",  "country": "TW", "earliest": "2021-08-11"},
    "XPAR":  {"xcal": "XPAR",  "country": "FR", "earliest": "2021-08-11"},
    # XMTA not in exchange_calendars — use XMIL (same country, same holidays)
    "XMTA":  {"xcal": "XMIL",  "country": "IT", "earliest": "2021-08-11"},
    "XMAD":  {"xcal": "XMAD",  "country": "ES", "earliest": "2021-08-11"},
    "BVMF":  {"xcal": "BVMF",  "country": "BR", "earliest": "2021-08-11"},
    "XTSX":  {"xcal": "XTSX",  "country": "CA", "earliest": "2021-08-11"},
    "XSAU":  {"xcal": "XSAU",  "country": "SA", "earliest": "2021-01-03"},
    "XJSE":  {"xcal": "XJSE",  "country": "ZA", "earliest": "2021-08-11"},
}

XCAL_START = date(2006, 8, 14)
END_DATE = date(2027, 12, 31)

COUNTRY_CLASSES = {
    "ID": country_holidays.ID,
    "US": country_holidays.US,
    "JP": country_holidays.JP,
    "HK": country_holidays.HK,
    "DE": country_holidays.Germany,
    "GB": country_holidays.UK,
    "KR": country_holidays.KR,
    "SG": country_holidays.SG,
    "AU": country_holidays.AU,
    "TH": country_holidays.Thailand,
    "PH": country_holidays.Philippines,
    "IN": country_holidays.India,
    "TW": country_holidays.Taiwan,
    "FR": country_holidays.France,
    "IT": country_holidays.Italy,
    "ES": country_holidays.Spain,
    "BR": country_holidays.Brazil,
    "CA": country_holidays.Canada,
    "SA": country_holidays.SaudiArabia,
    "ZA": country_holidays.SouthAfrica,
}


def get_xcal_holidays(xcal_name: str, start: date, end: date) -> list[tuple[date, str]]:
    """Get accurate market holidays from exchange_calendars (2006+)."""
    try:
        cal = xcals.get_calendar(xcal_name)
        cal_start = max(start, XCAL_START)
        cal_end = min(end, cal.last_session.date())
        if cal_start >= cal_end:
            return []
        sessions = cal.sessions_in_range(cal_start.isoformat(), cal_end.isoformat())
        session_set = set(sessions)
        all_bdays = pd.bdate_range(cal_start, cal_end)
        result = []
        for d in all_bdays:
            d_ts = pd.Timestamp(d)
            if d_ts not in session_set:
                result.append((d_ts.date(), "Market Holiday"))
        return result
    except Exception as e:
        logger.warning("exchange_calendars failed for %s: %s", xcal_name, e)
        return []


def get_country_holidays(country: str, start: date, end: date) -> list[tuple[date, str]]:
    """Get country public holidays from `holidays` library."""
    hol_cls = COUNTRY_CLASSES.get(country)
    if hol_cls is None:
        logger.warning("No holiday class for country %s", country)
        return []
    result = []
    for year in range(start.year, end.year + 1):
        try:
            year_hols = hol_cls(years=year)
            for d, name in sorted(year_hols.items()):
                d_date = d if isinstance(d, date) else d.date()
                if start <= d_date <= end and d_date.weekday() < 5:
                    result.append((d_date, str(name)))
        except Exception as e:
            logger.debug("holidays %s year %d failed: %s", country, year, e)
    return result


def merge_holidays(
    xcal_hols: list[tuple[date, str]],
    country_hols: list[tuple[date, str]],
) -> list[tuple[date, str]]:
    """Merge two holiday lists, deduplicating by date. xcal takes priority."""
    seen: set[date] = set()
    merged = []
    for d, name in xcal_hols:
        if d not in seen:
            seen.add(d)
            merged.append((d, name))
    for d, name in country_hols:
        if d not in seen:
            seen.add(d)
            merged.append((d, name))
    return merged


def cleanup_weekends(engine) -> int:
    """Remove weekend entries with empty holiday_name from exchange_holidays."""
    with engine.begin() as conn:
        result = conn.execute(text("""
            DELETE FROM exchange_holidays
            WHERE (holiday_name IS NULL OR holiday_name = '')
              AND EXTRACT(DOW FROM holiday_date) IN (0, 6)
        """))
        deleted = result.rowcount
        logger.info("Cleanup: removed %d weekend entries with empty names", deleted)
        return deleted


def backfill_exchange(engine, mic_code: str, config: dict, dry_run: bool = False) -> int:
    """Backfill holidays for a single exchange."""
    start = date.fromisoformat(config["earliest"])
    end = END_DATE

    xcal_hols = get_xcal_holidays(config["xcal"], start, end)
    country_hols = get_country_holidays(config["country"], start, end)
    merged = merge_holidays(xcal_hols, country_hols)

    if not merged:
        logger.warning("No holidays generated for %s", mic_code)
        return 0

    if dry_run:
        logger.info("[DRY-RUN] %s: %d holidays (%s → %s)",
                     mic_code, len(merged), merged[0][0], merged[-1][0])
        return len(merged)

    # Delete existing rows for this exchange, then insert fresh
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM exchange_holidays WHERE mic_code = :mic"),
                      {"mic": mic_code})
        # Insert using execute_values-style batch
        rows = [(mic_code, d.isoformat(), name, False) for d, name in merged]
        conn.execute(text("""
            INSERT INTO exchange_holidays (mic_code, holiday_date, holiday_name, is_half_day)
            VALUES (:mic, :d, :name, false)
        """), [{"mic": mic_code, "d": d.isoformat(), "name": name} for d, name in merged])

    logger.info("Backfilled %s: %d holidays (%s → %s)",
                mic_code, len(merged), merged[0][0], merged[-1][0])
    return len(merged)


def main():
    parser = argparse.ArgumentParser(description="Clean up and backfill exchange holidays")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually modify DB")
    parser.add_argument("--cleanup-only", action="store_true", help="Only cleanup weekends")
    parser.add_argument("--backfill-only", action="store_true", help="Only backfill (skip cleanup)")
    parser.add_argument("--exchange", type=str, help="Backfill single exchange (e.g. XIDX)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    engine = create_engine(settings.resolved_database_url)

    total_deleted = 0
    total_inserted = 0

    if not args.backfill_only:
        total_deleted = cleanup_weekends(engine)
        print(f"\nCleanup: removed {total_deleted} weekend entries with empty names")

    if not args.cleanup_only:
        exchanges = {args.exchange: EXCHANGES[args.exchange]} if args.exchange else EXCHANGES
        print(f"\nBackfilling {len(exchanges)} exchanges...")
        for mic_code, config in exchanges.items():
            n = backfill_exchange(engine, mic_code, config, dry_run=args.dry_run)
            total_inserted += n

    if not args.dry_run:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT mic_code, count(*) as n, min(holiday_date) as earliest, max(holiday_date) as latest
                FROM exchange_holidays GROUP BY mic_code ORDER BY mic_code
            """)).fetchall()
            print(f"\n{'='*60}")
            print(f"{'MIC':6s} {'Count':>6s}  {'Earliest':12s}  {'Latest':12s}")
            print(f"{'-'*60}")
            for r in rows:
                print(f"{r[0]:6s} {r[1]:6d}  {str(r[2]):12s}  {str(r[3]):12s}")
            total = sum(r[1] for r in rows)
            print(f"{'-'*60}")
            print(f"{'TOTAL':6s} {total:6d}")

    print(f"\nDone: deleted {total_deleted}, inserted {total_inserted}")


if __name__ == "__main__":
    main()
