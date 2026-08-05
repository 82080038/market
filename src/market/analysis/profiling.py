"""Instrument Knowledge Profiler (pustaka/39, 84, 89, 91, 92).

Pre-screening gate yang menilai seberapa baik aplikasi mengenal setiap instrumen
sebelum mengambil keputusan screening/selection. Setiap instrumen pasar modal
memiliki pola yang berbeda tergantung faktor yang mempengaruhinya.

Komponen:
- DataSufficiencyChecker: menentukan kebutuhan durasi & jumlah data minimum
  per instrumen berdasarkan strategy type dan asset class.
- InstrumentProfiler: memprofil kepribadian instrumen (volatility regime,
  trend bias, beta vs IHSG, liquidity, personality label).
- FactorRelevanceMapper: memetakan faktor mana yang paling relevan untuk
  instrumen ini (sektor, komoditas linkage, asset class).
- PatternKnowledgeAssessor: menilai pengetahuan pola historis per instrumen.
- ModelPerformanceTracker: melacak performa model per instrumen dan
  rekomendasi auto-adjustment.
- InstrumentReadinessGate: menggabungkan semua menjadi readiness score;
  hanya instrumen yang siap (ready) yang dilewatkan ke screening/decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import ClassVar

import numpy as np
import pandas as pd

from market.analysis.extras import PatternMemory

# ---------------------------------------------------------------------------
# Enums & Constants
# ---------------------------------------------------------------------------


class StrategyType(Enum):
    """Strategy types with different data duration requirements."""

    SCALPING = "scalping"
    DAY_TRADING = "day_trading"
    SWING = "swing"
    MOMENTUM = "momentum"
    POSITION = "position"
    VALUE = "value"
    DIVIDEND = "dividend"


class VolatilityRegime(Enum):
    """Volatility classification for an instrument."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class PersonalityLabel(Enum):
    """Instrument personality classification."""

    BLUE_CHIP = "blue_chip"
    MID_CAP = "mid_cap"
    SMALL_CAP = "small_cap"
    GORENGAN = "gorengan"
    ILLIQUID = "illiquid"
    HIGH_BETA = "high_beta"
    LOW_BETA = "low_beta"
    DIVIDEND_STOCK = "dividend_stock"
    COMMODITY_LINKED = "commodity_linked"
    UNKNOWN = "unknown"


class ReadinessLevel(Enum):
    """Readiness classification for the screening gate."""

    READY = "ready"
    CONDITIONAL = "conditional"
    NOT_READY = "not_ready"
    INSUFFICIENT_DATA = "insufficient_data"


# Minimum data bars required per strategy type (daily bars)
STRATEGY_MIN_BARS: dict[StrategyType, int] = {
    StrategyType.SCALPING: 60,
    StrategyType.DAY_TRADING: 120,
    StrategyType.SWING: 200,
    StrategyType.MOMENTUM: 252,
    StrategyType.POSITION: 504,
    StrategyType.VALUE: 756,
    StrategyType.DIVIDEND: 1008,
}

# Minimum data bars per asset class (baseline)
ASSET_CLASS_MIN_BARS: dict[str, int] = {
    "equity": 252,
    "etf": 252,
    "bond": 365,
    "commodity": 365,
    "forex": 252,
    "crypto": 365,
    "derivative": 120,
}

# Sector → factor relevance weights override
# Sectors that are commodity-dependent get higher global/relationship weights
SECTOR_FACTOR_OVERRIDES: dict[str, dict[str, float]] = {
    "energy": {
        "technical": 0.20, "fundamental": 0.20,
        "macro": 0.15, "global": 0.20,
        "relationship": 0.15, "sentiment": 0.10,
    },
    "materials": {
        "technical": 0.20, "fundamental": 0.20,
        "macro": 0.15, "global": 0.20,
        "relationship": 0.15, "sentiment": 0.10,
    },
    "consumer_staples": {
        "technical": 0.20, "fundamental": 0.35,
        "macro": 0.10, "global": 0.05,
        "relationship": 0.05, "sentiment": 0.25,
    },
    "consumer_discretionary": {
        "technical": 0.25, "fundamental": 0.25,
        "macro": 0.15, "global": 0.10,
        "relationship": 0.05, "sentiment": 0.20,
    },
    "financials": {
        "technical": 0.20, "fundamental": 0.30,
        "macro": 0.25, "global": 0.10,
        "relationship": 0.05, "sentiment": 0.10,
    },
    "healthcare": {
        "technical": 0.25, "fundamental": 0.35,
        "macro": 0.10, "global": 0.05,
        "relationship": 0.05, "sentiment": 0.20,
    },
    "technology": {
        "technical": 0.30, "fundamental": 0.25,
        "macro": 0.10, "global": 0.15,
        "relationship": 0.05, "sentiment": 0.15,
    },
    "industrials": {
        "technical": 0.25, "fundamental": 0.25,
        "macro": 0.20, "global": 0.10,
        "relationship": 0.10, "sentiment": 0.10,
    },
    "utilities": {
        "technical": 0.15, "fundamental": 0.35,
        "macro": 0.20, "global": 0.05,
        "relationship": 0.05, "sentiment": 0.20,
    },
    "real_estate": {
        "technical": 0.25, "fundamental": 0.30,
        "macro": 0.20, "global": 0.05,
        "relationship": 0.05, "sentiment": 0.15,
    },
    "communication_services": {
        "technical": 0.25, "fundamental": 0.25,
        "macro": 0.10, "global": 0.10,
        "relationship": 0.05, "sentiment": 0.25,
    },
}

