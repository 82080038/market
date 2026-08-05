# Analisis Teknikal

> **Tujuan:** Dokumen ini adalah referensi komprehensif tentang analisis teknikal — indikator, pola, strategi, dan implementasi — sebagai basis untuk membangun modul analisis teknikal dalam aplikasi pasar modal.

---

## Daftar Isi

1. [Konsep Dasar Analisis Teknikal](#1-konsep-dasar-analisis-teknikal)
2. [Klasifikasi Indikator](#2-klasifikasi-indikator)
3. [Indikator Trend](#3-indikator-trend)
4. [Indikator Momentum](#4-indikator-momentum)
5. [Indikator Volatilitas](#5-indikator-volatilitas)
6. [Indikator Volume](#6-indikator-volume)
7. [Pola Chart (Chart Patterns)](#7-pola-chart-chart-patterns)
8. [Candlestick Patterns](#8-candlestick-patterns)
9. [Konsep Support dan Resistance](#9-konsep-support-dan-resistance)
10. [Kombinasi Indikator](#10-kombinasi-indikator)
11. [Timeframe Analysis](#11-timeframe-analysis)
12. [Implementasi Kode](#12-implementasi-kode)
13. [Limitasi dan Pitfalls](#13-limitasi-dan-pitfalls)

---

## 1. Konsep Dasar Analisis Teknikal

### 1.1 Definisi

Analisis teknikal adalah metode evaluasi instrumen keuangan dengan menganalisis data statistik (harga, volume, open interest) yang dihasilkan oleh aktivitas pasar. Tidak seperti analisis fundamental yang mengevaluasi nilai intrinsik, analisis teknikal berfokus pada **pola harga historis** dan **indikator matematis**.

### 1.2 Tiga Asumsi Dasar

1. **Market action discounts everything:** Harga mencerminkan semua informasi (fundamental, makro, sentimen)
2. **Prices move in trends:** Harga bergerak dalam tren yang dapat diidentifikasi
3. **History repeats itself:** Pola harga cenderung berulang (psikologi pasar)

### 1.3 Leading vs Lagging Indicators

| Tipe | Karakteristik | Contoh |
|------|---------------|--------|
| **Leading** | Memprediksi pergerakan sebelum terjadi, lebih prone ke false signals | RSI, Stochastic |
| **Lagging** | Mengkonfirmasi trend yang sudah dimulai, lebih reliable tapi late | Moving Averages, MACD |

### 1.4 Analisis Teknikal vs Fundamental

| Aspek | Teknikal | Fundamental |
|-------|----------|-------------|
| **Fokus** | Harga & volume | Nilai intrinsik bisnis |
| **Data** | Chart, indikator | Laporan keuangan, rasio |
| **Timeframe** | Short-medium term | Long term |
| **Tujuan** | Timing entry/exit | Valuasi, selection |
| **Asumsi** | Harga mencerminkan semua | Harga konvergen ke nilai |

---

## 2. Klasifikasi Indikator

```
Indikator Teknikal
├── Trend Indicators
│   ├── Moving Averages (SMA, EMA, WMA)
│   ├── MACD
│   ├── ADX/DMI
│   ├── Ichimoku Cloud
│   └── Parabolic SAR
├── Momentum Indicators
│   ├── RSI
│   ├── Stochastic Oscillator
│   ├── ROC (Rate of Change)
│   ├── CCI (Commodity Channel Index)
│   └── Williams %R
├── Volatility Indicators
│   ├── Bollinger Bands
│   ├── ATR (Average True Range)
│   ├── Keltner Channels
│   └── Standard Deviation
└── Volume Indicators
    ├── OBV (On-Balance Volume)
    ├── VWAP
    ├── Volume Profile
    ├── MFI (Money Flow Index)
    └── Accumulation/Distribution Line
```

---

## 3. Indikator Trend

### 3.1 Simple Moving Average (SMA)

$$SMA_n = \frac{1}{n} \sum_{i=0}^{n-1} P_{t-i}$$

**Periode umum:**
- **SMA 20:** Short-term trend
- **SMA 50:** Medium-term trend
- **SMA 100:** Long-term trend
- **SMA 200:** Long-term trend (paling penting)

**Sinyal:**
- Harga di atas SMA 200 → bullish long-term
- Harga di bawah SMA 200 → bearish long-term
- **Golden Cross:** SMA 50 crosses above SMA 200 → bullish
- **Death Cross:** SMA 50 crosses below SMA 200 → bearish

### 3.2 Exponential Moving Average (EMA)

$$EMA_t = \alpha \cdot P_t + (1 - \alpha) \cdot EMA_{t-1}$$

Dimana $\alpha = \frac{2}{n+1}$

**Keunggulan EMA vs SMA:**
- Lebih responsif terhadap perubahan harga terbaru
- Lebih cepat memberikan sinyal
- Tetapi lebih banyak false signals di choppy market

**Periode umum:**
- **EMA 9:** Very short-term, day trading
- **EMA 12 & 26:** Komponen MACD
- **EMA 21:** Short-to-intermediate term
- **EMA 50 & 200:** Major trend indicators

### 3.3 Weighted Moving Average (WMA)

$$WMA_n = \frac{\sum_{i=0}^{n-1} (n-i) \cdot P_{t-i}}{\sum_{i=0}^{n-1} (n-i)}$$

Memberikan bobot lebih besar pada data terbaru, tetapi dengan linear weighting (bukan exponential).

### 3.4 MACD (Moving Average Convergence Divergence)

Dikembangkan oleh **Gerald Appel** (late 1970s).

**Komponen:**
- **MACD Line:** EMA(12) - EMA(26)
- **Signal Line:** EMA(9) of MACD Line
- **Histogram:** MACD Line - Signal Line

**Sinyal:**

| Sinyal | Kondisi | Implikasi |
|--------|---------|-----------|
| **Golden Cross** | MACD crosses above Signal | Bullish (buy signal) |
| **Death Cross** | MACD crosses below Signal | Bearish (sell signal) |
| **Zero Line Cross (up)** | MACD crosses above 0 | Bullish confirmation |
| **Zero Line Cross (down)** | MACD crosses below 0 | Bearish confirmation |
| **Bullish Divergence** | Price new low, MACD higher low | Potential reversal up |
| **Bearish Divergence** | Price new high, MACD lower high | Potential reversal down |
| **Histogram Shrinking** | Bars getting smaller | Momentum fading (early warning) |

**Implementasi:**
```python
def macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram
```

### 3.5 ADX (Average Directional Index)

Mengukur **kekuatan trend** (bukan arah).

- **+DI (Plus Directional Indicator):** Bullish pressure
- **-DI (Minus Directional Indicator):** Bearish pressure
- **ADX:** Kekuatan trend keseluruhan

**Interpretasi:**

| ADX Value | Kekuatan Trend |
|-----------|----------------|
| < 20 | Weak/No trend |
| 20-25 | Trend forming |
| 25-50 | Strong trend |
| 50-75 | Very strong trend |
| > 75 | Extremely strong (rare) |

### 3.6 Ichimoku Cloud (Ichimoku Kinko Hyo)

Dikembangkan oleh Goichi Hosoda (1960s). Lima komponen:

| Komponen | Periode | Deskripsi |
|----------|---------|-----------|
| **Tenkan-sen (Conversion Line)** | 9 | (9-high + 9-low) / 2 |
| **Kijun-sen (Base Line)** | 26 | (26-high + 26-low) / 2 |
| **Senkou Span A (Leading Span A)** | — | (Tenkan + Kijun) / 2, shifted 26 ahead |
| **Senkou Span B (Leading Span B)** | 52 | (52-high + 52-low) / 2, shifted 26 ahead |
| **Chikou Span (Lagging Span)** | — | Close shifted 26 back |

**Cloud (Kumo):** Area antara Senkou Span A dan B

- Harga di atas cloud → bullish
- Harga di bawah cloud → bearish
- Harga di dalam cloud → sideways/neutral
- Cloud hijau (A > B) → bullish cloud
- Cloud merah (A < B) → bearish cloud

### 3.7 Parabolic SAR (Stop and Reverse)

Dikembangkan oleh J. Welles Wilder.

$$SAR_{t+1} = SAR_t + AF \times (EP_t - SAR_t)$$

Dimana:
- AF = Acceleration Factor (starts at 0.02, increments by 0.02, max 0.20)
- EP = Extreme Point (highest high atau lowest low)

**Sinyal:**
- Dot di bawah harga → uptrend (bullish)
- Dot di atas harga → downtrend (bearish)
- Flip dot → trend reversal signal

---

## 4. Indikator Momentum

### 4.1 RSI (Relative Strength Index)

Dikembangkan oleh **J. Welles Wilder** (1978).

$$RSI = 100 - \frac{100}{1 + RS}$$

$$RS = \frac{\text{Average Gain over N periods}}{\text{Average Loss over N periods}}$$

**Periode default:** 14

**Interpretasi:**

| RSI | Kondisi | Sinyal |
|-----|---------|--------|
| > 70 | Overbought | Potential sell / pullback |
| < 30 | Oversold | Potential buy / bounce |
| ~ 50 | Neutral | Balance antara buyer & seller |
| > 80 | Extremely overbought | Strong bullish momentum |
| < 20 | Extremely oversold | Strong bearish momentum |

**Advanced RSI techniques:**

- **RSI Divergence:** Price new high tapi RSI lower high → bearish reversal
- **RSI Support/Resistance:** RSI sendiri dapat memiliki support/resistance
- **RSI 50 crossover:** Cross above 50 = bullish, cross below 50 = bearish
- **Failure swings:** RSI fails to reach previous high/low → reversal signal

**Implementasi:**
```python
def rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
```

### 4.2 Stochastic Oscillator

Dikembangkan oleh **George Lane** (1950s).

$$\%K = \frac{C - L_n}{H_n - L_n} \times 100$$

$$\%D = SMA_3(\%K)$$

Dimana:
- $C$ = close price saat ini
- $L_n$ = lowest low dalam N periode
- $H_n$ = highest high dalam N periode

**Periode default:** 14,3 (14 periode %K, 3 periode %D)

**Interpretasi:**

| Stochastic | Kondisi | Sinyal |
|------------|---------|--------|
| > 80 | Overbought | Potential sell |
| < 20 | Oversold | Potential buy |
| %K crosses above %D | Bullish cross | Buy signal |
| %K crosses below %D | Bearish cross | Sell signal |

### 4.3 ROC (Rate of Change)

$$ROC = \frac{C_t - C_{t-n}}{C_{t-n}} \times 100$$

Mengukur persentase perubahan harga dalam N periode.

### 4.4 CCI (Commodity Channel Index)

$$CCI = \frac{TP - SMA(TP)}{0.015 \times \text{Mean Deviation}}$$

Dimana $TP = \frac{H + L + C}{3}$ (Typical Price)

**Interpretasi:**
- CCI > +100: Overbought / strong bullish
- CCI < -100: Oversold / strong bearish
- Cross above +100: Buy signal
- Cross below -100: Sell signal

### 4.5 Williams %R

$$\%R = \frac{H_n - C}{H_n - L_n} \times -100$$

**Interpretasi:**
- %R > -20: Overbought
- %R < -80: Oversold
- Mirip Stochastic tetapi inverted scale

---

## 5. Indikator Volatilitas

### 5.1 Bollinger Bands

Dikembangkan oleh **John Bollinger** (1980s).

**Komponen:**
- **Middle Band:** SMA(20)
- **Upper Band:** SMA(20) + (2 × StdDev(20))
- **Lower Band:** SMA(20) - (2 × StdDev(20))

**Properti statistik:** ~95.4% harga berada dalam 2 standard deviasi (asumsi normal distribution).

**Sinyal:**

| Sinyal | Kondisi | Implikasi |
|--------|---------|-----------|
| **Bollinger Squeeze** | Bands menyempit | Volatility compressing → breakout imminent |
| **Band Expansion** | Bands melebar | Volatility increasing → trend strong |
| **Price touches upper band** | Harga di upper band | Overbought (tapi bisa continuation) |
| **Price touches lower band** | Harga di lower band | Oversold (tapi bisa continuation) |
| **Double bottom at lower band** | Dua kali bounce di lower band | Strong support, buy signal |

**%B Indicator:**
$$\%B = \frac{Price - Lower\ Band}{Upper\ Band - Lower\ Band}$$

- %B > 1: Harga di atas upper band (extreme strength)
- %B = 0.5: Harga di middle band
- %B < 0: Harga di bawah lower band (extreme weakness)

**Band Width:**
$$Band\ Width = \frac{Upper - Lower}{Middle} \times 100$$

Band Width yang mencapai 6-month low → Squeeze → breakout imminent.

**Implementasi:**
```python
def bollinger_bands(close, window=20, num_std=2):
    sma = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    middle = sma
    return upper, middle, lower
```

### 5.2 ATR (Average True Range)

Dikembangkan oleh **J. Welles Wilder**.

$$True\ Range = \max(H_t - L_t,\ |H_t - C_{t-1}|,\ |L_t - C_{t-1}|)$$

$$ATR = \frac{1}{n} \sum_{i=0}^{n-1} TR_{t-i}$$

**Periode default:** 14

**Interpretasi:**
- ATR mengukur **volatilitas**, bukan arah
- ATR tinggi → volatilitas tinggi
- ATR rendah → volatilitas rendah
- Digunakan untuk position sizing (volatility-adjusted)

**Implementasi:**
```python
def atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()
```

### 5.3 Keltner Channels

- **Middle:** EMA(20)
- **Upper:** EMA(20) + (2 × ATR(10))
- **Lower:** EMA(20) - (2 × ATR(10))

Mirip Bollinger Bands tetapi menggunakan ATR (bukan StdDev) → lebih stabil.

### 5.4 Standard Deviation

$$\sigma = \sqrt{\frac{1}{n-1} \sum_{i=0}^{n-1} (P_{t-i} - \bar{P})^2}$$

Mengukur dispersi harga dari rata-rata. Dasar dari Bollinger Bands.

---

## 6. Indikator Volume

### 6.1 OBV (On-Balance Volume)

$$OBV_t = OBV_{t-1} + \begin{cases} +V_t & \text{if } C_t > C_{t-1} \\ -V_t & \text{if } C_t < C_{t-1} \\ 0 & \text{if } C_t = C_{t-1} \end{cases}$$

**Interpretasi:**
- OBV naik → accumulation (smart money buying)
- OBV turun → distribution (smart money selling)
- OBV divergence dengan price → reversal signal

### 6.2 VWAP (Volume-Weighted Average Price)

$$VWAP = \frac{\sum (P_i \times V_i)}{\sum V_i}$$

**Penggunaan:**
- Benchmark untuk execution quality
- Harga di atas VWAP → bullish intraday
- Harga di bawah VWAP → bearish intraday
- Institutional traders target VWAP

### 6.3 MFI (Money Flow Index)

$$MFI = 100 - \frac{100}{1 + \text{Money Flow Ratio}}$$

Mirip RSI tetapi memasukkan volume:

$$Money\ Flow\ Ratio = \frac{\text{Positive Money Flow}}{\text{Negative Money Flow}}$$

**Interpretasi:**
- MFI > 80: Overbought
- MFI < 20: Oversold

### 6.4 Accumulation/Distribution Line

$$CL_t = CL_{t-1} + \frac{(C_t - L_t) - (H_t - C_t)}{H_t - L_t} \times V_t$$

Mengukur aliran uang masuk/keluar berdasarkan posisi close dalam range.

### 6.5 Volume Profile

Menampilkan volume pada setiap level harga (bukan waktu). Mengidentifikasi:

- **Point of Control (POC):** Level harga dengan volume tertinggi
- **Value Area:** Range harga dengan 70% volume
- **High Volume Nodes (HVN):** Level harga dengan volume tinggi (support/resistance)
- **Low Volume Nodes (LVN):** Level harga dengan volume rendah (fast move through)

---

## 7. Pola Chart (Chart Patterns)

### 7.1 Reversal Patterns

#### Head and Shoulders

```
        Head
         /\
        /  \
  Left /    \ Right
 Shoulder    Shoulder
   /\        /\
  /  \      /  \
```

- **Head:** Peak tertinggi
- **Left/Right Shoulder:** Peak lebih rendah, simetris
- **Neckline:** Support line connecting lows
- **Sinyal:** Break below neckline = bearish reversal
- **Target:** Height of head below neckline

#### Inverse Head and Shoulders

Mirror image → bullish reversal signal.

#### Double Top (M-Shape)

```
  Peak 1   Peak 2
    /\      /\
   /  \    /  \
  /    \  /    /
        \/    /
  Support----/
```

- Dua peak pada level yang sama
- Break below support = bearish
- Target: Height dari peak ke support

#### Double Bottom (W-Shape)

Mirror image → bullish reversal.

#### Triple Top / Triple Bottom

Tiga peak/trough pada level yang sama → lebih kuat dari double.

#### Rounding Bottom (Saucer)

Bentuk mangkuk → akumulasi bertahap → bullish reversal jangka panjang.

### 7.2 Continuation Patterns

#### Flag

```
Prior trend →
  /\
 /  \____
          \  Flag
           \  /
            \/
            → Continuation
```

Channel kecil melawan trend → continuation setelah breakout.

#### Pennant

Mirip flag tetapi segitiga (converging lines).

#### Triangle

| Tipe | Deskripsi | Sinyal |
|------|-----------|--------|
| **Ascending** | Flat upper, rising lower | Bullish |
| **Descending** | Rising upper, flat lower | Bearish |
| **Symmetrical** | Converging both | Direction uncertain |

#### Wedge

| Tipe | Deskripsi | Sinyal |
|------|-----------|--------|
| **Rising Wedge** | Both lines rising, converging | Bearish |
| **Falling Wedge** | Both lines falling, converging | Bullish |

#### Cup and Handle

Bentuk cangkir + handle kecil → bullish continuation.

### 7.3 Gap Patterns

| Gap | Deskripsi | Implikasi |
|-----|-----------|-----------|
| **Breakaway Gap** | Gap di awal trend baru | Strong signal, likely tidak diisi |
| **Runaway/Measuring Gap** | Gap di tengah trend | Continuation, target = first gap + move |
| **Exhaustion Gap** | Gap di akhir trend | Reversal signal, likely diisi |
| **Common Gap** | Gap di sideways | Likely diisi, tidak signifikan |

---

## 8. Candlestick Patterns

### 8.1 Single Candle Patterns

| Pattern | Deskripsi | Sinyal |
|---------|-----------|--------|
| **Doji** | Open ≈ Close | Indecision, potential reversal |
| **Hammer** | Small body, long lower shadow | Bullish reversal (downtrend) |
| **Hanging Man** | Small body, long lower shadow | Bearish reversal (uptrend) |
| **Inverted Hammer** | Small body, long upper shadow | Bullish reversal (downtrend) |
| **Shooting Star** | Small body, long upper shadow | Bearish reversal (uptrend) |
| **Marubozu** | No shadow (full body) | Strong conviction |

### 8.2 Two Candle Patterns

| Pattern | Deskripsi | Sinyal |
|---------|-----------|--------|
| **Bullish Engulfing** | Large green candle engulfs previous red | Bullish reversal |
| **Bearish Engulfing** | Large red candle engulfs previous green | Bearish reversal |
| **Tweezer Top** | Two candles same high | Bearish reversal |
| **Tweezer Bottom** | Two candles same low | Bullish reversal |
| **Harami** | Small candle inside previous large | Reversal (direction depends on color) |

### 8.3 Three Candle Patterns

| Pattern | Deskripsi | Sinyal |
|---------|-----------|--------|
| **Morning Star** | Red → Doji → Green | Bullish reversal |
| **Evening Star** | Green → Doji → Red | Bearish reversal |
| **Three White Soldiers** | Three green candles, ascending | Strong bullish |
| **Three Black Crows** | Three red candles, descending | Strong bearish |
| **Three Inside Up** | Harami + confirmation | Bullish reversal |
| **Three Inside Down** | Bearish Harami + confirmation | Bearish reversal |

---

## 9. Konsep Support dan Resistance

### 9.1 Definisi

- **Support:** Level harga di mana tekanan beli cukup kuat untuk menghentikan/membalikkan penurunan
- **Resistance:** Level harga di mana tekanan jual cukup kuat untuk menghentikan/membalikkan kenaikan

### 9.2 Jenis Support/Resistance

| Tipe | Deskripsi |
|------|-----------|
| **Horizontal** | Level harga spesifik yang diuji multiple times |
| **Trendline** | Garis miring connecting highs/lows |
| **Moving Average** | MA sebagai dynamic support/resistance |
| **Fibonacci Retracement** | Level 23.6%, 38.2%, 50%, 61.8%, 78.6% |
| **Round Numbers** | Angka bulat (Rp1000, Rp5000, dll.) |
| **Prior High/Low** | Swing high/low sebelumnya |
| **Volume Profile** | High Volume Nodes sebagai S/R |

### 9.3 Role Reversal

- Support yang ditembus → menjadi resistance
- Resistance yang ditembus → menjadi support

### 9.4 Fibonacci Retracement

| Level | Signifikansi |
|-------|-------------|
| 23.6% | Shallow retracement, strong trend |
| 38.2% | Moderate retracement |
| 50.0% | Moderate retracement (not official Fibonacci) |
| 61.8% | Golden ratio, key level |
| 78.6% | Deep retracement, trend masih hidup jika hold |

### 9.5 Fibonacci Extension

| Level | Target |
|-------|--------|
| 127.2% | Extension target 1 |
| 161.8% | Extension target 2 (golden ratio) |
| 261.8% | Extension target 3 |

---

## 10. Kombinasi Indikator

### 10.1 Prinsip Kombinasi

1. **Jangan gunakan indikator yang mengukur hal yang sama** (mis. RSI + Stochastic = redundan)
2. **Kombinasikan kategori berbeda:** Trend + Momentum + Volatility
3. **Maksimal 3 indikator** — lebih banyak = analysis paralysis
4. **Satu untuk arah, satu untuk timing, satu untuk risiko**

### 10.2 Kombinasi yang Direkomendasikan

| Style | Direction | Timing | Risk |
|-------|-----------|--------|------|
| **Trend Following** | EMA 200 | MACD Signal | ATR Stop |
| **Mean Reversion** | Bollinger Bands | RSI | Band Width |
| **Breakout** | Donchian Channel | Volume | ATR Position Size |
| **All-in-One** | Ichimoku Full | — | ATR |
| **Scalping** | VWAP | Stochastic | ATR(5) |

### 10.3 Confluence Trading

Confluence = area di mana multiple sinyal bertemu:

- EMA 200 + Fibonacci 61.8% + prior support
- Bollinger lower band + RSI < 30 + bullish candlestick
- Volume POC + 50% retracement + trendline

Semakin banyak confluence, semakin tinggi probabilitas sukses.

---

## 11. Timeframe Analysis

### 11.1 Multiple Timeframe Strategy

```
Long-term (Weekly/Daily)  → Tentukan trend utama
Medium-term (4H/1H)       → Cari setup
Short-term (15m/5m)       → Timing entry
```

### 11.2 Timeframe Matrix

| Timeframe | Tipe Trading | Hold Period | Indikator Utama |
|-----------|-------------|-------------|-----------------|
| 1m-5m | Scalping | Detik-menit | VWAP, Stochastic, EMA 9 |
| 15m-1H | Day trading | Jam | MACD, RSI, Volume |
| 4H-Daily | Swing trading | Hari-minggu | EMA 50/200, Bollinger, ADX |
| Weekly-Monthly | Position trading | Minggu-bulan | SMA 200, Ichimoku, Trendlines |

### 11.3 Top-Down Analysis

1. **Macro:** Trend market keseluruhan (IHSG/S&P 500)
2. **Sector:** Sektor yang outperform
3. **Stock:** Saham terbaik di sektor
4. **Entry:** Timing entry di timeframe lebih kecil

---

## 12. Implementasi Kode

### 12.1 Library Python

```python
# Library utama
import pandas as pd
import numpy as np
import talib  # atau pandas-ta
from ta import add_all_ta_features

# Untuk charting
import mplfinance as mpf
import plotly.graph_objects as go
```

### 12.2 Indikator Komprehensif

```python
def compute_all_indicators(df):
    """Compute all technical indicators for a DataFrame with OHLCV."""
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # Trend
    df['sma_20'] = close.rolling(20).mean()
    df['sma_50'] = close.rolling(50).mean()
    df['sma_200'] = close.rolling(200).mean()
    df['ema_12'] = close.ewm(span=12, adjust=False).mean()
    df['ema_26'] = close.ewm(span=26, adjust=False).mean()
    df['ema_50'] = close.ewm(span=50, adjust=False).mean()
    df['ema_200'] = close.ewm(span=200, adjust=False).mean()

    # MACD
    df['macd'] = df['ema_12'] - df['ema_26']
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # Momentum
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
    df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))

    # Stochastic
    low_14 = low.rolling(14).min()
    high_14 = high.rolling(14).max()
    df['stoch_k'] = 100 * (close - low_14) / (high_14 - low_14)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()

    # Volatility
    df['bb_middle'] = close.rolling(20).mean()
    df['bb_std'] = close.rolling(20).std()
    df['bb_upper'] = df['bb_middle'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_middle'] - 2 * df['bb_std']
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle'] * 100

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    # Volume
    df['obv'] = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    df['vwap'] = (df['close'] * volume).cumsum() / volume.cumsum()

    return df
```

### 12.3 Pattern Detection

```python
def detect_patterns(df):
    """Detect common candlestick patterns."""
    body = (df['close'] - df['open']).abs()
    upper_shadow = df['high'] - df[['open', 'close']].max(axis=1)
    lower_shadow = df[['open', 'close']].min(axis=1) - df['low']
    total_range = df['high'] - df['low']

    # Doji
    df['doji'] = body <= total_range * 0.1

    # Hammer (bullish reversal)
    df['hammer'] = (
        (lower_shadow > 2 * body) &
        (upper_shadow < body * 0.3) &
        (df['close'] > df['open'])
    )

    # Shooting Star (bearish reversal)
    df['shooting_star'] = (
        (upper_shadow > 2 * body) &
        (lower_shadow < body * 0.3) &
        (df['close'] < df['open'])
    )

    # Bullish Engulfing
    df['bullish_engulfing'] = (
        (df['close'].shift(1) < df['open'].shift(1)) &  # prev red
        (df['close'] > df['open']) &  # curr green
        (df['close'] > df['open'].shift(1)) &
        (df['open'] < df['close'].shift(1))
    )

    return df
```

---

## 13. Limitasi dan Pitfalls

### 13.1 Indikator Tidak Memprediksi Masa Depan

> **Setiap indikator berdasarkan data masa lalu.** RSI memberitahu seberapa cepat harga bergerak. MACD memberitahu bagaimana momentum bergesek. Bollinger Bands memberitahu seberapa volatile harga. Semua mendeskripsikan masa lalu, bukan memprediksi masa depan.

### 13.2 Lagging Nature

- Moving averages dan MACD selalu **late** — sinyal datang setelah pergerakan terjadi
- Di fast-moving market, sinyal MACD bisa terlambat beberapa bar
- Gunakan leading indicators (RSI, Stochastic) untuk early warning

### 13.3 False Signals di Choppy Market

- Indikator trend (MA, MACD) menghasilkan banyak false signals di sideways market
- Indikator momentum (RSI, Stochastic) memberikan premature overbought/oversold di strong trend

### 13.4 Overfitting

- Optimasi parameter indikator pada data historis → overfitting
- Pastikan out-of-sample testing
- Gunakan walk-forward analysis

### 13.5 Confirmation Bias

- Trader cenderung melihat sinyal yang mendukung bias mereka
- Selalu tunggu konfirmasi (close above/below level, tidak hanya touch)

### 13.6 Best Practices

1. **Gunakan multiple timeframe** untuk konfirmasi
2. **Kombinasikan indikator** dari kategori berbeda
3. **Tunggu konfirmasi** sebelum entry
4. **Backtest** sebelum live trading
5. **Gunakan indikator sebagai alat bantu**, bukan oracle
6. **Risk management** selalu di atas sinyal teknikal

---

## Referensi

1. Longbridge — Guide to U.S. Stock Technical Indicators: RSI, MACD, and Bollinger Bands
2. ChartingLens — RSI, MACD & Bollinger Bands Explained: Complete Guide
3. Brokerlytic — Technical Indicators Deep Dive: RSI, MACD, Bollinger Bands, ATR & Ichimoku
4. StockCalculator — Technical Indicators: Complete Trading Guide
5. DayTradingToolkit — RSI, MACD & Bollinger Bands: When They Help (And When They Lie)
6. John J. Murphy — Technical Analysis of the Financial Markets
7. Steve Nison — Japanese Candlestick Charting Techniques
8. Alexander Elder — Trading for a Living

---

> **Catatan:** Untuk implementasi produksi dalam aplikasi, lihat `11-knowledge-transfer-aplikasi.md` dan `12-panduan-membangun-aplikasi-pasar-modal.md`.
