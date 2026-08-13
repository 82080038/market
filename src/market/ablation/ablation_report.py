"""Ablation Report — generate comparison report across all engines.

Produces:
1. JSON report with per-engine metrics, scorecards, and rankings
2. Console summary table
3. Recommended weight adjustments based on ablation results
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


from market.ablation.isolated_backtest import IsolationResult
from market.ablation.scorecard import ScoreCard, Verdict, score_engine

logger = logging.getLogger(__name__)


@dataclass
class AblationReport:
    """Complete ablation report across all tested engines."""

    timestamp: str
    tickers: list[str]
    period: str
    results: list[IsolationResult] = field(default_factory=list)
    scorecards: list[ScoreCard] = field(default_factory=list)

    @property
    def keep_engines(self) -> list[ScoreCard]:
        return [s for s in self.scorecards if s.verdict == Verdict.KEEP]

    @property
    def marginal_engines(self) -> list[ScoreCard]:
        return [s for s in self.scorecards if s.verdict == Verdict.MARGINAL]

    @property
    def remove_engines(self) -> list[ScoreCard]:
        return [s for s in self.scorecards if s.verdict == Verdict.REMOVE]

    def ranked(self) -> list[ScoreCard]:
        return sorted(self.scorecards, key=lambda s: s.composite_score, reverse=True)

    def to_dict(self) -> dict:
        n = len(self.scorecards)
        bonferroni_alpha = 0.05 / max(n, 1)
        return {
            "metadata": {
                "timestamp": self.timestamp,
                "tickers": self.tickers,
                "period": self.period,
                "total_engines": n,
                "keep": len(self.keep_engines),
                "marginal": len(self.marginal_engines),
                "remove": len(self.remove_engines),
                "bonferroni_alpha": round(bonferroni_alpha, 6),
                "multiple_testing_correction": "Bonferroni",
            },
            "scorecards": [s.to_dict() for s in self.ranked()],
            "results": [
                {
                    "engine_name": r.engine_name,
                    "baseline_metrics": r.baseline_metrics,
                    "isolated_metrics": r.isolated_metrics,
                    "delta_metrics": r.delta_metrics,
                    "p_value": r.p_value,
                    "t_statistic": r.t_statistic,
                    "is_significant": r.is_significant,
                    "n_observations": r.n_observations,
                    "error": r.error,
                }
                for r in self.results
            ],
            "recommendations": self._recommendations(),
        }

    def _recommendations(self) -> list[dict]:
        """Generate weight adjustment recommendations."""
        recs = []
        for sc in self.ranked():
            if sc.verdict == Verdict.KEEP:
                action = "maintain_or_increase_weight"
                suggestion = "Increase weight by up to 50% (current contribution is significant)"
            elif sc.verdict == Verdict.MARGINAL:
                action = "monitor"
                suggestion = "Keep but monitor — consider reducing weight if no improvement in next audit"
            else:
                action = "reduce_or_remove"
                suggestion = "Reduce weight to 0 or remove from production pipeline"
            recs.append({
                "engine": sc.engine_name,
                "verdict": sc.verdict.value,
                "action": action,
                "suggestion": suggestion,
                "composite_score": round(sc.composite_score, 2),
            })
        return recs

    def save_json(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info("Report saved to %s", path)
        return path

    def save_to_db(self) -> int:
        """Persist this ablation run + scorecards to the database.

        Inserts one row into ``ablation_runs`` and N rows into
        ``ablation_scorecards`` (one per engine).

        Returns:
            The run_id (primary key of ablation_runs).
        """
        import json as _json

        from market.config import settings
        from market.db.raw import get_raw_connection

        n = len(self.scorecards)
        bonferroni_alpha = 0.05 / max(n, 1)
        is_pg = settings.db_backend == "postgresql"

        with get_raw_connection() as conn:
            if is_pg:
                cur = conn.execute(
                    "INSERT INTO ablation_runs "
                    "(run_timestamp, tickers, period, total_engines, "
                    " keep_count, marginal_count, remove_count, "
                    " bonferroni_alpha, multiple_testing_correction) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (
                        self.timestamp,
                        _json.dumps(self.tickers),
                        self.period,
                        n,
                        len(self.keep_engines),
                        len(self.marginal_engines),
                        len(self.remove_engines),
                        round(bonferroni_alpha, 6),
                        "Bonferroni",
                    ),
                )
                run_id = cur.fetchone()[0]
            else:
                cur = conn.execute(
                    "INSERT INTO ablation_runs "
                    "(run_timestamp, tickers, period, total_engines, "
                    " keep_count, marginal_count, remove_count, "
                    " bonferroni_alpha, multiple_testing_correction) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        self.timestamp,
                        _json.dumps(self.tickers),
                        self.period,
                        n,
                        len(self.keep_engines),
                        len(self.marginal_engines),
                        len(self.remove_engines),
                        round(bonferroni_alpha, 6),
                        "Bonferroni",
                    ),
                )
                run_id = cur.lastrowid
            conn.commit()

            ph = "%s" if is_pg else "?"
            for sc in self.ranked():
                conn.execute(
                    f"INSERT INTO ablation_scorecards "
                    f"(run_id, engine_name, verdict, composite_score, "
                    f" delta_sharpe, delta_alpha, delta_win_rate, "
                    f" p_value, is_significant, n_observations, "
                    f" isolated_sharpe, baseline_sharpe, reasons) "
                    f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, "
                    f" {ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
                    (
                        run_id,
                        sc.engine_name,
                        sc.verdict.value,
                        round(sc.composite_score, 2),
                        round(sc.delta_sharpe, 4),
                        round(sc.delta_alpha, 4),
                        round(sc.delta_win_rate, 2),
                        round(sc.p_value, 6),
                        sc.is_significant,
                        sc.n_observations,
                        round(sc.isolated_sharpe, 4),
                        round(sc.baseline_sharpe, 4),
                        _json.dumps(sc.reasons),
                    ),
                )
            conn.commit()

        logger.info("Ablation run saved to DB (run_id=%s)", run_id)
        return run_id

    def print_summary(self) -> None:
        sc_list = self.ranked()
        n = len(sc_list)
        bonf_alpha = 0.05 / max(n, 1)
        print("\n" + "=" * 90)
        print("ENGINE ABLATION SCORECARD")
        print("=" * 90)
        print(f"Period: {self.period} | Tickers: {', '.join(self.tickers)}")
        print(f"Engines tested: {n} | KEEP: {len(self.keep_engines)} | "
              f"MARGINAL: {len(self.marginal_engines)} | REMOVE: {len(self.remove_engines)}")
        print(f"Multiple testing correction: Bonferroni (α={bonf_alpha:.6f}, n={n})")
        print("-" * 90)
        print(f"{'Engine':20s} {'Verdict':10s} {'Score':>7s} {'Δ Sharpe':>10s} "
              f"{'Δ Alpha':>10s} {'p-value':>10s} {'Sig':>5s}")
        print("-" * 90)
        for sc in sc_list:
            sig = "✓" if sc.is_significant else "✗"
            print(
                f"{sc.engine_name:20s} {sc.verdict.value:10s} "
                f"{sc.composite_score:>7.1f} {sc.delta_sharpe:>+10.4f} "
                f"{sc.delta_alpha:>+10.4f} {sc.p_value:>10.6f} {sig:>5s}"
            )
        print("-" * 90)
        print("\nRecommendations:")
        for rec in self._recommendations():
            print(f"  {rec['engine']:20s} → {rec['action']:30s} (score={rec['composite_score']})")
        print("\n" + "=" * 90)


def generate_report(
    results: list[IsolationResult],
    tickers: list[str],
    period: str,
    n_engines_tested: int | None = None,
) -> AblationReport:
    """Generate ablation report from isolation results.

    Args:
        results: List of IsolationResult, one per engine.
        tickers: List of tickers tested.
        period: Backtest period string (e.g., "2024-01-01 to 2026-08-12").
        n_engines_tested: Number of engines tested (for Bonferroni correction).
            If None, uses len(results).

    Returns:
        AblationReport with scorecards and recommendations.
    """
    n = n_engines_tested if n_engines_tested is not None else len(results)
    scorecards = [score_engine(r, n_engines_tested=n) for r in results]
    return AblationReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        tickers=tickers,
        period=period,
        results=results,
        scorecards=scorecards,
    )


def load_latest_verdicts() -> list[dict]:
    """Load the most recent ablation run's scorecards from DB.

    Returns:
        List of dicts with keys: engine_name, verdict, composite_score,
        delta_sharpe, delta_alpha, p_value, is_significant, reasons.
        Empty list if no runs exist.
    """
    from market.db.raw import execute_query

    rows = execute_query(
        "SELECT id FROM ablation_runs ORDER BY run_timestamp DESC LIMIT 1"
    )
    if not rows:
        return []

    run_id = rows[0][0]
    rows = execute_query(
        "SELECT engine_name, verdict, composite_score, "
        " delta_sharpe, delta_alpha, delta_win_rate, "
        " p_value, is_significant, n_observations, "
        " isolated_sharpe, baseline_sharpe, reasons "
        "FROM ablation_scorecards WHERE run_id = ? "
        "ORDER BY composite_score DESC",
        (run_id,),
    )
    import json as _json

    return [
        {
            "engine_name": r[0],
            "verdict": r[1],
            "composite_score": r[2],
            "delta_sharpe": r[3],
            "delta_alpha": r[4],
            "delta_win_rate": r[5],
            "p_value": r[6],
            "is_significant": bool(r[7]),
            "n_observations": r[8],
            "isolated_sharpe": r[9],
            "baseline_sharpe": r[10],
            "reasons": _json.loads(r[11]) if r[11] else [],
        }
        for r in rows
    ]


def list_ablation_runs(limit: int = 20) -> list[dict]:
    """List recent ablation runs from DB.

    Args:
        limit: Maximum number of runs to return.

    Returns:
        List of dicts with run metadata.
    """
    from market.db.raw import execute_query

    rows = execute_query(
        "SELECT id, run_timestamp, period, total_engines, "
        " keep_count, marginal_count, remove_count, bonferroni_alpha "
        "FROM ablation_runs ORDER BY run_timestamp DESC LIMIT ?",
        (limit,),
    )
    return [
        {
            "run_id": r[0],
            "timestamp": str(r[1]),
            "period": r[2],
            "total_engines": r[3],
            "keep": r[4],
            "marginal": r[5],
            "remove": r[6],
            "bonferroni_alpha": r[7],
        }
        for r in rows
    ]
