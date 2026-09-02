"""add llm report export audit events

Revision ID: 20260524_000003
Revises: 20260524_000002
Create Date: 2026-05-24 14:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_000003"
down_revision = "20260524_000002"
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
            WHERE table_name IN (
                'documents',
                'source_library_items',
                'long_cycle_live_tasks',
                'ingest_submission_registry',
                'llm_report_quality_trends'
            )
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
                CREATE TABLE IF NOT EXISTS {quoted}.llm_report_export_audit_events (
                    id BIGSERIAL PRIMARY KEY,
                    trace_id VARCHAR(128),
                    source_trace_id VARCHAR(128),
                    request_id VARCHAR(128),
                    project_key VARCHAR(64),
                    job_id BIGINT,
                    export_format VARCHAR(32),
                    outcome VARCHAR(32) NOT NULL DEFAULT 'unknown',
                    integrity_mode VARCHAR(64),
                    integrity_trusted BOOLEAN NOT NULL DEFAULT false,
                    actor_id VARCHAR(128),
                    artifact_id VARCHAR(128),
                    artifact_sha256 VARCHAR(64),
                    filename TEXT,
                    content_type VARCHAR(128),
                    content_size_bytes BIGINT,
                    error_code VARCHAR(128),
                    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    payload JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT uq_llm_report_export_audit_events_trace_id UNIQUE (trace_id)
                )
                """
            )
        )
        for column in (
            "trace_id",
            "source_trace_id",
            "request_id",
            "project_key",
            "job_id",
            "export_format",
            "outcome",
            "integrity_mode",
            "integrity_trusted",
            "actor_id",
            "artifact_id",
            "artifact_sha256",
            "error_code",
            "recorded_at",
        ):
            op.execute(
                sa.text(
                    f"""
                    CREATE INDEX IF NOT EXISTS ix_llm_report_export_audit_events_{column}
                    ON {quoted}.llm_report_export_audit_events ({column})
                    """
                )
            )
        op.execute(
            sa.text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_llm_report_export_audit_events_project_format_outcome
                ON {quoted}.llm_report_export_audit_events (project_key, export_format, outcome, recorded_at DESC)
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_llm_report_export_audit_events_actor_recorded_at
                ON {quoted}.llm_report_export_audit_events (actor_id, recorded_at DESC)
                """
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {_quote_ident(schema)}.llm_report_export_audit_events"))
