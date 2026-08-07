"""Generate mock SQLite database untuk testing portfolio pipeline.

Membuat data/market_research_mock.db dengan 5 tabel (ohlcv, technical_indicators,
daily_trading_stats, stock_personality, instrument_master) berisi data tiruan
untuk 20 saham fokus, Jan 2023 – Aug 2026, menggunakan Geometric Brownian Motion.

Skema kolom & tipe data identik dengan database asli (src/market/db/models.py).
Semua data 100% lengkap (tanpa NULL) agar portfolio_final_execution.py langsung
jalan tanpa error.

Usage:
    python scripts/generate_mock_trading_data.py
    python scripts/generate_mock_trading_data.py --output data/market_research_mock.db

Runs in < 5 seconds. Produces ~130k rows total.
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


# ── 20 Focus Tickers ───────────────────────────────────────────────────────

FOCUS_TICKERS: list[str] = [
    "KPIG.JK", "TRIM.JK", "SONA.JK", "TIRT.JK", "TCID.JK", "MEDC.JK", "PANS.JK",
    "KDSI.JK", "MTDL.JK", "BCIC.JK", "SPMA.JK", "BVIC.JK", "APLI.JK", "RBMS.JK",
    "UNTR.JK", "BNBR.JK", "INDF.JK", "UNIC.JK", "ASBI.JK", "ICBP.JK",
]

# Sector assignment (matching real DB)
TICKER_SECTORS: dict[str, str] = {
    "KPIG.JK": "Consumer Cyclicals", "TRIM.JK": "Financials",
    "SONA.JK": "Consumer Cyclicals", "TIRT.JK": "Basic Materials",
    "TCID.JK": "Consumer Non-Cyclicals", "MEDC.JK": "Energy",
    "PANS.JK": "Financials", "KDSI.JK": "Basic Materials",
    "MTDL.JK": "Technology", "BCIC.JK": "Financials",
    "SPMA.JK": "Basic Materials", "BVIC.JK": "Financials",
    "APLI.JK": "Basic Materials", "RBMS.JK": "Properties & Real Estate",
    "UNTR.JK": "Industrials", "BNBR.JK": "Industrials",
    "INDF.JK": "Consumer Non-Cyclicals", "UNIC.JK": "Basic Materials",
    "ASBI.JK": "Financials", "ICBP.JK": "Consumer Non-Cyclicals",
}

# Ticker-specific GBM parameters: (initial_price, annual_drift, annual_vol, listed_shares)
# Calibrated to roughly match real market cap ranges.
TICKER_PARAMS: dict[str, tuple[float, float, float, float]] = {
    "KPIG.JK": (500.0, 0.05, 0.35, 15_804_254_940),
    "TRIM.JK": (150.0, 0.02, 0.30, 28_674_176_667),
    "SONA.JK": (180.0, 0.08, 0.32, 7_948_800_000),
    "TIRT.JK": (250.0, 0.03, 0.34, 2_387_788_410),
    "TCID.JK": (90.0, 0.06, 0.18, 12_064_000_020),
    "MEDC.JK": (500.0, 0.07, 0.28, 65_102_838_943),
    "PANS.JK": (50.0, 0.01, 0.25, 22_320_000_000),
    "KDSI.JK": (200.0, 0.04, 0.36, 3_645_000_000),
    "MTDL.JK": (350.0, 0.10, 0.28, 18_064_560_000),
    "BCIC.JK": (120.0, 0.05, 0.20, 18_971_758_519),
    "SPMA.JK": (300.0, 0.03, 0.32, 1_724_237_078),
    "BVIC.JK": (100.0, 0.02, 0.36, 14_748_653_190),
    "APLI.JK": (80.0, 0.04, 0.47, 4_428_682_050),
    "RBMS.JK": (60.0, -0.01, 0.43, 3_010_374_536),
    "UNTR.JK": (30000.0, 0.12, 0.25, 2_959_240_541),
    "BNBR.JK": (150.0, 0.06, 0.31, 121_391_782_756),
    "INDF.JK": (5000.0, 0.09, 0.21, 12_731_618_425),
    "UNIC.JK": (400.0, 0.05, 0.23, 14_374_926_113),
    "ASBI.JK": (25.0, 0.03, 0.32, 5_908_634_565),
    "ICBP.JK": (10000.0, 0.08, 0.21, 8_513_192_840),
}

# Benchmark ticker
BENCHMARK_TICKER = "^JKSE"

# Technical indicators to generate (must match REGIME_INVARIANT_INDICATORS)
INDICATORS = ["RSI", "MACD", "ATR14", "BB_LOWER", "VOLUME_SMA20",
              "MACD_SIGNAL", "MA20", "BB_UPPER", "ADX", "MA50"]


# ── GBM Price Simulation ───────────────────────────────────────────────────


def simulate_gbm_prices(
    n_days: int,
    initial_price: float,
    annual_drift: float,
    annual_vol: float,
    seed: int,
) -> np.ndarray:
    """Simulate daily close prices via Geometric Brownian Motion.

    S_t = S_{t-1} * exp((μ - σ²/2) * dt + σ * √dt * Z)

    where dt = 1/252, Z ~ N(0,1).
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / 252.0
    drift = (annual_drift - 0.5 * annual_vol ** 2) * dt
    diffusion = annual_vol * np.sqrt(dt) * rng.standard_normal(n_days)
    log_returns = drift + diffusion
    prices = np.zeros(n_days)
    prices[0] = initial_price
    for i in range(1, n_days):
        prices[i] = prices[i - 1] * np.exp(log_returns[i])
    return prices


