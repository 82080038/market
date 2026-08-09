# Rencana Lanjutan Production Pipeline

> **Tanggal:** 9 Agustus 2026
> **Status:** Step 1 (Remediation) selesai — 20 ticker, 14 jam eksekusi. Portfolio belum lolos gate KEEP.
> **Pipeline:** `run_production_pipeline.sh` — Step 1 ✓ (exit 1), Step 2 ✗ (abort), Step 3 ✗ (skip)

---

## 1. Hasil Pipeline Production (8 Agustus 2026)

### 1.1 Ringkasan Eksekusi

| Aspek | Detail |
|-------|--------|
| **Durasi total** | ~14 jam (01:19 WIB → 15:18 WIB, 8 Agu 2026) |
| **DB size** | 9.23 GB (`data/market_research.db`) |
| **Ticker diproses** | 20/20 (semua selesai) |
| **Metode** | Differential Evolution + walk-forward LightGBM per ticker |
| **OOM** | Tidak ada (RAM stabil 2.9%, CPU 99%) |
| **Output** | `best_ticker_quant_config.json` (26 KB), `portfolio_data_remediation_report.json` (31 KB) |

### 1.2 Portfolio Validation

| Metrik | Nilai | Target | Status |
|--------|-------|--------|--------|
| Score | 3.71/5.00 | ≥ 3.5 | ✓ lolos |
| Alpha | ~0.0 (3.2e-7) | > 0 | ✗ gagal |
| Sharpe | -10.0 | > 0 | ✗ gagal |
| Max DD | ~0.0% | > -10% | ✓ |
| Win Rate | 48.4% | > 50% | moderat |
| **Promoted KEEP** | **False** | True | ✗ |

### 1.3 Per-Ticker Results (ranked by Sharpe)

| # | Ticker | Sharpe | Alpha | Accept% | Baseline | κ | Cluster |
|---|--------|--------|-------|---------|----------|---|---------|
| 1 | UNTR.JK | +0.263 | +0.115 | 70.9% | donchian | 0.167 | cluster_2 |
| 2 | SONA.JK | +0.188 | +0.090 | 12.2% | donchian | 0.267 | cluster_1 |
| 3 | BCIC.JK | +0.093 | +0.068 | 52.8% | vwap | 0.208 | cluster_0 |
| 4 | APLI.JK | +0.075 | +0.087 | 40.4% | donchian | 0.102 | cluster_1 |
| 5 | BVIC.JK | +0.000 | +0.000 | 0.0% | donchian | 0.131 | cluster_0 |
| 6 | MTDL.JK | -0.008 | +0.056 | 3.7% | ema_env | 0.130 | cluster_0 |
| 7 | UNIC.JK | -0.053 | +0.045 | 14.7% | donchian | 0.300 | cluster_1 |
| 8 | TRIM.JK | -0.054 | +0.044 | 29.0% | donchian | 0.137 | cluster_0 |
| 9 | PANS.JK | -0.087 | +0.009 | 73.8% | donchian | 0.209 | cluster_0 |
| 10 | SPMA.JK | -0.123 | +0.028 | 11.8% | donchian | 0.134 | cluster_1 |
| 11 | TIRT.JK | -0.148 | +0.012 | 23.3% | donchian | 0.140 | cluster_1 |
| 12 | KDSI.JK | -0.165 | +0.015 | 29.5% | donchian | 0.176 | cluster_1 |
| 13 | ICBP.JK | -0.265 | -0.010 | 32.6% | donchian | 0.160 | cluster_2 |
| 14 | MEDC.JK | -0.266 | -0.034 | 56.8% | donchian | 0.132 | cluster_2 |
| 15 | INDF.JK | -0.282 | -0.018 | 42.9% | donchian | 0.170 | cluster_2 |
| 16 | TCID.JK | -0.290 | +0.007 | 23.4% | ema_env | 0.300 | cluster_1 |
| 17 | RBMS.JK | -0.311 | -0.058 | 36.1% | donchian | 0.128 | cluster_0 |
| 18 | KPIG.JK | -0.329 | -0.010 | 25.9% | donchian | 0.137 | cluster_1 |
| 19 | ASBI.JK | -0.410 | -0.025 | 16.0% | donchian | 0.206 | cluster_0 |
| 20 | BNBR.JK | -0.654 | -0.218 | 4.0% | donchian | 0.142 | cluster_2 |

### 1.4 Root Cause Analysis

**Masalah utama: Portfolio weighting collapse**

