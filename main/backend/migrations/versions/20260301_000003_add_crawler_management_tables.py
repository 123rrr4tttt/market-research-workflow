"""add crawler management tables

Revision ID: 20260301_000003
Revises: 20260301_000002
Create Date: 2026-03-01 11:40:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from migrations.util import table_exists


revision = "20260301_000003"
down_revision = "20260301_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    if not table_exists(conn, "crawler_projects", schema="public"):
        op.create_table(
            "crawler_projects",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("project_key", sa.String(length=64), nullable=False, unique=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source_type", sa.String(length=32), nullable=False, server_default="manual"),
            sa.Column("source_uri", sa.Text(), nullable=True),
            sa.Column("provider", sa.String(length=64), nullable=False, server_default="scrapyd"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="imported"),
            sa.Column("current_version", sa.String(length=128), nullable=True),
            sa.Column("deployed_version", sa.String(length=128), nullable=True),
            sa.Column("previous_version", sa.String(length=128), nullable=True),
            sa.Column("import_payload", pg.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("analysis_plan", pg.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            schema="public",
        )
        op.create_unique_constraint(
            "uq_crawler_projects_project_key",
            "crawler_projects",
            ["project_key"],
            schema="public",
        )

    if not table_exists(conn, "crawler_deploy_runs", schema="public"):
        op.create_table(
            "crawler_deploy_runs",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("crawler_project_id", sa.BigInteger(), nullable=False),
            sa.Column("action", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
            sa.Column("requested_version", sa.String(length=128), nullable=True),
            sa.Column("from_version", sa.String(length=128), nullable=True),
            sa.Column("to_version", sa.String(length=128), nullable=True),
            sa.Column("planner_mode", sa.String(length=16), nullable=False, server_default="heuristic"),
            sa.Column("plan", pg.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("external_provider", sa.String(length=64), nullable=True),
            sa.Column("external_job_id", sa.String(length=255), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["crawler_project_id"],
                ["public.crawler_projects.id"],
                ondelete="CASCADE",
                name="fk_crawler_deploy_runs_project_id",
            ),
            schema="public",
        )
        op.create_index(
            "ix_crawler_deploy_runs_project_created_at",
            "crawler_deploy_runs",
            ["crawler_project_id", "created_at"],
            unique=False,
            schema="public",
        )


def downgrade() -> None:
    op.drop_index(
        "ix_crawler_deploy_runs_project_created_at",
        table_name="crawler_deploy_runs",
        schema="public",
    )
    op.drop_table("crawler_deploy_runs", schema="public")

    op.drop_constraint(
        "uq_crawler_projects_project_key",
        "crawler_projects",
        schema="public",
        type_="unique",
    )
    op.drop_table("crawler_projects", schema="public")
