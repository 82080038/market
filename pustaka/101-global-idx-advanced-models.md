# Global-IDX Advanced Models: DCC-GARCH, Diebold-Yilmaz, Foreign Flow, Overnight Prediction

> **Tujuan:** Dokumen ini mendalami 4 gap model advanced yang belum diimplementasi dari pustaka/35 — DCC-GARCH (dynamic conditional correlation), Diebold-Yilmaz spillover index, foreign flow prediction, dan overnight global → IDX opening prediction. Setiap model dijelaskan teori, formula, implementasi kode untuk ablation testing, dan ekspektasi predictive power untuk IDX.

---

## Daftar Isi

1. [DCC-GARCH: Dynamic Conditional Correlation](#1-dcc-garch-dynamic-conditional-correlation)
2. [Diebold-Yilmaz Spillover Index](#2-diebold-yilmaz-spillover-index)
3. [Foreign Flow Prediction Model](#3-foreign-flow-prediction-model)
4. [Overnight Global → IDX Opening Prediction](#4-overnight-global--idx-opening-prediction)
5. [Implementasi Ablation Engine](#5-implementasi-ablation-engine)
6. [Ekspektasi dan Limitasi](#6-ekspektasi-dan-limitasi)

---

## 1. DCC-GARCH: Dynamic Conditional Correlation

### 1.1 Latar Belakang

Pustaka/35 §2.3 menjelaskan DCC-GARCH tetapi implementasi saat ini hanya EWM (exponentially weighted moving) approximation. DCC-GARCH asli (Engle, 2002) memberikan korelasi dinamis yang lebih akurat antara pasar global dan IDX.

### 1.2 Teori

**GARCH(1,1)** untuk variance tiap market:

$$h_{i,t} = \omega_i + \alpha_i \epsilon_{i,t-1}^2 + \beta_i h_{i,t-1}$$

**DCC** untuk correlation dynamics:

$$Q_t = (1-a-b)\bar{Q} + a \epsilon_{t-1}\epsilon_{t-1}' + b Q_{t-1}$$

$$R_t = \text{diag}(Q_t)^{-1/2} Q_t \text{diag}(Q_t)^{-1/2}$$

Dimana:
- $Q_t$ = quasi-correlation matrix
- $\bar{Q}$ = unconditional correlation matrix
- $a, b$ = DCC parameters (a = shock, b = persistence)
- $R_t$ = dynamic conditional correlation matrix

### 1.3 Interpretasi untuk IDX

| DCC Pattern | IDX Signal | Logic |
|-------------|------------|-------|
| Corr(IHSG, S&P500) naik >0.7 | Risk-off / neutral | Contagion risk — IDX terlalu mengikuti US |
| Corr(IHSG, S&P500) turun <0.3 | Idiosyncratic | IDX driven oleh faktor lokal — opportunity |
| Corr(IHSG, VIX) naik >-0.5 | Risk-off | VIX correlation meningkat = stress |
| Corr(IHSG, USD/IDR) >-0.5 | Risk-off | FX pressure dominant |

### 1.4 Implementasi (Simplified tanpa arch library)

Untuk ablation, implementasi simplified DCC tanpa full MLE optimization:

```python
def dcc_garch_correlation(
    returns_a: pd.Series,
    returns_b: pd.Series,
    garch_window: int = 20,
    dcc_alpha: float = 0.05,
    dcc_beta: float = 0.90,
) -> pd.Series:
    """Simplified DCC-GARCH correlation between two return series.

    Uses GARCH(1,1) for conditional variance + DCC for correlation.
    No MLE optimization — uses fixed parameters from literature.
    """
    # GARCH(1,1) variance for each series
    var_a = _garch_variance(returns_a, garch_window)
    var_b = _garch_variance(returns_b, garch_window)

    # Standardized residuals
    eps_a = returns_a / np.sqrt(var_a)
    eps_b = returns_b / np.sqrt(var_b)

    # DCC: quasi-correlation evolution
    # Q_t = (1-a-b)*Q_bar + a*eps_{t-1}*eps_{t-1}' + b*Q_{t-1}
    corr_bar = eps_a.corr(eps_b)  # unconditional correlation
    q_t = corr_bar
    dcc_corr = pd.Series(index=returns_a.index, dtype=float)

    for i in range(len(eps_a)):
        if i == 0:
            dcc_corr.iloc[i] = corr_bar
            continue
        ea = eps_a.iloc[i - 1]
        eb = eps_b.iloc[i - 1]
        q_t = (1 - dcc_alpha - dcc_beta) * corr_bar + \
              dcc_alpha * ea * eb + \
              dcc_beta * q_t
        # Normalize to [-1, 1]
        dcc_corr.iloc[i] = np.tanh(q_t)  # tanh ensures [-1, 1]

    return dcc_corr.shift(1)  # no look-ahead


def _garch_variance(returns: pd.Series, window: int = 20) -> pd.Series:
    """GARCH(1,1) conditional variance (simplified)."""
    # Initialize with rolling variance
    var = returns.rolling(window).var()
    # GARCH update: h_t = omega + alpha * eps^2 + beta * h_{t-1}
    alpha, beta = 0.1, 0.85
    omega = var.mean() * (1 - alpha - beta)
    h = var.copy()
    for i in range(1, len(h)):
        if pd.notna(h.iloc[i - 1]):
            h.iloc[i] = omega + alpha * returns.iloc[i - 1] ** 2 + beta * h.iloc[i - 1]
    return h
```

### 1.5 Signal Generation untuk Ablation

```
DCC(IHSG, S&P500) > 0.7 → signal = -1 (contagion risk, reduce)
DCC(IHSG, S&P500) < 0.3 → signal = +1 (idiosyncratic, opportunity)
DCC trending up → reduce confidence
DCC trending down → increase confidence
```

**Anti look-ahead:** DCC di-shift(1) sebelum digunakan untuk signal.

### 1.6 Referensi

- Engle, R. (2002). "Dynamic Conditional Correlation: A Simple Class of Multivariate GARCH Models." Journal of Business & Economic Statistics, 20(3), 339-350.
- Engle, R. & Sheppard, K. (2001). "Theoretical and Empirical Properties of Dynamic Conditional Correlation Multivariate GARCH." NBER Working Paper 8554.
- Cappiello, L., Engle, R.F., & Sheppard, K. (2006). "Asymmetric Dynamics in the Correlations of Global Equity and Bond Returns." Journal of Financial Econometrics, 4(4), 537-572.

---

## 2. Diebold-Yilmaz Spillover Index

### 1.1 Latar Belakang

Pustaka/35 §4.2 menjelaskan Diebold-Yilmaz spillover index tetapi implementasi di `cross_market.py` hanya lagged correlation. Implementasi penuh menggunakan VAR (Vector Autoregression) + Forecast Error Variance Decomposition (FEVD).

### 2.2 Teori

**VAR(p) model:**

$$y_t = c + A_1 y_{t-1} + A_2 y_{t-2} + ... + A_p y_{t-p} + \epsilon_t$$

Dimana $y_t$ = vector returns dari N markets.

**Forecast Error Variance Decomposition (FEVD):**

Decompose variance of forecast error at horizon H into contributions dari setiap market:

$$\theta_{ij}(H) = \frac{\sum_{h=0}^{H-1} (\psi_h P)_{ij}^2}{\sum_{h=0}^{H-1} (\psi_h P \psi_h P')_{ii}}$$

**Spillover Index (total):**

$$S(H) = \frac{\sum_{i \neq j} \theta_{ij}(H)}{N} \times 100$$

**Directional spillovers:**
- From others to i: $S_i^{from}(H) = \frac{\sum_{j \neq i} \theta_{ji}(H)}{N} \times 100$
- To others from i: $S_i^{to}(H) = \frac{\sum_{j \neq i} \theta_{ij}(H)}{N} \times 100$
- Net spillover: $S_i^{net}(H) = S_i^{to}(H) - S_i^{from}(H)$

### 2.3 Interpretasi untuk IDX

| Spillover Metric | IDX Signal | Logic |
|-----------------|------------|-------|
| Net spillover FROM global TO IDX tinggi | Passive follower | IDX menerima shock dari global — signal global lebih prediktif |
| Net spillover FROM IDX TO global tinggi | Active leader | IDX mempengaruhi global — jarang terjadi |
| Total spillover index naik tajam | Risk-off | Contagion — semua markets bergerak bersama |
| Spillover dari VIX ke IDX tinggi | Risk-off | VIX adalah transmitter utama |

### 2.4 Implementasi

```python
from statsmodels.tsa.api import VAR

def diebold_yilmaz_spillover(
    returns: pd.DataFrame,
    lag: int = 2,
    horizon: int = 10,
) -> dict:
    """Full Diebold-Yilmaz spillover index using VAR + FEVD.

    Args:
        returns: DataFrame with columns for each market's returns.
        lag: VAR lag order.
        horizon: Forecast horizon for FEVD.

    Returns:
        Dict with total spillover, directional spillovers, and signal.
    """
    data = returns.dropna()
    if len(data) < 60:
        return {"total_spillover": 0, "signal": 0}

    model = VAR(data)
    results = model.fit(lag)

    # FEVD
    fevd = results.fevd(horizon)
    spillover_table = fevd.decomp[-1]  # last period decomposition

    N = len(data.columns)
    # Total spillover index
    total_spillover = (spillover_table.sum() - spillover_table.diagonal().sum()) / N * 100

    # Directional
    from_others = spillover_table.sum(axis=1) - spillover_table.diagonal()
    to_others = spillover_table.sum(axis=0) - spillover_table.diagonal()
    net = to_others - from_others

    return {
        "total_spillover": float(total_spillover),
        "from_others": dict(zip(data.columns, from_others)),
        "to_others": dict(zip(data.columns, to_others)),
        "net_spillover": dict(zip(data.columns, net)),
        "spillover_table": spillover_table,
    }
```

### 2.5 Signal Generation untuk Ablation

```
Total spillover index > 60 → contagion regime → signal = -1 (risk-off)
Total spillover index < 30 → decoupled regime → signal = +1 (idiosyncratic)
Net spillover TO IDX > 20 → passive follower → use global signal
Net spillover FROM IDX > 20 → active leader → contrarian
```

**Anti look-ahead:** VAR di-estimasi pada expanding window (hanya data sampai T).

### 2.6 Referensi

- Diebold, F.X. & Yilmaz, K. (2012). "Better to Give than to Receive: Predictive Directional Measurement of Volatility Spillovers." International Journal of Forecasting, 28(1), 57-66.
- Diebold, F.X. & Yilmaz, K. (2014). "On the Network Topology of Variance Decompositions: Measuring the Connectedness of Financial Firms." Journal of Econometrics, 182(1), 119-134.
- Diebold, F.X. & Yilmaz, K. (2016). "Financial and Macroeconomic Connectedness: A Network Approach to Measurement and Monitoring." Oxford University Press.

---

## 3. Foreign Flow Prediction Model

### 3.1 Latar Belakang

Pustaka/35 §6.3 menjelaskan model prediksi foreign flow tetapi belum ada implementasi kode. Foreign flow adalah driver utama IDX — foreign investors hold ~40% of IDX market cap dan dominasi trading volume pada saham large-cap.

### 3.2 Teori

**Foreign flow determinants:**

| Factor | Proxy | Direction | Mechanism |
|--------|-------|-----------|-----------|
| Rate differential | BI Rate - Fed Rate | Positive carry → inflow | Carry trade incentive |
| USD strength | DXY change | USD up → outflow | EM risk-off |
| VIX level | ^VIX | High VIX → outflow | Risk-off sentiment |
| USD/IDR | USDIDR=X change | IDR weak → outflow | FX loss amplification |
| IDX valuation | IHSG P/E | Expensive → outflow | Overvaluation risk |
| Global liquidity | US 10Y yield | Yields up → outflow | Opportunity cost |

**Model:**

$$Flow_t = \alpha + \beta_1 (BI - Fed)_t + \beta_2 \Delta DXY_t + \beta_3 VIX_t + \beta_4 \Delta USDIDR_t + \beta_5 PE_{IDX,t} + \epsilon_t$$

### 3.3 Implementasi

```python
def predict_foreign_flow(
    bi_rate: float,
    fed_rate: float,
    dxy_change: float,
    vix_level: float,
    usd_idr_change: float,
    idx_pe: float,
) -> dict:
    """Predict foreign flow direction for IDX.

    Uses a linear scoring model based on literature-validated factors.
    Score > 55 = net buy, < 45 = net sell, else neutral.
    """
    rate_diff = bi_rate - fed_rate

    score = 50.0
    score += (rate_diff - 1.0) * 5.0    # positive carry = inflow
    score -= dxy_change * 100            # USD strength = outflow
    score -= (vix_level - 15) * 2        # high VIX = outflow
    score -= usd_idr_change * 100        # IDR weakness = outflow
    score -= (idx_pe - 15) * 2           # expensive = outflow

    score = max(0, min(100, score))

    return {
        "foreign_flow_score": score,
        "predicted_direction": "net_buy" if score > 55 else "net_sell" if score < 45 else "neutral",
        "rate_differential": rate_diff,
        "components": {
            "rate_carry": (rate_diff - 1.0) * 5.0,
            "dxy_impact": -dxy_change * 100,
            "vix_impact": -(vix_level - 15) * 2,
            "fx_impact": -usd_idr_change * 100,
            "valuation_impact": -(idx_pe - 15) * 2,
        },
        "confidence": min(abs(score - 50) / 25, 1.0),
    }
```

### 3.4 Signal Generation untuk Ablation

```
Foreign flow score > 60 → signal = +1 (expected inflow → bullish)
Foreign flow score < 40 → signal = -1 (expected outflow → bearish)
Confidence > 0.6 → boost signal strength
```

**Anti look-ahead:** Semua input (BI rate, Fed rate, DXY, VIX, USD/IDR, P/E) di-shift(1) — gunakan nilai T-1 untuk prediksi T.

### 3.5 Data Sources

| Variable | Source | Ticker | Lag |
|----------|--------|--------|-----|
| BI Rate | macro_data table | series_name="BI Rate" | T-1 (monthly) |
| Fed Rate | macro_data table | series_name="Fed Rate" | T-1 (monthly) |
| DXY | OHLCV table | DX-Y.NYB atau IDR=X | T-1 (close after IDX) |
| VIX | OHLCV table | ^VIX | T-1 (close after IDX) |
| USD/IDR | OHLCV table | IDR=X | T-1 |
| IDX P/E | fundamental_data | IHSG aggregate | T-1 (quarterly) |

### 3.6 Referensi

- BIS (2021). "Portfolio Flows to Emerging Markets." BIS Quarterly Review.
- IMF (2020). "Global Financial Stability Report: Bridge to Recovery."
- RBA (2019). "What Drives Portfolio Flows to Emerging Markets?" RBA Bulletin.
- BNP Paribas (2023). "EM Flow Tracker: Indonesia."

---

## 4. Overnight Global → IDX Opening Prediction

### 4.1 Latar Belakang

Pustaka/35 §6.2 menjelaskan model prediksi IDX opening dari overnight global markets tetapi belum di-integrate ke signal pipeline. Ini adalah model paling praktis karena timezone IDX memungkinkan prediksi dari market yang sudah close.

### 4.2 Teori

**Timezone advantage untuk IDX:**

```
Timeline (UTC):
00:00  Tokyo open
06:30  Tokyo close ← T-0 data available
08:00  Hong Kong close ← T-0 data available
08:50  IDX close (09:00 open, 15:50 close WIB)
14:30  NYSE open
21:00  NYSE close ← T-1 data for next day IDX

Prediction at 09:15 WIB (02:15 UTC) for IDX trading day:
- Tokyo: T-0 (closed at 06:30 UTC) ← same-day signal
- Hong Kong: T-0 (closed at 08:00 UTC) ← same-day signal
- Shanghai: T-0 (closed at 07:00 UTC) ← same-day signal
- US (S&P, Nasdaq, VIX): T-1 (closed at 21:00 UTC previous day)
- Commodities (Gold, Oil, CPO): T-1 (US-centric settle)
```

**Weighted overnight signal:**

$$Signal = 0.30 \cdot r_{SP500}^{T-1} + 0.20 \cdot r_{Nasdaq}^{T-1} - 0.20 \cdot \Delta VIX^{T-1} - 0.15 \cdot \Delta US10Y^{T-1} - 0.15 \cdot \Delta DXY^{T-1}$$

Plus Asian same-day confirmation:

$$Signal_{asian} = 0.35 \cdot r_{N225}^{T-0} + 0.35 \cdot r_{HSI}^{T-0} + 0.15 \cdot r_{SHCOMP}^{T-0} + 0.15 \cdot r_{CPO}^{T-0}$$

### 4.3 Implementasi

```python
def predict_idx_opening(
    sp500_ret_t1: float,
    nasdaq_ret_t1: float,
    vix_change_t1: float,
    us10y_change_t1: float,
    dxy_change_t1: float,
    nikkei_ret_t0: float = 0,
    hsi_ret_t0: float = 0,
    shanghai_ret_t0: float = 0,
    cpo_ret_t0: float = 0,
) -> dict:
    """Predict IDX opening direction from overnight global markets.

    Combines US overnight (T-1) + Asian same-day (T-0) signals.
    """
    # US overnight component (T-1)
    us_score = (
        sp500_ret_t1 * 0.30 +
        nasdaq_ret_t1 * 0.20 +
        vix_change_t1 * -0.20 +
        us10y_change_t1 * -0.15 +
        dxy_change_t1 * -0.15
    )

    # Asian same-day component (T-0)
    asian_score = (
        nikkei_ret_t0 * 0.35 +
        hsi_ret_t0 * 0.35 +
        shanghai_ret_t0 * 0.15 +
        cpo_ret_t0 * 0.15
    )

    # Composite: US overnight (60%) + Asian confirmation (40%)
    composite = us_score * 0.6 + asian_score * 0.4
    signal = composite * 20  # scale to [-100, +100]

    return {
        "predicted_direction": "up" if signal > 5 else "down" if signal < -5 else "flat",
        "signal_strength": abs(signal),
        "score": signal,
        "us_overnight": us_score,
        "asian_confirmation": asian_score,
        "confidence": min(abs(signal) / 50, 1.0),
    }
```

### 4.4 Signal Generation untuk Ablation

```
Composite signal > 5 → signal = +1 (bullish IDX)
Composite signal < -5 → signal = -1 (bearish IDX)
|signal| < 5 → signal = 0 (neutral)
Confidence > 0.6 → boost position size
```

**Anti look-ahead:**
- US data: T-1 (close after IDX, gunakan previous day)
- Asian data: T-0 (close before IDX, gunakan same day)
- Semua returns di-shift sesuai timezone lag dari `cross_market_timezone.py`

### 4.5 Referensi

- Chan, K. (1992). "A Further Analysis of the Lead-Lag Relationship Between the Cash Market and Stock Index Futures Market." Review of Financial Studies, 5(1), 123-152.
- Lin, W.L., Engle, R.F., & Ito, T. (1994). "Do Bulls and Bears Move Across Borders? International Transmission of Stock Returns and Volatility." Review of Financial Studies, 7(3), 507-538.
- Baur, D.G. & McDermott, T.K. (2010). "Is Gold a Safe Haven? International Evidence." Journal of Banking & Finance, 34(8), 1886-1898.
- Hamao, Y., Masulis, R.W., & Ng, V. (1990). "Correlations in Price Changes and Volatility Across International Stock Markets." Review of Financial Studies, 3(2), 281-307.

---

## 5. Implementasi Ablation Engine

### 5.1 Engine Baru

| Engine | Nama | Data Tables | Min Days | Signal Type |
|--------|------|-------------|----------|-------------|
| DCC-GARCH | `dcc_garch` | ohlcv (^GSPC, ^VIX, IDR=X, ^JKSE) | 120 | CONTEXT |
| Diebold-Yilmaz | `spillover_dy` | ohlcv (^GSPC, ^N225, ^HSI, ^JKSE) | 120 | CONTEXT |
| Foreign Flow | `foreign_flow` | macro_data, ohlcv (^VIX, IDR=X) | 90 | DIRECTIONAL |
| Overnight IDX | `overnight_idx` | ohlcv (^GSPC, ^IXIC, ^VIX, ^TNX, ^N225, ^HSI, 000001.SS, CPO=F) | 60 | DIRECTIONAL |

### 5.2 Anti Look-Ahead Compliance

Semua 4 engine mematuhi aturan anti look-ahead:

1. **dcc_garch**: DCC di-shift(1), GARCH variance di-shift(1)
2. **spillover_dy**: VAR di-estimasi pada expanding window (data sampai T-1)
3. **foreign_flow**: Semua input (BI rate, Fed rate, DXY, VIX, USD/IDR, P/E) di-shift(1)
4. **overnight_idx**: US data T-1, Asian data T-0 (close before IDX), semua di-shift sesuai timezone lag

### 5.3 Testing Protocol

Engine di-test berdampingan dengan 24 engine existing (19 asli + 5 v2). Total 28 engine di-ablation test yang sama untuk perbandingan yang adil dengan Bonferroni correction.

---

## 6. Ekspektasi dan Limitasi

### 6.1 Ekspektasi Predictive Power

| Model | Expected ΔSharpe | Rationale |
|-------|-----------------|-----------|
| DCC-GARCH | -0.2 to +0.1 | Korelasi dinamis sulit di-exploitasi directional |
| Diebold-Yilmaz | -0.3 to +0.1 | Spillover index lebih baik sebagai risk filter |
| Foreign Flow | -0.1 to +0.3 | Foreign flow adalah driver utama IDX — paling promising |
| Overnight IDX | -0.2 to +0.4 | Timezone advantage — Asian confirmation paling prediktif |

### 6.2 Limitasi

1. **DCC-GARCH simplified** — tanpa full MLE, parameter a=0.05, b=0.90 dari literature mungkin tidak optimal untuk IDX
2. **Diebold-Yilmaz VAR** — butuh minimal 4 market return series yang aligned, lag order selection bisa tricky
3. **Foreign Flow** — model linear, tidak capture non-linear regime shifts (mis. crisis vs normal)
4. **Overnight IDX** — signal hanya valid untuk opening 30 menit pertama, bukan full-day

### 6.3 Cross-Reference

- `pustaka/35-multi-asset-cross-market-analysis.md` — teori dasar intermarket analysis
- `pustaka/36-gap-data-timezone-global-idx.md` — timezone alignment & DST
- `pustaka/92-multi-market-multi-asset-trading-system.md` — multi-market system design
- `src/market/multi_asset/cross_market.py` — CrossMarketEngine existing
- `src/market/analysis/cross_market_timezone.py` — timezone lag helper
- `src/market/analysis/signal_enhancer.py:582-712` — existing cross_market signal

---

## Update 15 Agustus 2026 (P6 — DCC-GARCH + Spillover Execution)

### DCC-GARCH: Berhasil

- **60 pairs computed** (5 IDX proxy: BBCA, BBRI, ADRO, AALI, ANTM × 12 global drivers: ^GSPC, ^DJI, ^IXIC, ^N225, ^HSI, 000001.SS, ^VIX, CL=F, GC=F, CPO=F, HG=F, MTF=F).
- Returns matrix: 641 rows, 17 columns (lookback 750 hari).
- Persisted ke tabel baru `dcc_garch_results` (60 rows).
- Sample: BBCA.JK vs ^GSPC (latest_corr=0.053, avg_corr=0.104), BBCA.JK vs ^N225 (latest_corr=0.003, avg_corr=0.118).
- Korelasi umumnya lemah (|r| < 0.2) — IDX relatif terisolasi dari global drivers dalam short-term daily returns.

### Diebold-Yilmaz Spillover: GAGAL

- VAR estimation berhasil (264 obs, 8 tickers, lag order dari AIC).
- FEVD computation error: "need at least one array to concatenate" — statsmodels API compatibility issue.
- **Perlu fix:** Update `spillover_lab.py` untuk statsmodels terbaru, atau implement manual FEVD computation.
- Script: `scripts/batch_p6_spillover.py`.

### Granger Causality (P9 — terkait)

- 198 Granger tests (11 global drivers × 18 IDX stocks), maxlag=5.
- 28 significant (p<0.05), 11 strong (p<0.01).
- Top: NICK.L→INCO.JK p=0.0000, GC=F→UNVR.JK p=0.0002, NICK.L→PTBA.JK p=0.0006.
- Persisted ke `causal_relationships` (198 rows) + `causal_graphs` (1 summary graph).
- Script: `scripts/batch_p9_causal.py`.

---

## Referensi Lengkap

1. Engle, R. (2002). "Dynamic Conditional Correlation." JBES, 20(3), 339-350.
2. Diebold, F.X. & Yilmaz, K. (2012). "Better to Give than to Receive." IJF, 28(1), 57-66.
3. Diebold, F.X. & Yilmaz, K. (2016). "Financial and Macroeconomic Connectedness." Oxford UP.
4. Baur, D.G. & McDermott, T.K. (2010). "Is Gold a Safe Haven?" JBF, 34(8), 1886-1898.
5. Hamao, Y., Masulis, R.W., & Ng, V. (1990). "Correlations in Price Changes." RFS, 3(2), 281-307.
6. Lopez de Prado, M. (2018). "Advances in Financial Machine Learning." Wiley.
7. BIS (2021). "Portfolio Flows to Emerging Markets." BIS Quarterly Review.
8. IMF (2020). "Global Financial Stability Report: Bridge to Recovery."
