"""Backfill relational hierarchy tables from instrument_master.

Migrates data from the flat instrument_master table into the normalized
hierarchy: Negara → Regulator → Bursa → Sektor → Emiten → Instrumen
+ Indeks Pasar for index tickers.

Mapping rules:
  - .JK suffix → Bursa Efek Indonesia (BEI/IDX), OJK regulator, Indonesia
  - ^ prefix  → indeks_pasar table with jenis_indeks from index_category
  - =F suffix → instrumen with jenis_instrumen='Komoditas'
  - Other     → mapped by market_mic to appropriate bursa/regulator

Usage:
    python scripts/backfill_relational_tables.py [--db data/market_research.db] [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Regulator mapping by country/market ───────────────────────────────────

REGULATORS = [
    ("Otoritas Jasa Keuangan", "Indonesia"),
    ("Securities and Exchange Commission", "United States"),
    ("Securities and Futures Commission", "Hong Kong"),
    ("Financial Services Agency", "Japan"),
    ("Monetary Authority of Singapore", "Singapore"),
    ("Financial Conduct Authority", "United Kingdom"),
    ("Federal Financial Supervisory Authority", "Germany"),
    ("China Securities Regulatory Commission", "China"),
]

# MIC → (bursa_name, regulator_name, country)
MIC_TO_BURSA: dict[str, tuple[str, str, str]] = {
    "XIDX": ("Bursa Efek Indonesia", "Otoritas Jasa Keuangan", "Indonesia"),
    "XNYS": ("New York Stock Exchange", "Securities and Exchange Commission", "United States"),
    "XNAS": ("NASDAQ", "Securities and Exchange Commission", "United States"),
    "XHKG": ("Hong Kong Stock Exchange", "Securities and Futures Commission", "Hong Kong"),
    "XTSE": ("Tokyo Stock Exchange", "Financial Services Agency", "Japan"),
    "XSGX": ("Singapore Exchange", "Monetary Authority of Singapore", "Singapore"),
    "XLON": ("London Stock Exchange", "Financial Conduct Authority", "United Kingdom"),
    "XFRA": ("Frankfurt Stock Exchange", "Federal Financial Supervisory Authority", "Germany"),
    "XSHG": ("Shanghai Stock Exchange", "China Securities Regulatory Commission", "China"),
    "XCEC": ("CME/Chicago Exchange", "Securities and Exchange Commission", "United States"),
    "XFXS": ("Global FX Market", "Securities and Exchange Commission", "United States"),
}

# Index category → jenis_indeks mapping
INDEX_CATEGORY_MAP: dict[str, str] = {
    "broad_market": "Broad Market",
    "sectoral": "Sectoral",
    "factor": "Factor",
    "esg": "ESG",
    "sharia": "Sharia",
    "board": "Board",
    "volatility": "Volatility",
    "rate": "Rate",
    "currency": "Currency",
    "global": "Global",
    "composite": "Composite",
}


def get_or_create_regulator(conn: sqlite3.Connection, nama: str, negara: str) -> int:
    """Get or create a regulator row, return id_regulator."""
    row = conn.execute(
        "SELECT id_regulator FROM regulator WHERE nama_regulator=? AND negara=?",
        (nama, negara),
    ).fetchone()
    if row:
        return row[0]
    cursor = conn.execute(
        "INSERT INTO regulator (nama_regulator, negara) VALUES (?, ?)",
        (nama, negara),
    )
    return cursor.lastrowid


def get_or_create_bursa(conn: sqlite3.Connection, nama: str, mic: str | None, id_reg: int) -> int:
    """Get or create a bursa_efek row, return id_bursa."""
    row = conn.execute(
        "SELECT id_bursa FROM bursa_efek WHERE nama_bursa=?", (nama,)
    ).fetchone()
    if row:
        return row[0]
    cursor = conn.execute(
        "INSERT INTO bursa_efek (nama_bursa, mic_code, id_regulator) VALUES (?, ?, ?)",
        (nama, mic, id_reg),
    )
    return cursor.lastrowid


def get_or_create_sektor(conn: sqlite3.Connection, nama: str) -> int | None:
    """Get or create a sektor row, return id_sektor."""
    if not nama:
        return None
    row = conn.execute(
        "SELECT id_sektor FROM sektor WHERE nama_sektor=?", (nama,)
    ).fetchone()
    if row:
        return row[0]
    cursor = conn.execute(
        "INSERT INTO sektor (nama_sektor) VALUES (?)", (nama,)
    )
    return cursor.lastrowid


def get_or_create_emiten(
    conn: sqlite3.Connection,
    kode_ticker: str,
    nama: str | None,
    id_bursa: int,
    id_sektor: int | None,
    subsektor: str | None,
    is_active: bool,
) -> int:
    """Get or create an emiten row, return id_emiten."""
    row = conn.execute(
        "SELECT id_emiten FROM emiten WHERE kode_ticker=?", (kode_ticker,)
    ).fetchone()
    if row:
        return row[0]
    cursor = conn.execute(
        "INSERT INTO emiten (kode_ticker, nama_perusahaan, id_bursa, id_sektor, subsektor, is_active) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (kode_ticker, nama, id_bursa, id_sektor, subsektor, is_active),
    )
    return cursor.lastrowid


def get_or_create_instrumen(
    conn: sqlite3.Connection,
    id_emiten: int,
    jenis_instrumen: str,
    asset_class: str,
    base_currency: str,
    is_active: bool,
) -> int:
    """Get or create an instrumen row, return id_instrumen."""
    row = conn.execute(
        "SELECT id_instrumen FROM instrumen WHERE id_emiten=? AND jenis_instrumen=?",
        (id_emiten, jenis_instrumen),
    ).fetchone()
    if row:
        return row[0]
    cursor = conn.execute(
        "INSERT INTO instrumen (id_emiten, jenis_instrumen, asset_class, base_currency, is_active) "
        "VALUES (?, ?, ?, ?, ?)",
        (id_emiten, jenis_instrumen, asset_class, base_currency, is_active),
    )
    return cursor.lastrowid


def get_or_create_indeks(
    conn: sqlite3.Connection,
    kode_indeks: str,
    nama: str | None,
    id_bursa: int | None,
    jenis_indeks: str | None,
    asset_class: str,
    is_active: bool,
) -> int:
    """Get or create an indeks_pasar row, return id_indeks."""
    row = conn.execute(
        "SELECT id_indeks FROM indeks_pasar WHERE kode_indeks=?", (kode_indeks,)
    ).fetchone()
    if row:
        return row[0]
    cursor = conn.execute(
        "INSERT INTO indeks_pasar (kode_indeks, nama_indeks, id_bursa, jenis_indeks, asset_class, is_active) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (kode_indeks, nama, id_bursa, jenis_indeks, asset_class, is_active),
    )
    return cursor.lastrowid


def run_backfill(db_path: str, dry_run: bool = False) -> None:
    """Run the full backfill from instrument_master to relational tables."""
    conn = sqlite3.connect(db_path)

    # ── Step 1: Seed regulators ──────────────────────────────────────────
    logger.info("Step 1: Seeding regulators...")
    reg_ids: dict[str, int] = {}
    for nama, negara in REGULATORS:
        rid = get_or_create_regulator(conn, nama, negara)
        reg_ids[f"{nama}/{negara}"] = rid
    if not dry_run:
        conn.commit()
    logger.info("  %d regulators", len(reg_ids))

    # ── Step 2: Seed bursa_efek from market_registry ─────────────────────
    logger.info("Step 2: Seeding bursa_efek from market_registry...")
    bursa_ids: dict[str, int] = {}
    for mic, (nama, reg_nama, reg_negara) in MIC_TO_BURSA.items():
        reg_key = f"{reg_nama}/{reg_negara}"
        id_reg = reg_ids.get(reg_key)
        if id_reg is None:
            id_reg = get_or_create_regulator(conn, reg_nama, reg_negara)
            reg_ids[reg_key] = id_reg
        bid = get_or_create_bursa(conn, nama, mic, id_reg)
        bursa_ids[mic] = bid
    if not dry_run:
        conn.commit()
    logger.info("  %d bursa", len(bursa_ids))

    # ── Step 3: Seed sektor from distinct sectors ────────────────────────
    logger.info("Step 3: Seeding sektor...")
    sectors = conn.execute(
        "SELECT DISTINCT sector FROM instrument_master WHERE sector IS NOT NULL AND sector != '' ORDER BY sector"
    ).fetchall()
    sektor_ids: dict[str, int] = {}
    for (s,) in sectors:
        sid = get_or_create_sektor(conn, s)
        if sid is not None:
            sektor_ids[s] = sid
    if not dry_run:
        conn.commit()
    logger.info("  %d sektor", len(sektor_ids))

    # ── Step 4: Migrate instruments ──────────────────────────────────────
    logger.info("Step 4: Migrating instrument_master → emiten + instrumen/indeks_pasar...")
    rows = conn.execute(
        "SELECT ticker, market_mic, asset_class, name, sector, subsector, "
        "base_currency, is_active, index_category "
        "FROM instrument_master"
    ).fetchall()

    n_emiten = 0
    n_instrumen = 0
    n_indeks = 0

    for ticker, mic, asset_class, name, sector, subsector, base_currency, is_active, index_category in rows:
        # Determine bursa
        id_bursa = bursa_ids.get(mic, bursa_ids.get("XIDX", 1))

        # Determine sektor
        id_sektor = sektor_ids.get(sector) if sector else None

        # Determine jenis_instrumen based on asset_class
        if asset_class == "EQUITY_INDIVIDUAL":
            jenis_instrumen = "Saham"
        elif asset_class == "INDEX_COMPOSITE":
            jenis_instrumen = "Indeks"
        elif asset_class == "COMMODITY_FUTURES":
            jenis_instrumen = "Komoditas"
        elif asset_class == "VOLATILITY_RATE":
            jenis_instrumen = "Volatilitas/Suku Bunga"
        elif asset_class == "etf":
            jenis_instrumen = "ETF"
        elif asset_class == "fx":
            jenis_instrumen = "Valuta Asing"
        elif asset_class == "fund":
            jenis_instrumen = "Reksa Dana"
        else:
            jenis_instrumen = "Lainnya"

        # Route: indices → indeks_pasar, everything else → emiten + instrumen
        if asset_class in ("INDEX_COMPOSITE", "VOLATILITY_RATE"):
            jenis_indeks = INDEX_CATEGORY_MAP.get(index_category or "", None)
            get_or_create_indeks(
                conn, ticker, name, id_bursa, jenis_indeks, asset_class, is_active,
            )
            n_indeks += 1
        else:
            id_emiten = get_or_create_emiten(
                conn, ticker, name, id_bursa, id_sektor, subsector, is_active,
            )
            n_emiten += 1
            get_or_create_instrumen(
                conn, id_emiten, jenis_instrumen, asset_class,
                base_currency or "IDR", is_active,
            )
            n_instrumen += 1

    if not dry_run:
        conn.commit()
    logger.info("  %d emiten, %d instrumen, %d indeks_pasar", n_emiten, n_instrumen, n_indeks)

    # ── Summary ──────────────────────────────────────────────────────────
    if not dry_run:
        for table in ("regulator", "bursa_efek", "sektor", "emiten", "instrumen", "indeks_pasar"):
            r = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            logger.info("  Table %s: %d rows", table, r[0])

    conn.close()
    logger.info("Backfill complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill relational hierarchy tables from instrument_master")
    parser.add_argument("--db", default="data/market_research.db", help="Database path")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without committing")
    args = parser.parse_args()

    logger.info("Database: %s", args.db)
    logger.info("Dry run: %s", args.dry_run)
    run_backfill(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
