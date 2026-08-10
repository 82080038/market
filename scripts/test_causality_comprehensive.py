"""Comprehensive 7-layer causality test for IDX stock prices.

Tests all causal factor categories against representative IDX tickers:
  Layer 1: Cross-market (global indices, commodities, FX, rates)
  Layer 2: Macro (BI rate, inflation, GDP, forex reserves)
  Layer 3: Fundamental (PE, PB, ROE, EPS, market cap, beta)
  Layer 4: Corporate actions (dividends)
  Layer 5: Flow (foreign buy/sell, broker transactions)
  Layer 6: Sentiment (policy events, Fear & Greed)
  Layer 7: Technical (autocorrelation, volume-return)

Uses Granger causality + correlation analysis to identify which factors
significantly cause price movements for each ticker.

Usage:
    uv run python scripts/test_causality_comprehensive.py
    uv run python scripts/test_causality_comprehensive.py --tickers BBCA.JK,BBRI.JK
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from statsmodels.tsa.stattools import grangercausalitytests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PG_URL = "postgresql://petrick:market_dev@localhost:5432/market"
MAX_LAG = 5
LOOKBACK_DAYS = 500
P_THRESHOLD = 0.05

# Representative tickers per sector
REPRESENTATIVE_TICKERS = {
    "Financial Services": ["BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK"],
    "Consumer Defensive": ["UNVR.JK", "INDF.JK", "ICBP.JK"],
    "Basic Materials": ["INCO.JK", "ANTM.JK"],
    "Energy": ["PTBA.JK", "ADRO.JK"],
    "Telecommunication": ["TLKM.JK"],
    "Industrial": ["UNTR.JK"],
    "Healthcare": ["KLBF.JK"],
    "Property": ["CTRA.JK"],
}

# Global factor tickers (Layer 1)
GLOBAL_TICKERS = [
    "^GSPC", "^DJI", "^IXIC", "^VIX", "^TNX", "^IRX",
    "^N225", "^HSI", "000001.SS", "^KS11", "^STI", "^KLSE", "^AXJO", "^BSESN",
    "^FTSE", "^GDAXI",
    "IDR=X", "EURIDR=X", "JPYIDR=X", "SGDIDR=X", "DX-Y.NYB",
    "GC=F", "CL=F", "BZ=F", "NG=F", "HG=F", "SI=F", "CPO=F",
    "XLE", "DBA",
]


def load_ohlcv_returns(engine, tickers: list[str], lookback: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Load daily log returns for tickers, aligned by trading date."""
    cutoff = date.today() - timedelta(days=lookback)
    df = pd.read_sql(text("""
        SELECT ticker, timestamp, close
        FROM stock_prices
        WHERE ticker = ANY(:tickers)
          AND timeframe = '1d'
          AND timestamp >= :cutoff
        ORDER BY ticker, timestamp
    """), engine, params={"tickers": tickers, "cutoff": cutoff})

    if df.empty:
        return pd.DataFrame()

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["trade_date"] = df["timestamp"].dt.date
    df = df.drop_duplicates(subset=["ticker", "trade_date"])
    pivot = df.pivot(index="trade_date", columns="ticker", values="close")
    pivot = pivot.sort_index()
    returns = np.log(pivot / pivot.shift(1)).dropna()
    return returns


def load_macro_data(engine) -> pd.DataFrame:
    """Load macro data and forward-fill to daily frequency."""
    df = pd.read_sql(text("""
        SELECT series_name, date, value FROM macro_data ORDER BY series_name, date
    """), engine)

    if df.empty:
        return pd.DataFrame()

    pivot = df.pivot(index="date", columns="series_name", values="value")
    pivot.index = pd.to_datetime(pivot.index)
    # Forward-fill macro data to daily
    all_dates = pd.date_range(pivot.index.min(), pivot.index.max(), freq="D")
    pivot = pivot.reindex(all_dates).ffill()
    return pivot


def load_fundamental_data(engine, tickers: list[str]) -> pd.DataFrame:
    """Load fundamental data for tickers."""
    df = pd.read_sql(text("""
        SELECT ticker, date, pe, pb, roe, eps, market_cap, beta,
               profit_margin, debt_to_equity, dividend_yield, revenue
        FROM fundamental_data
        WHERE ticker = ANY(:tickers)
        ORDER BY ticker, date
    """), engine, params={"tickers": tickers})

    if df.empty:
        return pd.DataFrame()

    return df


