"""Recompute Analyzer — analyzes historical runs and stores predictions to DB.

This module runs periodically (e.g. after each recompute cycle) to:
1. Read historical run stats from ``recompute_run_stats``
2. Analyze patterns: duration vs ticker_count, incremental vs full, time-of-day effects
3. Compute predictions using multiple methods (rolling avg, exponential smoothing, linear regression)
4. Store predictions in ``recompute_predictions`` table
5. Evaluate accuracy of previous predictions (feedback loop)

The RecomputeEstimator then reads these pre-computed predictions from DB
instead of calculating on-the-fly.

Analysis methods:
- ``rolling_avg``: weighted average of last N runs (more recent = higher weight)
- ``exponential``: exponential smoothing (alpha=0.3)
- ``regression``: linear regression on duration vs ticker_count
- ``factor_adjusted``: rolling avg adjusted by time-of-day and incremental factors

Usage::

    from market.analysis.recompute_analyzer import RecomputeAnalyzer

    # Run full analysis (after recompute cycle)
    summary = RecomputeAnalyzer.analyze_all()

    # Analyze single function
    RecomputeAnalyzer.analyze_function("recompute_scores")

    # Get prediction from DB (used by RecomputeEstimator)
    pred = RecomputeAnalyzer.get_prediction("recompute_scores", incremental=True)
    # → {"predicted_duration_s": 45.2, "predicted_rows": 4800, "confidence": 0.85}
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from market.db.engine import get_sessionmaker
from market.db.models import RecomputePrediction, RecomputeRunStats

logger = logging.getLogger(__name__)

# Minimum samples needed for each method
_MIN_SAMPLES_ROLLING = 3
_MIN_SAMPLES_EXPONENTIAL = 3
_MIN_SAMPLES_REGRESSION = 5
_MAX_SAMPLE_LOOKBACK = 50  # Don't use runs older than this

# Exponential smoothing factor
_ALPHA = 0.3


class RecomputeAnalyzer:
    """Analyzes historical recompute runs and stores predictions to DB."""

    # ── Main entry points ──────────────────────────────────────────

    @staticmethod
    def analyze_all(session: Session | None = None) -> dict[str, Any]:
        """Run analysis for all functions that have historical run stats.

        Should be called periodically (e.g. after each recompute cycle,
        or as a scheduler task every few hours).

        Returns summary dict with functions analyzed and predictions generated.
        """
        own_session = False
        if session is None:
            session = get_sessionmaker()()
            own_session = True

        try:
            # Get all unique function names from run stats
            functions = session.execute(
                select(RecomputeRunStats.function_name)
                .where(RecomputeRunStats.status == "completed")
                .distinct()
            ).scalars().all()

            summary: dict[str, Any] = {
                "functions_analyzed": 0,
                "predictions_generated": 0,
                "predictions_updated": 0,
                "errors": [],
            }

            for fn_name in functions:
                try:
                    result = RecomputeAnalyzer.analyze_function(fn_name, session=session)
                    if result:
                        summary["functions_analyzed"] += 1
                        summary["predictions_generated"] += result.get("generated", 0)
                        summary["predictions_updated"] += result.get("updated", 0)
                except Exception as e:
                    logger.error("RecomputeAnalyzer: analyze %s failed: %s", fn_name, e)
                    summary["errors"].append(f"{fn_name}: {e}")

            # Evaluate accuracy of previous predictions
            eval_result = RecomputeAnalyzer.evaluate_prediction_accuracy(session=session)
            summary["accuracy_evaluated"] = eval_result

            logger.info(
                "RecomputeAnalyzer: analyzed %d functions, %d predictions generated, %d updated",
                summary["functions_analyzed"],
                summary["predictions_generated"],
                summary["predictions_updated"],
            )
            return summary
        except Exception as e:
            logger.error("RecomputeAnalyzer: analyze_all failed: %s", e)
            return {"error": str(e)}
        finally:
            if own_session:
                session.close()

    @staticmethod
    def analyze_function(
        function_name: str,
        session: Session | None = None,
    ) -> dict[str, Any]:
        """Analyze a single function and store predictions to DB.

        Generates predictions for both incremental and full modes.
        Uses the best available method based on sample size.
        """
        own_session = False
        if session is None:
            session = get_sessionmaker()()
            own_session = True

        try:
            # Load recent completed runs
            runs = session.execute(
                select(RecomputeRunStats)
                .where(
                    RecomputeRunStats.function_name == function_name,
                    RecomputeRunStats.status == "completed",
                )
                .order_by(RecomputeRunStats.started_at.desc())
                .limit(_MAX_SAMPLE_LOOKBACK)
            ).scalars().all()

            if not runs:
                return {"generated": 0, "updated": 0}

            # Split by incremental vs full
            incremental_runs = [r for r in runs if r.incremental]
            full_runs = [r for r in runs if not r.incremental]

            generated = 0
            updated = 0

            # Generate predictions for each mode
            for is_incremental, mode_runs in [(True, incremental_runs), (False, full_runs)]:
                if len(mode_runs) < 1:
                    continue

                prediction = RecomputeAnalyzer._compute_prediction(
                    function_name, mode_runs, is_incremental
                )
                if prediction:
                    # Upsert: replace existing prediction for this function+mode
                    existing = session.execute(
                        select(RecomputePrediction)
                        .where(
                            RecomputePrediction.function_name == function_name,
                            RecomputePrediction.incremental == is_incremental,
                            RecomputePrediction.was_used.is_(False),
                        )
                        .order_by(RecomputePrediction.analyzed_at.desc())
                        .limit(1)
                    ).scalar_one_or_none()

                    if existing:
                        # Update existing
                        existing.predicted_duration_s = prediction["predicted_duration_s"]
                        existing.predicted_rows = prediction["predicted_rows"]
                        existing.predicted_tickers = prediction.get("predicted_tickers")
                        existing.confidence_score = prediction["confidence_score"]
                        existing.analysis_method = prediction["analysis_method"]
                        existing.sample_size = prediction["sample_size"]
                        existing.ticker_count = prediction.get("ticker_count")
                        existing.time_of_day = prediction.get("time_of_day")
                        existing.day_of_week = prediction.get("day_of_week")
                        existing.analyzed_at = datetime.now(UTC)
                        updated += 1
                    else:
                        # Insert new
                        session.add(RecomputePrediction(
                            function_name=function_name,
                            predicted_duration_s=prediction["predicted_duration_s"],
                            predicted_rows=prediction["predicted_rows"],
                            predicted_tickers=prediction.get("predicted_tickers"),
                            confidence_score=prediction["confidence_score"],
                            analysis_method=prediction["analysis_method"],
                            sample_size=prediction["sample_size"],
                            ticker_count=prediction.get("ticker_count"),
                            incremental=is_incremental,
                            time_of_day=prediction.get("time_of_day"),
                            day_of_week=prediction.get("day_of_week"),
                            analyzed_at=datetime.now(UTC),
                        ))
                        generated += 1

            session.commit()
            return {"generated": generated, "updated": updated}
        except Exception as e:
            logger.error("RecomputeAnalyzer: analyze_function %s failed: %s", function_name, e)
            session.rollback()
            return {"generated": 0, "updated": 0, "error": str(e)}
        finally:
            if own_session:
                session.close()

    # ── Prediction computation ─────────────────────────────────────

    @staticmethod
    def _compute_prediction(
        function_name: str,
        runs: list[RecomputeRunStats],
        is_incremental: bool,
    ) -> dict[str, Any] | None:
        """Compute prediction from a list of historical runs.

        Selects the best method based on sample size:
        - < 3 runs: use last value (low confidence)
        - 3-4 runs: rolling average
        - 5+ runs: try regression, fall back to exponential
        """
        n = len(runs)
        if n == 0:
            return None

        # Extract durations and rows (filter None)
        durations = [float(r.duration_seconds) for r in runs if r.duration_seconds is not None]
        rows_list = [int(r.rows_affected) for r in runs if r.rows_affected is not None]
        tickers_list = [int(r.tickers_processed) for r in runs if r.tickers_processed is not None]

        if not durations:
            return None

        # Reverse to chronological order (runs are desc, we want asc for weighting)
        durations.reverse()
        rows_list.reverse()

        # Select best method
        if n >= _MIN_SAMPLES_REGRESSION and tickers_list:
            # Try regression: duration = a * ticker_count + b
            method = "regression"
            pred_dur, pred_rows, confidence = RecomputeAnalyzer._regression_predict(
                durations, rows_list, tickers_list
            )
        elif n >= _MIN_SAMPLES_EXPONENTIAL:
            # Exponential smoothing
            method = "exponential"
            pred_dur = RecomputeAnalyzer._exponential_smooth(durations, _ALPHA)
            pred_rows = int(RecomputeAnalyzer._exponential_smooth(rows_list, _ALPHA)) if rows_list else 0
            confidence = min(1.0, n / 10.0)
        elif n >= _MIN_SAMPLES_ROLLING:
            # Rolling average (weighted)
            method = "rolling_avg"
            pred_dur = RecomputeAnalyzer._weighted_average(durations)
            pred_rows = int(RecomputeAnalyzer._weighted_average(rows_list)) if rows_list else 0
            confidence = min(0.7, n / 10.0)
        else:
            # Use last value (low confidence)
            method = "last_value"
            pred_dur = durations[-1]
            pred_rows = rows_list[-1] if rows_list else 0
            confidence = 0.2

        # Factor adjustments
        now = datetime.now(UTC)
        time_of_day = now.hour
        day_of_week = now.weekday()

        # Time-of-day adjustment: DB is slower during business hours (9-17 WIB = 2-10 UTC)
        if 2 <= time_of_day <= 10:
            pred_dur *= 1.15  # 15% slower during trading hours

        # Weekend adjustment: DB is faster on weekends (no trading data)
        if day_of_week >= 5:
            pred_dur *= 0.9  # 10% faster on weekends

        # Ticker count estimate
        pred_tickers = None
        if tickers_list:
            pred_tickers = int(np.median(tickers_list))

        return {
            "predicted_duration_s": round(pred_dur, 1),
            "predicted_rows": max(pred_rows, 0),
            "predicted_tickers": pred_tickers,
            "confidence_score": round(confidence, 3),
            "analysis_method": method,
            "sample_size": n,
            "ticker_count": pred_tickers,
            "time_of_day": time_of_day,
            "day_of_week": day_of_week,
        }

    @staticmethod
    def _weighted_average(values: list[float]) -> float:
        """Weighted average with more weight on recent values."""
        n = len(values)
        if n == 0:
            return 0.0
        weights = [i + 1 for i in range(n)]  # 1, 2, ..., n
        total_weight = sum(weights)
        return sum(v * w for v, w in zip(values, weights)) / total_weight

    @staticmethod
    def _exponential_smooth(values: list[float], alpha: float) -> float:
        """Exponential smoothing."""
        if not values:
            return 0.0
        result = values[0]
        for v in values[1:]:
            result = alpha * v + (1 - alpha) * result
        return result

    @staticmethod
    def _regression_predict(
        durations: list[float],
        rows_list: list[int],
        tickers_list: list[int],
    ) -> tuple[float, int, float]:
        """Linear regression: duration = a * tickers + b.

        Returns (predicted_duration, predicted_rows, confidence).
        """
        # Use tickers as X, duration as Y
        n = min(len(durations), len(tickers_list))
        if n < 2:
            return durations[-1], rows_list[-1] if rows_list else 0, 0.3

        x = np.array(tickers_list[:n], dtype=float)
        y = np.array(durations[:n], dtype=float)

        # Simple linear regression
        x_mean = x.mean()
        y_mean = y.mean()
        ss_xy = ((x - x_mean) * (y - y_mean)).sum()
        ss_xx = ((x - x_mean) ** 2).sum()

        if ss_xx == 0:
            # No variation in ticker count → use average
            return y_mean, int(np.mean(rows_list[:n])), 0.5

        slope = ss_xy / ss_xx
        intercept = y_mean - slope * x_mean

        # Predict for median ticker count (representative)
        pred_tickers = int(np.median(x))
        pred_dur = slope * pred_tickers + intercept
        pred_rows = int(np.mean(rows_list[:n]))

        # R² for confidence
        y_pred = slope * x + intercept
        ss_res = ((y - y_pred) ** 2).sum()
        ss_tot = ((y - y_mean) ** 2).sum()
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.5

        confidence = max(0.3, min(1.0, r_squared))

        return max(pred_dur, 0.1), pred_rows, confidence

    # ── Read predictions from DB ───────────────────────────────────

    @staticmethod
    def get_prediction(
        function_name: str,
        incremental: bool = False,
        session: Session | None = None,
    ) -> dict[str, Any] | None:
        """Get the latest pre-computed prediction from DB.

        This is the method RecomputeEstimator should call instead of
        computing on-the-fly.
        """
        own_session = False
        if session is None:
            try:
                session = get_sessionmaker()()
                own_session = True
            except Exception:
                return None

        try:
            pred = session.execute(
                select(RecomputePrediction)
                .where(
                    RecomputePrediction.function_name == function_name,
                    RecomputePrediction.incremental == incremental,
                )
                .order_by(RecomputePrediction.analyzed_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            if pred is None:
                return None

            return {
                "function_name": pred.function_name,
                "predicted_duration_s": float(pred.predicted_duration_s),
                "predicted_rows": int(pred.predicted_rows),
                "predicted_tickers": pred.predicted_tickers,
                "confidence_score": float(pred.confidence_score),
                "analysis_method": pred.analysis_method,
                "sample_size": pred.sample_size,
                "incremental": pred.incremental,
                "analyzed_at": pred.analyzed_at.isoformat() if pred.analyzed_at else None,
            }
        except Exception as e:
            logger.debug("RecomputeAnalyzer: get_prediction failed: %s", e)
            return None
        finally:
            if own_session:
                session.close()

    @staticmethod
    def get_all_predictions(
        session: Session | None = None,
    ) -> list[dict[str, Any]]:
        """Get latest prediction for each function."""
        own_session = False
        if session is None:
            session = get_sessionmaker()()
            own_session = True

        try:
            # Get the latest prediction per function (both incremental and full)
            preds = session.execute(
                select(RecomputePrediction)
                .order_by(RecomputePrediction.function_name, RecomputePrediction.incremental, desc(RecomputePrediction.analyzed_at))
            ).scalars().all()

            # Deduplicate: keep only latest per (function_name, incremental)
            seen = set()
            result = []
            for p in preds:
                key = (p.function_name, p.incremental)
                if key in seen:
                    continue
                seen.add(key)
                result.append({
                    "function_name": p.function_name,
                    "incremental": p.incremental,
                    "predicted_duration_s": float(p.predicted_duration_s),
                    "predicted_rows": int(p.predicted_rows),
                    "confidence_score": float(p.confidence_score),
                    "analysis_method": p.analysis_method,
                    "sample_size": p.sample_size,
                    "analyzed_at": p.analyzed_at.isoformat() if p.analyzed_at else None,
                })
            return result
        except Exception as e:
            logger.debug("RecomputeAnalyzer: get_all_predictions failed: %s", e)
            return []
        finally:
            if own_session:
                session.close()

    # ── Feedback loop: evaluate prediction accuracy ────────────────

    @staticmethod
    def evaluate_prediction_accuracy(
        session: Session | None = None,
    ) -> dict[str, Any]:
        """Evaluate accuracy of predictions that have been used.

        Finds predictions where was_used=True and actual values are filled,
        computes error percentages, and returns summary statistics.

        Also marks old predictions as used when actual run stats are available.
        """
        own_session = False
        if session is None:
            session = get_sessionmaker()()
            own_session = True

        try:
            # Find predictions that have been used but not yet evaluated
            preds = session.execute(
                select(RecomputePrediction)
                .where(
                    RecomputePrediction.was_used.is_(True),
                    RecomputePrediction.actual_duration_s.is_(None),
                )
            ).scalars().all()

            evaluated = 0
            duration_errors: list[float] = []
            rows_errors: list[float] = []

            for pred in preds:
                # Find the actual run that used this prediction
                actual_run = session.execute(
                    select(RecomputeRunStats)
                    .where(
                        RecomputeRunStats.function_name == pred.function_name,
                        RecomputeRunStats.started_at >= pred.analyzed_at,
                        RecomputeRunStats.status == "completed",
                    )
                    .order_by(RecomputeRunStats.started_at.asc())
                    .limit(1)
                ).scalar_one_or_none()

                if actual_run and actual_run.duration_seconds is not None:
                    pred_dur = float(pred.predicted_duration_s)
                    actual_dur = float(actual_run.duration_seconds)

                    pred.actual_duration_s = actual_dur
                    pred.actual_rows = actual_run.rows_affected

                    if pred_dur > 0:
                        err_pct = (actual_dur - pred_dur) / pred_dur * 100
                        pred.duration_error_pct = err_pct
                        duration_errors.append(abs(err_pct))

                    if pred.predicted_rows and pred.predicted_rows > 0 and actual_run.rows_affected:
                        r_err = (actual_run.rows_affected - pred.predicted_rows) / pred.predicted_rows * 100
                        pred.rows_error_pct = r_err
                        rows_errors.append(abs(r_err))

                    evaluated += 1

            session.commit()

            # Compute summary
            summary = {
                "predictions_evaluated": evaluated,
                "avg_duration_error_pct": round(np.mean(duration_errors), 1) if duration_errors else None,
                "avg_rows_error_pct": round(np.mean(rows_errors), 1) if rows_errors else None,
                "max_duration_error_pct": round(max(duration_errors), 1) if duration_errors else None,
            }

            if evaluated > 0:
                logger.info(
                    "RecomputeAnalyzer: evaluated %d predictions, avg duration error=%.1f%%, avg rows error=%.1f%%",
                    evaluated,
                    summary["avg_duration_error_pct"] or 0,
                    summary["avg_rows_error_pct"] or 0,
                )

            return summary
        except Exception as e:
            logger.error("RecomputeAnalyzer: evaluate_accuracy failed: %s", e)
            session.rollback()
            return {"error": str(e)}
        finally:
            if own_session:
                session.close()

    @staticmethod
    def mark_prediction_used(
        function_name: str,
        incremental: bool,
        session: Session | None = None,
    ) -> None:
        """Mark the latest prediction for a function as used.

        Called when a recompute function starts using a prediction.
        """
        own_session = False
        if session is None:
            session = get_sessionmaker()()
            own_session = True

        try:
            pred = session.execute(
                select(RecomputePrediction)
                .where(
                    RecomputePrediction.function_name == function_name,
                    RecomputePrediction.incremental == incremental,
                    RecomputePrediction.was_used.is_(False),
                )
                .order_by(RecomputePrediction.analyzed_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            if pred:
                pred.was_used = True
                session.commit()
        except Exception:
            session.rollback()
        finally:
            if own_session:
                session.close()

    # ── Accuracy history ───────────────────────────────────────────

    @staticmethod
    def get_accuracy_history(
        function_name: str | None = None,
        limit: int = 20,
        session: Session | None = None,
    ) -> list[dict[str, Any]]:
        """Get prediction accuracy history for feedback analysis."""
        own_session = False
        if session is None:
            session = get_sessionmaker()()
            own_session = True

        try:
            query = select(RecomputePrediction).where(
                RecomputePrediction.was_used.is_(True),
                RecomputePrediction.actual_duration_s.is_not(None),
            )
            if function_name:
                query = query.where(RecomputePrediction.function_name == function_name)
            query = query.order_by(RecomputePrediction.analyzed_at.desc()).limit(limit)

            rows = session.execute(query).scalars().all()
            return [
                {
                    "function_name": r.function_name,
                    "incremental": r.incremental,
                    "predicted_duration_s": float(r.predicted_duration_s),
                    "actual_duration_s": float(r.actual_duration_s) if r.actual_duration_s else None,
                    "duration_error_pct": float(r.duration_error_pct) if r.duration_error_pct else None,
                    "predicted_rows": r.predicted_rows,
                    "actual_rows": r.actual_rows,
                    "rows_error_pct": float(r.rows_error_pct) if r.rows_error_pct else None,
                    "analysis_method": r.analysis_method,
                    "sample_size": r.sample_size,
                    "analyzed_at": r.analyzed_at.isoformat() if r.analyzed_at else None,
                }
                for r in rows
            ]
        except Exception as e:
            logger.debug("RecomputeAnalyzer: get_accuracy_history failed: %s", e)
            return []
        finally:
            if own_session:
                session.close()
