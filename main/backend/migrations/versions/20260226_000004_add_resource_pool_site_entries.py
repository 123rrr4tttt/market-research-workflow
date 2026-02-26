"""add resource pool site entries

Revision ID: 20260226_000004
Revises: 20260226_000003
Create Date: 2026-02-26 16:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = "20260226_000004"
down_revision = "20260226_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Shared table (总库) in public schema.
    op.create_table(
        "shared_resource_pool_site_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("site_url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("entry_type", sa.String(length=32), nullable=False, server_default="domain_root"),
        sa.Column("template", sa.Text(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("capabilities", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("source_ref", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("extra", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="public",
    )
    op.create_unique_constraint(
        "uq_shared_resource_pool_site_entries_site_url",
        "shared_resource_pool_site_entries",
        ["site_url"],
        schema="public",
    )

    # Tenant table (子项目库) in project schema.
    op.create_table(
        "resource_pool_site_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("site_url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("entry_type", sa.String(length=32), nullable=False, server_default="domain_root"),
        sa.Column("template", sa.Text(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("capabilities", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("source_ref", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("project_key", sa.String(length=64), nullable=True),
        sa.Column("extra", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_resource_pool_site_entries_site_url",
        "resource_pool_site_entries",
        ["site_url"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_resource_pool_site_entries_site_url",
        "resource_pool_site_entries",
        type_="unique",
    )
    op.drop_table("resource_pool_site_entries")

    op.drop_constraint(
        "uq_shared_resource_pool_site_entries_site_url",
        "shared_resource_pool_site_entries",
        schema="public",
        type_="unique",
    )
    op.drop_table("shared_resource_pool_site_entries", schema="public")

