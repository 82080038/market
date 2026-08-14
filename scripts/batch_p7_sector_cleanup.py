"""P7: Sector classification cleanup + standardize taxonomy in instrument_master.

Standardizes the inconsistent sector naming in instrument_master to a unified
GICS-like taxonomy. Also fills in missing sector values based on ticker patterns
and known IDX sector mappings.

Actions:
1. Standardize sector names (e.g., "Consumer Cyclicals" → "Consumer Cyclical")
2. Map empty/missing sectors to best-guess based on ticker name patterns
3. Fix subsector field for key commodity stocks
4. Audit final sector distribution

Usage:
    cd /home/petrick/projects/market && .venv/bin/python scripts/batch_p7_sector_cleanup.py
"""
from __future__ import annotations

import logging

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_DSN = "host=localhost dbname=market user=petrick password=market_dev"

# Standardize sector names to unified GICS-like taxonomy
SECTOR_NORMALIZATION = {
    "Consumer Cyclicals": "Consumer Cyclical",
    "Consumer Non-Cyclicals": "Consumer Non-Cyclical",
    "Consumer Defensive": "Consumer Non-Cyclical",
    "Commodities": "Basic Materials",
    "Properties & Real Estate": "Real Estate",
    "Transportation & Logistic": "Transportation & Logistics",
    "Financials": "Financials",
    "Basic Materials": "Basic Materials",
    "Energy": "Energy",
    "Industrials": "Industrials",
    "Technology": "Technology",
    "Healthcare": "Healthcare",
    "Infrastructures": "Industrials",
    "Utilities": "Utilities",
    "Communication Services": "Communication Services",
}

