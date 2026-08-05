"""Autonomous backtest simulation — non-look-ahead, multi-ticker, multi-strategy.

Runs BacktestEngine + PredictionEngine on real DB data, compares predictions
vs actuals, and outputs a structured report.

Usage:
    uv run python scripts/run_backtest_simulation.py
"""

from __future__ import annotations

import json
import logging
import warnings
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from market.analysis.market_context import MarketContextProvider
from market.analysis.ml_signal import MLSignalProvider
from market.analysis.multi_factor import MultiFactorModel
from market.analysis.prediction import PredictionMethod
from market.backtest.engine import BacktestEngine
from market.backtest.strategies import MACrossoverStrategy
from market.db.engine import get_sessionmaker
from market.db.models import OHLCV

warnings.filterwarnings("ignore", category=DeprecationWarning, module="lightgbm")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────

TICKERS = [
    "BBCA.JK", "BBRI.JK", "TLKM.JK", "ASII.JK", "UNVR.JK",
    "ANTM.JK", "MDKA.JK", "UNTR.JK",
]

# Backtest period: 2 years (2024-01-01 to 2026-08-03)
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-08-03"

# Prediction evaluation: predict at as_of, compare with actual N days later
PREDICTION_HORIZON_DAYS = 5
PREDICTION_AS_OF_DATES = [
    "2025-01-15", "2025-03-15", "2025-05-15", "2025-07-15",
    "2025-09-15", "2025-11-15", "2026-01-15", "2026-03-15",
    "2026-05-15", "2026-07-15",
]

INITIAL_CAPITAL = 100_000_000  # 100M IDR


def load_ticker_data(session, ticker: str) -> pd.DataFrame:
    """Load daily OHLCV from DB into DataFrame with adjusted prices.

    Applies corporate action adjustment (split/dividend) via adjusted_close
    to prevent false anomalies in backtesting.
    """
    from market.analysis.market_factors import ensure_adjusted

    rows = session.execute(
        select(OHLCV)
        .where(OHLCV.ticker == ticker, OHLCV.timeframe == "1d")
        .order_by(OHLCV.timestamp)
    ).scalars().all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        [
            {
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "adjusted_close": float(r.adjusted_close) if r.adjusted_close else None,
                "volume": r.volume,
            }
            for r in rows
        ],
        index=pd.DatetimeIndex([r.timestamp for r in rows]),
    )
    # Apply adjusted prices (splits, dividends)
    df = ensure_adjusted(df)
    return df


