"""Add data source metadata + delisting/merger info to instruments.

Database-as-source-of-truth: instruments must know WHERE to fetch data
(not just Yahoo Finance — also idx.co.id, Pirana API, Sectors.app, etc.)
and WHY a ticker is delisted (pailit, suspensi >24bln, merger, go-private).

Columns added:
  - data_source_type: yahoo_finance, idx_co_id, pirana_api, sectors_api, manual
  - data_source_url: endpoint URL for fetching (nullable, for API sources)
  - delisting_reason: text — why the instrument was delisted
  - merged_to_ticker: if company merged, the successor ticker

Also marks known delisted stocks with dates and reasons based on
BEI announcements (Pasardana.id sources, verified Aug 2026):
  - Jul 21, 2025 delisting (10 stocks): MAMI, KPAS, JKSW, KRAH, HDTX, PRAS, KPAL, NIPS, FORZ, MYRX
  - Nov 10, 2026 delisting effective (18 stocks): COWL, MTRA, SRIL, TOYS, SBAT, TDPM, TELE,
    LCGP, SUGI, MABA, LMAS, SKYB, ENVY, GOLL, PLAS, TRIL, UNIT, DUCK

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add data source metadata columns
    op.add_column("instruments", sa.Column("data_source_type", sa.String(30), nullable=True))
    op.add_column("instruments", sa.Column("data_source_url", sa.String(500), nullable=True))
    op.add_column("instruments", sa.Column("delisting_reason", sa.Text, nullable=True))
    op.add_column("instruments", sa.Column("merged_to_ticker", sa.String(30), nullable=True))

    op.create_index("idx_instruments_source_type", "instruments", ["data_source_type"])

    # 2. Seed data_source_type based on data_layer
    # idx_equity: primary = yahoo_finance, fallback = idx_co_id
    op.execute("""
        UPDATE instruments SET data_source_type = 'yahoo_finance'
        WHERE data_layer IN ('idx_equity', 'global_index', 'commodity', 'fx', 'etf', 'volatility', 'fund')
          AND data_source_type IS NULL;
    """)
    # idx_index: yahoo_finance doesn't have most IDX indices → use sectors_api or idx_co_id
    op.execute("""
        UPDATE instruments SET data_source_type = 'idx_co_id'
        WHERE data_layer = 'idx_index' AND data_source_type IS NULL;
    """)
    # macro_rate: yahoo_finance
    op.execute("""
        UPDATE instruments SET data_source_type = 'yahoo_finance'
        WHERE data_layer = 'macro_rate' AND data_source_type IS NULL;
    """)

    # 3. Mark delisted stocks — Jul 21, 2025 delisting (BEI Peng-DEL 07/2025)
    op.execute("""
        UPDATE instruments SET
            is_active = false,
            delisting_date = '2025-07-21',
            delisting_reason = 'Delisting BEI 21 Jul 2025 — suspensi >24 bulan',
            fetch_status = 'PAUSED'
        WHERE ticker IN ('MAMI.JK', 'KPAS.JK', 'JKSW.JK', 'KRAH.JK', 'HDTX.JK',
                         'PRAS.JK', 'KPAL.JK', 'NIPS.JK', 'FORZ.JK', 'MYRX.JK');
    """)

    # 4. Mark delisted stocks — effective Nov 10, 2026 (announced Apr 10, 2026)
    # Pailit: COWL, MTRA, SRIL, TOYS, SBAT, TDPM, TELE
    op.execute("""
        UPDATE instruments SET
            delisting_date = '2026-11-10',
            delisting_reason = 'Delisting BEI efektif 10 Nov 2026 — dinyatakan pailit',
            fetch_status = 'PAUSED'
        WHERE ticker IN ('COWL.JK', 'MTRA.JK', 'SRIL.JK', 'TOYS.JK', 'SBAT.JK', 'TDPM.JK', 'TELE.JK');
    """)
    # Suspensi >50 bulan: LCGP, SUGI, MABA, LMAS, SKYB, ENVY, GOLL, PLAS, TRIL, UNIT, DUCK
    op.execute("""
        UPDATE instruments SET
            delisting_date = '2026-11-10',
            delisting_reason = 'Delisting BEI efektif 10 Nov 2026 — suspensi >50 bulan',
            fetch_status = 'PAUSED'
        WHERE ticker IN ('LCGP.JK', 'SUGI.JK', 'MABA.JK', 'LMAS.JK', 'SKYB.JK',
                         'ENVY.JK', 'GOLL.JK', 'PLAS.JK', 'TRIL.JK', 'UNIT.JK', 'DUCK.JK');
    """)

    # 5. Mark potentially delisted stocks (70 from Dec 2025 BEI announcement)
    # These are still active but at risk — set fetch_status to STALE with a note
    op.execute("""
        UPDATE instruments SET
            delisting_reason = 'Potensi delisting — BEI Peng-00003/BEI.PLP/12-2025 (suspensi >6 bln)',
            fetch_status = CASE WHEN fetch_status = 'OK' THEN 'STALE' ELSE fetch_status END
        WHERE ticker IN (
            'ALMI.JK', 'ARMY.JK', 'ARTI.JK', 'BIKA.JK', 'BOSS.JK', 'BTEL.JK',
            'CBMF.JK', 'CPRI.JK', 'DEAL.JK', 'ETWA.JK', 'GAMA.JK',
            'HKMU.JK', 'HOME.JK', 'HOTL.JK', 'IIKP.JK', 'INAF.JK',
            'IPPE.JK', 'JSKY.JK', 'KAYU.JK', 'KBRI.JK', 'MAGP.JK',
            'MKNT.JK', 'NUSA.JK', 'POSA.JK', 'PPRO.JK', 'PURE.JK',
            'RIMO.JK', 'SIMA.JK', 'SMRU.JK', 'TECH.JK', 'TOPS.JK',
            'TRAM.JK', 'TRIO.JK', 'WMPP.JK', 'WSKT.JK',
            'POLL.JK', 'POOL.JK', 'MTSM.JK', 'MYTX.JK', 'FASW.JK',
            'LMSH.JK', 'MFMI.JK', 'PLIN.JK', 'PTMR.JK', 'RSGK.JK',
            'SMCB.JK', 'SUPR.JK', 'TGUK.JK', 'TGRA.JK', 'WICO.JK',
            'WIKA.JK', 'BEBS.JK'
        );
    """)

    # 6. Set data_source_url for idx_co_id instruments (IDX official API)
    op.execute("""
        UPDATE instruments SET data_source_url = 'https://idx.co.id/umbraco/Surface/TradingSummary/GetStockSummary'
        WHERE data_source_type = 'idx_co_id';
    """)

    # 7. For IDX indices that ARE available on yahoo_finance (^JKSE, ^JKLQ45), override
    op.execute("""
        UPDATE instruments SET data_source_type = 'yahoo_finance', data_source_url = NULL
        WHERE ticker IN ('^JKSE', '^JKLQ45') AND data_layer = 'idx_index';
    """)


def downgrade() -> None:
    op.drop_index("idx_instruments_source_type", table_name="instruments")
    op.drop_column("instruments", "merged_to_ticker")
    op.drop_column("instruments", "delisting_reason")
    op.drop_column("instruments", "data_source_url")
    op.drop_column("instruments", "data_source_type")
