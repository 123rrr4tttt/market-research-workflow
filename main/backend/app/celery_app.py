from __future__ import annotations

import logging

from celery import Celery, signals
from celery.exceptions import WorkerTerminate

from .composition.collect_runtime import configure_default_collect_adapters
from .composition.ingest import configure_ingest_adapters
from .composition.llm import configure_llm_providers
from .models.base import engine
from .production_observability.worker import install_worker_observability
from .composition.resource_pool import configure_resource_pool_ports
from .composition.source_library import configure_source_library_adapters
from .production_observability.worker_telemetry import install_worker_telemetry
from .settings.config import settings
from .services.projects.schema_initialization import initialize_default_project_schema


configure_default_collect_adapters()
configure_resource_pool_ports()
configure_ingest_adapters()
configure_llm_providers()
configure_source_library_adapters()


celery_app = Celery(
    "market_research_workflow",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

install_worker_observability()

celery_app.autodiscover_tasks(["app.services.tasks", "app.services.observability_tasks"])
install_worker_telemetry(celery_app)


def _initialize_celery_worker_schema(sender: object, **_kwargs: object) -> None:
    """Require the database in the main worker before any pool or consumer starts."""
    if getattr(sender, "app", None) is not celery_app:
        return

    try:
        initialize_default_project_schema(fail_closed=True)
        # Do not let prefork children inherit the parent's preflight connection.
        engine.dispose()
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).exception("Celery worker database startup failed")
        # Celery Signal.send catches Exception but lets WorkerTerminate stop startup.
        raise WorkerTerminate(1) from exc


signals.worker_init.connect(_initialize_celery_worker_schema, weak=False)
