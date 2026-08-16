"""Cross-Market Coefficient Engine (catatan.md TAHAP 3 -- Prompt 3.1).

Menghitung dan menyimpan koefisien cross-market dari indeks global ke target
ticker (default: IHSG/IDX), dengan:

1. Granger causality test (memakai ``market.analysis.causal_discovery``).
2. Lag analysis 1-5 hari dengan optimal lag detection.
3. Magnitude coefficient: % perubahan target per 1% perubahan source.
4. Asymmetric up/down: koefisien terpisah untuk hari source naik vs turun
   (bull vs bear behavior).
5. Regime classification: BULL/BEAR/SIDEWAYS berdasarkan 200-day MA slope.

Persisten ke tabel ``cross_market_coefficients`` (migration 0025), di-update
mingguan via scheduled job.

Integration:
- Signal generators query ``get_coefficient(source, target)`` untuk overnight
  gap prediction.
- ``DecisionEngine`` dapat menggunakan aggregate coefficients untuk market
  driver narrative.

Referensi:
- catatan.md L610-L623 (Prompt 3.1)
- pustaka/36-gap-data-timezone-global-idx.md
- pustaka/92-multi-market-multi-asset-trading-system.md §4
- pustaka/101-global-idx-advanced-models.md (DCC-GARCH, Diebold-Yilmaz)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text

from market.analysis.causal_discovery import granger_causality
from market.db.engine import get_engine

logger = logging.getLogger(__name__)

# Default source indices (catatan.md L615: S&P500, HSI, Nikkei)
DEFAULT_SOURCE_INDICES: list[str] = ["^GSPC", "^HSI", "^N225"]
# Default target: IHSG composite
DEFAULT_TARGET_TICKER = "^JKSE"
# Lag range (catatan.md L616: 1-5 hari)
DEFAULT_MAX_LAG = 5
# Minimum data points for reliable estimation
_MIN_DATA_POINTS = 120


@dataclass
class CrossMarketCoefficient:
    """Single cross-market coefficient record (mirrors DB row)."""

    source_index: str
    target_ticker: str
    lag_days: int
    coefficient: float | None = None
    p_value: float | None = None
    f_statistic: float | None = None
    asymmetric_up: float | None = None
    asymmetric_down: float | None = None
    regime: str | None = None
    sample_size: int | None = None
    last_updated: str | None = None


class CrossMarketCoefficientEngine:
    """Engine untuk menghitung & persist koefisien cross-market.

    Usage:
        engine = CrossMarketCoefficientEngine()
        engine.update_all()  # weekly job
        coef = engine.get_coefficient("^GSPC", "^JKSE", lag=1)
    """

    def __init__(
        self,
        source_indices: list[str] | None = None,
        target_ticker: str = DEFAULT_TARGET_TICKER,
        max_lag: int = DEFAULT_MAX_LAG,
        lookback_days: int = 756,
    ) -> None:
        self.source_indices = source_indices or DEFAULT_SOURCE_INDICES
        self.target_ticker = target_ticker
        self.max_lag = max_lag
        self.lookback_days = lookback_days

    # ── data loading ────────────────────────────────────────────────────────

    def _load_returns(self, ticker: str) -> pd.Series:
        """Load daily returns for ``ticker`` from DB, indexed by date (not ts).

        Different exchanges close at different UTC times (e.g. ^GSPC 20:00 UTC,
        ^JKSE 08:50 UTC), so we normalize to calendar date for lag analysis.
        """
        sql = text(
            """
            SELECT timestamp, close FROM ohlcv
            WHERE ticker = :t AND timeframe = '1d'
              AND timestamp >= NOW() - (:days || ' days')::interval
            ORDER BY timestamp ASC
            """
        )
        with get_engine().connect() as conn:
            df = pd.read_sql(sql, conn, params={"t": ticker, "days": int(self.lookback_days * 1.5)})
        if df.empty:
            return pd.Series(dtype=float)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp")
        # Normalize to date -- take last close per calendar date
        df["date"] = df.index.date
        daily = df.groupby("date")["close"].last().astype(float)
        daily.name = ticker
        return daily.pct_change(fill_method=None).dropna()

    # ── public API ──────────────────────────────────────────────────────────

    def update_all(self) -> dict[str, int]:
        """Compute & store coefficients for all source indices → target.

        Returns summary {"updated": N, "skipped": M, "errors": K}.
        """
        updated = skipped = errors = 0
        target_ret = self._load_returns(self.target_ticker)
        if len(target_ret) < _MIN_DATA_POINTS:
            logger.warning("Target %s has only %d data points -- skipping",
                           self.target_ticker, len(target_ret))
            return {"updated": 0, "skipped": len(self.source_indices), "errors": 0}
        regime = self._classify_regime(target_ret)
        for src in self.source_indices:
            try:
                src_ret = self._load_returns(src)
                if len(src_ret) < _MIN_DATA_POINTS:
                    skipped += 1
                    logger.info("Skip %s → %s: only %d data points",
                                src, self.target_ticker, len(src_ret))
                    continue
                coefs = self.compute_coefficients(src_ret, target_ret, regime)
                for c in coefs:
                    self._store(c)
                updated += len(coefs)
            except Exception as exc:
                errors += 1
                logger.warning("update %s failed: %s", src, exc)
        logger.info("CrossMarketCoefficientEngine.update_all: updated=%d skipped=%d errors=%d",
                    updated, skipped, errors)
        return {"updated": updated, "skipped": skipped, "errors": errors}

    def compute_coefficients(
        self,
        source_returns: pd.Series,
        target_returns: pd.Series,
        regime: str | None = None,
    ) -> list[CrossMarketCoefficient]:
        """Compute coefficients for all lags 1..max_lag.

        For each lag:
        - Granger F-stat, p-value, best lag (via causal_discovery).
        - Magnitude coefficient: regression β of target_t on source_{t-lag}.
        - Asymmetric up/down: β separately for source > 0 and source < 0.
        """
        # Align on common dates
        src_name = source_returns.name or "source"
        tgt_name = target_returns.name or self.target_ticker
        aligned = pd.concat(
            [source_returns.rename(src_name), target_returns.rename(tgt_name)],
            axis=1, join="inner",
        ).dropna()
        if len(aligned) < _MIN_DATA_POINTS:
            return []
        out: list[CrossMarketCoefficient] = []
        src = aligned[src_name]
        tgt = aligned[tgt_name]
        for lag in range(1, self.max_lag + 1):
            # Granger F-stat & p-value
            f_stat, p_val, _best_lag = granger_causality(src, tgt, max_lag=lag)
            # Magnitude coefficient: OLS tgt_t = alpha + β·src_{t-lag}
            shifted_src = src.shift(lag)
            pair = pd.concat([shifted_src.rename("s"), tgt.rename("t")], axis=1).dropna()
            if len(pair) < 60:
                continue
            coef = self._regression_beta(pair["s"].values, pair["t"].values)
            # Asymmetric: split by sign of source
            up_mask = pair["s"] > 0
            down_mask = pair["s"] < 0
            up_coef = (
                self._regression_beta(pair["s"][up_mask].values, pair["t"][up_mask].values)
                if up_mask.sum() >= 30 else None
            )
            down_coef = (
                self._regression_beta(pair["s"][down_mask].values, pair["t"][down_mask].values)
                if down_mask.sum() >= 30 else None
            )
            out.append(CrossMarketCoefficient(
                source_index=src.name or "",
                target_ticker=tgt.name or self.target_ticker,
                lag_days=lag,
                coefficient=coef,
                p_value=round(float(p_val), 4) if p_val == p_val else None,
                f_statistic=round(float(f_stat), 4) if f_stat == f_stat else None,
                asymmetric_up=up_coef,
                asymmetric_down=down_coef,
                regime=regime,
                sample_size=len(pair),
                last_updated=datetime.now(UTC).isoformat(),
            ))
        return out

    def get_coefficient(
        self, source_index: str, target_ticker: str | None = None, lag: int = 1,
    ) -> CrossMarketCoefficient | None:
        """Retrieve stored coefficient. None if not found."""
        tgt = target_ticker or self.target_ticker
        sql = text(
            "SELECT * FROM cross_market_coefficients "
            "WHERE source_index = :s AND target_ticker = :t AND lag_days = :l LIMIT 1"
        )
        with get_engine().connect() as conn:
            row = conn.execute(sql, {"s": source_index, "t": tgt, "l": lag}).mappings().first()
        if row is None:
            return None
        return self._row_to_coef(dict(row))

    def get_all_for_target(
        self, target_ticker: str | None = None,
    ) -> list[CrossMarketCoefficient]:
        """All stored coefficients pointing to ``target_ticker``."""
        tgt = target_ticker or self.target_ticker
        sql = text(
            "SELECT * FROM cross_market_coefficients WHERE target_ticker = :t "
            "ORDER BY source_index, lag_days"
        )
        with get_engine().connect() as conn:
            rows = conn.execute(sql, {"t": tgt}).mappings().all()
        return [self._row_to_coef(dict(r)) for r in rows]

    def get_optimal_lag(
        self, source_index: str, target_ticker: str | None = None,
    ) -> tuple[int, float]:
        """Return (optimal_lag, coefficient) -- lag with lowest p-value."""
        tgt = target_ticker or self.target_ticker
        all_coefs = self.get_all_for_target(tgt)
        relevant = [
            c for c in all_coefs
            if c.source_index == source_index and c.p_value is not None
        ]
        if not relevant:
            return (0, 0.0)
        best = min(relevant, key=lambda c: c.p_value or 1.0)
        return (best.lag_days, best.coefficient or 0.0)

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _regression_beta(x: np.ndarray, y: np.ndarray) -> float | None:
        """OLS β: y = alpha + β·x. Returns β or None if degenerate."""
        if len(x) < 30:
            return None
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        if len(x) < 30 or np.var(x) < 1e-12:
            return None
        X = np.column_stack([np.ones_like(x), x])
        try:
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            return round(float(beta[1]), 4)
        except Exception:
            return None

    @staticmethod
    def _classify_regime(returns: pd.Series) -> str:
        """Classify market regime: BULL/BEAR/SIDEWAYS via 200-day cumulative.

        BULL if 200-day cumulative return > +10%, BEAR if < -10%, else SIDEWAYS.
        """
        if len(returns) < 60:
            return "SIDEWAYS"
        window = min(200, len(returns))
        cum = float((1 + returns.tail(window)).prod() - 1) * 100
        if cum > 10:
            return "BULL"
        if cum < -10:
            return "BEAR"
        return "SIDEWAYS"

    # ── persistence ─────────────────────────────────────────────────────────

    def _store(self, c: CrossMarketCoefficient) -> None:
        col_map = {
            "source_index": c.source_index,
            "target_ticker": c.target_ticker,
            "lag_days": c.lag_days,
            "coefficient": c.coefficient,
            "p_value": c.p_value,
            "f_statistic": c.f_statistic,
            "asymmetric_up": c.asymmetric_up,
            "asymmetric_down": c.asymmetric_down,
            "regime": c.regime,
            "sample_size": c.sample_size,
            "last_updated": datetime.now(UTC),
        }
        cols = list(col_map.keys())
        placeholders = ", ".join(f":{c_}" for c_ in cols)
        updates = ", ".join(
            f"{c_} = EXCLUDED.{c_}" for c_ in cols
            if c_ not in ("source_index", "target_ticker", "lag_days")
        )
        sql = text(
            f"INSERT INTO cross_market_coefficients ({', '.join(cols)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (source_index, target_ticker, lag_days) DO UPDATE SET {updates}"
        )
        with get_engine().begin() as conn:
            conn.execute(sql, col_map)

    @staticmethod
    def _row_to_coef(row: dict[str, Any]) -> CrossMarketCoefficient:
        def _f(v: Any) -> float | None:
            if v is None:
                return None
            if isinstance(v, Decimal):
                return float(v)
            return float(v)

        def _i(v: Any) -> int | None:
            return int(v) if v is not None else None

        return CrossMarketCoefficient(
            source_index=row["source_index"],
            target_ticker=row["target_ticker"],
            lag_days=int(row["lag_days"]),
            coefficient=_f(row.get("coefficient")),
            p_value=_f(row.get("p_value")),
            f_statistic=_f(row.get("f_statistic")),
            asymmetric_up=_f(row.get("asymmetric_up")),
            asymmetric_down=_f(row.get("asymmetric_down")),
            regime=row.get("regime"),
            sample_size=_i(row.get("sample_size")),
            last_updated=str(row["last_updated"]) if row.get("last_updated") else None,
        )


__all__ = [
    "DEFAULT_SOURCE_INDICES",
    "DEFAULT_TARGET_TICKER",
    "CrossMarketCoefficient",
    "CrossMarketCoefficientEngine",
]
