"""Feature store automation (pustaka/58).

Manages feature computation, storage, and retrieval for ML pipelines.
Supports:
- Feature definition and registration
- Feature computation from raw OHLCV data
- Feature versioning and caching
- Feature serving for training and inference
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd


@dataclass
class FeatureDefinition:
    """Definition of a computable feature."""

    name: str
    description: str
    version: str
    compute_fn: Callable[[pd.DataFrame], pd.Series]
    dependencies: list[str] = field(default_factory=list)
    dtype: str = "float64"


@dataclass
class FeatureSet:
    """A computed feature set."""

    name: str
    version: str
    features: pd.DataFrame
    computed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    n_rows: int = 0

    def __post_init__(self) -> None:
        self.n_rows = len(self.features)


class FeatureStore:
    """Feature store for ML pipeline automation."""

    def __init__(self) -> None:
        self._definitions: dict[str, FeatureDefinition] = {}
        self._cache: dict[str, FeatureSet] = {}

    def register(self, definition: FeatureDefinition) -> None:
        """Register a feature definition.

        Args:
            definition: Feature definition to register.
        """
        key = f"{definition.name}@{definition.version}"
        self._definitions[key] = definition

    def register_default_features(self) -> None:
        """Register default trading features."""
        # RSI
        self.register(FeatureDefinition(
            name="rsi_14",
            description="Relative Strength Index (14-period)",
            version="1.0.0",
            compute_fn=self._compute_rsi,
            dependencies=["close"],
        ))

        # Moving averages
        self.register(FeatureDefinition(
            name="sma_20",
            description="Simple Moving Average (20-period)",
            version="1.0.0",
            compute_fn=lambda df: df["close"].rolling(20).mean(),
            dependencies=["close"],
        ))

        self.register(FeatureDefinition(
            name="sma_50",
            description="Simple Moving Average (50-period)",
            version="1.0.0",
            compute_fn=lambda df: df["close"].rolling(50).mean(),
            dependencies=["close"],
        ))

        # Bollinger Bands width
        self.register(FeatureDefinition(
            name="bb_width",
            description="Bollinger Bands width",
            version="1.0.0",
            compute_fn=self._compute_bb_width,
            dependencies=["close"],
        ))

        # Volume ratio
        self.register(FeatureDefinition(
            name="volume_ratio",
            description="Volume / 20-day average volume",
            version="1.0.0",
            compute_fn=lambda df: df["volume"] / df["volume"].rolling(20).mean(),
            dependencies=["volume"],
        ))

        # ATR
        self.register(FeatureDefinition(
            name="atr_14",
            description="Average True Range (14-period)",
            version="1.0.0",
            compute_fn=self._compute_atr,
            dependencies=["high", "low", "close"],
        ))

        # Forward returns (target)
        self.register(FeatureDefinition(
            name="forward_return_5d",
            description="5-day forward return",
            version="1.0.0",
            compute_fn=lambda df: df["close"].shift(-5).pct_change(5, fill_method=None),
            dependencies=["close"],
        ))

    @staticmethod
    def _compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _compute_bb_width(df: pd.DataFrame, period: int = 20) -> pd.Series:
        sma = df["close"].rolling(period).mean()
        std = df["close"].rolling(period).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        return (upper - lower) / sma

    @staticmethod
    def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def compute(
        self,
        data: pd.DataFrame,
        feature_names: list[str] | None = None,
        version: str = "1.0.0",
    ) -> FeatureSet:
        """Compute features from raw data.

        Args:
            data: Raw OHLCV DataFrame.
            feature_names: Features to compute. All if None.
            version: Feature version.

        Returns:
            FeatureSet with computed features.
        """
        if not self._definitions:
            self.register_default_features()

        if feature_names is None:
            feature_names = list(self._definitions.keys())

        # Also compute any dependencies
        to_compute = set()
        for name in feature_names:
            key = f"{name}@{version}" if "@" not in name else name
            to_compute.add(key)

        results = {}
        for key in to_compute:
            defn = self._definitions.get(key)
            if defn is None:
                # Try without version
                name = key.split("@")[0]
                defn = self._definitions.get(f"{name}@{version}")
            if defn is None:
                continue
            try:
                results[defn.name] = defn.compute_fn(data)
            except Exception as e:
                results[defn.name] = pd.Series(
                    np.nan, index=data.index, name=defn.name,
                )
                results[defn.name].attrs["error"] = str(e)

        feature_df = pd.DataFrame(results, index=data.index)
        return FeatureSet(
            name="default",
            version=version,
            features=feature_df,
        )

    def cache(self, feature_set: FeatureSet, key: str | None = None) -> str:
        """Cache a computed feature set.

        Args:
            feature_set: Feature set to cache.
            key: Optional cache key.

        Returns:
            Cache key used.
        """
        cache_key = key or f"{feature_set.name}@{feature_set.version}"
        self._cache[cache_key] = feature_set
        return cache_key

    def get_cached(self, key: str) -> FeatureSet | None:
        """Retrieve a cached feature set."""
        return self._cache.get(key)

    @property
    def registered_features(self) -> list[str]:
        """List registered feature names."""
        return list(self._definitions.keys())
