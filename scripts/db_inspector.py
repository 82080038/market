"""Database Inspector — Audit menyeluruh properti & struktur SQLite pasar modal.

Skrip mandiri (standalone) untuk DBA/Lead Data Engineer. Membaca
data/market_research.db dan mengekstrak metrik kritikal:

  1. Schema & Table Discovery  — daftar tabel + kolom & Dtype
  2. Data Coverage & Ticker Completeness — row count per tabel & per ticker,
     rentang tanggal (min/max) + deteksi date gaps untuk N ticker fokus
  3. Data Quality & Missing Values Audit — % NaN/NULL per kolom (fundamental,
     volume, indikator teknikal) + cek kolom klasifikasi eksternal
     (Sektor, Market Cap, Beta)
  4. JSON-Safe Metadata Output — ringkasan ke konsol + laporan teknis ke
     database_profile_report.json agar mudah dibaca AI pada instruksi
     berikutnya.

Hanya bergantung pada sqlite3, pandas, numpy (standar stack data). Tidak
mengimpor modul proyek agar benar-benar mandiri.

Usage:
    python scripts/db_inspector.py
    DB_PATH=data/market_research.db python scripts/db_inspector.py
    python scripts/db_inspector.py --db data/market_research.db \
        --tickers BBCA.JK,BBRI.JK --limit 20 \
        --output database_profile_report.json

Referensi:
  - AGENTS.md §2 (Keputusan Desain), §7 (Cross-Platform OS Awareness)
  - Konvensi pemilihan ticker fokus: audit_ai_utility.py (--limit 20, .JK 1d)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("db_inspector")

# ── Konstanta ──────────────────────────────────────────────────────────────
# Tabel utama yang diperiksa secara mendalam untuk kualitas data & coverage.
# Tabel-tabel ini memiliki kolom `ticker` dan/atau `date|timestamp`.
KEY_TICKER_TABLES = (
    "ohlcv",
    "technical_indicators",
    "fundamental_data",
    "daily_risk_metrics",
    "daily_trading_stats",
    "stock_personality",
    "ml_labels",
    "scores",
    "valuation_cache",
    "pattern_analysis",
)

# Kolom klasifikasi eksternal yang dicari lintas tabel (case-insensitive).
# Termasuk padanan Indonesia/English untuk Sektor Industri, Market Cap, Beta.
CLASSIFICATION_KEYWORDS = {
    "sector": ["sector", "subsector", "sektor", "subsektor", "industry", "industri"],
    "market_cap": ["market_cap", "marketcap", "kapitalisasi", "market_value"],
    "beta": ["beta"],
}

# Tabel referensi klasifikasi yang diperiksa khusus.
CLASSIFICATION_TABLES = ("instrument_master", "sector_master", "fundamental_data")


# ── Util ───────────────────────────────────────────────────────────────────
def human_bytes(n: int) -> str:
    """Konversi byte ke string yang dapat dibaca manusia."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PB"


def json_safe(obj: Any) -> Any:
    """Rekursif mengubah objek numpy/pandas/Timestamp menjadi JSON-safe."""
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if np.isnan(obj):
            return None
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.ndarray,)):
        return [json_safe(v) for v in obj.tolist()]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, float):
        if math_isnan(obj):
            return None
        return obj
    return obj


def math_isnan(x: float) -> bool:
    return x != x  # NaN tidak sama dengan dirinya sendiri


# ── 1. Schema & Table Discovery ────────────────────────────────────────────
def discover_schema(conn: sqlite3.Connection) -> dict[str, Any]:
    """List semua tabel + view, kolom beserta tipe datanya."""
    cur = conn.cursor()
    cur.execute(
        "SELECT name, type FROM sqlite_master "
        "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type, name"
    )
    objects = cur.fetchall()

    schema: dict[str, Any] = {"tables": {}, "views": {}, "total_tables": 0, "total_views": 0}
    for name, obj_type in objects:
        cur.execute(f'PRAGMA table_info("{name}")')
        cols = []
        for cid, cname, ctype, notnull, dflt, pk in cur.fetchall():
            cols.append({
                "name": cname,
                "dtype": ctype or "UNKNOWN",
                "not_null": bool(notnull),
                "primary_key": bool(pk),
                "default": dflt,
            })
        bucket = "tables" if obj_type == "table" else "views"
        schema[bucket][name] = {
            "columns": cols,
            "column_count": len(cols),
        }
    schema["total_tables"] = len(schema["tables"])
    schema["total_views"] = len(schema["views"])
    logger.info("Schema: %d tabel, %d view ditemukan",
                schema["total_tables"], schema["total_views"])
    return schema


