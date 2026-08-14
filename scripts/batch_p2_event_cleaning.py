"""P2: Clean external_events from noise + verify policy_event_scorer works.

The external_events table contains 119 rows but many are non-market-relevant
(dating retreats, murder cases, typhoon evacuations). This script:
1. Filters out noise events (keeps only: geopolitical conflict, trade war,
   pandemic, major natural disasters, monetary policy, elections)
2. Re-categorizes events with proper impact levels
3. Tests the PolicyEventScorer with PostgreSQL backend
4. Computes event signal for sample tickers

Usage:
    cd /home/petrick/projects/market && .venv/bin/python scripts/batch_p2_event_cleaning.py
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_DSN = "host=localhost dbname=market user=petrick password=market_dev"

# Keywords that indicate market-relevant events
MARKET_RELEVANT_KEYWORDS = [
    # Geopolitical conflict
    "war", "invasion", "missile", "airstrike", "nuclear", "sanction",
    "tariff", "trade war", "embargo", "conflict", "ceasefire",
    "geopolitical", "diplomatic", "ambassador", "treaty",
    # Economic/monetary
    "rate cut", "rate hike", "interest rate", "fed", "central bank",
    "inflation", "recession", "gdp", "stimulus", "quantitative easing",
    "bailout", "default", "currency crisis", "devaluation",
    # Pandemic/health
    "pandemic", "covid", "outbreak", "epidemic", "vaccine", "lockdown",
    "variant", "coronavirus", "who declares",
    # Natural disasters (major only)
    "earthquake", "tsunami", "volcanic", "hurricane", "cyclone",
    "flood", "drought", "wildfire", "el nino", "la nina",
    # Market events
    "stock market", "crash", "rally", "selloff", "correction",
    "circuit breaker", "trading halt", "ipo", "merger", "acquisition",
    # Political (major)
    "election", "president", "coup", "impeachment", "government",
    "parliament", "cabinet", "minister",
    # Commodity
    "oil price", "opec", "production cut", "supply disruption",
]

# Keywords that indicate noise (should be removed)
NOISE_KEYWORDS = [
    "dating", "monk", "retreat", "murder", "killer", "bodycam",
    "falconio", "typhoon makes landfall", "evacuated",
    "south korea takes place", "buddhist temple",
    "detained by armed", "questioned", "body of",
    "25th anniversary", "video shows", "watch:",
    "newly-released video", "dating trend",
]


def is_market_relevant(judul: str, deskripsi: str) -> bool:
    """Check if an event is market-relevant based on title and description."""
    text = f"{judul or ''} {deskripsi or ''}".lower()

    # Check noise keywords first
    for kw in NOISE_KEYWORDS:
        if kw in text:
            return False

    # Check market-relevant keywords
    for kw in MARKET_RELEVANT_KEYWORDS:
        if kw in text:
            return True

    return False


def classify_event(judul: str, deskripsi: str, kategori: str) -> tuple[str, str, str]:
    """Classify event into proper category, impact, and direction.

    Returns (new_kategori, dampak_market, direction).
    """
    text = f"{judul or ''} {deskripsi or ''}".lower()

    # Determine category
    if any(k in text for k in ["war", "invasion", "missile", "airstrike", "nuclear",
                                "sanction", "conflict", "geopolitical", "ceasefire"]):
        new_kategori = "Konflik Geopolitik"
    elif any(k in text for k in ["tariff", "trade war", "embargo"]):
        new_kategori = "Trade War"
    elif any(k in text for k in ["pandemic", "covid", "outbreak", "epidemic", "vaccine",
                                  "lockdown", "variant", "coronavirus"]):
        new_kategori = "Pandemi"
    elif any(k in text for k in ["earthquake", "tsunami", "volcanic", "hurricane",
                                  "cyclone", "flood", "drought", "wildfire"]):
        new_kategori = "Bencana Alam"
    elif any(k in text for k in ["rate cut", "rate hike", "interest rate", "fed",
                                  "central bank", "inflation", "recession",
                                  "stimulus", "quantitative easing"]):
        new_kategori = "Kebijakan Moneter"
    elif any(k in text for k in ["election", "president", "coup", "impeachment",
                                  "government", "parliament"]):
        new_kategori = "Politik"
    elif any(k in text for k in ["oil price", "opec", "production cut", "supply"]):
        new_kategori = "Komoditas"
    else:
        new_kategori = kategori or "Lainnya"

    # Determine impact level
    if any(k in text for k in ["war", "invasion", "nuclear", "pandemic", "crash",
                                "crisis", "default", "coup", "earthquake", "tsunami"]):
        dampak = "Tinggi"
    elif any(k in text for k in ["sanction", "tariff", "rate hike", "rate cut",
                                  "inflation", "recession", "flood", "drought",
                                  "election", "missile", "airstrike"]):
        dampak = "Sedang"
    else:
        dampak = "Rendah"

    # Determine direction
    if any(k in text for k in ["rate cut", "stimulus", "ceasefire", "treaty",
                                "rally", "vaccine", "recovery"]):
        direction = "Positif"
    elif any(k in text for k in ["war", "invasion", "crash", "pandemic", "sanction",
                                  "rate hike", "inflation", "recession", "crisis",
                                  "default", "earthquake", "tsunami"]):
        direction = "Negatif"
    else:
        direction = "Netral"

    return new_kategori, dampak, direction


def main() -> None:
    logger.info("=" * 70)
    logger.info("P2: EXTERNAL EVENTS CLEANING + EVENT SCORER VERIFICATION")
    logger.info("=" * 70)

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # Step 1: Audit current external_events
    logger.info("")
    logger.info("--- Step 1: Audit current external_events ---")
    cur.execute("SELECT kategori, count(*) FROM external_events GROUP BY kategori ORDER BY count(*) DESC")
    for row in cur.fetchall():
        logger.info("  '%s': %d", row[0], row[1])

    # Step 2: Identify and remove noise events
    logger.info("")
    logger.info("--- Step 2: Identify noise vs market-relevant events ---")
    cur.execute("SELECT id, judul, deskripsi, kategori FROM external_events ORDER BY id")
    all_rows = cur.fetchall()
    noise_ids = []
    relevant_count = 0
    for eid, judul, deskripsi, kategori in all_rows:
        if is_market_relevant(judul, deskripsi):
            relevant_count += 1
        else:
            noise_ids.append(eid)
            logger.info("  NOISE [id=%d]: %s", eid, (judul or "")[:80])

    logger.info("")
    logger.info("  Total: %d, Market-relevant: %d, Noise: %d",
                len(all_rows), relevant_count, len(noise_ids))

    # Step 3: Delete noise events
    logger.info("")
    logger.info("--- Step 3: Delete noise events ---")
    for eid in noise_ids:
        cur.execute("DELETE FROM external_events WHERE id = %s", (eid,))
    conn.commit()
    logger.info("  Deleted %d noise events", len(noise_ids))

    # Step 4: Re-classify remaining events
    logger.info("")
    logger.info("--- Step 4: Re-classify remaining events ---")
    cur.execute("SELECT id, judul, deskripsi, kategori FROM external_events ORDER BY id")
    remaining = cur.fetchall()
    reclassified = 0
    for eid, judul, deskripsi, kategori in remaining:
        new_kat, dampak, direction = classify_event(judul, deskripsi, kategori)
        cur.execute("""
            UPDATE external_events
            SET kategori = %s, dampak_market = %s
            WHERE id = %s
        """, (new_kat, dampak, eid))
        reclassified += cur.rowcount
    conn.commit()
    logger.info("  Reclassified %d events", reclassified)

    # Step 5: Final audit
    logger.info("")
    logger.info("--- Step 5: Final external_events audit ---")
    cur.execute("SELECT kategori, dampak_market, count(*) FROM external_events GROUP BY kategori, dampak_market ORDER BY kategori, dampak_market")
    for row in cur.fetchall():
        logger.info("  %s / %s: %d", row[0], row[1], row[2])
    cur.execute("SELECT count(*) FROM external_events")
    total = cur.fetchone()[0]
    logger.info("  Total remaining: %d", total)

    # Step 6: Test PolicyEventScorer
    logger.info("")
    logger.info("--- Step 6: Test PolicyEventScorer with PostgreSQL ---")
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from market.analysis.policy_event_scorer import PolicyEventScorer

        scorer = PolicyEventScorer()
        n_loaded = scorer.load()
        logger.info("  PolicyEventScorer loaded %d events", n_loaded)

        # Test with sample tickers
        as_of = datetime(2026, 8, 15)
        for ticker in ["BBCA.JK", "ADRO.JK", "AALI.JK", "ANTM.JK"]:
            signal = scorer.compute_event_signal(ticker, as_of)
            if signal:
                logger.info("  %s: score=%.2f direction=%s confidence=%.2f active_events=%d",
                            ticker, signal.score, signal.direction,
                            signal.confidence, len(signal.active_events))
            else:
                logger.info("  %s: no signal (no events loaded)", ticker)
    except Exception as e:
        logger.error("  PolicyEventScorer test failed: %s", e, exc_info=True)

    conn.close()
    logger.info("")
    logger.info("P2 COMPLETE.")


if __name__ == "__main__":
    main()
