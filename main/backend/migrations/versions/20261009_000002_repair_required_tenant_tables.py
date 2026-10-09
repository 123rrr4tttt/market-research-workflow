"""repair required tables in registered tenant schemas

Revision ID: 20261009_000002
Revises: 20261009_000001
Create Date: 2026-10-09 18:40:00.000000

The table definitions are derived from the application's canonical tenant
metadata.  The fixed DDL digest prevents a future model change from silently
reinterpreting this historical revision.
"""

from __future__ import annotations

import hashlib

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.sql.schema import Table

from app.services.projects.bootstrap import (
    ProjectSchemaIncompatibleError,
    TENANT_TABLES,
    validate_project_schema,
)


revision = "20261009_000002"
down_revision = "20261009_000001"
branch_labels = None
depends_on = None


REQUIRED_REPAIR_TABLE_NAMES = frozenset(
    {
        "graph_nodes",
        "graph_node_aliases",
        "graph_edges",
        "ingest_submission_registry",
        "resource_pool_site_entries",
    }
)
EXPECTED_NATIVE_DDL_SHA256 = "cabffbdc33c441286a8bd645afa471c97f36f4f233b1f452742563e3de3c4b7b"
_SYSTEM_SCHEMAS = frozenset({"public", "pg_catalog", "information_schema"})


def _repair_tables() -> tuple[Table, ...]:
    tables = tuple(
        table for table in TENANT_TABLES if table.name in REQUIRED_REPAIR_TABLE_NAMES
    )
    names = {table.name for table in tables}
    if names != REQUIRED_REPAIR_TABLE_NAMES:
        raise RuntimeError(
            "TENANT_REPAIR_METADATA_INCOMPLETE "
            f"actual={','.join(sorted(names))} "
            f"expected={','.join(sorted(REQUIRED_REPAIR_TABLE_NAMES))}"
        )
    return tables


def _native_ddl_sha256(tables: tuple[Table, ...]) -> str:
    dialect = postgresql.dialect()
    statements: list[str] = []
    for table in tables:
        statements.append(str(CreateTable(table).compile(dialect=dialect)))
        statements.extend(
            str(CreateIndex(index).compile(dialect=dialect))
            for index in sorted(table.indexes, key=lambda value: value.name or "")
        )
    return hashlib.sha256("\n-- statement --\n".join(statements).encode()).hexdigest()


def _quote_ident(raw: str) -> str:
    return '"' + raw.replace('"', '""') + '"'


def _target_project_schemas(conn: sa.Connection) -> tuple[str, ...]:
    rows = conn.execute(
        sa.text(
            "SELECT project_key, schema_name FROM public.projects "
            "WHERE enabled=true ORDER BY project_key"
        )
    ).fetchall()
    owners: dict[str, str] = {}
    for row in rows:
        project_key = str(row[0] or "").strip()
        schema_name = str(row[1] or "").strip()
        if not project_key or not schema_name:
            raise RuntimeError("TENANT_REPAIR_INVALID_PROJECT_REGISTRY")
        if schema_name in _SYSTEM_SCHEMAS or schema_name.startswith("pg_"):
            raise RuntimeError(
                f"TENANT_REPAIR_SYSTEM_SCHEMA project_key={project_key!r} schema={schema_name!r}"
            )
        prior_owner = owners.get(schema_name)
        if prior_owner is not None:
            raise RuntimeError(
                "TENANT_REPAIR_DUPLICATE_SCHEMA_OWNER "
                f"schema={schema_name!r} owners={prior_owner!r},{project_key!r}"
            )
        owners[schema_name] = project_key

    if not owners:
        return ()
    existing = {
        str(value)
        for value in conn.execute(
            sa.text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name = ANY(:schema_names)"
            ),
            {"schema_names": sorted(owners)},
        ).scalars()
    }
    missing = sorted(set(owners) - existing)
    if missing:
        raise RuntimeError(
            f"TENANT_REPAIR_SCHEMA_NOT_FOUND schemas={','.join(missing)}"
        )
    return tuple(sorted(owners))


