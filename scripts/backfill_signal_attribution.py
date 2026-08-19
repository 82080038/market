#!/usr/bin/env python3
"""Backfill signal_attribution_log with per-engine signals for all tickers.

For each trading day and each ticker, computes signals from all available
analysis engines and records them in signal_attribution_log. Forward returns
(1d, 3d, 5d, 10d) are filled in a second pass once price data is available.

Engines logged:
  1. technical        — TechnicalAnalysisEngine (RSI, MACD, BB, ATR)
  2. fundamental      — FundamentalAnalysisEngine (P/E, P/B, ROE, debt ratio)
  3. macro            — MacroEconomicEngine (BI rate, inflation, GDP)
  4. sentiment        — SentimentEngine (fear/greed, news sentiment)
  5. relationship     — MarketRelationshipEngine (cross-market correlation)
  6. global           — GlobalMarketEngine (global index signals)
  7. alpha            — Alpha signal engines (mean reversion, reversal, EWMA, regime)
  8. astronacci       — AstronacciEngine (astrology + Fibonacci confluence)
  9. ml               — MLSignalProvider (LSTM prediction)
 10. volume           — VolumeFeatures (OFI, VWAP deviation, OBV)
 11. policy_event     — PolicyEventScorer (BI/Fed rate, buyback, rights issue)
 12. sector_rotation  — SectorRotationEngine (sector momentum)
 13. pairs_trading    — PairsTradingEngine (cointegration z-score)
 14. meta_label       — MetaLabeler (bet sizing probability)
 15. news_sentiment   — NewsSentimentAnalyzer (RSS news sentiment)
 16. holiday_effect   — HolidayEffectAnalyzer (pre/post-holiday effect)
 17. market_influence — MarketInfluenceKB (market influence knowledge base)

Usage:
    python scripts/backfill_signal_attribution.py --days 250 --tickers BBCA.JK,BBRI.JK,^JKSE
    python scripts/backfill_signal_attribution.py --days 250 --all-idx
    python scripts/backfill_signal_attribution.py --fill-returns  # backfill fwd returns only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
warnings.filterwarnings("ignore", message=".*not converging.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)


def get_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://petrick:market_dev@localhost:5432/market")
    return url


def get_trading_dates(conn, start_date, end_date, ticker="^JKSE"):
    """Get trading dates from stock_prices table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT timestamp::date FROM stock_prices
            WHERE ticker = %s AND timeframe = '1d'
              AND timestamp::date BETWEEN %s AND %s
            ORDER BY timestamp::date
        """, (ticker, start_date, end_date))
        return [r[0] for r in cur.fetchall()]


def load_prices(conn, ticker, as_of_date, lookback=300):
    """Load OHLCV data up to as_of_date."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM stock_prices
            WHERE ticker = %s AND timeframe = '1d'
              AND timestamp <= %s
            ORDER BY timestamp DESC LIMIT %s
        """, (ticker, as_of_date, lookback))
        rows = cur.fetchall()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def compute_engine_signals(df, ticker, as_of_date, conn=None):
    """Compute signals from all available engines for a single ticker/date.

    Returns list of dicts: {engine_name, signal_value, signal_direction, confidence, rationale, metadata_json}
    """
    signals = []
    as_of_ts = pd.Timestamp(as_of_date)
    if as_of_ts.tzinfo is None:
        as_of_ts = as_of_ts.tz_localize("UTC")
    else:
        as_of_ts = as_of_ts.tz_convert("UTC")
    as_of_dt = as_of_ts.to_pydatetime()
    close_series = df["close"].copy()

    # --- 1. Technical ---
    # NOTE: IC analysis shows technical score is INVERTED over 5-day horizon.
    # High technical score (uptrend+RSI high) → price tends to FALL (mean reversion).
    # This is because IDX exhibits mean-reversion over 5-day horizons.
    # Fix: invert the signal so it aligns with actual forward returns.
    try:
        from market.analysis.technical import TechnicalAnalysisEngine
        eng = TechnicalAnalysisEngine()
        result = eng.analyze(ticker, df)
        raw_score = float(result.score) / 100.0 - 0.5  # [0,100] -> [-0.5,0.5]
        sig = -raw_score  # INVERT: momentum score → mean-reversion signal
        direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
        signals.append({
            "engine_name": "technical",
            "signal_value": round(sig, 4),
            "signal_direction": direction,
            "confidence": 0.6,
            "rationale": f"score={result.score:.1f}, trend={result.trend}, INVERTED (mean-reversion)",
            "metadata_json": json.dumps({"score": result.score, "raw_signal": raw_score, "inverted": True, "trend": result.trend, "breakdown": result.breakdown}),
        })
    except Exception:
        pass

    # --- 2. Fundamental ---
    try:
        from market.analysis.fundamental import FundamentalAnalysisEngine
        eng = FundamentalAnalysisEngine()
        result = eng.analyze(ticker)
        sig = float(result.score) / 100.0 - 0.5
        direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
        signals.append({
            "engine_name": "fundamental",
            "signal_value": round(sig, 4),
            "signal_direction": direction,
            "confidence": 0.5,
            "rationale": f"status={result.status}",
            "metadata_json": json.dumps({"score": result.score, "status": result.status, "ratios": result.ratios}),
        })
    except Exception:
        pass

    # --- 3. Macro ---
    # Wire macro engine with DB data: US10Y, gold, oil, USD/IDR from macro_data table
    try:
        from market.analysis.macro import MacroEconomicEngine
        eng = MacroEconomicEngine()
        macro_kwargs = {}
        if conn is not None:
            with conn.cursor() as cur:
                for series, field_curr, field_prev in [
                    ('US_10Y', 'us10y_yield', 'us10y_prev'),
                    ('GOLD', 'gold_price', 'gold_prev'),
                    ('CRUDE_OIL', 'oil_price', 'oil_prev'),
                    ('USD_IDR', 'usd_idr', 'usd_idr_prev'),
                ]:
                    cur.execute("""
                        SELECT value FROM macro_data
                        WHERE series_name = %s AND date <= %s
                        ORDER BY date DESC LIMIT 2
                    """, (series, as_of_dt))
                    rows = cur.fetchall()
                    if len(rows) >= 1:
                        macro_kwargs[field_curr] = float(rows[0][0])
                    if len(rows) >= 2:
                        macro_kwargs[field_prev] = float(rows[1][0])
        result = eng.analyze(**macro_kwargs)
        sig = float(result.score) / 100.0 - 0.5
        direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
        signals.append({
            "engine_name": "macro",
            "signal_value": round(sig, 4),
            "signal_direction": direction,
            "confidence": 0.5,
            "rationale": f"regime={result.regime}, inputs={list(macro_kwargs.keys())}",
            "metadata_json": json.dumps({"score": result.score, "regime": result.regime, "breakdown": result.breakdown, "inputs": macro_kwargs}),
        })
    except Exception:
        pass

    # --- 4. Sentiment ---
    # Wire sentiment with news_sentiment + foreign_flow from DB
    try:
        from market.analysis.sentiment import SentimentEngine
        eng = SentimentEngine()
        sentiment_kwargs = {"ticker": ticker}
        if conn is not None:
            with conn.cursor() as cur:
                # News sentiment: avg sentiment_score for ticker in last 7 days
                cur.execute("""
                    SELECT AVG(sentiment_score), COUNT(*) FROM news_sentiment
                    WHERE ticker = %s AND date >= %s - INTERVAL '7 days' AND date <= %s
                """, (ticker, as_of_dt, as_of_dt))
                row = cur.fetchone()
                if row and row[0] is not None and row[1] > 0:
                    # Convert sentiment_score (-1 to 1) to 0-100 scale
                    news_score = 50.0 + float(row[0]) * 50.0
                    sentiment_kwargs["news_texts"] = []  # trigger news_nlp weight
                    sentiment_kwargs["historical_score"] = news_score
                # Foreign flow: net foreign buy/sell in last 5 days
                cur.execute("""
                    SELECT SUM(CASE WHEN foreign_buy > 0 THEN foreign_buy ELSE 0 END) -
                           SUM(CASE WHEN foreign_sell > 0 THEN foreign_sell ELSE 0 END)
                    FROM foreign_flow
                    WHERE ticker = %s AND date >= %s - INTERVAL '5 days' AND date <= %s
                """, (ticker, as_of_dt, as_of_dt))
                ff_row = cur.fetchone()
                if ff_row and ff_row[0] is not None:
                    ff_val = float(ff_row[0])
                    # Convert to 0-100: positive flow = bullish (>50), negative = bearish (<50)
                    ff_score = 50.0 + max(-50.0, min(50.0, ff_val / 1e10 * 50.0))
                    sentiment_kwargs["foreign_flow_score"] = ff_score
        result = eng.analyze(**sentiment_kwargs)
        sig = float(result.score) / 100.0 - 0.5
        direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
        signals.append({
            "engine_name": "sentiment",
            "signal_value": round(sig, 4),
            "signal_direction": direction,
            "confidence": 0.5,
            "rationale": f"label={result.label}, sources={list(result.sources.keys())}",
            "metadata_json": json.dumps({"score": result.score, "label": result.label, "sources": result.sources, "breakdown": result.breakdown}),
        })
    except Exception:
        pass

    # --- 5. Relationship ---
    # Wire with market index returns as reference
    try:
        from market.analysis.relationship import MarketRelationshipEngine
        eng = MarketRelationshipEngine()
        # Signature: analyze(ticker, target_returns, reference_returns: dict[str, pd.Series])
        ref_returns_dict = {}
        if conn is not None:
            with conn.cursor() as cur:
                for ref_ticker in ['^JKSE', '^GSPC', '^HSI']:
                    cur.execute("""
                        SELECT timestamp, close FROM stock_prices
                        WHERE ticker = %s AND timeframe = '1d'
                        AND timestamp <= %s ORDER BY timestamp DESC LIMIT 60
                    """, (ref_ticker, as_of_dt))
                    rows = cur.fetchall()
                    if len(rows) >= 30:
                        mkt_df = pd.DataFrame(rows, columns=['timestamp', 'close'])
                        mkt_df = mkt_df.sort_values('timestamp')
                        mkt_df['close'] = pd.to_numeric(mkt_df['close'], errors='coerce')
                        ref_returns_dict[ref_ticker] = mkt_df['close'].pct_change().dropna()
        if ref_returns_dict:
            ticker_returns = close_series.pct_change().dropna()
            result = eng.analyze(ticker, ticker_returns, ref_returns_dict)
            # Use weighted correlation sign for directional signal
            # score = avg |corr| * 100 (influence magnitude, 0-100)
            # For direction: use sign of latest correlation with each ref, weighted by |corr|
            weighted_dir = 0.0
            total_weight = 0.0
            for rel in result.relationships:
                corr = float(rel.get("correlation", 0))
                weighted_dir += corr  # positive corr = same direction, negative = inverse
                total_weight += 1.0
            if total_weight > 0:
                avg_corr = weighted_dir / total_weight
                # Signal: positive avg corr + market up → bullish; negative → bearish
                # Use ^JKSE recent return as market direction proxy
                mkt_ret = 0.0
                if '^JKSE' in ref_returns_dict and len(ref_returns_dict['^JKSE']) > 0:
                    mkt_ret = float(ref_returns_dict['^JKSE'].iloc[-1]) if len(ref_returns_dict['^JKSE']) > 0 else 0.0
                sig = max(-0.5, min(0.5, avg_corr * mkt_ret * 100))  # scale corr*market_return
            else:
                sig = 0.0
        else:
            sig = 0.0
        direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
        signals.append({
            "engine_name": "relationship",
            "signal_value": round(sig, 4) if not (sig != sig) else 0.0,  # NaN check
            "signal_direction": direction,
            "confidence": 0.4 if sig != 0 else 0.3,
            "rationale": f"refs={list(ref_returns_dict.keys())}, avg_corr={sig:.3f}",
            "metadata_json": json.dumps({"ref_tickers": list(ref_returns_dict.keys()), "relationships": result.relationships[:3] if result.relationships else []}),
        })
    except Exception:
        pass

    # --- 6. Global ---
    # Wire with global index returns from DB
    try:
        from market.analysis.global_market import GlobalMarketEngine
        eng = GlobalMarketEngine()
        # Signature: analyze(data: dict[str, pd.DataFrame])
        global_data = {}
        if conn is not None:
            with conn.cursor() as cur:
                for idx_ticker in ['^GSPC', '^N225', '^HSI', '^FTSE']:
                    cur.execute("""
                        SELECT timestamp, close FROM stock_prices
                        WHERE ticker = %s AND timeframe = '1d'
                        AND timestamp <= %s ORDER BY timestamp DESC LIMIT 60
                    """, (idx_ticker, as_of_dt))
                    rows = cur.fetchall()
                    if len(rows) >= 20:
                        gdf = pd.DataFrame(rows, columns=['timestamp', 'close'])
                        gdf = gdf.sort_values('timestamp')
                        gdf['close'] = pd.to_numeric(gdf['close'], errors='coerce')
                        global_data[idx_ticker] = gdf
        if global_data:
            result = eng.analyze(global_data)
            sig = float(result.score) / 100.0 - 0.5
        else:
            sig = 0.0
        direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
        signals.append({
            "engine_name": "global",
            "signal_value": round(sig, 4),
            "signal_direction": direction,
            "confidence": 0.4 if sig != 0 else 0.3,
            "rationale": f"global_indices={list(global_data.keys())}",
            "metadata_json": json.dumps({"global_indices": list(global_data.keys())}),
        })
    except Exception:
        pass

    # --- 7. Alpha (4 sub-engines) ---
    try:
        from market.analysis.alpha_signals import (
            MeanReversionEngine, ShortTermReversalEngine,
            EWMAMomentumEngine, RegimeSwitchEngine,
        )
        for name, cls, params in [
            ("alpha_mean_reversion", MeanReversionEngine, {"bb_n_std": 1.5, "rsi_oversold": 35, "rsi_overbought": 65}),
            ("alpha_reversal", ShortTermReversalEngine, {"z_threshold": 1.0}),
            ("alpha_ewma_momentum", EWMAMomentumEngine, {}),
            ("alpha_regime_switch", RegimeSwitchEngine, {}),
        ]:
            try:
                eng = cls(**params)
                result = eng.generate_signals(close_series)
                # SignalResult.signal is a pd.Series — take last value (as_of date)
                sig = float(result.signal.iloc[-1]) if hasattr(result.signal, 'iloc') else float(result.signal)
                conf = float(result.confidence.iloc[-1]) if hasattr(result.confidence, 'iloc') else float(result.confidence)
                direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
                signals.append({
                    "engine_name": name,
                    "signal_value": round(sig, 4),
                    "signal_direction": direction,
                    "confidence": conf,
                    "rationale": json.dumps(result.metadata) if result.metadata else "",
                    "metadata_json": json.dumps({"signal": sig, "confidence": conf, "metadata": result.metadata}),
                })
            except Exception:
                pass
    except Exception:
        pass

    # --- 8. Astronacci ---
    try:
        from market.analysis.astronacci import compute_astronacci_signal
        current_price = float(df["close"].iloc[-1])
        prices_df = df[["timestamp", "close"]].copy()
        result = compute_astronacci_signal(
            as_of_dt, window_days=3, prices=prices_df, current_price=current_price,
        )
        raw_sig = float(result.get("time_signal", 0))
        # INVERT: IC analysis shows astronacci signal is inverted (IC=-0.22).
        # BULLISH_REVERSAL → price actually goes DOWN, BEARISH_REVERSAL → price goes UP.
        # This is consistent with mean-reversion: astrology predicts reversal direction,
        # but the actual reversal is opposite to what the cycle type suggests.
        sig = -raw_sig
        direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
        confl = result.get("confluence")
        meta = {"cycle_count": result.get("cycle_count", 0), "active_cycles": result.get("active_cycles", []), "raw_signal": raw_sig, "inverted": True}
        if confl:
            meta["confluence"] = confl
        signals.append({
            "engine_name": "astronacci",
            "signal_value": round(sig, 4),
            "signal_direction": direction,
            "confidence": float(result.get("confidence", 0.3)),
            "rationale": f"cycles={result.get('cycle_count', 0)}, confluence={'YES' if confl and confl.get('matched') else 'NO'}, INVERTED",
            "metadata_json": json.dumps(meta, default=str),
        })
    except Exception:
        pass

    # --- 9. ML (SKIP in batch mode — too expensive) ---
    # MLSignalProvider.train_and_predict() trains LSTM from scratch per call.
    # Not suitable for batch backfill. ML signals should be logged separately
    # by the daily cron when it runs predictions.

    # --- 10. Volume ---
    try:
        from market.analysis.volume_features import compute_ofi_proxy, compute_vwap
        # compute_ofi_proxy(close, volume, high, low)
        ofi_result = compute_ofi_proxy(df['close'], df['volume'], df['high'], df['low'])
        # compute_vwap(high, low, close, volume, window=20)
        vwap_result = compute_vwap(df['high'], df['low'], df['close'], df['volume'])
        # Normalize OFI using percentile rank (more robust than absolute scaling)
        ofi_series = ofi_result.ofi
        ofi_val = float(ofi_series.iloc[-1]) if hasattr(ofi_series, 'iloc') else float(ofi_series)
        vwap_dev_series = vwap_result.deviation
        vwap_dev = float(vwap_dev_series.iloc[-1]) if hasattr(vwap_dev_series, 'iloc') else float(vwap_dev_series)
        # Use rolling percentile rank for OFI
        if hasattr(ofi_series, 'rank'):
            ofi_rank = float(ofi_series.rank(pct=True).iloc[-1])
        else:
            ofi_rank = 0.5
        # OFI percentile: >0.5 = buying pressure, <0.5 = selling pressure
        ofi_sig = (ofi_rank - 0.5) * 2.0  # [-1, 1]
        # VWAP deviation: above VWAP = bullish, below = bearish
        vwap_sig = max(-1.0, min(1.0, vwap_dev * 10))  # scale deviation
        sig = max(-1.0, min(1.0, 0.6 * ofi_sig + 0.4 * vwap_sig))
        direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
        signals.append({
            "engine_name": "volume",
            "signal_value": round(sig, 4),
            "signal_direction": direction,
            "confidence": 0.5,
            "rationale": f"OFI={ofi_val:.2f}, VWAP_dev={vwap_dev:.4f}",
            "metadata_json": json.dumps({"ofi": ofi_val, "vwap_deviation": vwap_dev}),
        })
    except Exception:
        pass

    # --- 11. Policy Event ---
    try:
        from datetime import timezone as _tz
        from market.analysis.policy_event_scorer import PolicyEventScorer
        eng = PolicyEventScorer()
        eng.load()  # loads from DB (policy_events + external_events + corporate_calendar)
        # Pass timezone-aware datetime
        as_of_aware = as_of_dt.replace(tzinfo=_tz.utc) if as_of_dt.tzinfo is None else as_of_dt
        result = eng.compute_event_signal(ticker, as_of_aware)
        if result is not None:
            # PolicyEventScorer returns .score (not .signal), .direction, .confidence
            raw_score = float(getattr(result, 'score', 0.0))
            # Normalize score to [-1, 1] — typical range is -10 to +10
            sig = max(-1.0, min(1.0, raw_score / 10.0))
            direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
            signals.append({
                "engine_name": "policy_event",
                "signal_value": round(sig, 4),
                "signal_direction": direction,
                "confidence": float(getattr(result, 'confidence', 0.5)),
                "rationale": f"score={raw_score:.3f}, dir={getattr(result, 'direction', 'neutral')}",
                "metadata_json": json.dumps({"raw_score": raw_score, "direction": getattr(result, 'direction', 'neutral'), "market_wide": getattr(result, 'market_wide_score', 0), "ticker_specific": getattr(result, 'ticker_specific_score', 0)}),
            })
    except Exception:
        pass

    # --- 12. Sector Rotation ---
    try:
        from market.analysis.sector_rotation import SectorRotationEngine
        eng = SectorRotationEngine()
        recs = eng.recommend_sectors(prices=df[["close"]].copy())
        if recs:
            top = recs[0]
            sig = float(top.score) / 100.0 - 0.5
            direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
            signals.append({
                "engine_name": "sector_rotation",
                "signal_value": round(sig, 4),
                "signal_direction": direction,
                "confidence": 0.5,
                "rationale": f"sector={top.sector}, score={top.score:.1f}",
                "metadata_json": json.dumps({"sector": top.sector, "score": top.score}),
            })
    except Exception:
        pass

    # --- 13. Holiday Effect ---
    # Compute pre/post-holiday effect directly from exchange_holidays + stock_prices
    try:
        sig = 0.0
        holiday_meta = {}
        if conn is not None:
            with conn.cursor() as cur:
                # Check if next trading day is a holiday (pre-holiday effect)
                cur.execute("""
                    SELECT holiday_date, holiday_name FROM exchange_holidays
                    WHERE exchange_mic = 'XIDX'
                    AND holiday_date > %s
                    ORDER BY holiday_date ASC LIMIT 1
                """, (as_of_dt.date() if hasattr(as_of_dt, 'date') else as_of_dt,))
                next_holiday = cur.fetchone()
                if next_holiday:
                    days_to_holiday = (next_holiday[0] - (as_of_dt.date() if hasattr(as_of_dt, 'date') else as_of_dt)).days
                    if days_to_holiday <= 3:
                        # Pre-holiday: compute avg return 1 day before holidays
                        # Use simple heuristic: pre-holiday tends to be slightly bullish
                        # (window dressing, reduced selling)
                        sig = 0.1 * (1.0 - days_to_holiday / 4.0)  # stronger as holiday approaches
                        holiday_meta = {"next_holiday": str(next_holiday[0]), "name": next_holiday[1], "days_to_holiday": days_to_holiday}
                # Check if today is post-holiday (first trading day after holiday)
                cur.execute("""
                    SELECT holiday_date, holiday_name FROM exchange_holidays
                    WHERE exchange_mic = 'XIDX'
                    AND holiday_date < %s
                    ORDER BY holiday_date DESC LIMIT 1
                """, (as_of_dt.date() if hasattr(as_of_dt, 'date') else as_of_dt,))
                prev_holiday = cur.fetchone()
                if prev_holiday:
                    days_after = ((as_of_dt.date() if hasattr(as_of_dt, 'date') else as_of_dt) - prev_holiday[0]).days
                    if days_after <= 2:
                        # Post-holiday: compute actual return vs average
                        if len(df) >= 2:
                            today_ret = float(df['close'].iloc[-1] / df['close'].iloc[-2] - 1) if df['close'].iloc[-2] > 0 else 0
                            # Post-holiday effect: first trading day after holiday tends to be volatile
                            # Use actual return as signal direction
                            sig = max(-0.3, min(0.3, today_ret * 5))  # scale return
                            holiday_meta.update({"prev_holiday": str(prev_holiday[0]), "name": prev_holiday[1], "days_after": days_after, "post_ret": today_ret})
        direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
        signals.append({
            "engine_name": "holiday_effect",
            "signal_value": round(sig, 4),
            "signal_direction": direction,
            "confidence": 0.4,
            "rationale": f"pre_holiday={holiday_meta.get('days_to_holiday', 'N/A')}, post_holiday={holiday_meta.get('days_after', 'N/A')}",
            "metadata_json": json.dumps(holiday_meta),
        })
    except Exception:
        pass

    # --- 14. Market Influence KB ---
    try:
        from market.analysis.market_influence_kb import MarketInfluenceKB
        eng = MarketInfluenceKB()
        # Query active influences for this ticker from DB
        if conn is not None:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT influence_type, direction, strength, source_ticker, mechanism
                    FROM market_influence_kb
                    WHERE target_ticker = %s AND is_active = true
                    ORDER BY strength DESC LIMIT 5
                """, (ticker,))
                influences = cur.fetchall()
            if influences:
                # Aggregate influence signals
                bull_count = sum(1 for i in influences if i[1] == "bullish")
                bear_count = sum(1 for i in influences if i[1] == "bearish")
                total = bull_count + bear_count
                sig = (bull_count - bear_count) / max(total, 1)
                direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
                signals.append({
                    "engine_name": "market_influence",
                    "signal_value": round(sig, 4),
                    "signal_direction": direction,
                    "confidence": min(0.8, total / 10),
                    "rationale": f"{total} active influences ({bull_count} bull, {bear_count} bear)",
                    "metadata_json": json.dumps([{"type": i[0], "dir": i[1], "strength": float(i[2]), "source": i[3]} for i in influences]),
                })
    except Exception:
        pass

    # --- 15. Fama-French 5-Factor ---
    try:
        from market.analysis.fama_french import FamaFrench5Factor
        ff_engine = FamaFrench5Factor()
        # Get market data
        market_df = None
        if conn is not None:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT timestamp, close FROM stock_prices
                    WHERE ticker = '^JKSE' AND timeframe = '1d'
                    AND timestamp <= %s ORDER BY timestamp DESC LIMIT 300
                """, (as_of_dt,))
                rows = cur.fetchall()
                if len(rows) >= 60:
                    import pandas as _pd
                    market_df = _pd.DataFrame(rows, columns=['timestamp', 'close'])
                    market_df = market_df.sort_values('timestamp')
                    for c in market_df.columns:
                        if c != 'timestamp':
                            market_df[c] = pd.to_numeric(market_df[c], errors='coerce')
        # Get fundamentals from DB (column-based, not key-value)
        fundamentals = {}
        if conn is not None:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT pe, pb, roe, revenue_growth, market_cap, return_on_equity
                    FROM fundamental_data
                    WHERE ticker = %s AND date <= %s
                    ORDER BY date DESC LIMIT 1
                """, (ticker, as_of_dt.date() if hasattr(as_of_dt, 'date') else as_of_dt))
                row = cur.fetchone()
                if row:
                    fundamentals = {
                        'pe_ratio': float(row[0]) if row[0] else None,
                        'pb_ratio': float(row[1]) if row[1] else None,
                        'roe': float(row[2]) if row[2] else (float(row[5]) if row[5] else None),
                        'revenue_growth': float(row[3]) if row[3] else None,
                        'market_cap': float(row[4]) if row[4] else None,
                    }
        exposure = ff_engine.compute_signal(ticker, df, market_df=market_df, fundamentals=fundamentals or None)
        sig, conf, rationale = ff_engine.signal_from_exposure(exposure)
        direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
        signals.append({
            "engine_name": "fama_french_5f",
            "signal_value": round(sig, 4),
            "signal_direction": direction,
            "confidence": conf,
            "rationale": rationale,
            "metadata_json": json.dumps({
                "beta_mkt": exposure.beta_mkt, "beta_smb": exposure.beta_smb,
                "beta_hml": exposure.beta_hml, "beta_rmw": exposure.beta_rmw,
                "beta_cma": exposure.beta_cma, "predicted_return": exposure.predicted_return,
                "fundamentals": fundamentals,
            }),
        })
    except Exception:
        pass

    # --- 16. HMM Regime ---
    # Use fallback regime detection (volatility percentile) for performance.
    # HMM fitting takes ~9s per ticker-day; fallback takes <1ms with similar results.
    try:
        from market.analysis.hmm_regime import HMMRegimeDetector
        regime_detector = HMMRegimeDetector()
        # Skip fitting — use fallback directly
        result = regime_detector.detect(close_series)
        if result.regime_name == "trending":
            sig = 0.3 * result.signal_adjustment
        elif result.regime_name == "ranging":
            sig = -0.1
        else:  # crisis
            sig = -0.5
        sig = max(-1.0, min(1.0, sig))
        conf = result.confidence
        rationale = f"regime={result.regime_name}, vol_pctile={result.volatility_pctile:.2f} (fallback)"
        direction = "UP" if sig > 0.05 else "DOWN" if sig < -0.05 else "FLAT"
        signals.append({
            "engine_name": "hmm_regime",
            "signal_value": round(sig, 4),
            "signal_direction": direction,
            "confidence": conf,
            "rationale": rationale,
            "metadata_json": json.dumps({"signal": sig, "confidence": conf, "regime": result.regime_name, "vol_pctile": result.volatility_pctile, "method": "fallback"}),
        })
    except Exception:
        pass

    return signals


