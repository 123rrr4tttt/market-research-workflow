from __future__ import annotations

import json
from queue import Empty, Queue
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..contracts import ErrorCode, error_response
from ..contracts.errors import map_exception_to_error
from ..contracts.responses import ok
from ..models.base import SessionLocal
from ..models.entities import Project
from ..services.agent_core import (
    AgentCore,
    AgentCoreRequest,
    CoreApprovalResume,
    CoreModelStep,
    CoreToolCall,
    FakeCoreProvider,
    JsonCoreProvider,
    NativeToolCallingCoreProvider,
    build_project_core_tool_registry,
    select_core_tool_window,
)
from ..services.agent_runtime.material_ontology import classify_material_intent
from ..services.agent_runtime.interactive_agent import InteractiveAgentRuntime
from ..services.agent_runtime.session_memory import build_session_context_summary
from ..services.agent_runtime.tool_contract import build_stream_descriptor
from ..services.agent_runtime.tool_pool import AgentToolPoolAssembler, ToolPoolRequest
from ..services.agent_runtime.turn_decision import GuardedModelTurnDecisionPlanner
from ..services.agent_sessions.service import get_agent_session_service
from ..services.projects import bind_schema
from ..services.source_library import list_effective_items
from ..settings.config import settings
from .agent_batch import (
    _resolve_project_key,
    _submit_jobs_from_loop_tasks,
    inspect_executor_health,
    plan_batch_search_command,
    run_agent_batch_nl_command_loop,
)

router = APIRouter(prefix="/agent-chat", tags=["agent_chat"])


class AgentChatTurnRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    project_key: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=128)
    dry_run: bool = Field(default=False)
    enable_bounded_retry: bool = Field(default=True)
    enable_limited_branching: bool = Field(default=True)
    enable_model_tool_loop: bool = Field(default=False)
    require_high_risk_approval: bool = Field(default=False)
    runtime_variant: str | None = Field(default=None, max_length=32)


class AgentChatApprovalContinueRequest(BaseModel):
    approved_by: str = Field(default="user", min_length=1, max_length=128)
    binding_payload_overrides: dict[str, Any] = Field(default_factory=dict)


_RESERVED_AGENT_PROJECT_KEYS = {"", "default", "public"}
_SOURCE_LIBRARY_AGENT_CACHE_TTL_SECONDS = 5.0
_source_library_agent_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_source_library_agent_cache_lock = threading.Lock()


def _lookup_active_agent_project_key() -> str | None:
    """Resolve the user-facing chat project to the active tenant when the UI sends a reserved default key."""

    try:
        with bind_schema("public"):
            with SessionLocal() as session:
                row = (
                    session.execute(
                        select(Project)
                        .where(Project.enabled.is_(True), Project.is_active.is_(True))
                        .order_by(Project.id.asc())
                    )
                    .scalars()
                    .first()
                )
                if row and str(row.project_key or "").strip():
                    return str(row.project_key).strip()
                row = (
                    session.execute(
                        select(Project)
                        .where(Project.enabled.is_(True))
                        .order_by(Project.id.asc())
                    )
                    .scalars()
                    .first()
                )
                if row and str(row.project_key or "").strip():
                    return str(row.project_key).strip()
    except SQLAlchemyError:
        return None
    return None


def _resolve_agent_chat_project_key(project_key: str | None) -> str | None:
    raw = str(project_key or "").strip()
    if raw.lower() not in _RESERVED_AGENT_PROJECT_KEYS:
        return _resolve_project_key(raw)
    active = _lookup_active_agent_project_key()
    if active:
        return active
    return _resolve_project_key(None)


def _agent_chat_requires_explicit_project_key(payload: AgentChatTurnRequest) -> bool:
    raw = str(payload.project_key or "").strip().lower()
    return not payload.session_id and raw in _RESERVED_AGENT_PROJECT_KEYS


def _raise_invalid_input(message: str) -> None:
    raise HTTPException(
        status_code=400,
        detail=error_response(
            ErrorCode.INVALID_INPUT,
            message,
        ),
    )


def _raise_mapped_error(exc: Exception) -> None:
    if isinstance(exc, ValueError):
        _raise_invalid_input(str(exc) or "invalid agent chat request")
    code, message, details = map_exception_to_error(exc)
    status_code = 404 if code == ErrorCode.NOT_FOUND else 429 if code == ErrorCode.RATE_LIMITED else 502 if code in {ErrorCode.UPSTREAM_ERROR, ErrorCode.PARSE_ERROR} else 500
    raise HTTPException(
        status_code=status_code,
        detail=error_response(code, message, details=details),
    ) from exc


def _list_source_library_items_for_agent(project_key: str | None) -> list[dict[str, Any]]:
    key = str(project_key or "").strip() or "-"
    now = time.monotonic()
    with _source_library_agent_cache_lock:
        cached = _source_library_agent_cache.get(key)
        if cached and now - cached[0] <= _SOURCE_LIBRARY_AGENT_CACHE_TTL_SECONDS:
            return [dict(item) for item in cached[1]]
    items = list_effective_items(scope="effective", project_key=project_key, include_execution_plan=False)
    with _source_library_agent_cache_lock:
        _source_library_agent_cache[key] = (now, [dict(item) for item in items])
        if len(_source_library_agent_cache) > 32:
            oldest_key = min(_source_library_agent_cache.items(), key=lambda item: item[1][0])[0]
            _source_library_agent_cache.pop(oldest_key, None)
    return items


def _build_agent_core_provider() -> Any:
    if bool(getattr(settings, "agent_core_e2e_scripted_provider_enabled", False)):
        return _build_e2e_scripted_agent_core_provider()
    return NativeToolCallingCoreProvider(fallback_provider=JsonCoreProvider())


def _build_e2e_scripted_agent_core_provider() -> Any:
    """Deterministic provider used only when an explicit E2E env flag is enabled."""

    class E2EScriptedCoreProvider:
        def __init__(self) -> None:
            self.steps: list[CoreModelStep] | None = None
            self.calls: list[dict[str, Any]] = []

        def next_step(self, *, request: AgentCoreRequest, tools: list[Any], transcript: list[dict[str, Any]], remaining_budget: dict[str, Any]) -> CoreModelStep:
            self.calls.append(
                {
                    "message": request.message,
                    "tool_names": [getattr(tool, "name", "") for tool in tools],
                    "remaining_budget": dict(remaining_budget or {}),
                }
            )
            if self.steps is None:
                self.steps = _e2e_scripted_steps_for_message(request.message)
            if self.steps:
                return self.steps.pop(0)
            return CoreModelStep.final("E2E scripted provider completed.")

    return E2EScriptedCoreProvider()


