"""任务进程管理API - 管理Celery任务"""
from __future__ import annotations

import logging
import json
from contextlib import nullcontext
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from inspect import signature as inspect_signature
from fastapi import APIRouter, HTTPException, Query, Request
import os
from collections import deque
from functorial_kit import Failure
from pydantic import BaseModel
from sqlalchemy import select, func

from ..celery_app import celery_app
from ..contracts import ErrorCode, error_response
from ..contracts.responses import ok
from ..models.base import SessionLocal
from ..models.entities import EtlJobRun
from ..successor_runtime.runtime.observations import (
    LegacySourceObservation,
    ObservationClass,
    ObservationFreshness,
    ObservationSourceKind,
)
from ..successor_runtime.runtime.process_observation import (
    normalize_observed_status,
    try_join_process_observations,
)
from ..services.projects import bind_project
from ..services.skill_runtime import invoke_skill
from ..services.task_readback_metadata import (
    append_runtime_event,
    normalize_line_key,
    non_empty_text,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/process", tags=["process"])
_DB_JOB_PREFIX = "db-job-"
_RUNTIME_RUN_PREFIX = "runtime-run:"
_RUNTIME_READBACK_DEFAULT_LIMIT = 20
_RUNTIME_READBACK_MAX_LIMIT = 200


@dataclass(frozen=True, slots=True)
class _RuntimeReadbackSource:
    row: dict[str, Any]
    observation: LegacySourceObservation


def _raise_invalid_input(message: str) -> None:
    raise HTTPException(
        status_code=400,
        detail=error_response(
            ErrorCode.INVALID_INPUT,
            message,
        ),
    )


def _raise_not_found(message: str) -> None:
    raise HTTPException(
        status_code=404,
        detail=error_response(
            ErrorCode.NOT_FOUND,
            message,
        ),
    )


def _raise_internal_error(message: str, *, details: dict[str, Any] | None = None) -> None:
    raise HTTPException(
        status_code=500,
        detail=error_response(
            ErrorCode.INTERNAL_ERROR,
            message,
            details=details,
        ),
    )


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_int(value: Any) -> int | None:
    try:
        iv = int(value)
    except Exception:
        return None
    return iv if iv >= 0 else None


def _runtime_readback_limit(value: int) -> int:
    return max(1, min(int(value or _RUNTIME_READBACK_DEFAULT_LIMIT), _RUNTIME_READBACK_MAX_LIMIT))


def _runtime_readback_path(
    endpoint: str,
    *,
    line_key: str | None = None,
    limit: int | None = None,
    project_key: str | None = None,
) -> str:
    params: list[str] = []
    if line_key:
        params.append(f"line_key={line_key}")
    if limit is not None:
        params.append(f"limit={limit}")
    if project_key:
        params.append(f"project_key={project_key}")
    suffix = f"?{'&'.join(params)}" if params else ""
    return f"/api/v1/process/{endpoint}{suffix}"


def _first_runtime_value(*values: Any) -> str | None:
    for value in values:
        text = non_empty_text(value)
        if text:
            return text
    return None


def _projected_runtime_status(status: Any) -> str:
    return normalize_observed_status(non_empty_text(status)).lower()


def _typed_runtime_payloads(*payloads: Any) -> tuple[dict[str, Any], ...]:
    typed: list[dict[str, Any]] = []
    for payload in payloads:
        item = _as_dict(payload)
        for key in ("runtime_readback",):
            nested = _as_dict(item.get(key))
            if nested:
                typed.append(nested)
        if item:
            typed.append(item)
    return tuple(typed)


def _runtime_value_from_payload(payloads: tuple[dict[str, Any], ...], key: str) -> str | None:
    return _first_runtime_value(*(payload.get(key) for payload in payloads))


def _runtime_run_id_from_payload(*payloads: Any) -> str | None:
    return _runtime_value_from_payload(_typed_runtime_payloads(*payloads), "run_id")


def _runtime_trace_id_from_payload(*payloads: Any) -> str | None:
    return _runtime_value_from_payload(_typed_runtime_payloads(*payloads), "trace_id")


def _runtime_queue_from_payload(*payloads: Any, delivery_info: dict[str, Any] | None = None) -> str | None:
    return _first_runtime_value(
        *(
            payload.get("queue")
            for payload in _typed_runtime_payloads(*payloads)
        ),
        (delivery_info or {}).get("routing_key"),
    )


def _runtime_worker_from_payload(*payloads: Any) -> str | None:
    return _runtime_value_from_payload(_typed_runtime_payloads(*payloads), "worker_name")


def _runtime_events_from_payload(*payloads: Any) -> list[Any]:
    for payload in _typed_runtime_payloads(*payloads):
        value = payload.get("events")
        if isinstance(value, list) and value:
            return list(value)
    return []


def _async_result_snapshot(task_id: str | None) -> dict[str, Any]:
    if not task_id:
        return {}
    try:
        result = celery_app.AsyncResult(task_id)
        ready = bool(result.ready())
        snapshot = {
            "status": _projected_runtime_status(getattr(result, "status", None)),
            "result": _project_async_result_value(getattr(result, "result", None) if ready else None),
            "progress": getattr(result, "info", None) if not ready else None,
            "ready": ready,
        }
        return snapshot
    except Exception:
        return {}


def _project_async_result_value(value: Any) -> Any:
    """Render Celery failure values without changing successful result payloads."""
    if isinstance(value, BaseException):
        return {
            "message": str(value),
            "type": type(value).__name__,
        }
    return value


def _observed_at(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.astimezone()
    return value


def _runtime_source_observation(
    *,
    source_kind: ObservationSourceKind,
    source_locator: str,
    source_identity: str,
    observed_state: str | None,
    observed_at: datetime,
    linked_run_id: str | None = None,
) -> LegacySourceObservation:
    status = normalize_observed_status(observed_state)
    observation_class = ObservationClass.OBSERVED if status != "UNKNOWN" else ObservationClass.UNAVAILABLE
    reason = None if observation_class is ObservationClass.OBSERVED else "SOURCE_STATE_UNKNOWN"
    return LegacySourceObservation.from_content(
        source_kind=source_kind,
        source_locator=source_locator,
        source_identity=source_identity,
        observed_state=observed_state,
        observation_class=observation_class,
        observed_at=observed_at,
        freshness=ObservationFreshness.FRESH,
        linked_run_id=linked_run_id,
        reason=reason,
    )


def _raise_process_observation_failure(failure: Failure) -> None:
    _raise_internal_error(
        "process observation projection failed",
        details={
            "failure_code": failure.code,
            "failure_message": failure.message,
            "failure_context": dict(failure.context or {}),
        },
    )


def _project_runtime_readback_sources(
    sources: tuple[_RuntimeReadbackSource, ...] | list[_RuntimeReadbackSource],
) -> tuple[list[dict[str, Any]], str | None]:
    if not sources:
        return [], None
    joined = try_join_process_observations(
        (source.observation for source in sources),
        captured_at=datetime.now(timezone.utc),
    )
    if isinstance(joined, Failure):
        _raise_process_observation_failure(joined)
    tasks_by_identity = {task.task_id: task for task in joined.tasks}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        identity = source.observation.source_identity
        if identity in seen:
            continue
        seen.add(identity)
        task = tasks_by_identity[identity]
        row = dict(source.row)
        row.update(
            status=task.status.lower(),
            observation_class=task.observation_class.value,
            source_identities=list(task.source_identities),
            observation_reason=task.reason,
            view_digest=joined.view_digest,
            terminal_authority_claim=None,
        )
        rows.append(row)
    return rows, joined.view_digest


def _line_matches_filter(item_line_key: str | None, requested_line_key: str | None) -> bool:
    if not requested_line_key:
        return True
    return item_line_key == normalize_line_key(requested_line_key)


def _celery_request_payload(task: dict[str, Any], *, scheduled: bool = False) -> dict[str, Any]:
    request_payload = task.get("request") if scheduled else None
    return request_payload if isinstance(request_payload, dict) else task


def _task_project_key_from_payload(*payloads: Any) -> str | None:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in ("project_key",):
            if key in payload:
                return str(payload.get(key) or "").strip()
        for key in ("runtime_readback",):
            metadata = payload.get(key)
            if isinstance(metadata, dict) and "project_key" in metadata:
                return str(metadata.get("project_key") or "").strip()
    return None


def _celery_task_project_key(
    *,
    task_name: str | None,
    args: Any,
    kwargs: dict[str, Any],
    headers: dict[str, Any],
) -> str | None:
    explicit_project = _task_project_key_from_payload(kwargs, headers)
    if explicit_project is not None:
        return explicit_project

    task = celery_app.tasks.get(task_name or "")
    if task is None:
        return None
    positional_args = args if isinstance(args, list) else []
    try:
        parameters = list(inspect_signature(task.run).parameters.values())
    except (TypeError, ValueError):
        return None
    for index, parameter in enumerate(parameters):
        if parameter.name in {"project_key", "project"} and index < len(positional_args):
            return str(positional_args[index] or "").strip()
    return None


def _celery_task_matches_project(
    *,
    project_key: str | None,
    task_name: str | None,
    args: Any,
    kwargs: dict[str, Any],
    headers: dict[str, Any],
) -> bool:
    if not project_key:
        return True
    task_project = _celery_task_project_key(
        task_name=task_name,
        args=args,
        kwargs=kwargs,
        headers=headers,
    )
    return bool(task_project) and task_project == str(project_key).strip()


def _db_job_public_task_id(job: EtlJobRun) -> str:
    params = dict(job.params or {})
    runtime_task_id = non_empty_text(params.get("task_id"))
    if runtime_task_id:
        return runtime_task_id
    if not non_empty_text(job.external_provider) and non_empty_text(job.external_job_id):
        return non_empty_text(job.external_job_id) or ""
    if job.id is None:
        return ""
    return f"{_DB_JOB_PREFIX}{job.id}"


def _db_job_duration_seconds(job: EtlJobRun) -> float | None:
    if job.started_at and job.finished_at:
        return (job.finished_at - job.started_at).total_seconds()
    if job.started_at:
        return (datetime.now(job.started_at.tzinfo) - job.started_at).total_seconds()
    return None


def _celery_task_projection(
    *,
    task: dict[str, Any],
    worker_name: str,
    status: str,
    endpoint: str,
    requested_line_key: str | None,
    limit: int,
    scheduled: bool = False,
) -> dict[str, Any] | None:
    request_payload = _celery_request_payload(task, scheduled=scheduled)
    kwargs = request_payload.get("kwargs") if isinstance(request_payload.get("kwargs"), dict) else {}
    headers = request_payload.get("headers") if isinstance(request_payload.get("headers"), dict) else {}
    delivery_info = request_payload.get("delivery_info") if isinstance(request_payload.get("delivery_info"), dict) else {}
    task_id = _first_runtime_value(request_payload.get("id"), task.get("id"))
    task_name = _first_runtime_value(request_payload.get("task"), request_payload.get("name"), task.get("name"))
    snapshot = _async_result_snapshot(task_id)
    result_payload = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
    progress_payload = snapshot.get("progress") if isinstance(snapshot.get("progress"), dict) else {}
    runtime_payloads = _typed_runtime_payloads(kwargs, headers, result_payload, progress_payload)
    line_key = _runtime_value_from_payload(runtime_payloads, "line_key")
    if not _line_matches_filter(line_key, requested_line_key):
        return None
    # Celery PENDING is ambiguous for an unknown result, while inspect already
    # supplies the direct worker observation for this task.
    normalized_status = _projected_runtime_status(status)
    events = _runtime_events_from_payload(result_payload, progress_payload, kwargs, headers)
    inspect_event = f"celery_inspect_{status}"
    events = append_runtime_event(
        events,
        inspect_event,
        status=normalized_status,
        source="celery_inspect",
    )
    for event in events:
        if isinstance(event, dict) and event.get("event") == inspect_event:
            event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    item: dict[str, Any] = {
        "line_key": line_key,
        "task_id": task_id,
        "run_id": _runtime_run_id_from_payload(kwargs, headers, result_payload, progress_payload),
        "worker_name": _first_runtime_value(
            _runtime_worker_from_payload(kwargs, headers, result_payload, progress_payload),
            worker_name,
        ),
        "queue": _first_runtime_value(
            _runtime_queue_from_payload(kwargs, headers, delivery_info, result_payload, progress_payload),
        ),
        "trace_id": _runtime_trace_id_from_payload(kwargs, headers, result_payload, progress_payload),
        "status": normalized_status,
        "events": events,
        "event_source": "celery_inspect",
        "readback_source": "celery_inspect",
        "readback_endpoint": _runtime_readback_path(endpoint, line_key=requested_line_key, limit=limit),
        "readback_path": _runtime_readback_path(endpoint, line_key=requested_line_key, limit=limit),
        "mocked": False,
        "skipped": False,
        "task_name": task_name,
        "observation_source_kind": (
            ObservationSourceKind.CELERY_ASYNC_RESULT
            if snapshot
            else ObservationSourceKind.CELERY_INSPECT
        ).value,
        "args": request_payload.get("args", []),
        "kwargs": kwargs,
        "started_at": (
            datetime.fromtimestamp(task["time_start"]).isoformat()
            if task.get("time_start")
            else None
        ),
    }
    return item


def _celery_task_source(
    *,
    task: dict[str, Any],
    worker_name: str,
    status: str,
    endpoint: str,
    requested_line_key: str | None,
    limit: int,
    scheduled: bool = False,
) -> _RuntimeReadbackSource | None:
    row = _celery_task_projection(
        task=task,
        worker_name=worker_name,
        status=status,
        endpoint=endpoint,
        requested_line_key=requested_line_key,
        limit=limit,
        scheduled=scheduled,
    )
    if row is None:
        return None
    identity = non_empty_text(row.get("task_id"))
    if not identity:
        return None
    return _RuntimeReadbackSource(
        row=row,
        observation=_runtime_source_observation(
            source_kind=ObservationSourceKind(row["observation_source_kind"]),
            source_locator=f"{row['observation_source_kind']}://{worker_name}/{identity}",
            source_identity=identity,
            observed_state=non_empty_text(row.get("status")),
            observed_at=datetime.now(timezone.utc),
            linked_run_id=row.get("run_id"),
        ),
    )


def _db_job_source(
    *,
    job: EtlJobRun,
    endpoint: str,
    requested_line_key: str | None,
    limit: int,
    project_key: str | None = None,
) -> _RuntimeReadbackSource | None:
    params = dict(job.params or {})
    result_payload = params.get("result") if isinstance(params.get("result"), dict) else {}
    progress_payload = params.get("progress") if isinstance(params.get("progress"), dict) else {}
    runtime_payloads = _typed_runtime_payloads(params, result_payload, progress_payload)
    line_key = _runtime_value_from_payload(runtime_payloads, "line_key")
    if not _line_matches_filter(line_key, requested_line_key):
        return None
    if project_key:
        job_project = _task_project_key_from_payload(params)
        if job_project is not None and job_project != str(project_key).strip():
            return None
    status = _projected_runtime_status(job.status)
    task_id = _first_runtime_value(
        _runtime_value_from_payload(runtime_payloads, "task_id"),
        f"{_DB_JOB_PREFIX}{job.id}" if job.id is not None else None,
    )
    readback_task_id = task_id
    readback_path = _runtime_readback_path(
        readback_task_id,
        project_key=project_key,
    )
    run_id = _first_runtime_value(
        _runtime_run_id_from_payload(params, result_payload, progress_payload),
        str(job.id) if job.id is not None else None,
    )
    events = _runtime_events_from_payload(params, result_payload, progress_payload)
    if job.started_at:
        events = append_runtime_event(
            events,
            "etl_job_started",
            status="running",
            source="etl_job_runs",
        )
        for event in events:
            if isinstance(event, dict) and event.get("event") == "etl_job_started":
                event.setdefault("timestamp", job.started_at.isoformat())
    row = {
        "line_key": line_key,
        "task_id": task_id,
        "run_id": run_id,
        "worker_name": _runtime_worker_from_payload(params, result_payload, progress_payload),
        "queue": _runtime_queue_from_payload(params, result_payload, progress_payload),
        "trace_id": _runtime_trace_id_from_payload(params, result_payload, progress_payload),
        "status": status,
        "events": events,
        "event_source": "etl_job_runs",
        "readback_source": "etl_job_runs",
        "readback_endpoint": readback_path,
        "readback_path": readback_path,
        "mocked": False,
        "skipped": False,
        "job_type": job.job_type,
        "task_name": (
            str(params.get("job_type_full") or "").strip()
            or str(job.job_type or "").strip()
            or "db_job"
        ),
        "args": [],
        "kwargs": params,
        "started_at": job.started_at.isoformat() if job.started_at else None,
    }
    identity = non_empty_text(task_id) or (
        f"{_DB_JOB_PREFIX}{job.id}" if job.id is not None else f"{_DB_JOB_PREFIX}unpersisted"
    )
    return _RuntimeReadbackSource(
        row=row,
        observation=_runtime_source_observation(
            source_kind=ObservationSourceKind.ETL_JOB_RUN,
            source_locator=f"etl-job-run://{job.id if job.id is not None else 'unpersisted'}",
            source_identity=identity,
            observed_state=non_empty_text(job.status),
            observed_at=_observed_at(job.finished_at or job.started_at),
            linked_run_id=run_id,
        ),
    )


def _db_job_projection(
    *,
    job: EtlJobRun,
    endpoint: str,
    requested_line_key: str | None,
    limit: int,
    project_key: str | None = None,
) -> dict[str, Any] | None:
    source = _db_job_source(
        job=job,
        endpoint=endpoint,
        requested_line_key=requested_line_key,
        limit=limit,
        project_key=project_key,
    )
    if source is None:
        return None
    rows, _ = _project_runtime_readback_sources((source,))
    return rows[0] if rows else None


def _extract_handler_used(*payloads: Any) -> str | None:
    for payload in payloads:
        item = _as_dict(payload)
        direct = non_empty_text(item.get("handler_used"))
        if direct:
            return direct
        alloc = _as_dict(item.get("handler_allocation"))
        nested = non_empty_text(alloc.get("handler_used"))
        if nested:
            return nested
    return None


def _extract_skip_reason(*payloads: Any) -> str | None:
    candidates: list[str] = []
    for payload in payloads:
        item = _as_dict(payload)
        direct = non_empty_text(item.get("skip_reason"))
        if direct:
            return direct
        for key in ("page_gate", "pre_fetch_url_gate", "pre_write_content_gate", "provenance_gate"):
            nested = _as_dict(item.get(key))
            reason = non_empty_text(nested.get("reason"))
            if reason:
                return reason
        rb = item.get("rejection_breakdown")
        if isinstance(rb, dict):
            for k, v in rb.items():
                name = non_empty_text(k)
                count = _coerce_int(v)
                if name and count and count > 0:
                    candidates.append(name)
    if not candidates:
        return None
    # Deterministic fallback when only rejection breakdown is available.
    counts: Dict[str, int] = {}
    for name in candidates:
        counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _extract_error_code(*payloads: Any, status: Any = None, error: Any = None) -> str | None:
    for payload in payloads:
        item = _as_dict(payload)
        direct = non_empty_text(item.get("error_code"))
        if direct:
            return direct
        nested_error = _as_dict(item.get("error"))
        nested_code = non_empty_text(nested_error.get("code"))
        if nested_code:
            return nested_code
    status_text = str(status or "").strip().lower()
    if status_text == "failed" or non_empty_text(error):
        return "TASK_FAILED"
    if status_text in {"completed", "success"}:
        return "OK"
    return None


def _extract_quality_fields(*payloads: Any) -> Dict[str, Any]:
    data = [_as_dict(p) for p in payloads]
    inserted_valid: int | None = None
    rejected_count: int | None = None
    rejection_breakdown: Dict[str, int] = {}
    degradation_flags: list[str] = []
    quality_score: float | None = None

    for item in data:
        if inserted_valid is None:
            inserted_valid = _coerce_int(item.get("inserted_valid"))
        if rejected_count is None:
            rejected_count = _coerce_int(item.get("rejected_count"))
        rb = item.get("rejection_breakdown")
        if isinstance(rb, dict):
            for k, v in rb.items():
                key = str(k or "").strip()
                val = _coerce_int(v)
                if not key or val is None:
                    continue
                rejection_breakdown[key] = rejection_breakdown.get(key, 0) + val
        flags = item.get("degradation_flags")
        if isinstance(flags, list):
            for flag in flags:
                name = str(flag or "").strip()
                if name and name not in degradation_flags:
                    degradation_flags.append(name)
        if quality_score is None:
            try:
                qv = float(item.get("quality_score"))
            except Exception:
                qv = None
            if qv is not None and qv >= 0:
                quality_score = qv

    if rejected_count is None and rejection_breakdown:
        rejected_count = sum(rejection_breakdown.values())
    if rejected_count is None:
        rejected_count = 0

    out: Dict[str, Any] = {
        "rejected_count": rejected_count,
        "rejection_breakdown": rejection_breakdown,
        "degradation_flags": degradation_flags,
    }
    if inserted_valid is not None:
        out["inserted_valid"] = inserted_valid
    if quality_score is not None:
        out["quality_score"] = quality_score
    return out


class TaskInfo(BaseModel):
    """任务信息模型"""
    task_id: str
    name: str
    status: str
    args: List[Any]
    kwargs: Dict[str, Any]
    worker: Optional[str] = None
    started_at: Optional[str] = None
    display_meta: Optional[Dict[str, Any]] = None


class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: List[TaskInfo]
    stats: dict


@router.get("/list")
def list_tasks(
    status_filter: Optional[str] = None,
    limit: int = 100,
    project_key: Optional[str] = None,
) -> dict[str, Any]:
    """List current non-terminal tasks through the process observation projection."""
    try:
        from ..services.collect_runtime import infer_display_meta_from_celery_task, extract_display_meta_from_params
        readback_items = _runtime_readback_items(
            endpoint="list",
            line_key=None,
            limit=max(1, min(int(limit or 100), 300)),
            project_key=project_key,
        )
        current_items = [
            item for item in readback_items
            if str(item.get("status") or "") in {"active", "pending", "reserved"}
        ]
        requested_filter = str(status_filter or "").strip().lower() or None
        if requested_filter:
            current_items = [item for item in current_items if item.get("status") == requested_filter]

        tasks: list[TaskInfo] = []
        for item in current_items[:limit]:
            task_args = item.get("args") or []
            task_kwargs = item.get("kwargs") or {}
            task_name = str(item.get("task_name") or "unknown")
            display_meta = (
                infer_display_meta_from_celery_task(task_name, task_args, task_kwargs)
                if item.get("readback_source") == "celery_inspect"
                else extract_display_meta_from_params(task_kwargs)
            )
            tasks.append(
                TaskInfo(
                    task_id=str(item.get("task_id") or "unknown"),
                    name=task_name,
                    status=str(item.get("status") or "unknown"),
                    args=task_args,
                    kwargs=task_kwargs,
                    worker=item.get("worker_name"),
                    started_at=item.get("started_at"),
                    display_meta=display_meta,
                )
            )

        registered_tasks = celery_app.control.inspect().registered() or {}
        registered_task_names = set()
        for worker_name, task_list in registered_tasks.items():
            registered_task_names.update(task_list)
        total_tasks = len(current_items)
        active_count = sum(item.get("status") == "active" for item in current_items)
        pending_count = sum(item.get("status") in {"pending", "reserved"} for item in current_items)
        observed_workers = {item.get("worker_name") for item in current_items if item.get("worker_name")}

        stats = {
            "total_tasks": total_tasks,
            "active_tasks": active_count,
            "pending_tasks": pending_count,
            "task_count_scope": "project" if project_key else "global",
            "registered_task_types": len(registered_task_names),
            "workers": len(observed_workers | set(registered_tasks.keys())),
            "workers_scope": "global",
        }

        return ok(
            {
                "tasks": tasks,
                "stats": stats,
            }
        )

    except Exception as e:
        logger.exception("获取任务列表失败")
        _raise_internal_error(
            f"获取任务列表失败: {str(e)}",
            details={"exception_type": e.__class__.__name__},
        )


@router.get("/stats")
def get_task_stats(project_key: Optional[str] = Query(None)) -> dict[str, Any]:
    """获取任务统计信息"""
    try:
        items = _runtime_readback_items(
            endpoint="stats",
            line_key=None,
            limit=_RUNTIME_READBACK_MAX_LIMIT,
            project_key=project_key,
        )
        current_items = [
            item for item in items
            if str(item.get("status") or "") in {"active", "pending", "reserved"}
        ]
        active_count = sum(item.get("status") == "active" for item in current_items)
        scheduled_count = sum(item.get("status") == "pending" for item in current_items)
        reserved_count = sum(item.get("status") == "reserved" for item in current_items)

        registered_tasks = celery_app.control.inspect().registered() or {}
        registered_task_names = set()
        for worker_name, task_list in registered_tasks.items():
            registered_task_names.update(task_list)
        observed_workers = {item.get("worker_name") for item in current_items if item.get("worker_name")}
        workers = list(observed_workers | set(registered_tasks.keys()))

        return ok(
            {
                'active_tasks': active_count,
                'scheduled_tasks': scheduled_count,
                'reserved_tasks': reserved_count,
                'total_running': active_count + scheduled_count + reserved_count,
                'task_count_scope': 'project' if project_key else 'global',
                'registered_task_types': len(registered_task_names),
                'workers': len(workers),
                'workers_scope': 'global',
                'worker_names': workers,
            }
        )

    except Exception as e:
        logger.exception("获取任务统计信息失败")
        _raise_internal_error(
            f"获取任务统计信息失败: {str(e)}",
            details={"exception_type": e.__class__.__name__},
        )


@router.get("/history")
def get_task_history(
    limit: int = Query(default=50, ge=1, le=500),
    status: Optional[str] = Query(None, description="任务状态过滤: completed, failed, running"),
    job_type: Optional[str] = Query(None, description="任务类型过滤"),
    project_key: Optional[str] = Query(None, description="项目标识（用于查询对应项目 schema 的任务历史）"),
) -> dict[str, Any]:
    """获取任务历史记录"""
    try:
        from ..services.collect_runtime import extract_display_meta_from_params
        ctx = bind_project(project_key) if project_key else nullcontext()
        with ctx:
            with SessionLocal() as session:
                query = select(EtlJobRun)

            # 应用过滤器
                if status:
                    query = query.where(EtlJobRun.status == status)
                if job_type:
                    query = query.where(EtlJobRun.job_type == job_type)

            # 按开始时间倒序排列
                query = query.order_by(EtlJobRun.started_at.desc().nullslast()).limit(limit)

                jobs = session.execute(query).scalars().all()

            # 转换为字典格式
                history = []
                for job in jobs:
                    duration = _db_job_duration_seconds(job)
                    params = dict(job.params or {})
                    task_id = _db_job_public_task_id(job) or None
                    task_name = (
                        str(params.get("job_type_full") or "").strip()
                        or str(job.job_type or "").strip()
                        or "db_job"
                    )
                    quality_fields = _extract_quality_fields(
                        params,
                        params.get("result"),
                        params.get("progress"),
                    )
                    handler_used = _extract_handler_used(params, params.get("result"), params.get("progress"))
                    skip_reason = _extract_skip_reason(params, params.get("result"), params.get("progress"))
                    error_code = _extract_error_code(
                        params,
                        params.get("result"),
                        params.get("progress"),
                        status=job.status,
                        error=job.error,
                    )

                    history.append({
                        "id": job.id,
                        "task_id": task_id,
                        "task_name": task_name,
                        "source": "db",
                        "job_type": job.job_type,
                        "status": job.status,
                        "params": params,
                        "display_meta": extract_display_meta_from_params(params),
                        "started_at": job.started_at.isoformat() if job.started_at else None,
                        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                        "duration_seconds": duration,
                        "error": job.error,
                        "inserted_valid": quality_fields.get("inserted_valid"),
                        "rejected_count": quality_fields.get("rejected_count"),
                        "rejection_breakdown": quality_fields.get("rejection_breakdown") or {},
                        "degradation_flags": quality_fields.get("degradation_flags") or [],
                        "quality_score": quality_fields.get("quality_score"),
                        "error_code": error_code,
                        "handler_used": handler_used,
                        "skip_reason": skip_reason,
                    })

            # 获取统计信息
                total_query = select(func.count(EtlJobRun.id))
                if status:
                    total_query = total_query.where(EtlJobRun.status == status)
                if job_type:
                    total_query = total_query.where(EtlJobRun.job_type == job_type)
                total = session.execute(total_query).scalar() or 0

            # 按状态统计
                status_stats = {}
                status_query = select(
                    EtlJobRun.status,
                    func.count(EtlJobRun.id).label("count")
                )
                if job_type:
                    status_query = status_query.where(EtlJobRun.job_type == job_type)
                status_query = status_query.group_by(EtlJobRun.status)
                for row in session.execute(status_query).all():
                    status_stats[row.status] = row.count

                return ok(
                    {
                        "history": history,
                        "total": total,
                        "status_stats": status_stats,
                        "project_key": project_key,
                    }
                )

    except Exception as e:
        logger.exception("获取任务历史记录失败")
        _raise_internal_error(
            f"获取任务历史记录失败: {str(e)}",
            details={"exception_type": e.__class__.__name__},
        )


def _load_celery_runtime_readback_items(
    *,
    endpoint: str,
    line_key: str | None,
    limit: int,
    project_key: str | None = None,
) -> list[_RuntimeReadbackSource]:
    inspect = celery_app.control.inspect()
    active_tasks = inspect.active() or {}
    scheduled_tasks = inspect.scheduled() or {}
    reserved_tasks = inspect.reserved() or {}

    items: list[dict[str, Any]] = []
    seen_identities: set[str] = set()
    groups = (
        ("active", active_tasks, False),
        ("scheduled", scheduled_tasks, True),
        ("reserved", reserved_tasks, False),
    )
    for status, worker_tasks_by_name, scheduled in groups:
        if not isinstance(worker_tasks_by_name, dict):
            continue
        for worker_name, worker_tasks in worker_tasks_by_name.items():
            if not isinstance(worker_tasks, list):
                continue
            for task in worker_tasks:
                if not isinstance(task, dict):
                    continue
                request_payload = _celery_request_payload(task, scheduled=scheduled)
                task_name = _first_runtime_value(
                    request_payload.get("task"),
                    request_payload.get("name"),
                    task.get("name"),
                )
                task_args = request_payload.get("args", [])
                task_kwargs = request_payload.get("kwargs", {}) if isinstance(request_payload.get("kwargs", {}), dict) else {}
                task_headers = request_payload.get("headers", {}) if isinstance(request_payload.get("headers", {}), dict) else {}
                if not _celery_task_matches_project(
                    project_key=project_key,
                    task_name=task_name,
                    args=task_args,
                    kwargs=task_kwargs,
                    headers=task_headers,
                ):
                    continue
                source = _celery_task_source(
                    task=task,
                    worker_name=str(worker_name),
                    status=status,
                    endpoint=endpoint,
                    requested_line_key=line_key,
                    limit=limit,
                    scheduled=scheduled,
                )
                if source is not None:
                    identity = source.observation.source_identity
                    if identity in seen_identities:
                        continue
                    seen_identities.add(identity)
                    items.append(source)
                if len(items) >= limit:
                    return items
    return items


def _load_db_runtime_readback_items(
    *,
    endpoint: str,
    line_key: str | None,
    limit: int,
    project_key: str | None,
) -> list[_RuntimeReadbackSource]:
    query_limit = max(limit * 5, limit)
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        with SessionLocal() as session:
            query = (
                select(EtlJobRun)
                .order_by(EtlJobRun.started_at.desc().nullslast(), EtlJobRun.id.desc())
                .limit(min(query_limit, 500))
            )
            jobs = session.execute(query).scalars().all()

    items: list[_RuntimeReadbackSource] = []
    for job in jobs:
        source = _db_job_source(
            job=job,
            endpoint=endpoint,
            requested_line_key=line_key,
            limit=limit,
            project_key=project_key,
        )
        if source is None:
            continue
        items.append(source)
        if len(items) >= limit:
            break
    return items


def _runtime_readback_items(
    *,
    endpoint: str,
    line_key: str | None,
    limit: int,
    project_key: str | None,
) -> list[dict[str, Any]]:
    normalized_line_key = normalize_line_key(line_key)
    normalized_limit = _runtime_readback_limit(limit)
    sources = [
        *_load_celery_runtime_readback_items(
            endpoint=endpoint,
            line_key=normalized_line_key,
            limit=normalized_limit,
            project_key=project_key,
        ),
        *_load_db_runtime_readback_items(
            endpoint=endpoint,
            line_key=normalized_line_key,
            limit=normalized_limit,
            project_key=project_key,
        ),
    ]

    projected, _ = _project_runtime_readback_sources(sources)
    return projected[:normalized_limit]


@router.get("/tasks")
def list_runtime_readback_tasks(
    line_key: Optional[str] = Query(None, description="业务线 line_key 过滤"),
    limit: int = Query(default=_RUNTIME_READBACK_DEFAULT_LIMIT, ge=1, le=_RUNTIME_READBACK_MAX_LIMIT),
    project_key: Optional[str] = Query(None, description="项目标识（用于查询对应项目 schema 的任务历史）"),
) -> dict[str, Any]:
    """按 line_key 暴露真实 runtime task readback，不制造成功态。"""
    normalized_limit = _runtime_readback_limit(limit)
    items = _runtime_readback_items(
        endpoint="tasks",
        line_key=line_key,
        limit=normalized_limit,
        project_key=project_key,
    )
    return ok(
        {
            "items": items,
            "line_key": normalize_line_key(line_key),
            "limit": normalized_limit,
            "project_key": project_key,
            "readback_source": "celery_inspect_or_etl_job_runs",
        }
    )


@router.get("/logs")
def list_runtime_readback_logs(
    line_key: Optional[str] = Query(None, description="业务线 line_key 过滤"),
    limit: int = Query(default=_RUNTIME_READBACK_DEFAULT_LIMIT, ge=1, le=_RUNTIME_READBACK_MAX_LIMIT),
    project_key: Optional[str] = Query(None, description="项目标识（用于查询对应项目 schema 的任务历史）"),
) -> dict[str, Any]:
    """按 line_key 暴露真实 runtime log/readback projection，不走 /{task_id}/logs。"""
    normalized_limit = _runtime_readback_limit(limit)
    logs = _runtime_readback_items(
        endpoint="logs",
        line_key=line_key,
        limit=normalized_limit,
        project_key=project_key,
    )
    return ok(
        {
            "items": logs,
            "logs": logs,
            "line_key": normalize_line_key(line_key),
            "limit": normalized_limit,
            "project_key": project_key,
            "readback_source": "celery_inspect_or_etl_job_runs",
        }
    )


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str, terminate: bool = False) -> dict[str, Any]:
    """取消指定任务"""
    try:
        # 撤销任务
        celery_app.control.revoke(task_id, terminate=terminate)

        action = "强制终止" if terminate else "取消"

        return ok(
            {
                "success": True,
                "message": f"任务 {task_id} 已{action}",
                "task_id": task_id,
            }
        )

    except Exception as e:
        logger.exception(f"取消任务 {task_id} 失败")
        _raise_internal_error(
            f"取消任务失败: {str(e)}",
            details={"exception_type": e.__class__.__name__, "task_id": task_id},
        )


def _parse_db_job_id(task_id: str) -> int | None:
    if not str(task_id or "").startswith(_DB_JOB_PREFIX):
        return None
    suffix = str(task_id)[len(_DB_JOB_PREFIX):].strip()
    if not suffix.isdigit():
        return None
    return int(suffix)


def _resolve_db_job(task_id: str) -> EtlJobRun | None:
    job_id = _parse_db_job_id(task_id)
    with SessionLocal() as session:
        if job_id is not None:
            return session.get(EtlJobRun, job_id)
        query = (
            select(EtlJobRun)
            .where(
                EtlJobRun.external_job_id == str(task_id or "").strip(),
                EtlJobRun.external_provider.is_(None),
            )
            .order_by(EtlJobRun.started_at.desc().nullslast(), EtlJobRun.id.desc())
            .limit(1)
        )
        return session.execute(query).scalars().first()


def _extract_source_library_retry_payload(job: EtlJobRun) -> tuple[str, str | None, dict[str, Any]]:
    params = dict(job.params or {})
    item_key = str(params.get("item_key") or "").strip()
    if not item_key:
        _raise_invalid_input(f"db job {job.id} missing retry param: item_key")
    project_key = str(params.get("project_key") or "").strip() or None
    override_params = params.get("override_params")
    if not isinstance(override_params, dict):
        override_params = {}
    return item_key, project_key, dict(override_params)


def _db_job_to_task_info(task_id: str, job: EtlJobRun) -> dict[str, Any]:
    status_raw = str(job.status or "running").strip().lower()
    ready = status_raw in {"completed", "failed", "cancelled", "canceled"}
    is_external = bool(str(job.external_provider or "").strip())
    params_payload = dict(job.params or {})
    result_payload = None
    if ready:
        result_payload = dict(params_payload)
        if is_external:
            result_payload.setdefault(
                "external_log_hint",
                "External provider task is tracked in DB; live worker logs are unavailable.",
            )
    progress_payload = None
    if not ready:
        progress_payload = dict(params_payload)
        if is_external:
            progress_payload.setdefault("external_provider", job.external_provider)
            progress_payload.setdefault("external_job_id", job.external_job_id)
    quality_fields = _extract_quality_fields(params_payload, result_payload, progress_payload)
    handler_used = _extract_handler_used(params_payload, result_payload, progress_payload)
    skip_reason = _extract_skip_reason(params_payload, result_payload, progress_payload)
    error_code = _extract_error_code(
        params_payload,
        result_payload,
        progress_payload,
        status=job.status,
        error=job.error,
    )
    return {
        "task_id": task_id,
        "name": str(params_payload.get("job_type_full") or job.job_type or "db_job"),
        "status": str(job.status or "running").upper(),
        "ready": ready,
        "successful": ready and status_raw == "completed",
        "failed": ready and status_raw == "failed",
        "result": result_payload,
        "progress": progress_payload,
        "traceback": job.error if status_raw == "failed" else None,
        "worker": "external-provider" if is_external else _runtime_worker_from_payload(params_payload),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "ended_at": job.finished_at.isoformat() if job.finished_at else None,
        "elapsed_seconds": _db_job_duration_seconds(job),
        "external_provider": job.external_provider,
        "external_job_id": job.external_job_id,
        "retry_count": job.retry_count,
        "source": "db",
        "inserted_valid": quality_fields.get("inserted_valid"),
        "rejected_count": quality_fields.get("rejected_count"),
        "rejection_breakdown": quality_fields.get("rejection_breakdown") or {},
        "degradation_flags": quality_fields.get("degradation_flags") or [],
        "quality_score": quality_fields.get("quality_score"),
        "error_code": error_code,
        "handler_used": handler_used,
        "skip_reason": skip_reason,
    }


def _db_job_to_runtime_task_info(task_id: str, job: EtlJobRun, *, project_key: str | None = None) -> dict[str, Any]:
    task_info = _db_job_to_task_info(task_id, job)
    runtime_projection = _db_job_projection(
        job=job,
        endpoint=task_id,
        requested_line_key=None,
        limit=1,
        project_key=project_key,
    ) or {}
    return {**task_info, **runtime_projection}


def _runtime_output_value(exact_bytes: bytes) -> tuple[object | None, str]:
    """Decode canonical JSON values without guessing a schema for other codecs."""

    try:
        return json.loads(exact_bytes.decode("utf-8")), "json"
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "opaque"


def _runtime_run_task_info(
    *,
    run_ref: str,
    project_key: str,
    actor_id: str,
) -> dict[str, Any]:
    from app.composition.production import (
        read_installed_program,
        read_installed_program_outputs,
    )
    from app.models.base import engine
    from app.successor_runtime.runtime.transitions import RunState, TERMINAL_RUN_STATES

    run_id = run_ref.removeprefix(_RUNTIME_RUN_PREFIX).strip()
    if not run_id or run_ref != f"{_RUNTIME_RUN_PREFIX}{run_id}":
        _raise_invalid_input("runtime run reference must be runtime-run:<run_id>")

    run, steps, events = read_installed_program(
        engine=engine,
        project_key=project_key,
        actor_id=actor_id,
        run_id=run_id,
    )
    state = RunState(str(run["state"]))
    terminal = state in TERMINAL_RUN_STATES
    outputs = ()
    if run.get("plan_id") and run.get("plan_digest"):
        outputs = read_installed_program_outputs(
            engine=engine,
            project_key=project_key,
            actor_id=actor_id,
            run_id=run_id,
        )

    output_rows: list[dict[str, object]] = []
    for step_id, value_ref, exact_bytes in outputs:
        decoded, encoding = _runtime_output_value(exact_bytes)
        output_row: dict[str, object] = {
            "step_id": step_id,
            "value_ref": value_ref.to_plain(),
            "encoding": encoding,
        }
        if encoding == "json":
            output_row["value"] = decoded
        output_rows.append(output_row)

    step_rows = [
        {
            "step_id": str(step.get("step_id") or ""),
            "operation_id": str(step.get("operation_id") or ""),
            "operation_kind": str(step.get("operation_kind") or ""),
            "state": str(step.get("state") or ""),
            "output_digest": step.get("output_digest"),
            "failure_digest": step.get("failure_digest"),
            "started_at": step.get("started_at"),
            "finished_at": step.get("finished_at"),
        }
        for step in steps
    ]
    completed_steps = sum(step["state"] == "SUCCEEDED" for step in step_rows)
    failed_steps = sum(step["state"] == "FAILED" for step in step_rows)
    decoded_outputs = [row["value"] for row in output_rows if "value" in row]
    progress: dict[str, object] = {
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
        "total_steps": len(step_rows),
        "steps": step_rows,
    }
    quality_fields = _extract_quality_fields(*decoded_outputs, progress)
    task_info: dict[str, Any] = {
        "task_id": run_ref,
        "runtime_run_ref": run_ref,
        "run_id": run_id,
        "name": str(run.get("program_id") or "successor_runtime_program"),
        "status": state.value,
        "ready": terminal,
        "successful": state is RunState.COMPLETED if terminal else None,
        "failed": state is RunState.FAILED if terminal else None,
        "result": None,
        "runtime_outputs": output_rows,
        "progress": progress,
        "traceback": None,
        "started_at": run.get("created_at"),
        "ended_at": run.get("finished_at"),
        "source": "successor_runtime",
        "events": [
            {
                "seq": event.get("seq"),
                "event": event.get("event_type"),
                "step_id": event.get("step_id"),
                "created_at": event.get("created_at"),
            }
            for event in events
        ],
        "observation_class": "OBSERVED",
        "source_identities": [run_ref],
        "observation_reason": None,
        "terminal_authority_claim": None,
        "inserted_valid": quality_fields.get("inserted_valid"),
        "rejected_count": quality_fields.get("rejected_count"),
        "rejection_breakdown": quality_fields.get("rejection_breakdown") or {},
        "degradation_flags": quality_fields.get("degradation_flags") or [],
        "quality_score": quality_fields.get("quality_score"),
        "error_code": None,
        "handler_used": _extract_handler_used(*decoded_outputs, progress),
        "skip_reason": _extract_skip_reason(*decoded_outputs, progress),
    }
    return task_info


@router.get("/{task_id}")
def get_task_info(
    task_id: str,
    request: Request,
    project_key: Optional[str] = Query(None, description="项目标识（用于查询对应项目 schema 的 DB job）"),
) -> dict[str, Any]:
    """获取任务详细信息"""
    try:
        if task_id.startswith(_RUNTIME_RUN_PREFIX):
            normalized_project_key = str(project_key or "").strip()
            if not normalized_project_key:
                _raise_invalid_input("project_key is required for runtime run readback")
            from app.services.request_identity import require_trusted_actor_context

            actor = require_trusted_actor_context(request)
            return ok(
                _runtime_run_task_info(
                    run_ref=task_id,
                    project_key=normalized_project_key,
                    actor_id=actor.actor_id,
                )
            )
        ctx = bind_project(project_key) if project_key else nullcontext()
        with ctx:
            db_job = _resolve_db_job(task_id)
        if db_job is not None:
            return ok(_db_job_to_runtime_task_info(task_id, db_job, project_key=project_key))

        result = celery_app.AsyncResult(task_id)

        projected_status = _projected_runtime_status(result.status)
        async_source = _RuntimeReadbackSource(
            row={
                "task_id": task_id,
                "status": projected_status,
                "run_id": _runtime_run_id_from_payload(
                    getattr(result, "info", None) if isinstance(getattr(result, "info", None), dict) else {}
                ),
            },
            observation=_runtime_source_observation(
                source_kind=ObservationSourceKind.CELERY_ASYNC_RESULT,
                source_locator=f"celery-async-result://{task_id}",
                source_identity=task_id,
                observed_state=non_empty_text(result.status),
                observed_at=datetime.now(timezone.utc),
            ),
        )
        projected_rows, _ = _project_runtime_readback_sources((async_source,))
        runtime_projection = projected_rows[0] if projected_rows else {}

        task_info = {
            "task_id": task_id,
            "status": runtime_projection.get("status") or projected_status,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else None,
            "failed": result.failed() if result.ready() else None,
            "result": _project_async_result_value(result.result if result.ready() else None),
            "progress": result.info if not result.ready() and isinstance(getattr(result, "info", None), dict) else None,
            "traceback": result.traceback if result.failed() else None,
        }
        quality_fields = _extract_quality_fields(task_info.get("result"), task_info.get("progress"))
        handler_used = _extract_handler_used(task_info.get("result"), task_info.get("progress"))
        skip_reason = _extract_skip_reason(task_info.get("result"), task_info.get("progress"))
        error_code = _extract_error_code(
            task_info.get("result"),
            task_info.get("progress"),
            status=task_info.get("status"),
            error=task_info.get("traceback"),
        )
        task_info.update(
            {
                "inserted_valid": quality_fields.get("inserted_valid"),
                "rejected_count": quality_fields.get("rejected_count"),
                "rejection_breakdown": quality_fields.get("rejection_breakdown") or {},
                "degradation_flags": quality_fields.get("degradation_flags") or [],
                "quality_score": quality_fields.get("quality_score"),
                "error_code": error_code,
                "handler_used": handler_used,
                "skip_reason": skip_reason,
            }
        )

        # 尝试获取任务名称
        try:
            task_info["name"] = result.name
        except:
            task_info["name"] = "unknown"

        for field in (
            "observation_class",
            "source_identities",
            "observation_reason",
            "view_digest",
            "terminal_authority_claim",
        ):
            if field in runtime_projection:
                task_info[field] = runtime_projection[field]

        return ok(task_info)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"获取任务信息失败: {task_id}")
        _raise_internal_error(
            f"获取任务信息失败: {str(e)}",
            details={"exception_type": e.__class__.__name__, "task_id": task_id},
        )


