# Market Influence Knowledge Base

> **Tujuan:** Dokumen ini mendefinisikan basis pengetahuan terpusat yang menjawab pertanyaan: *"Apa yang mempengaruhi ticker X, dari sumber mana, dengan arah apa, lag berapa hari, melalui mekanisme apa, dan seberapa kuat?"*

---

## Daftar Isi

1. [Konsep dan Motivasi](#1-konsep-dan-motivasi)
2. [Skema Tabel](#2-skema-tabel)
3. [Sumber Data yang Dikonsolidasi](#3-sumber-data-yang-dikonsolidasi)
4. [Python Module](#4-python-module)
5. [Contoh Penggunaan](#5-contoh-penggunaan)
6. [Integrasi dengan Pipeline](#6-integrasi-dengan-pipeline)
7. [Limitasi dan Pengembangan](#7-limitasi-dan-pengembangan)

---

## 1. Konsep dan Motivasi

### 1.1 Masalah

Sebelum KB ini, data influence tersebar di 4 tabel terpisah:

| Tabel | Records | Jenis Data |
|-------|---------|-----------|
| `cross_market_coefficients` | 15 | Granger causality global index → ^JKSE |
| `causal_relationships` | 198 | Granger causality per-ticker (p<0.05: 28) |
| `commodity_to_stock_map` | 28 | Sensitivitas komoditas per saham |
| `pustaka/102` (teoretis) | — | Mapping sektor → global driver |

Tidak ada cara untuk query: *"Tampilkan semua pengaruh untuk BBCA.JK dari semua sumber"*. Harus query 4 tabel berbeda dengan schema berbeda.

### 1.2 Solusi

Satu tabel `market_influence_kb` yang mengonsolidasi semua sumber influence dengan schema seragam. Setiap baris menjawab: **"source_ticker mempengaruhi target_ticker dengan direction X, lag Y hari, strength Z, melalui mekanisme M."**

---

## 2. Skema Tabel

```sql
CREATE TABLE market_influence_kb (
    id              SERIAL PRIMARY KEY,
    target_ticker   VARCHAR(30) NOT NULL,      -- ticker yang dipengaruhi
    target_sector   VARCHAR(50),               -- sektor target
    source_ticker   VARCHAR(30) NOT NULL,      -- ticker sumber pengaruh
    source_name     VARCHAR(100),              -- nama deskriptif sumber
    source_layer    VARCHAR(20),               -- global_index, commodity, fx, macro_data, macro_rate
    influence_type  VARCHAR(30) NOT NULL,      -- jenis influence (lihat §3)
    direction       VARCHAR(10) NOT NULL,      -- positive, negative, mixed, neutral
    lag_days        INTEGER,                   -- lag dalam hari (0=T-0, 1=T-1)
    strength        NUMERIC(5,4),              -- 0.0000–1.0000
    p_value         NUMERIC(8,5),              -- statistical significance
    mechanism       TEXT,                      -- penjelasan kausal
    regime          VARCHAR(10),               -- BEAR/BULL/NEUTRAL (jika applicable)
    source_table    VARCHAR(50),               -- asal data (untuk traceability)
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(target_ticker, source_ticker, lag_days, influence_type)
);
```

### 2.1 Index

| Index | Kolom | Fungsi |
|-------|-------|--------|
| `idx_mikb_target` | `target_ticker` | Query: "apa yang mempengaruhi X?" |
| `idx_mikb_source` | `source_ticker` | Query: "apa yang dipengaruhi oleh X?" |
| `idx_mikb_sector` | `target_sector` | Query: "apa yang mempengaruhi sektor Y?" |
| `idx_mikb_type` | `influence_type` | Filter by jenis influence |

---

## 3. Sumber Data yang Dikonsolidasi

### 3.1 sector_global_link (1,626 records)

Dari `pustaka/102-sector-global-link-engine.md`. Mapping teoretis sektor IDX → global driver.

| Sektor IDX | Global Driver 1 | Global Driver 2 | Lag |
|------------|-----------------|-----------------|-----|
| Energy | `CL=F` (Crude Oil) | `^GSPC` (S&P 500) | T-1 |
| Basic Materials | `GC=F` (Gold) | `000001.SS` (Shanghai) | T-1/T-0 |
| Financials | `^TNX` (US 10Y) | `^GSPC` (S&P 500) | T-1 |
| Consumer Non-Cyclicals | `IDR=X` (USD/IDR) | `^GSPC` (S&P 500) | T-1 |
| Consumer Cyclicals | `^IXIC` (Nasdaq) | `^GSPC` (S&P 500) | T-1 |
| Communication Services | `^IXIC` (Nasdaq) | — | T-1 |
| Industrials | `000001.SS` (Shanghai) | `^GSPC` (S&P 500) | T-0/T-1 |
| Properties & Real Estate | `^TNX` (US 10Y) | — | T-1 |
| Technology | `^IXIC` (Nasdaq) | — | T-1 |
| Healthcare | `^GSPC` (S&P 500) | — | T-1 |
| Utilities | `^TNX` (US 10Y) | — | T-1 |
| Transportation & Logistic | `^GSPC`, `000001.SS` | — | T-1/T-0 |
| Infrastructures | `^GSPC` | — | T-1 |

### 3.2 commodity_sensitivity (28 records)

Dari `commodity_to_stock_map`. Sensitivitas empiris komoditas per saham.

| Komoditas | Ticker | Sensitivity |
|-----------|--------|-------------|
| CPO | AALI.JK | 0.85 |
| NEWCASTLE_COAL | ADRO.JK | 0.80 |
| GOLD | ANTM.JK | 0.60 |
| COPPER | INCO.JK | 0.40 |
| NICKEL | INCO.JK | (via NICK.L) |
| TIN | TINS.JK | (via TIN.L) |

### 3.3 granger_causality (28 records)

Dari `causal_relationships` dengan p<0.05. Granger causality test: source returns predict target returns.

Contoh signifikan:
- `NICK.L` → `INCO.JK` (lag=1, p<0.001)
- `GC=F` → `UNVR.JK` (lag=4, p=0.0002)
- `^GSPC` → `AALI.JK` (lag=1, p=0.004)

### 3.4 cross_market_coefficient (8 records)

Dari `cross_market_coefficients` dengan p<0.05. Granger causality global index → ^JKSE dengan regime-aware coefficients.

Contoh:
- `^GSPC` → `^JKSE` (lag=1, coef=0.29, regime=BEAR)
- `^N225` → `^JKSE` (lag=3, coef=-0.07, regime=BEAR)

### 3.5 macro_policy (480 records)

Pengaruh macro terhadap IDX equity:
- `BI_7DAY_REPO_RATE` → sektor rate-sensitive (Financials, Properties, Utilities, Consumer)
- `USD_IDR` → semua IDX equity (foreign flow)
- `VIX` → semua IDX equity (risk sentiment)

### 3.6 fx_flow & risk_sentiment (934+934 records)

- `USD_IDR` → semua 934 IDX equity (direction=negative, strength=0.6)
- `VIX` → semua 934 IDX equity (direction=negative, strength=0.5)

---

## 4. Python Module

**File:** `src/market/analysis/market_influence_kb.py`

**Class:** `MarketInfluenceKB`

### 4.1 Methods

| Method | Fungsi |
|--------|--------|
| `get_influences(ticker)` | Dapatkan semua influence untuk ticker |
| `get_targets(source_ticker)` | Dapatkan semua ticker yang dipengaruhi oleh source |
| `get_sector_influences(sector)` | Dapatkan influence untuk sektor |
| `compute_influence_signal(ticker, source_returns)` | Hitung sinyal agregat [-1, 1] |
| `get_source_layers(ticker)` | Distribusi layer sumber influence |
| `get_summary()` | Statistik KB per influence_type |
| `add_influence(...)` | Tambah/update influence record |
| `deactivate_influence(...)` | Nonaktifkan influence (soft delete) |

### 4.2 InfluenceSignal

```python
@dataclass
class InfluenceSignal:
    ticker: str
    net_signal: float        # [-1, 1] — positive=bullish, negative=bearish
    positive_strength: float  # total bullish strength
    negative_strength: float  # total bearish strength
    source_count: int         # jumlah sumber influence
    details: list[InfluenceRecord]
```

---

## 5. Contoh Penggunaan

### 5.1 Query: Apa yang mempengaruhi BBCA.JK?

```python
kb = MarketInfluenceKB(session)
influences = kb.get_influences("BBCA.JK")
# Output:
#   BI_7DAY_REPO_RATE  dir=negative  strength=0.700  via=macro_policy
#   USD_IDR            dir=negative  strength=0.600  via=fx_flow
#   VIX                dir=negative  strength=0.500  via=risk_sentiment
#   ^GSPC              dir=positive  strength=0.500  via=sector_global_link
#   ^TNX               dir=negative  strength=0.500  via=sector_global_link
```

### 5.2 Query: Apa yang dipengaruhi oleh CL=F?

```python
targets = kb.get_targets("CL=F")
# 100 tickers influenced by CL=F
# PTBA.JK (0.900), ITMG.JK (0.850), ADRO.JK (0.800), ...
```

### 5.3 Sinyal influence dengan return aktual

```python
source_returns = {
    '^GSPC': 0.015,   # S&P 500 +1.5%
    '^TNX': -0.02,    # 10Y yield -2%
    'CL=F': 0.03,     # Oil +3%
    'VIX': -0.05,     # VIX -5%
    'USD_IDR': -0.005 # IDR strengthening
}
sig = kb.compute_influence_signal("BBCA.JK", source_returns)
# net=+0.083 (bullish — S&P up + yield down + VIX down + IDR up)
```

---

## 6. Integrasi dengan Pipeline

### 6.1 SignalEnhancer

`MarketInfluenceKB` dapat diintegrasikan ke `SignalEnhancer` sebagai signal tambahan:
- Ambil influence list untuk ticker
- Fetch return terbaru untuk setiap source ticker
- Hitung `compute_influence_signal(ticker, source_returns)`
- Blend dengan weight ~5-8% ke composite signal

### 6.2 MarketContext

`MarketContextProvider` dapat menggunakan KB untuk:
- Mengisi field `cross_market_signal` dengan data dari KB
- Menentukan global driver mana yang paling relevan per ticker
- Mengganti hardcoded cross-market correlation dengan query KB dinamis

### 6.3 Recommendation Engine

`RecommendationEngine` dapat menggunakan KB untuk:
- Menjelaskan mengapa rekomendasi BUY/SELL diberikan
- "BBCA.JK direkomendasikan karena: ^GSPC +1.5% (bullish), ^TNX -2% (bullish), VIX -5% (bullish)"
- Menampilkan influence map di laporan

---

## 7. Limitasi dan Pengembangan

### 7.1 Limitasi Saat Ini

- **Strength teoretis**: sector_global_link menggunakan strength=0.5 (default), belum dikalibrasi dengan data empiris
- **Granger causality**: hanya 28 signifikan (p<0.05) dari 198 total — sample size terbatas
- **Regime-aware**: hanya cross_market_coefficients yang punya data per regime (BEAR/BULL)
- **Macro data**: BI Rate, USD/IDR, VIX diterapkan ke semua IDX equity — belum per-sektor kalibrasi

### 7.2 Pengembangan

- **Kalibrasi strength**: regresi rolling 60-day antara source return dan target return → coefficient = strength
- **DCC-GARCH integration**: gunakan `dcc_garch_results` untuk dynamic conditional correlation sebagai strength
- **Subsector override**: tambah mapping subsektor (banks, telecom, plantation, coal mining)
- **Event-driven influence**: tambah influence dari policy events (PolicyEventScorer)
- **Backtest validation**: validasi sinyal influence dengan backtest per ticker

---

## Cross-Reference

- `pustaka/35-multi-asset-cross-market-analysis.md` — framework intermarket analysis
- `pustaka/102-sector-global-link-engine.md` — mapping sektor → global driver
- `pustaka/99-matriks-relevansi-satelit-pasar-modal.md` — data satelit sebagai influence
- `src/market/analysis/market_influence_kb.py` — implementasi module
- `alembic/versions/0030_market_influence_kb.py` — migration
- `src/market/db/models.py` — ORM model `MarketInfluenceKB`
