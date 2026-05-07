from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import re
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from ..contracts import ErrorCode, error_response
from ..celery_app import celery_app
from ..contracts.responses import ok
from ..settings.config import get_effective_project_key_enforcement_mode, settings
from ..services.agent_batch.approval_binding import (
    REASON_APPROVAL_REQUIRED,
    approve_approval,
    cleanup_expired,
    request_approval,
    verify_approval_token,
)
from ..services.agent_batch.executor_health import inspect_executor_health
from ..services.agent_batch.agent_loop import run_agent_batch_nl_command_loop
from ..services.agent_batch.benchmark import build_search_policy_benchmark_pack, evaluate_search_policy_gate
from ..services.agent_batch.routing import apply_async_or_delay, resolve_queue_for_lane, validate_lane
from ..services.agent_batch.planner import plan_batch_search_command
from ..services.agent_batch.task_contract import (
    build_agent_batch_approval_argv,
    build_agent_batch_dispatch_invocation,
    build_agent_batch_execution_registry,
    build_agent_batch_submit_item_data,
    build_source_library_override_params,
    get_allowed_override_params_by_channel,
    get_agent_batch_known_channels,
    infer_agent_batch_channel,
    list_agent_batch_execution_bindings,
    resolve_agent_batch_lane,
)
from ..services.agent_sessions import get_agent_session_service
from ..services.skill_runtime import invoke_skill
from ..services import tasks as tasks_module
from ..services.projects import current_project_key
from ..services.workflow_graph.handoff_store import handoff_store

router = APIRouter(prefix="/agent-batch", tags=["agent_batch"])
logger = logging.getLogger(__name__)

_DEFAULT_CONTRACT_VERSION = "collect.request.v2"
_ALLOWED_CHANNELS = get_agent_batch_known_channels()
_ALLOWED_OVERRIDE_PARAMS_BY_CHANNEL = get_allowed_override_params_by_channel()


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
    lane: str | None = None
    workflow_run_id: str | None = None
    trace_id: str | None = None
    created_at: str = field(default_factory=_utcnow_iso)


@dataclass
class _BatchJobRecord:
    job_id: str
    project_key: str | None
    created_at: str = field(default_factory=_utcnow_iso)
    idempotency_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
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
    urls: list[str] = Field(default_factory=list)
    scope: str | None = Field(default=None, max_length=64)
    platforms: list[str] = Field(default_factory=list)
    source_mode: str | None = Field(default=None, max_length=64)
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
    dry_run: bool = Field(default=False)
    enable_bounded_retry: bool = Field(default=False)
    enable_limited_branching: bool = Field(default=False)
    wait_for_completion: bool = Field(default=False)
    completion_timeout_seconds: int = Field(default=90, ge=1, le=900)
    completion_poll_seconds: float = Field(default=2.0, ge=0.2, le=10.0)


class AgentBatchApprovalRequest(BaseModel):
    argv: list[str] = Field(default_factory=list)
    cwd: str | None = Field(default=None, max_length=512)
    env: dict[str, str] = Field(default_factory=dict)
    channel: str | None = Field(default=None, max_length=64)
    project_key: str | None = Field(default=None, max_length=128)
    requester_session_id: str | None = Field(default=None, max_length=64)
    requester_task_id: str | None = Field(default=None, max_length=64)
    requester_actor: str = Field(default="user_facing_assistant", max_length=64)


class AgentBatchApprovalResolveRequest(BaseModel):
    approved: bool = Field(default=True)


def _submit_jobs_from_loop_tasks(
    tasks: list[dict[str, Any]],
    project_key: str | None,
    idempotency_key: str | None,
) -> dict[str, Any]:
    planned_jobs: list[AgentBatchItemSubmit] = []
    for task in tasks:
        planned_jobs.append(_build_agent_batch_submit_item_from_task(task))
    submit_payload = AgentBatchSubmitRequest(
        project_key=project_key,
        idempotency_key=idempotency_key,
        batch=AgentBatchSubmitBatch(jobs=planned_jobs),
    )
    submit_resp = submit_agent_batch_job(submit_payload)
    return dict(submit_resp.get("data") or {})


def _build_agent_batch_submit_item_from_task(task: dict[str, Any]) -> AgentBatchItemSubmit:
    channel = str(task.get("channel") or "search.market").strip().lower() or "search.market"
    default_language = str(task.get("language") or "").strip()
    if not default_language and channel == "search.market":
        default_language = _detect_language(" ".join(list(task.get("query_terms") or [])))
    submit_item = build_agent_batch_submit_item_data(task, idx=1, default_language=default_language)
    return AgentBatchItemSubmit(**submit_item)


def _resolve_project_key(project_key: str | None) -> str | None:
    explicit = (project_key or "").strip()
    if explicit:
        return explicit
    if get_effective_project_key_enforcement_mode() == "require":
        raise HTTPException(
            status_code=400,
            detail=error_response(
                ErrorCode.PROJECT_KEY_REQUIRED,
                "project_key is required. Please select a project first.",
            ),
        )
    fallback = (current_project_key() or "").strip()
    if fallback:
        logger.warning("project_key_fallback_used endpoint=agent_batch resolved_project_key=%s", fallback)
        return fallback
    raise HTTPException(
        status_code=400,
        detail=error_response(
            ErrorCode.PROJECT_KEY_REQUIRED,
            "project_key is required. Please select a project first.",
        ),
    )


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
    _raise_invalid_input("each batch item requires item_key or source_id")


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
        _raise_not_found(f"agent batch job not found: {job_id}")
    return record