@router.post("/{task_id}/retry")
def retry_task(task_id: str) -> dict[str, Any]:
    """重试指定任务（优先支持 db-job 的 source_library_run）。"""
    try:
        db_job_id = _parse_db_job_id(task_id)
        if db_job_id is None:
            _raise_invalid_input(f"仅支持 db-job 任务重试，示例: {_DB_JOB_PREFIX}<id>")

        db_job = _resolve_db_job(task_id)
        if db_job is None:
            _raise_not_found(f"未找到任务: {task_id}")

        job_type = str(db_job.job_type or "").strip()
        if job_type != "source_library_run":
            _raise_invalid_input(f"当前仅支持重试 job_type=source_library_run，实际为: {job_type or '-'}")

        item_key, project_key, override_params = _extract_source_library_retry_payload(db_job)
        invoked = invoke_skill(
            skill_id="agent_batch.dispatch.source_library_item",
            payload={
                "item_key": item_key,
                "project_key": project_key,
                "override_params": dict(override_params or {}),
                "lane": "subagent",
            },
            context={
                "actor_role": "business_capability_wrapper",
                "permissions": ["agent_batch.dispatch.source_library_item"],
                "consumer": "process.retry_task.api",
                "trace_id": f"process.retry.{task_id}",
            },
        )
        result = invoked.get("result")
        retry_task_id = str((result or {}).get("task_id") or "").strip() if isinstance(result, dict) else ""
        if not retry_task_id:
            raise RuntimeError("source library retry dispatch skill returned empty task_id")
        return ok(
            {
                "success": True,
                "message": f"任务 {task_id} 已提交重试",
                "task_id": task_id,
                "source": "db",
                "job_type": job_type,
                "retry_task_id": retry_task_id,
                "params": {
                    "item_key": item_key,
                    "project_key": project_key,
                },
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"重试任务失败: {task_id}")
        _raise_internal_error(
            f"重试任务失败: {str(e)}",
            details={"exception_type": e.__class__.__name__, "task_id": task_id},
        )



def _tail_file(path: str, max_lines: int) -> list[str]:
    """读取文件末尾的若干行，容错忽略编码错误。"""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            dq = deque(f, maxlen=max_lines)
            return list(dq)
    except FileNotFoundError:
        return []


def _merge_ranges(ranges: list[tuple[int, int]], total: int) -> list[tuple[int, int]]:
    """合并并裁剪行号范围。"""
    if not ranges:
        return []
    normalized = sorted((max(0, s), min(total, e)) for s, e in ranges if s < e)
    if not normalized:
        return []
    merged: list[tuple[int, int]] = [normalized[0]]
    for start, end in normalized[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _extract_context_lines(lines: list[str], task_id: str, context: int = 20) -> list[str]:
    """提取包含 task_id 的命中行及其上下文，减少误过滤导致的“日志不更新”问题。"""
    if not lines:
        return []
    hit_indexes = [idx for idx, line in enumerate(lines) if task_id in line]
    if not hit_indexes:
        return []
    ranges = _merge_ranges([(idx - context, idx + context + 1) for idx in hit_indexes], total=len(lines))
    out: list[str] = []
    for start, end in ranges:
        out.extend(lines[start:end])
    return [line.rstrip("\n") for line in out]


@router.get("/{task_id}/logs")
def get_task_logs(task_id: str, tail: int = Query(default=200, ge=1, le=5000)) -> dict[str, Any]:
    """获取指定任务的运行日志（按task_id过滤，默认返回最后200行）。

    在Docker部署下，日志文件默认位于 /var/log/celery/worker.log，
    可通过环境变量 CELERY_LOG_FILE 覆盖。
    """
    try:
        db_job = _resolve_db_job(task_id)
        if db_job is not None:
            is_external = bool(str(db_job.external_provider or "").strip())
            summary_lines = [
                f"task_id={task_id}",
                f"status={db_job.status or 'running'}",
                f"external_provider={db_job.external_provider or '-'}",
                f"external_job_id={db_job.external_job_id or '-'}",
                f"retry_count={db_job.retry_count if db_job.retry_count is not None else '-'}",
            ]
            if db_job.error:
                summary_lines.append(f"error={db_job.error}")
            if is_external:
                summary_lines.append(
                    "logs=External provider task is DB-tracked; Celery worker log stream is not available."
                )
            else:
                summary_lines.append(
                    "logs=DB pseudo task id has no direct Celery log stream; check ETL job params/history."
                )
            return ok(
                {
                    "task_id": task_id,
                    "tail": tail,
                    "filtered": True,
                    "text": "\n".join(summary_lines[-tail:]),
                    "log_file": "db://etl_job_runs",
                    "source": "db",
                }
            )

        log_file = os.getenv("CELERY_LOG_FILE") or "/var/log/celery/worker.log"
        if not os.path.exists(log_file):
            state = str(celery_app.AsyncResult(task_id).status or "").upper() or "UNKNOWN"
            summary_lines = [
                f"task_id={task_id}",
                f"status={state}",
                f"log_file={log_file}",
                "logs=Celery worker log file is unavailable in current runtime; configure CELERY_LOG_FILE or check centralized logging.",
            ]
            return ok(
                {
                    "task_id": task_id,
                    "tail": tail,
                    "filtered": False,
                    "text": "\n".join(summary_lines[-tail:]),
                    "log_file": log_file,
                    "source": "unavailable",
                }
            )

        # 为了更大概率匹配到 task_id，先读取较多行再裁剪
        candidate_lines = _tail_file(log_file, max_lines=min(max(2000, tail * 10), 20000))

        # 优先返回 task_id 命中行及其上下文；若无匹配则退化为尾部日志。
        contextual_lines = _extract_context_lines(candidate_lines, task_id, context=20)
        plain_tail_lines = [line.rstrip("\n") for line in candidate_lines[-tail:]]
        if contextual_lines:
            # 对进行中的任务，拼接最新尾部日志，确保页面能持续看到增量变化。
            state = str(celery_app.AsyncResult(task_id).status or "").upper()
            if state in {"PENDING", "STARTED", "RETRY"}:
                merged_lines = (contextual_lines + plain_tail_lines)[-tail:]
                seen = set()
                used_lines = []
                for line in merged_lines:
                    if line in seen:
                        continue
                    seen.add(line)
                    used_lines.append(line)
                used_lines = used_lines[-tail:]
            else:
                used_lines = contextual_lines[-tail:]
            filtered = True
        else:
            used_lines = plain_tail_lines
            filtered = False

        return ok(
            {
                "task_id": task_id,
                "tail": tail,
                "filtered": filtered,
                "text": "\n".join(used_lines),
                "log_file": log_file,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("读取任务日志失败")
        _raise_internal_error(
            f"读取任务日志失败: {str(e)}",
            details={"exception_type": e.__class__.__name__, "task_id": task_id},
        )
