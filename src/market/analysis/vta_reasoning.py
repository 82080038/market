"""VTA-style Verbal Technical Analysis Reasoning Engine.

Inspired by VTA (Koa et al., ICLR 2026 — "Reasoning on Time-Series for Financial
Technical Analysis"), this module implements a rule-based version of the VTA
framework:

1. **Time-Series → Textual Annotations**: Convert OHLCV data into interpretable
   technical indicators (MA crossover, RSI, momentum, Bollinger Bands, volume
   trend, ATR regime) — same as VTA's annotation functions.

2. **Verbal Reasoning**: Generate natural language reasoning trace from the
   annotations using rule-based logic (VTA uses RL-fine-tuned LLM; we use
   structured rules that mimic the reasoning pattern).

3. **Signal Generation**: Convert reasoning attributes into a directional signal
   [-1, 0, +1] — VTA conditions time-series backbone on reasoning attributes;
   we use weighted attribute consensus.

4. **Explanation**: Produce a human-readable explanation in Bahasa Indonesia
   with technical terms preserved.

This is the "poor man's VTA" — same architecture, rule-based instead of LLM-based.
Future upgrade: replace rule-based reasoning with actual LLM (FinGPT/Ollama).

References:
    - VTA: arxiv.org/abs/2511.08616 (ICLR 2026)
    - pustaka/96-ai-ml-audit-framework.md (Pilar 2: Engine Ablation)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ReasoningTrace:
    """VTA-style reasoning trace with annotations, reasoning, and signal."""

    annotations: dict[str, float] = field(default_factory=dict)
    reasoning: str = ""
    signal: int = 0  # -1, 0, +1
    confidence: float = 0.0
    explanation: str = ""


def annotate_ohlcv(ohlcv: pd.DataFrame, lookback: int = 20) -> dict[str, float]:
    """Convert OHLCV time-series into textual annotations.

    This mirrors VTA's annotation functions: statistics + technical indicators
    that an LLM (or rule-based system) can reason over.

    Args:
        ohlcv: DataFrame with columns [open, high, low, close, volume].
        lookback: Number of recent bars to use for annotation.

    Returns:
        Dict of annotation name → value.
    """
    if len(ohlcv) == 0:
        return {
            "current_price": 0.0, "mean_price": 0.0, "min_price": 0.0,
            "max_price": 0.0, "ma_5": 0.0, "ma_20": 0.0, "ma_crossover": 0.0,
            "rsi": 50.0, "momentum_5d": 0.0, "bb_width": 0.0, "bb_pct": 0.0,
            "vol_ratio": 1.0, "atr_ratio": 1.0, "macd": 0.0,
            "macd_signal": 0.0, "macd_histogram": 0.0,
        }

    if len(ohlcv) < lookback:
        lookback = len(ohlcv)

    recent = ohlcv.tail(lookback)
    close = recent["close"].astype(float)
    high = recent["high"].astype(float)
    low = recent["low"].astype(float)
    volume = recent["volume"].astype(float)

    # Statistics
    mean_price = float(close.mean())
    min_price = float(close.min())
    max_price = float(close.max())
    current = float(close.iloc[-1])

    # Moving averages
    ma_5 = float(close.rolling(5).mean().iloc[-1]) if len(close) >= 5 else current
    ma_20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else mean_price

    # RSI (14-day)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = float((100 - (100 / (1 + rs))).iloc[-1]) if not avg_loss.iloc[-1] == 0 else 50.0
    if np.isnan(rsi):
        rsi = 50.0

    # Momentum (5-day return)
    momentum_5d = float(close.pct_change(5).iloc[-1]) if len(close) >= 6 else 0.0

    # Bollinger Bands
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_width = float((bb_std / bb_mid).iloc[-1]) if len(close) >= 20 and bb_mid.iloc[-1] != 0 else 0.0
    bb_pct = 0.0
    if len(close) >= 20 and bb_mid.iloc[-1] != 0:
        bb_std_val = bb_std.iloc[-1]
        if pd.notna(bb_std_val) and bb_std_val != 0:
            bb_pct = float((close.iloc[-1] - bb_mid.iloc[-1]) / (2 * bb_std_val))
    if np.isnan(bb_pct):
        bb_pct = 0.0

    # Volume trend
    vol_ma = volume.rolling(20).mean()
    vol_ratio = float((volume.iloc[-1] / vol_ma.iloc[-1])) if len(volume) >= 20 and vol_ma.iloc[-1] != 0 else 1.0
    if np.isnan(vol_ratio):
        vol_ratio = 1.0

    # ATR (volatility regime)
    tr = (high - low).abs()
    atr_14 = tr.rolling(14).mean()
    atr_50 = tr.rolling(50).mean() if len(tr) >= 50 else tr.rolling(min(len(tr), 20)).mean()
    atr_ratio = float((atr_14.iloc[-1] / atr_50.iloc[-1])) if atr_50.iloc[-1] != 0 else 1.0
    if np.isnan(atr_ratio):
        atr_ratio = 1.0

    # MACD
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd = float((ema_12 - ema_26).iloc[-1]) if len(close) >= 26 else 0.0
    macd_signal = float((ema_12 - ema_26).rolling(9).mean().iloc[-1]) if len(close) >= 35 else 0.0
    if np.isnan(macd):
        macd = 0.0
    if np.isnan(macd_signal):
        macd_signal = 0.0

    return {
        "current_price": current,
        "mean_price": mean_price,
        "min_price": min_price,
        "max_price": max_price,
        "ma_5": ma_5,
        "ma_20": ma_20,
        "ma_crossover": ma_5 - ma_20,
        "rsi": rsi,
        "momentum_5d": momentum_5d,
        "bb_width": bb_width,
        "bb_pct": bb_pct,
        "vol_ratio": vol_ratio,
        "atr_ratio": atr_ratio,
        "macd": macd,
        "macd_signal": macd_signal,
        "macd_histogram": macd - macd_signal,
    }


def generate_reasoning(annotations: dict[str, float]) -> ReasoningTrace:
    """Generate verbal reasoning trace from annotations.

    This is the rule-based equivalent of VTA's LLM reasoning. It follows
    the same pattern: analyze indicators → identify patterns → conclude
    direction → generate explanation.

    Args:
        annotations: Dict of technical indicator values.

    Returns:
        ReasoningTrace with signal, confidence, reasoning, and explanation.
    """
    reasons_bullish: list[str] = []
    reasons_bearish: list[str] = []
    weights_bullish = 0.0
    weights_bearish = 0.0

    # MA crossover (weight: 0.20)
    ma_cross = annotations.get("ma_crossover", 0.0)
    if ma_cross > 0:
        reasons_bullish.append(f"MA5 > MA20 (crossover bullish, diff={ma_cross:.2f})")
        weights_bullish += 0.20
    elif ma_cross < 0:
        reasons_bearish.append(f"MA5 < MA20 (crossover bearish, diff={ma_cross:.2f})")
        weights_bearish += 0.20

    # RSI (weight: 0.15)
    rsi = annotations.get("rsi", 50.0)
    if rsi < 30:
        reasons_bullish.append(f"RSI={rsi:.1f} (oversold → potential reversal)")
        weights_bullish += 0.15
    elif rsi > 70:
        reasons_bearish.append(f"RSI={rsi:.1f} (overbought → potential correction)")
        weights_bearish += 0.15
    elif rsi > 50:
        reasons_bullish.append(f"RSI={rsi:.1f} (bullish zone)")
        weights_bullish += 0.05
    elif rsi < 50:
        reasons_bearish.append(f"RSI={rsi:.1f} (bearish zone)")
        weights_bearish += 0.05

    # Momentum (weight: 0.20)
    mom = annotations.get("momentum_5d", 0.0)
    if mom > 0.02:
        reasons_bullish.append(f"5-day momentum={mom:+.2%} (strong uptrend)")
        weights_bullish += 0.20
    elif mom < -0.02:
        reasons_bearish.append(f"5-day momentum={mom:+.2%} (strong downtrend)")
        weights_bearish += 0.20
    elif mom > 0:
        reasons_bullish.append(f"5-day momentum={mom:+.2%} (mild uptrend)")
        weights_bullish += 0.08
    elif mom < 0:
        reasons_bearish.append(f"5-day momentum={mom:+.2%} (mild downtrend)")
        weights_bearish += 0.08

    # Bollinger Bands (weight: 0.10)
    bb_pct = annotations.get("bb_pct", 0.0)
    if bb_pct < -1.0:
        reasons_bullish.append(f"BB%={bb_pct:.2f} (below lower band → mean reversion buy)")
        weights_bullish += 0.10
    elif bb_pct > 1.0:
        reasons_bearish.append(f"BB%={bb_pct:.2f} (above upper band → mean reversion sell)")
        weights_bearish += 0.10

    # Volume (weight: 0.10)
    vol_ratio = annotations.get("vol_ratio", 1.0)
    if vol_ratio > 1.5 and ma_cross > 0:
        reasons_bullish.append(f"Volume ratio={vol_ratio:.2f} (high volume confirms bullish move)")
        weights_bullish += 0.10
    elif vol_ratio > 1.5 and ma_cross < 0:
        reasons_bearish.append(f"Volume ratio={vol_ratio:.2f} (high volume confirms bearish move)")
        weights_bearish += 0.10

    # MACD (weight: 0.15)
    macd_hist = annotations.get("macd_histogram", 0.0)
    if macd_hist > 0:
        reasons_bullish.append(f"MACD histogram={macd_hist:.4f} (bullish momentum)")
        weights_bullish += 0.15
    elif macd_hist < 0:
        reasons_bearish.append(f"MACD histogram={macd_hist:.4f} (bearish momentum)")
        weights_bearish += 0.15

    # ATR regime (weight: 0.10 — confidence modifier)
    atr_ratio = annotations.get("atr_ratio", 1.0)
    vol_regime = "high" if atr_ratio > 1.5 else "low" if atr_ratio < 0.7 else "normal"

    # Determine signal
    net_weight = weights_bullish - weights_bearish
    if net_weight > 0.15:
        signal = 1
    elif net_weight < -0.15:
        signal = -1
    else:
        signal = 0

    # Confidence: net weight scaled, reduced in high vol
    confidence = min(1.0, abs(net_weight))
    if vol_regime == "high":
        confidence *= 0.7  # Reduce confidence in high volatility
    elif vol_regime == "low":
        confidence *= 1.1  # Boost confidence in low volatility

    # Generate reasoning text
    all_reasons = reasons_bullish if signal > 0 else reasons_bearish if signal < 0 else []
    reasoning = "; ".join(all_reasons) if all_reasons else "No clear signal — indicators mixed."

    # Generate explanation in Bahasa Indonesia
    direction_id = "naik" if signal > 0 else "turun" if signal < 0 else "datar"
    explanation_parts = [f"Harga diprediksi {direction_id}."]

    if signal > 0:
        for r in reasons_bullish[:3]:
            explanation_parts.append(f"  • Bullish: {r}")
        if reasons_bearish:
            explanation_parts.append(f"  • Bearish counter: {'; '.join(reasons_bearish[:2])}")
    elif signal < 0:
        for r in reasons_bearish[:3]:
            explanation_parts.append(f"  • Bearish: {r}")
        if reasons_bullish:
            explanation_parts.append(f"  • Bullish counter: {'; '.join(reasons_bullish[:2])}")
    else:
        explanation_parts.append("  • Sinyal konflik — tidak ada konsensus indikator.")

    explanation_parts.append(f"  • Volatility regime: {vol_regime} (ATR ratio={atr_ratio:.2f})")
    explanation_parts.append(f"  • Confidence: {confidence:.2f}")

    explanation = "\n".join(explanation_parts)

    return ReasoningTrace(
        annotations=annotations,
        reasoning=reasoning,
        signal=signal,
        confidence=confidence,
        explanation=explanation,
    )


class VTAReasoningEngine:
    """VTA-style reasoning engine for verbal technical analysis.

    Converts OHLCV → annotations → reasoning → signal + explanation.
    This is the rule-based version. Future: replace with LLM backend.

    Usage:
        engine = VTAReasoningEngine()
        trace = engine.analyze(ohlcv_df)
        print(trace.explanation)
        # "Harga diprediksi naik.
        #    • Bullish: MA5 > MA20 (crossover bullish, diff=12.50)
        #    • Bullish: RSI=55.3 (bullish zone)
        #    • Bullish: 5-day momentum=+3.20% (strong uptrend)
        #    • Volatility regime: normal (ATR ratio=0.95)
        #    • Confidence: 0.65"
    """

    def __init__(self, lookback: int = 20) -> None:
        self.lookback = lookback

    def analyze(self, ohlcv: pd.DataFrame) -> ReasoningTrace:
        """Analyze OHLCV data and produce reasoning trace.

        Args:
            ohlcv: DataFrame with columns [open, high, low, close, volume],
                   indexed by date.

        Returns:
            ReasoningTrace with signal, reasoning, and explanation.
        """
        if len(ohlcv) < 5:
            return ReasoningTrace(
                reasoning="Insufficient data for analysis.",
                explanation="Data tidak cukup untuk analisis (minimum 5 bar).",
            )

        annotations = annotate_ohlcv(ohlcv, self.lookback)
        return generate_reasoning(annotations)

    def generate_signal_series(self, ohlcv: pd.DataFrame) -> pd.Series:
        """Generate signal series for backtesting.

        Walks through OHLCV bar-by-bar, producing a signal for each bar
        based on data up to that point (no look-ahead).

        Args:
            ohlcv: DataFrame with OHLCV data.

        Returns:
            Series of signals {-1, 0, +1} indexed by date.
        """
        signals = pd.Series(0, index=ohlcv.index)

        for i in range(self.lookback, len(ohlcv)):
            window = ohlcv.iloc[:i + 1]
            trace = self.analyze(window)
            signals.iloc[i] = trace.signal

        return signals
