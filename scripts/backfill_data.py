"""Comprehensive data backfill script.

Backfills:
1. Quarterly fundamentals (PE, PB, ROE, DER, EPS, dividend yield) from yfinance
2. News + sentiment from yfinance (keyword-based NLP)
3. UNTR foreign flow gap fill
4. Sector classification for InstrumentMaster

Uses dynamic rate limiting via RateLimiter.
"""

from __future__ import annotations

import logging
import warnings
from decimal import Decimal

import numpy as np
import pandas as pd
import yfinance as yf

from market.data.rate_limit import RateLimiter

warnings.filterwarnings("ignore", category=DeprecationWarning, module="lightgbm")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TICKERS = [
    "BBCA.JK", "BBRI.JK", "TLKM.JK", "ASII.JK", "UNVR.JK",
    "ANTM.JK", "MDKA.JK", "UNTR.JK",
]

# Sector mapping from yfinance
SECTOR_MAP = {
    "BBCA.JK": ("Financial Services", "Banks - Regional", "PT Bank Central Asia Tbk"),
    "BBRI.JK": ("Financial Services", "Banks - Regional", "PT Bank Rakyat Indonesia (Persero) Tbk"),
    "TLKM.JK": ("Communication Services", "Telecom Services", "PT Telekomunikasi Indonesia Tbk"),
    "ASII.JK": ("Industrials", "Conglomerates", "PT Astra International Tbk"),
    "UNVR.JK": ("Consumer Defensive", "Household & Personal Products",
                "PT Unilever Indonesia Tbk"),
    "ANTM.JK": ("Basic Materials", "Gold", "PT Antam (Persero) Tbk"),
    "MDKA.JK": ("Basic Materials", "Other Industrial Metals & Mining",
                "PT Merdeka Copper Gold Tbk"),
    "UNTR.JK": ("Basic Materials", "Other Industrial Metals & Mining",
                "PT United Tractors Tbk"),
}

# Dynamic rate limiter: start conservative, adapt
limiter = RateLimiter(max_calls=0.8, window_seconds=1.0)


def safe_float(val) -> float | None:
    """Convert to float, return None for NaN/None."""
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def backfill_instrument_master(session) -> None:
    """Insert sector/industry info into InstrumentMaster."""
    from sqlalchemy import select

    from market.db.models import InstrumentMaster

    logger.info("=== Backfilling InstrumentMaster ===")
    for ticker, (sector, subsector, name) in SECTOR_MAP.items():
        limiter.acquire()
        existing = session.execute(
            select(InstrumentMaster).where(InstrumentMaster.ticker == ticker)
        ).scalar_one_or_none()

        if existing:
            existing.sector = sector
            existing.subsector = subsector
            if not existing.name:
                existing.name = name
            logger.info("  Updated %s: sector=%s", ticker, sector)
        else:
            session.add(InstrumentMaster(
                ticker=ticker,
                market_mic="XIDX",
                asset_class="equity",
                name=name,
                base_currency="IDR",
                reporting_currency="IDR",
                lot_size=100,
                tick_size=1,
                is_active=True,
                sector=sector,
                subsector=subsector,
            ))
            logger.info("  Inserted %s: sector=%s", ticker, sector)
    session.commit()


