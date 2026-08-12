# Engine Ablation Study

Framework untuk menguji setiap signal engine secara terisolasi dan menentukan engine mana yang memberikan alpha signifikan.

## Cara Pakai

```bash
# Test semua engine pada ticker default
python scripts/engine_ablation/run_ablation.py

# Test engine spesifik
python scripts/engine_ablation/run_ablation.py --engines astronacci,volume,meta

# Custom tickers dan periode
python scripts/engine_ablation/run_ablation.py \
  --tickers BBCA.JK,BBRI.JK,UNVR.JK \
  --start 2023-01-01 --end 2026-08-12

# Dry run (lihat config tanpa eksekusi)
python scripts/engine_ablation/run_ablation.py --dry-run
```

## Engine yang Di-Test (29 engine)

### Original SignalEnhancer (8 engine)
| Engine | Weight | Deskripsi |
|--------|--------|----------|
| volume | 15% | OFI proxy, VWAP deviation, OBV divergence |
| event | 15% | PolicyEventScorer |
| meta | 20% | MetaLabeler bet sizing |
| smart_money | 12% | Bandarmology, retail absorption |
| cross_market | 12% | Global → IDX domino |
| sector | 10% | Sector rotation (rolling momentum + RS) |
| pairs | 10% | Pairs trading cointegration |
| astronacci | 6% | Moon phases, retrogrades, Fibonacci time |

### Original MarketContext (7 engine)
| Engine | Weight | Deskripsi |
|--------|--------|----------|
| fundamental | 14% | PE, ROE, dividend yield, DER |
| macro | 11% | BI rate, CPI, GDP |
| ml | 14% | LightGBM ensemble |
| news | 7% | News sentiment |
| commodity | 7% | CPO, batubara, emas |
| global_sentiment | 11% | VIX, Fear & Greed |
| governance | 5% | ESG, board structure |

### Alpha Signal Engines (4 engine, pustaka/97)
| Engine | Deskripsi |
|--------|-----------|
| mean_reversion | Bollinger Bands + RSI confirmation |
| reversal | Behavioral overreaction reversal (10d lookback) |
| ewma_momentum | EWMA crossover 20/50 dengan trend threshold |
| regime_switch | Adaptive momentum/mean-reversion (vol regime) |

### V2 Alternative Engines (5 engine)
| Engine | Deskripsi |
|--------|-----------|
| commodity_v2 | Regime filter (vol short vs long) |
| sector_v2 | RS z-score mean-reversion |
| volume_v2 | MFI (Money Flow Index) |
| event_v2 | Earnings momentum |
| ml_v2 | LightGBM walk-forward |

### Advanced Global-IDX Models (4 engine, pustaka/101)
| Engine | Deskripsi |
|--------|-----------|
| dcc_garch | DCC-GARCH dynamic conditional correlation (Engle 2002) |
| spillover_dy | Diebold-Yilmaz spillover index (VAR + FEVD) |
| foreign_flow | Foreign flow prediction (BI-Fed rate, VIX, USD/IDR) |
| overnight_idx | Overnight global → IDX opening (US T-1 + Asian T-0) |

### Sector-Global Link Engine (1 engine, pustaka/102)
| Engine | Deskripsi |
|--------|-----------|
| sector_global_link | Sector-specific global driver dengan timezone-aware lag |

## Output

- **JSON report** di `output/ablation/ablation_report_YYYYMMDD_HHMMSS.json`
- **Console summary** dengan tabel scorecard + Bonferroni correction

## Verdict

| Verdict | Kriteria | Aksi |
|---------|----------|------|
| **KEEP** | p < α_bonferroni AND Δ Sharpe > 0.1 | Pertahankan/tingkatkan weight |
| **MARGINAL** | p < α_bonferroni/2 OR (p < α_bonferroni AND Δ Sharpe > 0) | Monitor, pertimbangkan reduce |
| **REMOVE** | p ≥ α_bonferroni/2 OR Δ Sharpe ≤ 0 | Reduce ke 0 atau hapus |

**Bonferroni correction:** α_bonferroni = 0.05 / n_engines (29 engine → α = 0.001724)

## Struktur File

```
src/market/ablation/
├── __init__.py
├── engine_registry.py       — Daftar 29 engine untuk di-test
├── isolated_backtest.py      — Framework isolasi + metrics + significance test
├── scorecard.py              — KEEP/MARGINAL/REMOVE verdict + Bonferroni correction
├── ablation_report.py        — JSON report + console summary + recommendations
└── data_checker.py           — Pre-flight data validation per engine

scripts/engine_ablation/
├── run_ablation.py           — CLI runner dengan pre-flight check + isolated backtest
├── render_missing_data.py    — Visualisasi data gaps
└── README.md                 — Dokumentasi ini

tests/ablation/
├── test_engine_registry.py   — 8 tests (registry, categories, weights, duplicates)
├── test_isolated_backtest.py — 11 tests (simulate_returns, compute_metrics, backtester)
└── test_scorecard.py         — 11 tests (KEEP/MARGINAL/REMOVE, composite score, reasons)
```

## Hasil Ablation Terbaru

**Period:** 2024-01-01 to 2026-08-12 | **Tickers:** BBCA.JK, BBRI.JK, UNVR.JK, ANTM.JK, MDKA.JK, UNTR.JK, TLKM.JK, ASII.JK  
**Engines tested:** 29 | **Bonferroni α:** 0.001724

### Top 5 performers (by ΔSharpe):
1. **reversal**: ΔSharpe=+0.2146, ΔAlpha=+0.0674
2. **mean_reversion**: ΔSharpe=+0.1835, ΔAlpha=+0.0058
3. **governance**: ΔSharpe=+0.0935, ΔAlpha=+0.1062
4. **astronacci**: ΔSharpe=+0.0788, ΔAlpha=+0.0226
5. **dcc_garch**: ΔSharpe=+0.0517, ΔAlpha=+0.0853

### Catatan

- Semua 29 engine menghasilkan real signals (non-zero delta) kecuali: pairs, fundamental, macro, overnight_idx (kemungkinan data alignment issue)
- Semua verdict REMOVE setelah Bonferroni correction — ini expected karena 29 engine dengan α=0.001724 sangat konservatif
- Engine dengan positive ΔSharpe dan ΔAlpha (reversal, mean_reversion, governance, dcc_garch) adalah kandidat untuk di-preserve saat di-apply ke production
- Hasil ablation = rekomendasi saja, apply ke aplikasi butuh user approval
