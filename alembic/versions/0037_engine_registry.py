"""engine_registry table — catalog all engines/modules with properties.

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Table may already exist if created manually before migration
    conn = op.get_bind()
    exists = conn.execute(
        sa.text("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'engine_registry')")
    ).scalar()
    if exists:
        # Just stamp the version
        return
    op.create_table(
        "engine_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engine_name", sa.String(100), nullable=False, unique=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("module_path", sa.String(255), nullable=False),
        sa.Column("class_name", sa.String(100), nullable=True),
        sa.Column("method_name", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_data_sources", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("output_tables", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("dependencies", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("is_implemented", sa.Boolean(), server_default="true"),
        sa.Column("needs_gpu", sa.Boolean(), server_default="false"),
        sa.Column("needs_network", sa.Boolean(), server_default="false"),
        sa.Column("trigger_event", sa.String(100), nullable=True),
        sa.Column("trigger_phase", sa.String(50), nullable=True),
        sa.Column("trigger_frequency", sa.String(50), nullable=True),
        sa.Column("last_dry_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_dry_run_status", sa.String(20), nullable=True),
        sa.Column("last_dry_run_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    if not exists:
        op.create_index("ix_engine_registry_category", "engine_registry", ["category"])
        op.create_index("ix_engine_registry_trigger_phase", "engine_registry", ["trigger_phase"])


def downgrade() -> None:
    op.drop_index("ix_engine_registry_trigger_phase", table_name="engine_registry")
    op.drop_index("ix_engine_registry_category", table_name="engine_registry")
    op.drop_table("engine_registry")
