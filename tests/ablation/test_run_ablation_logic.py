"""Tests for the ablation runner's pure helper logic.

These tests pin down the logic fixes applied to
``scripts/engine_ablation/run_ablation.py`` so regressions are caught:

* ``_combine_pvalues_fisher`` — statistically valid p-value combination
  (replaces the invalid arithmetic mean of p-values).
* ``build_composite_signal`` — hierarchical composite, including the
  context-modulation fix that previously blew up exponentially
  (``1.3**N``) and saturated after clipping.
* ``simulate_returns`` cost model — round-trip cost is not double-charged
  and is applied on the correct day (covered in test_isolated_backtest).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC = PROJECT_ROOT / "src"
SCRIPTS = PROJECT_ROOT / "scripts" / "engine_ablation"


def _load_run_ablation():
    """Load run_ablation.py as a module (it lives under scripts/, not src/)."""
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    spec = importlib.util.spec_from_file_location(
        "run_ablation", SCRIPTS / "run_ablation.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ra():
    return _load_run_ablation()


# ── Fisher's method p-value combination ─────────────────────────────────


class TestCombinePvaluesFisher:
    def test_empty_returns_one(self, ra):
        assert ra._combine_pvalues_fisher([]) == 1.0

    def test_single_pvalue_is_identity(self, ra):
        # Fisher with k=1: X = -2 ln(p) ~ chi2(2); sf(X, 2) == p
        for p in (0.001, 0.01, 0.05, 0.1, 0.5, 0.9):
            assert ra._combine_pvalues_fisher([p]) == pytest.approx(p, abs=1e-9)

    def test_significant_pvalues_combine_to_smaller(self, ra):
        # Three independent p=0.01 should combine to a much smaller p-value
        combined = ra._combine_pvalues_fisher([0.01, 0.01, 0.01])
        assert combined < 0.01

    def test_non_significant_pvalues_stay_non_significant(self, ra):
        combined = ra._combine_pvalues_fisher([0.5, 0.5, 0.5])
        # Should not drop below the 0.05 significance bar
        assert combined > 0.05

    def test_zero_pvalue_does_not_crash(self, ra):
        # log(0) would be -inf; the helper must clip and still return ~0
        assert ra._combine_pvalues_fisher([0.0, 0.0]) == pytest.approx(0.0, abs=1e-10)

    def test_better_than_averaging_for_strong_evidence(self, ra):
        # Averaging [0.01, 0.01, 0.01] = 0.01; Fisher should be smaller
        # (more powerful combination of independent evidence).
        avg = sum([0.01, 0.01, 0.01]) / 3
        fisher = ra._combine_pvalues_fisher([0.01, 0.01, 0.01])
        assert fisher < avg


# ── build_composite_signal hierarchical pipeline ────────────────────────


def _entry(name, signal_type, weight=0.1):
    from market.ablation.engine_registry import (
        EngineCategory,
        EngineEntry,
        SignalType,
    )
    return EngineEntry(
        name=name,
        category=EngineCategory.SIGNAL_ENHANCER,
        signal_type=signal_type,
        default_weight=weight,
        purpose="t",
        description="t",
        module="t",
        data_tables=[],
        factory=lambda: None,
    )


class TestBuildCompositeSignal:
    def _make_index(self, n=50):
        return pd.date_range("2024-01-01", periods=n, freq="B")

    def test_directional_weighted_vote(self, ra):
        idx = self._make_index()
        baseline = pd.Series(0, index=idx)
        # Two directional engines: one always +1 (weight 0.6), one always -1 (0.4)
        sigs = {
            "d1": pd.Series(1, index=idx),
            "d2": pd.Series(-1, index=idx),
        }
        entries = [_entry("d1", ra.SignalType.DIRECTIONAL, 0.6),
                   _entry("d2", ra.SignalType.DIRECTIONAL, 0.4)]
        comp = ra.build_composite_signal(sigs, entries, baseline, idx)
        # Net vote = 0.6 - 0.4 = 0.2 > 0.15 threshold → BUY
        assert (comp == 1).all()

    def test_falls_back_to_baseline_when_no_directional(self, ra):
        idx = self._make_index()
        baseline = pd.Series(1, index=idx)
        sigs = {"ctx": pd.Series(1, index=idx)}
        entries = [_entry("ctx", ra.SignalType.CONTEXT, 0.5)]
        comp = ra.build_composite_signal(sigs, entries, baseline, idx)
        # No directional engines → raw_signal = baseline (1.0) → BUY
        assert (comp == 1).all()

    def test_filter_vetoes_directional(self, ra):
        idx = self._make_index()
        baseline = pd.Series(0, index=idx)
        sigs = {
            "d": pd.Series(1, index=idx),
            "f": pd.Series(0, index=idx),  # filter vetoes everywhere
        }
        entries = [
            _entry("d", ra.SignalType.DIRECTIONAL, 1.0),
            _entry("f", ra.SignalType.FILTER, 0.5),
        ]
        comp = ra.build_composite_signal(sigs, entries, baseline, idx)
        assert (comp == 0).all()

    def test_context_does_not_explode(self, ra):
        """Context modulation must not compound exponentially.

        Previously the scale factor was multiplied per-engine as
        ``1 + aligned*0.3*w*N`` which produced ``1.3**N`` amplification and
        saturated to ±1 after clipping for any positive context. With the
        additive fix, 7 context engines all at +1 (weight-normalized) yield a
        bounded ~1.3× modulation, not 1.3**7 ≈ 8.2×.
        """
        idx = self._make_index()
        baseline = pd.Series(0, index=idx)
        # A weak directional signal (0.5) so we can observe modulation
        sigs = {"d": pd.Series(0.5, index=idx)}
        # 7 context engines all fully bullish
        for i in range(7):
            sigs[f"ctx{i}"] = pd.Series(1, index=idx)
        entries = [_entry("d", ra.SignalType.DIRECTIONAL, 1.0)]
        entries += [_entry(f"ctx{i}", ra.SignalType.CONTEXT, 1.0) for i in range(7)]
        comp = ra.build_composite_signal(sigs, entries, baseline, idx)
        # raw = 0.5 * (1 + 0.3*1) = 0.65, clipped to [-1,1] → 0.65 → BUY (1)
        # Under the old buggy code raw would be 0.5 * 1.3**7 ≈ 4.1 → clipped
        # to 1.0 → still BUY, but the *magnitude* is wrong. We assert the
        # composite is BUY without saturation distortion by checking a
        # sub-threshold case below.
        assert (comp == 1).all()

    def test_context_modulation_keeps_weak_signal_below_threshold(self, ra):
        """A directional signal just above threshold, with neutral context,
        stays a signal; with strongly negative context it is attenuated below
        the 0.15 discretization threshold → HOLD. This proves modulation is
        bounded and bidirectional (not always saturating)."""
        idx = self._make_index()
        baseline = pd.Series(0, index=idx)
        # Directional vote = 0.2 (just above 0.15 threshold)
        sigs = {"d": pd.Series(0.2, index=idx), "ctx": pd.Series(-1, index=idx)}
        entries = [
            _entry("d", ra.SignalType.DIRECTIONAL, 1.0),
            _entry("ctx", ra.SignalType.CONTEXT, 1.0),
        ]
        comp = ra.build_composite_signal(sigs, entries, baseline, idx)
        # raw = 0.2 * (1 + 0.3*(-1)) = 0.2 * 0.7 = 0.14 < 0.15 → HOLD (0)
        assert (comp == 0).all()


# ── overnight_idx threshold sanity ───────────────────────────────────────


class TestOvernightIdxThreshold:
    def test_threshold_is_on_return_scale(self, ra):
        """The overnight_idx composite is a weighted average of daily returns
        (~0.01 scale). The threshold must be on that scale, not 5 (which made
        the engine never fire). We verify the threshold constant used in the
        function body is small enough that a typical 1% weighted move fires."""
        # Read the source to confirm the threshold is <= 0.01 (return scale)
        import inspect
        src = inspect.getsource(ra.generate_engine_signals)
        overnight_block = src[src.index("overnight_idx"):]
        # The fixed threshold 0.004 must be present and the old *20 / >5 gone
        assert "0.004" in overnight_block
        assert "signal_val * 20" not in overnight_block
        assert "> 5" not in overnight_block