# Commodity-linked tickers on IDX (pustaka/91)
COMMODITY_TICKERS: dict[str, str] = {
    "AALI": "cpo", "LSIP": "cpo", "SIMP": "cpo", "DSNG": "cpo",
    "GZCO": "cpo", "BWPT": "cpo", "SGRO": "cpo", "SMAR": "cpo",
    "ADRO": "coal", "PTBA": "coal", "ITMG": "coal", "BUKA": "coal",
    "HRUM": "coal", "BSSR": "coal", "PKPK": "coal", "SSMR": "coal",
    "INCO": "nickel", "ANTM": "gold", "MDKA": "nickel",
    "PSAB": "tin", "TINS": "tin",
    "MEDC": "oil", "ENRG": "oil", "RUIS": "oil",
    "EMTK": "gold", "ZINC": "zinc",
}


# ---------------------------------------------------------------------------
# 1. Data Sufficiency Checker
# ---------------------------------------------------------------------------


@dataclass
class DataSufficiencyResult:
    """Result of data sufficiency check."""

    ticker: str
    bars_available: int
    bars_required: int
    duration_days: int
    duration_required_days: int
    coverage_pct: float
    gap_count: int
    max_gap_days: int
    is_sufficient: bool
    data_quality_score: float
    reasons: list[str] = field(default_factory=list)


class DataSufficiencyChecker:
    """Checks if an instrument has enough historical data for screening.

    Different strategies and asset classes require different amounts of
    historical data. This checker enforces minimums and reports gaps.
    """

    def __init__(
        self,
        strategy: StrategyType = StrategyType.SWING,
        asset_class: str = "equity",
        custom_min_bars: int | None = None,
    ) -> None:
        self.strategy = strategy
        self.asset_class = asset_class
        self.min_bars = custom_min_bars or max(
            STRATEGY_MIN_BARS.get(strategy, 200),
            ASSET_CLASS_MIN_BARS.get(asset_class, 252),
        )
        # Approximate calendar days needed (bars / ~0.69 trading ratio)
        self.min_days = int(self.min_bars / 0.69)

    def check(self, ticker: str, df: pd.DataFrame) -> DataSufficiencyResult:
        """Check data sufficiency for a ticker.

        Args:
            ticker: Instrument ticker symbol.
            df: OHLCV DataFrame with datetime index.

        Returns:
            DataSufficiencyResult with details.
        """
        if df.empty:
            return DataSufficiencyResult(
                ticker=ticker,
                bars_available=0,
                bars_required=self.min_bars,
                duration_days=0,
                duration_required_days=self.min_days,
                coverage_pct=0.0,
                gap_count=0,
                max_gap_days=0,
                is_sufficient=False,
                data_quality_score=0.0,
                reasons=["No data available."],
            )

        bars = len(df)
        index = df.index

        # Duration in calendar days
        if hasattr(index, "min") and hasattr(index, "max"):
            duration = (index.max() - index.min()).days
        else:
            duration = bars

        # Gap detection
        if hasattr(index, "to_series"):
            dates = index.to_series()
        else:
            dates = pd.Series(pd.to_datetime(index))

        date_diffs = dates.diff().dt.days.dropna()
        gap_threshold = 5  # days
        gaps = date_diffs[date_diffs > gap_threshold]
        gap_count = len(gaps)
        max_gap = int(gaps.max()) if len(gaps) > 0 else 0

        # Coverage: actual bars vs expected bars in duration
        expected_bars = int(duration * 0.69) if duration > 0 else bars
        coverage = min(100.0, (bars / expected_bars * 100)) if expected_bars > 0 else 0.0

        # Data quality score
        quality = self._compute_quality(df, bars, coverage, gap_count, max_gap)

        reasons: list[str] = []
        is_sufficient = True

        if bars < self.min_bars:
            is_sufficient = False
            reasons.append(
                f"Insufficient bars: {bars}/{self.min_bars} required "
                f"for {self.strategy.value} strategy.",
            )

        if duration < self.min_days:
            is_sufficient = False
            reasons.append(
                f"Insufficient duration: {duration}/{self.min_days} days required.",
            )

        if gap_count > 10:
            is_sufficient = False
            reasons.append(f"Too many data gaps: {gap_count} gaps > 5 days.")

        if max_gap > 30:
            is_sufficient = False
            reasons.append(f"Max gap too large: {max_gap} days.")

        if quality < 50.0:
            is_sufficient = False
            reasons.append(f"Data quality score too low: {quality:.1f}/100.")

        if is_sufficient:
            reasons.append(
                f"Data sufficient: {bars} bars over {duration} days, "
                f"quality {quality:.1f}/100.",
            )

        return DataSufficiencyResult(
            ticker=ticker,
            bars_available=bars,
            bars_required=self.min_bars,
            duration_days=duration,
            duration_required_days=self.min_days,
            coverage_pct=round(coverage, 2),
            gap_count=gap_count,
            max_gap_days=max_gap,
            is_sufficient=is_sufficient,
            data_quality_score=round(quality, 2),
            reasons=reasons,
        )

    def _compute_quality(
        self,
        df: pd.DataFrame,
        bars: int,
        coverage: float,
        gap_count: int,
        max_gap: int,
    ) -> float:
        """Compute a data quality score (0-100)."""
        score = 100.0

        # Coverage penalty
        if coverage < 80:
            score -= (80 - coverage) * 0.5

        # Gap penalty
        score -= min(20, gap_count * 2)
        score -= min(15, max(0, max_gap - 5) * 1.5)

        # Null check
        required_cols = {"open", "high", "low", "close", "volume"}
        available = required_cols & set(df.columns)
        if available:
            null_pct = df[list(available)].isnull().sum().sum() / (
                bars * len(available)
            ) * 100
            score -= min(20, null_pct * 2)

        # Price sanity: close should be positive
        if "close" in df.columns:
            non_positive = (df["close"] <= 0).sum()
            if bars > 0:
                score -= min(15, (non_positive / bars * 100) * 3)

        return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# 2. Instrument Profiler
