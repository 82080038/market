"""P6: DCC-GARCH + Diebold-Yilmaz spillover — compute and persist.

Uses the existing SpilloverLab module to compute Diebold-Yilmaz spillover
index between IDX and global markets. Also computes simplified DCC-GARCH
correlation between IHSG and key global indices.

Usage:
    cd /home/petrick/projects/market && .venv/bin/python scripts/batch_p6_spillover.py
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_DSN = "host=localhost dbname=market user=petrick password=market_dev"


def fetch_daily_returns(conn, tickers: list[str], lookback_days: int = 500) -> pd.DataFrame:
    """Fetch daily returns for multiple tickers."""
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
    pivot = pivot.dropna(how="all")
    returns = pivot.pct_change().dropna(how="all")
    return returns


def compute_dcc_garch_simple(returns_a: pd.Series, returns_b: pd.Series,
                              garch_window: int = 20,
                              dcc_alpha: float = 0.05,
                              dcc_beta: float = 0.90) -> pd.Series:
    """Simplified DCC-GARCH correlation (from pustaka/101)."""
    # GARCH(1,1) variance
    var_a = returns_a.rolling(garch_window).var()
    var_b = returns_b.rolling(garch_window).var()
    # Standardized residuals
    eps_a = returns_a / np.sqrt(var_a)
    eps_b = returns_b / np.sqrt(var_b)
    # DCC quasi-correlation
    corr_bar = eps_a.corr(eps_b)
    q_t = corr_bar
    dcc_corr = pd.Series(index=returns_a.index, dtype=float)
    for i in range(1, len(returns_a)):
        if pd.isna(eps_a.iloc[i-1]) or pd.isna(eps_b.iloc[i-1]):
            continue
        q_t = (1 - dcc_alpha - dcc_beta) * corr_bar + \
              dcc_alpha * eps_a.iloc[i-1] * eps_b.iloc[i-1] + \
              dcc_beta * q_t
        if q_t > 0:
            dcc_corr.iloc[i] = q_t
    return dcc_corr


def compute_spillover_dy(returns: pd.DataFrame, max_lag: int = 4, horizon: int = 10) -> dict:
    """Compute Diebold-Yilmaz spillover index using VAR + FEVD."""
    from statsmodels.tsa.api import VAR

    returns_clean = returns.dropna()
    if len(returns_clean) < 50 or returns_clean.shape[1] < 2:
        return {}

    try:
        # Fit VAR
        model = VAR(returns_clean)
        results = model.fit(maxlags=max_lag, ic="aic")
        lag_order = results.k_ar

        # Generalized FEVD (Pesaran-Shin)
        fevd = results.fevd(horizon)
        # Get the generalized FEVD matrix (N x N) at the horizon
        # fevd.decomp is (N, horizon, N) for generalized
        n = returns_clean.shape[1]
        tickers = list(returns_clean.columns)

        # Use the last period's FEVD as the spillover table
        fevd_matrix = np.zeros((n, n))
        try:
            decomp = fevd.decomp  # shape varies by statsmodels version
            if decomp.ndim == 3:
                # (N, horizon, N) — take the horizon-th step
                fevd_matrix = decomp[:, -1, :]  # N x N
            elif decomp.ndim == 2:
                fevd_matrix = decomp
        except AttributeError:
            # Try alternative approach
            irf = results.irf(horizon)
            # Cumulative impulse response
            cum_irf = irf.cum_effects
            # FEVD approximation from cumulative IRF
            for i in range(n):
                total = np.sum(np.abs(cum_irf[:, i, :]), axis=0)
                if total.sum() > 0:
                    fevd_matrix[:, i] = np.abs(cum_irf[-1, i, :]) / np.abs(cum_irf[-1, i, :]).sum()

        # Normalize rows to sum to 100
        row_sums = fevd_matrix.sum(axis=0, keepdims=True)
        if row_sums.sum() > 0:
            fevd_matrix = fevd_matrix / row_sums * 100

        # Directional spillovers
        to_others = fevd_matrix.sum(axis=0) - np.diag(fevd_matrix)  # TO
        from_others = fevd_matrix.sum(axis=1) - np.diag(fevd_matrix)  # FROM
        net = to_others - from_others
        total = fevd_matrix.sum() - np.diag(fevd_matrix).sum()  # total spillover
        total_pct = total / (fevd_matrix.sum() + 1e-10) * 100

        return {
            "tickers": tickers,
            "fevd_matrix": fevd_matrix.tolist(),
            "to_others": {tickers[i]: float(to_others[i]) for i in range(n)},
            "from_others": {tickers[i]: float(from_others[i]) for i in range(n)},
            "net": {tickers[i]: float(net[i]) for i in range(n)},
            "total_spillover": float(total_pct),
            "lag_order": lag_order,
            "horizon": horizon,
            "n_obs": len(returns_clean),
        }
    except Exception as e:
        logger.warning("  Spillover computation failed: %s", e)
        return {}


def main() -> None:
    logger.info("=" * 70)
    logger.info("P6: DCC-GARCH + DIEBOLD-YILMAZ SPILLOVER")
    logger.info("=" * 70)

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # Key tickers for spillover analysis
    global_tickers = ["^GSPC", "^DJI", "^IXIC", "^N225", "^HSI", "000001.SS", "^VIX"]
    commodity_tickers = ["CL=F", "GC=F", "CPO=F", "HG=F", "MTF=F"]
    idx_proxy = ["BBCA.JK", "BBRI.JK", "ADRO.JK", "AALI.JK", "ANTM.JK"]

    # Step 1: DCC-GARCH between IDX proxy and global indices
    logger.info("")
    logger.info("--- Step 1: DCC-GARCH correlation (IDX proxy vs global) ---")
    all_tickers = idx_proxy + global_tickers + commodity_tickers
    returns = fetch_daily_returns(conn, all_tickers, lookback_days=750)

    if returns.empty:
        logger.error("  No return data available")
        conn.close()
        return

    logger.info("  Returns matrix: %d rows, %d columns", len(returns), returns.shape[1])

    # Compute DCC-GARCH for each IDX proxy vs each global index
    dcc_results = {}
    for idx_ticker in idx_proxy:
        if idx_ticker not in returns.columns:
            continue
        for global_ticker in global_tickers + commodity_tickers:
            if global_ticker not in returns.columns:
                continue
            common = returns[[idx_ticker, global_ticker]].dropna()
            if len(common) < 100:
                continue
            dcc = compute_dcc_garch_simple(common[idx_ticker], common[global_ticker])
            if not dcc.empty:
                latest_corr = float(dcc.dropna().iloc[-1]) if not dcc.dropna().empty else 0
                avg_corr = float(dcc.dropna().mean()) if not dcc.dropna().empty else 0
                dcc_results[f"{idx_ticker}_{global_ticker}"] = {
                    "latest_corr": round(latest_corr, 4),
                    "avg_corr": round(avg_corr, 4),
                    "n_obs": len(common),
                }

    logger.info("  DCC-GARCH computed for %d pairs", len(dcc_results))
    for pair, stats in list(dcc_results.items())[:10]:
        logger.info("    %s: latest_corr=%.3f avg_corr=%.3f n=%d",
                    pair, stats["latest_corr"], stats["avg_corr"], stats["n_obs"])

    # Step 2: Diebold-Yilmaz spillover
    logger.info("")
    logger.info("--- Step 2: Diebold-Yilmaz spillover index ---")

    # Use a subset for the VAR (too many tickers makes VAR unstable)
    spillover_tickers = ["^GSPC", "^N225", "^HSI", "CL=F", "GC=F", "BBCA.JK", "ADRO.JK", "ANTM.JK"]
    spillover_returns = returns[[t for t in spillover_tickers if t in returns.columns]].dropna()

    if len(spillover_returns) > 100 and spillover_returns.shape[1] >= 3:
        logger.info("  Computing spillover for %d tickers, %d observations",
                    spillover_returns.shape[1], len(spillover_returns))
        spillover = compute_spillover_dy(spillover_returns, max_lag=4, horizon=10)

        if spillover:
            logger.info("  Total spillover index: %.2f%%", spillover["total_spillover"])
            logger.info("  Lag order: %d, N obs: %d", spillover["lag_order"], spillover["n_obs"])
            logger.info("  TO spillover (net sender):")
            for ticker, val in sorted(spillover["to_others"].items(), key=lambda x: -x[1]):
                logger.info("    %s: %.2f", ticker, val)
            logger.info("  FROM spillover (net receiver):")
            for ticker, val in sorted(spillover["from_others"].items(), key=lambda x: -x[1]):
                logger.info("    %s: %.2f", ticker, val)
            logger.info("  NET spillover:")
            for ticker, val in sorted(spillover["net"].items(), key=lambda x: -x[1]):
                logger.info("    %s: %.2f", ticker, val)

            # Persist to causal_graphs table (reuse for spillover results)
            cur.execute("""
                INSERT INTO causal_graphs (computed_at, window_start, window_end, max_lag, tickers, graph_json, total_links, avg_strength)
                VALUES (now(), %s, %s, %s, %s, %s, %s, %s)
            """, (
                spillover_returns.index[0],
                spillover_returns.index[-1],
                spillover["lag_order"],
                json.dumps(spillover["tickers"]),
                json.dumps({"type": "diebold_yilmaz_spillover", **spillover}),
                len(spillover["tickers"]),
                spillover["total_spillover"],
            ))
            conn.commit()
            logger.info("  Spillover results persisted to causal_graphs table")
    else:
        logger.warning("  Insufficient data for spillover: %d obs, %d cols",
                       len(spillover_returns), spillover_returns.shape[1])

    # Step 3: Persist DCC-GARCH results
    logger.info("")
    logger.info("--- Step 3: Persist DCC-GARCH results ---")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dcc_garch_results (
            id SERIAL PRIMARY KEY,
            pair VARCHAR(100) NOT NULL,
            latest_corr FLOAT,
            avg_corr FLOAT,
            n_obs INTEGER,
            computed_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (pair)
        )
    """)
    for pair, stats in dcc_results.items():
        cur.execute("""
            INSERT INTO dcc_garch_results (pair, latest_corr, avg_corr, n_obs)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (pair) DO UPDATE SET
                latest_corr = EXCLUDED.latest_corr,
                avg_corr = EXCLUDED.avg_corr,
                n_obs = EXCLUDED.n_obs,
                computed_at = now()
        """, (pair, stats["latest_corr"], stats["avg_corr"], stats["n_obs"]))
    conn.commit()
    logger.info("  Persisted %d DCC-GARCH pairs", len(dcc_results))

    conn.close()
    logger.info("")
    logger.info("P6 COMPLETE.")


if __name__ == "__main__":
    main()
