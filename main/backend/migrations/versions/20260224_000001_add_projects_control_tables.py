"""add projects control tables

Revision ID: 20260224_000001
Revises: 20250224_000001
Create Date: 2026-02-24 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260224_000001"
down_revision = "20250224_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_key", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("schema_name", sa.String(128), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_projects_project_key", "projects", ["project_key"])
    op.create_unique_constraint("uq_projects_schema_name", "projects", ["schema_name"])

    op.create_table(
        "project_sync_state",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_key", sa.String(64), nullable=False),
        sa.Column("object_name", sa.String(64), nullable=False),
        sa.Column("cursor_value", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_project_sync_state_object",
        "project_sync_state",
        ["project_key", "object_name"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_project_sync_state_object", "project_sync_state", type_="unique")
    op.drop_table("project_sync_state")

    op.drop_constraint("uq_projects_schema_name", "projects", type_="unique")
    op.drop_constraint("uq_projects_project_key", "projects", type_="unique")
    op.drop_table("projects")
