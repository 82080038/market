"""Post-Trade Execution Analyzer — slippage, cost analysis, and net alpha attribution.

Adopts QuantConnect Execution Analyzer principles to measure fill quality and
post-cost performance from the ``transaksi_investor`` table (migration 0013).

Metrics computed:
1. **Slippage** — difference between target price (from daily_signal_cron signal)
   and actual fill price (``harga_per_saham``) per transaction.
2. **Net Alpha Attribution** — portfolio net profit after broker fees
   (``biaya_broker``) and PPh Final tax (0.1% on SELL for IDX).
3. **Execution Efficiency** — fill ratio, cost ratio, and timing analysis.

The module is designed to feed results into the Ablation Study pillar of
``scripts/audit_ai_advanced.py`` as a feedback loop for model decay detection.

References:
- QuantConnect Execution Analyzer architecture
- pustaka/52-transaction-cost-analysis-execution-quality.md
- pustaka/26-post-trade-settlement-rekonsiliasi.md
- IDX PPh Final 0.1% on sell transactions (PMK-84/2020)

"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

# IDX PPh Final 0.1% on SELL transactions (PMK-84/2020)
PPh_FINAL_SELL_RATE = 0.001  # 0.1%

# Default broker fee tiers (IDX retail, approximate)
BROKER_FEE_TIER1 = 0.0015  # 0.15% for transactions < 100M IDR
BROKER_FEE_TIER2 = 0.0011  # 0.11% for transactions >= 100M IDR
BROKER_FEE_TIER3 = 0.0008  # 0.08% for transactions >= 1B IDR

# Lot size for IDX
LOT_SIZE = 100


# ── Data Structures ─────────────────────────────────────────────────────────


@dataclass
class SlippageResult:
    """Slippage analysis result for a single transaction.

    Attributes:
        ticker: Instrument ticker symbol.
        tanggal: Transaction date.
        tipe: Transaction type (BUY/SELL).
        target_price: Expected price from signal/cron.
        fill_price: Actual executed price (harga_per_saham).
        slippage_bps: Slippage in basis points (positive = unfavorable).
        slippage_idr: Slippage in IDR per share.
        slippage_total_idr: Total slippage cost in IDR (slippage_idr * shares).
        jumlah_lot: Number of lots traded.
    """

    ticker: str
    tanggal: str
    tipe: str
    target_price: float
    fill_price: float
    slippage_bps: float
    slippage_idr: float
    slippage_total_idr: float
    jumlah_lot: int


@dataclass
class NetAlphaResult:
    """Net alpha attribution result.

    Attributes:
        gross_pnl: Gross profit/loss before costs.
        broker_fees_total: Total broker fees paid.
        pph_final_total: Total PPh Final tax paid.
        net_pnl: Net profit/loss after all costs.
        cost_ratio: Total costs as fraction of gross PnL.
        net_alpha_bps: Net alpha in basis points vs gross.
        n_trades: Number of trades analyzed.
        n_buy: Number of buy trades.
        n_sell: Number of sell trades.
        per_ticker: Dict of per-ticker net PnL breakdown.
    """

    gross_pnl: float
    broker_fees_total: float
    pph_final_total: float
    net_pnl: float
    cost_ratio: float
    net_alpha_bps: float
    n_trades: int
    n_buy: int
    n_sell: int
    per_ticker: dict[str, dict] = field(default_factory=dict)


@dataclass
class ExecutionEfficiencyResult:
    """Execution efficiency summary.

    Attributes:
        avg_slippage_bps: Average slippage across all trades (BPS).
        avg_slippage_buy_bps: Average slippage for BUY trades.
        avg_slippage_sell_bps: Average slippage for SELL trades.
        fill_rate: Fraction of orders with status 'FILLED'.
        cost_ratio_pct: Total cost as percentage of traded value.
        worst_slippage_bps: Worst single-trade slippage.
        best_slippage_bps: Best single-trade slippage.
        n_trades: Total trades analyzed.
    """

    avg_slippage_bps: float
    avg_slippage_buy_bps: float
    avg_slippage_sell_bps: float
    fill_rate: float
    cost_ratio_pct: float
    worst_slippage_bps: float
    best_slippage_bps: float
    n_trades: int


# ── Core Functions ──────────────────────────────────────────────────────────


def load_transactions(
    session: "Session",
    ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """Load transaction data from ``transaksi_investor`` table.

    Joins with ``instrumen`` and ``emiten`` to resolve ticker symbols.

    Args:
        session: SQLAlchemy session.
        ticker: Optional ticker filter (e.g. "BBCA.JK").
        start_date: Optional start date (ISO format).
        end_date: Optional end date (ISO format).

    Returns:
        DataFrame with columns: [id_transaksi, tanggal, ticker, tipe, jumlah_lot,
        harga_per_saham, biaya_broker, pajak_pph_final, status_eksekusi].
    """
    from sqlalchemy import text

    query = """
        SELECT ti.id_transaksi, ti.tanggal_transaksi, e.kode_ticker AS ticker,
               ti.tipe_transaksi, ti.jumlah_lot, ti.harga_per_saham,
               ti.biaya_broker, ti.pajak_pph_final, ti.status_eksekusi
        FROM transaksi_investor ti
        JOIN instrumen i ON ti.id_instrumen = i.id_instrumen
        JOIN emiten e ON i.id_emiten = e.id_emiten
        WHERE 1=1
    """
    params: dict = {}

    if ticker:
        query += " AND e.kode_ticker = :ticker"
        params["ticker"] = ticker
    if start_date:
        query += " AND ti.tanggal_transaksi >= :start_date"
        params["start_date"] = start_date
    if end_date:
        query += " AND ti.tanggal_transaksi <= :end_date"
        params["end_date"] = end_date

    query += " ORDER BY ti.tanggal_transaksi"

    result = session.execute(text(query), params)
    rows = result.fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "id_transaksi", "tanggal", "ticker", "tipe", "jumlah_lot",
        "harga_per_saham", "biaya_broker", "pajak_pph_final", "status_eksekusi",
    ])
    df["tanggal"] = pd.to_datetime(df["tanggal"])
    df["harga_per_saham"] = df["harga_per_saham"].astype(float)
    df["biaya_broker"] = df["biaya_broker"].astype(float)
    df["pajak_pph_final"] = df["pajak_pph_final"].astype(float)
    df["jumlah_lot"] = df["jumlah_lot"].astype(int)
    return df


def load_target_prices(
    session: "Session",
    tickers: list[str],
    dates: list[str],
) -> dict[str, dict[str, float]]:
    """Load target prices from daily_signal_cron output.

    Looks up the ``daily_prices`` table for close prices on signal dates
    to use as target (expected) prices for slippage calculation.

    Args:
        session: SQLAlchemy session.
        tickers: List of ticker symbols.
        dates: List of date strings (ISO format).

    Returns:
        Nested dict: {ticker: {date: close_price}}.
    """
    from sqlalchemy import text

    if not tickers or not dates:
        return {}

    placeholders_t = ",".join(f":t{i}" for i in range(len(tickers)))
    placeholders_d = ",".join(f":d{i}" for i in range(len(dates)))

    query = f"""
        SELECT ticker, date, close FROM daily_prices
        WHERE ticker IN ({placeholders_t})
        AND date IN ({placeholders_d})
        AND timeframe = '1d'
    """
    params = {}
    for i, t in enumerate(tickers):
        params[f"t{i}"] = t
    for i, d in enumerate(dates):
        params[f"d{i}"] = d

    result = session.execute(text(query), params)
    target_map: dict[str, dict[str, float]] = {}
    for row in result.fetchall():
        tk, dt, close = row[0], str(row[1]), float(row[2])
        target_map.setdefault(tk, {})[dt] = close

    return target_map


def compute_slippage(
    transactions: pd.DataFrame,
    target_prices: dict[str, dict[str, float]] | None = None,
) -> list[SlippageResult]:
    """Compute slippage for each transaction.

    Slippage = (fill_price - target_price) / target_price * 10000 (in BPS).
    For BUY: positive slippage = paid more than target (unfavorable).
    For SELL: positive slippage = received less than target (unfavorable).

    Args:
        transactions: DataFrame from ``load_transactions``.
        target_prices: Optional nested dict {ticker: {date: price}}.
            If None, uses previous day's close as target.

    Returns:
        List of SlippageResult per transaction.
    """
    if transactions.empty:
        return []

    results: list[SlippageResult] = []
    sorted_tx = transactions.sort_values("tanggal")

    # Build per-ticker price history for fallback target
    ticker_prices: dict[str, list[tuple[str, float]]] = {}
    for _, row in sorted_tx.iterrows():
        tk = row["ticker"]
        ticker_prices.setdefault(tk, []).append(
            (str(row["tanggal"].date()), row["harga_per_saham"])
        )

    for _, row in sorted_tx.iterrows():
        tk = row["ticker"]
        tanggal = str(row["tanggal"].date())
        fill_price = float(row["harga_per_saham"])
        tipe = str(row["tipe"]).upper()
        jumlah_lot = int(row["jumlah_lot"])

        # Resolve target price
        target_price = None
        if target_prices and tk in target_prices:
            target_price = target_prices[tk].get(tanggal)

        if target_price is None:
            # Fallback: use previous transaction's price for same ticker
            prices = ticker_prices.get(tk, [])
            idx = next(
                (i for i, (d, _) in enumerate(prices) if d == tanggal),
                len(prices),
            )
            if idx > 0:
                target_price = prices[idx - 1][1]
            else:
                target_price = fill_price  # No reference → zero slippage

        if target_price > 0:
            slippage_idr = fill_price - target_price
            if tipe == "SELL":
                slippage_idr = target_price - fill_price  # SELL: lower fill is worse
            slippage_bps = (slippage_idr / target_price) * 10000
        else:
            slippage_idr = 0.0
            slippage_bps = 0.0

        shares = jumlah_lot * LOT_SIZE
        slippage_total = slippage_idr * shares

        results.append(SlippageResult(
            ticker=tk,
            tanggal=tanggal,
            tipe=tipe,
            target_price=round(target_price, 4),
            fill_price=round(fill_price, 4),
            slippage_bps=round(slippage_bps, 2),
            slippage_idr=round(slippage_idr, 4),
            slippage_total_idr=round(slippage_total, 2),
            jumlah_lot=jumlah_lot,
        ))

    return results


def compute_net_alpha(transactions: pd.DataFrame) -> NetAlphaResult:
    """Compute net alpha attribution after broker fees and PPh Final tax.

    Calculates:
    - Gross PnL: sum of (SELL value - BUY value) per ticker
    - Broker fees: sum of ``biaya_broker`` column
    - PPh Final: sum of ``pajak_pph_final`` column (0.1% on SELL for IDX)
    - Net PnL: Gross - fees - tax
    - Net Alpha BPS: (Net PnL / Gross traded value) * 10000

    Args:
        transactions: DataFrame from ``load_transactions``.

    Returns:
        NetAlphaResult with full breakdown.
    """
    if transactions.empty:
        return NetAlphaResult(
            gross_pnl=0.0, broker_fees_total=0.0, pph_final_total=0.0,
            net_pnl=0.0, cost_ratio=0.0, net_alpha_bps=0.0,
            n_trades=0, n_buy=0, n_sell=0,
        )

    df = transactions.copy()
    df["trade_value"] = df["harga_per_saham"] * df["jumlah_lot"] * LOT_SIZE
    df["tipe_upper"] = df["tipe"].str.upper()

    # Per-ticker PnL: match BUYs with SELLs
    per_ticker: dict[str, dict] = {}
    for tk in df["ticker"].unique():
        tk_df = df[df["ticker"] == tk].sort_values("tanggal")
        buy_value = tk_df[tk_df["tipe_upper"] == "BUY"]["trade_value"].sum()
        sell_value = tk_df[tk_df["tipe_upper"] == "SELL"]["trade_value"].sum()
        buy_fees = tk_df[tk_df["tipe_upper"] == "BUY"]["biaya_broker"].sum()
        sell_fees = tk_df[tk_df["tipe_upper"] == "SELL"]["biaya_broker"].sum()
        buy_tax = tk_df[tk_df["tipe_upper"] == "BUY"]["pajak_pph_final"].sum()
        sell_tax = tk_df[tk_df["tipe_upper"] == "SELL"]["pajak_pph_final"].sum()
        gross = sell_value - buy_value
        fees = buy_fees + sell_fees
        tax = buy_tax + sell_tax
        net = gross - fees - tax
        per_ticker[tk] = {
            "gross_pnl": round(float(gross), 2),
            "broker_fees": round(float(fees), 2),
            "pph_final": round(float(tax), 2),
            "net_pnl": round(float(net), 2),
            "n_trades": len(tk_df),
        }

    # Aggregate
    gross_pnl = float(df[df["tipe_upper"] == "SELL"]["trade_value"].sum() -
                       df[df["tipe_upper"] == "BUY"]["trade_value"].sum())
    broker_fees_total = float(df["biaya_broker"].sum())
    pph_final_total = float(df["pajak_pph_final"].sum())
    net_pnl = gross_pnl - broker_fees_total - pph_final_total

    total_traded_value = float(df["trade_value"].sum())
    cost_ratio = (broker_fees_total + pph_final_total) / total_traded_value if total_traded_value > 0 else 0.0
    net_alpha_bps = (net_pnl / total_traded_value) * 10000 if total_traded_value > 0 else 0.0

    n_buy = int((df["tipe_upper"] == "BUY").sum())
    n_sell = int((df["tipe_upper"] == "SELL").sum())

    return NetAlphaResult(
        gross_pnl=round(gross_pnl, 2),
        broker_fees_total=round(broker_fees_total, 2),
        pph_final_total=round(pph_final_total, 2),
        net_pnl=round(net_pnl, 2),
        cost_ratio=round(cost_ratio, 6),
        net_alpha_bps=round(net_alpha_bps, 2),
        n_trades=len(df),
        n_buy=n_buy,
        n_sell=n_sell,
        per_ticker=per_ticker,
    )


def compute_execution_efficiency(
    slippage_results: list[SlippageResult],
    transactions: pd.DataFrame,
) -> ExecutionEfficiencyResult:
    """Compute execution efficiency summary from slippage results.

    Args:
        slippage_results: List of SlippageResult from ``compute_slippage``.
        transactions: Original transactions DataFrame for fill rate calc.

    Returns:
        ExecutionEfficiencyResult with aggregate metrics.
    """
    if not slippage_results:
        return ExecutionEfficiencyResult(
            avg_slippage_bps=0.0, avg_slippage_buy_bps=0.0,
            avg_slippage_sell_bps=0.0, fill_rate=0.0,
            cost_ratio_pct=0.0, worst_slippage_bps=0.0,
            best_slippage_bps=0.0, n_trades=0,
        )

    slip_bps = [r.slippage_bps for r in slippage_results]
    buy_bps = [r.slippage_bps for r in slippage_results if r.tipe == "BUY"]
    sell_bps = [r.slippage_bps for r in slippage_results if r.tipe == "SELL"]

    # Fill rate
    if not transactions.empty:
        filled = (transactions["status_eksekusi"].str.upper() == "FILLED").sum()
        fill_rate = float(filled) / len(transactions)
    else:
        fill_rate = 0.0

    # Cost ratio
    if not transactions.empty:
        total_value = (transactions["harga_per_saham"].astype(float) *
                       transactions["jumlah_lot"].astype(int) * LOT_SIZE).sum()
        total_cost = transactions["biaya_broker"].astype(float).sum() + \
                     transactions["pajak_pph_final"].astype(float).sum()
        cost_ratio_pct = (total_cost / total_value * 100) if total_value > 0 else 0.0
    else:
        cost_ratio_pct = 0.0

    return ExecutionEfficiencyResult(
        avg_slippage_bps=round(float(np.mean(slip_bps)), 2),
        avg_slippage_buy_bps=round(float(np.mean(buy_bps)) if buy_bps else 0.0, 2),
        avg_slippage_sell_bps=round(float(np.mean(sell_bps)) if sell_bps else 0.0, 2),
        fill_rate=round(fill_rate, 4),
        cost_ratio_pct=round(float(cost_ratio_pct), 4),
        worst_slippage_bps=round(float(max(slip_bps)), 2),
        best_slippage_bps=round(float(min(slip_bps)), 2),
        n_trades=len(slippage_results),
    )


def run_full_analysis(
    session: "Session",
    ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Run full post-trade execution analysis.

    Combines slippage, net alpha, and execution efficiency into a single
    report dict suitable for injection into audit_ai_advanced ablation study.

    Args:
        session: SQLAlchemy session.
        ticker: Optional ticker filter.
        start_date: Optional start date.
        end_date: Optional end date.

    Returns:
        Dict with keys: 'slippage', 'net_alpha', 'execution_efficiency',
        'transactions_count', 'model_decay_signal'.
    """
    tx = load_transactions(session, ticker=ticker, start_date=start_date, end_date=end_date)

    if tx.empty:
        logger.info("Execution Analyzer: no transactions found")
        return {
            "slippage": [],
            "net_alpha": None,
            "execution_efficiency": None,
            "transactions_count": 0,
            "model_decay_signal": "no_data",
        }

    logger.info("Execution Analyzer: %d transactions loaded", len(tx))

    # Load target prices from daily_prices
    tickers = tx["ticker"].unique().tolist()
    dates = [str(d.date()) for d in tx["tanggal"].unique()]
    target_prices = load_target_prices(session, tickers, dates)

    # Compute slippage
    slip_results = compute_slippage(tx, target_prices)
    logger.info("  Slippage: %d trades analyzed, avg %.2f BPS",
                len(slip_results),
                np.mean([r.slippage_bps for r in slip_results]) if slip_results else 0.0)

    # Compute net alpha
    net_alpha = compute_net_alpha(tx)
    logger.info("  Net Alpha: gross=%.0f, fees=%.0f, tax=%.0f, net=%.0f, alpha=%.2f BPS",
                net_alpha.gross_pnl, net_alpha.broker_fees_total,
                net_alpha.pph_final_total, net_alpha.net_pnl, net_alpha.net_alpha_bps)

    # Compute execution efficiency
    eff = compute_execution_efficiency(slip_results, tx)
    logger.info("  Efficiency: fill_rate=%.1f%%, cost_ratio=%.3f%%",
                eff.fill_rate * 100, eff.cost_ratio_pct)

    # Model decay signal: if average slippage is consistently high (>50 BPS),
    # it may indicate model predictions are stale or market conditions shifted
    if eff.avg_slippage_bps > 50:
        decay_signal = "high_slippage_decay"
    elif eff.avg_slippage_bps > 20:
        decay_signal = "moderate_slippage"
    else:
        decay_signal = "healthy"

    return {
        "slippage": [
            {
                "ticker": r.ticker, "tanggal": r.tanggal, "tipe": r.tipe,
                "target_price": r.target_price, "fill_price": r.fill_price,
                "slippage_bps": r.slippage_bps,
                "slippage_total_idr": r.slippage_total_idr,
            }
            for r in slip_results
        ],
        "net_alpha": {
            "gross_pnl": net_alpha.gross_pnl,
            "broker_fees_total": net_alpha.broker_fees_total,
            "pph_final_total": net_alpha.pph_final_total,
            "net_pnl": net_alpha.net_pnl,
            "cost_ratio": net_alpha.cost_ratio,
            "net_alpha_bps": net_alpha.net_alpha_bps,
            "n_trades": net_alpha.n_trades,
            "n_buy": net_alpha.n_buy,
            "n_sell": net_alpha.n_sell,
            "per_ticker": net_alpha.per_ticker,
        },
        "execution_efficiency": {
            "avg_slippage_bps": eff.avg_slippage_bps,
            "avg_slippage_buy_bps": eff.avg_slippage_buy_bps,
            "avg_slippage_sell_bps": eff.avg_slippage_sell_bps,
            "fill_rate": eff.fill_rate,
            "cost_ratio_pct": eff.cost_ratio_pct,
            "worst_slippage_bps": eff.worst_slippage_bps,
            "best_slippage_bps": eff.best_slippage_bps,
            "n_trades": eff.n_trades,
        },
        "transactions_count": len(tx),
        "model_decay_signal": decay_signal,
    }
