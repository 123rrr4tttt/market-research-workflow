from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

from .models.base import Base, engine
from .models.information_topology_entities import InformationTopologyLink, InformationTopologyState
from .models.project_retrieval import ProjectRetrievalMode, ProjectRetrievalPlan, ProjectRetrievalRun
from .models.base import SessionLocal
from .settings.config import settings
from .services.projects.schema_initialization import (
    initialize_default_project_schema,
    run_serialized_schema_ddl,
)
from .services.project_retrieval.topology import build_topology_service
from .models.entities import (
    AgentApproval,
    AgentArtifact,
    AgentEvent,
    AgentMessage,
    AgentSession,
    AgentTask,
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
    ResourcePoolCaptureConfig,
    ResourcePoolSiteEntry,
    ResourcePoolUrl,
    SearchHistory,
    SharedIngestChannel,
    SharedResourcePoolSiteEntry,
    SharedResourcePoolUrl,
    SharedSourceLibraryItem,
    Source,
    SourceLibraryItem,
    Topic,
    WorkflowGraphEvent,
    WorkflowGraphRun,
)
from .models.llm_report_export_audit import LlmReportExportAuditEvent
from .models.llm_report_export_token_state import LlmReportExportTokenState
from .models.llm_report_trends import LlmReportQualityTrend
from .models.writing_entities import WritingDocument, WritingDocumentCitation, WritingDocumentDraft