def get_ticker_tables(schema: dict[str, Any]) -> list[str]:
    """Tabel yang memiliki kolom `ticker`."""
    out = []
    for tname, info in schema["tables"].items():
        if any(c["name"].lower() == "ticker" for c in info["columns"]):
            out.append(tname)
    return sorted(out)


def get_date_column(table_cols: list[dict[str, Any]]) -> str | None:
    """Tentukan kolom tanggal utama untuk sebuah tabel."""
    names = [c["name"].lower() for c in table_cols]
    for cand in ("date", "timestamp", "as_of", "trade_date", "reporting_date"):
        if cand in names:
            return cand
    return None


# ── 2. Data Coverage & Ticker Completeness ─────────────────────────────────
def count_rows_per_table(conn: sqlite3.Connection,
                         schema: dict[str, Any]) -> dict[str, int]:
    """Hitung total baris per tabel."""
    counts: dict[str, int] = {}
    cur = conn.cursor()
    for tname in schema["tables"]:
        t0 = time.time()
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{tname}"')
            counts[tname] = cur.fetchone()[0]
        except sqlite3.OperationalError as exc:
            logger.warning("Gagal menghitung %s: %s", tname, exc)
            counts[tname] = -1
        logger.info("  row_count %-28s %12d  (%.2fs)",
                    tname, counts[tname], time.time() - t0)
    return counts


def select_focus_tickers(conn: sqlite3.Connection, limit: int,
                         explicit: list[str] | None) -> list[str]:
    """Pilih ticker fokus.

    Default: top-N ticker `.JK` di OHLCV (timeframe='1d') berdasarkan row count,
    mengikuti konvensi audit_ai_utility.py. Jika --tickers diberikan, gunakan
    itu langsung.
    """
    if explicit:
        tickers = [t.strip() for t in explicit if t.strip()]
        logger.info("Ticker fokus (eksplisit): %d -> %s", len(tickers), tickers)
        return tickers

    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT ticker, COUNT(*) AS cnt FROM ohlcv "
            "WHERE ticker LIKE '%.JK' AND timeframe='1d' "
            "GROUP BY ticker ORDER BY cnt DESC LIMIT ?",
            (limit,),
        )
        tickers = [r[0] for r in cur.fetchall()]
    except sqlite3.OperationalError as exc:
        logger.error("Gagal memilih ticker fokus dari ohlcv: %s", exc)
        tickers = []
    logger.info("Ticker fokus (top-%d .JK 1d): %d -> %s", limit, len(tickers), tickers)
    return tickers


def per_ticker_row_counts(conn: sqlite3.Connection, ticker_tables: list[str],
                          focus_tickers: list[str]) -> dict[str, Any]:
    """Row count per ticker untuk tabel berkolo ticker (hanya ticker fokus)."""
    if not focus_tickers:
        return {}
    placeholders = ",".join("?" for _ in focus_tickers)
    cur = conn.cursor()
    out: dict[str, Any] = {}
    for tname in ticker_tables:
        t0 = time.time()
        try:
            cur.execute(
                f'SELECT ticker, COUNT(*) FROM "{tname}" '
                f"WHERE ticker IN ({placeholders}) GROUP BY ticker",
                focus_tickers,
            )
            rows = dict(cur.fetchall())
        except sqlite3.OperationalError as exc:
            logger.warning("  per_ticker %s gagal: %s", tname, exc)
            rows = {}
        # pastikan semua ticker fokus muncul (0 jika tidak ada)
        out[tname] = {t: int(rows.get(t, 0)) for t in focus_tickers}
        logger.info("  per_ticker %-26s (%.2fs)", tname, time.time() - t0)
    return out