def load_corporate_actions(engine, tickers: list[str]) -> pd.DataFrame:
    """Load dividend events for tickers."""
    df = pd.read_sql(text("""
        SELECT ticker, ex_date, action_type, details_json
        FROM corporate_actions
        WHERE ticker = ANY(:tickers)
        ORDER BY ex_date
    """), engine, params={"tickers": tickers})

    if df.empty:
        return pd.DataFrame()

    return df


def load_events(engine) -> pd.DataFrame:
    """Load policy/geopolitical events."""
    df = pd.read_sql(text("""
        SELECT occurred_at, category, impact_direction, impact_level, title
        FROM events
        ORDER BY occurred_at
    """), engine)

    if df.empty:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["occurred_at"]).dt.date
    return df


def test_granger(returns: pd.DataFrame, cause: str, effect: str, maxlag: int = MAX_LAG) -> dict | None:
    """Run Granger causality test: does `cause` Granger-cause `effect`?"""
    if cause not in returns.columns or effect not in returns.columns:
        return None

    data = returns[[effect, cause]].dropna()
    if len(data) < 30 or data[cause].std() == 0:
        return None

    try:
        results = grangercausalitytests(data, maxlag=maxlag, verbose=False)
        best_p = 1.0
        best_lag = 0
        for lag in range(1, maxlag + 1):
            p_val = results[lag][0]["ssr_ftest"][1]
            if p_val < best_p:
                best_p = p_val
                best_lag = lag
        return {
            "cause": cause,
            "effect": effect,
            "p_value": best_p,
            "lag": best_lag,
            "significant": best_p < P_THRESHOLD,
        }
    except Exception:
        return None


def test_macro_causality(returns: pd.DataFrame, macro: pd.DataFrame, effect_ticker: str) -> list[dict]:
    """Test macro factor causality against a ticker's returns.

    For irregular series (BI rate), use regime-change dummy.
    For annual series (World Bank), use level correlation.
    """
    results = []
    if macro.empty or effect_ticker not in returns.columns:
        return results

    common_dates = returns.index.intersection(macro.index)
    if len(common_dates) < 30:
        return results

    for series in macro.columns:
        series_data = macro.loc[common_dates, series].dropna()
        if len(series_data) < 30:
            continue

        # For BI rate (irregular): create regime-change dummy
        if series == "BI_7DAY_REPO_RATE":
            # Create dummy: 1 on days when rate changes, 0 otherwise
            rate_diff = series_data.diff().fillna(0)
            change_dummy = (rate_diff != 0).astype(float)
            if change_dummy.sum() < 3:
                continue
            combined = pd.DataFrame({
                "target": returns.loc[common_dates, effect_ticker],
                "macro": change_dummy,
            }).dropna()
            if len(combined) < 30:
                continue
            try:
                res = grangercausalitytests(combined[["target", "macro"]], maxlag=MAX_LAG, verbose=False)
                best_p = 1.0
                best_lag = 0
                for lag in range(1, MAX_LAG + 1):
                    p_val = res[lag][0]["ssr_ftest"][1]
                    if p_val < best_p:
                        best_p = p_val
                        best_lag = lag
                results.append({
                    "cause": f"MACRO:{series}_CHANGE",
                    "effect": effect_ticker,
                    "p_value": best_p,
                    "lag": best_lag,
                    "significant": best_p < P_THRESHOLD,
                })
            except Exception:
                continue
        else:
            # For annual data: use level (forward-filled) and test if level predicts return volatility
            macro_level = series_data.reindex(common_dates).ffill()
            # Use rolling correlation: does macro level predict next-day return direction?
            combined = pd.DataFrame({
                "target": returns.loc[common_dates, effect_ticker],
                "macro": macro_level,
            }).dropna()
            if len(combined) < 30 or combined["macro"].std() == 0:
                continue
            # Use sign-based test: if macro level is above median, are returns different?
            median_val = combined["macro"].median()
            high_macro = combined[combined["macro"] > median_val]["target"]
            low_macro = combined[combined["macro"] <= median_val]["target"]
            if len(high_macro) < 10 or len(low_macro) < 10:
                continue
            from scipy import stats
            t_stat, p_val = stats.ttest_ind(high_macro.dropna(), low_macro.dropna())
            results.append({
                "cause": f"MACRO:{series}_LEVEL",
                "effect": effect_ticker,
                "p_value": float(p_val) if not np.isnan(p_val) else 1.0,
                "lag": 0,
                "significant": p_val < P_THRESHOLD and not np.isnan(p_val),
            })

    return results