# ---------------------------------------------------------------------------


@dataclass
class InstrumentProfile:
    """Profile of an instrument's trading characteristics."""

    ticker: str
    volatility_regime: VolatilityRegime
    trend_bias: str  # uptrend, downtrend, sideways
    beta_vs_ihsg: float
    liquidity_score: float  # 0-100
    avg_daily_volume: float
    avg_daily_volatility_pct: float
    personality_labels: list[PersonalityLabel]
    sector: str | None = None
    commodity_linkage: str | None = None
    profiled_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


class InstrumentProfiler:
    """Profiles an instrument's personality from OHLCV data.

    Determines volatility regime, trend bias, beta vs IHSG,
    liquidity, and personality labels.
    """

    def __init__(self, gorengan_threshold: float = 0.08) -> None:
        self.gorengan_threshold = gorengan_threshold

    def profile(
        self,
        ticker: str,
        df: pd.DataFrame,
        ihsg_df: pd.DataFrame | None = None,
        sector: str | None = None,
        market_cap: float | None = None,
    ) -> InstrumentProfile:
        """Profile an instrument from its OHLCV data.

        Args:
            ticker: Instrument ticker.
            df: OHLCV DataFrame.
            ihsg_df: IHSG index DataFrame for beta calculation.
            sector: Sector classification (e.g., "energy", "financials").
            market_cap: Market capitalization in IDR.

        Returns:
            InstrumentProfile with all characteristics.
        """
        if df.empty or len(df) < 20:
            return InstrumentProfile(
                ticker=ticker,
                volatility_regime=VolatilityRegime.LOW,
                trend_bias="unknown",
                beta_vs_ihsg=0.0,
                liquidity_score=0.0,
                avg_daily_volume=0.0,
                avg_daily_volatility_pct=0.0,
                personality_labels=[PersonalityLabel.UNKNOWN],
                sector=sector,
            )

        close = df["close"].astype(float)
        volume = (
            df["volume"].astype(float)
            if "volume" in df.columns
            else pd.Series(0.0, index=df.index)
        )

        # Volatility
        returns = close.pct_change(fill_method=None).dropna()
        avg_vol = float(returns.std() * 100) if len(returns) > 1 else 0.0
        vol_regime = self._classify_volatility(avg_vol)

        # Trend bias
        if len(close) >= 50:
            ma20 = close.rolling(20).mean().iloc[-1]
            ma50 = close.rolling(50).mean().iloc[-1]
            last = float(close.iloc[-1])
            if ma20 > ma50 and last > ma20:
                trend = "uptrend"
            elif ma20 < ma50 and last < ma20:
                trend = "downtrend"
            else:
                trend = "sideways"
        else:
            trend = "unknown"

        # Beta vs IHSG
        beta = 0.0
        if ihsg_df is not None and not ihsg_df.empty and len(ihsg_df) >= 20:
            beta = self._compute_beta(close, ihsg_df["close"].astype(float))

        # Liquidity
        adv = float(volume.tail(20).mean()) if len(volume) >= 20 else float(volume.mean())
        liquidity = self._compute_liquidity(adv, market_cap)

        # Personality labels
        labels = self._classify_personality(
            avg_vol, beta, liquidity, adv, market_cap, ticker, sector,
        )

        # Commodity linkage
        commodity = COMMODITY_TICKERS.get(ticker.replace(".JK", ""))

        return InstrumentProfile(
            ticker=ticker,
            volatility_regime=vol_regime,
            trend_bias=trend,
            beta_vs_ihsg=round(beta, 4),
            liquidity_score=round(liquidity, 2),
            avg_daily_volume=round(adv, 0),
            avg_daily_volatility_pct=round(avg_vol, 4),
            personality_labels=labels,
            sector=sector,
            commodity_linkage=commodity,
        )

    def _classify_volatility(self, avg_vol_pct: float) -> VolatilityRegime:
        if avg_vol_pct < 1.5:
            return VolatilityRegime.LOW
        if avg_vol_pct < 3.0:
            return VolatilityRegime.MEDIUM
        if avg_vol_pct < 5.0:
            return VolatilityRegime.HIGH
        return VolatilityRegime.EXTREME

    def _compute_beta(self, stock: pd.Series, index: pd.Series) -> float:
        """Compute beta of stock vs index."""
        stock_ret = stock.pct_change(fill_method=None).dropna()
        index_ret = index.pct_change(fill_method=None).dropna()

        # Align
        aligned = pd.concat([stock_ret, index_ret], axis=1, join="inner").dropna()
        if len(aligned) < 20:
            return 0.0

        cov = float(aligned.iloc[:, 0].cov(aligned.iloc[:, 1]))
        var = float(aligned.iloc[:, 1].var())
        return cov / var if var > 0 else 0.0

    def _compute_liquidity(
        self, adv: float, market_cap: float | None,
    ) -> float:
        """Compute liquidity score 0-100."""
        score = 0.0
        # Volume-based (0-60 points)
        if adv >= 10_000_000:
            score += 60
        elif adv >= 1_000_000:
            score += 40
        elif adv >= 100_000:
            score += 20
        elif adv >= 10_000:
            score += 10

        # Market cap-based (0-40 points)
        if market_cap is not None:
            if market_cap >= 10_000_000_000_000:  # 10T IDR
                score += 40
            elif market_cap >= 1_000_000_000_000:  # 1T IDR
                score += 30
            elif market_cap >= 100_000_000_000:  # 100B IDR
                score += 20
            elif market_cap >= 10_000_000_000:  # 10B IDR
                score += 10
        else:
            score += 20  # default if no market cap

        return min(100.0, score)

    def _classify_personality(
        self,
        avg_vol: float,
        beta: float,
        liquidity: float,
        adv: float,
        market_cap: float | None,
        ticker: str,
        sector: str | None,
    ) -> list[PersonalityLabel]:
        labels: list[PersonalityLabel] = []

        # Blue chip: high liquidity, low volatility, large cap
        if liquidity >= 55 and avg_vol < 3.0 and market_cap and market_cap >= 1_000_000_000_000:
            labels.append(PersonalityLabel.BLUE_CHIP)

        # Mid cap
        if market_cap and 100_000_000_000 <= market_cap < 1_000_000_000_000:
            labels.append(PersonalityLabel.MID_CAP)

        # Small cap
        if market_cap and market_cap < 100_000_000_000:
            labels.append(PersonalityLabel.SMALL_CAP)

        # Gorengan: high volatility + low liquidity
        if avg_vol > self.gorengan_threshold * 100 and liquidity < 30:
            labels.append(PersonalityLabel.GORENGAN)

        # Illiquid
        if liquidity < 20:
            labels.append(PersonalityLabel.ILLIQUID)

        # High beta
        if beta > 1.3:
            labels.append(PersonalityLabel.HIGH_BETA)

        # Low beta
        if 0 <= beta < 0.7:
            labels.append(PersonalityLabel.LOW_BETA)

        # Commodity linked
        clean_ticker = ticker.replace(".JK", "")
        if clean_ticker in COMMODITY_TICKERS:
            labels.append(PersonalityLabel.COMMODITY_LINKED)

        if not labels:
            labels.append(PersonalityLabel.UNKNOWN)

        return labels


