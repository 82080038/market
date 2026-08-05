"""Backtest strategies (pustaka/29).

Implements:
- Buy & Hold: Buy on first bar, hold until end.
- MA Crossover: Buy when MA20 crosses above MA50, sell on opposite.
- Conviction: Buy/sell based on composite score thresholds.
"""

from __future__ import annotations

from enum import Enum

import pandas as pd


class Signal(Enum):
    """Trade signal."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class Strategy:
    """Base strategy interface."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Generate signals for each bar.

        Args:
            data: OHLCV DataFrame.

        Returns:
            Series of Signal enums aligned to data index.
        """
        raise NotImplementedError


class BuyHoldStrategy(Strategy):
    """Buy on first bar, hold until end."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        signals = pd.Series(Signal.HOLD, index=data.index)
        if len(data) > 0:
            signals.iloc[0] = Signal.BUY
        if len(data) > 1:
            signals.iloc[-1] = Signal.SELL
        return signals


class MACrossoverStrategy(Strategy):
    """MA20/MA50 crossover strategy."""

    def __init__(self, fast: int = 20, slow: int = 50) -> None:
        self.fast = fast
        self.slow = slow

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        signals = pd.Series(Signal.HOLD, index=data.index)
        if len(data) < self.slow + 1:
            return signals

        close = data["close"].astype(float)
        ma_fast = close.rolling(self.fast).mean()
        ma_slow = close.rolling(self.slow).mean()

        for i in range(self.slow, len(data)):
            if pd.isna(ma_fast.iloc[i]) or pd.isna(ma_slow.iloc[i]):
                continue
            if pd.isna(ma_fast.iloc[i - 1]) or pd.isna(ma_slow.iloc[i - 1]):
                continue

            # Bullish crossover
            if (
                ma_fast.iloc[i - 1] <= ma_slow.iloc[i - 1]
                and ma_fast.iloc[i] > ma_slow.iloc[i]
            ):
                signals.iloc[i] = Signal.BUY
            # Bearish crossover
            elif (
                ma_fast.iloc[i - 1] >= ma_slow.iloc[i - 1]
                and ma_fast.iloc[i] < ma_slow.iloc[i]
            ):
                signals.iloc[i] = Signal.SELL

        return signals


class ConvictionStrategy(Strategy):
    """Buy/sell based on external conviction scores.

    Expects a 'score' column in the data DataFrame (0-100).
    Buy when score >= buy_threshold, sell when score <= sell_threshold.
    """

    def __init__(
        self,
        buy_threshold: float = 65.0,
        sell_threshold: float = 35.0,
    ) -> None:
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        signals = pd.Series(Signal.HOLD, index=data.index)

        if "score" not in data.columns:
            return signals

        scores = data["score"].astype(float)
        for i in range(len(data)):
            if pd.isna(scores.iloc[i]):
                continue
            if scores.iloc[i] >= self.buy_threshold:
                signals.iloc[i] = Signal.BUY
            elif scores.iloc[i] <= self.sell_threshold:
                signals.iloc[i] = Signal.SELL

        return signals
