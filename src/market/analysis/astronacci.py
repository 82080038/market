"""Astronacci Cycle Engine — Financial Astrology & Time Cycle integration.

Implements the Astronacci methodology (Astrology + Fibonacci) developed by
Gema Goeyardi / Astronacci International. Three core astrological elements
act as "WHEN" indicators — time triggers for potential market reversal windows:

1. **Moon Phase** — New Moon, First Quarter, Full Moon, Last Quarter.
   Indicator of market psychology/sensitivity shifts. Research shows ~78-79%
   reversal probability during New Moon and Full Moon phases (Goeyardi, 2026).

2. **Planetary Retrograde** — Mercury, Venus, Mars, Jupiter, Saturn, Uranus,
   Neptune, Pluto. Momentum slowdown, false breakouts, market evaluation phase.

3. **Planetary Ingress** — Planet moving from one zodiac constellation to
   another. Market character reset, new cycle phase initiation.

Additionally, **Fibonacci Time Windows** are computed from significant price
highs/lows to identify time-based reversal zones.

Framework:
    Astrology = Time reference (WHEN)
    Fibonacci = Structure validation (WHERE)
    Price action = Final confirmation

Sources:
    - Goeyardi, G. (2021). "Financial analysis method based on astrology,
      Fibonacci, and Astronacci." IJEBR Vol.22 No.2/3.
    - astronacci.com/blog/read/astrologi-trading-time-trigger-market-cycle
    - financialadviser.ph (March 2026 STA Philippines summit coverage)

Note: Astronacci cycles are time indicators, NOT directional predictions.
They identify WHEN market behavior may change, not WHICH direction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import ephem
import pandas as pd


# ── Constants ────────────────────────────────────────────────────────────────

ZODIAC_SIGNS = [
    "ARIES", "TAURUS", "GEMINI", "CANCER", "LEO", "VIRGO",
    "LIBRA", "SCORPIO", "SAGITTARIUS", "CAPRICORN", "AQUARIUS", "PISCES",
]

FIBONACCI_SEQUENCE = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610]

# Planets tracked for retrograde and ingress
PLANETARY_BODIES = {
    "MERCURY": ephem.Mercury,
    "VENUS": ephem.Venus,
    "MARS": ephem.Mars,
    "JUPITER": ephem.Jupiter,
    "SATURN": ephem.Saturn,
    "URANUS": ephem.Uranus,
    "NEPTUNE": ephem.Neptune,
    "PLUTO": ephem.Pluto,
}

# Sun ingress is the most significant for monthly cycle tracking
SUN_BODY = {"SUN": ephem.Sun}

# Impact levels per cycle type
DEFAULT_IMPACT = {
    "MOON_PHASE_NEW": "HIGH",
    "MOON_PHASE_FULL": "HIGH",
    "MOON_PHASE_FIRST_QUARTER": "MEDIUM",
    "MOON_PHASE_LAST_QUARTER": "MEDIUM",
    "MERCURY_RETROGRADE": "CRITICAL",
    "VENUS_RETROGRADE": "HIGH",
    "MARS_RETROGRADE": "HIGH",
    "JUPITER_RETROGRADE": "MEDIUM",
    "SATURN_RETROGRADE": "MEDIUM",
    "URANUS_RETROGRADE": "MEDIUM",
    "NEPTUNE_RETROGRADE": "LOW",
    "PLUTO_RETROGRADE": "LOW",
    "SUN_INGRESS": "MEDIUM",
    "MERCURY_INGRESS": "LOW",
    "VENUS_INGRESS": "LOW",
    "MARS_INGRESS": "MEDIUM",
    "JUPITER_INGRESS": "HIGH",
    "SATURN_INGRESS": "HIGH",
    "URANUS_INGRESS": "HIGH",
    "NEPTUNE_INGRESS": "MEDIUM",
    "PLUTO_INGRESS": "MEDIUM",
    "FIBONACCI_TIME": "HIGH",
}

# Expected reversal type per cycle type
DEFAULT_REVERSAL = {
    "MOON_PHASE_NEW": "VOLATILITY",
    "MOON_PHASE_FULL": "VOLATILITY",
    "MOON_PHASE_FIRST_QUARTER": "NEUTRAL",
    "MOON_PHASE_LAST_QUARTER": "NEUTRAL",
    "MERCURY_RETROGRADE": "BEARISH_REVERSAL",
    "VENUS_RETROGRADE": "BEARISH_REVERSAL",
    "MARS_RETROGRADE": "VOLATILITY",
    "JUPITER_RETROGRADE": "NEUTRAL",
    "SATURN_RETROGRADE": "NEUTRAL",
    "URANUS_RETROGRADE": "VOLATILITY",
    "NEPTUNE_RETROGRADE": "NEUTRAL",
    "PLUTO_RETROGRADE": "NEUTRAL",
    "SUN_INGRESS": "NEUTRAL",
    "MERCURY_INGRESS": "NEUTRAL",
    "VENUS_INGRESS": "NEUTRAL",
    "MARS_INGRESS": "VOLATILITY",
    "JUPITER_INGRESS": "VOLATILITY",
    "SATURN_INGRESS": "VOLATILITY",
    "URANUS_INGRESS": "VOLATILITY",
    "NEPTUNE_INGRESS": "NEUTRAL",
    "PLUTO_INGRESS": "NEUTRAL",
    "FIBONACCI_TIME": "VOLATILITY",
}

# Window duration (hours) for each cycle type — the event spans this many hours
WINDOW_HOURS = {
    "MOON_PHASE_NEW": 24,
    "MOON_PHASE_FULL": 24,
    "MOON_PHASE_FIRST_QUARTER": 12,
    "MOON_PHASE_LAST_QUARTER": 12,
    "MERCURY_RETROGRADE": 6,   # peak window within the retrograde period
    "VENUS_RETROGRADE": 6,
    "MARS_RETROGRADE": 6,
    "JUPITER_RETROGRADE": 6,
    "SATURN_RETROGRADE": 6,
    "URANUS_RETROGRADE": 6,
    "NEPTUNE_RETROGRADE": 6,
    "PLUTO_RETROGRADE": 6,
    "SUN_INGRESS": 12,
    "MERCURY_INGRESS": 6,
    "VENUS_INGRESS": 6,
    "MARS_INGRESS": 12,
    "JUPITER_INGRESS": 24,
    "SATURN_INGRESS": 24,
    "URANUS_INGRESS": 24,
    "NEPTUNE_INGRESS": 24,
    "PLUTO_INGRESS": 24,
    "FIBONACCI_TIME": 24,
}


# ── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class AstronacciCycle:
    """A single Astronacci time-cycle event."""
    cycle_type: str
    title: str
    start_at: datetime
    end_at: datetime
    potential_impact: str = "HIGH"
    target_asset_class: str = "ALL"
    expected_reversal: str = "NEUTRAL"
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "cycle_type": self.cycle_type,
            "title": self.title,
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
            "potential_impact": self.potential_impact,
            "target_asset_class": self.target_asset_class,
            "expected_reversal": self.expected_reversal,
            "description": self.description,
        }


# ── Helper Functions ─────────────────────────────────────────────────────────

_OBLIQUITY = math.radians(23.44)


def _geocentric_ecliptic_lon(body: ephem.Body, date: ephem.Date) -> float:
    """Compute geocentric ecliptic longitude in degrees [0, 360)."""
    body.compute(date)
    ra = float(body.ra)
    dec = float(body.dec)
    lon = math.atan2(
        math.sin(ra) * math.cos(_OBLIQUITY) - math.tan(dec) * math.sin(_OBLIQUITY),
        math.cos(ra),
    )
    return math.degrees(lon) % 360


def _zodiac_sign(lon_deg: float) -> str:
    """Return zodiac sign name for a given ecliptic longitude."""
    idx = int(lon_deg // 30) % 12
    return ZODIAC_SIGNS[idx]


def _ephem_to_datetime(d: ephem.Date) -> datetime:
    """Convert ephem.Date to timezone-aware UTC datetime."""
    dt = d.datetime()
    return dt.replace(tzinfo=timezone.utc)


# ── Moon Phase Calculator ────────────────────────────────────────────────────

class MoonPhaseCalculator:
    """Computes all moon phase events in a date range.

    Moon phases (New Moon, First Quarter, Full Moon, Last Quarter) occur
    approximately every 7.38 days (synodic month 29.53 / 4).
    """

    PHASE_FUNCS = {
        "MOON_PHASE_NEW": ephem.next_new_moon,
        "MOON_PHASE_FULL": ephem.next_full_moon,
        "MOON_PHASE_FIRST_QUARTER": ephem.next_first_quarter_moon,
        "MOON_PHASE_LAST_QUARTER": ephem.next_last_quarter_moon,
    }

    PHASE_TITLES = {
        "MOON_PHASE_NEW": "New Moon",
        "MOON_PHASE_FULL": "Full Moon",
        "MOON_PHASE_FIRST_QUARTER": "First Quarter Moon",
        "MOON_PHASE_LAST_QUARTER": "Last Quarter Moon",
    }

    PHASE_DESCRIPTIONS = {
        "MOON_PHASE_NEW": (
            "New Moon phase — historically associated with ~78-79% market "
            "reversal probability (Goeyardi 2026). Window of increased "
            "volatility and potential directional shift."
        ),
        "MOON_PHASE_FULL": (
            "Full Moon phase — historically associated with ~78-79% market "
            "reversal probability (Goeyardi 2026). Market sensitivity "
            "peaks; potential for emotional trading extremes."
        ),
        "MOON_PHASE_FIRST_QUARTER": (
            "First Quarter Moon — transitional phase. Market may show "
            "increased indecision or continuation of trend established "
            "at New Moon."
        ),
        "MOON_PHASE_LAST_QUARTER": (
            "Last Quarter Moon — transitional phase. Market may show "
            "preparation for the upcoming New/Full Moon reversal window."
        ),
    }

    def compute(self, start: datetime, end: datetime) -> list[AstronacciCycle]:
        cycles: list[AstronacciCycle] = []
        start_ephem = ephem.Date(start.replace(tzinfo=None))
        end_ephem = ephem.Date(end.replace(tzinfo=None))

        for phase_type, func in self.PHASE_FUNCS.items():
            d = start_ephem
            while True:
                try:
                    phase_date = func(d)
                except ephem.AlwaysUpError:
                    break
                if phase_date >= end_ephem:
                    break
                dt = _ephem_to_datetime(phase_date)
                window_h = WINDOW_HOURS[phase_type]
                cycles.append(AstronacciCycle(
                    cycle_type=phase_type,
                    title=self.PHASE_TITLES[phase_type],
                    start_at=dt,
                    end_at=dt + timedelta(hours=window_h),
                    potential_impact=DEFAULT_IMPACT[phase_type],
                    expected_reversal=DEFAULT_REVERSAL[phase_type],
                    description=self.PHASE_DESCRIPTIONS[phase_type],
                ))
                d = phase_date + 0.01  # advance slightly past current
        cycles.sort(key=lambda c: c.start_at)
        return cycles


# ── Retrograde Calculator ────────────────────────────────────────────────────

class RetrogradeCalculator:
    """Computes planetary retrograde periods by scanning geocentric
    ecliptic longitude day-by-day.

    A planet is retrograde when its geocentric ecliptic longitude decreases
    from one day to the next (apparent backward motion).
    """

    RETRO_TITLES = {
        "MERCURY": "Mercury Retrograde",
        "VENUS": "Venus Retrograde",
        "MARS": "Mars Retrograde",
        "JUPITER": "Jupiter Retrograde",
        "SATURN": "Saturn Retrograde",
        "URANUS": "Uranus Retrograde",
        "NEPTUNE": "Neptune Retrograde",
        "PLUTO": "Pluto Retrograde",
    }

    RETRO_DESCRIPTIONS = {
        "MERCURY": (
            "Mercury Retrograde — momentum trend melambat, false breakout "
            "meningkat, market memasuki mode evaluasi. Sektor komunikasi/tech "
            "paling terdampak. Reversal besar sering terjadi saat momentum "
            "melemah, bukan saat market kuat."
        ),
        "VENUS": (
            "Venus Retrograde — evaluasi nilai dan sentimen market. "
            "Sektor finansial/konsumer terdampak. Potensi reversal "
            "dalam tren nilai."
        ),
        "MARS": (
            "Mars Retrograde — energi market menurun, agresivitas berkurang. "
            "Volatilitas tinggi dengan momentum lemah."
        ),
        "JUPITER": (
            "Jupiter Retrograde — fase konsolidasi besar. Ekspansi market "
            "melambat, evaluasi pertumbuhan."
        ),
        "SATURN": (
            "Saturn Retrograde — fase restrukturisasi. Market mengkonsolidasi "
            "struktur dan mengevaluasi fondasi."
        ),
        "URANUS": (
            "Uranus Retrograde — volatilitas tak terduga. Potensi shock "
            "market atau perubahan mendadak."
        ),
        "NEPTUNE": (
            "Neptune Retrograde — ilusi market terkoreksi. Sentimen vs "
            "realitas divergen."
        ),
        "PLUTO": (
            "Pluto Retrograde — transformasi struktural mendalam. "
            "Perubahan fundamental market."
        ),
    }

    def compute(self, start: datetime, end: datetime) -> list[AstronacciCycle]:
        cycles: list[AstronacciCycle] = []
        start_ephem = ephem.Date(start.replace(tzinfo=None))
        end_ephem = ephem.Date(end.replace(tzinfo=None))

        for planet_name, body_class in PLANETARY_BODIES.items():
            body = body_class()
            d = ephem.Date(start_ephem)
            prev_lon = _geocentric_ecliptic_lon(body, d)
            d = ephem.Date(d + 1)  # move to next day
            retro_start: ephem.Date | None = None

            while d < end_ephem:
                curr_lon = _geocentric_ecliptic_lon(body, d)
                is_retro = curr_lon < prev_lon

                if is_retro and retro_start is None:
                    retro_start = ephem.Date(d - 1)  # retrograde began previous day
                elif not is_retro and retro_start is not None:
                    # Retrograde ended
                    cycle_key = f"{planet_name}_RETROGRADE"
                    start_dt = _ephem_to_datetime(retro_start)
                    end_dt = _ephem_to_datetime(d)
                    # Use the midpoint as the "peak" event time
                    peak_dt = start_dt + (end_dt - start_dt) / 2
                    window_h = WINDOW_HOURS.get(cycle_key, 6)
                    cycles.append(AstronacciCycle(
                        cycle_type=cycle_key,
                        title=self.RETRO_TITLES[planet_name],
                        start_at=peak_dt - timedelta(hours=window_h / 2),
                        end_at=peak_dt + timedelta(hours=window_h / 2),
                        potential_impact=DEFAULT_IMPACT.get(cycle_key, "MEDIUM"),
                        expected_reversal=DEFAULT_REVERSAL.get(cycle_key, "NEUTRAL"),
                        description=self.RETRO_DESCRIPTIONS[planet_name],
                    ))
                    retro_start = None

                prev_lon = curr_lon
                d = ephem.Date(d + 1)

            # Handle retrograde that extends past end date
            if retro_start is not None:
                cycle_key = f"{planet_name}_RETROGRADE"
                start_dt = _ephem_to_datetime(retro_start)
                end_dt = _ephem_to_datetime(end_ephem)
                peak_dt = start_dt + (end_dt - start_dt) / 2
                window_h = WINDOW_HOURS.get(cycle_key, 6)
                cycles.append(AstronacciCycle(
                    cycle_type=cycle_key,
                    title=self.RETRO_TITLES[planet_name],
                    start_at=peak_dt - timedelta(hours=window_h / 2),
                    end_at=peak_dt + timedelta(hours=window_h / 2),
                    potential_impact=DEFAULT_IMPACT.get(cycle_key, "MEDIUM"),
                    expected_reversal=DEFAULT_REVERSAL.get(cycle_key, "NEUTRAL"),
                    description=self.RETRO_DESCRIPTIONS[planet_name],
                ))

        cycles.sort(key=lambda c: c.start_at)
        return cycles


# ── Ingress Calculator ───────────────────────────────────────────────────────

class IngressCalculator:
    """Computes planetary ingress events (planet entering a new zodiac sign).

    Sun ingress (monthly) is the most significant. Major planet ingresses
    (Jupiter, Saturn, Uranus) mark larger cycle shifts.
    """

    INGRESS_DESCRIPTIONS = {
        "SUN": (
            "Sun ingress into {sign} — monthly cycle shift. Market "
            "character may reset; new psychological phase begins."
        ),
        "MERCURY": (
            "Mercury ingress into {sign} — communication/information "
            "flow shifts. Short-term sentiment change."
        ),
        "VENUS": (
            "Venus ingress into {sign} — value/sentiment shift. "
            "Consumer and financial sectors may be affected."
        ),
        "MARS": (
            "Mars ingress into {sign} — energy/aggression shift. "
            "Market momentum character changes."
        ),
        "JUPITER": (
            "Jupiter ingress into {sign} — major growth/expansion cycle "
            "shift. Annual-level market character change."
        ),
        "SATURN": (
            "Saturn ingress into {sign} — major structural cycle shift. "
            "2.5-year market phase transition."
        ),
        "URANUS": (
            "Uranus ingress into {sign} — disruption/innovation cycle "
            "shift. 7-year market phase transition."
        ),
        "NEPTUNE": (
            "Neptune ingress into {sign} — sentiment/illusion cycle "
            "shift. 14-year market phase transition."
        ),
        "PLUTO": (
            "Pluto ingress into {sign} — transformation/rebirth cycle "
            "shift. 20-year market phase transition."
        ),
    }

    # Which bodies to track for ingress (Sun + major planets)
    INGRESS_BODIES = {**SUN_BODY, **PLANETARY_BODIES}

    def compute(self, start: datetime, end: datetime) -> list[AstronacciCycle]:
        cycles: list[AstronacciCycle] = []
        start_ephem = ephem.Date(start.replace(tzinfo=None))
        end_ephem = ephem.Date(end.replace(tzinfo=None))

        for body_name, body_class in self.INGRESS_BODIES.items():
            body = body_class()
            d = ephem.Date(start_ephem)
            prev_sign = _zodiac_sign(_geocentric_ecliptic_lon(body, d))
            d = ephem.Date(d + 1)

            while d < end_ephem:
                curr_lon = _geocentric_ecliptic_lon(body, d)
                curr_sign = _zodiac_sign(curr_lon)

                if curr_sign != prev_sign:
                    cycle_key = f"{body_name}_INGRESS"
                    dt = _ephem_to_datetime(d)
                    window_h = WINDOW_HOURS.get(cycle_key, 12)
                    desc_template = self.INGRESS_DESCRIPTIONS.get(body_name, "")
                    cycles.append(AstronacciCycle(
                        cycle_type=cycle_key,
                        title=f"{body_name.title()} Ingress → {curr_sign}",
                        start_at=dt,
                        end_at=dt + timedelta(hours=window_h),
                        potential_impact=DEFAULT_IMPACT.get(cycle_key, "MEDIUM"),
                        expected_reversal=DEFAULT_REVERSAL.get(cycle_key, "NEUTRAL"),
                        description=desc_template.format(sign=curr_sign),
                    ))
                    prev_sign = curr_sign

                d = ephem.Date(d + 1)

        cycles.sort(key=lambda c: c.start_at)
        return cycles


# ── Fibonacci Time Window Calculator ─────────────────────────────────────────

class FibonacciTimeCalculator:
    """Computes Fibonacci time windows from significant price highs/lows.

    Uses the Fibonacci sequence (1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233...)
    applied as trading-day offsets from swing highs and lows to identify
    potential reversal time zones.
    """

    def __init__(self, fib_sequence: list[int] | None = None):
        self.fib_sequence = fib_sequence or FIBONACCI_SEQUENCE

    def find_swing_points(
        self,
        prices: pd.DataFrame,
        lookback: int = 20,
        min_separation: int = 30,
    ) -> list[tuple[pd.Timestamp, float, str]]:
        """Find swing highs and lows in price data.

        Args:
            prices: DataFrame with 'timestamp' and 'close' columns.
            lookback: bars on each side to confirm a swing point.
            min_separation: minimum bars between swing points of same type.

        Returns:
            List of (timestamp, price, type) tuples where type is 'HIGH' or 'LOW'.
        """
        if len(prices) < 2 * lookback + 1:
            return []

        closes = prices["close"].values
        timestamps = prices["timestamp"].values
        swing_points: list[tuple[pd.Timestamp, float, str]] = []

        last_high_idx = -min_separation
        last_low_idx = -min_separation

        for i in range(lookback, len(closes) - lookback):
            window = closes[i - lookback : i + lookback + 1]
            is_high = closes[i] == window.max()
            is_low = closes[i] == window.min()

            if is_high and (i - last_high_idx) >= min_separation:
                swing_points.append((pd.Timestamp(timestamps[i]), float(closes[i]), "HIGH"))
                last_high_idx = i
            elif is_low and (i - last_low_idx) >= min_separation:
                swing_points.append((pd.Timestamp(timestamps[i]), float(closes[i]), "LOW"))
                last_low_idx = i

        return swing_points

    def compute(
        self,
        prices: pd.DataFrame,
        start: datetime,
        end: datetime,
        lookback: int = 20,
    ) -> list[AstronacciCycle]:
        """Compute Fibonacci time windows from swing highs/lows.

        Args:
            prices: DataFrame with 'timestamp' and 'close' columns.
            start: Start of target date range.
            end: End of target date range.
            lookback: Bars on each side for swing detection.

        Returns:
            List of AstronacciCycle events for Fibonacci time windows.
        """
        swing_points = self.find_swing_points(prices, lookback=lookback)
        if not swing_points:
            return []

        # Build trading-day index for forward projection
        cycles: list[AstronacciCycle] = []
        start_utc = pd.Timestamp(start).tz_convert("UTC") if start.tzinfo else pd.Timestamp(start, tz="UTC")
        end_utc = pd.Timestamp(end).tz_convert("UTC") if end.tzinfo else pd.Timestamp(end, tz="UTC")

        for swing_ts, swing_price, swing_type in swing_points:
            # Ensure swing timestamp is tz-aware
            if swing_ts.tzinfo is None:
                swing_ts = swing_ts.tz_localize("UTC")
            for fib_n in self.fib_sequence:
                target_ts = swing_ts + pd.Timedelta(days=fib_n)
                if target_ts < start_utc or target_ts > end_utc:
                    continue
                direction = "BULLISH_REVERSAL" if swing_type == "LOW" else "BEARISH_REVERSAL"
                cycles.append(AstronacciCycle(
                    cycle_type="FIBONACCI_TIME",
                    title=f"Fibonacci +{fib_n}d from {swing_type} @ {swing_price:.2f}",
                    start_at=target_ts.to_pydatetime(),
                    end_at=(target_ts + pd.Timedelta(hours=24)).to_pydatetime(),
                    potential_impact=DEFAULT_IMPACT["FIBONACCI_TIME"],
                    expected_reversal=direction,
                    description=(
                        f"Fibonacci time window: {fib_n} trading days after "
                        f"swing {swing_type.lower()} at price {swing_price:.2f}. "
                        f"Potential reversal zone based on Fibonacci time ratio."
                    ),
                ))

        cycles.sort(key=lambda c: c.start_at)
        return cycles


# ── Astronacci Engine ────────────────────────────────────────────────────────

class AstronacciEngine:
    """Orchestrates all Astronacci cycle calculators.

    Computes moon phases, planetary retrogrades, planetary ingresses,
    and optionally Fibonacci time windows from price data.
    """

    def __init__(self, include_fibonacci: bool = False):
        self.moon_calc = MoonPhaseCalculator()
        self.retro_calc = RetrogradeCalculator()
        self.ingress_calc = IngressCalculator()
        self.fib_calc = FibonacciTimeCalculator() if include_fibonacci else None

    def compute(
        self,
        start: datetime,
        end: datetime,
        prices: pd.DataFrame | None = None,
    ) -> list[AstronacciCycle]:
        """Compute all Astronacci cycles in the given date range.

        Args:
            start: Start datetime (UTC).
            end: End datetime (UTC).
            prices: Optional price DataFrame for Fibonacci time windows.

        Returns:
            Sorted list of AstronacciCycle events.
        """
        cycles: list[AstronacciCycle] = []

        cycles.extend(self.moon_calc.compute(start, end))
        cycles.extend(self.retro_calc.compute(start, end))
        cycles.extend(self.ingress_calc.compute(start, end))

        if self.fib_calc and prices is not None and len(prices) > 0:
            cycles.extend(self.fib_calc.compute(prices, start, end))

        cycles.sort(key=lambda c: c.start_at)
        return cycles

    def compute_signal(self, as_of: datetime, window_days: int = 3) -> dict:
        """Compute an Astronacci time signal for a given date.

        This is the integration point for SignalEnhancer / MarketContext.
        Returns a signal dict with:
        - active_cycles: list of cycle types active within the window
        - time_signal: float in [-1, 1] (negative = bearish reversal risk,
          positive = bullish reversal opportunity, 0 = neutral)
        - volatility_signal: float in [0, 1] (higher = more expected volatility)
        - confidence: float in [0, 1]

        Args:
            as_of: The reference datetime (UTC).
            window_days: How many days forward to look for active cycles.

        Returns:
            Signal dictionary.
        """
        start = as_of - timedelta(days=1)
        end = as_of + timedelta(days=window_days)
        cycles = self.compute(start, end)

        if not cycles:
            return {
                "active_cycles": [],
                "time_signal": 0.0,
                "volatility_signal": 0.0,
                "confidence": 0.0,
                "cycle_count": 0,
            }

        time_signal = 0.0
        volatility_signal = 0.0
        active_types: list[str] = []

        for cycle in cycles:
            # Map expected_reversal to signal contribution
            reversal_map = {
                "BEARISH_REVERSAL": -0.3,
                "BULLISH_REVERSAL": 0.3,
                "VOLATILITY": 0.0,
                "NEUTRAL": 0.0,
            }
            impact_weight = {
                "CRITICAL": 1.0,
                "HIGH": 0.7,
                "MEDIUM": 0.4,
                "LOW": 0.2,
            }

            weight = impact_weight.get(cycle.potential_impact, 0.3)
            reversal_contrib = reversal_map.get(cycle.expected_reversal, 0.0)
            time_signal += reversal_contrib * weight

            if cycle.expected_reversal == "VOLATILITY":
                volatility_signal += weight * 0.5

            active_types.append(cycle.cycle_type)

        # Normalize
        n = len(cycles)
        time_signal = max(-1.0, min(1.0, time_signal / max(n, 1)))
        volatility_signal = min(1.0, volatility_signal / max(n, 1))
        confidence = min(1.0, n / 5.0)  # more active cycles = higher confidence

        return {
            "active_cycles": active_types,
            "time_signal": round(time_signal, 4),
            "volatility_signal": round(volatility_signal, 4),
            "confidence": round(confidence, 4),
            "cycle_count": n,
        }


def compute_astronacci_signal(as_of: datetime, window_days: int = 3) -> dict:
    """Convenience function to compute Astronacci signal for a given date.

    Args:
        as_of: Reference datetime (UTC).
        window_days: Forward look window in days.

    Returns:
        Signal dictionary with time_signal, volatility_signal, confidence.
    """
    engine = AstronacciEngine(include_fibonacci=False)
    return engine.compute_signal(as_of, window_days)