def _e2e_scripted_steps_for_message(message: str) -> list[CoreModelStep]:
    text = str(message or "")
    material_intent = classify_material_intent(text)
    asks_material_supplement = material_intent.material_state == "to_collect" or (
        material_intent.work_context == "writing"
        and material_intent.category in {"internal_existing", "internal_generated"}
        and any(token in text for token in ("资料", "材料", "数据", "证据", "素材"))
        and any(token in text for token in ("补", "搜索", "搜集", "收集", "查找", "找"))
    )
    if "CAPM" in text or "核心假设" in text:
        return [CoreModelStep.final("CAPM 的核心假设包括均值方差偏好、同质预期、无摩擦市场、可自由借贷和所有投资者持有市场组合。")]
    if "写作工作台上下文 JSON" in text and "用户请求：改写当前选区" in text:
        context = _extract_e2e_writing_workbench_context(text)
        doc_id = _safe_positive_int(context.get("doc_id"))
        range_start = _safe_nonnegative_int(context.get("selection_start"))
        range_end = _safe_nonnegative_int(context.get("selection_end"))
        selection_text = str(context.get("selected_text") or "").strip()
        version = _safe_positive_int(context.get("version"))
        etag = str(context.get("etag") or "").strip()
        if doc_id and range_start is not None and range_end is not None:
            selection_snapshot = {
                "selected_text": selection_text,
                "start": range_start,
                "end": range_end,
                "line": _safe_positive_int(context.get("selection_line")),
                "active_heading": str(context.get("active_heading") or "").strip(),
                "before": str(context.get("before_selection") or "")[:900],
                "after": str(context.get("after_selection") or "")[:900],
            }
            return [
                CoreModelStep.tools(CoreToolCall(tool_name="writing.document.read", call_id="call-e2e-workbench-read", arguments={"doc_id": doc_id})),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="writing.document.insert_paragraph",
                        call_id="call-e2e-workbench-rewrite",
                        arguments={
                            "doc_id": doc_id,
                            "operation": "replace_range",
                            "range_start": range_start,
                            "range_end": range_end,
                            "selection_snapshot": selection_snapshot,
                            "content_md": "Agent 改写后的选区段落。",
                            "base_version": version,
                            "if_match": etag,
                            "source_refs": ["project-context:e2e-writing-selection"],
                            "provenance": {"scenario": "writing_workbench_selection_e2e", "selection_snapshot": selection_snapshot},
                        },
                    )
                ),
                CoreModelStep.final("已读取当前写作工作台文档，并用 replace_range 按选区范围写回改写段落。"),
            ]
    if "source_candidate_review JSON" in text:
        review_context = _extract_e2e_source_candidate_review_context(text)
        decision = str(review_context.get("decision") or "approved").strip() or "approved"
        candidate = review_context.get("candidate") if isinstance(review_context.get("candidate"), dict) else {}
        if not candidate:
            candidate = {
                "title": "E2E Robotics Policy Candidate",
                "url": "https://example.gov/robotics-policy",
                "snippet": "Deterministic external search candidate for AgentCore browser E2E.",
                "provider": "e2e_scripted_search",
            }
        return [
            CoreModelStep.tools(
                CoreToolCall(
                    tool_name="source.candidate.review",
                    call_id="call-e2e-source-candidate-review",
                    arguments={
                        "decision": decision,
                        "candidate": candidate,
                        "preferred_ingest": review_context.get("preferred_ingest") or "url_pool",
                        "reason": review_context.get("reason") or "用户在候选来源卡片中选择采集。",
                        "idempotency_key": review_context.get("idempotency_key") or "e2e-source-candidate-review",
                    },
                )
            ),
            CoreModelStep.tools(
                CoreToolCall(
                    tool_name="ingest.url_pool.submit",
                    call_id="call-e2e-url-pool-submit",
                    arguments={
                        "ingest_payload": {
                            "type": "url_pool",
                            "url": candidate.get("url"),
                            "source_name": candidate.get("title") or candidate.get("url"),
                            "metadata": {
                                "source": "agent_candidate_review",
                                "title": candidate.get("title"),
                                "snippet": candidate.get("snippet"),
                                "provider": candidate.get("provider") or candidate.get("source_provider"),
                                "trust": candidate.get("trust") if isinstance(candidate.get("trust"), dict) else {},
                            },
                        },
                        "async_mode": True,
                        "idempotency_key": f"{review_context.get('idempotency_key') or 'e2e-source-candidate-review'}:url_pool",
                    },
                )
            ),
            CoreModelStep.final("候选来源已记录为已采集意向，并已通过 ingest.url_pool.submit 提交到 URL-pool 采集边界；可继续从 ingest status 或任务结果查看入库进度。"),
        ]
    if ("url-pool" in text.lower() or "URL-pool" in text or "刚才采集" in text or "刚才提交" in text) and any(token in text for token in ("状态", "完成", "检查", "进度")):
        return [
            CoreModelStep.tools(CoreToolCall(tool_name="source.history.read", call_id="call-e2e-source-history-status", arguments={"include_recent_sessions": False, "item_limit": 10})),
            CoreModelStep.tools(CoreToolCall(tool_name="ingest.url_pool.status", call_id="call-e2e-url-pool-status", arguments={"limit": 10})),
            CoreModelStep.final("已读取刚才 URL-pool 提交的会话历史和任务事件。当前可见 task event 已写回 Agent session；若尚无项目内正式 evidence，则写作仍应标记为待复核来源。"),
        ]
    if ("刚才采集" in text or "刚才提交" in text or "URL-pool" in text) and ("写" in text or "工作台" in text or "草稿" in text):
        return [
            CoreModelStep.tools(CoreToolCall(tool_name="agent_artifact.search", call_id="call-e2e-url-pool-artifact-search", arguments={"query": "ingest.url_pool_submissions", "limit": 5})),
            CoreModelStep.tools(CoreToolCall(tool_name="agent_artifact.read", call_id="call-e2e-url-pool-artifact-read", arguments={"artifact_ref": "ingest.url_pool_submissions.json"})),
            CoreModelStep.tools(
                CoreToolCall(
                    tool_name="writing.document.insert_paragraph",
                    call_id="call-e2e-url-pool-writing-append",
                    arguments={
                        "title": "E2E AgentCore Robotics Draft",
                        "operation": "append",
                        "allow_latest": True,
                        "content_md": "承接 e2e.robotics.baseline 的既有草稿线索：候选来源 https://example.gov/robotics-policy 已通过 URL-pool 采集边界提交；当前写作中先记录为待复核来源，待采集任务完成后再替换为正式引用。",
                        "source_refs": ["agent-artifact:ingest.url_pool_submissions.json", "url:https://example.gov/robotics-policy"],
                        "provenance": {"scenario": "url_pool_candidate_to_writing_e2e", "source_boundary": "ingest.url_pool.submit"},
                    },
                )
            ),
            CoreModelStep.final("已读取 URL-pool 提交 artifact，并把刚才采集的候选来源作为待复核来源追加到写作工作台草稿。"),
        ]
    if "来源库" in text and ("哪些" in text or "有什么" in text or "item" in text):
        return [
            CoreModelStep.tools(CoreToolCall(tool_name="source_library.item.list", call_id="call-e2e-source-catalog", arguments={"limit": 8})),
            CoreModelStep.final("当前我读取的是来源库/数据源目录，它们是采集入口，不等同于已经入库的项目资料。"),
        ]
    if any(token in text for token in ("长任务", "长程", "持续", "多轮", "调查", "追查", "线索")):
        return _e2e_long_task_scripted_steps()
    if material_intent.work_context == "writing" and material_intent.category in {"external_discovery", "external_ingest"}:
        return [
            CoreModelStep.tools(CoreToolCall(tool_name="project.context.bundle", call_id="call-e2e-writing-external-context", arguments={"query": text[:300], "limit": 8})),
            CoreModelStep.tools(
                CoreToolCall(
                    tool_name="source.discovery.plan",
                    call_id="call-e2e-writing-external-discovery",
                    arguments={
                        "topic": "写作外部资料补充",
                        "query_terms": ["official source", "market evidence"],
                        "candidate_urls": ["https://example.com/writing-source"],
                        "max_candidates": 4,
                        "matrix_mode": True,
                    },
                )
            ),
            CoreModelStep.tools(
                CoreToolCall(
                    tool_name="source.web.search",
                    call_id="call-e2e-writing-external-web-search",
                    arguments={
                        "query": "e2e writing external source candidates",
                        "query_variants": ["e2e writing external source candidates", "e2e writing external official evidence"],
                        "provider": "auto",
                        "language": "en",
                        "matrix_mode": True,
                        "max_results": 3,
                    },
                )
            ),
            CoreModelStep.tools(
                CoreToolCall(
                    tool_name="ingest.source_library.run",
                    call_id="call-e2e-writing-external-intake",
                    arguments={"items": ["e2e.writing.external"], "async_mode": True, "override_params": {"max_items": 1}},
                )
            ),
            CoreModelStep.final("已先读取写作语境和内部项目资料，再规划外部资料发现，并通过 source intake 提交 e2e.writing.external。"),
        ]
    if material_intent.work_context == "writing" and asks_material_supplement:
        return [
            CoreModelStep.tools(CoreToolCall(tool_name="project.context.bundle", call_id="call-e2e-writing-context", arguments={"query": text[:300], "limit": 8})),
            CoreModelStep.tools(CoreToolCall(tool_name="writing.document.list", call_id="call-e2e-writing-list", arguments={"limit": 8})),
            CoreModelStep.final("写作补资料已优先查看内部项目资料和写作工作台文档；当前没有直接执行外部采集。"),
        ]
    if asks_material_supplement:
        return [
            CoreModelStep.tools(CoreToolCall(tool_name="project.context.bundle", call_id="call-e2e-material-context", arguments={"query": text[:300], "limit": 8})),
            CoreModelStep.tools(
                CoreToolCall(
                    tool_name="source.discovery.plan",
                    call_id="call-e2e-material-discovery",
                    arguments={"topic": "一般资料补充", "query_terms": ["supplemental evidence"], "max_candidates": 4, "matrix_mode": True},
                )
            ),
            CoreModelStep.tools(
                CoreToolCall(
                    tool_name="source.web.search",
                    call_id="call-e2e-material-web-search",
                    arguments={
                        "query": "e2e supplemental material candidates",
                        "query_variants": ["e2e supplemental material candidates", "e2e supplemental official data"],
                        "provider": "auto",
                        "language": "en",
                        "matrix_mode": True,
                        "max_results": 3,
                    },
                )
            ),
            CoreModelStep.final("一般补充资料已先检查内部项目上下文，然后给出外部发现计划；没有直接把资料等同为来源库。"),
        ]
    if "已有资料" in text or "项目库" in text or "项目里有什么数据" in text:
        return [
            CoreModelStep.tools(CoreToolCall(tool_name="project.context.bundle", call_id="call-e2e-project-context", arguments={"query": text[:300], "limit": 8})),
            CoreModelStep.final("已读取项目上下文：内部已有资料、结构化数据、图谱、写作文档和来源库采集入口会被分开标注。"),
        ]
    return _e2e_long_task_scripted_steps()


