#!/usr/bin/env python3
"""CLI wrapper for satellite data fetching.

Fetches satellite data (NASA POWER + Sentinel-2 NDVI) and persists
to the database (SQLite or PostgreSQL based on .env configuration).

Location resolution:
  1. satellite_ticker_locations table (explicit per-ticker mapping)
  2. SECTOR_FALLBACK_LOCATIONS (sector-based global defaults)

Usage:
  # Fetch for all DB-configured tickers
  uv run python scripts/fetch_satellite_data.py

  # Fetch for specific ticker (uses DB mapping or sector fallback)
  uv run python scripts/fetch_satellite_data.py --ticker AALI.JK --sector agriculture
  uv run python scripts/fetch_satellite_data.py --ticker ZC=F --sector agriculture

  # Fetch for arbitrary location (any lat/lon on Earth)
  uv run python scripts/fetch_satellite_data.py --lat -13.0 --lon -56.0 --name Brazil_Soybean

  # Seed initial ticker-location mappings
  uv run python scripts/fetch_satellite_data.py --seed

  # Fetch for multiple tickers from watchlist
  uv run python scripts/fetch_satellite_data.py --from-watchlist
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from market.config import settings
from market.data.satellite_fetcher import (
    SECTOR_FALLBACK_LOCATIONS,
    SatelliteFetcher,
    seed_ticker_locations,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("fetch_satellite")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch satellite data for market correlation (global coverage)",
    )
    parser.add_argument("--years", type=int, default=2, help="Years of historical data")
    parser.add_argument("--ticker", type=str, default=None, help="Specific ticker to fetch")
    parser.add_argument("--sector", type=str, default=None,
                        help="Sector for fallback mapping (e.g., agriculture, energy, mining, shipping)")
    parser.add_argument("--lat", type=float, default=None, help="Arbitrary latitude (-90 to 90)")
    parser.add_argument("--lon", type=float, default=None, help="Arbitrary longitude (-180 to 180)")
    parser.add_argument("--name", type=str, default=None, help="Location name for arbitrary coordinates")
    parser.add_argument("--metrics", type=str, default=None,
                        help="Comma-separated metrics (default: all significant)")
    parser.add_argument("--seed", action="store_true", help="Seed initial ticker-location mappings")
    parser.add_argument("--from-watchlist", action="store_true",
                        help="Fetch for all tickers in watchlist table")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't persist to DB")
    args = parser.parse_args()

    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=args.years * 365)

    logger.info("Satellite data fetcher — period: %s → %s", start_date, end_date)
    logger.info("Database: %s", settings.resolved_database_url)

    if args.dry_run:
        fetcher = SatelliteFetcher(start_date=start_date, end_date=end_date)
        # Without session, data won't be persisted
        if args.lat is not None and args.lon is not None:
            loc_name = args.name or f"Custom_{args.lat}_{args.lon}"
            metrics = args.metrics.split(",") if args.metrics else ["NDVI", "T2M", "PRECTOTCORR", "RH2M", "ALLSKY_SFC_SW_DWN"]
            count = fetcher.fetch_location(loc_name, args.lat, args.lon, metrics)
            logger.info("Dry run: %d observations for %s (not persisted)", count, loc_name)
        return 0

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(settings.resolved_database_url)
    with Session(engine) as session:
        fetcher = SatelliteFetcher(
            session=session,
            start_date=start_date,
            end_date=end_date,
        )

        if args.seed:
            count = seed_ticker_locations(session)
            session.commit()
            logger.info("Seeded %d ticker-location mappings", count)
            return 0

        if args.lat is not None and args.lon is not None:
            # Arbitrary location — any point on Earth
            loc_name = args.name or f"Custom_{args.lat}_{args.lon}"
            metrics = args.metrics.split(",") if args.metrics else [
                "NDVI", "T2M", "PRECTOTCORR", "RH2M", "ALLSKY_SFC_SW_DWN",
            ]
            count = fetcher.fetch_location(loc_name, args.lat, args.lon, metrics)
            logger.info("Location %s: %d observations persisted", loc_name, count)

        elif args.ticker:
            # Specific ticker — uses DB mapping or sector fallback
            count = fetcher.fetch_for_ticker(args.ticker, args.sector)
            logger.info("Ticker %s: %d observations persisted", args.ticker, count)

        elif args.from_watchlist:
            # Fetch for all tickers in watchlist
            from market.db.models import Watchlist
            rows = session.query(Watchlist).all()
            tickers = [(r.ticker, None) for r in rows]
            # Try to get sector from InstrumentMaster
            from market.db.models import InstrumentMaster
            ticker_sectors: list[tuple[str, str | None]] = []
            for ticker, _ in tickers:
                inst = session.query(InstrumentMaster).filter(
                    InstrumentMaster.ticker == ticker,
                ).first()
                sector = inst.sector if inst else None
                ticker_sectors.append((ticker, sector))

            logger.info("Fetching for %d watchlist tickers", len(ticker_sectors))
            total = fetcher.fetch_for_tickers(ticker_sectors)
            logger.info("Watchlist: %d total observations persisted", total)

        else:
            # Default: fetch all DB-configured locations
            total = fetcher.fetch_all_configured()
            logger.info("All configured locations: %d total observations persisted", total)

        session.commit()

    logger.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
