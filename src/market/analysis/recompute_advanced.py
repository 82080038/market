"""Advanced recompute functions — extracted from recompute_graph.py inline blocks.

These 9 functions were previously implemented as inline if-elif blocks inside
``RecomputeGraph.trigger_recompute()``. They are now standalone functions with
the standard signature ``(session, dry_run, progress_cb, incremental) -> int``
so they can be tested independently and registered in FUNCTION_MAP directly.

Functions:
    recompute_holiday_effects          → HolidayEffectAnalyzer
    recompute_instrument_profiles      → InstrumentBehaviorProfiler
    recompute_cross_market_coefficients → CrossMarketCoefficientEngine
    recompute_dcc_garch                → DCCGarchEngine
    recompute_seasonal_patterns        → inline SQL (monthly returns)
    recompute_macro_correlation        → macro_correlation.full_analysis
    recompute_causal_relationships     → CrossMarketCoefficientEngine.update_all
    recompute_satellite_correlation    → not yet implemented (phantom, returns 0)
    recompute_astronacci_cycles        → AstronacciEngine

Usage::

    from market.analysis.recompute_advanced import recompute_holiday_effects
    count = recompute_holiday_effects(session)
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ProgressCb = "callable[[str, int, int, str], None] | None"


# ── 1. Holiday effects ─────────────────────────────────────────────


def recompute_holiday_effects(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Recompute holiday effects via HolidayEffectAnalyzer."""
    from market.analysis.holiday_effect import HolidayEffectAnalyzer

    analyzer = HolidayEffectAnalyzer(lookback_years=10)
    summary = analyzer.analyze_all()
    count = summary.get("holiday_effects", 0)
    logger.info("holiday_effects: %d rows", count)
    return count


# ── 2. Instrument profiles ──────────────────────────────────────────


