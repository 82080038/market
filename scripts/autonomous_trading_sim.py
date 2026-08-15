"""Autonomous trading simulation 2025-2026 — no look-ahead bias.

Uses AI/ML modules (PredictionEngine, MarketContextProvider, MLSignalProvider,
MultiFactorModel) + strategy selection (donchian, rsi_meanrev, ema_envelope)
to make buy/sell/hold decisions.

Capital: Rp 10,000,000 (10 juta)
Period: 2025-01-01 to 2026-08-07
Training data: everything before 2025-01-01 (strictly)
Execution: next-bar open, IDX costs (commission 0.15%, sales tax 0.1%, slippage 0.05%)

Usage:
    .venv/bin/python3 scripts/autonomous_trading_sim.py [--tickers A,B,C] [--capital N]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

warnings.filterwarnings("ignore", category=DeprecationWarning, module="lightgbm")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

COMMISSION_RATE = 0.0015  # 0.15%
SALES_TAX_RATE = 0.001    # 0.1% on sell
SLIPPAGE_RATE = 0.0005    # 0.05%
LOT_SIZE = 100            # IDX lot size
INITIAL_CAPITAL = 10_000_000  # Rp 10 juta
TRADE_START = "2025-01-01"
TRADE_END = "2026-08-07"
REBALANCE_FREQ = 10  # Re-evaluate every 10 trading days (less trading = less cost)
MAX_POSITIONS = 3   # Max concurrent positions (concentrated, high-conviction)
MAX_POSITION_PCT = 0.25  # Max 25% of equity per position (smaller in bear)
STOP_LOSS_PCT = -7.0  # Cut position if losing >7%
TAKE_PROFIT_PCT = 12.0  # Take profit if gaining >12%

# Default tickers — liquid, well-known IDX stocks
DEFAULT_TICKERS = [
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK",
    "UNTR.JK", "ANTM.JK", "MDKA.JK", "ICBP.JK", "ADRO.JK",
]


# ── Strategy functions (from fast_portfolio_pipeline.py) ──────────────────

def donchian_signals(close: pd.Series, period: int = 20) -> pd.Series:
    upper = close.rolling(period).max().shift(1)
    lower = close.rolling(period).min().shift(1)
    signal = pd.Series(0, index=close.index)
    signal[close > upper] = 1
    signal[close < lower] = -1
    return signal


def rsi_mean_reversion_signals(close: pd.Series, rsi_period: int = 14,
                                oversold: float = 30, overbought: float = 70) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = (-delta.clip(upper=0)).rolling(rsi_period).mean()
    rs = gain / loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    signal = pd.Series(0, index=close.index)
    signal[rsi < oversold] = 1
    signal[rsi > overbought] = -1
    return signal


def ema_envelope_signals(close: pd.Series, ema_period: int = 50,
                          envelope_pct: float = 0.03) -> pd.Series:
    ema = close.ewm(span=ema_period, adjust=False).mean()
    upper = ema * (1 + envelope_pct)
    lower = ema * (1 - envelope_pct)
    signal = pd.Series(0, index=close.index)
    signal[close < lower] = 1
    signal[close > upper] = -1
    return signal


def compute_sharpe(returns: pd.Series) -> float:
    if returns.empty or returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * np.sqrt(252))


def select_best_strategy(close: pd.Series, train_end: str) -> tuple[str, pd.Series]:
    """Select best strategy based on in-sample Sharpe (no look-ahead)."""
    train_close = close.loc[:pd.Timestamp(train_end) - pd.Timedelta(days=1)]
    if len(train_close) < 100:
        sig = donchian_signals(close, period=20)
        return "donchian", sig

    strategies = {
        "donchian": donchian_signals(train_close, period=20),
        "rsi_meanrev": rsi_mean_reversion_signals(train_close),
        "ema_envelope": ema_envelope_signals(train_close),
    }

    best_name = "donchian"
    best_sharpe = -999.0
    for name, sig in strategies.items():
        pos = sig.shift(1).fillna(0)
        rets = pos * train_close.astype(float).pct_change()
        sh = compute_sharpe(rets)
        if sh > best_sharpe:
            best_sharpe = sh
            best_name = name

    if best_name == "rsi_meanrev":
        sig = rsi_mean_reversion_signals(close)
    elif best_name == "ema_envelope":
        sig = ema_envelope_signals(close)
    else:
        sig = donchian_signals(close, period=20)

    return best_name, sig


# ── Data loading ──────────────────────────────────────────────────────────

def load_ohlcv(ticker: str, db_path: str) -> pd.DataFrame:
    """Load OHLCV from DB with adjusted prices."""
    from market.analysis.market_factors import ensure_adjusted
    from market.db.raw import get_raw_connection
    from sqlalchemy import text

    with get_raw_connection() as conn:
        df = pd.read_sql_query(
            text("SELECT timestamp, open, high, low, close, volume, adjusted_close "
                 "FROM ohlcv WHERE ticker=:ticker AND timeframe='1d' ORDER BY timestamp"),
            conn, params={"ticker": ticker}, parse_dates=["timestamp"],
        )
    if df.empty:
        return df
    df = df.set_index("timestamp")
    return ensure_adjusted(df)


# ── Trading simulation ────────────────────────────────────────────────────

class TradingSimulator:
    """Autonomous trading simulator with no look-ahead bias."""

    def __init__(
        self,
        tickers: list[str],
        initial_capital: float = INITIAL_CAPITAL,
        db_path: str | None = None,
    ) -> None:
        self.tickers = tickers
        self.initial_capital = initial_capital
        self.db_path = db_path
        self.cash = initial_capital
        self.positions: dict[str, dict] = {}  # ticker -> {shares, entry_price, entry_date}
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.predictions_log: list[dict] = []
        self.strategy_selection: dict[str, str] = {}

        # Load all data upfront (but only use up to as_of for decisions)
        self.data: dict[str, pd.DataFrame] = {}
        for t in tickers:
            df = load_ohlcv(t, db_path)
            if not df.empty and len(df) >= 100:
                self.data[t] = df

        # Load IHSG for trend filter
        self.ihsg_data = load_ohlcv("^JKSE", db_path)

        logger.info("Loaded data for %d/%d tickers", len(self.data), len(tickers))

        # Select best strategy for each ticker using pre-2025 data
        for t, df in self.data.items():
            pre_2025 = df.loc[df.index < TRADE_START]
            if len(pre_2025) >= 100:
                name, _ = select_best_strategy(df["close"].astype(float), TRADE_START)
                self.strategy_selection[t] = name
            else:
                self.strategy_selection[t] = "donchian"

        logger.info("Strategy selection: %s", self.strategy_selection)

    def get_trading_dates(self) -> list[pd.Timestamp]:
        """Get sorted unique trading dates in the trade period."""
        all_dates = set()
        for df in self.data.values():
            mask = (df.index >= TRADE_START) & (df.index <= TRADE_END)
            all_dates.update(df.loc[mask].index)
        return sorted(all_dates)

    def get_price(self, ticker: str, date: pd.Timestamp, field: str = "close") -> float | None:
        df = self.data.get(ticker)
        if df is None:
            return None
        if date not in df.index:
            valid = df.index[df.index <= date]
            if len(valid) == 0:
                return None
            date = valid[-1]
        val = df.loc[date, field]
        return float(val) if not pd.isna(val) else None

    def compute_portfolio_equity(self, date: pd.Timestamp) -> float:
        """Mark-to-market portfolio value."""
        total = self.cash
        for ticker, pos in self.positions.items():
            price = self.get_price(ticker, date, "close")
            if price is not None:
                total += pos["shares"] * price
        return total

    def get_market_regime(self, date: pd.Timestamp) -> str:
        """Get market regime at date (bear/bull/sideways) using IHSG MA200."""
        if self.ihsg_data is None or self.ihsg_data.empty:
            return "sideways"
        close = self.ihsg_data["close"].astype(float)
        close_up_to = close.loc[close.index <= date]
        if len(close_up_to) < 200:
            return "sideways"
        ma200 = close_up_to.rolling(200).mean().iloc[-1]
        current = close_up_to.iloc[-1]
        if current > ma200 * 1.02:
            return "bull"
        elif current < ma200 * 0.98:
            return "bear"
        return "sideways"

    def get_ihsg_trend(self, date: pd.Timestamp) -> float:
        """Get IHSG trend: +1 if above MA50, -1 if below, 0 if sideways."""
        if self.ihsg_data is None or self.ihsg_data.empty:
            return 0.0
        close = self.ihsg_data["close"].astype(float)
        close_up_to = close.loc[close.index <= date]
        if len(close_up_to) < 50:
            return 0.0
        ma50 = close_up_to.rolling(50).mean().iloc[-1]
        current = close_up_to.iloc[-1]
        if current > ma50 * 1.01:
            return 1.0
        elif current < ma50 * 0.99:
            return -1.0
        return 0.0

    def get_rsi(self, ticker: str, date: pd.Timestamp) -> float:
        """Get current RSI for ticker at date (no look-ahead)."""
        df = self.data.get(ticker)
        if df is None:
            return 50.0
        close = df["close"].astype(float)
        close_up_to = close.loc[close.index <= date]
        if len(close_up_to) < 15:
            return 50.0
        delta = close_up_to.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not rsi.empty and not pd.isna(rsi.iloc[-1]) else 50.0

    def get_mean_reversion_signal(self, ticker: str, date: pd.Timestamp) -> float:
        """Mean reversion signal: buy when oversold, sell when overbought.
        Returns -1 to +1."""
        rsi = self.get_rsi(ticker, date)
        df = self.data.get(ticker)
        if df is None:
            return 0.0
        close = df["close"].astype(float)
        close_up_to = close.loc[close.index <= date]
        if len(close_up_to) < 20:
            return 0.0
        ma20 = close_up_to.rolling(20).mean().iloc[-1]
        current = close_up_to.iloc[-1]
        deviation = (current - ma20) / ma20  # How far from MA20

        # RSI-based signal
        if rsi < 30:
            rsi_signal = (30 - rsi) / 30  # 0 to 1, stronger when more oversold
        elif rsi > 70:
            rsi_signal = -(rsi - 70) / 30  # 0 to -1
        else:
            rsi_signal = 0.0

        # Deviation signal: far below MA20 → buy, far above → sell
        dev_signal = max(-1, min(1, -deviation * 5))  # Scale deviation

        return rsi_signal * 0.6 + dev_signal * 0.4

    def get_strategy_signal(self, ticker: str, date: pd.Timestamp) -> int:
        """Get strategy signal for ticker at date (using only past data)."""
        df = self.data.get(ticker)
        if df is None:
            return 0

        close = df["close"].astype(float)
        # Only use data up to date (no look-ahead)
        close_up_to = close.loc[close.index <= date]
        if len(close_up_to) < 50:
            return 0

        strategy_name = self.strategy_selection.get(ticker, "donchian")
        if strategy_name == "rsi_meanrev":
            sig = rsi_mean_reversion_signals(close_up_to)
        elif strategy_name == "ema_envelope":
            sig = ema_envelope_signals(close_up_to)
        else:
            sig = donchian_signals(close_up_to, period=20)

        return int(sig.iloc[-1]) if not sig.empty else 0

    def get_ml_signal(self, ticker: str, date: pd.Timestamp) -> float:
        """Get ML composite signal for ticker at date (no look-ahead)."""
        df = self.data.get(ticker)
        if df is None:
            return 0.0

        # Use only data up to date
        df_up_to = df.loc[df.index <= date]
        if len(df_up_to) < 200:
            return 0.0

        try:
            from market.analysis.ml_signal import MLSignalProvider
            from market.analysis.multi_factor import MultiFactorModel

            ml_provider = MLSignalProvider(horizon=5, min_train_samples=200)
            ml_sig = ml_provider.train_and_predict(ticker, df_up_to, str(date.date()))

            mf_model = MultiFactorModel(horizon=5, min_train_samples=200)
            mf_pred = mf_model.train_and_predict(ticker, df_up_to, str(date.date()))

            if ml_sig.model_available and mf_pred.model_available:
                return ml_sig.signal * 0.4 + mf_pred.signal * 0.6
            elif mf_pred.model_available:
                return mf_pred.signal
            elif ml_sig.model_available:
                return ml_sig.signal
        except Exception as e:
            logger.debug("ML signal error for %s at %s: %s", ticker, date.date(), e)

        return 0.0

    def get_prediction(self, ticker: str, date: pd.Timestamp) -> dict | None:
        """Get AI prediction for ticker at date (no look-ahead)."""
        df = self.data.get(ticker)
        if df is None:
            return None

        df_up_to = df.loc[df.index <= date]
        if len(df_up_to) < 50:
            return None

        try:
            from market.analysis.pattern_detector import PatternDetector
            from market.analysis.prediction import PredictionEngine, PredictionMethod
            from market.analysis.market_context import MarketContextProvider
            from market.analysis.ml_signal import MLSignalProvider
            from market.analysis.multi_factor import MultiFactorModel

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
                ticker=ticker,
                data=df_up_to,
                method=PredictionMethod.ENSEMBLE,
                as_of=str(date.date()),
            )

            return {
                "direction": pred.predicted_direction,
                "price": round(pred.predicted_price, 2),
                "return_pct": round(pred.predicted_return_pct, 4),
                "confidence": round(pred.confidence, 3),
            }
        except Exception as e:
            logger.debug("Prediction error for %s at %s: %s", ticker, date.date(), e)
            return None

    def make_decision(self, ticker: str, date: pd.Timestamp) -> dict:
        """Make buy/sell/hold decision combining strategy + ML + prediction + mean reversion + market regime.

        V4 Decision logic:
        - Strategy signal: +1 (buy), -1 (sell), 0 (hold)
        - ML signal: -1 to +1 (continuous)
        - Prediction: direction + confidence
        - Mean reversion: RSI + deviation from MA20 (contrarian)
        - Market regime: bear → require agreement, but don't block all buys

        Combined score = strategy * 0.25 + ml * 0.25 + prediction * 0.25 + mean_reversion * 0.25
        """
        strat_sig = self.get_strategy_signal(ticker, date)
        ml_sig = self.get_ml_signal(ticker, date)
        pred = self.get_prediction(ticker, date)
        regime = self.get_market_regime(date)
        ihsg_trend = self.get_ihsg_trend(date)
        mr_sig = self.get_mean_reversion_signal(ticker, date)
        rsi = self.get_rsi(ticker, date)

        pred_signal = 0.0
        pred_confidence = 0.0
        pred_direction = "flat"
        if pred:
            pred_direction = pred["direction"]
            pred_confidence = pred["confidence"]
            if pred_direction == "up":
                pred_signal = pred_confidence
            elif pred_direction == "down":
                pred_signal = -pred_confidence

        # Combined score — equal weights across 4 signals
        score = strat_sig * 0.25 + ml_sig * 0.25 + pred_signal * 0.25 + mr_sig * 0.25

        # Adaptive thresholds based on market regime
        buy_threshold = 0.20
        sell_threshold = -0.15
        if regime == "bear":
            # In bear: require strong conviction (3+ signals agree)
            positive_signals = sum(1 for s in [strat_sig, ml_sig, pred_signal, mr_sig] if s > 0)
            negative_signals = sum(1 for s in [strat_sig, ml_sig, pred_signal, mr_sig] if s < 0)
            if positive_signals >= 3:
                buy_threshold = 0.20  # Strong agreement → allow buy
            elif positive_signals >= 2:
                buy_threshold = 0.35  # Moderate → very high bar
            else:
                buy_threshold = 0.80  # Weak → effectively block
            # Sell quickly if 2+ signals negative
            if negative_signals >= 2:
                sell_threshold = -0.05
            else:
                sell_threshold = -0.15
        elif regime == "bull":
            buy_threshold = 0.12
            sell_threshold = -0.20

        # IHSG trend filter: mild penalty, not complete block
        if ihsg_trend < 0 and score > 0:
            score *= 0.7

        action = "HOLD"
        if score > buy_threshold:
            action = "BUY"
        elif score < sell_threshold:
            action = "SELL"

        return {
            "action": action,
            "score": round(score, 4),
            "strategy_signal": strat_sig,
            "ml_signal": round(ml_sig, 4),
            "prediction": pred,
            "prediction_direction": pred_direction,
            "prediction_confidence": pred_confidence,
            "regime": regime,
            "ihsg_trend": ihsg_trend,
            "mean_reversion_signal": round(mr_sig, 4),
            "rsi": round(rsi, 1),
        }

    def execute_trade(
        self,
        ticker: str,
        action: str,
        date: pd.Timestamp,
        next_date: pd.Timestamp | None = None,
    ) -> dict | None:
        """Execute trade at next bar's open (no look-ahead)."""
        if next_date is None:
            return None

        exec_price = self.get_price(ticker, next_date, "open")
        if exec_price is None:
            return None

        # Apply slippage
        if action == "BUY":
            exec_price *= (1 + SLIPPAGE_RATE)
        else:
            exec_price *= (1 - SLIPPAGE_RATE)

        if action == "BUY" and ticker not in self.positions:
            equity = self.compute_portfolio_equity(date)
            deployable = min(self.cash, equity * MAX_POSITION_PCT)
            max_value = deployable / (1 + COMMISSION_RATE)
            shares_to_buy = int(max_value / exec_price)
            shares_to_buy = (shares_to_buy // LOT_SIZE) * LOT_SIZE

            if shares_to_buy <= 0:
                return None

            trade_value = shares_to_buy * exec_price
            commission = trade_value * COMMISSION_RATE
            total_cost = trade_value + commission

            if total_cost > self.cash:
                shares_to_buy = (int((self.cash / (1 + COMMISSION_RATE)) / exec_price) // LOT_SIZE) * LOT_SIZE
                if shares_to_buy <= 0:
                    return None
                trade_value = shares_to_buy * exec_price
                commission = trade_value * COMMISSION_RATE
                total_cost = trade_value + commission

            self.cash -= total_cost
            self.positions[ticker] = {
                "shares": shares_to_buy,
                "entry_price": exec_price,
                "entry_date": next_date,
            }

            trade = {
                "date": str(next_date.date()),
                "ticker": ticker,
                "side": "buy",
                "price": round(exec_price, 2),
                "shares": shares_to_buy,
                "commission": round(commission, 2),
                "strategy": self.strategy_selection.get(ticker, "donchian"),
            }
            self.trades.append(trade)
            return trade

        elif action == "SELL" and ticker in self.positions:
            shares = self.positions[ticker]["shares"]
            trade_value = shares * exec_price
            commission = trade_value * COMMISSION_RATE
            sales_tax = trade_value * SALES_TAX_RATE
            net_proceeds = trade_value - commission - sales_tax

            self.cash += net_proceeds
            entry_price = self.positions[ticker]["entry_price"]
            pnl = (exec_price - entry_price) * shares - commission - sales_tax
            pnl_pct = (exec_price - entry_price) / entry_price * 100

            trade = {
                "date": str(next_date.date()),
                "ticker": ticker,
                "side": "sell",
                "price": round(exec_price, 2),
                "shares": shares,
                "commission": round(commission, 2),
                "sales_tax": round(sales_tax, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "entry_price": round(entry_price, 2),
                "strategy": self.strategy_selection.get(ticker, "donchian"),
            }
            self.trades.append(trade)
            del self.positions[ticker]
            return trade

        return None

    def run(self) -> dict:
        """Run the full trading simulation."""
        trading_dates = self.get_trading_dates()
        logger.info("Trading dates: %d (%s to %s)",
                     len(trading_dates),
                     trading_dates[0].date() if trading_dates else "N/A",
                     trading_dates[-1].date() if trading_dates else "N/A")

        t0 = time.time()
        rebalance_count = 0
        decision_count = 0

        for i, date in enumerate(trading_dates):
            # Mark-to-market equity
            equity = self.compute_portfolio_equity(date)
            self.equity_curve.append({
                "date": str(date.date()),
                "equity": round(equity, 2),
                "cash": round(self.cash, 2),
                "positions_value": round(equity - self.cash, 2),
                "n_positions": len(self.positions),
            })

            # Check stop-loss / take-profit on every bar
            next_date = trading_dates[i + 1] if i + 1 < len(trading_dates) else None
            if next_date:
                for ticker in list(self.positions.keys()):
                    pos = self.positions[ticker]
                    current_price = self.get_price(ticker, date, "close")
                    if current_price is None:
                        continue
                    pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"] * 100
                    if pnl_pct <= STOP_LOSS_PCT:
                        logger.info("  STOP-LOSS: %s at %.0f (%.1f%%) — selling", ticker, current_price, pnl_pct)
                        self.execute_trade(ticker, "SELL", date, next_date)
                    elif pnl_pct >= TAKE_PROFIT_PCT:
                        logger.info("  TAKE-PROFIT: %s at %.0f (%.1f%%) — selling", ticker, current_price, pnl_pct)
                        self.execute_trade(ticker, "SELL", date, next_date)

            # Rebalance every REBALANCE_FREQ days
            if i % REBALANCE_FREQ != 0:
                continue

            rebalance_count += 1
            next_date = trading_dates[i + 1] if i + 1 < len(trading_dates) else None

            # Get decisions for all tickers
            decisions = {}
            for ticker in self.tickers:
                if ticker not in self.data:
                    continue
                decision = self.make_decision(ticker, date)
                decisions[ticker] = decision
                decision_count += 1

                # Log prediction
                self.predictions_log.append({
                    "date": str(date.date()),
                    "ticker": ticker,
                    "action": decision["action"],
                    "score": decision["score"],
                    "strategy_signal": decision["strategy_signal"],
                    "ml_signal": decision["ml_signal"],
                    "prediction_direction": decision["prediction_direction"],
                    "prediction_confidence": decision["prediction_confidence"],
                    "regime": decision.get("regime", "sideways"),
                    "ihsg_trend": decision.get("ihsg_trend", 0),
                    "mean_reversion_signal": decision.get("mean_reversion_signal", 0),
                    "rsi": decision.get("rsi", 50),
                    "has_position": ticker in self.positions,
                })

            # Sort by score: sells first, then buys
            sells = [(t, d) for t, d in decisions.items() if d["action"] == "SELL" and t in self.positions]
            buys = [(t, d) for t, d in decisions.items() if d["action"] == "BUY" and t not in self.positions]
            buys.sort(key=lambda x: x[1]["score"], reverse=True)

            # Execute sells first
            for ticker, decision in sells:
                self.execute_trade(ticker, "SELL", date, next_date)

            # Execute buys (respect max positions)
            for ticker, decision in buys:
                if len(self.positions) >= MAX_POSITIONS:
                    break
                self.execute_trade(ticker, "BUY", date, next_date)

            if (i + 1) % 50 == 0 or i == len(trading_dates) - 1:
                elapsed = time.time() - t0
                logger.info("  [%d/%d] %s — Equity: Rp %s | Positions: %d | Trades: %d — %.0fs",
                            i + 1, len(trading_dates), date.date(),
                            f"{equity:,.0f}", len(self.positions), len(self.trades), elapsed)

        # Close all positions at end
        last_date = trading_dates[-1] if trading_dates else None
        if last_date:
            for ticker in list(self.positions.keys()):
                price = self.get_price(ticker, last_date, "close")
                if price:
                    # Simulate sell at close
                    shares = self.positions[ticker]["shares"]
                    trade_value = shares * price
                    commission = trade_value * COMMISSION_RATE
                    sales_tax = trade_value * SALES_TAX_RATE
                    net = trade_value - commission - sales_tax
                    self.cash += net
                    entry_price = self.positions[ticker]["entry_price"]
                    pnl = (price - entry_price) * shares - commission - sales_tax
                    pnl_pct = (price - entry_price) / entry_price * 100
                    self.trades.append({
                        "date": str(last_date.date()),
                        "ticker": ticker,
                        "side": "sell",
                        "price": round(price, 2),
                        "shares": shares,
                        "commission": round(commission, 2),
                        "sales_tax": round(sales_tax, 2),
                        "pnl": round(pnl, 2),
                        "pnl_pct": round(pnl_pct, 2),
                        "entry_price": round(entry_price, 2),
                        "strategy": self.strategy_selection.get(ticker, "donchian"),
                        "note": "forced close at end",
                    })
                    del self.positions[ticker]

        # Compute final metrics
        equity_series = pd.Series(
            [e["equity"] for e in self.equity_curve],
            index=pd.DatetimeIndex([pd.Timestamp(e["date"]) for e in self.equity_curve]),
        )

        final_equity = float(equity_series.iloc[-1]) if not equity_series.empty else self.initial_capital
        total_return_pct = (final_equity - self.initial_capital) / self.initial_capital * 100

        returns = equity_series.pct_change(fill_method=None).dropna()
        sharpe = float(returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0.0

        downside = returns[returns < 0]
        sortino = float(returns.mean() / downside.std() * np.sqrt(252)) if len(downside) > 0 and downside.std() > 0 else 0.0

        running_max = equity_series.cummax()
        drawdown = (equity_series - running_max) / running_max
        max_dd = float(drawdown.min() * 100) if not drawdown.empty else 0.0

        # Win rate
        sell_trades = [t for t in self.trades if t["side"] == "sell"]
        wins = sum(1 for t in sell_trades if t.get("pnl", 0) > 0)
        win_rate = wins / len(sell_trades) * 100 if sell_trades else 0.0

        # Prediction accuracy
        pred_correct = 0
        pred_total = 0
        for p in self.predictions_log:
            if p["action"] in ("BUY", "SELL"):
                pred_total += 1
                # Check if the prediction direction matched actual price movement
                ticker = p["ticker"]
                date = pd.Timestamp(p["date"])
                df = self.data.get(ticker)
                if df is not None and date in df.index:
                    future_5d = df.index[(df.index > date) & (df.index <= date + pd.Timedelta(days=7))]
                    if len(future_5d) > 0:
                        current_price = float(df.loc[date, "close"])
                        future_price = float(df.loc[future_5d[-1], "close"])
                        actual_dir = "up" if future_price > current_price else "down"
                        if p["prediction_direction"] == actual_dir:
                            pred_correct += 1

        pred_accuracy = pred_correct / pred_total * 100 if pred_total > 0 else 0.0

        elapsed = time.time() - t0

        report = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "capital": self.initial_capital,
                "period": f"{TRADE_START} to {TRADE_END}",
                "tickers": self.tickers,
                "rebalance_freq": REBALANCE_FREQ,
                "max_positions": MAX_POSITIONS,
            },
            "strategy_selection": self.strategy_selection,
            "performance": {
                "initial_capital": self.initial_capital,
                "final_equity": round(final_equity, 2),
                "total_return_pct": round(total_return_pct, 2),
                "sharpe_ratio": round(sharpe, 3),
                "sortino_ratio": round(sortino, 3),
                "max_drawdown_pct": round(max_dd, 2),
                "win_rate_pct": round(win_rate, 1),
                "n_trades": len(self.trades),
                "n_sell_trades": len(sell_trades),
                "n_winning_trades": wins,
                "prediction_accuracy_pct": round(pred_accuracy, 1),
                "n_predictions": pred_total,
                "n_correct_predictions": pred_correct,
            },
            "trades": self.trades,
            "equity_curve": self.equity_curve,
            "predictions_log": self.predictions_log[-200:],  # Last 200 predictions
            "elapsed_seconds": round(elapsed, 1),
        }

        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous trading simulation 2025-2026")
    parser.add_argument("--tickers", default="", help="Comma-separated tickers")
    parser.add_argument("--capital", type=float, default=INITIAL_CAPITAL, help="Initial capital in IDR")
    parser.add_argument("--db", default=None, help="Database path (default: env DB_PATH atau settings.db_path)")
    parser.add_argument("--output", default="data/autonomous_trading_report.json", help="Output report path")
    args = parser.parse_args()

    tickers = args.tickers.split(",") if args.tickers else DEFAULT_TICKERS

    logger.info("=" * 76)
    logger.info("AUTONOMOUS TRADING SIMULATION — 2025-2026")
    logger.info("=" * 76)
    logger.info("Capital: Rp %s", f"{args.capital:,.0f}")
    logger.info("Period: %s to %s", TRADE_START, TRADE_END)
    logger.info("Tickers: %s", ", ".join(tickers))
    logger.info("Max positions: %d | Rebalance: every %d days", MAX_POSITIONS, REBALANCE_FREQ)
    logger.info("")

    from market.config import settings as _settings
    db_path = args.db or os.environ.get("DB_PATH") or _settings.db_path
    sim = TradingSimulator(tickers=tickers, initial_capital=args.capital, db_path=db_path)
    report = sim.run()

    # Save report
    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary
    perf = report["performance"]
    logger.info("")
    logger.info("=" * 76)
    logger.info("SIMULATION COMPLETE — %.1fs", report["elapsed_seconds"])
    logger.info("=" * 76)
    logger.info("  Initial capital:   Rp %s", f"{perf['initial_capital']:,.0f}")
    logger.info("  Final equity:      Rp %s", f"{perf['final_equity']:,.0f}")
    logger.info("  Total return:      %+.2f%%", perf["total_return_pct"])
    logger.info("  Sharpe ratio:      %.3f", perf["sharpe_ratio"])
    logger.info("  Sortino ratio:     %.3f", perf["sortino_ratio"])
    logger.info("  Max drawdown:      %.2f%%", perf["max_drawdown_pct"])
    logger.info("  Win rate:          %.1f%% (%d/%d trades)",
                perf["win_rate_pct"], perf["n_winning_trades"], perf["n_sell_trades"])
    logger.info("  Total trades:      %d", perf["n_trades"])
    logger.info("  Prediction acc:    %.1f%% (%d/%d)",
                perf["prediction_accuracy_pct"],
                perf["n_correct_predictions"], perf["n_predictions"])
    logger.info("")
    logger.info("Strategy selection:")
    for t, s in report["strategy_selection"].items():
        logger.info("  %s: %s", t, s)
    logger.info("")
    logger.info("Trades:")
    for t in report["trades"]:
        if t["side"] == "sell":
            logger.info("  %s SELL %s %d shares @ %s — PnL: %s (%+.1f%%) [%s]",
                        t["date"], t["ticker"], t["shares"], t["price"],
                        f"Rp {t['pnl']:,.0f}", t["pnl_pct"], t["strategy"])
        else:
            logger.info("  %s BUY  %s %d shares @ %s [%s]",
                        t["date"], t["ticker"], t["shares"], t["price"], t["strategy"])
    logger.info("")
    logger.info("Report saved to: %s", output_path)
    logger.info("=" * 76)


if __name__ == "__main__":
    main()
