# Data Governance & Data Lineage

> **Dokumen 53** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Data catalog, data lineage, data quality SLA, data retention policy, data stewardship, PII handling untuk sistem trading.
>
> **Konteks:** Dokumen 22 bahas data engineering pipeline. Dokumen 47 punya T-004 (validation) dan T-009 (quality report). Tapi belum ada comprehensive data governance: apa data yang ada, dari mana, ke mana, berapa lama disimpan, siapa yang bertanggung jawab.

---

## Daftar Isi

1. [Data Governance Framework](#1-data-governance-framework)
2. [Data Catalog](#2-data-catalog)
3. [Data Lineage](#3-data-lineage)
4. [Data Quality SLA](#4-data-quality-sla)
5. [Data Retention Policy](#5-data-retention-policy)
6. [Data Stewardship](#6-data-stewardship)
7. [PII & Sensitive Data Handling](#7-pii--sensitive-data-handling)
8. [Data Governance Metrics](#8-data-governance-metrics)

---

## 1. Data Governance Framework

### 1.1 Kenapa Data Governance

| Tanpa Governance | Dengan Governance |
|-----------------|-------------------|
| Tidak tahu data apa yang ada | Data catalog: 39 tables, documented |
| Tidak tahu dari mana data berasal | Lineage: Yahoo → normalize → validate → SQLite |
| Tidak tahu berapa lama simpan | Retention policy: OHLCV forever, audit_log 1 year |
| Tidak tahu siapa owner data | Stewardship: setiap table punya owner |
| Data quality tidak terukur | Quality SLA: completeness > 95%, accuracy > 90% |

### 1.2 Governance Principles

1. **Data is asset** — setiap table punya value dan cost
2. **Data has owner** — setiap table punya steward yang bertanggung jawab
3. **Data has lineage** — dari source ke consumption, dapat ditelusuri
4. **Data has lifecycle** — created, used, archived, deleted
5. **Data quality is measurable** — SLA per table, monitored

---

## 2. Data Catalog

### 2.1 Catalog Schema

Setiap table/database di sistem harus terdaftar di catalog:

| Table | Source | Owner | Format | Update Freq | Rows | Size | Quality SLA | Retention | PII? |
|-------|--------|-------|--------|-------------|------|------|-------------|-----------|------|
| `ohlcv` | Yahoo Finance | Data Engine | SQLite | Daily 16:30 | 2.9M | ~200MB | > 95% complete | Forever | No |
| `foreign_flow` | idx.co.id | Data Engine | SQLite | Daily 17:00 | 103K | ~10MB | > 90% complete | 5 years | No |
| `broker_flow` | idx.co.id | Data Engine | SQLite | Daily 17:00 | 15.8K | ~2MB | > 80% complete | 3 years | No |
| `macro_data` | BPS/BI/FRED | Data Engine | SQLite | Weekly | 10K | ~1MB | > 95% complete | Forever | No |
| `scores` | Internal (pipeline) | Analysis Engine | SQLite | Daily 18:00 | 9.8K | ~3MB | > 95% complete | 2 years | No |
| `technical_indicators` | Internal (T-010) | Analysis Engine | SQLite | Daily 18:00 | 11.1K | ~5MB | > 95% complete | 2 years | No |
| `relationship_matrix` | Internal (T-014) | Analysis Engine | SQLite | Daily 18:10 | 12K | ~8MB | > 90% complete | 1 year | No |
| `corporate_actions` | yfinance | Data Engine | SQLite | Weekly | 6.4K | ~1MB | > 95% complete | Forever | No |
| `dividends` | yfinance | Data Engine | SQLite | Weekly | 6K | ~0.5MB | > 95% complete | Forever | No |
| `audit_log` | Internal (all) | Data Engine | SQLite | Real-time | 3.1K | ~2MB | 100% append | 1 year | No |
| `pattern_analysis` | Internal (T-017) | Analysis Engine | SQLite | Daily 18:15 | 2.4K | ~1MB | > 90% complete | 2 years | No |
| `instrument_master` | yfinance + manual | Data Engine | SQLite | On change | 992 | ~0.5MB | > 99% complete | Forever | No |
| `fundamental_data` | yfinance | Data Engine | SQLite | Quarterly | 991 | ~2MB | > 90% complete | 5 years | No |
| `stock_personality` | Internal | Analysis Engine | SQLite | Monthly | 944 | ~1MB | > 90% complete | 2 years | No |
| `fear_greed` | Internal (T-015) | Analysis Engine | SQLite | Daily | 466 | ~0.1MB | > 95% complete | 5 years | No |
| `market_calendar` | IDX | Data Engine | SQLite | Yearly | 365 | ~0.05MB | 100% complete | Forever | No |
| `watchlist` | User input | Frontend | SQLite | On change | 359 | ~0.1MB | N/A | Forever | No |
| `esg_scores` | External | Data Engine | SQLite | Quarterly | 164 | ~0.1MB | > 80% complete | 3 years | No |
| `external_events` | Manual | User | SQLite | On input | 119 | ~0.1MB | N/A | 5 years | No |
| `news` | Scraping | Sentiment Engine | SQLite | Daily | 110 | ~0.5MB | > 80% relevant | 1 year | No |
| `policy_events` | Manual/Scrape | Data Engine | SQLite | On event | 179 | ~0.1MB | N/A | 5 years | No |
| `prediction_log` | Internal (T-022) | AI Learning | SQLite | Daily | — | — | > 95% complete | 2 years | No |
| `paper_trades` | Internal (T-040) | Execution Engine | SQLite | On trade | — | — | 100% accurate | 5 years | No |
| `orders` | Internal (T-041) | Execution Engine | SQLite | On trade | — | — | 100% accurate | 7 years | No |
| `tca_log` | Internal (TCA) | Execution Engine | SQLite | On fill | — | — | 100% accurate | 3 years | No |
| `model_registry` | Internal (T-025) | AI Learning | SQLite | On retrain | — | — | 100% accurate | Forever | No |
| `ai_weights` | Internal (T-024) | AI Learning | SQLite | Weekly | — | — | 100% accurate | 2 years | No |
| `portfolio_candidates` | Internal (T-033) | Portfolio Engine | SQLite | Daily | — | — | > 90% complete | 1 year | No |

### 2.2 External Data Sources

| Source | Data Provided | Access Method | Rate Limit | Reliability | Fallback |
|--------|--------------|---------------|------------|-------------|----------|
| **Yahoo Finance** | OHLCV, fundamentals, actions | yfinance API | 1 req/sec | Medium (rate limited) | Google Finance scrape |
| **idx.co.id** | Foreign flow, broker flow, calendar | cloudscraper | 0.3 req/sec | Low (anti-scrape) | Manual input |
| **BPS** | Inflasi, GDP | Web scrape | 1 req/sec | High | Last known value |
| **BI** | BI rate, monetary policy | Web scrape | 1 req/sec | High | Last known value |
| **FRED** | Global macro | API | 120 req/min | High | Last known value |
| **Telegram** | Alert delivery | Bot API | 30 msg/sec | High | Email |
| **Reddit/X** | Social sentiment | API/Scrape | Variable | Low | Skip source |

---

## 3. Data Lineage

### 3.1 Lineage Graph

```
External Sources          Ingestion              Storage              Processing           Output
─────────────────     ──────────────        ──────────────       ──────────────      ──────────────
                       │                    │                    │                    │
Yahoo Finance ──────▶ T-001 EOD Fetch ───▶ ohlcv ──────────▶ T-010 Technical ───▶ scores (technical)
                       │                    │                    │                    │
                       │                    │              ┌───▶ T-011 Fundamental ▶ scores (fundamental)
                       │                    │              │   T-012 Macro ──────▶ scores (macro)
                       │                    │              ├─── T-013 Global ────▶ scores (global)
                       │                    │              │   T-014 Relationship▶ scores (relationship)
                       │                    │              ├─── T-015 Sentiment ─▶ scores (sentiment)
                       │                    │              │   T-016 Regime ────▶ ai_weights
                       │                    │              └─── T-019 Pipeline ──▶ scores (composite)
                       │                    │                                        │
idx.co.id ─────────▶ T-002 Foreign Flow ▶ foreign_flow ─────▶ T-015 Sentiment ──▶ scores (sentiment)
                       │                    │
                       │               T-003 Broker Flow ▶ broker_flow ────▶ T-015 Sentiment
                       │                    │
BPS/BI/FRED ───────▶ T-005 Macro Fetch ─▶ macro_data ──────▶ T-012 Macro ─────▶ scores (macro)
                       │                    │              T-016 Regime ────▶ ai_weights
                       │                    │
yfinance (global) ─▶ T-006 Global Fetch ▶ ohlcv (global) ─▶ T-013 Global ───▶ scores (global)
                       │                    │
yfinance (actions)▶ T-007 Corp Actions ▶ corporate_actions  T-010 Technical (adjusted)
                                          dividends
                       │                    │
Internal ─────────▶ T-004 Validation ──▶ quality_score ───▶ T-009 Quality Report
                       │                    │
All tasks ────────▶ T-046 Audit Log ───▶ audit_log
                       │                    │
T-022 Prediction ──────────────────────▶ prediction_log ─▶ T-023 Self-Correction
                       │                    │
T-025 Retrain ────────────────────────▶ model_registry
                       │                    │
T-033 Portfolio ──────────────────────▶ portfolio_candidates
```

### 3.2 Lineage per Table

```yaml
table: ohlcv
lineage:
  sources:
    - Yahoo Finance API (primary)
    - Google Finance scrape (fallback)
  ingestion:
    - T-001: yfinance.batch_fetch() → normalize_ohlcv() → validation
  storage:
    - SQLite: ohlcv table (INSERT OR REPLACE)
    - Parquet: raw/ (archive)
  consumers:
    - T-010: Technical Analysis
    - T-011: Fundamental Analysis (market cap)
    - T-014: Relationship Analysis
    - T-017: Pattern Detection
    - T-020: LSTM Prediction
    - T-031: Risk Assessment (VaR computation)
    - Backtest Engine
  transformations:
    - normalize_ohlcv(): raw → standard schema
    - validate_ohlcv(): quality score
    - adjust_for_splits(): when corporate action detected
```

### 3.3 Lineage Query

```sql
-- "Data OHLCV untuk BBCA.JK tanggal 2026-08-05 berasal dari mana?"
SELECT
    ticker, date, source, ingested_at, quality_score
FROM ohlcv
WHERE ticker = 'BBCA.JK' AND date = '2026-08-05';

-- "Scores untuk BBCA.JK tanggal 2026-08-05 dihasilkan oleh task mana?"
SELECT
    engine, score, computed_at, pipeline_run_id
FROM scores
WHERE ticker = 'BBCA.JK' AND date = '2026-08-05'
ORDER BY computed_at;

-- "Prediction untuk BBCA.JK menggunakan model versi apa?"
SELECT
    p.prediction_id, p.ticker, p.direction, p.confidence,
    m.version, m.oos_r2, m.trained_at
FROM prediction_log p
JOIN model_registry m ON p.model_id = m.id
WHERE p.ticker = 'BBCA.JK'
ORDER BY p.created_at DESC LIMIT 5;
```

---

## 4. Data Quality SLA

### 4.1 Quality Dimensions

| Dimension | Definisi | Measurement | Target |
|-----------|----------|-------------|--------|
| **Completeness** | % data yang ada (tidak missing) | rows_expected / rows_actual | > 95% |
| **Accuracy** | % data yang benar (match reality) | manual spot check | > 90% |
| **Timeliness** | Data up-to-date sesuai schedule | latest_date vs today | < 1 day lag |
| **Consistency** | Data konsisten antar tables | cross-table validation | 100% |
| **Validity** | Data dalam range/format yang valid | schema validation | 100% |
| **Uniqueness** | Tidak ada duplicate | DISTINCT count vs total | 100% |

### 4.2 Quality SLA per Table

| Table | Completeness | Accuracy | Timeliness | Consistency | Uniqueness |
|-------|-------------|----------|------------|-------------|------------|
| `ohlcv` | > 95% | > 98% | < 1 day | 100% | 100% (ticker+date unique) |
| `foreign_flow` | > 90% | > 95% | < 1 day | 100% | 100% |
| `broker_flow` | > 80% | > 95% | < 1 day | 100% | 100% |
| `macro_data` | > 95% | > 98% | < 7 days | 100% | 100% |
| `scores` | > 95% | > 90% | < 1 day | 100% | 100% |
| `audit_log` | 100% | 100% | Real-time | 100% | 100% |
| `prediction_log` | > 95% | N/A | < 1 day | 100% | 100% |

### 4.3 Quality Monitoring

```python
# data/quality_monitor.py

def compute_quality_score(table_name, date):
    """
    Compute quality score 0-100 for a table on a given date.
    """
    checks = {}

    # Completeness
    expected_rows = get_expected_rows(table_name, date)
    actual_rows = get_actual_rows(table_name, date)
    checks["completeness"] = (actual_rows / expected_rows * 100) if expected_rows > 0 else 0

    # Timeliness
    latest_date = get_latest_date(table_name)
    lag_days = (date - latest_date).days
    checks["timeliness"] = max(0, 100 - lag_days * 20)  # -20 per day lag

    # Validity (schema check)
    invalid_rows = count_invalid_rows(table_name, date)
    total_rows = get_actual_rows(table_name, date)
    checks["validity"] = ((total_rows - invalid_rows) / total_rows * 100) if total_rows > 0 else 0

    # Uniqueness
    duplicate_rows = count_duplicates(table_name, date)
    checks["uniqueness"] = ((total_rows - duplicate_rows) / total_rows * 100) if total_rows > 0 else 0

    # Weighted composite
    weights = {"completeness": 0.35, "timeliness": 0.25,
               "validity": 0.25, "uniqueness": 0.15}

    score = sum(checks[k] * weights[k] for k in weights)
    return {"score": score, "checks": checks}
```

---

## 5. Data Retention Policy

### 5.1 Retention Tiers

| Tier | Retention | Tables | Rationale |
|------|-----------|--------|-----------|
| **Forever** | Indefinite | `ohlcv`, `macro_data`, `corporate_actions`, `dividends`, `instrument_master`, `market_calendar`, `model_registry` | Historical data is irreplaceable, needed for backtest |
| **Long-term** (7 years) | 7 years | `orders`, `paper_trades` | Regulatory requirement, tax audit |
| **Medium-term** (5 years) | 5 years | `foreign_flow`, `broker_flow`, `fundamental_data`, `fear_greed`, `esg_scores`, `external_events`, `policy_events`, `tca_log` | Useful for long-term analysis, but not critical |
| **Short-term** (2 years) | 2 years | `scores`, `technical_indicators`, `pattern_analysis`, `stock_personality`, `prediction_log`, `ai_weights`, `portfolio_candidates` | Can be recomputed from raw data |
| **Ephemeral** (1 year) | 1 year | `audit_log`, `news`, `relationship_matrix` | High volume, can be regenerated |

### 5.2 Archival Process

```
Active (SQLite) ──▶ Archive (Parquet) ──▶ Cold Storage (compressed) ──▶ Delete
     │                    │                       │
   < retention         = retention              + 1 year
   (hot query)         (cold query)             (backup only)
```

### 5.3 Archival Schedule

| Table | Archive Trigger | Archive To | Delete After |
|-------|----------------|------------|--------------|
| `scores` | Data > 2 years old | Parquet: `archive/tables/scores_YYYY.parquet` | + 1 year in archive |
| `audit_log` | Data > 1 year old | Parquet: `archive/tables/audit_YYYY.parquet` | + 1 year in archive |
| `prediction_log` | Data > 2 years old | Parquet: `archive/tables/predictions_YYYY.parquet` | + 1 year in archive |
| `technical_indicators` | Data > 2 years old | Parquet: `archive/tables/tech_ind_YYYY.parquet` | + 1 year in archive |

### 5.4 Archival Script

```python
# scripts/archive_old_data.py

def archive_table(table_name, retention_years):
    """
    Archive rows older than retention period to Parquet, then delete from SQLite.
    """
    cutoff_date = datetime.now() - timedelta(days=retention_years * 365)

    # Export to Parquet
    df = pd.read_sql(
        f"SELECT * FROM {table_name} WHERE date < '{cutoff_date.date()}'",
        sqlite_conn
    )
    parquet_path = f"archive/tables/{table_name}_{cutoff_date.year}.parquet"
    df.to_parquet(parquet_path, compression='snappy')

    # Verify
    parquet_df = pd.read_parquet(parquet_path)
    assert len(parquet_df) == len(df), "Archive verification failed"

    # Delete from SQLite
    conn.execute(f"DELETE FROM {table_name} WHERE date < '{cutoff_date.date()}'")
    conn.commit()

    audit_log(f"Archived {len(df)} rows from {table_name} to {parquet_path}")
```

---

## 6. Data Stewardship

### 6.1 Data Steward Roles

| Data Domain | Steward | Responsibilities |
|-------------|---------|-----------------|
| **Market Data** (OHLCV, foreign flow, broker flow) | Data Acquisition Engine | Source health, data quality, ingestion monitoring |
| **Analysis Data** (scores, indicators, patterns) | Analysis Engine | Correctness of computation, score validation |
| **AI/ML Data** (predictions, models, weights) | AI Learning Layer | Model integrity, prediction quality |
| **Execution Data** (orders, trades, TCA) | Execution Engine | Order accuracy, trade reconciliation |
| **Reference Data** (instrument_master, calendar) | Data Acquisition Engine | Up-to-date, accurate |
| **Audit Data** (audit_log) | Data Acquisition Engine | Completeness, immutability |

### 6.2 Steward Responsibilities

1. **Monitor quality** — check quality score for their domain daily
2. **Investigate anomalies** — if quality drops, investigate root cause
3. **Approve schema changes** — any schema change needs steward approval
4. **Manage retention** — ensure archival runs per schedule
5. **Document lineage** — keep lineage documentation up-to-date

---

## 7. PII & Sensitive Data Handling

### 7.1 PII Assessment

| Data | PII? | Sensitivity | Handling |
|------|------|-------------|----------|
| OHLCV | No | Public | No restriction |
| Scores | No | Internal | No restriction |
| Orders | No (but sensitive) | Financial | Encrypted at rest, access controlled |
| User watchlist | No (but personal) | Personal | User-owned, not shared |
| API Key | Yes (secret) | Critical | Env var, never in code, never logged |
| Broker credentials | Yes (secret) | Critical | Env var, encrypted, never logged |
| Telegram bot token | Yes (secret) | Critical | Env var, never in code |

### 7.2 Sensitive Data Rules

1. **API keys/credentials**: ONLY in `.env`, never committed to git
2. **`.env` in `.gitignore`**: ensure never accidentally committed
3. **Logging**: never log API keys, passwords, tokens
4. **Error messages**: never include credentials in error messages
5. **Database**: SQLite file permissions `600` (owner read/write only)
6. **Backup**: backup files same permissions as production

### 7.3 UU PDP Compliance (see doc 41)

- System does not collect user PII (name, ID, address) — only trading data
- If future: user registration → PDP compliance required (see doc 41)
- Current: single-user system, no PII stored beyond preferences

---

## 8. Data Governance Metrics

### 8.1 Monthly Governance Report

```markdown
## Data Governance Report — [Month Year]

### Data Catalog Status
- Total tables: 41
- Documented tables: 41 (100%)
- Tables with lineage: 41 (100%)
- Tables with steward: 41 (100%)

### Quality SLA Compliance
| Table | Completeness | Timeliness | Validity | Score | SLA Met? |
|-------|-------------|------------|----------|-------|----------|
| ohlcv | 98% | < 1 day | 100% | 96 | Yes |
| foreign_flow | 92% | < 1 day | 100% | 91 | Yes |
| scores | 96% | < 1 day | 100% | 95 | Yes |
| ... | ... | ... | ... | ... | ... |

### Retention Compliance
- Tables archived this month: [N]
- Rows archived: [N]
- Space saved: [X] MB

### Issues
- [ ] Any table below SLA
- [ ] Any lineage broken (source change not propagated)
- [ ] Any stale data (> 2 days lag)
```

---

## 9. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **22** (Data Engineering) | Pipeline implementation; this doc governs the data |
| **36** (Gap/Data/Timezone) | Data gaps are quality issues tracked here |
| **41** (UU PDP) | PII compliance framework |
| **47** (Operational Contract) | T-004 (validation), T-009 (quality report) feed governance |
| **48** (DR/BCP) | Backup strategy is part of data governance |
| **51** (MLOps) | Model data lineage tracked here |

---

## Referensi

1. `src/trading_system/data/storage.py` — Database schema & data access layer
2. `src/trading_system/data/validation.py` — Data quality checks
3. `alembic/versions/` — Schema migrations (0001-0003)
4. `pustaka/22-data-engineering-pipeline.md` — Data pipeline & ETL
5. `pustaka/41-uu-pdp-compliance-fintech.md` — PII compliance
6. `pustaka/84-new-data-arrival-processing-pipeline.md` — 8 quality checks, tier system
7. DAMA-DMBOK: Data Management Body of Knowledge
8. Apache Atlas: Data governance & metadata framework

---

> **Catatan:** Data governance bukan bureaucracy — adalah foundation. "Trust your data, trust your decisions. Distrust your data, distrust everything." Setiap decision yang dihasilkan sistem hanya sebaik data yang masuk.