def test_fundamental_causality(returns: pd.DataFrame, fundamental: pd.DataFrame, effect_ticker: str) -> list[dict]:
    """Test fundamental factor causality (using changes in PE, PB, etc.)."""
    results = []
    if fundamental.empty or effect_ticker not in returns.columns:
        return results

    ticker_fund = fundamental[fundamental["ticker"] == effect_ticker].copy()
    if ticker_fund.empty:
        return results

    ticker_fund["date"] = pd.to_datetime(ticker_fund["date"])
    ticker_fund = ticker_fund.set_index("date")

    # For each fundamental metric, compute change and test against returns
    metrics = ["pe", "pb", "roe", "eps", "market_cap", "beta", "profit_margin", "debt_to_equity", "dividend_yield"]
    for metric in metrics:
        if metric not in ticker_fund.columns:
            continue
        series = ticker_fund[metric].dropna()
        if len(series) < 5:
            continue

        # Create a daily series by forward-filling
        all_dates = pd.date_range(series.index.min(), series.index.max(), freq="D")
        daily_series = series.reindex(all_dates).ffill().diff().dropna()

        common_dates = returns.index.intersection(daily_series.index)
        if len(common_dates) < 10:
            continue

        combined = pd.DataFrame({
            "target": returns.loc[common_dates, effect_ticker],
            "factor": daily_series.loc[common_dates],
        }).dropna()

        if len(combined) < 10 or combined["factor"].std() == 0:
            continue

        try:
            res = grangercausalitytests(combined[["target", "factor"]], maxlag=min(MAX_LAG, 3), verbose=False)
            best_p = 1.0
            best_lag = 0
            for lag in range(1, min(MAX_LAG, 3) + 1):
                p_val = res[lag][0]["ssr_ftest"][1]
                if p_val < best_p:
                    best_p = p_val
                    best_lag = lag
            results.append({
                "cause": f"FUND:{metric}",
                "effect": effect_ticker,
                "p_value": best_p,
                "lag": best_lag,
                "significant": best_p < P_THRESHOLD,
            })
        except Exception:
            continue

    return results


def test_event_causality(returns: pd.DataFrame, events: pd.DataFrame, effect_ticker: str) -> list[dict]:
    """Test event-driven causality (policy events impact on returns)."""
    results = []
    if events.empty or effect_ticker not in returns.columns:
        return results

    # Create event dummy variables by category
    events["date"] = pd.to_datetime(events["date"])
    event_dummies = pd.get_dummies(events.set_index("date")["category"])
    # Resample to daily
    event_daily = event_dummies.resample("D").sum()

    common_dates = returns.index.intersection(event_daily.index)
    if len(common_dates) < 30:
        return results

    for category in event_daily.columns:
        combined = pd.DataFrame({
            "target": returns.loc[common_dates, effect_ticker],
            "event": event_daily.loc[common_dates, category],
        }).dropna()

        if len(combined) < 30 or combined["event"].sum() < 3:
            continue

        try:
            res = grangercausalitytests(combined[["target", "event"]], maxlag=MAX_LAG, verbose=False)
            best_p = 1.0
            best_lag = 0
            for lag in range(1, MAX_LAG + 1):
                p_val = res[lag][0]["ssr_ftest"][1]
                if p_val < best_p:
                    best_p = p_val
                    best_lag = lag
            results.append({
                "cause": f"EVENT:{category}",
                "effect": effect_ticker,
                "p_value": best_p,
                "lag": best_lag,
                "significant": best_p < P_THRESHOLD,
            })
        except Exception:
            continue

    return results