# ---------------------------------------------------------------------------
# 3. Factor Relevance Mapper
# ---------------------------------------------------------------------------


@dataclass
class FactorRelevance:
    """Factor relevance mapping for an instrument."""

    ticker: str
    weights: dict[str, float]
    primary_factors: list[str]
    secondary_factors: list[str]
    rationale: list[str]


class FactorRelevanceMapper:
    """Maps which factors are most relevant for a specific instrument.

    Different instruments are influenced by different factors:
    - Commodity stocks → global market + relationship (commodity prices)
    - Banking stocks → macro (interest rates)
    - Consumer stocks → fundamental + sentiment
    - Small cap / gorengan → technical + sentiment
    """

    DEFAULT_WEIGHTS: ClassVar[dict[str, float]] = {
        "technical": 0.20,
        "fundamental": 0.25,
        "macro": 0.10,
        "global": 0.10,
        "relationship": 0.10,
        "sentiment": 0.25,
    }

    def map_factors(
        self,
        ticker: str,
        profile: InstrumentProfile,
        asset_class: str = "equity",
    ) -> FactorRelevance:
        """Map factor relevance for an instrument.

        Args:
            ticker: Instrument ticker.
            profile: Instrument profile from InstrumentProfiler.
            asset_class: Asset class string.

        Returns:
            FactorRelevance with adjusted weights and rationale.
        """
        # Start with defaults
        weights = self.DEFAULT_WEIGHTS.copy()
        rationale: list[str] = []
        primary: list[str] = []
        secondary: list[str] = []

        # 1. Sector-based overrides
        if profile.sector and profile.sector in SECTOR_FACTOR_OVERRIDES:
            weights = SECTOR_FACTOR_OVERRIDES[profile.sector].copy()
            rationale.append(
                f"Sector '{profile.sector}' overrides: "
                f"emphasizes {self._top_factors(weights, 2)}.",
            )

        # 2. Commodity linkage → boost global + relationship
        if profile.commodity_linkage:
            weights["global"] = weights.get("global", 0.10) + 0.05
            weights["relationship"] = weights.get("relationship", 0.10) + 0.05
            weights["fundamental"] = max(0.10, weights.get("fundamental", 0.25) - 0.05)
            weights["sentiment"] = max(0.05, weights.get("sentiment", 0.25) - 0.05)
            rationale.append(
                f"Commodity linkage to '{profile.commodity_linkage}': "
                f"boosted global & relationship factors.",
            )

        # 3. Gorengan → boost technical + sentiment, reduce fundamental
        if PersonalityLabel.GORENGAN in profile.personality_labels:
            weights["technical"] = weights.get("technical", 0.20) + 0.10
            weights["sentiment"] = weights.get("sentiment", 0.25) + 0.10
            weights["fundamental"] = max(0.05, weights.get("fundamental", 0.25) - 0.15)
            weights["macro"] = max(0.05, weights.get("macro", 0.10) - 0.05)
            rationale.append(
                "Gorengan detected: boosted technical & sentiment, "
                "reduced fundamental (unreliable for gorengan).",
            )

        # 4. Blue chip → boost fundamental, reduce sentiment
        if PersonalityLabel.BLUE_CHIP in profile.personality_labels:
            weights["fundamental"] = weights.get("fundamental", 0.25) + 0.05
            weights["sentiment"] = max(0.05, weights.get("sentiment", 0.25) - 0.05)
            rationale.append(
                "Blue chip: boosted fundamental (reliable earnings), "
                "reduced sentiment (less noise-driven).",
            )

        # 5. High beta → boost technical (momentum matters more)
        if PersonalityLabel.HIGH_BETA in profile.personality_labels:
            weights["technical"] = weights.get("technical", 0.20) + 0.05
            weights["macro"] = weights.get("macro", 0.10) + 0.05
            rationale.append(
                "High beta: boosted technical & macro "
                "(sensitive to market movements).",
            )

        # 6. Illiquid → boost technical, reduce sentiment (low participation)
        if PersonalityLabel.ILLIQUID in profile.personality_labels:
            weights["technical"] = weights.get("technical", 0.20) + 0.05
            weights["sentiment"] = max(0.05, weights.get("sentiment", 0.25) - 0.05)
            rationale.append(
                "Illiquid: boosted technical, reduced sentiment "
                "(low news/retail participation).",
            )

        # 7. Extreme volatility → boost macro + global (regime-driven)
        if profile.volatility_regime == VolatilityRegime.EXTREME:
            weights["macro"] = weights.get("macro", 0.10) + 0.05
            weights["global"] = weights.get("global", 0.10) + 0.05
            weights["technical"] = max(0.10, weights.get("technical", 0.20) - 0.05)
            rationale.append(
                "Extreme volatility: boosted macro & global "
                "(regime-driven, technical less reliable).",
            )

        # 8. Asset class adjustments (non-equity)
        if asset_class != "equity":
            from market.multi_asset import AssetClass
            from market.multi_asset.fundamental_scorer import DECISION_WEIGHTS

            ac_map = {e.value: e for e in AssetClass}
            ac_enum = ac_map.get(asset_class)
            if ac_enum and ac_enum in DECISION_WEIGHTS:
                ac_weights = DECISION_WEIGHTS[ac_enum]
                # Blend 50/50 with current weights
                for k in weights:
                    if k in ac_weights:
                        weights[k] = (weights[k] + ac_weights[k]) / 2
                rationale.append(
                    f"Asset class '{asset_class}' adjustment: "
                    f"blended with asset-class-specific weights.",
                )

        # Normalize
        total = sum(weights.values())
        if total > 0:
            weights = {k: round(v / total, 4) for k, v in weights.items()}

        # Classify primary/secondary
        sorted_factors = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        primary = [f for f, w in sorted_factors[:3] if w >= 0.15]
        secondary = [f for f, w in sorted_factors[3:] if w >= 0.05]

        return FactorRelevance(
            ticker=ticker,
            weights=weights,
            primary_factors=primary,
            secondary_factors=secondary,
            rationale=rationale,
        )

    @staticmethod
    def _top_factors(weights: dict[str, float], n: int) -> str:
        sorted_w = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        return ", ".join(f"{f} ({w:.0%})" for f, w in sorted_w[:n])


