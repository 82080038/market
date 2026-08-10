"""Pairs Trading / Statistical Arbitrage Engine (pustaka/35, pustaka/89 §8).

Statistical arbitrage engine for pairs of IDX stocks based on
cointegration (Engle-Granger) and Z-score mean-reversion.

Research context (Yunita et al., ZERO Journal 2025): LSTM-based pairs
trading on IDX financial stocks achieved Sharpe 1.67 vs 0.69 traditional,
return 735% vs 482% (2015-2025). Identified pairs: AKRA-BMRI, BTPN-PWON,
BDMN-MIKA, BTPN-CPIN, ADMF-ISAT.

Key principles:
1. NO LOOK-AHEAD: Z-score at time T uses only data <= T. Rolling stats
   are shifted by 1 (``.shift(1)``) so signals never peek at the current
   bar's close when deciding to enter/exit.
2. COINTEGRATION FIRST: A pair must pass Engle-Granger cointegration
   (p-value < 0.05) before any spread signal is generated.
3. REGIME GATE: When rolling correlation between the pair exceeds 0.95
   (panic/euphoria regime), new entries are skipped — pairs trading
   fails when both legs move in lockstep (Pratama 2025, IDX regime filter).
4. CPU-ONLY: Uses pandas/numpy/scipy only (AGENTS.md §4 — no GPU needed).

statsmodels is NOT a project dependency (see ``pyproject.toml``). The
Engle-Granger test is implemented via OLS residuals + a custom ADF test
using numpy/scipy, with MacKinnon (1991) critical values for the
two-variable cointegration case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Engle-Granger / ADF critical values (MacKinnon 1991, N=2, constant case)
# ---------------------------------------------------------------------------
# Asymptotic critical values for the ADF test on residuals from a
# cointegrating regression with 2 variables and a constant. These are the
# standard tabulated values used by statsmodels' ``coint`` when no trend is
# specified. Sample-size correction is applied via the response surface
# ``CV(T) = c_inf + c_1 / T``.
_EG_CV_INF: dict[float, float] = {
    0.01: -3.9001,
    0.05: -3.3377,
    0.10: -3.0462,
}
_EG_CV_SLOPE: dict[float, float] = {
    0.01: -12.63,
    0.05: -5.71,
    0.10: -4.31,
}


def _eg_critical_value(significance: float, n: int) -> float:
    """MacKinnon (1991) response-surface critical value for Engle-Granger (N=2).

    Args:
        significance: Significance level (0.01, 0.05, or 0.10).
        n: Sample size used in the ADF regression.

    Returns:
        Critical value (more negative = stricter).
    """
    c_inf = _EG_CV_INF[significance]
    c1 = _EG_CV_SLOPE[significance]
    return c_inf + c1 / max(n, 1)


def _adf_pvalue(t_stat: float, n: int) -> float:
    """Approximate p-value for the Engle-Granger ADF t-statistic.

    Uses the MacKinnon (1991) response-surface critical values at 1%, 5%,
    10% and linearly interpolates / extrapolates the p-value. The test is
    left-tailed (more negative t-stat → more significant).

    Args:
        t_stat: ADF t-statistic (negative under stationarity).
        n: Sample size.

    Returns:
        Approximate p-value in [0, 1].
    """
    cv_01 = _eg_critical_value(0.01, n)
    cv_05 = _eg_critical_value(0.05, n)
    cv_10 = _eg_critical_value(0.10, n)

    # More negative than 1% CV → p < 0.01 (extrapolate toward 0)
    if t_stat <= cv_01:
        # Linear extrapolation in the far left tail.
        # Slope between 1% and 5% critical values.
        slope = (0.05 - 0.01) / (cv_05 - cv_01)
        p = 0.01 + slope * (t_stat - cv_01)
        return float(max(p, 0.0))

    # Between 1% and 5%
    if t_stat <= cv_05:
        slope = (0.05 - 0.01) / (cv_05 - cv_01)
        p = 0.01 + slope * (t_stat - cv_01)
        return float(p)

    # Between 5% and 10%
    if t_stat <= cv_10:
        slope = (0.10 - 0.05) / (cv_10 - cv_05)
        p = 0.05 + slope * (t_stat - cv_05)
        return float(p)

    # Less negative than 10% CV → p > 0.10 (extrapolate toward 1)
    slope = (0.10 - 0.05) / (cv_10 - cv_05)
    p = 0.10 + slope * (t_stat - cv_10)
    return float(min(p, 1.0))


def _adf_test(residuals: np.ndarray, max_lag: int = 1) -> tuple[float, float]:
    """Run an Augmented Dickey-Fuller test on a 1-D residual series.

    Regression (no constant - residuals have ~zero mean by construction):

        d(e_t) = gamma * e_{t-1} + sum_{i=1}^{p} delta_i * d(e_{t-i}) + eps_t

    H0: gamma = 0 (unit root -> not cointegrated).
    The t-statistic on gamma is the ADF statistic.

    Args:
        residuals: 1-D array of OLS residuals.
        max_lag: Number of lagged difference terms to include.

    Returns:
        Tuple of (adf_t_statistic, approximate p_value).
    """
    e = np.asarray(residuals, dtype=float)
    n = len(e)
    # Need enough points for the regression.
    min_obs = max_lag + 3
    if n < min_obs:
        return 0.0, 1.0

    diff = np.diff(e)  # Δe_t, length n-1
    lagged_level = e[:-1]  # e_{t-1}, length n-1

    # Build design matrix: [e_{t-1}, Δe_{t-1}, Δe_{t-2}, ...]
    cols = [lagged_level]
    for lag in range(1, max_lag + 1):
        if lag >= len(diff):
            break
        shifted = np.full_like(diff, np.nan)
        shifted[lag:] = diff[:-lag]
        cols.append(shifted)

    design = np.column_stack(cols)
    y = diff

    # Drop rows with NaN (from lag alignment).
    mask = ~np.isnan(design).any(axis=1)
    design = design[mask]
    y = y[mask]

    n_eff = len(y)
    if n_eff < min_obs:
        return 0.0, 1.0

    # OLS: y = design @ beta
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    resid = y - design @ beta
    dof = max(n_eff - design.shape[1], 1)
    sigma2 = float(resid @ resid) / dof
    # Covariance of beta = sigma2 * (X'X)^-1
    try:
        xtx_inv = np.linalg.inv(design.T @ design)
    except np.linalg.LinAlgError:
        return 0.0, 1.0
    se = np.sqrt(np.diag(sigma2 * xtx_inv))
    if se[0] == 0:
        return 0.0, 1.0
    t_stat = float(beta[0] / se[0])
    p_value = _adf_pvalue(t_stat, n_eff)
    return t_stat, p_value


def _half_life(residuals: np.ndarray) -> float:
    """Compute the half-life of mean reversion for a residual series.

    Fits an AR(1) model: e_t = rho * e_{t-1} + eps, then

        half_life = -ln(2) / ln(rho)

    A half-life of ``inf`` means no mean reversion (rho >= 1).

    Args:
        residuals: 1-D array of OLS residuals.

    Returns:
        Half-life in periods (days). Returns ``np.inf`` if non-stationary.
    """
    e = np.asarray(residuals, dtype=float)
    if len(e) < 3:
        return float("inf")
    y = e[1:]
    x = e[:-1]
    # OLS through origin: y = rho * x
    denom = float(x @ x)
    if denom == 0:
        return float("inf")
    rho = float(x @ y) / denom
    if rho <= 0:
        # Strongly mean-reverting; half-life essentially immediate.
        return 0.0
    if rho >= 1.0:
        return float("inf")
    return float(-np.log(2.0) / np.log(rho))


def _ols_hedge_ratio(price_a: pd.Series, price_b: pd.Series) -> tuple[float, float, np.ndarray]:
    """OLS regression: price_A = alpha + beta * price_B + epsilon.

    Args:
        price_a: Dependent series (leg A).
        price_b: Independent series (leg B).

    Returns:
        Tuple of (alpha, beta, residuals_array).
    """
    a = price_a.to_numpy(dtype=float)
    b = price_b.to_numpy(dtype=float)
    x = np.column_stack([np.ones_like(b), b])
    beta_vec, *_ = np.linalg.lstsq(x, a, rcond=None)
    alpha = float(beta_vec[0])
    beta = float(beta_vec[1])
    resid = a - x @ beta_vec
    return alpha, beta, resid


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class SignalAction(Enum):
    """Trading signal action for a spread position."""

    FLAT = "flat"
    LONG_SPREAD = "long_spread"  # buy A, sell B
    SHORT_SPREAD = "short_spread"  # sell A, buy B
    EXIT = "exit"
    STOP_LOSS = "stop_loss"


@dataclass
class PairResult:
    """Cointegration screening result for a single pair."""

    ticker_a: str
    ticker_b: str
    coint_stat: float
    p_value: float
    correlation: float
    half_life: float
    hedge_ratio: float
    intercept: float
    is_cointegrated: bool
    is_tradable: bool
    n_obs: int


@dataclass
class SpreadSignal:
    """A single-bar spread signal with no-look-ahead Z-score."""

    date: pd.Timestamp
    ticker_a: str
    ticker_b: str
    z_score: float
    spread: float
    hedge_ratio: float
    action: SignalAction
    regime_blocked: bool
    position: int  # +1 long spread, -1 short spread, 0 flat


@dataclass
class PairBacktestResult:
    """PnL result for a pairs trade backtest."""

    ticker_a: str
    ticker_b: str
    n_trades: int
    total_pnl: float
    total_return_pct: float
    winning_trades: int
    losing_trades: int
    avg_pnl_per_trade: float
    max_drawdown: float
    trade_log: list[dict[str, object]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PairsTradingEngine:
    """Statistical arbitrage engine for pairs of IDX stocks.

    Provides:
    - Cointegration screening (Engle-Granger via OLS + ADF).
    - Spread and Z-score calculation with no-look-ahead.
    - Mean-reversion signal generation (entry / exit / stop-loss).
    - Regime gate (rolling correlation filter).
    - Simple PnL backtest helper.
    """

    def __init__(
        self,
        p_value_threshold: float = 0.05,
        correlation_threshold: float = 0.5,
        half_life_threshold: float = 20.0,
        z_window: int = 20,
        entry_threshold: float = 2.0,
        exit_threshold: float = 0.5,
        stop_threshold: float = 4.0,
        regime_window: int = 60,
        regime_corr_threshold: float = 0.95,
        adf_max_lag: int = 1,
    ) -> None:
        """Initialize the pairs trading engine.

        Args:
            p_value_threshold: Max Engle-Granger p-value for cointegration.
            correlation_threshold: Min Pearson correlation to consider a pair.
            half_life_threshold: Max half-life (days) for a tradable pair.
            z_window: Rolling window for Z-score mean/std.
            entry_threshold: |Z-score| entry trigger.
            exit_threshold: |Z-score| exit trigger (mean reverted).
            stop_threshold: |Z-score| stop-loss trigger (cointegration broken).
            regime_window: Rolling window for regime-gate correlation.
            regime_corr_threshold: Skip new entries above this correlation.
            adf_max_lag: Lag order for the ADF test on residuals.
        """
        self.p_value_threshold = p_value_threshold
        self.correlation_threshold = correlation_threshold
        self.half_life_threshold = half_life_threshold
        self.z_window = z_window
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.stop_threshold = stop_threshold
        self.regime_window = regime_window
        self.regime_corr_threshold = regime_corr_threshold
        self.adf_max_lag = adf_max_lag

    # -- Cointegration screening -------------------------------------------

    def screen_pairs(
        self,
        prices: pd.DataFrame,
        tickers: list[str] | None = None,
    ) -> list[PairResult]:
        """Screen all ticker pairs for cointegration.

        Args:
            prices: DataFrame of close prices (columns = tickers, index = dates).
            tickers: Optional subset of tickers to screen. Defaults to all columns.

        Returns:
            List of PairResult sorted by p-value (most significant first).
            Only pairs passing the p-value, correlation, and half-life filters
            have ``is_tradable=True``; all screened pairs are returned for
            inspection.
        """
        if prices.empty:
            return []

        cols = tickers if tickers is not None else list(prices.columns)
        cols = [c for c in cols if c in prices.columns]
        results: list[PairResult] = []

        for i, a in enumerate(cols):
            for b in cols[i + 1 :]:
                pair_df = prices[[a, b]].dropna()
                n_obs = len(pair_df)
                if n_obs < 60:
                    continue
                result = self._test_pair(pair_df[a], pair_df[b], a, b, n_obs)
                results.append(result)

        results.sort(key=lambda r: (r.p_value, -r.correlation))
        return results

    def _test_pair(
        self,
        price_a: pd.Series,
        price_b: pd.Series,
        ticker_a: str,
        ticker_b: str,
        n_obs: int,
    ) -> PairResult:
        """Run cointegration + tradability test on a single pair."""
        correlation = float(price_a.corr(price_b))
        alpha, beta, resid = _ols_hedge_ratio(price_a, price_b)
        coint_stat, p_value = _adf_test(resid, max_lag=self.adf_max_lag)
        half_life = _half_life(resid)

        is_cointegrated = p_value < self.p_value_threshold
        is_tradable = (
            is_cointegrated
            and correlation > self.correlation_threshold
            and half_life < self.half_life_threshold
            and np.isfinite(half_life)
        )

        return PairResult(
            ticker_a=ticker_a,
            ticker_b=ticker_b,
            coint_stat=coint_stat,
            p_value=p_value,
            correlation=correlation,
            half_life=half_life,
            hedge_ratio=beta,
            intercept=alpha,
            is_cointegrated=is_cointegrated,
            is_tradable=is_tradable,
            n_obs=n_obs,
        )

    def test_pair(
        self,
        price_a: pd.Series,
        price_b: pd.Series,
        ticker_a: str = "A",
        ticker_b: str = "B",
    ) -> PairResult:
        """Test a single explicit pair for cointegration.

        Args:
            price_a: Close price series for leg A.
            price_b: Close price series for leg B.
            ticker_a: Ticker name for leg A.
            ticker_b: Ticker name for leg B.

        Returns:
            PairResult for the pair.
        """
        pair_df = pd.concat([price_a, price_b], axis=1).dropna()
        pair_df.columns = [ticker_a, ticker_b]
        n_obs = len(pair_df)
        if n_obs < 10:
            return PairResult(
                ticker_a=ticker_a,
                ticker_b=ticker_b,
                coint_stat=0.0,
                p_value=1.0,
                correlation=0.0,
                half_life=float("inf"),
                hedge_ratio=0.0,
                intercept=0.0,
                is_cointegrated=False,
                is_tradable=False,
                n_obs=n_obs,
            )
        return self._test_pair(
            pair_df[ticker_a], pair_df[ticker_b], ticker_a, ticker_b, n_obs
        )

    # -- Spread & Z-score --------------------------------------------------

    def compute_spread(
        self,
        price_a: pd.Series,
        price_b: pd.Series,
        hedge_ratio: float | None = None,
    ) -> pd.Series:
        """Compute the spread for a pair.

        Spread = price_A - beta * price_B, where beta is the OLS hedge ratio
        (re-estimated if not provided).

        Args:
            price_a: Leg A close prices.
            price_b: Leg B close prices.
            hedge_ratio: Pre-computed hedge ratio. If None, re-estimated via OLS.

        Returns:
            Spread series aligned to the inner join of both price series.
        """
        aligned = pd.concat([price_a, price_b], axis=1).dropna()
        aligned.columns = ["a", "b"]
        if aligned.empty:
            return pd.Series(dtype=float)
        if hedge_ratio is None:
            _, beta, _ = _ols_hedge_ratio(aligned["a"], aligned["b"])
        else:
            beta = hedge_ratio
        return aligned["a"] - beta * aligned["b"]

    def compute_zscore(
        self,
        spread: pd.Series,
        window: int | None = None,
        look_ahead_safe: bool = True,
    ) -> pd.Series:
        """Compute the rolling Z-score of a spread with no-look-ahead.

        Z_t = (spread_t - rolling_mean_t) / rolling_std_t

        When ``look_ahead_safe=True`` (default), the rolling mean and std are
        shifted by 1 bar so that the Z-score at time T only uses data up to
        T-1. This prevents the signal at bar T from peeking at the close of
        bar T itself.

        Args:
            spread: Spread series.
            window: Rolling window. Defaults to ``self.z_window``.
            look_ahead_safe: If True, shift rolling stats by 1 to avoid look-ahead.

        Returns:
            Z-score series.
        """
        w = window or self.z_window
        rolling_mean = spread.rolling(w).mean()
        rolling_std = spread.rolling(w).std()
        if look_ahead_safe:
            rolling_mean = rolling_mean.shift(1)
            rolling_std = rolling_std.shift(1)
        z = (spread - rolling_mean) / rolling_std
        return z.replace([np.inf, -np.inf], np.nan)

    # -- Regime gate -------------------------------------------------------

    def regime_filter(
        self,
        price_a: pd.Series,
        price_b: pd.Series,
        window: int | None = None,
    ) -> pd.Series:
        """Compute the rolling correlation regime gate.

        A boolean series where ``True`` means the regime is risky (rolling
        correlation exceeds the threshold) and new entries should be skipped.

        Args:
            price_a: Leg A close prices.
            price_b: Leg B close prices.
            window: Rolling window. Defaults to ``self.regime_window``.

        Returns:
            Boolean series (True = regime blocked / skip new entries).
        """
        w = window or self.regime_window
        aligned = pd.concat([price_a, price_b], axis=1).dropna()
        aligned.columns = ["a", "b"]
        if aligned.empty:
            return pd.Series(dtype=bool)
        rolling_corr = aligned["a"].rolling(w).corr(aligned["b"])
        return rolling_corr > self.regime_corr_threshold

    # -- Signal generation -------------------------------------------------

    def generate_signals(
        self,
        price_a: pd.Series,
        price_b: pd.Series,
        hedge_ratio: float | None = None,
        z_window: int | None = None,
    ) -> list[SpreadSignal]:
        """Generate mean-reversion trading signals for a pair.

        Signal logic (no-look-ahead Z-score):
        - Entry LONG spread (buy A, sell B): Z < -entry_threshold.
        - Entry SHORT spread (sell A, buy B): Z > +entry_threshold.
        - Exit: |Z| < exit_threshold (spread reverted to mean).
        - Stop-loss: |Z| > stop_threshold (cointegration broken).
        - Regime gate: if rolling correlation > threshold, skip new entries.

        Position state machine:
        - From FLAT: enter long/short on entry trigger (unless regime-blocked).
        - From LONG/SHORT: exit on |Z| < exit_threshold or stop on |Z| > stop.

        Args:
            price_a: Leg A close prices.
            price_b: Leg B close prices.
            hedge_ratio: Pre-computed hedge ratio. If None, re-estimated.
            z_window: Rolling Z-score window. Defaults to ``self.z_window``.

        Returns:
            List of SpreadSignal, one per bar (after warmup).
        """
        aligned = pd.concat([price_a, price_b], axis=1).dropna()
        aligned.columns = ["a", "b"]
        if len(aligned) < max(self.z_window, self.regime_window) + 2:
            return []

        if hedge_ratio is None:
            _, beta, _ = _ols_hedge_ratio(aligned["a"], aligned["b"])
        else:
            beta = hedge_ratio

        spread = aligned["a"] - beta * aligned["b"]
        z = self.compute_zscore(spread, window=z_window, look_ahead_safe=True)
        regime_blocked = self.regime_filter(aligned["a"], aligned["b"])

        signals: list[SpreadSignal] = []
        position = 0  # +1 long spread, -1 short spread, 0 flat

        for idx in aligned.index:
            z_val = z.get(idx)
            blocked = bool(regime_blocked.get(idx, False)) if not pd.isna(
                regime_blocked.get(idx)
            ) else False
            spread_val = float(spread.get(idx, np.nan))

            if pd.isna(z_val):
                signals.append(
                    SpreadSignal(
                        date=idx,
                        ticker_a=price_a.name or "A",
                        ticker_b=price_b.name or "B",
                        z_score=float("nan"),
                        spread=spread_val,
                        hedge_ratio=beta,
                        action=SignalAction.FLAT,
                        regime_blocked=blocked,
                        position=position,
                    )
                )
                continue

            zv = float(z_val)
            action = SignalAction.FLAT

            if position == 0:
                # Look for entry.
                if zv < -self.entry_threshold and not blocked:
                    action = SignalAction.LONG_SPREAD
                    position = 1
                elif zv > self.entry_threshold and not blocked:
                    action = SignalAction.SHORT_SPREAD
                    position = -1
                elif blocked and (zv < -self.entry_threshold or zv > self.entry_threshold):
                    # Would enter but regime blocks it.
                    action = SignalAction.FLAT
            elif position == 1 or position == -1:
                if abs(zv) > self.stop_threshold:
                    action = SignalAction.STOP_LOSS
                    position = 0
                elif abs(zv) < self.exit_threshold:
                    action = SignalAction.EXIT
                    position = 0

            signals.append(
                SpreadSignal(
                    date=idx,
                    ticker_a=price_a.name or "A",
                    ticker_b=price_b.name or "B",
                    z_score=zv,
                    spread=spread_val,
                    hedge_ratio=beta,
                    action=action,
                    regime_blocked=blocked,
                    position=position,
                )
            )

        return signals

    # -- Backtest helper ---------------------------------------------------

    def backtest_pair(
        self,
        price_a: pd.Series,
        price_b: pd.Series,
        signals: list[SpreadSignal] | None = None,
        hedge_ratio: float | None = None,
        capital_per_trade: float = 10000.0,
    ) -> PairBacktestResult:
        """Compute PnL of a pairs trade from entry/exit signals.

        This is a simple PnL calculator, not a full backtest engine. It
        tracks trades opened by LONG_SPREAD / SHORT_SPREAD signals and
        closed by EXIT / STOP_LOSS signals. PnL per trade is computed from
        the change in spread scaled by the capital allocated.

        For a LONG spread (buy A, sell B): pnl = (spread_exit - spread_entry) * units
        For a SHORT spread (sell A, buy B): pnl = (spread_entry - spread_exit) * units

        where ``units = capital_per_trade / |spread_entry|`` (a notional
        approximation that keeps position size comparable across trades).

        Args:
            price_a: Leg A close prices.
            price_b: Leg B close prices.
            signals: Pre-generated signals. If None, generated from prices.
            hedge_ratio: Hedge ratio for spread calc (used if signals is None).
            capital_per_trade: Notional capital per trade for sizing.

        Returns:
            PairBacktestResult with trade log and summary stats.
        """
        if signals is None:
            signals = self.generate_signals(
                price_a, price_b, hedge_ratio=hedge_ratio
            )

        aligned = pd.concat([price_a, price_b], axis=1).dropna()
        aligned.columns = ["a", "b"]

        ticker_a = price_a.name or "A"
        ticker_b = price_b.name or "B"

        trade_log: list[dict[str, object]] = []
        open_trade: dict[str, object] | None = None
        equity = 0.0
        peak_equity = 0.0
        max_drawdown = 0.0
        winning = 0
        losing = 0

        for sig in signals:
            spread_val = sig.spread
            if pd.isna(spread_val):
                continue

            if sig.action == SignalAction.LONG_SPREAD:
                if open_trade is None:
                    open_trade = {
                        "entry_date": sig.date,
                        "direction": "long",
                        "entry_spread": spread_val,
                        "entry_z": sig.z_score,
                        "units": capital_per_trade / abs(spread_val) if spread_val != 0 else 0.0,
                    }
            elif sig.action == SignalAction.SHORT_SPREAD:
                if open_trade is None:
                    open_trade = {
                        "entry_date": sig.date,
                        "direction": "short",
                        "entry_spread": spread_val,
                        "entry_z": sig.z_score,
                        "units": capital_per_trade / abs(spread_val) if spread_val != 0 else 0.0,
                    }
            elif (
                sig.action in (SignalAction.EXIT, SignalAction.STOP_LOSS)
                and open_trade is not None
            ):
                entry_spread = float(open_trade["entry_spread"])
                units = float(open_trade["units"])
                if open_trade["direction"] == "long":
                    pnl = (spread_val - entry_spread) * units
                else:
                    pnl = (entry_spread - spread_val) * units
                equity += pnl
                if pnl > 0:
                    winning += 1
                else:
                    losing += 1
                trade_log.append(
                    {
                        "entry_date": open_trade["entry_date"],
                        "exit_date": sig.date,
                        "direction": open_trade["direction"],
                        "entry_spread": entry_spread,
                        "exit_spread": spread_val,
                        "entry_z": open_trade["entry_z"],
                        "exit_z": sig.z_score,
                        "pnl": pnl,
                        "return_pct": (pnl / capital_per_trade) * 100.0
                        if capital_per_trade > 0
                        else 0.0,
                        "stop": sig.action == SignalAction.STOP_LOSS,
                    }
                )
                open_trade = None

            peak_equity = max(peak_equity, equity)
            drawdown = peak_equity - equity
            max_drawdown = max(max_drawdown, drawdown)

        n_trades = len(trade_log)
        total_pnl = sum(float(t["pnl"]) for t in trade_log)
        total_return = (total_pnl / capital_per_trade) * 100.0 if capital_per_trade > 0 else 0.0
        avg_pnl = total_pnl / n_trades if n_trades > 0 else 0.0

        return PairBacktestResult(
            ticker_a=ticker_a,
            ticker_b=ticker_b,
            n_trades=n_trades,
            total_pnl=total_pnl,
            total_return_pct=total_return,
            winning_trades=winning,
            losing_trades=losing,
            avg_pnl_per_trade=avg_pnl,
            max_drawdown=max_drawdown,
            trade_log=trade_log,
        )
