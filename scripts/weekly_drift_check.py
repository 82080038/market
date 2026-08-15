#!/usr/bin/env python3
"""Weekly drift detection cron — checks feature drift via PSI.

Dijalankan via scheduler task (weekly_drift_check) — cron Sabtu 10:00 WIB
trigger run_daily_scheduler.sh → run_all_due() → task ini due jika >6 hari.
Catch-up otomatis: kalau komputer mati Sabtu, task jalan di trigger berikutnya.
Checks feature distribution changes in technical_indicators_wide that could
degrade ML model performance.

Output: logs/drift_report_YYYY-MM-DD.json
"""
import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent
from market.config import settings as _settings
DB_PATH = _settings.db_path
LOG_DIR = PROJECT_DIR / "logs"

DRIFT_FEATURES = ["rsi", "macd", "atr14", "bb_lower", "volume_sma20"]
PSI_THRESHOLD = 0.25
BASELINE_DAYS = 180
CURRENT_DAYS = 30


def run_drift_check() -> dict:
    """Check feature drift between baseline and current periods."""
    conn = sqlite3.connect(str(DB_PATH))

    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    baseline_start = (pd.Timestamp.now() - pd.Timedelta(days=BASELINE_DAYS)).strftime("%Y-%m-%d")
    current_start = (pd.Timestamp.now() - pd.Timedelta(days=CURRENT_DAYS)).strftime("%Y-%m-%d")

    logger.info("Drift check: baseline %s → %s, current %s → %s",
                baseline_start, today, current_start, today)

    from market.mlops.drift import DriftDetector, population_stability_index

    detector = DriftDetector(psi_threshold=PSI_THRESHOLD)
    results = {}

    for feature in DRIFT_FEATURES:
        try:
            baseline_vals = pd.read_sql_query(
                f"SELECT {feature} FROM technical_indicators_wide "
                f"WHERE {feature} IS NOT NULL AND date >= ? AND date < ? "
                f"ORDER BY RANDOM() LIMIT 10000",
                conn, params=(baseline_start, current_start),
            )[feature].values

            current_vals = pd.read_sql_query(
                f"SELECT {feature} FROM technical_indicators_wide "
                f"WHERE {feature} IS NOT NULL AND date >= ? "
                f"ORDER BY RANDOM() LIMIT 10000",
                conn, params=(current_start,),
            )[feature].values

            if len(baseline_vals) < 100 or len(current_vals) < 100:
                results[feature] = {"psi": None, "drifted": False, "reason": "insufficient data"}
                continue

            psi = population_stability_index(baseline_vals, current_vals)
            results[feature] = {
                "psi": round(psi, 4),
                "drifted": psi > PSI_THRESHOLD,
                "baseline_n": len(baseline_vals),
                "current_n": len(current_vals),
            }

            if psi > PSI_THRESHOLD:
                logger.warning("  ⚠ DRIFT: %s PSI=%.4f > threshold %.2f", feature, psi, PSI_THRESHOLD)
            else:
                logger.info("  ✓ %s PSI=%.4f (OK)", feature, psi)

        except Exception as e:
            results[feature] = {"psi": None, "drifted": False, "error": str(e)}
            logger.error("  Error checking %s: %s", feature, e)

    conn.close()

    n_drifted = sum(1 for v in results.values() if v.get("drifted", False))
    report = {
        "checked_at": datetime.now().isoformat(),
        "baseline_period": f"{baseline_start} to {current_start}",
        "current_period": f"{current_start} to {today}",
        "psi_threshold": PSI_THRESHOLD,
        "features": results,
        "n_drifted": n_drifted,
        "is_drifted": n_drifted > 0,
    }

    LOG_DIR.mkdir(exist_ok=True)
    report_path = LOG_DIR / f"drift_report_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("Report saved: %s (%d drifted features)", report_path, n_drifted)
    return report


if __name__ == "__main__":
    report = run_drift_check()
    sys.exit(0 if not report["is_drifted"] else 1)
