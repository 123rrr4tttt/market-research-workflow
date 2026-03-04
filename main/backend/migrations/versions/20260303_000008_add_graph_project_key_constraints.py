"""add graph project_key constraints

Revision ID: 20260303_000008
Revises: 20260303_000007
Create Date: 2026-03-03 18:35:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260303_000008"
down_revision = "20260303_000007"
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


def _constraint_exists(conn, *, schema: str, table: str, name: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_schema = :schema AND table_name = :table_name AND constraint_name = :name "
            "LIMIT 1"
        ),
        {"schema": schema, "table_name": table, "name": name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_nodes" ADD COLUMN IF NOT EXISTS project_key VARCHAR(64)'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_node_aliases" ADD COLUMN IF NOT EXISTS project_key VARCHAR(64)'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_edges" ADD COLUMN IF NOT EXISTS project_key VARCHAR(64)'))

        op.execute(sa.text(f"UPDATE \"{schema}\".\"graph_nodes\" SET project_key = 'default' WHERE project_key IS NULL OR project_key = ''"))
        op.execute(sa.text(f"UPDATE \"{schema}\".\"graph_node_aliases\" SET project_key = 'default' WHERE project_key IS NULL OR project_key = ''"))
        op.execute(sa.text(f"UPDATE \"{schema}\".\"graph_edges\" SET project_key = 'default' WHERE project_key IS NULL OR project_key = ''"))

        op.execute(sa.text(f"ALTER TABLE \"{schema}\".\"graph_nodes\" ALTER COLUMN project_key SET DEFAULT 'default'"))
        op.execute(sa.text(f"ALTER TABLE \"{schema}\".\"graph_node_aliases\" ALTER COLUMN project_key SET DEFAULT 'default'"))
        op.execute(sa.text(f"ALTER TABLE \"{schema}\".\"graph_edges\" ALTER COLUMN project_key SET DEFAULT 'default'"))

        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_nodes" ALTER COLUMN project_key SET NOT NULL'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_node_aliases" ALTER COLUMN project_key SET NOT NULL'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_edges" ALTER COLUMN project_key SET NOT NULL'))

        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_nodes" DROP CONSTRAINT IF EXISTS uq_graph_nodes_type_canonical'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_node_aliases" DROP CONSTRAINT IF EXISTS uq_graph_node_aliases_norm_type'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_edges" DROP CONSTRAINT IF EXISTS uq_graph_edges_type_from_to'))

        if not _constraint_exists(conn, schema=schema, table="graph_nodes", name="uq_graph_nodes_project_type_canonical"):
            op.execute(
                sa.text(
                    f'ALTER TABLE "{schema}"."graph_nodes" '
                    'ADD CONSTRAINT uq_graph_nodes_project_type_canonical '
                    'UNIQUE (project_key, node_type, canonical_id)'
                )
            )
        if not _constraint_exists(conn, schema=schema, table="graph_node_aliases", name="uq_graph_node_aliases_project_norm_type"):
            op.execute(
                sa.text(
                    f'ALTER TABLE "{schema}"."graph_node_aliases" '
                    'ADD CONSTRAINT uq_graph_node_aliases_project_norm_type '
                    'UNIQUE (project_key, alias_norm, alias_type)'
                )
            )
        if not _constraint_exists(conn, schema=schema, table="graph_edges", name="uq_graph_edges_project_type_from_to"):
            op.execute(
                sa.text(
                    f'ALTER TABLE "{schema}"."graph_edges" '
                    'ADD CONSTRAINT uq_graph_edges_project_type_from_to '
                    'UNIQUE (project_key, edge_type, from_node_id, to_node_id)'
                )
            )

        op.execute(sa.text(f'CREATE INDEX IF NOT EXISTS ix_graph_nodes_project_key_updated_at ON "{schema}"."graph_nodes" (project_key, updated_at DESC)'))
        op.execute(sa.text(f'CREATE INDEX IF NOT EXISTS ix_graph_edges_project_key ON "{schema}"."graph_edges" (project_key)'))
        op.execute(sa.text(f'CREATE INDEX IF NOT EXISTS ix_graph_node_aliases_project_key_node_id ON "{schema}"."graph_node_aliases" (project_key, node_id)'))


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{schema}"."ix_graph_node_aliases_project_key_node_id"'))
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{schema}"."ix_graph_edges_project_key"'))
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{schema}"."ix_graph_nodes_project_key_updated_at"'))

        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_nodes" DROP CONSTRAINT IF EXISTS uq_graph_nodes_project_type_canonical'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_node_aliases" DROP CONSTRAINT IF EXISTS uq_graph_node_aliases_project_norm_type'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_edges" DROP CONSTRAINT IF EXISTS uq_graph_edges_project_type_from_to'))

        if not _constraint_exists(conn, schema=schema, table="graph_nodes", name="uq_graph_nodes_type_canonical"):
            op.execute(
                sa.text(
                    f'ALTER TABLE "{schema}"."graph_nodes" '
                    'ADD CONSTRAINT uq_graph_nodes_type_canonical '
                    'UNIQUE (node_type, canonical_id)'
                )
            )
        if not _constraint_exists(conn, schema=schema, table="graph_node_aliases", name="uq_graph_node_aliases_norm_type"):
            op.execute(
                sa.text(
                    f'ALTER TABLE "{schema}"."graph_node_aliases" '
                    'ADD CONSTRAINT uq_graph_node_aliases_norm_type '
                    'UNIQUE (alias_norm, alias_type)'
                )
            )
        if not _constraint_exists(conn, schema=schema, table="graph_edges", name="uq_graph_edges_type_from_to"):
            op.execute(
                sa.text(
                    f'ALTER TABLE "{schema}"."graph_edges" '
                    'ADD CONSTRAINT uq_graph_edges_type_from_to '
                    'UNIQUE (edge_type, from_node_id, to_node_id)'
                )
            )

        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_nodes" DROP COLUMN IF EXISTS project_key'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_node_aliases" DROP COLUMN IF EXISTS project_key'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."graph_edges" DROP COLUMN IF EXISTS project_key'))
