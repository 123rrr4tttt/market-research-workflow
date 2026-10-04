"""Persist versioned project retrieval methods, previews and runs.

Revision ID: 20260926_000001
Revises: 20260924_000001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260926_000001"
down_revision = "20260924_000001"
branch_labels = None
depends_on = None


def _schemas(conn: sa.Connection) -> tuple[str, ...]:
    rows = conn.execute(sa.text(
        "SELECT DISTINCT schema_name FROM public.projects WHERE schema_name IS NOT NULL "
        "AND schema_name NOT IN ('public', 'pg_catalog', 'information_schema')"
    )).scalars()
    return tuple(str(row) for row in rows if row)


def upgrade() -> None:
    for schema in _schemas(op.get_bind()):
        op.create_table(
            "project_retrieval_modes",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("project_key", sa.String(128), nullable=False),
            sa.Column("mode_id", sa.String(128), nullable=False),
            sa.Column("version", sa.String(128), nullable=False),
            sa.Column("source_revision", sa.String(64), nullable=False),
            sa.Column("snapshot", JSONB(), nullable=False),
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("project_key", "mode_id", "version", name="uq_project_retrieval_mode_version"),
            schema=schema,
        )
        op.create_index("uq_project_retrieval_mode_current", "project_retrieval_modes", ["project_key"],
                        unique=True, schema=schema, postgresql_where=sa.text("is_current IS TRUE"))
        op.create_table(
            "project_retrieval_plans",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("project_key", sa.String(128), nullable=False),
            sa.Column("plan_id", sa.String(64), nullable=False),
            sa.Column("mode_id", sa.String(128), nullable=False),
            sa.Column("mode_version", sa.String(128), nullable=False),
            sa.Column("payload", JSONB(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("project_key", "plan_id", name="uq_project_retrieval_plan"),
            schema=schema,
        )
        op.create_table(
            "project_retrieval_runs",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("project_key", sa.String(128), nullable=False),
            sa.Column("run_id", sa.String(64), nullable=False),
            sa.Column("plan_id", sa.String(64), nullable=False),
            sa.Column("idempotency_key", sa.String(255), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("phase", sa.String(64), nullable=False),
            sa.Column("counts", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("errors", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("receipt", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("project_key", "run_id", name="uq_project_retrieval_run"),
            sa.UniqueConstraint("project_key", "idempotency_key", name="uq_project_retrieval_idempotency"),
            schema=schema,
        )


def downgrade() -> None:
    for schema in reversed(_schemas(op.get_bind())):
        op.drop_table("project_retrieval_runs", schema=schema)
        op.drop_table("project_retrieval_plans", schema=schema)
        op.drop_index("uq_project_retrieval_mode_current", table_name="project_retrieval_modes", schema=schema)
        op.drop_table("project_retrieval_modes", schema=schema)