def ticker_date_coverage(conn: sqlite3.Connection, schema: dict[str, Any],
                         focus_tickers: list[str]) -> dict[str, Any]:
    """Rentang tanggal (min/max) + deteksi date gaps per ticker fokus.

    Date gap = hari kerja (Sen-Jum) yang hilang antara min_date dan max_date
    pada OHLCV timeframe='1d'. Ini mendeteksi data yang terputus di tengah.
    """
    if not focus_tickers:
        return {}
    cur = conn.cursor()
    placeholders = ",".join("?" for _ in focus_tickers)
    out: dict[str, Any] = {}

    # OHLCV adalah sumber truth utama untuk date coverage
    t0 = time.time()
    try:
        cur.execute(
            f"SELECT ticker, MIN(timestamp), MAX(timestamp), COUNT(*) "
            f"FROM ohlcv WHERE timeframe='1d' AND ticker IN ({placeholders}) "
            f"GROUP BY ticker",
            focus_tickers,
        )
        agg = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
    except sqlite3.OperationalError as exc:
        logger.warning("  ohlcv date coverage gagal: %s", exc)
        agg = {}
    logger.info("  ohlcv date coverage (%.2fs)", time.time() - t0)

    # Ambil tanggal aktual per ticker untuk deteksi gap
    for ticker in focus_tickers:
        entry: dict[str, Any] = {"ticker": ticker}
        if ticker not in agg:
            entry.update({"min_date": None, "max_date": None, "row_count": 0,
                          "missing_business_days": None, "gap_pct": None,
                          "largest_gap_days": None, "status": "NO_DATA"})
            out[ticker] = entry
            continue

        mn, mx, cnt = agg[ticker]
        entry["min_date"] = mn
        entry["max_date"] = mx
        entry["row_count"] = int(cnt)

        # Deteksi gap: bandingkan tanggal aktual vs hari kerja yang diharapkan
        try:
            cur.execute(
                "SELECT DISTINCT date(timestamp) FROM ohlcv "
                "WHERE timeframe='1d' AND ticker=? ORDER BY 1",
                (ticker,),
            )
            actual = pd.to_datetime([r[0] for r in cur.fetchall()])
        except sqlite3.OperationalError:
            actual = pd.to_datetime([])

        if len(actual) == 0:
            entry.update({"missing_business_days": None, "gap_pct": None,
                          "largest_gap_days": None, "status": "NO_DATES"})
        else:
            start = actual.min().normalize()
            end = actual.max().normalize()
            expected = pd.bdate_range(start, end)
            actual_set = set(actual.normalize())
            missing = [d for d in expected if d not in actual_set]
            missing_n = len(missing)
            gap_pct = round(100.0 * missing_n / len(expected), 2) if len(expected) else 0.0
            # rentang kosong terbesar (calendar days antara tanggal berurutan)
            diffs = actual.normalize().sort_values().to_series().diff().dropna().dt.days
            largest = int(diffs.max()) if len(diffs) else 0
            entry["missing_business_days"] = missing_n
            entry["gap_pct"] = gap_pct
            entry["largest_gap_days"] = largest
            # status: CONTINUOUS jika gap kecil (<5%), GAPS jika signifikan
            entry["status"] = "CONTINUOUS" if gap_pct < 5.0 else "GAPS_DETECTED"
        out[ticker] = entry
    return out


# ── 3. Data Quality & Missing Values Audit ─────────────────────────────────
def null_audit_table(conn: sqlite3.Connection, tname: str,
                     focus_tickers: list[str],
                     date_col: str | None) -> dict[str, Any]:
    """Hitung % NULL per kolom untuk sebuah tabel.

    - Tabel berkolo ticker: hanya ticker fokus (memakai index, cepat).
    - Tabel tanpa ticker: seluruh tabel (asumsi tabel kecil/referensi).
    """
    cur = conn.cursor()
    cur.execute(f'PRAGMA table_info("{tname}")')
    cols = [(c[1], c[2]) for c in cur.fetchall()]
    if not cols:
        return {}

    has_ticker = any(c[0].lower() == "ticker" for c in cols)
    where = ""
    params: list[Any] = []
    if has_ticker and focus_tickers:
        placeholders = ",".join("?" for _ in focus_tickers)
        where = f"WHERE ticker IN ({placeholders})"
        params = list(focus_tickers)

    # total baris pada subset
    try:
        cur.execute(f'SELECT COUNT(*) FROM "{tname}" {where}', params)
        total = cur.fetchone()[0]
    except sqlite3.OperationalError as exc:
        logger.warning("  null_audit %s: COUNT gagal: %s", tname, exc)
        return {}
    if total == 0:
        return {"_total_rows": 0, "_note": "no rows in subset"}

    nulls: dict[str, Any] = {"_total_rows": int(total)}
    for cname, _ctype in cols:
        try:
            cur.execute(
                f'SELECT COUNT(*) FROM "{tname}" {where} '
                f"AND \"{cname}\" IS NULL",
                params,
            )
            n_null = cur.fetchone()[0]
        except sqlite3.OperationalError:
            n_null = 0
        pct = round(100.0 * n_null / total, 4) if total else 0.0
        nulls[cname] = {"null_count": int(n_null), "null_pct": pct}
    return nulls