def backfill_quarterly_fundamentals(session) -> None:
    """Backfill quarterly fundamentals from yfinance.

    Computes PE, PB, ROE, DER, EPS, dividend yield from quarterly
    income statements and balance sheets, plus historical close prices.
    """
    from sqlalchemy import select

    from market.db.models import FundamentalData

    logger.info("=== Backfilling Quarterly Fundamentals ===")

    for ticker in TICKERS:
        limiter.acquire()
        logger.info("  Fetching quarterly statements for %s...", ticker)

        try:
            t = yf.Ticker(ticker)
            qis = t.quarterly_income_stmt
            qbs = t.quarterly_balance_sheet
            info = t.info
        except Exception as e:
            logger.warning("  Failed to fetch fundamentals for %s: %s", ticker, e)
            continue

        if qis is None or qbs is None or qis.empty or qbs.empty:
            logger.warning("  No quarterly data for %s", ticker)
            continue

        # Get historical close prices for PE/PB calculation
        limiter.acquire()
        try:
            hist = yf.download(ticker, period="5y", progress=False, auto_adjust=False)
        except Exception as e:
            logger.warning("  Failed to fetch history for %s: %s", ticker, e)
            continue

        # Process each quarter
        quarters = sorted(set(qis.columns) & set(qbs.columns))
        stored = 0

        for q_date in quarters:
            q_date_ts = pd.Timestamp(q_date)
            q_date_d = q_date_ts.date()

            # Check if already exists
            existing = session.execute(
                select(FundamentalData).where(
                    FundamentalData.ticker == ticker,
                    FundamentalData.date == q_date_d,
                )
            ).scalar_one_or_none()

            if existing:
                continue

            # Get close price at or before quarter end
            if hist is not None and not hist.empty:
                hist_before = hist[hist.index <= q_date_ts]
                if hist_before.empty:
                    continue
                close_val = hist_before["Close"].iloc[-1]
                if isinstance(close_val, pd.Series):
                    close_val = close_val.iloc[0]
                close_price = float(close_val)
            else:
                continue

            # Extract fundamental data from quarterly statements
            # EPS (quarterly)
            eps = safe_float(qis.loc["Diluted EPS", q_date]) if "Diluted EPS" in qis.index else None
            if eps is None and "Basic EPS" in qis.index:
                eps = safe_float(qis.loc["Basic EPS", q_date])

            # Net Income
            net_income = (
                safe_float(qis.loc["Net Income", q_date])
                if "Net Income" in qis.index else None
            )

            # Total Revenue
            revenue = (
                safe_float(qis.loc["Total Revenue", q_date])
                if "Total Revenue" in qis.index else None
            )

            # Total Assets
            total_assets = (
                safe_float(qbs.loc["Total Assets", q_date])
                if "Total Assets" in qbs.index else None
            )

            # Total Liabilities
            total_liab = safe_float(qbs.loc["Total Liabilities Net Minority Interest", q_date]) \
                if "Total Liabilities Net Minority Interest" in qbs.index else None

            # Stockholders Equity
            equity = safe_float(qbs.loc["Stockholders Equity", q_date]) \
                if "Stockholders Equity" in qbs.index else None
            if equity is None and "Common Stock Equity" in qbs.index:
                equity = safe_float(qbs.loc["Common Stock Equity", q_date])

            # Total Debt
            total_debt = (
                safe_float(qbs.loc["Total Debt", q_date])
                if "Total Debt" in qbs.index else None
            )

            # Shares outstanding
            shares = safe_float(qbs.loc["Ordinary Shares Number", q_date]) \
                if "Ordinary Shares Number" in qbs.index else None
            if shares is None and "Share Issued" in qbs.index:
                shares = safe_float(qbs.loc["Share Issued", q_date])

            # Compute derived metrics
            # PE ratio: price / (annualized EPS)
            annual_eps = eps * 4 if eps is not None and eps != 0 else None
            pe = close_price / annual_eps if annual_eps and annual_eps != 0 else None

            # Book value per share
            bvps = equity / shares if (equity and shares and shares != 0) else None

            # PB ratio: price / BVPS
            pb = close_price / bvps if bvps and bvps != 0 else None

            # ROE: net income / equity (quarterly annualized)
            roe = (net_income * 4 / equity) if (net_income and equity and equity != 0) else None

            # DER: total debt / equity
            der = total_debt / equity if (total_debt and equity and equity != 0) else None

            # Dividend yield from info (current snapshot)
            div_yield = safe_float(info.get("dividendYield"))
            if div_yield is not None:
                div_yield = div_yield * 100  # Convert to percentage

            # Market cap
            market_cap = close_price * shares if (close_price and shares) else None

            # Cash flow (from quarterly cashflow if available)
            cash_flow = None
            try:
                limiter.acquire()
                qcf = t.quarterly_cashflow
                if (
                    qcf is not None and not qcf.empty
                    and q_date in qcf.columns
                    and "Operating Cash Flow" in qcf.index
                ):
                    cash_flow = safe_float(
                        qcf.loc["Operating Cash Flow", q_date]
                    )
            except Exception:
                pass

            # Determine fiscal year and quarter
            fy = q_date_ts.year
            q = f"Q{(q_date_ts.month - 1) // 3 + 1}"

            session.add(FundamentalData(
                ticker=ticker,
                date=q_date_d,
                pe=Decimal(str(round(pe, 4))) if pe is not None else None,
                pb=Decimal(str(round(pb, 4))) if pb is not None else None,
                roe=Decimal(str(round(roe, 4))) if roe is not None else None,
                der=Decimal(str(round(der, 4))) if der is not None else None,
                dividend_yield=Decimal(str(round(div_yield, 6))) if div_yield is not None else None,
                eps=Decimal(str(round(eps, 4))) if eps is not None else None,
                book_value_per_share=Decimal(str(round(bvps, 4))) if bvps is not None else None,
                revenue=Decimal(str(round(revenue, 2))) if revenue is not None else None,
                net_income=Decimal(str(round(net_income, 2))) if net_income is not None else None,
                total_assets=Decimal(str(round(total_assets, 2)))
                if total_assets is not None else None,
                total_liabilities=Decimal(str(round(total_liab, 2)))
                if total_liab is not None else None,
                cash_flow=Decimal(str(round(cash_flow, 2))) if cash_flow is not None else None,
                market_cap=Decimal(str(round(market_cap, 2))) if market_cap is not None else None,
                fiscal_year=fy,
                quarter=q,
                source="yahoo_finance_quarterly",
            ))
            stored += 1

        session.commit()
        logger.info("  %s: stored %d quarterly fundamental rows", ticker, stored)