Inverse-variance weighting memberikan 100% bobot ke BVIC.JK (weight=1.0, semua ticker lain weight=0.0). BVIC.JK memiliki:
- Sharpe = 0.000 (tidak ada return)
- AcceptRate = 0.0% (tidak pernah menghasilkan sinyal trading)
- Zero variance → inverse-variance memberikan bobot maksimum

Akibatnya:
- Portfolio Sharpe = -10.0 (extreme negative — kemungkinan bug edge case)
- Portfolio Alpha ≈ 0.0 (tidak ada excess return)
- Promoted KEEP = False (meskipun Score 3.71 ≥ 3.5, Alpha tidak > 0)

**Masalah sekunder: Mayoritas ticker Sharpe negatif**

15 dari 20 ticker memiliki Sharpe negatif. Hanya 4 ticker dengan Alpha positif yang signifikan:
- UNTR.JK (+0.115), SONA.JK (+0.090), APLI.JK (+0.087), BCIC.JK (+0.068)

Ini menunjukkan model belum menemukan edge yang konsisten pada real DB (vs mock DB yang menghasilkan Score 4.19).

---

## 2. Rencana Aksi (Prioritas)

### 2.1 Immediate — Jalankan Daily Signal Cron (Hari Ini)

Config `best_ticker_quant_config.json` sudah ter-generate dan valid (20 ticker, best_params per ticker). Meskipun portfolio belum lolos KEEP, individual ticker params tetap dapat digunakan untuk monitoring.

```bash
DB_PATH=data/market_research.db .venv/bin/python3 scripts/daily_signal_cron.py
```

**Output:** Sinyal BUY/SELL/HOLD + position sizing untuk 20 ticker, insert ke `app_notifications` table.

### 2.2 Short-term — Fix Inverse-Variance Weighting (1-2 hari)

**Bug:** Ticker dengan AcceptRate=0% (BVIC.JK) mendapat weight=1.0 karena zero variance.

**Fix yang diperlukan di `portfolio_data_remediation.py`:**

1. **Filter pre-weighting:** Exclude ticker dengan AcceptRate < 5% dari inverse-variance pool
2. **Floor variance:** Tambah epsilon ke variance (smoothing) untuk menghindari divisi oleh nol
3. **Cap weight:** Batasi max weight per ticker (mis. 20%) untuk mencegah konsentrasi
4. **Fallback:** Jika hanya 1 ticker yang lolos filter, gunakan equal-weight untuk semua ticker dengan Alpha > 0

**File yang perlu diubah:**
- `scripts/portfolio_data_remediation.py` — fungsi `_compute_portfolio_weights()` atau equivalent
- `scripts/portfolio_final_execution.py` — fungsi `compute_daily_inverse_variance_weights()`

### 2.3 Medium-term — Re-run Pipeline dengan Fix (3-5 jam)

Setelah fix weighting, re-run pipeline:

```bash
bash scripts/run_production_pipeline.sh --n-calls 20
```

**Ekspektasi:**
- Portfolio weighting terdistribusi ke ticker dengan Alpha positif (UNTR, SONA, BCIC, APLI)
- Portfolio Alpha > 0 → Promoted KEEP = True
- Step 3 (final execution) berjalan → `final_portfolio_verdict.json` ter-generate

### 2.4 Medium-term — Jalankan Step 3 Manual (Opsional, 30-60 menit)

Jika tidak ingin menunggu re-run full pipeline, Step 3 bisa dijalankan manual dengan config yang ada:

```bash
.venv/bin/python3 scripts/portfolio_final_execution.py \
    --config best_ticker_quant_config.json \
    --oos-start 2024-01-01 \
    --oos-end 2026-08-31 \
    --db data/market_research.db
```

**Catatan:** Tanpa fix weighting, verdict mungkin tetap MARGINAL/REMOVE.

### 2.5 Long-term — Evaluasi Model Quality

**Masalah fundamental:** 15/20 ticker Sharpe negatif pada real DB.

**Investigasi yang diperlukan:**

1. **Bandingkan real vs mock DB:**
   - Mock DB: Score 4.19, p-value 0.0166, Max DD -3.98%
   - Real DB: Score 3.71, Alpha ≈ 0, Sharpe -10.0
   - Perbedaan ukuran: Mock ~46 MB vs Real 9.23 GB (200x lebih data)

2. **Cek data quality real DB:**
   - Apakah technical_indicators lengkap untuk semua ticker?
   - Apakah ada gap OHLCV yang menyebabkan walk-forward bias?
   - Apakah ada look-ahead bias yang tidak terdeteksi?