def _attach_loop_metadata(job_id: str, loop_result: dict[str, Any] | None) -> None:
    if not job_id:
        return
    record = _BATCH_JOB_REGISTRY.get(job_id)
    if record is None:
        return
    loop_payload = dict(loop_result or {})
    plan = dict(loop_payload.get("plan") or {})
    search_brief = dict(plan.get("search_brief") or {})
    if not search_brief:
        return
    branching = dict(plan.get("branching") or {})
    search_critic = dict(plan.get("search_critic") or {})
    search_retry = dict(plan.get("search_retry") or {})
    branching_stage = next(
        (dict(stage) for stage in list(loop_payload.get("stages") or []) if str(stage.get("name") or "") == "branching"),
        {},
    )
    search_brief_stage = next(
        (dict(stage) for stage in list(loop_payload.get("stages") or []) if str(stage.get("name") or "") == "search_brief"),
        {},
    )
    search_critic_stage = next(
        (dict(stage) for stage in list(loop_payload.get("stages") or []) if str(stage.get("name") or "") == "search_critic"),
        {},
    )
    search_retry_stage = next(
        (dict(stage) for stage in list(loop_payload.get("stages") or []) if str(stage.get("name") or "") == "search_retry"),
        {},
    )
    record.metadata.update(
        {
            "loop_id": str(loop_payload.get("loop_id") or "").strip() or None,
            "branching": branching,
            "search_brief": search_brief,
            "search_critic": search_critic,
            "search_retry": search_retry,
            "submit_rounds": list(loop_payload.get("submit_rounds") or []),
            "stage_artifacts": {
                "branching": branching_stage,
                "search_brief": search_brief_stage,
                "search_critic": search_critic_stage,
                "search_retry": search_retry_stage,
            },
        }
    )


def _project_agent_session_from_loop(
    *,
    command: str,
    request_payload: AgentBatchNlCommandRequest,
    loop_result: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        service = get_agent_session_service()
        bundle = service.project_agent_batch_compat(
            command=command,
            project_key=request_payload.project_key,
            request_payload=request_payload.model_dump(),
            loop_result=loop_result,
        )
    except Exception:
        return None

    session = dict(bundle.get("session") or {})
    session_id = str(session.get("session_id") or "").strip()
    compat_job_id = str(session.get("compat_job_id") or "").strip()
    if compat_job_id:
        record = _BATCH_JOB_REGISTRY.get(compat_job_id)
        if record is not None:
            record.metadata.update(
                {
                    "session_id": session_id,
                    "root_task_id": session.get("root_task_id"),
                    "current_phase": session.get("current_phase"),
                    "compat_mode": True,
                    "compat_projection_version": "claude-agent.v1",
                }
            )
    return session


def _project_agent_session_from_job_submission(
    *,
    record: _BatchJobRecord,
    request_payload: AgentBatchSubmitRequest,
    accepted_items: list[dict[str, Any]],
    rejected_items: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        service = get_agent_session_service()
        bundle = service.project_agent_batch_job_submission(
            job_id=record.job_id,
            project_key=record.project_key,
            request_payload=request_payload.model_dump(),
            accepted_items=accepted_items,
            rejected_items=rejected_items,
            rule_set_id=request_payload.rule_set_id,
        )
    except Exception:
        return None
    session = dict(bundle.get("session") or {})
    session_id = str(session.get("session_id") or "").strip()
    if session_id:
        record.metadata.update(
            {
                "session_id": session_id,
                "root_task_id": session.get("root_task_id"),
                "current_phase": session.get("current_phase"),
                "compat_mode": True,
                "compat_projection_version": session.get("compat_projection_version") or "agent_batch.jobs.v1",
            }
        )
    return session


def _project_agent_session_from_job_state(
    *,
    record: _BatchJobRecord,
    snapshots: list[dict[str, Any]],
    phase: str,
    progress: dict[str, Any],
) -> dict[str, Any] | None:
    session_id = str((record.metadata or {}).get("session_id") or "").strip()
    if not session_id:
        return None
    projected_items: list[dict[str, Any]] = []
    for item, snapshot in zip(record.items, snapshots):
        projected_items.append(
            {
                "item_id": item.item_id,
                "index": len(projected_items) + 1,
                "task_id": item.task_id,
                "channel": item.channel,
                "item_key": item.item_key,
                "lane": item.lane,
                "workflow_run_id": item.workflow_run_id,
                "trace_id": item.trace_id,
                "run_id": _resolve_run_id(item, snapshot),
                "snapshot": snapshot,
            }
        )
    try:
        bundle = get_agent_session_service().project_agent_batch_job_state(
            compat_job_id=record.job_id,
            projected_items=projected_items,
            phase=phase,
            progress=progress,
        )
    except Exception:
        return None
    session = dict((bundle or {}).get("session") or {})
    if session:
        record.metadata.update(
            {
                "session_id": session.get("session_id"),
                "root_task_id": session.get("root_task_id"),
                "current_phase": session.get("current_phase"),
                "compat_projection_version": session.get("compat_projection_version") or "agent_batch.jobs.v1",
            }
        )
    return session or None


def _task_snapshot(task_id: str) -> dict[str, Any]:
    result = celery_app.AsyncResult(task_id)
    status = str(result.status or "").lower() or "unknown"
    raw_result = result.result if result.ready() else None
    try:
        safe_result = jsonable_encoder(
            raw_result,
            custom_encoder={
                BaseException: lambda exc: str(exc) or exc.__class__.__name__,
            },
        )
    except Exception:
        safe_result = str(raw_result) if raw_result is not None else None
    return {
        "task_id": task_id,
        "status": status,
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else None,
        "failed": result.failed() if result.ready() else None,
        "result": safe_result,
    }


def _job_progress_from_snapshots(snapshots: list[dict[str, Any]]) -> dict[str, int]:
    total = len(snapshots)
    succeeded = sum(1 for it in snapshots if it.get("status") == "success")
    failed = sum(1 for it in snapshots if it.get("status") == "failure")
    running = sum(1 for it in snapshots if it.get("status") in {"pending", "started", "retry", "running"})
    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "running": running,
        "queued": max(0, total - succeeded - failed - running),
    }


def _await_job_completion(*, job_id: str, timeout_seconds: int, poll_seconds: float) -> dict[str, Any]:
    started_ts = time.time()
    deadline = started_ts + max(1, int(timeout_seconds))
    poll = max(0.2, min(float(poll_seconds), 10.0))
    record = _load_job(job_id)
    last_snapshots: list[dict[str, Any]] = []

    while True:
        last_snapshots = [_task_snapshot(item.task_id) for item in record.items]
        progress = _job_progress_from_snapshots(last_snapshots)
        completed = progress["total"] > 0 and (progress["succeeded"] + progress["failed"]) == progress["total"]
        now = time.time()
        timed_out = now >= deadline
        if completed or timed_out:
            items = []
            for item, snap in zip(record.items, last_snapshots):
                run_id = _resolve_run_id(item, snap)
                items.append(
                    {
                        "item_id": item.item_id,
                        "task_id": item.task_id,
                        "status": snap.get("status"),
                        "run_id": run_id,
                        "output": snap.get("result") if snap.get("successful") else None,
                        "error": snap.get("result") if snap.get("failed") else None,
                    }
                )
            return {
                "job_id": job_id,
                "completed": bool(completed),
                "timed_out": bool(timed_out and not completed),
                "phase": "completed" if completed else "running",
                "progress": progress,
                "elapsed_seconds": round(now - started_ts, 3),
                "items": items,
            }
        time.sleep(poll)


def _build_failure_reason_metrics(limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 100))
    reason_counts: dict[str, int] = {}
    sample_events: dict[str, dict[str, Any]] = {}

    for job in _BATCH_JOB_REGISTRY.values():
        for item in job.items:
            snap = _task_snapshot(item.task_id)
            status = str(snap.get("status") or "")
            if status not in {"failure", "revoked"}:
                continue
            result = snap.get("result")
            reason_code = "task_failed"
            if isinstance(result, dict):
                reason_code = str(result.get("reason_code") or result.get("code") or reason_code).strip() or reason_code
            elif result is not None:
                reason_text = str(result)
                if "unsupported collect channel" in reason_text:
                    reason_code = "unsupported_channel"
                elif "rate limit" in reason_text.lower():
                    reason_code = "rate_limited"
            reason_counts[reason_code] = int(reason_counts.get(reason_code) or 0) + 1
            sample_events.setdefault(
                reason_code,
                {
                    "job_id": job.job_id,
                    "item_id": item.item_id,
                    "task_id": item.task_id,
                    "status": status,
                    "ts": _utcnow_iso(),
                },
            )

    items = [
        {"reason_code": code, "count": count, "sample": sample_events.get(code)}
        for code, count in sorted(reason_counts.items(), key=lambda kv: kv[1], reverse=True)[:safe_limit]
    ]
    return {
        "contract_version": "agent_batch.metrics.v1",
        "taxonomy_version": "agent_batch.reason_taxonomy.v1",
        "items": items,
        "total_reasons": len(reason_counts),
        "taxonomy_coverage": 1.0 if not items else round(len(items) / max(1, len(reason_counts)), 4),
        "generated_at": _utcnow_iso(),
    }