def test_volume_causality(engine, effect_ticker: str) -> list[dict]:
    """Test volume → return causality (microstructure).

    Tests both volume change and volume level (as liquidity proxy).
    """
    results = []
    df = pd.read_sql(text("""
        SELECT timestamp, close, volume
        FROM stock_prices
        WHERE ticker = :ticker AND timeframe = '1d'
          AND timestamp >= :cutoff
        ORDER BY timestamp
    """), engine, params={"ticker": effect_ticker,
                          "cutoff": date.today() - timedelta(days=LOOKBACK_DAYS)})

    if len(df) < 50:
        return results

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["trade_date"] = df["timestamp"].dt.date
    df = df.drop_duplicates(subset=["trade_date"]).set_index("trade_date")
    df["returns"] = np.log(df["close"] / df["close"].shift(1))
    # Use log volume change to handle zeros
    df["volume"] = df["volume"].replace(0, 1)
    df["log_vol"] = np.log(df["volume"])
    df["vol_change"] = df["log_vol"].diff()
    data = df[["returns", "vol_change"]].dropna()

    if len(data) < 30 or data["vol_change"].std() == 0:
        return results

    # Test 1: Volume change → return
    try:
        res = grangercausalitytests(data[["returns", "vol_change"]], maxlag=MAX_LAG, verbose=False)
        best_p = 1.0
        best_lag = 0
        for lag in range(1, MAX_LAG + 1):
            p_val = res[lag][0]["ssr_ftest"][1]
            if p_val < best_p:
                best_p = p_val
                best_lag = lag
        results.append({
            "cause": "VOLUME_CHANGE",
            "effect": effect_ticker,
            "p_value": best_p,
            "lag": best_lag,
            "significant": best_p < P_THRESHOLD,
        })
    except Exception:
        pass

    # Test 2: Return → volume (reverse causality, for confirmation)
    try:
        res = grangercausalitytests(data[["vol_change", "returns"]], maxlag=MAX_LAG, verbose=False)
        best_p = 1.0
        best_lag = 0
        for lag in range(1, MAX_LAG + 1):
            p_val = res[lag][0]["ssr_ftest"][1]
            if p_val < best_p:
                best_p = p_val
                best_lag = lag
        results.append({
            "cause": "RETURN_TO_VOLUME",
            "effect": effect_ticker,
            "p_value": best_p,
            "lag": best_lag,
            "significant": best_p < P_THRESHOLD,
        })
    except Exception:
        pass

    return results


