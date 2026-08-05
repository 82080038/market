# Eval-Gated Promotion: A/B Testing untuk Self-Improvement

> **Dokumen 71** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Sistem eval-gated promotion yang memastikan setiap perubahan dari self-evolving AI terbukti lebih baik dari baseline sebelum dipromosikan ke production — menggunakan A/B testing, statistical significance, dan falsification criteria.
>
> **Konteks:** Dokumen 67 mendefinisikan Validator Agent yang menjalankan 7 validation layers. Dokumen 70 mendefinisikan hot-swap untuk integrasi. Tapi bagaimana memastikan bahwa kode/strategi/model baru benar-benar lebih baik dari yang lama? Dokumen ini mendefinisikan framework evaluasi yang rigorous, terinspirasi dari AHE (Agentic Harness Engineering) yang membuktikan bahwa eval-gated evolution dapat meningkatkan performance dari 69.7% ke 77.0% dalam 10 iterasi.

---

## Daftar Isi

1. [Konsep Eval-Gated Promotion](#1-konsep-eval-gated-promotion)
2. [Evaluation Framework](#2-evaluation-framework)
3. [A/B Testing untuk Trading](#3-ab-testing-untuk-trading)
4. [Statistical Significance](#4-statistical-significance)
5. [Falsification Criteria](#5-falsification-criteria)
6. [Promotion Pipeline](#6-promotion-pipeline)
7. [Champion/Challenger Pattern](#7-championchallenger-pattern)
8. [Database Schema](#8-database-schema)
9. [Implementasi Kode](#9-implementasi-kode)
10. [Checklist Implementasi](#10-checklist-implementasi)

---

## 1. Konsep Eval-Gated Promotion

### 1.1 Mengapa Eval-Gated

| Tanpa Eval-Gated | Dengan Eval-Gated |
|-------------------|-------------------|
| Setiap perubahan langsung di-promote | Perubahan harus terbukti lebih baik dulu |
| Tidak ada baseline comparison | A/B test: new vs baseline |
| Regression tidak terdeteksi | Falsification: cek apakah new TIDAK lebih buruk |
| "Self-improvement" tanpa evidence | "Self-improvement" dengan measurement |
| Overfitting ke noise | Statistical significance wajib |
| Promosi berdasarkan "feeling" LLM | Promosi berdasarkan metrik objektif |

### 1.2 Prinsip

| Prinsip | Deskripsi |
|---------|-----------|
| **Evidence-based** | Setiap promosi didukung data, bukan opini |
| **Falsifiable** | Setiap improvement bisa di-falsify (dibuktikan salah) |
| **Statistically significant** | Perbedaan bukan karena kebetulan (p < 0.05) |
| **Multi-metric** | Tidak hanya Sharpe — juga drawdown, win rate, stability |
| **Out-of-sample** | Evaluasi pada data yang tidak digunakan untuk development |
| **Reproducible** | Hasil eval bisa di-reproduce dengan seed yang sama |
| **Baseline-gated** | New harus > baseline, bukan hanya > 0 |

### 1.3 Inspirasi dari Riset

| Sumber | Insight | Adaptasi untuk Trading |
|--------|---------|----------------------|
| **AHE (2026)** | 10 iterasi: 69.7% → 77.0% via eval-gated evolution | Setiap self-evolution cycle harus terukur |
| **AHE** | "frozen harness transfers to SWE-bench" — improvement generalizable | Improvement harus transfer ke ticker lain |
| **Darwin Gödel Machine** | "empirically validates each change using coding benchmarks" | Setiap perubahan divalidasi via backtest benchmark |
| **AutoDev** | "eval-gated prompt evolution" — prompts sharpen over time | Strategy/indicator logic sharpen over time |
| **SEMAG** | "self-evolutionary model selection" — auto-upgrade backbone | Auto-switch model jika terbukti lebih baik |

---

## 2. Evaluation Framework

### 2.1 Evaluation Layers

```
┌──────────────────────────────────────────────────────────────┐
│                  EVAL-GATED PROMOTION                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Layer 1: UNIT TEST                                          │
│  - 100% pass required                                        │
│  - Coverage ≥ 80%                                            │
│  - No skipped tests                                          │
│                                                              │
│  Layer 2: INTEGRATION TEST                                   │
│  - 100% pass with test DB                                    │
│  - API contract validation                                   │
│  - Event bus integration                                     │
│                                                              │
│  Layer 3: BACKTEST (5 tahun, IDX)                            │
│  - Sharpe > baseline Sharpe                                  │
│  - Max drawdown ≤ baseline × 1.2                             │
│  - Win rate ≥ baseline × 0.95                                │
│  - Profit factor ≥ 1.2                                       │
│                                                              │
│  Layer 4: WALK-FORWARD (3 folds, purged TSS)                 │
│  - OOS Sharpe > 70% in-sample Sharpe                         │
│  - No fold dengan Sharpe < 0                                 │
│  - Stability: std(fold Sharpe) < 0.3                         │
│                                                              │
│  Layer 5: STATISTICAL SIGNIFICANCE                           │
│  - p-value < 0.05 (Sharpe difference)                        │
│  - Effect size (Cohen's d) > 0.2                             │
│  - Bootstrap CI: 95% CI tidak overlap 0                      │
│                                                              │
│  Layer 6: ROBUSTNESS                                         │
│  - Works on multiple tickers (min 10)                        │
│  - Works in multiple regimes (easing, tightening, risk_off)  │
│  - Transaction cost sensitive (still profitable with 2x fee) │
│                                                              │
│  Layer 7: CODE QUALITY                                       │
│  - ruff: 0 errors                                            │
│  - mypy: 0 errors                                            │
│  - bandit: 0 high/critical                                   │
│  - PIT-safe: no look-ahead bias                              │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  ALL 7 LAYERS PASS → PROMOTE                                 │
│  ANY LAYER FAILS → REJECT + FEEDBACK                         │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Metrics untuk Trading

| Metric | Formula | Gate | Weight |
|--------|---------|------|--------|
| **Sharpe Ratio** | `excess.mean() / returns.std() * sqrt(252)` | > baseline | 30% |
| **Max Drawdown** | `min((equity - cummax) / cummax)` | ≤ baseline × 1.2 | 20% |
| **Win Rate** | `wins / total_trades` | ≥ baseline × 0.95 | 15% |
| **Profit Factor** | `wins.sum() / abs(losses.sum())` | ≥ 1.2 | 15% |
| **Calmar Ratio** | `CAGR / abs(max_drawdown)` | > baseline | 10% |
| **Sortino Ratio** | `excess.mean() / downside.std() * sqrt(252)` | > baseline | 10% |

### 2.3 Composite Score

```python
composite_score = (
    sharpe_score * 0.30 +
    drawdown_score * 0.20 +
    winrate_score * 0.15 +
    profitfactor_score * 0.15 +
    calmar_score * 0.10 +
    sortino_score * 0.10
)

# Promote jika composite_score > baseline_composite_score
# DAN setiap individual metric pass gate-nya
```

---

## 3. A/B Testing untuk Trading

### 3.1 Konsep

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  BASELINE   │     │  CHALLENGER │     │  EVALUATION │
│  (Champion) │     │  (New code) │     │  WINDOW     │
│             │     │             │     │             │
│  Strategy A │     │  Strategy B │     │  Compare    │
│  Model v1   │     │  Model v2   │     │  A vs B     │
│  Weight set │     │  Weight set │     │  on same    │
│  old        │     │  new        │     │  data       │
└─────────────┘     └─────────────┘     └─────────────┘
```

### 3.2 Method

| Method | Deskripsi | Use Case |
|--------|-----------|----------|
| **Historical A/B** | Run both strategies pada historical data yang sama | Backtest comparison |
| **Forward A/B** | Run both strategies secara paralel dengan live data | Paper trading comparison |
| **Cross-validation A/B** | Run pada multiple fold, compare aggregate | Walk-forward comparison |
| **Monte Carlo A/B** | Run both pada bootstrap samples | Robustness comparison |

### 3.3 Historical A/B

```python
# self_evolution/eval_gated/ab_test.py
from dataclasses import dataclass, field
from typing import Any
import numpy as np
import pandas as pd

@dataclass
class ABTestResult:
    baseline_metrics: dict[str, float]
    challenger_metrics: dict[str, float]
    improvement: dict[str, float]  # percentage improvement
    p_values: dict[str, float]    # statistical significance
    effect_sizes: dict[str, float]  # Cohen's d
    overall_winner: str  # "baseline", "challenger", "tie"
    confidence: float   # 0-1
    recommendation: str  # "promote", "reject", "inconclusive"

class TradingABTest:
    """A/B testing untuk trading strategies/models."""

    def __init__(self, backtest_engine, walk_forward):
        self.backtest = backtest_engine
        self.walk_forward = walk_forward

    def run_historical_ab(self, baseline_fn, challenger_fn,
                          tickers: list[str], period: str = "5y") -> ABTestResult:
        """
        Run A/B test pada historical data.
        
        Args:
            baseline_fn: Function yang run baseline strategy
            challenger_fn: Function yang run challenger strategy
            tickers: List ticker untuk test
            period: Periode historical data
        """
        baseline_results = {}
        challenger_results = {}

        for ticker in tickers:
            # Run baseline
            baseline_result = baseline_fn(ticker, period)
            baseline_results[ticker] = self._extract_metrics(baseline_result)

            # Run challenger pada data yang sama
            challenger_result = challenger_fn(ticker, period)
            challenger_results[ticker] = self._extract_metrics(challenger_result)

        # Aggregate
        baseline_agg = self._aggregate_metrics(baseline_results)
        challenger_agg = self._aggregate_metrics(challenger_results)

        # Compute improvement
        improvement = self._compute_improvement(baseline_agg, challenger_agg)

        # Statistical significance
        p_values = self._compute_p_values(baseline_results, challenger_results)
        effect_sizes = self._compute_effect_sizes(baseline_results, challenger_results)

        # Determine winner
        winner, confidence = self._determine_winner(
            baseline_agg, challenger_agg, improvement, p_values
        )

        recommendation = self._make_recommendation(winner, confidence, p_values)

        return ABTestResult(
            baseline_metrics=baseline_agg,
            challenger_metrics=challenger_agg,
            improvement=improvement,
            p_values=p_values,
            effect_sizes=effect_sizes,
            overall_winner=winner,
            confidence=confidence,
            recommendation=recommendation,
        )

    def _extract_metrics(self, backtest_result) -> dict[str, float]:
        """Extract key metrics dari backtest result."""
        return {
            "sharpe": backtest_result.get("sharpe_ratio", 0),
            "max_drawdown": backtest_result.get("max_drawdown", 0),
            "win_rate": backtest_result.get("win_rate", 0),
            "profit_factor": backtest_result.get("profit_factor", 0),
            "calmar": backtest_result.get("calmar_ratio", 0),
            "sortino": backtest_result.get("sortino_ratio", 0),
            "total_return": backtest_result.get("total_return", 0),
            "cagr": backtest_result.get("cagr", 0),
        }

    def _aggregate_metrics(self, per_ticker: dict) -> dict[str, float]:
        """Aggregate metrics across tickers (median untuk robustness)."""
        metrics = {}
        for key in per_ticker[list(per_ticker.keys())[0]].keys():
            values = [t[key] for t in per_ticker.values()]
            metrics[key] = float(np.median(values))  # Median lebih robust
        return metrics

    def _compute_improvement(self, baseline: dict, challenger: dict) -> dict[str, float]:
        """Compute percentage improvement per metric."""
        improvement = {}
        for key in baseline:
            if baseline[key] != 0:
                improvement[key] = ((challenger[key] - baseline[key]) / abs(baseline[key])) * 100
            else:
                improvement[key] = 0.0 if challenger[key] == 0 else float('inf')
        return improvement

    def _compute_p_values(self, baseline: dict, challenger: dict) -> dict[str, float]:
        """Compute p-value per metric menggunakan paired t-test."""
        from scipy import stats
        p_values = {}
        for key in baseline[list(baseline.keys())[0]].keys():
            b_values = [t[key] for t in baseline.values()]
            c_values = [t[key] for t in challenger.values()]
            if len(b_values) > 1 and len(c_values) > 1:
                _, p = stats.ttest_rel(c_values, b_values)
                p_values[key] = float(p)
            else:
                p_values[key] = 1.0
        return p_values

    def _compute_effect_sizes(self, baseline: dict, challenger: dict) -> dict[str, float]:
        """Compute Cohen's d effect size per metric."""
        effect_sizes = {}
        for key in baseline[list(baseline.keys())[0]].keys():
            b_values = [t[key] for t in baseline.values()]
            c_values = [t[key] for t in challenger.values()]
            if len(b_values) > 1:
                pooled_std = np.std(b_values + c_values, ddof=1)
                if pooled_std > 0:
                    effect_sizes[key] = float(
                        (np.mean(c_values) - np.mean(b_values)) / pooled_std
                    )
                else:
                    effect_sizes[key] = 0.0
            else:
                effect_sizes[key] = 0.0
        return effect_sizes

    def _determine_winner(self, baseline, challenger, improvement, p_values) -> tuple[str, float]:
        """Determine overall winner berdasarkan multi-criteria."""
        # Key metrics yang harus improvement
        key_metrics = ["sharpe", "max_drawdown", "win_rate", "profit_factor"]
        
        wins = 0
        total = len(key_metrics)
        
        for metric in key_metrics:
            # Improvement + statistically significant
            if metric == "max_drawdown":
                # Lower is better
                is_better = challenger[metric] > baseline[metric]  # less negative
            else:
                is_better = challenger[metric] > baseline[metric]
            
            is_significant = p_values.get(metric, 1.0) < 0.05
            
            if is_better and is_significant:
                wins += 1
        
        confidence = wins / total
        
        if confidence > 0.7:
            return "challenger", confidence
        elif confidence < 0.3:
            return "baseline", 1 - confidence
        else:
            return "tie", 0.5

    def _make_recommendation(self, winner: str, confidence: float,
                              p_values: dict) -> str:
        """Make promotion recommendation."""
        if winner == "challenger" and confidence > 0.7:
            # Cek apakah semua key metrics significant
            key_p = [p_values.get(m, 1.0) for m in ["sharpe", "profit_factor"]]
            if all(p < 0.05 for p in key_p):
                return "promote"
            else:
                return "inconclusive"
        elif winner == "baseline":
            return "reject"
        else:
            return "inconclusive"
```

---

## 4. Statistical Significance

### 4.1 Tests

| Test | Use Case | Threshold |
|------|----------|-----------|
| **Paired t-test** | Compare Sharpe baseline vs challenger across tickers | p < 0.05 |
| **Wilcoxon signed-rank** | Non-parametric alternative jika tidak normal | p < 0.05 |
| **Bootstrap CI** | Confidence interval untuk Sharpe difference | 95% CI tidak overlap 0 |
| **Deflated Sharpe Ratio** | Correct for multiple testing | DSR > 0 |
| **Cohen's d** | Effect size | d > 0.2 (small), > 0.5 (medium), > 0.8 (large) |

### 4.2 Bootstrap Implementation

```python
# self_evolution/eval_gated/bootstrap.py
import numpy as np
from typing import tuple

def bootstrap_sharpe_difference(
    baseline_returns: np.ndarray,
    challenger_returns: np.ndarray,
    n_bootstrap: int = 10000,
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """
    Bootstrap test untuk Sharpe ratio difference.
    
    Returns:
        (mean_difference, lower_ci, upper_ci)
    """
    def sharpe(returns):
        if returns.std() == 0:
            return 0
        return returns.mean() / returns.std() * np.sqrt(252)
    
    baseline_sharpe = sharpe(baseline_returns)
    challenger_sharpe = sharpe(challenger_returns)
    observed_diff = challenger_sharpe - baseline_sharpe
    
    # Bootstrap
    n = len(baseline_returns)
    diffs = []
    for _ in range(n_bootstrap):
        idx = np.random.choice(n, n, replace=True)
        b_sample = baseline_returns[idx]
        c_sample = challenger_returns[idx]
        diffs.append(sharpe(c_sample) - sharpe(b_sample))
    
    diffs = np.array(diffs)
    lower = np.percentile(diffs, (1 - confidence) / 2 * 100)
    upper = np.percentile(diffs, (1 + confidence) / 2 * 100)
    
    return float(observed_diff), float(lower), float(upper)
```

---

## 5. Falsification Criteria

### 5.1 Konsep

> **Falsification:** Sebuah improvement dianggap valid hanya jika TIDAK BISA dibuktikan salah. Jika ada satu kondisi di mana improvement menjadi regression, maka tidak boleh di-promote.

### 5.2 Falsification Tests

| Test | Pertanyaan | Fail Condition |
|------|-----------|----------------|
| **Regime test** | Apakah improvement bekerja di SEMUA regime? | Sharpe < 0 di salah satu regime |
| **Ticker test** | Apakah improvement bekerja di > 80% tickers? | < 80% tickers show improvement |
| **Cost sensitivity** | Apakah masih profitable dengan 2x transaction cost? | Profit factor < 1.0 dengan 2x fee |
| **Period test** | Apakah improvement konsisten across 5 sub-periods? | Sharpe < 0 di salah satu sub-period |
| **Stress test** | Apakah survive crisis period (2008, 2020, 2024)? | Max drawdown > 40% di crisis |
| **Overfitting test** | Apakah in-sample vs OOS ratio < 1.5? | OOS Sharpe < 70% in-sample |
| **PIT-safe test** | Apakah tidak ada look-ahead bias? | Ditemukan akses ke future data |

### 5.3 Implementation

```python
# self_evolution/eval_gated/falsification.py
from dataclasses import dataclass

@dataclass
class FalsificationResult:
    test_name: str
    passed: bool
    details: str
    severity: str  # critical, high, medium, low

class FalsificationTester:
    """Falsification tests untuk self-generated improvements."""

    def run_all(self, baseline_metrics: dict, challenger_metrics: dict,
                per_ticker: dict, per_regime: dict) -> list[FalsificationResult]:
        results = []
        results.append(self.test_regime_robustness(per_regime))
        results.append(self.test_ticker_coverage(per_ticker))
        results.append(self.test_cost_sensitivity(challenger_metrics))
        results.append(self.test_period_consistency(per_ticker))
        results.append(self.test_overfitting(baseline_metrics, challenger_metrics))
        return results

    def test_regime_robustness(self, per_regime: dict) -> FalsificationResult:
        """Cek apakah improvement bekerja di semua regime."""
        failing_regimes = []
        for regime, metrics in per_regime.items():
            if metrics.get("sharpe", 0) < 0:
                failing_regimes.append(regime)
        
        if failing_regimes:
            return FalsificationResult(
                test_name="regime_robustness",
                passed=False,
                details=f"Negative Sharpe in regimes: {failing_regimes}",
                severity="critical",
            )
        return FalsificationResult(
            test_name="regime_robustness",
            passed=True,
            details="Positive Sharpe in all regimes",
            severity="low",
        )

    def test_ticker_coverage(self, per_ticker: dict) -> FalsificationResult:
        """Cek apakah improvement bekerja di > 80% tickers."""
        improved = sum(1 for m in per_ticker.values() if m.get("improved", False))
        total = len(per_ticker)
        coverage = improved / total if total > 0 else 0
        
        if coverage < 0.8:
            return FalsificationResult(
                test_name="ticker_coverage",
                passed=False,
                details=f"Only {coverage:.0%} of tickers improved ({improved}/{total})",
                severity="high",
            )
        return FalsificationResult(
            test_name="ticker_coverage",
            passed=True,
            details=f"{coverage:.0%} of tickers improved ({improved}/{total})",
            severity="low",
        )

    def test_cost_sensitivity(self, metrics: dict) -> FalsificationResult:
        """Cek apakah masih profitable dengan 2x transaction cost."""
        pf_2x = metrics.get("profit_factor_2x_cost", 0)
        if pf_2x < 1.0:
            return FalsificationResult(
                test_name="cost_sensitivity",
                passed=False,
                details=f"Profit factor with 2x cost: {pf_2x:.2f} (< 1.0)",
                severity="high",
            )
        return FalsificationResult(
            test_name="cost_sensitivity",
            passed=True,
            details=f"Profit factor with 2x cost: {pf_2x:.2f}",
            severity="low",
        )

    def test_overfitting(self, baseline: dict, challenger: dict) -> FalsificationResult:
        """Cek apakah in-sample vs OOS ratio acceptable."""
        is_sharpe = challenger.get("in_sample_sharpe", 0)
        oos_sharpe = challenger.get("out_of_sample_sharpe", 0)
        
        if is_sharpe > 0:
            ratio = oos_sharpe / is_sharpe
            if ratio < 0.7:
                return FalsificationResult(
                    test_name="overfitting",
                    passed=False,
                    details=f"OOS/IS ratio: {ratio:.2f} (< 0.70) — likely overfitting",
                    severity="critical",
                )
        return FalsificationResult(
            test_name="overfitting",
            passed=True,
            details=f"OOS/IS ratio: {oos_sharpe/max(is_sharpe, 0.01):.2f}",
            severity="low",
        )
```

---

## 6. Promotion Pipeline

### 6.1 Full Pipeline

```
BUILD RESULT (dari Builder Agent)
    │
    ▼
LAYER 1: Unit Test (sandbox)
    ├── PASS → continue
    └── FAIL → REJECT
    │
    ▼
LAYER 2: Integration Test (sandbox)
    ├── PASS → continue
    └── FAIL → REJECT
    │
    ▼
LAYER 3: Backtest (5 tahun, 10+ tickers)
    ├── Sharpe > baseline → continue
    └── Sharpe ≤ baseline → REJECT
    │
    ▼
LAYER 4: Walk-Forward (3 folds, purged TSS)
    ├── OOS > 70% IS → continue
    └── OOS < 70% IS → REJECT (overfitting)
    │
    ▼
LAYER 5: A/B Test (statistical significance)
    ├── p < 0.05 AND effect > 0.2 → continue
    └── p ≥ 0.05 → INCONCLUSIVE (hold for more data)
    │
    ▼
LAYER 6: Falsification Tests
    ├── All pass → continue
    └── Any critical fail → REJECT
    │
    ▼
LAYER 7: Code Quality (ruff, mypy, bandit, PIT-safe)
    ├── All pass → PROMOTE
    └── Any fail → REJECT
    │
    ▼
PROMOTE (hot-swap + knowledge base + audit log)
```

### 6.2 Decision Matrix

| A/B Result | Falsification | Code Quality | Decision |
|------------|---------------|---------------|----------|
| Challenger wins (p<0.05) | All pass | All pass | **PROMOTE** |
| Challenger wins (p<0.05) | Any critical fail | - | **REJECT** |
| Challenger wins (p<0.05) | All pass | Any fail | **REJECT** (fix code quality) |
| Tie (p≥0.05) | All pass | All pass | **HOLD** (collect more data) |
| Baseline wins | - | - | **REJECT** |
| Inconclusive | - | - | **HOLD** (max 3 holds, then REJECT) |

---

## 7. Champion/Challenger Pattern

### 7.1 Konsep

```
PRODUCTION (Champion)
    │
    ├── Performance metrics tracked continuously
    │
    ├── CHALLENGER arrives (from Builder)
    │   ├── Run A/B test
    │   ├── If challenger wins → promote to new champion
    │   └── If champion wins → reject challenger
    │
    └── CHAMPION retained
        ├── Monitor for drift
        ├── If drift detected → trigger new evolution
        └── If performance drop → trigger new evolution
```

### 7.2 Integration dengan MLOps

Dokumen ini melengkapi dokumen 51 (MLOps & Model Risk Management):
- Dokumen 51: model lifecycle, drift detection, champion/challenger untuk ML models
- Dokumen 71 (ini): eval-gated promotion untuk self-generated code/strategy/model
- Integrasi: self-generated model mengikuti champion/challenger pattern dari dokumen 51

---

## 8. Database Schema

```sql
-- A/B test results
CREATE TABLE IF NOT EXISTS eval_ab_tests (
    test_id TEXT PRIMARY KEY,
    trigger_id TEXT,
    baseline_hash TEXT NOT NULL,     -- SHA256 of baseline code
    challenger_hash TEXT NOT NULL,   -- SHA256 of challenger code
    baseline_metrics TEXT,           -- JSON
    challenger_metrics TEXT,         -- JSON
    improvement TEXT,                -- JSON
    p_values TEXT,                   -- JSON
    effect_sizes TEXT,               -- JSON
    winner TEXT,                     -- baseline, challenger, tie
    confidence REAL,
    recommendation TEXT,             -- promote, reject, inconclusive
    falsification_results TEXT,      -- JSON
    created_at TEXT NOT NULL,
    FOREIGN KEY (trigger_id) REFERENCES evolution_triggers(trigger_id)
);

-- Promotion log
CREATE TABLE IF NOT EXISTS eval_promotions (
    promotion_id TEXT PRIMARY KEY,
    test_id TEXT NOT NULL,
    trigger_id TEXT,
    promoted_module TEXT NOT NULL,
    old_version_hash TEXT,
    new_version_hash TEXT,
    metrics_before TEXT,             -- JSON
    metrics_after TEXT,              -- JSON (filled after post-promotion monitoring)
    status TEXT DEFAULT 'promoted',  -- promoted, reverted, failed
    created_at TEXT NOT NULL,
    FOREIGN KEY (test_id) REFERENCES eval_ab_tests(test_id),
    FOREIGN KEY (trigger_id) REFERENCES evolution_triggers(trigger_id)
);
```

---

## 9. Implementasi Kode

### 9.1 Module Structure

```
src/trading_system/self_evolution/eval_gated/
├── __init__.py
├── ab_test.py           # TradingABTest
├── bootstrap.py         # Bootstrap significance tests
├── falsification.py     # FalsificationTester
├── pipeline.py          # EvalPipeline — 7-layer pipeline
└── champion.py          # ChampionChallengerManager
```

### 9.2 EvalPipeline

```python
# self_evolution/eval_gated/pipeline.py
from dataclasses import dataclass, field
from typing import Any

@dataclass
class EvalResult:
    trigger_id: str
    layer_results: dict[str, dict[str, Any]]
    overall_passed: bool
    recommendation: str  # promote, reject, hold
    metrics: dict[str, float]
    failure_reasons: list[str] = field(default_factory=list)

class EvalPipeline:
    """7-layer evaluation pipeline untuk self-generated improvements."""

    def __init__(self, sandbox, backtest_engine, walk_forward, ab_test, falsifier):
        self.sandbox = sandbox
        self.backtest = backtest_engine
        self.walk_forward = walk_forward
        self.ab_test = ab_test
        self.falsifier = falsifier

    def evaluate(self, build_result, analysis, baseline_fn=None) -> EvalResult:
        """Run full 7-layer evaluation pipeline."""
        results = {}
        failures = []

        # Layer 1: Unit test
        results["unit_test"] = self._run_unit_tests(build_result)
        if not results["unit_test"]["passed"]:
            failures.append("Unit tests failed")

        # Layer 2: Integration test
        results["integration_test"] = self._run_integration_tests(build_result)
        if not results["integration_test"]["passed"]:
            failures.append("Integration tests failed")

        # Layer 3: Backtest
        if analysis.solution_type in ("new_strategy", "optimize_model", "add_feature"):
            results["backtest"] = self._run_backtest(build_result, analysis)
            if not results["backtest"]["passed"]:
                failures.append(f"Backtest failed: {results['backtest'].get('details', '')}")

        # Layer 4: Walk-forward
        if analysis.solution_type in ("new_strategy", "optimize_model"):
            results["walk_forward"] = self._run_walk_forward(build_result, analysis)
            if not results["walk_forward"]["passed"]:
                failures.append("Walk-forward failed: overfitting detected")

        # Layer 5: A/B test
        if baseline_fn and analysis.solution_type in ("new_strategy", "optimize_model"):
            results["ab_test"] = self._run_ab_test(build_result, baseline_fn)
            if results["ab_test"].get("recommendation") == "reject":
                failures.append("A/B test: baseline outperforms challenger")

        # Layer 6: Falsification
        if analysis.solution_type in ("new_strategy", "optimize_model"):
            results["falsification"] = self._run_falsification(results)
            if not results["falsification"]["passed"]:
                failures.append(f"Falsification: {results['falsification'].get('details', '')}")

        # Layer 7: Code quality
        results["code_quality"] = self._check_code_quality(build_result)
        if not results["code_quality"]["passed"]:
            failures.append("Code quality checks failed")

        # Determine recommendation
        if not failures:
            recommendation = "promote"
        elif any("critical" in str(f) for f in failures):
            recommendation = "reject"
        elif "inconclusive" in str(results.get("ab_test", {}).get("recommendation", "")):
            recommendation = "hold"
        else:
            recommendation = "reject"

        return EvalResult(
            trigger_id=analysis.trigger_id,
            layer_results=results,
            overall_passed=len(failures) == 0,
            recommendation=recommendation,
            metrics=results.get("backtest", {}).get("metrics", {}),
            failure_reasons=failures,
        )
```

---

## 10. Checklist Implementasi

### Phase 1: Core Pipeline

- [ ] Implementasi `EvalPipeline` dengan 7 layers
- [ ] Implementasi `TradingABTest` dengan historical A/B
- [ ] Implementasi `FalsificationTester` dengan 5 falsification tests
- [ ] Buat database tables: `eval_ab_tests`, `eval_promotions`
- [ ] Test: run pipeline dengan strategy yang sengaja lebih buruk → reject

### Phase 2: Statistical Rigor

- [ ] Implementasi bootstrap Sharpe difference test
- [ ] Implementasi paired t-test dan Wilcoxon test
- [ ] Implementasi Deflated Sharpe Ratio (correct for multiple testing)
- [ ] Implementasi Cohen's d effect size
- [ ] Test: run dengan random strategy → verify p-value > 0.05

### Phase 3: Integration

- [ ] Integrasikan dengan Validator Agent (dokumen 67)
- [ ] Integrasikan dengan Champion/Challenger dari dokumen 51
- [ ] Tambah post-promotion monitoring (track metrics after promote)
- [ ] Tambah auto-revert jika post-promotion performance drops > 20%
- [ ] E2E test: build → validate → A/B test → promote → monitor → revert

### Phase 4: Analytics

- [ ] Tambah dashboard: eval history, promotion rate, rejection reasons
- [ ] Tambah alert: "5 consecutive rejections → review LLM prompt quality"
- [ ] Tambah metric: "improvement velocity" (how fast system improves per cycle)
- [ ] Tambah metric: "false positive rate" (promotions that later reverted)

---

## Referensi Silang

| Topik | Dokumen Referensi |
|-------|-------------------|
| LLM Agent Layer | `67-llm-agent-layer-self-evolution.md` |
| Sandbox execution | `68-sandbox-execution-self-generated-code.md` |
| Hot-swap mechanism | `70-hot-swap-runtime-update.md` |
| MLOps & champion/challenger | `51-mlops-model-risk-management.md` |
| Backtesting & validation | `29-backtesting-strategy-validation.md` |
| Walk-forward & purged TSS | `23-machine-learning-trading.md` |
| Machine learning trading | `23-machine-learning-trading.md` |
| Change & release management | `50-change-release-management-trading.md` |

---

## Referensi Eksternal

1. **AHE (Agentic Harness Engineering)** — Observability-driven evolution, 10 iterasi: 69.7% → 77.0% (arxiv.org/abs/2604.25850, 2026) — "each self-modification is automatically falsified by the next iteration's flipped tasks"
2. **Darwin Gödel Machine** — Empirical validation on coding benchmarks (arxiv.org/abs/2505.22954, 2025) — "automatically improves its coding capabilities, producing performance increases on SWE-bench from 20.0% to 50.0%"
3. **AutoDev** — Eval-gated prompt evolution (github.com/RitikPatill/autodev, 2026) — "gated by an A/B eval harness — prompts sharpen over time based on observed outputs"
4. **Deflated Sharpe Ratio** — López de Prado, "Advances in Financial Machine Learning" — correct for multiple testing in strategy evaluation
5. **Bootstrap methods** — Efron & Tibshirani — for robust confidence intervals

---

> **Catatan:** Eval-gated promotion adalah **quality gate** yang memastikan self-evolution benar-benar menghasilkan improvement, bukan illusion. Tanpa eval-gated, sistem bisa "self-destruct" dengan mempromosikan perubahan yang sebenarnya regression. Dengan eval-gated, setiap promosi terbukti secara statistik dan praktis.
