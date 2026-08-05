"""Recompute internal data from OHLCV using application engines.

This script clears migrated parquet data for internal tables and recomputes
them from the OHLCV data already in the database, ensuring all internal
data is produced by the application's own engines.

Usage:
    ENV=paper python -m market.data.recompute_internal [--dry-run]
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import numpy as np
import pandas as pd
from sqlalchemy import select, text

from market.analysis.fundamental import FundamentalAnalysisEngine
from market.analysis.global_market import GLOBAL_INDICES, GlobalMarketEngine
from market.analysis.macro import MacroEconomicEngine
from market.analysis.profiling import InstrumentProfiler
from market.analysis.relationship import REFERENCE_ASSETS, MarketRelationshipEngine
from market.analysis.sentiment import SentimentEngine
from market.analysis.technical import TechnicalAnalysisEngine
from market.db.engine import get_sessionmaker
from market.db.models import (
    OHLCV,
    FearGreed,
    FundamentalData,
    RelationshipMatrix,
    Score,
    StockPersonality,
    TechnicalIndicator,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Tickers for global indices and reference assets
GLOBAL_TICKERS = list(GLOBAL_INDICES.keys())
REFERENCE_TICKERS = list(REFERENCE_ASSETS.keys())
IHSG_TICKER = "^JKSE"


def _load_ohlcv_df(session: Session, ticker: str) -> pd.DataFrame:
    """Load OHLCV data for a ticker into a pandas DataFrame."""
    rows = session.execute(
        select(OHLCV).where(OHLCV.ticker == ticker).order_by(OHLCV.timestamp)
    ).scalars().all()
    if not rows:
        return pd.DataFrame()
    data = [
        {
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": int(r.volume),
        }
        for r in rows
    ]
    idx = [r.timestamp for r in rows]
    df = pd.DataFrame(data, index=pd.DatetimeIndex(idx))
    return df


def _load_all_idx_tickers(session: Session) -> list[str]:
    """Get all IDX equity tickers from OHLCV (excluding indices/forex)."""
    result = session.execute(
        text(
            "SELECT DISTINCT ticker FROM ohlcv "
            "WHERE ticker LIKE '%.JK' "
            "ORDER BY ticker"
        )
    )
    return [r[0] for r in result.fetchall()]


def recompute_technical_indicators(session: Session, dry_run: bool = False) -> int:
    """Clear and recompute technical_indicators from OHLCV."""
    tickers = _load_all_idx_tickers(session)
    logger.info("Recomputing technical_indicators for %d tickers", len(tickers))

    if dry_run:
        return len(tickers)

    # Clear existing migrated data
    session.execute(text("DELETE FROM technical_indicators"))
    session.commit()

    engine = TechnicalAnalysisEngine()
    count = 0
    for ticker in tickers:
        df = _load_ohlcv_df(session, ticker)
        if df.empty or len(df) < 50:
            continue

        result = engine.analyze(ticker, df)
        if not result.indicators:
            continue

        # Save latest indicators
        today = datetime.now(UTC).date()
        indicator_map = {
            "ma20": "MA20",
            "ma50": "MA50",
            "rsi": "RSI",
            "macd": "MACD",
            "macd_signal": "MACD_SIGNAL",
            "adx": "ADX",
            "atr": "ATR14",
            "bb_upper": "BB_UPPER",
            "bb_lower": "BB_LOWER",
            "vol_ratio": "VOLUME_SMA20",
        }

        for key, label in indicator_map.items():
            val = result.indicators.get(key)
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                session.add(
                    TechnicalIndicator(
                        ticker=ticker,
                        date=today,
                        indicator=label,
                        value=float(val),
                        timeframe="1d",
                        source="computed",
                    )
                )
                count += 1

        if count % 1000 == 0:
            session.commit()
            logger.info("technical_indicators: %d rows", count)

    session.commit()
    return count


def recompute_scores(session: Session, dry_run: bool = False) -> int:
    """Clear and recompute scores from all 6 analysis engines."""
    tickers = _load_all_idx_tickers(session)
    logger.info("Recomputing scores for %d tickers", len(tickers))

    if dry_run:
        return len(tickers) * 6  # 6 engines

    # Clear existing migrated data
    session.execute(text("DELETE FROM scores"))
    session.commit()

    tech_engine = TechnicalAnalysisEngine()
    fund_engine = FundamentalAnalysisEngine()
    macro_engine = MacroEconomicEngine()
    global_engine = GlobalMarketEngine()
    rel_engine = MarketRelationshipEngine()
    sentiment_engine = SentimentEngine()

    # Load global index data
    global_data: dict[str, pd.DataFrame] = {}
    for gt in GLOBAL_TICKERS:
        df = _load_ohlcv_df(session, gt)
        if not df.empty:
            global_data[gt] = df

    # Compute global score once (same for all tickers)
    global_result = global_engine.analyze(global_data)

    # Load reference returns for relationship
    ref_returns: dict[str, pd.Series] = {}
    for rt in REFERENCE_TICKERS:
        df = _load_ohlcv_df(session, rt)
        if not df.empty and len(df) >= 20:
            ref_returns[rt] = df["close"].astype(float).pct_change(
                fill_method=None,
            ).dropna()

    # Load macro inputs from latest OHLCV
    us10y_df = _load_ohlcv_df(session, "^TNX")
    gold_df = _load_ohlcv_df(session, "GC=F")
    oil_df = _load_ohlcv_df(session, "CL=F")
    usd_df = _load_ohlcv_df(session, "IDR=X")

    def _latest_close(df: pd.DataFrame) -> tuple[float | None, float | None]:
        if df.empty or len(df) < 2:
            return None, None
        return float(df["close"].iloc[-1]), float(df["close"].iloc[-2])

    us10y_cur, us10y_prev = _latest_close(us10y_df)
    gold_cur, gold_prev = _latest_close(gold_df)
    oil_cur, oil_prev = _latest_close(oil_df)
    usd_cur, usd_prev = _latest_close(usd_df)

    macro_result = macro_engine.analyze(
        us10y_yield=us10y_cur,
        us10y_prev=us10y_prev,
        gold_price=gold_cur,
        gold_prev=gold_prev,
        oil_price=oil_cur,
        oil_prev=oil_prev,
        usd_idr=usd_cur,
        usd_idr_prev=usd_prev,
    )

    now = datetime.now(UTC)
    count = 0

    for ticker in tickers:
        df = _load_ohlcv_df(session, ticker)
        if df.empty or len(df) < 50:
            continue

        # Technical score
        tech_result = tech_engine.analyze(ticker, df)
        tech_score = tech_result.score if not np.isnan(tech_result.score) else 0.0
        session.add(
            Score(
                ticker=ticker,
                engine="technical",
                score=tech_score,
                breakdown=json.dumps(tech_result.breakdown),
                as_of=now,
            )
        )
        count += 1

        # Fundamental score (from fundamental_data table)
        fund_row = session.execute(
            select(FundamentalData)
            .where(FundamentalData.ticker == ticker)
            .order_by(FundamentalData.date.desc())
            .limit(1)
        ).scalar_one_or_none()

        if fund_row is not None:
            fund_result = fund_engine.analyze(
                ticker,
                pe=float(fund_row.pe) if fund_row.pe else None,
                pb=float(fund_row.pb) if fund_row.pb else None,
                roe=float(fund_row.roe) if fund_row.roe else None,
                der=float(fund_row.der) if fund_row.der else None,
                dividend_yield=(
                    float(fund_row.dividend_yield)
                    if fund_row.dividend_yield
                    else None
                ),
            )
        else:
            fund_result = fund_engine.analyze(ticker)

        session.add(
            Score(
                ticker=ticker,
                engine="fundamental",
                score=fund_result.score if not np.isnan(fund_result.score) else 0.0,
                breakdown=json.dumps(fund_result.breakdown),
                as_of=now,
            )
        )
        count += 1

        # Macro score (same for all tickers, but stored per-ticker)
        session.add(
            Score(
                ticker=ticker,
                engine="macro",
                score=macro_result.score if not np.isnan(macro_result.score) else 0.0,
                breakdown=json.dumps(macro_result.breakdown),
                as_of=now,
            )
        )
        count += 1

        # Global score (same for all tickers)
        session.add(
            Score(
                ticker=ticker,
                engine="global",
                score=global_result.score if not np.isnan(global_result.score) else 0.0,
                breakdown=json.dumps(global_result.breakdown),
                as_of=now,
            )
        )
        count += 1

        # Relationship score
        target_returns = df["close"].astype(float).pct_change(
            fill_method=None,
        ).dropna()
        rel_result = rel_engine.analyze(
            ticker, target_returns, ref_returns, window=60,
        )
        rel_score = rel_result.score if not np.isnan(rel_result.score) else 0.0
        session.add(
            Score(
                ticker=ticker,
                engine="relationship",
                score=rel_score,
                breakdown=json.dumps(
                    {"window": 60, "relationships": len(rel_result.relationships)}
                ),
                as_of=now,
            )
        )
        count += 1

        # Sentiment score (from foreign_flow if available)
        ff_row = session.execute(
            text(
                "SELECT foreign_net FROM foreign_flow "
                "WHERE ticker = :t ORDER BY date DESC LIMIT 1"
            ),
            {"t": ticker},
        ).first()

        if ff_row is not None and ff_row[0] is not None:
            # Simple foreign flow sentiment: positive net = bullish
            ff_val = float(ff_row[0])
            ff_score = min(100.0, max(0.0, 50.0 + ff_val / 1e9 * 10))
        else:
            ff_score = 50.0

        sent_result = sentiment_engine.analyze(
            ticker, foreign_flow_score=ff_score,
        )
        session.add(
            Score(
                ticker=ticker,
                engine="sentiment",
                score=sent_result.score if not np.isnan(sent_result.score) else 50.0,
                breakdown=json.dumps(sent_result.breakdown),
                as_of=now,
            )
        )
        count += 1

        if count % 500 == 0:
            session.commit()
            logger.info("scores: %d rows", count)

    session.commit()
    return count


def recompute_relationship_matrix(session: Session, dry_run: bool = False) -> int:
    """Clear and recompute relationship_matrix from OHLCV."""
    tickers = _load_all_idx_tickers(session)
    logger.info(
        "Recomputing relationship_matrix for %d tickers x %d references",
        len(tickers),
        len(REFERENCE_TICKERS),
    )

    if dry_run:
        return len(tickers) * len(REFERENCE_TICKERS)

    # Clear existing
    session.execute(text("DELETE FROM relationship_matrix"))
    session.commit()

    rel_engine = MarketRelationshipEngine()
    count = 0

    # Pre-load reference returns
    ref_returns: dict[str, pd.Series] = {}
    ref_dfs: dict[str, pd.DataFrame] = {}
    for rt in REFERENCE_TICKERS:
        df = _load_ohlcv_df(session, rt)
        if not df.empty and len(df) >= 20:
            ref_dfs[rt] = df
            ref_returns[rt] = df["close"].astype(float).pct_change(
                fill_method=None,
            ).dropna()

    for ticker in tickers:
        df = _load_ohlcv_df(session, ticker)
        if df.empty or len(df) < 60:
            continue

        target_returns = df["close"].astype(float).pct_change(
            fill_method=None,
        ).dropna()

        result = rel_engine.analyze(
            ticker, target_returns, ref_returns, window=60,
        )

        for rel in result.relationships:
            ref_ticker = str(rel["ticker"])
            corr_raw = cast("float | None", rel["correlation"])
            lag_raw = cast("int | None", rel["lag"])
            session.add(
                RelationshipMatrix(
                    asset_a=ticker,
                    asset_b=ref_ticker,
                    window=60,
                    correlation=float(corr_raw) if corr_raw is not None else None,
                    lag=int(lag_raw) if lag_raw is not None else None,
                )
            )
            count += 1

        if count % 1000 == 0:
            session.commit()
            logger.info("relationship_matrix: %d rows", count)

    session.commit()
    return count


def recompute_fear_greed(session: Session, dry_run: bool = False) -> int:
    """Clear and recompute fear_greed from OHLCV market data.

    Uses a composite of market momentum, volatility, and volume
    to compute a Fear & Greed index (0-100).
    """
    logger.info("Recomputing fear_greed index")

    if dry_run:
        return 365  # ~1 year of daily data

    # Clear existing
    session.execute(text("DELETE FROM fear_greed"))
    session.commit()

    # Load IHSG data
    ihsg_df = _load_ohlcv_df(session, IHSG_TICKER)
    if ihsg_df.empty or len(ihsg_df) < 50:
        logger.warning("No IHSG data for fear_greed computation")
        return 0

    close = ihsg_df["close"].astype(float)
    if "volume" in ihsg_df.columns:
        volume = ihsg_df["volume"].astype(float)
    else:
        volume = pd.Series(0.0, index=ihsg_df.index)

    # Compute daily Fear & Greed components
    count = 0
    window = 20
    for i in range(window, len(ihsg_df)):
        date_val = ihsg_df.index[i].date()

        # Momentum: close vs MA20
        ma20 = close.iloc[i - window : i].mean()
        momentum = ((close.iloc[i] - ma20) / ma20) * 100
        momentum_score = min(100.0, max(0.0, 50.0 + momentum * 5))

        # Volatility: ATR/close
        recent = close.iloc[i - window : i + 1]
        returns = recent.pct_change(fill_method=None).dropna()
        vol = float(returns.std() * 100) if len(returns) > 1 else 0.0
        vol_score = min(100.0, max(0.0, 100.0 - vol * 20))

        # Volume: current vs average
        vol_avg = volume.iloc[i - window : i].mean()
        vol_ratio = float(volume.iloc[i] / vol_avg) if vol_avg > 0 else 1.0
        vol_ratio_score = min(100.0, max(0.0, vol_ratio * 50))

        # Composite
        fgi = (momentum_score * 0.4 + vol_score * 0.35 + vol_ratio_score * 0.25)
        fgi = round(min(100.0, max(0.0, fgi)), 2)

        if fgi >= 75:
            label = "Extreme Greed"
        elif fgi >= 55:
            label = "Greed"
        elif fgi >= 45:
            label = "Neutral"
        elif fgi >= 25:
            label = "Fear"
        else:
            label = "Extreme Fear"

        session.add(
            FearGreed(
                tanggal=date_val,
                nilai=fgi,
                label=label,
            )
        )
        count += 1

    session.commit()
    return count


def recompute_stock_personality(session: Session, dry_run: bool = False) -> int:
    """Clear and recompute stock_personality from OHLCV."""
    tickers = _load_all_idx_tickers(session)
    logger.info("Recomputing stock_personality for %d tickers", len(tickers))

    if dry_run:
        return len(tickers)

    # Clear existing
    session.execute(text("DELETE FROM stock_personality"))
    session.commit()

    profiler = InstrumentProfiler()
    ihsg_df = _load_ohlcv_df(session, IHSG_TICKER)

    count = 0
    for ticker in tickers:
        df = _load_ohlcv_df(session, ticker)
        if df.empty or len(df) < 20:
            continue

        profile = profiler.profile(ticker, df, ihsg_df=ihsg_df)

        labels = [lbl.value for lbl in profile.personality_labels]
        primary_label = labels[0] if labels else "unknown"

        session.add(
            StockPersonality(
                ticker=ticker,
                volatility_regime=profile.volatility_regime.value,
                trend_bias=profile.trend_bias,
                beta_vs_ihsg=profile.beta_vs_ihsg,
                liquidity_score=profile.liquidity_score,
                personality_label=primary_label,
            )
        )
        count += 1

        if count % 100 == 0:
            session.commit()
            logger.info("stock_personality: %d", count)

    session.commit()
    return count


def run_all_recompute(session: Session, dry_run: bool = False) -> dict[str, int]:
    """Run all recompute functions."""
    results: dict[str, int] = {}
    functions = [
        ("technical_indicators", recompute_technical_indicators),
        ("scores", recompute_scores),
        ("relationship_matrix", recompute_relationship_matrix),
        ("fear_greed", recompute_fear_greed),
        ("stock_personality", recompute_stock_personality),
    ]

    for name, func in functions:
        logger.info("Recomputing %s...", name)
        try:
            count = func(session, dry_run=dry_run)
            results[name] = count
            logger.info("  %s: %d rows", name, count)
        except Exception as exc:
            logger.error("  %s FAILED: %s", name, exc)
            results[name] = -1
            session.rollback()

    return results


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    dry = "--dry-run" in sys.argv
    session = get_sessionmaker()()
    try:
        summary = run_all_recompute(session, dry_run=dry)
        print("\nRecompute summary:")
        for name, count in summary.items():
            status = f"{count} rows" if count >= 0 else "FAILED"
            print(f"  {name}: {status}")
    finally:
        session.close()
