"""Corporate action engine, feature store, and pattern memory.

References: pustaka/18 §3.2, pustaka/20, pustaka/26.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd


class ActionType(Enum):
    """Corporate action types."""

    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    DIVIDEND = "dividend"
    STOCK_DIVIDEND = "stock_dividend"
    RIGHTS = "rights"
    BONUS = "bonus"
    MERGER = "merger"
    SPINOFF = "spinoff"
    DELISTING = "delisting"


@dataclass
class CorporateAction:
    """A corporate action event."""

    ticker: str
    action_type: ActionType
    ex_date: str
    ratio: float = 1.0
    value: float = 0.0
    currency: str = "IDR"
    description: str = ""


@dataclass
class AdjustedBar:
    """A price bar after corporate action adjustment."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjustment_factor: float = 1.0


class CorporateActionEngine:
    """Processes corporate actions and adjusts historical OHLCV.

    Applies backward adjustment to price data based on
    splits, dividends, and other corporate actions.
    """

    def __init__(self) -> None:
        self._actions: list[CorporateAction] = []

    def register_action(self, action: CorporateAction) -> None:
        """Register a corporate action.

        Args:
            action: The corporate action to register.
        """
        self._actions.append(action)
        self._actions.sort(key=lambda a: a.ex_date, reverse=True)

    def adjust_ohlcv(
        self,
        ticker: str,
        data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Apply backward adjustment to OHLCV data.

        Args:
            ticker: Ticker symbol.
            data: DataFrame with columns open, high, low, close, volume.

        Returns:
            Adjusted DataFrame.
        """
        if data.empty:
            return data.copy()

        result = data.copy()
        actions = [a for a in self._actions if a.ticker == ticker]

        for action in actions:
            ex_date = pd.Timestamp(action.ex_date)
            mask = result.index < ex_date
            if not mask.any():
                continue

            if action.action_type in (
                ActionType.SPLIT, ActionType.STOCK_DIVIDEND, ActionType.BONUS,
            ):
                ratio = action.ratio
                for col in ["open", "high", "low", "close"]:
                    if col in result.columns:
                        result.loc[mask, col] /= ratio
                if "volume" in result.columns:
                    result.loc[mask, "volume"] *= ratio

            elif action.action_type == ActionType.DIVIDEND:
                div = action.value
                if "close" in result.columns:
                    prev_close = result.loc[mask, "close"].iloc[-1] if mask.any() else 0
                    if prev_close > 0:
                        factor = 1 - (div / prev_close)
                        for col in ["open", "high", "low", "close"]:
                            if col in result.columns:
                                result.loc[mask, col] *= factor

        return result

    def get_actions(self, ticker: str | None = None) -> list[CorporateAction]:
        """Get registered actions, optionally filtered by ticker."""
        if ticker:
            return [a for a in self._actions if a.ticker == ticker]
        return list(self._actions)


@dataclass
class FeatureEntry:
    """A single feature entry in the feature store."""

    ticker: str
    feature_name: str
    value: float
    as_of: str
    market_mic: str = "XIDX"
    asset_class: str = "equity"
    tags: list[str] = field(default_factory=list)


class FeatureStore:
    """Feature store with 42+ features per ticker.

    Stores computed features tagged by market_mic and asset_class.
    """

    def __init__(self) -> None:
        self._features: dict[str, list[FeatureEntry]] = {}

    def store(self, entry: FeatureEntry) -> None:
        """Store a feature entry.

        Args:
            entry: Feature entry to store.
        """
        key = f"{entry.ticker}:{entry.feature_name}"
        self._features.setdefault(key, []).append(entry)

    def store_batch(self, entries: list[FeatureEntry]) -> int:
        """Store multiple feature entries.

        Args:
            entries: List of feature entries.

        Returns:
            Number of entries stored.
        """
        for entry in entries:
            self.store(entry)
        return len(entries)

    def get_features(
        self,
        ticker: str,
        as_of: str | None = None,
    ) -> dict[str, float]:
        """Get all features for a ticker.

        Args:
            ticker: Ticker symbol.
            as_of: Optional date filter (ISO format).

        Returns:
            Dict of feature_name -> value.
        """
        result: dict[str, float] = {}
        for key, entries in self._features.items():
            if not key.startswith(f"{ticker}:"):
                continue
            feature_name = key.split(":", 1)[1]
            if as_of:
                filtered = [e for e in entries if e.as_of <= as_of]
                if filtered:
                    latest = max(filtered, key=lambda e: e.as_of)
                    result[feature_name] = latest.value
            else:
                if entries:
                    latest = max(entries, key=lambda e: e.as_of)
                    result[feature_name] = latest.value
        return result

    def get_feature_vector(
        self,
        ticker: str,
        feature_names: list[str] | None = None,
    ) -> np.ndarray[Any, np.dtype[Any]]:
        """Get feature vector for a ticker.

        Args:
            ticker: Ticker symbol.
            feature_names: Optional list of specific features.

        Returns:
            Numpy array of feature values.
        """
        features = self.get_features(ticker)
        if feature_names:
            return np.array([features.get(f, 0.0) for f in feature_names])
        return np.array(list(features.values()))

    def list_tickers(self) -> list[str]:
        """List all tickers with features."""
        tickers = set()
        for key in self._features:
            tickers.add(key.split(":")[0])
        return sorted(tickers)

    def feature_count(self, ticker: str | None = None) -> int:
        """Count features for a ticker or all tickers."""
        if ticker:
            return len(self.get_features(ticker))
        return len(self._features)

    @property
    def all_features(self) -> list[FeatureEntry]:
        """All feature entries."""
        return [e for entries in self._features.values() for e in entries]


@dataclass
class PatternRecord:
    """A detected pattern with reliability tracking."""

    pattern_id: str
    pattern_type: str
    ticker: str
    detected_at: str
    direction: str = "neutral"  # bullish, bearish, neutral
    confidence: float = 0.0
    outcome: str = ""  # confirmed, failed, pending
    price_at_detection: float = 0.0
    price_after_n_days: float = 0.0
    return_pct: float = 0.0


class PatternMemory:
    """Pattern memory / reliability tracker.

    Tracks detected patterns and their outcomes to build
    reliability statistics over time.
    """

    def __init__(self, evaluation_days: int = 5) -> None:
        self._patterns: list[PatternRecord] = []
        self._pattern_counter = 0
        self.evaluation_days = evaluation_days

    def record_pattern(
        self,
        pattern_type: str,
        ticker: str,
        direction: str = "neutral",
        confidence: float = 0.0,
        price_at_detection: float = 0.0,
    ) -> PatternRecord:
        """Record a newly detected pattern.

        Args:
            pattern_type: Type of pattern (e.g., "double_bottom").
            ticker: Ticker symbol.
            direction: Predicted direction.
            confidence: Confidence score (0-1).
            price_at_detection: Price when pattern was detected.

        Returns:
            The created PatternRecord.
        """
        self._pattern_counter += 1
        pattern = PatternRecord(
            pattern_id=f"PAT-{self._pattern_counter:05d}",
            pattern_type=pattern_type,
            ticker=ticker,
            detected_at=datetime.now(UTC).isoformat(),
            direction=direction,
            confidence=confidence,
            price_at_detection=price_at_detection,
            outcome="pending",
        )
        self._patterns.append(pattern)
        return pattern

    def update_outcome(
        self,
        pattern_id: str,
        price_after: float,
    ) -> PatternRecord | None:
        """Update the outcome of a pattern.

        Args:
            pattern_id: Pattern to update.
            price_after: Price after evaluation period.

        Returns:
            Updated PatternRecord, or None if not found.
        """
        pattern = next((p for p in self._patterns if p.pattern_id == pattern_id), None)
        if pattern is None:
            return None

        pattern.price_after_n_days = price_after
        if pattern.price_at_detection > 0:
            pattern.return_pct = (
                (price_after - pattern.price_at_detection)
                / pattern.price_at_detection * 100
            )

        if pattern.direction == "bullish":
            pattern.outcome = "confirmed" if price_after > pattern.price_at_detection else "failed"
        elif pattern.direction == "bearish":
            pattern.outcome = "confirmed" if price_after < pattern.price_at_detection else "failed"
        else:
            pattern.outcome = "confirmed"

        return pattern

    def get_reliability(
        self,
        pattern_type: str | None = None,
        ticker: str | None = None,
    ) -> dict[str, float]:
        """Get reliability statistics for patterns.

        Args:
            pattern_type: Optional pattern type filter.
            ticker: Optional ticker filter.

        Returns:
            Dict with reliability stats.
        """
        filtered = self._patterns
        if pattern_type:
            filtered = [p for p in filtered if p.pattern_type == pattern_type]
        if ticker:
            filtered = [p for p in filtered if p.ticker == ticker]

        evaluated = [p for p in filtered if p.outcome in ("confirmed", "failed")]
        if not evaluated:
            return {"reliability": 0.0, "total": 0, "confirmed": 0, "failed": 0}

        confirmed = sum(1 for p in evaluated if p.outcome == "confirmed")
        failed = sum(1 for p in evaluated if p.outcome == "failed")

        return {
            "reliability": round(confirmed / len(evaluated), 4),
            "total": len(evaluated),
            "confirmed": confirmed,
            "failed": failed,
        }

    def get_patterns(
        self,
        ticker: str | None = None,
        outcome: str | None = None,
    ) -> list[PatternRecord]:
        """Get patterns, optionally filtered."""
        filtered = self._patterns
        if ticker:
            filtered = [p for p in filtered if p.ticker == ticker]
        if outcome:
            filtered = [p for p in filtered if p.outcome == outcome]
        return filtered

    @property
    def patterns(self) -> list[PatternRecord]:
        """All pattern records."""
        return list(self._patterns)