# ---------------------------------------------------------------------------
# 4. Pattern Knowledge Assessor
# ---------------------------------------------------------------------------


@dataclass
class PatternKnowledgeResult:
    """Assessment of pattern knowledge for an instrument."""

    ticker: str
    total_patterns: int
    evaluated_patterns: int
    confirmed_patterns: int
    failed_patterns: int
    reliability_score: float  # 0-100
    best_patterns: list[str]
    confidence_level: str  # high, medium, low, none
    knowledge_gaps: list[str]


class PatternKnowledgeAssessor:
    """Assesses how well the application knows patterns for an instrument.

    Uses PatternMemory to evaluate:
    - How many patterns have been observed
    - How many have been evaluated (confirmed/failed)
    - Which patterns are most reliable for this instrument
    - Confidence level in pattern-based predictions
    """

    def __init__(self, pattern_memory: PatternMemory | None = None) -> None:
        self.pattern_memory = pattern_memory or PatternMemory()

    def assess(self, ticker: str) -> PatternKnowledgeResult:
        """Assess pattern knowledge for a ticker.

        Args:
            ticker: Instrument ticker.

        Returns:
            PatternKnowledgeResult with knowledge assessment.
        """
        patterns = self.pattern_memory.get_patterns(ticker=ticker)
        total = len(patterns)

        evaluated = [
            p for p in patterns if p.outcome in ("confirmed", "failed")
        ]
        confirmed = sum(1 for p in evaluated if p.outcome == "confirmed")
        failed = sum(1 for p in evaluated if p.outcome == "failed")

        reliability = (confirmed / len(evaluated)) * 100 if evaluated else 0.0

        pattern_types: dict[str, list[str]] = {}
        for p in evaluated:
            pattern_types.setdefault(p.pattern_type, []).append(p.outcome)

        best_patterns: list[str] = []
        for ptype, outcomes in pattern_types.items():
            if len(outcomes) >= 3:
                conf = sum(1 for o in outcomes if o == "confirmed")
                rate = conf / len(outcomes)
                if rate >= 0.6:
                    best_patterns.append(
                        f"{ptype} ({rate:.0%}, n={len(outcomes)})",
                    )

        best_patterns.sort(reverse=True)

        # Confidence level
        if total >= 20 and reliability >= 65:
            confidence = "high"
        elif total >= 10 and reliability >= 50:
            confidence = "medium"
        elif total >= 5:
            confidence = "low"
        else:
            confidence = "none"

        # Knowledge gaps
        gaps: list[str] = []
        if total < 5:
            gaps.append(
                f"Very few patterns observed ({total}). "
                f"Need more historical pattern detection.",
            )
        if len(evaluated) < total * 0.5 and total > 0:
            gaps.append(
                f"Many patterns pending evaluation ({total - len(evaluated)}). "
                f"Need to wait for outcome periods.",
            )
        if reliability < 50 and len(evaluated) >= 5:
            gaps.append(
                f"Low pattern reliability ({reliability:.1f}%). "
                f"Patterns may not be predictive for this instrument.",
            )
        if not best_patterns and len(evaluated) >= 5:
            gaps.append(
                "No high-reliability patterns identified yet. "
                "Need more observations per pattern type.",
            )

        return PatternKnowledgeResult(
            ticker=ticker,
            total_patterns=total,
            evaluated_patterns=len(evaluated),
            confirmed_patterns=confirmed,
            failed_patterns=failed,
            reliability_score=round(reliability, 2),
            best_patterns=best_patterns[:5],
            confidence_level=confidence,
            knowledge_gaps=gaps,
        )


