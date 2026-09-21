from __future__ import annotations

from celery import Celery, signals
from celery.exceptions import WorkerTerminate

from .composition.collect_runtime import configure_default_collect_adapters
from .composition.ingest import configure_ingest_adapters
from .composition.llm import configure_llm_providers
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
    "lottery_intel",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

install_worker_observability()

celery_app.autodiscover_tasks(["app.services.tasks", "app.services.observability_tasks"])
install_worker_telemetry(celery_app)


def initialize_celery_worker_schema() -> bool:
    """Initialize schema in each worker child before it can consume tasks."""
    try:
        return initialize_default_project_schema()
    except Exception as exc:  # noqa: BLE001
        # Celery Signal.send swallows Exception receivers. WorkerTerminate is a
        # BaseException so a production bootstrap failure actually stops the child.
        raise WorkerTerminate(1) from exc


@signals.worker_process_init.connect(weak=False)
def _initialize_celery_worker_schema(**_kwargs: object) -> None:
    initialize_celery_worker_schema()
