"""add graph edge projection table

Revision ID: 20260303_000005
Revises: 20260303_000004
Create Date: 2026-03-03 13:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260303_000005"
down_revision = "20260303_000004"
branch_labels = None
depends_on = None


def _target_schemas(conn) -> list[str]:
    rows = conn.execute(
        sa.text(
            "SELECT DISTINCT table_schema FROM information_schema.tables "
            "WHERE table_name = 'graph_nodes'"
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
                CREATE TABLE IF NOT EXISTS "{schema}"."graph_edges" (
                  id BIGSERIAL PRIMARY KEY,
                  project_key VARCHAR(64) NOT NULL DEFAULT 'default',
                  edge_type VARCHAR(64) NOT NULL,
                  from_node_id BIGINT NOT NULL,
                  to_node_id BIGINT NOT NULL,
                  properties JSONB NULL,
                  edge_schema_version VARCHAR(32) NOT NULL DEFAULT 'v1',
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  CONSTRAINT uq_graph_edges_project_type_from_to UNIQUE (project_key, edge_type, from_node_id, to_node_id),
                  CONSTRAINT fk_graph_edges_from_node
                    FOREIGN KEY(from_node_id) REFERENCES "{schema}"."graph_nodes"(id)
                    ON DELETE CASCADE,
                  CONSTRAINT fk_graph_edges_to_node
                    FOREIGN KEY(to_node_id) REFERENCES "{schema}"."graph_nodes"(id)
                    ON DELETE CASCADE
                )
                '''
            )
        )
        op.execute(
            sa.text(
                f'CREATE INDEX IF NOT EXISTS ix_graph_edges_project_key ON "{schema}"."graph_edges" (project_key)'
            )
        )
        op.execute(
            sa.text(
                f'CREATE INDEX IF NOT EXISTS ix_graph_edges_from_node ON "{schema}"."graph_edges" (from_node_id)'
            )
        )
        op.execute(
            sa.text(
                f'CREATE INDEX IF NOT EXISTS ix_graph_edges_to_node ON "{schema}"."graph_edges" (to_node_id)'
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}"."graph_edges"'))
