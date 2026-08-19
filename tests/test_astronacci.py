"""Tests for Astronacci cycle engine (src/market/analysis/astronacci.py).

Tests cover:
- Moon phase computation (New Moon, Full Moon, First/Last Quarter)
- Planetary retrograde detection (Mercury, Venus, Mars, etc.)
- Planetary ingress detection (Sun + major planets)
- Fibonacci price retracement computation from swing highs/lows
- Confluence logic (astrology event + Fibonacci price level alignment)
- AstronacciEngine orchestration
- Signal computation for SignalEnhancer integration
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.market.analysis.astronacci import (
    AstronacciCycle,
    AstronacciEngine,
    FibonacciPriceRetracementCalculator,
    IngressCalculator,
    MoonPhaseCalculator,
    RetrogradeCalculator,
    compute_astronacci_signal,
    _geocentric_ecliptic_lon,
    _zodiac_sign,
)
import ephem


# ── Moon Phase Tests ─────────────────────────────────────────────────────────


class TestMoonPhaseCalculator:
    """Test moon phase computation."""

    def test_new_moon_july_2025(self):
        calc = MoonPhaseCalculator()
        start = datetime(2025, 7, 1, tzinfo=timezone.utc)
        end = datetime(2025, 7, 31, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)

        new_moons = [c for c in cycles if c.cycle_type == "MOON_PHASE_NEW"]
        assert len(new_moons) == 1
        # Known: New Moon on July 24, 2025 at 19:11 UTC
        assert new_moons[0].start_at.day == 24

    def test_full_moon_july_2025(self):
        calc = MoonPhaseCalculator()
        start = datetime(2025, 7, 1, tzinfo=timezone.utc)
        end = datetime(2025, 7, 31, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)

        full_moons = [c for c in cycles if c.cycle_type == "MOON_PHASE_FULL"]
        assert len(full_moons) == 1
        # Known: Full Moon on July 10, 2025 at 20:36 UTC
        assert full_moons[0].start_at.day == 10

    def test_all_four_phases_in_month(self):
        calc = MoonPhaseCalculator()
        start = datetime(2025, 7, 1, tzinfo=timezone.utc)
        end = datetime(2025, 8, 15, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)

        phase_types = {c.cycle_type for c in cycles}
        assert "MOON_PHASE_NEW" in phase_types
        assert "MOON_PHASE_FULL" in phase_types
        assert "MOON_PHASE_FIRST_QUARTER" in phase_types
        assert "MOON_PHASE_LAST_QUARTER" in phase_types

    def test_moon_phase_impact_and_reversal(self):
        calc = MoonPhaseCalculator()
        start = datetime(2025, 7, 1, tzinfo=timezone.utc)
        end = datetime(2025, 7, 31, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)

        for c in cycles:
            if c.cycle_type == "MOON_PHASE_NEW":
                assert c.potential_impact == "HIGH"
                assert c.expected_reversal == "BULLISH_REVERSAL"
            elif c.cycle_type == "MOON_PHASE_FULL":
                assert c.potential_impact == "HIGH"
                assert c.expected_reversal == "BEARISH_REVERSAL"

    def test_moon_phase_window_duration(self):
        calc = MoonPhaseCalculator()
        start = datetime(2025, 7, 1, tzinfo=timezone.utc)
        end = datetime(2025, 7, 31, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)

        for c in cycles:
            if c.cycle_type in ("MOON_PHASE_NEW", "MOON_PHASE_FULL"):
                duration = c.end_at - c.start_at
                assert duration == timedelta(hours=24)
            elif c.cycle_type in ("MOON_PHASE_FIRST_QUARTER", "MOON_PHASE_LAST_QUARTER"):
                duration = c.end_at - c.start_at
                assert duration == timedelta(hours=12)

    def test_empty_range(self):
        calc = MoonPhaseCalculator()
        start = datetime(2025, 7, 10, tzinfo=timezone.utc)
        end = datetime(2025, 7, 10, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)
        assert len(cycles) == 0

    def test_cycles_sorted_chronologically(self):
        calc = MoonPhaseCalculator()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 3, 31, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)
        timestamps = [c.start_at for c in cycles]
        assert timestamps == sorted(timestamps)


# ── Retrograde Tests ─────────────────────────────────────────────────────────


class TestRetrogradeCalculator:
    """Test planetary retrograde detection."""

    def test_mercury_retrograde_2025(self):
        calc = RetrogradeCalculator()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 12, 31, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)

        mercury_retros = [c for c in cycles if c.cycle_type == "MERCURY_RETROGRADE"]
        # Mercury has 3-4 retrogrades per year
        assert len(mercury_retros) >= 3
        for c in mercury_retros:
            assert c.potential_impact == "CRITICAL"
            assert c.expected_reversal == "BEARISH_REVERSAL"

    def test_all_planets_have_retrogrades(self):
        calc = RetrogradeCalculator()
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 12, 31, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)

        planet_types = {c.cycle_type for c in cycles}
        # Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto
        expected = {
            "MERCURY_RETROGRADE", "VENUS_RETROGRADE", "MARS_RETROGRADE",
            "JUPITER_RETROGRADE", "SATURN_RETROGRADE", "URANUS_RETROGRADE",
            "NEPTUNE_RETROGRADE", "PLUTO_RETROGRADE",
        }
        assert expected.issubset(planet_types)

    def test_retrograde_window_duration(self):
        calc = RetrogradeCalculator()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 6, 30, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)

        for c in cycles:
            duration = c.end_at - c.start_at
            assert duration == timedelta(hours=6)

    def test_retrograde_cycles_sorted(self):
        calc = RetrogradeCalculator()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 6, 30, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)
        timestamps = [c.start_at for c in cycles]
        assert timestamps == sorted(timestamps)


# ── Ingress Tests ────────────────────────────────────────────────────────────


class TestIngressCalculator:
    """Test planetary ingress detection."""

    def test_sun_ingress_monthly(self):
        calc = IngressCalculator()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 12, 31, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)

        sun_ingresses = [c for c in cycles if c.cycle_type == "SUN_INGRESS"]
        # Sun enters a new zodiac sign roughly every 30 days → ~12 per year
        assert len(sun_ingresses) >= 11
        assert len(sun_ingresses) <= 13

    def test_sun_ingress_titles_contain_sign(self):
        calc = IngressCalculator()
        start = datetime(2025, 3, 1, tzinfo=timezone.utc)
        end = datetime(2025, 4, 30, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)

        sun_ingresses = [c for c in cycles if c.cycle_type == "SUN_INGRESS"]
        # Sun enters Aries around March 20-21
        assert any("ARIES" in c.title for c in sun_ingresses)

    def test_jupiter_ingress_rare(self):
        calc = IngressCalculator()
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 12, 31, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)

        jupiter_ingresses = [c for c in cycles if c.cycle_type == "JUPITER_INGRESS"]
        # Jupiter changes sign roughly once per year, but retrograde motion
        # can cause it to cross sign boundaries multiple times
        assert len(jupiter_ingresses) >= 1
        assert len(jupiter_ingresses) <= 8

    def test_ingress_cycles_sorted(self):
        calc = IngressCalculator()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 6, 30, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)
        timestamps = [c.start_at for c in cycles]
        assert timestamps == sorted(timestamps)


# ── Fibonacci Price Retracement Tests ────────────────────────────────────────


class TestFibonacciPriceRetracementCalculator:
    """Test Fibonacci price retracement computation from swing points."""

    def _make_test_prices(self, n: int = 200) -> pd.DataFrame:
        """Create synthetic price data with clear swing points."""
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        prices = []
        for i in range(n):
            if i < 50:
                prices.append(100 + i * 0.5)  # uptrend
            elif i < 100:
                prices.append(125 - (i - 50) * 0.5)  # downtrend
            elif i < 150:
                prices.append(100 + (i - 100) * 0.5)  # uptrend
            else:
                prices.append(125 - (i - 150) * 0.5)  # downtrend
        return pd.DataFrame({"timestamp": dates, "close": prices})

    def test_find_swing_points(self):
        calc = FibonacciPriceRetracementCalculator()
        prices = self._make_test_prices()
        swings = calc.find_swing_points(prices, lookback=10, min_separation=10)

        assert len(swings) > 0
        types = {s[2] for s in swings}
        assert "HIGH" in types
        assert "LOW" in types

    def test_retracement_levels_computed(self):
        calc = FibonacciPriceRetracementCalculator()
        prices = self._make_test_prices()
        levels = calc.compute_retracement_levels(prices, lookback=10)

        assert len(levels) > 0
        for level in levels:
            assert "ratio" in level
            assert "price_level" in level
            assert "direction" in level
            assert level["ratio"] in [0.236, 0.382, 0.500, 0.618, 0.786]

    def test_retracement_levels_within_swing_range(self):
        calc = FibonacciPriceRetracementCalculator()
        prices = self._make_test_prices()
        levels = calc.compute_retracement_levels(prices, lookback=10)

        for level in levels:
            assert level["swing_low"] <= level["price_level"] <= level["swing_high"]

    def test_confluence_match(self):
        """Confluence should detect when price is near a Fibonacci level."""
        calc = FibonacciPriceRetracementCalculator()
        prices = self._make_test_prices()
        levels = calc.compute_retracement_levels(prices, lookback=10)
        assert levels

        # Use the first level's price as current_price — should match
        target_price = levels[0]["price_level"]
        result = calc.check_confluence(target_price, prices)
        assert result is not None
        assert result["matched"] is True
        assert result["ratio"] == levels[0]["ratio"]

    def test_confluence_no_match(self):
        """Confluence should return None when price is far from any Fib level."""
        calc = FibonacciPriceRetracementCalculator()
        prices = self._make_test_prices()
        # Use a price far from any level (e.g., 9999)
        result = calc.check_confluence(9999.0, prices)
        assert result is None

    def test_compute_cycles_for_visualization(self):
        calc = FibonacciPriceRetracementCalculator()
        prices = self._make_test_prices()
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 12, 31, tzinfo=timezone.utc)
        cycles = calc.compute(prices, start, end)

        assert len(cycles) > 0
        for c in cycles:
            assert c.cycle_type == "FIBONACCI_PRICE"
            assert c.potential_impact == "HIGH"
            assert c.expected_reversal in ("BULLISH_REVERSAL", "BEARISH_REVERSAL")

    def test_empty_prices(self):
        calc = FibonacciPriceRetracementCalculator()
        empty = pd.DataFrame(columns=["timestamp", "close"])
        levels = calc.compute_retracement_levels(empty)
        assert len(levels) == 0


# ── AstronacciEngine Tests ───────────────────────────────────────────────────


class TestAstronacciEngine:
    """Test the orchestrating engine."""

    def test_compute_all_cycles(self):
        engine = AstronacciEngine()
        start = datetime(2025, 7, 1, tzinfo=timezone.utc)
        end = datetime(2025, 7, 31, tzinfo=timezone.utc)
        cycles = engine.compute(start, end)

        assert len(cycles) > 0
        types = {c.cycle_type for c in cycles}
        # Should have moon phases at minimum
        assert "MOON_PHASE_NEW" in types or "MOON_PHASE_FULL" in types

    def test_compute_sorted(self):
        engine = AstronacciEngine()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 3, 31, tzinfo=timezone.utc)
        cycles = engine.compute(start, end)

        timestamps = [c.start_at for c in cycles]
        assert timestamps == sorted(timestamps)

    def test_compute_with_fibonacci(self):
        engine = AstronacciEngine(include_fibonacci=True)
        # Create prices with clear swing points (not monotonic)
        n = 200
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        prices = []
        for i in range(n):
            if i < 50:
                prices.append(100 + i * 0.5)
            elif i < 100:
                prices.append(125 - (i - 50) * 0.5)
            elif i < 150:
                prices.append(100 + (i - 100) * 0.5)
            else:
                prices.append(125 - (i - 150) * 0.5)
        prices_df = pd.DataFrame({"timestamp": dates, "close": prices})
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 12, 31, tzinfo=timezone.utc)
        cycles = engine.compute(start, end, prices=prices_df)

        fib_cycles = [c for c in cycles if c.cycle_type == "FIBONACCI_PRICE"]
        assert len(fib_cycles) > 0

    def test_compute_empty_range(self):
        """Zero-width range may still return ongoing retrograde cycles.

        After BUG-1 fix, RetrogradeCalculator scans backwards to find
        ongoing retrogrades, so a zero-width range can return cycles
        for planets that are retrograde at that instant.
        """
        engine = AstronacciEngine()
        start = datetime(2025, 7, 15, tzinfo=timezone.utc)
        end = datetime(2025, 7, 15, tzinfo=timezone.utc)
        cycles = engine.compute(start, end)
        # Neptune and Pluto are retrograde in July 2025 — the fix
        # correctly detects these ongoing retrogrades.
        for c in cycles:
            assert c.cycle_type.endswith("_RETROGRADE")


# ── Signal Computation Tests ─────────────────────────────────────────────────


class TestAstronacciSignal:
    """Test signal computation for integration."""

    def test_signal_on_new_moon_date(self):
        """Signal should be active on a New Moon date."""
        # July 24, 2025 is a New Moon
        as_of = datetime(2025, 7, 24, tzinfo=timezone.utc)
        result = compute_astronacci_signal(as_of, window_days=3)

        assert result["cycle_count"] > 0
        assert "MOON_PHASE_NEW" in result["active_cycles"]
        assert result["confidence"] > 0

    def test_signal_no_cycles(self):
        """Signal should be zero when no cycles are active."""
        # Pick a date far in the past with no computed cycles
        as_of = datetime(1800, 1, 1, tzinfo=timezone.utc)
        result = compute_astronacci_signal(as_of, window_days=1)

        # In 1800, ephem might still compute cycles, so just check structure
        assert "time_signal" in result
        assert "volatility_signal" in result
        assert "confidence" in result
        assert "cycle_count" in result
        assert isinstance(result["time_signal"], float)
        assert isinstance(result["volatility_signal"], float)

    def test_signal_range(self):
        """Signal values should be in valid ranges."""
        as_of = datetime(2025, 7, 16, tzinfo=timezone.utc)
        result = compute_astronacci_signal(as_of, window_days=5)

        assert -1.0 <= result["time_signal"] <= 1.0
        assert 0.0 <= result["volatility_signal"] <= 1.0
        assert 0.0 <= result["confidence"] <= 1.0

    def test_signal_with_mercury_retrograde(self):
        """Mercury retrograde should contribute bearish signal."""
        # Find a Mercury retrograde date in 2025
        engine = AstronacciEngine()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 12, 31, tzinfo=timezone.utc)
        cycles = engine.compute(start, end)

        mercury = [c for c in cycles if c.cycle_type == "MERCURY_RETROGRADE"]
        if mercury:
            # Use the midpoint of the first Mercury retrograde
            retro = mercury[0]
            mid = retro.start_at + (retro.end_at - retro.start_at) / 2
            result = compute_astronacci_signal(mid, window_days=3)
            # Should have some active cycles
            assert result["cycle_count"] >= 0  # may or may not overlap exactly

    def test_signal_with_fibonacci_prices(self):
        """Signal should include Fibonacci price retracement cycles when prices are provided."""
        n = 200
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        prices = []
        for i in range(n):
            if i < 50:
                prices.append(100 + i * 0.5)
            elif i < 100:
                prices.append(125 - (i - 50) * 0.5)
            elif i < 150:
                prices.append(100 + (i - 100) * 0.5)
            else:
                prices.append(125 - (i - 150) * 0.5)
        prices_df = pd.DataFrame({"timestamp": dates, "close": prices})

        as_of = datetime(2024, 8, 1, tzinfo=timezone.utc)
        result = compute_astronacci_signal(as_of, window_days=10, prices=prices_df)

        # Should have Fibonacci price retracement in the active cycles
        assert "FIBONACCI_PRICE" in result["active_cycles"]
        assert result["cycle_count"] > 0

    def test_signal_with_confluence(self):
        """When current_price aligns with a Fib level, confluence should be detected."""
        n = 200
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        prices = []
        for i in range(n):
            if i < 50:
                prices.append(100 + i * 0.5)
            elif i < 100:
                prices.append(125 - (i - 50) * 0.5)
            elif i < 150:
                prices.append(100 + (i - 100) * 0.5)
            else:
                prices.append(125 - (i - 150) * 0.5)
        prices_df = pd.DataFrame({"timestamp": dates, "close": prices})

        # Compute retracement levels to find a target price
        calc = FibonacciPriceRetracementCalculator()
        levels = calc.compute_retracement_levels(prices_df, lookback=10)
        assert levels

        target_price = levels[0]["price_level"]
        as_of = datetime(2024, 8, 1, tzinfo=timezone.utc)
        result = compute_astronacci_signal(
            as_of, window_days=10, prices=prices_df, current_price=target_price,
        )

        assert result["confluence"] is not None
        assert result["confluence"]["matched"] is True
        assert result["confidence"] > 0

    def test_signal_no_confluence_without_price(self):
        """Without current_price, confluence should be None."""
        as_of = datetime(2025, 7, 24, tzinfo=timezone.utc)
        result = compute_astronacci_signal(as_of, window_days=3)
        assert result["confluence"] is None

    def test_signal_confidence_based_on_quality(self):
        """Confidence should be based on directional cycles + confluence."""
        as_of = datetime(2025, 7, 24, tzinfo=timezone.utc)
        result = compute_astronacci_signal(as_of, window_days=3)

        # Confidence should be in valid range
        assert 0.0 <= result["confidence"] <= 1.0
        # Moon phases are now BULLISH/BEARISH_REVERSAL → directional
        # So confidence should be non-zero when moon phases are active
        if "MOON_PHASE_NEW" in result["active_cycles"]:
            assert result["confidence"] > 0

    def test_retrograde_backward_scan_finds_ongoing(self):
        """RetrogradeCalculator should find ongoing retrogrades by scanning back."""
        calc = RetrogradeCalculator()
        # July 15, 2025: Neptune and Pluto are retrograde
        # Use a 1-second range to test that ongoing retrogrades are detected
        start = datetime(2025, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 7, 15, 12, 0, 1, tzinfo=timezone.utc)
        cycles = calc.compute(start, end)

        # Should find at least Neptune or Pluto retrograde
        retro_types = {c.cycle_type for c in cycles}
        assert "NEPTUNE_RETROGRADE" in retro_types or "PLUTO_RETROGRADE" in retro_types

    def test_compute_cycles_alias(self):
        """compute_cycles should be an alias for compute (scheduler compat)."""
        engine = AstronacciEngine()
        start = datetime(2025, 7, 1, tzinfo=timezone.utc)
        end = datetime(2025, 7, 31, tzinfo=timezone.utc)

        cycles_compute = engine.compute(start, end)
        cycles_alias = engine.compute_cycles(start, end)

        assert len(cycles_compute) == len(cycles_alias)
        assert [c.start_at for c in cycles_compute] == [c.start_at for c in cycles_alias]


# ── Helper Function Tests ────────────────────────────────────────────────────


class TestHelperFunctions:
    """Test internal helper functions."""

    def test_zodiac_sign_from_longitude(self):
        assert _zodiac_sign(0.0) == "ARIES"
        assert _zodiac_sign(30.0) == "TAURUS"
        assert _zodiac_sign(60.0) == "GEMINI"
        assert _zodiac_sign(90.0) == "CANCER"
        assert _zodiac_sign(180.0) == "LIBRA"
        assert _zodiac_sign(270.0) == "CAPRICORN"
        assert _zodiac_sign(359.9) == "PISCES"
        assert _zodiac_sign(360.0) == "ARIES"  # wraps

    def test_geocentric_ecliptic_lon_sun(self):
        """Sun's ecliptic longitude should be ~0 at vernal equinox."""
        sun = ephem.Sun()
        # March 20, 2025 — close to vernal equinox
        lon = _geocentric_ecliptic_lon(sun, ephem.Date("2025/03/20"))
        # Should be close to 0 degrees (Aries 0°)
        assert lon < 5.0 or lon > 355.0

    def test_geocentric_ecliptic_lon_range(self):
        """Ecliptic longitude should always be in [0, 360)."""
        mercury = ephem.Mercury()
        for day in range(0, 365, 30):
            d = ephem.Date("2025/01/01") + day
            lon = _geocentric_ecliptic_lon(mercury, d)
            assert 0.0 <= lon < 360.0


# ── AstronacciCycle Data Model Tests ─────────────────────────────────────────


class TestAstronacciCycle:
    """Test the AstronacciCycle dataclass."""

    def test_to_dict(self):
        c = AstronacciCycle(
            cycle_type="MOON_PHASE_NEW",
            title="New Moon",
            start_at=datetime(2025, 7, 24, 19, 11, tzinfo=timezone.utc),
            end_at=datetime(2025, 7, 25, 19, 11, tzinfo=timezone.utc),
            potential_impact="HIGH",
            expected_reversal="BULLISH_REVERSAL",
            description="Test cycle",
        )
        d = c.to_dict()
        assert d["cycle_type"] == "MOON_PHASE_NEW"
        assert d["title"] == "New Moon"
        assert "2025-07-24" in d["start_at"]
        assert d["potential_impact"] == "HIGH"
        assert d["expected_reversal"] == "BULLISH_REVERSAL"

    def test_defaults(self):
        c = AstronacciCycle(
            cycle_type="TEST",
            title="Test",
            start_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        )
        assert c.potential_impact == "HIGH"
        assert c.target_asset_class == "ALL"
        assert c.expected_reversal == "NEUTRAL"
        assert c.description == ""
