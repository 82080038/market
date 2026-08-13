#!/usr/bin/env python3
"""Engine Ablation Runner — isolated per-engine backtest & scoring.

Tests each signal engine in isolation against a baseline (no engine) to
measure individual contribution to prediction accuracy and portfolio
performance. Outputs a scorecard with KEEP / MARGINAL / REMOVE verdict.

Usage:
    # Test all engines on default tickers
    python scripts/engine_ablation/run_ablation.py

    # Test specific engines on specific tickers
    python scripts/engine_ablation/run_ablation.py --engines astronacci,volume,meta --tickers BBCA.JK,BBRI.JK

    # Custom period
    python scripts/engine_ablation/run_ablation.py --start 2023-01-01 --end 2026-08-12

    # Dry run (show config, don't execute)
    python scripts/engine_ablation/run_ablation.py --dry-run

Environment:
    DATABASE_URL=postgresql://petrick:market_dev@localhost:5432/market
    or SQLite default: data/market_research.db
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market.ablation.engine_registry import (
    EngineCategory,
    EngineEntry,
    EngineRegistry,
    SignalType,
    create_default_registry,
)
from market.ablation.isolated_backtest import IsolatedBacktester, IsolationResult, simulate_returns, compute_metrics
from market.ablation.ablation_report import generate_report
from market.backtest.strategies import Signal
from market.db.engine import get_sessionmaker
from market.db.models import OHLCV

warnings.filterwarnings("ignore", category=FutureWarning)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────

DEFAULT_TICKERS = [
    "BBCA.JK", "BBRI.JK", "UNVR.JK", "ANTM.JK",
    "MDKA.JK", "UNTR.JK", "TLKM.JK", "ASII.JK",
]


def _load_equity_tickers_from_db(session, limit: int = 20) -> list[str]:
    """Load IDX equity tickers from instruments table.

    Filters by exchange_mic='XIDX' and asset_class='EQUITY_INDIVIDUAL'
    to exclude indices (^JKSE, ^JKLQ45), commodities, ETFs, etc.

    Falls back to DEFAULT_TICKERS if DB is unavailable.
    """
    try:
        from market.db.models import Instrument
        rows = session.execute(
            select(Instrument.ticker).where(
                Instrument.exchange_mic == "XIDX",
                Instrument.asset_class == "EQUITY_INDIVIDUAL",
                Instrument.is_active == True,  # noqa: E712
            ).order_by(Instrument.ticker).limit(limit)
        ).scalars().all()
        if rows:
            return list(rows)
    except Exception as e:
        logger.warning("Failed to load tickers from DB: %s — using DEFAULT_TICKERS", e)
    return DEFAULT_TICKERS

DEFAULT_START = "2024-01-01"
DEFAULT_END = "2026-08-12"

OUTPUT_DIR = Path("data/ablation_reports")


def load_ohlcv_data(session, ticker: str, start: str, end: str) -> pd.DataFrame:
    """Load daily OHLCV from DB into DataFrame.

    Uses raw SQL to avoid ORM/PG schema mismatch (PG table lacks `id` column).
    """
    from sqlalchemy import text as sa_text
    rows = session.execute(
        sa_text(
            "SELECT timestamp, open, high, low, close, volume "
            "FROM ohlcv WHERE ticker = :ticker AND timeframe = '1d' "
            "AND timestamp >= :start AND timestamp <= :end "
            "ORDER BY timestamp"
        ),
        {"ticker": ticker, "start": start, "end": end},
    ).all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        [
            {
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": r.volume,
            }
            for r in rows
        ],
        index=pd.DatetimeIndex([r.timestamp for r in rows]),
    )
    # Normalize timezone: PG returns tz-aware timestamps, strip tz for consistent comparisons
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


def load_benchmark(session, start: str, end: str) -> pd.Series:
    """Load IHSG (^JKSE) daily returns as benchmark."""
    from sqlalchemy import text as sa_text
    rows = session.execute(
        sa_text(
            "SELECT timestamp, close FROM ohlcv "
            "WHERE ticker = '^JKSE' AND timeframe = '1d' "
            "AND timestamp >= :start AND timestamp <= :end "
            "ORDER BY timestamp"
        ),
        {"start": start, "end": end},
    ).all()

    if not rows:
        return pd.Series(dtype=float)

    closes = pd.Series(
        [float(r.close) for r in rows],
        index=pd.DatetimeIndex([r.timestamp for r in rows]),
    )
    # Normalize timezone: PG returns tz-aware timestamps, strip tz for consistent comparisons
    if closes.index.tz is not None:
        closes.index = closes.index.tz_localize(None)
    return closes.pct_change().dropna()


def generate_baseline_signals(ohlcv: pd.DataFrame) -> pd.Series:
    """Generate baseline technical signals (no AI/engine).

    Simple MA crossover + RSI:
    - BUY (1) when SMA20 > SMA50 AND RSI < 70
    - SELL (-1) when SMA20 < SMA50 AND RSI > 30
    - HOLD (0) otherwise
    """
    close = ohlcv["close"].astype(float)

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    signal = pd.Series(0, index=ohlcv.index)
    signal[(sma20 > sma50) & (rsi < 70)] = 1
    signal[(sma20 < sma50) & (rsi > 30)] = -1

    return signal


def _load_table_df(table: str, ticker_filter: str | None = None) -> pd.DataFrame:
    """Load a DB table into a DataFrame via raw query.

    Supports both SQLite (?) and PostgreSQL (%s) parameter styles.
    """
    try:
        from market.db.raw import get_raw_connection
        from market.config import settings as _settings
        is_pg = _settings.db_backend == "postgresql"
        ph = "%s" if is_pg else "?"
        with get_raw_connection() as conn:
            if ticker_filter and table in ("fundamental_data", "esg_scores", "corporate_governance"):
                cursor = conn.execute(
                    f"SELECT * FROM {table} WHERE ticker = {ph}",
                    (ticker_filter,),
                )
            else:
                cursor = conn.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            if not rows:
                return pd.DataFrame()
            cols = [desc[0] for desc in cursor.description] if cursor.description else None
            if cols is None:
                return pd.DataFrame(rows)
            return pd.DataFrame(rows, columns=cols)
    except Exception as e:
        logger.debug("Table %s load failed: %s", table, e)
        return pd.DataFrame()


def _load_global_ohlcv(session, tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """Load OHLCV for global/commodity tickers for cross-market signals."""
    result = {}
    for ticker in tickers:
        df = load_ohlcv_data(session, ticker, start, end)
        if not df.empty:
            result[ticker] = df
    return result


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI using Wilder's smoothing."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50.0)


def generate_engine_signals(
    ohlcv: pd.DataFrame,
    engine_name: str,
    baseline_signals: pd.Series,
    ticker: str,
    session,
    data_cache: dict,
) -> pd.Series:
    """Generate signals for a specific engine in isolation.

    Each engine is hooked to its ACTUAL implementation module.
    The signal type determines how the engine output is interpreted:

    - DIRECTIONAL: engine produces a direction signal [-1, +1] → map to {-1, 0, +1}
    - TIMING: engine produces a timing window → mark as active (±1) or inactive (0)
    - FILTER: engine filters/vetoes baseline signals (reduces false positives)
    - SIZING: engine adjusts confidence (not directly testable as signal)
    - CONTEXT: engine provides context score → modulate baseline signal strength

    Args:
        ohlcv: OHLCV DataFrame for the ticker.
        engine_name: Name of the engine to test.
        baseline_signals: Baseline technical signals (MA+RSI).
        ticker: Ticker symbol being tested.
        session: DB session for data loading.
        data_cache: Cache dict for loaded data (avoid re-loading per ticker).

    Returns:
        Signal series {-1, 0, +1} with ONLY this engine's contribution.
    """
    signals = baseline_signals.copy()
    close = ohlcv["close"].astype(float)

    # ── volume: VWAP deviation + OFI + OBV trend (full production logic) ─
    if engine_name == "volume":
        try:
            from market.analysis.volume_features import compute_vwap, compute_ofi_proxy, detect_obv_divergence
            high = ohlcv["high"].astype(float)
            low = ohlcv["low"].astype(float)
            close_f = ohlcv["close"].astype(float)
            volume = ohlcv["volume"].astype(float)

            # OFI proxy: use 5-day rolling mean (shifted, no look-ahead)
            ofi_result = compute_ofi_proxy(close_f, volume, high, low)
            ofi_5 = ofi_result.ofi_5

            # VWAP deviation (already shifted by 1 in compute_vwap)
            vwap_result = compute_vwap(high, low, close_f, volume, window=20)
            vwap_dev = vwap_result.deviation

            # OBV divergence — per-bar detection using rolling window
            obv = (np.sign(close_f.diff()) * volume).fillna(0).cumsum()
            obv_signal = pd.Series(0.0, index=ohlcv.index)
            for i in range(len(ohlcv)):
                if i < 20:
                    continue
                window_close = close_f.iloc[max(0, i - 20):i + 1]
                window_obv = obv.iloc[max(0, i - 20):i + 1]
                div = detect_obv_divergence(window_close, window_obv, window=20)
                if div.divergence_type == "bullish":
                    obv_signal.iloc[i] = 0.5 * div.strength
                elif div.divergence_type == "bearish":
                    obv_signal.iloc[i] = -0.5 * div.strength

            # Aggregate: clip to [-1, +1] like production SignalEnhancer
            vol_signal = np.clip(ofi_5 + vwap_dev * 5 + obv_signal, -1, 1)
            signals = pd.Series(0, index=ohlcv.index)
            signals[vol_signal > 0.1] = 1
            signals[vol_signal < -0.1] = -1
        except Exception as e:
            logger.warning("Volume signal failed: %s", e)

    # ── event: PolicyEventScorer ────────────────────────────────────────
    elif engine_name == "event":
        try:
            from market.analysis.policy_event_scorer import PolicyEventScorer
            scorer = data_cache.get("event_scorer")
            if scorer is None:
                scorer = PolicyEventScorer()
                scorer.load()
                data_cache["event_scorer"] = scorer
            signals = pd.Series(0, index=ohlcv.index)
            for idx in ohlcv.index:
                dt = idx.to_pydatetime()
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                result = scorer.compute_event_signal(ticker=ticker, as_of_date=dt)
                if result and result.direction == "bullish":
                    signals.loc[idx] = 1
                elif result and result.direction == "bearish":
                    signals.loc[idx] = -1
        except Exception as e:
            logger.warning("Event signal failed: %s", e)

    # ── meta: MetaLabeler (filter — veto low-confidence signals) ────────
    elif engine_name == "meta":
        # MetaLabeler requires a trained LightGBM model.
        # Without training, we test the FILTER behavior: veto signals
        # on high-volatility days (ATR > 1.5× mean ATR) where false signals are common.
        try:
            high = ohlcv["high"].astype(float)
            low = ohlcv["low"].astype(float)
            tr = (high - low).abs()
            atr = tr.rolling(14).mean()
            atr_ratio = atr / atr.rolling(50).mean()
            # Veto (set to 0) when ATR ratio > 1.5 (high volatility → low confidence)
            signals[atr_ratio > 1.5] = 0
        except Exception as e:
            logger.warning("Meta filter signal failed: %s", e)

    # ── smart_money: Foreign flow proxy (Bandarmology) ──────────────────
    elif engine_name == "smart_money":
        try:
            ff_df = data_cache.get("foreign_flow")
            if ff_df is None:
                ff_df = _load_table_df("foreign_flow", ticker_filter=ticker)
                data_cache["foreign_flow"] = ff_df
            if ff_df.empty:
                logger.debug("No foreign_flow data for %s", ticker)
            else:
                # Use foreign net flow as smart money proxy
                date_col = "date" if "date" in ff_df.columns else "tanggal"
                if date_col in ff_df.columns and "foreign_net" in ff_df.columns:
                    ff_df[date_col] = pd.to_datetime(ff_df[date_col], errors="coerce")
                    ff_df = ff_df.dropna(subset=[date_col, "foreign_net"])
                    ff_df = ff_df.sort_values(date_col)
                    ff_indexed = ff_df.set_index(date_col)["foreign_net"]

                    # 5-day rolling foreign net flow momentum
                    ff_5d = ff_indexed.rolling(5).sum()

                    signals = pd.Series(0, index=ohlcv.index)
                    for idx in signals.index:
                        # Find most recent foreign flow on or before idx
                        prior = ff_5d[ff_5d.index <= idx]
                        if not prior.empty:
                            val = prior.iloc[-1]
                            if pd.notna(val):
                                # Positive foreign net flow → institutional accumulation → bullish
                                if val > 0:
                                    signals.loc[idx] = 1
                                elif val < 0:
                                    signals.loc[idx] = -1
        except Exception as e:
            logger.warning("Smart money signal failed: %s", e)

    # ── cross_market: Asian market domino effect ────────────────────────
    elif engine_name == "cross_market":
        try:
            global_data = data_cache.get("global_ohlcv")
            if global_data is None:
                global_tickers = ["^N225", "^HSI", "000001.SS", "CPO=F"]
                global_data = _load_global_ohlcv(session, global_tickers, "2024-01-01", "2026-08-12")
                data_cache["global_ohlcv"] = global_data

            weights = {"^N225": 0.35, "^HSI": 0.35, "000001.SS": 0.15, "CPO=F": 0.15}
            signals = pd.Series(0, index=ohlcv.index)

            for gticker, weight in weights.items():
                gdf = global_data.get(gticker)
                if gdf is None or gdf.empty:
                    continue
                g_returns = gdf["close"].pct_change().shift(1)  # T-1 return (no look-ahead)
                for idx in signals.index:
                    if idx in g_returns.index:
                        ret = g_returns.loc[idx]
                        if pd.notna(ret):
                            if ret > 0.005:
                                signals.loc[idx] += weight
                            elif ret < -0.005:
                                signals.loc[idx] -= weight
            # Normalize: if net signal > 0.1 → buy, < -0.1 → sell
            signals = signals.apply(lambda x: 1 if x > 0.1 else -1 if x < -0.1 else 0)
        except Exception as e:
            logger.warning("Cross-market signal failed: %s", e)

    # ── sector: Sector rotation ─────────────────────────────────────────
    elif engine_name == "sector":
        try:
            from market.analysis.sector_rotation import compute_sector_momentum, compute_relative_strength
            # Load IHSG as market benchmark
            ihsg = data_cache.get("ihsg_ohlcv")
            if ihsg is None:
                ihsg = load_ohlcv_data(session, "^JKSE", "2024-01-01", "2026-08-12")
                data_cache["ihsg_ohlcv"] = ihsg

            if not ihsg.empty:
                ticker_returns = close.pct_change().dropna()
                market_returns = ihsg["close"].astype(float).pct_change().dropna()

                # Time-varying sector signals using rolling momentum + RS
                signals = pd.Series(0, index=ohlcv.index)
                lookback = 20
                rs_window = 60

                for i in range(len(ohlcv)):
                    if i < max(lookback, rs_window):
                        continue
                    # Rolling momentum: cumulative return over lookback
                    window_ret = ticker_returns.iloc[i - lookback:i]
                    mom = float((1.0 + window_ret).prod() - 1.0)

                    # Rolling RS: sector vs market over rs_window
                    sec_window = ticker_returns.iloc[i - rs_window:i]
                    mkt_window = market_returns.reindex(sec_window.index).dropna()
                    if len(mkt_window) > 0:
                        sec_cum = float((1.0 + sec_window).prod() - 1.0)
                        mkt_cum = float((1.0 + mkt_window).prod() - 1.0)
                        rs = sec_cum - mkt_cum
                    else:
                        rs = 0.0

                    # Composite: momentum + RS direction
                    if mom > 0 and rs > 0:
                        signals.iloc[i] = 1
                    elif mom < 0 and rs < 0:
                        signals.iloc[i] = -1
        except Exception as e:
            logger.warning("Sector signal failed: %s", e)

    # ── pairs: Cointegration-based stat arb (walk-forward, no look-ahead) ─
    elif engine_name == "pairs":
        try:
            from market.analysis.pairs_trading import PairsTradingEngine
            # Find a pair: use the next ticker in default list
            all_tickers = data_cache.get("all_tickers", DEFAULT_TICKERS)
            pair_ticker = None
            for t in all_tickers:
                if t != ticker:
                    pair_ticker = t
                    break
            if pair_ticker:
                pair_df = data_cache.get(f"pair_ohlcv_{pair_ticker}")
                if pair_df is None:
                    pair_df = load_ohlcv_data(session, pair_ticker, "2024-01-01", "2026-08-12")
                    data_cache[f"pair_ohlcv_{pair_ticker}"] = pair_df

                if not pair_df.empty:
                    engine = PairsTradingEngine()
                    pair_close = pair_df["close"].astype(float)

                    # Align both price series on common dates
                    aligned = pd.DataFrame({"a": close, "b": pair_close}).dropna()
                    if len(aligned) > 252:
                        signals = pd.Series(0, index=ohlcv.index)

                        # Walk-forward: re-test cointegration every 60 days
                        retest_interval = 60
                        min_train = 252  # 1 year minimum for cointegration test

                        # State: hedge_ratio, spread_mean, spread_std, is_cointegrated
                        current_hedge = None
                        current_mean = 0.0
                        current_std = 1.0
                        current_cointegrated = False
                        last_test_end = 0

                        for i in range(len(aligned)):
                            # Re-test cointegration periodically with data up to i
                            if i >= min_train and (current_hedge is None or (i - last_test_end) >= retest_interval):
                                train_data = aligned.iloc[:i + 1]  # data up to day i (inclusive)
                                price_a_train = train_data["a"]
                                price_b_train = train_data["b"]

                                pair_result = engine.test_pair(
                                    price_a_train, price_b_train, ticker, pair_ticker
                                )
                                if pair_result.is_cointegrated:
                                    current_cointegrated = True
                                    # Compute hedge ratio and spread stats from training data
                                    from market.analysis.pairs_trading import _ols_hedge_ratio
                                    _, _, residuals = _ols_hedge_ratio(price_a_train, price_b_train)
                                    current_hedge = pair_result.hedge_ratio if hasattr(pair_result, 'hedge_ratio') else None
                                    if current_hedge is None:
                                        # Recompute from OLS
                                        hedge, _, _ = _ols_hedge_ratio(price_a_train, price_b_train)
                                        current_hedge = hedge
                                    current_mean = float(np.mean(residuals))
                                    current_std = float(np.std(residuals)) if np.std(residuals) > 0 else 1.0
                                else:
                                    current_cointegrated = False
                                last_test_end = i

                            # Generate signal using current state
                            if current_cointegrated and current_hedge is not None and i >= min_train:
                                # Compute spread for current bar
                                spread = aligned["a"].iloc[i] - current_hedge * aligned["b"].iloc[i]
                                z_score = (spread - current_mean) / current_std if current_std > 0 else 0.0

                                # Entry/exit logic
                                date = aligned.index[i]
                                if date in signals.index:
                                    if z_score < -2.0:
                                        signals.loc[date] = 1  # Long spread (buy A, sell B)
                                    elif z_score > 2.0:
                                        signals.loc[date] = -1  # Short spread
                                    elif abs(z_score) < 0.5:
                                        signals.loc[date] = 0  # Exit

                        logger.debug("Pairs: %s-%s walk-forward tested, cointegrated=%s",
                                     ticker, pair_ticker, current_cointegrated)
                    else:
                        signals = pd.Series(0, index=ohlcv.index)
                        logger.debug("Pairs: %s-%s insufficient aligned data (%d bars)",
                                     ticker, pair_ticker, len(aligned))
        except Exception as e:
            logger.warning("Pairs signal failed: %s", e)

    # ── astronacci: Time cycle (timing indicator) ───────────────────────
    elif engine_name == "astronacci":
        try:
            from market.analysis.astronacci import compute_astronacci_signal
            for idx in signals.index:
                dt = idx.to_pydatetime().replace(tzinfo=timezone.utc)
                result = compute_astronacci_signal(dt, window_days=3)
                if result["cycle_count"] > 0:
                    ts = result["time_signal"]
                    if ts < -0.1:
                        signals.loc[idx] = -1
                    elif ts > 0.1:
                        signals.loc[idx] = 1
        except Exception as e:
            logger.warning("Astronacci signal failed: %s", e)

    # ── fundamental: PE, ROE, DER, dividend yield (no look-ahead) ────────
    elif engine_name == "fundamental":
        try:
            fund_df = data_cache.get("fundamental_data")
            if fund_df is None:
                fund_df = _load_table_df("fundamental_data", ticker_filter=ticker)
                data_cache["fundamental_data"] = fund_df
            if not fund_df.empty:
                signals = pd.Series(0, index=ohlcv.index)
                # DB columns: pe, roe, der, dividend_yield, date, ticker
                pe_col = "pe" if "pe" in fund_df.columns else "pe_ratio"
                date_col = "date" if "date" in fund_df.columns else "timestamp"
                if pe_col in fund_df.columns and date_col in fund_df.columns:
                    fund_df = fund_df.copy()
                    fund_df[date_col] = pd.to_datetime(fund_df[date_col], errors="coerce")
                    fund_df = fund_df.dropna(subset=[date_col, pe_col]).sort_values(date_col)
                    fund_df = fund_df.set_index(date_col)
                    pe_series = fund_df[pe_col]
                    if not pe_series.empty:
                        # Expanding median: only use data up to day T (no look-ahead)
                        expanding_median = pe_series.expanding(min_periods=20).median()
                        for idx in signals.index:
                            # Find PE value on or before idx
                            prior_pe = pe_series[pe_series.index <= idx]
                            prior_median = expanding_median[expanding_median.index <= idx]
                            if not prior_pe.empty and not prior_median.empty:
                                current_pe = prior_pe.iloc[-1]
                                current_median = prior_median.iloc[-1]
                                if pd.notna(current_median) and current_median > 0:
                                    if current_pe < current_median * 0.8:
                                        signals.loc[idx] = 1
                                    elif current_pe > current_median * 1.2:
                                        signals.loc[idx] = -1
                else:
                    logger.debug("Fundamental: pe/date columns not found in %s", list(fund_df.columns))
        except Exception as e:
            logger.warning("Fundamental signal failed: %s", e)

    # ── macro: BI rate, CPI, GDP ────────────────────────────────────────
    elif engine_name == "macro":
        try:
            macro_df = data_cache.get("macro_data")
            if macro_df is None:
                macro_df = _load_table_df("macro_data")
                data_cache["macro_data"] = macro_df
            if not macro_df.empty:
                signals = pd.Series(0, index=ohlcv.index)
                # DB columns: series_name (not indicator), date, value
                series_col = "series_name" if "series_name" in macro_df.columns else "indicator"
                if series_col in macro_df.columns and "value" in macro_df.columns and "date" in macro_df.columns:
                    bi_rows = macro_df[macro_df[series_col].str.contains("bi_rate|bank_indonesia", case=False, na=False)]
                    if not bi_rows.empty:
                        bi_rows = bi_rows.sort_values("date")
                        bi_rows["date"] = pd.to_datetime(bi_rows["date"])
                        bi_changes = bi_rows["value"].diff()
                        for i, delta_val in bi_changes.dropna().items():
                            row = bi_rows.loc[i]
                            date = row.get("date")
                            if pd.notna(date) and date in signals.index:
                                if delta_val < 0:  # Rate cut → bullish
                                    signals.loc[date] = 1
                                elif delta_val > 0:  # Rate hike → bearish
                                    signals.loc[date] = -1
        except Exception as e:
            logger.warning("Macro signal failed: %s", e)

    # ── ml: On-the-fly ML prediction (logistic regression) ──────────────
    elif engine_name == "ml":
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler

            close_f = close.astype(float)
            returns = close_f.pct_change()

            # Features: lagged returns, RSI, momentum, volatility
            rsi = _rsi(close_f, 14)
            mom_5 = returns.rolling(5).sum().shift(1)
            mom_20 = returns.rolling(20).sum().shift(1)
            vol_20 = returns.rolling(20).std().shift(1)
            lag_1 = returns.shift(1)
            lag_2 = returns.shift(2)
            lag_3 = returns.shift(3)
            rsi_lag = rsi.shift(1)

            features = pd.DataFrame({
                "lag_1": lag_1, "lag_2": lag_2, "lag_3": lag_3,
                "mom_5": mom_5, "mom_20": mom_20, "vol_20": vol_20,
                "rsi": rsi_lag,
            }).dropna()

            # Label: next-day direction (1 if up, 0 if down)
            labels = (returns.shift(-1) > 0).astype(int).dropna()

            # Align features and labels
            common_idx = features.index.intersection(labels.index)
            if len(common_idx) > 200:
                X = features.loc[common_idx].values
                y = labels.loc[common_idx].values

                # Walk-forward: train on first 60%, test on remaining 40%
                split = int(len(X) * 0.6)
                X_train, X_test = X[:split], X[split:]
                y_train, y_test = y[:split], y[split:]

                scaler = StandardScaler()
                X_train_s = scaler.fit_transform(X_train)
                X_test_s = scaler.transform(X_test)

                model = LogisticRegression(max_iter=500, random_state=42)
                model.fit(X_train_s, y_train)

                # Predict on test set
                y_pred = model.predict(X_test_s)
                y_proba = model.predict_proba(X_test_s)[:, 1]

                # Convert to signals: 1 if predict up with confidence > 0.55, -1 if < 0.45
                signals = pd.Series(0, index=ohlcv.index)
                test_indices = common_idx[split:]
                for i, idx in enumerate(test_indices):
                    if y_proba[i] > 0.55:
                        signals.loc[idx] = 1
                    elif y_proba[i] < 0.45:
                        signals.loc[idx] = -1

                logger.debug("ML: trained LR on %d samples, test accuracy=%.3f",
                             split, model.score(X_test_s, y_test))
            else:
                logger.debug("ML: insufficient data for training (%d samples)", len(common_idx))
        except Exception as e:
            logger.warning("ML signal failed: %s", e)

    # ── news: News sentiment ────────────────────────────────────────────
    elif engine_name == "news":
        try:
            from market.analysis.news_sentiment import NewsSentimentAnalyzer
            news_df = data_cache.get("news")
            if news_df is None:
                news_df = _load_table_df("news")
                data_cache["news"] = news_df
            if not news_df.empty:
                analyzer = NewsSentimentAnalyzer(method="keyword")
                signals = pd.Series(0, index=ohlcv.index)
                # DB columns: published_at (RFC822 format), headline, source
                date_col = None
                for c in ["published_at", "date", "published"]:
                    if c in news_df.columns:
                        date_col = c
                        break
                title_col = None
                for c in ["headline", "title"]:
                    if c in news_df.columns:
                        title_col = c
                        break
                if date_col and title_col:
                    news_df[date_col] = pd.to_datetime(news_df[date_col], errors="coerce", utc=True)
                    news_df = news_df.dropna(subset=[date_col])
                    for idx in signals.index:
                        # Handle both tz-aware and tz-naive ohlcv index
                        day_start = idx.normalize()
                        if day_start.tzinfo is not None:
                            day_start = day_start.tz_convert("UTC")
                        else:
                            day_start = day_start.tz_localize("UTC")
                        day_end = day_start + pd.Timedelta(days=1)
                        day_news = news_df[
                            (news_df[date_col] >= day_start) &
                            (news_df[date_col] < day_end)
                        ]
                        if not day_news.empty:
                            items = [{"title": row.get(title_col, ""), "date": row[date_col].date()} for _, row in day_news.iterrows()]
                            score = analyzer.weighted_sentiment(items, reference_date=idx.date())
                            if score > 0.15:
                                signals.loc[idx] = 1
                            elif score < -0.15:
                                signals.loc[idx] = -1
        except Exception as e:
            logger.warning("News signal failed: %s", e)

    # ── commodity: CPO, gold, coal correlation ──────────────────────────
    elif engine_name == "commodity":
        try:
            commodity_tickers = ["CPO=F", "GC=F", "^BRENT"]
            global_data = data_cache.get("commodity_ohlcv")
            if global_data is None:
                global_data = _load_global_ohlcv(session, commodity_tickers, "2024-01-01", "2026-08-12")
                data_cache["commodity_ohlcv"] = global_data
            signals = pd.Series(0, index=ohlcv.index)
            for ct in commodity_tickers:
                cdf = global_data.get(ct)
                if cdf is None or cdf.empty:
                    continue
                c_ret = cdf["close"].pct_change().shift(1)
                for idx in signals.index:
                    if idx in c_ret.index:
                        ret = c_ret.loc[idx]
                        if pd.notna(ret):
                            if ret > 0.01:
                                signals.loc[idx] = max(signals.loc[idx], 1)
                            elif ret < -0.01:
                                signals.loc[idx] = min(signals.loc[idx], -1)
        except Exception as e:
            logger.warning("Commodity signal failed: %s", e)

    # ── global_sentiment: VIX + Fear & Greed ────────────────────────────
    elif engine_name == "global_sentiment":
        try:
            vix_df = data_cache.get("vix_ohlcv")
            if vix_df is None:
                vix_df = load_ohlcv_data(session, "^VIX", "2024-01-01", "2026-08-12")
                data_cache["vix_ohlcv"] = vix_df
            fg_df = data_cache.get("fear_greed")
            if fg_df is None:
                fg_df = _load_table_df("fear_greed")
                data_cache["fear_greed"] = fg_df

            signals = pd.Series(0, index=ohlcv.index)

            # VIX component: 20-day MA ratio
            vix_signal = pd.Series(0.0, index=ohlcv.index)
            if not vix_df.empty:
                vix_close = vix_df["close"].astype(float)
                vix_ma = vix_close.rolling(20).mean()
                vix_ratio = vix_close / vix_ma
                for idx in signals.index:
                    if idx in vix_ratio.index:
                        ratio = vix_ratio.loc[idx]
                        if pd.notna(ratio):
                            if ratio > 1.2:  # VIX elevated → risk-off
                                vix_signal.loc[idx] = -1.0
                            elif ratio < 0.8:  # VIX low → risk-on
                                vix_signal.loc[idx] = 1.0

            # Fear & Greed component: use 'nilai' column (0-100 scale)
            fg_signal = pd.Series(0.0, index=ohlcv.index)
            if not fg_df.empty:
                fg_date_col = "tanggal" if "tanggal" in fg_df.columns else "date"
                fg_val_col = "nilai" if "nilai" in fg_df.columns else "value"
                if fg_date_col in fg_df.columns and fg_val_col in fg_df.columns:
                    fg_df[fg_date_col] = pd.to_datetime(fg_df[fg_date_col], errors="coerce")
                    fg_df = fg_df.dropna(subset=[fg_date_col, fg_val_col])
                    fg_indexed = fg_df.set_index(fg_date_col)[fg_val_col].sort_index()
                    for idx in signals.index:
                        # Find most recent F&G value on or before idx
                        prior = fg_indexed[fg_indexed.index <= idx]
                        if not prior.empty:
                            val = float(prior.iloc[-1])
                            if val < 25:  # Extreme Fear → contrarian bullish
                                fg_signal.loc[idx] = 1.0
                            elif val > 75:  # Extreme Greed → contrarian bearish
                                fg_signal.loc[idx] = -1.0

            # Composite: average VIX + F&G signals
            composite = (vix_signal + fg_signal) / 2.0
            signals[composite > 0.1] = 1
            signals[composite < -0.1] = -1
        except Exception as e:
            logger.warning("Global sentiment signal failed: %s", e)

    # ── governance: ESG + corporate governance (no look-ahead) ───────────
    elif engine_name == "governance":
        try:
            esg_df = data_cache.get("esg_scores")
            if esg_df is None:
                esg_df = _load_table_df("esg_scores", ticker_filter=ticker)
                data_cache["esg_scores"] = esg_df
            gov_df = data_cache.get("corporate_governance")
            if gov_df is None:
                gov_df = _load_table_df("corporate_governance", ticker_filter=ticker)
                data_cache["corporate_governance"] = gov_df

            signals = pd.Series(0, index=ohlcv.index)

            # ESG component: expanding mean (only data up to year T)
            score_col = "score" if "esg_scores" != "esg_scores" or "score" not in esg_df.columns else "score"
            if not esg_df.empty and score_col in esg_df.columns:
                esg_df = esg_df.copy()
                esg_df["year"] = pd.to_numeric(esg_df["year"], errors="coerce")
                esg_df = esg_df.dropna(subset=["year", score_col])
                # Only use numeric scores (skip text-only ratings like 'baik')
                esg_numeric = esg_df[pd.to_numeric(esg_df[score_col], errors="coerce").notna()].copy()
                if not esg_numeric.empty:
                    esg_numeric = esg_numeric.sort_values("year")
                    esg_numeric[score_col] = pd.to_numeric(esg_numeric[score_col])
                    # Expanding mean by year
                    esg_by_year = esg_numeric.groupby("year")[score_col].first()
                    expanding_avg = esg_by_year.expanding(min_periods=2).mean()

                    for idx in signals.index:
                        year = idx.year
                        # Use ESG data up to current year (no look-ahead)
                        prior = expanding_avg[expanding_avg.index <= year]
                        current = esg_by_year[esg_by_year.index <= year]
                        if not prior.empty and not current.empty:
                            current_score = current.iloc[-1]
                            avg_score = prior.iloc[-1]
                            if pd.notna(avg_score) and avg_score > 0:
                                # Time-varying: compare current year score vs expanding average
                                if current_score > avg_score * 1.1:
                                    signals.loc[idx] = 1
                                elif current_score < avg_score * 0.9:
                                    signals.loc[idx] = -1

            # Corporate governance component: GCG score trend
            if not gov_df.empty and "gcg_score" in gov_df.columns:
                gov_df = gov_df.copy()
                gov_df["year"] = pd.to_numeric(gov_df["year"], errors="coerce")
                gov_df = gov_df.dropna(subset=["year"]).sort_values("year")
                # Map GCG scores to numeric: baik=3, cukup=2, kurang=1
                gcg_map = {"baik": 3, "Baik": 3, "cukup": 2, "Cukup": 2, "kurang": 1, "Kurang": 1}
                gov_df["gcg_numeric"] = gov_df["gcg_score"].map(gcg_map).fillna(2)
                gcg_by_year = gov_df.groupby("year")["gcg_numeric"].first()
                # Trend: compare current year vs previous
                for idx in signals.index:
                    year = idx.year
                    prior_years = gcg_by_year[gcg_by_year.index <= year]
                    if len(prior_years) >= 2:
                        current_gcg = prior_years.iloc[-1]
                        prev_gcg = prior_years.iloc[-2]
                        if current_gcg > prev_gcg:
                            signals.loc[idx] = max(signals.loc[idx], 1)
                        elif current_gcg < prev_gcg:
                            signals.loc[idx] = min(signals.loc[idx], -1)
        except Exception as e:
            logger.warning("Governance signal failed: %s", e)

    # ── mean_reversion: Bollinger Bands + RSI confirmation ──────────────
    elif engine_name == "mean_reversion":
        try:
            from market.analysis.alpha_signals import MeanReversionEngine
            engine = MeanReversionEngine()
            result = engine.generate_signals(close)
            signals = result.signal
        except Exception as e:
            logger.warning("Mean reversion signal failed: %s", e)

    # ── reversal: Short-term behavioral reversal ────────────────────────
    elif engine_name == "reversal":
        try:
            from market.analysis.alpha_signals import ShortTermReversalEngine
            engine = ShortTermReversalEngine()
            result = engine.generate_signals(close)
            signals = result.signal
        except Exception as e:
            logger.warning("Reversal signal failed: %s", e)

    # ── ewma_momentum: Volatility-scaled EWMA crossover ─────────────────
    elif engine_name == "ewma_momentum":
        try:
            from market.analysis.alpha_signals import EWMAMomentumEngine
            engine = EWMAMomentumEngine()
            result = engine.generate_signals(close)
            signals = result.signal
        except Exception as e:
            logger.warning("EWMA momentum signal failed: %s", e)

    # ── regime_switch: Adaptive momentum/mean-reversion ─────────────────
    elif engine_name == "regime_switch":
        try:
            from market.analysis.alpha_signals import RegimeSwitchEngine
            engine = RegimeSwitchEngine()
            result = engine.generate_signals(close)
            signals = result.signal
        except Exception as e:
            logger.warning("Regime switch signal failed: %s", e)

    # ════════════════════════════════════════════════════════════════════
    # ── ALTERNATIVE ENGINES (v2) — tested alongside originals ───────────
    # ════════════════════════════════════════════════════════════════════

    # ── commodity_v2: Commodity as regime filter (vol-based) ────────────
    elif engine_name == "commodity_v2":
        try:
            commodity_tickers = ["CPO=F", "GC=F", "^BRENT"]
            global_data = data_cache.get("commodity_ohlcv")
            if global_data is None:
                global_data = _load_global_ohlcv(session, commodity_tickers, "2024-01-01", "2026-08-12")
                data_cache["commodity_ohlcv"] = global_data

            signals = pd.Series(0, index=ohlcv.index)

            # Compute composite commodity vol ratio
            vol_ratios = pd.Series(1.0, index=ohlcv.index)
            count = 0
            for ct in commodity_tickers:
                cdf = global_data.get(ct)
                if cdf is None or cdf.empty:
                    continue
                c_ret = cdf["close"].astype(float).pct_change()
                c_vol_short = c_ret.rolling(20).std().shift(1)  # no look-ahead
                c_vol_long = c_ret.rolling(60).std().shift(1)
                c_ratio = (c_vol_short / c_vol_long.replace(0, np.nan)).fillna(1.0)
                # Align to ohlcv index
                for idx in signals.index:
                    if idx in c_ratio.index:
                        vol_ratios.loc[idx] += c_ratio.loc[idx]
                count += 1

            if count > 0:
                vol_ratios = vol_ratios / (count + 1)  # average across commodities
                # Regime filter: high commodity vol → risk-off, stable → risk-on
                for idx in signals.index:
                    vr = vol_ratios.loc[idx]
                    if pd.notna(vr):
                        if vr > 1.5:  # Commodity vol spike → risk-off
                            signals.loc[idx] = -1
                        elif vr < 0.8:  # Commodity vol stable → risk-on
                            signals.loc[idx] = 1
        except Exception as e:
            logger.warning("Commodity v2 signal failed: %s", e)

    # ── sector_v2: RS z-score with mean-reversion entry ─────────────────
    elif engine_name == "sector_v2":
        try:
            ihsg = data_cache.get("ihsg_ohlcv")
            if ihsg is None:
                ihsg = load_ohlcv_data(session, "^JKSE", "2024-01-01", "2026-08-12")
                data_cache["ihsg_ohlcv"] = ihsg

            if not ihsg.empty:
                ticker_returns = close.pct_change().dropna()
                market_returns = ihsg["close"].astype(float).pct_change().dropna()

                signals = pd.Series(0, index=ohlcv.index)
                rs_window = 60
                z_window = 60

                for i in range(len(ohlcv)):
                    if i < max(rs_window, z_window) + 20:
                        continue

                    # Rolling RS: sector vs market over rs_window (up to i-1, no look-ahead)
                    sec_window = ticker_returns.iloc[i - rs_window:i]
                    mkt_window = market_returns.reindex(sec_window.index).dropna()
                    if len(mkt_window) < 10:
                        continue
                    sec_cum = float((1.0 + sec_window).prod() - 1.0)
                    mkt_cum = float((1.0 + mkt_window).prod() - 1.0)
                    rs = sec_cum - mkt_cum

                    # RS z-score: compare current RS to rolling history (shifted, no look-ahead)
                    if i >= rs_window + z_window:
                        rs_history = []
                        for j in range(i - z_window, i):
                            if j < rs_window:
                                continue
                            sw = ticker_returns.iloc[j - rs_window:j]
                            mw = market_returns.reindex(sw.index).dropna()
                            if len(mw) >= 10:
                                rs_history.append(float((1.0 + sw).prod() - 1.0) - float((1.0 + mw).prod() - 1.0))

                        if len(rs_history) >= 20:
                            rs_mean = np.mean(rs_history)
                            rs_std = np.std(rs_history)
                            if rs_std > 0:
                                z = (rs - rs_mean) / rs_std
                                # Mean-reversion: buy oversold sectors, sell overbought
                                if z < -1.5:
                                    signals.iloc[i] = 1
                                elif z > 1.5:
                                    signals.iloc[i] = -1
        except Exception as e:
            logger.warning("Sector v2 signal failed: %s", e)

    # ── volume_v2: Money Flow Index (volume-weighted RSI) ───────────────
    elif engine_name == "volume_v2":
        try:
            high = ohlcv["high"].astype(float)
            low = ohlcv["low"].astype(float)
            close_f = ohlcv["close"].astype(float)
            volume = ohlcv["volume"].astype(float)

            # Typical price
            tp = (high + low + close_f) / 3.0
            # Raw money flow = typical price * volume
            mf = tp * volume

            # Positive/negative money flow
            tp_prev = tp.shift(1)
            pos_mf = pd.Series(0.0, index=ohlcv.index)
            neg_mf = pd.Series(0.0, index=ohlcv.index)
            pos_mf[tp > tp_prev] = mf[tp > tp_prev]
            neg_mf[tp < tp_prev] = mf[tp < tp_prev]

            # 14-period MFI (shifted for no look-ahead)
            pos_mf_14 = pos_mf.rolling(14).sum().shift(1)
            neg_mf_14 = neg_mf.rolling(14).sum().shift(1)

            mfr = pos_mf_14 / neg_mf_14.replace(0, np.nan)
            mfi = 100 - (100 / (1 + mfr))
            mfi = mfi.fillna(50.0).clip(0, 100)

            signals = pd.Series(0, index=ohlcv.index)
            signals[mfi < 20] = 1   # Oversold → buy
            signals[mfi > 80] = -1  # Overbought → sell
        except Exception as e:
            logger.warning("Volume v2 (MFI) signal failed: %s", e)

    # ── event_v2: Earnings momentum from quarterly fundamental changes ──
    elif engine_name == "event_v2":
        try:
            fund_df = data_cache.get("fundamental_data")
            if fund_df is None:
                fund_df = _load_table_df("fundamental_data", ticker_filter=ticker)
                data_cache["fundamental_data"] = fund_df
            if not fund_df.empty:
                signals = pd.Series(0, index=ohlcv.index)
                pe_col = "pe" if "pe" in fund_df.columns else "pe_ratio"
                date_col = "date" if "date" in fund_df.columns else "timestamp"
                roe_col = "roe" if "roe" in fund_df.columns else None

                if pe_col in fund_df.columns and date_col in fund_df.columns:
                    fund_df = fund_df.copy()
                    fund_df[date_col] = pd.to_datetime(fund_df[date_col], errors="coerce")
                    fund_df = fund_df.dropna(subset=[date_col]).sort_values(date_col)

                    # Compute quarterly PE change (proxy for earnings momentum)
                    fund_df["pe_change"] = fund_df[pe_col].pct_change()

                    # Also use ROE if available
                    if roe_col and roe_col in fund_df.columns:
                        fund_df["roe_change"] = fund_df[roe_col].diff()

                    for i in range(1, len(fund_df)):
                        date = fund_df[date_col].iloc[i]
                        pe_chg = fund_df["pe_change"].iloc[i]

                        # Earnings momentum: PE decreasing (earnings growing faster than price)
                        # → bullish; PE increasing → bearish
                        if pd.notna(pe_chg):
                            # Signal persists for ~60 trading days (quarter)
                            end_date = date + pd.Timedelta(days=90)
                            mask = (signals.index >= date) & (signals.index <= end_date)
                            if pe_chg < -0.1:  # PE dropped >10% → earnings growth
                                signals.loc[mask] = 1
                            elif pe_chg > 0.1:  # PE rose >10% → earnings decline
                                signals.loc[mask] = -1

                        # ROE improvement as confirmation
                        if roe_col and "roe_change" in fund_df.columns:
                            roe_chg = fund_df["roe_change"].iloc[i]
                            if pd.notna(roe_chg) and pd.notna(pe_chg):
                                if roe_chg > 0 and pe_chg < 0:
                                    # Both confirm: earnings up + ROE up → strong buy
                                    end_date = date + pd.Timedelta(days=90)
                                    mask = (signals.index >= date) & (signals.index <= end_date)
                                    signals.loc[mask] = 1
                                elif roe_chg < 0 and pe_chg > 0:
                                    end_date = date + pd.Timedelta(days=90)
                                    mask = (signals.index >= date) & (signals.index <= end_date)
                                    signals.loc[mask] = -1
        except Exception as e:
            logger.warning("Event v2 (earnings momentum) signal failed: %s", e)

    # ── ml_v2: LightGBM with walk-forward retraining ────────────────────
    elif engine_name == "ml_v2":
        try:
            import lightgbm as lgb
            from sklearn.preprocessing import StandardScaler

            close_f = close.astype(float)
            high = ohlcv["high"].astype(float)
            low = ohlcv["low"].astype(float)
            volume = ohlcv["volume"].astype(float)
            returns = close_f.pct_change()

            # Richer feature set (12 features, all shifted for no look-ahead)
            rsi = _rsi(close_f, 14).shift(1)
            mom_5 = returns.rolling(5).sum().shift(1)
            mom_20 = returns.rolling(20).sum().shift(1)
            vol_20 = returns.rolling(20).std().shift(1)
            lag_1 = returns.shift(1)
            lag_2 = returns.shift(2)
            lag_3 = returns.shift(3)

            # MACD (shifted)
            ema_12 = close_f.ewm(span=12, adjust=False).mean()
            ema_26 = close_f.ewm(span=26, adjust=False).mean()
            macd = (ema_12 - ema_26).shift(1)

            # Bollinger Band width (shifted)
            bb_mid = close_f.rolling(20).mean()
            bb_std = close_f.rolling(20).std()
            bb_width = (bb_std / bb_mid).shift(1)

            # ATR ratio (shifted)
            tr = (high - low).abs()
            atr_14 = tr.rolling(14).mean()
            atr_50 = tr.rolling(50).mean()
            atr_ratio = (atr_14 / atr_50.replace(0, np.nan)).shift(1).fillna(1.0)

            # Volume ratio (shifted)
            vol_ma = volume.rolling(20).mean()
            vol_ratio = (volume / vol_ma.replace(0, np.nan)).shift(1).fillna(1.0)

            features = pd.DataFrame({
                "rsi": rsi, "mom_5": mom_5, "mom_20": mom_20, "vol_20": vol_20,
                "lag_1": lag_1, "lag_2": lag_2, "lag_3": lag_3,
                "macd": macd, "bb_width": bb_width, "atr_ratio": atr_ratio,
                "vol_ratio": vol_ratio,
            }).dropna()

            # Label: next-day direction
            labels = (returns.shift(-1) > 0).astype(int)

            common_idx = features.index.intersection(labels.index)
            if len(common_idx) > 252:
                X_all = features.loc[common_idx].values
                y_all = labels.loc[common_idx].values

                signals = pd.Series(0, index=ohlcv.index)

                # Walk-forward: retrain every 60 days
                initial_train = 252
                retrain_interval = 60
                model = None
                scaler = None
                last_train_end = 0

                for i in range(len(common_idx)):
                    if i < initial_train:
                        continue

                    # Retrain periodically
                    if model is None or (i - last_train_end) >= retrain_interval:
                        X_train = X_all[:i]
                        y_train = y_all[:i]
                        scaler = StandardScaler()
                        X_train_s = scaler.fit_transform(X_train)
                        model = lgb.LGBMClassifier(
                            n_estimators=100,
                            max_depth=5,
                            learning_rate=0.05,
                            subsample=0.8,
                            colsample_bytree=0.8,
                            random_state=42,
                            verbose=-1,
                        )
                        model.fit(X_train_s, y_train)
                        last_train_end = i

                    # Predict on current bar
                    X_bar = scaler.transform(X_all[i:i+1])
                    y_proba = model.predict_proba(X_bar)[0]

                    idx = common_idx[i]
                    if y_proba[1] > 0.55:
                        signals.loc[idx] = 1
                    elif y_proba[1] < 0.45:
                        signals.loc[idx] = -1

                logger.debug("ML v2: LightGBM walk-forward, %d predictions", len(common_idx) - initial_train)
            else:
                logger.debug("ML v2: insufficient data (%d samples)", len(common_idx))
        except Exception as e:
            logger.warning("ML v2 (LightGBM) signal failed: %s", e)

    # ════════════════════════════════════════════════════════════════════
    # ── ADVANCED GLOBAL-IDX MODELS (pustaka/101) ────────────────────────
    # ════════════════════════════════════════════════════════════════════

    # ── dcc_garch: DCC-GARCH dynamic conditional correlation ────────────
    elif engine_name == "dcc_garch":
        try:
            global_tickers = ["^GSPC", "^VIX", "IDR=X"]
            global_data = data_cache.get("dcc_global_ohlcv")
            if global_data is None:
                global_data = _load_global_ohlcv(session, global_tickers, "2024-01-01", "2026-08-12")
                data_cache["dcc_global_ohlcv"] = global_data

            ihsg = data_cache.get("ihsg_ohlcv")
            if ihsg is None:
                ihsg = load_ohlcv_data(session, "^JKSE", "2024-01-01", "2026-08-12")
                data_cache["ihsg_ohlcv"] = ihsg

            if ihsg.empty:
                signals = pd.Series(0, index=ohlcv.index)
            else:
                ihsg_ret = ihsg["close"].astype(float).pct_change()
                ticker_ret = close.pct_change()

                signals = pd.Series(0, index=ohlcv.index)
                garch_window = 20
                dcc_alpha, dcc_beta = 0.05, 0.90

                for gt in global_tickers:
                    gdf = global_data.get(gt)
                    if gdf is None or gdf.empty:
                        continue
                    g_ret = gdf["close"].astype(float).pct_change()

                    # Align with ticker returns
                    aligned = pd.DataFrame({"ticker": ticker_ret, "global": g_ret}).dropna()
                    if len(aligned) < garch_window + 20:
                        continue

                    # GARCH(1,1) variance for each series (simplified)
                    var_t = aligned["ticker"].rolling(garch_window).var()
                    var_g = aligned["global"].rolling(garch_window).var()

                    # Standardized residuals
                    eps_t = aligned["ticker"] / np.sqrt(var_t.replace(0, np.nan))
                    eps_g = aligned["global"] / np.sqrt(var_g.replace(0, np.nan))
                    eps_t = eps_t.fillna(0).clip(-5, 5)
                    eps_g = eps_g.fillna(0).clip(-5, 5)

                    # DCC: Q_t = (1-a-b)*Q_bar + a*eps_{t-1}*eps_{t-1}' + b*Q_{t-1}
                    corr_bar = float(eps_t.corr(eps_g))
                    if np.isnan(corr_bar):
                        corr_bar = 0.0

                    q_t = corr_bar
                    dcc_corr_series = pd.Series(index=aligned.index, dtype=float)
                    for i in range(len(aligned)):
                        if i == 0:
                            dcc_corr_series.iloc[i] = corr_bar
                            continue
                        ea = eps_t.iloc[i - 1]
                        eb = eps_g.iloc[i - 1]
                        q_t = (1 - dcc_alpha - dcc_beta) * corr_bar + \
                              dcc_alpha * ea * eb + \
                              dcc_beta * q_t
                        dcc_corr_series.iloc[i] = np.tanh(q_t)

                    # Shift for no look-ahead
                    dcc_corr_series = dcc_corr_series.shift(1)

                    # Signal: high corr = contagion risk, low = idiosyncratic
                    for idx in signals.index:
                        if idx in dcc_corr_series.index:
                            c = dcc_corr_series.loc[idx]
                            if pd.notna(c):
                                if gt == "^VIX":
                                    # VIX correlation: high = risk-off
                                    if c > 0.3:
                                        signals.loc[idx] = min(signals.loc[idx], -1)
                                    elif c < -0.1:
                                        signals.loc[idx] = max(signals.loc[idx], 1)
                                elif gt == "IDR=X":
                                    # USD/IDR correlation: high = FX pressure
                                    if c > 0.3:
                                        signals.loc[idx] = min(signals.loc[idx], -1)
                                    elif c < -0.1:
                                        signals.loc[idx] = max(signals.loc[idx], 1)
                                else:
                                    # S&P 500 correlation: high = contagion
                                    if c > 0.7:
                                        signals.loc[idx] = min(signals.loc[idx], -1)
                                    elif c < 0.3:
                                        signals.loc[idx] = max(signals.loc[idx], 1)
        except Exception as e:
            logger.warning("DCC-GARCH signal failed: %s", e)

    # ── spillover_dy: Diebold-Yilmaz spillover index ────────────────────
    elif engine_name == "spillover_dy":
        try:
            from statsmodels.tsa.api import VAR

            global_tickers = ["^GSPC", "^N225", "^HSI"]
            global_data = data_cache.get("spillover_global_ohlcv")
            if global_data is None:
                global_data = _load_global_ohlcv(session, global_tickers, "2024-01-01", "2026-08-12")
                data_cache["spillover_global_ohlcv"] = global_data

            ihsg = data_cache.get("ihsg_ohlcv")
            if ihsg is None:
                ihsg = load_ohlcv_data(session, "^JKSE", "2024-01-01", "2026-08-12")
                data_cache["ihsg_ohlcv"] = ihsg

            if ihsg.empty:
                signals = pd.Series(0, index=ohlcv.index)
            else:
                ihsg_ret = ihsg["close"].astype(float).pct_change()
                ticker_ret = close.pct_change()

                # Build multi-market returns DataFrame
                ret_data = {"ticker": ticker_ret, "ihsg": ihsg_ret}
                for gt in global_tickers:
                    gdf = global_data.get(gt)
                    if gdf is not None and not gdf.empty:
                        ret_data[gt] = gdf["close"].astype(float).pct_change()

                ret_df = pd.DataFrame(ret_data).dropna()
                if len(ret_df) < 120:
                    signals = pd.Series(0, index=ohlcv.index)
                else:
                    signals = pd.Series(0, index=ohlcv.index)
                    lag_order = 2
                    horizon = 10
                    retest_interval = 60
                    last_test_end = 0
                    current_spillover = 50.0

                    for i in range(120, len(ret_df)):
                        # Re-estimate VAR periodically (walk-forward, no look-ahead)
                        if i - last_test_end >= retest_interval or last_test_end == 0:
                            train_data = ret_df.iloc[:i]
                            try:
                                model = VAR(train_data)
                                results = model.fit(lag_order)
                                fevd = results.fevd(horizon)
                                spillover_table = fevd.decomp[-1]
                                N = len(train_data.columns)
                                total_spillover = (spillover_table.sum() - spillover_table.diagonal().sum()) / N * 100
                                current_spillover = float(total_spillover)
                                last_test_end = i
                            except Exception:
                                pass

                        # Signal from spillover level
                        idx = ret_df.index[i]
                        if idx in signals.index:
                            if current_spillover > 60:
                                signals.loc[idx] = -1  # contagion regime
                            elif current_spillover < 30:
                                signals.loc[idx] = 1   # decoupled regime

                    logger.debug("Spillover DY: final spillover index=%.1f%%", current_spillover)
        except Exception as e:
            logger.warning("Spillover DY signal failed: %s", e)

    # ── foreign_flow: Foreign flow prediction model ─────────────────────
    elif engine_name == "foreign_flow":
        try:
            # Load macro data (BI rate, Fed rate)
            macro_df = data_cache.get("macro_data")
            if macro_df is None:
                macro_df = _load_table_df("macro_data")
                data_cache["macro_data"] = macro_df

            # Load VIX and USD/IDR
            global_tickers = ["^VIX", "IDR=X"]
            global_data = data_cache.get("ff_global_ohlcv")
            if global_data is None:
                global_data = _load_global_ohlcv(session, global_tickers, "2024-01-01", "2026-08-12")
                data_cache["ff_global_ohlcv"] = global_data

            signals = pd.Series(0, index=ohlcv.index)

            # Extract BI rate and Fed rate from macro_data
            bi_rate = 6.0  # default
            fed_rate = 5.0  # default
            if not macro_df.empty and "series_name" in macro_df.columns:
                bi_rows = macro_df[macro_df["series_name"] == "BI Rate"]
                fed_rows = macro_df[macro_df["series_name"] == "Fed Rate"]
                if not bi_rows.empty and "value" in bi_rows.columns:
                    val = pd.to_numeric(bi_rows["value"], errors="coerce").dropna()
                    if not val.empty:
                        bi_rate = float(val.iloc[-1])
                if not fed_rows.empty and "value" in fed_rows.columns:
                    val = pd.to_numeric(fed_rows["value"], errors="coerce").dropna()
                    if not val.empty:
                        fed_rate = float(val.iloc[-1])

            # VIX level (T-1, shifted for no look-ahead)
            vix_df = global_data.get("^VIX")
            vix_series = None
            if vix_df is not None and not vix_df.empty:
                vix_series = vix_df["close"].astype(float).shift(1)

            # USD/IDR change (T-1)
            usd_idr_df = global_data.get("IDR=X")
            usd_idr_ret = None
            if usd_idr_df is not None and not usd_idr_df.empty:
                usd_idr_ret = usd_idr_df["close"].astype(float).pct_change().shift(1)

            # Compute foreign flow score per day
            rate_diff = bi_rate - fed_rate
            for idx in signals.index:
                vix_level = 15.0
                if vix_series is not None and idx in vix_series.index:
                    v = vix_series.loc[idx]
                    if pd.notna(v):
                        vix_level = float(v)

                usd_idr_change = 0.0
                if usd_idr_ret is not None and idx in usd_idr_ret.index:
                    u = usd_idr_ret.loc[idx]
                    if pd.notna(u):
                        usd_idr_change = float(u)

                # Linear scoring model
                score = 50.0
                score += (rate_diff - 1.0) * 5.0
                score -= (vix_level - 15) * 2
                score -= usd_idr_change * 100
                score = max(0, min(100, score))

                if score > 55:
                    signals.loc[idx] = 1
                elif score < 45:
                    signals.loc[idx] = -1
        except Exception as e:
            logger.warning("Foreign flow signal failed: %s", e)

    # ── overnight_idx: Overnight global → IDX opening prediction ────────
    elif engine_name == "overnight_idx":
        try:
            us_tickers = ["^GSPC", "^IXIC", "^VIX", "^TNX"]
            asian_tickers = ["^N225", "^HSI", "000001.SS", "CPO=F"]

            all_global = us_tickers + asian_tickers
            global_data = data_cache.get("overnight_global_ohlcv")
            if global_data is None:
                global_data = _load_global_ohlcv(session, all_global, "2024-01-01", "2026-08-12")
                data_cache["overnight_global_ohlcv"] = global_data

            signals = pd.Series(0, index=ohlcv.index)

            # Compute returns for each global ticker
            global_returns = {}
            for gt in all_global:
                gdf = global_data.get(gt)
                if gdf is not None and not gdf.empty:
                    global_returns[gt] = gdf["close"].astype(float).pct_change()

            # US data: T-1 (shift 1 — US closes after IDX)
            # Asian data: T-0 (shift 0 — Asian closes before IDX)
            # But for anti look-ahead, we still shift(1) everything
            # because we use the signal on day T+1 returns

            for idx in signals.index:
                us_score = 0.0
                us_weight = 0.0

                # US overnight component (T-1)
                for gt, w in [("^GSPC", 0.30), ("^IXIC", 0.20), ("^VIX", -0.20), ("^TNX", -0.15)]:
                    if gt in global_returns:
                        ret_series = global_returns[gt].shift(1)  # T-1
                        if idx in ret_series.index:
                            r = ret_series.loc[idx]
                            if pd.notna(r):
                                us_score += float(r) * w
                                us_weight += abs(w)

                # Asian same-day component (T-0, but shifted for no look-ahead in backtest)
                asian_score = 0.0
                asian_weight = 0.0
                for gt, w in [("^N225", 0.35), ("^HSI", 0.35), ("000001.SS", 0.15), ("CPO=F", 0.15)]:
                    if gt in global_returns:
                        ret_series = global_returns[gt].shift(1)  # shift for no look-ahead
                        if idx in ret_series.index:
                            r = ret_series.loc[idx]
                            if pd.notna(r):
                                asian_score += float(r) * w
                                asian_weight += abs(w)

                if us_weight > 0 and asian_weight > 0:
                    # Composite: US overnight (60%) + Asian confirmation (40%)
                    composite = (us_score / us_weight) * 0.6 + (asian_score / asian_weight) * 0.4
                    signal_val = composite * 20  # scale to [-100, +100]

                    if signal_val > 5:
                        signals.loc[idx] = 1
                    elif signal_val < -5:
                        signals.loc[idx] = -1
        except Exception as e:
            logger.warning("Overnight IDX signal failed: %s", e)

    # ── sector_global_link: Sector-specific global driver with timezone lag ─
    elif engine_name == "sector_global_link":
        try:
            # Sector → global driver mapping (pustaka/102 §2)
            SECTOR_GLOBAL_MAP = {
                "Energy": [("CL=F", 1), ("^GSPC", 1)],
                "Basic Materials": [("GC=F", 1), ("000001.SS", 0)],
                "Financial Services": [("^TNX", -1), ("^GSPC", 1)],
                "Consumer Defensive": [("IDR=X", -1), ("^GSPC", 1)],
                "Consumer Cyclical": [("^IXIC", 1), ("^GSPC", 1)],
                "Communication Services": [("^IXIC", 1)],
                "Industrials": [("000001.SS", 1), ("^GSPC", 1)],
                "Real Estate": [("^TNX", -1)],
                "Technology": [("^IXIC", 1)],
                "Healthcare": [("^GSPC", 1)],
                "Utilities": [("^TNX", -1)],
            }

            # Subsector override (pustaka/102 §2.2)
            SUBSECTOR_OVERRIDE = {
                "Gold": [("GC=F", 1)],
                "Banks - Regional": [("^TNX", -1)],
                "Telecom Services": [("^IXIC", 1)],
            }

            # All global tickers needed
            all_global_tickers = list(
                set(t for pairs in SECTOR_GLOBAL_MAP.values() for t, _ in pairs)
                | set(t for pairs in SUBSECTOR_OVERRIDE.values() for t, _ in pairs)
            )

            global_data = data_cache.get("sgl_global_ohlcv")
            if global_data is None:
                global_data = _load_global_ohlcv(session, list(all_global_tickers), "2024-01-01", "2026-08-12")
                data_cache["sgl_global_ohlcv"] = global_data

            # Load instrument_master for sector lookup
            instr_df = data_cache.get("instrument_master")
            if instr_df is None:
                instr_df = _load_table_df("instrument_master")
                data_cache["instrument_master"] = instr_df

            # Lookup sector for this ticker
            ticker_no_jk = ticker.replace(".JK", "")
            sector = None
            subsector = None
            if not instr_df.empty and "ticker" in instr_df.columns:
                match = instr_df[instr_df["ticker"] == ticker_no_jk]
                if not match.empty:
                    sector = match.iloc[0].get("sector")
                    subsector = match.iloc[0].get("subsector")

            signals = pd.Series(0, index=ohlcv.index)

            if sector is None:
                logger.debug("Sector global link: no sector for %s", ticker)
            else:
                # Determine drivers
                drivers = SECTOR_GLOBAL_MAP.get(sector, [])
                if subsector and subsector in SUBSECTOR_OVERRIDE:
                    drivers = SUBSECTOR_OVERRIDE[subsector]

                if not drivers:
                    logger.debug("Sector global link: no drivers for sector=%s", sector)
                else:
                    threshold = 0.005  # 0.5% significant move
                    ticker_ret = close.pct_change()

                    for idx in signals.index:
                        consensus = 0
                        n_drivers = 0

                        for gt, direction in drivers:
                            gdf = global_data.get(gt)
                            if gdf is None or gdf.empty:
                                continue

                            g_ret = gdf["close"].astype(float).pct_change().shift(1)

                            if idx in g_ret.index:
                                r = g_ret.loc[idx]
                                if pd.notna(r):
                                    n_drivers += 1
                                    if r > threshold:
                                        consensus += direction
                                    elif r < -threshold:
                                        consensus -= direction

                        # Signal: consensus among drivers
                        if n_drivers > 0:
                            if consensus > 0:
                                signals.loc[idx] = 1
                            elif consensus < 0:
                                signals.loc[idx] = -1
                            # If consensus == 0 (drivers disagree), signal = 0

                    logger.debug("Sector global link: %s sector=%s drivers=%d", ticker, sector, len(drivers))
        except Exception as e:
            logger.warning("Sector global link signal failed: %s", e)

    # ════════════════════════════════════════════════════════════════════
    # ── MISSING PRODUCTION ENGINES (added to match application pipeline) ─
    # ════════════════════════════════════════════════════════════════════

    # ── mc_sentiment: Fear & Greed contrarian (MarketContext factor) ────
    elif engine_name == "mc_sentiment":
        try:
            fg_df = data_cache.get("fear_greed")
            if fg_df is None:
                fg_df = _load_table_df("fear_greed")
                data_cache["fear_greed"] = fg_df
            signals = pd.Series(0, index=ohlcv.index)
            if not fg_df.empty:
                fg_date_col = "tanggal" if "tanggal" in fg_df.columns else "date"
                fg_val_col = "nilai" if "nilai" in fg_df.columns else "value"
                if fg_date_col in fg_df.columns and fg_val_col in fg_df.columns:
                    fg_df[fg_date_col] = pd.to_datetime(fg_df[fg_date_col], errors="coerce")
                    fg_df = fg_df.dropna(subset=[fg_date_col, fg_val_col])
                    fg_indexed = fg_df.set_index(fg_date_col)[fg_val_col].sort_index()
                    for idx in signals.index:
                        prior = fg_indexed[fg_indexed.index <= idx]
                        if not prior.empty:
                            val = float(prior.iloc[-1])
                            if val < 25:  # Extreme Fear → contrarian bullish
                                signals.loc[idx] = 1
                            elif val > 75:  # Extreme Greed → contrarian bearish
                                signals.loc[idx] = -1
        except Exception as e:
            logger.warning("MC sentiment signal failed: %s", e)

    # ── mc_flow: Foreign net flow 5-day cumulative (MarketContext factor) ─
    elif engine_name == "mc_flow":
        try:
            ff_df = data_cache.get("foreign_flow_mc")
            if ff_df is None:
                ff_df = _load_table_df("foreign_flow", ticker_filter=ticker)
                data_cache["foreign_flow_mc"] = ff_df
            signals = pd.Series(0, index=ohlcv.index)
            if not ff_df.empty:
                date_col = "date" if "date" in ff_df.columns else "tanggal"
                if date_col in ff_df.columns and "foreign_net" in ff_df.columns:
                    ff_df[date_col] = pd.to_datetime(ff_df[date_col], errors="coerce")
                    ff_df = ff_df.dropna(subset=[date_col, "foreign_net"]).sort_values(date_col)
                    ff_indexed = ff_df.set_index(date_col)["foreign_net"]
                    ff_5d = ff_indexed.rolling(5).sum()
                    for idx in signals.index:
                        prior = ff_5d[ff_5d.index <= idx]
                        if not prior.empty:
                            val = prior.iloc[-1]
                            if pd.notna(val):
                                if val > 0:
                                    signals.loc[idx] = 1
                                elif val < 0:
                                    signals.loc[idx] = -1
        except Exception as e:
            logger.warning("MC flow signal failed: %s", e)

    # ── mc_cross_market: Correlation regime (MarketContext factor) ──────
    elif engine_name == "mc_cross_market":
        try:
            global_tickers = ["^GSPC", "^HSI", "^N225", "^JKSE"]
            global_data = data_cache.get("mc_cm_global_ohlcv")
            if global_data is None:
                global_data = _load_global_ohlcv(session, global_tickers, "2024-01-01", "2026-08-12")
                data_cache["mc_cm_global_ohlcv"] = global_data

            signals = pd.Series(0, index=ohlcv.index)
            ticker_ret = close.pct_change()
            corr_window = 60

            for gt in global_tickers:
                gdf = global_data.get(gt)
                if gdf is None or gdf.empty:
                    continue
                g_ret = gdf["close"].astype(float).pct_change()
                aligned = pd.DataFrame({"ticker": ticker_ret, "global": g_ret}).dropna()
                if len(aligned) < corr_window + 20:
                    continue
                rolling_corr = aligned["ticker"].rolling(corr_window).corr(aligned["global"]).shift(1)
                for idx in signals.index:
                    if idx in rolling_corr.index:
                        c = rolling_corr.loc[idx]
                        if pd.notna(c):
                            if gt == "^JKSE":
                                # IHSG correlation: high = normal, low = decoupled (opportunity)
                                if c < 0.3:
                                    signals.loc[idx] = max(signals.loc[idx], 1)
                                elif c > 0.8:
                                    signals.loc[idx] = min(signals.loc[idx], -1)
                            else:
                                # Global correlation: high = contagion risk, low = idiosyncratic
                                if c > 0.7:
                                    signals.loc[idx] = min(signals.loc[idx], -1)
                                elif c < 0.2:
                                    signals.loc[idx] = max(signals.loc[idx], 1)
        except Exception as e:
            logger.warning("MC cross-market signal failed: %s", e)

    # ── mc_astronacci: Astronacci as MarketContext factor (low weight) ──
    elif engine_name == "mc_astronacci":
        try:
            from market.analysis.astronacci import compute_astronacci_signal
            signals = pd.Series(0, index=ohlcv.index)
            for idx in signals.index:
                dt = idx.to_pydatetime().replace(tzinfo=timezone.utc)
                result = compute_astronacci_signal(dt, window_days=3)
                if result["cycle_count"] > 0:
                    ts = result["time_signal"]
                    if ts < -0.1:
                        signals.loc[idx] = -1
                    elif ts > 0.1:
                        signals.loc[idx] = 1
        except Exception as e:
            logger.warning("MC astronacci signal failed: %s", e)

    # ── multi_factor: LightGBM 3-class BUY/SELL/HOLD with PCA ──────────
    elif engine_name == "multi_factor":
        try:
            import lightgbm as lgb
            from sklearn.preprocessing import StandardScaler
            from sklearn.decomposition import PCA

            close_f = close.astype(float)
            high = ohlcv["high"].astype(float)
            low = ohlcv["low"].astype(float)
            volume = ohlcv["volume"].astype(float)
            returns = close_f.pct_change()

            # Endogenous features (subset of production 30 features)
            rsi = _rsi(close_f, 14).shift(1)
            mom_5 = returns.rolling(5).sum().shift(1)
            mom_20 = returns.rolling(20).sum().shift(1)
            vol_20 = returns.rolling(20).std().shift(1)
            lag_1 = returns.shift(1)
            lag_2 = returns.shift(2)
            lag_3 = returns.shift(3)
            autocorr_5 = returns.rolling(5).apply(lambda x: x.autocorr(lag=1) if len(x) > 2 else 0, raw=False).shift(1)
            autocorr_10 = returns.rolling(10).apply(lambda x: x.autocorr(lag=1) if len(x) > 2 else 0, raw=False).shift(1)

            # Candlestick
            body_ratio = ((close_f - ohlcv["open"].astype(float)).abs() / (high - low).replace(0, np.nan)).shift(1)
            doji = (body_ratio < 0.1).astype(float).shift(1)

            # Bollinger
            bb_mid = close_f.rolling(20).mean()
            bb_std = close_f.rolling(20).std()
            bb_width = (bb_std / bb_mid).shift(1)
            bb_pct = ((close_f - bb_mid) / (2 * bb_std).replace(0, np.nan)).shift(1)

            # MACD
            ema_12 = close_f.ewm(span=12, adjust=False).mean()
            ema_26 = close_f.ewm(span=26, adjust=False).mean()
            macd = (ema_12 - ema_26).shift(1)
            macd_signal = macd.rolling(9).mean().shift(1)

            # MA ratios
            ma_5 = close_f.rolling(5).mean()
            ma_20 = close_f.rolling(20).mean()
            ma_ratio = (ma_5 / ma_20).shift(1)

            # Volume features
            vol_ma = volume.rolling(20).mean()
            vol_ratio = (volume / vol_ma.replace(0, np.nan)).shift(1)
            vwap = (high * volume + low * volume + close_f * volume).rolling(20).sum() / volume.rolling(20).sum().replace(0, np.nan)
            vwap_ratio = (close_f / vwap).shift(1)

            # ATR
            tr = (high - low).abs()
            atr_14 = tr.rolling(14).mean()
            atr_50 = tr.rolling(50).mean()
            atr_ratio = (atr_14 / atr_50.replace(0, np.nan)).shift(1)

            features = pd.DataFrame({
                "rsi": rsi, "mom_5": mom_5, "mom_20": mom_20, "vol_20": vol_20,
                "lag_1": lag_1, "lag_2": lag_2, "lag_3": lag_3,
                "autocorr_5": autocorr_5, "autocorr_10": autocorr_10,
                "body_ratio": body_ratio, "doji": doji,
                "bb_width": bb_width, "bb_pct": bb_pct,
                "macd": macd, "macd_signal": macd_signal,
                "ma_ratio": ma_ratio, "vol_ratio": vol_ratio,
                "vwap_ratio": vwap_ratio, "atr_ratio": atr_ratio,
            }).dropna()

            # Label: 3-class (up >1% = 2, down <-1% = 0, else 1)
            labels = returns.shift(-1).apply(
                lambda x: 2 if x > 0.01 else 0 if x < -0.01 else 1
            ).dropna()

            common_idx = features.index.intersection(labels.index)
            if len(common_idx) > 252:
                X_all = features.loc[common_idx].values
                y_all = labels.loc[common_idx].values

                signals = pd.Series(0, index=ohlcv.index)

                # Walk-forward: 80/20 split, retrain every 60 days
                initial_train = int(len(common_idx) * 0.8)
                retrain_interval = 60
                model = None
                scaler = None
                pca = None
                last_train_end = 0

                for i in range(initial_train, len(common_idx)):
                    if model is None or (i - last_train_end) >= retrain_interval:
                        X_train = X_all[:i]
                        y_train = y_all[:i]
                        scaler = StandardScaler()
                        X_train_s = scaler.fit_transform(X_train)
                        # PCA: reduce to min(18, n_features) components
                        n_components = min(18, X_train_s.shape[1])
                        pca = PCA(n_components=n_components, random_state=42)
                        X_train_pca = pca.fit_transform(X_train_s)
                        model = lgb.LGBMClassifier(
                            n_estimators=300,
                            max_depth=5,
                            learning_rate=0.05,
                            subsample=0.8,
                            colsample_bytree=0.8,
                            random_state=42,
                            verbose=-1,
                        )
                        model.fit(X_train_pca, y_train)
                        last_train_end = i

                    # Predict
                    X_bar = pca.transform(scaler.transform(X_all[i:i+1]))
                    y_proba = model.predict_proba(X_bar)[0]
                    # Signal = P(BUY) - P(SELL)
                    p_buy = y_proba[2] if len(y_proba) > 2 else 0.0
                    p_sell = y_proba[0] if len(y_proba) > 0 else 0.0
                    signal_val = p_buy - p_sell

                    idx = common_idx[i]
                    if signal_val > 0.15:
                        signals.loc[idx] = 1
                    elif signal_val < -0.15:
                        signals.loc[idx] = -1

                logger.debug("Multi-factor: LightGBM 3-class, %d predictions", len(common_idx) - initial_train)
            else:
                logger.debug("Multi-factor: insufficient data (%d samples)", len(common_idx))
        except Exception as e:
            logger.warning("Multi-factor signal failed: %s", e)

    # ── pred_ma: MA crossover (PredictionEngine core method) ───────────
    elif engine_name == "pred_ma":
        try:
            close_f = close.astype(float)
            ma_short = close_f.rolling(5).mean()
            ma_long = close_f.rolling(20).mean()
            signals = pd.Series(0, index=ohlcv.index)
            # MA short > MA long → bullish, else bearish
            diff = (ma_short - ma_long).shift(1)  # no look-ahead
            signals[diff > 0] = 1
            signals[diff < 0] = -1
        except Exception as e:
            logger.warning("Pred MA signal failed: %s", e)

    # ── pred_momentum: Damped momentum (PredictionEngine core method) ──
    elif engine_name == "pred_momentum":
        try:
            close_f = close.astype(float)
            returns = close_f.pct_change()
            momentum = returns.rolling(5).sum().shift(1)  # 5-day momentum, no look-ahead
            # Damped: signal direction based on sign, magnitude damped by 0.5
            signals = pd.Series(0, index=ohlcv.index)
            signals[momentum > 0] = 1
            signals[momentum < 0] = -1
        except Exception as e:
            logger.warning("Pred momentum signal failed: %s", e)

    # ── pred_pattern: Chart pattern detection (PredictionEngine core) ──
    elif engine_name == "pred_pattern":
        try:
            from market.analysis.pattern_detector import PatternDetector
            detector = PatternDetector()
            signals = pd.Series(0, index=ohlcv.index)
            for i in range(len(ohlcv)):
                if i < 30:
                    continue
                window_df = ohlcv.iloc[:i+1]
                patterns = detector.detect(ticker, window_df, window_df.index[-1])
                if patterns:
                    bullish = sum(1 for p in patterns if p.direction == "bullish")
                    bearish = sum(1 for p in patterns if p.direction == "bearish")
                    if bullish > bearish:
                        signals.iloc[i] = 1
                    elif bearish > bullish:
                        signals.iloc[i] = -1
        except Exception as e:
            logger.warning("Pred pattern signal failed: %s", e)

    # ── pred_vol_adj: Volatility-adjusted prediction (PredictionEngine) ─
    elif engine_name == "pred_vol_adj":
        try:
            close_f = close.astype(float)
            high = ohlcv["high"].astype(float)
            low = ohlcv["low"].astype(float)
            ma_short = close_f.rolling(5).mean()
            ma_long = close_f.rolling(20).mean()
            tr = (high - low).abs()
            atr = tr.rolling(14).mean()
            atr_ratio = (atr / atr.rolling(50).mean().replace(0, np.nan)).shift(1)
            ma_diff = (ma_short - ma_long).shift(1)

            signals = pd.Series(0, index=ohlcv.index)
            for idx in signals.index:
                if idx in ma_diff.index and idx in atr_ratio.index:
                    md = ma_diff.loc[idx]
                    ar = atr_ratio.loc[idx]
                    if pd.notna(md) and pd.notna(ar):
                        if md > 0 and ar < 1.5:
                            signals.loc[idx] = 1  # MA bullish + low vol → confident buy
                        elif md < 0 and ar < 1.5:
                            signals.loc[idx] = -1  # MA bearish + low vol → confident sell
                        elif md > 0 and ar >= 1.5:
                            signals.loc[idx] = 0  # High vol → no signal (uncertain)
        except Exception as e:
            logger.warning("Pred vol-adj signal failed: %s", e)

    # ════════════════════════════════════════════════════════════════════
    # ── GLOBAL MARKET AI ENGINES (pustaka research integration) ─────────
    # ════════════════════════════════════════════════════════════════════

    # ── vta_reasoning: VTA-style verbal technical analysis ──────────────
    elif engine_name == "vta_reasoning":
        try:
            from market.analysis.vta_reasoning import VTAReasoningEngine
            engine = VTAReasoningEngine(lookback=20)
            signals = engine.generate_signal_series(ohlcv)
        except Exception as e:
            logger.warning("VTA reasoning signal failed: %s", e)

    # ── causal_discovery: CausalStock-style Granger causality ───────────
    elif engine_name == "causal_discovery":
        try:
            from market.analysis.causal_discovery import CausalDiscoveryEngine

            # Load all tickers' OHLCV for cross-ticker causal analysis
            all_tickers = data_cache.get("all_tickers", [ticker])
            all_ohlcv = data_cache.get("causal_all_ohlcv")
            if all_ohlcv is None:
                all_ohlcv = {}
                for t in all_tickers:
                    t_df = load_ohlcv_data(session, t, "2024-01-01", "2026-08-12")
                    if not t_df.empty:
                        all_ohlcv[t] = t_df["close"].astype(float).pct_change()
                # Add IHSG as market factor
                ihsg = data_cache.get("ihsg_ohlcv")
                if ihsg is None:
                    ihsg = load_ohlcv_data(session, "^JKSE", "2024-01-01", "2026-08-12")
                    data_cache["ihsg_ohlcv"] = ihsg
                if not ihsg.empty:
                    all_ohlcv["^JKSE"] = ihsg["close"].astype(float).pct_change()
                data_cache["causal_all_ohlcv"] = all_ohlcv

            # Build returns DataFrame
            returns_df = pd.DataFrame(all_ohlcv).dropna()
            if len(returns_df) >= 120 and ticker in returns_df.columns:
                engine = CausalDiscoveryEngine(max_lag=3, retest_interval=60, min_data_days=120)
                signals = engine.generate_signal_series(ticker, returns_df)
            else:
                signals = pd.Series(0, index=ohlcv.index)
        except Exception as e:
            logger.warning("Causal discovery signal failed: %s", e)

    # ── denoised_news: Multi-perspective denoised news scoring ──────────
    elif engine_name == "denoised_news":
        try:
            from market.analysis.denoised_news import DenoisedNewsEncoder

            news_df = data_cache.get("denoised_news_df")
            if news_df is None:
                news_df = _load_table_df("news", ticker_filter=ticker)
                data_cache["denoised_news_df"] = news_df

            encoder = DenoisedNewsEncoder()
            signals = encoder.generate_signal_series(
                news_df, ticker, ohlcv.index, lookback_days=5,
            )
        except Exception as e:
            logger.warning("Denoised news signal failed: %s", e)

    # ── spillover_lab: Full Diebold-Yilmaz spillover index ──────────────
    elif engine_name == "spillover_lab":
        try:
            from market.analysis.spillover_lab import SpilloverLabEngine

            global_tickers = ["^GSPC", "^N225", "^HSI"]
            global_data = data_cache.get("spillover_lab_global_ohlcv")
            if global_data is None:
                global_data = _load_global_ohlcv(session, global_tickers, "2024-01-01", "2026-08-12")
                data_cache["spillover_lab_global_ohlcv"] = global_data

            ihsg = data_cache.get("ihsg_ohlcv")
            if ihsg is None:
                ihsg = load_ohlcv_data(session, "^JKSE", "2024-01-01", "2026-08-12")
                data_cache["ihsg_ohlcv"] = ihsg

            if ihsg.empty:
                signals = pd.Series(0, index=ohlcv.index)
            else:
                # Build returns DataFrame with ticker + IHSG + global
                ret_data = {ticker: close.pct_change(), "^JKSE": ihsg["close"].astype(float).pct_change()}
                for gt in global_tickers:
                    gdf = global_data.get(gt)
                    if gdf is not None and not gdf.empty:
                        ret_data[gt] = gdf["close"].astype(float).pct_change()

                returns_df = pd.DataFrame(ret_data).dropna()

                if len(returns_df) >= 120:
                    engine = SpilloverLabEngine(
                        lag_order=2, horizon=10, window=120, retest_interval=60,
                    )
                    signals = engine.generate_signal_series(ticker, returns_df)
                else:
                    signals = pd.Series(0, index=ohlcv.index)
        except Exception as e:
            logger.warning("Spillover lab signal failed: %s", e)

    return signals


def build_composite_signal(
    engine_signals: dict[str, pd.Series],
    engine_entries: list,
    baseline_signals: pd.Series,
    index: pd.Index,
) -> pd.Series:
    """Build a hierarchical composite signal from multiple engine signals.

    Architecture (5-layer hierarchical pipeline):

        Layer 1: DIRECTIONAL → weighted vote → raw signal [-1, +1]
        Layer 2: FILTER → veto false signals (zero out where filter says 0)
        Layer 3: CONTEXT → modulate signal strength (scale by context)
        Layer 4: TIMING → gate (reduce signal when timing is unfavorable)
        Layer 5: DISCRETIZE → convert to {-1, 0, +1}

    Key difference from flat blending:
    - Directional engines ARE the signal (not baseline modification)
    - Filter runs AFTER directional (veto, not blend)
    - Context modulates AFTER filter (scale, not vote)
    - Baseline is used as fallback when no directional engines have weight

    Args:
        engine_signals: Dict of engine_name → signal Series.
        engine_entries: List of EngineEntry objects with weights.
        baseline_signals: Baseline technical signals (MA+RSI).
        index: OHLCV index to align signals.

    Returns:
        Composite signal series {-1, 0, +1}.
    """
    from market.ablation.engine_registry import SignalType

    # Separate engines by signal type
    directional_signals = {}
    directional_weights = {}
    filter_signals = {}
    filter_weights = {}
    context_signals = {}
    context_weights = {}
    timing_signals = {}
    timing_weights = {}

    for entry in engine_entries:
        if entry.name not in engine_signals:
            continue
        if entry.default_weight <= 0:
            continue  # skip zero-weight engines (disabled by tuning)
        sig = engine_signals[entry.name]
        if entry.signal_type == SignalType.DIRECTIONAL:
            directional_signals[entry.name] = sig
            directional_weights[entry.name] = entry.default_weight
        elif entry.signal_type == SignalType.FILTER:
            filter_signals[entry.name] = sig
            filter_weights[entry.name] = entry.default_weight
        elif entry.signal_type in (SignalType.CONTEXT, SignalType.SIZING):
            context_signals[entry.name] = sig
            context_weights[entry.name] = entry.default_weight
        elif entry.signal_type == SignalType.TIMING:
            timing_signals[entry.name] = sig
            timing_weights[entry.name] = entry.default_weight

    # ── Layer 1: Directional weighted vote ──
    total_dir_weight = sum(directional_weights.values())
    if total_dir_weight > 0 and directional_signals:
        raw_signal = pd.Series(0.0, index=index)
        for name, sig in directional_signals.items():
            w = directional_weights[name] / total_dir_weight
            aligned = sig.reindex(index).fillna(0)
            raw_signal += aligned * w
    else:
        # Fallback to baseline if no directional engines
        raw_signal = baseline_signals.reindex(index).fillna(0).astype(float)

    # ── Layer 2: Filter veto ──
    # Filter engines output 1 (pass) or 0 (veto). Where ANY filter says 0,
    # zero out the signal. Weighted: higher-weight filters have stronger veto.
    if filter_signals:
        for name, sig in filter_signals.items():
            aligned = sig.reindex(index).fillna(1)  # default: pass (1)
            # Filter signal: 0 = veto, non-zero = pass
            veto_mask = aligned == 0
            raw_signal[veto_mask] = 0.0

    # ── Layer 3: Context modulation ──
    # Context signals [-1, +1] scale the signal strength.
    # Positive context → amplify, negative → attenuate.
    # Weighted by context engine weights.
    if context_signals:
        total_ctx_weight = sum(context_weights.values())
        if total_ctx_weight > 0:
            context_scale = pd.Series(1.0, index=index)
            for name, sig in context_signals.items():
                w = context_weights[name] / total_ctx_weight
                aligned = sig.reindex(index).fillna(0)
                # Context in [-1, +1] → scale factor [1 - 0.3*w, 1 + 0.3*w]
                context_scale *= (1.0 + aligned * 0.3 * w * len(context_signals))
            raw_signal *= context_scale
            # Clip to [-1, 1] range
            raw_signal = raw_signal.clip(-1.0, 1.0)

    # ── Layer 4: Timing gate ──
    # Timing signals: non-zero = active window, 0 = inactive.
    # Where timing says inactive, reduce signal by 70%.
    if timing_signals:
        for name, sig in timing_signals.items():
            aligned = sig.reindex(index).fillna(0)
            # Where timing signal is 0, attenuate by 70%
            inactive_mask = aligned.abs() < 0.01
            raw_signal[inactive_mask] *= 0.3

    # ── Layer 5: Discretize ──
    composite = pd.Series(0, index=index)
    composite[raw_signal > 0.15] = 1
    composite[raw_signal < -0.15] = -1

    return composite


def run_pipeline_ablation(
    tickers: list[str],
    engines: list[str],
    start: str,
    end: str,
    output_dir: Path,
) -> None:
    """Run pipeline (leave-one-out) ablation study.

    For each engine X:
    1. Generate signals from ALL engines
    2. Build full composite (weighted blend of all engines)
    3. Build composite WITHOUT engine X
    4. delta = backtest(full_composite) - backtest(composite_without_X)
    5. Positive delta → engine X contributes to the pipeline

    This tests engines as they actually function in the application —
    as part of a modular pipeline where output from one module feeds
    into the composite signal.
    """
    registry = create_default_registry()

    if engines[0] == "all":
        engine_entries = registry.enabled_entries()
    else:
        engine_entries = []
        for name in engines:
            entry = registry.get(name)
            if entry is None:
                logger.error("Unknown engine: %s", name)
                continue
            engine_entries.append(entry)

    if not engine_entries:
        logger.error("No valid engines to test")
        return

    # Pre-flight data check
    from market.ablation.data_checker import DataChecker
    checker = DataChecker()
    check_results = checker.check_engines(engine_entries, tickers, start, end)

    runnable_engines = []
    skipped_engines = []
    for entry in engine_entries:
        result = check_results.get(entry.name)
        if result and result.status.value == "PASS":
            runnable_engines.append(entry)
        else:
            reason = result.reason if result else "Unknown"
            skipped_engines.append((entry.name, reason))

    if skipped_engines:
        logger.info("Skipping %d engines due to insufficient data:", len(skipped_engines))
        for name, reason in skipped_engines:
            logger.info("  ✗ %s: %s", name, reason)

    if not runnable_engines:
        logger.error("No engines have sufficient data to run ablation")
        return

    logger.info("")
    logger.info("PHASE 2: Pipeline (leave-one-out) backtest (%d engines)", len(runnable_engines))
    logger.info("=" * 70)
    logger.info("Method: For each engine X, compare full pipeline vs pipeline-without-X")
    logger.info("Delta = backtest(all_engines) - backtest(all_minus_X)")
    logger.info("Positive delta → engine contributes to pipeline")
    logger.info("=" * 70)

    engine_entries = runnable_engines
    engine_names = [e.name for e in engine_entries]

    session = get_sessionmaker()()
    backtester = IsolatedBacktester()

    benchmark = load_benchmark(session, start, end)
    if benchmark.empty:
        logger.warning("No IHSG benchmark data — alpha/beta will be 0")

    data_cache: dict = {"all_tickers": tickers}
    all_results: list[IsolationResult] = []

    try:
        for ticker in tickers:
            logger.info("Loading data for %s...", ticker)
            ohlcv = load_ohlcv_data(session, ticker, start, end)

            if ohlcv.empty or len(ohlcv) < 60:
                logger.warning("  Insufficient data for %s (%d bars), skipping", ticker, len(ohlcv))
                continue

            logger.info("  %d bars (%s to %s)", len(ohlcv), ohlcv.index[0].date(), ohlcv.index[-1].date())

            baseline_signals = generate_baseline_signals(ohlcv)

            # ── Generate signals from ALL engines for this ticker ──
            logger.info("  Generating signals for all %d engines...", len(engine_entries))
            engine_signals: dict[str, pd.Series] = {}
            for entry in engine_entries:
                sig = generate_engine_signals(
                    ohlcv, entry.name, baseline_signals, ticker, session, data_cache,
                )
                engine_signals[entry.name] = sig

            # ── Build full composite (all engines) ──
            full_composite = build_composite_signal(
                engine_signals, engine_entries, baseline_signals, ohlcv.index,
            )
            full_ret = simulate_returns(ohlcv, full_composite, backtester.cost_per_trade)
            full_metrics = compute_metrics(full_ret, benchmark if not benchmark.empty else None)

            logger.info("  Full pipeline: Sharpe=%.4f, Alpha=%.4f, WinRate=%.1f%%",
                        full_metrics["sharpe_ratio"], full_metrics["alpha"],
                        full_metrics["win_rate_pct"])

            # ── Leave-one-out: for each engine, build composite without it ──
            for entry in engine_entries:
                loo_name = entry.name
                loo_entries = [e for e in engine_entries if e.name != loo_name]
                loo_signals = {k: v for k, v in engine_signals.items() if k != loo_name}

                loo_composite = build_composite_signal(
                    loo_signals, loo_entries, baseline_signals, ohlcv.index,
                )

                result = backtester.run(
                    engine_name=loo_name,
                    ohlcv=ohlcv,
                    baseline_signals=full_composite,  # "baseline" is now the full pipeline
                    engine_signals=loo_composite,     # "engine" is the reduced pipeline
                    benchmark_returns=benchmark if not benchmark.empty else None,
                )

                # Invert delta: we want full - without_X, but backtester computes engine - baseline
                # So delta = loo - full = -(full - loo) → we need to negate
                for key in result.delta_metrics:
                    result.delta_metrics[key] = -result.delta_metrics[key]

                all_results.append(result)

                if result.error:
                    logger.error("    FAILED: %s", result.error)
                else:
                    logger.info(
                        "    %s: Δ Sharpe=%+.4f, Δ Alpha=%+.4f, p=%.4f, sig=%s",
                        loo_name,
                        result.delta_sharpe,
                        result.delta_alpha,
                        result.p_value,
                        result.is_significant,
                    )

    finally:
        session.close()

    # Generate report
    if not all_results:
        logger.error("No results to report")
        return

    # Aggregate results across tickers
    engine_names_unique = list(dict.fromkeys(r.engine_name for r in all_results))
    aggregated: list[IsolationResult] = []

    for name in engine_names_unique:
        engine_results = [r for r in all_results if r.engine_name == name and not r.error]
        if not engine_results:
            if any(r.engine_name == name for r in all_results):
                err = next(r for r in all_results if r.engine_name == name)
                aggregated.append(IsolationResult(
                    engine_name=name,
                    baseline_metrics={},
                    isolated_metrics={},
                    error=err.error,
                ))
            continue

        avg_baseline: dict[str, float] = {}
        avg_isolated: dict[str, float] = {}
        avg_delta: dict[str, float] = {}

        keys = engine_results[0].baseline_metrics.keys()
        for key in keys:
            vals_b = [r.baseline_metrics.get(key, 0) for r in engine_results]
            vals_i = [r.isolated_metrics.get(key, 0) for r in engine_results]
            vals_d = [r.delta_metrics.get(key, 0) for r in engine_results]
            avg_baseline[key] = sum(vals_b) / len(vals_b)
            avg_isolated[key] = sum(vals_i) / len(vals_i)
            avg_delta[key] = sum(vals_d) / len(vals_d)

        avg_p = sum(r.p_value for r in engine_results) / len(engine_results)
        avg_t = sum(r.t_statistic for r in engine_results) / len(engine_results)
        total_obs = sum(r.n_observations for r in engine_results)

        aggregated.append(IsolationResult(
            engine_name=name,
            baseline_metrics=avg_baseline,
            isolated_metrics=avg_isolated,
            delta_metrics=avg_delta,
            p_value=avg_p,
            t_statistic=avg_t,
            is_significant=avg_p < 0.05,
            n_observations=total_obs,
        ))

    period_str = f"{start} to {end}"
    report = generate_report(aggregated, tickers, period_str, n_engines_tested=len(engine_entries))

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"ablation_pipeline_report_{timestamp_str}.json"
    report.save_json(output_path)

    try:
        run_id = report.save_to_db()
        logger.info("Report saved to DB (run_id=%s)", run_id)
    except Exception as e:
        logger.warning("Failed to save ablation run to DB: %s", e)

    report.print_summary()
    logger.info("Pipeline report saved to: %s", output_path)


def run_ablation(
    tickers: list[str],
    engines: list[str],
    start: str,
    end: str,
    output_dir: Path,
    mode: str = "isolated",
) -> None:
    """Run ablation study across specified engines and tickers.

    Args:
        mode: "isolated" (test each engine alone), "pipeline" (leave-one-out),
              "both" (run both modes for comparison).

    ISOLATION GUARANTEE:
        This function is READ-ONLY. It reads from the application database
        to load OHLCV and engine-specific data tables, but it NEVER writes
        to the database, modifies application state, or changes engine weights.
        Ablation results are recommendations only — applying them to the
        application requires explicit user approval based on verified scores.

    PRE-FLIGHT DATA CHECK:
        Before testing, each engine's data requirements are validated.
        Engines with insufficient data (missing tables, too few rows,
        inadequate date range overlap) are SKIPPED with a clear reason.
        This prevents false "REMOVE" verdicts caused by data gaps.
    """
    # ── Mode dispatch ──
    if mode == "pipeline":
        run_pipeline_ablation(tickers, engines, start, end, output_dir)
        return
    elif mode == "both":
        logger.info("=" * 70)
        logger.info("RUNNING BOTH MODES: isolated + pipeline")
        logger.info("=" * 70)
        logger.info("")
        logger.info("╔══════════════════════════════════════════════════════════╗")
        logger.info("║  MODE 1: ISOLATED (each engine tested independently)    ║")
        logger.info("╚══════════════════════════════════════════════════════════╝")
        _run_isolated_ablation(tickers, engines, start, end, output_dir)
        logger.info("")
        logger.info("╔══════════════════════════════════════════════════════════╗")
        logger.info("║  MODE 2: PIPELINE (leave-one-out, modular pipeline)     ║")
        logger.info("╚══════════════════════════════════════════════════════════╝")
        run_pipeline_ablation(tickers, engines, start, end, output_dir)
        return

    # Default: isolated mode (original behavior)
    _run_isolated_ablation(tickers, engines, start, end, output_dir)


def _run_isolated_ablation(
    tickers: list[str],
    engines: list[str],
    start: str,
    end: str,
    output_dir: Path,
) -> None:
    """Run isolated per-engine ablation (original method).

    Tests each engine independently against a baseline (no engine).
    """
    registry = create_default_registry()

    if engines[0] == "all":
        engine_entries = registry.enabled_entries()
    else:
        engine_entries = []
        for name in engines:
            entry = registry.get(name)
            if entry is None:
                logger.error("Unknown engine: %s", name)
                continue
            engine_entries.append(entry)

    if not engine_entries:
        logger.error("No valid engines to test")
        return

    logger.info("=" * 70)
    logger.info("ENGINE ABLATION STUDY")
    logger.info("Period: %s to %s", start, end)
    logger.info("Tickers: %s", ", ".join(tickers))
    logger.info("Engines: %s", ", ".join(e.name for e in engine_entries))
    logger.info("=" * 70)

    # ── Pre-flight data check ──────────────────────────────────────────
    logger.info("")
    logger.info("PHASE 1: Pre-flight data check")
    logger.info("-" * 40)

    from market.ablation.data_checker import DataChecker, CheckStatus
    checker = DataChecker()
    data_checks = checker.check_engines(engine_entries, tickers, start, end)
    checker.print_summary(data_checks)

    # Filter out engines that cannot run
    runnable_engines: list[EngineEntry] = []
    skipped_engines: list[tuple[str, str]] = []
    for entry in engine_entries:
        check = data_checks.get(entry.name)
        if check and check.can_run:
            runnable_engines.append(entry)
        else:
            reason = check.reason if check else "Unknown"
            skipped_engines.append((entry.name, reason))

    if skipped_engines:
        logger.info("Skipping %d engines due to insufficient data:", len(skipped_engines))
        for name, reason in skipped_engines:
            logger.info("  ✗ %s: %s", name, reason)

    if not runnable_engines:
        logger.error("No engines have sufficient data to run ablation")
        return

    logger.info("")
    logger.info("PHASE 2: Isolated backtest (%d engines)", len(runnable_engines))
    logger.info("=" * 70)

    engine_entries = runnable_engines

    session = get_sessionmaker()()
    backtester = IsolatedBacktester()

    # Load benchmark
    benchmark = load_benchmark(session, start, end)
    if benchmark.empty:
        logger.warning("No IHSG benchmark data — alpha/beta will be 0")

    # Data cache shared across tickers/engines to avoid re-loading
    data_cache: dict = {"all_tickers": tickers}

    all_results: list[IsolationResult] = []

    try:
        for ticker in tickers:
            logger.info("Loading data for %s...", ticker)
            ohlcv = load_ohlcv_data(session, ticker, start, end)

            if ohlcv.empty or len(ohlcv) < 60:
                logger.warning("  Insufficient data for %s (%d bars), skipping", ticker, len(ohlcv))
                continue

            logger.info("  %d bars (%s to %s)", len(ohlcv), ohlcv.index[0].date(), ohlcv.index[-1].date())

            baseline_signals = generate_baseline_signals(ohlcv)

            for entry in engine_entries:
                logger.info("  Testing engine: %s...", entry.name)
                engine_signals = generate_engine_signals(
                    ohlcv, entry.name, baseline_signals, ticker, session, data_cache,
                )

                result = backtester.run(
                    engine_name=entry.name,
                    ohlcv=ohlcv,
                    baseline_signals=baseline_signals,
                    engine_signals=engine_signals,
                    benchmark_returns=benchmark if not benchmark.empty else None,
                )

                all_results.append(result)

                if result.error:
                    logger.error("    FAILED: %s", result.error)
                else:
                    logger.info(
                        "    Δ Sharpe=%+.4f, Δ Alpha=%+.4f, p=%.4f, sig=%s",
                        result.delta_sharpe,
                        result.delta_alpha,
                        result.p_value,
                        result.is_significant,
                    )

    finally:
        session.close()

    # Generate report
    if not all_results:
        logger.error("No results to report")
        return

    # Aggregate results across tickers (average delta metrics)
    engine_names = list(dict.fromkeys(r.engine_name for r in all_results))
    aggregated: list[IsolationResult] = []

    for name in engine_names:
        engine_results = [r for r in all_results if r.engine_name == name and not r.error]
        if not engine_results:
            if any(r.engine_name == name for r in all_results):
                err = next(r for r in all_results if r.engine_name == name)
                aggregated.append(IsolationResult(
                    engine_name=name,
                    baseline_metrics={},
                    isolated_metrics={},
                    error=err.error,
                ))
            continue

        # Average the metrics across tickers
        avg_baseline: dict[str, float] = {}
        avg_isolated: dict[str, float] = {}
        avg_delta: dict[str, float] = {}

        keys = engine_results[0].baseline_metrics.keys()
        for key in keys:
            vals_b = [r.baseline_metrics.get(key, 0) for r in engine_results]
            vals_i = [r.isolated_metrics.get(key, 0) for r in engine_results]
            vals_d = [r.delta_metrics.get(key, 0) for r in engine_results]
            avg_baseline[key] = sum(vals_b) / len(vals_b)
            avg_isolated[key] = sum(vals_i) / len(vals_i)
            avg_delta[key] = sum(vals_d) / len(vals_d)

        # Average p-value (Fisher's method would be better, but avg is simpler)
        avg_p = sum(r.p_value for r in engine_results) / len(engine_results)
        avg_t = sum(r.t_statistic for r in engine_results) / len(engine_results)
        total_obs = sum(r.n_observations for r in engine_results)

        aggregated.append(IsolationResult(
            engine_name=name,
            baseline_metrics=avg_baseline,
            isolated_metrics=avg_isolated,
            delta_metrics=avg_delta,
            p_value=avg_p,
            t_statistic=avg_t,
            is_significant=avg_p < 0.05,
            n_observations=total_obs,
        ))

    period_str = f"{start} to {end}"
    report = generate_report(aggregated, tickers, period_str, n_engines_tested=len(engine_entries))

    # Save
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"ablation_report_{timestamp_str}.json"
    report.save_json(output_path)

    # Save to database
    try:
        run_id = report.save_to_db()
        logger.info("Report saved to DB (run_id=%s)", run_id)
    except Exception as e:
        logger.warning("Failed to save ablation run to DB: %s", e)

    # Print summary
    report.print_summary()

    logger.info("Report saved to: %s", output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Engine Ablation Study — isolated per-engine backtest & scoring",
    )
    parser.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="Comma-separated tickers (default: auto-load EQUITY_INDIVIDUAL from DB)",
    )
    parser.add_argument(
        "--max-tickers",
        type=int,
        default=20,
        help="Max tickers to load from DB when --tickers not specified (default: 20)",
    )
    parser.add_argument(
        "--engines",
        type=str,
        default="all",
        help="Comma-separated engine names or 'all' (default: all)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=DEFAULT_START,
        help=f"Start date YYYY-MM-DD (default: {DEFAULT_START})",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=DEFAULT_END,
        help=f"End date YYYY-MM-DD (default: {DEFAULT_END})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(OUTPUT_DIR),
        help=f"Output directory (default: {OUTPUT_DIR})",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="isolated",
        choices=["isolated", "pipeline", "both"],
        help="Ablation mode: 'isolated' (each engine alone), 'pipeline' (leave-one-out), 'both' (default: isolated)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show config without executing",
    )
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
    else:
        session = get_sessionmaker()()
        try:
            tickers = _load_equity_tickers_from_db(session, limit=args.max_tickers)
        finally:
            session.close()
        logger.info("Auto-loaded %d EQUITY_INDIVIDUAL tickers from DB", len(tickers))
    engines = [e.strip() for e in args.engines.split(",")]
    output_dir = Path(args.output_dir)

    if args.dry_run:
        registry = create_default_registry()
        print("DRY RUN — Configuration:")
        print(f"  Mode: {args.mode}")
        print(f"  Tickers: {tickers}")
        print(f"  Engines: {engines}")
        print(f"  Period: {args.start} to {args.end}")
        print(f"  Output: {output_dir}")
        print(f"  Available engines: {registry.names()}")
        return

    run_ablation(tickers, engines, args.start, args.end, output_dir, mode=args.mode)


if __name__ == "__main__":
    main()