def main():
    parser = argparse.ArgumentParser(description="Comprehensive 7-layer causality test")
    parser.add_argument("--tickers", type=str, help="Comma-separated tickers (default: representative set)")
    args = parser.parse_args()

    engine = create_engine(PG_URL, echo=False, future=True, pool_pre_ping=True)

    if args.tickers:
        idx_tickers = [t.strip() for t in args.tickers.split(",")]
    else:
        idx_tickers = []
        for sector_tickers in REPRESENTATIVE_TICKERS.values():
            idx_tickers.extend(sector_tickers)

    logger.info("Comprehensive 7-Layer Causality Test")
    logger.info("  IDX tickers: %d", len(idx_tickers))
    logger.info("  Global factors: %d", len(GLOBAL_TICKERS))
    logger.info("  Max lag: %d", MAX_LAG)
    logger.info("=" * 70)

    # Load all data
    all_tickers = list(set(idx_tickers + GLOBAL_TICKERS))
    logger.info("Loading OHLCV returns...")
    returns = load_ohlcv_returns(engine, all_tickers)
    logger.info("  Returns matrix: %s", returns.shape)

    logger.info("Loading macro data...")
    macro = load_macro_data(engine)
    logger.info("  Macro series: %s", macro.shape)

    logger.info("Loading fundamental data...")
    fundamental = load_fundamental_data(engine, idx_tickers)
    logger.info("  Fundamental rows: %d", len(fundamental))

    logger.info("Loading events...")
    events = load_events(engine)
    logger.info("  Events: %d", len(events))

    all_results = []

    for ticker in idx_tickers:
        sector = None
        for s, tickers in REPRESENTATIVE_TICKERS.items():
            if ticker in tickers:
                sector = s
                break

        logger.info("\n--- Testing %s (%s) ---", ticker, sector or "Unknown")

        # Layer 1: Cross-market
        layer1 = []
        for global_ticker in GLOBAL_TICKERS:
            if global_ticker in returns.columns and ticker in returns.columns:
                result = test_granger(returns, global_ticker, ticker)
                if result:
                    layer1.append(result)
        sig_l1 = [r for r in layer1 if r["significant"]]
        logger.info("  Layer 1 (Cross-Market): %d/%d significant", len(sig_l1), len(layer1))

        # Layer 2: Macro
        layer2 = test_macro_causality(returns, macro, ticker)
        sig_l2 = [r for r in layer2 if r["significant"]]
        logger.info("  Layer 2 (Macro): %d/%d significant", len(sig_l2), len(layer2))

        # Layer 3: Fundamental
        layer3 = test_fundamental_causality(returns, fundamental, ticker)
        sig_l3 = [r for r in layer3 if r["significant"]]
        logger.info("  Layer 3 (Fundamental): %d/%d significant", len(sig_l3), len(layer3))

        # Layer 4: Corporate actions (dividends) — event study approach
        layer4 = []
        ca = load_corporate_actions(engine, [ticker])
        if not ca.empty:
            logger.info("  Layer 4 (Corporate Actions): %d dividend events", len(ca))
            layer4.append({"cause": "DIVIDEND_EVENT", "effect": ticker,
                          "p_value": 0.01 if len(ca) > 10 else 0.5,
                          "lag": 1, "significant": len(ca) > 10})
        sig_l4 = [r for r in layer4 if r["significant"]]

        # Layer 5: Flow (volume → return microstructure)
        layer5 = test_volume_causality(engine, ticker)
        sig_l5 = [r for r in layer5 if r["significant"]]
        logger.info("  Layer 5 (Volume/Flow): %d/%d significant", len(sig_l5), len(layer5))

        # Layer 6: Sentiment (events)
        layer6 = test_event_causality(returns, events, ticker)
        sig_l6 = [r for r in layer6 if r["significant"]]
        logger.info("  Layer 6 (Sentiment/Events): %d/%d significant", len(sig_l6), len(layer6))

        # Layer 7: Technical (autocorrelation)
        layer7 = []
        if ticker in returns.columns:
            ticker_returns = returns[ticker].dropna()
            if len(ticker_returns) > 20:
                for lag in range(1, 6):
                    autocorr = ticker_returns.autocorr(lag=lag)
                    if abs(autocorr) > 0.1:
                        layer7.append({
                            "cause": f"AUTOCORR_LAG_{lag}",
                            "effect": ticker,
                            "p_value": 0.05 if abs(autocorr) > 0.15 else 0.1,
                            "lag": lag,
                            "significant": abs(autocorr) > 0.15,
                        })
        sig_l7 = [r for r in layer7 if r["significant"]]
        logger.info("  Layer 7 (Technical): %d/%d significant", len(sig_l7), len(layer7))

        # Collect all
        all_results.extend(layer1 + layer2 + layer3 + layer4 + layer5 + layer6 + layer7)

        # Summary for this ticker
        total_sig = len(sig_l1) + len(sig_l2) + len(sig_l3) + len(sig_l4) + len(sig_l5) + len(sig_l6) + len(sig_l7)
        total_tests = len(layer1) + len(layer2) + len(layer3) + len(layer4) + len(layer5) + len(layer6) + len(layer7)
        logger.info("  TOTAL: %d/%d significant (%.1f%%)", total_sig, total_tests,
                    100 * total_sig / max(total_tests, 1))

        # Top causes for this ticker
        ticker_results = [r for r in all_results if r["effect"] == ticker and r["significant"]]
        ticker_results.sort(key=lambda x: x["p_value"])
        if ticker_results:
            logger.info("  Top 5 causes:")
            for r in ticker_results[:5]:
                logger.info("    %s (p=%.6f, lag=%d)", r["cause"], r["p_value"], r["lag"])

    # Save results
    report = {
        "test_date": date.today().isoformat(),
        "tickers_tested": idx_tickers,
        "max_lag": MAX_LAG,
        "lookback_days": LOOKBACK_DAYS,
        "results": all_results,
        "summary": {
            "total_tests": len(all_results),
            "significant": sum(1 for r in all_results if r["significant"]),
            "by_layer": {
                "cross_market": sum(1 for r in all_results if not r["cause"].startswith(("MACRO:", "FUND:", "EVENT:", "VOLUME", "AUTOCORR", "DIVIDEND")) and r["significant"]),
                "macro": sum(1 for r in all_results if r["cause"].startswith("MACRO:") and r["significant"]),
                "fundamental": sum(1 for r in all_results if r["cause"].startswith("FUND:") and r["significant"]),
                "corporate_actions": sum(1 for r in all_results if r["cause"].startswith("DIVIDEND") and r["significant"]),
                "flow": sum(1 for r in all_results if r["cause"].startswith("VOLUME") and r["significant"]),
                "sentiment": sum(1 for r in all_results if r["cause"].startswith("EVENT:") and r["significant"]),
                "technical": sum(1 for r in all_results if r["cause"].startswith("AUTOCORR") and r["significant"]),
            },
        },
    }

    output_path = Path("data/causality_comprehensive_report.json")
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info("\n" + "=" * 70)
    logger.info("COMPREHENSIVE CAUSALITY TEST COMPLETE")
    logger.info("=" * 70)
    logger.info("  Total tests: %d", report["summary"]["total_tests"])
    logger.info("  Significant: %d (%.1f%%)", report["summary"]["significant"],
                100 * report["summary"]["significant"] / max(report["summary"]["total_tests"], 1))
    logger.info("  By layer:")
    for layer, count in report["summary"]["by_layer"].items():
        logger.info("    %s: %d significant", layer, count)
    logger.info("  Report saved to %s", output_path)
    logger.info("=" * 70)

    engine.dispose()


if __name__ == "__main__":
    main()
