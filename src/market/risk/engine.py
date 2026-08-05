"""Risk Engine (pustaka/18 §6.1, pustaka/07, pustaka/31).

Computes position sizing, stop loss, take profit, VaR/CVaR,
Kelly criterion, and drawdown circuit breaker.

Position sizing: fixed fractional, risk 1% capital per trade.
Stop loss: ATR-based, stop = price - 1.5 * ATR.
Take profit: risk-reward 1:2, tp = price + 2 * stop_distance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class RiskAssessment:
    """Risk assessment for a single trade candidate."""

    ticker: str
    last_price: float
    atr: float
    position_size: float
    stop_loss: float
    take_profit: float
    slippage: float
    risk_flags: list[str] = field(default_factory=list)
    avg_daily_volume: float = 0.0
    var_95: float | None = None
    cvar_95: float | None = None
    kelly_fraction: float | None = None


@dataclass
class CircuitBreakerState:
    """Drawdown circuit breaker state."""

    is_triggered: bool = False
    current_drawdown_pct: float = 0.0
    threshold_pct: float = 10.0
    peak_equity: float = 0.0


class RiskEngine:
    """Risk engine for position sizing, SL/TP, and risk flags."""

    def __init__(
        self,
        risk_per_trade_pct: float = 1.0,
        atr_multiplier_sl: float = 1.5,
        risk_reward_ratio: float = 2.0,
        max_volatility_pct: float = 50.0,
        liquidity_threshold_pct: float = 1.0,
    ) -> None:
        self.risk_per_trade_pct = risk_per_trade_pct
        self.atr_multiplier_sl = atr_multiplier_sl
        self.risk_reward_ratio = risk_reward_ratio
        self.max_volatility_pct = max_volatility_pct
        self.liquidity_threshold_pct = liquidity_threshold_pct

    def assess(
        self,
        ticker: str,
        last_price: float,
        atr: float,
        capital: float,
        avg_daily_volume: float = 0.0,
        target_value: float = 0.0,
        returns: pd.Series | None = None,
        win_rate: float | None = None,
        avg_win: float | None = None,
        avg_loss: float | None = None,
    ) -> RiskAssessment:
        """Assess risk for a trade candidate.

        Args:
            ticker: Stock ticker.
            last_price: Current market price.
            atr: ATR value (14-day).
            capital: Total portfolio capital.
            avg_daily_volume: Average daily volume (shares).
            target_value: Intended trade value (IDR).
            returns: Daily returns series for VaR/CVaR.
            win_rate: Historical win rate (0-1) for Kelly.
            avg_win: Average win percentage for Kelly.
            avg_loss: Average loss percentage for Kelly.

        Returns:
            RiskAssessment with position size, SL/TP, flags, VaR.
        """
        risk_flags: list[str] = []

        # Stop loss and take profit
        stop_distance = self.atr_multiplier_sl * atr
        stop_loss = last_price - stop_distance
        take_profit = last_price + self.risk_reward_ratio * stop_distance

        # Position sizing: risk 1% of capital
        risk_amount = capital * (self.risk_per_trade_pct / 100)
        position_size = risk_amount / stop_distance if stop_distance > 0 else 0.0

        # Slippage estimate (0.05% default)
        slippage = 0.0005

        # Liquidity check
        if avg_daily_volume > 0 and target_value > 0:
            adv_value = avg_daily_volume * last_price
            if target_value > adv_value * (self.liquidity_threshold_pct / 100):
                risk_flags.append("LIQUIDITY_LOW")

        # Volatility check
        if returns is not None and len(returns) >= 20:
            vol_annualized = float(returns.std() * np.sqrt(252) * 100)
            if vol_annualized > self.max_volatility_pct:
                risk_flags.append("HIGH_VOLATILITY")

        # VaR/CVaR (95% confidence)
        var_95: float | None = None
        cvar_95: float | None = None
        if returns is not None and len(returns) >= 20:
            var_95 = float(np.percentile(returns, 5))
            tail = returns[returns <= var_95]
            cvar_95 = float(tail.mean()) if len(tail) > 0 else var_95

        # Kelly criterion (conservative: half-Kelly)
        kelly_fraction: float | None = None
        if (
            win_rate is not None
            and avg_win is not None
            and avg_loss is not None
            and avg_loss != 0
        ):
            b = abs(avg_win / avg_loss)
            w = win_rate
            q = 1 - w
            kelly = (b * w - q) / b
            kelly_fraction = max(0.0, kelly * 0.5)  # Half-Kelly

        return RiskAssessment(
            ticker=ticker,
            last_price=last_price,
            atr=atr,
            position_size=round(position_size, 4),
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            slippage=slippage,
            risk_flags=risk_flags,
            avg_daily_volume=avg_daily_volume,
            var_95=var_95,
            cvar_95=cvar_95,
            kelly_fraction=kelly_fraction,
        )


class CircuitBreaker:
    """Drawdown circuit breaker — halts trading when DD exceeds threshold."""

    def __init__(self, threshold_pct: float = 10.0) -> None:
        self.threshold_pct = threshold_pct
        self._peak_equity = 0.0
        self._triggered = False

    def update(self, current_equity: float) -> CircuitBreakerState:
        """Update circuit breaker state with current equity.

        Args:
            current_equity: Current portfolio equity value.

        Returns:
            CircuitBreakerState with trigger status and drawdown.
        """
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity

        drawdown_pct = 0.0
        if self._peak_equity > 0:
            drawdown_pct = (
                (self._peak_equity - current_equity) / self._peak_equity * 100
            )

        if drawdown_pct >= self.threshold_pct:
            self._triggered = True

        return CircuitBreakerState(
            is_triggered=self._triggered,
            current_drawdown_pct=round(drawdown_pct, 2),
            threshold_pct=self.threshold_pct,
            peak_equity=self._peak_equity,
        )

    def reset(self) -> None:
        """Reset the circuit breaker (manual override)."""
        self._triggered = False
        self._peak_equity = 0.0
