"""Install tables needed to read previously saved workflow runs and events.

Revision ID: 20261119_000001
Revises: 20261009_000002

Earlier installations could create these tables at application startup.
Preserve those tables and their rows; new installations get the same read
surface from the packaged migrations instead.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "20261119_000001"
down_revision = "20261009_000002"
branch_labels = None
depends_on = None


def _tables() -> tuple[sa.Table, sa.Table]:
    metadata = sa.MetaData(schema="public")
    runs = sa.Table(
        "workflow_graph_runs",
        metadata,
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("workflow_id", sa.String(128)),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("node_statuses", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("results", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", name="uq_workflow_graph_runs_run_id"),
    )
    events = sa.Table(
        "workflow_graph_events",
        metadata,
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), nullable=False, index=True),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("node_id", sa.String(128)),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "seq", name="uq_workflow_graph_events_run_seq"),
    )
    return runs, events


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = set(inspector.get_table_names(schema="public"))
    missing_tables = []
    for table in _tables():
        if table.name not in existing_tables:
            if inspector.has_table(table.name, schema="public"):
                raise RuntimeError(f"WORKFLOW_HISTORY_RELATION_CONFLICT public.{table.name}")  # noqa: TRY003
            missing_tables.append(table)
            continue
        columns = {column["name"] for column in inspector.get_columns(table.name, schema="public")}
        missing_columns = sorted(set(table.columns.keys()) - columns)
        if missing_columns:
            raise RuntimeError(  # noqa: TRY003
                f"WORKFLOW_HISTORY_COLUMNS_MISSING public.{table.name}: {','.join(missing_columns)}"
            )

    for table in missing_tables:
        table.create(connection)


def downgrade() -> None:
    # No reliable distinction exists between tables created here and ones
    # predating the repair. Preserve all saved runs when moving the revision.
    return None
