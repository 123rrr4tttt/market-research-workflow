from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.schema import Table

from ...models.base import engine
from ...models.information_topology_entities import InformationTopologyLink, InformationTopologyState
from ...models.ingest_registry import IngestSubmissionRegistry
from ...models.project_retrieval import project_retrieval_tables
from ...models.entities import (
    ConfigState,
    Material,
    Embedding,
    EtlJobRun,
    GraphEdgeRecord,
    GraphNodeAliasRecord,
    GraphNodeRecord,
    IngestChannel,
    KeywordHistory,
    KeywordPrior,
    LlmServiceConfig,
    MarketMetricPoint,
    MarketStat,
    PriceObservation,
    Product,
    ResourcePoolSiteEntry,
    ResourcePoolUrl,
    SearchHistory,
    Source,
    SourceLibraryItem,
    Topic,
)
from ...models.writing_entities import WritingDocument, WritingDocumentCitation, WritingDocumentDraft
from .context import normalize_project_key, project_schema_name
from .schema_initialization import (
    ensure_database_revision_compatible,
    run_serialized_schema_ddl,
)


logger = logging.getLogger(__name__)


_TENANT_TABLE_CANDIDATES = [
    Source.__table__,
    Material.__table__,
    GraphNodeRecord.__table__,
    GraphNodeAliasRecord.__table__,
    GraphEdgeRecord.__table__,
    MarketStat.__table__,
    ConfigState.__table__,
    Embedding.__table__,
    EtlJobRun.__table__,
    SearchHistory.__table__,
    KeywordHistory.__table__,
    KeywordPrior.__table__,
    LlmServiceConfig.__table__,
    IngestSubmissionRegistry.__table__,
    Topic.__table__,
    IngestChannel.__table__,
    SourceLibraryItem.__table__,
    MarketMetricPoint.__table__,
    Product.__table__,
    PriceObservation.__table__,
    ResourcePoolUrl.__table__,
    ResourcePoolSiteEntry.__table__,
    WritingDocument.__table__,
    WritingDocumentDraft.__table__,
    WritingDocumentCitation.__table__,
    InformationTopologyState.__table__,
    InformationTopologyLink.__table__,
    *project_retrieval_tables(),
]


def _require_table(value: object) -> Table:
    if isinstance(value, Table):
        return value
    raise TypeError("tenant table candidate must be a SQLAlchemy Table")


TENANT_TABLES: list[Table] = [_require_table(table) for table in _TENANT_TABLE_CANDIDATES]
_OPTIONAL_TENANT_TABLES = frozenset({"embeddings"})


class ProjectSchemaIncompatibleError(RuntimeError):
    """A registered schema is missing canonical tables or columns."""

    def __init__(
        self,
        *,
        schema_name: str,
        missing_tables: tuple[str, ...] = (),
        missing_columns: tuple[str, ...] = (),
    ) -> None:
        self.schema_name = schema_name
        self.missing_tables = missing_tables
        self.missing_columns = missing_columns
        super().__init__(
            "PROJECT_SCHEMA_INCOMPATIBLE "
            f"schema={schema_name} missing_tables={','.join(missing_tables) or '<none>'} "
            f"missing_columns={','.join(missing_columns) or '<none>'}; run migration or repair"
        )


def _is_missing_vector_type(exc: Exception) -> bool:
    message = str(exc).lower()
    return "vector" in message and "does not exist" in message


def tenant_table_exists(
    connection: Connection,
    *,
    schema_name: str,
    table_name: str,
) -> bool:
    """Check the tenant namespace directly without search_path fallback."""
    exists = connection.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=:schema_name AND table_name=:table_name)"
        ),
        {"schema_name": schema_name, "table_name": table_name},
    ).scalar()
    return bool(exists)


def validate_project_schema(
    connection: Connection,
    *,
    schema_name: str,
    tables: list[Table] | None = None,
) -> None:
    """Validate canonical tables from native metadata without publishing DDL."""
    declared_tables = TENANT_TABLES if tables is None else tables
    inspector = inspect(connection)
    missing_tables: list[str] = []
    missing_columns: list[str] = []
    for table in declared_tables:
        if not inspector.has_table(table.name, schema=schema_name):
            if table.name not in _OPTIONAL_TENANT_TABLES:
                missing_tables.append(table.name)
            continue
        actual_columns = {
            str(column["name"])
            for column in inspector.get_columns(table.name, schema=schema_name)
        }
        for column in table.columns:
            if column.name not in actual_columns:
                missing_columns.append(f"{table.name}.{column.name}")
    if missing_tables or missing_columns:
        raise ProjectSchemaIncompatibleError(
            schema_name=schema_name,
            missing_tables=tuple(sorted(missing_tables)),
            missing_columns=tuple(sorted(missing_columns)),
        )