def technical_indicators_audit(conn: sqlite3.Connection,
                               focus_tickers: list[str]) -> dict[str, Any]:
    """Audit khusus technical_indicators (format panjang: indicator/value).

    Hitung: null % pada `value`, coverage per jenis indikator, dan rentang
    tanggal per ticker. Memakai index ix_ti_ticker.
    """
    if not focus_tickers:
        return {}
    placeholders = ",".join("?" for _ in focus_tickers)
    cur = conn.cursor()
    t0 = time.time()

    # Total baris untuk ticker fokus
    cur.execute(
        f"SELECT COUNT(*) FROM technical_indicators WHERE ticker IN ({placeholders})",
        focus_tickers,
    )
    total = cur.fetchone()[0]

    # Null pada value
    cur.execute(
        f"SELECT COUNT(*) FROM technical_indicators WHERE ticker IN ({placeholders}) "
        f"AND value IS NULL",
        focus_tickers,
    )
    value_null = cur.fetchone()[0]

    # Coverage per jenis indikator
    cur.execute(
        f"SELECT indicator, COUNT(*), "
        f"SUM(CASE WHEN value IS NULL THEN 1 ELSE 0 END) "
        f"FROM technical_indicators WHERE ticker IN ({placeholders}) "
        f"GROUP BY indicator ORDER BY 2 DESC",
        focus_tickers,
    )
    per_indicator: dict[str, Any] = {}
    for ind, cnt, nnull in cur.fetchall():
        per_indicator[ind] = {
            "row_count": int(cnt),
            "null_count": int(nnull),
            "null_pct": round(100.0 * nnull / cnt, 4) if cnt else 0.0,
        }

    logger.info("  technical_indicators audit (%.2fs, %d rows fokus)",
                time.time() - t0, total)
    return {
        "_total_rows_focus": int(total),
        "value_null_count": int(value_null),
        "value_null_pct": round(100.0 * value_null / total, 4) if total else 0.0,
        "indicators": per_indicator,
        "distinct_indicators": len(per_indicator),
    }


def data_quality_audit(conn: sqlite3.Connection, schema: dict[str, Any],
                       focus_tickers: list[str]) -> dict[str, Any]:
    """Audit nilai kosong (NULL/NaN) per kolom pada tabel-tabelutama."""
    audit: dict[str, Any] = {}

    # Tabel format lebar (per-kolom null %)
    wide_tables = [t for t in KEY_TICKER_TABLES if t != "technical_indicators"
                   and t in schema["tables"]]
    for tname in wide_tables:
        t0 = time.time()
        date_col = get_date_column(schema["tables"][tname]["columns"])
        res = null_audit_table(conn, tname, focus_tickers, date_col)
        if res:
            audit[tname] = res
            logger.info("  null_audit %-26s (%.2fs)", tname, time.time() - t0)

    # technical_indicators (format panjang) — audit khusus
    if "technical_indicators" in schema["tables"]:
        audit["technical_indicators"] = technical_indicators_audit(conn, focus_tickers)

    return audit


