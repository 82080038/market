"""Populate index_category, region, and sector for all instruments.

Classification scheme:
  index_category: composite | sectoral | sharia | esg | factor | board |
                  global | volatility | rate | currency | broad_market
  region: ID | US | EU | AS | CN | GLOBAL

Also sets sector for sectoral indices (maps to equity sector names).

Usage:
    DATABASE_URL=postgresql://petrick:market_dev@localhost:5433/market python scripts/classify_instruments.py
"""

from __future__ import annotations

import logging
import sys

from market.config import settings
from market.db.engine import get_sessionmaker
from market.db.models import InstrumentMaster

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── Index classification ─────────────────────────────────────────────────

# (ticker, index_category, region, sector_or_None)
INDEX_CLASSIFICATION: dict[str, tuple[str, str, str | None]] = {
    # IDX Composite / Broad Market
    "^JKSE": ("composite", "ID", None),
    "^JKLQ45": ("broad_market", "ID", None),
    "KOMPAS100.JK": ("broad_market", "ID", None),
    "BISNIS27.JK": ("broad_market", "ID", None),
    "MNC36.JK": ("broad_market", "ID", None),
    "INVESTOR33.JK": ("broad_market", "ID", None),
    "PEFINDO25.JK": ("broad_market", "ID", None),
    "IDXSMCCOM.JK": ("broad_market", "ID", None),
    "IDXSMCLIQ.JK": ("broad_market", "ID", None),
    "IGRADE.JK": ("broad_market", "ID", None),

    # IDX Sectoral
    "IDXENERGY.JK": ("sectoral", "ID", "Energy"),
    "IDXBASIC.JK": ("sectoral", "ID", "Basic Materials"),
    "IDXINDUST.JK": ("sectoral", "ID", "Industrials"),
    "IDXNONCYC.JK": ("sectoral", "ID", "Consumer Non-Cyclicals"),
    "IDXCYCLIC.JK": ("sectoral", "ID", "Consumer Cyclicals"),
    "IDXHEALTH.JK": ("sectoral", "ID", "Healthcare"),
    "IDXFINANCE.JK": ("sectoral", "ID", "Financials"),
    "IDXPROPER.JK": ("sectoral", "ID", "Properties & Real Estate"),
    "IDXTECHNO.JK": ("sectoral", "ID", "Technology"),
    "IDXINFRA.JK": ("sectoral", "ID", "Infrastructures"),
    "IDXTRANS.JK": ("sectoral", "ID", "Transportation & Logistic"),

    # IDX Size/Style
    "IDX30.JK": ("factor", "ID", None),
    "IDX80.JK": ("factor", "ID", None),
    "IDXV30.JK": ("factor", "ID", None),
    "IDXG30.JK": ("factor", "ID", None),
    "IDXQ30.JK": ("factor", "ID", None),
    "IDXHIDIV20.JK": ("factor", "ID", None),
    "IDXBUMN20.JK": ("factor", "ID", None),
    "IDXMESBUMN.JK": ("factor", "ID", None),
    "IDXCYCLIC30.JK": ("factor", "ID", None),
    "IDXVESTA28.JK": ("factor", "ID", None),

    # IDX Sharia
    "IDXJII.JK": ("sharia", "ID", None),
    "JII70.JK": ("sharia", "ID", None),
    "ISSI.JK": ("sharia", "ID", None),
    "IDXSHAGROW.JK": ("sharia", "ID", None),

    # IDX ESG
    "ESGQKEHATI.JK": ("esg", "ID", None),
    "ESGSKEHATI.JK": ("esg", "ID", None),
    "IDXESGL.JK": ("esg", "ID", None),
    "IDXLQ45LCL.JK": ("esg", "ID", None),
    "SRIKEHATI.JK": ("esg", "ID", None),

    # IDX Board
    "MBX.JK": ("board", "ID", None),
    "DBX.JK": ("board", "ID", None),
    "ABX.JK": ("board", "ID", None),

    # IDX Thematic
    "INFOBANK15.JK": ("factor", "ID", "Financials"),
    "PRIMBANK10.JK": ("factor", "ID", "Financials"),
    "SMINFRA18.JK": ("factor", "ID", "Infrastructures"),

    # Global indices
    "^GSPC": ("global", "US", None),
    "^IXIC": ("global", "US", None),
    "^DJI": ("global", "US", None),
    "^VIX": ("volatility", "US", None),
    "^TNX": ("rate", "US", None),
    "^FTSE": ("global", "EU", None),
    "^GDAXI": ("global", "EU", None),
    "^HSI": ("global", "AS", None),
    "^N225": ("global", "AS", None),
    "000001.SS": ("global", "CN", None),
    "DX-Y.NYB": ("currency", "GLOBAL", None),
}

