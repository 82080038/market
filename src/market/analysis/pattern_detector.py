"""Pattern detector with strict no-look-ahead bias (pustaka/18 §3.3, pustaka/29).

Detects chart patterns using ONLY data up to as_of date.
Never peeks at future data. All indicators computed on truncated series.

Pattern types:
- Double bottom / double top
- Head & shoulders / inverse H&S
- Triangle (ascending/descending/symmetric)
- Support/resistance break
- Bollinger squeeze
- RSI divergence (bullish/bearish)
- MACD crossover

Each detection records:
- pattern_type, direction (bullish/bearish/neutral)
- confidence (0-1)
- price_at_detection
- key levels (support, resistance, neckline, etc.)

All detections are recorded into PatternMemory for outcome tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from market.analysis.delisting_memory import DelistingMemory
from market.analysis.extras import PatternMemory, PatternRecord


@dataclass
class PatternDetection:
    """A detected pattern at a point in time."""

    pattern_type: str
    ticker: str
    as_of: str  # ISO date — the detection date
    direction: str  # bullish, bearish, neutral
    confidence: float
    price_at_detection: float
    key_levels: dict[str, float] = field(default_factory=dict)
    description: str = ""
    indicators_snapshot: dict[str, float] = field(default_factory=dict)
    pattern_record: PatternRecord | None = None


@dataclass
class DetectionLogEntry:
    """Terminal log entry for streaming output."""

    timestamp: str
    level: str  # info, warn, error, detect
    ticker: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class PatternDetector:
    """Detects chart patterns with no look-ahead bias.

    All computations use ONLY data up to as_of date.
    """

    def __init__(
        self,
        pattern_memory: PatternMemory | None = None,
        delisting_memory: DelistingMemory | None = None,
        min_lookback: int = 60,
    ) -> None:
        self.pattern_memory = pattern_memory or PatternMemory()
        self.delisting_memory = delisting_memory or DelistingMemory()
        self.min_lookback = min_lookback
        self._log: list[DetectionLogEntry] = []

    @property
    def log(self) -> list[DetectionLogEntry]:
        """Detection log entries for terminal output."""
        return self._log

    def clear_log(self) -> None:
        """Clear the detection log."""
        self._log.clear()

    def _log_entry(
        self,
        level: str,
        ticker: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        entry = DetectionLogEntry(
            timestamp=datetime.now(UTC).isoformat(),
            level=level,
            ticker=ticker,
            message=message,
            data=data or {},
        )
        self._log.append(entry)

    def _truncate(
        self,
        data: pd.DataFrame,
        as_of: str | pd.Timestamp | None,
    ) -> pd.DataFrame:
        """Truncate data to as_of date — NO LOOK-AHEAD."""
        if as_of is None:
            return data
        cutoff = pd.Timestamp(as_of)
        truncated = data[data.index <= cutoff]
        return truncated

    def detect(
        self,
        ticker: str,
        data: pd.DataFrame,
        as_of: str | pd.Timestamp | None = None,
    ) -> list[PatternDetection]:
        """Detect all patterns as of a given date.

        Args:
            ticker: Instrument ticker.
            data: Full OHLCV DataFrame (will be truncated to as_of).
            as_of: Detection date. Only data up to this date is used.

        Returns:
            List of PatternDetection objects.
        """
        self.clear_log()
        df = self._truncate(data, as_of)

        if len(df) < self.min_lookback:
            self._log_entry(
                "warn", ticker,
                f"Insufficient data: {len(df)} bars (need {self.min_lookback}). "
                f"as_of={as_of}",
            )
            return []

        as_of_str = (
            pd.Timestamp(as_of).isoformat() if as_of else str(df.index[-1])
        )

        self._log_entry(
            "info", ticker,
            f"Starting pattern detection: {len(df)} bars, as_of={as_of_str}",
        )

        # Check delisting memory for this ticker
        if self.delisting_memory.is_blocked(ticker):
            record = self.delisting_memory.get_record(ticker)
            self._log_entry(
                "error", ticker,
                f"INSTRUMENT BLOCKED/DELISTED: {record.reason.value if record else 'unknown'}. "
                f"Lesson: {record.lesson if record else ''}",
            )
            return []

        if self.delisting_memory.is_suspended(ticker):
            record = self.delisting_memory.get_record(ticker)
            self._log_entry(
                "warn", ticker,
                f"INSTRUMENT SUSPENDED: {record.reason.value if record else 'unknown'}. "
                f"Lesson: {record.lesson if record else ''}",
            )

        # Generate AI reminders for warning patterns
        reminders = self.delisting_memory.generate_reminders(ticker, df, as_of)
        for reminder in reminders:
            self._log_entry(
                "warn" if reminder.severity != "critical" else "error",
                ticker,
                f"AI REMINDER [{reminder.severity.upper()}]: {reminder.message}",
                data={
                    "reminder_type": reminder.reminder_type,
                    "risk_score": reminder.risk_score,
                    "similar_delisted": reminder.similar_delisted,
                    "recommendation": reminder.recommendation,
                },
            )

        detections: list[PatternDetection] = []

        # Run each detector
        for detector_name in [
            "double_bottom",
            "double_top",
            "head_shoulders",
            "inverse_head_shoulders",
            "triangle_ascending",
            "triangle_descending",
            "support_break",
            "resistance_break",
            "bollinger_squeeze",
            "rsi_divergence_bull",
            "rsi_divergence_bear",
            "macd_bullish_cross",
            "macd_bearish_cross",
        ]:
            method = getattr(self, f"_detect_{detector_name}", None)
            if method is None:
                continue

            try:
                result = method(ticker, df, as_of_str)
                if result is not None:
                    detections.append(result)
                    self._log_entry(
                        "detect", ticker,
                        f"DETECTED {result.pattern_type}: "
                        f"direction={result.direction} "
                        f"confidence={result.confidence:.2f} "
                        f"price={result.price_at_detection:.2f}",
                        data={
                            "pattern_type": result.pattern_type,
                            "direction": result.direction,
                            "confidence": result.confidence,
                            "key_levels": result.key_levels,
                        },
                    )
            except Exception as e:
                self._log_entry(
                    "error", ticker,
                    f"Error detecting {detector_name}: {e}",
                )

        # Record detections into PatternMemory
        for d in detections:
            pat_record = self.pattern_memory.record_pattern(
                pattern_type=d.pattern_type,
                ticker=ticker,
                direction=d.direction,
                confidence=d.confidence,
                price_at_detection=d.price_at_detection,
            )
            d.pattern_record = pat_record

        self._log_entry(
            "info", ticker,
            f"Detection complete: {len(detections)} patterns found",
        )

        return detections

    def _get_recent(self, df: pd.DataFrame, n: int = 60) -> pd.DataFrame:
        """Get last n bars."""
        return df.iloc[-n:]

    def _find_local_extrema(
        self,
        series: pd.Series,
        order: int = 5,
    ) -> tuple[list[int], list[int]]:
        """Find local minima and maxima indices.

        Args:
            series: Price series.
            order: How many points on each side to check.

        Returns:
            (minima_indices, maxima_indices)
        """
        mins: list[int] = []
        maxs: list[int] = []

        for i in range(order, len(series) - order):
            window_left = series.iloc[i - order : i]
            window_right = series.iloc[i + 1 : i + order + 1]
            val = series.iloc[i]

            if val < window_left.min() and val < window_right.min():
                mins.append(i)
            if val > window_left.max() and val > window_right.max():
                maxs.append(i)

        return mins, maxs

    def _detect_double_bottom(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect double bottom pattern (bullish reversal)."""
        recent = self._get_recent(df, 60)
        close = recent["close"].astype(float)
        lows = recent["low"].astype(float)

        mins, _ = self._find_local_extrema(lows, order=5)
        if len(mins) < 2:
            return None

        # Check last two minima
        m1, m2 = mins[-2], mins[-1]
        if m2 < len(close) - 10:  # Second trough should be recent
            return None

        price1 = float(lows.iloc[m1])
        price2 = float(lows.iloc[m2])
        trough_diff = abs(price1 - price2) / max(price1, price2)

        # Troughs within 3% of each other
        if trough_diff > 0.03:
            return None

        # Neckline = high between the two troughs
        between = close.iloc[m1 : m2 + 1]
        neckline = float(between.max())

        current_price = float(close.iloc[-1])

        # Confidence based on trough similarity and volume
        confidence = max(0.5, 1.0 - trough_diff * 10)

        # Volume check (second trough should have less volume = selling exhaustion)
        vol1 = float(recent["volume"].iloc[m1])
        vol2 = float(recent["volume"].iloc[m2])
        if vol2 < vol1:
            confidence = min(1.0, confidence + 0.1)

        return PatternDetection(
            pattern_type="double_bottom",
            ticker=ticker,
            as_of=as_of,
            direction="bullish",
            confidence=round(confidence, 3),
            price_at_detection=current_price,
            key_levels={
                "trough_1": round(price1, 2),
                "trough_2": round(price2, 2),
                "neckline": round(neckline, 2),
            },
            description=(
                f"Double bottom: troughs at {price1:.2f} and {price2:.2f} "
                f"(diff {trough_diff:.1%}), neckline at {neckline:.2f}"
            ),
            indicators_snapshot={
                "trough_diff_pct": round(trough_diff * 100, 2),
                "vol_ratio_2_vs_1": round(vol2 / vol1, 3) if vol1 > 0 else 0,
            },
        )

    def _detect_double_top(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect double top pattern (bearish reversal)."""
        recent = self._get_recent(df, 60)
        close = recent["close"].astype(float)
        highs = recent["high"].astype(float)

        _, maxs = self._find_local_extrema(highs, order=5)
        if len(maxs) < 2:
            return None

        m1, m2 = maxs[-2], maxs[-1]
        if m2 < len(close) - 10:
            return None

        price1 = float(highs.iloc[m1])
        price2 = float(highs.iloc[m2])
        peak_diff = abs(price1 - price2) / max(price1, price2)

        if peak_diff > 0.03:
            return None

        between = close.iloc[m1 : m2 + 1]
        neckline = float(between.min())

        current_price = float(close.iloc[-1])
        confidence = max(0.5, 1.0 - peak_diff * 10)

        vol1 = float(recent["volume"].iloc[m1])
        vol2 = float(recent["volume"].iloc[m2])
        if vol2 < vol1:
            confidence = min(1.0, confidence + 0.1)

        return PatternDetection(
            pattern_type="double_top",
            ticker=ticker,
            as_of=as_of,
            direction="bearish",
            confidence=round(confidence, 3),
            price_at_detection=current_price,
            key_levels={
                "peak_1": round(price1, 2),
                "peak_2": round(price2, 2),
                "neckline": round(neckline, 2),
            },
            description=(
                f"Double top: peaks at {price1:.2f} and {price2:.2f} "
                f"(diff {peak_diff:.1%}), neckline at {neckline:.2f}"
            ),
            indicators_snapshot={
                "peak_diff_pct": round(peak_diff * 100, 2),
                "vol_ratio_2_vs_1": round(vol2 / vol1, 3) if vol1 > 0 else 0,
            },
        )

    def _detect_head_shoulders(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect head and shoulders pattern (bearish reversal)."""
        recent = self._get_recent(df, 80)
        highs = recent["high"].astype(float)
        close = recent["close"].astype(float)

        _, maxs = self._find_local_extrema(highs, order=5)
        if len(maxs) < 3:
            return None

        # Check last 3 peaks: L, H, L (head higher than shoulders)
        p1, p2, p3 = maxs[-3], maxs[-2], maxs[-1]
        price1 = float(highs.iloc[p1])
        price2 = float(highs.iloc[p2])
        price3 = float(highs.iloc[p3])

        # Head (p2) should be highest
        if price2 <= price1 or price2 <= price3:
            return None

        # Shouldshoulders roughly equal
        shoulder_diff = abs(price1 - price3) / max(price1, price3)
        if shoulder_diff > 0.05:
            return None

        # Neckline = lows between peaks
        neckline = float(
            recent["low"].iloc[p1 : p3 + 1].min()
        )

        current_price = float(close.iloc[-1])
        confidence = max(0.5, 1.0 - shoulder_diff * 8)

        return PatternDetection(
            pattern_type="head_shoulders",
            ticker=ticker,
            as_of=as_of,
            direction="bearish",
            confidence=round(confidence, 3),
            price_at_detection=current_price,
            key_levels={
                "left_shoulder": round(price1, 2),
                "head": round(price2, 2),
                "right_shoulder": round(price3, 2),
                "neckline": round(neckline, 2),
            },
            description=(
                f"Head & shoulders: LS={price1:.2f}, H={price2:.2f}, "
                f"RS={price3:.2f}, neckline={neckline:.2f}"
            ),
        )

    def _detect_inverse_head_shoulders(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect inverse head and shoulders (bullish reversal)."""
        recent = self._get_recent(df, 80)
        lows = recent["low"].astype(float)
        close = recent["close"].astype(float)

        mins, _ = self._find_local_extrema(lows, order=5)
        if len(mins) < 3:
            return None

        p1, p2, p3 = mins[-3], mins[-2], mins[-1]
        price1 = float(lows.iloc[p1])
        price2 = float(lows.iloc[p2])
        price3 = float(lows.iloc[p3])

        # Head (p2) should be lowest
        if price2 >= price1 or price2 >= price3:
            return None

        shoulder_diff = abs(price1 - price3) / max(price1, price3)
        if shoulder_diff > 0.05:
            return None

        neckline = float(recent["high"].iloc[p1 : p3 + 1].max())

        current_price = float(close.iloc[-1])
        confidence = max(0.5, 1.0 - shoulder_diff * 8)

        return PatternDetection(
            pattern_type="inverse_head_shoulders",
            ticker=ticker,
            as_of=as_of,
            direction="bullish",
            confidence=round(confidence, 3),
            price_at_detection=current_price,
            key_levels={
                "left_shoulder": round(price1, 2),
                "head": round(price2, 2),
                "right_shoulder": round(price3, 2),
                "neckline": round(neckline, 2),
            },
            description=(
                f"Inverse H&S: LS={price1:.2f}, H={price2:.2f}, "
                f"RS={price3:.2f}, neckline={neckline:.2f}"
            ),
        )

    def _detect_triangle_ascending(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect ascending triangle (bullish continuation)."""
        recent = self._get_recent(df, 40)
        highs = recent["high"].astype(float)
        lows = recent["low"].astype(float)
        close = recent["close"].astype(float)

        # Resistance: at least 2 touches at similar level
        _, maxs = self._find_local_extrema(highs, order=3)
        if len(maxs) < 2:
            return None

        resistance = float(highs.iloc[maxs[-1]])
        # Check all recent maxima near resistance
        near_resistance = [
            float(highs.iloc[i]) for i in maxs[-3:]
            if abs(float(highs.iloc[i]) - resistance) / resistance < 0.02
        ]
        if len(near_resistance) < 2:
            return None

        # Support: rising lows
        mins, _ = self._find_local_extrema(lows, order=3)
        if len(mins) < 2:
            return None

        recent_mins = mins[-3:]
        min_prices = [float(lows.iloc[i]) for i in recent_mins]
        # Check if rising
        if len(min_prices) >= 2 and min_prices[-1] <= min_prices[0]:
            return None

        current_price = float(close.iloc[-1])
        confidence = 0.6

        return PatternDetection(
            pattern_type="triangle_ascending",
            ticker=ticker,
            as_of=as_of,
            direction="bullish",
            confidence=confidence,
            price_at_detection=current_price,
            key_levels={
                "resistance": round(resistance, 2),
                "rising_support": round(min_prices[-1], 2),
            },
            description=(
                f"Ascending triangle: resistance={resistance:.2f}, "
                f"rising support={min_prices[-1]:.2f}"
            ),
        )

    def _detect_triangle_descending(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect descending triangle (bearish continuation)."""
        recent = self._get_recent(df, 40)
        highs = recent["high"].astype(float)
        lows = recent["low"].astype(float)
        close = recent["close"].astype(float)

        # Support: at least 2 touches
        mins, _ = self._find_local_extrema(lows, order=3)
        if len(mins) < 2:
            return None

        support = float(lows.iloc[mins[-1]])
        near_support = [
            float(lows.iloc[i]) for i in mins[-3:]
            if abs(float(lows.iloc[i]) - support) / support < 0.02
        ]
        if len(near_support) < 2:
            return None

        # Resistance: falling highs
        _, maxs = self._find_local_extrema(highs, order=3)
        if len(maxs) < 2:
            return None

        recent_maxs = maxs[-3:]
        max_prices = [float(highs.iloc[i]) for i in recent_maxs]
        if len(max_prices) >= 2 and max_prices[-1] >= max_prices[0]:
            return None

        current_price = float(close.iloc[-1])
        confidence = 0.6

        return PatternDetection(
            pattern_type="triangle_descending",
            ticker=ticker,
            as_of=as_of,
            direction="bearish",
            confidence=confidence,
            price_at_detection=current_price,
            key_levels={
                "support": round(support, 2),
                "falling_resistance": round(max_prices[-1], 2),
            },
            description=(
                f"Descending triangle: support={support:.2f}, "
                f"falling resistance={max_prices[-1]:.2f}"
            ),
        )

    def _detect_support_break(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect support level break (bearish)."""
        recent = self._get_recent(df, 60)
        close = recent["close"].astype(float)
        lows = recent["low"].astype(float)

        mins, _ = self._find_local_extrema(lows, order=5)
        if len(mins) < 2:
            return None

        # Recent support level
        support = float(lows.iloc[mins[-2]])
        current_price = float(close.iloc[-1])

        # Price broke below support
        if current_price >= support:
            return None

        break_pct = (support - current_price) / support * 100
        if break_pct < 0.5:
            return None

        confidence = min(0.9, 0.5 + break_pct / 10)

        return PatternDetection(
            pattern_type="support_break",
            ticker=ticker,
            as_of=as_of,
            direction="bearish",
            confidence=round(confidence, 3),
            price_at_detection=current_price,
            key_levels={
                "broken_support": round(support, 2),
                "break_pct": round(break_pct, 2),
            },
            description=(
                f"Support break: support={support:.2f}, "
                f"price={current_price:.2f} ({break_pct:.1f}% below)"
            ),
        )

    def _detect_resistance_break(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect resistance level break (bullish)."""
        recent = self._get_recent(df, 60)
        close = recent["close"].astype(float)
        highs = recent["high"].astype(float)

        _, maxs = self._find_local_extrema(highs, order=5)
        if len(maxs) < 2:
            return None

        resistance = float(highs.iloc[maxs[-2]])
        current_price = float(close.iloc[-1])

        if current_price <= resistance:
            return None

        break_pct = (current_price - resistance) / resistance * 100
        if break_pct < 0.5:
            return None

        confidence = min(0.9, 0.5 + break_pct / 10)

        return PatternDetection(
            pattern_type="resistance_break",
            ticker=ticker,
            as_of=as_of,
            direction="bullish",
            confidence=round(confidence, 3),
            price_at_detection=current_price,
            key_levels={
                "broken_resistance": round(resistance, 2),
                "break_pct": round(break_pct, 2),
            },
            description=(
                f"Resistance break: resistance={resistance:.2f}, "
                f"price={current_price:.2f} ({break_pct:.1f}% above)"
            ),
        )

    def _detect_bollinger_squeeze(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect Bollinger Band squeeze (volatility contraction → expansion)."""
        recent = self._get_recent(df, 60)
        close = recent["close"].astype(float)

        if len(close) < 20:
            return None

        ma = close.rolling(20).mean()
        sd = close.rolling(20).std()
        upper = ma + 2 * sd
        lower = ma - 2 * sd
        bandwidth = (upper - lower) / ma

        # Current bandwidth vs historical
        current_bw = float(bandwidth.iloc[-1])
        avg_bw = float(bandwidth.iloc[-20:].mean()) if len(bandwidth) >= 20 else 0

        if avg_bw == 0 or current_bw == 0:
            return None

        # Squeeze: current bandwidth < 50% of average
        if current_bw / avg_bw > 0.5:
            return None

        current_price = float(close.iloc[-1])
        confidence = min(0.9, 0.5 + (1 - current_bw / avg_bw))

        return PatternDetection(
            pattern_type="bollinger_squeeze",
            ticker=ticker,
            as_of=as_of,
            direction="neutral",
            confidence=round(confidence, 3),
            price_at_detection=current_price,
            key_levels={
                "bb_upper": round(float(upper.iloc[-1]), 2),
                "bb_lower": round(float(lower.iloc[-1]), 2),
                "bb_middle": round(float(ma.iloc[-1]), 2),
                "bandwidth": round(current_bw, 4),
                "avg_bandwidth": round(avg_bw, 4),
            },
            description=(
                f"Bollinger squeeze: bandwidth={current_bw:.4f} "
                f"vs avg={avg_bw:.4f} ({current_bw / avg_bw:.1%})"
            ),
        )

    def _detect_rsi_divergence_bull(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect bullish RSI divergence (price lower low, RSI higher low)."""
        recent = self._get_recent(df, 60)
        close = recent["close"].astype(float)

        if len(close) < 14:
            return None

        # Compute RSI
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        mins_price, _ = self._find_local_extrema(close, order=5)
        if len(mins_price) < 2:
            return None

        m1, m2 = mins_price[-2], mins_price[-1]
        price1 = float(close.iloc[m1])
        price2 = float(close.iloc[m2])
        rsi1 = float(rsi.iloc[m1])
        rsi2 = float(rsi.iloc[m2])

        # Price lower low, RSI higher low
        if price2 >= price1 or rsi2 <= rsi1:
            return None

        current_price = float(close.iloc[-1])
        confidence = min(0.85, 0.5 + abs(rsi2 - rsi1) / 20)

        return PatternDetection(
            pattern_type="rsi_divergence_bull",
            ticker=ticker,
            as_of=as_of,
            direction="bullish",
            confidence=round(confidence, 3),
            price_at_detection=current_price,
            key_levels={
                "price_low_1": round(price1, 2),
                "price_low_2": round(price2, 2),
                "rsi_1": round(rsi1, 2),
                "rsi_2": round(rsi2, 2),
            },
            description=(
                f"Bullish RSI divergence: price {price1:.2f}→{price2:.2f} (lower), "
                f"RSI {rsi1:.1f}→{rsi2:.1f} (higher)"
            ),
        )

    def _detect_rsi_divergence_bear(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect bearish RSI divergence (price higher high, RSI lower high)."""
        recent = self._get_recent(df, 60)
        close = recent["close"].astype(float)

        if len(close) < 14:
            return None

        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        _, maxs_price = self._find_local_extrema(close, order=5)
        if len(maxs_price) < 2:
            return None

        m1, m2 = maxs_price[-2], maxs_price[-1]
        price1 = float(close.iloc[m1])
        price2 = float(close.iloc[m2])
        rsi1 = float(rsi.iloc[m1])
        rsi2 = float(rsi.iloc[m2])

        # Price higher high, RSI lower high
        if price2 <= price1 or rsi2 >= rsi1:
            return None

        current_price = float(close.iloc[-1])
        confidence = min(0.85, 0.5 + abs(rsi1 - rsi2) / 20)

        return PatternDetection(
            pattern_type="rsi_divergence_bear",
            ticker=ticker,
            as_of=as_of,
            direction="bearish",
            confidence=round(confidence, 3),
            price_at_detection=current_price,
            key_levels={
                "price_high_1": round(price1, 2),
                "price_high_2": round(price2, 2),
                "rsi_1": round(rsi1, 2),
                "rsi_2": round(rsi2, 2),
            },
            description=(
                f"Bearish RSI divergence: price {price1:.2f}→{price2:.2f} (higher), "
                f"RSI {rsi1:.1f}→{rsi2:.1f} (lower)"
            ),
        )

    def _detect_macd_bullish_cross(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect MACD bullish crossover."""
        recent = self._get_recent(df, 40)
        close = recent["close"].astype(float)

        if len(close) < 26:
            return None

        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=9, adjust=False).mean()

        # Check for crossover in last 3 bars
        for i in range(-3, 0):
            if (
                macd_line.iloc[i - 1] <= signal_line.iloc[i - 1]
                and macd_line.iloc[i] > signal_line.iloc[i]
            ):
                current_price = float(close.iloc[-1])
                return PatternDetection(
                    pattern_type="macd_bullish_cross",
                    ticker=ticker,
                    as_of=as_of,
                    direction="bullish",
                    confidence=0.65,
                    price_at_detection=current_price,
                    key_levels={
                        "macd": round(float(macd_line.iloc[i]), 4),
                        "signal": round(float(signal_line.iloc[i]), 4),
                    },
                    description=(
                        f"MACD bullish crossover: "
                        f"MACD={float(macd_line.iloc[i]):.4f} "
                        f"> signal={float(signal_line.iloc[i]):.4f}"
                    ),
                )

        return None

    def _detect_macd_bearish_cross(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str,
    ) -> PatternDetection | None:
        """Detect MACD bearish crossover."""
        recent = self._get_recent(df, 40)
        close = recent["close"].astype(float)

        if len(close) < 26:
            return None

        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=9, adjust=False).mean()

        for i in range(-3, 0):
            if (
                macd_line.iloc[i - 1] >= signal_line.iloc[i - 1]
                and macd_line.iloc[i] < signal_line.iloc[i]
            ):
                current_price = float(close.iloc[-1])
                return PatternDetection(
                    pattern_type="macd_bearish_cross",
                    ticker=ticker,
                    as_of=as_of,
                    direction="bearish",
                    confidence=0.65,
                    price_at_detection=current_price,
                    key_levels={
                        "macd": round(float(macd_line.iloc[i]), 4),
                        "signal": round(float(signal_line.iloc[i]), 4),
                    },
                    description=(
                        f"MACD bearish crossover: "
                        f"MACD={float(macd_line.iloc[i]):.4f} "
                        f"< signal={float(signal_line.iloc[i]):.4f}"
                    ),
                )

        return None
