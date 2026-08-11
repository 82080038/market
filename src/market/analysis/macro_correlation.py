"""Macro ↔ Stock correlation & causality analysis (Dimensi 1 "WHY").

This module analyses the statistical relationship between macroeconomic
indicators (stored in ``macroeconomic_indicators``) and stock price movements
(stored in ``stock_prices``). Three complementary approaches are provided:

1. **PostgreSQL-native lagged CORR()** — ``lagged_corr_sql`` computes the
   Pearson correlation between an indicator's daily pct-change and a ticker's
   daily pct-change at a range of lags, entirely inside the database.

2. **Pandas event study** — ``event_study`` identifies macro "shock" events
   (e.g. VIX jumps > 20% in one day) and measures the ticker's return over a
   configurable forward window (e.g. 24-48 hours / 1-2 trading days).

3. **Granger causality** — ``granger_causality_test`` runs the Granger-cause
   F-test to check whether the indicator's lagged values help predict the
   ticker's returns beyond the ticker's own history.

All analysis uses UTC-anchored timestamps from the database. Stock prices are
daily (``timeframe='1d'``); macro indicators are daily (yfinance) or monthly
(FRED). For lagged correlation we align on the calendar date (UTC date part).

References:
  - Granger, C.W.J. (1969). "Investigating Causal Relations by Econometric
    Models and Cross-Spectral Methods." Econometrica, 37(3), 424-438.
  - López de Prado, M. (2018). "Advances in Financial Machine Learning," Ch. 6
    (Cross-Validation in Finance) — caution on correlated features.
  - Sumber data: yfinance (IDR=X, ^VIX, GC=F, BZ=F), FRED (FEDFUNDS, CPIAUCSL).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import text

from market.db.engine import get_sessionmaker

logger = logging.getLogger(__name__)


@dataclass
class LaggedCorrResult:
    """Result of a lagged correlation analysis."""

    indicator_code: str
    ticker: str
    lag_days: int
    pearson_r: float
    p_value: float
    n_observations: int


@dataclass
class EventStudyResult:
    """Result of an event-study shock analysis."""

    indicator_code: str
    ticker: str
    shock_threshold_pct: float
    n_events: int
    mean_forward_return_pct: float
    median_forward_return_pct: float
    std_forward_return_pct: float
    min_forward_return_pct: float
    max_forward_return_pct: float
    win_rate_pct: float  # % of events where ticker moved in expected direction
    t_stat: float
    p_value: float
    event_dates: list[datetime] = field(default_factory=list)
    forward_returns: list[float] = field(default_factory=list)


@dataclass
class GrangerResult:
    """Result of a Granger causality test."""

    indicator_code: str
    ticker: str
    max_lag: int
    ssr_ftest: float
    p_value: float
    is_significant: bool  # p < 0.05


# ──────────────────────────────────────────────────────────────────────────────
# 1. PostgreSQL-native lagged CORR()
# ──────────────────────────────────────────────────────────────────────────────

def lagged_corr_sql(
    indicator_code: str,
    ticker: str,
    max_lag_days: int = 5,
    timeframe: str = "1d",
) -> list[LaggedCorrResult]:
    """Compute lagged Pearson correlation between macro indicator and stock.

    Uses PostgreSQL ``CORR()`` aggregate. For each lag L in ``0..max_lag_days``,
    computes CORR(indicator_pct_change_t, stock_pct_change_{t+L}).

    A positive lag L means: indicator change today vs stock change L days later
    (indicator leads stock). A negative lag means stock leads indicator.

    Args:
        indicator_code: e.g. 'VIX_INDEX', 'USD_IDR'.
        ticker: e.g. 'BBCA.JK'.
        max_lag_days: maximum forward lag to test.
        timeframe: stock_prices timeframe to query.

    Returns:
        List of :class:`LaggedCorrResult` sorted by lag_days.
    """
    session = get_sessionmaker()()
    results: list[LaggedCorrResult] = []
    try:
        for lag in range(-max_lag_days, max_lag_days + 1):
            sign = "+" if lag >= 0 else ""
            # Align on UTC date; compute daily pct-change for both series,
            # then shift stock by `lag` days and compute CORR.
            sql = text(f"""
                WITH macro_daily AS (
                    SELECT (recorded_at AT TIME ZONE 'UTC')::date AS d,
                           value,
                           value / NULLIF(LAG(value) OVER (
                               PARTITION BY indicator_code ORDER BY recorded_at), 0) - 1 AS pct_chg
                    FROM macroeconomic_indicators
                    WHERE indicator_code = :code
                ),
                stock_daily AS (
                    SELECT (timestamp AT TIME ZONE 'UTC')::date AS d,
                           close,
                           close / NULLIF(LAG(close) OVER (
                               PARTITION BY ticker, timeframe ORDER BY timestamp), 0) - 1 AS pct_chg
                    FROM stock_prices
                    WHERE ticker = :ticker AND timeframe = :tf
                )
                SELECT CORR(m.pct_chg, s.pct_chg) AS r,
                       COUNT(*) AS n
                FROM macro_daily m
                JOIN stock_daily s
                  ON s.d = m.d + INTERVAL '{sign}{abs(lag)} days'
                WHERE m.pct_chg IS NOT NULL AND s.pct_chg IS NOT NULL
            """)
            row = session.execute(sql, {
                "code": indicator_code, "ticker": ticker, "tf": timeframe,
            }).fetchone()
            if row and row.n and row.n >= 10 and row.r is not None:
                # p-value from t-distribution: t = r*sqrt((n-2)/(1-r^2))
                n = int(row.n)
                r = float(row.r)
                t_stat = r * np.sqrt((n - 2) / max(1e-12, 1 - r ** 2))
                p_val = 2 * stats.t.sf(abs(t_stat), df=n - 2)
                results.append(LaggedCorrResult(
                    indicator_code=indicator_code, ticker=ticker,
                    lag_days=lag, pearson_r=r, p_value=p_val, n_observations=n,
                ))
    finally:
        session.close()
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 2. Pandas event study — macro shock → forward stock return
# ──────────────────────────────────────────────────────────────────────────────

def _load_macro_series(session, indicator_code: str) -> pd.DataFrame:
    """Load a macro indicator as a daily DataFrame indexed by UTC date."""
    rows = session.execute(text("""
        SELECT (recorded_at AT TIME ZONE 'UTC')::date AS d, value
        FROM macroeconomic_indicators
        WHERE indicator_code = :code
        ORDER BY recorded_at
    """), {"code": indicator_code}).fetchall()
    if not rows:
        return pd.DataFrame(columns=["value"])
    df = pd.DataFrame(rows, columns=["d", "value"])
    df["value"] = df["value"].astype(float)
    df["d"] = pd.to_datetime(df["d"], utc=True)
    return df.set_index("d")


def _load_stock_series(session, ticker: str, timeframe: str = "1d") -> pd.DataFrame:
    """Load stock daily closes as a DataFrame indexed by UTC date."""
    rows = session.execute(text("""
        SELECT (timestamp AT TIME ZONE 'UTC')::date AS d, close
        FROM stock_prices
        WHERE ticker = :ticker AND timeframe = :tf
        ORDER BY timestamp
    """), {"ticker": ticker, "tf": timeframe}).fetchall()
    if not rows:
        return pd.DataFrame(columns=["close"])
    df = pd.DataFrame(rows, columns=["d", "close"])
    df["close"] = df["close"].astype(float)
    df["d"] = pd.to_datetime(df["d"], utc=True)
    return df.set_index("d")


def event_study(
    indicator_code: str,
    ticker: str,
    shock_threshold_pct: float = 20.0,
    forward_window_days: int = 2,
    expected_direction: str = "NEGATIVE",
    timeframe: str = "1d",
) -> EventStudyResult:
    """Event study: when indicator jumps > threshold, what's the ticker return?

    Example (the user's question):
        event_study('VIX_INDEX', 'BBCA.JK', shock_threshold_pct=20.0,
                    forward_window_days=2, expected_direction='NEGATIVE')
        → "When VIX jumps > 20%, what's BBCA.JK return over next 2 trading days?"

    Args:
        indicator_code: macro indicator to monitor for shocks.
        ticker: stock ticker to measure forward return.
        shock_threshold_pct: daily pct-change threshold that defines a "shock"
            (e.g. 20.0 = 20% jump). Uses absolute value.
        forward_window_days: number of trading days after the shock to measure
            the ticker's cumulative return (2 ≈ 24-48h for daily bars).
        expected_direction: 'NEGATIVE' (shock → stock falls) or 'POSITIVE'.
        timeframe: stock_prices timeframe.

    Returns:
        :class:`EventStudyResult` with summary statistics.
    """
    session = get_sessionmaker()()
    try:
        macro_df = _load_macro_series(session, indicator_code)
        stock_df = _load_stock_series(session, ticker, timeframe)
    finally:
        session.close()

    if macro_df.empty or stock_df.empty:
        raise ValueError(
            f"No data for indicator={indicator_code} or ticker={ticker}")

    macro_df["pct_chg"] = macro_df["value"].pct_change()
    stock_df["fwd_return"] = stock_df["close"].pct_change(
        periods=forward_window_days).shift(-forward_window_days)

    # Identify shock events (|daily change| >= threshold)
    threshold = shock_threshold_pct / 100.0
    shocks = macro_df[macro_df["pct_chg"].abs() >= threshold].copy()
    # For directional shocks (e.g. VIX jump UP), keep only positive changes
    shocks = shocks[shocks["pct_chg"] >= threshold]

    event_dates: list[datetime] = []
    forward_returns: list[float] = []
    for shock_date, _row in shocks.iterrows():
        # Find the stock return measured from the shock date forward
        # Align: use the stock close on/after the shock date
        future = stock_df.loc[stock_df.index >= shock_date]
        if len(future) < forward_window_days + 1:
            continue
        entry = future["close"].iloc[0]
        exit_ = future["close"].iloc[forward_window_days]
        if pd.isna(entry) or pd.isna(exit_) or entry == 0:
            continue
        ret = (exit_ / entry - 1) * 100.0  # percent
        event_dates.append(shock_date.to_pydatetime())
        forward_returns.append(float(ret))

    n = len(forward_returns)
    if n == 0:
        return EventStudyResult(
            indicator_code=indicator_code, ticker=ticker,
            shock_threshold_pct=shock_threshold_pct, n_events=0,
            mean_forward_return_pct=float("nan"),
            median_forward_return_pct=float("nan"),
            std_forward_return_pct=float("nan"),
            min_forward_return_pct=float("nan"),
            max_forward_return_pct=float("nan"),
            win_rate_pct=float("nan"), t_stat=float("nan"),
            p_value=float("nan"))

    arr = np.array(forward_returns)
    expected_positive = expected_direction.upper() == "POSITIVE"
    wins = sum(1 for r in forward_returns if (r > 0) == expected_positive)
    mean_r = float(np.mean(arr))
    std_r = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    # One-sample t-test: is mean return significantly different from 0?
    if n > 1 and std_r > 0:
        t_stat = float(stats.ttest_1samp(arr, 0.0).statistic)
        p_val = float(stats.ttest_1samp(arr, 0.0).pvalue)
    else:
        t_stat, p_val = float("nan"), float("nan")

    return EventStudyResult(
        indicator_code=indicator_code, ticker=ticker,
        shock_threshold_pct=shock_threshold_pct, n_events=n,
        mean_forward_return_pct=mean_r,
        median_forward_return_pct=float(np.median(arr)),
        std_forward_return_pct=std_r,
        min_forward_return_pct=float(np.min(arr)),
        max_forward_return_pct=float(np.max(arr)),
        win_rate_pct=wins / n * 100.0, t_stat=t_stat, p_value=p_val,
        event_dates=event_dates, forward_returns=forward_returns)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Granger causality test
# ──────────────────────────────────────────────────────────────────────────────

def granger_causality_test(
    indicator_code: str,
    ticker: str,
    max_lag: int = 5,
    timeframe: str = "1d",
) -> GrangerResult:
    """Test whether the macro indicator Granger-causes the stock's returns.

    Uses ``statsmodels.tsa.stattools.grangercausalitytests``. The null
    hypothesis is that the indicator does NOT Granger-cause the stock return.
    A p-value < 0.05 rejects the null → indicator helps predict stock.

    Args:
        indicator_code: macro indicator (cause candidate).
        ticker: stock ticker (effect candidate).
        max_lag: maximum lag order to test.
        timeframe: stock_prices timeframe.

    Returns:
        :class:`GrangerResult` with the SSR F-test p-value at ``max_lag``.
    """
    from statsmodels.tsa.stattools import grangercausalitytests

    session = get_sessionmaker()()
    try:
        macro_df = _load_macro_series(session, indicator_code)
        stock_df = _load_stock_series(session, ticker, timeframe)
    finally:
        session.close()

    if macro_df.empty or stock_df.empty:
        raise ValueError(
            f"No data for indicator={indicator_code} or ticker={ticker}")

    macro_df["pct_chg"] = macro_df["value"].pct_change()
    stock_df["pct_chg"] = stock_df["close"].pct_change()

    # Merge on date, drop NaN
    merged = macro_df[["pct_chg"]].join(
        stock_df[["pct_chg"]], lsuffix="_macro", rsuffix="_stock", how="inner"
    ).dropna()
    merged = merged.rename(columns={
        "pct_chg_macro": "macro", "pct_chg_stock": "stock"})

    if len(merged) < max_lag + 5:
        raise ValueError(
            f"Insufficient overlapping observations ({len(merged)}) "
            f"for max_lag={max_lag}")

    # grangercausalitytests expects [target, cause] columns
    data = merged[["stock", "macro"]].values
    result = grangercausalitytests(data, maxlag=max_lag, verbose=False)
    # SSR F-test at the max lag: returns (statistic, pvalue, df_denom, df_num)
    f_stat, p_val = result[max_lag][0]["ssr_ftest"][0], result[max_lag][0]["ssr_ftest"][1]
    p_val_f = float(p_val)
    return GrangerResult(
        indicator_code=indicator_code, ticker=ticker, max_lag=max_lag,
        ssr_ftest=float(f_stat), p_value=p_val_f,
        is_significant=p_val_f < 0.05)


# ──────────────────────────────────────────────────────────────────────────────
# Convenience: full analysis report for one indicator ↔ one ticker
# ──────────────────────────────────────────────────────────────────────────────

def full_analysis(
    indicator_code: str,
    ticker: str,
    shock_threshold_pct: float = 20.0,
    forward_window_days: int = 2,
    expected_direction: str = "NEGATIVE",
    max_lag: int = 5,
) -> dict[str, Any]:
    """Run all three analyses and return a combined report dict."""
    lagged = lagged_corr_sql(indicator_code, ticker, max_lag_days=max_lag)
    event = event_study(
        indicator_code, ticker, shock_threshold_pct, forward_window_days,
        expected_direction)
    try:
        granger = granger_causality_test(indicator_code, ticker, max_lag=max_lag)
    except Exception as exc:
        logger.warning("Granger test failed: %s", exc)
        granger = None

    return {
        "indicator_code": indicator_code,
        "ticker": ticker,
        "lagged_correlation": [
            {"lag_days": r.lag_days, "pearson_r": round(r.pearson_r, 4),
             "p_value": round(r.p_value, 4), "n": r.n_observations}
            for r in lagged
        ],
        "event_study": {
            "shock_threshold_pct": event.shock_threshold_pct,
            "n_events": event.n_events,
            "mean_forward_return_pct": round(event.mean_forward_return_pct, 3),
            "median_forward_return_pct": round(event.median_forward_return_pct, 3),
            "std_forward_return_pct": round(event.std_forward_return_pct, 3),
            "min_forward_return_pct": round(event.min_forward_return_pct, 3),
            "max_forward_return_pct": round(event.max_forward_return_pct, 3),
            "win_rate_pct": round(event.win_rate_pct, 2),
            "t_stat": round(event.t_stat, 3) if event.t_stat == event.t_stat else None,
            "p_value": round(event.p_value, 4) if event.p_value == event.p_value else None,
            "event_dates": [d.isoformat() for d in event.event_dates],
        },
        "granger_causality": {
            "max_lag": granger.max_lag,
            "ssr_ftest": round(granger.ssr_ftest, 4),
            "p_value": round(granger.p_value, 4),
            "is_significant": granger.is_significant,
        } if granger else None,
    }