# ── Region mapping by market_mic ─────────────────────────────────────────

MARKET_REGION: dict[str, str] = {
    "XIDX": "ID",
    "XNYS": "US",
    "XNAS": "US",
    "XCEC": "US",  # CME/COMEX commodities
    "XFXS": "GLOBAL",  # FX
    "XSHG": "CN",
    "XTSE": "AS",  # Japan
    "XHKG": "AS",  # Hong Kong
    "XLON": "EU",
    "XFRA": "EU",
}


def main() -> None:
    log.info("Database: %s", settings.resolved_db_path)

    Session = get_sessionmaker()
    session = Session()

    try:
        # 1. Classify indices
        index_updated = 0
        for ticker, (cat, region, sector) in INDEX_CLASSIFICATION.items():
            inst = session.get(InstrumentMaster, ticker)
            if not inst:
                log.warning("Ticker not found: %s", ticker)
                continue

            changed = False
            if inst.index_category != cat:
                inst.index_category = cat
                changed = True
            if inst.region != region:
                inst.region = region
                changed = True
            if sector and inst.sector != sector:
                inst.sector = sector
                changed = True

            if changed:
                index_updated += 1

        session.commit()
        log.info("Indices classified: %d updated", index_updated)

        # 2. Set region for all instruments based on market_mic
        all_inst = session.query(InstrumentMaster).all()
        region_updated = 0
        for inst in all_inst:
            if inst.region:
                continue  # Already set (indices above)
            region = MARKET_REGION.get(inst.market_mic)
            if region:
                inst.region = region
                region_updated += 1

        session.commit()
        log.info("Regions set for non-index instruments: %d updated", region_updated)

        # 3. Summary
        from sqlalchemy import func, select

        # By index_category
        rows = session.execute(
            select(InstrumentMaster.index_category, func.count())
            .where(InstrumentMaster.asset_class == "index")
            .group_by(InstrumentMaster.index_category)
            .order_by(func.count().desc())
        ).all()
        log.info("\n=== Index category distribution ===")
        for cat, cnt in rows:
            log.info("  %s: %d", cat or "NULL", cnt)

        # By region
        rows = session.execute(
            select(InstrumentMaster.region, func.count())
            .group_by(InstrumentMaster.region)
            .order_by(func.count().desc())
        ).all()
        log.info("\n=== Region distribution (all instruments) ===")
        for reg, cnt in rows:
            log.info("  %s: %d", reg or "NULL", cnt)

        # By asset_class + region
        rows = session.execute(
            select(InstrumentMaster.asset_class, InstrumentMaster.region, func.count())
            .group_by(InstrumentMaster.asset_class, InstrumentMaster.region)
            .order_by(InstrumentMaster.asset_class, func.count().desc())
        ).all()
        log.info("\n=== Asset class × Region ===")
        for ac, reg, cnt in rows:
            log.info("  %s × %s: %d", ac, reg or "NULL", cnt)

        # Sectoral indices with sector
        rows = session.execute(
            select(InstrumentMaster.ticker, InstrumentMaster.name, InstrumentMaster.sector)
            .where(InstrumentMaster.index_category == "sectoral")
            .order_by(InstrumentMaster.ticker)
        ).all()
        log.info("\n=== Sectoral indices with sector ===")
        for t, n, s in rows:
            log.info("  %s: %s → %s", t, n, s)

    finally:
        session.close()


if __name__ == "__main__":
    main()