# ── News sentiment (keyword-based NLP) ────────────────────────────────────

# Financial sentiment lexicon (English + Indonesian)
POSITIVE_WORDS = {
    # English
    "surge", "soar", "rally", "gain", "profit", "beat", "exceed", "upgrade",
    "bullish", "outperform", "strong", "growth", "rise", "jump", "breakthrough",
    "record", "high", "positive", "optimistic", "expand", "acquire", "launch",
    "approve", "approval", "dividend", "buyback", "raise", "boost", "improve",
    "recover", "rebound", "opportunity", "favorable", "robust", "solid",
    "increase", "higher", "above", "overweight", "target",
    # Indonesian
    "naik", "untung", "lab", "tumbuh", "tinggi", "positif", "optimis",
    "kuat", "bangun", "rekomendasi", "beli", "akumulasi", "naikkan",
}

NEGATIVE_WORDS = {
    # English
    "plunge", "crash", "drop", "fall", "loss", "miss", "downgrade", "bearish",
    "underperform", "weak", "decline", "cut", "reduce", "lower", "sell",
    "warning", "risk", "concern", "fear", "negative", "pessimistic",
    "suspend", "halt", "delay", "lawsuit", "fraud", "investigation",
    "default", "bankrupt", "restructure", "impairment", "write-down",
    "decrease", "below", "disappoint", "pressure", "challenge", "headwind",
    # Indonesian
    "turun", "rugi", "kerugian", "turunkan", "lemah", "negatif", "pesimis",
    "jual", "jual besar", "tekanan", "risiko", "ancaman", "gagal",
}


def classify_sentiment(text: str) -> tuple[float, str]:
    """Classify text sentiment using keyword matching.

    Returns:
        Tuple of (sentiment_score, impact_label).
        Score: -1.0 (very negative) to 1.0 (very positive).
        Impact: "positive", "negative", "neutral".
    """
    if not text:
        return 0.0, "neutral"

    text_lower = text.lower()
    set(text_lower.split())

    pos_count = sum(1 for w in POSITIVE_WORDS if w in text_lower)
    neg_count = sum(1 for w in NEGATIVE_WORDS if w in text_lower)

    total = pos_count + neg_count
    if total == 0:
        return 0.0, "neutral"

    score = (pos_count - neg_count) / total
    if score > 0.2:
        return score, "positive"
    elif score < -0.2:
        return score, "negative"
    return 0.0, "neutral"


def backfill_news_sentiment(session) -> None:
    """Fetch news from yfinance and classify sentiment."""
    from sqlalchemy import select

    from market.db.models import News

    logger.info("=== Backfilling News + Sentiment ===")

    total_stored = 0
    for ticker in TICKERS:
        limiter.acquire()
        logger.info("  Fetching news for %s...", ticker)

        try:
            t = yf.Ticker(ticker)
            news_items = t.news
        except Exception as e:
            logger.warning("  Failed to fetch news for %s: %s", ticker, e)
            continue

        if not news_items:
            logger.info("  No news for %s", ticker)
            continue

        stored = 0
        for item in news_items:
            content = item.get("content", item)
            news_id = item.get("id", content.get("id", ""))

            # Check if already exists
            existing = session.execute(
                select(News).where(News.news_id == news_id)
            ).scalar_one_or_none()

            if existing:
                continue

            headline = content.get("title", "")
            summary = content.get("summary", "")
            body = f"{headline}. {summary}" if summary else headline
            pub_date = content.get("pubDate", content.get("displayTime", ""))
            source = content.get("provider", {}).get("displayName", "yahoo_finance")

            # Classify sentiment
            sentiment_score, impact = classify_sentiment(body)

            session.add(News(
                news_id=news_id,
                headline=headline,
                body=summary,
                published_at=pub_date,
                source=source,
                entities=ticker,
                topic="market",
                sentiment=Decimal(str(round(sentiment_score, 2))),
                impact=impact,
            ))
            stored += 1

        session.commit()
        total_stored += stored
        logger.info("  %s: stored %d news items", ticker, stored)

    logger.info("  Total news items stored: %d", total_stored)


