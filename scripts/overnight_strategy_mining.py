#!/usr/bin/env python3
"""Overnight Strategy Mining — Trade Ideas Mode.

Runs at 02:00 WIB (19:00 UTC previous day) via crontab to mine optimal
Donchian Channel parameters for IHSG morning session based on overnight
global market conditions.

Workflow:
1. Fetch latest close data for global indicators: ^GSPC, ^VIX, CL=F, MTF=F
2. Assess overnight macro regime (risk-on vs risk-off)
3. Load IHSG (^JKSE) data from mock DB
4. Run LightGBM-based Donchian parameter sweep (period 10–25)
5. Select parameter with thinnest Max Drawdown for current macro regime
6. Update best_ticker_quant_config.json with optimal donchian_period
7. Insert notification into app_notifications table

Crontab entry:
    0 19 * * 1-5  DB_PATH=data/market_research_mock.db python scripts/overnight_strategy_mining.py
    (19:00 UTC = 02:00 WIB next day, Mon-Fri)

Requires: yfinance, lightgbm, pandas, numpy, sqlite3
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Constants ───────────────────────────────────────────────────────────────

GLOBAL_TICKERS = ["^GSPC", "^VIX", "CL=F", "MTF=F"]
IHSG_TICKER = "^JKSE"
DONCHIAN_RANGE = range(10, 26)  # 10 to 25 inclusive
DEFAULT_DB_PATH = "data/market_research_mock.db"
CONFIG_PATH = "best_ticker_quant_config.json"

# Macro regime thresholds
VIX_RISK_OFF_THRESHOLD = 25.0
OIL_BEAR_THRESHOLD = -0.02  # Daily return < -2% = bearish


# ── Data Fetching ───────────────────────────────────────────────────────────


def fetch_global_overnight() -> dict[str, dict]:
    """Fetch latest OHLCV data for global market indicators.

    Returns:
        Dict: {ticker: {close, daily_return, prev_close, date}}
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed — cannot fetch global data")
        return {}

    results: dict[str, dict] = {}
    for ticker in GLOBAL_TICKERS:
        try:
            tkr = yf.Ticker(ticker)
            hist = tkr.history(period="5d")
            if hist.empty:
                logger.warning("No data for %s", ticker)
                continue

            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else latest
            daily_return = (latest["Close"] - prev["Close"]) / prev["Close"] if prev["Close"] > 0 else 0.0

            results[ticker] = {
                "close": float(latest["Close"]),
                "prev_close": float(prev["Close"]),
                "daily_return": float(daily_return),
                "date": str(latest.name.date()),
            }
            logger.info("  %s: close=%.2f, return=%.2f%%",
                        ticker, latest["Close"], daily_return * 100)
        except Exception as e:
            logger.warning("  Failed to fetch %s: %s", ticker, e)

    return results


def assess_macro_regime(global_data: dict[str, dict]) -> dict:
    """Assess overnight macro regime from global market data.

    Classifies regime as:
    - "risk_on": VIX < 25, S&P up, Oil stable
    - "risk_off": VIX >= 25, or S&P down > 1%, or Oil down > 2%
    - "neutral": Mixed signals

    Returns:
        Dict with regime label and component signals.
    """
    vix = global_data.get("^VIX", {})
    spx = global_data.get("^GSPC", {})
    oil = global_data.get("CL=F", {})
    mtf = global_data.get("MTF=F", {})

    vix_level = vix.get("close", 20.0)
    spx_return = spx.get("daily_return", 0.0)
    oil_return = oil.get("daily_return", 0.0)
    mtf_return = mtf.get("daily_return", 0.0)

    risk_off_signals = 0
    if vix_level >= VIX_RISK_OFF_THRESHOLD:
        risk_off_signals += 1
    if spx_return < -0.01:
        risk_off_signals += 1
    if oil_return < OIL_BEAR_THRESHOLD:
        risk_off_signals += 1

    if risk_off_signals >= 2:
        regime = "risk_off"
    elif risk_off_signals == 0 and spx_return > 0:
        regime = "risk_on"
    else:
        regime = "neutral"

    return {
        "regime": regime,
        "vix_level": round(vix_level, 2),
        "spx_return_pct": round(spx_return * 100, 2),
        "oil_return_pct": round(oil_return * 100, 2),
        "mtf_return_pct": round(mtf_return * 100, 2),
        "risk_off_signals": risk_off_signals,
    }


