"""30-day paper trading simulation using PaperTradingEngine + strategy signals.

Runs a 30-day simulation using historical OHLCV data from the database.
Uses PaperTradingEngine for realistic IDX execution (lot size, commission,
sales tax) and strategy signals (donchian, RSI mean reversion, EMA envelope)
combined with ML predictions.

Usage:
    .venv/bin/python3 scripts/run_30day_paper_trading.py [--tickers A,B,C] [--capital N]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from datetime import UTC, datetime, timedelta
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

COMMISSION_RATE = 0.0015
SALES_TAX_RATE = 0.001
SLIPPAGE_RATE = 0.0005
LOT_SIZE = 100
INITIAL_CAPITAL = 100_000_000  # Rp 100 juta
MAX_POSITIONS = 5
MAX_POSITION_PCT = 0.20
STOP_LOSS_PCT = -7.0
TAKE_PROFIT_PCT = 12.0
REBALANCE_FREQ = 5  # Re-evaluate every 5 trading days

DEFAULT_TICKERS = [
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK",
    "UNTR.JK", "ANTM.JK", "ICBP.JK", "ADRO.JK", "MDKA.JK",
]


# ── Strategy functions ────────────────────────────────────────────────────

def donchian_signals(close: pd.Series, period: int = 20) -> pd.Series:
    upper = close.rolling(period).max().shift(1)
    lower = close.rolling(period).min().shift(1)
    signal = pd.Series(0, index=close.index)
    signal[close > upper] = 1
    signal[close < lower] = -1
    return signal


def rsi_mean_reversion_signals(
    close: pd.Series, rsi_period: int = 14,
    oversold: float = 30, overbought: float = 70,
) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = (-delta.clip(upper=0)).rolling(rsi_period).mean()
    rs = gain / loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    signal = pd.Series(0, index=close.index)
    signal[rsi < oversold] = 1
    signal[rsi > overbought] = -1
    return signal


def ema_envelope_signals(
    close: pd.Series, ema_period: int = 50, envelope_pct: float = 0.03,
) -> pd.Series:
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
    train_end_ts = pd.Timestamp(train_end).tz_localize("UTC")
    train_close = close.loc[:train_end_ts - pd.Timedelta(days=1)]
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

def load_ohlcv(ticker: str) -> pd.DataFrame:
    from market.analysis.market_factors import ensure_adjusted
    from market.db.engine import get_sessionmaker
    from sqlalchemy import text

    session = get_sessionmaker()()
    try:
        df = pd.read_sql_query(
            text("SELECT timestamp, open, high, low, close, volume, adjusted_close "
                 "FROM ohlcv WHERE ticker=:ticker AND timeframe='1d' ORDER BY timestamp"),
            session.connection(), params={"ticker": ticker}, parse_dates=["timestamp"],
        )
    finally:
        session.close()
    if df.empty:
        return df
    df = df.set_index("timestamp")
    return ensure_adjusted(df)


# ── 30-day simulator ──────────────────────────────────────────────────────

class PaperTradingSimulator30D:
    """30-day paper trading simulator using PaperTradingEngine."""

    def __init__(
        self,
        tickers: list[str],
        initial_capital: float = INITIAL_CAPITAL,
        sim_days: int = 30,
    ) -> None:
        self.tickers = tickers
        self.initial_capital = initial_capital
        self.sim_days = sim_days
        self.strategy_selection: dict[str, str] = {}
        self.data: dict[str, pd.DataFrame] = {}
        self.ihsg_data = pd.DataFrame()

        from market.backtest.paper_trading import PaperTradingEngine
        self.engine = PaperTradingEngine(
            initial_capital=initial_capital,
            commission_rate=COMMISSION_RATE,
            sales_tax_rate=SALES_TAX_RATE,
            lot_size=LOT_SIZE,
        )

        # Determine date range: last N days from latest data
        all_dates = set()
        for t in tickers:
            df = load_ohlcv(t)
            if not df.empty and len(df) >= 100:
                self.data[t] = df
                all_dates.update(df.index)

        self.ihsg_data = load_ohlcv("^JKSE")

        if not all_dates:
            logger.error("No data loaded for any ticker")
            return

        sorted_dates = sorted(all_dates)
        self.trade_end = sorted_dates[-1]
        self.trade_start = sorted_dates[-(sim_days + 1)]  # +1 for inclusive

        # Determine training cutoff (everything before trade_start)
        self.train_end = str(self.trade_start.date())

        logger.info("Loaded data for %d/%d tickers", len(self.data), len(tickers))
        logger.info("Simulation period: %s to %s (%d days)",
                     self.trade_start.date(), self.trade_end.date(), sim_days)

        # Select best strategy for each ticker using pre-simulation data
        for t, df in self.data.items():
            pre_period = df.loc[df.index < self.trade_start]
            if len(pre_period) >= 100:
                name, _ = select_best_strategy(
                    df["close"].astype(float), self.train_end)
                self.strategy_selection[t] = name
            else:
                self.strategy_selection[t] = "donchian"

        logger.info("Strategy selection: %s", self.strategy_selection)

    def get_trading_dates(self) -> list[pd.Timestamp]:
        all_dates = set()
        for df in self.data.values():
            mask = (df.index >= self.trade_start) & (df.index <= self.trade_end)
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

    def get_strategy_signal(self, ticker: str, date: pd.Timestamp) -> int:
        df = self.data.get(ticker)
        if df is None:
            return 0
        close = df["close"].astype(float)
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

    def get_rsi(self, ticker: str, date: pd.Timestamp) -> float:
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

    def get_market_regime(self, date: pd.Timestamp) -> str:
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

    def make_decision(self, ticker: str, date: pd.Timestamp) -> dict:
        strat_sig = self.get_strategy_signal(ticker, date)
        rsi = self.get_rsi(ticker, date)
        regime = self.get_market_regime(date)

        # Simple RSI-based signal
        if rsi < 30:
            rsi_signal = (30 - rsi) / 30
        elif rsi > 70:
            rsi_signal = -(rsi - 70) / 30
        else:
            rsi_signal = 0.0

        score = strat_sig * 0.6 + rsi_signal * 0.4

        buy_threshold = 0.20
        sell_threshold = -0.15
        if regime == "bear":
            buy_threshold = 0.40
            sell_threshold = -0.10
        elif regime == "bull":
            buy_threshold = 0.12
            sell_threshold = -0.20

        action = "HOLD"
        if score > buy_threshold:
            action = "BUY"
        elif score < sell_threshold:
            action = "SELL"

        return {
            "action": action,
            "score": round(score, 4),
            "strategy_signal": strat_sig,
            "rsi": round(rsi, 1),
            "regime": regime,
        }

    def run(self) -> dict:
        trading_dates = self.get_trading_dates()
        if not trading_dates:
            return {"error": "No trading dates in simulation period"}

        logger.info("Trading dates: %d (%s to %s)",
                     len(trading_dates),
                     trading_dates[0].date(),
                     trading_dates[-1].date())

        equity_curve = []
        decisions_log = []
        t0 = datetime.now()

        for i, date in enumerate(trading_dates):
            # Check stop-loss / take-profit
            for ticker in list(self.engine.positions.keys()):
                pos = self.engine.positions[ticker]
                current_price = self.get_price(ticker, date, "close")
                if current_price is None:
                    continue
                pnl_pct = (current_price - pos.avg_cost) / pos.avg_cost * 100
                if pnl_pct <= STOP_LOSS_PCT:
                    logger.info("  STOP-LOSS: %s at %.0f (%.1f%%)", ticker, current_price, pnl_pct)
                    self.engine.sell(ticker, pos.shares, current_price)
                elif pnl_pct >= TAKE_PROFIT_PCT:
                    logger.info("  TAKE-PROFIT: %s at %.0f (%.1f%%)", ticker, current_price, pnl_pct)
                    self.engine.sell(ticker, pos.shares, current_price)

            # Rebalance every REBALANCE_FREQ days
            if i % REBALANCE_FREQ != 0:
                # Still record equity
                prices = {}
                for ticker in self.engine.positions:
                    p = self.get_price(ticker, date, "close")
                    if p:
                        prices[ticker] = p
                equity = self.engine.get_portfolio_value(prices)
                equity_curve.append({
                    "date": str(date.date()),
                    "equity": round(equity, 2),
                    "cash": round(self.engine.cash, 2),
                    "n_positions": len(self.engine.positions),
                })
                continue

            # Get decisions
            decisions = {}
            for ticker in self.tickers:
                if ticker not in self.data:
                    continue
                decision = self.make_decision(ticker, date)
                decisions[ticker] = decision
                decisions_log.append({
                    "date": str(date.date()),
                    "ticker": ticker,
                    **decision,
                    "has_position": ticker in self.engine.positions,
                })

            # Execute sells first
            sells = [(t, d) for t, d in decisions.items()
                     if d["action"] == "SELL" and t in self.engine.positions]
            for ticker, _ in sells:
                pos = self.engine.positions[ticker]
                price = self.get_price(ticker, date, "close")
                if price:
                    self.engine.sell(ticker, pos.shares, price)

            # Execute buys
            buys = [(t, d) for t, d in decisions.items()
                    if d["action"] == "BUY" and t not in self.engine.positions]
            buys.sort(key=lambda x: x[1]["score"], reverse=True)

            for ticker, _ in buys:
                if len(self.engine.positions) >= MAX_POSITIONS:
                    break
                price = self.get_price(ticker, date, "close")
                if price is None:
                    continue
                equity = self.engine.get_portfolio_value(
                    {t: self.get_price(t, date, "close") or 0
                     for t in self.engine.positions}
                )
                deployable = min(self.engine.cash, equity * MAX_POSITION_PCT)
                max_value = deployable / (1 + COMMISSION_RATE + SLIPPAGE_RATE)
                shares = int(max_value / price)
                shares = (shares // LOT_SIZE) * LOT_SIZE
                if shares > 0:
                    self.engine.buy(ticker, shares, price)

            # Record equity
            prices = {}
            for ticker in self.engine.positions:
                p = self.get_price(ticker, date, "close")
                if p:
                    prices[ticker] = p
            equity = self.engine.get_portfolio_value(prices)
            equity_curve.append({
                "date": str(date.date()),
                "equity": round(equity, 2),
                "cash": round(self.engine.cash, 2),
                "n_positions": len(self.engine.positions),
            })

            if (i + 1) % 5 == 0 or i == len(trading_dates) - 1:
                logger.info("  [%d/%d] %s — Equity: Rp %s | Positions: %d | Trades: %d",
                            i + 1, len(trading_dates), date.date(),
                            f"{equity:,.0f}", len(self.engine.positions), len(self.engine.orders))

        # Close all positions at end
        last_date = trading_dates[-1]
        for ticker in list(self.engine.positions.keys()):
            price = self.get_price(ticker, last_date, "close")
            if price:
                pos = self.engine.positions[ticker]
                self.engine.sell(ticker, pos.shares, price)

        # Compute metrics
        equity_series = pd.Series(
            [e["equity"] for e in equity_curve],
            index=pd.DatetimeIndex([pd.Timestamp(e["date"]) for e in equity_curve]),
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

        sell_orders = [o for o in self.engine.orders if o.side == "sell"]
        wins = sum(1 for o in sell_orders if o.total_cost > 0 and
                   o.shares * o.price > sum(
                       ord.total_cost for ord in self.engine.orders
                       if ord.ticker == o.ticker and ord.side == "buy"
                   ))
        # Simpler: use realized PnL from positions
        total_realized = sum(p.realized_pnl for p in self.engine.positions.values())
        win_rate = 0.0
        if sell_orders:
            profitable = sum(
                1 for p in self.engine.positions.values() if p.realized_pnl > 0)
            win_rate = profitable / len(sell_orders) * 100 if sell_orders else 0.0

        elapsed = (datetime.now() - t0).total_seconds()

        report = {
            "metadata": {
                "timestamp": datetime.now(UTC).isoformat(),
                "simulation_type": "30_day_paper_trading",
                "capital": self.initial_capital,
                "period": f"{self.trade_start.date()} to {self.trade_end.date()}",
                "sim_days": self.sim_days,
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
                "n_trades": len(self.engine.orders),
                "n_buy_orders": sum(1 for o in self.engine.orders if o.side == "buy"),
                "n_sell_orders": len(sell_orders),
                "total_realized_pnl": round(total_realized, 2),
                "win_rate_pct": round(win_rate, 1),
            },
            "orders": [
                {
                    "ticker": o.ticker,
                    "side": o.side,
                    "shares": o.shares,
                    "price": o.price,
                    "commission": o.commission,
                    "sales_tax": o.sales_tax,
                    "total_cost": o.total_cost,
                    "status": o.status,
                    "rejection_reason": o.rejection_reason,
                }
                for o in self.engine.orders
            ],
            "equity_curve": equity_curve,
            "decisions_log": decisions_log[-100:],
            "elapsed_seconds": round(elapsed, 1),
        }

        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="30-day paper trading simulation")
    parser.add_argument("--tickers", default="", help="Comma-separated tickers")
    parser.add_argument("--capital", type=float, default=INITIAL_CAPITAL, help="Initial capital in IDR")
    parser.add_argument("--days", type=int, default=30, help="Simulation days")
    parser.add_argument("--output", default="data/paper_trading_30day_report.json", help="Output report path")
    args = parser.parse_args()

    tickers = args.tickers.split(",") if args.tickers else DEFAULT_TICKERS

    logger.info("=" * 76)
    logger.info("30-DAY PAPER TRADING SIMULATION")
    logger.info("=" * 76)
    logger.info("Capital: Rp %s", f"{args.capital:,.0f}")
    logger.info("Simulation days: %d", args.days)
    logger.info("Tickers: %s", ", ".join(tickers))
    logger.info("Max positions: %d | Rebalance: every %d days", MAX_POSITIONS, REBALANCE_FREQ)
    logger.info("")

    sim = PaperTradingSimulator30D(
        tickers=tickers,
        initial_capital=args.capital,
        sim_days=args.days,
    )
    report = sim.run()

    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

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
    logger.info("  Total trades:      %d", perf["n_trades"])
    logger.info("  Realized PnL:      Rp %s", f"{perf['total_realized_pnl']:,.0f}")
    logger.info("")
    logger.info("Strategy selection:")
    for t, s in report["strategy_selection"].items():
        logger.info("  %s: %s", t, s)
    logger.info("")
    logger.info("Orders:")
    for o in report["orders"]:
        if o["side"] == "sell":
            logger.info("  SELL %s %d shares @ %.0f — status: %s",
                        o["ticker"], o["shares"], o["price"], o["status"])
        else:
            logger.info("  BUY  %s %d shares @ %.0f — status: %s",
                        o["ticker"], o["shares"], o["price"], o["status"])
    logger.info("")
    logger.info("Report saved to: %s", output_path)
    logger.info("=" * 76)


if __name__ == "__main__":
    main()
