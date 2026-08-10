"""Classify instrument_master into 4 ML-ready segments + commodity-driven subsectors.

Segments (asset_class column):
  EQUITY_INDIVIDUAL  — .JK suffix, operational stocks (was "equity")
  INDEX_COMPOSITE    — ^ prefix indices + IDX API indices (was "index")
  COMMODITY_FUTURES  — =F suffix futures (was "commodity")
  VOLATILITY_RATE    — ^VIX, ^TNX, DX-Y.NYB (macro/volatility/rate)

Commodity-driven subsectors:
  Energy-Coal, Energy-Oil&Gas, Energy-Power, Energy-Other
  Materials-Nickel, Materials-Gold, Materials-Steel, Materials-Cement,
  Materials-Aluminum, Materials-Tin, Materials-Chemicals, Materials-Pulp&Paper,
  Materials-Plastics, Materials-Other
  Agri-PalmOil (for Consumer Non-Cyclicals plantation companies)

Usage:
    python scripts/classify_instruments_v2.py [--db data/market_research.db] [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Ticker patterns ────────────────────────────────────────────────────────

VOLATILITY_RATE_TICKERS = {"^VIX", "^TNX", "DX-Y.NYB"}

# ── Commodity-driven subsector mapping ─────────────────────────────────────
# Explicit mapping for well-known commodity-driven companies

COMMODITY_SUBSECTOR_MAP: dict[str, str] = {
    # Energy-Coal
    "ADRO.JK": "Energy-Coal", "PTBA.JK": "Energy-Coal", "ITMG.JK": "Energy-Coal",
    "BUMI.JK": "Energy-Coal", "HRUM.JK": "Energy-Coal", "TOBA.JK": "Energy-Coal",
    "SMMT.JK": "Energy-Coal", "MYOH.JK": "Energy-Coal", "MBAP.JK": "Energy-Coal",
    "BSSR.JK": "Energy-Coal", "BSML.JK": "Energy-Coal", "GEMS.JK": "Energy-Coal",
    "SRAJ.JK": "Energy-Coal", "TOPS.JK": "Energy-Coal", "ELTY.JK": "Energy-Coal",
    "DSSA.JK": "Energy-Coal", "AADI.JK": "Energy-Coal", "ABMM.JK": "Energy-Coal",
    "ADMR.JK": "Energy-Coal", "ARII.JK": "Energy-Coal", "ATLA.JK": "Energy-Coal",
    "BBRM.JK": "Energy-Coal", "BESS.JK": "Energy-Coal", "BIPI.JK": "Energy-Coal",
    "BOAT.JK": "Energy-Coal", "BOSS.JK": "Energy-Coal", "BULL.JK": "Energy-Coal",
    "KKGI.JK": "Energy-Coal", "MTFN.JK": "Energy-Coal", "SGER.JK": "Energy-Coal",
    "WOWS.JK": "Energy-Coal", "TEBE.JK": "Energy-Coal", "TPMA.JK": "Energy-Coal",
    "TRAM.JK": "Energy-Coal", "UNIQ.JK": "Energy-Coal", "RMKE.JK": "Energy-Coal",
    "RMKO.JK": "Energy-Coal", "MCOL.JK": "Energy-Coal", "ITMA.JK": "Energy-Coal",
    "KOPI.JK": "Energy-Coal", "JSKY.JK": "Energy-Coal", "HILL.JK": "Energy-Coal",
    "GTSI.JK": "Energy-Coal", "MAHA.JK": "Energy-Coal", "PKPK.JK": "Energy-Coal",
    "PTIS.JK": "Energy-Coal", "SEMA.JK": "Energy-Coal", "SICO.JK": "Energy-Coal",
    "SUNI.JK": "Energy-Coal", "SURE.JK": "Energy-Coal", "TAMU.JK": "Energy-Coal",
    "TCPI.JK": "Energy-Coal", "SHIP.JK": "Energy-Coal", "MBSS.JK": "Energy-Coal",
    "PSSI.JK": "Energy-Coal", "LEAD.JK": "Energy-Coal", "HUMI.JK": "Energy-Coal",
    "HITS.JK": "Energy-Coal", "IATA.JK": "Energy-Coal", "INDY.JK": "Energy-Coal",
    "INPS.JK": "Energy-Coal", "MKAP.JK": "Energy-Coal", "RATU.JK": "Energy-Coal",
    "RGAS.JK": "Energy-Coal", "SMRU.JK": "Energy-Coal", "SOCI.JK": "Energy-Coal",
    "SUGI.JK": "Energy-Coal", "PTRO.JK": "Energy-Coal", "ATPK.JK": "Energy-Coal",
    "MERQ.JK": "Energy-Coal", "PCLE.JK": "Energy-Coal", "PTSP.JK": "Energy-Coal",
    "RUIS.JK": "Energy-Coal", "TBMS.JK": "Energy-Coal", "TPSI.JK": "Energy-Coal",
    "WINS.JK": "Energy-Coal", "ZINC.JK": "Energy-Coal", "DAMI.JK": "Energy-Coal",
    "ENZO.JK": "Energy-Coal", "GTBO.JK": "Energy-Coal", "MTRA.JK": "Energy-Coal",
    "ARTI.JK": "Energy-Coal", "ALII.JK": "Energy-Coal", "AKRA.JK": "Energy-Coal",

    # Energy-Oil&Gas
    "MEDC.JK": "Energy-Oil&Gas", "ENRG.JK": "Energy-Oil&Gas",
    "ELSA.JK": "Energy-Oil&Gas", "OASA.JK": "Energy-Oil&Gas",
    "RIGS.JK": "Energy-Oil&Gas", "MOLI.JK": "Energy-Oil&Gas",
    "OILS.JK": "Energy-Oil&Gas", "PHEX.JK": "Energy-Oil&Gas",
    "AKPL.JK": "Energy-Oil&Gas", "APEX.JK": "Energy-Oil&Gas",
    "PGAS.JK": "Energy-Oil&Gas", "EMRG.JK": "Energy-Oil&Gas",
    "RAJA.JK": "Energy-Oil&Gas", "SBNR.JK": "Energy-Oil&Gas",

    # Energy-Power
    "PGUN.JK": "Energy-Power", "PWON.JK": "Energy-Power",
    "MSRU.JK": "Energy-Power", "MTPS.JK": "Energy-Power",
    "ENRG.JK": "Energy-Power", "JKSW.JK": "Energy-Power",
    "SOLA.JK": "Energy-Power", "NUSA.JK": "Energy-Power",

    # Materials-Nickel
    "INCO.JK": "Materials-Nickel", "NCKL.JK": "Materials-Nickel",
    "MDKA.JK": "Materials-Nickel", "BRMS.JK": "Materials-Nickel",
    "AYLS.JK": "Materials-Nickel", "IFSH.JK": "Materials-Nickel",
    "GPCC.JK": "Materials-Nickel", "HRTA.JK": "Materials-Nickel",
    "PSDN.JK": "Materials-Nickel", "DKFT.JK": "Materials-Nickel",
    "MBMA.JK": "Materials-Nickel", "NICL.JK": "Materials-Nickel",
    "AMMN.JK": "Materials-Nickel", "DAAZ.JK": "Materials-Nickel",

    # Materials-Gold
    "ANTM.JK": "Materials-Nickel&Gold", "ARCI.JK": "Materials-Gold",
    "EMAS.JK": "Materials-Gold", "MDKI.JK": "Materials-Gold",
    "PSAB.JK": "Materials-Gold", "OKAS.JK": "Materials-Gold",
    "SQMI.JK": "Materials-Gold", "PURE.JK": "Materials-Gold",
    "TIRT.JK": "Materials-Gold", "SIMA.JK": "Materials-Gold",
    "DGWG.JK": "Materials-Gold",

    # Materials-Steel
    "KRAS.JK": "Materials-Steel", "ISSP.JK": "Materials-Steel",
    "BAJA.JK": "Materials-Steel", "GDST.JK": "Materials-Steel",
    "GGRP.JK": "Materials-Steel", "JPRS.JK": "Materials-Steel",
    "HKMU.JK": "Materials-Steel", "INTD.JK": "Materials-Steel",
    "BTON.JK": "Materials-Steel", "OPMS.JK": "Materials-Steel",
    "TBMS.JK": "Materials-Steel",

    # Materials-Cement
    "SMGR.JK": "Materials-Cement", "INTP.JK": "Materials-Cement",
    "SMCB.JK": "Materials-Cement", "SMBR.JK": "Materials-Cement",
    "CMNT.JK": "Materials-Cement", "WSBP.JK": "Materials-Cement",
    "WTON.JK": "Materials-Cement",

    # Materials-Aluminum
    "ALMI.JK": "Materials-Aluminum", "INAI.JK": "Materials-Aluminum",

    # Materials-Tin
    "TINS.JK": "Materials-Tin", "NIKL.JK": "Materials-Tin",
    "TBMS.JK": "Materials-Tin",

    # Materials-Chemicals
    "TPIA.JK": "Materials-Chemicals", "FPNI.JK": "Materials-Chemicals",
    "ESSA.JK": "Materials-Chemicals", "LTLS.JK": "Materials-Chemicals",
    "CHEM.JK": "Materials-Chemicals", "IGAR.JK": "Materials-Chemicals",
    "UNIC.JK": "Materials-Chemicals", "OBMD.JK": "Materials-Chemicals",
    "INCI.JK": "Materials-Chemicals", "TDPM.JK": "Materials-Chemicals",
    "SRSN.JK": "Materials-Chemicals", "SBMA.JK": "Materials-Chemicals",
    "SULI.JK": "Materials-Chemicals", "SWAT.JK": "Materials-Chemicals",
    "EKAD.JK": "Materials-Chemicals",

    # Materials-Pulp&Paper
    "INKP.JK": "Materials-Pulp&Paper", "INRU.JK": "Materials-Pulp&Paper",
    "TKIM.JK": "Materials-Pulp&Paper", "IPOL.JK": "Materials-Pulp&Paper",
    "PPRI.JK": "Materials-Pulp&Paper", "SPMA.JK": "Materials-Pulp&Paper",
    "KBRI.JK": "Materials-Pulp&Paper", "KDSI.JK": "Materials-Pulp&Paper",
    "IFII.JK": "Materials-Pulp&Paper", "FWCT.JK": "Materials-Pulp&Paper",
    "KAYU.JK": "Materials-Pulp&Paper",

    # Materials-Plastics
    "ADMG.JK": "Materials-Plastics", "APLI.JK": "Materials-Plastics",
    "AVIA.JK": "Materials-Plastics", "CLPI.JK": "Materials-Plastics",
    "EPAC.JK": "Materials-Plastics", "ESIP.JK": "Materials-Plastics",
    "FASW.JK": "Materials-Plastics", "KMTR.JK": "Materials-Plastics",
    "PACK.JK": "Materials-Plastics", "PBID.JK": "Materials-Plastics",
    "PDPP.JK": "Materials-Plastics", "PICO.JK": "Materials-Plastics",
    "SMKL.JK": "Materials-Plastics", "TALF.JK": "Materials-Plastics",
    "TRST.JK": "Materials-Plastics", "BRNA.JK": "Materials-Plastics",
    "AKPI.JK": "Materials-Plastics", "ALDO.JK": "Materials-Plastics",

    # Materials-Other
    "ALKA.JK": "Materials-Other", "BATR.JK": "Materials-Other",
    "BEBS.JK": "Materials-Other", "BLES.JK": "Materials-Other",
    "BMSR.JK": "Materials-Other", "BRPT.JK": "Materials-Other",
    "CITA.JK": "Materials-Other", "CTBN.JK": "Materials-Other",
    "ETWA.JK": "Materials-Other", "LMSH.JK": "Materials-Other",
    "MINE.JK": "Materials-Other", "NAIK.JK": "Materials-Other",
    "NICE.JK": "Materials-Other", "NPGF.JK": "Materials-Other",
    "SAMF.JK": "Materials-Other", "SMGA.JK": "Materials-Other",
    "SMLE.JK": "Materials-Other", "SOLI.JK": "Materials-Other",
    "SMKL.JK": "Materials-Other",

    # Agri-PalmOil (Consumer Non-Cyclicals plantation)
    "BWPT.JK": "Agri-PalmOil", "CSRA.JK": "Agri-PalmOil",
    "GOLL.JK": "Agri-PalmOil", "GZCO.JK": "Agri-PalmOil",
    "MAGP.JK": "Agri-PalmOil", "NSSS.JK": "Agri-PalmOil",
    "PSGO.JK": "Agri-PalmOil", "SSMS.JK": "Agri-PalmOil",
    "UNSP.JK": "Agri-PalmOil", "AALI.JK": "Agri-PalmOil",
    "SIMP.JK": "Agri-PalmOil", "LSIP.JK": "Agri-PalmOil",
    "SGRO.JK": "Agri-PalmOil", "ANJT.JK": "Agri-PalmOil",
    "TAPG.JK": "Agri-PalmOil", "MDLT.JK": "Agri-PalmOil",
}


def classify_asset_class(ticker: str, current_asset_class: str) -> str:
    """Classify ticker into one of 4 ML-ready segments.

    Args:
        ticker: Instrument ticker symbol.
        current_asset_class: Current asset_class value.

    Returns:
        One of: EQUITY_INDIVIDUAL, INDEX_COMPOSITE, COMMODITY_FUTURES, VOLATILITY_RATE
    """
    # VOLATILITY_RATE: specific macro/volatility tickers
    if ticker in VOLATILITY_RATE_TICKERS:
        return "VOLATILITY_RATE"

    # COMMODITY_FUTURES: futures contracts (=F suffix)
    if ticker.endswith("=F") or current_asset_class == "commodity":
        return "COMMODITY_FUTURES"

    # INDEX_COMPOSITE: ^ prefix or currently classified as index
    if ticker.startswith("^") or current_asset_class == "index":
        return "INDEX_COMPOSITE"

    # EQUITY_INDIVIDUAL: .JK suffix equities
    if ticker.endswith(".JK") and current_asset_class == "equity":
        return "EQUITY_INDIVIDUAL"

    # ETFs and FX: keep as-is (not part of 4 ML segments)
    if current_asset_class in ("etf", "fx", "fund"):
        return current_asset_class

    # Default: if it ends with .JK, treat as equity
    if ticker.endswith(".JK"):
        return "EQUITY_INDIVIDUAL"

    # Fallback: keep current
    return current_asset_class


def classify_subsector(ticker: str, sector: str, name: str, current_subsector: str) -> str:
    """Classify subsector using commodity-driven labels.

    Uses explicit mapping first, then name-based heuristics.

    Args:
        ticker: Instrument ticker.
        sector: Current sector value.
        name: Company name.
        current_subsector: Current subsector value.

    Returns:
        Commodity-driven subsector label.
    """
    # 1. Explicit mapping takes priority
    if ticker in COMMODITY_SUBSECTOR_MAP:
        return COMMODITY_SUBSECTOR_MAP[ticker]

    # 2. Name-based heuristics for Energy sector
    if sector == "Energy":
        name_lower = (name or "").lower()
        if any(k in name_lower for k in ["tambang", "coal", "batubara", "mining"]):
            return "Energy-Coal"
        if any(k in name_lower for k in ["gas", "oil", "minyak", "petro"]):
            return "Energy-Oil&Gas"
        if any(k in name_lower for k in ["power", "listrik", "electric", "energi"]):
            return "Energy-Power"
        return "Energy-Other"

    # 3. Name-based heuristics for Basic Materials sector
    if sector == "Basic Materials":
        name_lower = (name or "").lower()
        if any(k in name_lower for k in ["nickel", "nikel", "tembaga"]):
            return "Materials-Nickel"
        if any(k in name_lower for k in ["gold", "emas", "perak", "silver"]):
            return "Materials-Gold"
        if any(k in name_lower for k in ["steel", "baja", "iron", "besi"]):
            return "Materials-Steel"
        if any(k in name_lower for k in ["semen", "cement", "concrete", "beton"]):
            return "Materials-Cement"
        if any(k in name_lower for k in ["alumunium", "aluminum", "aluminium"]):
            return "Materials-Aluminum"
        if any(k in name_lower for k in ["timah", "tin"]):
            return "Materials-Tin"
        if any(k in name_lower for k in ["chemical", "kimia", "gas industry"]):
            return "Materials-Chemicals"
        if any(k in name_lower for k in ["pulp", "paper", "kertas", "timber", "kayu"]):
            return "Materials-Pulp&Paper"
        if any(k in name_lower for k in ["plastik", "plastic", "poly", "pack"]):
            return "Materials-Plastics"
        return "Materials-Other"

    # 4. Palm oil / plantation for Consumer Non-Cyclicals
    if sector == "Consumer Non-Cyclicals":
        name_lower = (name or "").lower()
        if any(k in name_lower for k in ["sawit", "palm", "plantation", "perkebunan"]):
            return "Agri-PalmOil"

    # 5. Keep existing subsector if not commodity-driven
    return current_subsector or ""


def run_classification(db_path: str, dry_run: bool = False) -> None:
    """Run the classification on the database.

    Args:
        db_path: Path to SQLite database.
        dry_run: If True, only print stats without updating DB.
    """
    conn = sqlite3.connect(db_path)

    rows = conn.execute(
        "SELECT ticker, asset_class, sector, subsector, name FROM instrument_master"
    ).fetchall()

    stats: dict[str, int] = {}
    subsector_changes = 0
    updates: list[tuple[str, str, str, str]] = []

    for ticker, old_ac, sector, old_sub, name in rows:
        new_ac = classify_asset_class(ticker, old_ac)
        new_sub = classify_subsector(ticker, sector or "", name or "", old_sub or "")

        stats[new_ac] = stats.get(new_ac, 0) + 1

        if new_ac != old_ac or new_sub != (old_sub or ""):
            updates.append((new_ac, new_sub, ticker, old_ac))
            if new_sub != (old_sub or ""):
                subsector_changes += 1

    logger.info("Classification results:")
    for ac, count in sorted(stats.items(), key=lambda x: -x[1]):
        logger.info("  %s: %d", ac, count)

    logger.info("Total rows needing update: %d (asset_class changes + %d subsector changes)",
                len(updates), subsector_changes)

    if dry_run:
        logger.info("DRY RUN — no changes written.")
        # Show sample changes
        for new_ac, new_sub, ticker, old_ac in updates[:20]:
            logger.info("  %s: %s → %s, subsector → %s", ticker, old_ac, new_ac, new_sub)
        if len(updates) > 20:
            logger.info("  ... and %d more", len(updates) - 20)
    else:
        for new_ac, new_sub, ticker, old_ac in updates:
            conn.execute(
                "UPDATE instrument_master SET asset_class=?, subsector=? WHERE ticker=?",
                (new_ac, new_sub, ticker),
            )
        conn.commit()
        logger.info("Updated %d rows in instrument_master.", len(updates))

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify instruments into 4 ML-ready segments")
    parser.add_argument("--db", default="data/market_research.db", help="Database path")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without updating DB")
    args = parser.parse_args()

    logger.info("Database: %s", args.db)
    logger.info("Dry run: %s", args.dry_run)
    run_classification(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
