from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..celery_app import celery_app
from ..contracts.responses import ok
from ..services import tasks as tasks_module
from ..services.projects import current_project_key

router = APIRouter(prefix="/agent-batch", tags=["agent_batch"])

_DEFAULT_CONTRACT_VERSION = "collect.request.v2"
_ALLOWED_CHANNELS = {"search.market", "source_library"}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _BatchItemRecord:
    item_id: str
    item_key: str
    project_key: str | None
    channel: str | None = None
    query_terms: list[str] = field(default_factory=list)
    max_items: int | None = None
    provider: str | None = None
    language: str | None = None
    days_back: int | None = None
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
    channel: str | None = Field(default=None, max_length=64)
    query_terms: list[str] = Field(default_factory=list)
    max_items: int | None = Field(default=None, ge=1, le=100)
    provider: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=16)
    days_back: int | None = Field(default=None, ge=1, le=365)
    contract_version: str = Field(default=_DEFAULT_CONTRACT_VERSION, max_length=64)
    input: dict[str, Any] | str | None = None
    override_params: dict[str, Any] = Field(default_factory=dict)


class AgentBatchSubmitBatch(BaseModel):
    jobs: list[AgentBatchItemSubmit] = Field(default_factory=list, min_length=1)


class AgentBatchSubmitRequest(BaseModel):
    project_key: str | None = Field(default=None, max_length=128)
    batch: AgentBatchSubmitBatch
    idempotency_key: str | None = Field(default=None, max_length=128)
    priority: int | None = Field(default=None, ge=0, le=9)
    rule_set_id: str | None = Field(default=None, max_length=128)
    rule_set: dict[str, Any] = Field(default_factory=dict)


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


class AgentBatchNlCommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=2000)
    project_key: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)


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


def _normalize_query_terms(raw: list[str]) -> list[str]:
    cleaned = []
    for term in raw:
        value = str(term or "").strip()
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def _extract_query_terms_from_command(command: str) -> list[str]:
    text = str(command or "").strip()
    if not text:
        return []
    separators = r"[，,、；;和与及\|/]+"
    segments = [seg.strip() for seg in re.split(separators, text) if seg.strip()]
    if not segments:
        return [text]
    return _normalize_query_terms(segments[:6])