def _build_search_policy_metrics() -> dict[str, Any]:
    next_action_counts: dict[str, int] = {}
    retry_outcome_counts = {"scheduled": 0, "skipped": 0}
    scores: list[float] = []
    round_counts: list[int] = []

    for job in _BATCH_JOB_REGISTRY.values():
        metadata = dict(job.metadata or {})
        critic = dict(metadata.get("search_critic") or {})
        retry = dict(metadata.get("search_retry") or {})
        submit_rounds = list(metadata.get("submit_rounds") or [])

        if critic:
            try:
                scores.append(float(critic.get("score") or 0.0))
            except Exception:
                pass
            next_action = str(critic.get("next_action") or "").strip() or "unknown"
            next_action_counts[next_action] = int(next_action_counts.get(next_action) or 0) + 1

        if retry:
            if bool(retry.get("scheduled")):
                retry_outcome_counts["scheduled"] += 1
            else:
                retry_outcome_counts["skipped"] += 1

        if submit_rounds:
            round_counts.append(len(submit_rounds))

    return {
        "contract_version": "agent_batch.search_policy_metrics.v1",
        "job_count": len(_BATCH_JOB_REGISTRY),
        "critic_job_count": len(scores),
        "average_critic_score": round(sum(scores) / len(scores), 4) if scores else None,
        "next_action_counts": next_action_counts,
        "retry_outcome_counts": retry_outcome_counts,
        "average_submit_rounds": round(sum(round_counts) / len(round_counts), 4) if round_counts else None,
        "generated_at": _utcnow_iso(),
    }


def _build_item_workflow_run_id(*, job_id: str, item_id: str) -> str:
    safe_item = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(item_id or "").strip()) or "item"
    return f"{job_id}-{safe_item}-run"


def _build_item_trace_id(*, job_id: str, item_id: str) -> str:
    safe_item = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(item_id or "").strip()) or "item"
    return f"trace-{job_id}-{safe_item}"


def _resolve_lane(*, channel: str, priority: int | None) -> str:
    return resolve_agent_batch_lane(channel, priority)


def _resolve_queue_for_lane(lane: str) -> str:
    return resolve_queue_for_lane(lane)


def _apply_async_or_delay(task_func: Any, args: tuple[Any, ...], kwargs: dict[str, Any], lane: str) -> Any:
    return apply_async_or_delay(task_func, args, kwargs, lane)


def _resolve_run_id(item: _BatchItemRecord, task_snapshot: dict[str, Any]) -> str | None:
    pinned = str(item.workflow_run_id or "").strip()
    if pinned:
        return pinned
    result = task_snapshot.get("result")
    if isinstance(result, dict):
        for key in ("run_id", "workflow_run_id"):
            value = str(result.get(key) or "").strip()
            if value:
                return value
        for parent in ("data", "meta", "persistence", "workflow_graph"):
            nested = result.get(parent)
            if not isinstance(nested, dict):
                continue
            for key in ("run_id", "workflow_run_id"):
                value = str(nested.get(key) or "").strip()
                if value:
                    return value
    for key in ("run_id", "workflow_run_id"):
        value = str(item.override_params.get(key) or "").strip()
        if value:
            return value
    return None


def _invoke_agent_batch_dispatch(channel: str, payload: dict[str, Any], *, trace_id: str | None) -> dict[str, Any]:
    invocation = build_agent_batch_dispatch_invocation(channel, payload, trace_id=trace_id)
    return invoke_skill(
        skill_id=str(invocation.get("skill_id") or ""),
        payload=dict(invocation.get("payload") or {}),
        context=dict(invocation.get("context") or {}),
    )


def _submit_source_item(
    *,
    item_key: str,
    project_key: str | None,
    override_params: dict[str, Any],
    trace_id: str | None = None,
    lane: str = "main",
    workflow_run_id: str | None = None,
) -> str:
    invoked = _invoke_agent_batch_dispatch(
        "source_library",
        {
            "item_key": item_key,
            "project_key": project_key,
            "override_params": dict(override_params or {}),
            "trace_id": trace_id,
            "lane": lane,
            "workflow_run_id": workflow_run_id,
        },
        trace_id=trace_id,
    )
    result = invoked.get("result")
    if not isinstance(result, dict) or not str(result.get("task_id") or "").strip():
        raise RuntimeError("skill dispatch returned no task_id for source_library_item")
    return str(result.get("task_id"))


