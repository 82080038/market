"""Prediction engine with no-look-ahead bias and error memory (pustaka/23, pustaka/29, pustaka/67).

Predicts next-period price/direction using ONLY data up to as_of date.
Tracks prediction errors, identifies root causes, and stores them as
risk factors for future decision-making.

Key principles:
1. NO LOOK-AHEAD: Only data up to as_of is used for prediction.
2. ERROR TRACKING: Every prediction is compared to actual outcome.
3. ROOT CAUSE ANALYSIS: When prediction errors occur, the system
   identifies why (regime change, volatility spike, pattern failure, etc.).
4. RISK MEMORY: Errors are stored as risk factors that influence
   future position sizing and execution decisions.
5. SELF-EVOLUTION: Error patterns feed into SelfEvolutionAgent for
   autonomous model adjustment.

Prediction methods:
- MA-based: Simple moving average extrapolation
- Momentum: Rate-of-change based prediction
- Pattern-based: Prediction from detected pattern direction
- Volatility-adjusted: Prediction adjusted for ATR
- Ensemble: Weighted combination of all methods
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from market.analysis.pattern_detector import PatternDetection, PatternDetector

# Module-level cache for exogenous data (FX, Shanghai) loaded once per process
_fx_cache: pd.DataFrame | None = None
_shanghai_cache: pd.DataFrame | None = None


def _load_fx_cache() -> pd.DataFrame | None:
    """Load USD/IDR FX data once and cache."""
    global _fx_cache
    if _fx_cache is not None:
        return _fx_cache
    try:
        from market.db.raw import get_raw_connection, _PgConnWrapper

        def _rc(c):
            return c._conn if isinstance(c, _PgConnWrapper) else c

        with get_raw_connection() as conn:
            _fx_cache = pd.read_sql(
                "SELECT timestamp as date, close FROM ohlcv WHERE ticker='IDR=X' ORDER BY timestamp",
                _rc(conn),
            )
            if not _fx_cache.empty:
                _fx_cache["date"] = pd.to_datetime(_fx_cache["date"])
                _fx_cache = _fx_cache.set_index("date")
    except Exception:
        _fx_cache = pd.DataFrame()
    return _fx_cache


def _load_shanghai_cache() -> pd.DataFrame | None:
    """Load Shanghai Composite data once and cache."""
    global _shanghai_cache
    if _shanghai_cache is not None:
        return _shanghai_cache
    try:
        from market.db.raw import get_raw_connection, _PgConnWrapper

        def _rc(c):
            return c._conn if isinstance(c, _PgConnWrapper) else c

        with get_raw_connection() as conn:
            _shanghai_cache = pd.read_sql(
                "SELECT timestamp as date, close FROM ohlcv WHERE ticker='000001.SS' ORDER BY timestamp",
                _rc(conn),
            )
            if not _shanghai_cache.empty:
                _shanghai_cache["date"] = pd.to_datetime(_shanghai_cache["date"])
                _shanghai_cache = _shanghai_cache.set_index("date")
    except Exception:
        _shanghai_cache = pd.DataFrame()
    return _shanghai_cache

if TYPE_CHECKING:
    from market.analysis.delisting_memory import DelistingMemory
    from market.analysis.market_context import MarketContext, MarketContextProvider


class PredictionMethod(Enum):
    """Available prediction methods."""

    MA_BASED = "ma_based"
    MOMENTUM = "momentum"
    PATTERN_BASED = "pattern_based"
    VOLATILITY_ADJUSTED = "volatility_adjusted"
    ENSEMBLE = "ensemble"


class ErrorCategory(Enum):
    """Categories of prediction errors for root cause analysis."""

    REGIME_CHANGE = "regime_change"
    VOLATILITY_SPIKE = "volatility_spike"
    PATTERN_FAILURE = "pattern_failure"
    DATA_ANOMALY = "data_anomaly"
    MODEL_LIMITATION = "model_limitation"
    LIQUIDITY_EVENT = "liquidity_event"
    UNKNOWN = "unknown"


@dataclass
class Prediction:
    """A prediction for an instrument at a point in time."""

    ticker: str
    as_of: str
    method: PredictionMethod
    predicted_price: float
    predicted_direction: str  # up, down, flat
    predicted_return_pct: float
    confidence: float
    horizon_days: int
    indicators_used: dict[str, float] = field(default_factory=dict)
    pattern_signals: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class PredictionError:
    """A prediction error with root cause analysis."""

    error_id: str
    ticker: str
    as_of: str
    method: PredictionMethod
    predicted_price: float
    actual_price: float
    predicted_direction: str
    actual_direction: str
    error_pct: float
    direction_correct: bool
    error_category: ErrorCategory
    root_cause: str
    lesson: str
    risk_weight: float  # How much to weight this error in future risk calc
    recorded_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class PredictionLogEntry:
    """Terminal log entry for prediction streaming."""

    timestamp: str
    level: str  # info, warn, error, predict, verify
    ticker: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class PredictionEngine:
    """Predicts instrument prices with no look-ahead bias.

    Tracks errors and stores them as risk factors.
    """

    _error_counter = 0

    def __init__(
        self,
        pattern_detector: PatternDetector | None = None,
        delisting_memory: DelistingMemory | None = None,
        error_memory: list[PredictionError] | None = None,
        ma_short: int = 10,
        ma_long: int = 30,
        horizon: int = 5,
        context_provider: MarketContextProvider | None = None,
        use_lstm: bool = False,
    ) -> None:
        self.pattern_detector = pattern_detector or PatternDetector()
        self.delisting_memory = delisting_memory or self.pattern_detector.delisting_memory
        self.error_memory = error_memory or []
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.horizon = horizon
        self.context_provider = context_provider
        self._log: list[PredictionLogEntry] = []
        self._pending: dict[str, Prediction] = {}  # ticker → pending prediction
        self._lstm_predictor = None
        if use_lstm:
            try:
                from market.analysis.lstm_predictor import LSTMPredictor
                self._lstm_predictor = LSTMPredictor()
            except Exception:
                pass

    @property
    def log(self) -> list[PredictionLogEntry]:
        """Prediction log entries for terminal output."""
        return self._log

    def clear_log(self) -> None:
        """Clear the prediction log."""
        self._log.clear()

    def _log_entry(
        self,
        level: str,
        ticker: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        entry = PredictionLogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            ticker=ticker,
            message=message,
            data=data or {},
        )
        self._log.append(entry)

    def _truncate(
        self,
        data: pd.DataFrame,
        as_of: str | pd.Timestamp | None,
    ) -> pd.DataFrame:
        """Truncate data to as_of date — NO LOOK-AHEAD."""
        if as_of is None:
            return data
        cutoff = pd.Timestamp(as_of)
        return data[data.index <= cutoff]

    def predict(
        self,
        ticker: str,
        data: pd.DataFrame,
        as_of: str | pd.Timestamp | None = None,
        method: PredictionMethod = PredictionMethod.ENSEMBLE,
    ) -> Prediction:
        """Generate prediction using only data up to as_of.

        Args:
            ticker: Instrument ticker.
            data: Full OHLCV DataFrame (will be truncated).
            as_of: Prediction date. Only data up to this date is used.
            method: Prediction method to use.

        Returns:
            Prediction object.
        """
        self.clear_log()
        df = self._truncate(data, as_of)

        if len(df) < self.ma_long + self.horizon:
            self._log_entry("warn", ticker, f"Insufficient data: {len(df)} bars")
            return Prediction(
                ticker=ticker,
                as_of=str(as_of) if as_of else str(df.index[-1]),
                method=method,
                predicted_price=0.0,
                predicted_direction="flat",
                predicted_return_pct=0.0,
                confidence=0.0,
                horizon_days=self.horizon,
                rationale="Insufficient data for prediction",
            )

        as_of_str = str(as_of) if as_of else str(df.index[-1])
        self._log_entry(
            "info", ticker,
            f"Starting prediction: method={method.value}, "
            f"bars={len(df)}, as_of={as_of_str}, horizon={self.horizon}d",
        )

        # Check delisting memory — refuse to predict blocked/delisted instruments
        if self.delisting_memory.is_blocked(ticker):
            record = self.delisting_memory.get_record(ticker)
            self._log_entry(
                "error", ticker,
                f"INSTRUMENT BLOCKED/DELISTED: {record.reason.value if record else 'unknown'}. "
                f"Prediction refused. Lesson: {record.lesson if record else ''}",
            )
            return Prediction(
                ticker=ticker,
                as_of=as_of_str,
                method=method,
                predicted_price=0.0,
                predicted_direction="flat",
                predicted_return_pct=0.0,
                confidence=0.0,
                horizon_days=self.horizon,
                rationale=(
                    f"Instrument is BLOCKED/DELISTED "
                    f"({record.reason.value if record else 'unknown'}). "
                    f"Prediction refused for safety."
                ),
            )

        if self.delisting_memory.is_suspended(ticker):
            record = self.delisting_memory.get_record(ticker)
            self._log_entry(
                "warn", ticker,
                f"INSTRUMENT SUSPENDED: {record.reason.value if record else 'unknown'}. "
                f"Prediction confidence reduced. Lesson: {record.lesson if record else ''}",
            )

        close = df["close"].astype(float)
        current_price = float(close.iloc[-1])

        # Guard: zero or negative price → safe fallback (prevents ZeroDivisionError)
        if current_price <= 0:
            self._log_entry(
                "warn", ticker,
                f"Invalid price ({current_price}) — prediction refused",
            )
            return Prediction(
                ticker=ticker,
                as_of=str(as_of) if as_of else str(df.index[-1]),
                method=method,
                predicted_price=0.0,
                predicted_direction="flat",
                predicted_return_pct=0.0,
                confidence=0.0,
                horizon_days=self.horizon,
                rationale=f"Invalid current price ({current_price}) — prediction refused",
            )

        # Run pattern detection (no look-ahead)
        patterns = self.pattern_detector.detect(ticker, df, as_of)
        pattern_signals = [p.pattern_type for p in patterns]

        self._log_entry(
            "info", ticker,
            f"Pattern signals: {pattern_signals or 'none'}",
        )

        # Compute indicators (only from truncated data)
        ma_s = float(close.rolling(self.ma_short).mean().iloc[-1])
        ma_l = float(close.rolling(self.ma_long).mean().iloc[-1])
        rsi = self._compute_rsi(close)
        atr = self._compute_atr(df)
        momentum = self._compute_momentum(close, self.horizon)

        indicators = {
            "ma_short": round(ma_s, 2),
            "ma_long": round(ma_l, 2),
            "rsi": round(rsi, 2),
            "atr": round(atr, 2),
            "momentum_pct": round(momentum, 2),
            "current_price": round(current_price, 2),
        }

        # Fetch market context (fundamental, macro, sentiment, flow)
        market_ctx: MarketContext | None = None
        if self.context_provider is not None:
            try:
                market_ctx = self.context_provider.get_context(ticker, as_of_str, df=df)
                if market_ctx.is_available:
                    indicators["pe_ratio"] = market_ctx.pe_ratio or 0.0
                    indicators["roe"] = market_ctx.roe or 0.0
                    indicators["vix"] = market_ctx.vix or 0.0
                    indicators["fear_greed"] = market_ctx.fear_greed_index or 0.0
                    indicators["foreign_net_5d"] = market_ctx.foreign_net_flow_5d or 0.0
                    indicators["fundamental_score"] = market_ctx.fundamental_score or 0.0
                    indicators["technical_score"] = market_ctx.technical_score or 0.0
                    self._log_entry(
                        "info", ticker,
                        f"Market context: PE={market_ctx.pe_ratio}, "
                        f"VIX={market_ctx.vix}, "
                        f"FG={market_ctx.fear_greed_index}, "
                        f"Flow5d={market_ctx.foreign_net_flow_5d}, "
                        f"composite={market_ctx.composite_signal():.3f}",
                    )
            except Exception as e:
                self._log_entry("warn", ticker, f"Context fetch failed: {e}")

        # Generate prediction based on method
        if method == PredictionMethod.MA_BASED:
            pred = self._predict_ma(
                ticker, as_of_str, current_price,
                ma_s, ma_l, indicators, pattern_signals,
            )
        elif method == PredictionMethod.MOMENTUM:
            pred = self._predict_momentum(
                ticker, as_of_str, current_price,
                momentum, indicators, pattern_signals,
            )
        elif method == PredictionMethod.PATTERN_BASED:
            pred = self._predict_pattern(
                ticker, as_of_str, current_price, patterns, indicators,
            )
        elif method == PredictionMethod.VOLATILITY_ADJUSTED:
            pred = self._predict_vol_adj(
                ticker, as_of_str, current_price,
                ma_s, ma_l, atr, indicators, pattern_signals,
            )
        else:  # ENSEMBLE
            pred = self._predict_ensemble(
                ticker, as_of_str, current_price, ma_s, ma_l,
                momentum, rsi, atr, patterns, indicators, pattern_signals,
                market_ctx=market_ctx,
            )

        # Adjust confidence based on historical error rate
        error_rate = self._get_error_rate(ticker)
        if error_rate > 0:
            adjustment = 1.0 - (error_rate * 0.3)
            pred.confidence = round(max(0.1, pred.confidence * adjustment), 3)
            self._log_entry(
                "info", ticker,
                f"Historical error rate: {error_rate:.1%}, "
                f"confidence adjusted to {pred.confidence:.3f}",
            )

        # Adjust confidence for suspended instruments
        if self.delisting_memory.is_suspended(ticker):
            pred.confidence = round(pred.confidence * 0.3, 3)
            self._log_entry(
                "warn", ticker,
                f"Instrument suspended — confidence reduced to {pred.confidence:.3f}",
            )

        # Adjust confidence based on delisting warning patterns
        reminders = self.delisting_memory.generate_reminders(ticker, df, as_of)
        if reminders:
            max_risk = max(r.risk_score for r in reminders)
            pred.confidence = round(pred.confidence * (1.0 - max_risk * 0.5), 3)
            self._log_entry(
                "warn", ticker,
                f"Delisting risk detected (max_risk={max_risk:.3f}) — "
                f"confidence adjusted to {pred.confidence:.3f}",
            )

        # Store as pending for later verification
        self._pending[ticker] = pred

        self._log_entry(
            "predict", ticker,
            f"PREDICTION: direction={pred.predicted_direction} "
            f"price={pred.predicted_price:.2f} "
            f"return={pred.predicted_return_pct:.2f}% "
            f"confidence={pred.confidence:.3f}",
            data={
                "predicted_price": pred.predicted_price,
                "predicted_direction": pred.predicted_direction,
                "predicted_return_pct": pred.predicted_return_pct,
                "confidence": pred.confidence,
            },
        )

        return pred

    def verify(
        self,
        ticker: str,
        data: pd.DataFrame,
        as_of: str | pd.Timestamp,
    ) -> PredictionError | None:
        """Verify a pending prediction against actual outcome.

        Args:
            ticker: Instrument ticker.
            data: Full OHLCV data (including future data for verification).
            as_of: The date the prediction was made.

        Returns:
            PredictionError if there was an error, None if prediction was correct
            or no pending prediction exists.
        """
        if ticker not in self._pending:
            self._log_entry("warn", ticker, "No pending prediction to verify")
            return None

        pred = self._pending.pop(ticker)
        cutoff = pd.Timestamp(as_of)
        future = data[data.index > cutoff]

        if len(future) < self.horizon:
            self._log_entry("warn", ticker, "Insufficient future data for verification")
            return None

        actual_price = float(future["close"].iloc[self.horizon - 1])
        actual_direction = (
            "up" if actual_price > float(data.loc[cutoff, "close"]) else
            "down" if actual_price < float(data.loc[cutoff, "close"]) else
            "flat"
        )

        error_pct = abs(
            (actual_price - pred.predicted_price) / pred.predicted_price * 100
        ) if pred.predicted_price > 0 else 0.0

        direction_correct = pred.predicted_direction == actual_direction

        self._log_entry(
            "verify", ticker,
            f"VERIFICATION: predicted={pred.predicted_price:.2f} "
            f"actual={actual_price:.2f} error={error_pct:.2f}% "
            f"direction={'✓' if direction_correct else '✗'} "
            f"(pred={pred.predicted_direction} actual={actual_direction})",
            data={
                "predicted_price": pred.predicted_price,
                "actual_price": actual_price,
                "error_pct": error_pct,
                "direction_correct": direction_correct,
            },
        )

        if direction_correct and error_pct < 2.0:
            self._log_entry("info", ticker, "Prediction within tolerance — no error recorded")
            return None

        # Analyze root cause
        category, root_cause, lesson, risk_weight = self._analyze_error(
            ticker, pred, actual_price, actual_direction, data, cutoff,
        )

        PredictionEngine._error_counter += 1
        error = PredictionError(
            error_id=f"ERR-{PredictionEngine._error_counter:05d}",
            ticker=ticker,
            as_of=str(as_of),
            method=pred.method,
            predicted_price=pred.predicted_price,
            actual_price=actual_price,
            predicted_direction=pred.predicted_direction,
            actual_direction=actual_direction,
            error_pct=round(error_pct, 2),
            direction_correct=direction_correct,
            error_category=category,
            root_cause=root_cause,
            lesson=lesson,
            risk_weight=round(risk_weight, 3),
        )

        self.error_memory.append(error)

        self._log_entry(
            "error", ticker,
            f"PREDICTION ERROR: category={category.value} "
            f"root_cause={root_cause} "
            f"lesson={lesson} "
            f"risk_weight={risk_weight:.3f}",
            data={
                "error_id": error.error_id,
                "category": category.value,
                "root_cause": root_cause,
                "lesson": lesson,
                "risk_weight": risk_weight,
            },
        )

        return error

    def _analyze_error(
        self,
        ticker: str,
        pred: Prediction,
        actual_price: float,
        actual_direction: str,
        data: pd.DataFrame,
        as_of: pd.Timestamp,
    ) -> tuple[ErrorCategory, str, str, float]:
        """Analyze root cause of a prediction error.

        Returns:
            (category, root_cause, lesson, risk_weight)
        """
        future = data[data.index > as_of]
        pre = data[data.index <= as_of]

        if pre.empty or future.empty:
            return ErrorCategory.UNKNOWN, "Insufficient data for analysis", "Need more data", 0.5

        # Check for volatility spike
        pre_atr = self._compute_atr(pre)
        future_atr = self._compute_atr(future.head(self.horizon + 14))
        if future_atr > pre_atr * 2:
            cat = ErrorCategory.VOLATILITY_SPIKE
            cause = (
                f"Volatility spike: ATR jumped from {pre_atr:.2f} to {future_atr:.2f} "
                f"({future_atr / pre_atr:.1f}x)"
            )
            lesson = (
                "When ATR is rising rapidly, reduce confidence in directional predictions. "
                "Add volatility regime filter: if ATR ratio > 2.0, switch to neutral or "
                "reduce position size by 50%."
            )
            return cat, cause, lesson, 0.8

        # Check for regime change (trend reversal)
        pre_close = pre["close"].astype(float)
        pre_trend = "up" if pre_close.iloc[-1] > pre_close.iloc[-20] else "down"
        future_close = future["close"].astype(float).head(self.horizon)
        future_trend = "up" if future_close.iloc[-1] > future_close.iloc[0] else "down"

        if pre_trend != future_trend:
            cat = ErrorCategory.REGIME_CHANGE
            cause = (
                f"Regime change: pre-trend={pre_trend}, "
                f"post-trend={future_trend}. "
                f"Trend reversed during prediction horizon."
            )
            lesson = (
                "Trend reversals can invalidate momentum-based predictions. "
                "Add trend strength filter (ADX > 25 required for trend-following). "
                "Monitor for divergence between price and RSI/MACD as early warning."
            )
            return cat, cause, lesson, 0.7

        # Check for pattern failure
        if pred.pattern_signals:
            cat = ErrorCategory.PATTERN_FAILURE
            cause = (
                f"Pattern signals failed: {pred.pattern_signals}. "
                f"Pattern predicted {pred.predicted_direction} but actual was {actual_direction}."
            )
            lesson = (
                "Patterns are probabilistic, not deterministic. "
                "Reduce confidence when multiple conflicting patterns detected. "
                "Always set stop-loss at pattern invalidation level."
            )
            return cat, cause, lesson, 0.6

        # Check for data anomaly (gap)
        pre_last = float(pre["close"].iloc[-1])
        future_first = float(future["open"].iloc[0])
        gap_pct = abs(future_first - pre_last) / pre_last * 100
        if gap_pct > 3.0:
            cat = ErrorCategory.DATA_ANOMALY
            cause = (
                f"Price gap detected: {gap_pct:.1f}% gap between "
                f"close ({pre_last:.2f}) and next open ({future_first:.2f})"
            )
            lesson = (
                "Price gaps can invalidate predictions. "
                "Add gap detection: if overnight gap > 3%, reduce confidence by 50%. "
                "Consider gap-fill probability in prediction model."
            )
            return cat, cause, lesson, 0.65

        # Check for liquidity event (volume spike)
        pre_vol = float(pre["volume"].iloc[-20:].mean())
        future_vol = float(future["volume"].head(self.horizon).mean())
        if future_vol > pre_vol * 3:
            cat = ErrorCategory.LIQUIDITY_EVENT
            cause = (
                f"Liquidity event: volume spiked from avg {pre_vol:.0f} to {future_vol:.0f} "
                f"({future_vol / pre_vol:.1f}x)"
            )
            lesson = (
                "Volume spikes indicate unusual market activity. "
                "Add volume filter: if volume > 3x average, reduce position size. "
                "Large volume can cause slippage and invalidate price predictions."
            )
            return cat, cause, lesson, 0.7

        # Default: model limitation
        cat = ErrorCategory.MODEL_LIMITATION
        cause = (
            f"Model limitation: {pred.method.value} method could not predict "
            f"actual movement. Error="
            f"{abs((actual_price - pred.predicted_price) / pred.predicted_price * 100):.1f}%"
        )
        lesson = (
            "No single model captures all market dynamics. "
            "Consider ensemble approach with multiple methods. "
            "Regularly retrain models and adjust weights based on recent performance."
        )
        return cat, cause, lesson, 0.5

    def _get_error_rate(self, ticker: str) -> float:
        """Get historical error rate for a ticker."""
        ticker_errors = [e for e in self.error_memory if e.ticker == ticker]
        if not ticker_errors:
            return 0.0
        incorrect = sum(1 for e in ticker_errors if not e.direction_correct)
        return incorrect / len(ticker_errors)

    def get_risk_adjustment(self, ticker: str) -> float:
        """Get risk adjustment factor based on historical prediction errors.

        Returns a multiplier (0.5 - 1.0) to apply to position size.
        More errors → lower multiplier → smaller positions.
        """
        ticker_errors = [e for e in self.error_memory if e.ticker == ticker]
        if not ticker_errors:
            return 1.0

        avg_risk_weight = np.mean([e.risk_weight for e in ticker_errors])
        error_rate = len(ticker_errors) / max(len(ticker_errors), 10)

        # Combine error rate and average risk weight
        adjustment = 1.0 - (error_rate * 0.3 + float(avg_risk_weight) * 0.3)
        return round(max(0.5, adjustment), 3)

    def get_error_summary(self, ticker: str | None = None) -> dict[str, Any]:
        """Get summary of prediction errors."""
        errors = self.error_memory
        if ticker:
            errors = [e for e in errors if e.ticker == ticker]

        if not errors:
            return {
                "total_errors": 0,
                "error_rate": 0.0,
                "by_category": {},
                "avg_error_pct": 0.0,
                "direction_accuracy": 0.0,
                "risk_adjustment": 1.0 if ticker else {},
            }

        by_category: dict[str, int] = {}
        for e in errors:
            by_category[e.error_category.value] = by_category.get(e.error_category.value, 0) + 1

        direction_correct = sum(1 for e in errors if e.direction_correct)

        return {
            "total_errors": len(errors),
            "by_category": by_category,
            "avg_error_pct": round(float(np.mean([e.error_pct for e in errors])), 2),
            "direction_accuracy": round(direction_correct / len(errors), 3),
            "avg_risk_weight": round(float(np.mean([e.risk_weight for e in errors])), 3),
            "risk_adjustment": self.get_risk_adjustment(ticker) if ticker else {},
            "recent_lessons": [e.lesson for e in errors[-5:]],
        }

    # -----------------------------------------------------------------------
    # Prediction methods
    # -----------------------------------------------------------------------

    def _predict_ma(
        self,
        ticker: str,
        as_of: str,
        price: float,
        ma_s: float,
        ma_l: float,
        indicators: dict[str, float],
        pattern_signals: list[str],
    ) -> Prediction:
        """MA-based prediction: price moves toward short MA."""
        predicted_price = ma_s
        ret_pct = (predicted_price - price) / price * 100
        if predicted_price > price * 1.005:
            direction = "up"
        elif predicted_price < price * 0.995:
            direction = "down"
        else:
            direction = "flat"

        confidence = 0.5
        if ma_s > ma_l:
            confidence += 0.15  # Uptrend bonus
        if abs(ret_pct) < 1.0:
            confidence -= 0.1  # Too small to predict

        return Prediction(
            ticker=ticker, as_of=as_of, method=PredictionMethod.MA_BASED,
            predicted_price=round(predicted_price, 2),
            predicted_direction=direction,
            predicted_return_pct=round(ret_pct, 2),
            confidence=round(max(0.1, min(1.0, confidence)), 3),
            horizon_days=self.horizon,
            indicators_used=indicators,
            pattern_signals=pattern_signals,
            rationale=f"MA-based: price tends toward MA{self.ma_short}={ma_s:.2f}",
        )

    def _predict_momentum(
        self,
        ticker: str,
        as_of: str,
        price: float,
        momentum: float,
        indicators: dict[str, float],
        pattern_signals: list[str],
    ) -> Prediction:
        """Momentum-based prediction: continue current momentum."""
        predicted_return = momentum * 0.5  # Damped momentum
        predicted_price = price * (1 + predicted_return / 100)
        if predicted_return > 0.5:
            direction = "up"
        elif predicted_return < -0.5:
            direction = "down"
        else:
            direction = "flat"

        confidence = min(0.8, 0.4 + abs(momentum) / 20)

        return Prediction(
            ticker=ticker, as_of=as_of, method=PredictionMethod.MOMENTUM,
            predicted_price=round(predicted_price, 2),
            predicted_direction=direction,
            predicted_return_pct=round(predicted_return, 2),
            confidence=round(confidence, 3),
            horizon_days=self.horizon,
            indicators_used=indicators,
            pattern_signals=pattern_signals,
            rationale=(
                f"Momentum: recent {self.horizon}d return="
                f"{momentum:.2f}%, damped to {predicted_return:.2f}%"
            ),
        )

    def _predict_pattern(
        self,
        ticker: str,
        as_of: str,
        price: float,
        patterns: list[PatternDetection],
        indicators: dict[str, float],
    ) -> Prediction:
        """Pattern-based prediction: direction from detected patterns."""
        if not patterns:
            return Prediction(
                ticker=ticker, as_of=as_of, method=PredictionMethod.PATTERN_BASED,
                predicted_price=round(price, 2),
                predicted_direction="flat",
                predicted_return_pct=0.0,
                confidence=0.3,
                horizon_days=self.horizon,
                indicators_used=indicators,
                pattern_signals=[],
                rationale="No patterns detected — flat prediction",
            )

        # Aggregate pattern signals
        bullish = sum(1 for p in patterns if p.direction == "bullish")
        bearish = sum(1 for p in patterns if p.direction == "bearish")
        neutral = sum(1 for p in patterns if p.direction == "neutral")

        if bullish > bearish:
            direction = "up"
            avg_conf = float(np.mean([p.confidence for p in patterns if p.direction == "bullish"]))
            ret_pct = 2.0 * avg_conf
        elif bearish > bullish:
            direction = "down"
            avg_conf = float(np.mean([p.confidence for p in patterns if p.direction == "bearish"]))
            ret_pct = -2.0 * avg_conf
        else:
            direction = "flat"
            avg_conf = 0.4
            ret_pct = 0.0

        predicted_price = price * (1 + ret_pct / 100)

        return Prediction(
            ticker=ticker, as_of=as_of, method=PredictionMethod.PATTERN_BASED,
            predicted_price=round(predicted_price, 2),
            predicted_direction=direction,
            predicted_return_pct=round(ret_pct, 2),
            confidence=round(avg_conf, 3),
            horizon_days=self.horizon,
            indicators_used=indicators,
            pattern_signals=[p.pattern_type for p in patterns],
            rationale=(
                f"Pattern-based: {bullish} bullish, "
                f"{bearish} bearish, {neutral} neutral patterns"
            ),
        )

    def _predict_vol_adj(
        self,
        ticker: str,
        as_of: str,
        price: float,
        ma_s: float,
        ma_l: float,
        atr: float,
        indicators: dict[str, float],
        pattern_signals: list[str],
    ) -> Prediction:
        """Volatility-adjusted prediction: MA direction with ATR-based magnitude."""
        direction_raw = ma_s - ma_l
        # Predicted move = fraction of ATR in trend direction
        predicted_move = direction_raw * 0.3 + (atr * 0.5 if direction_raw > 0 else -atr * 0.5)
        predicted_price = price + predicted_move
        ret_pct = (predicted_price - price) / price * 100
        direction = "up" if ret_pct > 0.5 else "down" if ret_pct < -0.5 else "flat"

        # Confidence inversely proportional to volatility
        vol_pct = atr / price * 100
        confidence = max(0.2, min(0.8, 0.6 - vol_pct / 20))

        return Prediction(
            ticker=ticker, as_of=as_of, method=PredictionMethod.VOLATILITY_ADJUSTED,
            predicted_price=round(predicted_price, 2),
            predicted_direction=direction,
            predicted_return_pct=round(ret_pct, 2),
            confidence=round(confidence, 3),
            horizon_days=self.horizon,
            indicators_used=indicators,
            pattern_signals=pattern_signals,
            rationale=f"Vol-adj: MA trend={direction_raw:.2f}, ATR={atr:.2f}, vol={vol_pct:.1f}%",
        )

    def _predict_ensemble(
        self,
        ticker: str,
        as_of: str,
        price: float,
        ma_s: float,
        ma_l: float,
        momentum: float,
        rsi: float,
        atr: float,
        patterns: list[PatternDetection],
        indicators: dict[str, float],
        pattern_signals: list[str],
        market_ctx: MarketContext | None = None,
    ) -> Prediction:
        """Ensemble prediction: weighted combination of all methods + market context.

        P6: Ticker-specific ensemble weights and direction thresholds.
        """
        # P6: Ticker-specific profiles
        # Mean-reverting tickers: wider threshold, less momentum weight
        # Trending tickers: tighter threshold, more momentum weight
        TICKER_ENSEMBLE_PROFILES = {
            "BBCA.JK": {"weights": {"ma": 0.25, "momentum": 0.20, "pattern": 0.30, "vol_adj": 0.25}, "threshold": 0.15},
            "BBRI.JK": {"weights": {"ma": 0.25, "momentum": 0.20, "pattern": 0.30, "vol_adj": 0.25}, "threshold": 0.15},
            "UNVR.JK": {"weights": {"ma": 0.20, "momentum": 0.25, "pattern": 0.30, "vol_adj": 0.25}, "threshold": 0.15},
            "ANTM.JK": {"weights": {"ma": 0.15, "momentum": 0.35, "pattern": 0.25, "vol_adj": 0.25}, "threshold": 0.12},
            "MDKA.JK": {"weights": {"ma": 0.20, "momentum": 0.30, "pattern": 0.25, "vol_adj": 0.25}, "threshold": 0.20},
            "UNTR.JK": {"weights": {"ma": 0.30, "momentum": 0.15, "pattern": 0.30, "vol_adj": 0.25}, "threshold": 0.25},
            "APLI.JK": {"weights": {"ma": 0.25, "momentum": 0.20, "pattern": 0.30, "vol_adj": 0.25}, "threshold": 0.20},
            "BCIC.JK": {"weights": {"ma": 0.30, "momentum": 0.15, "pattern": 0.30, "vol_adj": 0.25}, "threshold": 0.25},
            "INCO.JK": {"weights": {"ma": 0.20, "momentum": 0.25, "pattern": 0.30, "vol_adj": 0.25}, "threshold": 0.15},
            "KRAS.JK": {"weights": {"ma": 0.20, "momentum": 0.25, "pattern": 0.30, "vol_adj": 0.25}, "threshold": 0.15},
        }
        
        profile = TICKER_ENSEMBLE_PROFILES.get(ticker, {})
        direction_threshold = profile.get("threshold", 0.15)
        
        # Generate individual predictions
        pred_ma = self._predict_ma(
            ticker, as_of, price, ma_s, ma_l, indicators, pattern_signals,
        )
        pred_mom = self._predict_momentum(
            ticker, as_of, price, momentum, indicators, pattern_signals,
        )
        pred_pat = self._predict_pattern(
            ticker, as_of, price, patterns, indicators,
        )
        pred_vol = self._predict_vol_adj(
            ticker, as_of, price, ma_s, ma_l, atr, indicators, pattern_signals,
        )

        # Weights (sum to 1.0) — P6: ticker-specific
        weights = profile.get("weights", {
            "ma": 0.20,
            "momentum": 0.25,
            "pattern": 0.30,
            "vol_adj": 0.25,
        })

        # Adjust weights based on pattern availability
        if not patterns:
            weights["pattern"] = 0.0
            weights["ma"] += 0.10
            weights["momentum"] += 0.10
            weights["vol_adj"] += 0.10

        # Weighted average predicted price
        predicted_price = (
            pred_ma.predicted_price * weights["ma"]
            + pred_mom.predicted_price * weights["momentum"]
            + pred_pat.predicted_price * weights["pattern"]
            + pred_vol.predicted_price * weights["vol_adj"]
        )

        ret_pct = (predicted_price - price) / price * 100
        direction = "up" if ret_pct > direction_threshold else "down" if ret_pct < -direction_threshold else "flat"

        # Confidence = weighted average
        confidence = (
            pred_ma.confidence * weights["ma"]
            + pred_mom.confidence * weights["momentum"]
            + pred_pat.confidence * weights["pattern"]
            + pred_vol.confidence * weights["vol_adj"]
        )

        # RSI adjustment
        if rsi > 70:
            confidence *= 0.8  # Overbought → reduce confidence
        elif rsi < 30:
            confidence *= 0.8  # Oversold → reduce confidence

        # ── Market context adjustment ────────────────────────────────────
        context_signal = 0.0
        context_rationale = ""
        if market_ctx is not None and market_ctx.is_available:
            context_signal = market_ctx.composite_signal()
            fund_signal = market_ctx.fundamental_signal()
            macro_signal = market_ctx.macro_signal()
            sent_signal = market_ctx.sentiment_signal()
            flow_signal = market_ctx.flow_signal()

            # Adjust predicted price: context signal shifts price expectation
            # Scale: context_signal in [-1, 1], apply up to ±5% adjustment
            context_adjustment = context_signal * 5.0
            predicted_price *= (1.0 + context_adjustment / 100.0)
            ret_pct = (predicted_price - price) / price * 100

            # Re-evaluate direction with context (P6: ticker-specific threshold)
            direction = "up" if ret_pct > direction_threshold else "down" if ret_pct < -direction_threshold else "flat"

            # Adjust confidence based on context alignment with technical signal
            technical_signal = 1.0 if ret_pct > 0 else -1.0 if ret_pct < 0 else 0.0
            alignment = context_signal * technical_signal
            if alignment > 0:
                confidence *= 1.15  # Context confirms technical → boost
            elif alignment < 0:
                confidence *= 0.85  # Context contradicts technical → reduce

            # Fear & Greed extreme adjustment
            if market_ctx.fear_greed_index is not None:
                fg = market_ctx.fear_greed_index
                if fg < 25:  # Extreme fear → contrarian bullish
                    if direction == "down":
                        confidence *= 0.9
                    elif direction == "up":
                        confidence *= 1.1
                elif fg > 75:  # Extreme greed → contrarian bearish
                    if direction == "up":
                        confidence *= 0.9
                    elif direction == "down":
                        confidence *= 1.1

            context_rationale = (
                f" Context: fund={fund_signal:.2f}, macro={macro_signal:.2f}, "
                f"sent={sent_signal:.2f}, flow={flow_signal:.2f}, "
                f"composite={context_signal:.2f}"
            )

        # P7: Direct exogenous ecosystem adjustment
        # USD/IDR and Shanghai Composite directly adjust predicted price
        # based on sector sensitivity
        exog_rationale = ""

        # LSTM adjustment (if enabled)
        lstm_rationale = ""
        if self._lstm_predictor is not None:
            try:
                lstm_pred = self._lstm_predictor.predict(df, ticker=ticker)
                if lstm_pred and lstm_pred.confidence > 0:
                    lstm_signal = 1.0 if lstm_pred.direction == "up" else -1.0 if lstm_pred.direction == "down" else 0.0
                    lstm_weight = 0.10  # 10% weight for LSTM signal
                    predicted_price = predicted_price * (1.0 - lstm_weight) + \
                        price * (1.0 + lstm_pred.predicted_return_pct / 100.0) * lstm_weight
                    ret_pct = (predicted_price - price) / price * 100
                    direction = "up" if ret_pct > direction_threshold else "down" if ret_pct < -direction_threshold else "flat"
                    if lstm_signal * (1.0 if ret_pct > 0 else -1.0) > 0:
                        confidence *= 1.05
                    lstm_rationale = f" LSTM={lstm_pred.direction}({lstm_pred.confidence:.2f})"
            except Exception:
                pass

        try:
            _as_of_dt = pd.Timestamp(as_of)

            # USD/IDR 5-day return (cached, filter by as_of in pandas)
            _fx_full = _load_fx_cache()
            if _fx_full is not None and not _fx_full.empty:
                _fx = _fx_full[_fx_full.index <= _as_of_dt]
                if len(_fx) > 5:
                    _fx_ret5 = _fx["close"].pct_change(5).iloc[-1]
                    exog_adjust = 0.0
                    if ticker in ("ANTM.JK", "MDKA.JK", "INCO.JK", "KRAS.JK", "APLI.JK", "UNTR.JK"):
                        exog_adjust = _fx_ret5 * 1.5
                    elif ticker in ("BBCA.JK", "BBRI.JK", "BCIC.JK"):
                        exog_adjust = -_fx_ret5 * 1.0
                    elif ticker == "UNVR.JK":
                        exog_adjust = -_fx_ret5 * 1.0
                    if abs(exog_adjust) > 0.01:
                        predicted_price *= (1.0 + exog_adjust / 100.0)
                        ret_pct = (predicted_price - price) / price * 100
                        direction = "up" if ret_pct > direction_threshold else "down" if ret_pct < -direction_threshold else "flat"
                        exog_rationale = f" FX5d={_fx_ret5:.2%}→adj={exog_adjust:+.2f}%"

            # Shanghai Composite 5-day return (cached, filter by as_of in pandas)
            _sh_full = _load_shanghai_cache()
            if _sh_full is not None and not _sh_full.empty:
                _sh = _sh_full[_sh_full.index <= _as_of_dt]
                if len(_sh) > 5 and ticker in ("ANTM.JK", "MDKA.JK", "INCO.JK", "KRAS.JK", "APLI.JK"):
                    _sh_ret5 = _sh["close"].pct_change(5).iloc[-1]
                    sh_adjust = _sh_ret5 * 1.5
                    if abs(sh_adjust) > 0.01:
                        predicted_price *= (1.0 + sh_adjust / 100.0)
                        ret_pct = (predicted_price - price) / price * 100
                        direction = "up" if ret_pct > direction_threshold else "down" if ret_pct < -direction_threshold else "flat"
                        exog_rationale += f" SH5d={_sh_ret5:.2%}→adj={sh_adjust:+.2f}%"
        except Exception:
            pass

        return Prediction(
            ticker=ticker, as_of=as_of, method=PredictionMethod.ENSEMBLE,
            predicted_price=round(predicted_price, 2),
            predicted_direction=direction,
            predicted_return_pct=round(ret_pct, 2),
            confidence=round(max(0.1, min(1.0, confidence)), 3),
            horizon_days=self.horizon,
            indicators_used=indicators,
            pattern_signals=pattern_signals,
            rationale=(
                f"Ensemble: MA={weights['ma']:.0%}, Mom={weights['momentum']:.0%}, "
                f"Pat={weights['pattern']:.0%}, Vol={weights['vol_adj']:.0%}. "
                f"RSI={rsi:.1f}.{context_rationale}{lstm_rationale}"
            ),
        )

    # -----------------------------------------------------------------------
    # Indicator helpers
    # -----------------------------------------------------------------------

    def _compute_rsi(self, close: pd.Series, period: int = 14) -> float:
        """Compute RSI."""
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])

    def _compute_atr(
        self,
        df: pd.DataFrame,
        period: int = 14,
    ) -> float:
        """Compute ATR."""
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)

        if len(close) < period:
            return 0.0

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
        return float(atr.iloc[-1])

    def _compute_momentum(self, close: pd.Series, period: int = 5) -> float:
        """Compute momentum as percentage return over period."""
        if len(close) < period + 1:
            return 0.0
        return float((close.iloc[-1] / close.iloc[-period - 1] - 1) * 100)
