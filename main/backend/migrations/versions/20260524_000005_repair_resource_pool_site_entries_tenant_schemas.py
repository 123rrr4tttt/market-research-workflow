"""repair resource pool site entry tables in tenant schemas

Revision ID: 20260524_000005
Revises: 20260524_000004
Create Date: 2026-05-24 18:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_000005"
down_revision = "20260524_000004"
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
                   WHERE table_name IN (
                       'source_library_items',
                       'resource_pool_urls',
                       'ingest_submission_registry'
                   )
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
            CREATE TABLE IF NOT EXISTS {quoted}.resource_pool_site_entries (
                id BIGSERIAL PRIMARY KEY,
                site_url TEXT NOT NULL,
                domain VARCHAR(255),
                entry_type VARCHAR(32) NOT NULL DEFAULT 'domain_root',
                template TEXT,
                name VARCHAR(255),
                capabilities JSONB,
                source VARCHAR(32) NOT NULL DEFAULT 'manual',
                source_ref JSONB,
                tags JSONB,
                enabled BOOLEAN NOT NULL DEFAULT true,
                project_key VARCHAR(64),
                extra JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_pool_site_entries_site_url
            ON {quoted}.resource_pool_site_entries (site_url)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_resource_pool_site_entries_project_key
            ON {quoted}.resource_pool_site_entries (project_key)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_resource_pool_site_entries_enabled
            ON {quoted}.resource_pool_site_entries (enabled)
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
        op.execute(sa.text(f"DROP TABLE IF EXISTS {_quote_ident(schema)}.resource_pool_site_entries"))