# ── Klasifikasi eksternal (Sektor, Market Cap, Beta) ───────────────────────
def classification_audit(conn: sqlite3.Connection,
                         schema: dict[str, Any],
                         focus_tickers: list[str]) -> dict[str, Any]:
    """Cek kolom klasifikasi eksternal: Sektor Industri, Market Cap, Beta."""
    cur = conn.cursor()
    found: dict[str, Any] = {"columns_found": {}, "coverage_for_focus_tickers": {}}

    # 1. Pindai semua tabel untuk kolom yang cocok keyword
    for tname, info in schema["tables"].items():
        col_names = [c["name"] for c in info["columns"]]
        lower = {c.lower(): c for c in col_names}
        for category, keywords in CLASSIFICATION_KEYWORDS.items():
            for kw in keywords:
                matches = [orig for low, orig in lower.items() if kw in low]
                for m in matches:
                    key = f"{tname}.{m}"
                    found["columns_found"].setdefault(category, []).append(key)

    # dedup
    for cat in found["columns_found"]:
        found["columns_found"][cat] = sorted(set(found["columns_found"][cat]))

    # 2. Coverage untuk ticker fokus pada instrument_master (sumber utama)
    if focus_tickers and "instrument_master" in schema["tables"]:
        cur.execute("PRAGMA table_info(instrument_master)")
        im_cols = [c[1] for c in cur.fetchall()]
        placeholders = ",".join("?" for _ in focus_tickers)
        # ambil kolom klasifikasi yang ada di instrument_master
        sel_cols = []
        for c in im_cols:
            cl = c.lower()
            if (any(k in cl for k in CLASSIFICATION_KEYWORDS["sector"])
                    or any(k in cl for k in CLASSIFICATION_KEYWORDS["market_cap"])
                    or any(k in cl for k in CLASSIFICATION_KEYWORDS["beta"])
                    or c.lower() == "ticker"):
                sel_cols.append(c)
        if sel_cols:
            sel_sql = ", ".join(f'"{c}"' for c in sel_cols)
            try:
                cur.execute(
                    f"SELECT {sel_sql} FROM instrument_master "
                    f"WHERE ticker IN ({placeholders})",
                    focus_tickers,
                )
                rows = cur.fetchall()
                df = pd.DataFrame(rows, columns=sel_cols)
                cov: dict[str, Any] = {}
                for c in sel_cols:
                    if c.lower() == "ticker":
                        continue
                    non_null = int(df[c].notna().sum())
                    cov[c] = {
                        "non_null": non_null,
                        "total": len(df),
                        "coverage_pct": round(100.0 * non_null / len(df), 2) if len(df) else 0.0,
                    }
                found["coverage_for_focus_tickers"] = cov
            except sqlite3.OperationalError as exc:
                logger.warning("  classification coverage gagal: %s", exc)

    # 3. Ringkasan: apakah Beta ada di DB?
    found["beta_present"] = len(found["columns_found"].get("beta", [])) > 0
    found["sector_present"] = len(found["columns_found"].get("sector", [])) > 0
    found["market_cap_present"] = len(found["columns_found"].get("market_cap", [])) > 0
    return found