def register_startup_hooks(app: FastAPI) -> None:
    logger = logging.getLogger("app")

    app.state.information_topology_service = build_topology_service()
    @app.on_event("startup")
    def _ensure_default_project_schema() -> None:
        initialize_default_project_schema(logger_obj=logger)

    def _is_missing_vector_type(exc: Exception) -> bool:
        message = str(exc).lower()
        return "vector" in message and "does not exist" in message

    def _create_tenant_tables_best_effort(schema_name: str, tenant_tables: list) -> None:
        def _create(conn: object) -> None:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
            conn.execute(text(f'SET search_path TO "{schema_name}", public'))
            for table in tenant_tables:
                try:
                    with conn.begin_nested():
                        table.create(bind=conn, checkfirst=True)
                except Exception as exc:  # noqa: BLE001
                    table_name = getattr(table, "name", "")
                    if table_name == "embeddings" and _is_missing_vector_type(exc):
                        logger.warning(
                            "skip embeddings table for schema=%s because vector type is unavailable in current search_path: %s",
                            schema_name,
                            exc,
                        )
                        continue
                    raise

        run_serialized_schema_ddl(
            engine,
            schema_name=schema_name,
            operation=_create,
        )

    @app.on_event("startup")
    def _ensure_bootstrap_projects() -> None:
        """
        Bootstrap control-plane projects with neutral defaults.

        Meaning:
        - First install: if no projects exist, create "business_survey" (商业调查) as the initial project.
        - All projects are peers. "public" schema is reserved for control-plane and shared tables.
        """
        try:
            def _bootstrap(conn: object) -> None:
                conn.execute(text('SET search_path TO "public"'))

                count = conn.execute(text("SELECT COUNT(*) FROM public.projects")).scalar() or 0
                if int(count) == 0 and bool(getattr(settings, "bootstrap_create_initial_project", False)):
                    conn.execute(
                        text(
                            """
                            INSERT INTO public.projects(project_key, name, schema_name, enabled, is_active, created_at, updated_at)
                            VALUES (:project_key, :name, :schema_name, true, true, now(), now())
                            """
                        ),
                        {
                            "project_key": "business_survey",
                            "name": "商业调查",
                            "schema_name": "project_business_survey",
                        },
                    )
                elif int(count) == 0:
                    logging.getLogger("app").info(
                        "project bootstrap skipped: no projects found and bootstrap_create_initial_project=false"
                    )

                has_public_docs = conn.execute(text("SELECT to_regclass('public.documents') IS NOT NULL")).scalar()
                neutral_schema = f'{settings.project_schema_prefix}{settings.active_project_key}'
                has_target_docs = conn.execute(
                    text(f"SELECT to_regclass('{neutral_schema}.documents') IS NOT NULL")
                ).scalar()
                if has_public_docs and not has_target_docs:
                    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{neutral_schema}"'))
                    tenant_tables = [
                        "sources",
                        "documents",
                        "market_stats",
                        "config_states",
                        "embeddings",
                        "etl_job_runs",
                        "search_history",
                        "llm_service_configs",
                        "topics",
                        "ingest_channels",
                        "source_library_items",
                        "market_metric_points",
                        "products",
                        "price_observations",
                        "resource_pool_urls",
                    ]
                    for t in tenant_tables:
                        conn.execute(text(f'ALTER TABLE IF EXISTS public."{t}" SET SCHEMA "{neutral_schema}"'))
                    for t in tenant_tables:
                        conn.execute(
                            text(f'ALTER SEQUENCE IF EXISTS public."{t}_id_seq" SET SCHEMA "{neutral_schema}"')
                        )

            run_serialized_schema_ddl(
                engine,
                schema_name="public",
                operation=_bootstrap,
            )
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("app").warning("failed to bootstrap projects: %s", exc)

    @app.on_event("startup")
    def _ensure_all_project_schemas_ready() -> None:
        tenant_tables = [
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
            LlmReportQualityTrend.__table__,
            LlmReportExportAuditEvent.__table__,
            LlmReportExportTokenState.__table__,
            WritingDocument.__table__,
            WritingDocumentDraft.__table__,
            WritingDocumentCitation.__table__,
            InformationTopologyState.__table__,
            InformationTopologyLink.__table__,
            ProjectRetrievalMode.__table__,
            ProjectRetrievalPlan.__table__,
            ProjectRetrievalRun.__table__,
        ]
        try:
            with engine.begin() as conn:
                rows = conn.execute(
                    text("SELECT project_key, schema_name FROM public.projects WHERE enabled = true")
                ).fetchall()
            for _project_key, schema_name in rows:
                if not schema_name:
                    continue
                _create_tenant_tables_best_effort(schema_name, tenant_tables)
        except Exception as exc:  # noqa: BLE001
            logger.warning("failed to ensure project schemas ready: %s", exc)

    @app.on_event("startup")
    def _sync_llm_prompts_from_files() -> None:
        try:
            from scripts.sync_llm_prompts import sync_prompts

            prompts_dir = Path(__file__).resolve().parent.parent / "llm_prompts"
            if (prompts_dir / "default.yaml").exists():
                n = sync_prompts()
                logging.getLogger("app").info("LLM prompts synced: %d configs", n)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("app").warning("LLM prompts sync failed: %s", exc)

    @app.on_event("startup")
    def _ensure_shared_library_tables_ready() -> None:
        shared_tables = [
            AgentSession.__table__,
            AgentTask.__table__,
            AgentMessage.__table__,
            AgentArtifact.__table__,
            AgentEvent.__table__,
            AgentApproval.__table__,
            SharedIngestChannel.__table__,
            SharedSourceLibraryItem.__table__,
            SharedResourcePoolUrl.__table__,
            SharedResourcePoolSiteEntry.__table__,
            ResourcePoolCaptureConfig.__table__,
            WorkflowGraphRun.__table__,
            WorkflowGraphEvent.__table__,
        ]
        try:
            def _create_shared_tables(conn: object) -> None:
                conn.execute(text('SET search_path TO "public"'))
                Base.metadata.create_all(bind=conn, tables=shared_tables, checkfirst=True)

            run_serialized_schema_ddl(
                engine,
                schema_name="public",
                operation=_create_shared_tables,
            )
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("app").warning("failed to ensure shared source-library tables ready: %s", exc)
