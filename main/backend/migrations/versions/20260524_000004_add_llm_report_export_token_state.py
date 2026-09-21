"""add llm report export token state

Revision ID: 20260524_000004
Revises: 20260524_000003
Create Date: 2026-05-24 15:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_000004"
down_revision = "20260524_000003"
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
                'llm_report_quality_trends',
                'llm_report_export_audit_events'
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
                CREATE TABLE IF NOT EXISTS {quoted}.llm_report_export_token_states (
                    id BIGSERIAL PRIMARY KEY,
                    artifact_id VARCHAR(128) NOT NULL,
                    actor_id VARCHAR(128),
                    project_key VARCHAR(64),
                    trace_id VARCHAR(128),
                    request_id VARCHAR(128),
                    job_id BIGINT,
                    used_at TIMESTAMPTZ,
                    revoked_at TIMESTAMPTZ,
                    revoke_reason TEXT,
                    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    payload JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT uq_llm_report_export_token_states_artifact_id UNIQUE (artifact_id)
                )
                """
            )
        )
        for column in (
            "artifact_id",
            "project_key",
            "actor_id",
            "used_at",
            "revoked_at",
        ):
            op.execute(
                sa.text(
                    f"""
                    CREATE INDEX IF NOT EXISTS ix_llm_report_export_token_states_{column}
                    ON {quoted}.llm_report_export_token_states ({column})
                    """
                )
            )
        op.execute(
            sa.text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_llm_report_export_token_states_project_actor_last_seen
                ON {quoted}.llm_report_export_token_states (project_key, actor_id, last_seen_at DESC)
                """
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {_quote_ident(schema)}.llm_report_export_token_states"))