def _extract_e2e_writing_workbench_context(message: str) -> dict[str, Any]:
    marker = "写作工作台上下文 JSON："
    _, _, suffix = str(message or "").partition(marker)
    if not suffix:
        return {}
    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(suffix.strip())
    except json.JSONDecodeError:
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _extract_e2e_source_candidate_review_context(message: str) -> dict[str, Any]:
    marker = "source_candidate_review JSON："
    _, _, suffix = str(message or "").partition(marker)
    if not suffix:
        return {}
    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(suffix.strip())
    except json.JSONDecodeError:
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _safe_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _safe_nonnegative_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _e2e_long_task_scripted_steps() -> list[CoreModelStep]:
    calls = [
        CoreToolCall(tool_name="project.context.bundle", call_id="call-e2e-context", arguments={"query": "机器人商业化 写作 外部资料", "limit": 8}),
        CoreToolCall(
            tool_name="agent_long_task.stage.update",
            call_id="call-e2e-stage-internal",
            arguments={
                "stage": "internal_evidence",
                "stage_status": "completed",
                "task_kind": "writing",
                "summary": "已先读取内部项目资料，发现仍缺外部官方来源。",
                "evidence_refs": [{"id": "internal.context.bundle", "label": "内部项目资料"}],
                "gap_list": [{"id": "gap.official.robotics", "summary": "缺少官方或监管来源"}],
                "next_actions": ["规划外部来源发现"],
                "idempotency_key": "e2e-stage-internal",
            },
        ),
        CoreToolCall(
            tool_name="source.discovery.plan",
            call_id="call-e2e-discovery",
            arguments={
                "topic": "机器人商业化与政策监管来源",
                "query_terms": ["robotics commercialization", "official robotics policy"],
                "candidate_urls": ["https://example.com/robotics-policy"],
                "source_kinds": ["official", "regulatory", "company"],
                "max_candidates": 4,
                "min_trust_score": 50,
                "matrix_mode": True,
            },
        ),
        CoreToolCall(
            tool_name="source.web.search",
            call_id="call-e2e-web-search",
            arguments={
                "query": "e2e robotics policy source candidates",
                "query_variants": ["e2e robotics policy source candidates", "e2e robotics official regulation evidence"],
                "provider": "auto",
                "language": "en",
                "matrix_mode": True,
                "max_results": 3,
            },
        ),
        CoreToolCall(tool_name="ingest.source_library.run", call_id="call-e2e-intake", arguments={"items": ["e2e.robotics.baseline"], "async_mode": True, "override_params": {"max_items": 1, "source_mode": "e2e_scripted"}}),
        CoreToolCall(
            tool_name="agent_long_task.stage.update",
            call_id="call-e2e-stage-intake",
            arguments={
                "stage": "source_intake",
                "stage_status": "completed",
                "task_kind": "writing",
                "summary": "已通过来源库 intake 边界提交外部来源采集任务。",
                "source_intake": [{"item_key": "e2e.robotics.baseline", "task_id": "e2e-task-robotics-baseline"}],
                "next_actions": ["保存线索并写入工作台草稿"],
                "idempotency_key": "e2e-stage-intake",
            },
        ),
        CoreToolCall(
            tool_name="agent_investigation.leads.append",
            call_id="call-e2e-leads",
            arguments={
                "artifact_name": "e2e-robotics.leads.json",
                "goal": "机器人商业化写作补充外部资料",
                "summary": "保存内部缺口、外部发现和 intake 线索。",
                "clue_nodes": [{"id": "robotics_policy_source", "label": "机器人政策来源", "kind": "source_candidate", "source_intake_task_id": "e2e-task-robotics-baseline"}],
                "pending_questions": ["采集任务完成后复核是否有官方统计口径"],
                "followed_leads": ["e2e.robotics.baseline"],
                "citations": ["source-library:e2e.robotics.baseline"],
                "idempotency_key": "e2e-leads",
            },
        ),
        CoreToolCall(
            tool_name="writing.document.insert_paragraph",
            call_id="call-e2e-writing",
            arguments={
                "title": "E2E AgentCore Robotics Draft",
                "operation": "append",
                "allow_latest": True,
                "content_md": "内部项目资料显示机器人商业化主题已有基础材料；外部来源已通过 e2e.robotics.baseline 进入采集边界，后续可按官方来源继续校验。",
                "source_refs": ["source-library:e2e.robotics.baseline", "agent-artifact:e2e-robotics.leads.json"],
                "provenance": {"scenario": "agent_core_real_backend_e2e", "material_flow": "internal_first_then_external_intake"},
            },
        ),
        CoreToolCall(
            tool_name="agent_long_task.stage.update",
            call_id="call-e2e-stage-draft",
            arguments={
                "stage": "draft_output",
                "stage_status": "completed",
                "task_kind": "writing",
                "summary": "已把内部资料判断和外部 intake 线索写入工作台草稿。",
                "draft_refs": [{"title": "E2E AgentCore Robotics Draft"}],
                "next_actions": ["等待采集结果完成后替换为正式引用"],
                "idempotency_key": "e2e-stage-draft",
            },
        ),
    ]
    return [CoreModelStep.tools(call) for call in calls] + [CoreModelStep.final("已完成内部优先检索、外部来源发现、source intake、线索保存和写作工作台草稿写入。")]


