"""Add satellite_ticker_locations table for DB-driven ticker→location mapping.

Enables global satellite data fetching: any ticker can be mapped to
any geographic location. Falls back to sector-based defaults when
no explicit ticker mapping exists.

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "satellite_ticker_locations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(30), nullable=False, index=True),
        sa.Column("location_name", sa.String(100), nullable=False),
        sa.Column("lat", sa.Numeric(10, 6), nullable=False),
        sa.Column("lon", sa.Numeric(10, 6), nullable=False),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("metrics", sa.Text, nullable=False,
                  server_default="NDVI,T2M,PRECTOTCORR,RH2M,ALLSKY_SFC_SW_DWN"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("ticker", "location_name", name="uq_sattickerloc_pk"),
    )
    op.create_index("ix_sattickerloc_ticker", "satellite_ticker_locations", ["ticker"])
    op.create_index("ix_sattickerloc_sector", "satellite_ticker_locations", ["sector"])


def downgrade() -> None:
    op.drop_table("satellite_ticker_locations")