def _submit_market_collect(
    *,
    query_terms: list[str],
    max_items: int,
    project_key: str | None,
    provider: str | None,
    language: str | None,
    days_back: int | None,
    override_params: dict[str, Any] | None = None,
    trace_id: str | None = None,
    lane: str = "main",
    workflow_run_id: str | None = None,
) -> str:
    invoked = _invoke_agent_batch_dispatch(
        "search.market",
        {
            "query_terms": list(query_terms or []),
            "max_items": int(max_items),
            "project_key": project_key,
            "provider": provider,
            "language": language,
            "days_back": days_back,
            "override_params": dict(override_params or {}),
            "trace_id": trace_id,
            "lane": lane,
            "workflow_run_id": workflow_run_id,
        },
        trace_id=trace_id,
    )
    result = invoked.get("result")
    if not isinstance(result, dict) or not str(result.get("task_id") or "").strip():
        raise RuntimeError("skill dispatch returned no task_id for market_collect")
    return str(result.get("task_id"))


def _skill_dispatch_source_library_item(payload: dict[str, Any]) -> dict[str, Any]:
    item_key = str((payload or {}).get("item_key") or "").strip()
    if not item_key:
        raise ValueError("item_key is required")
    project_key = str((payload or {}).get("project_key") or "").strip() or None
    override_params = dict((payload or {}).get("override_params") or {})
    trace_id = str((payload or {}).get("trace_id") or "").strip() or None
    lane = validate_lane((payload or {}).get("lane"), fallback="main")
    workflow_run_id = str((payload or {}).get("workflow_run_id") or "").strip() or None
    task = _apply_async_or_delay(
        tasks_module.task_run_source_library_item,
        (item_key, project_key, override_params),
        {"workflow_run_id": workflow_run_id, "trace_id": trace_id},
        lane,
    )
    return {"task_id": str(task.id)}


def _skill_dispatch_market_collect(payload: dict[str, Any]) -> dict[str, Any]:
    query_terms = _normalize_query_terms(list((payload or {}).get("query_terms") or []))
    if not query_terms:
        raise ValueError("query_terms is required")
    max_items = int((payload or {}).get("max_items") or 20)
    max_items = max(1, min(100, max_items))
    project_key = str((payload or {}).get("project_key") or "").strip() or None
    provider = str((payload or {}).get("provider") or "auto").strip() or "auto"
    language = str((payload or {}).get("language") or _detect_language(" ".join(query_terms))).strip()
    days_back_raw = (payload or {}).get("days_back")
    days_back = int(days_back_raw) if isinstance(days_back_raw, int) else None
    override_params = dict((payload or {}).get("override_params") or {})
    enable_extraction = bool(override_params.get("enable_extraction", True))
    start_offset = override_params.get("start_offset")
    if not isinstance(start_offset, int):
        start_offset = None
    trace_id = str((payload or {}).get("trace_id") or "").strip() or None
    lane = validate_lane((payload or {}).get("lane"), fallback="main")
    workflow_run_id = str((payload or {}).get("workflow_run_id") or "").strip() or None
    task = _apply_async_or_delay(
        tasks_module.task_ingest_market,
        (query_terms, max_items, enable_extraction, project_key, start_offset, days_back, language, provider),
        {"workflow_run_id": workflow_run_id, "trace_id": trace_id},
        lane,
    )
    return {"task_id": str(task.id)}


def _normalize_channel(job: AgentBatchItemSubmit) -> str:
    inferred = infer_agent_batch_channel(
        {
            "channel": job.channel,
            "item_key": job.item_key,
            "source_id": job.source_id,
            "query_terms": list(job.query_terms or []),
            "input": job.input if isinstance(job.input, dict) else None,
        }
    )
    return str(inferred or "").strip().lower()


def _validate_override_params_for_channel(channel: str, override_params: dict[str, Any] | None) -> dict[str, Any] | None:
    params = dict(override_params or {})
    allowed = _ALLOWED_OVERRIDE_PARAMS_BY_CHANNEL.get(channel)
    if not allowed:
        return None
    unknown = sorted(key for key in params.keys() if str(key or "").strip() and key not in allowed)
    if unknown:
        return {
            "reason_code": "override_params_keys_unsupported",
            "message": f"override_params contains unsupported keys for channel={channel}",
            "details": {
                "channel": channel,
                "unsupported_keys": unknown,
                "allowed_keys": sorted(allowed),
            },
        }
    return None


def _enforce_search_market_rule_set(job: AgentBatchItemSubmit, rule_set: dict[str, Any]) -> dict[str, Any] | None:
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


def _submit_search_market_job(
    job: AgentBatchItemSubmit,
    *,
    project_key: str | None,
    lane: str,
    trace_id: str | None,
    workflow_run_id: str,
) -> tuple[str, dict[str, Any]]:
    query_terms = _normalize_query_terms(job.query_terms)
    if not query_terms and isinstance(job.input, dict):
        query_terms = _normalize_query_terms(job.input.get("query_terms") or [])
    if not query_terms:
        _raise_invalid_input("search.market item requires query_terms")
    max_items = int(job.max_items or 20)
    language = job.language or _detect_language(" ".join(query_terms))
    override_params = dict(job.override_params or {})
    task_id = _submit_market_collect(
        query_terms=query_terms,
        max_items=max_items,
        project_key=project_key,
        provider=job.provider or "auto",
        language=language,
        days_back=job.days_back,
        override_params=override_params,
        trace_id=trace_id,
        lane=lane,
        workflow_run_id=workflow_run_id,
    )
    return task_id, {
        "query_terms": query_terms,
        "max_items": max_items,
        "provider": job.provider or "auto",
        "language": language,
        "days_back": job.days_back,
        "override_params": override_params,
    }


