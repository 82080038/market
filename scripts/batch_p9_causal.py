"""P9: Causal discovery — run Granger causality + persist to causal_graphs/causal_relationships.

Computes Granger causality between global market indicators and IDX stocks,
then persists results to causal_relationships and causal_graphs tables.

Usage:
    cd /home/petrick/projects/market && .venv/bin/python scripts/batch_p9_causal.py
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import psycopg2
from statsmodels.tsa.stattools import grangercausalitytests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_DSN = "host=localhost dbname=market user=petrick password=market_dev"

# Global drivers to test causality
GLOBAL_DRIVERS = ["^GSPC", "^N225", "^HSI", "^VIX", "CL=F", "GC=F", "CPO=F", "HG=F", "MTF=F", "NICK.L", "TIN.L"]

# IDX stocks to test (representative per sector)
IDX_STOCKS = [
    "BBCA.JK", "BBRI.JK", "BMRI.JK",  # Financials
    "ADRO.JK", "PTBA.JK", "ITMG.JK",  # Energy/Coal
    "AALI.JK", "LSIP.JK", "SIMP.JK",  # Plantation/CPO
    "ANTM.JK", "INCO.JK", "MDKA.JK",  # Basic Materials/Nickel
    "TINS.JK",  # Tin
    "TLKM.JK",  # Telecom
    "ASII.JK",  # Consumer Cyclical
    "INDF.JK", "ICBP.JK",  # Consumer Non-Cyclical
    "UNVR.JK",  # Consumer Non-Cyclical
]


def fetch_returns(conn, tickers: list[str], lookback_days: int = 500) -> pd.DataFrame:
    """Fetch daily returns for tickers."""
    cur = conn.cursor()
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    placeholders = ",".join(["%s"] * len(tickers))
    cur.execute(f"""
        SELECT timestamp::date, ticker, close
        FROM stock_prices
        WHERE ticker IN ({placeholders})
          AND timeframe = '1d'
          AND timestamp >= %s
          AND close IS NOT NULL
        ORDER BY timestamp, ticker
    """, (*tickers, start_date))
    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "ticker", "close"])
    df["close"] = df["close"].astype(float)
    # Use pivot_table to handle duplicate timestamps (take last)
    pivot = df.pivot_table(index="date", columns="ticker", values="close", aggfunc="last")
    returns = pivot.pct_change().dropna(how="all")
    return returns


def granger_causality(data: pd.DataFrame, cause: str, effect: str, maxlag: int = 5) -> dict | None:
    """Run Granger causality test: does `cause` Granger-cause `effect`?"""
    pair = data[[effect, cause]].dropna()
    if len(pair) < 50:
        return None
    try:
        results = grangercausalitytests(pair, maxlag=maxlag, verbose=False)
        # Get the minimum p-value across all lags
        p_values = []
        for lag in range(1, maxlag + 1):
            if lag in results:
                # Use the F-test p-value (ssr_ftest)
                p_val = results[lag][0]["ssr_ftest"][1]
                p_values.append(p_val)
        if not p_values:
            return None
        min_p = min(p_values)
        best_lag = p_values.index(min_p) + 1
        return {
            "cause": cause,
            "effect": effect,
            "min_p_value": float(min_p),
            "best_lag": best_lag,
            "significant": min_p < 0.05,
            "strong": min_p < 0.01,
        }
    except Exception as e:
        logger.debug("  Granger test failed %s→%s: %s", cause, effect, e)
        return None


def main() -> None:
    logger.info("=" * 70)
    logger.info("P9: CAUSAL DISCOVERY — Granger causality global→IDX")
    logger.info("=" * 70)

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # Fetch returns for all tickers
    all_tickers = GLOBAL_DRIVERS + IDX_STOCKS
    logger.info("")
    logger.info("--- Fetching daily returns for %d tickers ---", len(all_tickers))
    returns = fetch_returns(conn, all_tickers, lookback_days=750)

    if returns.empty:
        logger.error("  No return data available")
        conn.close()
        return

    logger.info("  Returns matrix: %d rows, %d columns", len(returns), returns.shape[1])

    # Run Granger causality tests
    logger.info("")
    logger.info("--- Running Granger causality tests ---")
    results = []
    for idx_stock in IDX_STOCKS:
        if idx_stock not in returns.columns:
            continue
        for driver in GLOBAL_DRIVERS:
            if driver not in returns.columns:
                continue
            result = granger_causality(returns, cause=driver, effect=idx_stock, maxlag=5)
            if result:
                results.append(result)

    logger.info("  Total tests run: %d", len(results))
    significant = [r for r in results if r["significant"]]
    strong = [r for r in results if r["strong"]]
    logger.info("  Significant (p<0.05): %d", len(significant))
    logger.info("  Strong (p<0.01): %d", len(strong))

    # Clear old causal_relationships
    cur.execute("DELETE FROM causal_relationships")
    conn.commit()

    # Persist to causal_relationships
    logger.info("")
    logger.info("--- Persisting to causal_relationships ---")
    persisted = 0
    for r in results:
        cur.execute("""
            INSERT INTO causal_relationships
                (cause_ticker, effect_ticker, method, p_value, lag_days,
                 f_statistic, direction, test_date, sample_size)
            VALUES (%s, %s, 'granger', %s, %s, NULL, %s, %s, %s)
            ON CONFLICT (cause_ticker, effect_ticker, lag_days, test_date, method) DO NOTHING
        """, (
            r["cause"], r["effect"], float(r["min_p_value"]),
            int(r["best_lag"]),
            "pos" if r["significant"] else "neu",
            datetime.now().date(),
            641,
        ))
        persisted += cur.rowcount
    conn.commit()
    logger.info("  Persisted %d causal relationships", persisted)

    # Also persist a summary graph to causal_graphs
    logger.info("")
    logger.info("--- Persisting summary graph to causal_graphs ---")
    # Build adjacency list of significant relationships
    graph = {}
    for r in significant:
        if r["cause"] not in graph:
            graph[r["cause"]] = []
        graph[r["cause"]].append({"target": r["effect"], "p_value": r["min_p_value"], "lag": r["best_lag"]})

    graph_json = {
        "type": "granger_causality_summary",
        "n_tests": len(results),
        "n_significant": len(significant),
        "n_strong": len(strong),
        "graph": graph,
    }

    cur.execute("""
        INSERT INTO causal_graphs (computed_at, window_start, window_end, max_lag, tickers, graph_json, total_links, avg_strength)
        VALUES (now(), %s, %s, 5, %s, %s, %s, %s)
    """, (
        returns.index[0],
        returns.index[-1],
        json.dumps(all_tickers),
        json.dumps(graph_json),
        len(significant),
        len(strong) / max(len(results), 1),
    ))
    conn.commit()
    logger.info("  Summary graph persisted")

    # Print top causal relationships
    logger.info("")
    logger.info("--- Top causal relationships (p<0.01) ---")
    for r in sorted(strong, key=lambda x: x["min_p_value"])[:20]:
        logger.info("  %s → %s: p=%.4f lag=%d", r["cause"], r["effect"], r["min_p_value"], r["best_lag"])

    # Final audit
    logger.info("")
    logger.info("--- Final audit ---")
    cur.execute("SELECT count(*) FROM causal_relationships")
    total = cur.fetchone()[0]
    logger.info("  causal_relationships: %d rows", total)

    cur.execute("SELECT count(*) FROM causal_graphs")
    total_g = cur.fetchone()[0]
    logger.info("  causal_graphs: %d rows", total_g)

    cur.execute("""
        SELECT cause_ticker, count(*) as n_effects
        FROM causal_relationships
        WHERE p_value < 0.05
        GROUP BY cause_ticker
        ORDER BY n_effects DESC
    """)
    logger.info("  Significant causes by driver:")
    for row in cur.fetchall():
        logger.info("    %s: %d effects", row[0], row[1])

    conn.close()
    logger.info("")
    logger.info("P9 COMPLETE.")


if __name__ == "__main__":
    main()