# ── Orkestrasi ─────────────────────────────────────────────────────────────
def inspect_database(db_path: Path, focus_limit: int,
                     explicit_tickers: list[str] | None) -> dict[str, Any]:
    """Jalankan audit menyeluruh dan kembalikan profil database."""
    logger.info("=" * 72)
    logger.info("DATABASE INSPECTOR — Audit Properti & Struktur")
    logger.info("=" * 72)
    logger.info("Path DB : %s", db_path)
    logger.info("Ukuran  : %s", human_bytes(db_path.stat().st_size))
    logger.info("SQLite  : %s", sqlite3.sqlite_version)
    logger.info("pandas  : %s | numpy : %s", pd.__version__, np.__version__)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        # 1. Schema
        logger.info("\n--- 1. SCHEMA & TABLE DISCOVERY ---")
        schema = discover_schema(conn)
        ticker_tables = get_ticker_tables(schema)
        logger.info("Tabel berkolo 'ticker': %d -> %s",
                    len(ticker_tables), ticker_tables)

        # 2a. Row count per tabel
        logger.info("\n--- 2a. ROW COUNT PER TABEL ---")
        row_counts = count_rows_per_table(conn, schema)
        total_rows = sum(v for v in row_counts.values() if v > 0)
        logger.info("TOTAL baris (semua tabel): %s", f"{total_rows:,}")

        # 2b. Pilih ticker fokus
        logger.info("\n--- 2b. PILIH TICKER FOKUS ---")
        focus_tickers = select_focus_tickers(conn, focus_limit, explicit_tickers)

        # 2c. Per-ticker row count
        logger.info("\n--- 2c. ROW COUNT PER TICKER (fokus) ---")
        per_ticker = per_ticker_row_counts(conn, ticker_tables, focus_tickers)

        # 2d. Date coverage + gap detection
        logger.info("\n--- 2d. DATE COVERAGE & GAP DETECTION ---")
        date_cov = ticker_date_coverage(conn, schema, focus_tickers)
        gaps = [t for t, v in date_cov.items() if v.get("status") == "GAPS_DETECTED"]
        no_data = [t for t, v in date_cov.items() if v.get("status") in ("NO_DATA", "NO_DATES")]
        logger.info("Ticker dgn gap signifikan (>=5%% bdays hilang): %d %s", len(gaps), gaps)
        logger.info("Ticker tanpa data OHLCV 1d: %d %s", len(no_data), no_data)

        # 3. Data quality
        logger.info("\n--- 3. DATA QUALITY & MISSING VALUES ---")
        quality = data_quality_audit(conn, schema, focus_tickers)

        # 4. Klasifikasi eksternal
        logger.info("\n--- 4. KLASIFIKASI EKSTERNAL (Sektor/MarketCap/Beta) ---")
        classification = classification_audit(conn, schema, focus_tickers)
        logger.info("Sektor     : %s (%s)",
                    classification["sector_present"],
                    classification["columns_found"].get("sector", []))
        logger.info("Market Cap : %s (%s)",
                    classification["market_cap_present"],
                    classification["columns_found"].get("market_cap", []))
        logger.info("Beta       : %s (%s)",
                    classification["beta_present"],
                    classification["columns_found"].get("beta", []))

        # Ringkasan
        summary = {
            "db_path": str(db_path),
            "db_size_bytes": int(db_path.stat().st_size),
            "db_size_human": human_bytes(db_path.stat().st_size),
            "sqlite_version": sqlite3.sqlite_version,
            "total_tables": schema["total_tables"],
            "total_views": schema["total_views"],
            "total_rows_all_tables": int(total_rows),
            "focus_ticker_count": len(focus_tickers),
            "focus_tickers": focus_tickers,
            "ticker_tables_count": len(ticker_tables),
            "tickers_with_gaps": gaps,
            "tickers_no_data": no_data,
            "sector_present": classification["sector_present"],
            "market_cap_present": classification["market_cap_present"],
            "beta_present": classification["beta_present"],
        }

        report = {
            "generated_at": pd.Timestamp.now().isoformat(),
            "summary": summary,
            "schema": schema,
            "row_counts": row_counts,
            "ticker_tables": ticker_tables,
            "per_ticker_row_counts": per_ticker,
            "ticker_date_coverage": date_cov,
            "data_quality": quality,
            "classification_columns": classification,
        }
        return report
    finally:
        conn.close()