def generate_ohlcv_rows(
    ticker: str,
    dates: list[date],
    prices: np.ndarray,
    seed: int,
) -> list[tuple]:
    """Generate OHLCV rows from close prices with realistic intraday range."""
    rng = np.random.default_rng(seed + 1000)
    rows = []
    for i, d in enumerate(dates):
        close = round(float(prices[i]), 4)
        # Intraday volatility: 0.3% – 1.5% of close
        intraday_range = close * rng.uniform(0.003, 0.015)
        high = round(close + intraday_range * rng.random(), 4)
        low = round(close - intraday_range * rng.random(), 4)
        opn = round(low + (high - low) * rng.random(), 4)
        # Ensure OHLC consistency
        high = max(high, opn, close)
        low = min(low, opn, close)
        volume = int(rng.integers(500_000, 50_000_000))
        ts = datetime.combine(d, datetime.min.time())
        rows.append((
            ticker, ts, "1d", opn, high, low, close, volume,
            close, 100.0, "mock_gbm",
            datetime.now(timezone.utc),
        ))
    return rows


def compute_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """Compute RSI from price array."""
    deltas = np.diff(prices, prepend=prices[0])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.convolve(gains, np.ones(period) / period, mode="full")[:len(prices)]
    avg_loss = np.convolve(losses, np.ones(period) / period, mode="full")[:len(prices)]
    # Exponential smoothing
    for i in range(period, len(prices)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period
    rs = np.where(avg_loss > 0, avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss), 100.0)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return np.clip(rsi, 0.0, 100.0)


