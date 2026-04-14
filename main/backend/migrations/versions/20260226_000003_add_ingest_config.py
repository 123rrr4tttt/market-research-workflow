"""add ingest_config

Revision ID: 20260226_000003
Revises: 20260226_000002
Create Date: 2026-02-26 15:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from migrations.util import table_exists


revision = "20260226_000003"
down_revision = "20260226_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not table_exists(conn, "ingest_config"):
        op.create_table(
            "ingest_config",
            sa.Column("project_key", sa.String(length=64), nullable=False),
            sa.Column("config_key", sa.String(length=128), nullable=False),
            sa.Column("config_type", sa.String(length=64), nullable=False),
            sa.Column("payload", pg.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("project_key", "config_key"),
            schema="public",
        )


def downgrade() -> None:
    op.drop_table("ingest_config", schema="public")