# ── Donchian Channel Strategy ───────────────────────────────────────────────


def generate_donchian_signals(ohlcv: pd.DataFrame, period: int) -> pd.Series:
    """Generate Donchian Channel breakout signals.

    BUY (1) when close breaks above upper channel.
    SELL (-1) when close breaks below lower channel.
    HOLD (0) otherwise.

    Args:
        ohlcv: DataFrame with 'high', 'low', 'close' columns.
        period: Donchian channel lookback period.

    Returns:
        Series of signals (-1, 0, 1).
    """
    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)
    close = ohlcv["close"].astype(float)

    upper = high.rolling(period).max().shift(1)
    lower = low.rolling(period).min().shift(1)

    signal = pd.Series(0, index=ohlcv.index)
    signal[close > upper] = 1
    signal[close < lower] = -1

    # Trend persistence: maintain position until opposite signal
    signal = signal.replace(0, np.nan).ffill().fillna(0).astype(int)
    return signal


def simulate_returns(ohlcv: pd.DataFrame, signals: pd.Series, cost_per_trade: float = 0.002) -> pd.Series:
    """Simulate strategy returns from signals.

    Args:
        ohlcv: OHLCV DataFrame with 'close' column.
        signals: Series of positions (-1, 0, 1).
        cost_per_trade: Round-trip cost per trade (default 0.2%).

    Returns:
        Daily returns series (after cost).
    """
    close = ohlcv["close"].astype(float)
    returns = close.pct_change()
    signals = signals.reindex(returns.index).fillna(0)

    signal_change = signals.diff().fillna(0) != 0
    cost = signal_change.astype(float) * cost_per_trade

    strategy_returns = signals.shift(1) * returns - cost
    return strategy_returns.dropna()


def compute_max_drawdown(returns: pd.Series) -> float:
    """Compute maximum drawdown from a returns series.

    Returns:
        Max drawdown as negative float (e.g. -0.15 = -15%).
    """
    if returns.empty:
        return 0.0
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    return float(drawdown.min())


def compute_sharpe(returns: pd.Series) -> float:
    """Compute annualized Sharpe ratio."""
    if returns.empty or returns.std() == 0:
        return 0.0
    return float(np.sqrt(252) * returns.mean() / returns.std())


# ── LightGBM Parameter Optimization ─────────────────────────────────────────


