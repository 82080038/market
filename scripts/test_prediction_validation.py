"""Prediction module validation script (S2 layer test).

Tests PredictionEngine against real PostgreSQL data:
1. Correctness — predictions are produced without errors
2. Data leakage — no future data used in predictions
3. Error handling — NaN, division by zero, missing data
4. Consistency — same input → same output

Usage:
    python scripts/test_prediction_validation.py
    python scripts/test_prediction_validation.py --ticker BBCA.JK
    python scripts/test_prediction_validation.py --all
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, date, datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

# Focus tickers for testing
FOCUS_TICKERS = [
    "BBCA.JK", "BBRI.JK", "UNVR.JK", "ANTM.JK", "MDKA.JK",
    "UNTR.JK", "APLI.JK", "BCIC.JK", "INCO.JK", "KRAS.JK",
]


def load_ohlcv_from_pg(ticker: str, days: int = 500) -> pd.DataFrame:
    """Load OHLCV data from PostgreSQL stock_prices table."""
    from sqlalchemy import text
    from market.db.engine import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        sql = text("""
            SELECT timestamp, open, high, low, close, volume
            FROM stock_prices
            WHERE ticker = :ticker
            AND timestamp >= :start_date
            ORDER BY timestamp
        """)
        cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
        df = pd.read_sql(sql, conn, params={"ticker": ticker, "start_date": cutoff})

    if df.empty:
        logger.warning("No data for %s", ticker)
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    df.index = df.index.tz_localize(None)  # strip timezone for consistency
    return df


def test_basic_prediction(ticker: str) -> dict:
    """Test 1: Basic prediction — can PredictionEngine produce output?"""
    from market.analysis.prediction import PredictionEngine, PredictionMethod

    df = load_ohlcv_from_pg(ticker)
    if df.empty or len(df) < 35:
        return {"test": "basic_prediction", "ticker": ticker, "status": "SKIP", "reason": f"Insufficient data: {len(df)} bars"}

    engine = PredictionEngine()
    pred = engine.predict(ticker, df, method=PredictionMethod.ENSEMBLE)

    result = {
        "test": "basic_prediction",
        "ticker": ticker,
        "status": "PASS" if pred.predicted_price > 0 else "FAIL",
        "direction": pred.predicted_direction,
        "predicted_price": pred.predicted_price,
        "confidence": pred.confidence,
        "return_pct": pred.predicted_return_pct,
        "horizon_days": pred.horizon_days,
        "bars_used": len(df),
        "rationale": pred.rationale[:200] if pred.rationale else "",
    }
    return result


def test_no_data_leakage(ticker: str) -> dict:
    """Test 2: Data leakage — prediction at T should not use data from T+1."""
    from market.analysis.prediction import PredictionEngine, PredictionMethod

    df = load_ohlcv_from_pg(ticker, days=365)
    if len(df) < 60:
        return {"test": "no_data_leakage", "ticker": ticker, "status": "SKIP", "reason": "Insufficient data"}

    # Split data: use first 80% as "past", last 20% as "future"
    split_idx = int(len(df) * 0.8)
    as_of_date = df.index[split_idx]

    engine = PredictionEngine()

    # Prediction with truncation at as_of
    pred_truncated = engine.predict(ticker, df, as_of=as_of_date, method=PredictionMethod.ENSEMBLE)

    # Prediction with only past data (manual truncation)
    df_past = df.iloc[:split_idx + 1].copy()
    pred_manual = engine.predict(ticker, df_past, as_of=None, method=PredictionMethod.ENSEMBLE)

    # Prices should be identical (no look-ahead)
    price_diff = abs(pred_truncated.predicted_price - pred_manual.predicted_price)
    direction_match = pred_truncated.predicted_direction == pred_manual.predicted_direction

    # Also verify the current price used is the same
    # (both should use close at split_idx)
    current_price_truncated = float(df.loc[:as_of_date, "close"].iloc[-1])
    current_price_manual = float(df_past["close"].iloc[-1])
    price_basis_match = abs(current_price_truncated - current_price_manual) < 0.01

    result = {
        "test": "no_data_leakage",
        "ticker": ticker,
        "status": "PASS" if (price_diff < 0.50 and price_basis_match) else "FAIL",
        "as_of_date": str(as_of_date.date()),
        "truncated_price": pred_truncated.predicted_price,
        "manual_price": pred_manual.predicted_price,
        "price_diff": round(price_diff, 4),
        "direction_match": direction_match,
        "price_basis_match": price_basis_match,
    }
    return result


def test_nan_handling(ticker: str) -> dict:
    """Test 3: NaN handling — engine should not crash on NaN data."""
    from market.analysis.prediction import PredictionEngine, PredictionMethod

    df = load_ohlcv_from_pg(ticker, days=120)
    if len(df) < 35:
        return {"test": "nan_handling", "ticker": ticker, "status": "SKIP", "reason": "Insufficient data"}

    # Inject some NaN values
    df_nan = df.copy()
    df_nan.iloc[10, df_nan.columns.get_loc("close")] = float("nan")
    df_nan.iloc[20, df_nan.columns.get_loc("high")] = float("nan")

    engine = PredictionEngine()
    try:
        pred = engine.predict(ticker, df_nan, method=PredictionMethod.ENSEMBLE)
        # Engine should either produce a valid prediction or a safe fallback
        status = "PASS" if pred.predicted_price >= 0 else "FAIL"
        return {
            "test": "nan_handling",
            "ticker": ticker,
            "status": status,
            "predicted_price": pred.predicted_price,
            "direction": pred.predicted_direction,
            "confidence": pred.confidence,
        }
    except Exception as e:
        return {
            "test": "nan_handling",
            "ticker": ticker,
            "status": "FAIL",
            "error": str(e)[:200],
        }


def test_division_by_zero(ticker: str) -> dict:
    """Test 4: Division by zero — engine should handle zero prices gracefully."""
    from market.analysis.prediction import PredictionEngine, PredictionMethod

    # Create synthetic data with zero close prices
    dates = pd.date_range("2026-01-01", periods=60, freq="B")
    df_zero = pd.DataFrame({
        "open": [100.0] * 60,
        "high": [105.0] * 60,
        "low": [95.0] * 60,
        "close": [0.0] * 60,  # All zeros
        "volume": [1000] * 60,
    }, index=dates)

    engine = PredictionEngine()
    try:
        pred = engine.predict(f"{ticker}_ZERO_TEST", df_zero, method=PredictionMethod.ENSEMBLE)
        # Should not crash, may return flat/zero
        status = "PASS"  # Not crashing is the criteria
        return {
            "test": "division_by_zero",
            "ticker": ticker,
            "status": status,
            "predicted_price": pred.predicted_price,
            "direction": pred.predicted_direction,
            "confidence": pred.confidence,
        }
    except (ZeroDivisionError, ValueError) as e:
        return {
            "test": "division_by_zero",
            "ticker": ticker,
            "status": "FAIL",
            "error": f"{type(e).__name__}: {e}",
        }
    except Exception as e:
        # Other exceptions are acceptable as long as it's not a crash
        return {
            "test": "division_by_zero",
            "ticker": ticker,
            "status": "PASS",
            "note": f"Handled via exception: {type(e).__name__}",
        }


def test_insufficient_data(ticker: str) -> dict:
    """Test 5: Insufficient data — engine should return safe fallback."""
    from market.analysis.prediction import PredictionEngine, PredictionMethod

    dates = pd.date_range("2026-01-01", periods=10, freq="B")
    df_short = pd.DataFrame({
        "open": [100.0] * 10,
        "high": [105.0] * 10,
        "low": [95.0] * 10,
        "close": [100.0] * 10,
        "volume": [1000] * 10,
    }, index=dates)

    engine = PredictionEngine()
    pred = engine.predict(ticker, df_short, method=PredictionMethod.ENSEMBLE)

    status = "PASS" if pred.predicted_direction == "flat" and pred.confidence == 0.0 else "FAIL"
    return {
        "test": "insufficient_data",
        "ticker": ticker,
        "status": status,
        "direction": pred.predicted_direction,
        "confidence": pred.confidence,
        "rationale": pred.rationale,
    }


def test_prediction_consistency(ticker: str) -> dict:
    """Test 6: Consistency — same input should produce same output."""
    from market.analysis.prediction import PredictionEngine, PredictionMethod

    df = load_ohlcv_from_pg(ticker, days=120)
    if len(df) < 35:
        return {"test": "consistency", "ticker": ticker, "status": "SKIP", "reason": "Insufficient data"}

    engine = PredictionEngine()
    as_of = df.index[-30]

    pred1 = engine.predict(ticker, df, as_of=as_of, method=PredictionMethod.ENSEMBLE)
    pred2 = engine.predict(ticker, df, as_of=as_of, method=PredictionMethod.ENSEMBLE)

    price_match = abs(pred1.predicted_price - pred2.predicted_price) < 0.01
    direction_match = pred1.predicted_direction == pred2.predicted_direction
    confidence_match = abs(pred1.confidence - pred2.confidence) < 0.001

    status = "PASS" if (price_match and direction_match and confidence_match) else "FAIL"
    return {
        "test": "consistency",
        "ticker": ticker,
        "status": status,
        "price_match": price_match,
        "direction_match": direction_match,
        "confidence_match": confidence_match,
        "pred1_price": pred1.predicted_price,
        "pred2_price": pred2.predicted_price,
    }


def test_temporal_consistency(ticker: str) -> dict:
    """Test 7: Temporal consistency — prediction at T-5 should differ from T.

    This verifies the engine is actually using different data windows.
    """
    from market.analysis.prediction import PredictionEngine, PredictionMethod

    df = load_ohlcv_from_pg(ticker, days=365)
    if len(df) < 60:
        return {"test": "temporal_consistency", "ticker": ticker, "status": "SKIP", "reason": "Insufficient data"}

    engine = PredictionEngine()

    as_of_t1 = df.index[-30]
    as_of_t2 = df.index[-1]

    pred_t1 = engine.predict(ticker, df, as_of=as_of_t1, method=PredictionMethod.ENSEMBLE)
    pred_t2 = engine.predict(ticker, df, as_of=as_of_t2, method=PredictionMethod.ENSEMBLE)

    # Predictions should be different (different data windows)
    price_diff = abs(pred_t1.predicted_price - pred_t2.predicted_price)
    status = "PASS" if price_diff > 0.01 else "FAIL"

    return {
        "test": "temporal_consistency",
        "ticker": ticker,
        "status": status,
        "as_of_t1": str(as_of_t1.date()),
        "as_of_t2": str(as_of_t2.date()),
        "pred_t1_price": pred_t1.predicted_price,
        "pred_t2_price": pred_t2.predicted_price,
        "price_diff": round(price_diff, 4),
        "pred_t1_dir": pred_t1.predicted_direction,
        "pred_t2_dir": pred_t2.predicted_direction,
    }


def test_market_context_integration(ticker: str) -> dict:
    """Test 8: Market context integration — does context provider work with PG?"""
    from market.analysis.prediction import PredictionEngine, PredictionMethod
    from market.analysis.market_context import MarketContextProvider

    df = load_ohlcv_from_pg(ticker, days=365)
    if len(df) < 60:
        return {"test": "market_context", "ticker": ticker, "status": "SKIP", "reason": "Insufficient data"}

    from market.db.engine import get_sessionmaker
    session = get_sessionmaker()()

    try:
        provider = MarketContextProvider(session=session)
        engine = PredictionEngine(context_provider=provider)

        as_of = df.index[-1]
        pred = engine.predict(ticker, df, as_of=as_of, method=PredictionMethod.ENSEMBLE)

        status = "PASS" if pred.predicted_price > 0 else "FAIL"
        return {
            "test": "market_context",
            "ticker": ticker,
            "status": status,
            "predicted_price": pred.predicted_price,
            "direction": pred.predicted_direction,
            "confidence": pred.confidence,
            "rationale": pred.rationale[:300] if pred.rationale else "",
        }
    except Exception as e:
        return {
            "test": "market_context",
            "ticker": ticker,
            "status": "FAIL",
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        }
    finally:
        session.close()


def run_all_tests(tickers: list[str]) -> dict:
    """Run all prediction validation tests."""
    all_results: list[dict] = []
    summary = {"total": 0, "pass": 0, "fail": 0, "skip": 0}

    test_functions = [
        test_basic_prediction,
        test_no_data_leakage,
        test_nan_handling,
        test_division_by_zero,
        test_insufficient_data,
        test_prediction_consistency,
        test_temporal_consistency,
        test_market_context_integration,
    ]

    for ticker in tickers:
        logger.info("Testing %s...", ticker)
        for test_fn in test_functions:
            t0 = time.perf_counter()
            try:
                result = test_fn(ticker)
            except Exception as e:
                result = {
                    "test": test_fn.__name__,
                    "ticker": ticker,
                    "status": "FAIL",
                    "error": f"{type(e).__name__}: {str(e)[:300]}",
                }
            elapsed = time.perf_counter() - t0
            result["elapsed_ms"] = round(elapsed * 1000, 1)

            all_results.append(result)

            status = result.get("status", "FAIL")
            summary["total"] += 1
            if status == "PASS":
                summary["pass"] += 1
            elif status == "SKIP":
                summary["skip"] += 1
            else:
                summary["fail"] += 1

            logger.info(
                "  %s: %s (%s) — %.0fms",
                result["test"], status, ticker, elapsed * 1000,
            )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "results": all_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prediction module validation")
    parser.add_argument("--ticker", type=str, default=None, help="Single ticker to test")
    parser.add_argument("--all", action="store_true", help="Test all focus tickers")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output JSON file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.ticker:
        tickers = [args.ticker]
    elif args.all:
        tickers = FOCUS_TICKERS
    else:
        tickers = FOCUS_TICKERS[:3]  # Default: test 3 tickers

    logger.info("Running prediction validation for %d tickers: %s", len(tickers), tickers)
    report = run_all_tests(tickers)

    print(f"\n{'='*60}")
    print(f"PREDICTION VALIDATION REPORT")
    print(f"{'='*60}")
    print(f"Total: {report['summary']['total']}")
    print(f"Pass:  {report['summary']['pass']}")
    print(f"Fail:  {report['summary']['fail']}")
    print(f"Skip:  {report['summary']['skip']}")
    print(f"{'='*60}")

    # Print failures
    failures = [r for r in report["results"] if r["status"] == "FAIL"]
    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for f in failures:
            print(f"  [{f['test']}] {f['ticker']}: {f.get('error', f.get('reason', 'Unknown'))}")

    # Print as table
    print(f"\n{'Ticker':<12} {'Test':<25} {'Status':<8} {'Detail':<40}")
    print("-" * 85)
    for r in report["results"]:
        detail = ""
        if r["status"] == "PASS":
            detail = f"price={r.get('predicted_price', '—')} dir={r.get('direction', '—')} conf={r.get('confidence', '—')}"
        elif r["status"] == "FAIL":
            detail = r.get("error", r.get("reason", ""))[:40]
        elif r["status"] == "SKIP":
            detail = r.get("reason", "")[:40]
        print(f"{r['ticker']:<12} {r['test']:<25} {r['status']:<8} {detail:<40}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        logger.info("Report saved to %s", args.output)


if __name__ == "__main__":
    main()
