"""add resource pool capture config

Revision ID: 20260226_000002
Revises: 20260226_000001
Create Date: 2026-02-26 14:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = "20260226_000002"
down_revision = "20260226_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_pool_capture_config",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_key", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="project"),
        sa.Column("job_types", pg.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="public",
    )
    op.create_unique_constraint(
        "uq_resource_pool_capture_config_project",
        "resource_pool_capture_config",
        ["project_key"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_resource_pool_capture_config_project",
        "resource_pool_capture_config",
        schema="public",
        type_="unique",
    )
    op.drop_table("resource_pool_capture_config", schema="public")
