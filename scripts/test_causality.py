"""Comprehensive cross-market causality test.

Tests Granger causality between IDX sector/categories and global markets:
- ^GSPC (S&P 500), ^N225 (Nikkei), ^HSI (Hang Seng), ^FTSE, ^GDAXI, ^VIX
- GC=F (Gold), CL=F (Oil), IDR=X (USD/IDR)
- IDX sectors: BBCA.JK (Financial), TLKM.JK (Telecom), UNVR.JK (Consumer),
  ADRO.JK (Energy), INCO.JK (Basic Materials), GOTO.JK (Tech)

Uses daily returns from PostgreSQL stock_prices table (TIMESTAMPTZ, market close aligned).

Output: JSON report + console summary.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from statsmodels.tsa.stattools import grangercausalitytests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PG_URL = "postgresql://petrick:market_dev@localhost:5432/market"

# Global reference tickers — expanded with causal factors
GLOBAL_TICKERS = [
    # US indices
    "^GSPC", "^DJI", "^IXIC", "^VIX", "^TNX", "^IRX",
    # Asia-Pacific indices
    "^N225", "^HSI", "000001.SS", "^KS11", "^STI", "^KLSE", "^AXJO", "^BSESN",
    # Europe indices
    "^FTSE", "^GDAXI",
    # FX pairs
    "IDR=X", "EURIDR=X", "JPYIDR=X", "SGDIDR=X", "DX-Y.NYB",
    # Commodities
    "GC=F", "CL=F", "BZ=F", "NG=F", "HG=F", "SI=F", "CPO=F",
    # Sector ETFs
    "XLE", "DBA",
]

# IDX sector representatives
IDX_SECTORS = {
    "Financial Services": ["BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK"],
    "Telecommunication": ["TLKM.JK", "ISAT.JK", "EXCL.JK"],
    "Consumer Defensive": ["UNVR.JK", "INDF.JK", "ICBP.JK"],
    "Energy": ["ADRO.JK", "PTBA.JK", "MEDC.JK"],
    "Basic Materials": ["INCO.JK", "ANTM.JK", "TINS.JK"],
    "Technology": ["GOTO.JK", "EMTK.JK", "BUKA.JK"],
    "Industrial": ["UNTR.JK", "WIKA.JK", "PTWS.JK"],
    "Healthcare": ["KLBF.JK", "INAF.JK", "DVLA.JK"],
    "Property": ["CTRA.JK", "LPKR.JK", "ASRI.JK"],
    "Infrastructure": ["ACST.JK", "WSBP.JK", "TOTL.JK"],
}

MAX_LAG = 5
LOOKBACK_DAYS = 500


def load_daily_returns(engine, tickers: list[str], lookback_days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Load daily close prices and compute log returns.

    Timestamps are normalized to trading DATE (not exact close time) so that
    different markets (IDX 08:50 UTC, NYSE 20:00 UTC, etc.) can be aligned
    on the same trading day for cross-market analysis.
    """
    cutoff = date.today() - timedelta(days=lookback_days)
    query = text("""
        SELECT ticker, timestamp, close
        FROM stock_prices
        WHERE ticker = ANY(:tickers)
          AND timeframe = '1d'
          AND timestamp >= :cutoff
        ORDER BY ticker, timestamp
    """)
    df = pd.read_sql(query, engine, params={"tickers": tickers, "cutoff": cutoff})
    if df.empty:
        return pd.DataFrame()

    # Normalize timestamp to trading date (UTC date, ignoring time component)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["trade_date"] = df["timestamp"].dt.date

    # Pivot: rows=trade_date, columns=ticker, values=close
    pivot = df.pivot_table(index="trade_date", columns="ticker", values="close")
    pivot = pivot.sort_index()

    # Log returns
    returns = np.log(pivot / pivot.shift(1)).dropna(how="all")
    return returns


