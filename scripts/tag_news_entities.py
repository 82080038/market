"""Tag news articles with ticker entities using keyword matching.

Matches news headlines against IDX ticker codes and company names.
Updates the `entities` field in the news table with comma-separated tickers.

Usage:
    DATABASE_URL=postgresql://petrick:market_dev@localhost:5433/market python scripts/tag_news_entities.py
"""

from __future__ import annotations

import logging
import re
import sys

from sqlalchemy import select, text

from market.db.engine import get_sessionmaker
from market.db.models import InstrumentMaster, News

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Market-wide entities (not specific tickers) — keys MUST be uppercase
MARKET_ENTITIES = {
    "IHSG": "^JKSE",
    "LQ45": "^JKLQ45",
    "JCI": "^JKSE",
    "BEI": "XIDX",
    "IDX": "XIDX",
    "OJK": "OJK",
    "BI": "BI",
    "LPS": "LPS",
    "KSSK": "KSSK",
    "RUPIAH": "FX_USD_IDR",
    "SBN": "SBN",
    "SUN": "SBN",
    "DJSB": "SBN",
    "ASING": "^JKSE",
    "FOREIGN": "^JKSE",
    "EMITEN": "XIDX",
    "SAHAM": "XIDX",
    "PASAR MODAL": "XIDX",
    "PASAR SAHAM": "XIDX",
}

# Common company abbreviations → actual tickers
COMPANY_ABBREVIATIONS = {
    "BNI": "BBNI.JK",
    "BCA": "BBCA.JK",
    "BRI": "BBRI.JK",
    "MANDIRI": "BMRI.JK",
    "TELKOM": "TLKM.JK",
    "PERTAMINA": "PERTAMINA",
    "PLN": "PLN",
    "BULOG": "BULOG",
    "PEGADAIAN": "PEGADAIAN",
    "PNM": "PNM",
    "ESDM": "ESDM",
    "BPS": "BPS",
    "GIIAS": "GIIAS",
    "MBG": "MBG",
    "RUPTL": "RUPTL",
}

# Sectoral index keywords
SECTORAL_KEYWORDS = {
    "ENERGY": "IDXENERGY.JK",
    "FINANCE": "IDXFINANCE.JK",
    "FINANSIAL": "IDXFINANCE.JK",
    "HEALTH": "IDXHEALTH.JK",
    "KESEHATAN": "IDXHEALTH.JK",
    "BANK": "IDXFINANCE.JK",
    "PERBANKAN": "IDXFINANCE.JK",
    "TEKNOLOGI": "IDXTECHNO.JK",
    "TECHNOLOGY": "IDXTECHNO.JK",
    "PROPERTI": "IDXPROPER.JK",
    "INFRASTRUKTUR": "IDXINFRA.JK",
    "BANDARA": "IDXINFRA.JK",
    "CNG": "IDXENERGY.JK",
    "PLTS": "IDXENERGY.JK",
    "LISTRIK": "IDXENERGY.JK",
    "BERAS": "IDXNONCYC.JK",
    "PANGAN": "IDXNONCYC.JK",
    "SHOPPING": "IDXCYCLIC.JK",
    "RETAIL": "IDXCYCLIC.JK",
    "MOBIL": "IDXCYCLIC.JK",
    "OTOMOTIF": "IDXCYCLIC.JK",
    "VIRUS": "IDXHEALTH.JK",
    "OBAT": "IDXHEALTH.JK",
    "KEUANGAN": "GOV_FISCAL",
    "APBN": "GOV_FISCAL",
    "FISKAL": "GOV_FISCAL",
}


