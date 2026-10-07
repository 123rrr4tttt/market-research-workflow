from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Annotated, Any, NoReturn, TypeGuard
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..contracts import ErrorCode, error_response
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
from ..services.agent_batch.routing import apply_async_or_delay, resolve_queue_for_lane, validate_lane
from ..services.agent_batch.task_contract import (
    build_agent_batch_approval_argv,
    get_allowed_override_params_by_channel,
    get_agent_batch_known_channels,
    infer_agent_batch_channel,
    resolve_agent_batch_lane,
)
from ..services.agent_sessions import get_agent_session_service
from ..services.task_readback_metadata import build_runtime_readback_payload
from ..services import tasks as tasks_module
from ..services.projects import current_project_key
from ..services.workflow_graph.handoff_store import handoff_store
from app.successor_runtime.capabilities import batch_task
from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver
from app.services.agent_batch.dispatch import (
    load_dispatch_run as dispatch_load_run,
    submit_dispatch_run as dispatch_submit_run,
)
from app.successor_runtime.substrate.postgres.authority_provider import (
    CurrentAuthorityGrantUnavailable,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
)
from app.models.base import engine
from app.services.request_identity import RequestActorContext, require_trusted_actor_context

router = APIRouter(prefix="/agent-batch", tags=["agent_batch"])
logger = logging.getLogger(__name__)

_DEFAULT_CONTRACT_VERSION = "collect.request.v2"
_ALLOWED_CHANNELS = get_agent_batch_known_channels()
_ALLOWED_OVERRIDE_PARAMS_BY_CHANNEL = get_allowed_override_params_by_channel()
_READBACK_LINE_KEYS_BY_CHANNEL = {
    "search.market": "search_discovery_index",
    "source_library": "resource_source_library",
}


def _raise_invalid_input(message: str) -> NoReturn:
    raise HTTPException(
        status_code=400,
        detail=error_response(
            ErrorCode.INVALID_INPUT,
            message,
        ),
    )


def _raise_not_found(message: str) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail=error_response(
            ErrorCode.NOT_FOUND,
            message,
        ),
    )


def _raise_agent_runtime_retired() -> NoReturn:
    detail = error_response(
        ErrorCode.INVALID_INPUT,
        "agent batch natural-language command execution is retired; submit structured jobs",
        details={"runtime_variant": "legacy_nl_command"},
    )
    detail["error"]["code"] = "agent_runtime_retired"
    raise HTTPException(
        status_code=410,
        detail=detail,
    )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _object_list(value: object) -> list[object]:
    return list(value) if _is_object_list(value) else []


def _normalized_string_set(value: object) -> set[str]:
    normalized: set[str] = set()
    for entry in _object_list(value):
        text = str(entry or "").strip().lower()
        if text:
            normalized.add(text)
    return normalized


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


class RuleSetValidateRequest(BaseModel):
    rule_set_id: str | None = Field(default=None, max_length=128)
    rule_set: dict[str, Any] = Field(default_factory=dict)
    batch_schema_version: str | None = Field(default=None, max_length=64)
    sample_items: list[dict[str, Any]] = Field(default_factory=list)


class AgentBatchNlCommandRequest(BaseModel):
    """Minimal request body retained only to return a stable retirement response."""

    command: str | None = None


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


