"""Add instrument_master columns: listed_shares, tradeable_shares,
delisting_risk_score, delisting_risk_reason, former_ticker, former_name.

These columns were added to the ORM model but missing from migrations,
causing test DB schema mismatch.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "instrument_master",
        sa.Column("listed_shares", sa.Numeric(20, 2), nullable=True),
    )
    op.add_column(
        "instrument_master",
        sa.Column("tradeable_shares", sa.Numeric(20, 2), nullable=True),
    )
    op.add_column(
        "instrument_master",
        sa.Column("delisting_risk_score", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "instrument_master",
        sa.Column("delisting_risk_reason", sa.Text, nullable=True),
    )
    op.add_column(
        "instrument_master",
        sa.Column("former_ticker", sa.String(30), nullable=True),
    )
    op.add_column(
        "instrument_master",
        sa.Column("former_name", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instrument_master", "former_name")
    op.drop_column("instrument_master", "former_ticker")
    op.drop_column("instrument_master", "delisting_risk_reason")
    op.drop_column("instrument_master", "delisting_risk_score")
    op.drop_column("instrument_master", "tradeable_shares")
    op.drop_column("instrument_master", "listed_shares")