def run_backtest_for_ticker(df: pd.DataFrame, ticker: str) -> dict:
    """Run backtest with MA crossover strategy on a single ticker."""
    # Filter to backtest period
    mask = (df.index >= BACKTEST_START) & (df.index <= BACKTEST_END)
    bt_data = df.loc[mask].copy()

    if len(bt_data) < 50:
        return {"ticker": ticker, "error": "Insufficient data", "bars": len(bt_data)}

    engine = BacktestEngine(initial_capital=INITIAL_CAPITAL, max_position_pct=0.25)

    # Strategy 1: MA Crossover (fast=5, slow=20)
    strategy_ma = MACrossoverStrategy(fast=5, slow=20)
    result_ma = engine.run(strategy=strategy_ma, data=bt_data, ticker=ticker)

    # Strategy 2: MA Crossover (fast=20, slow=50) — classic swing
    strategy_swing = MACrossoverStrategy(fast=20, slow=50)
    engine2 = BacktestEngine(initial_capital=INITIAL_CAPITAL, max_position_pct=0.25)
    result_swing = engine2.run(strategy=strategy_swing, data=bt_data, ticker=ticker)

    # Buy & hold benchmark
    first_close = float(bt_data["close"].iloc[0])
    last_close = float(bt_data["close"].iloc[-1])
    bn_return = (last_close - first_close) / first_close * 100

    # Calculate metrics
    def metrics_from_result(result):
        if result.equity_curve.empty:
            return {"total_return_pct": 0, "n_trades": 0, "final_equity": INITIAL_CAPITAL}
        final = float(result.equity_curve.iloc[-1])
        total_return = (final - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
        return {
            "total_return_pct": round(total_return, 2),
            "n_trades": len(result.trades),
            "final_equity": round(final, 0),
            "metrics": {
                k: round(v, 4) if isinstance(v, float) else v
                for k, v in result.metrics.items()
            },
        }

    return {
        "ticker": ticker,
        "bars": len(bt_data),
        "period": f"{bt_data.index[0].date()} to {bt_data.index[-1].date()}",
        "buy_hold_return_pct": round(bn_return, 2),
        "strategy_ma_fast5_slow20": metrics_from_result(result_ma),
        "strategy_ma_fast20_slow50": metrics_from_result(result_swing),
    }


def run_prediction_evaluation(
    df: pd.DataFrame, ticker: str, context_provider: MarketContextProvider,
) -> dict:
    """Run prediction at multiple as_of dates, compare with actual."""
    from market.analysis.pattern_detector import PatternDetector
    from market.analysis.prediction import PredictionEngine

    pattern_detector = PatternDetector()
    pred_engine = PredictionEngine(
        pattern_detector=pattern_detector,
        context_provider=context_provider,
    )

    results = []
    for as_of_str in PREDICTION_AS_OF_DATES:
        as_of = pd.Timestamp(as_of_str)
        if as_of not in df.index:
            # Find closest date before as_of
            valid = df.index[df.index <= as_of]
            if len(valid) == 0:
                continue
            as_of = valid[-1]

        # Find actual price N days later
        future_date = as_of + pd.Timedelta(days=PREDICTION_HORIZON_DAYS)
        future_data = df.index[df.index >= future_date]
        if len(future_data) == 0:
            continue
        actual_date = future_data[0]
        actual_close = (
            float(df.loc[actual_date, "close"].iloc[0])
            if isinstance(df.loc[actual_date, "close"], pd.Series)
            else float(df.loc[actual_date, "close"])
        )
        as_of_close = (
            float(df.loc[as_of, "close"].iloc[0])
            if isinstance(df.loc[as_of, "close"], pd.Series)
            else float(df.loc[as_of, "close"])
        )

        # Run prediction (non-look-ahead: only data up to as_of)
        try:
            pred = pred_engine.predict(
                ticker=ticker,
                data=df,
                method=PredictionMethod.ENSEMBLE,
                as_of=str(as_of.date()),
            )

            actual_direction = "up" if actual_close > as_of_close else "down"
            pred_direction = pred.predicted_direction
            direction_correct = actual_direction == pred_direction

            actual_pct = (actual_close - as_of_close) / as_of_close * 100

            results.append({
                "as_of": str(as_of.date()),
                "actual_date": str(actual_date.date()),
                "predicted_direction": pred_direction,
                "actual_direction": actual_direction,
                "direction_correct": direction_correct,
                "predicted_price": round(pred.predicted_price, 2),
                "actual_price": round(actual_close, 2),
                "actual_pct_change": round(actual_pct, 2),
                "confidence": round(pred.confidence, 3),
                "predicted_return_pct": round(pred.predicted_return_pct, 2),
            })
        except Exception as e:
            results.append({
                "as_of": str(as_of.date()),
                "error": str(e),
            })

    if not results:
        return {"ticker": ticker, "predictions": [], "accuracy": None}

    correct = sum(1 for r in results if r.get("direction_correct"))
    total = len(results)
    accuracy = round(correct / total * 100, 1) if total > 0 else 0

    return {
        "ticker": ticker,
        "n_predictions": total,
        "n_correct": correct,
        "direction_accuracy_pct": accuracy,
        "predictions": results,
    }


def main() -> None:
    logger.info("=" * 70)
    logger.info("AUTONOMOUS BACKTEST SIMULATION — NON-LOOK-AHEAD")
    logger.info("Period: %s to %s", BACKTEST_START, BACKTEST_END)
    logger.info("Tickers: %s", ", ".join(TICKERS))
    logger.info("Initial capital: IDR %s", f"{INITIAL_CAPITAL:,}")
    logger.info("=" * 70)

    session = get_sessionmaker()()
    ml_provider = MLSignalProvider(horizon=PREDICTION_HORIZON_DAYS)
    multifactor = MultiFactorModel(horizon=PREDICTION_HORIZON_DAYS)
    context_provider = MarketContextProvider(
        session=session,
        ml_provider=ml_provider,
        multifactor_model=multifactor,
    )
    all_backtest_results = []
    all_prediction_results = []
    errors = []

    try:
        for i, ticker in enumerate(TICKERS, 1):
            logger.info("[%d/%d] Loading data for %s...", i, len(TICKERS), ticker)
            df = load_ticker_data(session, ticker)

            if df.empty:
                errors.append(f"{ticker}: No data found")
                logger.warning("  No data for %s", ticker)
                continue

            logger.info("  Loaded %d bars (%s to %s)",
                        len(df), df.index[0].date(), df.index[-1].date())

            # Run backtest
            logger.info("  Running backtest...")
            bt_result = run_backtest_for_ticker(df, ticker)
            all_backtest_results.append(bt_result)
            ma5_val = bt_result.get(
                "strategy_ma_fast5_slow20", {}
            ).get("total_return_pct", "N/A")
            ma20_val = bt_result.get(
                "strategy_ma_fast20_slow50", {}
            ).get("total_return_pct", "N/A")
            logger.info(
                "  Backtest: MA5/20=%s%%, MA20/50=%s%%, B&H=%s%%",
                ma5_val, ma20_val,
                bt_result.get("buy_hold_return_pct", "N/A"),
            )

            # Run prediction evaluation with market context
            logger.info("  Running prediction evaluation (with market context)...")
            pred_result = run_prediction_evaluation(df, ticker, context_provider)
            all_prediction_results.append(pred_result)
            if pred_result["direction_accuracy_pct"] is not None:
                logger.info("  Prediction accuracy: %s%% (%d/%d correct)",
                            pred_result["direction_accuracy_pct"],
                            pred_result["n_correct"],
                            pred_result["n_predictions"])
    finally:
        session.close()

    # ── Generate Report ──────────────────────────────────────────────────
    report = {
        "simulation_metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "backtest_period": f"{BACKTEST_START} to {BACKTEST_END}",
            "tickers": TICKERS,
            "initial_capital_idr": INITIAL_CAPITAL,
            "prediction_horizon_days": PREDICTION_HORIZON_DAYS,
            "prediction_dates": PREDICTION_AS_OF_DATES,
        },
        "backtest_results": all_backtest_results,
        "prediction_results": all_prediction_results,
        "errors": errors,
        "summary": {
            "total_tickers": len(TICKERS),
            "successful_backtests": len(all_backtest_results),
            "successful_predictions": len([
                r for r in all_prediction_results
                if r.get("direction_accuracy_pct") is not None
            ]),
            "errors": len(errors),
        },
    }

    # Calculate aggregate prediction accuracy
    all_preds = [r for r in all_prediction_results if r.get("direction_accuracy_pct") is not None]
    if all_preds:
        total_correct = sum(r["n_correct"] for r in all_preds)
        total_preds = sum(r["n_predictions"] for r in all_preds)
        report["summary"]["aggregate_prediction_accuracy_pct"] = round(
            total_correct / total_preds * 100, 1
        ) if total_preds > 0 else 0
        report["summary"]["total_predictions"] = total_preds
        report["summary"]["total_correct_predictions"] = total_correct

    # Calculate aggregate backtest performance
    ma5_returns = [
        r["strategy_ma_fast5_slow20"]["total_return_pct"]
        for r in all_backtest_results
        if "strategy_ma_fast5_slow20" in r
    ]
    ma20_returns = [
        r["strategy_ma_fast20_slow50"]["total_return_pct"]
        for r in all_backtest_results
        if "strategy_ma_fast20_slow50" in r
    ]
    bn_returns = [
        r["buy_hold_return_pct"]
        for r in all_backtest_results
        if "buy_hold_return_pct" in r
    ]

    if ma5_returns:
        report["summary"]["avg_ma5_20_return_pct"] = round(sum(ma5_returns) / len(ma5_returns), 2)
    if ma20_returns:
        report["summary"]["avg_ma20_50_return_pct"] = round(
            sum(ma20_returns) / len(ma20_returns), 2
        )
    if bn_returns:
        report["summary"]["avg_buy_hold_return_pct"] = round(sum(bn_returns) / len(bn_returns), 2)

    # Save report
    output_path = Path("data/backtest_simulation_report.json")
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info("=" * 70)
    logger.info("SIMULATION COMPLETE")
    logger.info("Report saved to: %s", output_path)
    logger.info("=" * 70)

    # Print summary to console
    print("\n" + "=" * 70)
    print("BACKTEST SIMULATION SUMMARY")
    print("=" * 70)
    print(f"Tickers tested: {report['summary']['total_tickers']}")
    print(f"Errors: {report['summary']['errors']}")
    print()

    print("BACKTEST RESULTS (2-year period):")
    print(f"{'Ticker':12s} {'MA 5/20':>14s} {'MA 20/50':>14s} {'Buy&Hold':>14s}")
    print("-" * 56)
    for r in all_backtest_results:
        ma5 = r.get("strategy_ma_fast5_slow20", {}).get("total_return_pct", 0)
        ma20 = r.get("strategy_ma_fast20_slow50", {}).get("total_return_pct", 0)
        bn = r.get("buy_hold_return_pct", 0)
        print(f"{r['ticker']:12s} {ma5:>13.2f}% {ma20:>13.2f}% {bn:>13.2f}%")

    print()
    print("PREDICTION ACCURACY (direction, 5-day horizon):")
    print(f"{'Ticker':12s} {'Accuracy':>10s} {'Correct':>10s} {'Total':>10s}")
    print("-" * 44)
    for r in all_prediction_results:
        if r.get("direction_accuracy_pct") is not None:
            print(
                f"{r['ticker']:12s} {r['direction_accuracy_pct']:>9.1f}% "
                f"{r['n_correct']:>10d} {r['n_predictions']:>10d}"
            )

    if "aggregate_prediction_accuracy_pct" in report["summary"]:
        print(
            f"\nAggregate prediction accuracy: "
            f"{report['summary']['aggregate_prediction_accuracy_pct']}%"
        )
        print(f"Total predictions: {report['summary']['total_predictions']}")
        print(f"Correct predictions: {report['summary']['total_correct_predictions']}")

    print()
    if ma5_returns:
        print(f"Avg MA 5/20 return: {report['summary']['avg_ma5_20_return_pct']}%")
    if ma20_returns:
        print(f"Avg MA 20/50 return: {report['summary']['avg_ma20_50_return_pct']}%")
    if bn_returns:
        print(f"Avg Buy & Hold return: {report['summary']['avg_buy_hold_return_pct']}%")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