def print_console_summary(report: dict[str, Any]) -> None:
    """Cetak ringkasan profil database ke konsol (bersih, mudah dibaca)."""
    s = report["summary"]
    print("\n" + "=" * 72)
    print("RINGKASAN PROFIL DATABASE")
    print("=" * 72)
    print(f"Path              : {s['db_path']}")
    print(f"Ukuran            : {s['db_size_human']}")
    print(f"Total tabel       : {s['total_tables']}  (view: {s['total_views']})")
    print(f"Total baris       : {s['total_rows_all_tables']:,}")
    print(f"Tabel berkolo ticker: {s['ticker_tables_count']}")
    print(f"Ticker fokus      : {s['focus_ticker_count']} -> {s['focus_tickers']}")

    print("\n--- Row count per tabel (top 15) ---")
    rc = sorted(report["row_counts"].items(), key=lambda x: x[1], reverse=True)
    for tname, cnt in rc[:15]:
        print(f"  {tname:<30s} {cnt:>14,}")
    if len(rc) > 15:
        print(f"  ... ({len(rc) - 15} tabel lainnya)")

    print("\n--- Date coverage ticker fokus (OHLCV 1d) ---")
    print(f"  {'Ticker':<12s} {'min_date':<12s} {'max_date':<12s} "
          f"{'rows':>10s} {'miss_bdays':>11s} {'gap%':>7s} {'status':<14s}")
    for t, v in report["ticker_date_coverage"].items():
        if v.get("min_date") is None:
            print(f"  {t:<12s} {'-':<12s} {'-':<12s} {v.get('row_count',0):>10,} "
                  f"{'-':>11s} {'-':>7s} {v.get('status','-'):<14s}")
            continue
        print(f"  {t:<12s} {v['min_date']:<12s} {v['max_date']:<12s} "
              f"{v['row_count']:>10,} {v.get('missing_business_days','-'):>11} "
              f"{v.get('gap_pct','-'):>7} {v['status']:<14s}")

    print("\n--- Klasifikasi eksternal ---")
    cc = report["classification_columns"]
    print(f"  Sektor Industri : {'ADA' if cc['sector_present'] else 'TIDAK ADA'} "
          f"-> {cc['columns_found'].get('sector', [])}")
    print(f"  Market Cap      : {'ADA' if cc['market_cap_present'] else 'TIDAK ADA'} "
          f"-> {cc['columns_found'].get('market_cap', [])}")
    print(f"  Beta            : {'ADA' if cc['beta_present'] else 'TIDAK ADA'} "
          f"-> {cc['columns_found'].get('beta', [])}")
    if cc["coverage_for_focus_tickers"]:
        print("  Coverage (instrument_master, ticker fokus):")
        for col, cov in cc["coverage_for_focus_tickers"].items():
            print(f"    {col:<22s} {cov['non_null']}/{cov['total']} ({cov['coverage_pct']}%)")

    print("\n--- Data quality highlight (NULL% kolom kunci) ---")
    dq = report["data_quality"]
    # OHLCV
    if "ohlcv" in dq:
        print("  ohlcv:")
        for col in ("open", "high", "low", "close", "volume", "adjusted_close",
                    "data_quality_score"):
            if col in dq["ohlcv"]:
                print(f"    {col:<22s} null {dq['ohlcv'][col]['null_pct']}%")
    if "fundamental_data" in dq:
        print("  fundamental_data:")
        for col in ("pe", "pb", "roe", "der", "market_cap", "eps", "revenue",
                    "dividend_yield"):
            if col in dq["fundamental_data"]:
                print(f"    {col:<22s} null {dq['fundamental_data'][col]['null_pct']}%")
    if "technical_indicators" in dq:
        ti = dq["technical_indicators"]
        print(f"  technical_indicators: value null {ti['value_null_pct']}% "
              f"({ti['distinct_indicators']} indikator berbeda)")
        # top 5 indikator by row count
        inds = sorted(ti["indicators"].items(), key=lambda x: x[1]["row_count"],
                      reverse=True)[:5]
        for ind, info in inds:
            print(f"    {ind:<22s} rows {info['row_count']:,} null {info['null_pct']}%")

    print("\n" + "=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit menyeluruh properti & struktur database SQLite pasar modal.",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path file SQLite (default: env DB_PATH atau <project>/data/market_research.db)",
    )
    parser.add_argument(
        "--tickers", type=str, default=None,
        help="Daftar ticker fokus dipisah koma (default: top-N .JK dari OHLCV 1d)",
    )
    parser.add_argument(
        "--limit", type=int, default=20,
        help="Jumlah ticker fokus (default: 20, mengikuti konvensi audit_ai_utility)",
    )
    parser.add_argument(
        "--output", type=str, default="database_profile_report.json",
        help="File output laporan JSON (default: database_profile_report.json)",
    )
    args = parser.parse_args()

    # Resolusi path DB: arg > env DB_PATH > <project_root>/data/market_research.db
    # project_root = parent dari direktori scripts/
    project_root = Path(__file__).resolve().parent.parent
    db_path_str = args.db or os.environ.get("DB_PATH") or \
        str(project_root / "data" / "market_research.db")
    db_path = Path(db_path_str)

    if not db_path.exists():
        logger.error("File database TIDAK DITEMUKAN: %s", db_path)
        logger.error("Gunakan --db <path> atau set env DB_PATH=<path>")
        return 2
    if not db_path.is_file():
        logger.error("Path bukan file: %s", db_path)
        return 2

    explicit = None
    if args.tickers:
        explicit = [t.strip() for t in args.tickers.split(",") if t.strip()]

    t_start = time.time()
    try:
        report = inspect_database(db_path, args.limit, explicit)
    except sqlite3.DatabaseError as exc:
        logger.error("Database error: %s", exc)
        return 3
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error tak terduga saat audit: %s", exc)
        return 4

    print_console_summary(report)

    # Simpan laporan JSON
    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = project_root / out_path
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(json_safe(report), fh, indent=2, ensure_ascii=False)
    logger.info("Laporan JSON disimpan: %s (%.2f KB)", out_path,
                out_path.stat().st_size / 1024.0)
    logger.info("Audit selesai dalam %.2fs", time.time() - t_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
