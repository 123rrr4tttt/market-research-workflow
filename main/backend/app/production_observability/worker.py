from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json
from threading import RLock
import time
from typing import Any, Mapping

from celery import signals
from prometheus_client import Counter, Histogram


WORKER_TASKS_METRIC_NAME = "market_api_production_observability_worker_tasks_total"
WORKER_TASK_LATENCY_METRIC_NAME = "market_api_production_observability_worker_task_duration_seconds"

WORKER_TASKS = Counter(
    WORKER_TASKS_METRIC_NAME,
    "Celery task executions by bounded worker/project/status labels",
    ("task_name", "worker_name", "queue", "project_key", "line_key", "status"),
)
WORKER_TASK_LATENCY = Histogram(
    WORKER_TASK_LATENCY_METRIC_NAME,
    "Celery task duration by bounded worker/project labels",
    ("task_name", "worker_name", "queue", "project_key", "line_key"),
)

_LOGGER = __name__
_MAX_TRACES = 128


@dataclass
class _WorkerTaskContext:
    task_id: str
    task_name: str
    worker_name: str
    queue: str
    project_key: str
    line_key: str
    request_id: str
    run_id: str
    trace_id: str
    candidate_review_key: str
    candidate_id: str
    started_monotonic: float


_LOCK = RLock()
_CONTEXTS: dict[str, _WorkerTaskContext] = {}
_TRACE_ORDER: deque[str] = deque()
_TRACES: dict[str, list[dict[str, Any]]] = {}
_INSTALLED = False


def _identity(value: Any, *, fallback: str = "unknown", label: bool = False) -> str:
    text = str(value or "").strip() or fallback
    if label:
        return text[:128]
    if len(text) <= 128 and all(char.isprintable() for char in text):
        return text
    digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
    return f"sha256:{digest}"


