"""repair graph projection constraints in existing tenant schemas

Revision ID: 20260402_000002
Revises: 20260402_000001
Create Date: 2026-04-02 12:30:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260402_000002"
down_revision = "20260402_000001"
branch_labels = None
depends_on = None


GRAPH_NODE_UNIQUE = "uq_graph_nodes_type_canonical"
GRAPH_NODE_ALIAS_UNIQUE = "uq_graph_node_aliases_norm_type"
GRAPH_EDGE_UNIQUE = "uq_graph_edges_type_from_to"


def _quote_ident(raw: str) -> str:
    return '"' + raw.replace('"', '""') + '"'


def _target_schemas(conn) -> list[str]:
    rows = conn.execute(
        sa.text(
            """
            SELECT DISTINCT table_schema
            FROM information_schema.tables
            WHERE table_name IN ('graph_nodes', 'graph_node_aliases', 'graph_edges')
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema
            """
        )
    ).fetchall()
    return [str(row[0]) for row in rows if row and row[0]]


def _has_table(conn, schema: str, table: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = :schema AND table_name = :table
                """
            ),
            {"schema": schema, "table": table},
        ).fetchone()
    )


def _has_constraint(conn, schema: str, table: str, constraint: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = :schema
                  AND table_name = :table
                  AND constraint_name = :constraint
                """
            ),
            {"schema": schema, "table": table, "constraint": constraint},
        ).fetchone()
    )


def _dedupe_graph_projection_tables(schema: str) -> None:
    quoted = _quote_ident(schema)
    op.execute(
        sa.text(
            f"""
            WITH duplicate_nodes AS (
                SELECT
                    id,
                    MIN(id) OVER (PARTITION BY node_type, canonical_id) AS keep_id
                FROM {quoted}.graph_nodes
            )
            UPDATE {quoted}.graph_edges edges
            SET from_node_id = duplicate_nodes.keep_id
            FROM duplicate_nodes
            WHERE edges.from_node_id = duplicate_nodes.id
              AND duplicate_nodes.id <> duplicate_nodes.keep_id
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            WITH duplicate_nodes AS (
                SELECT
                    id,
                    MIN(id) OVER (PARTITION BY node_type, canonical_id) AS keep_id
                FROM {quoted}.graph_nodes
            )
            UPDATE {quoted}.graph_edges edges
            SET to_node_id = duplicate_nodes.keep_id
            FROM duplicate_nodes
            WHERE edges.to_node_id = duplicate_nodes.id
              AND duplicate_nodes.id <> duplicate_nodes.keep_id
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            WITH duplicate_nodes AS (
                SELECT
                    id,
                    MIN(id) OVER (PARTITION BY node_type, canonical_id) AS keep_id
                FROM {quoted}.graph_nodes
            )
            UPDATE {quoted}.graph_node_aliases aliases
            SET node_id = duplicate_nodes.keep_id
            FROM duplicate_nodes
            WHERE aliases.node_id = duplicate_nodes.id
              AND duplicate_nodes.id <> duplicate_nodes.keep_id
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            WITH duplicate_edges AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY edge_type, from_node_id, to_node_id
                        ORDER BY id
                    ) AS rn
                FROM {quoted}.graph_edges
            )
            DELETE FROM {quoted}.graph_edges edges
            USING duplicate_edges
            WHERE edges.id = duplicate_edges.id
              AND duplicate_edges.rn > 1
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            WITH duplicate_aliases AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY alias_norm, alias_type
                        ORDER BY id
                    ) AS rn
                FROM {quoted}.graph_node_aliases
            )
            DELETE FROM {quoted}.graph_node_aliases aliases
            USING duplicate_aliases
            WHERE aliases.id = duplicate_aliases.id
              AND duplicate_aliases.rn > 1
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            WITH duplicate_nodes AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY node_type, canonical_id
                        ORDER BY id
                    ) AS rn
                FROM {quoted}.graph_nodes
            )
            DELETE FROM {quoted}.graph_nodes nodes
            USING duplicate_nodes
            WHERE nodes.id = duplicate_nodes.id
              AND duplicate_nodes.rn > 1
            """
        )
    )


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        quoted = _quote_ident(schema)
        has_nodes = _has_table(conn, schema, "graph_nodes")
        has_aliases = _has_table(conn, schema, "graph_node_aliases")
        has_edges = _has_table(conn, schema, "graph_edges")
        if has_nodes and has_aliases and has_edges:
            _dedupe_graph_projection_tables(schema)
        if has_nodes and not _has_constraint(conn, schema, "graph_nodes", GRAPH_NODE_UNIQUE):
            op.execute(
                sa.text(
                    f"""
                    ALTER TABLE {quoted}.graph_nodes
                    ADD CONSTRAINT {GRAPH_NODE_UNIQUE}
                    UNIQUE (node_type, canonical_id)
                    """
                )
            )
        if has_aliases and not _has_constraint(conn, schema, "graph_node_aliases", GRAPH_NODE_ALIAS_UNIQUE):
            op.execute(
                sa.text(
                    f"""
                    ALTER TABLE {quoted}.graph_node_aliases
                    ADD CONSTRAINT {GRAPH_NODE_ALIAS_UNIQUE}
                    UNIQUE (alias_norm, alias_type)
                    """
                )
            )
        if has_edges and not _has_constraint(conn, schema, "graph_edges", GRAPH_EDGE_UNIQUE):
            op.execute(
                sa.text(
                    f"""
                    ALTER TABLE {quoted}.graph_edges
                    ADD CONSTRAINT {GRAPH_EDGE_UNIQUE}
                    UNIQUE (edge_type, from_node_id, to_node_id)
                    """
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        quoted = _quote_ident(schema)
        if _has_constraint(conn, schema, "graph_edges", GRAPH_EDGE_UNIQUE):
            op.execute(sa.text(f"ALTER TABLE {quoted}.graph_edges DROP CONSTRAINT {GRAPH_EDGE_UNIQUE}"))
        if _has_constraint(conn, schema, "graph_node_aliases", GRAPH_NODE_ALIAS_UNIQUE):
            op.execute(sa.text(f"ALTER TABLE {quoted}.graph_node_aliases DROP CONSTRAINT {GRAPH_NODE_ALIAS_UNIQUE}"))
        if _has_constraint(conn, schema, "graph_nodes", GRAPH_NODE_UNIQUE):
            op.execute(sa.text(f"ALTER TABLE {quoted}.graph_nodes DROP CONSTRAINT {GRAPH_NODE_UNIQUE}"))
