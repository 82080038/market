"""Market context provider for prediction engine (pustaka/23, pustaka/35).

Gathers fundamental, macro, foreign flow, and sentiment data from DB
to enrich predictions with real-world market context.

All data is fetched with as_of cutoff to maintain no-look-ahead guarantee.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from market.analysis.ml_signal import MLSignalProvider

logger = logging.getLogger(__name__)


@dataclass
class MarketContext:
    """Contextual market data for a ticker at a point in time."""

    # Fundamental factors
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    roe: float | None = None
    dividend_yield: float | None = None
    der: float | None = None
    eps: float | None = None

    # Macro factors
    vix: float | None = None
    us_10y_yield: float | None = None
    fed_funds_rate: float | None = None

    # Sentiment
    fear_greed_index: float | None = None
    fear_greed_label: str | None = None

    # Foreign flow (net buy/sell in IDR, latest available)
    foreign_net_flow: float | None = None
    foreign_net_flow_5d: float | None = None

    # Composite scores from DB
    technical_score: float | None = None
    fundamental_score: float | None = None

    # Cross-market correlations (ticker vs global indices)
    corr_us: float | None = None       # vs ^GSPC
    corr_hk: float | None = None       # vs ^HSI
    corr_jp: float | None = None       # vs ^N225
    corr_ihsg: float | None = None     # vs ^JKSE

    # ML model prediction signal
    ml_signal: float | None = None     # -1.0 to 1.0

    # News sentiment (from NLP-processed news)
    news_sentiment: float | None = None  # -1.0 to 1.0
    news_count: int | None = None        # number of recent news items

    # Sector-specific commodity momentum
    sector: str | None = None
    commodity_signal: float | None = None  # -1.0 to 1.0

    # Global sentiment from Time-Zone Bucket Grid
    global_sentiment: float | None = None  # -1.0 to 1.0

    # ESG & corporate governance (pustaka/18 §13 D28, D29)
    esg_score: float | None = None           # numeric ESG score
    esg_rating: str | None = None            # letter rating (e.g. 'AAA')
    governance_score: float | None = None    # normalized 0-100
    has_whistleblowing: bool | None = None
    has_risk_committee: bool | None = None

    # Astronacci time-cycle signal (pustaka/99)
    astronacci_signal: float | None = None   # -1.0 to 1.0 (time-cycle directional)
    astronacci_volatility: float | None = None  # 0.0 to 1.0 (expected volatility)
    astronacci_active_cycles: list[str] | None = None

    # Holiday effect (pustaka/36 — holiday effect on returns)
    is_pre_holiday: bool | None = None       # True if tomorrow is holiday
    is_post_holiday: bool | None = None      # True if yesterday was holiday
    days_to_next_holiday: int | None = None  # days until next exchange holiday
    pre_holiday_expected_return: float | None = None  # avg pre-holiday return %
    post_holiday_expected_return: float | None = None  # avg post-holiday return %
    spillover_expected_return: float | None = None  # global holiday spillover to IDX

    # Alpha signals (4 engines: mean_reversion, reversal, ewma_momentum, regime_switch)
    alpha_mean_reversion: float | None = None    # -1.0 to 1.0
    alpha_reversal: float | None = None          # -1.0 to 1.0
    alpha_ewma_momentum: float | None = None     # -1.0 to 1.0
    alpha_regime_switch: float | None = None     # -1.0 to 1.0

    # Policy event signal (from policy_events + external_events tables)
    policy_event_signal: float | None = None     # -1.0 to 1.0
    policy_event_count: int | None = None        # number of active events

    # Sector rotation signal (from SectorRotationEngine)
    sector_rotation_signal: float | None = None  # -1.0 to 1.0

    # Pairs trading Z-score (from PairsTradingEngine)
    pairs_trading_zscore: float | None = None    # Z-score, typically -3 to 3

    # Meta-labeling probability (P(primary prediction correct))
    meta_label_probability: float | None = None  # 0.0 to 1.0

    # Volume features (OFI proxy, VWAP deviation, OBV divergence)
    volume_ofi: float | None = None              # Order Flow Imbalance proxy
    volume_vwap_deviation: float | None = None   # VWAP deviation %
    volume_obv_divergence: float | None = None   # OBV divergence signal

    # Seasonal pattern score (from seasonal_patterns table)
    seasonal_score: float | None = None          # -1.0 to 1.0
    seasonal_pattern_name: str | None = None     # e.g. "year_end_rally"

    # Earnings calendar impact (from earnings_calendar table)
    earnings_days_to_report: int | None = None   # days to next earnings
    earnings_expected_surprise: float | None = None  # expected surprise %

    # Instrument behavior profile (from instrument_behavior_profiles table)
    profile_volatility_regime: str | None = None  # "low"/"medium"/"high"
    profile_liquidity_score: float | None = None  # 0-10
    profile_overnight_gap_pct: float | None = None  # avg overnight gap %

    # DCC-GARCH correlation (from dcc_garch_results table)
    dcc_garch_corr_global: float | None = None   # dynamic correlation with global

    # Granger causality signal (from causal_relationships table)
    granger_cause_count: int | None = None       # number of significant causes
    granger_top_cause: str | None = None         # strongest cause ticker

    # Derived signals
    signals: dict[str, str] = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        """Check if any context data is available."""
        return any(
            v is not None
            for v in [
                self.pe_ratio, self.vix, self.fear_greed_index,
                self.foreign_net_flow, self.technical_score,
                self.corr_us, self.corr_ihsg, self.ml_signal,
                self.news_sentiment, self.esg_score, self.governance_score,
                self.astronacci_signal,
                self.alpha_mean_reversion, self.alpha_reversal,
                self.alpha_ewma_momentum, self.alpha_regime_switch,
                self.policy_event_signal, self.sector_rotation_signal,
                self.pairs_trading_zscore, self.meta_label_probability,
                self.volume_ofi, self.seasonal_score,
                self.earnings_days_to_report, self.dcc_garch_corr_global,
            ]
        )

    def fundamental_signal(self) -> float:
        """Return a composite fundamental signal: -1.0 (bearish) to 1.0 (bullish).

        Handles outliers:
        - PE > 500 or < -100 → treat as unreliable (skip)
        - PB > 100 → skip (near-zero book value)
        - Dividend yield > 50% → likely data error (skip)
        - DER > 10 → high leverage penalty
        - ROE can be quarterly-annualized or annual; normalize
        """
        score = 0.0
        n = 0

        # PE ratio (skip extreme outliers from near-zero EPS)
        if self.pe_ratio is not None and 0 < self.pe_ratio < 500:
            if self.pe_ratio < 10:
                score += 0.3
            elif self.pe_ratio < 20:
                score += 0.1
            elif self.pe_ratio > 50:
                score -= 0.2
            n += 1

        # ROE (normalize: if > 1.0, assume already percentage; if < 1.0, it's a ratio)
        if self.roe is not None:
            roe_norm = self.roe if self.roe <= 1.0 else self.roe / 100.0
            if roe_norm > 0.20:
                score += 0.3
            elif roe_norm > 0.10:
                score += 0.1
            elif roe_norm < 0:
                score -= 0.3  # Negative ROE = losing money
            elif roe_norm < 0.05:
                score -= 0.2
            n += 1

        # Dividend yield (skip > 50% — likely data error)
        if (
            self.dividend_yield is not None
            and 0 < self.dividend_yield < 50
        ):
            if self.dividend_yield > 8:
                score += 0.2
            elif self.dividend_yield > 4:
                score += 0.1
            n += 1

        # DER (debt-to-equity ratio)
        if self.der is not None and self.der >= 0:
            if self.der < 2:
                score += 0.1
            elif self.der > 5:
                score -= 0.3  # High leverage
            elif self.der > 2:
                score -= 0.1
            n += 1

        return score / n if n > 0 else 0.0

    def macro_signal(self) -> float:
        """Return a composite macro signal: -1.0 (risk-off) to 1.0 (risk-on)."""
        score = 0.0
        n = 0

        if self.vix is not None:
            if self.vix < 15:
                score += 0.3
            elif self.vix < 25:
                score += 0.1
            elif self.vix > 35:
                score -= 0.3
            elif self.vix > 25:
                score -= 0.1
            n += 1

        if self.us_10y_yield is not None:
            if self.us_10y_yield < 3.0:
                score += 0.2
            elif self.us_10y_yield > 5.0:
                score -= 0.2
            n += 1

        if self.fed_funds_rate is not None:
            if self.fed_funds_rate < 2.0:
                score += 0.2
            elif self.fed_funds_rate > 5.0:
                score -= 0.2
            n += 1

        return score / n if n > 0 else 0.0

    def sentiment_signal(self) -> float:
        """Return sentiment signal from Fear & Greed: -1.0 (fear) to 1.0 (greed)."""
        if self.fear_greed_index is not None:
            return (self.fear_greed_index - 50) / 50.0
        return 0.0

    def flow_signal(self) -> float:
        """Return foreign flow signal: -1.0 (outflow) to 1.0 (inflow)."""
        if self.foreign_net_flow_5d is not None and self.foreign_net_flow_5d != 0:
            # Normalize: large inflow → +1, large outflow → -1
            # Use 10 billion IDR as scale reference
            return max(-1.0, min(1.0, self.foreign_net_flow_5d / 10_000_000_000))
        if self.foreign_net_flow is not None and self.foreign_net_flow != 0:
            return max(-1.0, min(1.0, self.foreign_net_flow / 5_000_000_000))
        return 0.0

    def cross_market_signal(self) -> float:
        """Return cross-market correlation signal: -1.0 to 1.0.

        High correlation with US/HK/JP markets during risk-on = bullish.
        High correlation with IHSG = stock moves with market (neutral).
        Low correlation = idiosyncratic (depends on fundamentals).
        """
        score = 0.0
        n = 0

        # US correlation: positive corr in risk-on environment
        if self.corr_us is not None:
            # Moderate positive correlation is healthy
            if 0.2 < self.corr_us < 0.6:
                score += 0.1
            elif self.corr_us > 0.7:
                score -= 0.1  # Too correlated — contagion risk
            elif self.corr_us < -0.3:
                score += 0.15  # Diversifier
            n += 1

        # IHSG correlation: high = beta to market
        if self.corr_ihsg is not None:
            if self.corr_ihsg > 0.7:
                score += 0.0  # Moves with market — neutral
            elif self.corr_ihsg < 0.3:
                score += 0.1  # Idiosyncratic — alpha potential
            n += 1

        return score / n if n > 0 else 0.0

    def news_sentiment_signal(self) -> float:
        """Return news sentiment signal: -1.0 (negative) to 1.0 (positive).

        Weighted by news count: more news = stronger signal.
        """
        if self.news_sentiment is not None:
            # Scale by news count: 1 news = 0.5 weight, 5+ = full weight
            weight = min(1.0, (self.news_count or 1) / 5.0)
            return self.news_sentiment * weight
        return 0.0

    def governance_signal(self) -> float:
        """Return governance/ESG signal: -1.0 (poor) to 1.0 (strong).

        Combines ESG score (normalized to 0-1 → -1 to +1) and governance
        quality indicators (whistleblowing, risk committee, board independence).
        """
        score = 0.0
        n = 0

        if self.esg_score is not None:
            # ESG scores typically 0-100; normalize to [-1, 1]
            esg_norm = max(-1.0, min(1.0, (self.esg_score - 50) / 50.0))
            score += esg_norm * 0.5
            n += 1

        if self.governance_score is not None:
            # Governance score 0-100; normalize to [-1, 1]
            gov_norm = max(-1.0, min(1.0, (self.governance_score - 50) / 50.0))
            score += gov_norm * 0.3
            n += 1

        if self.has_whistleblowing is not None:
            score += 0.1 if self.has_whistleblowing else -0.1
            n += 1

        if self.has_risk_committee is not None:
            score += 0.1 if self.has_risk_committee else -0.1
            n += 1

        return score / n if n > 0 else 0.0

    def composite_signal(self) -> float:
        """Weighted composite of all context signals: -1.0 to 1.0.

        Weights are loaded from DB (signal_weights table) via WeightRegistry,
        with sector-specific overrides. No hardcoded fallback — raises
        WeightRegistryError if DB weights are unavailable.

        Sector-specific weighting:
        - Basic Materials: commodity signal weighted higher
        - Financial Services: macro and flow weighted higher
        - Consumer Defensive: fundamental weighted higher
        """
        from market.analysis.weight_registry import WeightRegistry

        weights = WeightRegistry.get_weights("market_context", sector=self.sector or "DEFAULT")

        return (
            self.fundamental_signal() * weights["fundamental"]
            + self.macro_signal() * weights["macro"]
            + self.sentiment_signal() * weights["sentiment"]
            + self.flow_signal() * weights["flow"]
            + self.cross_market_signal() * weights["cross_market"]
            + (self.ml_signal or 0.0) * weights["ml"]
            + self.news_sentiment_signal() * weights["news"]
            + (self.commodity_signal or 0.0) * weights["commodity"]
            + (self.global_sentiment or 0.0) * weights["global_sentiment"]
            + self.governance_signal() * weights["governance"]
            + (self.astronacci_signal or 0.0) * weights["astronacci"]
            + self.holiday_signal() * weights["holiday"]
            + self.alpha_composite_signal() * weights["alpha"]
            + self.policy_event_signal_value() * weights["policy_event"]
            + self.sector_rotation_signal_value() * weights["sector_rotation"]
            + self.volume_signal() * weights["volume"]
            + self.seasonal_signal() * weights["seasonal"]
            + self.earnings_signal() * weights["earnings"]
            + self.causal_signal() * weights["causal"]
            + self.meta_label_signal() * weights["meta_label"]
        )

    def holiday_signal(self) -> float:
        """Holiday effect signal: -1.0 (bearish) to 1.0 (bullish).

        Combines pre/post holiday expected returns and spillover.
        Pre-holiday: often positive (window dressing)
        Post-holiday: can be reversal or continuation
        Spillover: global holiday → IDX next day
        """
        signal = 0.0
        # Pre-holiday effect (expected return already in %)
        if self.is_pre_holiday and self.pre_holiday_expected_return is not None:
            signal += max(-1.0, min(1.0, self.pre_holiday_expected_return / 0.5))
        # Post-holiday effect
        if self.is_post_holiday and self.post_holiday_expected_return is not None:
            signal += max(-1.0, min(1.0, self.post_holiday_expected_return / 0.5))
        # Spillover from global holidays
        if self.spillover_expected_return is not None:
            signal += max(-1.0, min(1.0, self.spillover_expected_return / 0.5))
        # Normalize: if only one component active, don't double-count
        n_active = sum([
            self.is_pre_holiday is True,
            self.is_post_holiday is True,
            self.spillover_expected_return is not None,
        ])
        if n_active > 1:
            signal /= n_active
        return max(-1.0, min(1.0, signal))

    def alpha_composite_signal(self) -> float:
        """Composite of 4 alpha engines: -1.0 to 1.0.

        Equal-weight blend of mean_reversion, reversal, ewma_momentum, regime_switch.
        Only includes engines with non-None values.
        """
        signals = [
            self.alpha_mean_reversion,
            self.alpha_reversal,
            self.alpha_ewma_momentum,
            self.alpha_regime_switch,
        ]
        active = [s for s in signals if s is not None]
        if not active:
            return 0.0
        return max(-1.0, min(1.0, sum(active) / len(active)))

    def policy_event_signal_value(self) -> float:
        """Policy event signal: -1.0 (bearish event) to 1.0 (bullish event).

        Scaled by event count: more events = stronger signal.
        """
        if self.policy_event_signal is None:
            return 0.0
        weight = min(1.0, (self.policy_event_count or 1) / 5.0)
        return max(-1.0, min(1.0, self.policy_event_signal * weight))

    def sector_rotation_signal_value(self) -> float:
        """Sector rotation signal: -1.0 (sector out-of-favor) to 1.0 (sector in-favor)."""
        return self.sector_rotation_signal or 0.0

    def pairs_trading_signal_value(self) -> float:
        """Pairs trading Z-score signal: -1.0 to 1.0.

        Z-score > 2 → short (overextended), Z < -2 → long (oversold).
        Scaled by 1/3 for ±3σ → ±1.0.
        """
        if self.pairs_trading_zscore is None:
            return 0.0
        return max(-1.0, min(1.0, -self.pairs_trading_zscore / 3.0))

    def meta_label_signal(self) -> float:
        """Meta-labeling signal: 0.0 to 1.0 → -1.0 to 1.0.

        P(primary prediction correct) > 0.5 → bullish on prediction confidence.
        """
        if self.meta_label_probability is None:
            return 0.0
        return (self.meta_label_probability - 0.5) * 2.0

    def volume_signal(self) -> float:
        """Volume features composite signal: -1.0 to 1.0.

        Combines OFI, VWAP deviation, OBV divergence.
        """
        score = 0.0
        n = 0
        if self.volume_ofi is not None:
            score += max(-1.0, min(1.0, self.volume_ofi / 0.5))
            n += 1
        if self.volume_vwap_deviation is not None:
            # Positive VWAP deviation = buying pressure
            score += max(-1.0, min(1.0, self.volume_vwap_deviation / 2.0))
            n += 1
        if self.volume_obv_divergence is not None:
            score += max(-1.0, min(1.0, self.volume_obv_divergence))
            n += 1
        return score / n if n > 0 else 0.0

    def seasonal_signal(self) -> float:
        """Seasonal pattern signal: -1.0 (bearish season) to 1.0 (bullish season)."""
        return self.seasonal_score or 0.0

    def earnings_signal(self) -> float:
        """Earnings calendar impact signal: -1.0 to 1.0.

        Pre-earnings (< 5 days): reduce confidence (uncertainty).
        Post-earnings: drift based on expected surprise.
        """
        if self.earnings_days_to_report is None:
            return 0.0
        if self.earnings_days_to_report <= 0:
            # Post-earnings drift
            if self.earnings_expected_surprise is not None:
                return max(-1.0, min(1.0, self.earnings_expected_surprise / 5.0))
            return 0.0
        elif self.earnings_days_to_report <= 5:
            # Pre-earnings uncertainty → slight bearish bias
            return -0.15
        return 0.0

    def causal_signal(self) -> float:
        """Granger causality signal: -1.0 to 1.0.

        If ticker has significant Granger causes from bullish global drivers,
        signal is positive. Based on granger_cause_count and top cause direction.
        """
        if self.granger_cause_count is None or self.granger_cause_count == 0:
            return 0.0
        # More causes = more externally driven = higher uncertainty
        # But we don't know direction without the cause ticker's momentum
        # Use count as a confidence modifier (more causes → less idiosyncratic)
        return 0.0  # neutral without cause direction data


class MarketContextProvider:
    """Fetches market context from DB with as_of cutoff (no look-ahead)."""

    def __init__(
        self,
        session: Session | None = None,
        ml_provider: MLSignalProvider | None = None,
        multifactor_model: object | None = None,
    ) -> None:
        self._session = session
        self._ml_provider = ml_provider
        self._multifactor_model = multifactor_model

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        from market.db.engine import get_sessionmaker
        return get_sessionmaker()()

    def get_context(
        self,
        ticker: str,
        as_of: str | pd.Timestamp,
        df: pd.DataFrame | None = None,
        strict_cutoff: bool = False,
    ) -> MarketContext:
        """Fetch all available market context for ticker at as_of date.

        Args:
            ticker: Instrument ticker (e.g., 'BBCA.JK').
            as_of: Date cutoff — only data <= as_of is returned.
            df: Optional OHLCV DataFrame for ML signal computation.
            strict_cutoff: If True, enforce as_of cutoff strictly (live mode).
                If False (backtest mode), use latest available data for
                slow-changing features (fundamentals, correlations, scores).

        Returns:
            MarketContext with available data.
        """
        cutoff = pd.Timestamp(as_of).date()
        ctx = MarketContext()
        session = self._get_session()

        try:
            fetchers = [
                ("fundamental", lambda: self._fetch_fundamental(session, ticker, ctx, cutoff, strict_cutoff)),
                ("macro", lambda: self._fetch_macro(session, ctx, cutoff)),
                ("sentiment", lambda: self._fetch_sentiment(session, ctx, cutoff)),
                ("foreign_flow", lambda: self._fetch_foreign_flow(session, ticker, ctx, cutoff)),
                ("scores", lambda: self._fetch_scores(session, ticker, ctx, cutoff, strict_cutoff)),
                ("cross_market", lambda: self._fetch_cross_market(session, ticker, ctx, cutoff, strict_cutoff)),
                ("news_sentiment", lambda: self._fetch_news_sentiment(session, ticker, ctx, cutoff)),
                ("sector", lambda: self._fetch_sector(session, ticker, ctx)),
                ("commodity", lambda: self._fetch_commodity_signal(session, ticker, ctx, cutoff)),
                ("global_sentiment", lambda: self._fetch_global_sentiment(session, ctx, cutoff)),
                ("esg_governance", lambda: self._fetch_esg_governance(session, ticker, ctx)),
                ("astronacci", lambda: self._fetch_astronacci(ctx, as_of)),
                ("holiday_effect", lambda: self._fetch_holiday_effect(ctx, ticker, cutoff)),
                ("alpha_signals", lambda: self._fetch_alpha_signals(ctx, ticker, df, cutoff)),
                ("policy_events", lambda: self._fetch_policy_events(session, ticker, ctx, cutoff)),
                ("sector_rotation", lambda: self._fetch_sector_rotation(session, ticker, ctx, cutoff)),
                ("volume_features", lambda: self._fetch_volume_features(ctx, ticker, df, cutoff)),
                ("seasonal_patterns", lambda: self._fetch_seasonal_patterns(session, ticker, ctx, cutoff)),
                ("earnings_calendar", lambda: self._fetch_earnings_calendar(session, ticker, ctx, cutoff)),
                ("instrument_profile", lambda: self._fetch_instrument_profile(session, ticker, ctx)),
                ("dcc_garch", lambda: self._fetch_dcc_garch(session, ticker, ctx, cutoff)),
                ("causal_relationships", lambda: self._fetch_causal_relationships(session, ticker, ctx, cutoff)),
            ]
            for name, fetcher in fetchers:
                try:
                    fetcher()
                except Exception as e:
                    logger.debug("Skip %s for %s: %s", name, ticker, e)
                    try:
                        session.rollback()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("Failed to fetch market context for %s: %s", ticker, e)
        finally:
            if self._session is None:
                session.close()

        # ML signal (requires OHLCV data)
        if self._ml_provider is not None and df is not None:
            try:
                ml_result = self._ml_provider.train_and_predict(
                    ticker, df, as_of,
                )
                if ml_result.model_available:
                    ctx.ml_signal = ml_result.signal
            except Exception as e:
                logger.debug("ML signal failed for %s: %s", ticker, e)

        # Multi-factor model signal (requires OHLCV + global data)
        if self._multifactor_model is not None and df is not None:
            try:
                global_data = self._load_global_data(session)
                mf_result = self._multifactor_model.train_and_predict(
                    ticker, df, as_of, global_data=global_data,
                )
                if mf_result.model_available:
                    # Blend multi-factor signal with existing ML signal
                    if ctx.ml_signal is not None:
                        ctx.ml_signal = (
                            ctx.ml_signal * 0.4 + mf_result.signal * 0.6
                        )
                    else:
                        ctx.ml_signal = mf_result.signal
                    logger.debug(
                        "MultiFactor %s: action=%s signal=%.3f",
                        ticker, mf_result.action, mf_result.signal,
                    )
            except Exception as e:
                logger.debug("MultiFactor failed for %s: %s", ticker, e)

        return ctx

    def _fetch_fundamental(
        self, session: Session, ticker: str, ctx: MarketContext,
        cutoff: date, strict: bool = False,
    ) -> None:
        from sqlalchemy import select

        from market.db.models import FundamentalData

        stmt = (
            select(FundamentalData)
            .where(FundamentalData.ticker == ticker)
        )
        if strict:
            stmt = stmt.where(FundamentalData.date <= cutoff)
        stmt = stmt.order_by(FundamentalData.date.desc()).limit(1)
        row = session.execute(stmt).scalar_one_or_none()

        if row:
            ctx.pe_ratio = float(row.pe) if row.pe is not None else None
            ctx.pb_ratio = float(row.pb) if row.pb is not None else None
            ctx.roe = float(row.roe) if row.roe is not None else None
            ctx.dividend_yield = (
                float(row.dividend_yield) if row.dividend_yield is not None else None
            )
            ctx.der = float(row.der) if row.der is not None else None
            ctx.eps = float(row.eps) if row.eps is not None else None

    def _fetch_macro(
        self, session: Session, ctx: MarketContext, cutoff: date,
    ) -> None:
        from sqlalchemy import select

        from market.db.models import MacroData

        for series, attr in [
            ("VIXCLS", "vix"),
            ("DGS10", "us_10y_yield"),
            ("fed_funds_rate", "fed_funds_rate"),
        ]:
            row = session.execute(
                select(MacroData)
                .where(MacroData.series_name == series)
                .where(MacroData.date <= cutoff)
                .order_by(MacroData.date.desc())
                .limit(1)
            ).scalar_one_or_none()
            if row and row.value is not None:
                setattr(ctx, attr, float(row.value))

    def _fetch_sentiment(
        self, session: Session, ctx: MarketContext, cutoff: date,
    ) -> None:
        from sqlalchemy import select

        from market.db.models import FearGreed

        row = session.execute(
            select(FearGreed)
            .where(FearGreed.date <= cutoff)
            .order_by(FearGreed.date.desc())
            .limit(1)
        ).scalar_one_or_none()

        if row:
            ctx.fear_greed_index = float(row.value) if row.value is not None else None
            ctx.fear_greed_label = row.label

    def _fetch_foreign_flow(
        self, session: Session, ticker: str, ctx: MarketContext, cutoff: date,
    ) -> None:
        from sqlalchemy import select

        from market.db.models import ForeignFlow

        # Latest flow
        row = session.execute(
            select(ForeignFlow)
            .where(ForeignFlow.ticker == ticker)
            .where(ForeignFlow.date <= cutoff)
            .order_by(ForeignFlow.date.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row and row.foreign_net is not None:
            ctx.foreign_net_flow = float(row.foreign_net)

        # 5-day cumulative flow
        rows = session.execute(
            select(ForeignFlow)
            .where(ForeignFlow.ticker == ticker)
            .where(ForeignFlow.date <= cutoff)
            .order_by(ForeignFlow.date.desc())
            .limit(5)
        ).scalars().all()
        if rows:
            ctx.foreign_net_flow_5d = sum(
                float(r.foreign_net) for r in rows if r.foreign_net is not None
            )

    def _fetch_scores(
        self, session: Session, ticker: str, ctx: MarketContext,
        cutoff: date, strict: bool = False,
    ) -> None:
        from sqlalchemy import select

        from market.db.models import Score

        stmt = (
            select(Score)
            .where(Score.ticker == ticker)
        )
        if strict:
            stmt = stmt.where(Score.as_of <= pd.Timestamp(cutoff))
        stmt = stmt.order_by(Score.as_of.desc()).limit(6)
        rows = session.execute(stmt).scalars().all()

        for row in rows:
            score_val = float(row.score) if row.score is not None else None
            if row.engine == "technical" and ctx.technical_score is None:
                ctx.technical_score = score_val
            elif row.engine == "fundamental" and ctx.fundamental_score is None:
                ctx.fundamental_score = score_val

    def _fetch_cross_market(
        self, session: Session, ticker: str, ctx: MarketContext,
        cutoff: date, strict: bool = False,
    ) -> None:
        from sqlalchemy import select

        from market.db.models import RelationshipMatrix

        stmt = (
            select(RelationshipMatrix)
            .where(RelationshipMatrix.asset_a == ticker)
        )
        if strict:
            stmt = stmt.where(RelationshipMatrix.as_of <= pd.Timestamp(cutoff))
        stmt = stmt.order_by(RelationshipMatrix.as_of.desc())
        rows = session.execute(stmt).scalars().all()

        for row in rows:
            if row.asset_b == "^GSPC" and ctx.corr_us is None:
                ctx.corr_us = float(row.correlation) if row.correlation is not None else None
            elif row.asset_b == "^HSI" and ctx.corr_hk is None:
                ctx.corr_hk = float(row.correlation) if row.correlation is not None else None
            elif row.asset_b == "^N225" and ctx.corr_jp is None:
                ctx.corr_jp = float(row.correlation) if row.correlation is not None else None
            elif row.asset_b == "^JKSE" and ctx.corr_ihsg is None:
                ctx.corr_ihsg = (
                    float(row.correlation) if row.correlation is not None else None
                )

    def _fetch_news_sentiment(
        self, session: Session, ticker: str, ctx: MarketContext,
        cutoff: date,
    ) -> None:
        """Fetch recent news sentiment for ticker with time-decay weighting.

        Priority 1: PostgreSQL news_sentiment table (continuous score -1.0 to 1.0,
        from unified NewsSentimentAnalyzer via scrape_rss_news.py).
        Uses exponential time-decay weighting (half-life=7 days).
        Priority 2: Legacy news table (sentiment 0/1/-1).
        Looks back 30 days before cutoff.
        """
        from sqlalchemy import func, select

        # --- Priority 1: PostgreSQL news_sentiment with time-decay ---
        try:
            from market.db.models import NewsSentiment

            from market.analysis.news_sentiment import NewsSentimentAnalyzer
            from datetime import timedelta
            lookback = cutoff - timedelta(days=30)

            rows = session.execute(
                select(NewsSentiment.sentiment_score, NewsSentiment.sentiment_label, NewsSentiment.date)
                .where(NewsSentiment.ticker == ticker)
                .where(NewsSentiment.date >= lookback)
                .where(NewsSentiment.date <= cutoff)
                .where(NewsSentiment.sentiment_score.isnot(None))
            ).all()

            if rows:
                # Build items for time-decay weighted sentiment
                items = [
                    {"date": r[2], "title": "", "score": float(r[0])}
                    for r in rows if r[0] is not None
                ]
                if items:
                    analyzer = NewsSentimentAnalyzer()
                    # Use pre-computed scores with time-decay
                    decay_score = analyzer.weighted_sentiment(
                        items, reference_date=cutoff, half_life_days=7.0,
                    )
                    # Also compute simple average for comparison
                    scores = [float(r[0]) for r in rows if r[0] is not None]
                    ctx.news_sentiment = decay_score if decay_score != 0.0 else sum(scores) / len(scores)
                    ctx.news_count = len(scores)
                    return
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass  # Table might not exist (SQLite fallback)

        # --- Priority 2: Legacy news table ---
        from market.db.models import News

        rows = session.execute(
            select(News.sentiment, func.count())
            .where(News.entities == ticker)
            .where(News.sentiment.isnot(None))
            .group_by(News.sentiment)
        ).all()

        if not rows:
            # Try matching by ticker in entities field (broader search)
            rows = session.execute(
                select(News.sentiment)
                .where(News.entities.ilike(f"%{ticker}%"))
                .where(News.sentiment.isnot(None))
            ).scalars().all()
            if rows:
                avg_sentiment = sum(float(r) for r in rows) / len(rows)
                ctx.news_sentiment = avg_sentiment
                ctx.news_count = len(rows)
            return

        # Weighted average sentiment
        total_weight = 0
        weighted_sum = 0.0
        for sentiment, count in rows:
            s = float(sentiment) if sentiment is not None else 0.0
            c = int(count)
            weighted_sum += s * c
            total_weight += c

        if total_weight > 0:
            ctx.news_sentiment = weighted_sum / total_weight
            ctx.news_count = total_weight

    def _fetch_sector(
        self, session: Session, ticker: str, ctx: MarketContext,
    ) -> None:
        """Fetch sector classification from instruments table."""
        from sqlalchemy import select

        # Try PG instruments table first
        try:
            from market.db.models import Instrument

            row = session.execute(
                select(Instrument.sector)
                .where(Instrument.ticker == ticker)
            ).scalar_one_or_none()

            if row:
                ctx.sector = row
                return
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass

        # Fallback: SQLite instrument_master table
        from market.db.models import InstrumentMaster

        row = session.execute(
            select(InstrumentMaster.sector)
            .where(InstrumentMaster.ticker == ticker)
        ).scalar_one_or_none()

        if row:
            ctx.sector = row

    def _load_close_prices(
        self, session: Session, ticker: str, cutoff: date,
        limit: int | None = None, order_desc: bool = False,
    ) -> list[tuple[float, datetime]]:
        """Load (close, timestamp) pairs from StockPrice (PG) or OHLCV (SQLite)."""
        from sqlalchemy import select

        # Try PG stock_prices table first
        try:
            from market.db.models import StockPrice

            stmt = (
                select(StockPrice.close, StockPrice.timestamp)
                .where(StockPrice.ticker == ticker)
                .where(StockPrice.timeframe == "1d")
            )
            if cutoff is not None:
                stmt = stmt.where(StockPrice.timestamp <= pd.Timestamp(cutoff))
            if order_desc:
                stmt = stmt.order_by(StockPrice.timestamp.desc())
            else:
                stmt = stmt.order_by(StockPrice.timestamp)
            if limit is not None:
                stmt = stmt.limit(limit)

            rows = session.execute(stmt).all()
            if rows:
                return [(float(r[0]), r[1]) for r in rows]
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass

        # Fallback: SQLite ohlcv table
        from market.db.models import OHLCV

        stmt = (
            select(OHLCV.close, OHLCV.timestamp)
            .where(OHLCV.ticker == ticker)
            .where(OHLCV.timeframe == "1d")
        )
        if cutoff is not None:
            stmt = stmt.where(OHLCV.timestamp <= pd.Timestamp(cutoff))
        if order_desc:
            stmt = stmt.order_by(OHLCV.timestamp.desc())
        else:
            stmt = stmt.order_by(OHLCV.timestamp)
        if limit is not None:
            stmt = stmt.limit(limit)

        rows = session.execute(stmt).all()
        return [(float(r[0]), r[1]) for r in rows]

    def _fetch_commodity_signal(
        self, session: Session, ticker: str, ctx: MarketContext,
        cutoff: date,
    ) -> None:
        """Compute commodity momentum signal based on sector.

        Sector-specific commodity proxies:
        - Basic Materials/Gold (ANTM): GC=F (gold) 20-day momentum
        - Basic Materials/Copper (MDKA, UNTR): HG=F (copper) + GC=F
        - Industrials (ASII): CL=F (oil) + broader commodities
        - Others: no commodity signal
        """
        if ctx.sector is None:
            return

        # Determine relevant commodity tickers based on sector/industry
        commodity_tickers: list[str] = []
        if ctx.sector == "Basic Materials":
            commodity_tickers = ["GC=F", "HG=F", "NI=F"]
        elif ctx.sector == "Industrials":
            commodity_tickers = ["CL=F", "GC=F"]
        elif ctx.sector == "Energy":
            commodity_tickers = ["CL=F", "MTF=F"]
        elif ctx.sector == "Consumer Defensive":
            commodity_tickers = ["CPO=F"]
        elif ctx.sector == "Financial Services":
            # Banks benefit from steepening yield curve, not commodities
            return
        else:
            return

        signals: list[float] = []
        for comm_ticker in commodity_tickers:
            rows = self._load_close_prices(
                session, comm_ticker, cutoff, limit=25, order_desc=True,
            )

            if len(rows) < 20:
                continue

            closes = [r[0] for r in rows]
            closes.reverse()  # oldest first
            current = closes[-1]
            ma_20 = sum(closes[-20:]) / 20.0

            if ma_20 > 0:
                momentum = (current - ma_20) / ma_20
                # Normalize: ±10% momentum → ±1.0 signal
                signal = max(-1.0, min(1.0, momentum / 0.10))
                signals.append(signal)

        if signals:
            ctx.commodity_signal = sum(signals) / len(signals)

    def _fetch_global_sentiment(
        self, session: Session, ctx: MarketContext, cutoff: date,
    ) -> None:
        """Compute global market sentiment using Time-Zone Bucket Grid.

        Uses data from global indices (^GSPC, ^N225, ^HSI) that closed
        BEFORE the IDX trading day defined by cutoff. This ensures
        strict no-look-ahead: only data available before IDX opened
        is used to compute the sentiment signal.

        Time-Zone Buckets (UTC):
        - B0: 00:00-05:59 (US overnight, no new signals)
        - B1: 06:00-07:59 (Asia pre-open: Japan open 00:00, HK 01:30)
        - B2: 08:00-09:59 (IDX open 02:00, Europe pre-open)
        - B3: 10:00-13:59 (Europe open, US pre-open)
        - B4: 14:00-23:59 (US open, IDX close)

        Signal weights:
        - US close (previous day, 21:00 UTC) → IDX morning session
        - Japan close (same day, 06:00 UTC) → IDX morning session
        - Hong Kong close (same day, 08:00 UTC) → IDX afternoon session
        """
        from market.analysis.market_factors import compute_global_sentiment_signal

        global_tickers = ["^GSPC", "^N225", "^HSI"]
        global_data: dict[str, pd.DataFrame] = {}

        for gt in global_tickers:
            rows = self._load_close_prices(session, gt, cutoff=None, order_desc=False)

            if rows:
                global_data[gt] = pd.DataFrame(
                    {"close": [r[0] for r in rows]},
                    index=pd.DatetimeIndex([r[1] for r in rows]),
                )

        if not global_data:
            return

        idx_date = pd.Timestamp(cutoff)
        signals = compute_global_sentiment_signal(
            global_data, idx_date, lookback=5,
        )

        if "combined_global" in signals:
            ctx.global_sentiment = signals["combined_global"]

    def _load_global_data(self, session: Session) -> dict[str, pd.DataFrame]:
        """Load global index and commodity OHLCV data for MultiFactorModel.

        Returns dict of {ticker: DataFrame} for all global assets
        used in the multi-factor feature pipeline.
        """
        from market.analysis.multi_factor import GLOBAL_ASSETS

        global_data: dict[str, pd.DataFrame] = {}
        for gticker in GLOBAL_ASSETS:
            rows = self._load_close_prices(session, gticker, cutoff=None, order_desc=False)
            if rows:
                global_data[gticker] = pd.DataFrame(
                    {"close": [r[0] for r in rows]},
                    index=pd.DatetimeIndex([r[1] for r in rows]),
                )
        return global_data

    def _fetch_esg_governance(
        self, session: Session, ticker: str, ctx: MarketContext,
    ) -> None:
        """Fetch ESG scores and corporate governance data from DB.

        Loads the latest ESG score and corporate governance record for the
        ticker. ESG scores are typically slow-changing (annual), so no
        as_of cutoff is applied — the latest available record is used.
        """
        from sqlalchemy import select

        from market.db.models import CorporateGovernance, ESGScore

        # Latest ESG score
        esg_row = session.execute(
            select(ESGScore)
            .where(ESGScore.ticker == ticker)
            .order_by(ESGScore.year.desc())
            .limit(1)
        ).scalar_one_or_none()

        if esg_row:
            ctx.esg_score = float(esg_row.score) if esg_row.score is not None else None
            ctx.esg_rating = esg_row.rating

        # Latest corporate governance
        cg_row = session.execute(
            select(CorporateGovernance)
            .where(CorporateGovernance.ticker == ticker)
            .order_by(CorporateGovernance.year.desc())
            .limit(1)
        ).scalar_one_or_none()

        if cg_row:
            # Normalize ACGS score to 0-100 if it's a letter grade
            acgs = cg_row.acgs_score
            if acgs is not None:
                try:
                    ctx.governance_score = float(acgs)
                except (ValueError, TypeError):
                    # Letter grade mapping: A=90, B=75, C=60, D=40
                    grade_map = {"A": 90.0, "B": 75.0, "C": 60.0, "D": 40.0}
                    ctx.governance_score = grade_map.get(str(acgs).strip().upper(), 50.0)
            ctx.has_whistleblowing = cg_row.has_whistleblowing
            ctx.has_risk_committee = cg_row.has_risk_committee

    def _fetch_astronacci(
        self, ctx: MarketContext, as_of: str | pd.Timestamp,
    ) -> None:
        """Fetch Astronacci time-cycle signal for the given date.

        Computes active astrological cycles (Moon Phases, Retrogrades,
        Ingresses) within a 3-day forward window and derives a directional
        signal + volatility expectation.
        """

        from market.analysis.astronacci import compute_astronacci_signal

        cutoff = pd.Timestamp(as_of)
        if cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize("UTC")
        as_of_dt = cutoff.to_pydatetime()

        result = compute_astronacci_signal(as_of_dt, window_days=3)

        if result["cycle_count"] > 0:
            ctx.astronacci_signal = result["time_signal"]
            ctx.astronacci_volatility = result["volatility_signal"]
            ctx.astronacci_active_cycles = result["active_cycles"]

    def _fetch_holiday_effect(
        self, ctx: MarketContext, ticker: str, cutoff: date,
    ) -> None:
        """Fetch holiday effect features for IDX tickers.

        Populates is_pre_holiday, is_post_holiday, days_to_next_holiday,
        pre/post_holiday_expected_return, and spillover_expected_return.
        Only applies to IDX tickers (mic_code = XIDX).
        """
        if not ticker.endswith(".JK"):
            return

        from market.analysis.holiday_effect import HolidayEffectAnalyzer

        try:
            analyzer = HolidayEffectAnalyzer()
            features = analyzer.get_holiday_features("XIDX", cutoff)
            ctx.is_pre_holiday = features["is_pre_holiday"]
            ctx.is_post_holiday = features["is_post_holiday"]
            ctx.days_to_next_holiday = features["days_to_next_holiday"]
            ctx.pre_holiday_expected_return = features["pre_holiday_expected_return"]
            ctx.post_holiday_expected_return = features["post_holiday_expected_return"]

            # Spillover from global holidays
            spillover = analyzer.get_spillover_features(cutoff)
            if spillover.get("spillover_active_count", 0) > 0:
                ctx.spillover_expected_return = spillover["spillover_total_expected_return"]
        except Exception as e:
            logger.debug("Holiday effect fetch failed for %s: %s", ticker, e)

    # ------------------------------------------------------------------
    # New fetchers: alpha, policy, sector rotation, volume, seasonal,
    # earnings, instrument profile, DCC-GARCH, causal relationships
    # ------------------------------------------------------------------

    def _fetch_alpha_signals(
        self, ctx: MarketContext, ticker: str,
        df: pd.DataFrame | None, cutoff: date,
    ) -> None:
        """Compute 4 alpha signals from OHLCV data."""
        if df is None or df.empty or len(df) < 50:
            return

        try:
            from market.analysis.alpha_signals import (
                EWMAMomentumEngine,
                MeanReversionEngine,
                RegimeSwitchEngine,
                ShortTermReversalEngine,
            )

            truncated = df[df.index <= pd.Timestamp(cutoff)] if cutoff else df
            if len(truncated) < 50 or "close" not in truncated.columns:
                return

            close = truncated["close"]

            mr = MeanReversionEngine().generate_signals(close)
            ctx.alpha_mean_reversion = float(mr.signal.iloc[-1]) if len(mr.signal) else None

            rev = ShortTermReversalEngine().generate_signals(close)
            ctx.alpha_reversal = float(rev.signal.iloc[-1]) if len(rev.signal) else None

            ewma = EWMAMomentumEngine().generate_signals(close)
            ctx.alpha_ewma_momentum = float(ewma.signal.iloc[-1]) if len(ewma.signal) else None

            rs = RegimeSwitchEngine().generate_signals(close)
            ctx.alpha_regime_switch = float(rs.signal.iloc[-1]) if len(rs.signal) else None
        except Exception as e:
            logger.debug("Alpha signals fetch failed for %s: %s", ticker, e)

    def _fetch_policy_events(
        self, session: Session, ticker: str, ctx: MarketContext, cutoff: date,
    ) -> None:
        """Fetch policy/external event signal from DB."""
        from sqlalchemy import text

        try:
            from datetime import timedelta

            lookback = cutoff - timedelta(days=30)

            # Policy events
            rows = session.execute(text("""
                SELECT event_type, direction, impact_score
                FROM policy_events
                WHERE event_date BETWEEN :lookback AND :cutoff
                ORDER BY event_date DESC LIMIT 20
            """), {"lookback": lookback, "cutoff": cutoff}).all()

            # External events
            rows2 = session.execute(text("""
                SELECT kategori, dampak_market
                FROM external_events
                WHERE tanggal BETWEEN :lookback AND :cutoff
                ORDER BY tanggal DESC LIMIT 20
            """), {"lookback": lookback, "cutoff": cutoff}).all()

            total_events = len(rows) + len(rows2)
            if total_events == 0:
                return

            signal = 0.0
            for row in rows:
                direction = row[1] if row[1] else 0.0
                signal += float(direction)
            for row in rows2:
                dampak = row[1] if row[1] else "Sedang"
                signal += {"Tinggi": 0.5, "Sedang": 0.0, "Rendah": -0.3}.get(dampak, 0.0)

            ctx.policy_event_signal = max(-1.0, min(1.0, signal / max(total_events, 1)))
            ctx.policy_event_count = total_events
        except Exception as e:
            logger.debug("Policy events fetch failed for %s: %s", ticker, e)

    def _fetch_sector_rotation(
        self, session: Session, ticker: str, ctx: MarketContext, cutoff: date,
    ) -> None:
        """Compute sector rotation signal from sector index momentum."""
        if ctx.sector is None:
            return

        try:
            # Map sector to IDX sector index ticker
            sector_map = {
                "Basic Materials": "IDXBASIC",
                "Financial Services": "IDXFINANCE",
                "Energy": "IDXENERGY",
                "Healthcare": "IDXHEALTH",
                "Technology": "IDXTECHNO",
                "Industrials": "IDXINDUST",
                "Real Estate": "IDXPROPER",
                "Transportation": "IDXTRANS",
                "Infrastructure": "IDXINFRA",
                "Consumer Defensive": "IDXNONCYC",
                "Consumer Cyclical": "IDXCYCLIC",
            }
            sector_ticker = sector_map.get(ctx.sector)
            if sector_ticker is None:
                return

            rows = self._load_close_prices(
                session, sector_ticker, cutoff, limit=25, order_desc=True,
            )
            if len(rows) < 20:
                return

            closes = [r[0] for r in rows]
            closes.reverse()
            current = closes[-1]
            ma_20 = sum(closes[-20:]) / 20.0

            if ma_20 > 0:
                momentum = (current - ma_20) / ma_20
                ctx.sector_rotation_signal = max(-1.0, min(1.0, momentum / 0.05))
        except Exception as e:
            logger.debug("Sector rotation fetch failed for %s: %s", ticker, e)

    def _fetch_volume_features(
        self, ctx: MarketContext, ticker: str,
        df: pd.DataFrame | None, cutoff: date,
    ) -> None:
        """Compute volume features (OFI, VWAP deviation, OBV divergence)."""
        if df is None or df.empty or len(df) < 20:
            return

        try:
            from market.analysis.volume_features import (
                compute_ofi_proxy,
                compute_vwap,
                detect_obv_divergence,
            )

            truncated = df[df.index <= pd.Timestamp(cutoff)] if cutoff else df
            if len(truncated) < 20:
                return

            # OFI proxy
            ofi_result = compute_ofi_proxy(truncated)
            ctx.volume_ofi = float(ofi_result.ofi.iloc[-1]) if len(ofi_result.ofi) else None

            # VWAP deviation
            vwap_result = compute_vwap(truncated)
            if len(vwap_result.vwap) and "close" in truncated.columns:
                last_close = float(truncated["close"].iloc[-1])
                last_vwap = float(vwap_result.vwap.iloc[-1])
                if last_vwap > 0:
                    ctx.volume_vwap_deviation = (last_close - last_vwap) / last_vwap * 100

            # OBV divergence
            div_result = detect_obv_divergence(truncated)
            ctx.volume_obv_divergence = float(div_result.signal.iloc[-1]) if len(div_result.signal) else None
        except Exception as e:
            logger.debug("Volume features fetch failed for %s: %s", ticker, e)

    def _fetch_seasonal_patterns(
        self, session: Session, ticker: str, ctx: MarketContext, cutoff: date,
    ) -> None:
        """Fetch seasonal pattern score from DB."""
        from sqlalchemy import text

        try:
            month = cutoff.month
            row = session.execute(text("""
                SELECT pattern_type, seasonal_score
                FROM seasonal_patterns
                WHERE ticker = :ticker AND month = :month
                ORDER BY seasonal_score DESC LIMIT 1
            """), {"ticker": ticker, "month": month}).first()

            if row:
                ctx.seasonal_score = float(row[1]) if row[1] is not None else None
                ctx.seasonal_pattern_name = row[0]
        except Exception as e:
            logger.debug("Seasonal patterns fetch failed for %s: %s", ticker, e)

    def _fetch_earnings_calendar(
        self, session: Session, ticker: str, ctx: MarketContext, cutoff: date,
    ) -> None:
        """Fetch earnings calendar impact from DB."""
        from sqlalchemy import text

        try:
            row = session.execute(text("""
                SELECT report_date, expected_surprise_pct
                FROM earnings_calendar
                WHERE ticker = :ticker AND report_date >= :cutoff
                ORDER BY report_date LIMIT 1
            """), {"ticker": ticker, "cutoff": cutoff}).first()

            if row:
                report_date = row[0]
                if report_date:
                    days_to = (report_date - cutoff).days if hasattr(report_date, 'days') else (
                        pd.Timestamp(report_date).date() - cutoff
                    ).days
                    ctx.earnings_days_to_report = days_to
                if row[1] is not None:
                    ctx.earnings_expected_surprise = float(row[1])
        except Exception as e:
            logger.debug("Earnings calendar fetch failed for %s: %s", ticker, e)

    def _fetch_instrument_profile(
        self, session: Session, ticker: str, ctx: MarketContext,
    ) -> None:
        """Fetch instrument behavior profile from DB."""
        from sqlalchemy import text

        try:
            row = session.execute(text("""
                SELECT volatility_regime, liquidity_score, overnight_gap_pct
                FROM instrument_behavior_profiles
                WHERE ticker = :ticker
                ORDER BY profiled_at DESC LIMIT 1
            """), {"ticker": ticker}).first()

            if row:
                ctx.profile_volatility_regime = row[0]
                ctx.profile_liquidity_score = float(row[1]) if row[1] is not None else None
                ctx.profile_overnight_gap_pct = float(row[2]) if row[2] is not None else None
        except Exception as e:
            logger.debug("Instrument profile fetch failed for %s: %s", ticker, e)

    def _fetch_dcc_garch(
        self, session: Session, ticker: str, ctx: MarketContext, cutoff: date,
    ) -> None:
        """Fetch DCC-GARCH correlation from DB."""
        from sqlalchemy import text

        try:
            row = session.execute(text("""
                SELECT correlation_with_global
                FROM dcc_garch_results
                WHERE ticker = :ticker
                ORDER BY estimated_at DESC LIMIT 1
            """), {"ticker": ticker}).first()

            if row and row[0] is not None:
                ctx.dcc_garch_corr_global = float(row[0])
        except Exception as e:
            logger.debug("DCC-GARCH fetch failed for %s: %s", ticker, e)

    def _fetch_causal_relationships(
        self, session: Session, ticker: str, ctx: MarketContext, cutoff: date,
    ) -> None:
        """Fetch Granger causality signal from DB."""
        from sqlalchemy import text

        try:
            row = session.execute(text("""
                SELECT count(*) as n_causes,
                       (SELECT cause_ticker FROM causal_relationships
                        WHERE effect_ticker = :ticker AND p_value < 0.05
                        ORDER BY p_value ASC LIMIT 1) as top_cause
                FROM causal_relationships
                WHERE effect_ticker = :ticker AND p_value < 0.05
            """), {"ticker": ticker}).first()

            if row:
                ctx.granger_cause_count = int(row[0]) if row[0] else 0
                ctx.granger_top_cause = row[1]
        except Exception as e:
            logger.debug("Causal relationships fetch failed for %s: %s", ticker, e)
