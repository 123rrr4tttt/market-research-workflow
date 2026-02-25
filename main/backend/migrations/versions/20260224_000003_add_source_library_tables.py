"""add source library tables

Revision ID: 20260224_000003
Revises: 20260224_000002
Create Date: 2026-02-24 22:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


# revision identifiers, used by Alembic.
revision = "20260224_000003"
down_revision = "20260224_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Shared library tables in public schema (control plane).
    op.create_table(
        "shared_ingest_channels",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("channel_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("credential_refs", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("default_params", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("param_schema", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extends_channel_key", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("extra", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_shared_ingest_channel_key", "shared_ingest_channels", ["channel_key"])

    op.create_table(
        "shared_source_library_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("item_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("channel_key", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("params", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("schedule", sa.String(length=128), nullable=True),
        sa.Column("extends_item_key", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("extra", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_shared_source_library_item_key", "shared_source_library_items", ["item_key"])

    # Tenant tables (created in current schema; project bootstrap logic will ensure per-project schemas).
    op.create_table(
        "ingest_channels",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("channel_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("credential_refs", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("default_params", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("param_schema", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extends_channel_key", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("extra", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_ingest_channel_key", "ingest_channels", ["channel_key"])

    op.create_table(
        "source_library_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("item_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("channel_key", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("params", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("schedule", sa.String(length=128), nullable=True),
        sa.Column("extends_item_key", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("extra", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_source_library_item_key", "source_library_items", ["item_key"])


def downgrade() -> None:
    op.drop_constraint("uq_source_library_item_key", "source_library_items", type_="unique")
    op.drop_table("source_library_items")

    op.drop_constraint("uq_ingest_channel_key", "ingest_channels", type_="unique")
    op.drop_table("ingest_channels")

    op.drop_constraint("uq_shared_source_library_item_key", "shared_source_library_items", type_="unique")
    op.drop_table("shared_source_library_items")

    op.drop_constraint("uq_shared_ingest_channel_key", "shared_ingest_channels", type_="unique")
    op.drop_table("shared_ingest_channels")

