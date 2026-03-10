from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..celery_app import celery_app
from ..contracts.responses import ok
from ..services import tasks as tasks_module
from ..services.projects import current_project_key

router = APIRouter(prefix="/agent-batch", tags=["agent_batch"])


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _BatchItemRecord:
    item_id: str
    item_key: str
    project_key: str | None
    override_params: dict[str, Any] = field(default_factory=dict)
    task_id: str = ""
    created_at: str = field(default_factory=_utcnow_iso)


@dataclass
class _BatchJobRecord:
    job_id: str
    project_key: str | None
    created_at: str = field(default_factory=_utcnow_iso)
    idempotency_key: str | None = None
    items: list[_BatchItemRecord] = field(default_factory=list)


_BATCH_JOB_REGISTRY: dict[str, _BatchJobRecord] = {}
_IDEMPOTENCY_INDEX: dict[str, str] = {}


class AgentBatchItemSubmit(BaseModel):
    item_id: str | None = Field(default=None, max_length=128)
    source_id: str | None = Field(default=None, max_length=128)
    item_key: str | None = Field(default=None, max_length=128)
    input: dict[str, Any] | str | None = None
    override_params: dict[str, Any] = Field(default_factory=dict)


class AgentBatchSubmitBatch(BaseModel):
    jobs: list[AgentBatchItemSubmit] = Field(default_factory=list, min_length=1)


class AgentBatchSubmitRequest(BaseModel):
    project_key: str | None = Field(default=None, max_length=128)
    batch: AgentBatchSubmitBatch
    idempotency_key: str | None = Field(default=None, max_length=128)
    priority: int | None = Field(default=None, ge=0, le=9)


class AgentBatchRetryRequest(BaseModel):
    scope: str = Field(default="job")
    item_ids: list[str] = Field(default_factory=list)
    reason: str | None = Field(default=None, max_length=512)
    max_retries: int | None = Field(default=None, ge=1, le=20)


class RuleSetValidateRequest(BaseModel):
    rule_set_id: str | None = Field(default=None, max_length=128)
    rule_set: dict[str, Any] = Field(default_factory=dict)
    batch_schema_version: str | None = Field(default=None, max_length=64)
    sample_items: list[dict[str, Any]] = Field(default_factory=list)


def _resolve_project_key(project_key: str | None) -> str | None:
    explicit = (project_key or "").strip()
    if explicit:
        return explicit
    fallback = (current_project_key() or "").strip()
    return fallback or None


def _resolve_item_key(job: AgentBatchItemSubmit) -> str:
    for candidate in (job.item_key, job.source_id):
        value = str(candidate or "").strip()
        if value:
            return value
    if isinstance(job.input, dict):
        for key in ("item_key", "source_id"):
            value = str(job.input.get(key) or "").strip()
            if value:
                return value
    raise HTTPException(status_code=400, detail="each batch item requires item_key or source_id")


def _load_job(job_id: str) -> _BatchJobRecord:
    record = _BATCH_JOB_REGISTRY.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"agent batch job not found: {job_id}")
    return record


def _task_snapshot(task_id: str) -> dict[str, Any]:
    result = celery_app.AsyncResult(task_id)
    status = str(result.status or "").lower() or "unknown"
    return {
        "task_id": task_id,
        "status": status,
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else None,
        "failed": result.failed() if result.ready() else None,
        "result": result.result if result.ready() else None,
    }


def _submit_source_item(*, item_key: str, project_key: str | None, override_params: dict[str, Any]) -> str:
    task = tasks_module.task_run_source_library_item.delay(item_key, project_key, override_params or {})
    return str(task.id)


@router.post("/jobs")
def submit_agent_batch_job(payload: AgentBatchSubmitRequest) -> dict[str, Any]:
    project_key = _resolve_project_key(payload.project_key)
    idem = str(payload.idempotency_key or "").strip() or None
    if idem and idem in _IDEMPOTENCY_INDEX:
        existing_job_id = _IDEMPOTENCY_INDEX[idem]
        existing = _load_job(existing_job_id)
        return ok(
            {
                "job_id": existing.job_id,
                "status": "accepted",
                "accepted_count": len(existing.items),
                "rejected_count": 0,
                "accepted_job_items": [{"item_id": it.item_id, "task_id": it.task_id} for it in existing.items],
                "rejected_job_items": [],
                "created_at": existing.created_at,
                "idempotency_reused": True,
            }
        )

    job_id = f"abj-{uuid4().hex[:16]}"
    record = _BatchJobRecord(job_id=job_id, project_key=project_key, idempotency_key=idem)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for idx, item in enumerate(payload.batch.jobs):
        try:
            item_key = _resolve_item_key(item)
            item_id = str(item.item_id or f"{job_id}-item-{idx+1}").strip()
            task_id = _submit_source_item(
                item_key=item_key,
                project_key=project_key,
                override_params=dict(item.override_params or {}),
            )
            record.items.append(
                _BatchItemRecord(
                    item_id=item_id,
                    item_key=item_key,
                    project_key=project_key,
                    override_params=dict(item.override_params or {}),
                    task_id=task_id,
                )
            )
            accepted.append({"index": idx, "item_id": item_id, "task_id": task_id, "item_key": item_key})
        except Exception as exc:  # noqa: BLE001
            rejected.append({"index": idx, "reason": str(exc)})

    _BATCH_JOB_REGISTRY[job_id] = record
    if idem:
        _IDEMPOTENCY_INDEX[idem] = job_id
    return ok(
        {
            "job_id": job_id,
            "status": "accepted",
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "accepted_job_items": accepted,
            "rejected_job_items": rejected,
            "created_at": record.created_at,
            "links": {
                "self": f"/api/v1/agent-batch/jobs/{job_id}",
                "items": f"/api/v1/agent-batch/jobs/{job_id}/items",
                "events": f"/api/v1/agent-batch/jobs/{job_id}/events",
                "retry": f"/api/v1/agent-batch/jobs/{job_id}/retry",
            },
        }
    )