def build_keyword_map(session) -> dict[str, str]:
    """Build keyword → ticker mapping from instrument_master."""
    rows = session.execute(
        select(InstrumentMaster.ticker, InstrumentMaster.name)
        .where(
            InstrumentMaster.market_mic == "XIDX",
            InstrumentMaster.asset_class == "equity",
            InstrumentMaster.is_active == True,
        )
    ).all()

    keyword_map: dict[str, str] = {}

    for ticker, name in rows:
        ticker_clean = ticker.replace(".JK", "")
        # Always map the ticker code itself (e.g., "BBCA" → "BBCA.JK")
        if len(ticker_clean) >= 3:
            keyword_map[ticker_clean] = ticker

        if name:
            # Extract meaningful parts of company name
            # Remove common suffixes
            clean_name = re.sub(
                r"\b(Tbk\.?|Inc\.?|Corp\.?|Corporation|Group|Investama|Development|"
                r"International|Indonesia|Persero|Sejahtera|Mandiri|Nasional|"
                r"Jaya|Abadi|Pratama|Utama|Sentosa|Sakti|Lestari| Makmur|"
                r"Resources|Energy|Mining|Mineral|Metal|Finance|Bank|"
                r"Asuransi|Securities|Investment|Property|Realty|Land|"
                r"Development|Konstruksi|Energi|Listrik|Telekomunikasi)\b",
                "",
                name,
                flags=re.IGNORECASE,
            )
            parts = clean_name.split()
            for p in parts:
                p_upper = p.upper().strip(".,;:()[]{}\"'")
                if len(p_upper) >= 4 and p_upper not in keyword_map:
                    keyword_map[p_upper] = ticker

    # Add market entities (uppercase keys)
    keyword_map.update(MARKET_ENTITIES)
    keyword_map.update(SECTORAL_KEYWORDS)
    keyword_map.update(COMPANY_ABBREVIATIONS)

    return keyword_map


def tag_article(headline: str, keyword_map: dict[str, str]) -> str:
    """Find ticker entities in a headline. Returns comma-separated tickers."""
    if not headline:
        return ""

    headline_upper = headline.upper()
    found: dict[str, None] = {}  # preserve order, dedupe

    # Sort keywords by length (longest first) to avoid partial matches
    # Uppercase all keywords to match uppercased headline
    sorted_keywords = sorted(keyword_map.keys(), key=len, reverse=True)

    for kw in sorted_keywords:
        kw_upper = kw.upper()
        # Use word boundary matching for tickers (4+ chars)
        if len(kw_upper) >= 4:
            pattern = r"\b" + re.escape(kw_upper) + r"\b"
            if re.search(pattern, headline_upper):
                found[keyword_map[kw]] = None
        else:
            # Short keywords (3 chars) — only match if surrounded by spaces/punctuation
            pattern = r"(?:^|\s)" + re.escape(kw_upper) + r"(?:\s|$|[,.;:!?)])"
            if re.search(pattern, headline_upper):
                found[keyword_map[kw]] = None

    return ",".join(found.keys())


def main():
    session = get_sessionmaker()()

    logger.info("Building keyword map...")
    keyword_map = build_keyword_map(session)
    logger.info("  %d keywords mapped", len(keyword_map))

    # Get all news with empty entities
    rows = session.execute(
        select(News.id, News.headline).where(
            (News.entities.is_(None)) | (News.entities == "")
        )
    ).all()

    logger.info("News articles to tag: %d", len(rows))

    tagged = 0
    no_match = 0

    for news_id, headline in rows:
        entities = tag_article(headline or "", keyword_map)

        if entities:
            session.execute(
                text("UPDATE news SET entities = :e WHERE id = :id"),
                {"e": entities, "id": news_id},
            )
            tagged += 1
        else:
            no_match += 1

        if (tagged + no_match) % 20 == 0:
            session.commit()

    session.commit()

    logger.info("=" * 60)
    logger.info("FINAL SUMMARY")
    logger.info("  Tagged: %d", tagged)
    logger.info("  No match: %d", no_match)

    # Verify
    total = session.execute(
        text("SELECT COUNT(*) FROM news WHERE entities IS NOT NULL AND entities != ''")
    ).scalar()
    logger.info("  News with entities: %d / %d", total, tagged + no_match)

    # Sample tagged articles
    samples = session.execute(
        text("SELECT headline, entities FROM news WHERE entities IS NOT NULL AND entities != '' LIMIT 10")
    ).fetchall()
    logger.info("\n=== Sample tagged articles ===")
    for h, e in samples:
        logger.info("  [%s] %s", e, h[:80] if h else "")

    session.close()


if __name__ == "__main__":
    main()
