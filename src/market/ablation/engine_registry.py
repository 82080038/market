"""Engine Registry — catalog of all signal engines for ablation testing.

Each engine is registered with metadata describing its PURPOSE, signal type,
data requirements, and the module that implements it. This ensures the ablation
framework correctly understands what each engine does and how to test it.

Signal Types:
    - DIRECTIONAL: Produces buy/sell signals (-1, 0, +1) based on analysis
    - TIMING: Produces time-window signals (when to act, not what direction)
    - FILTER: Filters/vetoes existing signals (reduces false positives)
    - SIZING: Adjusts bet size/confidence of existing signals
    - CONTEXT: Provides market context that modulates other signals

Categories:
    - SIGNAL_ENHANCER: 8 signals in SignalEnhancer pipeline
    - MARKET_CONTEXT: 7 context factors in MarketContext composite
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class EngineCategory(str, Enum):
    SIGNAL_ENHANCER = "signal_enhancer"
    MARKET_CONTEXT = "market_context"


class SignalType(str, Enum):
    DIRECTIONAL = "directional"    # Buy/sell signal based on analysis
    TIMING = "timing"              # When to act (time window), not direction
    FILTER = "filter"              # Veto/filter low-confidence signals
    SIZING = "sizing"              # Adjust bet size / confidence
    CONTEXT = "context"            # Market context that modulates other signals


@dataclass
class EngineEntry:
    """Registry entry for a single engine.

    Attributes:
        name: Unique engine identifier (matches SignalEnhancer/MarketContext key).
        category: Which pipeline this engine belongs to.
        signal_type: What kind of signal this engine produces.
        default_weight: Weight in the composite signal (from SignalEnhancer/MarketContext).
        purpose: One-sentence description of what this engine is FOR.
        description: Longer description of implementation details.
        module: Python module path where the engine is implemented.
        data_tables: DB tables required for this engine to function.
        factory: Callable that creates engine instance (lazy import).
        enabled: Whether this engine is active for testing.
        notes: Additional notes about testing caveats.
    """

    name: str
    category: EngineCategory
    signal_type: SignalType
    default_weight: float
    purpose: str
    description: str
    module: str
    data_tables: list[str]
    factory: Callable[[], Any]
    enabled: bool = True
    notes: str = ""
    min_data_days: int = 30  # Minimum days of data overlap needed for valid testing
    data_duration_notes: str = ""  # Research-based justification for min_data_days


class EngineRegistry:
    """Registry of all engines available for ablation testing."""

    def __init__(self) -> None:
        self._entries: dict[str, EngineEntry] = {}

    def register(self, entry: EngineEntry) -> None:
        if entry.name in self._entries:
            raise ValueError(f"Engine '{entry.name}' already registered")
        self._entries[entry.name] = entry

    def get(self, name: str) -> EngineEntry | None:
        return self._entries.get(name)

    def all_entries(self) -> list[EngineEntry]:
        return list(self._entries.values())

    def enabled_entries(self) -> list[EngineEntry]:
        return [e for e in self._entries.values() if e.enabled]

    def by_category(self, category: EngineCategory) -> list[EngineEntry]:
        return [
            e for e in self._entries.values()
            if e.category == category and e.enabled
        ]

    def names(self) -> list[str]:
        return list(self._entries.keys())

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: str) -> bool:
        return name in self._entries


def _noop_factory() -> None:
    """Default factory for engines that are tested via signal injection
    rather than direct instantiation."""
    return None


def create_default_registry() -> EngineRegistry:
    """Create registry with all known engines from the application.

    Engines are registered with their default weights from SignalEnhancer
    and MarketContext. Factory functions are lazy — they import the engine
    module only when called, to avoid heavy imports at registry creation time.
    """
    registry = EngineRegistry()

    # ── SignalEnhancer engines (8 signals) ──────────────────────────────
    se = EngineCategory.SIGNAL_ENHANCER

    registry.register(EngineEntry(
        name="volume",
        category=se,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.15,
        purpose="Detect volume anomalies that precede price moves (volume leads price)",
        description=(
            "Computes VWAP deviation, Order Flow Imbalance (OFI) proxy, OBV trend, "
            "and volume-weighted momentum. Signal direction: positive when price "
            "above VWAP with rising volume (bullish), negative when below with "
            "rising volume (bearish)."
        ),
        module="market.analysis.volume_features",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        data_duration_notes="VWAP rolling window=20d, OBV divergence window=20d, foreign flow Z-score window=5d. 20d minimum, 60d recommended for stable OBV + multiple regimes.",
    ))
    registry.register(EngineEntry(
        name="event",
        category=se,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.15,
        purpose="Score policy/macro events (BI rate, Fed, regulations) for market impact",
        description=(
            "PolicyEventScorer loads policy_events + external_events from DB, maps "
            "Indonesian-language categories to event types, computes exponential "
            "time-decay (half-life=10 days), and produces composite bullish/bearish "
            "score. Market-wide events weighted 0.3, ticker-specific 1.0."
        ),
        module="market.analysis.policy_event_scorer",
        data_tables=["policy_events", "external_events"],
        factory=_noop_factory,
        data_duration_notes="Exponential decay half-life=10d. Events relevant up to ~30d (3 half-lives). Need 90d for multiple BI rate decisions, geopolitical events, earnings cycles.",
    ))
    registry.register(EngineEntry(
        name="meta",
        category=se,
        signal_type=SignalType.FILTER,
        default_weight=0.20,
        purpose="Filter false signals and size bets using Lopez de Prado meta-labeling",
        description=(
            "MetaLabeler is a secondary LightGBM classifier that predicts P(primary "
            "model direction is correct). Uses triple-barrier labels, CUSUM events, "
            "purged+embargoed walk-forward CV. Outputs bet size [0,1] and trade/no-trade "
            "decision. Requires trained model — cannot test without training first."
        ),
        module="market.analysis.meta_labeling",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        notes="Requires trained LightGBM model. Without training, only filter behavior can be tested.",
        data_duration_notes="Lopez de Prado: minimum 500 labeled events for training. Walk-forward CV needs 500+ days. Without trained model, engine is SKIP.",
    ))
    registry.register(EngineEntry(
        name="smart_money",
        category=se,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.12,
        purpose="Detect institutional accumulation/distribution via foreign flow proxy (Bandarmology)",
        description=(
            "Uses foreign_flow data as proxy for smart money: foreign net buying "
            "with price stability indicates institutional accumulation (bullish). "
            "Foreign net selling with price decline indicates distribution (bearish). "
            "Outputs signal [-1, +1] based on 5-day foreign flow momentum."
        ),
        module="market.analysis.volume_features",
        data_tables=["foreign_flow", "ohlcv"],
        factory=_noop_factory,
        data_duration_notes="Retail absorption lookback=5d + buffer. Need per-ticker broker_flow (not __MARKET__). 20d minimum, 60d recommended for accumulation streak patterns.",
    ))
    registry.register(EngineEntry(
        name="cross_market",
        category=se,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.12,
        purpose="Predict IDX direction from Asian markets that close before IDX (domino effect)",
        description=(
            "Queries v_domino_timeline (PostgreSQL) or falls back to OHLCV. Uses "
            "pre-IDX market returns: ^N225 (weight 0.35, close 06:30 UTC), ^HSI (0.35, "
            "08:00 UTC), 000001.SS (0.15, 07:00 UTC), CPO=F (0.15, T-1). Anti-lookahead: "
            "only uses markets that have already closed before IDX."
        ),
        module="market.analysis.signal_enhancer._compute_cross_market_signal",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        notes="Needs global OHLCV (^N225, ^HSI, 000001.SS, CPO=F) in DB.",
        data_duration_notes="Diebold-Yilmaz spillover index uses 200d rolling VAR. Rapach et al. use monthly data 1972-2022. 60d minimum for stable spillover, 252d recommended.",
    ))
    registry.register(EngineEntry(
        name="sector",
        category=se,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.10,
        purpose="Identify which sectors are rotating into/out of favor for stock selection",
        description=(
            "SectorRotationEngine computes sector momentum (short/long window), rotation "
            "detection (short vs long return comparison), and relative strength vs market "
            "benchmark. Returns SectorRecommendation with rotation_signal for top sectors."
        ),
        module="market.analysis.sector_rotation",
        data_tables=["ohlcv", "sector_master"],
        factory=_noop_factory,
        data_duration_notes="Momentum lookback=20d, rotation short=5d/long=20d, RS window=60d. 60d minimum, 252d recommended for full RS normalization.",
    ))
    registry.register(EngineEntry(
        name="pairs",
        category=se,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.10,
        purpose="Generate mean-reversion signals from cointegrated stock pairs (stat arb)",
        description=(
            "PairsTradingEngine screens pairs via Engle-Granger cointegration (OLS + ADF), "
            "computes spread Z-score with no-look-ahead, generates entry/exit/stop signals "
            "when |Z| > entry_threshold (default 2.0). Regime gate skips when correlation "
            "breaks (rolling corr > 0.95)."
        ),
        module="market.analysis.pairs_trading",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        notes="Needs OHLCV for 2+ cointegrated tickers. Best tested on known pairs (e.g. BBCA-BBRI).",
        data_duration_notes="Engle-Granger cointegration requires 252d+ (1 year). Z-score window=20d, regime gate=20d rolling corr. 252d minimum, 504d recommended for stable cointegration.",
    ))
    registry.register(EngineEntry(
        name="astronacci",
        category=se,
        signal_type=SignalType.TIMING,
        default_weight=0.06,
        purpose="Identify time windows where market reversals are likely (financial astrology)",
        description=(
            "AstronacciEngine computes Moon phases, planetary retrogrades, planetary "
            "ingresses, and Fibonacci time windows. Produces time_signal [-1, +1] and "
            "volatility_signal. This is a TIMING indicator — it says WHEN, not WHAT "
            "direction. Low weight (6%) is intentional."
        ),
        module="market.analysis.astronacci",
        data_tables=["astronacci_cycles"],
        factory=_noop_factory,
        notes="Timing indicator, not directional. Should be evaluated on timing accuracy, not P&L alone.",
        data_duration_notes="Astronomical calculation — no DB data dependency. 1d minimum. Evaluate on timing accuracy (cycle hit rate), not P&L alone.",
    ))

    # ── MarketContext engines (7 factors) ───────────────────────────────
    mc = EngineCategory.MARKET_CONTEXT

    registry.register(EngineEntry(
        name="fundamental",
        category=mc,
        signal_type=SignalType.CONTEXT,
        default_weight=0.14,
        purpose="Assess whether stock is over/undervalued vs fundamentals (PE, ROE, DER, dividend yield)",
        description=(
            "FundamentalScorer computes valuation signals from fundamental_data table: "
            "PE ratio (low = undervalued), ROE (high = quality), DER (low = safe), "
            "dividend yield (high = income). Produces composite fundamental score."
        ),
        module="market.multi_asset.fundamental_scorer",
        data_tables=["fundamental_data", "instrument_master"],
        factory=_noop_factory,
        data_duration_notes="Fundamental data is quarterly/annual. Need 365d (1 year) minimum for trend. Current DB has snapshot, not time-series. 1095d (3 years) recommended.",
    ))
    registry.register(EngineEntry(
        name="macro",
        category=mc,
        signal_type=SignalType.CONTEXT,
        default_weight=0.11,
        purpose="Assess macroeconomic environment (BI rate, CPI, GDP) for market regime",
        description=(
            "MacroCorrelation analyzes correlation between macro_indicators and stock "
            "returns. Computes macro regime signal: rising rates -> negative for equities, "
            "expanding GDP -> positive, high CPI -> mixed. Produces macro context score."
        ),
        module="market.analysis.macro_correlation",
        data_tables=["macro_data", "ohlcv"],
        factory=_noop_factory,
        data_duration_notes="Macro indicators are monthly/quarterly. Need 90d for meaningful correlation. 252d recommended for full macro cycle (BI rate, CPI, GDP).",
    ))
    registry.register(EngineEntry(
        name="ml",
        category=mc,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.14,
        purpose="Generate ML-based price direction predictions using LightGBM ensemble",
        description=(
            "MLSignalProvider uses trained LightGBM models with technical + fundamental "
            "features to predict next-day direction. Outputs probability [0,1] and "
            "direction signal. Requires trained model."
        ),
        module="market.analysis.ml_signal",
        data_tables=["ohlcv", "technical_indicators"],
        factory=_noop_factory,
        notes="Requires trained LightGBM model. Without training, returns neutral signal.",
        data_duration_notes="Walk-forward train/test split needs 500+ days. Lopez de Prado: 500-1000 labeled events minimum. Without trained model, engine is SKIP.",
    ))
    registry.register(EngineEntry(
        name="news",
        category=mc,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.07,
        purpose="Gauge market sentiment from news headlines (IndoBERT or keyword lexicon)",
        description=(
            "NewsSentimentAnalyzer analyzes news titles/bodies with IndoBERT (transformer) "
            "or keyword lexicon fallback. Handles negation, intensifiers, financial relevance. "
            "Time-decay weighting (half-life=7 days). Produces sentiment score [-1, +1]."
        ),
        module="market.analysis.news_sentiment",
        data_tables=["news"],
        factory=_noop_factory,
        data_duration_notes="Time-decay half-life=7d. Need 30d for meaningful sentiment patterns. 100+ news items for statistical significance. 90d recommended for diverse news patterns.",
    ))
    registry.register(EngineEntry(
        name="commodity",
        category=mc,
        signal_type=SignalType.CONTEXT,
        default_weight=0.07,
        purpose="Assess commodity price impact on commodity-linked IDX stocks (CPO, coal, gold, nickel)",
        description=(
            "Computes correlation between commodity prices (CPO, batubara, emas, nikel) "
            "and IDX emiten in commodity sectors. Positive commodity move -> bullish for "
            "producers, bearish for consumers. Uses OHLCV for commodity tickers."
        ),
        module="market.analysis.macro_correlation",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        notes="Needs commodity ticker OHLCV (e.g. CPO=F, GOLD, COAL) in DB.",
        data_duration_notes="CPO-ASEAN equity studies use 5-15 years daily data. Correlation analysis needs 60d rolling minimum. 252d recommended for stable commodity-equity correlation.",
    ))
    registry.register(EngineEntry(
        name="global_sentiment",
        category=mc,
        signal_type=SignalType.CONTEXT,
        default_weight=0.11,
        purpose="Assess global risk appetite via VIX and Fear & Greed index",
        description=(
            "Uses VIX (^VIX OHLCV) and Fear & Greed index (fear_greed table) to compute "
            "global sentiment. High VIX / Extreme Fear -> risk-off (negative for IDX). "
            "Low VIX / Extreme Greed -> risk-on (positive for IDX)."
        ),
        module="market.analysis.signal_enhancer",
        data_tables=["ohlcv", "fear_greed"],
        factory=_noop_factory,
        data_duration_notes="CNN F&G uses 125-day SMA for momentum component. VIX uses 50-day SMA. Need 125d minimum. 252d recommended for full F&G calculation + VIX normalization.",
    ))
    registry.register(EngineEntry(
        name="governance",
        category=mc,
        signal_type=SignalType.CONTEXT,
        default_weight=0.05,
        purpose="Assess corporate governance quality (ESG, board structure) for long-term risk",
        description=(
            "Uses esg_scores and corporate_governance tables to compute governance "
            "quality score. High ESG / good board structure -> lower long-term risk. "
            "Low ESG / poor governance -> higher risk premium. Slow-moving signal."
        ),
        module="market.multi_asset.fundamental_scorer",
        data_tables=["esg_scores", "corporate_governance"],
        factory=_noop_factory,
        notes="Slow-moving signal — changes quarterly. Best evaluated on long timeframes.",
        data_duration_notes="ESG scores are annual. MSCI study: ESG financial effects unfold over multiyear periods. G=short-term event risk, E/S=long-term erosion risk. 730d (2 years) minimum, 1095d (3 years) recommended.",
    ))

    # ── Research-backed alpha signal engines (new) ──────────────────────
    se2 = EngineCategory.SIGNAL_ENHANCER

    registry.register(EngineEntry(
        name="mean_reversion",
        category=se2,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.15,
        purpose="Generate mean-reversion signals from Bollinger Bands + RSI confirmation",
        description=(
            "Combines Bollinger Bands (price stretched > 2 std) with RSI (momentum "
            "exhausted < 30 or > 70) for confirmed mean-reversion entries. Two weak "
            "signals that agree are stronger than one. Reference: Bollinger (2002), "
            "Wilder (1978)."
        ),
        module="market.analysis.alpha_signals.MeanReversionEngine",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=30,
        data_duration_notes="BB window=20d, RSI period=14d. Need 30d minimum for warmup. 252d recommended for multiple regime cycles.",
    ))

    registry.register(EngineEntry(
        name="reversal",
        category=se2,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.15,
        purpose="Exploit short-term price reversal from behavioral overreaction (panic selling → bounce)",
        description=(
            "Stocks that fall/rise the most over 5-21 days tend to revert within 5 "
            "trading days. Uses Z-score of cumulative returns. IC +0.020-0.025, "
            "win rate 54-58% on NIFTY 100 (similar to IDX). Reference: Jegadeesh "
            "(1990), Lehmann (1990)."
        ),
        module="market.analysis.alpha_signals.ShortTermReversalEngine",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=60,
        data_duration_notes="Lookback=10d, Z-score rolling window=60d. Need 60d minimum for Z-score stability. 252d recommended.",
    ))

    registry.register(EngineEntry(
        name="ewma_momentum",
        category=se2,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.15,
        purpose="Generate volatility-scaled EWMA momentum signals (time-series momentum)",
        description=(
            "Uses exponentially weighted moving average crossover (12/26) with "
            "volatility scaling to target 15% annual vol. Reference: Moskowitz, "
            "Ooi, Pedersen (2012) 'Time Series Momentum'."
        ),
        module="market.analysis.alpha_signals.EWMAMomentumEngine",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=30,
        data_duration_notes="EWMA short=12d, long=26d, vol window=20d. Need 30d minimum. 252d recommended for vol scaling stability.",
    ))

    registry.register(EngineEntry(
        name="regime_switch",
        category=se2,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.15,
        purpose="Adapt between momentum (trending) and mean-reversion (ranging) based on volatility regime",
        description=(
            "Detects regime via rolling vol ratio (short/long). Low vol → follow "
            "momentum; High vol → fade extremes (mean-revert). Reference: Daniel & "
            "Moskowitz (2013), Baltas & Kosowski (2015)."
        ),
        module="market.analysis.alpha_signals.RegimeSwitchEngine",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=120,
        data_duration_notes="Vol short=20d, vol long=120d, momentum lookback=20d, reversion lookback=10d. Need 120d minimum for long vol window. 252d recommended.",
    ))

    # ── Alternative engines (v2) for underperformers ───────────────────
    # Tested alongside originals — NOT replacing them. User decides which to keep.

    registry.register(EngineEntry(
        name="commodity_v2",
        category=se2,
        signal_type=SignalType.CONTEXT,
        default_weight=0.10,
        purpose="Commodity as regime filter — high commodity vol = risk-off, stable = risk-on",
        description=(
            "Instead of directional commodity signals (which are not predictive for IDX), "
            "uses commodity volatility as a regime filter. When commodity vol spikes "
            "(CPO/brent/gold 20d vol > 1.5x long-term avg), signal risk-off. When stable, "
            "signal risk-on. Reference: Baur & McDermott (2010) — gold as safe haven."
        ),
        module="market.analysis.alpha_signals",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=60,
        data_duration_notes="Commodity vol short=20d, long=60d. Need 60d minimum. 252d recommended.",
    ))

    registry.register(EngineEntry(
        name="sector_v2",
        category=se2,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.12,
        purpose="Sector relative strength with mean-reversion entry (RS z-score)",
        description=(
            "Instead of pure momentum (false signals in ranging markets), uses RS z-score "
            "with mean-reversion entry. Buys when RS is below historical average by >1.5 std "
            "(oversold sector), sells when above. Reference: DeBondt & Thaler (1985) — "
            "sector mean reversion in emerging markets."
        ),
        module="market.analysis.alpha_signals",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=60,
        data_duration_notes="RS window=60d, z-score window=60d. Need 60d minimum. 252d recommended.",
    ))

    registry.register(EngineEntry(
        name="volume_v2",
        category=se2,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.12,
        purpose="Money Flow Index — volume-weighted RSI for overbought/oversold detection",
        description=(
            "Replaces OFI+VWAP+OBV combo (too noisy) with MFI: a volume-weighted RSI "
            "that incorporates price and volume. MFI < 20 = oversold (buy), MFI > 80 = "
            "overbought (sell). Reference: Quong & Soudack (1989). MFI is more predictive "
            "than RSI alone because it weights by volume."
        ),
        module="market.analysis.alpha_signals",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=30,
        data_duration_notes="MFI period=14d. Need 30d minimum. 252d recommended for multiple cycles.",
    ))

    registry.register(EngineEntry(
        name="event_v2",
        category=se2,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.10,
        purpose="Earnings momentum from quarterly fundamental changes",
        description=(
            "Replaces policy event scorer (rarely triggers) with earnings momentum: "
            "compares quarterly EPS/revenue growth. Positive earnings surprise → bullish, "
            "negative → bearish. Uses PE and EPS from fundamental_data. "
            "Reference: Ball & Brown (1968) — post-earnings announcement drift."
        ),
        module="market.analysis.alpha_signals",
        data_tables=["fundamental_data", "ohlcv"],
        factory=_noop_factory,
        min_data_days=90,
        data_duration_notes="Quarterly comparison needs 90d minimum. 365d recommended for 4 quarters.",
    ))

    registry.register(EngineEntry(
        name="ml_v2",
        category=se2,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.15,
        purpose="LightGBM with walk-forward retraining and richer feature set",
        description=(
            "Replaces simple LogisticRegression with LightGBM + 12 features (lagged returns, "
            "RSI, MACD, BB width, ATR ratio, volume ratio, momentum). Walk-forward: retrain "
            "every 60 days, train on expanding window. Reference: Lopez de Prado (2018) — "
            "cross-validation for financial ML."
        ),
        module="market.analysis.alpha_signals",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=252,
        data_duration_notes="Walk-forward: 252d initial train, retrain every 60d. 504d recommended.",
    ))

    # ── Advanced global-IDX models (pustaka/101) ───────────────────────
    registry.register(EngineEntry(
        name="dcc_garch",
        category=se2,
        signal_type=SignalType.CONTEXT,
        default_weight=0.10,
        purpose="DCC-GARCH dynamic conditional correlation between IDX and global markets",
        description=(
            "Uses DCC-GARCH (Engle 2002) to compute dynamic correlation between IHSG and "
            "S&P 500, VIX, USD/IDR. High correlation = contagion risk (reduce), low = "
            "idiosyncratic opportunity. Simplified implementation without full MLE. "
            "Reference: Engle (2002), pustaka/101 §1."
        ),
        module="market.analysis.alpha_signals",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=120,
        data_duration_notes="GARCH window=20d, DCC needs 120d for stable correlation estimate. 252d recommended.",
    ))

    registry.register(EngineEntry(
        name="spillover_dy",
        category=se2,
        signal_type=SignalType.CONTEXT,
        default_weight=0.10,
        purpose="Diebold-Yilmaz spillover index — contagion vs decoupled regime detection",
        description=(
            "Full Diebold-Yilmaz spillover index using VAR + FEVD. Total spillover > 60% = "
            "contagion regime (risk-off), < 30% = decoupled (idiosyncratic opportunity). "
            "Walk-forward: VAR re-estimated on expanding window. "
            "Reference: Diebold & Yilmaz (2012), pustaka/101 §2."
        ),
        module="market.analysis.alpha_signals",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=120,
        data_duration_notes="VAR lag=2, FEVD horizon=10. Need 120d for stable VAR. 252d recommended.",
    ))

    registry.register(EngineEntry(
        name="foreign_flow",
        category=se2,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.12,
        purpose="Foreign flow prediction from rate differential, DXY, VIX, USD/IDR, valuation",
        description=(
            "Predicts foreign investor flow direction using linear scoring model: "
            "BI-Fed rate differential, DXY change, VIX level, USD/IDR change, IDX P/E. "
            "Score > 55 = net buy, < 45 = net sell. Foreign flow is primary IDX driver. "
            "Reference: BIS (2021), pustaka/101 §3."
        ),
        module="market.analysis.alpha_signals",
        data_tables=["macro_data", "ohlcv"],
        factory=_noop_factory,
        min_data_days=90,
        data_duration_notes="Monthly macro data + daily VIX/USDIDR. Need 90d minimum. 365d recommended.",
    ))

    registry.register(EngineEntry(
        name="overnight_idx",
        category=se2,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.15,
        purpose="Overnight global market → IDX opening prediction with timezone-aware lag",
        description=(
            "Combines US overnight (T-1: S&P, Nasdaq, VIX, US 10Y, DXY) with Asian same-day "
            "(T-0: Nikkei, Hang Seng, Shanghai, CPO) to predict IDX direction. Timezone "
            "advantage: Asian markets close before IDX. Weighted composite signal. "
            "Reference: Hamao et al. (1990), pustaka/101 §4."
        ),
        module="market.analysis.alpha_signals",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=60,
        data_duration_notes="US T-1 + Asian T-0. Need 60d for stable weights. 252d recommended.",
    ))

    # ── Sector-Global Link Engine (pustaka/102) ─────────────────────────
    registry.register(EngineEntry(
        name="sector_global_link",
        category=se2,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.12,
        purpose="Sector-specific global market driver with timezone-aware lag",
        description=(
            "Maps each IDX sector to its relevant global market driver(s) with timezone-aware "
            "lag (T-0 Asian, T-1 US/Europe). Energy→Oil, Financials→US 10Y, Basic Mat→Gold, "
            "Tech→Nasdaq, Consumer→USD/IDR. Subsector override for gold/coal/banks/telecom. "
            "Threshold 0.5% for significant moves. Multi-driver consensus. "
            "Reference: Chen et al. (1986), pustaka/102."
        ),
        module="market.analysis.alpha_signals",
        data_tables=["ohlcv", "instrument_master"],
        factory=_noop_factory,
        min_data_days=60,
        data_duration_notes="Global OHLCV + sector mapping. Need 60d minimum. 252d recommended.",
    ))

    return registry