def _agent_runtime_feature_flags() -> dict[str, bool]:
    return {
        "agent_runtime_v2_enabled": bool(getattr(settings, "agent_runtime_v2_enabled", True)),
        "agent_stream_enabled": bool(getattr(settings, "agent_stream_enabled", True)),
        "agent_batch_as_tool_enabled": bool(getattr(settings, "agent_batch_as_tool_enabled", True)),
    }


def _resolve_runtime_variant(payload: AgentChatTurnRequest) -> str:
    requested = str(payload.runtime_variant or "").strip().lower()
    if requested in {"core", "agent_core", "agent_core_v3", "v3"}:
        return "agent_core_v3"
    if requested in {"legacy", "legacy_batch", "agent_batch"}:
        return "legacy_batch"
    if requested in {"v2", "runtime_v2", "agent_runtime_v2"}:
        return "agent_runtime_v2"
    return "agent_core_v3"


def _run_legacy_batch_turn(payload: AgentChatTurnRequest, *, command: str, project_key: str | None) -> dict[str, Any]:
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
    submit = dict(loop_result.get("submit") or {})
    job_id = submit.get("job_id")
    return {
        "contract_version": "agent_chat.legacy_batch_turn.v1",
        "runtime_variant": "legacy_batch",
        "turn": {"message": command},
        "project_key": project_key,
        "loop_result": loop_result,
        "capability_calls": [
            {
                "capability_id": "agent_batch.nl_command.submit",
                "tool_name": "agent_batch.nl_command.submit",
                "status": "completed" if job_id else "skipped",
                "summary": f"legacy agent_batch submitted job_id={job_id}" if job_id else "legacy agent_batch completed without job_id",
                "result": loop_result,
            }
        ],
        "final_answer": (
            f"已通过 legacy agent_batch 回退路径处理，job_id={job_id}。"
            if job_id
            else "已通过 legacy agent_batch 回退路径处理。"
        ),
        "feature_flags": _agent_runtime_feature_flags(),
    }


def _run_agent_runtime_v2_turn(payload: AgentChatTurnRequest, *, command: str, project_key: str | None) -> dict[str, Any]:
    runtime = InteractiveAgentRuntime()
    model_planner_enabled = bool(payload.enable_model_tool_loop)
    out = runtime.run_turn(
        message=command,
        project_key=project_key,
        session_id=payload.session_id,
        idempotency_key=payload.idempotency_key,
        dry_run=bool(payload.dry_run),
        enable_bounded_retry=bool(payload.enable_bounded_retry),
        enable_limited_branching=bool(payload.enable_limited_branching),
        batch_loop_runner=run_agent_batch_nl_command_loop,
        parser_fallback=plan_batch_search_command,
        submitter=_submit_jobs_from_loop_tasks,
        executor_snapshot=inspect_executor_health,
        source_library_lister=_list_source_library_items_for_agent,
        run_loop_planner=None,
        turn_decision_planner=GuardedModelTurnDecisionPlanner() if model_planner_enabled else None,
        require_high_risk_approval=bool(payload.require_high_risk_approval),
    )
    out["feature_flags"] = _agent_runtime_feature_flags()
    out["runtime_variant"] = "agent_runtime_v2"
    return out


def _prepare_agent_core_session(payload: AgentChatTurnRequest, *, command: str, project_key: str | None) -> tuple[Any, dict[str, Any], str, str | None]:
    service = get_agent_session_service()
    if payload.session_id:
        session = service.get_session(payload.session_id)
        project_key = _validate_agent_core_session_project(session=session, project_key=project_key)
        session_id = str(session["session_id"])
        service.create_message(
            session_id,
            role="user",
            actor="agent_core_user",
            content=command,
            metadata={"project_key": project_key, "runtime_variant": "agent_core_v3"},
        )
    else:
        source = "e2e-scripted" if bool(getattr(settings, "agent_core_e2e_scripted_provider_enabled", False)) else "user"
        bundle = service.create_session(
            source=source,
            entrypoint_type="agent_core",
            goal=command,
            project_key=project_key,
            initial_context={"message": command, "runtime_variant": "agent_core_v3"},
            metadata={"agent_core": {"contract_version": "agent_core.turn.v1"}},
            task_blueprints=[
                {
                    "subject": "Agent Core Turn",
                    "description": "Conversation-first agent-core turn with model-owned tool selection.",
                    "task_type": "agent_core_turn",
                    "phase": "conversation",
                    "execution_mode": "coordinator",
                    "priority": 1,
                    "write_set": [],
                    "read_set": ["project:context"],
                    "task_spec": {
                        "task_type": "agent_core_turn",
                        "goal": command,
                        "context": {"runtime_variant": "agent_core_v3", "project_key": project_key},
                        "target_scope": "session",
                        "write_set": [],
                        "completion_criteria": [
                            "Answer directly or call project tools selected by the model.",
                        ],
                        "verification_steps": [
                            "Persist core events and tool results for frontend replay.",
                        ],
                        "artifact_targets": [],
                    },
                    "metadata": {"agent_core": True, "mechanical_plan": False},
                }
            ],
        )
        session = dict(bundle["session"])
        session_id = str(session["session_id"])
    return service, session, session_id, project_key


