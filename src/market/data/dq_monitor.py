"""Data quality monitor & alert automation (Gap #10).

Computes data quality scores per ticker on-the-fly and generates alerts
when quality drops below thresholds. Avoids schema changes to the
partitioned ``stock_prices`` table by computing DQ metrics at query time.

DQ score components (0-1 scale, weighted):
- Completeness: % of expected trading days present in last N days
- Gap detection: missing dates in the sequence
- Outlier detection: extreme price movements (>20% daily change)
- Volume anomaly: zero-volume days ratio
- Staleness: days since last data update

Alert thresholds:
- DQ score < 0.7 → WARNING alert
- DQ score < 0.5 → ERROR alert
- Staleness > 7 days → WARNING alert
- Zero-volume ratio > 30% → WARNING alert
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Thresholds
DQ_WARNING_THRESHOLD = 0.7
DQ_ERROR_THRESHOLD = 0.5
STALENESS_WARNING_DAYS = 7
ZERO_VOLUME_RATIO_THRESHOLD = 0.30
EXTREME_PRICE_CHANGE_PCT = 20.0
DEFAULT_LOOKBACK_DAYS = 60

# Weights for composite DQ score
DQ_WEIGHTS = {
    "completeness": 0.35,
    "gap_free": 0.20,
    "outlier_free": 0.15,
    "volume_quality": 0.15,
    "freshness": 0.15,
}


@dataclass
class DataQualityResult:
    """DQ assessment result for a single ticker."""
    ticker: str
    dq_score: float = 0.0                    # composite 0-1
    completeness: float = 0.0                # 0-1
    gap_free: float = 0.0                    # 0-1 (1 = no gaps)
    outlier_free: float = 0.0                # 0-1 (1 = no outliers)
    volume_quality: float = 0.0              # 0-1 (1 = no zero-vol issues)
    freshness: float = 0.0                   # 0-1 (1 = fresh)
    staleness_days: int = 0
    row_count: int = 0
    zero_volume_count: int = 0
    extreme_change_count: int = 0
    missing_days: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def severity(self) -> str:
        """Alert severity based on DQ score."""
        if self.dq_score < DQ_ERROR_THRESHOLD:
            return "error"
        if self.dq_score < DQ_WARNING_THRESHOLD:
            return "warning"
        return "ok"

    def to_alert(self) -> dict[str, Any] | None:
        """Convert to alert dict if quality is below threshold."""
        if self.dq_score >= DQ_WARNING_THRESHOLD and not self.issues:
            return None

        return {
            "type": "data_quality_drop",
            "severity": self.severity,
            "message": (
                f"{self.ticker}: DQ score {self.dq_score:.2f} "
                f"(completeness={self.completeness:.2f}, "
                f"freshness={self.freshness:.2f}, "
                f"staleness={self.staleness_days}d, "
                f"issues={self.issues})"
            ),
            "ticker": self.ticker,
            "dq_score": round(self.dq_score, 4),
            "completeness": round(self.completeness, 4),
            "gap_free": round(self.gap_free, 4),
            "outlier_free": round(self.outlier_free, 4),
            "volume_quality": round(self.volume_quality, 4),
            "freshness": round(self.freshness, 4),
            "staleness_days": self.staleness_days,
            "row_count": self.row_count,
            "issues": self.issues,
        }


class DataQualityMonitor:
    """Monitors data quality for tickers and generates alerts.

    Args:
        lookback_days: Number of recent days to assess (default 60).
        expected_trading_days_per_week: Expected trading days (5 for IDX).
    """

    def __init__(
        self,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        expected_trading_days_per_week: int = 5,
    ) -> None:
        self.lookback_days = lookback_days
        self.expected_days_per_week = expected_trading_days_per_week

    def assess_ticker(self, ticker: str, ohlcv_df: pd.DataFrame) -> DataQualityResult:
        """Assess data quality for a single ticker.

        Args:
            ticker: Ticker symbol.
            ohlcv_df: DataFrame with 'close', 'volume', and datetime index.
                Should contain recent data (last N days).

        Returns:
            DataQualityResult with component scores and composite.
        """
        result = DataQualityResult(ticker=ticker)

        if ohlcv_df.empty:
            result.issues.append("No data available")
            return result

        result.row_count = len(ohlcv_df)

        # Ensure index is datetime
        if not isinstance(ohlcv_df.index, pd.DatetimeIndex):
            if "timestamp" in ohlcv_df.columns:
                ohlcv_df = ohlcv_df.set_index("timestamp")
            elif "date" in ohlcv_df.columns:
                ohlcv_df = ohlcv_df.set_index("date")
            ohlcv_df.index = pd.to_datetime(ohlcv_df.index)

        # Sort by date
        ohlcv_df = ohlcv_df.sort_index()

        # 1. Freshness — days since last data point
        latest = ohlcv_df.index.max()
        if hasattr(latest, "tzinfo") and latest.tzinfo is None:
            latest = latest.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        if hasattr(latest, "to_pydatetime"):
            latest_dt = latest.to_pydatetime()
        else:
            latest_dt = latest
        if latest_dt.tzinfo is None:
            latest_dt = latest_dt.replace(tzinfo=UTC)
        result.staleness_days = max(0, (now - latest_dt).days)
        result.freshness = max(0.0, 1.0 - result.staleness_days / 30.0)
        if result.staleness_days > STALENESS_WARNING_DAYS:
            result.issues.append(f"Stale data: {result.staleness_days} days old")

        # 2. Completeness — % of expected trading days present
        expected = int(self.lookback_days * self.expected_days_per_week / 7)
        cutoff = ohlcv_df.index.max() - pd.Timedelta(days=self.lookback_days)
        recent = ohlcv_df.loc[ohlcv_df.index >= cutoff]
        actual = len(recent)
        result.completeness = min(1.0, actual / max(1, expected))
        result.missing_days = max(0, expected - actual)
        if result.completeness < 0.8:
            result.issues.append(
                f"Low completeness: {result.completeness:.0%} "
                f"({actual}/{expected} expected days)"
            )

        # 3. Gap-free — check for missing dates in sequence
        if len(recent) > 1:
            dates = recent.index.normalize().unique()
            # Count business day gaps (excluding weekends)
            business_days = pd.bdate_range(dates[0], dates[-1])
            expected_business_days = len(business_days)
            actual_business_days = len(dates)
            result.gap_free = min(1.0, actual_business_days / max(1, expected_business_days))
        else:
            result.gap_free = 0.0

        # 4. Outlier-free — extreme price changes
        if "close" in recent.columns and len(recent) > 1:
            closes = recent["close"].astype(float)
            pct_changes = closes.pct_change().dropna() * 100
            extreme = (pct_changes.abs() > EXTREME_PRICE_CHANGE_PCT).sum()
            result.extreme_change_count = int(extreme)
            result.outlier_free = 1.0 - min(1.0, extreme / max(1, len(pct_changes) * 5))
            if extreme > 0:
                result.issues.append(f"{extreme} extreme price changes (>{EXTREME_PRICE_CHANGE_PCT}%)")
        else:
            result.outlier_free = 1.0

        # 5. Volume quality — zero-volume days
        if "volume" in recent.columns and len(recent) > 0:
            volumes = recent["volume"].astype(float)
            zero_vol = (volumes == 0).sum()
            result.zero_volume_count = int(zero_vol)
            zero_ratio = zero_vol / len(recent)
            result.volume_quality = 1.0 - min(1.0, zero_ratio / ZERO_VOLUME_RATIO_THRESHOLD)
            if zero_ratio > ZERO_VOLUME_RATIO_THRESHOLD:
                result.issues.append(
                    f"High zero-volume ratio: {zero_ratio:.0%} "
                    f"({zero_vol}/{len(recent)} days)"
                )
        else:
            result.volume_quality = 1.0

        # Composite score
        result.dq_score = (
            DQ_WEIGHTS["completeness"] * result.completeness
            + DQ_WEIGHTS["gap_free"] * result.gap_free
            + DQ_WEIGHTS["outlier_free"] * result.outlier_free
            + DQ_WEIGHTS["volume_quality"] * result.volume_quality
            + DQ_WEIGHTS["freshness"] * result.freshness
        )

        return result

    def assess_batch(
        self,
        data: dict[str, pd.DataFrame],
    ) -> list[DataQualityResult]:
        """Assess DQ for multiple tickers.

        Args:
            data: Dict mapping ticker to OHLCV DataFrame.

        Returns:
            List of DataQualityResult, sorted by DQ score ascending.
        """
        results: list[DataQualityResult] = []
        for ticker, df in data.items():
            try:
                results.append(self.assess_ticker(ticker, df))
            except Exception as exc:
                logger.warning("DQ assessment failed for %s: %s", ticker, exc)
                results.append(DataQualityResult(
                    ticker=ticker,
                    issues=[f"Assessment failed: {exc}"],
                ))
        results.sort(key=lambda r: r.dq_score)
        return results

    def generate_alerts(
        self,
        data: dict[str, pd.DataFrame],
    ) -> list[dict[str, Any]]:
        """Assess DQ and return alert dicts for tickers below threshold.

        Args:
            data: Dict mapping ticker to OHLCV DataFrame.

        Returns:
            List of alert dicts suitable for AlertPipeline.
        """
        results = self.assess_batch(data)
        alerts: list[dict[str, Any]] = []
        for r in results:
            alert = r.to_alert()
            if alert:
                alerts.append(alert)
        return alerts
