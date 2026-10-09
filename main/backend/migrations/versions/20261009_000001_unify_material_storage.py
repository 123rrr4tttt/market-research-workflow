"""Unify legacy Document storage and migrate topology current states.

Revision ID: 20261009_000001
Revises: 20260926_000001
Create Date: 2026-10-09 16:00:00.000000

The physical table is renamed in place. Existing rows, PostgreSQL OIDs, foreign
keys, sequences, extra columns, and nullability are deliberately preserved.
"""

# Migration failures deliberately carry schema/project/code details in their
# RuntimeError text because Alembic surfaces that text as the operator receipt.
# ruff: noqa: TRY003, TRY004

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from alembic import context, op
from functorial_kit import Failure
import sqlalchemy as sa


revision = "20261009_000001"
down_revision = "20260926_000001"
branch_labels = None
depends_on = None

_SYSTEM_SCHEMAS = frozenset({"pg_catalog", "information_schema"})
_RESERVED_SCHEMAS = _SYSTEM_SCHEMAS
_FORWARD_NAME_RULES = (
    ("source_doc_id", "source_material_id"),
    ("documents", "materials"),
    ("document", "material"),
    ("doc_type", "material_type"),
)
_SOURCE_COLUMN_NAME_RULES = (("source_doc_id", "source_material_id"),)
_SOURCE_COLUMN_REVERSE_NAME_RULES = (("source_material_id", "source_doc_id"),)
_REVERSE_NAME_RULES = (
    ("source_material_id", "source_doc_id"),
    ("material_type", "doc_type"),
    ("materials", "documents"),
    ("material", "document"),
)
_SOURCE_ROOT_PARAMETER = "material_source_root"


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _qualified(schema: str, relation: str) -> str:
    return f"{_quote(schema)}.{_quote(relation)}"


def _mapped_name(name: str, rules: tuple[tuple[str, str], ...]) -> str | None:
    mapped = name
    changed = False
    for source, target in rules:
        if source in mapped:
            mapped = mapped.replace(source, target)
            changed = True
    return mapped if changed else None


def _schema_rows(conn: sa.Connection) -> dict[str, str]:
    rows = conn.execute(sa.text("SELECT schema_name FROM information_schema.schemata")).scalars()
    return {str(row): str(row) for row in rows if row}


def _registered_projects(conn: sa.Connection, schemas: dict[str, str]) -> dict[str, str]:
    if "projects" not in {
        str(row[0])
        for row in conn.execute(
            sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
    }:
        raise RuntimeError("MATERIAL_PREFLIGHT_FAILED public.projects is required")
    rows = conn.execute(
        sa.text(
            "SELECT project_key, schema_name FROM public.projects WHERE schema_name IS NOT NULL AND schema_name <> ''"
        )
    ).all()
    projects: dict[str, str] = {}
    for project_key, schema_name in rows:
        schema = str(schema_name)
        if schema in _RESERVED_SCHEMAS or schema.startswith("pg_"):
            raise RuntimeError(f"MATERIAL_PREFLIGHT_FAILED registered project uses reserved schema {schema!r}")
        if schema not in schemas:
            raise RuntimeError(
                f"MATERIAL_PREFLIGHT_FAILED registered schema is absent project={project_key!r} schema={schema!r}"
            )
        if schema in projects:
            raise RuntimeError(f"MATERIAL_PREFLIGHT_FAILED duplicate registered schema {schema!r}")
        projects[schema] = str(project_key)
    return projects


def _table_schemas(conn: sa.Connection, table_name: str) -> set[str]:
    rows = conn.execute(
        sa.text("SELECT table_schema FROM information_schema.tables WHERE table_name = :table_name"),
        {"table_name": table_name},
    ).scalars()
    return {str(schema) for schema in rows if str(schema) not in _SYSTEM_SCHEMAS and not str(schema).startswith("pg_")}


def _column_exists(conn: sa.Connection, schema: str, table: str, column: str) -> bool:
    return (
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
            ),
            {"schema": schema, "table": table, "column": column},
        ).fetchone()
        is not None
    )


