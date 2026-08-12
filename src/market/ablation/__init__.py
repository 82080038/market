"""Engine Ablation Framework — isolated per-engine backtest & scoring.

Tests each signal engine in isolation (all others disabled) to measure
individual contribution to prediction accuracy and portfolio performance.

Output: per-engine scorecard with KEEP / MARGINAL / REMOVE verdict.

See: pustaka/96-ai-ml-audit-framework.md (Pilar 2: Ablation Study)
"""

from market.ablation.engine_registry import EngineRegistry, EngineEntry, EngineCategory, SignalType
from market.ablation.isolated_backtest import IsolatedBacktester, IsolationResult
from market.ablation.scorecard import ScoreCard, Verdict, score_engine
from market.ablation.ablation_report import AblationReport, generate_report
from market.ablation.data_checker import DataChecker, EngineDataCheck, CheckStatus

__all__ = [
    "EngineRegistry",
    "EngineEntry",
    "EngineCategory",
    "SignalType",
    "IsolatedBacktester",
    "IsolationResult",
    "ScoreCard",
    "Verdict",
    "score_engine",
    "AblationReport",
    "generate_report",
    "DataChecker",
    "EngineDataCheck",
    "CheckStatus",
]
