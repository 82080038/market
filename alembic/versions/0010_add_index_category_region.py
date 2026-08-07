"""Add index_category and region columns to instrument_master.

Enables AI/ML/LLM to distinguish index types (sectoral, composite, global,
volatility, rate, currency, sharia, esg, factor, board) and geographic
region (ID, US, EU, AS, CN, GLOBAL).

Also standardizes sector names for equities (merges duplicates).

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-07
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "instrument_master",
        sa.Column("index_category", sa.String(30), nullable=True),
    )
    op.add_column(
        "instrument_master",
        sa.Column("region", sa.String(10), nullable=True),
    )

    # Standardize sector names — merge duplicates
    op.execute(
        "UPDATE instrument_master SET sector = 'Consumer Cyclicals' "
        "WHERE sector = 'Consumer Cyclical'"
    )
    op.execute(
        "UPDATE instrument_master SET sector = 'Financials' "
        "WHERE sector = 'Financial Services'"
    )
    op.execute(
        "UPDATE instrument_master SET sector = 'Properties & Real Estate' "
        "WHERE sector = 'Real Estate'"
    )


def downgrade() -> None:
    op.drop_column("instrument_master", "region")
    op.drop_column("instrument_master", "index_category")
