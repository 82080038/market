"""Populate exchange_holidays table with comprehensive holiday data.

Uses two data sources:
1. **exchange_calendars** (2006-2027) — accurate market trading holidays
2. **holidays** library (pre-2006) — country public holidays as proxy

Covers ALL exchanges present in the PG database:
  XNYS (NYSE), XNAS (NASDAQ), XTSE (Tokyo), XLON (LSE), XHKG (HKEX),
  XFRA (XETRA/Frankfurt), XIDX (IDX/Indonesia), XSHG (Shanghai),
  XKRX (Korea), XASX (Australia), XSES (Singapore), XKLS (Malaysia),
  XBOM (Bombay/NSE India), XCEC (CBOE), XFXS (Forex)

Holiday range: from earliest OHLCV date per exchange to 2027-12-31.

Usage:
    python scripts/seed_exchange_holidays.py [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime

import exchange_calendars as xcals
import holidays as country_holidays
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

# ── Mapping: exchange MIC → config ──
# xcal_name: exchange_calendars calendar name (None = not in xcal)
# country: ISO code for holidays library
# earliest: fallback earliest date if not in PG
EXCHANGE_MAP = {
    "XNYS": {"xcal_name": "XNYS", "country": "US", "earliest": "1927-12-31"},
    "XNAS": {"xcal_name": "XNAS", "country": "US", "earliest": "1971-02-06"},
    "XTSE": {"xcal_name": "XTSE", "country": "JP", "earliest": "1965-01-05"},
    "XLON": {"xcal_name": "XLON", "country": "GB", "earliest": "1984-01-03"},
    "XHKG": {"xcal_name": "XHKG", "country": "HK", "earliest": "1986-12-31"},
    "XFRA": {"xcal_name": "XFRA", "country": "DE", "earliest": "1987-12-30"},
    "XIDX": {"xcal_name": "XIDX", "country": "ID", "earliest": "1990-04-06"},
    "XSHG": {"xcal_name": "XSHG", "country": "CN", "earliest": "1997-07-02"},
    "XKRX": {"xcal_name": "XKRX", "country": "KR", "earliest": "2021-08-11"},
    "XASX": {"xcal_name": "XASX", "country": "AU", "earliest": "2021-08-11"},
    "XSES": {"xcal_name": "XSES", "country": "SG", "earliest": "2021-08-11"},
    "XKLS": {"xcal_name": "XKLS", "country": "MY", "earliest": "2021-08-11"},
    "XBOM": {"xcal_name": "XBOM", "country": "IN", "earliest": "2021-08-11"},
}

# Exchanges in PG but not in exchange_calendars — use country holidays only
EXTRA_EXCHANGES = {
    "XCEC": {"country": "US", "earliest": "2021-07-13"},
    "XFXS": {"country": "US", "earliest": "2021-07-13"},
}

XCAL_START = date(2006, 8, 14)
END_DATE = date(2027, 12, 31)


def get_xcal_holidays(mic_code: str, start: date, end: date) -> list[tuple[date, str, bool]]:
    """Get accurate market holidays from exchange_calendars (2006+).

    Returns list of (date, name, is_half_day).
    """
    import pandas as pd

    try:
        cal = xcals.get_calendar(mic_code)
        cal_start = max(start, XCAL_START)
        cal_end = min(end, cal.last_session.date())
        if cal_start >= cal_end:
            return []

        # Get all sessions in range
        sessions = cal.sessions_in_range(cal_start.isoformat(), cal_end.isoformat())
        session_set = set(sessions)

        # Get all business days in range
        all_bdays = pd.bdate_range(cal_start, cal_end)
        holidays_list = []

        for d in all_bdays:
            d_ts = pd.Timestamp(d)
            if d_ts not in session_set:
                d_date = d_ts.date()
                holidays_list.append((d_date, "Market Holiday", False))

        return holidays_list
    except Exception as e:
        logger.warning("exchange_calendars failed for %s: %s", mic_code, e)
        return []


def get_country_holidays(
    country: str,
    start: date,
    end: date,
) -> list[tuple[date, str, bool]]:
    """Get country public holidays from `holidays` library.

    Used as proxy for market holidays pre-2006 (when exchange_calendars has no data).

    Returns list of (date, name, is_half_day).
    """
    # Map ISO country code to holidays library class
    COUNTRY_CLASSES = {
        "US": country_holidays.US,
        "GB": country_holidays.UK,
        "JP": country_holidays.JP,
        "HK": country_holidays.HK,
        "DE": country_holidays.Germany,
        "ID": country_holidays.ID,
        "CN": country_holidays.CN,
        "KR": country_holidays.KR,
        "AU": country_holidays.AU,
        "SG": country_holidays.SG,
        "MY": country_holidays.Malaysia,
        "IN": country_holidays.India,
    }

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
                if start <= d_date <= end:
                    if d_date.weekday() < 5:
                        result.append((d_date, str(name), False))
        except Exception as e:
            logger.debug("holidays %s year %d failed: %s", country, year, e)
            continue
    return result


def merge_holidays(
    xcal_hols: list[tuple[date, str, bool]],
    country_hols: list[tuple[date, str, bool]],
) -> list[tuple[date, str, bool]]:
    """Merge two holiday lists, deduplicating by date.

    exchange_calendars takes priority (more accurate for market holidays).
    """
    seen_dates: set[date] = set()
    merged = []

    for d, name, half in xcal_hols:
        if d not in seen_dates:
            seen_dates.add(d)
            merged.append((d, name, half))

    for d, name, half in country_hols:
        if d not in seen_dates:
            seen_dates.add(d)
            merged.append((d, name, half))

    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed exchange_holidays table")
    parser.add_argument("--dry-run", action="store_true", help="Print without inserting")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL", "postgresql://petrick:market_dev@localhost:5432/market")
    engine = create_engine(db_url)

    # Get actual earliest dates from PG database
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT exchange_mic, MIN(timestamp) as min_d FROM ohlcv GROUP BY exchange_mic")
        )
        pg_dates = {row.exchange_mic: row.min_d.date() for row in result}

    print("=" * 70)
    print("EXCHANGE HOLIDAYS SEED SCRIPT")
    print("=" * 70)
    print(f"Data sources: exchange_calendars (2006+) + holidays library (pre-2006)")
    print(f"End date: {END_DATE}")
    print()

    total_inserted = 0
    total_skipped = 0

    if not args.dry_run:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM exchange_holidays"))
        print("Cleared existing exchange_holidays data.\n")

    all_exchanges = {**EXCHANGE_MAP, **EXTRA_EXCHANGES}

    for mic_code, config in sorted(all_exchanges.items()):
        # Use actual earliest date from PG if available
        earliest = pg_dates.get(mic_code)
        if earliest is None:
            earliest = datetime.strptime(config["earliest"], "%Y-%m-%d").date()

        country = config["country"]
        xcal_name = config.get("xcal_name")

        print(f"  {mic_code:6s} ({country}) — earliest={earliest}")

        # Get holidays from exchange_calendars (2006+)
        xcal_hols = []
        if xcal_name:
            xcal_hols = get_xcal_holidays(xcal_name, earliest, END_DATE)

        # Get holidays from country library (pre-2006 for xcal exchanges, full range for others)
        if xcal_name:
            # Only need country holidays for pre-2006 period
            pre_2006_end = min(date(2006, 8, 13), END_DATE)
            country_hols = []
            if earliest < XCAL_START:
                country_hols = get_country_holidays(country, earliest, pre_2006_end)
        else:
            # No exchange_calendars data — use country holidays for full range
            country_hols = get_country_holidays(country, earliest, END_DATE)

        # Merge
        all_hols = merge_holidays(xcal_hols, country_hols)
        all_hols.sort(key=lambda x: x[0])

        print(f"    xcal={len(xcal_hols)}, country_pre2006={len(country_hols)}, merged={len(all_hols)}")

        if args.dry_run:
            if all_hols:
                print(f"    First: {all_hols[0][0]} {all_hols[0][1]}")
                print(f"    Last:  {all_hols[-1][0]} {all_hols[-1][1]}")
            total_inserted += len(all_hols)
            continue

        # Insert
        inserted = 0
        skipped = 0
        with engine.begin() as conn:
            for d, name, half in all_hols:
                try:
                    conn.execute(
                        text(
                            "INSERT INTO exchange_holidays (mic_code, holiday_date, holiday_name, is_half_day) "
                            "VALUES (:mic, :d, :name, :half) "
                            "ON CONFLICT (mic_code, holiday_date) DO NOTHING"
                        ),
                        {"mic": mic_code, "d": d, "name": name[:200], "half": half},
                    )
                    inserted += 1
                except Exception:
                    skipped += 1

        total_inserted += inserted
        total_skipped += skipped
        print(f"    Inserted: {inserted}, Skipped: {skipped}")

    print()
    print("=" * 70)
    if args.dry_run:
        print(f"DRY RUN: {total_inserted} holidays would be inserted")
    else:
        print(f"Total: {total_inserted} inserted, {total_skipped} skipped")

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT mic_code, MIN(holiday_date) as min_d, MAX(holiday_date) as max_d, "
                    "COUNT(*) as cnt FROM exchange_holidays GROUP BY mic_code ORDER BY mic_code"
                )
            )
            print("\nFinal exchange_holidays per exchange:")
            for r in result:
                print(f"  {r.mic_code:6s} {r.min_d} to {r.max_d}  ({r.cnt} rows)")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