def _submit_source_library_job(
    job: AgentBatchItemSubmit,
    *,
    project_key: str | None,
    lane: str,
    trace_id: str | None,
    workflow_run_id: str,
) -> tuple[str, dict[str, Any]]:
    item_key = _resolve_item_key(job)
    override_params = build_source_library_override_params(
        {
            "override_params": dict(job.override_params or {}),
            "query_terms": list(job.query_terms or []),
            "urls": list(job.urls or []),
            "max_items": job.max_items,
            "provider": job.provider,
            "language": job.language,
            "scope": job.scope,
            "platforms": list(job.platforms or []),
            "source_mode": job.source_mode,
        },
        workflow_run_id=workflow_run_id,
    )
    task_id = _submit_source_item(
        item_key=item_key,
        project_key=project_key,
        override_params=override_params,
        trace_id=trace_id,
        lane=lane,
        workflow_run_id=workflow_run_id,
    )
    return task_id, {
        "item_key": item_key,
        "query_terms": _normalize_query_terms(job.query_terms),
        "max_items": job.max_items,
        "provider": job.provider,
        "language": job.language,
        "override_params": override_params,
    }


_CHANNEL_EXECUTION_REGISTRY = build_agent_batch_execution_registry(
    execution_bindings=list_agent_batch_execution_bindings(),
    globals_map=globals(),
)


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

    override_guard = _validate_override_params_for_channel(channel, job.override_params)
    if override_guard is not None:
        return override_guard

    channel_registry = dict(_CHANNEL_EXECUTION_REGISTRY.get(channel) or {})
    rule_guard = channel_registry.get("rule_guard")
    if rule_guard is not None:
        guard = rule_guard(job, rule_set)
        if guard is not None:
            return guard
    return None


def _submit_batch_item(
    job: AgentBatchItemSubmit,
    *,
    project_key: str | None,
    priority: int | None,
    trace_id: str | None,
    workflow_run_id: str,
) -> tuple[str, str, str, dict[str, Any]]:
    channel = _normalize_channel(job)
    lane = _resolve_lane(channel=channel, priority=priority)
    channel_registry = dict(_CHANNEL_EXECUTION_REGISTRY.get(channel) or {})
    submitter = channel_registry.get("submitter")
    if submitter is None:
        _raise_invalid_input(f"channel has no submit handler: {channel}")
    task_id, resolved_payload = submitter(
        job,
        project_key=project_key,
        lane=lane,
        trace_id=trace_id,
        workflow_run_id=workflow_run_id,
    )
    return task_id, channel, lane, resolved_payload


def _build_approval_binding(
    *,
    channel: str,
    project_key: str | None,
    workflow_run_id: str,
    trace_id: str,
    job: AgentBatchItemSubmit,
) -> dict[str, Any]:
    approval_payload: dict[str, Any] = {"query_terms": _normalize_query_terms(job.query_terms)}
    candidate_item_key = str(job.item_key or job.source_id or "").strip()
    if not candidate_item_key and isinstance(job.input, dict):
        candidate_item_key = str(job.input.get("item_key") or job.input.get("source_id") or "").strip()
    if candidate_item_key:
        approval_payload["item_key"] = candidate_item_key
    argv = build_agent_batch_approval_argv(channel, approval_payload)
    if not argv:
        _raise_invalid_input(f"channel has no approval binding handler: {channel}")
    return {
        "argv": argv,
        "cwd": str(project_key or "").strip() or "/workspace",
        "env": {"WORKFLOW_RUN_ID": workflow_run_id, "TRACE_ID": trace_id},
        "channel": channel,
        "project_key": project_key,
    }


def _enforce_approval_if_needed(
    *,
    channel: str,
    project_key: str | None,
    workflow_run_id: str,
    trace_id: str,
    job: AgentBatchItemSubmit,
    rule_set: dict[str, Any],
) -> dict[str, Any] | None:
    require_approval = bool(rule_set.get("require_approval")) or bool((job.override_params or {}).get("require_approval"))
    if not require_approval:
        return None
    binding = _build_approval_binding(
        channel=channel,
        project_key=project_key,
        workflow_run_id=workflow_run_id,
        trace_id=trace_id,
        job=job,
    )
    ok_approval, reason = verify_approval_token(
        approval_token=(job.override_params or {}).get("approval_token"),
        binding=binding,
    )
    if ok_approval:
        return None
    return {
        "reason_code": reason or REASON_APPROVAL_REQUIRED,
        "reason": "approval required or binding mismatch",
        "details": {"channel": channel},
    }