def recompute_instrument_profiles(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Recompute instrument behavior profiles via InstrumentBehaviorProfiler."""
    from market.analysis.instrument_profiler import InstrumentBehaviorProfiler

    profiler = InstrumentBehaviorProfiler()
    result = profiler.profile_all_instruments()
    count = sum(result.values()) if isinstance(result, dict) else 0
    logger.info("instrument_profiles: %d rows", count)
    return count


# ── 3. Cross-market coefficients ────────────────────────────────────


def recompute_cross_market_coefficients(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Recompute cross-market coefficients via CrossMarketCoefficientEngine."""
    from market.analysis.cross_market_coefficients import CrossMarketCoefficientEngine

    engine = CrossMarketCoefficientEngine()
    result = engine.update_all()
    count = sum(result.values()) if isinstance(result, dict) else 0
    logger.info("cross_market_coefficients: %d rows", count)
    return count


# ── 4. DCC-GARCH ────────────────────────────────────────────────────


def recompute_dcc_garch(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Recompute DCC-GARCH correlations for top tickers by volume.

    Selects top 15 tickers by volume, loads returns, runs DCC-GARCH,
    stores pairwise correlations to ``dcc_garch_results``.
    """
    from market.analysis.dcc_garch import DCCGarchEngine
    import pandas as _pd

    # Get top tickers by volume
    tickers = session.execute(
        text(
            "SELECT ticker FROM stock_prices "
            "WHERE timeframe = '1d' AND ticker LIKE '%.JK' "
            "GROUP BY ticker ORDER BY SUM(volume) DESC LIMIT 15"
        )
    ).scalars().all()

    if len(tickers) < 3:
        logger.info("DCC-GARCH: need >=3 tickers, got %d", len(tickers))
        return 0

    # Load returns
    returns_dict: dict[str, _pd.Series] = {}
    for tk in tickers:
        rows = session.execute(
            text(
                "SELECT timestamp, close FROM stock_prices "
                "WHERE ticker = :t AND timeframe = '1d' "
                "ORDER BY timestamp"
            ),
            {"t": tk},
        ).all()
        if len(rows) < 60:
            continue
        s = _pd.Series(
            [float(r[1]) for r in rows],
            index=_pd.to_datetime([r[0] for r in rows]),
        )
        returns_dict[tk] = s.pct_change().dropna()

    if len(returns_dict) < 3:
        logger.info("DCC-GARCH: insufficient valid tickers (%d)", len(returns_dict))
        return 0

    returns_df = _pd.DataFrame(returns_dict).dropna()
    engine = DCCGarchEngine(use_gpu=True, max_assets=len(returns_df.columns))
    result = engine.compute(returns=returns_df, n_ahead=5)

    # Store to dcc_garch_results
    count = 0
    for i, t1 in enumerate(returns_df.columns):
        for j, t2 in enumerate(returns_df.columns):
            if i >= j:
                continue
            corr = float(result.correlation_matrix.iloc[i, j]) if result.correlation_matrix is not None else 0.0
            session.execute(
                text(
                    "INSERT INTO dcc_garch_results "
                    "(ticker_a, ticker_b, correlation, forecast_horizon, computed_at) "
                    "VALUES (:a, :b, :c, :h, NOW()) "
                    "ON CONFLICT (ticker_a, ticker_b, forecast_horizon) DO UPDATE SET "
                    "correlation=EXCLUDED.correlation, computed_at=NOW()"
                ),
                {"a": t1, "b": t2, "c": corr, "h": 5},
            )
            count += 1
    session.commit()
    logger.info("dcc_garch: %d rows", count)
    return count


# ── 5. Seasonal patterns ────────────────────────────────────────────


def recompute_seasonal_patterns(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Recompute seasonal patterns from stock_prices monthly returns.

    For each ticker (limited to 200 for speed), computes monthly average
    returns and stores seasonal score to ``seasonal_patterns``.
    """
    import pandas as _pd

    tickers = session.execute(
        text("SELECT DISTINCT ticker FROM stock_prices ORDER BY ticker")
    ).scalars().all()

    count = 0
    for tk in tickers[:200]:  # limit to avoid long runtime
        rows = session.execute(
            text(
                "SELECT date_trunc('month', timestamp)::date as month, "
                "AVG(close) as avg_close "
                "FROM stock_prices WHERE ticker = :t "
                "GROUP BY 1 ORDER BY 1"
            ),
            {"t": tk},
        ).all()
        if len(rows) < 24:
            continue
        monthly = _pd.DataFrame(rows, columns=["month", "avg_close"])
        monthly["ret"] = monthly["avg_close"].pct_change()
        for month in range(1, 13):
            month_data = monthly[monthly["month"].dt.month == month]["ret"].dropna()
            if len(month_data) < 3:
                continue
            avg_ret = float(month_data.mean())
            std_ret = float(month_data.std())
            win_rate = float((month_data > 0).mean())
            score = max(0.0, min(100.0, 50.0 + avg_ret * 100))
            session.execute(
                text(
                    "INSERT INTO seasonal_patterns "
                    "(ticker, month, avg_return, std_return, win_rate, n_years, seasonal_score, pattern_type, computed_at) "
                    "VALUES (:t, :m, :ar, :sr, :wr, :n, :sc, :pt, NOW()) "
                    "ON CONFLICT (ticker, month) DO UPDATE SET "
                    "avg_return=EXCLUDED.avg_return, std_return=EXCLUDED.std_return, "
                    "win_rate=EXCLUDED.win_rate, seasonal_score=EXCLUDED.seasonal_score, "
                    "computed_at=NOW()"
                ),
                {
                    "t": tk, "m": month, "ar": avg_ret, "sr": std_ret,
                    "wr": win_rate, "n": len(month_data),
                    "sc": score, "pt": "bullish" if avg_ret > 0 else "bearish",
                },
            )
            count += 1
    session.commit()
    logger.info("seasonal_patterns: %d rows", count)
    return count


# ── 6. Macro correlation ────────────────────────────────────────────


def recompute_macro_correlation(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Recompute macro correlation for top indicators vs IHSG."""
    from market.analysis.macro_correlation import full_analysis

    indicators = session.execute(
        text("SELECT DISTINCT indicator_code FROM macroeconomic_indicators WHERE indicator_code IS NOT NULL")
    ).scalars().all()

    count = 0
    for ind_code in indicators[:5]:
        full_analysis(ind_code, "^JKSE")
        count += 1
    logger.info("macro_correlation: %d indicators analyzed", count)
    return count


# ── 7. Causal relationships ─────────────────────────────────────────


def recompute_causal_relationships(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Recompute causal relationships via CrossMarketCoefficientEngine."""
    from market.analysis.cross_market_coefficients import CrossMarketCoefficientEngine

    engine = CrossMarketCoefficientEngine()
    result = engine.update_all()
    count = sum(result.values()) if isinstance(result, dict) else 0
    logger.info("causal_relationships: %d rows", count)
    return count


# ── 8. Satellite correlation (phantom — not yet implemented) ────────


def recompute_satellite_correlation(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Satellite correlation recompute — not yet implemented.

    Placeholder function. Returns 0. Will be implemented when
    satellite_observations data pipeline is complete.
    """
    logger.info("satellite_correlation: not yet implemented, skipping")
    return 0


# ── 9. Astronacci cycles ────────────────────────────────────────────


def recompute_astronacci_cycles(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Recompute astronacci time cycles for the past year."""
    from market.analysis.astronacci import AstronacciEngine

    engine = AstronacciEngine()
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=365)
    cycles = engine.compute(start_dt, end_dt)
    count = len(cycles)
    logger.info("astronacci_cycles: %d cycles", count)
    return count
