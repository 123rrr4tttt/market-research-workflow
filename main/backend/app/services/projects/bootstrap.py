from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.schema import Table

from ...models.base import engine
from ...models.information_topology_entities import InformationTopologyLink, InformationTopologyState
from ...models.ingest_registry import IngestSubmissionRegistry
from ...models.project_retrieval import project_retrieval_tables
from ...models.entities import (
    ConfigState,
    Document,
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
from .schema_initialization import run_serialized_schema_ddl


logger = logging.getLogger(__name__)


_TENANT_TABLE_CANDIDATES = [
    Source.__table__,
    Document.__table__,
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


def ensure_project_schema_ready(project_key: str, *, name: str | None = None) -> dict[str, str]:
    """Ensure a project can run tenant-scoped scripts outside FastAPI startup."""
    normalized = normalize_project_key(project_key)
    schema_name = project_schema_name(normalized)
    display_name = (name or normalized.replace("_", " ").title()).strip() or normalized

    def _initialize(conn: Connection) -> None:
        conn.execute(text('SET search_path TO "public"'))
        conn.execute(
            text(
                """
                INSERT INTO public.projects(project_key, name, schema_name, enabled, is_active, created_at, updated_at)
                VALUES (:project_key, :name, :schema_name, true, false, now(), now())
                ON CONFLICT (project_key) DO UPDATE
                SET schema_name = EXCLUDED.schema_name,
                    enabled = true,
                    updated_at = now()
                """
            ),
            {"project_key": normalized, "name": display_name, "schema_name": schema_name},
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

    run_serialized_schema_ddl(
        engine,
        schema_name=schema_name,
        operation=_initialize,
    )
    return {"project_key": normalized, "schema_name": schema_name}


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
