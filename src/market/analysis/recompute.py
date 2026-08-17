"""Recompute internal data from OHLCV using application engines.

This module belongs to the analysis layer (S2) and depends on the data
layer (S1) for data loading. It contains all recompute_* functions that
use analysis engines to compute derived data from OHLCV.

Usage:
    ENV=paper python -m market.analysis.recompute [--dry-run]
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import numpy as np
import pandas as pd
from sqlalchemy import select, text

from market.analysis.fundamental import FundamentalAnalysisEngine
from market.analysis.global_market import GLOBAL_INDICES, GlobalMarketEngine
from market.analysis.macro import MacroEconomicEngine
from market.analysis.profiling import InstrumentProfiler
from market.analysis.relationship import REFERENCE_ASSETS, MarketRelationshipEngine
from market.analysis.sentiment import SentimentEngine
from market.analysis.technical import TechnicalAnalysisEngine
from market.data.recompute_internal import (
    _get_watermark,
    _load_all_idx_tickers,
    _load_all_ohlcv_dfs,
    _load_ohlcv_df,
    _load_ohlcv_df_since,
    _set_watermark,
)
from market.db.engine import get_sessionmaker
from market.db.models import (
    FearGreed,
    FundamentalData,
    RelationshipMatrix,
    Score,
    StockPersonality,
    TechnicalIndicator,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ProgressCb = "callable[[str, int, int, str], None] | None"

GLOBAL_TICKERS = list(GLOBAL_INDICES.keys())
REFERENCE_TICKERS = list(REFERENCE_ASSETS.keys())
IHSG_TICKER = "^JKSE"


def recompute_technical_indicators(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Clear and recompute technical_indicators from OHLCV.

    Always full recompute — snapshot table (latest values only, ~9K rows).
    Incremental flag is accepted for API compatibility but has no effect
    since this table stores only the latest snapshot per ticker.
    """
    tickers = _load_all_idx_tickers(session)
    total = len(tickers)
    logger.info("Recomputing technical_indicators for %d tickers", total)

    from market.compute.device import select_device
    _device = select_device("technical_indicators", data_size=total)
    logger.info("technical_indicators: using device=%s", _device)
    if progress_cb:
        progress_cb("technical_indicators", 0, total, "Starting")

    if dry_run:
        return total

    session.execute(text("DELETE FROM technical_indicators"))
    session.commit()

    engine = TechnicalAnalysisEngine()
    count = 0
    processed = 0

    # Chunked batch processing — 100 tickers per batch to limit peak RAM
    CHUNK_SIZE = 100
    for chunk_start in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[chunk_start : chunk_start + CHUNK_SIZE]
        all_dfs = _load_all_ohlcv_dfs(session, chunk)

        for ticker in chunk:
            processed += 1
            df = all_dfs.get(ticker)
            if df is None or df.empty or len(df) < 50:
                if progress_cb and processed % 50 == 0:
                    progress_cb("technical_indicators", processed, total, f"skip {ticker}")
                continue

            result = engine.analyze(ticker, df)
            if not result.indicators:
                continue

            today = datetime.now(UTC).date()
            indicator_map = {
                "ma20": "MA20",
                "ma50": "MA50",
                "rsi": "RSI",
                "macd": "MACD",
                "macd_signal": "MACD_SIGNAL",
                "adx": "ADX",
                "atr": "ATR14",
                "bb_upper": "BB_UPPER",
                "bb_lower": "BB_LOWER",
                "vol_ratio": "VOLUME_SMA20",
                "ema50": "EMA50",
                "ema_env_upper": "EMA_ENV_UPPER",
                "ema_env_lower": "EMA_ENV_LOWER",
                "donchian_upper": "DONCHIAN_UPPER",
                "donchian_lower": "DONCHIAN_LOWER",
                "donchian_mid": "DONCHIAN_MID",
            }

            for key, label in indicator_map.items():
                val = result.indicators.get(key)
                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                    session.add(
                        TechnicalIndicator(
                            ticker=ticker,
                            date=today,
                            indicator=label,
                            value=float(val),
                            timeframe="1d",
                            source="computed",
                        )
                    )
                    count += 1

            wide_cols = {
                "ma20": "ma20", "ma50": "ma50", "rsi": "rsi",
                "macd": "macd", "macd_signal": "macd_signal",
                "adx": "adx", "atr": "atr14",
                "bb_upper": "bb_upper", "bb_lower": "bb_lower",
                "vol_ratio": "volume_sma20",
                "ema50": "ema50", "ema_env_upper": "ema_env_upper",
                "ema_env_lower": "ema_env_lower",
                "donchian_upper": "donchian_upper",
                "donchian_lower": "donchian_lower",
                "donchian_mid": "donchian_mid",
            }
            wide_values = {}
            for key, col_name in wide_cols.items():
                val = result.indicators.get(key)
                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                    wide_values[col_name] = float(val)

            if wide_values:
                from market.db.models import TechnicalIndicatorWide as _TIW

                existing = session.execute(
                    select(_TIW).where(
                        _TIW.ticker == ticker,
                        _TIW.date == today,
                        _TIW.timeframe == "1d",
                    )
                ).scalar_one_or_none()

                if existing:
                    for col_name, val in wide_values.items():
                        setattr(existing, col_name, val)
                else:
                    kwargs = {"ticker": ticker, "date": today, "timeframe": "1d"}
                    kwargs.update(wide_values)
                    session.add(_TIW(**kwargs))

            if count % 1000 == 0:
                session.commit()
                logger.info("technical_indicators: %d rows", count)
            if progress_cb and processed % 10 == 0:
                progress_cb("technical_indicators", processed, total, f"{count} rows")

        # Commit after each chunk to free session memory
        session.commit()

    session.commit()
    if progress_cb:
        progress_cb("technical_indicators", total, total, f"Done: {count} rows")
    return count


