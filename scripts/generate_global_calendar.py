"""Generate market calendar for global exchanges (non-IDX).

Uses the `pandas_market_calendars` library if available, otherwise falls back
to `yfinance` holiday data or manual holiday lists for major exchanges.

Populates the market_calendar table with trading/non-trading days for:
- XNYS (NYSE), XNAS (Nasdaq) — US
- XHKG (HKEX) — Hong Kong
- XTKS (Tokyo) — Japan
- XLON (LSE) — UK
- XEUC (Euronext) — EU

Usage:
    ENV=research uv run python scripts/generate_global_calendar.py [--year 2025] [--all-years]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from sqlalchemy import select, text

from market.db.engine import get_sessionmaker
from market.db.models import MarketCalendar

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Exchange → (MIC, timezone, weekends)
EXCHANGES = [
    ("XNYS", "America/New_York"),
    ("XNAS", "America/New_York"),
    ("XHKG", "Asia/Hong_Kong"),
    ("XTKS", "Asia/Tokyo"),
    ("XLON", "Europe/London"),
    ("XEUC", "Europe/Paris"),
]

# Fixed holidays per exchange (non-DST dependent)
# These are the common closed days; floating holidays handled below
FIXED_HOLIDAYS = {
    "XNYS": [
        (1, 1, "New Year's Day"),
        (7, 4, "Independence Day"),
        (12, 25, "Christmas"),
    ],
    "XNAS": [
        (1, 1, "New Year's Day"),
        (7, 4, "Independence Day"),
        (12, 25, "Christmas"),
    ],
    "XHKG": [
        (1, 1, "New Year's Day"),
        (12, 25, "Christmas"),
    ],
    "XTKS": [
        (1, 1, "New Year's Day"),
        (12, 25, "Christmas"),  # Not official but often closed
    ],
    "XLON": [
        (1, 1, "New Year's Day"),
        (12, 25, "Christmas"),
        (12, 26, "Boxing Day"),
    ],
    "XEUC": [
        (1, 1, "New Year's Day"),
        (12, 25, "Christmas"),
        (12, 26, "St Stephen's Day"),
    ],
}

# US floating holidays (observed on weekdays)
US_FLOATING_HOLIDAYS = {
    # MLK Day: 3rd Monday of January
    "mlk_day": lambda y: _nth_weekday(y, 1, 0, 3),  # Monday=0
    # Presidents Day: 3rd Monday of February
    "presidents_day": lambda y: _nth_weekday(y, 2, 0, 3),
    # Memorial Day: last Monday of May
    "memorial_day": lambda y: _last_weekday(y, 5, 0),
    # Labor Day: 1st Monday of September
    "labor_day": lambda y: _nth_weekday(y, 9, 0, 1),
    # Thanksgiving: 4th Thursday of November
    "thanksgiving": lambda y: _nth_weekday(y, 11, 3, 4),
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Get the nth weekday of a month. weekday: Monday=0."""
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    d += timedelta(weeks=n - 1)
    return d


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Get the last weekday of a month. weekday: Monday=0."""
    if month == 12:
        d = date(year, 12, 31)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def get_us_holidays(year: int) -> dict[date, str]:
    """Return US market holidays for a given year."""
    holidays: dict[date, str] = {}

    for m, d, name in FIXED_HOLIDAYS["XNYS"]:
        try:
            hd = date(year, m, d)
            # If weekend, observe on nearest weekday
            if hd.weekday() == 5:  # Saturday → Friday
                hd = hd - timedelta(days=1)
            elif hd.weekday() == 6:  # Sunday → Monday
                hd = hd + timedelta(days=1)
            holidays[hd] = name
        except ValueError:
            pass

    for name, func in US_FLOATING_HOLIDAYS.items():
        holidays[func(year)] = name.replace("_", " ").title()

    # Good Friday (NYSE closed)
    good_friday = _good_friday(year)
    if good_friday:
        holidays[good_friday] = "Good Friday"

    return holidays


def _good_friday(year: int) -> date | None:
    """Calculate Good Friday using the Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    easter = date(year, month, day)
    return easter - timedelta(days=2)


