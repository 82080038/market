"""Import dataset-saham-idx CSV files into the database.

Enriches:
1. instrument_master — listing_date, listed_shares, tradeable_shares, board, sector
2. foreign_flow — daily foreign_buy/sell per ticker (2019-07-29 → 2025-02-21)

Usage:
    python scripts/import_dataset_saham_idx.py
    python scripts/import_dataset_saham_idx.py --flow-only    # skip instrument enrichment
    python scripts/import_dataset_saham_idx.py --instruments-only
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select

from market.config import settings
from market.db.engine import get_sessionmaker
from market.db.models import ForeignFlow, InstrumentMaster

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DATASET_DIR = Path(__file__).resolve().parent.parent / "data" / "dataset-saham-idx"
SAHAM_DIR = DATASET_DIR / "Saham" / "Semua"
EMITEN_CSV = DATASET_DIR / "List Emiten" / "all.csv"
SECTORS_DIR = DATASET_DIR / "List Emiten" / "Sectors"

BOARD_MAP = {
    "Utama": "Utama",
    "Pengembangan": "Pengembangan",
    "Pemantauan Khusus": "Pemantauan Khusus",
    "Akselerasi": "Akselerasi",
}


def load_sector_map() -> dict[str, str]:
    """Load sector classification from Sectors CSVs."""
    sector_map: dict[str, str] = {}
    if not SECTORS_DIR.exists():
        log.warning("Sectors directory not found: %s", SECTORS_DIR)
        return sector_map
    for csv_path in SECTORS_DIR.glob("*.csv"):
        sector_name = csv_path.stem
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get("code", "").strip()
                if code:
                    sector_map[code] = sector_name
    log.info("Loaded %d sector mappings", len(sector_map))
    return sector_map


def import_instruments(session, sector_map: dict[str, str]) -> int:
    """Enrich instrument_master with listing_date, shares, board, sector."""
    if not EMITEN_CSV.exists():
        log.error("Emiten CSV not found: %s", EMITEN_CSV)
        return 0

    updated = 0
    created = 0
    with open(EMITEN_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["code"].strip()
            ticker = f"{code}.JK"
            name = row.get("name", "").strip()
            listing_date_str = row.get("listingDate", "").strip()
            shares_str = row.get("shares", "").strip()
            board = row.get("listingBoard", "").strip()

            listing_date = None
            if listing_date_str:
                try:
                    listing_date = date.fromisoformat(listing_date_str[:10])
                except ValueError:
                    pass

            shares = float(shares_str) if shares_str else None
            sector = sector_map.get(code)

            existing = session.get(InstrumentMaster, ticker)
            if existing:
                changed = False
                if listing_date and not existing.listing_date:
                    existing.listing_date = listing_date
                    changed = True
                if shares and not existing.listed_shares:
                    existing.listed_shares = shares
                    changed = True
                if board and not existing.board:
                    existing.board = board
                    changed = True
                if sector and not existing.sector:
                    existing.sector = sector
                    changed = True
                if name and not existing.name:
                    existing.name = name
                    changed = True
                if changed:
                    updated += 1
            else:
                session.add(InstrumentMaster(
                    ticker=ticker,
                    market_mic="XIDX",
                    asset_class="equity",
                    name=name or None,
                    base_currency="IDR",
                    reporting_currency="IDR",
                    listing_date=listing_date,
                    listed_shares=shares,
                    board=board or None,
                    sector=sector,
                    is_active=True,
                ))
                created += 1

    session.commit()
    log.info("Instruments: %d updated, %d created", updated, created)
    return updated + created


def import_foreign_flow(session) -> int:
    """Import daily foreign flow from CSV files."""
    if not SAHAM_DIR.exists():
        log.error("Saham directory not found: %s", SAHAM_DIR)
        return 0

    csv_files = sorted(SAHAM_DIR.glob("*.csv"))
    log.info("Found %d CSV files in %s", len(csv_files), SAHAM_DIR)

    total_inserted = 0
    total_skipped = 0
    total_errors = 0

    for i, csv_path in enumerate(csv_files):
        code = csv_path.stem
        ticker = f"{code}.JK"

        try:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                batch_count = 0
                for row in reader:
                    date_str = row.get("date", "").strip()
                    if not date_str:
                        continue

                    try:
                        row_date = date.fromisoformat(date_str)
                    except ValueError:
                        continue

                    fb_str = row.get("foreign_buy", "").strip()
                    fs_str = row.get("foreign_sell", "").strip()

                    if not fb_str and not fs_str:
                        continue

                    fb = float(fb_str) if fb_str else None
                    fs = float(fs_str) if fs_str else None
                    fn = (fb - fs) if (fb is not None and fs is not None) else None

                    existing = session.execute(
                        select(ForeignFlow).where(
                            ForeignFlow.ticker == ticker,
                            ForeignFlow.date == row_date,
                            ForeignFlow.source == "dataset_saham_idx",
                        )
                    ).scalar_one_or_none()

                    if existing:
                        total_skipped += 1
                        continue

                    session.add(ForeignFlow(
                        ticker=ticker,
                        date=row_date,
                        foreign_buy=fb,
                        foreign_sell=fs,
                        foreign_net=fn,
                        source="dataset_saham_idx",
                    ))
                    batch_count += 1
                    total_inserted += 1

                session.commit()
            if (i + 1) % 50 == 0:
                log.info("[%d/%d] %s: +%d rows | Running: ins=%d skip=%d err=%d",
                         i + 1, len(csv_files), ticker, batch_count,
                         total_inserted, total_skipped, total_errors)
        except Exception as e:
            log.error("Error processing %s: %s", csv_path.name, e)
            total_errors += 1
            session.rollback()

    log.info("Foreign flow complete: %d inserted, %d skipped, %d errors",
             total_inserted, total_skipped, total_errors)
    return total_inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Import dataset-saham-idx to DB")
    parser.add_argument("--flow-only", action="store_true", help="Skip instrument enrichment")
    parser.add_argument("--instruments-only", action="store_true", help="Skip foreign flow import")
    args = parser.parse_args()

    log.info("Database: %s", settings.resolved_db_path)
    log.info("Dataset dir: %s", DATASET_DIR)

    if not DATASET_DIR.exists():
        log.error("Dataset directory not found: %s", DATASET_DIR)
        sys.exit(1)

    Session = get_sessionmaker()
    session = Session()

    try:
        if not args.flow_only:
            sector_map = load_sector_map()
            import_instruments(session, sector_map)

        if not args.instruments_only:
            import_foreign_flow(session)

        log.info("Import complete!")
    finally:
        session.close()


if __name__ == "__main__":
    main()