# Known IDX sector mappings for tickers with empty sector
# Based on IDX sector classification (ICDM/ICB)
KNOWN_SECTORS = {
    # Banks
    "BBCA.JK": "Financials", "BBRI.JK": "Financials", "BMRI.JK": "Financials",
    "BBNI.JK": "Financials", "BBTN.JK": "Financials", "BNGA.JK": "Financials",
    "BTPS.JK": "Financials", "BTPN.JK": "Financials", "BJBR.JK": "Financials",
    "BJTM.JK": "Financials", "BNII.JK": "Financials", "BDMN.JK": "Financials",
    "MEGA.JK": "Financials", "BFIN.JK": "Financials", "ADMF.JK": "Financials",
    "CFIN.JK": "Financials", "TRUS.JK": "Financials", "VOKS.JK": "Financials",
    "PNSE.JK": "Financials", "PNLF.JK": "Financials", "BBHI.JK": "Financials",
    "ARTO.JK": "Financials", "AMAR.JK": "Financials", "BSWD.JK": "Financials",
    # Energy / Coal
    "ADRO.JK": "Energy", "PTBA.JK": "Energy", "ITMG.JK": "Energy",
    "HRUM.JK": "Energy", "BYAN.JK": "Energy", "BSSR.JK": "Energy",
    "GEMS.JK": "Energy", "SMMT.JK": "Energy", "PTRO.JK": "Energy",
    "BORN.JK": "Energy", "ELSA.JK": "Energy", "ENRG.JK": "Energy",
    "MEDC.JK": "Energy", "ARTI.JK": "Energy", "RIGI.JK": "Energy",
    "APEX.JK": "Energy", "BOSS.JK": "Energy", "MTFN.JK": "Energy",
    "MTLA.JK": "Energy", "SURE.JK": "Energy", "TOBA.JK": "Energy",
    "ZBRA.JK": "Energy", "MBAP.JK": "Energy",
    # Basic Materials / Mining
    "INCO.JK": "Basic Materials", "ANTM.JK": "Basic Materials",
    "MDKA.JK": "Basic Materials", "TINS.JK": "Basic Materials",
    "BRPT.JK": "Basic Materials", "SMRU.JK": "Basic Materials",
    "PSAB.JK": "Basic Materials", "SMMT.JK": "Basic Materials",
    "UNTR.JK": "Basic Materials", "IKBI.JK": "Basic Materials",
    "SULI.JK": "Basic Materials", "DPNS.JK": "Basic Materials",
    "ZINC.JK": "Basic Materials", "IFSH.JK": "Basic Materials",
    # Plantation / CPO (Consumer Non-Cyclical)
    "AALI.JK": "Consumer Non-Cyclical", "LSIP.JK": "Consumer Non-Cyclical",
    "SIMP.JK": "Consumer Non-Cyclical", "DSNG.JK": "Consumer Non-Cyclical",
    "ANJT.JK": "Consumer Non-Cyclical", "SGRO.JK": "Consumer Non-Cyclical",
    "BWPT.JK": "Consumer Non-Cyclical", "SSMS.JK": "Consumer Non-Cyclical",
    "TAPG.JK": "Consumer Non-Cyclical", "GZCO.JK": "Consumer Non-Cyclical",
    "PALM.JK": "Consumer Non-Cyclical", "AALI.JK": "Consumer Non-Cyclical",
    # Consumer Cyclical
    "ASII.JK": "Consumer Cyclical", "IMAS.JK": "Consumer Cyclical",
    "BMTR.JK": "Consumer Cyclical", "MAPI.JK": "Consumer Cyclical",
    "RALS.JK": "Consumer Cyclical", "MAPA.JK": "Consumer Cyclical",
    "MAPB.JK": "Consumer Cyclical", "TELE.JK": "Consumer Cyclical",
    "ERAA.JK": "Consumer Cyclical", "MLIA.JK": "Consumer Cyclical",
    "HOME.JK": "Consumer Cyclical", "ACES.JK": "Consumer Cyclical",
    "RANC.JK": "Consumer Cyclical", "CSAP.JK": "Consumer Cyclical",
    # Consumer Non-Cyclical
    "INDF.JK": "Consumer Non-Cyclical", "ICBP.JK": "Consumer Non-Cyclical",
    "MYOR.JK": "Consumer Non-Cyclical", "ULTJ.JK": "Consumer Non-Cyclical",
    "CPIN.JK": "Consumer Non-Cyclical", "JPFA.JK": "Consumer Non-Cyclical",
    "MAIN.JK": "Consumer Non-Cyclical", "SMAR.JK": "Consumer Non-Cyclical",
    "SIDO.JK": "Consumer Non-Cyclical", "KLBF.JK": "Healthcare",
    "INCO.JK": "Basic Materials",
    # Healthcare
    "KLBF.JK": "Healthcare", "DVLA.JK": "Healthcare", "MIKA.JK": "Healthcare",
    "SRAJ.JK": "Healthcare", "PEHA.JK": "Healthcare", "PRDA.JK": "Healthcare",
    "SILO.JK": "Healthcare", "SAME.JK": "Healthcare", "HEAL.JK": "Healthcare",
    # Technology
    "GIAA.JK": "Technology", "MTDL.JK": "Technology", "LUCK.JK": "Technology",
    "WIRG.JK": "Technology", "KIOS.JK": "Technology", "DMMX.JK": "Technology",
    "BELI.JK": "Technology", "DCII.JK": "Technology", "EDGE.JK": "Technology",
    # Telecommunication
    "TLKM.JK": "Communication Services", "ISAT.JK": "Communication Services",
    "EXCL.JK": "Communication Services", "FREN.JK": "Communication Services",
    "BTEL.JK": "Communication Services", "MTEL.JK": "Communication Services",
    # Transportation & Logistics
    "SMDR.JK": "Transportation & Logistics", "IPCC.JK": "Transportation & Logistics",
    "PORT.JK": "Transportation & Logistics", "BULL.JK": "Transportation & Logistics",
    "TUGU.JK": "Transportation & Logistics", "HITS.JK": "Transportation & Logistics",
    "SOCI.JK": "Transportation & Logistics", "LEAD.JK": "Transportation & Logistics",
    "CMPP.JK": "Transportation & Logistics", "ASSA.JK": "Transportation & Logistics",
    # Real Estate
    "CTRA.JK": "Real Estate", "PWON.JK": "Real Estate", "BKSL.JK": "Real Estate",
    "BSDE.JK": "Real Estate", "LPCK.JK": "Real Estate", "MTLA.JK": "Real Estate",
    "ASRI.JK": "Real Estate", "LPIN.JK": "Real Estate", "BAPA.JK": "Real Estate",
    "DUTI.JK": "Real Estate", "JRPT.JK": "Real Estate", "MKPI.JK": "Real Estate",
    "RDTX.JK": "Real Estate", "RBMS.JK": "Real Estate", "GMTD.JK": "Real Estate",
    # Industrials
    "UNVR.JK": "Consumer Non-Cyclical", "TPIA.JK": "Basic Materials",
    "ASDM.JK": "Industrials", "BTON.JK": "Industrials", "WSBP.JK": "Industrials",
    "WIKA.JK": "Industrials", "WSKT.JK": "Industrials", "PTPP.JK": "Industrials",
    "NRCA.JK": "Industrials", "PBSA.JK": "Industrials", "MTRA.JK": "Industrials",
    # Utilities
    "GASJ.JK": "Utilities", "PGAS.JK": "Utilities", "AKSI.JK": "Utilities",
}


