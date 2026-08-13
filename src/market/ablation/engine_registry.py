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

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class EngineCategory(str, Enum):
    SIGNAL_ENHANCER = "signal_enhancer"
    MARKET_CONTEXT = "market_context"
    PREDICTION_CORE = "prediction_core"


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
        enabled=False,  # BUANG: overlap with Bollinger/RSI in MultiFactor features
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
        enabled=False,  # BUANG: overlap with pred_momentum (momentum reversal)
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
        enabled=False,  # BUANG: overlap with pred_ma (MA crossover)
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
        enabled=False,  # PERTIMBANGKAN: regime detection unik, pending ablation test
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
        enabled=False,  # BUANG: commodity (price momentum) sudah dipakai, v2 (vol ratio) redundant
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
        enabled=False,  # BUANG: sector (momentum+RS) sudah dipakai, v2 (z-score mean-reversion) bertentangan
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
        enabled=False,  # BUANG: volume (OFI+VWAP+OBV) lebih lengkap, MFI redundant
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
        enabled=False,  # BUANG: event (PolicyEventScorer) + fundamental sudah cover, v2 redundant
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
        enabled=False,  # BUANG: ml (LogReg) + multi_factor (LightGBM 3-class) sudah cover, v2 redundant
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
        enabled=False,  # PERTIMBANGKAN: dynamic correlation unik, pending ablation test
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
        enabled=False,  # PERTIMBANGKAN: spillover index unik, tapi VAR berat, pending ablation test
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
        enabled=False,  # BUANG: mc_flow (actual flow) + smart_money (broker absorption) sudah cover
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
        enabled=False,  # PERTIMBANGKAN: overnight signal unik, tapi overlap dengan cross_market, pending test
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
        enabled=False,  # PERTIMBANGKAN: sector-global driver unik, tapi overlap dengan commodity, pending test
    ))

    # ── Missing MarketContext factors (production pipeline) ────────────
    # These are separate from the SignalEnhancer versions above.
    # In the application, MarketContext.composite_signal() uses 11 weighted
    # factors. The original 7 were already registered; these 4 were missing.

    registry.register(EngineEntry(
        name="mc_sentiment",
        category=mc,
        signal_type=SignalType.CONTEXT,
        default_weight=0.07,
        purpose="Assess market sentiment via Fear & Greed index (contrarian signal)",
        description=(
            "Uses fear_greed table to compute contrarian sentiment signal. "
            "Extreme Fear (<25) → bullish (contrarian buy), Extreme Greed (>75) "
            "→ bearish (contrarian sell). This is SEPARATE from global_sentiment "
            "(which uses VIX + Time-Zone Bucket Grid). In production, both have "
            "independent weights in MarketContext.composite_signal()."
        ),
        module="market.analysis.market_context.MarketContext.sentiment_signal",
        data_tables=["fear_greed"],
        factory=_noop_factory,
        data_duration_notes="CNN F&G uses 125-day SMA for momentum component. Need 30d minimum. 252d recommended.",
    ))

    registry.register(EngineEntry(
        name="mc_flow",
        category=mc,
        signal_type=SignalType.CONTEXT,
        default_weight=0.09,
        purpose="Assess foreign investor flow pressure (5-day net buy/sell momentum)",
        description=(
            "Uses foreign_flow table to compute 5-day cumulative net foreign flow. "
            "Positive net flow → bullish (institutional buying), negative → bearish. "
            "This is the MarketContext factor, NOT the SignalEnhancer smart_money "
            "(which uses broker-level absorption) or the foreign_flow prediction model "
            "(which predicts flow direction from rate differentials)."
        ),
        module="market.analysis.market_context.MarketContext.flow_signal",
        data_tables=["foreign_flow"],
        factory=_noop_factory,
        data_duration_notes="5-day rolling cumulative. Need 20d minimum. 90d recommended for flow pattern stability.",
    ))

    registry.register(EngineEntry(
        name="mc_cross_market",
        category=mc,
        signal_type=SignalType.CONTEXT,
        default_weight=0.06,
        purpose="Assess cross-market correlation regime (vs US, HK, JP, IHSG)",
        description=(
            "Uses rolling correlation between ticker and global indices (^GSPC, ^HSI, "
            "^N225, ^JKSE) from relationship_matrix or computed on-the-fly. High corr "
            "= contagion risk, low = idiosyncratic opportunity. This is the "
            "MarketContext factor, NOT the SignalEnhancer cross_market (which uses "
            "pre-IDX Asian market returns for domino effect directional signal)."
        ),
        module="market.analysis.market_context.MarketContext.cross_market_signal",
        data_tables=["ohlcv", "relationship_matrix"],
        factory=_noop_factory,
        data_duration_notes="Rolling correlation window=60d. Need 60d minimum. 252d recommended.",
    ))

    registry.register(EngineEntry(
        name="mc_astronacci",
        category=mc,
        signal_type=SignalType.TIMING,
        default_weight=0.03,
        purpose="Astronacci time-cycle as MarketContext factor (low weight timing overlay)",
        description=(
            "Same AstronacciEngine as the SignalEnhancer version (weight 0.06), but "
            "here as a MarketContext factor with lower weight (0.03, or 0.04 for "
            "Communication Services sector). Provides time_signal and volatility_signal "
            "as context overlay. The dual registration reflects the actual production "
            "architecture where Astronacci appears in both pipelines."
        ),
        module="market.analysis.astronacci",
        data_tables=["astronacci_cycles"],
        factory=_noop_factory,
        notes="Timing indicator. Same engine as 'astronacci' (SE) but with MC weight.",
        data_duration_notes="Astronomical calculation — no DB data dependency. 1d minimum.",
    ))

    # ── MultiFactorModel (production pipeline) ─────────────────────────
    registry.register(EngineEntry(
        name="multi_factor",
        category=mc,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.14,
        purpose="LightGBM 3-class BUY/SELL/HOLD with 30+ features + PCA dimensionality reduction",
        description=(
            "MultiFactorFeaturePipeline: 30 endogenous features (autocorrelation, "
            "candlestick, Bollinger, MACD, RSI, momentum, MA ratios, vol regime, VWAP, "
            "volume trend) + 24 exogenous features (global returns + rolling corr) → "
            "PCA 18 components (95.8% variance). LightGBM 3-class (BUY=2, HOLD=1, SELL=0), "
            "300 trees, depth 5, lr 0.05, walk-forward 80/20. Signal = P(BUY) - P(SELL). "
            "In production, blended 60% with MLSignalProvider (40%) in MarketContext.ml_signal."
        ),
        module="market.analysis.multi_factor.MultiFactorModel",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        notes="Requires 200+ samples for training. Walk-forward CV.",
        data_duration_notes="Walk-forward 80/20 split needs 252d minimum. 504d recommended for stable PCA.",
    ))

    # ── PredictionEngine core ensemble methods ─────────────────────────
    # These 4 methods form the ensemble in PredictionEngine._predict_ensemble().
    # Testing them individually reveals which contributes most to prediction.
    pc = EngineCategory.PREDICTION_CORE

    registry.register(EngineEntry(
        name="pred_ma",
        category=pc,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.25,
        purpose="Moving average crossover prediction (MA short vs MA long)",
        description=(
            "Computes MA short (5-day) and MA long (20-day) crossover. "
            "MA short > MA long → bullish, MA short < MA long → bearish. "
            "One of 4 ensemble methods in PredictionEngine._predict_ensemble(). "
            "Ticker-specific weights (e.g. UNTR.JK: 0.30, ANTM.JK: 0.15)."
        ),
        module="market.analysis.prediction.PredictionEngine._predict_ma",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=20,
        data_duration_notes="MA short=5d, MA long=20d. Need 20d minimum. 252d recommended.",
    ))

    registry.register(EngineEntry(
        name="pred_momentum",
        category=pc,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.25,
        purpose="Damped momentum prediction (recent return × 0.5 damping factor)",
        description=(
            "Computes momentum as percentage return over horizon (default 5d), "
            "applies 0.5 damping factor. Positive momentum → bullish, negative → bearish. "
            "Confidence = 0.4 + |momentum|/20, capped at 0.8. "
            "One of 4 ensemble methods in PredictionEngine._predict_ensemble()."
        ),
        module="market.analysis.prediction.PredictionEngine._predict_momentum",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=5,
        data_duration_notes="Momentum period=5d. Need 5d minimum. 60d recommended for momentum stability.",
    ))

    registry.register(EngineEntry(
        name="pred_pattern",
        category=pc,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.30,
        purpose="Chart pattern detection prediction (head&shoulders, triangle, double top/bottom)",
        description=(
            "PatternDetector detects technical patterns in OHLCV data. "
            "Aggregates bullish/bearish/neutral pattern signals. "
            "If no patterns detected → flat. If more bullish → buy, more bearish → sell. "
            "Highest weight in ensemble (0.30 default, up to 0.40 when no patterns found). "
            "One of 4 ensemble methods in PredictionEngine._predict_ensemble()."
        ),
        module="market.analysis.pattern_detector.PatternDetector",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=30,
        data_duration_notes="Pattern detection needs 30d minimum for reliable pattern formation. 252d recommended.",
    ))

    registry.register(EngineEntry(
        name="pred_vol_adj",
        category=pc,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.25,
        purpose="Volatility-adjusted prediction (ATR-based confidence scaling)",
        description=(
            "Combines MA crossover with ATR-based volatility adjustment. "
            "High ATR → reduce confidence (uncertain regime), low ATR → increase confidence. "
            "One of 4 ensemble methods in PredictionEngine._predict_ensemble()."
        ),
        module="market.analysis.prediction.PredictionEngine._predict_vol_adj",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=20,
        data_duration_notes="ATR period=14d, MA short=5d, MA long=20d. Need 20d minimum. 252d recommended.",
    ))

    # ════════════════════════════════════════════════════════════════════
    # ── GLOBAL MARKET AI ENGINES (pustaka research integration) ─────────
    # ════════════════════════════════════════════════════════════════════

    # ── vta_reasoning: VTA-style verbal technical analysis ──────────────
    # Inspired by VTA (Koa et al., ICLR 2026). Converts OHLCV → textual
    # annotations → rule-based reasoning → signal + natural language explanation.
    # Future upgrade: replace rules with LLM (FinGPT/Ollama).
    registry.register(EngineEntry(
        name="vta_reasoning",
        category=se,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.10,
        purpose="VTA-style verbal reasoning: OHLCV → annotations → reasoning → signal + explanation",
        description=(
            "Implements VTA framework (ICLR 2026): (1) Convert OHLCV to textual annotations "
            "(MA, RSI, momentum, BB, volume, ATR, MACD), (2) Generate reasoning trace from "
            "annotations using weighted rule-based logic, (3) Produce directional signal + "
            "Bahasa Indonesia explanation. Rule-based version of LLM reasoning. "
            "Source: arxiv.org/abs/2511.08616"
        ),
        module="market.analysis.vta_reasoning.VTAReasoningEngine",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=20,
        data_duration_notes="MA20 + BB20 + ATR14. Need 20d minimum. 252d recommended for stable reasoning.",
    ))

    # ── causal_discovery: CausalStock-style directed causal graph ───────
    # Inspired by CausalStock (Liu et al., 2024). Uses Granger causality
    # to discover directed (asymmetric) causal links between tickers.
    registry.register(EngineEntry(
        name="causal_discovery",
        category=se,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.08,
        purpose="CausalStock-style lag-dependent causal discovery between tickers (Granger causality)",
        description=(
            "Discovers directed causal relationships between tickers using Granger causality "
            "(practical substitute for CausalStock's variational inference). Builds causal graph "
            "with F-test significance + sigmoid strength normalization. Signal: weighted consensus "
            "of causal influencers' recent returns. Re-estimates graph every 60 days (walk-forward). "
            "Source: arxiv.org/abs/2411.06391"
        ),
        module="market.analysis.causal_discovery.CausalDiscoveryEngine",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=120,
        data_duration_notes="Granger causality needs 120d minimum for stable F-test. 252d recommended.",
    ))

    # ── denoised_news: CausalStock-style denoised news encoder ──────────
    # Inspired by CausalStock's Denoised News Encoder + Ploutos' Sentiment Expert.
    # Scores news from multiple perspectives (sentiment, impact, relevance).
    registry.register(EngineEntry(
        name="denoised_news",
        category=se,
        signal_type=SignalType.DIRECTIONAL,
        default_weight=0.10,
        purpose="Multi-perspective denoised news scoring (sentiment + impact + relevance)",
        description=(
            "CausalStock-style denoised news encoder: scores each news article from 3 perspectives "
            "(sentiment [-1,1], impact [0,100], relevance [0,1]). Produces denoised_score = "
            "sentiment × impact × relevance. Aggregates with exponential time decay over lookback "
            "window. Rule-based backend (keyword + lexicon). Future: LLM backend. "
            "Sources: arxiv.org/abs/2411.06391 (§4.2), arxiv.org/abs/2403.00782 (§3.1.1)"
        ),
        module="market.analysis.denoised_news.DenoisedNewsEncoder",
        data_tables=["news"],
        factory=_noop_factory,
        min_data_days=30,
        data_duration_notes="News sentiment with 5-day exponential decay. Need 30d minimum. 90d recommended.",
    ))

    # ── spillover_lab: Full Diebold-Yilmaz spillover index ──────────────
    # Upgraded from simplified spillover_dy. Adds directional TO/FROM/NET measures.
    registry.register(EngineEntry(
        name="spillover_lab",
        category=mc,
        signal_type=SignalType.CONTEXT,
        default_weight=0.06,
        purpose="Full Diebold-Yilmaz spillover: directional TO/FROM/NET + rolling dynamics",
        description=(
            "Upgraded spillover_dy with full DY (2012) framework: (1) VAR(p) with optimal lag, "
            "(2) Generalized FEVD (Pesaran-Shin, order-invariant), (3) Directional TO/FROM/NET "
            "spillover measures per ticker, (4) Total spillover index, (5) Rolling window "
            "re-estimation. Signal: high NET spillover → contagion (bearish), low → decoupled (bullish). "
            "Source: Diebold-Yilmaz (2012), github.com/aalemoro/spillover-lab"
        ),
        module="market.analysis.spillover_lab.SpilloverLabEngine",
        data_tables=["ohlcv"],
        factory=_noop_factory,
        min_data_days=120,
        data_duration_notes="VAR(2) + FEVD(10) needs 120d minimum. 252d recommended for stable estimation.",
    ))

    return registry
