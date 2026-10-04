"""Add revisioned information-topology storage to public and tenant schemas.

Revision ID: 20260924_000001
Revises: 20260905_000001
Create Date: 2026-09-24 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260924_000001"
down_revision = "20260905_000001"
branch_labels = None
depends_on = None


def _project_schemas(conn: sa.Connection) -> tuple[str, ...]:
    if not sa.inspect(conn).has_table("projects", schema="public"):
        return ()
    rows = conn.execute(sa.text(
        "SELECT DISTINCT schema_name FROM public.projects "
        "WHERE schema_name IS NOT NULL AND schema_name NOT IN "
        "('public', 'pg_catalog', 'information_schema') ORDER BY schema_name"
    )).scalars()
    return tuple(str(name) for name in rows if name)


def _create_in_schema(schema: str) -> None:
    op.create_table(
        "information_topology_states",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_key", sa.String(128), nullable=False),
        sa.Column("module_id", sa.String(128), nullable=False),
        sa.Column("namespace", sa.String(255), nullable=False),
        sa.Column("state_id", sa.String(255), nullable=False),
        sa.Column("profile_id", sa.String(255), nullable=False),
        sa.Column("profile_version", sa.String(128), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("provenance", JSONB(), nullable=True),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "project_key", "module_id", "namespace", "state_id", "revision",
            name="uq_information_topology_state_revision",
        ),
        schema=schema,
    )
    op.create_index(
        "uq_information_topology_state_current",
        "information_topology_states", ["project_key", "module_id", "namespace", "state_id"],
        unique=True, schema=schema, postgresql_where=sa.text("is_current IS TRUE"),
    )
    op.create_index(
        "ix_information_topology_state_project_module", "information_topology_states",
        ["project_key", "module_id"], schema=schema,
    )
    op.create_table(
        "information_topology_links",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_key", sa.String(128), nullable=False),
        sa.Column("link_id", sa.String(255), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("record_kind", sa.String(32), nullable=False),
        sa.Column("type_or_rule_ref", sa.String(512), nullable=False),
        sa.Column("endpoints", JSONB(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("provenance", JSONB(), nullable=True),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_key", "link_id", "revision", name="uq_information_topology_link_revision"),
        schema=schema,
    )
    op.create_index(
        "uq_information_topology_link_current", "information_topology_links", ["project_key", "link_id"],
        unique=True, schema=schema, postgresql_where=sa.text("is_current IS TRUE"),
    )
    op.create_index(
        "ix_information_topology_link_project_kind", "information_topology_links",
        ["project_key", "record_kind"], schema=schema,
    )


def upgrade() -> None:
    conn = op.get_bind()
    for schema in ("public", *_project_schemas(conn)):
        _create_in_schema(schema)


def downgrade() -> None:
    conn = op.get_bind()
    for schema in reversed(("public", *_project_schemas(conn))):
        op.drop_table("information_topology_links", schema=schema)
        op.drop_table("information_topology_states", schema=schema)