# ---------------------------------------------------------------------------
# 5. Model Performance Tracker
# ---------------------------------------------------------------------------


@dataclass
class ModelPerformanceRecord:
    """A single model performance record for an instrument."""

    ticker: str
    model_id: str
    model_type: str
    sharpe_ratio: float
    mae: float
    directional_accuracy: float
    evaluated_at: str
    is_degraded: bool = False


@dataclass
class ModelPerformanceAssessment:
    """Assessment of model performance for an instrument."""

    ticker: str
    has_model: bool
    latest_sharpe: float
    latest_mae: float
    latest_directional_accuracy: float
    is_degraded: bool
    degradation_reasons: list[str]
    auto_adjustment: str | None
    recommendation: str


class ModelPerformanceTracker:
    """Tracks per-instrument model performance and auto-adjustment.

    Monitors:
    - Latest model performance metrics
    - Performance degradation detection
    - Auto-adjustment recommendations
    - Model retraining triggers
    """

    def __init__(
        self,
        degradation_sharpe_threshold: float = 0.5,
        degradation_accuracy_threshold: float = 55.0,
        baseline_window: int = 30,
    ) -> None:
        self.degradation_sharpe_threshold = degradation_sharpe_threshold
        self.degradation_accuracy_threshold = degradation_accuracy_threshold
        self.baseline_window = baseline_window
        self._records: dict[str, list[ModelPerformanceRecord]] = {}

    def record_performance(self, record: ModelPerformanceRecord) -> None:
        """Record a model performance entry for a ticker."""
        self._records.setdefault(record.ticker, []).append(record)

    def assess(self, ticker: str) -> ModelPerformanceAssessment:
        """Assess model performance for a ticker.

        Args:
            ticker: Instrument ticker.

        Returns:
            ModelPerformanceAssessment with degradation check and recommendation.
        """
        records = self._records.get(ticker, [])

        if not records:
            return ModelPerformanceAssessment(
                ticker=ticker,
                has_model=False,
                latest_sharpe=0.0,
                latest_mae=0.0,
                latest_directional_accuracy=0.0,
                is_degraded=False,
                degradation_reasons=["No model trained for this instrument."],
                auto_adjustment=None,
                recommendation="Train initial model with sufficient historical data.",
            )

        latest = records[-1]
        reasons: list[str] = []
        is_degraded = False

        # Check Sharpe degradation
        if latest.sharpe_ratio < self.degradation_sharpe_threshold:
            is_degraded = True
            reasons.append(
                f"Sharpe ratio {latest.sharpe_ratio:.3f} "
                f"< threshold {self.degradation_sharpe_threshold}.",
            )

        # Check directional accuracy
        if latest.directional_accuracy < self.degradation_accuracy_threshold:
            is_degraded = True
            reasons.append(
                f"Directional accuracy {latest.directional_accuracy:.1f}% "
                f"< threshold {self.degradation_accuracy_threshold}%.",
            )

        # Compare to baseline if enough records
        if len(records) >= 5:
            baseline = records[:max(3, len(records) // 3)]
            baseline_sharpe = np.mean([r.sharpe_ratio for r in baseline])
            if baseline_sharpe > 0 and latest.sharpe_ratio < baseline_sharpe * 0.7:
                is_degraded = True
                reasons.append(
                    f"Performance degraded from baseline: "
                    f"sharpe {latest.sharpe_ratio:.3f} vs baseline {baseline_sharpe:.3f}.",
                )

        # Auto-adjustment recommendation
        auto_adjust = None
        if is_degraded:
            if latest.directional_accuracy < 45:
                auto_adjust = "retrain"
            elif latest.sharpe_ratio < 0:
                auto_adjust = "reduce_position_size"
            else:
                auto_adjust = "adjust_hyperparameters"

        # Final recommendation
        if is_degraded:
            if auto_adjust == "retrain":
                rec = "Retrain model with recent data; current model is unreliable."
            elif auto_adjust == "reduce_position_size":
                rec = "Reduce position size until model performance recovers."
            else:
                rec = "Adjust model hyperparameters; performance is degrading."
        else:
            rec = "Model performing within acceptable parameters."

        return ModelPerformanceAssessment(
            ticker=ticker,
            has_model=True,
            latest_sharpe=round(latest.sharpe_ratio, 4),
            latest_mae=round(latest.mae, 6),
            latest_directional_accuracy=round(latest.directional_accuracy, 2),
            is_degraded=is_degraded,
            degradation_reasons=reasons,
            auto_adjustment=auto_adjust,
            recommendation=rec,
        )


# ---------------------------------------------------------------------------
# 6. Instrument Readiness Gate
# ---------------------------------------------------------------------------


@dataclass
class InstrumentReadinessReport:
    """Complete readiness report for an instrument.

    Combines data sufficiency, instrument profile, factor relevance,
    pattern knowledge, and model performance into a single readiness
    assessment.
    """

    ticker: str
    readiness_level: ReadinessLevel
    readiness_score: float  # 0-100
    data_sufficiency: DataSufficiencyResult | None = None
    profile: InstrumentProfile | None = None
    factor_relevance: FactorRelevance | None = None
    pattern_knowledge: PatternKnowledgeResult | None = None
    model_performance: ModelPerformanceAssessment | None = None
    summary: str = ""
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class InstrumentReadinessGate:
    """Pre-screening gate that assesses instrument readiness.

    Before the application makes instrument selection decisions, this gate
    evaluates whether the application has sufficient knowledge about each
    instrument. Only instruments with adequate readiness proceed to
    screening and decision-making.

    This ensures the application is aware of:
    - Data duration and quality sufficiency
    - Instrument-specific patterns and personality
    - Which factors are relevant for this instrument
    - Pattern knowledge and reliability
    - Model performance and auto-adjustment needs
    """

    def __init__(
        self,
        data_checker: DataSufficiencyChecker | None = None,
        profiler: InstrumentProfiler | None = None,
        factor_mapper: FactorRelevanceMapper | None = None,
        pattern_assessor: PatternKnowledgeAssessor | None = None,
        model_tracker: ModelPerformanceTracker | None = None,
        min_readiness_score: float = 50.0,
    ) -> None:
        self.data_checker = data_checker or DataSufficiencyChecker()
        self.profiler = profiler or InstrumentProfiler()
        self.factor_mapper = factor_mapper or FactorRelevanceMapper()
        self.pattern_assessor = pattern_assessor or PatternKnowledgeAssessor()
        self.model_tracker = model_tracker or ModelPerformanceTracker()
        self.min_readiness_score = min_readiness_score

    def evaluate(
        self,
        ticker: str,
        df: pd.DataFrame,
        ihsg_df: pd.DataFrame | None = None,
        sector: str | None = None,
        market_cap: float | None = None,
        asset_class: str = "equity",
    ) -> InstrumentReadinessReport:
        """Evaluate readiness for a single instrument.

        Args:
            ticker: Instrument ticker.
            df: OHLCV DataFrame.
            ihsg_df: IHSG index DataFrame for beta calculation.
            sector: Sector classification.
            market_cap: Market capitalization in IDR.
            asset_class: Asset class string.

        Returns:
            InstrumentReadinessReport with full assessment.
        """
        blockers: list[str] = []
        warnings: list[str] = []
        recommendations: list[str] = []

        # 1. Data sufficiency
        data_result = self.data_checker.check(ticker, df)
        if not data_result.is_sufficient:
            blockers.extend(data_result.reasons)

        # 2. Instrument profile
        profile = self.profiler.profile(
            ticker, df, ihsg_df, sector, market_cap,
        )
        if PersonalityLabel.UNKNOWN in profile.personality_labels:
            warnings.append(
                "Instrument personality unknown — profile may be incomplete.",
            )
        if PersonalityLabel.GORENGAN in profile.personality_labels:
            warnings.append(
                "Gorengan detected — high risk, exercise extreme caution.",
            )
        if profile.volatility_regime == VolatilityRegime.EXTREME:
            warnings.append(
                "Extreme volatility — position sizing must be conservative.",
            )

        # 3. Factor relevance
        factor_rel = self.factor_mapper.map_factors(ticker, profile, asset_class)

        # 4. Pattern knowledge
        pattern_knowledge = self.pattern_assessor.assess(ticker)
        if pattern_knowledge.confidence_level == "none":
            warnings.append(
                "No pattern knowledge — application has not observed "
                "enough patterns for this instrument.",
            )
        elif pattern_knowledge.confidence_level == "low":
            warnings.append(
                "Low pattern confidence — more historical observation needed.",
            )
        recommendations.extend(pattern_knowledge.knowledge_gaps)

        # 5. Model performance
        model_perf = self.model_tracker.assess(ticker)
        if model_perf.is_degraded:
            warnings.append(f"Model degraded: {'; '.join(model_perf.degradation_reasons)}")
        if model_perf.auto_adjustment:
            recommendations.append(
                f"Auto-adjustment: {model_perf.auto_adjustment} — "
                f"{model_perf.recommendation}",
            )

        # 6. Compute readiness score
        score = self._compute_readiness_score(
            data_result, profile, pattern_knowledge, model_perf,
        )

        # 7. Determine readiness level
        if data_result.bars_available < 50:
            level = ReadinessLevel.INSUFFICIENT_DATA
        elif score >= self.min_readiness_score and not blockers:
            level = ReadinessLevel.READY
        elif score >= self.min_readiness_score * 0.7 and len(blockers) <= 1:
            level = ReadinessLevel.CONDITIONAL
        else:
            level = ReadinessLevel.NOT_READY

        # 8. Summary
        summary = self._generate_summary(
            ticker, level, score, data_result, profile,
            pattern_knowledge, model_perf,
        )

        return InstrumentReadinessReport(
            ticker=ticker,
            readiness_level=level,
            readiness_score=round(score, 2),
            data_sufficiency=data_result,
            profile=profile,
            factor_relevance=factor_rel,
            pattern_knowledge=pattern_knowledge,
            model_performance=model_perf,
            summary=summary,
            blockers=blockers,
            warnings=warnings,
            recommendations=recommendations,
        )

    def evaluate_batch(
        self,
        instruments: dict[str, pd.DataFrame],
        ihsg_df: pd.DataFrame | None = None,
        sectors: dict[str, str] | None = None,
        market_caps: dict[str, float] | None = None,
        asset_classes: dict[str, str] | None = None,
    ) -> dict[str, InstrumentReadinessReport]:
        """Evaluate readiness for multiple instruments.

        Args:
            instruments: Dict of ticker → OHLCV DataFrame.
            ihsg_df: IHSG index DataFrame.
            sectors: Dict of ticker → sector.
            market_caps: Dict of ticker → market cap.
            asset_classes: Dict of ticker → asset class.

        Returns:
            Dict of ticker → InstrumentReadinessReport.
            Only instruments with readiness_level READY or CONDITIONAL
            should proceed to screening.
        """
        results: dict[str, InstrumentReadinessReport] = {}
        for ticker, df in instruments.items():
            sector = sectors.get(ticker) if sectors else None
            mcap = market_caps.get(ticker) if market_caps else None
            ac = asset_classes.get(ticker, "equity") if asset_classes else "equity"
            results[ticker] = self.evaluate(
                ticker, df, ihsg_df, sector, mcap, ac,
            )
        return results

    def filter_ready(
        self,
        reports: dict[str, InstrumentReadinessReport],
        include_conditional: bool = True,
    ) -> list[str]:
        """Filter tickers that are ready for screening.

        Args:
            reports: Dict from evaluate_batch.
            include_conditional: Whether to include CONDITIONAL instruments.

        Returns:
            List of ticker symbols ready for screening.
        """
        ready_levels = {ReadinessLevel.READY}
        if include_conditional:
            ready_levels.add(ReadinessLevel.CONDITIONAL)

        return [
            ticker for ticker, report in reports.items()
            if report.readiness_level in ready_levels
        ]

    def _compute_readiness_score(
        self,
        data: DataSufficiencyResult,
        profile: InstrumentProfile,
        patterns: PatternKnowledgeResult,
        model: ModelPerformanceAssessment,
    ) -> float:
        """Compute overall readiness score (0-100).

        Weights:
        - Data sufficiency: 35%
        - Instrument profile clarity: 20%
        - Pattern knowledge: 25%
        - Model performance: 20%
        """
        # Data sufficiency score
        if data.is_sufficient:
            data_score = min(100, 60 + data.data_quality_score * 0.4)
        else:
            bars_ratio = data.bars_available / data.bars_required if data.bars_required > 0 else 0
            data_score = bars_ratio * 50

        # Profile clarity score
        if PersonalityLabel.UNKNOWN in profile.personality_labels:
            profile_score = 20.0
        else:
            profile_score = 80.0
            # Bonus for well-defined profile
            if profile.beta_vs_ihsg > 0:
                profile_score += 10
            if profile.sector:
                profile_score += 10
            profile_score = min(100, profile_score)

        # Pattern knowledge score
        pattern_score = 0.0
        if patterns.total_patterns > 0:
            pattern_score = min(
                100,
                patterns.reliability_score * 0.5
                + min(50, patterns.total_patterns * 2.5),
            )

        # Model performance score
        if not model.has_model:
            model_score = 25.0  # neutral — can still screen without ML
        elif model.is_degraded:
            model_score = 30.0
        else:
            model_score = min(
                100,
                50 + model.latest_directional_accuracy * 0.5,
            )

        total = (
            data_score * 0.35
            + profile_score * 0.20
            + pattern_score * 0.25
            + model_score * 0.20
        )

        return max(0.0, min(100.0, total))

    def _generate_summary(
        self,
        ticker: str,
        level: ReadinessLevel,
        score: float,
        data: DataSufficiencyResult,
        profile: InstrumentProfile,
        patterns: PatternKnowledgeResult,
        model: ModelPerformanceAssessment,
    ) -> str:
        """Generate a human-readable readiness summary."""
        parts: list[str] = []
        parts.append(f"{ticker}: {level.value.upper()} (score {score:.1f}/100).")
        parts.append(
            f"Data: {data.bars_available}/{data.bars_required} bars, "
            f"quality {data.data_quality_score:.0f}.",
        )
        parts.append(
            f"Profile: {profile.volatility_regime.value} volatility, "
            f"{profile.trend_bias} trend, beta {profile.beta_vs_ihsg:.2f}, "
            f"liquidity {profile.liquidity_score:.0f}.",
        )
        labels = ", ".join(lbl.value for lbl in profile.personality_labels)
        parts.append(f"Personality: {labels}.")
        parts.append(
            f"Patterns: {patterns.total_patterns} observed, "
            f"{patterns.reliability_score:.0f}% reliability, "
            f"confidence={patterns.confidence_level}.",
        )
        if model.has_model:
            parts.append(
                f"Model: sharpe {model.latest_sharpe:.2f}, "
                f"accuracy {model.latest_directional_accuracy:.0f}%, "
                f"{'DEGRADED' if model.is_degraded else 'OK'}.",
            )
        else:
            parts.append("Model: not trained.")

        return " ".join(parts)