def _validate_agent_core_session_project(*, session: dict[str, Any], project_key: str | None) -> str | None:
    session_project_key = str(session.get("project_key") or "").strip() or None
    requested_project_key = str(project_key or "").strip() or None
    if session_project_key and requested_project_key and session_project_key != requested_project_key:
        raise ValueError(
            "session_id belongs to a different project; start a new agent session or use the session project_key"
        )
    return requested_project_key or session_project_key


_CONTEXTUAL_FOLLOWUP_TOKENS = (
    "总结",
    "概括",
    "整理",
    "继续",
    "接着",
    "然后",
    "下一步",
    "展开",
    "上面",
    "刚才",
    "这个",
    "这些",
    "它",
    "那",
    "其中",
    "第二",
    "第三",
    "第一",
    "summarize",
    "continue",
    "expand",
    "above",
    "previous",
    "that",
    "those",
)


def _build_agent_core_context(
    *,
    service: Any,
    session: dict[str, Any],
    session_id: str,
    command: str,
    project_key: str | None,
    stream: bool = False,
) -> dict[str, Any]:
    prior_transcript = _compact_prior_session_transcript(service=service, session_id=session_id, current_command=command)
    session_context_summary = _build_agent_core_session_context_summary(
        service=service,
        session_id=session_id,
        command=command,
        project_key=project_key,
    )
    return {
        "runtime_variant": "agent_core_v3",
        "stream": bool(stream),
        "agent_core_emit_turn_state_events": True,
        "root_task_id": str(session.get("root_task_id") or "").strip() or None,
        "project_key": project_key,
        "contextual_followup": _looks_like_contextual_followup(command),
        "prior_transcript": prior_transcript,
        "session_context_summary": session_context_summary,
        "session_context_policy": (
            "If the user message is elliptical, deictic, or a follow-up such as summarizing, continuing, or expanding, "
            "resolve it against prior_transcript and session_context_summary before asking a clarification question. "
            "If a follow-up depends on project data/tools used earlier, expose the same project tool family again."
        ),
    }


