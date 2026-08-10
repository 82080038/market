"""Drop redundant tables: emiten, instrumen, sektor, bursa_efek, indeks_pasar,
fx_rates, regulator, transaksi_investor.

Data already consolidated into:
  emiten/instrumen → instrument_master
  sektor → sector_master
  bursa_efek → market_registry
  indeks_pasar → instrument_master
  fx_rates → ohlcv (ticker='IDR=X')
  regulator → only referenced by bursa_efek
  transaksi_investor → 0 rows, no IDX transaction API

broker_bursa recreated without FK to bursa_efek.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-10
"""
from alembic import op
from sqlalchemy import text


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Save broker_bursa data
    conn = op.get_bind()
    bb_rows = conn.execute(
        text("SELECT id_broker, id_bursa FROM broker_bursa")
    ).fetchall()

    # Disable FK enforcement for clean drops
    conn.execute(text("PRAGMA foreign_keys = OFF"))

    # Drop indexes first
    for idx_sql in [
        "DROP INDEX IF EXISTS ix_transaksi_broker",
        "DROP INDEX IF EXISTS ix_transaksi_instrumen",
        "DROP INDEX IF EXISTS ix_transaksi_tanggal",
        "DROP INDEX IF EXISTS ix_instrumen_jenis",
        "DROP INDEX IF EXISTS ix_instrumen_emiten",
        "DROP INDEX IF EXISTS ix_emiten_sektor",
        "DROP INDEX IF EXISTS ix_emiten_bursa",
        "DROP INDEX IF EXISTS ix_indeks_jenis",
        "DROP INDEX IF EXISTS ix_indeks_bursa",
        "DROP INDEX IF EXISTS ix_bursa_regulator",
    ]:
        conn.execute(text(idx_sql))

    # Drop tables in FK dependency order (children first)
    for table in [
        "transaksi_investor",
        "instrumen",
        "emiten",
        "indeks_pasar",
        "broker_bursa",
        "bursa_efek",
        "sektor",
        "regulator",
        "fx_rates",
    ]:
        conn.execute(text(f"DROP TABLE IF EXISTS {table}"))

    conn.execute(text("PRAGMA foreign_keys = ON"))

    # Recreate broker_bursa without FK to bursa_efek
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS broker_bursa ("
            "id_broker INTEGER NOT NULL, "
            "id_bursa INTEGER NOT NULL, "
            "PRIMARY KEY (id_broker, id_bursa)"
            ")"
        )
    )
    for id_broker, id_bursa in bb_rows:
        conn.execute(
            text("INSERT OR REPLACE INTO broker_bursa (id_broker, id_bursa) VALUES (:b, :u)"),
            {"b": id_broker, "u": id_bursa},
        )


