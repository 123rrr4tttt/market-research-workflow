"""add graph node projection tables

Revision ID: 20260303_000004
Revises: 20260301_000003
Create Date: 2026-03-03 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = "20260303_000004"
down_revision = "20260301_000003"
branch_labels = None
depends_on = None


def _target_schemas(conn) -> list[str]:
    rows = conn.execute(
        sa.text(
            "SELECT DISTINCT table_schema FROM information_schema.tables "
            "WHERE table_name = 'documents'"
        )
    ).fetchall()
    schemas = [str(r[0]) for r in rows if r and r[0]]
    return schemas or ["public"]


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(
            sa.text(
                f'''
                CREATE TABLE IF NOT EXISTS "{schema}"."graph_nodes" (
                  id BIGSERIAL PRIMARY KEY,
                  project_key VARCHAR(64) NOT NULL DEFAULT 'default',
                  node_type VARCHAR(64) NOT NULL,
                  canonical_id VARCHAR(255) NOT NULL,
                  display_name TEXT NULL,
                  properties JSONB NULL,
                  source_doc_id BIGINT NULL,
                  node_schema_version VARCHAR(32) NOT NULL DEFAULT 'v1',
                  quality_flags JSONB NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  CONSTRAINT uq_graph_nodes_project_type_canonical UNIQUE (project_key, node_type, canonical_id)
                )
                '''
            )
        )
        op.execute(
            sa.text(
                f'''
                CREATE TABLE IF NOT EXISTS "{schema}"."graph_node_aliases" (
                  id BIGSERIAL PRIMARY KEY,
                  project_key VARCHAR(64) NOT NULL DEFAULT 'default',
                  node_id BIGINT NOT NULL,
                  alias_text TEXT NOT NULL,
                  alias_norm TEXT NOT NULL,
                  alias_type VARCHAR(32) NOT NULL DEFAULT 'display',
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  CONSTRAINT uq_graph_node_aliases_project_norm_type UNIQUE (project_key, alias_norm, alias_type),
                  CONSTRAINT fk_graph_node_aliases_node_id
                    FOREIGN KEY(node_id) REFERENCES "{schema}"."graph_nodes"(id)
                    ON DELETE CASCADE
                )
                '''
            )
        )
        op.execute(
            sa.text(
                f'CREATE INDEX IF NOT EXISTS ix_graph_nodes_project_key ON "{schema}"."graph_nodes" (project_key)'
            )
        )
        op.execute(
            sa.text(
                f'CREATE INDEX IF NOT EXISTS ix_graph_nodes_type ON "{schema}"."graph_nodes" (node_type)'
            )
        )
        op.execute(
            sa.text(
                f'CREATE INDEX IF NOT EXISTS ix_graph_nodes_updated_at ON "{schema}"."graph_nodes" (updated_at DESC)'
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}"."graph_node_aliases"'))
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}"."graph_nodes"'))
