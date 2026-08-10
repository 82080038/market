"""Relational hierarchy tables: regulator, bursa_efek, sektor, emiten, instrumen,
indeks_pasar, broker, broker_bursa, transaksi_investor, app_notifications.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-10

Changes:
1. Create 9 new relational tables with strict FK hierarchy:
   Negara → Regulator → Bursa → Sektor → Emiten → Instrumen
   + Indeks Pasar, Broker, Broker-Bursa, Transaksi Investor
2. Create app_notifications table (formalize ad-hoc CREATE TABLE IF NOT EXISTS)
3. Add indexes on all FK columns and unique constraints
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. regulator — top of hierarchy (Negara → Regulator)
    op.create_table(
        "regulator",
        sa.Column("id_regulator", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("nama_regulator", sa.String(100), nullable=False),
        sa.Column("negara", sa.String(50), nullable=False),
        sa.UniqueConstraint("nama_regulator", "negara", name="uq_regulator_nama_negara"),
    )

    # 2. bursa_efek — regulated by regulator
    op.create_table(
        "bursa_efek",
        sa.Column("id_bursa", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("nama_bursa", sa.String(100), nullable=False),
        sa.Column("mic_code", sa.String(10), nullable=True),
        sa.Column("id_regulator", sa.Integer,
                  sa.ForeignKey("regulator.id_regulator", ondelete="RESTRICT"),
                  nullable=False),
        sa.UniqueConstraint("nama_bursa", name="uq_bursa_nama"),
    )
    op.create_index("ix_bursa_regulator", "bursa_efek", ["id_regulator"])

    # 3. sektor — independent lookup
    op.create_table(
        "sektor",
        sa.Column("id_sektor", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("nama_sektor", sa.String(100), nullable=False, unique=True),
    )

    # 4. emiten — listed on bursa, belongs to sektor
    op.create_table(
        "emiten",
        sa.Column("id_emiten", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("kode_ticker", sa.String(30), nullable=False, unique=True),
        sa.Column("nama_perusahaan", sa.String(200), nullable=True),
        sa.Column("id_bursa", sa.Integer,
                  sa.ForeignKey("bursa_efek.id_bursa", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("id_sektor", sa.Integer,
                  sa.ForeignKey("sektor.id_sektor", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("subsektor", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_emiten_bursa", "emiten", ["id_bursa"])
    op.create_index("ix_emiten_sektor", "emiten", ["id_sektor"])

    # 5. instrumen — instrument issued by emiten
    op.create_table(
        "instrumen",
        sa.Column("id_instrumen", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("id_emiten", sa.Integer,
                  sa.ForeignKey("emiten.id_emiten", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("jenis_instrumen", sa.String(30), nullable=False),
        sa.Column("asset_class", sa.String(30), nullable=False, default="EQUITY_INDIVIDUAL"),
        sa.Column("base_currency", sa.String(3), nullable=False, default="IDR"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_instrumen_emiten", "instrumen", ["id_emiten"])
    op.create_index("ix_instrumen_jenis", "instrumen", ["jenis_instrumen"])

    # 6. indeks_pasar — market index, belongs to bursa
    op.create_table(
        "indeks_pasar",
        sa.Column("id_indeks", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("kode_indeks", sa.String(30), nullable=False, unique=True),
        sa.Column("nama_indeks", sa.String(200), nullable=True),
        sa.Column("id_bursa", sa.Integer,
                  sa.ForeignKey("bursa_efek.id_bursa", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("jenis_indeks", sa.String(30), nullable=True),
        sa.Column("asset_class", sa.String(30), nullable=False, default="INDEX_COMPOSITE"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_indeks_bursa", "indeks_pasar", ["id_bursa"])
    op.create_index("ix_indeks_jenis", "indeks_pasar", ["jenis_indeks"])

    # 7. broker — independent lookup
    op.create_table(
        "broker",
        sa.Column("id_broker", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("nama_broker", sa.String(200), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # 8. broker_bursa — many-to-many junction
    op.create_table(
        "broker_bursa",
        sa.Column("id_broker", sa.Integer,
                  sa.ForeignKey("broker.id_broker", ondelete="CASCADE"),
                  nullable=False, primary_key=True),
        sa.Column("id_bursa", sa.Integer,
                  sa.ForeignKey("bursa_efek.id_bursa", ondelete="CASCADE"),
                  nullable=False, primary_key=True),
    )

    # 9. transaksi_investor — transaction records
    op.create_table(
        "transaksi_investor",
        sa.Column("id_transaksi", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tanggal_transaksi", sa.Date, nullable=False),
        sa.Column("id_instrumen", sa.Integer,
                  sa.ForeignKey("instrumen.id_instrumen", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("id_broker", sa.Integer,
                  sa.ForeignKey("broker.id_broker", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("tipe_transaksi", sa.String(20), nullable=False),
        sa.Column("jumlah_lot", sa.Integer, nullable=False, default=0),
        sa.Column("harga_per_saham", sa.Numeric(20, 4), nullable=False, default=0),
        sa.Column("biaya_broker", sa.Numeric(20, 4), nullable=True, default=0),
        sa.Column("pajak_pph_final", sa.Numeric(20, 4), nullable=True, default=0),
        sa.Column("status_eksekusi", sa.String(20), nullable=False, default="PENDING"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_transaksi_tanggal", "transaksi_investor", ["tanggal_transaksi"])
    op.create_index("ix_transaksi_instrumen", "transaksi_investor", ["id_instrumen"])
    op.create_index("ix_transaksi_broker", "transaksi_investor", ["id_broker"])

    # 10. app_notifications — formalize ad-hoc table from daily_signal_cron.py
    op.create_table(
        "app_notifications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body_json", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="UNREAD"),
    )
    op.create_index("ix_app_notif_status", "app_notifications", ["status", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_app_notif_status", table_name="app_notifications")
    op.drop_table("app_notifications")

    op.drop_index("ix_transaksi_broker", table_name="transaksi_investor")
    op.drop_index("ix_transaksi_instrumen", table_name="transaksi_investor")
    op.drop_index("ix_transaksi_tanggal", table_name="transaksi_investor")
    op.drop_table("transaksi_investor")

    op.drop_table("broker_bursa")

    op.drop_table("broker")

    op.drop_index("ix_indeks_jenis", table_name="indeks_pasar")
    op.drop_index("ix_indeks_bursa", table_name="indeks_pasar")
    op.drop_table("indeks_pasar")

    op.drop_index("ix_instrumen_jenis", table_name="instrumen")
    op.drop_index("ix_instrumen_emiten", table_name="instrumen")
    op.drop_table("instrumen")

    op.drop_index("ix_emiten_sektor", table_name="emiten")
    op.drop_index("ix_emiten_bursa", table_name="emiten")
    op.drop_table("emiten")

    op.drop_table("sektor")

    op.drop_index("ix_bursa_regulator", table_name="bursa_efek")
    op.drop_table("bursa_efek")

    op.drop_table("regulator")
