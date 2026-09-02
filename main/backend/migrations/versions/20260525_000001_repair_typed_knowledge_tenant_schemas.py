"""repair typed knowledge tables in tenant schemas

Revision ID: 20260525_000001
Revises: 20260524_000005
Create Date: 2026-05-25 19:25:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260525_000001"
down_revision = "20260524_000005"
branch_labels = None
depends_on = None


def _quote_ident(raw: str) -> str:
    return '"' + raw.replace('"', '""') + '"'


def _target_schemas(conn) -> list[str]:
    rows = conn.execute(
        sa.text(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name = 'public'
               OR schema_name LIKE 'project_%'
               OR schema_name IN (
                   SELECT schema_name FROM public.projects
               )
               OR schema_name IN (
                   SELECT DISTINCT table_schema
                   FROM information_schema.tables
                   WHERE table_name IN ('documents', 'writing_documents', 'workflow_graph_runs')
               )
            ORDER BY schema_name
            """
        )
    ).fetchall()
    return [str(row[0]) for row in rows if row and row[0]]


def _create_tenant_table(schema: str) -> None:
    quoted = _quote_ident(schema)
    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {quoted}.typed_knowledge_objects (
                id BIGSERIAL PRIMARY KEY,
                project_key VARCHAR(64) NOT NULL,
                object_type VARCHAR(32) NOT NULL,
                object_key VARCHAR(255) NOT NULL,
                identity_ref VARCHAR(512) NOT NULL,
                visibility_scope VARCHAR(64) NOT NULL,
                lifecycle_state VARCHAR(32) NOT NULL,
                review_state VARCHAR(64) NOT NULL,
                governance JSONB,
                writing_handoff_refs JSONB,
                payload JSONB,
                updated_at_text VARCHAR(64),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_typed_knowledge_project_type_key
                    UNIQUE (project_key, object_type, object_key),
                CONSTRAINT uq_typed_knowledge_identity_ref UNIQUE (identity_ref)
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_typed_knowledge_objects_project_key
            ON {quoted}.typed_knowledge_objects (project_key)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_typed_knowledge_objects_object_type
            ON {quoted}.typed_knowledge_objects (object_type)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_typed_knowledge_objects_review_state
            ON {quoted}.typed_knowledge_objects (review_state)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_typed_knowledge_objects_identity_ref
            ON {quoted}.typed_knowledge_objects (identity_ref)
            """
        )
    )


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        _create_tenant_table(schema)


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {_quote_ident(schema)}.typed_knowledge_objects"))
