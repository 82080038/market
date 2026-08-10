#!/usr/bin/env python
"""Fetch macro/commodity data from BPS, World Bank, NOAA, yfinance.

Usage:
    ENV=paper python scripts/fetch_macro_data.py [--source all|bps|world_bank|noaa|commodity]

Integrates ``market.data.macro_data_fetcher.MacroDataFetcher`` into the
daily pipeline. Data is saved to the ``macro_data`` table in the application
database.

References:
    pustaka/97-strategi-alternatif-ekspansi-data-2026.md §4 (data satelit proxy)
    pustaka/22-data-engineering-pipeline.md §12-13
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch macro/commodity data")
    parser.add_argument(
        "--source",
        default="all",
        choices=["all", "bps", "world_bank", "noaa", "commodity"],
        help="Data source to fetch (default: all)",
    )
    args = parser.parse_args()

    from market.data.macro_data_fetcher import MacroDataFetcher

    fetcher = MacroDataFetcher()

    if args.source == "all":
        logger.info("Fetching all macro sources...")
        results = fetcher.fetch_all()
        for src, result in results.items():
            if result.success:
                logger.info("  %s: %d rows (%.1fs)", src, len(result.data), result.elapsed_seconds)
            else:
                logger.warning("  %s: FAILED — %s", src, result.error)
        combined = fetcher.fetch_all_combined()
        logger.info("Total combined: %d rows", len(combined))
    else:
        logger.info("Fetching source: %s", args.source)
        result = fetcher.fetch_source(args.source)
        if result.success:
            logger.info("  %d rows (%.1fs)", len(result.data), result.elapsed_seconds)
        else:
            logger.error("  FAILED — %s", result.error)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
