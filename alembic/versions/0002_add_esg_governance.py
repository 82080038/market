"""Add esg_scores and corporate_governance tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "esg_scores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("kode", sa.String(30), nullable=False, index=True),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("rating_agency", sa.String(50), nullable=False),
        sa.Column("rating", sa.String(30), nullable=True),
        sa.Column("score", sa.Numeric(10, 4), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("kode", "year", "rating_agency", name="uq_esg_pk"),
    )

    op.create_table(
        "corporate_governance",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("kode", sa.String(30), nullable=False, index=True),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("board_commissioners", sa.Numeric(10, 2), nullable=True),
        sa.Column("independent_commissioners", sa.Numeric(10, 2), nullable=True),
        sa.Column("board_directors", sa.Numeric(10, 2), nullable=True),
        sa.Column("audit_committee_meetings", sa.Numeric(10, 2), nullable=True),
        sa.Column("gcg_score", sa.String(50), nullable=True),
        sa.Column("acgs_score", sa.String(50), nullable=True),
        sa.Column("has_whistleblowing", sa.Boolean, nullable=True),
        sa.Column("has_risk_committee", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("kode", "year", name="uq_cg_pk"),
    )


def downgrade() -> None:
    op.drop_table("corporate_governance")
    op.drop_table("esg_scores")