def _runtime_identity(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    readback = kwargs.get("runtime_readback")
    source = readback if isinstance(readback, Mapping) else kwargs
    return dict(source)


def _context(
    *,
    task_name: str,
    task_request: Any,
    kwargs: Mapping[str, Any],
) -> _WorkerTaskContext:
    runtime = _runtime_identity(kwargs)
    delivery_info = getattr(task_request, "delivery_info", None)
    if not isinstance(delivery_info, Mapping):
        delivery_info = {}
    return _WorkerTaskContext(
        task_id=_identity(getattr(task_request, "id", None), fallback="unknown"),
        task_name=_identity(task_name or getattr(task_request, "task", None), label=True),
        worker_name=_identity(getattr(task_request, "hostname", None), label=True),
        queue=_identity(
            kwargs.get("queue")
            or runtime.get("queue")
            or delivery_info.get("routing_key")
            or delivery_info.get("queue"),
            label=True,
        ),
        project_key=_identity(kwargs.get("project_key"), label=True),
        line_key=_identity(kwargs.get("line_key") or runtime.get("line_key"), label=True),
        request_id=_identity(kwargs.get("request_id") or runtime.get("request_id")),
        run_id=_identity(kwargs.get("workflow_run_id") or runtime.get("run_id")),
        trace_id=_identity(kwargs.get("trace_id") or runtime.get("trace_id")),
        candidate_review_key=_identity(
            kwargs.get("candidate_review_key") or runtime.get("candidate_review_key"),
        ),
        candidate_id=_identity(kwargs.get("candidate_id") or runtime.get("candidate_id")),
        started_monotonic=time.monotonic(),
    )


def _event(context: _WorkerTaskContext, event: str, **extra: Any) -> dict[str, Any]:
    return {
        "event": event,
        "timestamp": time.time(),
        "task_id": context.task_id,
        "task_name": context.task_name,
        "worker_name": context.worker_name,
        "queue": context.queue,
        "project_key": context.project_key,
        "line_key": context.line_key,
        "request_id": context.request_id,
        "run_id": context.run_id,
        "trace_id": context.trace_id,
        "candidate_review_key": context.candidate_review_key,
        "candidate_id": context.candidate_id,
        "candidate_identity_redacted": True,
        **extra,
    }


def _emit(event_payload: Mapping[str, Any]) -> None:
    import logging

    logging.getLogger(_LOGGER).info(
        "%s",
        json.dumps(dict(event_payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def _remember_trace(trace_id: str, event_payload: Mapping[str, Any]) -> None:
    if trace_id in _TRACES:
        _TRACES[trace_id].append(dict(event_payload))
        return
    _TRACES[trace_id] = [dict(event_payload)]
    _TRACE_ORDER.append(trace_id)
    while len(_TRACE_ORDER) > _MAX_TRACES:
        _TRACES.pop(_TRACE_ORDER.popleft(), None)


def observe_worker_task_started(
    *,
    task_name: str,
    task_request: Any,
    kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    context = _context(task_name=task_name, task_request=task_request, kwargs=kwargs)
    event_payload = _event(context, "worker_task_started")
    with _LOCK:
        _CONTEXTS[context.task_id] = context
        _remember_trace(context.trace_id, event_payload)
    _emit(event_payload)
    return dict(event_payload)


def observe_worker_task_finished(
    *,
    task_name: str,
    task_request: Any,
    kwargs: Mapping[str, Any],
    state: str,
    result: Any = None,
) -> dict[str, Any]:
    task_id = _identity(getattr(task_request, "id", None))
    with _LOCK:
        context = _CONTEXTS.pop(task_id, None)
    if context is None:
        context = _context(task_name=task_name, task_request=task_request, kwargs=kwargs)
    status = _identity(state, label=True).lower()
    if status in {"success", "succeeded"}:
        status = "succeeded"
    elif status in {"failure", "failed", "error"}:
        status = "failed"
    else:
        status = _identity(status, fallback="unknown", label=True)
    try:
        result_digest = hashlib.sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
    except Exception:
        result_digest = "unavailable"
    event_payload = _event(
        context,
        "worker_task_finished",
        status=status,
        duration_seconds=max(0.0, time.monotonic() - context.started_monotonic),
        result_sha256=result_digest,
    )
    WORKER_TASKS.labels(
        context.task_name,
        context.worker_name,
        context.queue,
        context.project_key,
        context.line_key,
        status,
    ).inc()
    WORKER_TASK_LATENCY.labels(
        context.task_name,
        context.worker_name,
        context.queue,
        context.project_key,
        context.line_key,
    ).observe(event_payload["duration_seconds"])
    with _LOCK:
        _remember_trace(context.trace_id, event_payload)
    _emit(event_payload)
    return dict(event_payload)


def worker_trace_snapshot(trace_id: str) -> list[dict[str, Any]]:
    normalized = _identity(trace_id)
    with _LOCK:
        return [dict(item) for item in _TRACES.get(normalized, [])]


def install_worker_observability() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    @signals.task_prerun.connect(weak=False)
    def _task_prerun(task=None, **kwargs: object) -> None:
        if task is None:
            return
        request = getattr(task, "request", None)
        task_kwargs = getattr(request, "kwargs", None)
        observe_worker_task_started(
            task_name=str(getattr(task, "name", "") or getattr(request, "task", "")),
            task_request=request,
            kwargs=task_kwargs if isinstance(task_kwargs, Mapping) else {},
        )

    @signals.task_postrun.connect(weak=False)
    def _task_postrun(task=None, state=None, retval=None, **kwargs: object) -> None:
        if task is None:
            return
        request = getattr(task, "request", None)
        task_kwargs = getattr(request, "kwargs", None)
        observe_worker_task_finished(
            task_name=str(getattr(task, "name", "") or getattr(request, "task", "")),
            task_request=request,
            kwargs=task_kwargs if isinstance(task_kwargs, Mapping) else {},
            state=str(state or "unknown"),
            result=retval,
        )

    _INSTALLED = True


__all__ = [
    "WORKER_TASKS",
    "WORKER_TASKS_METRIC_NAME",
    "WORKER_TASK_LATENCY",
    "WORKER_TASK_LATENCY_METRIC_NAME",
    "install_worker_observability",
    "observe_worker_task_finished",
    "observe_worker_task_started",
    "worker_trace_snapshot",
]
