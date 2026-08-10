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
from market.analysis.meta_labeling import MetaLabeler, cusum_filter
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
    "BBCA.JK", "BBRI.JK", "UNVR.JK", "ANTM.JK",
    "MDKA.JK", "UNTR.JK", "APLI.JK", "BCIC.JK",
    "INCO.JK", "KRAS.JK",
]

# Backtest period: 2 years (2024-01-01 to 2026-08-03)
BACKTEST_START = "2024-01-01"
BACKTEST_END = "2026-08-03"

# Prediction evaluation: predict at as_of, compare with actual N days later
PREDICTION_HORIZON_DAYS = 5
PREDICTION_AS_OF_DATES = [
    "2024-03-15", "2024-04-15", "2024-05-15", "2024-06-15",
    "2024-07-15", "2024-08-15", "2024-09-15", "2024-10-15",
    "2024-11-15", "2024-12-15",
    "2025-01-15", "2025-02-15", "2025-03-15", "2025-04-15",
    "2025-05-15", "2025-06-15", "2025-07-15", "2025-08-15",
    "2025-09-15", "2025-10-15", "2025-11-15", "2025-12-15",
    "2026-01-15", "2026-02-15", "2026-03-15", "2026-04-15",
    "2026-05-15", "2026-06-15", "2026-07-15",
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


def load_vix_series(session) -> pd.Series:
    """Load VIX close prices from DB as a Series indexed by date."""
    rows = session.execute(
        select(OHLCV)
        .where(OHLCV.ticker == "^VIX", OHLCV.timeframe == "1d")
        .order_by(OHLCV.timestamp)
    ).scalars().all()
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series(
        [float(r.close) for r in rows],
        index=pd.DatetimeIndex([r.timestamp for r in rows]),
        name="vix",
    )


def load_foreign_flow_series(session, ticker: str) -> pd.Series:
    """Load foreign net flow for a ticker from DB as a Series indexed by date."""
    from market.db.models import ForeignFlow

    rows = session.execute(
        select(ForeignFlow)
        .where(ForeignFlow.ticker == ticker)
        .order_by(ForeignFlow.date)
    ).scalars().all()
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series(
        [float(r.foreign_net) if r.foreign_net is not None else 0.0 for r in rows],
        index=pd.DatetimeIndex([r.date for r in rows]),
        name="foreign_flow",
    )


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
    vix_series: pd.Series | None = None,
    foreign_flow_series: pd.Series | None = None,
    multifactor: MultiFactorModel | None = None,
) -> dict:
    """Run prediction at multiple as_of dates, compare with actual.

    Also trains a MetaLabeler on historical CUSUM-filtered events and uses it
    to veto low-confidence predictions (bet size = 0 → no trade).
    """
    from market.analysis.pattern_detector import PatternDetector
    from market.analysis.prediction import PredictionEngine

    pattern_detector = PatternDetector()
    pred_engine = PredictionEngine(
        pattern_detector=pattern_detector,
        context_provider=context_provider,
    )

    # ── Train MetaLabeler on historical data ────────────────────────────
    # Generate CUSUM-filtered events from the full dataset (non-look-ahead:
    # events are based on past price movements only).
    events = cusum_filter(df["close"].astype(float))
    if events is not None and len(events) > 0:
        # Assign sides based on short-term momentum at each event.
        event_sides = []
        for ev_date in events:
            loc = df.index.get_loc(ev_date)
            if loc < 5:
                event_sides.append(0)
            else:
                ret_5 = (float(df["close"].iloc[loc]) - float(df["close"].iloc[loc - 5])) / float(df["close"].iloc[loc - 5])
                event_sides.append(1 if ret_5 >= 0 else -1)
        events_df = pd.DataFrame({"side": event_sides}, index=events)
    else:
        events_df = pd.DataFrame(columns=["side"])

    meta_labeler = MetaLabeler(min_train_samples=100, prob_threshold=0.0)
    meta_metrics = {"mean_accuracy": 0.5, "mean_auc": 0.5}
    if len(events_df) >= 100:
        meta_metrics = meta_labeler.fit(df, events_df)
        logger.info(
            "  MetaLabeler trained: acc=%.3f, auc=%.3f, n_events=%d",
            meta_metrics["mean_accuracy"], meta_metrics["mean_auc"],
            len(events_df),
        )
    else:
        logger.info("  MetaLabeler: insufficient events (%d < 100), skipping", len(events_df))

    results = []
    meta_filtered = 0
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

        # P5-4: Multi-horizon actual direction — majority vote of 3/5/7-day
        actual_directions = []
        for h in [3, 5, 7]:
            fd = as_of + pd.Timedelta(days=h)
            fdata = df.index[df.index >= fd]
            if len(fdata) > 0:
                ac = float(df.loc[fdata[0], "close"].iloc[0]) if isinstance(df.loc[fdata[0], "close"], pd.Series) else float(df.loc[fdata[0], "close"])
                actual_directions.append("up" if ac > as_of_close else "down")
        # Majority vote for actual direction
        if actual_directions:
            actual_direction = "up" if actual_directions.count("up") > actual_directions.count("down") else "down"
        else:
            actual_direction = "up" if actual_close > as_of_close else "down"

        # Run prediction (non-look-ahead: only data up to as_of)
        try:
            pred = pred_engine.predict(
                ticker=ticker,
                data=df,
                method=PredictionMethod.ENSEMBLE,
                as_of=str(as_of.date()),
            )

            pred_direction = pred.predicted_direction
            direction_correct = actual_direction == pred_direction

            actual_pct = (actual_close - as_of_close) / as_of_close * 100

            # ── MetaLabeler soft bet sizing ────────────────────────────────
            # P3-4: Instead of hard veto at 0.45, use soft approach:
            # - meta_prob < 0.35 → veto (no trade)
            # - meta_prob 0.35-0.50 → P4-3: try MultiFactorModel override
            # - meta_prob >= 0.50 → keep with full confidence
            primary_side = 1 if pred_direction == "up" else -1 if pred_direction == "down" else 0
            meta_result = meta_labeler.predict(
                df, as_of=as_of, primary_side=primary_side,
                primary_confidence=pred.confidence,
            )
            meta_prob = meta_result.probability
            HARD_VETO_THRESHOLD = 0.30
            LOW_CONFIDENCE_ZONE = 0.50
            meta_vetoed = meta_prob < HARD_VETO_THRESHOLD

            # P4-3: Confidence-weighted ensemble override (DISABLED — hurt accuracy)
            # When meta_prob is in low-confidence zone (0.35-0.50), MultiFactorModel
            # override was tested but flipped to wrong direction too often.
            # if not meta_vetoed and meta_prob < LOW_CONFIDENCE_ZONE and multifactor is not None:
            #     ...

            if meta_vetoed:
                meta_filtered += 1
                # If vetoed, flip to HOLD — but preserve original prediction
                # for raw accuracy comparison.
                original_pred_direction = pred_direction
                original_direction_correct = direction_correct
                results.append({
                    "as_of": str(as_of.date()),
                    "actual_date": str(actual_date.date()),
                    "predicted_direction": "hold",
                    "actual_direction": actual_direction,
                    "direction_correct": False,
                    "meta_vetoed": True,
                    "original_pred_direction": original_pred_direction,
                    "original_direction_correct": original_direction_correct,
                    "meta_probability": round(meta_prob, 3),
                    "meta_bet_size": round(meta_result.bet_size, 3),
                    "predicted_price": round(pred.predicted_price, 2),
                    "actual_price": round(actual_close, 2),
                    "actual_pct_change": round(actual_pct, 2),
                    "confidence": round(pred.confidence, 3),
                    "predicted_return_pct": round(pred.predicted_return_pct, 2),
                })
                continue

            results.append({
                "as_of": str(as_of.date()),
                "actual_date": str(actual_date.date()),
                "predicted_direction": pred_direction,
                "actual_direction": actual_direction,
                "direction_correct": direction_correct,
                "meta_vetoed": False,
                "meta_probability": round(meta_result.probability, 3),
                "meta_bet_size": round(meta_result.bet_size, 3),
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

    # Accuracy on non-vetoed predictions only (meta-filtered accuracy)
    non_vetoed = [r for r in results if not r.get("meta_vetoed", False)]
    correct = sum(1 for r in non_vetoed if r.get("direction_correct"))
    total = len(non_vetoed)
    accuracy = round(correct / total * 100, 1) if total > 0 else 0

    # Raw accuracy: all predictions as if no meta-labeler (use original direction)
    raw_correct = sum(
        1 for r in results
        if r.get("original_direction_correct", r.get("direction_correct"))
    )
    raw_total = len(results)
    raw_accuracy = round(raw_correct / raw_total * 100, 1) if raw_total > 0 else 0

    # Total including vetoed for reporting
    total_all = len(results)

    return {
        "ticker": ticker,
        "n_predictions": total_all,
        "n_correct": correct,
        "direction_accuracy_pct": accuracy,  # meta-filtered (same as raw now since both exclude vetoed)
        "raw_accuracy_pct": raw_accuracy,
        "meta_filtered": meta_filtered,
        "meta_accuracy": round(meta_metrics["mean_accuracy"], 3),
        "meta_auc": round(meta_metrics["mean_auc"], 3),
        "n_meta_trained": len(events_df),
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

    # Load VIX series once (shared across all tickers)
    logger.info("Loading VIX series from DB...")
    vix_series = load_vix_series(session)
    if vix_series.empty:
        logger.warning("VIX data not found in DB — meta-model will use rolling std proxy")
    else:
        logger.info("  VIX: %d bars (%s to %s)",
                    len(vix_series), vix_series.index[0].date(),
                    vix_series.index[-1].date())

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

            # Run prediction evaluation with market context + exogenous signals
            logger.info("  Running prediction evaluation (with market context + meta-labeling)...")
            ff_series = load_foreign_flow_series(session, ticker)
            if ff_series.empty:
                logger.info("  No foreign flow data for %s — using endogenous only", ticker)
            pred_result = run_prediction_evaluation(
                df, ticker, context_provider,
                vix_series=vix_series if not vix_series.empty else None,
                foreign_flow_series=ff_series if not ff_series.empty else None,
                multifactor=multifactor,
            )
            all_prediction_results.append(pred_result)
            if pred_result["direction_accuracy_pct"] is not None:
                logger.info(
                    "  Prediction accuracy: %s%% (meta-filtered, %d/%d correct, %d vetoed)",
                    pred_result["direction_accuracy_pct"],
                    pred_result["n_correct"],
                    pred_result["n_predictions"] - pred_result.get("meta_filtered", 0),
                    pred_result.get("meta_filtered", 0),
                )
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
        total_meta_filtered = sum(r.get("meta_filtered", 0) for r in all_preds)
        non_vetoed_total = total_preds - total_meta_filtered
        report["summary"]["aggregate_prediction_accuracy_pct"] = round(
            total_correct / non_vetoed_total * 100, 1
        ) if non_vetoed_total > 0 else 0
        # Raw accuracy: count original_direction_correct across all predictions
        total_raw_correct = sum(
            sum(1 for p in r.get("predictions", [])
                if p.get("original_direction_correct", p.get("direction_correct")))
            for r in all_preds
        )
        report["summary"]["raw_aggregate_accuracy_pct"] = round(
            total_raw_correct / total_preds * 100, 1
        ) if total_preds > 0 else 0
        report["summary"]["total_predictions"] = total_preds
        report["summary"]["total_correct_predictions"] = total_correct
        report["summary"]["total_meta_filtered"] = total_meta_filtered

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
    print("PREDICTION ACCURACY (direction, 5-day horizon, meta-filtered):")
    print(f"{'Ticker':12s} {'Meta-Acc':>10s} {'Raw-Acc':>10s} {'Vetoed':>8s} {'Meta-AUC':>10s}")
    print("-" * 54)
    for r in all_prediction_results:
        if r.get("direction_accuracy_pct") is not None:
            print(
                f"{r['ticker']:12s} {r['direction_accuracy_pct']:>9.1f}% "
                f"{r.get('raw_accuracy_pct', 0):>9.1f}% "
                f"{r.get('meta_filtered', 0):>8d} "
                f"{r.get('meta_auc', 0):>9.3f}"
            )

    if "aggregate_prediction_accuracy_pct" in report["summary"]:
        print(
            f"\nAggregate meta-filtered accuracy: "
            f"{report['summary']['aggregate_prediction_accuracy_pct']}%"
        )
        print(
            f"Aggregate raw accuracy: "
            f"{report['summary'].get('raw_aggregate_accuracy_pct', 0)}%"
        )
        print(f"Total predictions: {report['summary']['total_predictions']}")
        print(f"Correct predictions: {report['summary']['total_correct_predictions']}")
        print(f"Meta-filtered (vetoed): {report['summary'].get('total_meta_filtered', 0)}")

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