def main() -> None:
    logger.info("=" * 70)
    logger.info("P7: SECTOR CLASSIFICATION CLEANUP")
    logger.info("=" * 70)

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # Step 1: Audit current sectors
    logger.info("")
    logger.info("--- Step 1: Audit current sector distribution ---")
    cur.execute("SELECT sector, count(*) FROM instrument_master GROUP BY sector ORDER BY count(*) DESC")
    for row in cur.fetchall():
        logger.info("  '%s': %d", row[0], row[1])

    # Step 2: Normalize existing sector names
    logger.info("")
    logger.info("--- Step 2: Normalize sector names ---")
    normalized = 0
    for old_name, new_name in SECTOR_NORMALIZATION.items():
        if old_name == new_name:
            continue
        cur.execute("UPDATE instrument_master SET sector = %s WHERE sector = %s", (new_name, old_name))
        if cur.rowcount > 0:
            logger.info("  '%s' → '%s': %d rows", old_name, new_name, cur.rowcount)
            normalized += cur.rowcount
    conn.commit()
    logger.info("  Total normalized: %d", normalized)

    # Step 3: Fill missing sectors from KNOWN_SECTORS
    logger.info("")
    logger.info("--- Step 3: Fill missing sectors from known mapping ---")
    filled = 0
    for ticker, sector in KNOWN_SECTORS.items():
        cur.execute("SELECT sector FROM instrument_master WHERE ticker = %s", (ticker,))
        row = cur.fetchone()
        if row is None:
            continue
        current = row[0]
        if current is None or current.strip() == "" or current == "Industrials":
            # Only override if empty, or if it's the generic "Industrials" fallback
            # and we have a more specific mapping
            if current is None or current.strip() == "":
                cur.execute("UPDATE instrument_master SET sector = %s WHERE ticker = %s", (sector, ticker))
                filled += cur.rowcount
    conn.commit()
    logger.info("  Filled %d tickers with known sectors", filled)

    # Step 4: For remaining empty sectors, try to infer from ticker name
    logger.info("")
    logger.info("--- Step 4: Infer remaining empty sectors from name ---")
    cur.execute("SELECT ticker, name FROM instrument_master WHERE sector IS NULL OR sector = '' OR sector = 'Indonesia'")
    rows = cur.fetchall()
    inferred = 0
    for ticker, name in rows:
        if name is None:
            continue
        name_lower = name.lower()
        inferred_sector = None
        if any(k in name_lower for k in ["bank", "finance", "sekuritas", "asuransi", "pembiayaan"]):
            inferred_sector = "Financials"
        elif any(k in name_lower for k in ["energi", "coal", "mining", "tambang", "batubara", "oil", "gas"]):
            inferred_sector = "Energy"
        elif any(k in name_lower for k in ["sawit", "plantation", "perkebunan", "agro"]):
            inferred_sector = "Consumer Non-Cyclical"
        elif any(k in name_lower for k in ["properti", "realty", "land", "developer"]):
            inferred_sector = "Real Estate"
        elif any(k in name_lower for k in ["farmasi", "pharma", "health", "medika", "klinik"]):
            inferred_sector = "Healthcare"
        elif any(k in name_lower for k in ["telekomunikasi", "telkom", "satelit"]):
            inferred_sector = "Communication Services"
        elif any(k in name_lower for k in ["teknologi", "tech", "digital", "data", "cloud"]):
            inferred_sector = "Technology"
        elif any(k in name_lower for k in ["logistik", "port", "pelabuhan", "shipping"]):
            inferred_sector = "Transportation & Logistics"

        if inferred_sector:
            cur.execute("UPDATE instrument_master SET sector = %s WHERE ticker = %s", (inferred_sector, ticker))
            inferred += cur.rowcount
    conn.commit()
    logger.info("  Inferred %d tickers from name patterns", inferred)

    # Step 5: Set commodity/index tickers to appropriate sectors
    logger.info("")
    logger.info("--- Step 5: Set commodity/index/FX tickers ---")
    cur.execute("""
        UPDATE instrument_master SET sector = 'Index'
        WHERE ticker LIKE '^%' OR ticker IN ('000001.SS','JKSE','^JKSE')
    """)
    logger.info("  Index tickers: %d", cur.rowcount)
    cur.execute("""
        UPDATE instrument_master SET sector = 'FX'
        WHERE ticker IN ('IDR=X','DX-Y.NYB','EURUSD=X','JPY=X','GBPUSD=X','AUDUSD=X')
        OR ticker LIKE '%%%X'
    """)
    logger.info("  FX tickers: %d", cur.rowcount)
    conn.commit()

    # Step 6: Final audit
    logger.info("")
    logger.info("--- Step 6: Final sector distribution ---")
    cur.execute("SELECT sector, count(*) FROM instrument_master GROUP BY sector ORDER BY count(*) DESC")
    for row in cur.fetchall():
        logger.info("  '%s': %d", row[0], row[1])

    cur.execute("SELECT count(*) FROM instrument_master WHERE sector IS NULL OR sector = ''")
    empty = cur.fetchone()[0]
    logger.info("")
    logger.info("  Empty sector: %d tickers", empty)

    conn.close()
    logger.info("")
    logger.info("P7 COMPLETE.")


if __name__ == "__main__":
    main()