def _selected_relation_kinds(
    conn: sa.Connection,
    *,
    schema_name: str,
) -> dict[str, str]:
    rows = conn.execute(
        sa.text(
            "SELECT c.relname, c.relkind FROM pg_class AS c "
            "JOIN pg_namespace AS n ON n.oid=c.relnamespace "
            "WHERE n.nspname=:schema_name AND c.relname = ANY(:table_names)"
        ),
        {
            "schema_name": schema_name,
            "table_names": sorted(REQUIRED_REPAIR_TABLE_NAMES),
        },
    ).fetchall()
    return {str(row[0]): str(row[1]) for row in rows}


def _preflight_schema(
    conn: sa.Connection,
    *,
    schema_name: str,
    tables: tuple[Table, ...],
) -> frozenset[str]:
    relation_kinds = _selected_relation_kinds(conn, schema_name=schema_name)
    conflicting_relations = sorted(
        name for name, kind in relation_kinds.items() if kind not in {"r", "p"}
    )
    if conflicting_relations:
        raise RuntimeError(
            "TENANT_REPAIR_RELATION_CONFLICT "
            f"schema={schema_name!r} relations={','.join(conflicting_relations)}"
        )

    try:
        validate_project_schema(conn, schema_name=schema_name, tables=TENANT_TABLES)
    except ProjectSchemaIncompatibleError as exc:
        missing = frozenset(exc.missing_tables)
        if exc.missing_columns:
            raise RuntimeError(
                "TENANT_REPAIR_COLUMN_CONFLICT "
                f"schema={schema_name!r} columns={','.join(exc.missing_columns)}"
            ) from exc
        unsupported = sorted(missing - REQUIRED_REPAIR_TABLE_NAMES)
        if unsupported:
            raise RuntimeError(
                "TENANT_REPAIR_UNSUPPORTED_GAP "
                f"schema={schema_name!r} tables={','.join(unsupported)}"
            ) from exc
    else:
        missing = frozenset()

    existing_tables = [table for table in tables if table.name not in missing]
    try:
        validate_project_schema(
            conn,
            schema_name=schema_name,
            tables=list(existing_tables),
        )
    except ProjectSchemaIncompatibleError as exc:
        raise RuntimeError(
            f"TENANT_REPAIR_EXISTING_TABLE_CONFLICT schema={schema_name!r}"
        ) from exc
    return missing


def upgrade() -> None:
    conn = op.get_bind()
    tables = _repair_tables()
    actual_digest = _native_ddl_sha256(tables)
    if actual_digest != EXPECTED_NATIVE_DDL_SHA256:
        raise RuntimeError(
            "TENANT_REPAIR_MODEL_SHAPE_DRIFT "
            f"actual={actual_digest} expected={EXPECTED_NATIVE_DDL_SHA256}"
        )

    schemas = _target_project_schemas(conn)
    missing_by_schema = {
        schema_name: _preflight_schema(
            conn,
            schema_name=schema_name,
            tables=tables,
        )
        for schema_name in schemas
    }

    original_search_path = str(
        conn.execute(sa.text("SELECT current_setting('search_path')")).scalar_one()
    )
    try:
        for schema_name in schemas:
            missing = missing_by_schema[schema_name]
            if not missing:
                continue
            conn.execute(
                sa.text(f"SET LOCAL search_path TO {_quote_ident(schema_name)}")
            )
            schema_metadata = sa.MetaData()
            schema_tables = {
                table.name: table.to_metadata(
                    schema_metadata,
                    schema=schema_name,
                )
                for table in tables
            }
            for table in tables:
                if table.name in missing:
                    schema_tables[table.name].create(bind=conn, checkfirst=False)
    finally:
        conn.execute(
            sa.text("SELECT set_config('search_path', :search_path, true)"),
            {"search_path": original_search_path},
        )

    for schema_name in schemas:
        validate_project_schema(
            conn,
            schema_name=schema_name,
            tables=TENANT_TABLES,
        )


def downgrade() -> None:
    # There is no durable per-schema creation ledger.  Retain every table to
    # avoid deleting one that predated this repair; only the Alembic head moves.
    return None