def _preflight(conn: sa.Connection) -> tuple[dict[str, str], set[str]]:
    schemas = _schema_rows(conn)
    projects = _registered_projects(conn, schemas)
    document_schemas = _table_schemas(conn, "documents")
    material_schemas = _table_schemas(conn, "materials")

    if material_schemas:
        counts = conn.execute(
            sa.text(
                """
                SELECT table_schema,
                       CASE WHEN table_name = 'documents' THEN 1 ELSE 0 END AS is_document
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                  AND table_schema NOT LIKE 'pg\\_%'
                  AND table_name IN ('documents', 'materials')
                ORDER BY table_schema, table_name
                """
            )
        ).all()
        detail = ", ".join(f"{row.table_schema}:{'documents' if row.is_document else 'materials'}" for row in counts)
        raise RuntimeError(
            "MATERIAL_TABLE_CONFLICT pre-existing materials table requires "
            "explicit evidence before this revision; tables=" + detail
        )

    targets = set(document_schemas)
    for schema in sorted(targets):
        if not _column_exists(conn, schema, "documents", "doc_type"):
            raise RuntimeError(f"MATERIAL_PREFLIGHT_FAILED documents.doc_type is absent schema={schema!r}")

    graph_schemas = _table_schemas(conn, "graph_nodes")
    citation_schemas = _table_schemas(conn, "writing_document_citations")
    for schema in sorted(graph_schemas):
        has_old = _column_exists(conn, schema, "graph_nodes", "source_doc_id")
        has_new = _column_exists(conn, schema, "graph_nodes", "source_material_id")
        if has_old and has_new:
            raise RuntimeError(f"MATERIAL_COLUMN_CONFLICT graph_nodes has both source columns schema={schema!r}")
        if has_new and schema not in targets:
            raise RuntimeError(f"MATERIAL_PREFLIGHT_FAILED new graph column has no Material table schema={schema!r}")
        if has_old and schema not in targets:
            raise RuntimeError(
                f"MATERIAL_PREFLIGHT_FAILED graph_nodes.source_doc_id has no Material table schema={schema!r}"
            )
        if schema in targets and not has_old:
            raise RuntimeError(f"MATERIAL_PREFLIGHT_FAILED graph_nodes lacks source_doc_id schema={schema!r}")
    for schema in sorted(citation_schemas):
        has_old = _column_exists(conn, schema, "writing_document_citations", "source_doc_id")
        has_new = _column_exists(conn, schema, "writing_document_citations", "source_material_id")
        if has_old and has_new:
            raise RuntimeError(f"MATERIAL_COLUMN_CONFLICT writing citations has both source columns schema={schema!r}")
        if has_new and schema not in targets:
            raise RuntimeError(
                f"MATERIAL_PREFLIGHT_FAILED new writing citation column has no Material table schema={schema!r}"
            )
        if has_old and schema not in targets:
            raise RuntimeError(
                f"MATERIAL_PREFLIGHT_FAILED writing citation source_doc_id has no Material table schema={schema!r}"
            )
        if schema in targets and not has_old:
            raise RuntimeError(f"MATERIAL_PREFLIGHT_FAILED writing citations lack source_doc_id schema={schema!r}")

    return projects, targets


def _relation_name_exists(conn: sa.Connection, schema: str, name: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :schema AND c.relname = :name"
        ),
        {"schema": schema, "name": name},
    ).fetchone()
    return row is not None


def _rename_constraints_and_indexes(
    conn: sa.Connection,
    schema: str,
    table: str,
    rules: tuple[tuple[str, str], ...],
) -> None:
    constraint_names = conn.execute(
        sa.text(
            "SELECT conname FROM pg_constraint AS c "
            "JOIN pg_class AS t ON t.oid = c.conrelid "
            "JOIN pg_namespace AS n ON n.oid = t.relnamespace "
            "WHERE n.nspname = :schema AND t.relname = :table "
            "ORDER BY conname"
        ),
        {"schema": schema, "table": table},
    ).scalars()
    for old_name in tuple(constraint_names):
        new_name = _mapped_name(str(old_name), rules)
        if new_name is None:
            continue
        if _relation_name_exists(conn, schema, new_name):
            raise RuntimeError(f"MATERIAL_NAME_CONFLICT schema={schema!r} relation={new_name!r}")
        conn.execute(
            sa.text(
                f"ALTER TABLE {_qualified(schema, table)} "
                f"RENAME CONSTRAINT {_quote(str(old_name))} TO {_quote(new_name)}"
            )
        )

    index_names = conn.execute(
        sa.text(
            "SELECT indexname FROM pg_indexes WHERE schemaname = :schema AND tablename = :table ORDER BY indexname"
        ),
        {"schema": schema, "table": table},
    ).scalars()
    for old_name in tuple(index_names):
        new_name = _mapped_name(str(old_name), rules)
        if new_name is None:
            continue
        if _relation_name_exists(conn, schema, new_name):
            raise RuntimeError(f"MATERIAL_NAME_CONFLICT schema={schema!r} relation={new_name!r}")
        conn.execute(sa.text(f"ALTER INDEX {_qualified(schema, str(old_name))} RENAME TO {_quote(new_name)}"))