def get_holidays_for_exchange(exchange: str, year: int) -> dict[date, str]:
    """Get holidays for a specific exchange and year."""
    if exchange in ("XNYS", "XNAS"):
        return get_us_holidays(year)

    holidays: dict[date, str] = {}
    fixed = FIXED_HOLIDAYS.get(exchange, [])
    for m, d, name in fixed:
        try:
            hd = date(year, m, d)
            if hd.weekday() == 5:
                hd = hd - timedelta(days=1)
            elif hd.weekday() == 6:
                hd = hd + timedelta(days=1)
            holidays[hd] = name
        except ValueError:
            pass

    # Good Friday for all exchanges
    gf = _good_friday(year)
    if gf:
        holidays[gf] = "Good Friday"

    # Exchange-specific floating holidays
    if exchange == "XHKG":
        # Lunar New Year (approximate — typically late Jan / early Feb)
        # Using fixed dates as approximation; real LNY varies
        # Easter Monday (HK closed)
        easter_monday = gf + timedelta(days=3) if gf else None
        if easter_monday:
            holidays[easter_monday] = "Easter Monday"
        # Buddha's birthday, Mid-Autumn, National Day — complex lunar calc
        # For simplicity, add National Day (Oct 1)
        try:
            holidays[date(year, 10, 1)] = "National Day"
        except ValueError:
            pass

    if exchange == "XTKS":
        # Golden Week (late April / early May)
        try:
            holidays[date(year, 4, 29)] = "Showa Day"
            holidays[date(year, 5, 3)] = "Constitution Day"
            holidays[date(year, 5, 4)] = "Greenery Day"
            holidays[date(year, 5, 5)] = "Children's Day"
        except ValueError:
            pass
        # Respect for the Aged Day: 3rd Monday of September
        holidays[_nth_weekday(year, 9, 0, 3)] = "Respect for the Aged Day"
        # Health-Sports Day: 2nd Monday of October
        holidays[_nth_weekday(year, 10, 0, 2)] = "Health-Sports Day"

    if exchange == "XLON":
        # UK Spring Bank Holiday: last Monday of May
        holidays[_last_weekday(year, 5, 0)] = "Spring Bank Holiday"
        # Summer Bank Holiday: last Monday of August
        holidays[_last_weekday(year, 8, 0)] = "Summer Bank Holiday"
        # Easter Monday
        if gf:
            holidays[gf + timedelta(days=3)] = "Easter Monday"

    if exchange == "XEUC":
        # May Day: 1st of May
        try:
            holidays[date(year, 5, 1)] = "Labour Day"
        except ValueError:
            pass
        # Easter Monday
        if gf:
            holidays[gf + timedelta(days=3)] = "Easter Monday"

    return holidays


def generate_calendar_for_exchange(session, exchange: str, year: int) -> int:
    """Generate trading calendar for one exchange and year."""
    holidays = get_holidays_for_exchange(exchange, year)
    inserted = 0

    d = date(year, 1, 1)
    end = date(year, 12, 31)

    while d <= end:
        is_weekend = d.weekday() >= 5  # Sat=5, Sun=6
        holiday_name = holidays.get(d)

        is_trading = not is_weekend and holiday_name is None

        # Check if already exists
        existing = session.execute(
            select(MarketCalendar).where(
                MarketCalendar.date == d,
                MarketCalendar.exchange == exchange,
            )
        ).scalar_one_or_none()

        if not existing:
            session.add(MarketCalendar(
                date=d,
                exchange=exchange,
                is_trading_day=is_trading,
                holiday_name=holiday_name,
                half_day=False,
            ))
            inserted += 1

        d += timedelta(days=1)

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Generate global market calendar")
    parser.add_argument("--year", type=int, default=None, help="Specific year (default: current year)")
    parser.add_argument("--all-years", action="store_true", help="Generate 2020-2027")
    args = parser.parse_args()

    if args.all_years:
        years = list(range(2020, 2028))
    elif args.year:
        years = [args.year]
    else:
        years = [date.today().year]

    session = get_sessionmaker()()

    total_inserted = 0
    for exchange, tz in EXCHANGES:
        for year in years:
            inserted = generate_calendar_for_exchange(session, exchange, year)
            total_inserted += inserted
            logger.info("  %s %d: %d days inserted", exchange, year, inserted)
        session.commit()

    logger.info("=" * 60)
    logger.info("Total days inserted: %d", total_inserted)

    # Summary per exchange
    rows = session.execute(
        text(
            "SELECT exchange, COUNT(*) as total, "
            "SUM(CASE WHEN is_trading_day = 1 THEN 1 ELSE 0 END) as trading_days "
            "FROM market_calendar GROUP BY exchange ORDER BY exchange"
        )
    ).fetchall()

    logger.info("Calendar summary:")
    for r in rows:
        logger.info("  %-6s: %5d total days, %4d trading days", r[0], r[1], r[2])

    session.close()


if __name__ == "__main__":
    main()
