"""Provision typed knowledge for existing registered projects that lack it.

Revision ID: 20261119_000002
Revises: 20261119_000001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "20261119_000002"
down_revision = "20261119_000001"
branch_labels = None
depends_on = None


def _table(metadata: sa.MetaData, schema: str) -> sa.Table:
    return sa.Table(
        "typed_knowledge_objects",
        metadata,
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_key", sa.String(64), nullable=False, index=True),
        sa.Column("object_type", sa.String(32), nullable=False, index=True),
        sa.Column("object_key", sa.String(255), nullable=False),
        sa.Column("identity_ref", sa.String(512), nullable=False, index=True),
        sa.Column("visibility_scope", sa.String(64), nullable=False),
        sa.Column("lifecycle_state", sa.String(32), nullable=False),
        sa.Column("review_state", sa.String(64), nullable=False, index=True),
        sa.Column("governance", JSONB),
        sa.Column("writing_handoff_refs", JSONB),
        sa.Column("payload", JSONB),
        sa.Column("updated_at_text", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_key", "object_type", "object_key", name="uq_typed_knowledge_project_type_key"),
        sa.UniqueConstraint("identity_ref", name="uq_typed_knowledge_identity_ref"),
        schema=schema,
    )


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_schemas = set(inspector.get_schema_names())
    # Archived projects remain readable and may be restored, so include them.
    schemas = connection.execute(sa.text("SELECT schema_name FROM public.projects ORDER BY schema_name")).scalars()
    seen: set[str] = set()
    metadata = sa.MetaData()
    missing_tables = []
    for schema in schemas:
        if (
            schema in seen or schema not in existing_schemas
            or schema in {"public", "information_schema"} or schema.startswith("pg_")
        ):
            raise RuntimeError(f"TYPED_KNOWLEDGE_REPAIR_INVALID_SCHEMA {schema!r}")  # noqa: TRY003
        seen.add(schema)
        table = _table(metadata, schema)
        if table.name not in inspector.get_table_names(schema=schema):
            if inspector.has_table(table.name, schema=schema):
                raise RuntimeError(f"TYPED_KNOWLEDGE_REPAIR_RELATION_CONFLICT {schema!r}")  # noqa: TRY003
            missing_tables.append(table)
            continue
        columns = {column["name"] for column in inspector.get_columns(table.name, schema=schema)}
        missing_columns = sorted(set(table.columns.keys()) - columns)
        if missing_columns:
            raise RuntimeError(  # noqa: TRY003
                f"TYPED_KNOWLEDGE_REPAIR_COLUMNS_MISSING {schema!r}: {','.join(missing_columns)}"
            )

    for table in missing_tables:
        table.create(connection)


def downgrade() -> None:
    # Never drop typed knowledge, including rows saved after this repair.
    return None