def _rename_owned_sequences(
    conn: sa.Connection,
    schema: str,
    table: str,
    rules: tuple[tuple[str, str], ...],
) -> None:
    rows = conn.execute(
        sa.text(
            """
            SELECT s.oid, s.relname
            FROM pg_class AS s
            JOIN pg_depend AS d
              ON d.objid = s.oid
             AND d.classid = 'pg_class'::regclass
             AND d.refclassid = 'pg_class'::regclass
            JOIN pg_class AS t ON t.oid = d.refobjid
            JOIN pg_namespace AS n ON n.oid = t.relnamespace
            WHERE s.relkind = 'S' AND n.nspname = :schema AND t.relname = :table
            ORDER BY s.relname
            """
        ),
        {"schema": schema, "table": table},
    ).all()
    for _, old_name in rows:
        new_name = _mapped_name(str(old_name), rules)
        if new_name is None:
            continue
        if _relation_name_exists(conn, schema, new_name):
            raise RuntimeError(f"MATERIAL_NAME_CONFLICT schema={schema!r} relation={new_name!r}")
        conn.execute(sa.text(f"ALTER SEQUENCE {_qualified(schema, str(old_name))} RENAME TO {_quote(new_name)}"))


def _rename_material_tables(
    conn: sa.Connection,
    targets: set[str],
    *,
    forward: bool,
) -> None:
    source_table, target_table = ("documents", "materials") if forward else ("materials", "documents")
    source_column, target_column = ("doc_type", "material_type") if forward else ("material_type", "doc_type")
    graph_source, graph_target = (
        ("source_doc_id", "source_material_id") if forward else ("source_material_id", "source_doc_id")
    )
    citation_source, citation_target = graph_source, graph_target
    source_rules = _SOURCE_COLUMN_NAME_RULES if forward else _SOURCE_COLUMN_REVERSE_NAME_RULES

    for schema in sorted(targets):
        conn.execute(sa.text(f"ALTER TABLE {_qualified(schema, source_table)} RENAME TO {_quote(target_table)}"))
        conn.execute(
            sa.text(
                f"ALTER TABLE {_qualified(schema, target_table)} "
                f"RENAME COLUMN {_quote(source_column)} TO {_quote(target_column)}"
            )
        )
        rules = _FORWARD_NAME_RULES if forward else _REVERSE_NAME_RULES
        _rename_constraints_and_indexes(conn, schema, target_table, rules)
        _rename_owned_sequences(conn, schema, target_table, rules)

        if _column_exists(conn, schema, "graph_nodes", graph_source):
            conn.execute(
                sa.text(
                    f"ALTER TABLE {_qualified(schema, 'graph_nodes')} "
                    f"RENAME COLUMN {_quote(graph_source)} TO {_quote(graph_target)}"
                )
            )
            _rename_constraints_and_indexes(conn, schema, "graph_nodes", source_rules)
        if _column_exists(conn, schema, "writing_document_citations", citation_source):
            conn.execute(
                sa.text(
                    f"ALTER TABLE {_qualified(schema, 'writing_document_citations')} "
                    f"RENAME COLUMN {_quote(citation_source)} TO {_quote(citation_target)}"
                )
            )
            _rename_constraints_and_indexes(conn, schema, "writing_document_citations", source_rules)


def _topology_project_key(
    conn: sa.Connection,
    schema: str,
    registered_project_key: str | None,
) -> str | None:
    if not _column_exists(conn, schema, "information_topology_states", "project_key"):
        raise RuntimeError(
            f"MATERIAL_PREFLIGHT_FAILED information_topology_states.project_key is absent schema={schema!r}"
        )
    count = conn.execute(
        sa.text(f"SELECT count(*) FROM {_qualified(schema, 'information_topology_states')}")
    ).scalar_one()
    if int(count) == 0:
        return None
    values = (
        conn.execute(
            sa.text(
                "SELECT DISTINCT project_key FROM "
                + _qualified(schema, "information_topology_states")
                + " ORDER BY project_key"
            )
        )
        .scalars()
        .all()
    )
    if len(values) != 1:
        raise RuntimeError(f"MATERIAL_TOPOLOGY_PROJECT_KEY_CONFLICT schema={schema!r} values={values!r}")
    persisted_project_key = str(values[0])
    if registered_project_key is not None and persisted_project_key != registered_project_key:
        raise RuntimeError(
            "MATERIAL_TOPOLOGY_PROJECT_KEY_CONFLICT "
            f"schema={schema!r} registered={registered_project_key!r} "
            f"persisted={persisted_project_key!r}"
        )
    return registered_project_key or persisted_project_key


def _topology_calls(
    conn: sa.Connection,
    projects: dict[str, str],
    schemas: set[str],
) -> Iterator[tuple[str, str]]:
    topology_schemas = _table_schemas(conn, "information_topology_states")
    for schema in sorted(schemas & topology_schemas):
        project_key = _topology_project_key(conn, schema, projects.get(schema))
        if project_key is not None:
            yield project_key, schema