@router.get("/jobs/{job_id}")
def get_agent_batch_job(job_id: str) -> dict[str, Any]:
    record = _load_job(job_id)
    snapshots = [_task_snapshot(item.task_id) for item in record.items]
    total = len(snapshots)
    succeeded = sum(1 for it in snapshots if it.get("status") == "success")
    failed = sum(1 for it in snapshots if it.get("status") == "failure")
    running = sum(1 for it in snapshots if it.get("status") in {"pending", "started", "retry", "running"})
    phase = "completed" if total > 0 and (succeeded + failed) == total else "running"
    return ok(
        {
            "job_id": record.job_id,
            "status": phase,
            "phase": phase,
            "progress": {
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
                "running": running,
                "queued": max(0, total - succeeded - failed - running),
            },
            "started_at": record.created_at,
            "updated_at": _utcnow_iso(),
            "finished_at": _utcnow_iso() if phase == "completed" else None,
            "retry_count": 0,
            "error": None,
            "meta": {"project_key": record.project_key},
        }
    )


@router.get("/jobs/{job_id}/items")
def list_agent_batch_items(job_id: str) -> dict[str, Any]:
    record = _load_job(job_id)
    items = []
    for item in record.items:
        snap = _task_snapshot(item.task_id)
        items.append(
            {
                "item_id": item.item_id,
                "task_id": item.task_id,
                "status": snap.get("status"),
                "input": {"item_key": item.item_key, "override_params": item.override_params},
                "output": snap.get("result") if snap.get("successful") else None,
                "error": snap.get("result") if snap.get("failed") else None,
                "last_update_at": _utcnow_iso(),
            }
        )
    return ok({"items": items, "pagination": {"next_cursor": None, "has_more": False}})


@router.post("/jobs/{job_id}/retry")
def retry_agent_batch_job(job_id: str, payload: AgentBatchRetryRequest) -> dict[str, Any]:
    record = _load_job(job_id)
    target_ids = set(payload.item_ids or [])
    replayed_task_ids: list[str] = []
    for item in list(record.items):
        if target_ids and item.item_id not in target_ids:
            continue
        snap = _task_snapshot(item.task_id)
        if snap.get("status") not in {"failure", "revoked"}:
            continue
        new_task_id = _submit_source_item(
            item_key=item.item_key,
            project_key=item.project_key,
            override_params=item.override_params,
        )
        replayed_task_ids.append(new_task_id)
        record.items.append(
            _BatchItemRecord(
                item_id=f"{item.item_id}-retry-{len(replayed_task_ids)}",
                item_key=item.item_key,
                project_key=item.project_key,
                override_params=item.override_params,
                task_id=new_task_id,
            )
        )
    return ok(
        {
            "job_id": job_id,
            "retry_session_id": f"retry-{uuid4().hex[:12]}",
            "status": "accepted",
            "retry_count": len(replayed_task_ids),
            "targets": replayed_task_ids,
        }
    )


@router.get("/jobs/{job_id}/events")
def get_agent_batch_events(job_id: str) -> dict[str, Any]:
    record = _load_job(job_id)
    events = []
    for item in record.items:
        snap = _task_snapshot(item.task_id)
        events.append(
            {
                "id": f"evt-{item.task_id}",
                "event_type": f"task.{snap.get('status')}",
                "ts": _utcnow_iso(),
                "item_id": item.item_id,
                "severity": "error" if snap.get("failed") else "info",
                "message": f"task {item.task_id} status={snap.get('status')}",
                "payload": {"task_id": item.task_id, "status": snap.get("status")},
            }
        )
    return ok({"events": events, "pagination": {"next_cursor": None, "has_more": False}})


@router.post("/rule-sets/validate")
def validate_agent_batch_rule_set(payload: RuleSetValidateRequest) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not payload.rule_set:
        errors.append({"code": "rule_set_empty", "message": "rule_set is required"})
    if payload.batch_schema_version and not str(payload.batch_schema_version).strip():
        errors.append({"code": "schema_version_invalid", "message": "batch_schema_version must be non-empty"})
    if payload.sample_items and len(payload.sample_items) > 500:
        warnings.append({"code": "sample_items_truncated", "message": "sample_items exceeds 500; consider reducing"})
    return ok(
        {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "normalized_rule_set": payload.rule_set,
            "unsupported_fields": [],
        }
    )