def _resolve_project_key(project_key: str | None) -> str:
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
    cleaned: list[str] = []
    for term in raw:
        value = str(term or "").strip()
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def _detect_language(command: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", command or "") else "en"



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


def _apply_async_or_delay(
    task_func: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    lane: str,
    task_id: str | None = None,
) -> Any:
    return apply_async_or_delay(task_func, args, kwargs, lane, task_id=task_id)


def _build_dispatch_runtime_readback(
    *,
    channel: str,
    trace_id: str | None,
    workflow_run_id: str | None,
    queue: str | None,
) -> dict[str, Any]:
    line_key = _READBACK_LINE_KEYS_BY_CHANNEL.get(str(channel or "").strip().lower())
    if not line_key:
        return {}
    return build_runtime_readback_payload(
        line_key=line_key,
        trace_id=trace_id,
        run_id=workflow_run_id,
        queue=queue,
        status="queued",
        event="agent_batch_dispatched",
        event_source="agent_batch_api",
    )









def _skill_dispatch_source_library_item(payload: dict[str, Any]) -> dict[str, Any]:
    item_key = str((payload or {}).get("item_key") or "").strip()
    if not item_key:
        raise ValueError("item_key is required")
    project_key = str((payload or {}).get("project_key") or "").strip() or None
    override_params = dict((payload or {}).get("override_params") or {})
    trace_id = str((payload or {}).get("trace_id") or "").strip() or None
    dispatch_task_id = str((payload or {}).get("task_id") or "").strip() or None
    lane = validate_lane((payload or {}).get("lane"), fallback="main")
    workflow_run_id = str((payload or {}).get("workflow_run_id") or "").strip() or None
    queue_name = _resolve_queue_for_lane(lane)
    runtime_readback = dict((payload or {}).get("runtime_readback") or {})
    if not runtime_readback:
        runtime_readback = _build_dispatch_runtime_readback(
            channel="source_library",
            trace_id=trace_id,
            workflow_run_id=workflow_run_id,
            queue=queue_name,
        )
    override_params.setdefault("workflow_run_id", workflow_run_id)
    override_params.setdefault("trace_id", trace_id)
    override_params.setdefault("line_key", runtime_readback.get("line_key") or "resource_source_library")
    override_params.setdefault("queue", queue_name)
    override_params.setdefault("runtime_readback", runtime_readback)
    task = _apply_async_or_delay(
        tasks_module.task_run_source_library_item,
        (item_key, project_key, override_params),
        {
            "workflow_run_id": workflow_run_id,
            "trace_id": trace_id,
            "line_key": runtime_readback.get("line_key") or "resource_source_library",
            "queue": queue_name,
            "runtime_readback": runtime_readback,
        },
        lane,
        task_id=dispatch_task_id,
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
    dispatch_task_id = str((payload or {}).get("task_id") or "").strip() or None
    lane = validate_lane((payload or {}).get("lane"), fallback="main")
    workflow_run_id = str((payload or {}).get("workflow_run_id") or "").strip() or None
    queue_name = _resolve_queue_for_lane(lane)
    runtime_readback = dict((payload or {}).get("runtime_readback") or {})
    if not runtime_readback:
        runtime_readback = _build_dispatch_runtime_readback(
            channel="search.market",
            trace_id=trace_id,
            workflow_run_id=workflow_run_id,
            queue=queue_name,
        )
    task = _apply_async_or_delay(
        tasks_module.task_ingest_market,
        (query_terms, max_items, enable_extraction, project_key, start_offset, days_back, language, provider),
        {
            "workflow_run_id": workflow_run_id,
            "trace_id": trace_id,
            "line_key": runtime_readback.get("line_key") or "search_discovery_index",
            "queue": queue_name,
            "runtime_readback": runtime_readback,
        },
        lane,
        task_id=dispatch_task_id,
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


def build_dispatch_single_payload_from_item(
    *,
    item: AgentBatchItemSubmit,
    dispatch_id: str,
    project_key: str,
    resolved_schema: str,
    registry_revision: int,
    scope_incarnation: str,
    scope_digest: str,
    capability_id: str,
    lane: str,
    queue: str | None,
    trace_id: str | None,
    workflow_run_id: str | None,
    runtime_readback: dict[str, Any] | None = None,
) -> Annotated[
    batch_task.BatchTaskSingleDispatchPayload,
    "kit:non-authoritative derived_as=payload fact_source=resolved_project_scope_and_batch_submission_item witness=test:test_body_lowering_preserves_channel_scope_and_routing",
]:
    """Pure typed body -> single-dispatch payload lowering.

    The resolved project scope, capability identity and routing context are
    supplied by the caller (server-side scope resolution and admission); this
    function performs no network, database, provider or credential work.
    """

    channel = _normalize_channel(item)
    submission_item = batch_task.AgentBatchSubmissionItem(
        job_id=str(item.item_id or dispatch_id),
        channel=channel,
        query_terms=tuple(item.query_terms or []),
        urls=tuple(item.urls or []),
        max_items=int(item.max_items or 20),
        provider=str(item.provider or "auto"),
        language=str(item.language or "zh"),
        days_back=item.days_back,
        item_key=_resolve_item_key(item) if channel == "source_library" else item.item_key,
        scope=item.scope,
        platforms=tuple(item.platforms or []),
        override_params=dict(item.override_params or {}),
        lane=lane,
        workflow_run_id=workflow_run_id,
        trace_id=trace_id,
    )
    return batch_task.BatchTaskSingleDispatchPayload(
        schema_version=batch_task.DISPATCH_SINGLE_PAYLOAD_SCHEMA,
        operation_kind=batch_task.DISPATCH_SINGLE_KIND,
        dispatch_id=dispatch_id,
        project_key=project_key,
        resolved_schema=resolved_schema,
        registry_revision=registry_revision,
        scope_incarnation=scope_incarnation,
        scope_digest=scope_digest,
        capability_id=capability_id,
        item=submission_item,
        lane=lane,
        queue=queue,
        trace_id=trace_id,
        workflow_run_id=workflow_run_id,
        runtime_readback=dict(runtime_readback or {}),
    )


def _submit_dispatch_run(
    *,
    run_id: str,
    payloads: tuple[batch_task.BatchTaskSingleDispatchPayload, ...],
    project_key: str,
    actor_id: str,
    queue: str,
    idempotency_key: str | None,
    now: datetime,
) -> tuple[str, tuple[str, ...]]:
    return dispatch_submit_run(
        run_id=run_id,
        payloads=payloads,
        project_key=project_key,
        actor_id=actor_id,
        queue=queue,
        idempotency_key=idempotency_key,
        now=now,
    )


def _load_dispatch_run(
    *,
    run_id: str,
    project_key: str,
    actor_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], tuple[dict[str, Any], ...]]:
    return dispatch_load_run(
        run_id=run_id,
        project_key=project_key,
        actor_id=actor_id,
    )


def _run_product_status(run: dict[str, Any], items: list[dict[str, Any]]) -> str:
    state = str(run.get("state") or "")
    if state in {"SUBMITTED", "COMPILING"}:
        return "queued"
    if state in {"FAILED", "CANCELLED", "SUPERSEDED"}:
        return state.lower()
    if state == "COMPLETED":
        return "completed" if run.get("business_program") and all(item["status"] == "succeeded" for item in items) else "submitted"
    if any(item["status"] == "unknown" for item in items):
        return "unknown"
    if state == "WAITING" or any(item["status"] == "waiting" for item in items):
        return "waiting"
    return "running"


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

    allowlist = _normalized_string_set(rule_set.get("provider_allowlist"))
    provider = str(job.provider or "auto").strip().lower()
    if allowlist and provider not in allowlist:
        return {
            "reason_code": "provider_blocked_by_rule_set",
            "message": f"provider blocked by rule_set: {provider}",
            "details": {"provider": provider, "allowlist": sorted(allowlist)},
        }
    return None


_CHANNEL_EXECUTION_REGISTRY = {
    "search.market": {"rule_guard": _enforce_search_market_rule_set},
}


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

    blocked_channels = _normalized_string_set(rule_set.get("blocked_channels"))
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
def submit_agent_batch_job(
    payload: AgentBatchSubmitRequest, request: Request
) -> dict[str, Any]:
    return submit_agent_batch_for_actor(payload, require_trusted_actor_context(request))


def submit_agent_batch_for_actor(
    payload: AgentBatchSubmitRequest, actor: RequestActorContext
) -> dict[str, Any]:
    """Submit using the trusted actor proof from HTTP or verified host context."""
    if not actor.actor_trusted or not actor.actor_id or actor.actor_source in {
        "authenticated_oauth_token_sink", "authenticated_oauth_token_sink_claims",
    }:
        raise HTTPException(status_code=401, detail="trusted actor required")
    cleanup_expired()
    project_key = _resolve_project_key(payload.project_key)
    jobs = payload.batch.jobs
    rule_set = dict(payload.rule_set or {})
    with engine.connect() as connection:
        project_scope = ServerProjectScopeResolver(connection=connection).resolve(
            project_key
        )
    logical_request_id = str(payload.idempotency_key or "").strip() or None
    if logical_request_id:
        job_id = batch_task.derive_dispatch_run_id(
            project_scope_digest=project_scope.scope_digest,
            actor_id=actor.actor_id,
            logical_request_id=logical_request_id,
        )
    else:
        job_id = f"batch-dispatch-{uuid4().hex[:16]}"

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    dispatch_payloads: list[batch_task.BatchTaskSingleDispatchPayload] = []
    worker_queue: str | None = None
    for idx, item in enumerate(jobs):
        guard = _guard_batch_item(item, project_key=project_key, rule_set=rule_set)
        if guard is not None:
            rejected.append({"index": idx, **guard})
            continue
        item_id = str(item.item_id or f"{job_id}-item-{idx + 1}").strip()
        dispatch_id = f"{job_id}:{item_id}"
        resolved_channel = _normalize_channel(item)
        lane = _resolve_lane(channel=resolved_channel, priority=payload.priority)
        queue = _resolve_queue_for_lane(lane)
        worker_queue = worker_queue or queue
        workflow_run_id = _build_item_workflow_run_id(job_id=job_id, item_id=item_id)
        trace_id = _build_item_trace_id(job_id=job_id, item_id=item_id)
        runtime_readback = _build_dispatch_runtime_readback(
            channel=resolved_channel,
            trace_id=trace_id,
            workflow_run_id=workflow_run_id,
            queue=queue,
        )
        # Request-time event timestamps are observations, not dispatch input.
        # Runtime and business execution own the persisted event history.
        runtime_readback.pop("events", None)
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
        dispatch_payloads.append(
            build_dispatch_single_payload_from_item(
                item=item,
                dispatch_id=dispatch_id,
                project_key=project_key,
                resolved_schema=project_scope.resolved_schema,
                registry_revision=project_scope.project_registry_revision,
                scope_incarnation=project_scope.incarnation,
                scope_digest=project_scope.scope_digest,
                capability_id=batch_task.BATCH_TASK_OWNER,
                lane=lane,
                queue=queue,
                trace_id=trace_id,
                workflow_run_id=workflow_run_id,
                runtime_readback=runtime_readback,
            )
        )
        accepted.append(
            {
                "index": idx,
                "item_id": item_id,
                "dispatch_id": dispatch_id,
                "channel": resolved_channel,
                "lane": lane,
                "trace_id": trace_id,
            }
        )

    if not dispatch_payloads:
        return ok(
            {
                "job_id": None,
                "status": "rejected",
                "accepted_count": 0,
                "rejected_count": len(rejected),
                "accepted_job_items": [],
                "rejected_job_items": rejected,
            }
        )

    try:
        run_id, work_item_ids = _submit_dispatch_run(
            run_id=job_id,
            payloads=tuple(dispatch_payloads),
            project_key=project_key,
            actor_id=actor.actor_id,
            queue=worker_queue or _resolve_queue_for_lane("main"),
            idempotency_key=logical_request_id,
            now=datetime.now(timezone.utc),
        )
    except CurrentAuthorityGrantUnavailable as exc:
        raise HTTPException(
            status_code=403,
            detail=error_response(
                ErrorCode.INVALID_INPUT,
                "actor has no current dispatch grant",
            ),
        ) from exc
    except ExactBindingConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=error_response(
                ErrorCode.INVALID_INPUT,
                "idempotency request conflicts with an existing dispatch",
            ),
        ) from exc
    return ok(
        {
            "job_id": run_id,
            "status": "accepted",
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "accepted_job_items": accepted,
            "rejected_job_items": rejected,
            "run_ids": [run_id],
            "work_item_ids": work_item_ids,
            "created_at": _utcnow_iso(),
            "rule_set_id": payload.rule_set_id,
        }
    )


@router.get("/jobs/{job_id}")
def get_agent_batch_job(
    job_id: str, request: Request, project_key: str | None = None
) -> dict[str, Any]:
    actor = require_trusted_actor_context(request)
    resolved_project_key = _resolve_project_key(project_key)
    run, items, events = _load_dispatch_run(
        run_id=job_id,
        project_key=resolved_project_key,
        actor_id=actor.actor_id,
    )
    return ok(
        {
            "job_id": job_id,
            "status": _run_product_status(run, items),
            "phase": run.get("state"),
            "progress": {
                "total": len(items),
                **{state: sum(item["status"] == state for item in items)
                   for state in ("succeeded", "failed", "cancelled", "superseded", "running", "queued", "waiting", "unknown", "submitted")},
            },
            "retry_count": 0,
            "error": None,
            "events": events,
            "business_terminal": bool(items) and all(item["business_terminal"] for item in items),
            "meta": {"project_key": resolved_project_key},
        }
    )


@router.get("/jobs/{job_id}/items")
def list_agent_batch_items(
    job_id: str, request: Request, project_key: str | None = None
) -> dict[str, Any]:
    actor = require_trusted_actor_context(request)
    resolved_project_key = _resolve_project_key(project_key)
    _, items, _ = _load_dispatch_run(
        run_id=job_id, project_key=resolved_project_key, actor_id=actor.actor_id
    )
    return ok({"items": items, "pagination": {"next_cursor": None, "has_more": False}})



@router.get("/jobs/{job_id}/events")
def get_agent_batch_events(
    job_id: str, request: Request, project_key: str | None = None
) -> dict[str, Any]:
    actor = require_trusted_actor_context(request)
    resolved_project_key = _resolve_project_key(project_key)
    _, _, events = _load_dispatch_run(
        run_id=job_id, project_key=resolved_project_key, actor_id=actor.actor_id
    )
    return ok({"events": events, "pagination": {"next_cursor": None, "has_more": False}})


@router.get("/jobs/{job_id}/workflow-handoffs")
def list_agent_batch_job_workflow_handoffs(job_id: str, handoff_mode: str | None = None) -> dict[str, Any]:
    handoffs: dict[str, Any]
    try:
        handoffs = handoff_store.list_handoffs(run_id=job_id, handoff_mode=handoff_mode)
    except (KeyError, ValueError):
        handoffs = {"items": [], "total": 0, "query_error": "run_or_handoff_unavailable"}
    handoff_items: list[dict[str, object]] = [
        dict(entry)
        for entry in _object_list(handoffs.get("items"))
        if _is_object_dict(entry)
    ]
    replay_map = {
        str(entry.get("handoff_id") or ""): {
            "workflow_graph": (
                f"/api/v1/workflow-graph/runs/{job_id}/handoff/{entry.get('handoff_id')}/replay?source=historical"
            )
        }
        for entry in handoff_items
        if str(entry.get("handoff_id") or "").strip()
    }

    return ok(
        {
            "job_id": job_id,
            "items": [
                {
                    "item_id": job_id,
                    "run_id": job_id,
                    "handoffs_total": len(handoff_items),
                    "handoffs": handoff_items,
                    "replay_entry_map": replay_map,
                }
            ],
            "runs_total": 1,
            "handoffs_total": len(handoff_items),
            "skipped_items": [],
            "skipped_count": 0,
            "contract_version": "agent_batch.workflow_handoff.query.v1",
        }
    )

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
    _raise_agent_runtime_retired()
    raise AssertionError("unreachable retired agent runtime")


@router.post("/nl-command/direct")
def run_agent_batch_nl_command_direct(payload: AgentBatchNlCommandRequest) -> dict[str, Any]:
    _raise_agent_runtime_retired()
    raise AssertionError("unreachable retired agent runtime")


@router.get("/executor/health")
def get_agent_batch_executor_health() -> dict[str, Any]:
    return ok(inspect_executor_health())

# Native dispatch names are resolved by the authoritative task-contract manifest.
__all__ = ["_skill_dispatch_source_library_item", "_skill_dispatch_market_collect"]
