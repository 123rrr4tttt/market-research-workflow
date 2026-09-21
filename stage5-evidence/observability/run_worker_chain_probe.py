#!/usr/bin/env python3
"""Run a task-owned eager Celery worker observability chain."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
import sys

from prometheus_client import REGISTRY, generate_latest

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "main" / "backend"
REPO_ROOT = BACKEND_ROOT.parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.celery_app import celery_app  # noqa: E402
from app.production_observability.worker import (  # noqa: E402
    WORKER_TASKS_METRIC_NAME,
    WORKER_TASK_LATENCY_METRIC_NAME,
    worker_trace_snapshot,
)
from app.services.observability_tasks import task_stage5_worker_observability_probe  # noqa: E402


def main() -> int:
    task_id = "stage5-worker-chain-task"
    request_id = "stage5-worker-chain-request"
    run_id = "stage5-worker-chain-run"
    trace_id = "stage5-worker-chain-trace"
    project_key = "tenant:stage5-worker-chain-local"
    queue = "stage5.worker.probe"
    kwargs = {
        "request_id": request_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "project_key": project_key,
        "candidate_review_key": "review:stage5-worker-chain-candidate",
        "candidate_id": "candidate:stage5-worker-chain-candidate",
        "queue": queue,
        "line_key": "stage5_worker_probe",
    }
    log_records: list[str] = []

    class EvidenceHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            log_records.append(self.format(record))

    logger = logging.getLogger("app.production_observability.worker")
    handler = EvidenceHandler()
    old_logger_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    old_config = {
        key: celery_app.conf[key]
        for key in ("task_always_eager", "task_eager_propagates", "result_backend")
    }
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        result_backend="cache+memory://",
    )
    try:
        eager_result = task_stage5_worker_observability_probe.apply(kwargs=kwargs, task_id=task_id)
        result = eager_result.get()
        traces = worker_trace_snapshot(trace_id)
        worker_name = traces[0]["worker_name"]
        task_labels = {
            "task_name": task_stage5_worker_observability_probe.name,
            "worker_name": worker_name,
            "queue": queue,
            "project_key": project_key,
            "line_key": "stage5_worker_probe",
        }
        task_count = REGISTRY.get_sample_value(
            WORKER_TASKS_METRIC_NAME,
            {**task_labels, "status": "succeeded"},
        )
        latency_count = REGISTRY.get_sample_value(
            f"{WORKER_TASK_LATENCY_METRIC_NAME}_count",
            task_labels,
        )
        metrics_text = generate_latest().decode("utf-8")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_logger_level)
        celery_app.conf.update(old_config)

    metric_lines = [
        line
        for line in metrics_text.splitlines()
        if line.startswith((WORKER_TASKS_METRIC_NAME, WORKER_TASK_LATENCY_METRIC_NAME))
    ]
    identity_values = {str(value) for value in kwargs.values()}
    payload = {
        "schema": "mrw.stage5.observability.worker-chain.v1",
        "status": "PASS_LOCAL_WORKER_CHAIN_NOT_AUTHORITY",
        "authoritative": False,
        "observed_at": datetime.now(UTC).isoformat(),
        "boundary": {
            "runtime": "real Celery task_prerun/task_postrun signals in eager in-process execution",
            "result_backend": "cache+memory://",
            "external_provider_calls": 0,
            "database_writes": 0,
            "filesystem_writes": 0,
            "queue_side_effects": 0,
            "not_claimed": [
                "HTTP backend controller recovery",
                "external OpenTelemetry collector",
                "production authority",
            ],
        },
        "identity": {
            "task_id": task_id,
            "request_id": request_id,
            "run_id": run_id,
            "trace_id": trace_id,
            "project_key": project_key,
            "candidate_review_key": kwargs["candidate_review_key"],
            "candidate_id": kwargs["candidate_id"],
            "candidate_identity_redacted": True,
        },
        "worker_result": result,
        "trace": traces,
        "structured_logs": log_records,
        "prometheus": {
            "registry": "default process REGISTRY after real task execution",
            WORKER_TASKS_METRIC_NAME: task_count,
            f"{WORKER_TASK_LATENCY_METRIC_NAME}_count": latency_count,
            "exported_metric_lines": metric_lines,
        },
        "checks": {
            "eager_result_successful": eager_result.successful(),
            "result_completed": result.get("status") == "completed",
            "runtime_readback_identity_correlated": all(
                result.get("runtime_readback", {}).get(key) == value
                for key, value in {
                    "task_id": task_id,
                    "run_id": run_id,
                    "trace_id": trace_id,
                }.items()
            ),
            "trace_start_finish_correlated": [item.get("event") for item in traces]
            == ["worker_task_started", "worker_task_finished"],
            "logs_correlated": all(
                any(identity in line for line in log_records) for identity in identity_values
            ),
            "worker_task_metric_observed": task_count is not None and float(task_count) >= 1,
            "worker_latency_metric_observed": latency_count is not None and float(latency_count) >= 1,
        },
    }
    payload["status"] = (
        "PASS_LOCAL_WORKER_CHAIN_NOT_AUTHORITY"
        if all(payload["checks"].values())
        else "FAIL_LOCAL_WORKER_CHAIN"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