def backfill_untr_foreign_flow(session) -> None:
    """Backfill UNTR foreign flow data (only 32 rows, need more)."""
    from sqlalchemy import func, select

    from market.db.models import ForeignFlow

    logger.info("=== Backfilling UNTR Foreign Flow ===")

    # Check current count
    cnt = session.execute(
        select(func.count()).select_from(ForeignFlow)
        .where(ForeignFlow.ticker == "UNTR.JK")
    ).scalar()

    if cnt >= 1000:
        logger.info("  UNTR already has %d rows, skipping", cnt)
        return

    # UNTR foreign flow is not available from yfinance directly.
    # We'll generate synthetic flow data based on volume and price direction
    # as a placeholder. In production, this would come from IDX data.
    from market.db.models import OHLCV

    rows = session.execute(
        select(OHLCV).where(
            OHLCV.ticker == "UNTR.JK",
            OHLCV.timeframe == "1d",
        ).order_by(OHLCV.timestamp)
    ).scalars().all()

    if not rows:
        logger.warning("  No OHLCV data for UNTR.JK")
        return

    stored = 0
    for row in rows:
        row_date = row.timestamp.date() if hasattr(row.timestamp, 'date') else row.timestamp

        # Check if already exists
        existing = session.execute(
            select(ForeignFlow).where(
                ForeignFlow.ticker == "UNTR.JK",
                ForeignFlow.date == row_date,
            )
        ).scalar_one_or_none()

        if existing:
            continue

        # Estimate foreign flow from volume and price direction
        # (placeholder: in production, fetch from IDX)
        volume = int(row.volume) if row.volume else 0
        price_change = float(row.close) - float(row.open)
        direction = 1 if price_change > 0 else -1

        # Estimate: foreign typically ~30% of volume
        foreign_vol = volume * 0.3
        foreign_buy = foreign_vol * (0.5 + 0.1 * direction)
        foreign_sell = foreign_vol - foreign_buy
        foreign_net = foreign_buy - foreign_sell

        session.add(ForeignFlow(
            ticker="UNTR.JK",
            date=row_date,
            foreign_buy=int(foreign_buy),
            foreign_sell=int(foreign_sell),
            foreign_net=int(foreign_net),
            domestic_buy=int(volume - foreign_buy),
            domestic_sell=int(volume - foreign_sell),
            domestic_net=int(foreign_net * -1),
            source="estimated_from_volume",
        ))
        stored += 1

    session.commit()
    logger.info("  UNTR: stored %d foreign flow rows (estimated)", stored)


def main() -> None:
    """Run comprehensive data backfill."""
    from market.db.engine import get_sessionmaker

    logger.info("=" * 70)
    logger.info("COMPREHENSIVE DATA BACKFILL")
    logger.info("Tickers: %s", ", ".join(TICKERS))
    logger.info("Rate limit: 0.8 calls/sec (dynamic)")
    logger.info("=" * 70)

    session = get_sessionmaker()()

    try:
        # Step 1: InstrumentMaster (sector info)
        backfill_instrument_master(session)

        # Step 2: Quarterly fundamentals
        backfill_quarterly_fundamentals(session)

        # Step 3: News + sentiment
        backfill_news_sentiment(session)

        # Step 4: UNTR foreign flow
        backfill_untr_foreign_flow(session)

        # Summary
        from sqlalchemy import func, select

        from market.db.models import (
            ForeignFlow,
            FundamentalData,
            News,
        )

        fund_cnt = session.execute(
            select(func.count()).select_from(FundamentalData)
        ).scalar()
        news_cnt = session.execute(
            select(func.count()).select_from(News)
        ).scalar()
        untr_flow = session.execute(
            select(func.count()).select_from(ForeignFlow)
            .where(ForeignFlow.ticker == "UNTR.JK")
        ).scalar()

        logger.info("=" * 70)
        logger.info("BACKFILL COMPLETE")
        logger.info("  FundamentalData: %d total rows", fund_cnt)
        logger.info("  News: %d total rows", news_cnt)
        logger.info("  UNTR ForeignFlow: %d rows", untr_flow)
        logger.info("=" * 70)

    finally:
        session.close()


if __name__ == "__main__":
    main()
