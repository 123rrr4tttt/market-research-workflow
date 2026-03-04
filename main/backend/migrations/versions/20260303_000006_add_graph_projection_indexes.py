"""add graph projection indexes

Revision ID: 20260303_000006
Revises: 20260303_000005
Create Date: 2026-03-03 14:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260303_000006"
down_revision = "20260303_000005"
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


def _column_exists(conn, *, schema: str, table: str, column: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table_name AND column_name = :column_name "
            "LIMIT 1"
        ),
        {"schema": schema, "table_name": table, "column_name": column},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(
            sa.text(
                f'CREATE INDEX IF NOT EXISTS ix_graph_node_aliases_node_id '
                f'ON "{schema}"."graph_node_aliases" (node_id)'
            )
        )
        if _column_exists(conn, schema=schema, table="graph_node_aliases", column="project_key"):
            op.execute(
                sa.text(
                    f'CREATE INDEX IF NOT EXISTS ix_graph_node_aliases_project_key '
                    f'ON "{schema}"."graph_node_aliases" (project_key)'
                )
            )
        op.execute(
            sa.text(
                f'CREATE INDEX IF NOT EXISTS ix_graph_edges_edge_type '
                f'ON "{schema}"."graph_edges" (edge_type)'
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(
            sa.text(f'DROP INDEX IF EXISTS "{schema}"."ix_graph_node_aliases_node_id"')
        )
        op.execute(
            sa.text(f'DROP INDEX IF EXISTS "{schema}"."ix_graph_node_aliases_project_key"')
        )
        op.execute(
            sa.text(f'DROP INDEX IF EXISTS "{schema}"."ix_graph_edges_edge_type"')
        )
