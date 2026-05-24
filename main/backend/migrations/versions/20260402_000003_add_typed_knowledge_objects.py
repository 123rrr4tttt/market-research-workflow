"""add typed knowledge live objects table

Revision ID: 20260402_000003
Revises: 20260402_000002
Create Date: 2026-04-02 12:45:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260402_000003"
down_revision = "20260402_000002"
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
            WHERE table_name IN ('documents', 'writing_documents')
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


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {_quote_ident(schema)}.typed_knowledge_objects"))
