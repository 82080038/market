# Ablation Follow-Up Plan: Rencana Tindak Lanjut

> Dokumen ini berisi rencana tindak lanjut untuk pengembangan ablation framework
> setelah implementasi 29 engine dan hasil ablation pertama (13 Agustus 2026).

## Status Saat Ini

| Item | Status |
|------|--------|
| Engine terdaftar | 29 (22 SignalEnhancer + 7 MarketContext) |
| Engine ter-hook ke signal generator | 29/29 (semua) |
| Pre-flight data checker | ✅ Implemented |
| Bonferroni correction | ✅ Implemented |
| Walk-forward validation | ❌ Not implemented |
| Deflated Sharpe Ratio | ❌ Not implemented |
| Tests | 30/30 passed |
| Hasil ablation terakhir | 29 engine, semua REMOVE (Bonferroni α=0.001724) |

## Prioritas Tindak Lanjut

### Phase 1: Fix Data Issues (HIGH, immediate)

#### 1.1 Fix overnight_idx data alignment
**Masalah:** Engine menghasilkan ΔSharpe identik dengan pairs/fundamental/macro (-0.0609), mengindikasikan tidak ada signal yang di-generate.

**Root cause hipotesis:** Global ticker OHLCV index (date-based) tidak ter-align dengan ticker OHLCV index. `_load_global_ohlcv` mengembalikan dict dengan DatetimeIndex per ticker, tapi `idx in ret_series.index` lookup mungkin gagal karena timezone mismatch atau date format difference.

**Aksi:**
- Debug: print index type dan timezone untuk ticker OHLCV vs global OHLCV
- Fix: normalize semua index ke date-only (timezone-naive) sebelum lookup
- Test: verify overnight_idx menghasilkan non-zero signals

**File:** `scripts/engine_ablation/run_ablation.py` — `overnight_idx` block

#### 1.2 Fix pairs/fundamental/macro identical results
**Masalah:** 4 engine (pairs, fundamental, macro, overnight_idx) menghasilkan ΔSharpe yang identik (-0.0609), mengindikasikan semua menghasilkan signal = 0 (baseline-only).

**Aksi:**
- Verifikasi: cek apakah signal series semuanya nol
- Untuk pairs: cek apakah cointegration test pass untuk test tickers
- Untuk fundamental: cek apakah fundamental_data tersedia untuk periode test
- Untuk macro: cek apakah macro_data tersedia untuk periode test

**File:** `scripts/engine_ablation/run_ablation.py` — masing-masing engine block

### Phase 2: Refine sector_global_link (HIGH, next)

#### 2.1 Threshold dinamis per sektor
**Masalah:** Fixed threshold 0.5% menyebabkan over-trading untuk sektor low-volatility (Financial Services) dan under-trading untuk sektor high-volatility (Basic Materials).

**Aksi:**
- Ganti fixed threshold dengan ATR-based threshold: `threshold = ATR_20 * multiplier`
- Multiplier = 1.0 (default), bisa di-tune per sektor
- Implementasi di `sector_global_link` block di `run_ablation.py`

#### 2.2 Rolling correlation direction
**Masalah:** Static direction assumption (oil up = energy up) tidak selalu valid. Correlation antara global driver dan IDX sector bisa berubah regime.

