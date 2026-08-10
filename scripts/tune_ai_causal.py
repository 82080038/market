"""AI/ML tuning with comprehensive 7-layer causal features.

Tests the updated MultiFactorModel with:
- Expanded exogenous features (28 global assets vs 11 before)
- Macro features (BI rate, inflation, GDP, real interest rate)
- Fundamental features (PE, PB, ROE, EPS, beta, market cap)

Runs walk-forward backtest on representative tickers and compares
accuracy vs the baseline (Stage 5: 49.3%).

Usage:
    uv run python scripts/tune_ai_causal.py
    uv run python scripts/tune_ai_causal.py --tickers BBCA.JK,BBRI.JK
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from market.analysis.multi_factor import MultiFactorModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PG_URL = "postgresql://petrick:market_dev@localhost:5432/market"

REPRESENTATIVE_TICKERS = [
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK",
    "UNVR.JK", "INDF.JK", "ICBP.JK",
    "INCO.JK", "ANTM.JK",
    "PTBA.JK", "ADRO.JK",
    "TLKM.JK", "UNTR.JK", "KLBF.JK", "CTRA.JK",
]

# Expanded global assets matching multi_factor.py GLOBAL_ASSETS
GLOBAL_TICKERS = [
    "^GSPC", "^IXIC", "^DJI", "^VIX", "^TNX", "^IRX",
    "^N225", "^HSI", "000001.SS", "^KS11", "^STI", "^KLSE", "^AXJO", "^BSESN",
    "^FTSE", "^GDAXI",
    "IDR=X", "EURIDR=X", "JPYIDR=X", "SGDIDR=X", "DX-Y.NYB",
    "GC=F", "CL=F", "BZ=F", "NG=F", "HG=F", "SI=F", "CPO=F",
    "XLE", "DBA",
]


def load_ohlcv(engine, ticker: str, lookback: int = 700) -> pd.DataFrame:
    """Load OHLCV data for a ticker."""
    cutoff = date.today() - timedelta(days=lookback)
    df = pd.read_sql(text("""
        SELECT timestamp, open, high, low, close, volume
        FROM stock_prices
        WHERE ticker = :ticker AND timeframe = '1d'
          AND timestamp >= :cutoff
        ORDER BY timestamp
    """), engine, params={"ticker": ticker, "cutoff": cutoff})

    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["date"] = df["timestamp"].dt.date
    df = df.drop_duplicates(subset=["date"]).set_index("date")
    df.index = pd.to_datetime(df.index)
    return df[["open", "high", "low", "close", "volume"]]


def load_global_data(engine, lookback: int = 700) -> dict[str, pd.DataFrame]:
    """Load OHLCV for all global tickers."""
    cutoff = date.today() - timedelta(days=lookback)
    df = pd.read_sql(text("""
        SELECT ticker, timestamp, close
        FROM stock_prices
        WHERE ticker = ANY(:tickers)
          AND timeframe = '1d'
          AND timestamp >= :cutoff
        ORDER BY ticker, timestamp
    """), engine, params={"tickers": GLOBAL_TICKERS, "cutoff": cutoff})

    if df.empty:
        return {}

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["date"] = df["timestamp"].dt.date

    result = {}
    for ticker in GLOBAL_TICKERS:
        tdf = df[df["ticker"] == ticker].drop_duplicates(subset=["date"]).set_index("date")
        tdf.index = pd.to_datetime(tdf.index)
        if not tdf.empty:
            result[ticker] = tdf[["close"]].rename(columns={"close": "close"})

    return result


def load_macro_df(engine) -> pd.DataFrame:
    """Load macro data as a DataFrame with date index."""
    df = pd.read_sql(text("""
        SELECT series_name, date, value FROM macro_data ORDER BY series_name, date
    """), engine)

    if df.empty:
        return pd.DataFrame()

    pivot = df.pivot(index="date", columns="series_name", values="value")
    pivot.index = pd.to_datetime(pivot.index)
    all_dates = pd.date_range(pivot.index.min(), pivot.index.max(), freq="D")
    pivot = pivot.reindex(all_dates).ffill()
    return pivot


def load_fundamental_for_ticker(engine, ticker: str) -> dict[str, float]:
    """Load latest fundamental data for a ticker."""
    df = pd.read_sql(text("""
        SELECT pe, pb, roe, eps, market_cap, beta, profit_margin,
               debt_to_equity, dividend_yield, revenue
        FROM fundamental_data
        WHERE ticker = :ticker
        ORDER BY date DESC LIMIT 1
    """), engine, params={"ticker": ticker})

    if df.empty:
        return {}

    row = df.iloc[0]
    result = {}
    for col in df.columns:
        val = row[col]
        if pd.notna(val):
            result[col] = float(val)
    return result


def run_walk_forward_backtest(
    engine,
    ticker: str,
    global_data: dict,
    macro_df: pd.DataFrame,
    use_causal: bool = True,
    n_splits: int = 5,
    train_window: int = 300,
    test_window: int = 20,
) -> dict:
    """Run walk-forward backtest for a single ticker."""
    df = load_ohlcv(engine, ticker)
    if len(df) < train_window + test_window:
        return {"ticker": ticker, "error": "insufficient data", "n_bars": len(df)}

    fundamental = load_fundamental_for_ticker(engine, ticker) if use_causal else None

    model = MultiFactorModel(
        horizon=5,
        min_train_samples=150,
        n_estimators=200,
        max_depth=4,
        learning_rate=0.03,
        use_pca=False,
        select_features=True,
        top_k_features=35,
    )

    results = []
    start_idx = train_window

    while start_idx + test_window <= len(df):
        as_of = df.index[start_idx]
        try:
            pred = model.train_and_predict(
                ticker=ticker,
                df=df.iloc[:start_idx + 1],
                as_of=as_of,
                global_data=global_data if use_causal else None,
                macro_data=macro_df if use_causal else None,
                fundamental_data=fundamental if use_causal else None,
            )

            # Get actual return over horizon
            if start_idx + 5 < len(df):
                future_close = df["close"].iloc[start_idx + 5]
                current_close = df["close"].iloc[start_idx]
                actual_return = (future_close / current_close - 1) * 100
                actual_class = 2 if actual_return > 1 else (0 if actual_return < -1 else 1)

                results.append({
                    "date": str(as_of.date()),
                    "predicted": pred.action,
                    "actual_class": actual_class,
                    "correct": pred.action_code == actual_class,
                    "signal": pred.signal,
                    "confidence": pred.confidence,
                    "n_features": len(model._feature_names.get(ticker, [])),
                })
        except Exception as e:
            logger.debug("  Skip %s at %s: %s", ticker, as_of.date(), e)

        start_idx += test_window

    if not results:
        return {"ticker": ticker, "error": "no valid predictions", "n_bars": len(df)}

    accuracy = sum(r["correct"] for r in results) / len(results)
    buy_correct = sum(1 for r in results if r["predicted"] == "BUY" and r["correct"]) / max(
        sum(1 for r in results if r["predicted"] == "BUY"), 1)
    sell_correct = sum(1 for r in results if r["predicted"] == "SELL" and r["correct"]) / max(
        sum(1 for r in results if r["predicted"] == "SELL"), 1)
    hold_correct = sum(1 for r in results if r["predicted"] == "HOLD" and r["correct"]) / max(
        sum(1 for r in results if r["predicted"] == "HOLD"), 1)

    avg_features = np.mean([r["n_features"] for r in results])

    return {
        "ticker": ticker,
        "accuracy": round(accuracy * 100, 1),
        "n_predictions": len(results),
        "buy_accuracy": round(buy_correct * 100, 1),
        "sell_accuracy": round(sell_correct * 100, 1),
        "hold_accuracy": round(hold_correct * 100, 1),
        "buy_count": sum(1 for r in results if r["predicted"] == "BUY"),
        "sell_count": sum(1 for r in results if r["predicted"] == "SELL"),
        "hold_count": sum(1 for r in results if r["predicted"] == "HOLD"),
        "avg_features": round(avg_features, 1),
        "avg_confidence": round(np.mean([r["confidence"] for r in results]), 3),
    }


def main():
    parser = argparse.ArgumentParser(description="AI/ML tuning with causal features")
    parser.add_argument("--tickers", type=str, help="Comma-separated tickers")
    parser.add_argument("--no-causal", action="store_true", help="Disable causal features (baseline)")
    args = parser.parse_args()

    engine = create_engine(PG_URL, echo=False, future=True, pool_pre_ping=True)

    tickers = args.tickers.split(",") if args.tickers else REPRESENTATIVE_TICKERS
    use_causal = not args.no_causal

    logger.info("=" * 70)
    logger.info("AI/ML TUNING WITH 7-LAYER CAUSAL FEATURES")
    logger.info("  Mode: %s", "WITH causal features" if use_causal else "BASELINE (no causal)")
    logger.info("  Tickers: %d", len(tickers))
    logger.info("  Global assets: %d", len(GLOBAL_TICKERS))
    logger.info("=" * 70)

    logger.info("Loading global data...")
    global_data = load_global_data(engine)
    logger.info("  Global tickers loaded: %d/%d", len(global_data), len(GLOBAL_TICKERS))

    logger.info("Loading macro data...")
    macro_df = load_macro_df(engine)
    logger.info("  Macro series: %d", macro_df.shape[1] if not macro_df.empty else 0)

    all_results = []
    for i, ticker in enumerate(tickers):
        logger.info("\n[%d/%d] Testing %s...", i + 1, len(tickers), ticker)
        result = run_walk_forward_backtest(
            engine, ticker, global_data, macro_df, use_causal=use_causal,
        )
        if "error" in result:
            logger.info("  SKIP: %s (%d bars)", result["error"], result.get("n_bars", 0))
        else:
            logger.info("  Accuracy: %.1f%% (%d predictions, %d features avg)",
                        result["accuracy"], result["n_predictions"], result["avg_features"])
            logger.info("  BUY: %d (%.1f%%), SELL: %d (%.1f%%), HOLD: %d (%.1f%%)",
                        result["buy_count"], result["buy_accuracy"],
                        result["sell_count"], result["sell_accuracy"],
                        result["hold_count"], result["hold_accuracy"])
        all_results.append(result)

    # Summary
    valid = [r for r in all_results if "error" not in r]
    if valid:
        avg_acc = np.mean([r["accuracy"] for r in valid])
        avg_features = np.mean([r["avg_features"] for r in valid])
        logger.info("\n" + "=" * 70)
        logger.info("SUMMARY (%s)", "WITH CAUSAL" if use_causal else "BASELINE")
        logger.info("=" * 70)
        logger.info("  Tickers tested: %d/%d", len(valid), len(tickers))
        logger.info("  Average accuracy: %.1f%%", avg_acc)
        logger.info("  Average features: %.1f", avg_features)
        logger.info("  Per-ticker:")
        for r in valid:
            logger.info("    %s: %.1f%% (%d features)", r["ticker"], r["accuracy"], r["avg_features"])
        logger.info("=" * 70)

        report = {
            "mode": "causal" if use_causal else "baseline",
            "test_date": date.today().isoformat(),
            "avg_accuracy": round(avg_acc, 1),
            "avg_features": round(avg_features, 1),
            "results": all_results,
        }
        output_path = Path(f"data/tune_ai_{'causal' if use_causal else 'baseline'}.json")
        output_path.parent.mkdir(exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        logger.info("  Report: %s", output_path)

    engine.dispose()


if __name__ == "__main__":
    main()
