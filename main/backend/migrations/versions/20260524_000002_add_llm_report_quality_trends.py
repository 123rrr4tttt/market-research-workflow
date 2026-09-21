"""add llm report quality trends

Revision ID: 20260524_000002
Revises: 20260524_000001
Create Date: 2026-05-24 13:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_000002"
down_revision = "20260524_000001"
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
                'ingest_submission_registry'
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
                CREATE TABLE IF NOT EXISTS {quoted}.llm_report_quality_trends (
                    id BIGSERIAL PRIMARY KEY,
                    trace_id VARCHAR(128),
                    request_id VARCHAR(128),
                    project_key VARCHAR(64),
                    job_id BIGINT,
                    job_status VARCHAR(32),
                    topic TEXT,
                    decision VARCHAR(16) NOT NULL DEFAULT 'fail',
                    passed BOOLEAN NOT NULL DEFAULT false,
                    gate_mode VARCHAR(16),
                    gate_mode_raw VARCHAR(32),
                    gate_mode_fallback BOOLEAN NOT NULL DEFAULT false,
                    citation_coverage NUMERIC(6, 4) NOT NULL DEFAULT 0,
                    evidence_coverage NUMERIC(6, 4) NOT NULL DEFAULT 0,
                    source_count INTEGER NOT NULL DEFAULT 0,
                    source_count_requested INTEGER NOT NULL DEFAULT 0,
                    source_count_resolved INTEGER NOT NULL DEFAULT 0,
                    missing_items_count INTEGER NOT NULL DEFAULT 0,
                    hard_failure_count INTEGER NOT NULL DEFAULT 0,
                    soft_failure_count INTEGER NOT NULL DEFAULT 0,
                    readiness VARCHAR(32),
                    next_action VARCHAR(128),
                    record_source VARCHAR(32) NOT NULL DEFAULT 'generate',
                    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    payload JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT uq_llm_report_quality_trends_trace_id UNIQUE (trace_id)
                )
                """
            )
        )
        for column in (
            "trace_id",
            "request_id",
            "project_key",
            "job_id",
            "job_status",
            "decision",
            "gate_mode",
            "readiness",
            "record_source",
            "recorded_at",
        ):
            op.execute(
                sa.text(
                    f"""
                    CREATE INDEX IF NOT EXISTS ix_llm_report_quality_trends_{column}
                    ON {quoted}.llm_report_quality_trends ({column})
                    """
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {_quote_ident(schema)}.llm_report_quality_trends"))
