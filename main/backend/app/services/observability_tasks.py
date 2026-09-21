from __future__ import annotations

from typing import Any

from ..celery_app import celery_app
from .task_readback_metadata import merge_request_runtime_context, merge_runtime_readback_payload


@celery_app.task(bind=True, name="task_stage5_worker_observability_probe")
def task_stage5_worker_observability_probe(
    self,
    *,
    request_id: str,
    run_id: str,
    trace_id: str,
    project_key: str,
    candidate_review_key: str,
    candidate_id: str,
    queue: str,
    line_key: str = "stage5_worker_probe",
    runtime_readback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a task-owned no-op worker chain without DB, provider, or IO effects."""

    runtime = merge_request_runtime_context(
        runtime_readback or {
            "line_key": line_key,
            "run_id": run_id,
            "trace_id": trace_id,
            "queue": queue,
        },
        getattr(self, "request", None),
        fallback_worker_name="stage5-eager-worker",
        fallback_queue=queue,
        status="running",
        event="worker_execution_started",
    )
    completed = merge_runtime_readback_payload(
        runtime,
        runtime,
        status="completed",
        event="worker_execution_completed",
        event_source="celery_worker",
    )
    return {
        "status": "completed",
        "request_id": request_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "project_key": project_key,
        "candidate_identity": {
            "candidate_review_key": candidate_review_key,
            "candidate_id": candidate_id,
            "source_payload_retained": False,
        },
        "effect_boundary": {
            "external_provider_calls": 0,
            "database_writes": 0,
            "filesystem_writes": 0,
            "queue_side_effects": 0,
        },
        "runtime_readback": completed,
    }