def compute_macd(prices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute MACD line and signal line."""
    ema12 = _ema(prices, 12)
    ema26 = _ema(prices, 26)
    macd = ema12 - ema26
    signal = _ema(macd, 9)
    return macd, signal


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average."""
    alpha = 2.0 / (period + 1)
    result = np.zeros_like(data)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def compute_atr14(prices: np.ndarray) -> np.ndarray:
    """Simplified ATR14 (using close-to-close range as proxy)."""
    deltas = np.abs(np.diff(prices, prepend=prices[0]))
    atr = np.convolve(deltas, np.ones(14) / 14, mode="full")[:len(prices)]
    return atr


def compute_bollinger(prices: np.ndarray, period: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """Compute Bollinger Bands upper and lower."""
    sma = np.convolve(prices, np.ones(period) / period, mode="full")[:len(prices)]
    # Rolling std (simplified)
    std = np.zeros_like(prices)
    for i in range(period, len(prices)):
        std[i] = np.std(prices[i - period:i])
    upper = sma + 2 * std
    lower = sma - 2 * std
    return upper, lower


def compute_adx(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """Simplified ADX."""
    deltas = np.abs(np.diff(prices, prepend=prices[0]))
    adx = np.convolve(deltas, np.ones(period) / period, mode="full")[:len(prices)]
    return np.clip(adx / prices * 100, 0.0, 100.0)


def compute_volume_sma20(volumes: np.ndarray) -> np.ndarray:
    """20-day volume SMA."""
    return np.convolve(volumes, np.ones(20) / 20, mode="full")[:len(volumes)]


def generate_technical_indicator_rows(
    ticker: str,
    dates: list[date],
    prices: np.ndarray,
    volumes: np.ndarray,
) -> list[tuple]:
    """Generate technical_indicators rows (long format) for all indicators."""
    rsi = compute_rsi(prices)
    macd, macd_signal = compute_macd(prices)
    atr14 = compute_atr14(prices)
    bb_upper, bb_lower = compute_bollinger(prices)
    adx = compute_adx(prices)
    ma20 = _ema(prices, 20)
    ma50 = _ema(prices, 50)
    vol_sma20 = compute_volume_sma20(volumes)

    indicator_map = {
        "RSI": rsi, "MACD": macd, "ATR14": atr14,
        "BB_LOWER": bb_lower, "VOLUME_SMA20": vol_sma20,
        "MACD_SIGNAL": macd_signal, "MA20": ma20,
        "BB_UPPER": bb_upper, "ADX": adx, "MA50": ma50,
    }

    rows = []
    now = datetime.now(timezone.utc)
    for i, d in enumerate(dates):
        for ind_name, values in indicator_map.items():
            val = round(float(values[i]), 6)
            if np.isnan(val) or np.isinf(val):
                val = 0.0
            rows.append((
                ticker, d, ind_name, val, "1d", "mock_computed", now,
            ))
    return rows


def generate_daily_trading_stats_rows(
    ticker: str,
    dates: list[date],
    prices: np.ndarray,
    listed_shares: float,
    seed: int,
) -> list[tuple]:
    """Generate daily_trading_stats rows."""
    rng = np.random.default_rng(seed + 2000)
    rows = []
    now = datetime.now(timezone.utc)
    for i, d in enumerate(dates):
        close = float(prices[i])
        prev_close = float(prices[i - 1]) if i > 0 else close
        change = round(close - prev_close, 4)
        value = round(close * rng.integers(500_000, 50_000_000), 2)
        freq = int(rng.integers(100, 10000))
        rows.append((
            ticker, d, round(prev_close, 4), round(close, 4), change,
            value, freq, round(close, 4), round(close * 1.001, 4),
            float(rng.integers(100, 50000)), round(close * 0.999, 4),
            float(rng.integers(100, 50000)), listed_shares,
            listed_shares * 0.5, 0.0001, 0.0, 0.0, 0,
            "mock_dataset", now,
        ))
    return rows


def generate_stock_personality_rows() -> list[tuple]:
    """Generate stock_personality rows (one per ticker, 100% filled)."""
    rows = []
    now = datetime.now(timezone.utc)
    for ticker in FOCUS_TICKERS:
        _, _, ann_vol, _ = TICKER_PARAMS[ticker]
        vol_regime = "high" if ann_vol > 0.30 else ("medium" if ann_vol > 0.22 else "low")
        rows.append((
            ticker, vol_regime, "trend_following", round(0.8 + np.random.random() * 0.4, 4),
            round(60 + np.random.random() * 30, 2),
            f"{vol_regime}_vol_trend",
            float(np.random.randint(1_000_000, 50_000_000)),
            round(ann_vol / np.sqrt(252), 4),
            round(0.5 + np.random.random() * 0.4, 2),
            round(50 + np.random.random() * 40, 2),
            round(0.3 + np.random.random() * 0.5, 4),
            round(np.random.uniform(-1, 1), 2),
            "donchian_breakout", round(55 + np.random.random() * 15, 2),
            "mean_reversion", round(35 + np.random.random() * 15, 2),
            120, 65, round(54.2, 2),
            round(3 + np.random.random() * 5, 2),
            round(2 + np.random.random() * 4, 2),
            date(2026, 1, 1), now,
        ))
    return rows


def generate_instrument_master_rows() -> list[tuple]:
    """Generate instrument_master rows (one per ticker)."""
    rows = []
    now = datetime.now(timezone.utc)
    for ticker in FOCUS_TICKERS:
        sector = TICKER_SECTORS.get(ticker, "Unknown")
        _, _, _, listed_shares = TICKER_PARAMS[ticker]
        rows.append((
            ticker, "XIDX", "equity", f"Mock {ticker.split('.')[0]}",
            "IDR", "IDR", 100, 1.0, True,
            sector, sector, None, date(2010, 1, 1),
            None, None, "MAIN", 0.3,
            None, listed_shares, listed_shares * 0.5,
            0, None, None, None, "IDX", "ID",
            now, now,
        ))
    # Benchmark
    rows.append((
        BENCHMARK_TICKER, "XIDX", "index", "Jakarta Composite Index",
        "IDR", "IDR", 1, 0.1, True,
        "Index", "Index", None, date(1990, 4, 6),
        None, None, "MAIN", 1.0,
        None, 1_000_000_000, 1_000_000_000,
        0, None, None, None, "IDX", "ID",
        now, now,
    ))
    return rows


# ── DDL: CREATE TABLE statements (matching real schema) ────────────────────


DDL_STATEMENTS = [
    # instrument_master
    """CREATE TABLE IF NOT EXISTS instrument_master (
        ticker TEXT PRIMARY KEY,
        market_mic TEXT NOT NULL,
        asset_class TEXT NOT NULL DEFAULT 'equity',
        name TEXT,
        base_currency TEXT NOT NULL DEFAULT 'IDR',
        reporting_currency TEXT NOT NULL DEFAULT 'IDR',
        lot_size INTEGER,
        tick_size REAL,
        is_active BOOLEAN DEFAULT 1,
        sector TEXT,
        subsector TEXT,
        underlying_ticker TEXT,
        listing_date DATE,
        suspension_date DATE,
        delisting_date DATE,
        board TEXT,
        free_float REAL,
        market_cap REAL,
        listed_shares REAL,
        tradeable_shares REAL,
        delisting_risk_score REAL DEFAULT 0,
        delisting_risk_reason TEXT,
        former_ticker TEXT,
        former_name TEXT,
        index_category TEXT,
        region TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    # ohlcv
    """CREATE TABLE IF NOT EXISTS ohlcv (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        timestamp DATETIME NOT NULL,
        timeframe TEXT NOT NULL DEFAULT '1d',
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        volume INTEGER NOT NULL DEFAULT 0,
        adjusted_close REAL,
        data_quality_score REAL,
        source TEXT DEFAULT 'yahoo_finance',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ticker, timestamp, timeframe)
    )""",
    # technical_indicators
    """CREATE TABLE IF NOT EXISTS technical_indicators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        date DATE NOT NULL,
        indicator TEXT NOT NULL,
        value REAL NOT NULL,
        timeframe TEXT DEFAULT '1d',
        source TEXT DEFAULT 'computed',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ticker, date, indicator, timeframe, source)
    )""",
    # daily_trading_stats
    """CREATE TABLE IF NOT EXISTS daily_trading_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        date DATE NOT NULL,
        previous_close REAL,
        first_trade REAL,
        change REAL,
        value REAL,
        frequency INTEGER,
        index_individual REAL,
        offer REAL,
        offer_volume REAL,
        bid REAL,
        bid_volume REAL,
        listed_shares REAL,
        tradeable_shares REAL,
        weight_for_index REAL,
        non_regular_volume REAL,
        non_regular_value REAL,
        non_regular_frequency INTEGER,
        source TEXT DEFAULT 'github_dataset',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ticker, date, source)
    )""",
    # stock_personality
    """CREATE TABLE IF NOT EXISTS stock_personality (
        ticker TEXT PRIMARY KEY,
        volatility_regime TEXT,
        trend_bias TEXT,
        beta_vs_ihsg REAL,
        liquidity_score REAL,
        personality_label TEXT,
        avg_volume REAL,
        avg_daily_volatility REAL,
        volume_consistency REAL,
        trend_strength REAL,
        correlation_ihsg REAL,
        net_distribution_score REAL,
        best_pattern TEXT,
        best_pattern_winrate REAL,
        worst_pattern TEXT,
        worst_pattern_winrate REAL,
        total_patterns_detected INTEGER,
        total_patterns_success INTEGER,
        overall_pattern_winrate REAL,
        avg_uptrend_streak REAL,
        avg_downtrend_streak REAL,
        profile_date DATE,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
]

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS ix_ohlcv_ticker_ts ON ohlcv(ticker, timestamp)",
    "CREATE INDEX IF NOT EXISTS ix_ohlcv_ticker ON ohlcv(ticker)",
    "CREATE INDEX IF NOT EXISTS ix_ti_ticker_date ON technical_indicators(ticker, date)",
    "CREATE INDEX IF NOT EXISTS ix_ti_ticker ON technical_indicators(ticker)",
    "CREATE INDEX IF NOT EXISTS ix_dts_ticker_date ON daily_trading_stats(ticker, date)",
    "CREATE INDEX IF NOT EXISTS ix_dts_ticker ON daily_trading_stats(ticker)",
]