def downgrade() -> None:
    # Recreate tables (schema only, data lost)
    conn = op.get_bind()

    conn.execute(text("PRAGMA foreign_keys = OFF"))
    conn.execute(text("DROP TABLE IF EXISTS broker_bursa"))
    conn.execute(text("PRAGMA foreign_keys = ON"))

    # Recreate regulator
    conn.execute(
        text(
            "CREATE TABLE regulator ("
            "id_regulator INTEGER PRIMARY KEY AUTOINCREMENT, "
            "nama_regulator VARCHAR(100) NOT NULL, "
            "negara VARCHAR(50) NOT NULL, "
            "CONSTRAINT uq_regulator_nama_negara UNIQUE (nama_regulator, negara)"
            ")"
        )
    )

    # Recreate bursa_efek
    conn.execute(
        text(
            "CREATE TABLE bursa_efek ("
            "id_bursa INTEGER PRIMARY KEY AUTOINCREMENT, "
            "nama_bursa VARCHAR(100) NOT NULL, "
            "mic_code VARCHAR(10), "
            "id_regulator INTEGER NOT NULL REFERENCES regulator(id_regulator) ON DELETE RESTRICT, "
            "CONSTRAINT uq_bursa_nama UNIQUE (nama_bursa)"
            ")"
        )
    )
    conn.execute(text("CREATE INDEX ix_bursa_regulator ON bursa_efek (id_regulator)"))

    # Recreate sektor
    conn.execute(
        text(
            "CREATE TABLE sektor ("
            "id_sektor INTEGER PRIMARY KEY AUTOINCREMENT, "
            "nama_sektor VARCHAR(100) NOT NULL UNIQUE"
            ")"
        )
    )

    # Recreate emiten
    conn.execute(
        text(
            "CREATE TABLE emiten ("
            "id_emiten INTEGER PRIMARY KEY AUTOINCREMENT, "
            "kode_ticker VARCHAR(30) NOT NULL UNIQUE, "
            "nama_perusahaan VARCHAR(200), "
            "id_bursa INTEGER NOT NULL REFERENCES bursa_efek(id_bursa) ON DELETE RESTRICT, "
            "id_sektor INTEGER REFERENCES sektor(id_sektor) ON DELETE SET NULL, "
            "subsektor VARCHAR(100), "
            "is_active BOOLEAN DEFAULT 1, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
    )
    conn.execute(text("CREATE INDEX ix_emiten_bursa ON emiten (id_bursa)"))
    conn.execute(text("CREATE INDEX ix_emiten_sektor ON emiten (id_sektor)"))

    # Recreate instrumen
    conn.execute(
        text(
            "CREATE TABLE instrumen ("
            "id_instrumen INTEGER PRIMARY KEY AUTOINCREMENT, "
            "id_emiten INTEGER NOT NULL REFERENCES emiten(id_emiten) ON DELETE CASCADE, "
            "jenis_instrumen VARCHAR(30) NOT NULL, "
            "asset_class VARCHAR(30) NOT NULL DEFAULT 'EQUITY_INDIVIDUAL', "
            "base_currency VARCHAR(3) NOT NULL DEFAULT 'IDR', "
            "is_active BOOLEAN DEFAULT 1, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
    )
    conn.execute(text("CREATE INDEX ix_instrumen_emiten ON instrumen (id_emiten)"))
    conn.execute(text("CREATE INDEX ix_instrumen_jenis ON instrumen (jenis_instrumen)"))

    # Recreate indeks_pasar
    conn.execute(
        text(
            "CREATE TABLE indeks_pasar ("
            "id_indeks INTEGER PRIMARY KEY AUTOINCREMENT, "
            "kode_indeks VARCHAR(30) NOT NULL UNIQUE, "
            "nama_indeks VARCHAR(200), "
            "id_bursa INTEGER REFERENCES bursa_efek(id_bursa) ON DELETE SET NULL, "
            "jenis_indeks VARCHAR(30), "
            "asset_class VARCHAR(30) NOT NULL DEFAULT 'INDEX_COMPOSITE', "
            "is_active BOOLEAN DEFAULT 1, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
    )
    conn.execute(text("CREATE INDEX ix_indeks_bursa ON indeks_pasar (id_bursa)"))
    conn.execute(text("CREATE INDEX ix_indeks_jenis ON indeks_pasar (jenis_indeks)"))

    # Recreate broker_bursa with FK
    conn.execute(
        text(
            "CREATE TABLE broker_bursa ("
            "id_broker INTEGER NOT NULL REFERENCES broker(id_broker) ON DELETE CASCADE, "
            "id_bursa INTEGER NOT NULL REFERENCES bursa_efek(id_bursa) ON DELETE CASCADE, "
            "PRIMARY KEY (id_broker, id_bursa)"
            ")"
        )
    )

    # Recreate transaksi_investor
    conn.execute(
        text(
            "CREATE TABLE transaksi_investor ("
            "id_transaksi INTEGER PRIMARY KEY AUTOINCREMENT, "
            "tanggal_transaksi DATE NOT NULL, "
            "id_instrumen INTEGER NOT NULL REFERENCES instrumen(id_instrumen) ON DELETE RESTRICT, "
            "id_broker INTEGER REFERENCES broker(id_broker) ON DELETE SET NULL, "
            "tipe_transaksi VARCHAR(20) NOT NULL, "
            "jumlah_lot INTEGER NOT NULL DEFAULT 0, "
            "harga_per_saham NUMERIC(20, 4) NOT NULL DEFAULT 0, "
            "biaya_broker NUMERIC(20, 4) DEFAULT 0, "
            "pajak_pph_final NUMERIC(20, 4) DEFAULT 0, "
            "status_eksekusi VARCHAR(20) NOT NULL DEFAULT 'PENDING', "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
    )
    conn.execute(text("CREATE INDEX ix_transaksi_tanggal ON transaksi_investor (tanggal_transaksi)"))
    conn.execute(text("CREATE INDEX ix_transaksi_instrumen ON transaksi_investor (id_instrumen)"))
    conn.execute(text("CREATE INDEX ix_transaksi_broker ON transaksi_investor (id_broker)"))

    # Recreate fx_rates
    conn.execute(
        text(
            "CREATE TABLE fx_rates ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "base_currency VARCHAR(3) NOT NULL, "
            "quote_currency VARCHAR(3) NOT NULL DEFAULT 'IDR', "
            "date DATE NOT NULL, "
            "rate NUMERIC(20, 8) NOT NULL, "
            "source VARCHAR(50) DEFAULT 'yahoo_finance', "
            "created_at DATETIME, "
            "UNIQUE (base_currency, quote_currency, date)"
            ")"
        )
    )