def _registered_project(connection: Connection, project_key: str) -> tuple[str, str] | None:
    row = connection.execute(
        text(
            "SELECT project_key, schema_name FROM public.projects "
            "WHERE project_key=:project_key"
        ),
        {"project_key": project_key},
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), str(row[1])


def _schema_has_relations(connection: Connection, schema_name: str) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_class AS c "
                "JOIN pg_namespace AS n ON n.oid=c.relnamespace "
                "WHERE n.nspname=:schema_name)"
            ),
            {"schema_name": schema_name},
        ).scalar()
    )


def ensure_project_schema_ready(
    project_key: str,
    *,
    name: str | None = None,
    enabled: bool = True,
) -> dict[str, str]:
    """Validate registered projects or atomically initialize one empty project."""
    normalized = normalize_project_key(project_key)
    schema_name = project_schema_name(normalized)
    display_name = (name or normalized.replace("_", " ").title()).strip() or normalized

    result: dict[str, str] = {}

    def _initialize(conn: Connection) -> None:
        ensure_database_revision_compatible(conn)
        conn.execute(text('SET search_path TO "public"'))
        registered = _registered_project(conn, normalized)
        if registered is not None:
            registered_key, registered_schema = registered
            validate_project_schema(conn, schema_name=registered_schema)
            result.update(project_key=registered_key, schema_name=registered_schema)
            return

        if _schema_has_relations(conn, schema_name):
            raise ProjectSchemaIncompatibleError(
                schema_name=schema_name,
                missing_tables=("unowned_nonempty_schema",),
            )

        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        conn.execute(text(f'SET search_path TO "{schema_name}", public'))
        for table in TENANT_TABLES:
            if tenant_table_exists(
                conn,
                schema_name=schema_name,
                table_name=table.name,
            ):
                continue
            try:
                with conn.begin_nested():
                    table.create(bind=conn, checkfirst=False)
            except SQLAlchemyError as exc:
                table_name = table.name
                if table_name == "embeddings" and _is_missing_vector_type(exc):
                    logger.warning(
                        "skip embeddings table for schema=%s because vector type is unavailable: %s",
                        schema_name,
                        exc,
                    )
                    continue
                raise

        _ensure_tenant_id_sequences(schema_name, connection=conn)
        conn.execute(text('SET search_path TO "public"'))
        conn.execute(
            text(
                """
                INSERT INTO public.projects(project_key, name, schema_name, enabled, is_active, created_at, updated_at)
                VALUES (:project_key, :name, :schema_name, :enabled, false, now(), now())
                """
            ),
            {
                "project_key": normalized,
                "name": display_name,
                "schema_name": schema_name,
                "enabled": enabled,
            },
        )
        result.update(project_key=normalized, schema_name=schema_name)

    run_serialized_schema_ddl(
        engine,
        schema_name=schema_name,
        operation=_initialize,
    )
    return result


def _ensure_tenant_id_sequences(schema_name: str, *, connection: Connection) -> None:
    table_names = [table.name for table in TENANT_TABLES if "id" in table.c]
    for table_name in table_names:
        connection.execute(
            text(
                """
                    DO $$
                    DECLARE
                      seq_qualified text := format('%I.%I_id_seq', :schema_name, :table_name);
                      table_qualified text := format('%I.%I', :schema_name, :table_name);
                      has_table regclass;
                    BEGIN
                      EXECUTE format('SELECT to_regclass(%L)', table_qualified) INTO has_table;
                      IF has_table IS NULL THEN
                        RETURN;
                      END IF;

                      EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %s', seq_qualified);
                      EXECUTE format('ALTER SEQUENCE %s OWNED BY %I.%I.id', seq_qualified, :schema_name, :table_name);
                      EXECUTE format(
                        'ALTER TABLE %I.%I ALTER COLUMN id SET DEFAULT nextval(%L::regclass)',
                        :schema_name, :table_name, seq_qualified
                      );
                      EXECUTE format(
                        'SELECT setval(%L, COALESCE((SELECT MAX(id) FROM %I.%I), 0) + 1, false)',
                        seq_qualified, :schema_name, :table_name
                      );
                    END$$;
                """
            ),
            {"schema_name": schema_name, "table_name": table_name},
        )