def _build_agent_core_session_context_summary(
    *,
    service: Any,
    session_id: str,
    command: str,
    project_key: str | None,
) -> dict[str, Any]:
    try:
        bundle = service.get_session_bundle(session_id)
        summary = build_session_context_summary(
            dict(bundle or {}),
            latest_user_instruction=command,
            project_key=project_key,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": {"type": exc.__class__.__name__, "message": str(exc)[:300]}}
    return _compact_agent_core_session_context_summary(summary)


def _compact_agent_core_session_context_summary(summary: dict[str, Any]) -> dict[str, Any]:
    data = dict(summary or {})
    stable = dict(data.get("stable_summary") or {})
    project_context = dict(data.get("project_context") or {})
    tool_use = dict(data.get("tool_use_summary") or {})
    budgeted = dict(data.get("budgeted_context") or {})
    return {
        "contract_version": data.get("contract_version"),
        "stable_summary": {
            "session": dict(stable.get("session") or {}),
            "counts": dict(stable.get("counts") or {}),
            "latest_user_instruction": stable.get("latest_user_instruction"),
            "memory_correction": dict(stable.get("memory_correction") or {}),
            "current_task": stable.get("current_task"),
            "history_summary": stable.get("history_summary"),
        },
        "project_context": {
            "project_key": project_context.get("project_key"),
            "goal": project_context.get("goal"),
            "session_status": project_context.get("session_status"),
            "artifact_index": project_context.get("artifact_index"),
            "source_library": project_context.get("source_library"),
            "ingest_status": project_context.get("ingest_status"),
            "workflow_graph": project_context.get("workflow_graph"),
            "recent_runs": project_context.get("recent_runs"),
        },
        "tool_use_summary": {
            "total_calls": tool_use.get("total_calls"),
            "unique_tool_count": tool_use.get("unique_tool_count"),
            "tool_counts": dict(tool_use.get("tool_counts") or {}),
            "status_counts": dict(tool_use.get("status_counts") or {}),
            "recent_results": list(tool_use.get("recent_results") or [])[-5:],
            "latest_failures": list(tool_use.get("latest_failures") or [])[-3:],
        },
        "budgeted_context": {
            "used_chars": budgeted.get("used_chars"),
            "omitted_sections": list(budgeted.get("omitted_sections") or []),
            "text": _truncate_context_text(budgeted.get("text"), limit=5000),
        },
        "memory_update": data.get("memory_update"),
    }


def _agent_core_tool_window_message(command: str, context: dict[str, Any]) -> str:
    if not _should_extend_tool_window_from_prior(command):
        return command
    parts = [str(command or "").strip()]
    session_summary = dict(context.get("session_context_summary") or {})
    stable = dict(session_summary.get("stable_summary") or {})
    session_info = dict(stable.get("session") or {})
    semantic_lines: list[str] = []
    for value in (session_info.get("goal"), stable.get("latest_user_instruction")):
        text = _truncate_context_text(value, limit=500)
        if text:
            semantic_lines.append(text)
    for item in list(context.get("prior_transcript") or [])[-5:]:
        if not isinstance(item, dict):
            continue
        text = _truncate_context_text(item.get("content"), limit=700)
        if text:
            semantic_lines.append(text)
    prior_text = _truncate_context_text("\n".join(semantic_lines), limit=2600)
    if prior_text:
        parts.append(f"Prior semantic context:\n{prior_text}")
    return "\n\n".join(part for part in parts if part)


def _should_extend_tool_window_from_prior(message: str) -> bool:
    lowered = str(message or "").strip().lower()
    if not lowered:
        return False
    return any(token in lowered for token in _CONTEXTUAL_FOLLOWUP_TOKENS)


def _agent_core_context_summary_for_response(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "agent_core.context_summary.v1",
        "contextual_followup": bool(context.get("contextual_followup")),
        "prior_transcript_count": len(list(context.get("prior_transcript") or [])),
        "session_context_summary": dict(context.get("session_context_summary") or {}),
    }


def _agent_core_turn_budgets(tool_window: Any) -> dict[str, int]:
    profile = str(getattr(tool_window, "profile", "") or "")
    visible_tool_count = int(getattr(tool_window, "visible_tool_count", 0) or 0)
    if profile in {"long-task-investigation", "writing-workbench", "material-collection"}:
        return {
            "max_iterations": 14,
            "max_tool_calls": max(8, min(16, max(visible_tool_count + 2, 12))),
        }
    return {
        "max_iterations": 6,
        "max_tool_calls": max(1, min(12, max(4, visible_tool_count + 2))),
    }


def _compact_prior_session_transcript(*, service: Any, session_id: str, current_command: str) -> list[dict[str, Any]]:
    try:
        messages = [dict(item or {}) for item in service.list_messages(session_id)]
    except Exception:  # noqa: BLE001
        return []
    if messages:
        last = messages[-1]
        if str(last.get("role") or "") == "user" and str(last.get("content") or "").strip() == str(current_command or "").strip():
            messages = messages[:-1]
    out: list[dict[str, Any]] = []
    for item in messages[-8:]:
        role = str(item.get("role") or "").strip()
        if role not in {"user", "assistant"}:
            continue
        content = _truncate_context_text(item.get("content"), limit=2200)
        if not content:
            continue
        out.append(
            {
                "role": role,
                "content": content,
                "actor": str(item.get("actor") or role),
                "created_at": item.get("created_at"),
            }
        )
    return out


def _truncate_context_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _looks_like_contextual_followup(message: str) -> bool:
    text = str(message or "").strip()
    lowered = text.lower()
    if not text:
        return False
    return any(token in lowered for token in _CONTEXTUAL_FOLLOWUP_TOKENS)


def _run_agent_core_turn(payload: AgentChatTurnRequest, *, command: str, project_key: str | None) -> dict[str, Any]:
    service, session, session_id, project_key = _prepare_agent_core_session(payload, command=command, project_key=project_key)
    registry = build_project_core_tool_registry(
        service=service,
        source_library_lister=_list_source_library_items_for_agent,
    )
    all_specs = registry.list_specs()
    core_context = _build_agent_core_context(
        service=service,
        session=session,
        session_id=session_id,
        command=command,
        project_key=project_key,
    )
    tool_window_message = _agent_core_tool_window_message(command, core_context)
    tool_window = select_core_tool_window(message=tool_window_message, tool_specs=all_specs)
    core_context["tool_window_profile"] = tool_window.profile
    core_context["agent_core_auto_answer_after_project_tools"] = False
    provider = _build_agent_core_provider()
    core = AgentCore(provider=provider, tool_registry=registry, tool_specs=list(tool_window.specs), policy_tool_specs=all_specs)
    budgets = _agent_core_turn_budgets(tool_window)
    result = core.run(
        AgentCoreRequest(
            message=command,
            session_id=session_id,
            project_key=project_key,
            context=core_context,
            max_iterations=budgets["max_iterations"],
            max_tool_calls=budgets["max_tool_calls"],
            approval_policy="enabled" if payload.require_high_risk_approval else "frozen",
        )
    )
    root_task_id = str(session.get("root_task_id") or "").strip() or None
    final_answer, persisted_approval = _persist_agent_core_result(
        service=service,
        session_id=session_id,
        command=command,
        project_key=project_key,
        result=result,
        root_task_id=root_task_id,
    )
    bundle = service.get_session_bundle(session_id)
    capability_calls = [_capability_call_from_core_tool_result(item) for item in result.tool_results]
    approval_requests = [persisted_approval] if persisted_approval else []
    return {
        "contract_version": "agent_core.turn.v1",
        "runtime_variant": "agent_core_v3",
        "turn": {"turn_id": result.turn_id, "message": command, "dry_run": bool(payload.dry_run)},
        "session": bundle["session"],
        "tasks": bundle["tasks"],
        "messages": bundle["messages"],
        "events": [event.to_dict() for event in result.events],
        "artifacts": _compact_agent_artifacts_for_chat(list(bundle["artifacts"] or [])),
        "approvals": bundle["approvals"],
        "agent_mode": "core",
        "plan": {
            "strategy": "model-owned-tool-loop",
            "classifier": "not_used",
            "tool_count": tool_window.visible_tool_count,
            **tool_window.to_plan_metadata(),
            "tool_window_context_used": tool_window_message != command,
            "stop_reason": result.stop_reason,
        },
        "capability_calls": capability_calls,
        "suggested_next_actions": [],
        "loop_result": {},
        "run_loop": _compact_agent_core_run_loop(result),
        "approval_requests": approval_requests,
        "context_summary": _agent_core_context_summary_for_response(core_context),
        "stream": build_stream_descriptor(session_id=session_id),
        "final_answer": final_answer,
        "feature_flags": _agent_runtime_feature_flags(),
    }


def _capability_call_from_core_tool_result(result: Any) -> dict[str, Any]:
    payload = result.to_dict()
    return {
        "contract_version": "agent_core.capability_call.v1",
        "turn_id": payload.get("turn_id"),
        "capability_id": payload.get("tool_name"),
        "tool_name": payload.get("tool_name"),
        "status": payload.get("status"),
        "summary": payload.get("ui_summary") or payload.get("model_summary"),
        "result": payload.get("structured_content") or {},
        "error": payload.get("error"),
        "call_id": payload.get("call_id"),
        "protocol": "agent_core",
        "stream_state": payload.get("status"),
    }


def _compact_agent_core_run_loop(result: Any) -> dict[str, Any]:
    return {
        "session_id": result.session_id,
        "turn_id": result.turn_id,
        "event_count": len(list(result.events or [])),
        "final_answer": result.final_answer,
        "tool_results": [
            {
                "call_id": item.call_id,
                "tool_name": item.tool_name,
                "status": item.status,
                "summary": item.ui_summary or item.model_summary,
            }
            for item in list(result.tool_results or [])
        ],
        "permission_request": result.permission_request.to_dict() if result.permission_request else None,
        "stop_reason": result.stop_reason,
    }


def _compact_agent_artifacts_for_chat(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "artifact_id": item.get("artifact_id"),
            "artifact_type": item.get("artifact_type"),
            "name": item.get("name"),
            "mime_type": item.get("mime_type"),
            "summary": item.get("summary"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        for item in artifacts
    ]


def _continue_agent_core_approval(approval_id: str, payload: AgentChatApprovalContinueRequest) -> dict[str, Any]:
    service = get_agent_session_service()
    approval = service.store.get_approval(str(approval_id or "").strip())
    binding_payload = dict(approval.get("binding_payload") or {})
    if str(binding_payload.get("contract_version") or "") != "agent_core.permission_request.v1":
        raise ValueError("approval is not an agent_core permission request")
    if str(approval.get("status") or "") == "pending":
        approval = service.resolve_approval(str(approval_id), approved_by=payload.approved_by, approved=True)
    if str(approval.get("status") or "") != "approved":
        raise ValueError("approval must be approved before continue")

    session_id = str(binding_payload.get("session_id") or approval.get("requester_session_id") or "").strip()
    project_key = str(binding_payload.get("project_key") or "").strip() or None
    user_message = str(binding_payload.get("user_message") or "继续").strip() or "继续"
    tool_payload = dict(binding_payload.get("tool_call") or {})
    arguments = dict(tool_payload.get("arguments") or {})
    overrides = dict(payload.binding_payload_overrides or {})
    if isinstance(overrides.get("arguments"), dict):
        arguments.update(dict(overrides["arguments"]))
    elif overrides:
        arguments.update(overrides)
    tool_call = CoreToolCall(
        tool_name=str(tool_payload.get("tool_name") or "").strip(),
        arguments=arguments,
        call_id=str(tool_payload.get("call_id") or "").strip(),
        reason=str(tool_payload.get("reason") or "").strip() or None,
    )
    if not session_id or not tool_call.tool_name or not tool_call.call_id:
        raise ValueError("agent_core approval binding is missing resume fields")
    session = service.get_session(session_id)
    project_key = _validate_agent_core_session_project(session=session, project_key=project_key)
    registry = build_project_core_tool_registry(
        service=service,
        source_library_lister=_list_source_library_items_for_agent,
    )
    all_specs = registry.list_specs()
    forced_tool_names = {tool_call.tool_name}
    core_context = _build_agent_core_context(
        service=service,
        session=session,
        session_id=session_id,
        command=user_message,
        project_key=project_key,
    )
    core_context["approval_id"] = approval_id
    tool_window_message = _agent_core_tool_window_message(user_message, core_context)
    tool_window = select_core_tool_window(message=tool_window_message, tool_specs=all_specs, forced_tool_names=forced_tool_names)
    core_context["tool_window_profile"] = tool_window.profile
    core_context["agent_core_auto_answer_after_project_tools"] = False
    provider = _build_agent_core_provider()
    core = AgentCore(provider=provider, tool_registry=registry, tool_specs=list(tool_window.specs), policy_tool_specs=all_specs)
    result = core.run(
        AgentCoreRequest(
            message=user_message,
            session_id=session_id,
            project_key=project_key,
            context=core_context,
            approval_policy="enabled",
            resume=CoreApprovalResume(
                approval_id=str(approval_id),
                tool_call=tool_call,
                approved=True,
                approved_by=payload.approved_by,
                updated_arguments=arguments,
            ),
        )
    )
    root_task_id = str(session.get("root_task_id") or "").strip() or None
    final_answer, persisted_approval = _persist_agent_core_result(
        service=service,
        session_id=session_id,
        command=user_message,
        project_key=project_key,
        result=result,
        root_task_id=root_task_id,
    )
    bundle = service.get_session_bundle(session_id)
    capability_calls = [_capability_call_from_core_tool_result(item) for item in result.tool_results]
    return {
        "contract_version": "agent_core.approval_continue.v1",
        "runtime_variant": "agent_core_v3",
        "approval": approval,
        "session": bundle["session"],
        "tasks": bundle["tasks"],
        "messages": bundle["messages"],
        "events": [event.to_dict() for event in result.events],
        "artifacts": bundle["artifacts"],
        "approvals": bundle["approvals"],
        "capability_call": capability_calls[-1] if capability_calls else {},
        "capability_calls": capability_calls,
        "approval_requests": [persisted_approval] if persisted_approval else [],
        "continued": True,
        "stream": build_stream_descriptor(session_id=session_id),
        "final_answer": final_answer,
    }


def _persist_agent_core_result(
    *,
    service: Any,
    session_id: str,
    command: str,
    project_key: str | None,
    result: Any,
    root_task_id: str | None,
) -> tuple[str, dict[str, Any] | None]:
    for event in result.events:
        service.store.append_event(
            session_id,
            event_type=f"agent_core.{event.event_type}",
            task_id=root_task_id,
            payload=event.to_dict(),
        )
    persisted_approval = None
    if result.permission_request is not None:
        persisted_approval = service.create_or_update_approval(
            approval_id=result.permission_request.approval_id,
            binding_payload={
                "contract_version": "agent_core.permission_request.v1",
                "session_id": session_id,
                "turn_id": result.turn_id,
                "tool_call": result.permission_request.tool_call.to_dict(),
                "tool_spec": result.permission_request.tool_spec.to_dict(),
                "user_message": command,
                "project_key": project_key,
            },
            requester_session_id=session_id,
            requester_task_id=root_task_id,
            requester_actor="agent_core",
            expires_at=None,
            status="pending",
            metadata={"runtime_variant": "agent_core_v3", "force_approval": True},
            audit_log=[{"action": "requested", "actor": "agent_core"}],
        )
    final_answer = result.final_answer
    cancel_completed = any(
        str(getattr(tool_result, "tool_name", "") or "") == "task.cancel"
        and str(getattr(tool_result, "status", "") or "").lower() == "completed"
        for tool_result in list(result.tool_results or [])
    )
    if not final_answer and persisted_approval:
        final_answer = "我需要先确认这个工具调用的执行边界，确认后会从同一会话继续。"
    if final_answer:
        service.create_message(
            session_id,
            role="assistant",
            actor="agent_core",
            task_id=root_task_id,
            content=final_answer,
            metadata={"runtime_variant": "agent_core_v3", "turn_id": result.turn_id, "stop_reason": result.stop_reason},
        )
    if root_task_id:
        task_status = "canceled" if cancel_completed else "blocked" if persisted_approval else "completed"
        service.release_task(
            session_id,
            root_task_id,
            status=task_status,
            result_summary=final_answer or result.stop_reason,
            result_payload=_compact_agent_core_run_loop(result),
            tool_use_count=len(list(result.tool_results or [])),
            activity=f"agent_core stop_reason={result.stop_reason}",
        )
    service.store.update_session(
        session_id,
        {
            "status": "canceled" if cancel_completed else "blocked" if persisted_approval else "completed",
            "current_phase": "approval" if persisted_approval else "final",
            "final_result": _compact_agent_core_run_loop(result),
        },
    )
    service._refresh_memory_artifacts(session_id, force=True)
    return final_answer, persisted_approval


def _run_agent_chat_turn_payload(payload: AgentChatTurnRequest) -> dict[str, Any]:
    command = str(payload.message or "").strip()
    if not command:
        _raise_invalid_input("message is required")
    if _agent_chat_requires_explicit_project_key(payload):
        raise ValueError("project_key is required for a new agent chat turn; do not rely on default project fallback")
    project_key = None if payload.session_id and str(payload.project_key or "").strip().lower() in _RESERVED_AGENT_PROJECT_KEYS else _resolve_agent_chat_project_key(payload.project_key)
    runtime_variant = _resolve_runtime_variant(payload)
    if runtime_variant == "legacy_batch":
        return _run_legacy_batch_turn(payload, command=command, project_key=project_key)
    if runtime_variant == "agent_core_v3":
        return _run_agent_core_turn(payload, command=command, project_key=project_key)
    return _run_agent_runtime_v2_turn(payload, command=command, project_key=project_key)


def _iter_agent_core_stream(payload: AgentChatTurnRequest):
    command = str(payload.message or "").strip()
    if not command:
        yield _sse("agent_core.error", {"status": "error", "error": error_response(ErrorCode.INVALID_INPUT, "message is required")})
        return
    if _agent_chat_requires_explicit_project_key(payload):
        yield _sse(
            "agent_core.error",
            {
                "status": "error",
                "error": error_response(
                    ErrorCode.INVALID_INPUT,
                    "project_key is required for a new agent chat turn; do not rely on default project fallback",
                ),
            },
        )
        return
    project_key = None if payload.session_id and str(payload.project_key or "").strip().lower() in _RESERVED_AGENT_PROJECT_KEYS else _resolve_agent_chat_project_key(payload.project_key)
    service, session, session_id, project_key = _prepare_agent_core_session(payload, command=command, project_key=project_key)
    registry = build_project_core_tool_registry(
        service=service,
        source_library_lister=_list_source_library_items_for_agent,
    )
    all_specs = registry.list_specs()
    core_context = _build_agent_core_context(
        service=service,
        session=session,
        session_id=session_id,
        command=command,
        project_key=project_key,
        stream=True,
    )
    tool_window_message = _agent_core_tool_window_message(command, core_context)
    tool_window = select_core_tool_window(message=tool_window_message, tool_specs=all_specs)
    core_context["tool_window_profile"] = tool_window.profile
    core_context["agent_core_auto_answer_after_project_tools"] = False
    provider = _build_agent_core_provider()
    core = AgentCore(provider=provider, tool_registry=registry, tool_specs=list(tool_window.specs), policy_tool_specs=all_specs)
    budgets = _agent_core_turn_budgets(tool_window)
    event_queue: Queue[Any] = Queue()
    result_holder: dict[str, Any] = {}

    def _target() -> None:
        try:
            result_holder["result"] = core.run(
                AgentCoreRequest(
                    message=command,
                    session_id=session_id,
                    project_key=project_key,
                    context=core_context,
                    max_iterations=budgets["max_iterations"],
                    max_tool_calls=budgets["max_tool_calls"],
                    approval_policy="enabled" if payload.require_high_risk_approval else "frozen",
                ),
                event_sink=event_queue.put,
            )
        except Exception as exc:  # noqa: BLE001
            result_holder["error"] = exc
        finally:
            event_queue.put(None)

    thread = threading.Thread(target=_target, name=f"agent-core-stream-{session_id}", daemon=True)
    thread.start()
    yield _sse("agent_core.stream_started", {"runtime_variant": "agent_core_v3", "session_id": session_id})
    last_keepalive_at = time.monotonic()
    while True:
        try:
            item = event_queue.get(timeout=0.25)
        except Empty:
            now = time.monotonic()
            if now - last_keepalive_at >= 5.0:
                last_keepalive_at = now
                yield _sse("agent_core.keepalive", {"status": "running", "session_id": session_id})
            if not thread.is_alive():
                break
            continue
        if item is None:
            break
        yield _sse(f"agent_core.{item.event_type}", item.to_dict())
    thread.join(timeout=1.0)
    if "error" in result_holder:
        exc = result_holder["error"]
        code, message, details = map_exception_to_error(exc)
        yield _sse(
            "agent_core.error",
            {"status": "error", "error": error_response(code, message, details=details)},
        )
        return
    result = result_holder.get("result")
    if result is None:
        yield _sse(
            "agent_core.error",
            {"status": "error", "error": error_response(ErrorCode.UPSTREAM_ERROR, "agent core stream ended without a result")},
        )
        return
    root_task_id = str(session.get("root_task_id") or "").strip() or None
    final_answer, persisted_approval = _persist_agent_core_result(
        service=service,
        session_id=session_id,
        command=command,
        project_key=project_key,
        result=result,
        root_task_id=root_task_id,
    )
    bundle = service.get_session_bundle(session_id)
    capability_calls = [_capability_call_from_core_tool_result(item) for item in result.tool_results]
    out = {
        "contract_version": "agent_core.turn.v1",
        "runtime_variant": "agent_core_v3",
        "turn": {"turn_id": result.turn_id, "message": command, "dry_run": bool(payload.dry_run)},
        "session": bundle["session"],
        "tasks": bundle["tasks"],
        "messages": bundle["messages"],
        "events": [],
        "event_count": len(list(result.events or [])),
        "artifacts": _compact_agent_artifacts_for_chat(list(bundle["artifacts"] or [])),
        "approvals": bundle["approvals"],
        "agent_mode": "core",
        "plan": {
            "strategy": "model-owned-tool-loop",
            "classifier": "not_used",
            "tool_count": tool_window.visible_tool_count,
            **tool_window.to_plan_metadata(),
            "tool_window_context_used": tool_window_message != command,
            "stop_reason": result.stop_reason,
        },
        "capability_calls": capability_calls,
        "suggested_next_actions": [],
        "loop_result": {},
        "run_loop": _compact_agent_core_run_loop(result),
        "approval_requests": [persisted_approval] if persisted_approval else [],
        "context_summary": _agent_core_context_summary_for_response(core_context),
        "stream": build_stream_descriptor(session_id=session_id),
        "final_answer": final_answer,
        "feature_flags": _agent_runtime_feature_flags(),
    }
    yield _sse(
        "agent_core.final_answer",
        {
            "status": "ok",
            "runtime_variant": "agent_core_v3",
            "session": out.get("session"),
            "final_answer": final_answer,
            "stream": out.get("stream"),
            "result": out,
        },
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    encoded = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {encoded}\n\n"


@router.get("/capabilities")
def list_agent_chat_capabilities(project_key: str | None = None) -> dict[str, Any]:
    runtime = InteractiveAgentRuntime()
    flags = _agent_runtime_feature_flags()
    resolved_project_key = str(project_key or "").strip() or None
    tool_pool = AgentToolPoolAssembler().assemble(
        ToolPoolRequest(
            project_key=resolved_project_key,
            agent_mode="read_only",
            feature_flags=flags,
        )
    )
    return ok({"items": runtime.list_capabilities(), "feature_flags": flags, "tool_pool": tool_pool})


@router.post("/turn")
def run_agent_chat_turn(payload: AgentChatTurnRequest) -> dict[str, Any]:
    try:
        out = _run_agent_chat_turn_payload(payload)
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok(out)


@router.post("/turn/stream")
def stream_agent_chat_turn(payload: AgentChatTurnRequest) -> StreamingResponse:
    def _iter():
        runtime_variant = _resolve_runtime_variant(payload)
        if runtime_variant == "agent_core_v3":
            yield _sse(
                "agent_core.stream_opened",
                {
                    "status": "ok",
                    "runtime_variant": "agent_core_v3",
                    "session_id": payload.session_id,
                },
            )
            yield from _iter_agent_core_stream(payload)
            return
        yield _sse("interactive_agent.stream_started", {"runtime_variant": runtime_variant})
        try:
            out = _run_agent_chat_turn_payload(payload)
        except Exception as exc:  # noqa: BLE001
            code, message, details = map_exception_to_error(exc)
            yield _sse(
                "interactive_agent.error",
                {
                    "status": "error",
                    "error": error_response(code, message, details=details),
                },
            )
            return
        for event in list(out.get("events") or []):
            if isinstance(event, dict):
                yield _sse(str(event.get("event_type") or "interactive_agent.event"), event)
        yield _sse(
            "interactive_agent.final_answer",
            {
                "status": "ok",
                "runtime_variant": out.get("runtime_variant"),
                "session": out.get("session"),
                "final_answer": out.get("final_answer"),
                "stream": out.get("stream"),
                "result": out,
            },
        )

    return StreamingResponse(_iter(), media_type="text/event-stream")


@router.post("/approvals/{approval_id}/continue")
def continue_agent_chat_approval(approval_id: str, payload: AgentChatApprovalContinueRequest) -> dict[str, Any]:
    runtime = InteractiveAgentRuntime()
    try:
        try:
            approval = get_agent_session_service().store.get_approval(str(approval_id or "").strip())
            binding_payload = dict(approval.get("binding_payload") or {})
        except Exception:
            binding_payload = {}
        if str(binding_payload.get("contract_version") or "") == "agent_core.permission_request.v1":
            out = _continue_agent_core_approval(approval_id, payload)
        else:
            out = runtime.continue_approved_capability(
                approval_id=approval_id,
                approved_by=payload.approved_by,
                binding_payload_overrides=dict(payload.binding_payload_overrides or {}),
            )
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=error_response(ErrorCode.NOT_FOUND, "approval not found"),
        )
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok(out)
