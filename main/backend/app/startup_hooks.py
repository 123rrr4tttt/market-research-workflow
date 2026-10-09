from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.sql.schema import Table

from .models.base import engine, require_model_table
from .settings.config import settings
from .services.projects.schema_initialization import (
    ensure_database_revision_compatible,
    initialize_default_project_schema,
)
from .services.projects.bootstrap import (
    TENANT_TABLES,
    ensure_project_schema_ready,
    validate_project_schema,
)
from .services.project_retrieval.topology import build_topology_service
from .models.entities import (
    AgentApproval,
    AgentArtifact,
    AgentEvent,
    AgentMessage,
    AgentSession,
    AgentTask,
    ResourcePoolCaptureConfig,
    SharedIngestChannel,
    SharedResourcePoolSiteEntry,
    SharedResourcePoolUrl,
    SharedSourceLibraryItem,
    WorkflowGraphEvent,
    WorkflowGraphRun,
)


def register_startup_hooks(app: FastAPI) -> None:
    logger = logging.getLogger("app")

    app.state.information_topology_service = build_topology_service()

    def _ensure_default_project_schema() -> None:
        initialize_default_project_schema(logger_obj=logger)

    # This must precede every other FastAPI startup callback, including callbacks
    # already registered by app.main before this module is composed.
    app.router.on_startup.insert(0, _ensure_default_project_schema)

    def _ensure_bootstrap_projects() -> None:
        """
        Bootstrap control-plane projects with neutral defaults.

        Meaning:
        - First install: if no projects exist, create "business_survey" (商业调查) as the initial project.
        - All projects are peers. "public" schema is reserved for control-plane and shared tables.
        """
        with engine.begin() as conn:
            ensure_database_revision_compatible(conn)
            raw_count = conn.execute(text("SELECT COUNT(*) FROM public.projects")).scalar()
            count = raw_count if isinstance(raw_count, int) else 0
        if count == 0 and settings.bootstrap_create_initial_project:
            ensure_project_schema_ready("business_survey", name="商业调查")
        elif count == 0:
            logging.getLogger("app").info(
                "project bootstrap skipped: no projects found and bootstrap_create_initial_project=false"
            )

    app.router.add_event_handler("startup", _ensure_bootstrap_projects)

    def _ensure_all_project_schemas_ready() -> None:
        with engine.begin() as conn:
            ensure_database_revision_compatible(conn)
            rows = conn.execute(
                text(
                    "SELECT project_key, schema_name FROM public.projects "
                    "WHERE enabled = true"
                )
            ).fetchall()
            for _project_key, schema_name_value in rows:
                if not isinstance(schema_name_value, str) or not schema_name_value:
                    continue
                validate_project_schema(
                    conn,
                    schema_name=schema_name_value,
                    tables=TENANT_TABLES,
                )

    app.router.add_event_handler("startup", _ensure_all_project_schemas_ready)

    def _sync_llm_prompts_from_files() -> None:
        try:
            from scripts.sync_llm_prompts import sync_prompts

            prompts_dir = Path(__file__).resolve().parent.parent / "llm_prompts"
            if (prompts_dir / "default.yaml").exists():
                n = sync_prompts()
                logging.getLogger("app").info("LLM prompts synced: %d configs", n)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("app").warning("LLM prompts sync failed: %s", exc)

    app.router.add_event_handler("startup", _sync_llm_prompts_from_files)

    def _ensure_shared_library_tables_ready() -> None:
        shared_tables: list[Table] = [
            require_model_table(table)
            for table in (
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
            )
        ]
        with engine.begin() as conn:
            ensure_database_revision_compatible(conn)
            validate_project_schema(
                conn,
                schema_name="public",
                tables=shared_tables,
            )

    app.router.add_event_handler("startup", _ensure_shared_library_tables_ready)