def granger_test(data: pd.DataFrame, cause: str, effect: str, maxlag: int = MAX_LAG) -> dict:
    """Run Granger causality test: does `cause` Granger-cause `effect`?

    Returns dict with F-test p-values for each lag.
    """
    pair = data[[effect, cause]].dropna()
    if len(pair) < 30:
        return {"error": f"Insufficient data: {len(pair)} rows"}

    try:
        results = grangercausalitytests(pair, maxlag=maxlag, verbose=False)
        p_values = {}
        for lag in range(1, maxlag + 1):
            # F-test p-value (ssr_ftest)
            p_val = results[lag][0]["ssr_ftest"][1]
            p_values[f"lag_{lag}"] = round(p_val, 6)

        # Find minimum p-value and corresponding lag
        min_p = min(p_values.values())
        min_lag = [k for k, v in p_values.items() if v == min_p][0]

        return {
            "p_values": p_values,
            "min_p_value": round(min_p, 6),
            "best_lag": min_lag,
            "significant": min_p < 0.05,
            "n_obs": len(pair),
        }
    except Exception as e:
        return {"error": str(e)}


def main() -> None:
    engine = create_engine(PG_URL, echo=False, future=True, pool_pre_ping=True)

    # Collect all tickers
    all_global = GLOBAL_TICKERS
    all_idx = [t for tickers in IDX_SECTORS.values() for t in tickers]
    all_tickers = all_global + all_idx

    logger.info("Loading daily returns for %d tickers (%d days lookback)...",
                len(all_tickers), LOOKBACK_DAYS)
    returns = load_daily_returns(engine, all_tickers, LOOKBACK_DAYS)
    engine.dispose()

    logger.info("Returns matrix: %d days x %d tickers", len(returns), returns.shape[1])
    logger.info("Date range: %s to %s", returns.index[0], returns.index[-1])

    # Check data availability
    available = returns.columns.tolist()
    missing = [t for t in all_tickers if t not in available]
    if missing:
        logger.warning("Missing tickers (no data in range): %s", missing)

    # Run Granger causality tests
    results = {
        "metadata": {
            "date_range": [str(returns.index[0]), str(returns.index[-1])],
            "n_observations": len(returns),
            "lookback_days": LOOKBACK_DAYS,
            "max_lag": MAX_LAG,
            "significance_level": 0.05,
        },
        "global_to_idx": {},
        "idx_to_global": {},
        "global_to_global": {},
        "summary": {},
    }

    # Test 1: Global → IDX sectors (does global market cause IDX sector moves?)
    logger.info("\n" + "=" * 70)
    logger.info("TEST 1: Global Markets → IDX Sectors (Granger Causality)")
    logger.info("=" * 70)

    for sector, idx_tickers in IDX_SECTORS.items():
        results["global_to_idx"][sector] = {}
        for idx_ticker in idx_tickers:
            if idx_ticker not in returns.columns:
                continue
            results["global_to_idx"][sector][idx_ticker] = {}
            for global_ticker in GLOBAL_TICKERS:
                if global_ticker not in returns.columns:
                    continue
                res = granger_test(returns, global_ticker, idx_ticker)
                results["global_to_idx"][sector][idx_ticker][global_ticker] = res

                if res.get("significant"):
                    logger.info("  %s → %s: p=%.4f (lag=%s) *",
                                global_ticker, idx_ticker,
                                res["min_p_value"], res["best_lag"])

    # Test 2: IDX sectors → Global (does IDX cause global moves? — unlikely but test)
    logger.info("\n" + "=" * 70)
    logger.info("TEST 2: IDX Sectors → Global Markets (Granger Causality)")
    logger.info("=" * 70)

    for sector, idx_tickers in IDX_SECTORS.items():
        for idx_ticker in idx_tickers:
            if idx_ticker not in returns.columns:
                continue
            results["idx_to_global"].setdefault(sector, {}).setdefault(idx_ticker, {})
            for global_ticker in GLOBAL_TICKERS:
                if global_ticker not in returns.columns:
                    continue
                res = granger_test(returns, idx_ticker, global_ticker)
                results["idx_to_global"][sector][idx_ticker][global_ticker] = res

                if res.get("significant"):
                    logger.info("  %s → %s: p=%.4f (lag=%s) *",
                                idx_ticker, global_ticker,
                                res["min_p_value"], res["best_lag"])

    # Test 3: Global → Global (cross-market causality)
    logger.info("\n" + "=" * 70)
    logger.info("TEST 3: Cross-Market Global Causality")
    logger.info("=" * 70)

    for i, t1 in enumerate(GLOBAL_TICKERS):
        if t1 not in returns.columns:
            continue
        results["global_to_global"][t1] = {}
        for t2 in GLOBAL_TICKERS:
            if t2 not in returns.columns or t1 == t2:
                continue
            res = granger_test(returns, t1, t2)
            results["global_to_global"][t1][t2] = res

            if res.get("significant"):
                logger.info("  %s → %s: p=%.4f (lag=%s) *",
                            t1, t2, res["min_p_value"], res["best_lag"])

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)

    # Count significant relationships
    sig_global_to_idx = 0
    total_global_to_idx = 0
    for sector_data in results["global_to_idx"].values():
        for ticker_data in sector_data.values():
            for res in ticker_data.values():
                if "error" not in res:
                    total_global_to_idx += 1
                    if res.get("significant"):
                        sig_global_to_idx += 1

    sig_idx_to_global = 0
    total_idx_to_global = 0
    for sector_data in results["idx_to_global"].values():
        for ticker_data in sector_data.values():
            for res in ticker_data.values():
                if "error" not in res:
                    total_idx_to_global += 1
                    if res.get("significant"):
                        sig_idx_to_global += 1

    sig_global_to_global = 0
    total_global_to_global = 0
    for ticker_data in results["global_to_global"].values():
        for res in ticker_data.values():
            if "error" not in res:
                total_global_to_global += 1
                if res.get("significant"):
                    sig_global_to_global += 1

    logger.info("  Global → IDX:    %d/%d significant (%.1f%%)",
                sig_global_to_idx, total_global_to_idx,
                100 * sig_global_to_idx / max(total_global_to_idx, 1))
    logger.info("  IDX → Global:    %d/%d significant (%.1f%%)",
                sig_idx_to_global, total_idx_to_global,
                100 * sig_idx_to_global / max(total_idx_to_global, 1))
    logger.info("  Global → Global: %d/%d significant (%.1f%%)",
                sig_global_to_global, total_global_to_global,
                100 * sig_global_to_global / max(total_global_to_global, 1))

    # Top causal relationships
    logger.info("\n--- Top 10 Global→IDX Causal Relationships ---")
    all_pairs = []
    for sector, sector_data in results["global_to_idx"].items():
        for idx_ticker, ticker_data in sector_data.items():
            for global_ticker, res in ticker_data.items():
                if res.get("significant"):
                    all_pairs.append({
                        "cause": global_ticker,
                        "effect": idx_ticker,
                        "sector": sector,
                        "p_value": res["min_p_value"],
                        "lag": res["best_lag"],
                    })
    all_pairs.sort(key=lambda x: x["p_value"])
    for p in all_pairs[:10]:
        logger.info("  %s → %s (%s): p=%.6f, lag=%s",
                    p["cause"], p["effect"], p["sector"], p["p_value"], p["lag"])

    results["summary"] = {
        "global_to_idx_significant": sig_global_to_idx,
        "global_to_idx_total": total_global_to_idx,
        "idx_to_global_significant": sig_idx_to_global,
        "idx_to_global_total": total_idx_to_global,
        "global_to_global_significant": sig_global_to_global,
        "global_to_global_total": total_global_to_global,
        "top_causal_pairs": all_pairs[:20],
    }

    # Save report
    report_path = "data/causality_test_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info("\nReport saved to %s", report_path)

    print("\n" + "=" * 70)
    print("CAUSALITY TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
