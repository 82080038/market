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

## Engine yang Di-Test

### SignalEnhancer (8 sinyal)
| Engine | Weight | Deskripsi |
|--------|--------|-----------|
| volume | 15% | OFI proxy, VWAP deviation, OBV |
| event | 15% | PolicyEventScorer |
| meta | 20% | MetaLabeler bet sizing |
| smart_money | 12% | Bandarmology, retail absorption |
| cross_market | 12% | Global → IDX domino |
| sector | 10% | Sector rotation |
| pairs | 10% | Pairs trading cointegration |
| astronacci | 6% | Moon phases, retrogrades, Fibonacci time |

### MarketContext (7 faktor)
| Engine | Weight | Deskripsi |
|--------|--------|-----------|
| fundamental | 14% | PE, ROE, dividend yield, DER |
| macro | 11% | BI rate, CPI, GDP |
| ml | 14% | LightGBM ensemble |
| news | 7% | News sentiment |
| commodity | 7% | CPO, batubara, emas |
| global_sentiment | 11% | VIX, Fear & Greed |
| governance | 5% | ESG, board structure |

## Output

- **JSON report** di `data/ablation_reports/ablation_report_YYYYMMDD_HHMMSS.json`
- **Console summary** dengan tabel scorecard

## Verdict

| Verdict | Kriteria | Aksi |
|---------|----------|------|
| **KEEP** | p < 0.05 AND Δ Sharpe > 0.1 | Pertahankan/tingkatkan weight |
| **MARGINAL** | p < 0.10 OR (p < 0.05 AND Δ Sharpe > 0) | Monitor, pertimbangkan reduce |
| **REMOVE** | p ≥ 0.10 OR Δ Sharpe ≤ 0 | Reduce ke 0 atau hapus |

## Struktur File

```
src/market/ablation/
├── __init__.py
├── engine_registry.py       — Daftar 15 engine untuk di-test
├── isolated_backtest.py      — Framework isolasi + metrics + significance test
├── scorecard.py              — KEEP/MARGINAL/REMOVE verdict + composite score
└── ablation_report.py        — JSON report + console summary + recommendations

scripts/engine_ablation/
├── run_ablation.py           — CLI runner
└── README.md                 — Dokumentasi ini

tests/ablation/
├── test_engine_registry.py
├── test_isolated_backtest.py
└── test_scorecard.py
```

## Catatan

- Engine yang belum punya implementasi signal generator (placeholder) akan menghasilkan delta = 0 (sama dengan baseline). Ini wajar — perlu di-hook ke engine aktual untuk hasil bermakna.
- Astronacci sudah ter-hook ke `compute_astronacci_signal()` untuk pengujian nyata.
- Untuk engine lain, ganti fungsi `generate_engine_signals()` di `run_ablation.py` dengan call ke engine aktual.
