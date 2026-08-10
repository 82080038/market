"""Tests for meta_labeling module: triple-barrier, bet sizing, no-look-ahead.

References: pustaka/23 §7.2 (Triple-Barrier), §7.3 (Meta-Labeling).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.analysis.meta_labeling import (
    META_FEATURE_COLS,
    MetaLabeler,
    bet_size_from_probability,
    compute_meta_features,
    cusum_filter,
    purged_walk_forward_splits,
    triple_barrier_labels,
)

# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_ohlcv() -> pd.DataFrame:
    """200-bar synthetic OHLCV with a deterministic uptrend then downtrend."""
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    np.random.seed(42)
    # First 100 bars uptrend, then downtrend.
    trend = np.concatenate([
        np.linspace(0, 20, 100),
        np.linspace(20, 0, 100),
    ])
    close = 100.0 + trend + np.random.randn(n) * 0.5
    high = close + np.abs(np.random.randn(n)) * 0.5
    low = close - np.abs(np.random.randn(n)) * 0.5
    volume = np.random.randint(1000, 10000, n).astype(float)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )


@pytest.fixture
def deterministic_ohlcv() -> pd.DataFrame:
    """Deterministic OHLCV where we know exactly which barriers get hit."""
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    # Price jumps +3% on day 2, then flat. Upper barrier +2% should hit on day 2.
    close = np.array([100, 100, 103, 103, 103, 103, 103, 103, 103, 103], dtype=float)
    high = close + 0.5
    low = close - 0.5
    return pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.full(10, 5000.0),
        },
        index=dates,
    )


# ── Triple-Barrier Labeling ────────────────────────────────────────────────


class TestTripleBarrier:
    """Tests for triple_barrier_labels."""

    def test_upper_barrier_hit(self, deterministic_ohlcv: pd.DataFrame) -> None:
        """A buy at day 1 should hit the +2% upper barrier on day 2."""
        events = pd.DataFrame(
            {"side": [1]}, index=[deterministic_ohlcv.index[1]],
        )
        labels = triple_barrier_labels(
            deterministic_ohlcv,
            events,
            upper_barrier=0.02,
            lower_barrier=-0.02,
            vertical_barrier=5,
        )
        assert len(labels) == 1
        row = labels.iloc[0]
        assert row["label"] == 1  # upper barrier
        assert bool(row["correct"]) is True  # buy + upper = correct
        assert row["hit_day"] == 1  # hit on day 2 (1 bar after entry)

    def test_lower_barrier_hit(self, deterministic_ohlcv: pd.DataFrame) -> None:
        """A sell at day 1 should NOT hit lower (-2%) since price goes up."""
        events = pd.DataFrame(
            {"side": [-1]}, index=[deterministic_ohlcv.index[1]],
        )
        labels = triple_barrier_labels(
            deterministic_ohlcv,
            events,
            upper_barrier=0.02,
            lower_barrier=-0.02,
            vertical_barrier=5,
        )
        row = labels.iloc[0]
        # Price went up to 103, so upper barrier (102) is hit → label=+1.
        # For a sell, label=+1 means incorrect.
        assert row["label"] == 1
        assert bool(row["correct"]) is False

    def test_vertical_barrier(self, deterministic_ohlcv: pd.DataFrame) -> None:
        """When neither horizontal barrier is hit, label should be 0 (vertical)."""
        # Use tiny barriers that won't be hit by the +3% move... actually +3%
        # exceeds any small upper barrier. Build a flat price series instead.
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        close = np.full(10, 100.0)
        df = pd.DataFrame(
            {
                "open": close, "high": close + 0.1, "low": close - 0.1,
                "close": close, "volume": np.full(10, 1000.0),
            },
            index=dates,
        )
        events = pd.DataFrame({"side": [1]}, index=[df.index[1]])
        labels = triple_barrier_labels(
            df, events,
            upper_barrier=0.02, lower_barrier=-0.02, vertical_barrier=5,
        )
        row = labels.iloc[0]
        assert row["label"] == 0  # vertical barrier
        assert bool(row["correct"]) is False  # buy but no upper hit
        assert row["hit_day"] == 5

    def test_no_look_ahead(self, synthetic_ohlcv: pd.DataFrame) -> None:
        """Label for event at T must not depend on data before T+1.

        We verify by truncating the DataFrame to only the bars up to
        T + vertical_barrier and confirming the label is identical to the
        label computed on the full dataset.
        """
        event_date = synthetic_ohlcv.index[50]
        events = pd.DataFrame({"side": [1]}, index=[event_date])

        full_labels = triple_barrier_labels(
            synthetic_ohlcv, events,
            upper_barrier=0.02, lower_barrier=-0.02, vertical_barrier=5,
        )

        # Truncate to only T + vertical_barrier bars (no future data beyond).
        truncate_pos = synthetic_ohlcv.index.get_loc(event_date) + 6
        truncated = synthetic_ohlcv.iloc[:truncate_pos]
        trunc_labels = triple_barrier_labels(
            truncated, events,
            upper_barrier=0.02, lower_barrier=-0.02, vertical_barrier=5,
        )

        assert full_labels.iloc[0]["label"] == trunc_labels.iloc[0]["label"]
        assert full_labels.iloc[0]["hit_day"] == trunc_labels.iloc[0]["hit_day"]
        assert full_labels.iloc[0]["correct"] == trunc_labels.iloc[0]["correct"]

    def test_atr_scaling(self, deterministic_ohlcv: pd.DataFrame) -> None:
        """When use_atr=True, barriers scale by ATR at entry."""
        df = deterministic_ohlcv.copy()
        df["atr"] = 1.0  # constant ATR
        events = pd.DataFrame({"side": [1]}, index=[df.index[1]])
        labels = triple_barrier_labels(
            df, events,
            upper_barrier=2.0, lower_barrier=-2.0,  # multipliers
            vertical_barrier=5, use_atr=True, atr_col="atr",
        )
        # upper level = 100 * (1 + 2.0 * 1.0) = 300 → never hit by 103.
        # lower level = 100 * (1 - 2.0 * 1.0) = -100 → never hit.
        # So label should be 0 (vertical).
        row = labels.iloc[0]
        assert row["label"] == 0

    def test_empty_events(self, deterministic_ohlcv: pd.DataFrame) -> None:
        """Empty events DataFrame should return empty labels."""
        events = pd.DataFrame({"side": []}, index=pd.DatetimeIndex([]))
        labels = triple_barrier_labels(deterministic_ohlcv, events)
        assert labels.empty


# ── Bet Sizing ─────────────────────────────────────────────────────────────


class TestBetSizing:
    """Tests for bet_size_from_probability."""

    def test_below_threshold_no_trade(self) -> None:
        """Probability below threshold → size 0, no trade."""
        result = bet_size_from_probability(0.3, prob_threshold=0.5)
        assert result.size == 0.0
        assert result.trade is False
        assert result.probability == 0.3

    def test_at_threshold(self) -> None:
        """Probability exactly at threshold → linear gives size 0."""
        result = bet_size_from_probability(0.5, prob_threshold=0.5, method="linear")
        assert result.size == 0.0
        # (0.5 - 0.5) * 2 = 0 → trade is False (size not > 0)
        assert result.trade is False

    def test_above_threshold_linear(self) -> None:
        """Linear method: size = (p - 0.5) * 2."""
        result = bet_size_from_probability(0.75, prob_threshold=0.5, method="linear")
        assert pytest.approx(result.size) == 0.5  # (0.75 - 0.5) * 2
        assert result.trade is True

    def test_max_size_cap(self) -> None:
        """Size should be capped at max_size."""
        result = bet_size_from_probability(
            1.0, prob_threshold=0.5, max_size=0.8, method="linear",
        )
        # (1.0 - 0.5) * 2 = 1.0 → capped to 0.8
        assert result.size == 0.8
        assert result.trade is True

    def test_lopes_de_prado_method(self) -> None:
        """López de Prado method: size = probability (when >= threshold)."""
        result = bet_size_from_probability(
            0.7, prob_threshold=0.5, method="lopes_de_prado",
        )
        assert pytest.approx(result.size) == 0.7
        assert result.trade is True

    def test_probability_clipped(self) -> None:
        """Probabilities outside [0, 1] are clipped."""
        result = bet_size_from_probability(1.5, prob_threshold=0.5)
        assert result.probability == 1.0
        assert result.size == 1.0

        result_neg = bet_size_from_probability(-0.5, prob_threshold=0.5)
        assert result_neg.probability == 0.0
        assert result_neg.size == 0.0
        assert result_neg.trade is False


# ── CUSUM Filter ───────────────────────────────────────────────────────────


class TestCUSUMFilter:
    """Tests for cusum_filter."""

    def test_returns_subset_of_index(self, synthetic_ohlcv: pd.DataFrame) -> None:
        """CUSUM events must be a subset of the close index."""
        events = cusum_filter(synthetic_ohlcv["close"], threshold=0.02)
        assert len(events) > 0
        for ts in events:
            assert ts in synthetic_ohlcv.index

    def test_flat_price_no_events(self) -> None:
        """A perfectly flat price series should produce no CUSUM events."""
        dates = pd.date_range("2024-01-01", periods=50, freq="B")
        close = pd.Series(np.full(50, 100.0), index=dates)
        events = cusum_filter(close, threshold=0.02)
        assert len(events) == 0

    def test_big_jump_produces_event(self) -> None:
        """A single large jump should trigger at least one CUSUM event."""
        dates = pd.date_range("2024-01-01", periods=30, freq="B")
        close = np.full(30, 100.0)
        close[15] = 110.0  # +10% jump
        close[16:] = 110.0
        events = cusum_filter(pd.Series(close, index=dates), threshold=0.02)
        assert len(events) > 0


# ── Feature Engineering ────────────────────────────────────────────────────


class TestMetaFeatures:
    """Tests for compute_meta_features."""

    def test_all_columns_present(self, synthetic_ohlcv: pd.DataFrame) -> None:
        """All expected feature columns should be present."""
        features = compute_meta_features(synthetic_ohlcv)
        for col in META_FEATURE_COLS:
            assert col in features.columns

    def test_no_nan_after_warmup(self, synthetic_ohlcv: pd.DataFrame) -> None:
        """Features should not have NaN after the warmup period."""
        features = compute_meta_features(synthetic_ohlcv)
        # After 60 bars all rolling windows should be populated.
        warm = features.iloc[60:]
        assert not warm.isna().any().any(), "NaN values found after warmup"

    def test_no_look_ahead_in_features(self, synthetic_ohlcv: pd.DataFrame) -> None:
        """Features at time T must be identical whether computed on full data
        or on data truncated at T (no future information used)."""
        full = compute_meta_features(synthetic_ohlcv)
        cutoff = synthetic_ohlcv.index[100]
        truncated = synthetic_ohlcv.loc[:cutoff]
        trunc = compute_meta_features(truncated)

        # Compare the row at the cutoff date.
        for col in META_FEATURE_COLS:
            full_val = float(full.loc[cutoff, col])
            trunc_val = float(trunc.loc[cutoff, col])
            assert pytest.approx(full_val, abs=1e-9) == trunc_val, (
                f"Look-ahead detected in feature {col}: "
                f"full={full_val}, trunc={trunc_val}"
            )


# ── Purged Walk-Forward CV ─────────────────────────────────────────────────


class TestPurgedWalkForward:
    """Tests for purged_walk_forward_splits."""

    def test_no_overlap(self) -> None:
        """Train and test indices must not overlap."""
        splits = purged_walk_forward_splits(500, n_splits=5, purge_gap=5, embargo=5)
        assert len(splits) > 0
        for train_idx, test_idx in splits:
            assert len(np.intersect1d(train_idx, test_idx)) == 0

    def test_test_after_train(self) -> None:
        """All test indices must come after all train indices (walk-forward)."""
        splits = purged_walk_forward_splits(500, n_splits=5, purge_gap=5, embargo=5)
        for train_idx, test_idx in splits:
            assert test_idx.min() > train_idx.max()

    def test_purge_gap_respected(self) -> None:
        """There must be at least purge_gap bars between train end and test start."""
        purge_gap = 7
        splits = purged_walk_forward_splits(
            500, n_splits=5, purge_gap=purge_gap, embargo=5,
        )
        for train_idx, test_idx in splits:
            gap = test_idx.min() - train_idx.max()
            assert gap >= purge_gap, f"Purge gap violated: {gap} < {purge_gap}"

    def test_empty_for_small_n(self) -> None:
        """Very small n should produce no splits."""
        splits = purged_walk_forward_splits(5, n_splits=5, purge_gap=5, embargo=5)
        assert splits == []


# ── MetaLabeler Integration ────────────────────────────────────────────────


class TestMetaLabeler:
    """Integration tests for the MetaLabeler class."""

    def test_predict_without_fit_returns_no_trade(
        self, synthetic_ohlcv: pd.DataFrame,
    ) -> None:
        """Calling predict before fit should return a no-trade result."""
        labeler = MetaLabeler(min_train_samples=10)
        result = labeler.predict(
            synthetic_ohlcv, as_of=synthetic_ohlcv.index[100],
            primary_side=1, primary_confidence=0.7,
        )
        assert result.trade is False
        assert result.bet_size == 0.0
        assert result.model_available is False

    def test_flat_side_no_trade(self, synthetic_ohlcv: pd.DataFrame) -> None:
        """A flat primary side (0) should always result in no trade."""
        labeler = MetaLabeler(min_train_samples=10)
        # Fit with a trivial model first (may not train due to data size).
        events = pd.DataFrame(
            {"side": [1] * 20},
            index=synthetic_ohlcv.index[20:40],
        )
        labeler.fit(synthetic_ohlcv, events)
        result = labeler.predict(
            synthetic_ohlcv, as_of=synthetic_ohlcv.index[100],
            primary_side=0, primary_confidence=0.5,
        )
        assert result.trade is False
        assert result.bet_size == 0.0

    def test_fit_and_predict_end_to_end(
        self, synthetic_ohlcv: pd.DataFrame,
    ) -> None:
        """Full fit + predict cycle should produce a valid result."""
        # Create events at regular intervals with mixed sides.
        event_dates = synthetic_ohlcv.index[30:170:5]
        sides = [1 if i % 2 == 0 else -1 for i in range(len(event_dates))]
        events = pd.DataFrame({"side": sides}, index=event_dates)

        labeler = MetaLabeler(
            upper_barrier=0.03,
            lower_barrier=-0.03,
            vertical_barrier=5,
            min_train_samples=20,
            n_estimators=20,
            max_depth=3,
            n_splits=3,
            purge_gap=3,
            embargo=3,
        )
        metrics = labeler.fit(synthetic_ohlcv, events)
        assert "mean_accuracy" in metrics
        assert "mean_auc" in metrics

        # Predict at a date after the training events.
        result = labeler.predict(
            synthetic_ohlcv,
            as_of=synthetic_ohlcv.index[180],
            primary_side=1,
            primary_confidence=0.7,
        )
        assert result.model_available is True
        assert 0.0 <= result.probability <= 1.0
        assert 0.0 <= result.bet_size <= 1.0
        # Feature values should be populated.
        assert len(result.feature_values) == len(META_FEATURE_COLS)

    def test_no_look_ahead_in_predict(
        self, synthetic_ohlcv: pd.DataFrame,
    ) -> None:
        """Predict at T with truncated data (<=T) must equal predict on full data."""
        event_dates = synthetic_ohlcv.index[30:150:5]
        sides = [1 if i % 2 == 0 else -1 for i in range(len(event_dates))]
        events = pd.DataFrame({"side": sides}, index=event_dates)

        labeler = MetaLabeler(
            upper_barrier=0.03, lower_barrier=-0.03, vertical_barrier=5,
            min_train_samples=20, n_estimators=20, max_depth=3,
            n_splits=2, purge_gap=3, embargo=3,
        )
        labeler.fit(synthetic_ohlcv, events)

        cutoff = synthetic_ohlcv.index[160]
        full_result = labeler.predict(
            synthetic_ohlcv, as_of=cutoff,
            primary_side=1, primary_confidence=0.7,
        )
        trunc_df = synthetic_ohlcv.loc[:cutoff]
        trunc_result = labeler.predict(
            trunc_df, as_of=cutoff,
            primary_side=1, primary_confidence=0.7,
        )
        # Probabilities should be identical (features at cutoff use only <=T).
        assert pytest.approx(full_result.probability, abs=1e-6) == trunc_result.probability