3. **Eksperimen tambahan:**
   - Tingkatkan `n_calls` DE dari 20 ke 50-100 untuk konvergensi lebih baik
   - Tambah baseline candidates (mis. mean-reversion, momentum)
   - Gunakan GPU (cuda:1) untuk LightGBM training acceleration
   - Evaluasi multi-factor model (MultiFactorFeaturePipeline) sebagai sinyal tambahan

4. **Diversifikasi ticker pool:**
   - 20 ticker fokus mungkin tidak cukup untuk portfolio diversification
   - Pertimbangkan 50-100 ticker dari hasil screener
   - Sektoral balancing (energy, financial, consumer, basic materials)

---

## 3. File yang Perlu Di-Update

### 3.1 Kode Fix (Prioritas High)

| File | Perubahan | Status |
|------|-----------|--------|
| `scripts/portfolio_data_remediation.py` | Fix IV weighting: filter AcceptRate<5%, cap weight, floor variance | Pending |
| `scripts/portfolio_final_execution.py` | Sama: fix `compute_daily_inverse_variance_weights()` | Pending |
| `scripts/daily_signal_cron.py` | Sudah ada IV fix (blend 50% verdict + 50% daily) — verify | OK |

### 3.2 Dokumentasi (Prioritas Medium)

| File | Perubahan | Status |
|------|-----------|--------|
| `MEGAPLAN.md` | Tambah section "Fase 6: Production Pipeline" dengan hasil real DB | Pending |
| `.devin/SESSION_MEMORY.md` | Update checkpoint dengan hasil production pipeline | Pending |
| `PROGRESS-OPTIMASI-RECOMPUTE.md` | Tambah section production pipeline results | Pending |
| `pustaka/96-ai-ml-audit-framework.md` | Update dengan hasil real DB audit | Pending |
| `docs/AUDIT-FINDINGS.md` | Tambah section production pipeline audit | Pending |

### 3.3 Config & Output (Prioritas Low — auto-generated)

| File | Status |
|------|--------|
| `best_ticker_quant_config.json` | ✓ Generated (26 KB, 20 tickers) |
| `portfolio_data_remediation_report.json` | ✓ Generated (31 KB) |
| `final_portfolio_verdict.json` | ✗ Belum ada (Step 3 tidak jalan) |

---

## 4. Timeline Estimasi

| Tahap | Durasi | Output |
|-------|--------|--------|
| Daily signal cron (immediate) | 30 detik | `app_notifications` populated |
| Fix IV weighting | 1-2 hari | Code fix + test |
| Re-run pipeline | 3-5 jam | Config + verdict baru |
| Step 3 manual (opsional) | 30-60 menit | `final_portfolio_verdict.json` |
| Evaluasi model quality | 1-2 minggu | Research report + improvement plan |

---

## 5. Crontab (Tetap Aktif)

Daily signal cron sudah dikonfigurasi untuk berjalan otomatis:

```bash
# 16:15 WIB (09:15 UTC) setiap hari bursa Senin-Jumat
15 9 * * 1-5 DB_PATH=/home/petrick/projects/market/data/market_research.db \
    PORTFOLIO_CAPITAL=100000000 \
    /home/petrick/projects/market/.venv/bin/python3 \
    /home/petrick/projects/market/scripts/daily_signal_cron.py \
    >> /home/petrick/projects/market/logs/daily_signal.log 2>&1
```

**Catatan:** Crontab belum di-install. Install dengan:
```bash
crontab -e
# Paste baris di atas, save
```

---

## 6. Lesson Learned

1. **Mock DB → Real DB bukan linear scaling:** Hasil mock (Score 4.19) tidak replikasi pada real DB (Score 3.71). Volume data 200x lebih besar, noise lebih tinggi, edge lebih sulit ditemukan.
2. **Inverse-variance weighting fragile:** Ticker dengan zero variance (AcceptRate=0%) meng-collapse seluruh portfolio. Perlu robust filtering.
3. **DE optimization pada real DB memakan ~45 menit/ticker:** 20 ticker × 45 menit = 15 jam. Untuk 100 ticker, butuh ~75 jam — perlu GPU acceleration atau parallel processing.
4. **OOM guard bekerja:** DB 9.23 GB dengan RAM 2.9% — tidak ada OOM. `oom_score_adj = -500` efektif.
5. **Bash `set -euo pipefail` bekerja:** Exit code 1 dari Step 1 menghentikan pipeline dengan benar — tidak melanjutkan ke Step 2/3 dengan config yang tidak valid.