def _material_source_roots(
    project_keys: set[str],
    raw_arguments: Iterable[str],
) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    prefix = _SOURCE_ROOT_PARAMETER + "="
    for raw in raw_arguments:
        if not raw.startswith(prefix):
            continue
        assignment = raw[len(prefix) :]
        project_key, separator, path_value = assignment.partition("=")
        if not separator or not project_key or not path_value:
            raise RuntimeError(
                "MATERIAL_SOURCE_ROOT_INVALID expected material_source_root=<project_key>=<absolute-directory>"
            )
        if project_key not in project_keys:
            raise RuntimeError(f"MATERIAL_SOURCE_ROOT_UNKNOWN_PROJECT project={project_key!r}")
        if project_key in roots:
            raise RuntimeError(f"MATERIAL_SOURCE_ROOT_DUPLICATE project={project_key!r}")
        root = Path(path_value)
        if not root.is_absolute():
            raise RuntimeError(f"MATERIAL_SOURCE_ROOT_NOT_ABSOLUTE project={project_key!r} path={path_value!r}")
        if not root.is_dir():
            raise RuntimeError(f"MATERIAL_SOURCE_ROOT_NOT_DIRECTORY project={project_key!r} path={path_value!r}")
        roots[project_key] = root
    return roots


def _merge_topology_states(
    conn: sa.Connection,
    calls: tuple[tuple[str, str], ...],
    source_roots: dict[str, Path],
) -> None:
    from app.services.project_retrieval.topology import build_topology_service
    from app.services.projects.context import bind_resolved_project
    from sqlalchemy.orm import Session

    service = build_topology_service()
    material_schemas = _table_schemas(conn, "materials")
    original_search_path = str(conn.execute(sa.text("SHOW search_path")).scalar_one())
    for project_key, schema in calls:
        if schema not in material_schemas:
            raise RuntimeError(f"MATERIAL_TOPOLOGY_MATERIAL_TABLE_MISSING schema={schema!r} project={project_key!r}")
        conn.execute(sa.text(f"SET LOCAL search_path = {_quote(schema)}"))
        session: Session | None = None
        try:
            session = Session(
                bind=conn,
                join_transaction_mode="rollback_only",
                expire_on_commit=False,
            )
            with bind_resolved_project(project_key, schema):
                result = service.merge_materials_in_session(
                    session,
                    project_key,
                    source_root=source_roots.get(project_key),
                )
            if isinstance(result, Failure):
                context = dict(getattr(result, "context", {}) or {})
                raise RuntimeError(
                    "MATERIAL_TOPOLOGY_MIGRATION_FAILED "
                    f"code={getattr(result, 'code', 'UNKNOWN')!r} "
                    f"schema={schema!r} project={project_key!r} "
                    f"message={getattr(result, 'message', '')!r} context={context!r}"
                )
            migrated = int(result["migrated_states"])
            if migrated < 0:
                raise RuntimeError(f"MATERIAL_TOPOLOGY_MIGRATION_INVALID schema={schema!r} project={project_key!r}")
        finally:
            if session is not None:
                session.close()
            conn.execute(
                sa.text("SELECT set_config('search_path', :search_path, true)"),
                {"search_path": original_search_path},
            )


def upgrade() -> None:
    conn = op.get_bind()
    projects, targets = _preflight(conn)
    all_schemas = set(_schema_rows(conn)) - _RESERVED_SCHEMAS
    all_schemas = {schema for schema in all_schemas if not schema.startswith("pg_")}
    calls = tuple(_topology_calls(conn, projects, all_schemas))
    call_projects: dict[str, str] = {}
    for project_key, schema in calls:
        prior_schema = call_projects.setdefault(project_key, schema)
        if prior_schema != schema:
            raise RuntimeError(
                f"MATERIAL_TOPOLOGY_PROJECT_KEY_CONFLICT project={project_key!r} schemas={[prior_schema, schema]!r}"
            )
    source_roots = _material_source_roots(
        {project_key for project_key, _ in calls},
        context.get_x_argument(as_dictionary=False),
    )
    _rename_material_tables(conn, targets, forward=True)
    _merge_topology_states(conn, calls, source_roots)


def downgrade() -> None:
    conn = op.get_bind()
    targets = _table_schemas(conn, "materials")
    if _table_schemas(conn, "documents"):
        raise RuntimeError("MATERIAL_DOWNGRADE_CONFLICT both document table variants exist")
    # This reverses only storage identifiers.  Material topology revisions are
    # append-only business history and deliberately retain their current v3
    # payloads; a verified database snapshot is required for content rollback.
    _rename_material_tables(conn, targets, forward=False)


__all__ = [
    "revision",
    "down_revision",
    "upgrade",
    "downgrade",
    "_material_source_roots",
]