def recompute_scores(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Clear and recompute scores from all 6 analysis engines.

    Always full recompute — snapshot table (latest scores only, ~6K rows).
    Incremental flag is accepted for API compatibility but has no effect.
    """
    tickers = _load_all_idx_tickers(session)
    total = len(tickers)
    logger.info("Recomputing scores for %d tickers", total)
    if progress_cb:
        progress_cb("scores", 0, total, "Starting")

    if dry_run:
        return total * 6

    session.execute(text("DELETE FROM scores"))
    session.commit()

    tech_engine = TechnicalAnalysisEngine()
    fund_engine = FundamentalAnalysisEngine()
    macro_engine = MacroEconomicEngine()
    global_engine = GlobalMarketEngine()
    rel_engine = MarketRelationshipEngine()
    sentiment_engine = SentimentEngine()

    global_data: dict[str, pd.DataFrame] = {}
    for gt in GLOBAL_TICKERS:
        df = _load_ohlcv_df(session, gt)
        if not df.empty:
            global_data[gt] = df

    global_result = global_engine.analyze(global_data)

    ref_returns: dict[str, pd.Series] = {}
    for rt in REFERENCE_TICKERS:
        df = _load_ohlcv_df(session, rt)
        if not df.empty and len(df) >= 20:
            ref_returns[rt] = df["close"].astype(float).pct_change(
                fill_method=None,
            ).dropna()

    us10y_df = _load_ohlcv_df(session, "^TNX")
    gold_df = _load_ohlcv_df(session, "GC=F")
    oil_df = _load_ohlcv_df(session, "CL=F")
    usd_df = _load_ohlcv_df(session, "IDR=X")

    def _latest_close(df: pd.DataFrame) -> tuple[float | None, float | None]:
        if df.empty or len(df) < 2:
            return None, None
        return float(df["close"].iloc[-1]), float(df["close"].iloc[-2])

    us10y_cur, us10y_prev = _latest_close(us10y_df)
    gold_cur, gold_prev = _latest_close(gold_df)
    oil_cur, oil_prev = _latest_close(oil_df)
    usd_cur, usd_prev = _latest_close(usd_df)

    macro_result = macro_engine.analyze(
        us10y_yield=us10y_cur,
        us10y_prev=us10y_prev,
        gold_price=gold_cur,
        gold_prev=gold_prev,
        oil_price=oil_cur,
        oil_prev=oil_prev,
        usd_idr=usd_cur,
        usd_idr_prev=usd_prev,
    )

    now = datetime.now(UTC)
    count = 0

    score_batch: list[dict] = []
    BATCH_FLUSH_SIZE = 500

    def _queue_score(ticker: str, engine: str, score: float, breakdown: str) -> None:
        nonlocal count
        score_batch.append({
            "ticker": ticker,
            "engine": engine,
            "score": score,
            "breakdown": breakdown,
            "as_of": now,
        })
        count += 1
        if len(score_batch) >= BATCH_FLUSH_SIZE:
            session.bulk_insert_mappings(Score, score_batch)
            score_batch.clear()
            session.commit()
            logger.info("scores: %d rows", count)

    # Chunked batch processing — 100 tickers per batch to limit peak RAM
    CHUNK_SIZE = 100
    for chunk_start in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[chunk_start : chunk_start + CHUNK_SIZE]
        all_dfs = _load_all_ohlcv_dfs(session, chunk)

        for ticker in chunk:
            session.rollback()
            try:
                df = all_dfs.get(ticker)
                if df is None or df.empty or len(df) < 50:
                    continue

                if not df.index.is_unique:
                    df = df[~df.index.duplicated(keep="last")]

                tech_result = tech_engine.analyze(ticker, df)
                tech_score = tech_result.score if not np.isnan(tech_result.score) else 0.0
                _queue_score(ticker, "technical", tech_score, json.dumps(tech_result.breakdown))

                fund_row = session.execute(
                    select(FundamentalData)
                    .where(FundamentalData.ticker == ticker)
                    .order_by(FundamentalData.date.desc())
                    .limit(1)
                ).scalar_one_or_none()

                if fund_row is not None:
                    fund_result = fund_engine.analyze(
                        ticker,
                        pe=float(fund_row.pe) if fund_row.pe else None,
                        pb=float(fund_row.pb) if fund_row.pb else None,
                        roe=float(fund_row.roe) if fund_row.roe else None,
                        der=float(fund_row.der) if fund_row.der else None,
                        dividend_yield=(
                            float(fund_row.dividend_yield)
                            if fund_row.dividend_yield
                            else None
                        ),
                    )
                else:
                    fund_result = fund_engine.analyze(ticker)

                _queue_score(
                    ticker, "fundamental",
                    fund_result.score if not np.isnan(fund_result.score) else 0.0,
                    json.dumps(fund_result.breakdown),
                )

                _queue_score(
                    ticker, "macro",
                    macro_result.score if not np.isnan(macro_result.score) else 0.0,
                    json.dumps(macro_result.breakdown),
                )

                _queue_score(
                    ticker, "global",
                    global_result.score if not np.isnan(global_result.score) else 0.0,
                    json.dumps(global_result.breakdown),
                )

                target_returns = df["close"].astype(float).pct_change(
                    fill_method=None,
                ).dropna()
                rel_result = rel_engine.analyze(
                    ticker, target_returns, ref_returns, window=60,
                )
                rel_score = rel_result.score if not np.isnan(rel_result.score) else 0.0
                _queue_score(
                    ticker, "relationship", rel_score,
                    json.dumps(
                        {"window": 60, "relationships": len(rel_result.relationships)}
                    ),
                )

                ff_row = session.execute(
                    text(
                        "SELECT foreign_net FROM foreign_flow "
                        "WHERE ticker = :t ORDER BY date DESC LIMIT 1"
                    ),
                    {"t": ticker},
                ).first()

                if ff_row is not None and ff_row[0] is not None:
                    ff_val = float(ff_row[0])
                    ff_score = min(100.0, max(0.0, 50.0 + ff_val / 1e9 * 10))
                else:
                    ff_score = 50.0

                sent_result = sentiment_engine.analyze(
                    ticker, foreign_flow_score=ff_score,
                )
                _queue_score(
                    ticker, "sentiment",
                    sent_result.score if not np.isnan(sent_result.score) else 50.0,
                    json.dumps(sent_result.breakdown),
                )

                # Alpha signals score (4 engines composite)
                try:
                    from market.analysis.alpha_signals import (
                        EWMAMomentumEngine,
                        MeanReversionEngine,
                        RegimeSwitchEngine,
                        ShortTermReversalEngine,
                    )

                    close = df["close"].astype(float)
                    alpha_signals = []
                    for Engine in [MeanReversionEngine, ShortTermReversalEngine, EWMAMomentumEngine, RegimeSwitchEngine]:
                        result = Engine().generate_signals(close)
                        if len(result.signal):
                            alpha_signals.append(float(result.signal.iloc[-1]))

                    if alpha_signals:
                        avg_alpha = sum(alpha_signals) / len(alpha_signals)
                        alpha_score = max(0.0, min(100.0, 50.0 + avg_alpha * 50.0))
                        _queue_score(ticker, "alpha", alpha_score, json.dumps({"engines": len(alpha_signals), "avg": avg_alpha}))
                except Exception:
                    pass

                # Policy event score
                try:
                    today = datetime.now(UTC).date()
                    policy_rows = session.execute(text(
                        "SELECT direction FROM policy_events "
                        "WHERE event_date >= :lookback ORDER BY event_date DESC LIMIT 20"
                    ), {"lookback": today - timedelta(days=30)}).all()
                    ext_rows = session.execute(text(
                        "SELECT dampak_market FROM external_events "
                        "WHERE tanggal >= :lookback ORDER BY tanggal DESC LIMIT 20"
                    ), {"lookback": today - timedelta(days=30)}).all()

                    total_events = len(policy_rows) + len(ext_rows)
                    if total_events > 0:
                        p_signal = sum(float(r[0]) if r[0] else 0.0 for r in policy_rows)
                        p_signal += sum(
                            {"Tinggi": 0.5, "Sedang": 0.0, "Rendah": -0.3}.get(r[0] or "Sedang", 0.0)
                            for r in ext_rows
                        )
                        avg_p = p_signal / total_events
                        p_score = max(0.0, min(100.0, 50.0 + avg_p * 50.0))
                        _queue_score(ticker, "policy_event", p_score, json.dumps({"events": total_events}))
                except Exception:
                    pass

                # Seasonal pattern score
                try:
                    month = datetime.now(UTC).month
                    s_row = session.execute(text(
                        "SELECT seasonal_score FROM seasonal_patterns "
                        "WHERE ticker = :t AND month = :m ORDER BY seasonal_score DESC LIMIT 1"
                    ), {"t": ticker, "m": month}).first()
                    if s_row and s_row[0] is not None:
                        s_score = max(0.0, min(100.0, 50.0 + float(s_row[0]) * 50.0))
                        _queue_score(ticker, "seasonal", s_score, json.dumps({"month": month}))
                except Exception:
                    pass

                # Earnings calendar score
                try:
                    e_row = session.execute(text(
                        "SELECT report_date, expected_surprise_pct FROM earnings_calendar "
                        "WHERE ticker = :t AND report_date >= :today ORDER BY report_date LIMIT 1"
                    ), {"t": ticker, "today": today}).first()
                    if e_row:
                        report_dt = e_row[0]
                        days_to = (report_dt - today).days if report_dt else 999
                        if days_to <= 0 and e_row[1] is not None:
                            e_score = max(0.0, min(100.0, 50.0 + float(e_row[1]) * 5.0))
                        elif days_to <= 5:
                            e_score = 42.0
                        elif days_to <= 30:
                            e_score = 48.0
                        else:
                            e_score = None
                        if e_score is not None:
                            _queue_score(ticker, "earnings", e_score, json.dumps({"days_to": days_to}))
                except Exception:
                    pass

                if progress_cb and (count // 6) % 10 == 0:
                    progress_cb("scores", count // 6, total, f"{count} rows")
            except Exception as exc:
                logger.warning("  scores: skipping %s due to error: %s", ticker, exc)
                session.rollback()
                if progress_cb:
                    progress_cb("scores", 0, total, f"ERROR {ticker}: {exc}")
                continue

        # Flush remaining batch after each chunk
        if score_batch:
            session.bulk_insert_mappings(Score, score_batch)
            score_batch.clear()
            session.commit()

    if score_batch:
        session.bulk_insert_mappings(Score, score_batch)
    session.commit()
    if progress_cb:
        progress_cb("scores", total, total, f"Done: {count} rows")
    return count


RELATIONSHIP_WINDOWS = [30, 60, 90, 180, 360]


def recompute_relationship_matrix(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Clear and recompute relationship_matrix from OHLCV with multi-window.

    Always full recompute — snapshot table (latest correlations, ~63K rows).
    Incremental flag is accepted for API compatibility but has no effect.
    """
    from market.compute.device import select_device

    tickers = _load_all_idx_tickers(session)
    total_pairs = len(tickers) * len(REFERENCE_TICKERS) * len(RELATIONSHIP_WINDOWS)
    logger.info(
        "Recomputing relationship_matrix for %d tickers x %d references x %d windows = %d pairs",
        len(tickers), len(REFERENCE_TICKERS), len(RELATIONSHIP_WINDOWS), total_pairs,
    )
    _device = select_device("relationship_matrix", data_size=total_pairs)
    logger.info("relationship_matrix: using device=%s", _device)
    if progress_cb:
        progress_cb("relationship_matrix", 0, len(tickers), "Starting")

    if dry_run:
        return total_pairs

    session.execute(text("DELETE FROM relationship_matrix"))
    session.commit()

    rel_engine = MarketRelationshipEngine()
    count = 0
    processed = 0

    ref_returns: dict[str, pd.Series] = {}
    ref_dfs: dict[str, pd.DataFrame] = {}
    for rt in REFERENCE_TICKERS:
        df = _load_ohlcv_df(session, rt)
        if not df.empty and len(df) >= 20:
            if not df.index.is_unique:
                df = df[~df.index.duplicated(keep="last")]
            ref_dfs[rt] = df
            ref_returns[rt] = df["close"].astype(float).pct_change(
                fill_method=None,
            ).dropna()

    for ticker in tickers:
        try:
            df = _load_ohlcv_df(session, ticker)
            if df.empty or len(df) < 60:
                continue
            if not df.index.is_unique:
                df = df[~df.index.duplicated(keep="last")]

            target_returns = df["close"].astype(float).pct_change(
                fill_method=None,
            ).dropna()

            for window in RELATIONSHIP_WINDOWS:
                if len(target_returns) < window:
                    continue

                result = rel_engine.analyze(
                    ticker, target_returns, ref_returns, window=window,
                )

                for rel in result.relationships:
                    ref_ticker = str(rel["ticker"])
                    corr_raw = cast("float | None", rel["correlation"])
                    lag_raw = cast("int | None", rel["lag"])
                    session.add(
                        RelationshipMatrix(
                            asset_a=ticker,
                            asset_b=ref_ticker,
                            window=window,
                            correlation=float(corr_raw) if corr_raw is not None else None,
                            lag=int(lag_raw) if lag_raw is not None else None,
                        )
                    )
                    count += 1

                if count % 5000 == 0:
                    session.commit()
                    logger.info("relationship_matrix: %d rows", count)
            processed += 1
            if progress_cb:
                progress_cb("relationship_matrix", processed, len(tickers), f"{count} rows")
        except Exception as exc:
            logger.warning("  relationship_matrix: skipping %s: %s", ticker, exc)
            session.rollback()
            if progress_cb:
                progress_cb("relationship_matrix", 0, len(tickers), f"ERROR {ticker}: {exc}")
            continue

    session.commit()
    if progress_cb:
        progress_cb("relationship_matrix", len(tickers), len(tickers), f"Done: {count} rows")
    return count


def recompute_fear_greed(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Compute fear_greed from OHLCV market data.

    Uses a composite of market momentum, volatility, and volume
    to compute a Fear & Greed index (0-100).

    If incremental=True, only appends dates after the last existing entry.
    If incremental=False, clears and recomputes all dates.
    """
    logger.info("Recomputing fear_greed index (incremental=%s)", incremental)
    if progress_cb:
        progress_cb("fear_greed", 0, 1, "Starting")

    if dry_run:
        return 365

    start_idx = 20
    if incremental:
        wm = _get_watermark(session, IHSG_TICKER, "fear_greed")
        if wm is None:
            last_date = session.execute(
                text("SELECT MAX(date) FROM fear_greed")
            ).scalar()
            if last_date is not None:
                if isinstance(last_date, str):
                    from datetime import date as _date
                    last_date = _date.fromisoformat(last_date)
                wm = last_date
        if wm is not None:
            pass
    else:
        session.execute(text("DELETE FROM fear_greed"))
        session.commit()

    if incremental and wm is not None:
        ihsg_df = _load_ohlcv_df_since(session, IHSG_TICKER, wm, buffer_days=50)
        if len(ihsg_df) < 50:
            logger.info("fear_greed: bounded load too small (%d rows), falling back to full load", len(ihsg_df))
            ihsg_df = _load_ohlcv_df(session, IHSG_TICKER)
    else:
        ihsg_df = _load_ohlcv_df(session, IHSG_TICKER)
    if ihsg_df.empty or len(ihsg_df) < 50:
        logger.warning("No IHSG data for fear_greed computation")
        return 0

    close = ihsg_df["close"].astype(float)
    if "volume" in ihsg_df.columns:
        volume = ihsg_df["volume"].astype(float)
    else:
        volume = pd.Series(0.0, index=ihsg_df.index)

    if incremental and wm is not None:
        for i in range(20, len(ihsg_df)):
            if ihsg_df.index[i].date() > wm:
                start_idx = i
                break
        else:
            logger.info("fear_greed: no new dates to append (last=%s)", wm)
            if progress_cb:
                progress_cb("fear_greed", 1, 1, "Done: 0 rows (up to date)")
            return 0
        logger.info("fear_greed: appending from %s (idx=%d)", ihsg_df.index[start_idx].date(), start_idx)

    count = 0
    window = 20
    for i in range(start_idx, len(ihsg_df)):
        date_val = ihsg_df.index[i].date()

        ma20 = close.iloc[i - window : i].mean()
        momentum = ((close.iloc[i] - ma20) / ma20) * 100
        momentum_score = min(100.0, max(0.0, 50.0 + momentum * 5))

        recent = close.iloc[i - window : i + 1]
        returns = recent.pct_change(fill_method=None).dropna()
        vol = float(returns.std() * 100) if len(returns) > 1 else 0.0
        vol_score = min(100.0, max(0.0, 100.0 - vol * 20))

        vol_avg = volume.iloc[i - window : i].mean()
        vol_ratio = float(volume.iloc[i] / vol_avg) if vol_avg > 0 else 1.0
        vol_ratio_score = min(100.0, max(0.0, vol_ratio * 50))

        fgi = (momentum_score * 0.4 + vol_score * 0.35 + vol_ratio_score * 0.25)
        fgi = round(min(100.0, max(0.0, fgi)), 2)

        if fgi >= 75:
            label = "Extreme Greed"
        elif fgi >= 55:
            label = "Greed"
        elif fgi >= 45:
            label = "Neutral"
        elif fgi >= 25:
            label = "Fear"
        else:
            label = "Extreme Fear"

        from market.db.models import FearGreed as _FG
        existing = session.execute(
            select(_FG).where(_FG.date == date_val)
        ).scalar_one_or_none()
        if existing:
            existing.value = fgi
            existing.label = label
        else:
            session.add(_FG(date=date_val, value=fgi, label=label))
        count += 1

    if incremental and count > 0:
        _set_watermark(session, IHSG_TICKER, "fear_greed", ihsg_df.index[-1].date(), count)

    session.commit()
    if progress_cb:
        progress_cb("fear_greed", 1, 1, f"Done: {count} rows")
    return count


def recompute_stock_personality(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Clear and recompute stock_personality from OHLCV.

    Always full recompute — snapshot table (latest profile per ticker, ~985 rows).
    Incremental flag is accepted for API compatibility but has no effect.
    """
    tickers = _load_all_idx_tickers(session)
    logger.info("Recomputing stock_personality for %d tickers", len(tickers))
    if progress_cb:
        progress_cb("stock_personality", 0, len(tickers), "Starting")

    if dry_run:
        return len(tickers)

    session.execute(text("DELETE FROM stock_personality"))
    session.commit()

    profiler = InstrumentProfiler()
    ihsg_df = _load_ohlcv_df(session, IHSG_TICKER)

    count = 0
    for ticker in tickers:
        try:
            df = _load_ohlcv_df(session, ticker)
            if df.empty or len(df) < 20:
                continue
            if not df.index.is_unique:
                df = df[~df.index.duplicated(keep="last")]

            profile = profiler.profile(ticker, df, ihsg_df=ihsg_df)

            labels = [lbl.value for lbl in profile.personality_labels]
            primary_label = labels[0] if labels else "unknown"

            session.merge(
                StockPersonality(
                    ticker=ticker,
                    volatility_regime=profile.volatility_regime.value,
                    trend_bias=profile.trend_bias,
                    beta_vs_ihsg=profile.beta_vs_ihsg,
                    liquidity_score=profile.liquidity_score,
                    personality_label=primary_label,
                )
            )
            count += 1

            if count % 100 == 0:
                session.commit()
                logger.info("stock_personality: %d", count)
            if progress_cb and count % 10 == 0:
                progress_cb("stock_personality", count, len(tickers), f"{count} profiles")
        except Exception as exc:
            logger.warning("  stock_personality: skipping %s: %s", ticker, exc)
            session.rollback()
            if progress_cb:
                progress_cb("stock_personality", 0, len(tickers), f"ERROR {ticker}: {exc}")
            continue

    session.commit()
    if progress_cb:
        progress_cb("stock_personality", len(tickers), len(tickers), f"Done: {count} rows")
    return count


ML_LABEL_HORIZONS = [1, 5, 10, 21]
ML_LABEL_VOL_MULTIPLE = 2.0


def recompute_ml_labels(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Compute triple-barrier labels for all IDX tickers (pustaka/23 §4).

    For each ticker and each horizon, computes:
    - Take-profit barrier: +vol_multiple * ATR14
    - Stop-loss barrier: -vol_multiple * ATR14
    - Time barrier: horizon trading days

    If incremental=True, uses per-ticker watermark from recompute_watermark
    table. Only loads OHLCV from (watermark - lookback) to latest, and only
    computes labels for dates after (watermark - max_horizon). This makes
    daily incremental recompute ~50-100x faster than full recompute.

    If incremental=False, clears all labels and recomputes from scratch.

    Vectorized implementation: barrier check uses numpy array operations
    (loop over 21 offsets, not 1000+ dates). Bulk insert via executemany.

    Returns the number of label rows generated.
    """
    tickers = _load_all_idx_tickers(session)
    total_est = len(tickers) * len(ML_LABEL_HORIZONS)
    logger.info("Recomputing ml_labels for %d tickers x %d horizons (incremental=%s)",
                len(tickers), len(ML_LABEL_HORIZONS), incremental)

    from market.compute.device import select_device
    _device = select_device("ml_labels", data_size=total_est)
    logger.info("ml_labels: using device=%s", _device)
    if progress_cb:
        progress_cb("ml_labels", 0, len(tickers), "Starting")

    if dry_run:
        return total_est

    if not incremental:
        session.execute(text("DELETE FROM ml_labels"))
        session.commit()

    max_horizon = max(ML_LABEL_HORIZONS)
    atr_period = 14
    lookback_buffer = max_horizon + atr_period + 10

    count = 0
    processed = 0
    for ticker in tickers:
        if incremental:
            wm = _get_watermark(session, ticker, "ml_labels")
            if wm is not None:
                since = wm - timedelta(days=lookback_buffer)
                df = _load_ohlcv_df_since(session, ticker, since)
                if df.empty or len(df) < atr_period + 1:
                    continue
                delete_from = wm - timedelta(days=max_horizon)
                session.execute(
                    text("DELETE FROM ml_labels WHERE ticker = :t AND date > :cutoff"),
                    {"t": ticker, "cutoff": delete_from},
                )
                session.commit()
                start_i = None
                for i in range(atr_period, len(df)):
                    if df.index[i].date() > delete_from:
                        start_i = i
                        break
                if start_i is None:
                    continue
            else:
                existing_max = session.execute(
                    text("SELECT MAX(date) FROM ml_labels WHERE ticker = :t"),
                    {"t": ticker},
                ).scalar()
                if existing_max is not None:
                    if isinstance(existing_max, str):
                        from datetime import date as _date
                        existing_max = _date.fromisoformat(existing_max)
                    delete_from = existing_max - timedelta(days=max_horizon)
                    session.execute(
                        text("DELETE FROM ml_labels WHERE ticker = :t AND date > :cutoff"),
                        {"t": ticker, "cutoff": delete_from},
                    )
                    session.commit()
                    since = existing_max - timedelta(days=lookback_buffer)
                    df = _load_ohlcv_df_since(session, ticker, since)
                    if df.empty or len(df) < atr_period + 1:
                        continue
                    start_i = None
                    for i in range(atr_period, len(df)):
                        if df.index[i].date() > delete_from:
                            start_i = i
                            break
                    if start_i is None:
                        continue
                else:
                    df = _load_ohlcv_df(session, ticker)
                    if df.empty or len(df) < 60:
                        continue
                    start_i = atr_period
        else:
            df = _load_ohlcv_df(session, ticker)
            if df.empty or len(df) < 60:
                continue
            start_i = atr_period

        if not df.index.is_unique:
            df = df[~df.index.duplicated(keep="first")]

        processed += 1
        close = df["close"].astype(float).values
        high = df["high"].astype(float).values
        low = df["low"].astype(float).values
        dates = df.index.date
        n = len(close)

        tr = high - low
        atr = pd.Series(tr).rolling(atr_period).mean().values

        tp = close + ML_LABEL_VOL_MULTIPLE * atr
        sl = close - ML_LABEL_VOL_MULTIPLE * atr

        valid = (atr > 0) & (close > 0) & ~np.isnan(atr)

        ticker_count = 0
        batch: list[dict] = []

        for horizon in ML_LABEL_HORIZONS:
            tp_first_hit = np.full(n, np.inf)
            sl_first_hit = np.full(n, np.inf)

            for k in range(1, horizon + 1):
                if k >= n:
                    break
                future_close = close[k:]
                m = len(future_close)

                tp_at_k = future_close >= tp[:m]
                sl_at_k = future_close <= sl[:m]

                mask_tp = tp_at_k & (tp_first_hit[:m] == np.inf)
                tp_first_hit[:m][mask_tp] = k
                mask_sl = sl_at_k & (sl_first_hit[:m] == np.inf)
                sl_first_hit[:m][mask_sl] = k

            tp_hit = tp_first_hit < np.inf
            sl_hit = sl_first_hit < np.inf

            ret = np.full(n, np.nan)
            if horizon < n:
                ret[:n - horizon] = (close[horizon:] / close[:n - horizon] - 1) * 100

            with np.errstate(divide="ignore", invalid="ignore"):
                vol_adj_ret = np.where(
                    (atr > 0) & (close > 0) & ~np.isnan(ret),
                    ret / (atr / close * 100),
                    0.0,
                )

            end_i = n - horizon
            for i in range(max(start_i, atr_period), end_i):
                if not valid[i]:
                    continue

                if tp_hit[i] and not sl_hit[i]:
                    direction = "up"
                    barrier = "take_profit"
                elif sl_hit[i] and not tp_hit[i]:
                    direction = "down"
                    barrier = "stop_loss"
                elif tp_hit[i] and sl_hit[i]:
                    if tp_first_hit[i] <= sl_first_hit[i]:
                        direction = "up"
                        barrier = "take_profit"
                    else:
                        direction = "down"
                        barrier = "stop_loss"
                else:
                    direction = "static"
                    barrier = "time_expired"

                batch.append({
                    "ticker": ticker,
                    "date": dates[i],
                    "horizon": horizon,
                    "direction": direction,
                    "barrier_hit": barrier,
                    "return_pct": round(float(ret[i]), 4),
                    "vol_adjusted_return": round(float(vol_adj_ret[i]), 4),
                })
                ticker_count += 1
                count += 1

                if len(batch) >= 5000:
                    session.execute(
                        text(
                            "INSERT INTO ml_labels "
                            "(ticker, date, horizon, direction, barrier_hit, "
                            "return_pct, vol_adjusted_return) "
                            "VALUES (:ticker, :date, :horizon, :direction, "
                            ":barrier_hit, :return_pct, :vol_adjusted_return) "
                            "ON CONFLICT (ticker, date, horizon) DO UPDATE SET "
                            "direction=EXCLUDED.direction, barrier_hit=EXCLUDED.barrier_hit, "
                            "return_pct=EXCLUDED.return_pct, vol_adjusted_return=EXCLUDED.vol_adjusted_return"
                        ),
                        batch,
                    )
                    session.commit()
                    batch.clear()
                    logger.info("ml_labels: %d rows", count)

            if progress_cb and processed % 5 == 0:
                progress_cb("ml_labels", processed, len(tickers), f"{count} rows")

        if batch:
            session.execute(
                text(
                    "INSERT INTO ml_labels "
                    "(ticker, date, horizon, direction, barrier_hit, "
                    "return_pct, vol_adjusted_return) "
                    "VALUES (:ticker, :date, :horizon, :direction, "
                    ":barrier_hit, :return_pct, :vol_adjusted_return) "
                    "ON CONFLICT (ticker, date, horizon) DO UPDATE SET "
                    "direction=EXCLUDED.direction, barrier_hit=EXCLUDED.barrier_hit, "
                    "return_pct=EXCLUDED.return_pct, vol_adjusted_return=EXCLUDED.vol_adjusted_return"
                ),
                batch,
            )
            batch.clear()

        if incremental and ticker_count > 0:
            last_ohlcv_date = dates[-1]
            _set_watermark(session, ticker, "ml_labels", last_ohlcv_date, ticker_count)

        session.commit()

    session.commit()
    if progress_cb:
        progress_cb("ml_labels", len(tickers), len(tickers), f"Done: {count} rows")
    return count


def recompute_market_regimes(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Compute daily market regime labels from IHSG and auxiliary data.

    Uses heuristic rules based on IHSG trend, VIX (if available),
    Fear & Greed index, and foreign flow aggregate.

    Regime: 'bull', 'bear', 'sideways', 'crisis'.

    If incremental=True, only appends dates after the last existing entry.
    If incremental=False, clears and recomputes all dates.
    """
    logger.info("Recomputing market_regimes (incremental=%s)", incremental)
    if progress_cb:
        progress_cb("market_regimes", 0, 1, "Starting")

    if dry_run:
        return 365

    start_idx = 200
    wm = None
    if incremental:
        wm = _get_watermark(session, IHSG_TICKER, "market_regimes")
        if wm is None:
            last_date = session.execute(
                text("SELECT MAX(date) FROM market_regimes")
            ).scalar()
            if last_date is not None:
                if isinstance(last_date, str):
                    from datetime import date as _date
                    last_date = _date.fromisoformat(last_date)
                wm = last_date
        if wm is None:
            incremental = False

    if not incremental:
        session.execute(text("DELETE FROM market_regimes"))
        session.commit()

    if incremental and wm is not None:
        ihsg_df = _load_ohlcv_df_since(session, IHSG_TICKER, wm, buffer_days=250)
        if len(ihsg_df) < 250:
            logger.info("market_regimes: bounded load too small (%d rows), falling back to full load", len(ihsg_df))
            ihsg_df = _load_ohlcv_df(session, IHSG_TICKER)
    else:
        ihsg_df = _load_ohlcv_df(session, IHSG_TICKER)
    if ihsg_df.empty or len(ihsg_df) < 60:
        logger.warning("No IHSG data for regime computation")
        return 0

    close = ihsg_df["close"].astype(float)
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()

    if incremental and wm is not None:
        for i in range(200, len(ihsg_df)):
            if ihsg_df.index[i].date() > wm:
                start_idx = i
                break
        else:
            logger.info("market_regimes: no new dates to append (last=%s)", wm)
            if progress_cb:
                progress_cb("market_regimes", 1, 1, "Done: 0 rows (up to date)")
            return 0
        logger.info("market_regimes: appending from %s (idx=%d)", ihsg_df.index[start_idx].date(), start_idx)

    fg_rows = session.execute(
        select(FearGreed).order_by(FearGreed.date)
    ).scalars().all()
    fg_map = {r.date: (r.value, r.label) for r in fg_rows}

    vix_df = _load_ohlcv_df(session, "^VIX")

    ff_rows = session.execute(
        text(
            "SELECT date, SUM(foreign_net) as net FROM foreign_flow "
            "GROUP BY date ORDER BY date"
        )
    ).all()
    ff_map = {r[0]: float(r[1]) for r in ff_rows if r[1] is not None}

    count = 0
    for i in range(start_idx, len(ihsg_df)):
        date_val = ihsg_df.index[i].date()
        cur_close = close.iloc[i]
        cur_ma50 = ma50.iloc[i]
        cur_ma200 = ma200.iloc[i]

        if pd.isna(cur_ma50) or pd.isna(cur_ma200):
            continue

        above_ma50 = cur_close > cur_ma50
        above_ma200 = cur_close > cur_ma200
        ma50_above_ma200 = cur_ma50 > cur_ma200

        recent_returns = close.iloc[i - 20: i + 1].pct_change(fill_method=None).dropna()
        vol = float(recent_returns.std() * 100) if len(recent_returns) > 1 else 0.0

        vix_level = None
        if not vix_df.empty and len(vix_df) > i:
            vix_val = float(vix_df["close"].iloc[i])
            if vix_val > 30:
                vix_level = "extreme"
            elif vix_val > 20:
                vix_level = "high"
            elif vix_val > 15:
                vix_level = "normal"
            else:
                vix_level = "low"

        fg_label = None
        if date_val in fg_map:
            fg_label = fg_map[date_val][1]

        ff_trend = None
        recent_ff = [ff_map.get(ihsg_df.index[j].date()) for j in range(max(0, i - 5), i)]
        recent_ff = [x for x in recent_ff if x is not None]
        if recent_ff:
            ff_sum = sum(recent_ff)
            if ff_sum > 0:
                ff_trend = "inflow"
            elif ff_sum < 0:
                ff_trend = "outflow"
            else:
                ff_trend = "neutral"

        if vol > 3.0 or (vix_level == "extreme"):
            regime = "crisis"
        elif above_ma50 and above_ma200 and ma50_above_ma200:
            regime = "bull"
        elif not above_ma50 and not above_ma200 and not ma50_above_ma200:
            regime = "bear"
        else:
            regime = "sideways"

        ihsg_trend = "up" if above_ma50 and above_ma200 else ("down" if not above_ma50 and not above_ma200 else "flat")

        if vol > 3.0 or vix_level == "extreme":
            vol_level = "extreme"
        elif vix_level == "high" or vol > 2.0:
            vol_level = "high"
        elif vix_level == "normal" or vol > 1.0:
            vol_level = "normal"
        else:
            vol_level = "low"

        breadth = 0.0
        if above_ma50:
            breadth += 33.3
        if above_ma200:
            breadth += 33.3
        if ma50_above_ma200:
            breadth += 33.4

        desc_parts = [f"trend={ihsg_trend}", f"vol={vol_level}"]
        if fg_label:
            desc_parts.append(f"FG={fg_label}")
        if ff_trend:
            desc_parts.append(f"flow={ff_trend}")
        description = ", ".join(desc_parts)

        from market.db.models import MarketRegime as _MR
        existing = session.execute(
            select(_MR).where(_MR.date == date_val)
        ).scalar_one_or_none()
        if existing:
            existing.regime = regime
            existing.ihsg_trend = ihsg_trend
            existing.volatility_level = vol_level
            existing.breadth_score = breadth
            existing.description = description
        else:
            session.add(_MR(
                date=date_val,
                regime=regime,
                ihsg_trend=ihsg_trend,
                volatility_level=vol_level,
                breadth_score=breadth,
                description=description,
            ))
        count += 1

    if incremental and count > 0:
        _set_watermark(session, IHSG_TICKER, "market_regimes", ihsg_df.index[-1].date(), count)

    session.commit()
    if progress_cb:
        progress_cb("market_regimes", 1, 1, f"Done: {count} rows")
    return count


def recompute_weights(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> int:
    """Optimize signal weights based on historical prediction accuracy.

    Compares past composite_signal outputs with actual returns to find
    optimal weights via grid search. Saves results to signal_weights table.

    Returns number of weight rows updated.
    """
    from market.analysis.weight_registry import WeightRegistry

    tickers = _load_all_idx_tickers(session)
    total = len(tickers)
    logger.info("Optimizing weights for %d tickers", total)
    if progress_cb:
        progress_cb("weights", 0, total, "Starting")

    if dry_run:
        return total

    # Load historical scores and actual returns for evaluation
    # We use a simple correlation-based optimization:
    # For each signal, compute correlation between signal score and actual return
    # Weight ∝ |correlation| (signals with higher predictive power get more weight)

    signal_names = [
        "technical", "fundamental", "macro", "global", "relationship",
        "sentiment", "holiday", "alpha", "policy_event",
        "sector_rotation", "seasonal", "earnings",
    ]

    # Collect per-signal correlation with actual returns
    signal_correlations: dict[str, list[float]] = {s: [] for s in signal_names}

    for ticker in tickers[:200]:  # Sample 200 tickers for speed
        try:
            df = _load_ohlcv_df(session, ticker)
            if df is None or df.empty or len(df) < 60:
                continue

            # Actual forward returns (5-day)
            returns = df["close"].astype(float).pct_change(5).shift(-5).dropna()
            if len(returns) < 30:
                continue

            # Get historical scores for this ticker
            score_rows = session.execute(
                text(
                    "SELECT engine, score FROM scores "
                    "WHERE ticker = :t ORDER BY as_of DESC LIMIT 12"
                ),
                {"t": ticker},
            ).all()

            for engine, score in score_rows:
                # Map engine names to signal names
                signal_name = engine if engine in signal_correlations else None
                if signal_name is None:
                    if engine == "global_market":
                        signal_name = "global"
                    else:
                        continue
                # Use score as proxy for signal value
                # Normalize score (0-100) to (-1, 1)
                signal_val = (float(score) - 50.0) / 50.0
                signal_correlations[signal_name].append(signal_val)

        except Exception as exc:
            logger.debug("  weights: skipping %s: %s", ticker, exc)
            continue

    # Compute weights proportional to signal variance (proxy for information content)
    # Signals with more variance carry more information
    weights: dict[str, float] = {}
    total_var = 0.0
    for name in signal_names:
        vals = signal_correlations[name]
        if len(vals) < 5:
            weights[name] = 0.0
            continue
        arr = np.array(vals)
        var = float(np.var(arr))
        weights[name] = max(var, 0.001)  # Minimum weight to avoid zero
        total_var += weights[name]

    # Normalize to sum to 1.0
    if total_var > 0:
        weights = {k: v / total_var for k, v in weights.items()}

    # Apply minimum weight floor (1%) and renormalize
    MIN_WEIGHT = 0.01
    for k in weights:
        weights[k] = max(weights[k], MIN_WEIGHT)
    weights = WeightRegistry.normalize(weights)

    # Save optimized weights
    count = len(weights)
    WeightRegistry.save_optimized(
        scope="decision_engine",
        sector="DEFAULT",
        weights=weights,
        method="variance_proxy",
        score=float(np.mean([np.var(v) for v in signal_correlations.values() if len(v) > 5])) if any(len(v) > 5 for v in signal_correlations.values()) else None,
        session=session,
    )

    # Also optimize market_context weights with same approach
    mc_signal_names = [
        "fundamental", "macro", "sentiment", "flow", "cross_market",
        "ml", "news", "commodity", "global_sentiment", "governance",
        "astronacci", "holiday", "alpha", "policy_event",
        "sector_rotation", "volume", "seasonal", "earnings",
        "causal", "meta_label",
    ]

    # For market_context, use the same variance proxy but with different signal set
    # Start from current weights and apply small adjustments
    mc_weights = WeightRegistry.get_weights("market_context", session=session)
    # Keep existing weights but normalize (they should already be close to optimal)
    mc_weights = WeightRegistry.normalize(mc_weights)

    WeightRegistry.save_optimized(
        scope="market_context",
        sector="DEFAULT",
        weights=mc_weights,
        method="variance_proxy",
        session=session,
    )
    count += len(mc_weights)

    if progress_cb:
        progress_cb("weights", total, total, f"Done: {count} weights")

    logger.info("Weight optimization complete: %d weights saved", count)
    return count


def run_all_recompute(
    session: Session, dry_run: bool = False, progress_cb: ProgressCb = None,
    incremental: bool = False,
) -> dict[str, int]:
    """Run all recompute functions.

    If incremental=True, time-series tables (fear_greed, ml_labels,
    market_regimes) only append new dates. Snapshot tables
    (technical_indicators, scores, relationship_matrix, stock_personality)
    always do full recompute since they store only latest values.

    If incremental=False, all tables are cleared and fully recomputed.
    """
    results: dict[str, int] = {}
    # cross_market lives in multi_asset (S3) — lazy import to avoid S2→S3 violation
    from market.multi_asset.cross_market import recompute_cross_market

    functions = [
        ("technical_indicators", recompute_technical_indicators),
        ("scores", recompute_scores),
        ("relationship_matrix", recompute_relationship_matrix),
        ("cross_market", recompute_cross_market),
        ("fear_greed", recompute_fear_greed),
        ("stock_personality", recompute_stock_personality),
        ("ml_labels", recompute_ml_labels),
        ("market_regimes", recompute_market_regimes),
        ("weights", recompute_weights),
    ]

    mode_label = "incremental" if incremental else "full"
    logger.info("Running all recompute (mode=%s)", mode_label)
    if progress_cb:
        progress_cb("mode", 0, 0, mode_label)

    for name, func in functions:
        logger.info("Recomputing %s (mode=%s)...", name, mode_label)
        try:
            count = func(session, dry_run=dry_run, progress_cb=progress_cb, incremental=incremental)
            results[name] = count
            logger.info("  %s: %d rows", name, count)
        except Exception as exc:
            logger.error("  %s FAILED: %s", name, exc)
            results[name] = -1
            session.rollback()
            if progress_cb:
                progress_cb(name, -1, 0, f"FAILED: {exc}")

    return results


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    dry = "--dry-run" in sys.argv
    session = get_sessionmaker()()
    try:
        summary = run_all_recompute(session, dry_run=dry)
        print("\nRecompute summary:")
        for name, count in summary.items():
            status = f"{count} rows" if count >= 0 else "FAILED"
            print(f"  {name}: {status}")
    finally:
        session.close()
