"""Generate advanced mock SQLite database untuk testing portfolio pipeline.

Menggantikan generate_mock_trading_data.py dengan model finansial yang lebih
realistis menggunakan:

1. **Regime-Switching Markov Chain** — dua rezim pasar makro:
   - Bull (trending): vol rendah, drift positif, autokorelasi positif (trend memory)
   - Bear (crisis): vol tinggi, drift negatif, Poisson downward jumps

2. **Merton Jump-Diffusion** — compound Poisson process untuk shock krisis:
   dS_t = S_{t-1} * [μ dt + σ dW_t + J_t]
   J_t = Σ Y_i,  Y_i ~ LogNormal(-jump_mean, jump_std),  N_t ~ Poisson(λ)

3. **Ornstein-Uhlenbeck (Mean-Reverting)** untuk volatilitas stokastik:
   dσ_t = κ(θ - σ_t) dt + ξ dW^σ_t
   Volatilitas kembali ke level ekuilibrium θ dengan kecepatan κ.

4. **Beta-Correlated Stock Returns** — setiap saham berkorelasi dengan IHSG:
   r_i,t = α_i + β_i * r_market,t + ε_i,t
   ε_i,t ~ N(0, σ_idio) dengan AR(1) autocorrelation di rezim bull

5. **stock_personality 100% non-NULL** — Beta, volatilitas, trend_strength,
   dan korelasi IHSG dihitung dari hasil simulasi (sinkron matematis).

Usage:
    python scripts/generate_advanced_mock_data.py
    python scripts/generate_advanced_mock_data.py --output data/market_research_mock.db

Runs in < 10 seconds. DB < 50 MB.
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════════════════
# KONSTANTA & KONFIGURASI
# ═══════════════════════════════════════════════════════════════════════════

FOCUS_TICKERS: list[str] = [
    "KPIG.JK", "TRIM.JK", "SONA.JK", "TIRT.JK", "TCID.JK", "MEDC.JK", "PANS.JK",
    "KDSI.JK", "MTDL.JK", "BCIC.JK", "SPMA.JK", "BVIC.JK", "APLI.JK", "RBMS.JK",
    "UNTR.JK", "BNBR.JK", "INDF.JK", "UNIC.JK", "ASBI.JK", "ICBP.JK",
]

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

BENCHMARK_TICKER = "^JKSE"

# Per-ticker parameters:
#   (initial_price, beta, idio_vol_annual, listed_shares, ar1_strength)
#
# Beta dikalibrasi: defensif (ICBP, INDF, UNTR) < 1.0, volatil (APLI, RBMS, BVIC) > 1.5
# ar1_strength: autokorelasi return harian di rezim bull (trend memory)
#   - Tinggi (>0.3): saham trending kuat, cocok untuk Donchian/EMA
#   - Rendah (<0.1): saham choppy/mean-reverting
TICKER_PARAMS: dict[str, tuple[float, float, float, float, float]] = {
    "KPIG.JK": (500.0, 1.35, 0.28, 15_804_254_940, 0.25),
    "TRIM.JK": (150.0, 1.20, 0.22, 28_674_176_667, 0.15),
    "SONA.JK": (180.0, 1.50, 0.30, 7_948_800_000, 0.30),
    "TIRT.JK": (250.0, 1.25, 0.26, 2_387_788_410, 0.20),
    "TCID.JK": (90.0, 0.75, 0.12, 12_064_000_020, 0.10),
    "MEDC.JK": (500.0, 1.10, 0.20, 65_102_838_943, 0.22),
    "PANS.JK": (50.0, 1.15, 0.18, 22_320_000_000, 0.12),
    "KDSI.JK": (200.0, 1.45, 0.28, 3_645_000_000, 0.28),
    "MTDL.JK": (350.0, 1.30, 0.22, 18_064_560_000, 0.35),
    "BCIC.JK": (120.0, 0.95, 0.15, 18_971_758_519, 0.18),
    "SPMA.JK": (300.0, 1.20, 0.24, 1_724_237_078, 0.20),
    "BVIC.JK": (100.0, 1.60, 0.30, 14_748_653_190, 0.25),
    "APLI.JK": (80.0, 1.70, 0.35, 4_428_682_050, 0.22),
    "RBMS.JK": (60.0, 1.55, 0.32, 3_010_374_536, 0.15),
    "UNTR.JK": (30000.0, 0.85, 0.16, 2_959_240_541, 0.30),
    "BNBR.JK": (150.0, 1.25, 0.22, 121_391_782_756, 0.18),
    "INDF.JK": (5000.0, 0.70, 0.14, 12_731_618_425, 0.28),
    "UNIC.JK": (400.0, 0.90, 0.17, 14_374_926_113, 0.20),
    "ASBI.JK": (25.0, 1.30, 0.24, 5_908_634_565, 0.15),
    "ICBP.JK": (10000.0, 0.65, 0.12, 8_513_192_840, 0.32),
}

# Technical indicators (must match REGIME_INVARIANT_INDICATORS in remediation)
INDICATORS = ["RSI", "MACD", "ATR14", "BB_LOWER", "VOLUME_SMA20",
              "MACD_SIGNAL", "MA20", "BB_UPPER", "ADX", "MA50"]

# ── Regime Parameters (annualized) ──
# Rezim Bull: drift positif, vol rendah, autokorelasi tinggi
BULL_DRIFT = 0.22          # 22% annual return (strong bull trend)
BULL_VOL = 0.13            # 13% annual vol (low vol trending)
BULL_AR1 = 0.28            # AR(1) trend memory (strong autocorrelation)

# Rezim Bear: drift negatif, vol tinggi, jumps
BEAR_DRIFT = -0.12         # -12% annual return (mild correction)
BEAR_VOL = 0.25            # 25% annual vol (elevated)
BEAR_JUMP_LAMBDA = 6       # Poisson: ~6 jumps/year (selective crisis shocks)
BEAR_JUMP_MEAN = -0.03     # Average jump: -3% per jump
BEAR_JUMP_STD = 0.02       # Jump size std

# Markov transition matrix (daily probabilities)
# P(stay bull) = 0.994, P(bull→bear) = 0.006
# P(stay bear) = 0.980, P(bear→bull) = 0.020
# Expected bull duration: 1/0.006 ≈ 167 days (~8 months)
# Expected bear duration: 1/0.020 ≈ 50 days (~2.5 months)
# Stationary: π_bull = 0.020/(0.006+0.020) ≈ 77%, π_bear ≈ 23%
# Net expected annual return: 0.77×22% + 0.23×(-12%) ≈ +14%
P_BULL_TO_BULL = 0.994
P_BULL_TO_BEAR = 0.006
P_BEAR_TO_BEAR = 0.980
P_BEAR_TO_BULL = 0.020

# ── OU Volatility Parameters ──
OU_KAPPA = 5.0       # Mean-reversion speed (fast)
OU_THETA = 0.20      # Long-run equilibrium vol
OU_XI = 0.05         # Vol-of-vol


# ═══════════════════════════════════════════════════════════════════════════
# MODUL 1: REGIME-SWITCHING MARKOV CHAIN
# ═══════════════════════════════════════════════════════════════════════════


def simulate_regime_path(n_days: int, seed: int = 42) -> np.ndarray:
    """Simulasi path rezim pasar via Markov chain 2-state.

    State 0 = Bull (trending), State 1 = Bear (crisis).
    Transisi harian mengikuti matriks probabilitas:
        P = [[0.992, 0.008],
             [0.015, 0.985]]

    Expected duration bull ≈ 125 hari, bear ≈ 67 hari.
    Rezim awal: Bull (sesuai kondisi IDX Jan 2023).
    """
    rng = np.random.default_rng(seed)
    regimes = np.zeros(n_days, dtype=int)
    regimes[0] = 0  # Mulai di Bull

    for t in range(1, n_days):
        if regimes[t - 1] == 0:  # Bull
            regimes[t] = 0 if rng.random() < P_BULL_TO_BULL else 1
        else:  # Bear
            regimes[t] = 1 if rng.random() < P_BEAR_TO_BEAR else 0

    return regimes


# ═══════════════════════════════════════════════════════════════════════════
# MODUL 2: BENCHMARK (^JKSE) — REGIME-SWITCHING + MERTON JUMP-DIFFUSION
# ═══════════════════════════════════════════════════════════════════════════


def simulate_benchmark_prices(
    n_days: int,
    regimes: np.ndarray,
    initial_price: float = 6_800.0,
    seed: int = 999,
) -> np.ndarray:
    """Simulasi harga IHSG (^JKSE) dengan regime-switching Merton jump-diffusion.

    Model harian (dt = 1/252):
        Bull: r_t = (μ_bull - 0.5σ²_bull) dt + σ_bull √dt Z_t + AR(1) memory
        Bear: r_t = (μ_bear - 0.5σ²_bear) dt + σ_bear √dt Z_t + Σ J_i

    J_i ~ LogNormal(jump_mean, jump_std) dengan N_t ~ Poisson(λ_bear * dt)
    AR(1) memory di bull: r_t += φ * (r_{t-1} - μ_drift) untuk autokorelasi positif.
    Ini menciptakan trend persistence yang bisa diekstrak oleh Donchian/EMA.
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / 252.0
    prices = np.zeros(n_days)
    prices[0] = initial_price
    prev_log_ret = 0.0

    for t in range(1, n_days):
        regime = regimes[t]

        if regime == 0:  # Bull
            mu = BULL_DRIFT
            sigma = BULL_VOL
            # Drift + diffusion
            log_ret = (mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * rng.standard_normal()
            # AR(1) trend memory: positive autocorrelation
            log_ret += BULL_AR1 * prev_log_ret
        else:  # Bear
            mu = BEAR_DRIFT
            sigma = BEAR_VOL
            log_ret = (mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * rng.standard_normal()
            # Merton jump-diffusion: Poisson downward jumps
            n_jumps = rng.poisson(BEAR_JUMP_LAMBDA * dt)
            if n_jumps > 0:
                jump_sizes = rng.normal(BEAR_JUMP_MEAN, BEAR_JUMP_STD, n_jumps)
                log_ret += jump_sizes.sum()

        prices[t] = prices[t - 1] * np.exp(log_ret)
        prev_log_ret = log_ret

    return prices


# ═══════════════════════════════════════════════════════════════════════════
# MODUL 3: STOCK PRICES — BETA-CORRELATED + OU VOLATILITY + IDIO INNOVATION
# ═══════════════════════════════════════════════════════════════════════════


def simulate_stock_prices(
    n_days: int,
    regimes: np.ndarray,
    benchmark_log_returns: np.ndarray,
    initial_price: float,
    beta: float,
    idio_vol: float,
    ar1_strength: float,
    seed: int,
) -> np.ndarray:
    """Simulasi harga saham individual dengan model multi-faktor:

    r_i,t = α_i + β_i * r_market,t + ε_i,t

    di mana:
    - α_i (alpha) = drift idiosinkratik kecil (±2% annual)
    - β_i = sensitivitas terhadap IHSG (dari TICKER_PARAMS)
    - ε_i,t = inovasi idiosinkratik dengan:
        * Volatilitas stokastik via Ornstein-Uhlenbeck:
          dσ_t = κ(θ - σ_t) dt + ξ dW^σ_t
        * AR(1) autocorrelation di rezim bull (trend memory):
          ε_t = φ * ε_{t-1} + η_t,  η_t ~ N(0, σ_t² dt)
        * Jumps mengikuti rezim bear (sinkron dengan IHSG)

    OU process memastikan volatilitas mean-reverting ke equilibrium θ,
    bukan konstan seperti GBM murni.
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / 252.0
    prices = np.zeros(n_days)
    prices[0] = initial_price

    # Alpha idiosinkratik kecil (random ±2% annual)
    alpha_idio = rng.uniform(-0.02, 0.02)

    # Inisialisasi OU volatility
    sigma_t = idio_vol
    prev_idio_ret = 0.0

    for t in range(1, n_days):
        regime = regimes[t]

        # ── OU volatility update: dσ = κ(θ - σ) dt + ξ √dt Z ──
        sigma_t += OU_KAPPA * (OU_THETA - sigma_t) * dt + OU_XI * np.sqrt(dt) * rng.standard_normal()
        sigma_t = max(sigma_t, 0.05)  # Floor: minimum 5% annual vol

        # ── Market component: β * r_market ──
        market_ret = beta * benchmark_log_returns[t]

        # ── Idiosyncratic component ──
        if regime == 0:  # Bull
            idio_drift = alpha_idio * dt
            idio_shock = sigma_t * np.sqrt(dt) * rng.standard_normal()
            # AR(1) trend memory
            idio_ret = idio_drift + ar1_strength * prev_idio_ret + idio_shock
        else:  # Bear
            idio_drift = alpha_idio * dt * 0.5  # Alpha tereduksi di krisis
            idio_shock = sigma_t * 1.5 * np.sqrt(dt) * rng.standard_normal()  # Amplified vol
            # Idiosyncratic jumps (firm-specific shocks)
            n_jumps = rng.poisson(BEAR_JUMP_LAMBDA * dt * 0.3)  # 30% of market jump freq
            jump_component = 0.0
            if n_jumps > 0:
                jump_component = rng.normal(BEAR_JUMP_MEAN * 0.8, BEAR_JUMP_STD, n_jumps).sum()
            idio_ret = idio_drift + idio_shock + jump_component

        # ── Total log return ──
        total_log_ret = market_ret + idio_ret
        prices[t] = prices[t - 1] * np.exp(total_log_ret)
        prev_idio_ret = idio_ret

    return prices


# ═══════════════════════════════════════════════════════════════════════════
# MODUL 4: TECHNICAL INDICATORS (computed from simulated prices)
# ═══════════════════════════════════════════════════════════════════════════


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average.

    EMA_t = α * price_t + (1-α) * EMA_{t-1},  α = 2/(period+1)
    Memberikan bobot lebih besar pada data terbaru → responsif terhadap tren.
    """
    alpha = 2.0 / (period + 1)
    result = np.zeros_like(data)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def _sma(data: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average via convolution."""
    return np.convolve(data, np.ones(period) / period, mode="full")[:len(data)]


def compute_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index.

    RSI = 100 - 100/(1+RS),  RS = avg_gain / avg_loss
    Mengukur momentum overbought/oversold pada skala 0-100.
    """
    deltas = np.diff(prices, prepend=prices[0])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = _sma(gains, period)
    avg_loss = _sma(losses, period)
    # Exponential smoothing for stability
    for i in range(period, len(prices)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period
    rs = np.where(avg_loss > 1e-10, avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss), 100.0)
    return np.clip(100.0 - 100.0 / (1.0 + rs), 0.0, 100.0)


def compute_macd(prices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """MACD Line = EMA(12) - EMA(26), Signal = EMA(9) of MACD."""
    ema12 = _ema(prices, 12)
    ema26 = _ema(prices, 26)
    macd = ema12 - ema26
    signal = _ema(macd, 9)
    return macd, signal


def compute_atr14(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """Average True Range (14-day).

    Simplified: ATR = SMA(|Δprice|, 14)
    Mengukur volatilitas absolut → scale-free untuk regime-invariant features.
    """
    deltas = np.abs(np.diff(prices, prepend=prices[0]))
    return _sma(deltas, period)


def compute_bollinger(prices: np.ndarray, period: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """Bollinger Bands.

    Upper = SMA(20) + 2σ,  Lower = SMA(20) - 2σ
    Mengukur deviasi harga dari rata-rata bergerak → mean-reversion signal.
    """
    sma = _sma(prices, period)
    std = np.zeros_like(prices)
    for i in range(period, len(prices)):
        std[i] = np.std(prices[i - period:i])
    return sma + 2 * std, sma - 2 * std


def compute_adx(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """ADX (simplified) — trend strength indicator.

    ADX tinggi = tren kuat, ADX rendah = sideways/consolidation.
    Di sini dihitung sebagai normalized ATR.
    """
    atr = compute_atr14(prices, period)
    return np.clip(atr / np.where(prices > 0, prices, 1.0) * 100, 0.0, 100.0)


def generate_technical_indicator_rows(
    ticker: str,
    dates: list[date],
    prices: np.ndarray,
    volumes: np.ndarray,
) -> list[tuple]:
    """Generate technical_indicators rows (long format) untuk semua indikator."""
    rsi = compute_rsi(prices)
    macd, macd_signal = compute_macd(prices)
    atr14 = compute_atr14(prices)
    bb_upper, bb_lower = compute_bollinger(prices)
    adx = compute_adx(prices)
    ma20 = _ema(prices, 20)
    ma50 = _ema(prices, 50)
    vol_sma20 = _sma(volumes.astype(float), 20)

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
            rows.append((ticker, d, ind_name, val, "1d", "mock_advanced", now))
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# MODUL 5: OHLCV & DAILY TRADING STATS
# ═══════════════════════════════════════════════════════════════════════════


def generate_ohlcv_rows(
    ticker: str,
    dates: list[date],
    prices: np.ndarray,
    volumes: np.ndarray,
    seed: int,
) -> list[tuple]:
    """Generate OHLCV rows dari close prices dengan intraday range realistis.

    Intraday high/low dihasilkan dari fraksi volatilitas harian:
        high = close + |close| * intraday_range * U_high
        low  = close - |close| * intraday_range * U_low
    di mana intraday_range ~ Uniform(0.3%, 1.5%) dan U ~ Uniform(0,1).
    Open diambil dari interpolasi low-high.
    """
    rng = np.random.default_rng(seed + 1000)
    rows = []
    for i, d in enumerate(dates):
        close = round(float(prices[i]), 4)
        intraday_range = close * rng.uniform(0.003, 0.015)
        high = round(close + intraday_range * rng.random(), 4)
        low = round(close - intraday_range * rng.random(), 4)
        opn = round(low + (high - low) * rng.random(), 4)
        high = max(high, opn, close)
        low = min(low, opn, close)
        ts = datetime.combine(d, datetime.min.time())
        rows.append((
            ticker, ts, "1d", opn, high, low, close, int(volumes[i]),
            close, 100.0, "mock_advanced",
            datetime.now(timezone.utc),
        ))
    return rows


def generate_daily_trading_stats_rows(
    ticker: str,
    dates: list[date],
    prices: np.ndarray,
    volumes: np.ndarray,
    listed_shares: float,
    seed: int,
) -> list[tuple]:
    """Generate daily_trading_stats rows dari harga & volume simulasi."""
    rng = np.random.default_rng(seed + 2000)
    rows = []
    now = datetime.now(timezone.utc)
    for i, d in enumerate(dates):
        close = float(prices[i])
        prev_close = float(prices[i - 1]) if i > 0 else close
        change = round(close - prev_close, 4)
        vol = int(volumes[i])
        value = round(close * vol, 2)
        freq = int(rng.integers(100, 10000))
        rows.append((
            ticker, d, round(prev_close, 4), round(close, 4), change,
            value, freq, round(close, 4), round(close * 1.001, 4),
            float(rng.integers(100, 50000)), round(close * 0.999, 4),
            float(rng.integers(100, 50000)), listed_shares,
            listed_shares * 0.5, 0.0001, 0.0, 0.0, 0,
            "mock_advanced", now,
        ))
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# MODUL 6: STOCK PERSONALITY — COMPUTED FROM SIMULATED DATA (100% non-NULL)
# ═══════════════════════════════════════════════════════════════════════════


def compute_stock_personality(
    ticker: str,
    prices: np.ndarray,
    volumes: np.ndarray,
    benchmark_log_returns: np.ndarray,
    regimes: np.ndarray,
    beta: float,
) -> tuple:
    """Hitung stock_personality dari data simulasi (sinkron matematis).

    Metrik dihitung dari harga & volume hasil simulasi, bukan random:
    - avg_daily_volatility: std(log returns) * √252 (annualized)
    - trend_strength: R² of linear regression on log prices (0-100)
    - correlation_ihsg: Pearson correlation(stock_returns, benchmark_returns)
    - beta_vs_ihsg: OLS beta (slope of stock vs market)
    - volume_consistency: 1 - CV(volume) (coefficient of variation)
    - avg_volume: mean(volume)
    - net_distribution_score: skewness of returns (negative = left-skewed)
    - avg_uptrend_streak / avg_downtrend_streak: mean consecutive up/down days
    """
    log_rets = np.diff(np.log(prices))
    n = len(log_rets)

    # Volatility (annualized)
    avg_daily_vol = float(np.std(log_rets))
    ann_vol = avg_daily_vol * np.sqrt(252)

    # Trend strength: R² of log(price) vs time index
    log_prices = np.log(prices)
    x = np.arange(len(prices))
    x_mean = x.mean()
    y_mean = log_prices.mean()
    ss_xy = np.sum((x - x_mean) * (log_prices - y_mean))
    ss_xx = np.sum((x - x_mean) ** 2)
    ss_yy = np.sum((log_prices - y_mean) ** 2)
    r_squared = (ss_xy ** 2) / (ss_xx * ss_yy + 1e-10)
    trend_strength = float(np.clip(r_squared * 100, 0, 100))

    # Correlation with benchmark
    stock_rets = log_rets
    bench_rets = benchmark_log_returns[1:]  # align
    min_len = min(len(stock_rets), len(bench_rets))
    corr = float(np.corrcoef(stock_rets[:min_len], bench_rets[:min_len])[0, 1])
    if np.isnan(corr):
        corr = 0.0

    # Beta (OLS regression: stock = α + β * market)
    cov = np.cov(stock_rets[:min_len], bench_rets[:min_len])[0, 1]
    var_bench = np.var(bench_rets[:min_len])
    beta_computed = float(cov / (var_bench + 1e-10))

    # Volume metrics
    avg_volume = float(np.mean(volumes))
    vol_cv = float(np.std(volumes) / (np.mean(volumes) + 1e-10))
    volume_consistency = float(np.clip(1.0 - vol_cv, 0, 1) * 100)

    # Skewness (net distribution score)
    from scipy.stats import skew
    net_dist = float(skew(log_rets)) if n > 10 else 0.0

    # Streak analysis
    up_streaks = []
    down_streaks = []
    current_up = 0
    current_down = 0
    for r in log_rets:
        if r > 0:
            current_up += 1
            if current_down > 0:
                down_streaks.append(current_down)
                current_down = 0
        else:
            current_down += 1
            if current_up > 0:
                up_streaks.append(current_up)
                current_up = 0
    if current_up > 0:
        up_streaks.append(current_up)
    if current_down > 0:
        down_streaks.append(current_down)
    avg_up = float(np.mean(up_streaks)) if up_streaks else 0.0
    avg_down = float(np.mean(down_streaks)) if down_streaks else 0.0

    # Volatility regime classification
    if ann_vol > 0.30:
        vol_regime = "high"
    elif ann_vol > 0.20:
        vol_regime = "medium"
    else:
        vol_regime = "low"

    # Trend bias based on overall drift
    total_return = float(np.log(prices[-1] / prices[0]))
    trend_bias = "trend_following" if total_return > 0 else "mean_reverting"

    # Best/worst pattern (simulated)
    best_pattern = "donchian_breakout" if trend_strength > 30 else "mean_reversion"
    best_winrate = float(np.clip(50 + trend_strength * 0.3 + np.random.uniform(-5, 10), 35, 75))
    worst_pattern = "rsi_oversold" if vol_regime == "high" else "ma_crossover"
    worst_winrate = float(np.clip(35 + np.random.uniform(-5, 10), 20, 50))

    # Personality label
    trend_type = "trend" if trend_strength > 30 else "range"
    beta_type = "high_beta" if beta > 1.2 else "low_beta"
    personality_label = f"{vol_regime}_vol_{trend_type}_{beta_type}"

    # Liquidity score (0-100): based on avg volume relative to listed shares
    turnover = avg_volume / (TICKER_PARAMS[ticker][3] + 1e-10)
    liquidity_score = float(np.clip(turnover * 10000, 10, 95))

    now = datetime.now(timezone.utc)

    return (
        ticker, vol_regime, trend_bias, round(beta_computed, 4),
        round(liquidity_score, 2),
        personality_label,
        round(avg_volume, 2),
        round(avg_daily_vol, 4),
        round(volume_consistency, 2),
        round(trend_strength, 2),
        round(corr, 4),
        round(net_dist, 2),
        best_pattern, round(best_winrate, 2),
        worst_pattern, round(worst_winrate, 2),
        120, 65, round((best_winrate + worst_winrate) / 2, 2),
        round(avg_up, 2), round(avg_down, 2),
        date(2026, 1, 1), now,
    )


# ═══════════════════════════════════════════════════════════════════════════
# MODUL 7: INSTRUMENT MASTER
# ═══════════════════════════════════════════════════════════════════════════


def generate_instrument_master_rows() -> list[tuple]:
    """Generate instrument_master rows (one per ticker + benchmark)."""
    rows = []
    now = datetime.now(timezone.utc)
    for ticker in FOCUS_TICKERS:
        sector = TICKER_SECTORS.get(ticker, "Unknown")
        _, _, _, listed_shares, _ = TICKER_PARAMS[ticker]
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


# ═══════════════════════════════════════════════════════════════════════════
# DDL: CREATE TABLE (identik dengan schema real DB)
# ═══════════════════════════════════════════════════════════════════════════

DDL_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS instrument_master (
        ticker TEXT PRIMARY KEY, market_mic TEXT NOT NULL,
        asset_class TEXT NOT NULL DEFAULT 'equity', name TEXT,
        base_currency TEXT NOT NULL DEFAULT 'IDR',
        reporting_currency TEXT NOT NULL DEFAULT 'IDR',
        lot_size INTEGER, tick_size REAL, is_active BOOLEAN DEFAULT 1,
        sector TEXT, subsector TEXT, underlying_ticker TEXT,
        listing_date DATE, suspension_date DATE, delisting_date DATE,
        board TEXT, free_float REAL, market_cap REAL,
        listed_shares REAL, tradeable_shares REAL,
        delisting_risk_score REAL DEFAULT 0, delisting_risk_reason TEXT,
        former_ticker TEXT, former_name TEXT, index_category TEXT,
        region TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS ohlcv (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL,
        timestamp DATETIME NOT NULL, timeframe TEXT NOT NULL DEFAULT '1d',
        open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL,
        close REAL NOT NULL, volume INTEGER NOT NULL DEFAULT 0,
        adjusted_close REAL, data_quality_score REAL,
        source TEXT DEFAULT 'yahoo_finance',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ticker, timestamp, timeframe)
    )""",
    """CREATE TABLE IF NOT EXISTS technical_indicators (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL,
        date DATE NOT NULL, indicator TEXT NOT NULL, value REAL NOT NULL,
        timeframe TEXT DEFAULT '1d', source TEXT DEFAULT 'computed',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ticker, date, indicator, timeframe, source)
    )""",
    """CREATE TABLE IF NOT EXISTS daily_trading_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL,
        date DATE NOT NULL, previous_close REAL, first_trade REAL,
        change REAL, value REAL, frequency INTEGER, index_individual REAL,
        offer REAL, offer_volume REAL, bid REAL, bid_volume REAL,
        listed_shares REAL, tradeable_shares REAL, weight_for_index REAL,
        non_regular_volume REAL, non_regular_value REAL,
        non_regular_frequency INTEGER, source TEXT DEFAULT 'github_dataset',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ticker, date, source)
    )""",
    """CREATE TABLE IF NOT EXISTS stock_personality (
        ticker TEXT PRIMARY KEY, volatility_regime TEXT, trend_bias TEXT,
        beta_vs_ihsg REAL, liquidity_score REAL, personality_label TEXT,
        avg_volume REAL, avg_daily_volatility REAL, volume_consistency REAL,
        trend_strength REAL, correlation_ihsg REAL, net_distribution_score REAL,
        best_pattern TEXT, best_pattern_winrate REAL, worst_pattern TEXT,
        worst_pattern_winrate REAL, total_patterns_detected INTEGER,
        total_patterns_success INTEGER, overall_pattern_winrate REAL,
        avg_uptrend_streak REAL, avg_downtrend_streak REAL,
        profile_date DATE, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
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


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════


def generate_advanced_mock_db(
    output_path: str = "data/market_research_mock.db",
) -> None:
    """Generate advanced mock SQLite database.

    Pipeline:
    1. Simulasi regime path (Markov chain 2-state)
    2. Simulasi benchmark IHSG (regime-switching Merton jump-diffusion)
    3. Per ticker: simulasi harga (beta-correlated + OU vol + AR(1) memory)
    4. Hitung technical indicators dari harga simulasi
    5. Hitung stock_personality dari data simulasi (100% non-NULL, sinkron)
    6. Insert semua ke SQLite
    """
    t0 = time.time()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    # Date range: Jan 2023 – Aug 2026 (business days)
    dates = pd.bdate_range("2023-01-02", "2026-08-29").tolist()
    date_objs = [d.date() for d in dates]
    n_days = len(date_objs)
    print(f"Date range: {date_objs[0]} → {date_objs[-1]} ({n_days} business days)")

    # ── Step 1: Regime path ──
    regimes = simulate_regime_path(n_days, seed=42)
    n_bull = int((regimes == 0).sum())
    n_bear = int((regimes == 1).sum())
    print(f"Regime: Bull={n_bull} days ({n_bull/n_days*100:.1f}%), "
          f"Bear={n_bear} days ({n_bear/n_days*100:.1f}%)")

    # ── Step 2: Benchmark (^JKSE) ──
    bench_prices = simulate_benchmark_prices(n_days, regimes, seed=999)
    bench_log_rets = np.zeros(n_days)
    bench_log_rets[1:] = np.diff(np.log(bench_prices))
    bench_total_ret = float(np.log(bench_prices[-1] / bench_prices[0]) * 100)
    print(f"Benchmark ^JKSE: {bench_prices[0]:.0f} → {bench_prices[-1]:.0f} "
          f"({bench_total_ret:+.1f}% log return)")

    # Generate volumes for benchmark
    rng_vol = np.random.default_rng(99900)
    bench_volumes = rng_vol.integers(1_000_000_000, 5_000_000_000, n_days)

    # ── Connect DB ──
    conn = sqlite3.connect(str(path))
    try:
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

        # ── Benchmark OHLCV ──
        bench_ohlcv = generate_ohlcv_rows(
            BENCHMARK_TICKER, date_objs, bench_prices, bench_volumes, seed=999)
        conn.executemany(
            "INSERT OR REPLACE INTO ohlcv "
            "(ticker, timestamp, timeframe, open, high, low, close, volume, "
            "adjusted_close, data_quality_score, source, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            bench_ohlcv,
        )

        # ── Per-ticker simulation ──
        total_ohlcv = len(bench_ohlcv)
        total_ti = 0
        total_dts = 0
        sp_rows = []

        for i, ticker in enumerate(FOCUS_TICKERS):
            seed = hash(ticker) % (2**31)
            init_price, beta, idio_vol, listed_shares, ar1 = TICKER_PARAMS[ticker]

            # Step 3: Simulate stock prices
            prices = simulate_stock_prices(
                n_days, regimes, bench_log_rets,
                init_price, beta, idio_vol, ar1, seed=seed,
            )

            # Generate volumes (correlated with price moves)
            rng_t = np.random.default_rng(seed + 5000)
            base_vol = listed_shares * 0.005  # ~0.5% daily turnover
            vol_noise = rng_t.lognormal(0, 0.5, n_days) * base_vol
            # Higher volume in bear regime
            vol_multiplier = np.where(regimes == 1, 1.8, 1.0)
            volumes = (vol_noise * vol_multiplier).astype(int)

            # OHLCV
            ohlcv_rows = generate_ohlcv_rows(ticker, date_objs, prices, volumes, seed=seed)
            conn.executemany(
                "INSERT OR REPLACE INTO ohlcv "
                "(ticker, timestamp, timeframe, open, high, low, close, volume, "
                "adjusted_close, data_quality_score, source, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ohlcv_rows,
            )
            total_ohlcv += len(ohlcv_rows)

            # Technical indicators
            ti_rows = generate_technical_indicator_rows(ticker, date_objs, prices, volumes)
            conn.executemany(
                "INSERT OR REPLACE INTO technical_indicators "
                "(ticker, date, indicator, value, timeframe, source, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                ti_rows,
            )
            total_ti += len(ti_rows)

            # Daily trading stats
            dts_rows = generate_daily_trading_stats_rows(
                ticker, date_objs, prices, volumes, listed_shares, seed=seed)
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

            # Stock personality (computed from simulated data)
            sp = compute_stock_personality(
                ticker, prices, volumes.astype(float),
                bench_log_rets, regimes, beta,
            )
            sp_rows.append(sp)

            total_ret = float(np.log(prices[-1] / prices[0]) * 100)
            print(f"  [{2+i:2d}/21] {ticker:10s} | β={beta:.2f} "
                  f"ret={total_ret:+6.1f}% vol={sp[7]:.4f} "
                  f"trend={sp[9]:.1f} corr={sp[10]:.3f}")

        # ── stock_personality ──
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
        description="Generate advanced mock SQLite DB with regime-switching "
                    "Merton jump-diffusion + OU mean-reverting volatility",
    )
    parser.add_argument("--output", type=str,
                        default="data/market_research_mock.db",
                        help="Output DB path")
    args = parser.parse_args()
    generate_advanced_mock_db(args.output)


if __name__ == "__main__":
    main()
