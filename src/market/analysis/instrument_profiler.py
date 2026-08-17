"""Instrument Behavior Profiler (catatan.md TAHAP 2 -- Prompt 2.1).

Comprehensive per-instrument behavior profiler yang menghitung dan menyimpan
profil unik setiap instrumen pasar modal ke tabel
``instrument_behavior_profiles`` (migration 0024).

Berbeda dari ``market.analysis.profiling.InstrumentProfiler`` yang bersifat
in-memory dan fokus pada personality label, modul ini:

- Persisten ke database (ticker PRIMARY KEY, weekly recalculation).
- Menghitung metrik lengkap: volatility regime + clustering, momentum vs
  mean-reversion dengan optimal lookback, mean-reversion halflife (Ornstein-
  Uhlenbeck), liquidity score + optimal position size %, beta vs IHSG,
  correlation to sector, sensitivity to USD & rates, seasonality (best/worst
  months, day-of-week effect), event response (earnings drift, dividend
  ex-date effect), dan trading-style suitability (intraday/swing/investing).
- Mendukung ``detect_regime_change()`` untuk alert perubahan perilaku.

Integration contract:
- Signal generators query ``get_profile(ticker)`` sebelum generate signal.
- Position sizing respect ``optimal_position_size_pct``.
- ``profile_all_instruments()`` dijalankan weekly via scheduled job.

Referensi:
- catatan.md L502-L606 (Prompt 2.1 + schema)
- pustaka/39-instrument-knowledge-base.md
- pustaka/89-faktor-pasar-modal-analisis-implementasi.md
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from market.db.engine import get_engine, get_sessionmaker

logger = logging.getLogger(__name__)

# IHSG composite index ticker (DB)
_IHSG_TICKER = "^JKSE"
_USD_IDR_TICKER = "IDR=X"  # USD/IDR
_RATES_TICKER = "^TNX"  # 10Y Treasury yield

# Default lookback windows
_DEFAULT_LOOKBACK = 756  # ~3 trading years
_MIN_DATA_POINTS = 60  # minimum for any meaningful profile
_VOL_REGIME_THRESHOLDS = (1.0, 2.0, 4.0)  # LOW/MEDIUM/HIGH/EXTREME (% daily)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class InstrumentProfile:
    """Comprehensive profile of an instrument (mirrors DB row)."""

    ticker: str
    asset_class: str | None = None
    sector: str | None = None
    # Volatility
    avg_daily_volatility: float | None = None
    volatility_regime: str | None = None  # LOW/MEDIUM/HIGH/EXTREME
    volatility_clustering_coefficient: float | None = None
    # Momentum & Mean Reversion
    momentum_strength: float | None = None
    optimal_momentum_lookback: int | None = None
    mean_reversion_halflife: float | None = None
    # Liquidity
    avg_daily_volume: int | None = None
    avg_spread_pct: float | None = None
    liquidity_score: float | None = None  # 1-10
    optimal_position_size_pct: float | None = None
    # Correlation & Sensitivity
    beta_to_ihsg: float | None = None
    correlation_to_sector: float | None = None
    sensitivity_to_usd: float | None = None
    sensitivity_to_rates: float | None = None
    # Seasonality
    best_months: list[int] = field(default_factory=list)
    worst_months: list[int] = field(default_factory=list)
    day_of_week_effect: dict[str, float] = field(default_factory=dict)
    # Event Response
    earnings_drift_days: int | None = None
    earnings_avg_move: float | None = None
    dividend_ex_date_effect: float | None = None
    # Suitability (1-10)
    intraday_suitability: float | None = None
    swing_suitability: float | None = None
    investing_suitability: float | None = None
    # Metadata
    profile_confidence: float | None = None
    last_updated: str | None = None
    data_points_used: int | None = None


@dataclass
class RegimeChangeAlert:
    """Alert ketika perilaku instrumen berubah signifikan."""

    ticker: str
    changed: bool
    old_regime: str | None
    new_regime: str | None
    volatility_change_pct: float
    momentum_shift: float
    severity: str  # LOW/MEDIUM/HIGH
    details: str


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------


class InstrumentBehaviorProfiler:
    """Calculate, store, and retrieve per-instrument behavior profiles.

    Usage:
        profiler = InstrumentBehaviorProfiler()
        profiler.profile_all_instruments()  # weekly job
        prof = profiler.get_profile("BBCA.JK")
    """

    def __init__(
        self,
        ihsg_ticker: str = _IHSG_TICKER,
        usd_ticker: str = _USD_IDR_TICKER,
        rates_ticker: str = _RATES_TICKER,
        session: Session | None = None,
    ) -> None:
        self.ihsg_ticker = ihsg_ticker
        self.usd_ticker = usd_ticker
        self.rates_ticker = rates_ticker
        self._session = session
        self._own_session = session is None

    # ── session helpers ─────────────────────────────────────────────────────

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        return get_sessionmaker()()

    def _close_session(self) -> None:
        if self._own_session and self._session is None:
            # session created ad-hoc in a method -- caller is responsible for
            # closing via context. We rely on SQLAlchemy lazy close.
            pass

    # ── data loading ────────────────────────────────────────────────────────

    def _load_ohlcv(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        """Load daily OHLCV for ``ticker`` from DB, sorted ascending."""
        sql = text(
            """
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv
            WHERE ticker = :t AND timeframe = '1d'
              AND timestamp >= NOW() - (:days || ' days')::interval
            ORDER BY timestamp ASC
            """
        )
        with get_engine().connect() as conn:
            df = pd.read_sql(
                sql, conn, params={"t": ticker, "days": int(lookback_days * 1.5)},
            )
        if df.empty:
            return df
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df

    def _load_instrument_meta(self, ticker: str) -> dict[str, Any]:
        sql = text(
            "SELECT asset_class, sector FROM instruments WHERE ticker = :t LIMIT 1"
        )
        with get_engine().connect() as conn:
            row = conn.execute(sql, {"t": ticker}).first()
        if row is None:
            return {"asset_class": None, "sector": None}
        return {"asset_class": row[0], "sector": row[1]}

    def _load_active_tickers(self, asset_classes: list[str] | None = None) -> list[str]:
        """All active tradeable tickers (optionally filtered by asset_class)."""
        if asset_classes:
            sql = text(
                "SELECT ticker FROM instruments WHERE is_active = true "
                "AND asset_class = ANY(:ac) ORDER BY ticker"
            )
            params: dict[str, Any] = {"ac": asset_classes}
        else:
            sql = text(
                "SELECT ticker FROM instruments WHERE is_active = true ORDER BY ticker"
            )
            params = {}
        with get_engine().connect() as conn:
            rows = conn.execute(sql, params).all()
        return [r[0] for r in rows]

    # ── public API ──────────────────────────────────────────────────────────

    def profile_all_instruments(
        self,
        lookback_days: int = _DEFAULT_LOOKBACK,
        asset_classes: list[str] | None = None,
        batch_size: int = 50,
    ) -> dict[str, int]:
        """Calculate and store profiles for all active instruments.

        Returns summary dict: {"profiled": N, "skipped": M, "errors": K}.
        """
        tickers = self._load_active_tickers(asset_classes)
        logger.info("Profiling %d instruments (lookback=%d days)", len(tickers), lookback_days)
        profiled = skipped = errors = 0
        for i, ticker in enumerate(tickers, 1):
            try:
                prof = self.profile_single(ticker, lookback_days=lookback_days)
                if prof.data_points_used and prof.data_points_used >= _MIN_DATA_POINTS:
                    self._store_profile(prof)
                    profiled += 1
                else:
                    skipped += 1
            except Exception as exc:
                errors += 1
                logger.warning("profile %s failed: %s", ticker, exc)
            if i % batch_size == 0:
                logger.info("  progress %d/%d (profiled=%d skipped=%d errors=%d)",
                            i, len(tickers), profiled, skipped, errors)
        logger.info("Done. profiled=%d skipped=%d errors=%d", profiled, skipped, errors)
        return {"profiled": profiled, "skipped": skipped, "errors": errors}

    def profile_single(
        self, ticker: str, lookback_days: int = _DEFAULT_LOOKBACK,
    ) -> InstrumentProfile:
        """Calculate comprehensive profile for one instrument."""
        df = self._load_ohlcv(ticker, lookback_days)
        meta = self._load_instrument_meta(ticker)
        prof = InstrumentProfile(
            ticker=ticker,
            asset_class=meta["asset_class"],
            sector=meta["sector"],
            data_points_used=len(df),
            last_updated=datetime.now(UTC).isoformat(),
        )
        if df.empty or len(df) < _MIN_DATA_POINTS:
            return prof

        df = df.set_index("timestamp")
        close = df["close"].astype(float)
        volume = df["volume"].astype(float) if "volume" in df.columns else pd.Series(0.0,
            index=df.index)
        returns = close.pct_change(fill_method=None).dropna()

        # Volatility
        prof.avg_daily_volatility = float(returns.std() * 100) if len(returns) > 1 else 0.0
        prof.volatility_regime = self._classify_volatility(prof.avg_daily_volatility)
        prof.volatility_clustering_coefficient = self._volatility_clustering(returns)

        # Momentum vs mean-reversion
        strength, lookback = self._momentum_vs_meanrevert(close)
        prof.momentum_strength = strength
        prof.optimal_momentum_lookback = lookback
        prof.mean_reversion_halflife = self._mean_reversion_halflife(returns)

        # Liquidity
        adv = float(volume.tail(60).mean()) if len(volume) >= 60 else float(volume.mean())
        prof.avg_daily_volume = int(adv) if adv == adv else 0  # NaN guard
        prof.avg_spread_pct = self._estimate_spread(df)
        prof.liquidity_score = self._liquidity_score(adv, prof.avg_spread_pct)
        prof.optimal_position_size_pct = self._optimal_position_size_pct(adv,
            prof.avg_daily_volatility)

        # Correlation & sensitivity
        prof.beta_to_ihsg = self._beta_to_index(close, self.ihsg_ticker, lookback_days)
        prof.correlation_to_sector = self._correlation_to_sector(close, meta["sector"],
            lookback_days)
        prof.sensitivity_to_usd = self._sensitivity(close, self.usd_ticker, lookback_days)
        prof.sensitivity_to_rates = self._sensitivity(close, self.rates_ticker, lookback_days)

        # Seasonality
        best, worst = self._seasonality(close)
        prof.best_months = best
        prof.worst_months = worst
        prof.day_of_week_effect = self._day_of_week_effect(returns)

        # Event response (best-effort -- data may be sparse)
        prof.earnings_drift_days, prof.earnings_avg_move = self._earnings_response(ticker)
        prof.dividend_ex_date_effect = self._dividend_ex_date_effect(ticker)

        # Suitability
        suit = self.calculate_trading_style_suitability_from_data(prof)
        prof.intraday_suitability = suit["intraday"]
        prof.swing_suitability = suit["swing"]
        prof.investing_suitability = suit["investing"]

        # Confidence: function of data points and completeness
        prof.profile_confidence = self._confidence(prof)
        return prof

    def get_profile(self, ticker: str) -> InstrumentProfile | None:
        """Retrieve stored profile from database. None if not found."""
        sql = text("SELECT * FROM instrument_behavior_profiles WHERE ticker = :t LIMIT 1")
        with get_engine().connect() as conn:
            row = conn.execute(sql, {"t": ticker}).mappings().first()
        if row is None:
            return None
        return self._row_to_profile(dict(row))

    def calculate_volatility_regime(self, ticker: str) -> str:
        """Classify volatility: LOW (<1%), MEDIUM (1-2%), HIGH (2-4%), EXTREME (>4%)."""
        df = self._load_ohlcv(ticker, 252)
        if df.empty or len(df) < 20:
            return "LOW"
        returns = df["close"].astype(float).pct_change(fill_method=None).dropna()
        avg_vol = float(returns.std() * 100) if len(returns) > 1 else 0.0
        return self._classify_volatility(avg_vol)

    def calculate_momentum_vs_meanrevert(self, ticker: str) -> tuple[float, int]:
        """Return (strength, optimal_lookback). positive=momentum, negative=mean-revert."""
        df = self._load_ohlcv(ticker, _DEFAULT_LOOKBACK)
        if df.empty or len(df) < _MIN_DATA_POINTS:
            return (0.0, 20)
        return self._momentum_vs_meanrevert(df["close"].astype(float))

    def calculate_trading_style_suitability(self, ticker: str) -> dict[str, float]:
        """Score 1-10 for intraday/swing/investing suitability."""
        prof = self.get_profile(ticker)
        if prof is not None and prof.intraday_suitability is not None:
            return {
                "intraday": float(prof.intraday_suitability),
                "swing": float(prof.swing_suitability),
                "investing": float(prof.investing_suitability),
            }
        prof = self.profile_single(ticker)
        return self.calculate_trading_style_suitability_from_data(prof)

    def detect_regime_change(self, ticker: str) -> RegimeChangeAlert:
        """Detect if instrument behavior has changed significantly.

        Compares stored profile (last_updated) vs fresh 60-day window.
        """
        stored = self.get_profile(ticker)
        df = self._load_ohlcv(ticker, 60)
        if df.empty or len(df) < 30:
            return RegimeChangeAlert(
                ticker=ticker, changed=False, old_regime=None, new_regime=None,
                volatility_change_pct=0.0, momentum_shift=0.0, severity="LOW",
                details="insufficient recent data",
            )
        returns = df["close"].astype(float).pct_change(fill_method=None).dropna()
        new_vol = float(returns.std() * 100) if len(returns) > 1 else 0.0
        new_regime = self._classify_volatility(new_vol)
        old_vol = (
            float(stored.avg_daily_volatility)
            if stored and stored.avg_daily_volatility else new_vol
        )
        old_regime = stored.volatility_regime if stored else None
        vol_change = ((new_vol - old_vol) / old_vol * 100) if old_vol > 0 else 0.0
        # Momentum shift via 20-day return sign vs stored
        recent_ret = (
            float(df["close"].astype(float).pct_change(20).iloc[-1])
            if len(df) > 20 else 0.0
        )
        old_mom = (
            float(stored.momentum_strength)
            if stored and stored.momentum_strength is not None else 0.0
        )
        mom_shift = recent_ret - old_mom
        changed = (
            old_regime != new_regime
            or abs(vol_change) > 50.0
            or abs(mom_shift) > 0.15
        )
        severity = "LOW"
        if abs(vol_change) > 100 or abs(mom_shift) > 0.30:
            severity = "HIGH"
        elif abs(vol_change) > 50 or abs(mom_shift) > 0.15:
            severity = "MEDIUM"
        return RegimeChangeAlert(
            ticker=ticker, changed=changed,
            old_regime=old_regime, new_regime=new_regime,
            volatility_change_pct=round(vol_change, 2),
            momentum_shift=round(mom_shift, 4),
            severity=severity,
            details=(
                f"vol {old_vol:.2f}%→{new_vol:.2f}% ({vol_change:+.1f}%), "
                f"regime {old_regime}→{new_regime}, momentum shift {mom_shift:+.4f}"
            ),
        )

    # ── calculation helpers ─────────────────────────────────────────────────

    @staticmethod
    def _classify_volatility(avg_vol_pct: float) -> str:
        if avg_vol_pct < _VOL_REGIME_THRESHOLDS[0]:
            return "LOW"
        if avg_vol_pct < _VOL_REGIME_THRESHOLDS[1]:
            return "MEDIUM"
        if avg_vol_pct < _VOL_REGIME_THRESHOLDS[2]:
            return "HIGH"
        return "EXTREME"

    @staticmethod
    def _volatility_clustering(returns: pd.Series) -> float:
        """Engle's ARCH-LM-like coefficient: corr(|r_t|, |r_{t-1}|).

        Higher → more clustering (volatility begets volatility).
        Range [-1, 1]; typical 0.1-0.4 for equities.
        """
        if len(returns) < 30:
            return 0.0
        abs_r = returns.abs()
        return float(abs_r.autocorr(lag=1) or 0.0)

    @staticmethod
    def _momentum_vs_meanrevert(close: pd.Series) -> tuple[float, int]:
        """Find optimal lookback via autocorrelation of returns.

        Positive autocorrelation at lag N → momentum at N.
        Negative → mean-reversion at N.
        Returns (strength, optimal_lookback) where strength is the
        autocorrelation with largest |value| across candidate lookbacks.
        """
        returns = close.pct_change(fill_method=None).dropna()
        if len(returns) < 60:
            return (0.0, 20)
        candidates = [5, 10, 20, 60, 120, 252]
        best_strength = 0.0
        best_lag = 20
        for lag in candidates:
            if len(returns) <= lag + 5:
                continue
            ac = float(returns.autocorr(lag=lag) or 0.0)
            if abs(ac) > abs(best_strength):
                best_strength = ac
                best_lag = lag
        return (round(best_strength, 4), best_lag)

    @staticmethod
    def _mean_reversion_halflife(returns: pd.Series) -> float | None:
        """Ornstein-Uhlenbeck half-life of mean reversion (in days).

        Uses AR(1) on log prices: hl = -ln(2) / ln(phi).
        Returns None if process is not mean-reverting (phi >= 0 or >= 1).
        """
        if len(returns) < 60:
            return None
        # Use cumulative log returns as proxy for price
        log_p = np.log(1 + returns).cumsum()
        # AR(1): Δy_t = alpha + φ·y_{t-1} + ε
        y = log_p.values
        if len(y) < 30:
            return None
        dy = np.diff(y)
        y_lag = y[:-1]
        # OLS: dy = a + b*y_lag
        x = np.column_stack([np.ones_like(y_lag), y_lag])
        try:
            coef, *_ = np.linalg.lstsq(x, dy, rcond=None)
            phi = coef[1]
        except Exception:
            return None
        if phi >= 0 or phi >= -1e-9:
            return None  # not mean-reverting
        hl = -np.log(2) / np.log(1 + phi) if (1 + phi) > 0 else None
        return round(float(hl), 2) if hl is not None and hl == hl else None

    @staticmethod
    def _estimate_spread(df: pd.DataFrame) -> float:
        """Estimate average spread % from high-low range.

        Proxy: avg((high - low) / close) * 0.5 (half-spread assumption).
        """
        if df.empty or len(df) < 20:
            return 0.0
        hl = ((df["high"].astype(float) - df["low"].astype(float))
              / df["close"].astype(float)).dropna()
        return round(float(hl.tail(60).mean() * 0.5 * 100), 4) if not hl.empty else 0.0

    @staticmethod
    def _liquidity_score(adv: float, spread_pct: float) -> float:
        """Liquidity score 1-10. Higher = more liquid."""
        score = 5.0
        if adv >= 10_000_000:
            score += 4.0
        elif adv >= 1_000_000:
            score += 2.5
        elif adv >= 100_000:
            score += 1.0
        elif adv < 10_000:
            score -= 2.0
        if spread_pct < 0.1:
            score += 1.0
        elif spread_pct > 1.0:
            score -= 1.5
        return float(max(1.0, min(10.0, round(score, 2))))

    @staticmethod
    def _optimal_position_size_pct(adv: float, avg_vol_pct: float) -> float:
        """Max % of daily volume to trade without >0.5% market impact.

        Square-root impact model: impact ≈ 0.1 · sqrt(participation_rate) · vol.
        Solve for impact ≤ 0.5% → participation ≤ (0.5 / (0.1·vol))².
        Capped at 10% (regulatory prudence).
        """
        if avg_vol_pct <= 0 or adv <= 0:
            return 0.01
        vol = max(avg_vol_pct, 0.5)  # floor to avoid blow-up
        pr = (0.5 / (0.1 * vol)) ** 2 / 100.0  # as fraction
        return float(max(0.005, min(0.10, round(pr, 4))))

    def _beta_to_index(self, close: pd.Series, index_ticker: str, lookback: int) -> float:
        idx_df = self._load_ohlcv(index_ticker, lookback)
        if idx_df.empty or len(idx_df) < 20:
            return 0.0
        s_ret = close.pct_change(fill_method=None).dropna()
        i_ret = idx_df["close"].astype(float).pct_change(fill_method=None).dropna()
        aligned = pd.concat([s_ret, i_ret], axis=1, join="inner").dropna()
        if len(aligned) < 20:
            return 0.0
        cov = float(aligned.iloc[:, 0].cov(aligned.iloc[:, 1]))
        var = float(aligned.iloc[:, 1].var())
        return round(cov / var, 4) if var > 0 else 0.0

    def _correlation_to_sector(
        self, close: pd.Series, sector: str | None, lookback: int,
    ) -> float:
        """Correlation to equal-weighted sector index (excl. self)."""
        if not sector:
            return 0.0
        sql = text(
            "SELECT ticker FROM instruments WHERE sector = :s AND is_active = true "
            "AND ticker <> :self LIMIT 20"
        )
        with get_engine().connect() as conn:
            peers = [r[0] for r in conn.execute(sql, {"s": sector, "self": close.name or ""}).all()]
        if not peers:
            return 0.0
        s_ret = close.pct_change(fill_method=None).dropna()
        rets: list[pd.Series] = []
        for p in peers[:10]:
            pdf = self._load_ohlcv(p, lookback)
            if pdf.empty or len(pdf) < 60:
                continue
            rets.append(pdf["close"].astype(float).pct_change(fill_method=None).dropna())
        if not rets:
            return 0.0
        sector_idx = pd.concat(rets, axis=1).mean(axis=1)
        aligned = pd.concat([s_ret, sector_idx], axis=1, join="inner").dropna()
        if len(aligned) < 20:
            return 0.0
        return round(float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1])), 4)

    def _sensitivity(self, close: pd.Series, factor_ticker: str, lookback: int) -> float:
        """Beta-like sensitivity of stock returns to factor returns."""
        f_df = self._load_ohlcv(factor_ticker, lookback)
        if f_df.empty or len(f_df) < 20:
            return 0.0
        s_ret = close.pct_change(fill_method=None).dropna()
        f_ret = f_df["close"].astype(float).pct_change(fill_method=None).dropna()
        aligned = pd.concat([s_ret, f_ret], axis=1, join="inner").dropna()
        if len(aligned) < 20:
            return 0.0
        cov = float(aligned.iloc[:, 0].cov(aligned.iloc[:, 1]))
        var = float(aligned.iloc[:, 1].var())
        return round(cov / var, 4) if var > 0 else 0.0

    @staticmethod
    def _seasonality(close: pd.Series) -> tuple[list[int], list[int]]:
        """Best/worst months by average monthly return.

        Returns (best_months, worst_months) as list of month numbers 1-12.
        """
        if len(close) < 252:
            return ([], [])
        monthly = close.resample("ME").last().dropna()
        if len(monthly) < 12:
            return ([], [])
        monthly_ret = monthly.pct_change(fill_method=None).dropna()
        if monthly_ret.empty:
            return ([], [])
        avg_by_month = monthly_ret.groupby(monthly_ret.index.month).mean()
        # Best 3 / worst 3 months
        sorted_months = avg_by_month.sort_values(ascending=False)
        best = [int(m) for m in sorted_months.head(3).index.tolist()]
        worst = [int(m) for m in sorted_months.tail(3).index.tolist()]
        return (best, worst)

    @staticmethod
    def _day_of_week_effect(returns: pd.Series) -> dict[str, float]:
        """Average return by day of week (Mon=0..Sun=6). Returns dict {day_name: avg_ret_pct}."""
        if len(returns) < 60:
            return {}
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        by_dow = returns.groupby(returns.index.dayofweek).mean() * 100
        return {names[d]: round(float(by_dow.get(d, 0.0)), 4) for d in range(5)}

    def _earnings_response(self, ticker: str) -> tuple[int | None, float | None]:
        """Earnings drift days + avg move. Best-effort from earnings_calendar."""
        sql = text(
            """
            SELECT earnings_date FROM earnings_calendar
            WHERE ticker = :t AND earnings_date <= NOW()
            ORDER BY earnings_date DESC LIMIT 20
            """
        )
        try:
            with get_engine().connect() as conn:
                rows = conn.execute(sql, {"t": ticker}).all()
        except Exception:
            return (None, None)
        if not rows:
            return (None, None)
        df = self._load_ohlcv(ticker, 252)
        if df.empty or len(df) < 60:
            return (None, None)
        df = df.set_index("timestamp")
        moves: list[float] = []
        drifts: list[int] = []
        for r in rows:
            d = r[0]
            if hasattr(d, "date"):
                d = d.date()
            # 5-day post-earnings drift
            post = df.loc[df.index.date > d].head(5)
            if post.empty:
                continue
            pre_close = df.loc[df.index.date <= d, "close"].astype(float)
            if pre_close.empty:
                continue
            base = float(pre_close.iloc[-1])
            day1 = float(post["close"].iloc[0])
            moves.append((day1 - base) / base * 100)
            # Drift days: how many of 5 days move in same direction as day1
            sign = 1 if day1 > base else -1
            cum = 0
            for c in post["close"].astype(float).tolist():
                if (1 if c > base else -1) == sign:
                    cum += 1
                else:
                    break
            drifts.append(cum)
        if not moves:
            return (None, None)
        return (int(np.median(drifts)), round(float(np.mean(moves)), 4))

    def _dividend_ex_date_effect(self, ticker: str) -> float | None:
        """Avg abnormal return on dividend ex-date (%). Best-effort."""
        sql = text(
            """
            SELECT ex_date FROM dividends WHERE ticker = :t
            AND ex_date <= NOW() ORDER BY ex_date DESC LIMIT 20
            """
        )
        try:
            with get_engine().connect() as conn:
                rows = conn.execute(sql, {"t": ticker}).all()
        except Exception:
            return None
        if not rows:
            return None
        df = self._load_ohlcv(ticker, 252)
        if df.empty or len(df) < 60:
            return None
        df = df.set_index("timestamp")
        effects: list[float] = []
        for r in rows:
            d = r[0]
            if hasattr(d, "date"):
                d = d.date()
            window = df.loc[df.index.date >= d].head(2)
            if len(window) < 2:
                continue
            ret = float(window["close"].astype(float).pct_change().iloc[-1]) * 100
            effects.append(ret)
        if not effects:
            return None
        return round(float(np.mean(effects)), 4)

    @staticmethod
    def calculate_trading_style_suitability_from_data(prof: InstrumentProfile) -> dict[str, float]:
        """Score 1-10 for intraday/swing/investing suitability from a profile."""
        vol = prof.avg_daily_volatility or 0.0
        liq = prof.liquidity_score or 5.0
        spread = prof.avg_spread_pct or 0.5
        mom = prof.momentum_strength or 0.0
        hl = prof.mean_reversion_halflife or 0.0
        beta = prof.beta_to_ihsg or 1.0
        n = prof.data_points_used or 0

        # Intraday: wants high liquidity, low spread, high volatility (but not extreme),
        # low mean-reversion halflife (intraday mean revert OK), moderate momentum.
        intraday = 5.0
        intraday += (liq - 5) * 0.6
        intraday -= max(0, spread - 0.3) * 2
        if 1.5 <= vol <= 4.0:
            intraday += 1.5
        elif vol > 4.0:
            intraday -= 1.0
        if 0 < hl < 5:
            intraday += 0.5

        # Swing: wants moderate volatility, momentum (positive autocorr),
        # moderate halflife (5-30 days), moderate beta.
        swing = 5.0
        if 1.5 <= vol <= 4.0:
            swing += 1.5
        elif vol > 4:
            swing -= 0.5
        if mom > 0.05:
            swing += 1.0
        elif mom < -0.05:
            swing += 0.5  # mean-revert swing also viable
        if 5 <= hl <= 30:
            swing += 1.0
        if 0.7 <= beta <= 1.5:
            swing += 0.5
        swing += (liq - 5) * 0.2

        # Investing: wants low volatility, high data history, low spread,
        # positive or stable long-run behavior, low beta desirable but not required.
        investing = 5.0
        if vol < 2.0:
            investing += 1.5
        elif vol > 4.0:
            investing -= 1.5
        if n >= 756:
            investing += 1.5
        elif n >= 252:
            investing += 0.5
        else:
            investing -= 1.0
        investing += (liq - 5) * 0.3
        if spread < 0.3:
            investing += 0.5

        return {
            "intraday": float(max(1.0, min(10.0, round(intraday, 2)))),
            "swing": float(max(1.0, min(10.0, round(swing, 2)))),
            "investing": float(max(1.0, min(10.0, round(investing, 2)))),
        }

    @staticmethod
    def _confidence(prof: InstrumentProfile) -> float:
        """Profile confidence 1-10 based on data completeness & points."""
        n = prof.data_points_used or 0
        score = 0.0
        if n >= 756:
            score += 4.0
        elif n >= 252:
            score += 2.5
        elif n >= 120:
            score += 1.5
        elif n >= 60:
            score += 0.5
        # Completeness: count non-None core fields
        core = [
            prof.avg_daily_volatility, prof.volatility_regime,
            prof.momentum_strength, prof.beta_to_ihsg,
            prof.liquidity_score, prof.intraday_suitability,
        ]
        filled = sum(1 for x in core if x is not None)
        score += (filled / len(core)) * 4.0
        # Seasonality bonus
        if prof.best_months:
            score += 1.0
        # Event response bonus
        if prof.earnings_drift_days is not None or prof.dividend_ex_date_effect is not None:
            score += 1.0
        return float(max(1.0, min(10.0, round(score, 2))))

    # ── persistence ─────────────────────────────────────────────────────────

    def _store_profile(self, prof: InstrumentProfile) -> None:
        """Upsert profile to ``instrument_behavior_profiles``."""
        col_map = {
            "ticker": prof.ticker,
            "asset_class": prof.asset_class,
            "sector": prof.sector,
            "avg_daily_volatility": prof.avg_daily_volatility,
            "volatility_regime": prof.volatility_regime,
            "volatility_clustering_coefficient": prof.volatility_clustering_coefficient,
            "momentum_strength": prof.momentum_strength,
            "optimal_momentum_lookback": prof.optimal_momentum_lookback,
            "mean_reversion_halflife": prof.mean_reversion_halflife,
            "avg_daily_volume": prof.avg_daily_volume,
            "avg_spread_pct": prof.avg_spread_pct,
            "liquidity_score": prof.liquidity_score,
            "optimal_position_size_pct": prof.optimal_position_size_pct,
            "beta_to_ihsg": prof.beta_to_ihsg,
            "correlation_to_sector": prof.correlation_to_sector,
            "sensitivity_to_usd": prof.sensitivity_to_usd,
            "sensitivity_to_rates": prof.sensitivity_to_rates,
            "best_months": json.dumps(prof.best_months) if prof.best_months else None,
            "worst_months": json.dumps(prof.worst_months) if prof.worst_months else None,
            "day_of_week_effect": (
                json.dumps(prof.day_of_week_effect) if prof.day_of_week_effect else None
            ),
            "earnings_drift_days": prof.earnings_drift_days,
            "earnings_avg_move": prof.earnings_avg_move,
            "dividend_ex_date_effect": prof.dividend_ex_date_effect,
            "intraday_suitability": prof.intraday_suitability,
            "swing_suitability": prof.swing_suitability,
            "investing_suitability": prof.investing_suitability,
            "profile_confidence": prof.profile_confidence,
            "last_updated": datetime.now(UTC),
            "data_points_used": prof.data_points_used,
        }
        # Build INSERT ... ON CONFLICT (ticker) DO UPDATE
        cols = list(col_map.keys())
        placeholders = ", ".join(f":{c}" for c in cols)
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "ticker")
        sql = text(
            f"INSERT INTO instrument_behavior_profiles ({', '.join(cols)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (ticker) DO UPDATE SET {updates}"
        )
        # JSON columns need explicit JSON serialization for psycopg2
        with get_engine().begin() as conn:
            conn.execute(sql, col_map)

    @staticmethod
    def _row_to_profile(row: dict[str, Any]) -> InstrumentProfile:
        """Convert DB row mapping to InstrumentProfile."""
        def _f(v: Any) -> float | None:
            if v is None:
                return None
            if isinstance(v, Decimal):
                return float(v)
            return float(v)

        def _i(v: Any) -> int | None:
            return int(v) if v is not None else None

        return InstrumentProfile(
            ticker=row["ticker"],
            asset_class=row.get("asset_class"),
            sector=row.get("sector"),
            avg_daily_volatility=_f(row.get("avg_daily_volatility")),
            volatility_regime=row.get("volatility_regime"),
            volatility_clustering_coefficient=_f(row.get("volatility_clustering_coefficient")),
            momentum_strength=_f(row.get("momentum_strength")),
            optimal_momentum_lookback=_i(row.get("optimal_momentum_lookback")),
            mean_reversion_halflife=_f(row.get("mean_reversion_halflife")),
            avg_daily_volume=_i(row.get("avg_daily_volume")),
            avg_spread_pct=_f(row.get("avg_spread_pct")),
            liquidity_score=_f(row.get("liquidity_score")),
            optimal_position_size_pct=_f(row.get("optimal_position_size_pct")),
            beta_to_ihsg=_f(row.get("beta_to_ihsg")),
            correlation_to_sector=_f(row.get("correlation_to_sector")),
            sensitivity_to_usd=_f(row.get("sensitivity_to_usd")),
            sensitivity_to_rates=_f(row.get("sensitivity_to_rates")),
            best_months=row.get("best_months") or [],
            worst_months=row.get("worst_months") or [],
            day_of_week_effect=row.get("day_of_week_effect") or {},
            earnings_drift_days=_i(row.get("earnings_drift_days")),
            earnings_avg_move=_f(row.get("earnings_avg_move")),
            dividend_ex_date_effect=_f(row.get("dividend_ex_date_effect")),
            intraday_suitability=_f(row.get("intraday_suitability")),
            swing_suitability=_f(row.get("swing_suitability")),
            investing_suitability=_f(row.get("investing_suitability")),
            profile_confidence=_f(row.get("profile_confidence")),
            last_updated=str(row["last_updated"]) if row.get("last_updated") else None,
            data_points_used=_i(row.get("data_points_used")),
        )


__all__ = [
    "InstrumentBehaviorProfiler",
    "InstrumentProfile",
    "RegimeChangeAlert",
]
