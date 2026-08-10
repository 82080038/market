"""Batch compute ML signals + predictions for ALL tickers in stock_personality.

Usage:
    .venv/bin/python3 scripts/batch_compute_predictions.py [--limit N] [--tickers A.JK,B.JK]

This script:
1. Loads OHLCV for each ticker from DB
2. Computes ML signals (MLSignalProvider + MultiFactorModel) → ml_signal, multifactor_signal, composite_signal
3. Computes predictions (PredictionEngine ensemble + MarketContextProvider) → predicted_direction, predicted_price, etc.
4. Saves all results to stock_personality table

Designed to run weekly (after fast_portfolio_pipeline) or on-demand.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_ohlcv_from_db(conn: sqlite3.Connection, ticker: str) -> pd.DataFrame:
    """Load OHLCV data for a ticker from DB."""
    df = pd.read_sql_query(
        "SELECT timestamp, open, high, low, close, volume, adjusted_close "
        "FROM ohlcv WHERE ticker=? AND timeframe='1d' ORDER BY timestamp",
        conn, params=(ticker,), parse_dates=["timestamp"],
    )
    if df.empty:
        return df
    df = df.set_index("timestamp")
    # Use adjusted_close if available
    if "adjusted_close" in df.columns and df["adjusted_close"].notna().any():
        df["close"] = df["adjusted_close"].fillna(df["close"])
    return df


def compute_ml_signals(
    ticker: str,
    ohlcv: pd.DataFrame,
    as_of: str,
) -> dict:
    """Compute ML signal (MLSignalProvider) + MultiFactor signal, blend 40/60."""
    from market.analysis.ml_signal import MLSignalProvider
    from market.analysis.multi_factor import MultiFactorModel

    result = {
        "ml_signal": 0.0,
        "multifactor_signal": 0.0,
        "composite_signal": 0.0,
        "top_factors": None,
    }

    if len(ohlcv) < 200:
        return result

    # ML Signal
    ml_provider = MLSignalProvider(horizon=5, min_train_samples=200)
    ml_sig = ml_provider.train_and_predict(ticker, ohlcv, as_of)
    result["ml_signal"] = round(ml_sig.signal, 4)

    # MultiFactor
    mf_model = MultiFactorModel(horizon=5, min_train_samples=200)
    mf_pred = mf_model.train_and_predict(ticker, ohlcv, as_of)
    result["multifactor_signal"] = round(mf_pred.signal, 4)

    # Blend: 40% ML + 60% MultiFactor
    if ml_sig.model_available and mf_pred.model_available:
        result["composite_signal"] = round(
            ml_sig.signal * 0.4 + mf_pred.signal * 0.6, 4
        )
    elif mf_pred.model_available:
        result["composite_signal"] = round(mf_pred.signal, 4)
    elif ml_sig.model_available:
        result["composite_signal"] = round(ml_sig.signal, 4)

    # Top factors
    if mf_pred.top_features:
        result["top_factors"] = json.dumps(
            {k: round(float(v), 4) for k, v in list(mf_pred.top_features.items())[:10]}
        )

    return result


def compute_prediction(
    ticker: str,
    ohlcv: pd.DataFrame,
    as_of: str,
) -> dict:
    """Compute prediction using PredictionEngine + MarketContextProvider."""
    from market.analysis.prediction import PredictionEngine, PredictionMethod
    from market.analysis.market_context import MarketContextProvider
    from market.analysis.ml_signal import MLSignalProvider
    from market.analysis.multi_factor import MultiFactorModel

    result = {
        "predicted_direction": "",
        "predicted_price": 0.0,
        "predicted_return_pct": 0.0,
        "prediction_confidence": 0.0,
        "factors_summary": None,
    }

    if len(ohlcv) < 50:
        return result

    ml_provider = MLSignalProvider(horizon=5, min_train_samples=200)
    mf_model = MultiFactorModel(horizon=5, min_train_samples=200)
    ctx_provider = MarketContextProvider(
        ml_provider=ml_provider,
        multifactor_model=mf_model,
    )

    engine = PredictionEngine(
        horizon=5,
        context_provider=ctx_provider,
    )

    pred = engine.predict(
        ticker, ohlcv, as_of=as_of,
        method=PredictionMethod.ENSEMBLE,
    )

    result["predicted_direction"] = pred.predicted_direction
    result["predicted_price"] = round(pred.predicted_price, 2)
    result["predicted_return_pct"] = round(pred.predicted_return_pct, 4)
    result["prediction_confidence"] = round(pred.confidence, 3)

    # Extract factors from market context
    try:
        ctx = ctx_provider.get_context(ticker, as_of, df=ohlcv, strict_cutoff=True)
        if ctx.is_available:
            result["factors_summary"] = json.dumps({
                "fundamental": round(float(ctx.fundamental_signal()), 3),
                "macro": round(float(ctx.macro_signal()), 3),
                "sentiment": round(float(ctx.sentiment_signal()), 3),
                "flow": round(float(ctx.flow_signal()), 3),
                "ml": round(float(ctx.ml_signal or 0.0), 3),
                "pe_ratio": float(ctx.pe_ratio) if ctx.pe_ratio is not None else None,
                "vix": float(ctx.vix) if ctx.vix is not None else None,
                "fear_greed": float(ctx.fear_greed_index) if ctx.fear_greed_index is not None else None,
                "foreign_net_5d": float(ctx.foreign_net_flow_5d) if ctx.foreign_net_flow_5d is not None else None,
            })
    except Exception:
        pass

    return result


def save_to_db(
    conn: sqlite3.Connection,
    ticker: str,
    ml: dict,
    pred: dict,
) -> None:
    """Save ML signals + prediction to stock_prediction + stock_personality."""
    from datetime import datetime
    now = datetime.now().isoformat()

    # Write to stock_prediction (new split table)
    conn.execute("""
        INSERT OR REPLACE INTO stock_prediction
            (ticker, predicted_direction, predicted_price, predicted_return_pct,
             prediction_confidence, ml_signal, multifactor_signal,
             composite_signal, factors_summary, prediction_updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ticker,
        pred["predicted_direction"],
        pred["predicted_price"],
        pred["predicted_return_pct"],
        pred["prediction_confidence"],
        ml["ml_signal"],
        ml["multifactor_signal"],
        ml["composite_signal"],
        ml["top_factors"],
        now,
    ))

    # Also update stock_personality for backward compat
    conn.execute("""
        UPDATE stock_personality SET
            ml_signal = ?,
            multifactor_signal = ?,
            composite_signal = ?,
            factors_summary = COALESCE(?, factors_summary),
            predicted_direction = ?,
            predicted_price = ?,
            predicted_return_pct = ?,
            prediction_confidence = ?,
            prediction_updated_at = ?
        WHERE ticker = ?
    """, (
        ml["ml_signal"],
        ml["multifactor_signal"],
        ml["composite_signal"],
        ml["top_factors"],
        pred["predicted_direction"],
        pred["predicted_price"],
        pred["predicted_return_pct"],
        pred["prediction_confidence"],
        now,
        ticker,
    ))
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch compute predictions for all tickers")
    parser.add_argument("--db", default="data/market_research.db", help="Database path")
    parser.add_argument("--tickers", default="", help="Comma-separated tickers (default: all)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of tickers (0=all)")
    parser.add_argument("--as-of", default="", help="As-of date (default: latest OHLCV date)")
    parser.add_argument("--skip-ml", action="store_true", help="Skip ML signal computation")
    parser.add_argument("--skip-pred", action="store_true", help="Skip prediction computation")
    args = parser.parse_args()

    db_path = args.db
    conn_ro = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    # Get tickers
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
    else:
        rows = conn_ro.execute(
            "SELECT ticker FROM stock_personality ORDER BY ticker"
        ).fetchall()
        tickers = [r[0] for r in rows]

    if args.limit > 0:
        tickers = tickers[:args.limit]

    # Get as_of date
    if args.as_of:
        as_of = args.as_of
    else:
        r = conn_ro.execute(
            "SELECT MAX(timestamp) FROM ohlcv WHERE timeframe='1d'"
        ).fetchone()
        as_of = str(r[0]) if r and r[0] else None

    logger.info("=" * 76)
    logger.info("BATCH COMPUTE PREDICTIONS")
    logger.info("=" * 76)
    logger.info("DB: %s", db_path)
    logger.info("Tickers: %d", len(tickers))
    logger.info("As-of: %s", as_of)
    logger.info("Skip ML: %s, Skip Pred: %s", args.skip_ml, args.skip_pred)
    logger.info("")

    # Writable connection
    conn_rw = sqlite3.connect(db_path)

    # ModelRegistry: track model versions for each ticker
    try:
        from market.mlops.registry import ModelRegistry, ModelAlias
        registry = ModelRegistry()
        use_registry = True
    except Exception:
        use_registry = False

    t0 = time.time()
    n_ok = 0
    n_err = 0
    n_ml_ok = 0
    n_pred_ok = 0

    for i, ticker in enumerate(tickers):
        try:
            ohlcv = load_ohlcv_from_db(conn_ro, ticker)
            if len(ohlcv) < 50:
                n_err += 1
                continue

            ml = {"ml_signal": 0.0, "multifactor_signal": 0.0, "composite_signal": 0.0, "top_factors": None}
            pred = {"predicted_direction": "", "predicted_price": 0.0, "predicted_return_pct": 0.0, "prediction_confidence": 0.0, "factors_summary": None}

            if not args.skip_ml:
                ml = compute_ml_signals(ticker, ohlcv, as_of)
                if ml["composite_signal"] != 0.0:
                    n_ml_ok += 1

            if not args.skip_pred:
                pred = compute_prediction(ticker, ohlcv, as_of)
                if pred["predicted_direction"]:
                    n_pred_ok += 1

            save_to_db(conn_rw, ticker, ml, pred)

            # Register model version in registry
            if use_registry and ml["composite_signal"] != 0.0:
                from datetime import datetime, UTC
                registry.register(
                    model_id=f"{ticker}_ml_v1",
                    model_type="lightgbm_ml",
                    version="1.0",
                    metrics={
                        "ml_signal": ml["ml_signal"],
                        "multifactor_signal": ml["multifactor_signal"],
                        "composite_signal": ml["composite_signal"],
                    },
                    trained_at=datetime.now(UTC).isoformat(),
                    device="cpu",
                    n_samples=len(ohlcv),
                    alias=ModelAlias.EXPERIMENT,
                )

            n_ok += 1

            if (i + 1) % 50 == 0 or (i + 1) == len(tickers):
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (len(tickers) - i - 1) / rate if rate > 0 else 0
                logger.info(
                    "  [%d/%d] %s — ml=%+.3f pred=%s %.1f%% — %.1fs elapsed, %.0fs ETA",
                    i + 1, len(tickers), ticker,
                    ml["composite_signal"],
                    pred["predicted_direction"] or "-",
                    pred["predicted_return_pct"],
                    elapsed, eta,
                )

        except Exception as e:
            n_err += 1
            logger.debug("  ERROR %s: %s", ticker, e)

    conn_rw.close()
    conn_ro.close()

    elapsed = time.time() - t0
    logger.info("")
    logger.info("=" * 76)
    logger.info("BATCH COMPLETE — %.1fs", elapsed)
    logger.info("  Total: %d | OK: %d | Errors: %d", len(tickers), n_ok, n_err)
    logger.info("  ML signals non-zero: %d/%d (%.1f%%)", n_ml_ok, n_ok, n_ml_ok / max(n_ok, 1) * 100)
    logger.info("  Predictions generated: %d/%d (%.1f%%)", n_pred_ok, n_ok, n_pred_ok / max(n_ok, 1) * 100)
    logger.info("=" * 76)


if __name__ == "__main__":
    main()
