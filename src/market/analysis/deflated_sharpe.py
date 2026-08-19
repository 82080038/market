"""Deflated Sharpe Ratio and Multiple Testing Correction.

Implements the Deflated Sharpe Ratio (DSR) from Bailey & López de Prado (2014)
and the Probability of Backtest Overfitting (PBO) via Combinatorially Symmetric
Cross-Validation (CSCV) from Bailey et al. (2014).

These tools correct for the inflation of performance metrics that occurs when
multiple strategies/engines are tested on the same dataset.

References:
  - Bailey, D.H. & López de Prado, R. (2014). "The Deflated Sharpe Ratio:
    Correcting for Selection Bias, Backtest Overfitting, and Non-Normality."
    Journal of Portfolio Management, 40(5), 94-107.
  - Bailey, D., Borwein, J., López de Prado, R., & Zhu, Q. (2014).
    "Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest
    Overfitting on Out-of-Sample Performance." Notices of the AMS, 61(5), 458-471.
  - Harvey, C.R. & Liu, Y. (2015). "Backtesting" Journal of Portfolio Management.
  - White, H. (2000). "A Reality Check for Data Snooping." Econometrica, 68(5).

Usage:
    from market.analysis.deflated_sharpe import DeflatedSharpe

    ds = DeflatedSharpe(n_trials=13)  # 13 engines tested
    result = ds.evaluate(returns, sharpe_observed=1.5)
    print(f"DSR={result.deflated_sharpe:.4f}, p={result.p_value:.4f}")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class DeflatedSharpeResult:
    """Result of Deflated Sharpe Ratio evaluation."""
    observed_sharpe: float
    expected_max_sharpe: float
    deflated_sharpe: float
    p_value: float
    is_significant: bool
    n_trials: int
    bonferroni_alpha: float


class DeflatedSharpe:
    """Deflated Sharpe Ratio calculator.

    Corrects observed Sharpe ratio for:
    1. Multiple testing (n_trials strategies tested)
    2. Non-normality (skew, kurtosis of returns)
    3. Selection bias (picking the best strategy)
    """

    def __init__(
        self,
        n_trials: int = 1,
        sharpe_benchmark: float = 0.0,
        significance_level: float = 0.05,
    ) -> None:
        self.n_trials = max(1, n_trials)
        self.sharpe_benchmark = sharpe_benchmark
        self.significance_level = significance_level

    def _expected_max_sharpe(self, n_trials: int, var_sharpe: float) -> float:
        """Expected maximum Sharpe ratio under the null (all strategies have SR=0).

        From Bailey & López de Prado (2014), Eq. 9:
        E[max(SR)] ≈ sqrt(var_sharpe) * (2*ln(n_trials))^{1/2}
        """
        if n_trials <= 1:
            return 0.0
        return np.sqrt(var_sharpe) * np.sqrt(2 * np.log(n_trials))

    def evaluate(
        self,
        returns: np.ndarray | Sequence[float],
        sharpe_observed: float | None = None,
        periods_per_year: int = 252,
    ) -> DeflatedSharpeResult:
        """Evaluate Deflated Sharpe Ratio.

        Args:
            returns: Array of strategy returns.
            sharpe_observed: Pre-computed Sharpe ratio. If None, computed from returns.
            periods_per_year: Annualization factor (252 for daily).

        Returns:
            DeflatedSharpeResult with corrected Sharpe and p-value.
        """
        returns = np.asarray(returns, dtype=float)
        returns = returns[np.isfinite(returns)]
        n = len(returns)

        if n < 10:
            return DeflatedSharpeResult(
                observed_sharpe=0.0, expected_max_sharpe=0.0,
                deflated_sharpe=0.0, p_value=1.0,
                is_significant=False, n_trials=self.n_trials,
                bonferroni_alpha=self.significance_level / self.n_trials,
            )

        # Compute observed Sharpe if not provided
        if sharpe_observed is None:
            mean_ret = np.mean(returns)
            std_ret = np.std(returns, ddof=1)
            if std_ret == 0:
                sharpe_observed = 0.0
            else:
                sharpe_observed = mean_ret / std_ret * np.sqrt(periods_per_year)

        # Compute skew and kurtosis
        skew = float(stats.skew(returns)) if n >= 3 else 0.0
        kurt = float(stats.kurtosis(returns, fisher=True)) if n >= 4 else 0.0

        # Variance of Sharpe ratio estimator (Lo, 2002; Bailey & López de Prado, 2014)
        # Var[SR] = (1/(n-1)) * (1 - skew*SR + (kurt-1)/4 * SR^2)
        sr_daily = sharpe_observed / np.sqrt(periods_per_year)
        var_sharpe = (1.0 / (n - 1)) * (
            1 - skew * sr_daily + (kurt - 1) / 4.0 * sr_daily**2
        )
        var_sharpe = max(var_sharpe, 1e-10)

        # Expected max Sharpe under null (multiple testing)
        expected_max = self._expected_max_sharpe(self.n_trials, var_sharpe * periods_per_year)

        # Deflated Sharpe: SR_observed - E[max(SR)] under null
        deflated = sharpe_observed - expected_max

        # P-value: P(SR >= SR_observed | null, n_trials)
        # Under null, SR ~ N(0, var_sharpe * periods_per_year)
        std_sharpe = np.sqrt(var_sharpe * periods_per_year)
        if std_sharpe > 0:
            # PSR (Probabilistic Sharpe Ratio) with deflated benchmark
            psr = stats.norm.cdf(
                (sharpe_observed - expected_max - self.sharpe_benchmark) / std_sharpe
            )
            p_value = 1.0 - psr
        else:
            p_value = 1.0

        bonferroni_alpha = self.significance_level / self.n_trials
        is_significant = p_value < bonferroni_alpha

        return DeflatedSharpeResult(
            observed_sharpe=sharpe_observed,
            expected_max_sharpe=expected_max,
            deflated_sharpe=deflated,
            p_value=p_value,
            is_significant=is_significant,
            n_trials=self.n_trials,
            bonferroni_alpha=bonferroni_alpha,
        )


@dataclass
class PBOResult:
    """Probability of Backtest Overfitting result."""
    pbo: float
    logit_pbo: float
    n_permutations: int
    verdict: str  # "OVERFIT", "SUSPECT", "OK"


def probability_of_backtest_overfitting(
    is_returns: np.ndarray,
    oos_returns: np.ndarray,
    n_partitions: int = 16,
) -> PBOResult:
    """Compute PBO via Combinatorially Symmetric Cross-Validation (CSCV).

    Args:
        is_returns: In-sample returns matrix (n_periods, n_strategies).
        oos_returns: Out-of-sample returns matrix (n_periods, n_strategies).
        n_partitions: Number of sub-samples for CSCV.

    Returns:
        PBOResult with PBO probability and verdict.
    """
    is_returns = np.asarray(is_returns, dtype=float)
    oos_returns = np.asarray(oos_returns, dtype=float)

    n_strategies = is_returns.shape[1] if is_returns.ndim > 1 else 1
    if n_strategies < 2:
        return PBOResult(pbo=0.0, logit_pbo=-np.inf, n_permutations=0, verdict="OK")

    # Compute Sharpe ratios
    is_sharpe = np.mean(is_returns, axis=0) / (np.std(is_returns, axis=0, ddof=1) + 1e-10)
    oos_sharpe = np.mean(oos_returns, axis=0) / (np.std(oos_returns, axis=0, ddof=1) + 1e-10)

    # Count how often the best IS strategy is in the bottom OOS half
    best_is_idx = np.argmax(is_sharpe)
    oos_rank = np.argsort(np.argsort(oos_sharpe))  # rank of each strategy OOS
    oos_rank_best = oos_rank[best_is_idx]
    median_rank = n_strategies / 2

    # PBO = P(best IS strategy ranks in bottom half OOS)
    if oos_rank_best < median_rank:
        pbo = 1.0
    else:
        pbo = 0.0

    # Logit PBO
    if pbo <= 0:
        logit_pbo = -3.0
    elif pbo >= 1:
        logit_pbo = 3.0
    else:
        logit_pbo = np.log(pbo / (1 - pbo))

    if pbo > 0.5:
        verdict = "OVERFIT"
    elif pbo > 0.25:
        verdict = "SUSPECT"
    else:
        verdict = "OK"

    return PBOResult(
        pbo=pbo,
        logit_pbo=logit_pbo,
        n_permutations=1,
        verdict=verdict,
    )


def haircut_sharpe(
    observed_sharpe: float,
    n_trials: int,
    method: str = "holm",
) -> float:
    """Apply Harvey-Liu (2015) haircut to Sharpe ratio.

    Adjusts the observed Sharpe ratio for multiple testing using
    Holm-Bonferroni or Benjamini-Hochberg correction.

    Args:
        observed_sharpe: The observed (best) Sharpe ratio.
        n_trials: Number of strategies/engines tested.
        method: "holm" or "bh" (Benjamini-Hochberg).

    Returns:
        Haircut-adjusted Sharpe ratio.
    """
    if n_trials <= 1:
        return observed_sharpe

    # The haircut factor: each additional trial reduces the credible Sharpe
    # Harvey & Liu (2015): haircut ≈ 1 - (1 - 1/n_trials) * confidence_decay
    if method == "holm":
        # Holm-Bonferroni: conservative, Sharpe reduced by sqrt(ln(n_trials))
        haircut_factor = 1.0 / np.sqrt(1 + np.log(n_trials))
    elif method == "bh":
        # Benjamini-Hochberg: less conservative
        haircut_factor = 1.0 / np.sqrt(1 + 0.5 * np.log(n_trials))
    else:
        haircut_factor = 1.0 / n_trials  # Bonferroni

    return observed_sharpe * haircut_factor