def insert_signals(conn, as_of_date, ticker, signals):
    """Insert signals into signal_attribution_log (upsert)."""
    if not signals:
        return 0
    rows = []
    for s in signals:
        rows.append((
            as_of_date,
            ticker,
            s["engine_name"],
            s["signal_value"],
            s["signal_direction"],
            s.get("confidence"),
            s.get("rationale"),
            s.get("metadata_json"),
            False,  # backtest_filled
        ))
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO signal_attribution_log
                (as_of_date, ticker, engine_name, signal_value, signal_direction,
                 confidence, rationale, metadata_json, backtest_filled)
            VALUES %s
            ON CONFLICT (as_of_date, ticker, engine_name) DO UPDATE SET
                signal_value = EXCLUDED.signal_value,
                signal_direction = EXCLUDED.signal_direction,
                confidence = EXCLUDED.confidence,
                rationale = EXCLUDED.rationale,
                metadata_json = EXCLUDED.metadata_json
            """,
            rows,
            page_size=500,
        )
    conn.commit()
    return len(rows)


def fill_forward_returns(conn, as_of_date=None, ticker=None):
    """Fill forward returns and direction_correct for logged signals."""
    with conn.cursor() as cur:
        # Get signals that haven't been backfilled yet
        params = []
        where_clauses = ["backtest_filled = false"]
        if as_of_date:
            where_clauses.append("as_of_date <= %s")
            params.append(as_of_date)
        if ticker:
            where_clauses.append("ticker = %s")
            params.append(ticker)
        where_sql = " AND ".join(where_clauses)

        cur.execute(f"""
            SELECT id, as_of_date, ticker, signal_direction
            FROM signal_attribution_log
            WHERE {where_sql}
            ORDER BY as_of_date DESC, ticker
            LIMIT 5000
        """, params)
        rows = cur.fetchall()

    if not rows:
        return 0

    updates = []
    for row_id, log_date, tk, predicted_dir in rows:
        # Get forward prices
        with conn.cursor() as cur:
            cur.execute("""
                SELECT timestamp::date, close FROM stock_prices
                WHERE ticker = %s AND timeframe = '1d'
                  AND timestamp::date > %s
                ORDER BY timestamp::date ASC LIMIT 11
            """, (tk, log_date))
            price_rows = cur.fetchall()

        if len(price_rows) < 10:
            continue

        # Get close on log_date
        with conn.cursor() as cur:
            cur.execute("""
                SELECT close FROM stock_prices
                WHERE ticker = %s AND timeframe = '1d'
                  AND timestamp::date <= %s
                ORDER BY timestamp::date DESC LIMIT 1
            """, (tk, log_date))
            base_row = cur.fetchone()

        if not base_row:
            continue

        base_price = float(base_row[0])
        if base_price == 0:
            continue

        fwd_returns = {}
        for days, idx in [(1, 0), (3, 2), (5, 4), (10, 9)]:
            if idx < len(price_rows):
                fwd_price = float(price_rows[idx][1])
                fwd_returns[f"fwd_return_{days}d"] = (fwd_price - base_price) / base_price * 100
                actual_up = fwd_returns[f"fwd_return_{days}d"] > 0
                predicted_up = predicted_dir == "UP"
                predicted_down = predicted_dir == "DOWN"
                if predicted_up or predicted_down:
                    fwd_returns[f"direction_correct_{days}d"] = (predicted_up == actual_up)
                else:
                    fwd_returns[f"direction_correct_{days}d"] = None

        if fwd_returns:
            updates.append((row_id, fwd_returns))

    # Batch update
    with conn.cursor() as cur:
        for row_id, fr in updates:
            set_parts = []
            params = []
            for k, v in fr.items():
                if v is None:
                    set_parts.append(f"{k} = NULL")
                else:
                    set_parts.append(f"{k} = %s")
                    params.append(v)
            set_parts.append("backtest_filled = true")
            params.append(row_id)
            cur.execute(
                f"UPDATE signal_attribution_log SET {', '.join(set_parts)} WHERE id = %s",
                params,
            )
    conn.commit()
    return len(updates)


def main():
    parser = argparse.ArgumentParser(description="Backfill signal_attribution_log")
    parser.add_argument("--days", type=int, default=250, help="Number of trading days to backfill")
    parser.add_argument("--tickers", type=str, default="BBCA.JK,BBRI.JK,BMRI.JK,TLKM.JK,ASII.JK,^JKSE",
                        help="Comma-separated tickers")
    parser.add_argument("--all-idx", action="store_true", help="Use all active IDX tickers")
    parser.add_argument("--fill-returns", action="store_true", help="Only fill forward returns for existing rows")
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't insert")
    args = parser.parse_args()

    db_url = get_db_url()
    print(f"Connecting to: {db_url.split('@')[1] if '@' in db_url else db_url}")
    conn = psycopg2.connect(db_url)

    if args.fill_returns:
        print("Filling forward returns for existing signal_attribution_log rows...")
        n = fill_forward_returns(conn)
        print(f"Updated {n} rows with forward returns")
        conn.close()
        return

    # Determine tickers
    if args.all_idx:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT sp.ticker FROM stock_prices sp
                JOIN instruments i ON sp.ticker = i.ticker
                WHERE sp.ticker LIKE '%%.JK' AND sp.timeframe = '1d'
                  AND sp.timestamp >= NOW() - INTERVAL '30 days'
                ORDER BY sp.ticker LIMIT 50
            """)
            tickers = [r[0] for r in cur.fetchall()]
    else:
        tickers = args.tickers.split(",")

    print(f"Tickers: {tickers}")
    print(f"Days: {args.days}")

    # Determine date range
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=args.days + 30)
    trading_dates = get_trading_dates(conn, start_date, end_date)
    # Only use last N dates
    trading_dates = trading_dates[-args.days:]
    print(f"Trading dates: {len(trading_dates)} ({trading_dates[0]} to {trading_dates[-1]})")

    if args.dry_run:
        print("[DRY RUN] Computing signals without inserting...")

    total_signals = 0
    t0 = time.time()

    for i, dt in enumerate(trading_dates):
        for ticker in tickers:
            df = load_prices(conn, ticker, dt)
            if df is None or len(df) < 30:
                continue

            signals = compute_engine_signals(df, ticker, dt, conn=conn)
            if signals:
                if not args.dry_run:
                    inserted = insert_signals(conn, dt, ticker, signals)
                    total_signals += inserted
                else:
                    total_signals += len(signals)

        if (i + 1) % 10 == 0:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(trading_dates)}] {dt} | {total_signals} signals | {elapsed:.1f}s")

    elapsed = time.time() - t0
    print(f"\nTotal signals: {total_signals} in {elapsed:.1f}s")

    # Fill forward returns
    if not args.dry_run:
        print("\nFilling forward returns...")
        n = fill_forward_returns(conn)
        print(f"Updated {n} rows with forward returns")

    # Summary
    if not args.dry_run:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM signal_attribution_log")
            total = cur.fetchone()[0]
            cur.execute("SELECT engine_name, COUNT(*) FROM signal_attribution_log GROUP BY engine_name ORDER BY COUNT(*) DESC")
            print(f"\nsignal_attribution_log: {total} rows")
            for r in cur.fetchall():
                print(f"  {r[0]:25s} {r[1]:6d}")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
