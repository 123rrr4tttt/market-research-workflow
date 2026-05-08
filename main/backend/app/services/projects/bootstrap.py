from __future__ import annotations

import logging

from sqlalchemy import text

from ...models.base import engine
from ...models.entities import (
    ConfigState,
    Document,
    Embedding,
    EtlJobRun,
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
from .context import _normalize_project_key, project_schema_name


logger = logging.getLogger(__name__)


TENANT_TABLES = [
    Source.__table__,
    Document.__table__,
    MarketStat.__table__,
    ConfigState.__table__,
    Embedding.__table__,
    EtlJobRun.__table__,
    SearchHistory.__table__,
    KeywordHistory.__table__,
    KeywordPrior.__table__,
    LlmServiceConfig.__table__,
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
]


def _is_missing_vector_type(exc: Exception) -> bool:
    message = str(exc).lower()
    return "vector" in message and "does not exist" in message


def ensure_project_schema_ready(project_key: str, *, name: str | None = None) -> dict[str, str]:
    """Ensure a project can run tenant-scoped scripts outside FastAPI startup."""
    normalized = _normalize_project_key(project_key)
    schema_name = project_schema_name(normalized)
    display_name = (name or normalized.replace("_", " ").title()).strip() or normalized

    with engine.begin() as conn:
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

    for table in TENANT_TABLES:
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO "{schema_name}"'))
            try:
                table.create(bind=conn, checkfirst=True)
            except Exception as exc:  # noqa: BLE001
                table_name = getattr(table, "name", "")
                if table_name == "embeddings" and _is_missing_vector_type(exc):
                    logger.warning(
                        "skip embeddings table for schema=%s because vector type is unavailable: %s",
                        schema_name,
                        exc,
                    )
                    continue
                raise

    _ensure_tenant_id_sequences(schema_name)
    return {"project_key": normalized, "schema_name": schema_name}


def _ensure_tenant_id_sequences(schema_name: str) -> None:
    table_names = [table.name for table in TENANT_TABLES if "id" in table.c]
    for table_name in table_names:
        with engine.begin() as conn:
            conn.execute(
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
