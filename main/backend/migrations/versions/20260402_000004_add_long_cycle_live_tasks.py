"""add long-cycle live scheduler task table

Revision ID: 20260402_000004
Revises: 20260402_000003
Create Date: 2026-04-02 13:10:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260402_000004"
down_revision = "20260402_000003"
branch_labels = None
depends_on = None


def _quote_ident(raw: str) -> str:
    return '"' + raw.replace('"', '""') + '"'


def _target_schemas(conn) -> list[str]:
    rows = conn.execute(
        sa.text(
            """
            SELECT DISTINCT table_schema
            FROM information_schema.tables
            WHERE table_name IN ('documents', 'writing_documents', 'typed_knowledge_objects')
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema
            """
        )
    ).fetchall()
    schemas = [str(row[0]) for row in rows if row and row[0]]
    return schemas or ["public"]


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        quoted = _quote_ident(schema)
        op.execute(
            sa.text(
                f"""
                CREATE TABLE IF NOT EXISTS {quoted}.long_cycle_live_tasks (
                    id BIGSERIAL PRIMARY KEY,
                    project_key VARCHAR(64) NOT NULL,
                    task_key VARCHAR(96) NOT NULL,
                    queue_item_key VARCHAR(96) NOT NULL,
                    dispatch_key VARCHAR(96) NOT NULL,
                    dispatch_ref VARCHAR(256) NOT NULL,
                    scheduler_ref VARCHAR(256) NOT NULL,
                    persistent_ref VARCHAR(256) NOT NULL,
                    queue_name VARCHAR(128) NOT NULL,
                    worker_task_name VARCHAR(128) NOT NULL,
                    selected_window VARCHAR(32) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    output_ref TEXT,
                    live_dispatch BOOLEAN NOT NULL DEFAULT false,
                    live_enqueue BOOLEAN NOT NULL DEFAULT false,
                    live_db_write BOOLEAN NOT NULL DEFAULT false,
                    worker_consumed BOOLEAN NOT NULL DEFAULT false,
                    digestion_output_readback BOOLEAN NOT NULL DEFAULT false,
                    downstream_handoff_observed BOOLEAN NOT NULL DEFAULT false,
                    task_payload JSONB NOT NULL,
                    queue_payload JSONB NOT NULL,
                    persistence_writes JSONB NOT NULL,
                    lifecycle_events JSONB NOT NULL,
                    downstream_handoffs JSONB NOT NULL,
                    closure_evidence JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT uq_long_cycle_live_tasks_project_task UNIQUE (project_key, task_key),
                    CONSTRAINT uq_long_cycle_live_tasks_project_queue_item UNIQUE (project_key, queue_item_key)
                )
                """
            )
        )
        for column in ("project_key", "task_key", "queue_item_key", "dispatch_key", "status"):
            op.execute(
                sa.text(
                    f"""
                    CREATE INDEX IF NOT EXISTS ix_long_cycle_live_tasks_{column}
                    ON {quoted}.long_cycle_live_tasks ({column})
                    """
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {_quote_ident(schema)}.long_cycle_live_tasks"))