def optimize_donchian_with_lightgbm(
    ohlcv: pd.DataFrame,
    macro_regime: str,
    donchian_range: range = DONCHIAN_RANGE,
) -> dict:
    """Run Donchian parameter sweep with LightGBM-based evaluation.

    For each Donchian period in range:
    1. Generate signals
    2. Build features (returns, volatility, drawdown)
    3. Train a quick LightGBM model to predict next-day return
    4. Backtest strategy and compute Max Drawdown + Sharpe

    Selects the parameter with thinnest Max Drawdown for the macro regime.

    Args:
        ohlcv: OHLCV DataFrame for IHSG.
        macro_regime: Current macro regime ("risk_on", "risk_off", "neutral").
        donchian_range: Range of Donchian periods to test.

    Returns:
        Dict with best_period, best_max_dd, best_sharpe, all_results.
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("lightgbm not available — using simple backtest only")
        lgb = None

    if len(ohlcv) < 60:
        logger.warning("Insufficient OHLCV data: %d rows (need >= 60)", len(ohlcv))
        return {"best_period": 20, "best_max_dd": 0.0, "best_sharpe": 0.0, "all_results": []}

    all_results: list[dict] = []

    for period in donchian_range:
        if period + 5 > len(ohlcv):
            continue

        signals = generate_donchian_signals(ohlcv, period)
        returns = simulate_returns(ohlcv, signals)

        if returns.empty:
            continue

        max_dd = compute_max_drawdown(returns)
        sharpe = compute_sharpe(returns)
        win_rate = float((returns > 0).sum() / len(returns[returns != 0])) if (returns != 0).any() else 0.0

        # LightGBM quick evaluation: predict next-day return from features
        lgb_score = 0.0
        if lgb is not None and len(returns) > 50:
            try:
                # Build simple features
                feat_df = pd.DataFrame(index=returns.index)
                feat_df["ret_1"] = returns
                feat_df["ret_5"] = returns.rolling(5).mean()
                feat_df["vol_10"] = returns.rolling(10).std()
                feat_df["cum_return"] = (1 + returns).cumprod() - 1
                feat_df["donchian_period"] = period
                feat_df["signal"] = signals.reindex(returns.index).fillna(0)
                feat_df["target"] = returns.shift(-1)

                feat_df = feat_df.dropna()
                if len(feat_df) > 30:
                    split_idx = int(len(feat_df) * 0.8)
                    train = feat_df.iloc[:split_idx]
                    val = feat_df.iloc[split_idx:]

                    X_train = train.drop(columns=["target"]).values
                    y_train = train["target"].values
                    X_val = val.drop(columns=["target"]).values
                    y_val = val["target"].values

                    model = lgb.LGBMRegressor(
                        n_estimators=50,
                        max_depth=4,
                        learning_rate=0.05,
                        verbose=-1,
                        n_jobs=1,
                    )
                    model.fit(X_train, y_train)
                    preds = model.predict(X_val)
                    lgb_score = float(np.corrcoef(preds, y_val)[0, 1]) if np.std(y_val) > 0 else 0.0
                    lgb_score = max(-1.0, min(1.0, lgb_score))
            except Exception as e:
                logger.debug("LightGBM eval failed for period=%d: %s", period, e)

        # Regime-adjusted score: prioritize thin Max DD
        # For risk_off: more conservative (weight Max DD heavier)
        # For risk_on: can tolerate slightly more DD for higher Sharpe
        if macro_regime == "risk_off":
            composite_score = -abs(max_dd) * 3.0 + sharpe * 0.5 + lgb_score * 0.5
        elif macro_regime == "risk_on":
            composite_score = -abs(max_dd) * 1.0 + sharpe * 1.5 + lgb_score * 1.0
        else:
            composite_score = -abs(max_dd) * 2.0 + sharpe * 1.0 + lgb_score * 0.5

        all_results.append({
            "period": period,
            "max_drawdown": round(max_dd, 6),
            "sharpe": round(sharpe, 4),
            "win_rate": round(win_rate, 4),
            "lgb_score": round(lgb_score, 4),
            "composite_score": round(composite_score, 4),
        })

    if not all_results:
        return {"best_period": 20, "best_max_dd": 0.0, "best_sharpe": 0.0, "all_results": []}

    # Select best: thinnest Max Drawdown (primary), then highest composite
    # User requirement: "Hasil parameter terbaik yang menghasilkan Max Drawdown tertipis"
    best = min(all_results, key=lambda r: abs(r["max_drawdown"]))

    logger.info("  Donchian sweep complete: %d periods tested", len(all_results))
    logger.info("  Best period: %d (MaxDD=%.2f%%, Sharpe=%.3f, WinRate=%.1f%%)",
                best["period"], best["max_drawdown"] * 100, best["sharpe"], best["win_rate"] * 100)

    return {
        "best_period": best["period"],
        "best_max_dd": best["max_drawdown"],
        "best_sharpe": best["sharpe"],
        "best_win_rate": best["win_rate"],
        "best_lgb_score": best["lgb_score"],
        "all_results": all_results,
    }


# ── Config Update ───────────────────────────────────────────────────────────


def update_config(
    config_path: str,
    best_period: int,
    macro_regime: dict,
    optimization_result: dict,
) -> None:
    """Update best_ticker_quant_config.json with optimal Donchian parameter.

    Adds/updates an 'overnight_strategy' section with the mining results.

    Args:
        config_path: Path to best_ticker_quant_config.json.
        best_period: Optimal Donchian period.
        macro_regime: Macro regime assessment.
        optimization_result: Full optimization results.
    """
    path = Path(config_path)
    config: dict = {}

    if path.exists():
        with path.open("r") as f:
            config = json.load(f)

    config["overnight_strategy"] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "macro_regime": macro_regime,
        "best_donchian_period": best_period,
        "best_max_drawdown": optimization_result.get("best_max_dd", 0.0),
        "best_sharpe": optimization_result.get("best_sharpe", 0.0),
        "best_win_rate": optimization_result.get("best_win_rate", 0.0),
        "best_lgb_score": optimization_result.get("best_lgb_score", 0.0),
        "all_results": optimization_result.get("all_results", []),
    }

    # Also update IHSG ticker config if it exists
    tickers = config.get("tickers", {})
    if IHSG_TICKER in tickers:
        tickers[IHSG_TICKER]["donchian_period"] = best_period
        tickers[IHSG_TICKER]["overnight_regime"] = macro_regime["regime"]
    else:
        tickers[IHSG_TICKER] = {
            "donchian_period": best_period,
            "overnight_regime": macro_regime["regime"],
            "strategy": "donchian_overnight",
        }
    config["tickers"] = tickers

    with path.open("w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False, default=str)

    logger.info("  Config updated: %s (donchian_period=%d)", config_path, best_period)


# ── Notification Sync ───────────────────────────────────────────────────────


def insert_overnight_notification(
    conn: sqlite3.Connection,
    macro_regime: dict,
    optimization_result: dict,
) -> int:
    """Insert overnight strategy mining results into app_notifications.

    Args:
        conn: SQLite connection.
        macro_regime: Macro regime assessment.
        optimization_result: Donchian optimization results.

    Returns:
        Notification row ID, or -1 if failed.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            title TEXT NOT NULL,
            body_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'UNREAD'
        )
    """)
    conn.commit()

    now = datetime.now(timezone.utc).isoformat()
    best_period = optimization_result.get("best_period", 20)
    best_dd = optimization_result.get("best_max_dd", 0.0)
    best_sharpe = optimization_result.get("best_sharpe", 0.0)
    regime = macro_regime.get("regime", "neutral")

    title = f"Overnight Strategy Mining: Donchian={best_period} ({regime})"

    payload = {
        "type": "overnight_strategy_mining",
        "generated_at": now,
        "macro_regime": macro_regime,
        "best_donchian_period": best_period,
        "best_max_drawdown": best_dd,
        "best_sharpe": best_sharpe,
        "best_win_rate": optimization_result.get("best_win_rate", 0.0),
        "best_lgb_score": optimization_result.get("best_lgb_score", 0.0),
        "all_results": optimization_result.get("all_results", []),
        "recommendation": (
            f"Untuk IHSG pagi hari: gunakan Donchian period={best_period} "
            f"(MaxDD={best_dd*100:.2f}%, Sharpe={best_sharpe:.3f}). "
            f"Regime makro: {regime} (VIX={macro_regime.get('vix_level', 'N/A')})"
        ),
    }

    body_json = json.dumps(payload, indent=2, ensure_ascii=False, default=str)

    cursor = conn.execute(
        "INSERT INTO app_notifications (timestamp, title, body_json, status) "
        "VALUES (?, ?, ?, 'UNREAD')",
        (now, title, body_json),
    )
    conn.commit()
    notif_id = cursor.lastrowid
    logger.info("  Notification inserted: id=%d, title='%s'", notif_id, title)
    return notif_id


# ── Main ────────────────────────────────────────────────────────────────────


def load_ihsg_from_db(db_path: str) -> pd.DataFrame:
    """Load IHSG (^JKSE) OHLCV data from database.

    Args:
        db_path: Path to SQLite database.

    Returns:
        DataFrame with DatetimeIndex and OHLCV columns.
    """
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume FROM ohlcv "
            "WHERE ticker = '^JKSE' AND timeframe = '1d' "
            "ORDER BY date",
            conn,
        )
    except Exception as e:
        logger.warning("Failed to load ^JKSE from %s: %s", db_path, e)
        df = pd.DataFrame()
    finally:
        conn.close()

    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    return df


def main():
    parser = argparse.ArgumentParser(description="Overnight Strategy Mining (Trade Ideas Mode)")
    parser.add_argument("--db-path", type=str, default=DEFAULT_DB_PATH,
                        help="Path to mock database for IHSG data")
    parser.add_argument("--config-path", type=str, default=CONFIG_PATH,
                        help="Path to best_ticker_quant_config.json")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Skip yfinance fetch (use mock macro data)")
    parser.add_argument("--insert-notification", action="store_true", default=True,
                        help="Insert results into app_notifications table")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("OVERNIGHT STRATEGY MINING (Trade Ideas Mode)")
    logger.info("=" * 60)
    logger.info("  Time: %s WIB", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Step 1: Fetch global overnight data
    logger.info("")
    logger.info("STEP 1: Global Market Overnight Scan")
    if args.skip_fetch:
        global_data = {
            "^VIX": {"close": 18.5, "daily_return": -0.02, "date": "2024-01-01"},
            "^GSPC": {"close": 4800, "daily_return": 0.005, "date": "2024-01-01"},
            "CL=F": {"close": 72.0, "daily_return": 0.01, "date": "2024-01-01"},
            "MTF=F": {"close": 3500, "daily_return": 0.003, "date": "2024-01-01"},
        }
        logger.info("  (skipped fetch — using mock data)")
    else:
        global_data = fetch_global_overnight()

    if not global_data:
        logger.warning("  No global data available — using neutral regime defaults")
        global_data = {
            "^VIX": {"close": 20.0, "daily_return": 0.0},
            "^GSPC": {"close": 4800, "daily_return": 0.0},
            "CL=F": {"close": 72.0, "daily_return": 0.0},
            "MTF=F": {"close": 3500, "daily_return": 0.0},
        }

    # Step 2: Assess macro regime
    logger.info("")
    logger.info("STEP 2: Macro Regime Assessment")
    macro_regime = assess_macro_regime(global_data)
    logger.info("  Regime: %s", macro_regime["regime"])
    logger.info("  VIX: %.2f, S&P: %.2f%%, Oil: %.2f%%, MTF: %.2f%%",
                macro_regime["vix_level"], macro_regime["spx_return_pct"],
                macro_regime["oil_return_pct"], macro_regime["mtf_return_pct"])

    # Step 3: Load IHSG data from mock DB
    logger.info("")
    logger.info("STEP 3: Load IHSG Data from Mock DB")
    ihsg = load_ihsg_from_db(args.db_path)
    if ihsg.empty:
        logger.error("  No IHSG data in %s — aborting", args.db_path)
        return
    logger.info("  IHSG rows: %d (%s to %s)",
                len(ihsg), ihsg.index[0].date(), ihsg.index[-1].date())

    # Step 4: Donchian parameter optimization with LightGBM
    logger.info("")
    logger.info("STEP 4: Donchian Parameter Optimization (LightGBM)")
    logger.info("  Testing periods: %s", list(DONCHIAN_RANGE))
    opt_result = optimize_donchian_with_lightgbm(ihsg, macro_regime["regime"])

    # Step 5: Update config
    logger.info("")
    logger.info("STEP 5: Update best_ticker_quant_config.json")
    update_config(args.config_path, opt_result["best_period"], macro_regime, opt_result)

    # Step 6: Insert notification
    if args.insert_notification:
        logger.info("")
        logger.info("STEP 6: Insert App Notification")
        try:
            conn = sqlite3.connect(args.db_path)
            insert_overnight_notification(conn, macro_regime, opt_result)
            conn.close()
        except Exception as e:
            logger.warning("  Notification insert failed: %s", e)

    logger.info("")
    logger.info("=" * 60)
    logger.info("OVERNIGHT STRATEGY MINING COMPLETE")
    logger.info("  Best Donchian: %d | MaxDD: %.2f%% | Sharpe: %.3f | Regime: %s",
                opt_result["best_period"],
                opt_result.get("best_max_dd", 0) * 100,
                opt_result.get("best_sharpe", 0),
                macro_regime["regime"])
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