@router.post("/jobs")
def submit_agent_batch_job(payload: AgentBatchSubmitRequest) -> dict[str, Any]:
    cleanup_expired()
    project_key = _resolve_project_key(payload.project_key)
    idem = str(payload.idempotency_key or "").strip() or None
    if idem and idem in _IDEMPOTENCY_INDEX:
        existing_job_id = _IDEMPOTENCY_INDEX[idem]
        existing = _load_job(existing_job_id)
        run_ids = [run_id for run_id in (str(it.workflow_run_id or "").strip() for it in existing.items) if run_id]
        return ok(
            {
                "job_id": existing.job_id,
                "status": "accepted",
                "accepted_count": len(existing.items),
                "rejected_count": 0,
                "accepted_job_items": [
                    {
                        "item_id": it.item_id,
                        "task_id": it.task_id,
                        "lane": it.lane,
                        "workflow_run_id": it.workflow_run_id,
                        "trace_id": it.trace_id,
                    }
                    for it in existing.items
                ],
                "rejected_job_items": [],
                "run_ids": run_ids,
                "created_at": existing.created_at,
                "idempotency_reused": True,
                "session_id": (existing.metadata or {}).get("session_id"),
                "current_phase": (existing.metadata or {}).get("current_phase"),
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
            item_id = str(item.item_id or f"{job_id}-item-{idx+1}").strip()
            workflow_run_id = _build_item_workflow_run_id(job_id=job_id, item_id=item_id)
            trace_id = _build_item_trace_id(job_id=job_id, item_id=item_id)
            resolved_channel = _normalize_channel(item)
            approval_guard = _enforce_approval_if_needed(
                channel=resolved_channel,
                project_key=project_key,
                workflow_run_id=workflow_run_id,
                trace_id=trace_id,
                job=item,
                rule_set=rule_set,
            )
            if approval_guard is not None:
                rejected.append({"index": idx, **approval_guard})
                continue

            task_id, resolved_channel, lane, resolved_payload = _submit_batch_item(
                item,
                project_key=project_key,
                priority=payload.priority,
                trace_id=trace_id,
                workflow_run_id=workflow_run_id,
            )
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
                    override_params=dict(resolved_payload.get("override_params") or item.override_params or {}),
                    task_id=task_id,
                    lane=lane,
                    workflow_run_id=workflow_run_id,
                    trace_id=trace_id,
                )
            )
            accepted.append(
                {
                    "index": idx,
                    "item_id": item_id,
                    "task_id": task_id,
                    "lane": lane,
                    "channel": resolved_channel,
                    "item_key": resolved_payload.get("item_key"),
                    "query_terms": resolved_payload.get("query_terms"),
                    "contract_version": item.contract_version,
                    "run_id": workflow_run_id,
                    "workflow_run_id": workflow_run_id,
                    "trace_id": trace_id,
                }
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            error = detail.get("error") if isinstance(detail, dict) else {}
            rejected.append(
                {
                    "index": idx,
                    "reason_code": "dispatch_error",
                    "reason": str(error.get("message") or exc.detail or "dispatch error"),
                    "details": {
                        "error_code": error.get("code"),
                        **(dict(error.get("details") or {}) if isinstance(error, dict) else {}),
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001
            rejected.append({"index": idx, "reason_code": "dispatch_error", "reason": str(exc)})

    _BATCH_JOB_REGISTRY[job_id] = record
    if idem:
        _IDEMPOTENCY_INDEX[idem] = job_id
    projected_session = _project_agent_session_from_job_submission(
        record=record,
        request_payload=payload,
        accepted_items=accepted,
        rejected_items=rejected,
    )
    run_ids = [run_id for run_id in (str(it.workflow_run_id or "").strip() for it in record.items) if run_id]
    return ok(
        {
            "job_id": job_id,
            "status": "accepted",
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "accepted_job_items": accepted,
            "rejected_job_items": rejected,
            "run_ids": run_ids,
            "created_at": record.created_at,
            "links": {
                "self": f"/api/v1/agent-batch/jobs/{job_id}",
                "items": f"/api/v1/agent-batch/jobs/{job_id}/items",
                "events": f"/api/v1/agent-batch/jobs/{job_id}/events",
                "retry": f"/api/v1/agent-batch/jobs/{job_id}/retry",
            },
            "rule_set_id": payload.rule_set_id,
            "session_id": str((projected_session or {}).get("session_id") or "").strip() or None,
            "current_phase": (projected_session or {}).get("current_phase"),
        }
    )


@router.get("/jobs/{job_id}")
def get_agent_batch_job(job_id: str) -> dict[str, Any]:
    record = _load_job(job_id)
    snapshots = [_task_snapshot(item.task_id) for item in record.items]
    run_ids: list[str] = []
    for item, snapshot in zip(record.items, snapshots):
        run_id = _resolve_run_id(item, snapshot)
        if run_id and run_id not in run_ids:
            run_ids.append(run_id)
    total = len(snapshots)
    succeeded = sum(1 for it in snapshots if it.get("status") == "success")
    failed = sum(1 for it in snapshots if it.get("status") == "failure")
    running = sum(1 for it in snapshots if it.get("status") in {"pending", "started", "retry", "running"})
    phase = "completed" if total > 0 and (succeeded + failed) == total else "running"
    progress = {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "running": running,
        "queued": max(0, total - succeeded - failed - running),
    }
    projected_session = _project_agent_session_from_job_state(record=record, snapshots=snapshots, phase=phase, progress=progress)
    session_id = str((record.metadata or {}).get("session_id") or "").strip() or None
    current_phase = str((record.metadata or {}).get("current_phase") or "").strip() or None
    return ok(
        {
            "job_id": record.job_id,
            "status": phase,
            "phase": phase,
            "session_id": str((projected_session or {}).get("session_id") or session_id or "").strip() or None,
            "current_phase": (projected_session or {}).get("current_phase") or current_phase,
            "progress": progress,
            "started_at": record.created_at,
            "updated_at": _utcnow_iso(),
            "finished_at": _utcnow_iso() if phase == "completed" else None,
            "retry_count": 0,
            "error": None,
            "meta": {"project_key": record.project_key, **dict(record.metadata or {})},
            "run_ids": run_ids,
        }
    )


@router.get("/jobs/{job_id}/items")
def list_agent_batch_items(job_id: str) -> dict[str, Any]:
    record = _load_job(job_id)
    snapshots = [_task_snapshot(item.task_id) for item in record.items]
    phase = "completed" if snapshots and all(it.get("status") in {"success", "failure", "revoked"} for it in snapshots) else "running"
    progress = _job_progress_from_snapshots(snapshots)
    _project_agent_session_from_job_state(record=record, snapshots=snapshots, phase=phase, progress=progress)
    items = []
    for item, snap in zip(record.items, snapshots):
        run_id = _resolve_run_id(item, snap)
        items.append(
            {
                "item_id": item.item_id,
                "task_id": item.task_id,
                "lane": item.lane,
                "run_id": run_id,
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
                    "run_id": run_id,
                    "workflow_run_id": item.workflow_run_id,
                    "trace_id": item.trace_id,
                    "lane": item.lane,
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
        retry_index = len(replayed_task_ids) + 1
        retry_item_id = f"{item.item_id}-retry-{retry_index}"
        retry_run_id = _build_item_workflow_run_id(job_id=job_id, item_id=retry_item_id)
        retry_trace_id = _build_item_trace_id(job_id=job_id, item_id=retry_item_id)
        retry_job = AgentBatchItemSubmit(
            item_id=retry_item_id,
            item_key=item.item_key or None,
            channel=item.channel,
            query_terms=list(item.query_terms or []),
            max_items=item.max_items,
            provider=item.provider,
            language=item.language,
            days_back=item.days_back,
            override_params=dict(item.override_params or {}),
        )
        resolved_channel = _normalize_channel(retry_job)
        new_task_id, _, resolved_lane, resolved_payload = _submit_batch_item(
            retry_job,
            project_key=item.project_key,
            priority=None,
            trace_id=retry_trace_id,
            workflow_run_id=retry_run_id,
        )
        replayed_task_ids.append(new_task_id)
        record.items.append(
            _BatchItemRecord(
                item_id=retry_item_id,
                item_key=str(resolved_payload.get("item_key") or item.item_key or ""),
                channel=resolved_channel,
                query_terms=list(resolved_payload.get("query_terms") or item.query_terms or []),
                max_items=resolved_payload.get("max_items", item.max_items),
                provider=resolved_payload.get("provider", item.provider),
                language=resolved_payload.get("language", item.language),
                days_back=resolved_payload.get("days_back", item.days_back),
                project_key=item.project_key,
                override_params=dict(resolved_payload.get("override_params") or item.override_params or {}),
                task_id=new_task_id,
                lane=resolved_lane,
                workflow_run_id=retry_run_id,
                trace_id=retry_trace_id,
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
    snapshots = [_task_snapshot(item.task_id) for item in record.items]
    phase = "completed" if snapshots and all(it.get("status") in {"success", "failure", "revoked"} for it in snapshots) else "running"
    progress = _job_progress_from_snapshots(snapshots)
    _project_agent_session_from_job_state(record=record, snapshots=snapshots, phase=phase, progress=progress)
    events = []
    search_brief = dict((record.metadata or {}).get("search_brief") or {})
    search_critic = dict((record.metadata or {}).get("search_critic") or {})
    search_retry = dict((record.metadata or {}).get("search_retry") or {})
    submit_rounds = list((record.metadata or {}).get("submit_rounds") or [])
    search_brief_stage = dict(((record.metadata or {}).get("stage_artifacts") or {}).get("search_brief") or {})
    search_critic_stage = dict(((record.metadata or {}).get("stage_artifacts") or {}).get("search_critic") or {})
    search_retry_stage = dict(((record.metadata or {}).get("stage_artifacts") or {}).get("search_retry") or {})
    if search_brief:
        events.append(
            {
                "id": f"evt-{record.job_id}-search-brief",
                "event_type": "search_brief.created",
                "ts": _utcnow_iso(),
                "item_id": None,
                "lane": None,
                "run_id": None,
                "severity": "info",
                "message": "search brief created for nl-command job",
                "payload": {
                    "loop_id": (record.metadata or {}).get("loop_id"),
                    "search_brief": search_brief,
                    "stage": search_brief_stage,
                },
            }
        )
    if submit_rounds:
        for submit_round in submit_rounds:
            round_index = int(submit_round.get("round") or 0)
            events.append(
                {
                    "id": f"evt-{record.job_id}-search-round-{round_index}",
                    "event_type": "search_round.completed",
                    "ts": _utcnow_iso(),
                    "item_id": None,
                    "lane": None,
                    "run_id": None,
                    "severity": "info",
                    "message": f"search round {round_index} completed",
                    "payload": {
                        "loop_id": (record.metadata or {}).get("loop_id"),
                        "round": submit_round,
                    },
                }
            )
    if search_critic:
        events.append(
            {
                "id": f"evt-{record.job_id}-search-critic",
                "event_type": "search_critic.scored",
                "ts": _utcnow_iso(),
                "item_id": None,
                "lane": None,
                "run_id": None,
                "severity": "info",
                "message": "search critic scored the current plan",
                "payload": {
                    "loop_id": (record.metadata or {}).get("loop_id"),
                    "search_critic": search_critic,
                    "stage": search_critic_stage,
                },
            }
        )
    if search_retry:
        retry_event_type = "search_retry.scheduled" if bool(search_retry.get("scheduled")) else "search_retry.skipped"
        events.append(
            {
                "id": f"evt-{record.job_id}-search-retry",
                "event_type": retry_event_type,
                "ts": _utcnow_iso(),
                "item_id": None,
                "lane": None,
                "run_id": None,
                "severity": "info",
                "message": "bounded retry decision recorded",
                "payload": {
                    "loop_id": (record.metadata or {}).get("loop_id"),
                    "search_retry": search_retry,
                    "stage": search_retry_stage,
                },
            }
        )
    if search_critic and str(search_critic.get("next_action") or "").strip().lower() == "stop":
        events.append(
            {
                "id": f"evt-{record.job_id}-search-stop",
                "event_type": "search_stop.completed",
                "ts": _utcnow_iso(),
                "item_id": None,
                "lane": None,
                "run_id": None,
                "severity": "info",
                "message": "search loop stopped after critic evaluation",
                "payload": {
                    "loop_id": (record.metadata or {}).get("loop_id"),
                    "search_critic": search_critic,
                    "search_retry": search_retry,
                },
            }
        )
    for item, snap in zip(record.items, snapshots):
        run_id = _resolve_run_id(item, snap)
        events.append(
            {
                "id": f"evt-{item.task_id}",
                "event_type": f"task.{snap.get('status')}",
                "ts": _utcnow_iso(),
                "item_id": item.item_id,
                "lane": item.lane,
                "run_id": run_id,
                "severity": "error" if snap.get("failed") else "info",
                "message": f"task {item.task_id} status={snap.get('status')}",
                "payload": {
                    "task_id": item.task_id,
                    "lane": item.lane,
                    "status": snap.get("status"),
                    "run_id": run_id,
                    "workflow_run_id": item.workflow_run_id,
                    "trace_id": item.trace_id,
                },
            }
        )
    session_id = str((record.metadata or {}).get("session_id") or "").strip()
    if session_id:
        try:
            session_events = get_agent_session_service().list_events(session_id)
            for event in session_events:
                events.append(
                    {
                        "id": f"session-{session_id}-{event.get('seq')}",
                        "event_type": f"agent_session.{event.get('event_type')}",
                        "ts": event.get("ts"),
                        "item_id": None,
                        "lane": None,
                        "run_id": None,
                        "severity": "info",
                        "message": str(event.get("event_type") or "agent session event"),
                        "payload": dict(event.get("payload") or {}),
                    }
                )
        except Exception:
            pass
    return ok({"events": events, "pagination": {"next_cursor": None, "has_more": False}})


@router.get("/metrics/search-policy")
def get_agent_batch_search_policy_metrics() -> dict[str, Any]:
    return ok(_build_search_policy_metrics())


@router.get("/metrics/search-policy/benchmark-pack")
def get_agent_batch_search_policy_benchmark_pack() -> dict[str, Any]:
    return ok(build_search_policy_benchmark_pack())


@router.get("/metrics/search-policy/gate")
def get_agent_batch_search_policy_gate() -> dict[str, Any]:
    return ok(evaluate_search_policy_gate(_build_search_policy_metrics()))


@router.get("/jobs/{job_id}/workflow-handoffs")
def list_agent_batch_job_workflow_handoffs(job_id: str, handoff_mode: str | None = None) -> dict[str, Any]:
    record = _load_job(job_id)
    run_cache: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for item in record.items:
        snap = _task_snapshot(item.task_id)
        run_id = _resolve_run_id(item, snap)
        if not run_id:
            skipped.append(
                {
                    "item_id": item.item_id,
                    "task_id": item.task_id,
                    "reason_code": "run_id_missing",
                    "reason": "item has no resolvable run_id",
                }
            )
            continue

        if run_id not in run_cache:
            try:
                run_cache[run_id] = handoff_store.list_handoffs(run_id=run_id, handoff_mode=handoff_mode)
            except (KeyError, ValueError):
                run_cache[run_id] = {"items": [], "total": 0, "query_error": "run_or_handoff_unavailable"}

        handoff_items = list(run_cache[run_id].get("items") or [])
        replay_map = {
            str(entry.get("handoff_id") or ""): {
                "workflow_graph": f"/api/v1/workflow-graph/runs/{run_id}/handoff/{entry.get('handoff_id')}/replay"
            }
            for entry in handoff_items
            if str(entry.get("handoff_id") or "").strip()
        }
        items.append(
            {
                "item_id": item.item_id,
                "task_id": item.task_id,
                "task_status": snap.get("status"),
                "run_id": run_id,
                "handoffs_total": len(handoff_items),
                "handoffs": handoff_items,
                "replay_entry_map": replay_map,
            }
        )

    return ok(
        {
            "job_id": record.job_id,
            "items": items,
            "runs_total": len(run_cache),
            "handoffs_total": sum(len(x.get("items") or []) for x in run_cache.values()),
            "skipped_items": skipped,
            "skipped_count": len(skipped),
            "contract_version": "agent_batch.workflow_handoff.query.v1",
        }
    )


@router.get("/observability/failure-reasons")
def get_agent_batch_failure_reasons(limit: int = 20) -> dict[str, Any]:
    return ok(_build_failure_reason_metrics(limit=limit))


@router.post("/approvals/request")
def create_agent_batch_approval(payload: AgentBatchApprovalRequest) -> dict[str, Any]:
    binding = {
        "argv": list(payload.argv or []),
        "cwd": payload.cwd,
        "env": dict(payload.env or {}),
        "channel": payload.channel,
        "project_key": payload.project_key,
    }
    approval = request_approval(
        binding=binding,
        ttl_seconds=int(getattr(settings, "agent_batch_approval_ttl_seconds", 900) or 900),
    )
    try:
        get_agent_session_service().create_or_update_approval(
            approval_id=str(approval.get("approval_token") or ""),
            binding_payload=binding,
            requester_session_id=str(payload.requester_session_id or "").strip() or None,
            requester_task_id=str(payload.requester_task_id or "").strip() or None,
            requester_actor=payload.requester_actor,
            expires_at=datetime.fromtimestamp(int(approval.get("expires_at") or 0), tz=timezone.utc)
            if approval.get("expires_at")
            else None,
            status="pending",
            metadata={"channel": payload.channel, "project_key": payload.project_key},
            audit_log=[
                {
                    "at": _utcnow_iso(),
                    "action": "requested",
                    "actor": payload.requester_actor,
                }
            ],
        )
    except Exception:
        pass
    return ok({"status": "pending", **approval})


@router.post("/approvals/{approval_token}/resolve")
def resolve_agent_batch_approval(approval_token: str, payload: AgentBatchApprovalResolveRequest) -> dict[str, Any]:
    if not payload.approved:
        _raise_invalid_input("only approved=true is supported")
    try:
        out = approve_approval(approval_token=approval_token)
    except KeyError:
        _raise_not_found("approval token not found")
    except ValueError as exc:
        _raise_invalid_input(str(exc))
    try:
        get_agent_session_service().resolve_approval(
            approval_token,
            approved=True,
            approved_by="agent_batch.compat",
        )
    except Exception:
        pass
    return ok(out)


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
        _raise_invalid_input("command is required")
    project_key = _resolve_project_key(payload.project_key)
    try:
        loop_result = run_agent_batch_nl_command_loop(
            command=command,
            project_key=project_key,
            idempotency_key=payload.idempotency_key,
            dry_run=bool(payload.dry_run),
            enable_bounded_retry=bool(payload.enable_bounded_retry),
            enable_limited_branching=bool(payload.enable_limited_branching),
            parser_fallback=plan_batch_search_command,
            submitter=_submit_jobs_from_loop_tasks,
            executor_snapshot=inspect_executor_health,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_invalid_input(f"failed to execute command loop: {exc}")
    submit = loop_result.get("submit") if isinstance(loop_result, dict) else None
    job_id = str((submit or {}).get("job_id") or "").strip() if isinstance(submit, dict) else ""
    if job_id:
        _attach_loop_metadata(job_id, loop_result)
    if bool(payload.wait_for_completion) and not bool(payload.dry_run):
        if job_id:
            loop_result["completion"] = _await_job_completion(
                job_id=job_id,
                timeout_seconds=int(payload.completion_timeout_seconds),
                poll_seconds=float(payload.completion_poll_seconds),
            )
    projected = _project_agent_session_from_loop(
        command=command,
        request_payload=payload,
        loop_result=loop_result,
    )
    if isinstance(projected, dict) and projected:
        loop_result["session_id"] = projected.get("session_id")
        loop_result["root_task_id"] = projected.get("root_task_id")
        loop_result["current_phase"] = projected.get("current_phase")
        loop_result["compat_mode"] = True
        loop_result["compat_projection_version"] = "claude-agent.v1"
    return ok(loop_result)


@router.post("/nl-command/direct")
def run_agent_batch_nl_command_direct(payload: AgentBatchNlCommandRequest) -> dict[str, Any]:
    direct_payload = payload.model_copy(update={"wait_for_completion": True})
    return run_agent_batch_nl_command(direct_payload)


@router.get("/executor/health")
def get_agent_batch_executor_health() -> dict[str, Any]:
    return ok(inspect_executor_health())
