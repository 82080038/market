"""Data quality validation engine (pustaka/18 §2.2).

Validates OHLCV data for completeness, plausibility, volume spikes,
and gap detection. Produces a quality score (0-100) and action.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from market.data.contracts import DataQualityResult, NormalizedOHLCV

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class DataQualityEngine:
    """Data quality validation engine.

    Checks:
    1. Completeness: missing values, daily gaps.
    2. Plausibility: price ≤ 0, low > high, close outside range.
    3. Volume spike: volume > 10x median.
    4. Gap detection: gap > 5 trading days.
    """

    def validate(
        self,
        records: Sequence[NormalizedOHLCV],
        expected_daily: bool = True,
    ) -> DataQualityResult:
        """Validate a batch of OHLCV records for a single ticker.

        Args:
            records: List of NormalizedOHLCV for one ticker, sorted by timestamp.
            expected_daily: Whether data is expected to be daily frequency.

        Returns:
            DataQualityResult with score, action, and anomaly list.
        """
        if not records:
            return DataQualityResult(
                ticker="",
                score=0.0,
                action="pause",
                anomalies=["no_data"],
                checked_at=datetime.now(UTC),
            )

        ticker = records[0].ticker
        anomalies: list[str] = []
        checks_passed = 0
        total_checks = 4

        # 1. Completeness
        missing_count = sum(1 for r in records if r.volume is None or r.close is None)
        if missing_count == 0:
            checks_passed += 1
        else:
            anomalies.append(f"missing_values:{missing_count}")

        if expected_daily:
            gap_anomalies = self._check_gaps(records)
            if not gap_anomalies:
                checks_passed += 1
            else:
                anomalies.extend(gap_anomalies)
        else:
            checks_passed += 1

        # 2. Plausibility
        implausible = self._check_plausibility(records)
        if not implausible:
            checks_passed += 1
        else:
            anomalies.extend(implausible)

        # 3. Volume spike
        vol_spikes = self._check_volume_spikes(records)
        if not vol_spikes:
            checks_passed += 1
        else:
            anomalies.extend(vol_spikes)

        score = (checks_passed / total_checks) * 100.0

        if score >= 90:
            action = "accept"
        elif score >= 70:
            action = "flag"
        else:
            action = "pause"

        return DataQualityResult(
            ticker=ticker,
            score=round(score, 2),
            action=action,
            anomalies=anomalies,
            checked_at=datetime.now(UTC),
        )

    def _check_gaps(self, records: Sequence[NormalizedOHLCV]) -> list[str]:
        """Check for gaps > 5 trading days (excluding weekends)."""
        anomalies: list[str] = []
        for i in range(1, len(records)):
            prev_ts = records[i - 1].timestamp
            curr_ts = records[i].timestamp
            delta = curr_ts - prev_ts
            if delta > timedelta(days=7):
                anomalies.append(f"gap:{prev_ts.date()}_to_{curr_ts.date()}")
        return anomalies

    def _check_plausibility(self, records: Sequence[NormalizedOHLCV]) -> list[str]:
        """Check for implausible price values."""
        anomalies: list[str] = []
        for r in records:
            if r.open <= 0 or r.high <= 0 or r.low <= 0 or r.close <= 0:
                anomalies.append(f"non_positive_price:{r.timestamp.date()}")
                continue
            if r.low > r.high:
                anomalies.append(f"low_gt_high:{r.timestamp.date()}")
            if r.close < r.low or r.close > r.high:
                anomalies.append(f"close_outside_range:{r.timestamp.date()}")
        return anomalies

    def _check_volume_spikes(self, records: Sequence[NormalizedOHLCV]) -> list[str]:
        """Check for volume > 10x median."""
        anomalies: list[str] = []
        volumes = [r.volume for r in records if r.volume and r.volume > 0]
        if not volumes:
            return anomalies

        volumes_sorted = sorted(volumes)
        n = len(volumes_sorted)
        median = volumes_sorted[n // 2] if n % 2 == 1 else (
            (volumes_sorted[n // 2 - 1] + volumes_sorted[n // 2]) / 2
        )

        if median <= 0:
            return anomalies

        for r in records:
            if r.volume and r.volume > 10 * median:
                anomalies.append(f"volume_spike:{r.timestamp.date()}")

        return anomalies