def _detect_language(command: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", command or "") else "en"


def _extract_days_back(command: str) -> int:
    text = str(command or "")
    m_cn = re.search(r"最近\s*(\d{1,3})\s*天", text)
    if m_cn:
        return max(1, min(365, int(m_cn.group(1))))
    m_en = re.search(r"last\s+(\d{1,3})\s+days?", text, flags=re.IGNORECASE)
    if m_en:
        return max(1, min(365, int(m_en.group(1))))
    return 7


def _extract_max_items(command: str) -> int:
    text = str(command or "")
    m_cn = re.search(r"(\d{1,3})\s*条", text)
    if m_cn:
        return max(1, min(100, int(m_cn.group(1))))
    m_en = re.search(r"(top|first)\s+(\d{1,3})", text, flags=re.IGNORECASE)
    if m_en:
        return max(1, min(100, int(m_en.group(2))))
    return 20


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


def _submit_market_collect(
    *,
    query_terms: list[str],
    max_items: int,
    project_key: str | None,
    provider: str | None,
    language: str | None,
    days_back: int | None,
) -> str:
    task = tasks_module.task_ingest_market.delay(
        query_terms,
        max_items,
        True,
        project_key,
        None,
        days_back,
        language,
        provider,
    )
    return str(task.id)


def _normalize_channel(job: AgentBatchItemSubmit) -> str:
    channel = str(job.channel or "").strip().lower()
    if channel:
        return channel
    if str(job.item_key or "").strip() or str(job.source_id or "").strip():
        return "source_library"
    if isinstance(job.input, dict):
        if str(job.input.get("item_key") or "").strip() or str(job.input.get("source_id") or "").strip():
            return "source_library"
    return "search.market"


def _guard_batch_item(
    job: AgentBatchItemSubmit,
    *,
    project_key: str | None,
    rule_set: dict[str, Any],
) -> dict[str, Any] | None:
    channel = _normalize_channel(job)
    if channel not in _ALLOWED_CHANNELS:
        return {
            "reason_code": "unsupported_channel",
            "message": f"unsupported channel: {channel}",
            "details": {"channel": channel, "allowed_channels": sorted(_ALLOWED_CHANNELS)},
        }

    contract_version = str(job.contract_version or "").strip()
    if not contract_version:
        return {
            "reason_code": "contract_version_missing",
            "message": "contract_version is required",
            "details": {"channel": channel},
        }

    if bool(rule_set.get("require_project_key")) and not str(project_key or "").strip():
        return {
            "reason_code": "project_key_required_by_rule_set",
            "message": "project_key is required by rule_set",
            "details": {"channel": channel},
        }

    blocked_channels_raw = rule_set.get("blocked_channels")
    blocked_channels = {str(x or "").strip().lower() for x in blocked_channels_raw or [] if str(x or "").strip()}
    if channel in blocked_channels:
        return {
            "reason_code": "channel_blocked_by_rule_set",
            "message": f"channel blocked by rule_set: {channel}",
            "details": {"channel": channel},
        }

    if channel == "search.market":
        max_items_cap = rule_set.get("max_items_cap")
        if max_items_cap is not None:
            try:
                cap = max(1, min(100, int(max_items_cap)))
            except Exception:
                cap = 100
            requested = int(job.max_items or 20)
            if requested > cap:
                return {
                    "reason_code": "max_items_exceeds_rule_set_cap",
                    "message": f"max_items exceeds rule_set cap: {requested} > {cap}",
                    "details": {"requested": requested, "cap": cap},
                }

        allowlist_raw = rule_set.get("provider_allowlist")
        allowlist = {str(x or "").strip().lower() for x in allowlist_raw or [] if str(x or "").strip()}
        provider = str(job.provider or "auto").strip().lower()
        if allowlist and provider not in allowlist:
            return {
                "reason_code": "provider_blocked_by_rule_set",
                "message": f"provider blocked by rule_set: {provider}",
                "details": {"provider": provider, "allowlist": sorted(allowlist)},
            }

    return None


def _submit_batch_item(job: AgentBatchItemSubmit, *, project_key: str | None) -> tuple[str, str, dict[str, Any]]:
    channel = _normalize_channel(job)
    if channel == "search.market":
        query_terms = _normalize_query_terms(job.query_terms)
        if not query_terms and isinstance(job.input, dict):
            query_terms = _normalize_query_terms(job.input.get("query_terms") or [])
        if not query_terms:
            raise HTTPException(status_code=400, detail="search.market item requires query_terms")
        max_items = int(job.max_items or 20)
        task_id = _submit_market_collect(
            query_terms=query_terms,
            max_items=max_items,
            project_key=project_key,
            provider=job.provider or "auto",
            language=job.language or _detect_language(" ".join(query_terms)),
            days_back=job.days_back,
        )
        return task_id, "search.market", {
            "query_terms": query_terms,
            "max_items": max_items,
            "provider": job.provider or "auto",
            "language": job.language or _detect_language(" ".join(query_terms)),
            "days_back": job.days_back,
        }

    item_key = _resolve_item_key(job)
    task_id = _submit_source_item(
        item_key=item_key,
        project_key=project_key,
        override_params=dict(job.override_params or {}),
    )
    return task_id, "source_library", {"item_key": item_key, "override_params": dict(job.override_params or {})}


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

    rule_set = dict(payload.rule_set or {})
    for idx, item in enumerate(payload.batch.jobs):
        guard = _guard_batch_item(item, project_key=project_key, rule_set=rule_set)
        if guard is not None:
            rejected.append(
                {
                    "index": idx,
                    "reason_code": guard["reason_code"],
                    "reason": guard["message"],
                    "details": guard.get("details") or {},
                }
            )
            continue
        try:
            task_id, resolved_channel, resolved_payload = _submit_batch_item(item, project_key=project_key)
            item_id = str(item.item_id or f"{job_id}-item-{idx+1}").strip()
            record.items.append(
                _BatchItemRecord(
                    item_id=item_id,
                    item_key=str(resolved_payload.get("item_key") or ""),
                    channel=resolved_channel,
                    query_terms=list(resolved_payload.get("query_terms") or []),
                    max_items=resolved_payload.get("max_items"),
                    provider=resolved_payload.get("provider"),
                    language=resolved_payload.get("language"),
                    days_back=resolved_payload.get("days_back"),
                    project_key=project_key,
                    override_params=dict(item.override_params or {}),
                    task_id=task_id,
                )
            )
            accepted.append(
                {
                    "index": idx,
                    "item_id": item_id,
                    "task_id": task_id,
                    "channel": resolved_channel,
                    "item_key": resolved_payload.get("item_key"),
                    "query_terms": resolved_payload.get("query_terms"),
                    "contract_version": item.contract_version,
                }
            )
        except Exception as exc:  # noqa: BLE001
            rejected.append({"index": idx, "reason_code": "dispatch_error", "reason": str(exc)})

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
            "rule_set_id": payload.rule_set_id,
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
                "input": {
                    "item_key": item.item_key,
                    "channel": item.channel,
                    "query_terms": item.query_terms,
                    "max_items": item.max_items,
                    "provider": item.provider,
                    "language": item.language,
                    "days_back": item.days_back,
                    "override_params": item.override_params,
                },
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
        if (item.channel or "source_library") == "search.market":
            new_task_id = _submit_market_collect(
                query_terms=list(item.query_terms or []),
                max_items=int(item.max_items or 20),
                project_key=item.project_key,
                provider=item.provider,
                language=item.language,
                days_back=item.days_back,
            )
        else:
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
                channel=item.channel,
                query_terms=list(item.query_terms or []),
                max_items=item.max_items,
                provider=item.provider,
                language=item.language,
                days_back=item.days_back,
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
    unsupported_fields = sorted(
        [
            k
            for k in payload.rule_set.keys()
            if k not in {"blocked_channels", "max_items_cap", "provider_allowlist", "require_project_key"}
        ]
    )
    if unsupported_fields:
        warnings.append({"code": "rule_set_unsupported_fields", "message": "rule_set contains unsupported fields"})
    return ok(
        {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "normalized_rule_set": payload.rule_set,
            "unsupported_fields": unsupported_fields,
        }
    )


@router.post("/nl-command")
def run_agent_batch_nl_command(payload: AgentBatchNlCommandRequest) -> dict[str, Any]:
    command = str(payload.command or "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="command is required")
    parsed = {
        "channel": "search.market",
        "query_terms": _extract_query_terms_from_command(command),
        "max_items": _extract_max_items(command),
        "provider": "auto",
        "language": _detect_language(command),
        "days_back": _extract_days_back(command),
    }
    submit_payload = AgentBatchSubmitRequest(
        project_key=payload.project_key,
        idempotency_key=payload.idempotency_key,
        batch=AgentBatchSubmitBatch(
            jobs=[
                AgentBatchItemSubmit(
                    channel=parsed["channel"],
                    query_terms=parsed["query_terms"],
                    max_items=parsed["max_items"],
                    provider=parsed["provider"],
                    language=parsed["language"],
                    days_back=parsed["days_back"],
                )
            ]
        ),
    )
    submit_resp = submit_agent_batch_job(submit_payload)
    return ok({"command": command, "parsed": parsed, "submit": submit_resp.get("data")})
