from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

from .models.base import Base, engine
from .settings.config import settings
from .models.entities import (
    ConfigState,
    Document,
    Embedding,
    EtlJobRun,
    IngestChannel,
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
)


def register_startup_hooks(app: FastAPI) -> None:
    @app.on_event("startup")
    def _ensure_bootstrap_projects() -> None:
        """
        Bootstrap control-plane projects with neutral defaults.

        Meaning:
        - Optional one-time migration: legacy project_key "default" -> "online_lottery"
          (schema rename, table moves, aggregator remap), controlled by
          `enable_legacy_default_to_online_lottery_migration`.
        - First install: if no projects exist, create "business_survey" (商业调查) as the initial project.
        - All projects are peers. "public" schema is reserved for control-plane and shared tables.
        """
        try:
            with engine.begin() as conn:
                conn.execute(text('SET search_path TO "public"'))

                legacy = conn.execute(
                    text("SELECT project_key, schema_name FROM public.projects WHERE project_key = 'default' LIMIT 1")
                ).first()
                if legacy and bool(getattr(settings, "enable_legacy_default_to_online_lottery_migration", False)):
                    has_old_schema = conn.execute(
                        text("SELECT to_regclass('project_default.documents') IS NOT NULL")
                    ).scalar()
                    has_new_schema = conn.execute(
                        text("SELECT to_regclass('project_online_lottery.documents') IS NOT NULL")
                    ).scalar()
                    if has_old_schema and not has_new_schema:
                        target_has_any = conn.execute(
                            text(
                                """
                                SELECT EXISTS(
                                  SELECT 1 FROM pg_tables WHERE schemaname='project_online_lottery' LIMIT 1
                                )
                                """
                            )
                        ).scalar()
                        if not target_has_any:
                            conn.execute(text('DROP SCHEMA IF EXISTS "project_online_lottery" CASCADE'))
                        conn.execute(text('ALTER SCHEMA "project_default" RENAME TO "project_online_lottery"'))

                    conn.execute(
                        text(
                            """
                            UPDATE public.projects
                            SET project_key = 'online_lottery',
                                name = COALESCE(NULLIF(name, ''), '线上彩票项目'),
                                schema_name = 'project_online_lottery'
                            WHERE project_key = 'default'
                            """
                        )
                    )
                    conn.execute(
                        text("UPDATE public.project_sync_state SET project_key='online_lottery' WHERE project_key='default'")
                    )
                    conn.execute(text('CREATE SCHEMA IF NOT EXISTS "aggregator"'))
                    for t in ["documents_agg", "market_metric_points_agg", "price_observations_agg"]:
                        exists = conn.execute(text(f"SELECT to_regclass('aggregator.{t}') IS NOT NULL")).scalar()
                        if exists:
                            conn.execute(
                                text(
                                    f'UPDATE aggregator."{t}" SET project_key = \'online_lottery\' WHERE project_key = \'default\''
                                )
                            )

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
            LlmServiceConfig.__table__,
            Topic.__table__,
            IngestChannel.__table__,
            SourceLibraryItem.__table__,
            MarketMetricPoint.__table__,
            Product.__table__,
            PriceObservation.__table__,
            ResourcePoolUrl.__table__,
            ResourcePoolSiteEntry.__table__,
        ]
        try:
            with engine.begin() as conn:
                rows = conn.execute(
                    text("SELECT project_key, schema_name FROM public.projects WHERE enabled = true")
                ).fetchall()
                for _project_key, schema_name in rows:
                    if not schema_name:
                        continue
                    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
                    conn.execute(text(f'SET search_path TO "{schema_name}"'))
                    Base.metadata.create_all(bind=conn, tables=tenant_tables, checkfirst=True)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("app").warning("failed to ensure project schemas ready: %s", exc)

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
            SharedIngestChannel.__table__,
            SharedSourceLibraryItem.__table__,
            SharedResourcePoolUrl.__table__,
            SharedResourcePoolSiteEntry.__table__,
            ResourcePoolCaptureConfig.__table__,
        ]
        try:
            with engine.begin() as conn:
                conn.execute(text('SET search_path TO "public"'))
                Base.metadata.create_all(bind=conn, tables=shared_tables, checkfirst=True)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("app").warning("failed to ensure shared source-library tables ready: %s", exc)
