"""add ingest submission registry

Revision ID: 20260524_000001
Revises: 20260402_000004
Create Date: 2026-05-24 10:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_000001"
down_revision = "20260402_000004"
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
            WHERE table_name IN ('documents', 'source_library_items', 'long_cycle_live_tasks')
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
                CREATE TABLE IF NOT EXISTS {quoted}.ingest_submission_registry (
                    id BIGSERIAL PRIMARY KEY,
                    project_key VARCHAR(64) NOT NULL,
                    trigger_type VARCHAR(96) NOT NULL,
                    registry_key VARCHAR(512) NOT NULL,
                    idempotency_key VARCHAR(256) NOT NULL,
                    submission_id VARCHAR(64) NOT NULL,
                    task_id VARCHAR(128),
                    status VARCHAR(32) NOT NULL DEFAULT 'submitted',
                    request_hash VARCHAR(64) NOT NULL,
                    request_payload JSONB,
                    subject_payload JSONB,
                    response_payload JSONB,
                    last_error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT uq_ingest_submission_registry_key UNIQUE (registry_key),
                    CONSTRAINT uq_ingest_submission_project_trigger_key
                        UNIQUE (project_key, trigger_type, idempotency_key)
                )
                """
            )
        )
        for column in (
            "project_key",
            "trigger_type",
            "registry_key",
            "idempotency_key",
            "submission_id",
            "task_id",
            "status",
            "request_hash",
        ):
            op.execute(
                sa.text(
                    f"""
                    CREATE INDEX IF NOT EXISTS ix_ingest_submission_registry_{column}
                    ON {quoted}.ingest_submission_registry ({column})
                    """
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {_quote_ident(schema)}.ingest_submission_registry"))