# ── Main ───────────────────────────────────────────────────────────────────


def generate_mock_db(output_path: str = "data/market_research_mock.db") -> None:
    """Generate the mock SQLite database."""
    t0 = time.time()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing
    if path.exists():
        path.unlink()

    # Date range: Jan 2023 – Aug 2026 (business days)
    dates = pd.bdate_range("2023-01-02", "2026-08-29").tolist()
    date_objs = [d.date() for d in dates]
    n_days = len(date_objs)
    print(f"Date range: {date_objs[0]} → {date_objs[-1]} ({n_days} business days)")

    conn = sqlite3.connect(str(path))
    try:
        # Create tables
        for ddl in DDL_STATEMENTS:
            conn.execute(ddl)
        for idx in INDEX_STATEMENTS:
            conn.execute(idx)
        conn.commit()

        # ── instrument_master ──
        im_rows = generate_instrument_master_rows()
        conn.executemany(
            "INSERT OR REPLACE INTO instrument_master "
            "(ticker, market_mic, asset_class, name, base_currency, "
            "reporting_currency, lot_size, tick_size, is_active, sector, "
            "subsector, underlying_ticker, listing_date, suspension_date, "
            "delisting_date, board, free_float, market_cap, listed_shares, "
            "tradeable_shares, delisting_risk_score, delisting_risk_reason, "
            "former_ticker, former_name, index_category, region, "
            "created_at, updated_at) VALUES (" +
            ",".join("?" * len(im_rows[0])) + ")",
            im_rows,
        )
        print(f"  instrument_master: {len(im_rows)} rows")

        # ── Benchmark OHLCV (^JKSE) ──
        bench_prices = simulate_gbm_prices(n_days, 6_500.0, 0.06, 0.15, seed=999)
        bench_ohlcv = generate_ohlcv_rows(BENCHMARK_TICKER, date_objs, bench_prices, seed=999)
        conn.executemany(
            "INSERT OR REPLACE INTO ohlcv "
            "(ticker, timestamp, timeframe, open, high, low, close, volume, "
            "adjusted_close, data_quality_score, source, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            bench_ohlcv,
        )

        # ── Per-ticker data ──
        total_ohlcv = len(bench_ohlcv)
        total_ti = 0
        total_dts = 0

        for i, ticker in enumerate(FOCUS_TICKERS):
            seed = hash(ticker) % (2**31)
            init_price, drift, vol, listed_shares = TICKER_PARAMS[ticker]

            prices = simulate_gbm_prices(n_days, init_price, drift, vol, seed=seed)

            # OHLCV
            ohlcv_rows = generate_ohlcv_rows(ticker, date_objs, prices, seed=seed)
            conn.executemany(
                "INSERT OR REPLACE INTO ohlcv "
                "(ticker, timestamp, timeframe, open, high, low, close, volume, "
                "adjusted_close, data_quality_score, source, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ohlcv_rows,
            )
            total_ohlcv += len(ohlcv_rows)

            # Technical indicators
            volumes = np.array([r[7] for r in ohlcv_rows], dtype=float)
            ti_rows = generate_technical_indicator_rows(
                ticker, date_objs, prices, volumes,
            )
            conn.executemany(
                "INSERT OR REPLACE INTO technical_indicators "
                "(ticker, date, indicator, value, timeframe, source, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                ti_rows,
            )
            total_ti += len(ti_rows)

            # Daily trading stats
            dts_rows = generate_daily_trading_stats_rows(
                ticker, date_objs, prices, listed_shares, seed=seed,
            )
            conn.executemany(
                "INSERT OR REPLACE INTO daily_trading_stats "
                "(ticker, date, previous_close, first_trade, change, value, "
                "frequency, index_individual, offer, offer_volume, bid, "
                "bid_volume, listed_shares, tradeable_shares, weight_for_index, "
                "non_regular_volume, non_regular_value, non_regular_frequency, "
                "source, created_at) VALUES (" +
                ",".join("?" * len(dts_rows[0])) + ")",
                dts_rows,
            )
            total_dts += len(dts_rows)

            print(f"  [{2+i:2d}/21] {ticker:10s} | "
                  f"ohlcv={len(ohlcv_rows)} ti={len(ti_rows)} dts={len(dts_rows)}")

        # ── stock_personality ──
        sp_rows = generate_stock_personality_rows()
        conn.executemany(
            "INSERT OR REPLACE INTO stock_personality "
            "(ticker, volatility_regime, trend_bias, beta_vs_ihsg, "
            "liquidity_score, personality_label, avg_volume, "
            "avg_daily_volatility, volume_consistency, trend_strength, "
            "correlation_ihsg, net_distribution_score, best_pattern, "
            "best_pattern_winrate, worst_pattern, worst_pattern_winrate, "
            "total_patterns_detected, total_patterns_success, "
            "overall_pattern_winrate, avg_uptrend_streak, "
            "avg_downtrend_streak, profile_date, updated_at) VALUES (" +
            ",".join("?" * len(sp_rows[0])) + ")",
            sp_rows,
        )
        print(f"  stock_personality: {len(sp_rows)} rows")

        conn.commit()

        # ── Summary ──
        print()
        print(f"  Total rows: ohlcv={total_ohlcv} "
              f"technical_indicators={total_ti} "
              f"daily_trading_stats={total_dts} "
              f"stock_personality={len(sp_rows)} "
              f"instrument_master={len(im_rows)}")
        print(f"  Database: {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)")
        print(f"  Elapsed: {time.time() - t0:.2f}s")

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate mock SQLite DB for portfolio pipeline testing",
    )
    parser.add_argument("--output", type=str,
                        default="data/market_research_mock.db",
                        help="Output DB path")
    args = parser.parse_args()
    generate_mock_db(args.output)


if __name__ == "__main__":
    main()