**Aksi:**
- Ganti static direction dengan rolling 60d correlation sign
- `direction = sign(rolling_corr_60d(ticker_ret, global_ret))`
- Jika |rolling_corr| < 0.2 → signal = 0 (weak relationship, don't trade)
- Implementasi di `sector_global_link` block

#### 2.3 Weighted multi-driver
**Masalah:** Multi-driver consensus menggunakan equal weight, padahal driver 1 biasanya lebih dominan.

**Aksi:**
- Driver 1 weight = 0.7, Driver 2 weight = 0.3
- Consensus = weighted sum, bukan simple consensus
- Implementasi di `sector_global_link` block

### Phase 3: Expand Testing Scope (MEDIUM, next)

#### 3.1 Walk-forward validation
**Masalah:** Ablation saat ini menggunakan full-period backtest, bukan walk-forward. Tidak menangkap regime change.

**Aksi:**
- Tambah `--walk-forward` flag di CLI
- Rolling window: 252d train, 63d test, step 63d
- Hitung ablation per window, agregasi dengan mean + std
- File: `scripts/engine_ablation/run_ablation.py` + `src/market/ablation/isolated_backtest.py`

#### 3.2 Expand ticker universe
**Masalah:** Hanya 8 ticker di-test, tidak representatif untuk semua sektor IDX.

**Aksi:**
- Tambah ticker per sektor: Energy (ADRO, PTBA), Basic Materials (INCO, TINS), Consumer (ICBP, INDF), Tech (EMTK), Healthcare (KLBF), Property (CTRA), Utilities (PWON)
- Total target: 16-24 tickers (2-3 per sektor)
- Update `DEFAULT_TICKERS` di `run_ablation.py`

#### 3.3 Longer test period
**Masalah:** Periode test 2024-01-01 to 2026-08-12 hanya ~2.5 tahun, tidak mencakup berbagai regime (bull, bear, sideways, crisis).

**Aksi:**
- Extend start ke 2022-01-01 (4.5 tahun, mencakup post-COVID recovery + 2022 bear + 2023-2024 bull)
- Pastikan data global ticker tersedia untuk periode extended

### Phase 4: Advanced Metrics (MEDIUM, future)

#### 4.1 Deflated Sharpe Ratio (DSR)
**Masalah:** Bonferroni correction terlalu konservatif. DSR (Bailey & López de Prado 2014) lebih tepat untuk multiple strategy testing.

**Aksi:**
- Implementasi DSR di `scorecard.py`
- DSR = Prob(SR > SR_observed | n_trials, n_obs, skew, kurtosis)
- Tambah DSR ke report JSON dan console summary
- File: `src/market/ablation/scorecard.py` + `src/market/ablation/ablation_report.py`

#### 4.2 Data quality checks
**Masalah:** Data checker hanya cek existence, tidak cek quality (stale data, outlier, missing bars).

**Aksi:**
- Tambah quality checks di `data_checker.py`:
  - Stale data: last update > 7 days ago
  - Outlier: returns > 5σ dari mean
  - Missing bars: gap > 5 trading days
  - Zero volume: > 10% bars dengan volume = 0
- Status: PASS (good quality), WARN (minor issues), SKIP (serious issues)
- File: `src/market/ablation/data_checker.py`

### Phase 5: Apply to Production (LOW, future, butuh user approval)

#### 5.1 Weight adjustment berdasarkan ablation
**Masalah:** Engine weights saat ini berdasarkan assumption, bukan empiris.

**Aksi:**
- Engine dengan positive ΔSharpe + ΔAlpha: pertahankan atau tingkatkan weight
- Engine dengan negative ΔSharpe: reduce weight ke 0
- Engine dengan no signal: fix data issue sebelum decide
- Apply ke `SignalEnhancer.__init__()` weights
- **BUTUH USER APPROVAL sebelum apply**

#### 5.2 Engine selection
**Masalah:** 29 engine terlalu banyak — beberapa mungkin redundant atau counterproductive.

**Aksi:**
- Berdasarkan ablation results, pilih top 10-15 engine untuk production
- Pertimbangkan: engine diversity (jangan pilih semua dari kategori yang sama)
- Engine dengan positive ΔAlpha: reversal, mean_reversion, governance, dcc_garch
- **BUTUH USER APPROVAL sebelum apply**

## Timeline

| Phase | Estimasi | Dependensi |
|-------|----------|-----------|
| Phase 1 (Fix data issues) | 1-2 hari | Tidak ada |
| Phase 2 (Refine sector_global_link) | 2-3 hari | Phase 1 selesai |
| Phase 3 (Expand testing) | 3-5 hari | Phase 2 selesai |
| Phase 4 (Advanced metrics) | 3-5 hari | Phase 3 selesai |
| Phase 5 (Apply to production) | 1-2 hari | Phase 4 selesai + user approval |

## Referensi

- `pustaka/96-ai-ml-audit-framework.md` — Pilar 2 Ablation Study
- `pustaka/101-global-idx-advanced-models.md` — 4 advanced global-IDX models
- `pustaka/102-sector-global-link-engine.md` — Sector-global link engine
- `docs/ablation-deep-analysis.md` — Deep analysis ablation best practices
- `scripts/engine_ablation/README.md` — Engine ablation runner documentation
- Bailey, H. & López de Prado, M. (2014). "The Deflated Sharpe Ratio." SSRN 2460551.
