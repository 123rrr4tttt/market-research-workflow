"""Authoring and workflow project tools.

The module owns the authored tool declarations and special handlers for task,
session-resume, URL-pool, investigation, writing, workflow, report, and batch
execution.  Assembly remains with ``project_tools``; compiling this catalog
grants no business-effect authority.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import difflib
import json
from typing import Any

from functorial_kit import Failure

from app.services.agent_sessions.service import AgentSessionService
from app.services.projects import bind_project
from app.services.skill_runtime import invoke_skill
from app.services.agent_runtime.structured_data_search import query_project_structured_data
from app.services.writing import (
    WritingVersionConflictError,
    create_document,
    get_document,
    list_citations,
    list_documents,
    save_document_with_conflict,
    upsert_citations,
)
from mrw_functorial_kit.core.agent_service_semantics import agent_runtime_failures

from .contracts import AgentCoreRequest, CoreEvent, CoreToolCall, CoreToolResult, CoreToolSpec
from .tool_support import (
    _abort_requested_result,
    _compact_json_value,
    _compact_session,
    _concurrency_from_class,
    _missing_project_result,
    _normalize_string_list,
    _permission_from_approval,
    _resolve_project_key,
    _risk_from_metadata,
    _runtime_failure_result,
    _safe_int,
    _safe_nonnegative_int,
    _session_abort_requested,
    _stable_hash,
    _utcnow_iso,
)
from .tool_contribution import ProjectToolAuthorSource


def _agent_batch_submit_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_batch.submit",
        title="Submit Agent Batch Work",
        description_for_model=(
            "Submit governed background agent_batch work from structured jobs. "
            "Use this only for explicit user requests to dispatch batch tasks."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "jobs": {
                    "type": "array",
                    "description": "Structured agent_batch jobs.",
                    "items": {"type": "object", "additionalProperties": True},
                },
                "batch": {
                    "type": "object",
                    "properties": {"jobs": {"type": "array", "items": {"type": "object", "additionalProperties": True}}},
                    "additionalProperties": True,
                },
                "idempotency_key": {"type": "string"},
                "priority": {"type": "integer", "minimum": 0, "maximum": 9},
                "rule_set_id": {"type": "string"},
                "rule_set": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_external",
        permission="ask",
        concurrency="serial",
        timeout_seconds=30,
        result_budget=8000,
        project_service_id="agent_batch.submit",
        metadata={"contract_version": "agent_batch.submit.v1", "implemented": True},
    )

def _agent_batch_submit_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        return _run_agent_batch_submit_tool(tool_call=tool_call, request=request)

    return handler

def _agent_task_plan_append_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_task.plan.append",
        title="Append Agent Task Plan",
        description_for_model=(
            "Append durable subtasks to the current agent session for long-running work. "
            "Use this when the user asks for multi-step writing, investigation, clue tracing, or work that should continue across turns. "
            "This mutates only the session task ledger and is idempotent when idempotency_key or identical task content is replayed."
        ),
        input_schema={
            "type": "object",
            "required": ["tasks"],
            "properties": {
                "goal": {"type": "string", "description": "Optional refined goal for the appended plan."},
                "idempotency_key": {"type": "string", "description": "Stable key for replay-safe task creation."},
                "sequential": {"type": "boolean", "description": "When true, later tasks depend on the previous task unless dependencies are explicit."},
                "tasks": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 50,
                    "items": {
                        "type": "object",
                        "required": ["subject"],
                        "properties": {
                            "task_id": {"type": "string"},
                            "subject": {"type": "string"},
                            "description": {"type": "string"},
                            "phase": {
                                "type": "string",
                                "enum": ["conversation", "research", "synthesis", "implementation", "verification", "maintenance"],
                            },
                            "task_type": {"type": "string"},
                            "priority": {"type": "integer", "minimum": 1, "maximum": 10},
                            "blocked_by": {"type": "array", "items": {"type": "string"}},
                            "blocked_by_refs": {"type": "array", "items": {"type": "string"}},
                            "read_set": {"type": "array", "items": {"type": "string"}},
                            "write_set": {"type": "array", "items": {"type": "string"}},
                            "completion_criteria": {"type": "array", "items": {"type": "string"}},
                            "verification_steps": {"type": "array", "items": {"type": "string"}},
                            "artifact_targets": {"type": "array", "items": {"type": "string"}},
                            "metadata": {"type": "object", "additionalProperties": True},
                        },
                        "additionalProperties": True,
                    },
                },
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="allow",
        concurrency="serial",
        timeout_seconds=10,
        result_budget=5000,
        project_service_id="agent_task.plan.append",
        metadata={"auto_allow_session_write": True, "contract_version": "agent_task.plan.append.v1"},
    )

def _agent_task_plan_append_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        raw_tasks = tool_call.arguments.get("tasks") or tool_call.arguments.get("task_blueprints") or []
        if not isinstance(raw_tasks, list) or not raw_tasks:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="agent_task.plan.append requires a non-empty tasks array.",
                error={"code": "missing_tasks", "message": "tasks must be a non-empty array"},
            )

        idempotency_key = str(tool_call.arguments.get("idempotency_key") or "").strip()
        normalized_for_hash = _compact_json_value(raw_tasks, max_items=60, max_depth=6, max_string=800)
        if not idempotency_key:
            idempotency_key = _stable_hash(
                {
                    "session_id": request.session_id,
                    "goal": tool_call.arguments.get("goal") or request.message,
                    "tasks": normalized_for_hash,
                }
            )

        existing_tasks = service.list_tasks(request.session_id)
        existing_ids = {str(task.get("task_id") or "") for task in existing_tasks}
        existing_keys = {
            str((task.get("metadata") or {}).get("agent_core_plan_idempotency_key") or "")
            for task in existing_tasks
            if isinstance(task.get("metadata"), dict)
        }
        if idempotency_key in existing_keys:
            matched = [
                _compact_task(task)
                for task in existing_tasks
                if str((task.get("metadata") or {}).get("agent_core_plan_idempotency_key") or "") == idempotency_key
            ]
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"Task plan already exists; skipped duplicate append with {len(matched)} task(s).",
                structured_content={
                    "contract_version": "agent_task.plan.append.v1",
                    "session_id": request.session_id,
                    "idempotency_key": idempotency_key,
                    "created_count": 0,
                    "skipped_count": len(matched),
                    "tasks": matched,
                    "duplicate_replay": True,
                },
            )

        sequential = bool(tool_call.arguments.get("sequential"))
        blueprints: list[dict[str, Any]] = []
        skipped_task_ids: list[str] = []
        for index, raw in enumerate(raw_tasks[:50], start=1):
            if not isinstance(raw, dict):
                continue
            subject = str(raw.get("subject") or raw.get("title") or "").strip()
            if not subject:
                continue
            task_id = str(raw.get("task_id") or "").strip()
            if task_id and task_id in existing_ids:
                skipped_task_ids.append(task_id)
                continue
            blocked_by_refs = list(raw.get("blocked_by_refs") or [])
            if sequential and index > 1 and not raw.get("blocked_by") and "prev" not in blocked_by_refs:
                blocked_by_refs.append("prev")
            metadata = dict(raw.get("metadata") or {})
            metadata.update(
                {
                    "created_by": "agent_core",
                    "agent_core_call_id": tool_call.call_id,
                    "agent_core_plan_idempotency_key": idempotency_key,
                    "agent_core_plan_index": index,
                }
            )
            blueprint = {
                "subject": subject,
                "description": raw.get("description"),
                "phase": str(raw.get("phase") or "research").strip() or "research",
                "task_type": str(raw.get("task_type") or raw.get("phase") or "research").strip() or "research",
                "priority": int(raw.get("priority") or 5),
                "blocked_by": list(raw.get("blocked_by") or []),
                "blocked_by_refs": blocked_by_refs,
                "read_set": list(raw.get("read_set") or []),
                "write_set": list(raw.get("write_set") or []),
                "completion_criteria": list(raw.get("completion_criteria") or []),
                "verification_steps": list(raw.get("verification_steps") or []),
                "artifact_targets": list(raw.get("artifact_targets") or []),
                "metadata": metadata,
                "task_spec": dict(raw.get("task_spec") or {}),
            }
            if task_id:
                blueprint["task_id"] = task_id
            blueprints.append(blueprint)

        if not blueprints:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"No new tasks were appended; skipped {len(skipped_task_ids)} existing task id(s).",
                structured_content={
                    "contract_version": "agent_task.plan.append.v1",
                    "session_id": request.session_id,
                    "idempotency_key": idempotency_key,
                    "created_count": 0,
                    "skipped_task_ids": skipped_task_ids,
                },
            )

        try:
            created = service.append_task_blueprints(
                request.session_id,
                goal=str(tool_call.arguments.get("goal") or request.message or "").strip() or None,
                task_blueprints=blueprints,
            )
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to append task plan: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )

        compact_tasks = [_compact_task(task) for task in created]
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Appended {len(created)} durable task(s) to the current agent session.",
            ui_summary=f"Added {len(created)} task(s) to the session plan.",
            structured_content={
                "contract_version": "agent_task.plan.append.v1",
                "session_id": request.session_id,
                "idempotency_key": idempotency_key,
                "created_count": len(created),
                "skipped_task_ids": skipped_task_ids,
                "tasks": compact_tasks,
            },
        )

    return handler

_LONG_TASK_STAGE_ORDER = (
    "plan",
    "internal_evidence",
    "gap_analysis",
    "external_discovery",
    "source_intake",
    "clue_trace",
    "draft_output",
    "verification",
    "done",
)

_LONG_TASK_STAGE_LABELS = {
    "plan": "Plan stages",
    "internal_evidence": "Internal evidence pass",
    "gap_analysis": "Gap list",
    "external_discovery": "External discovery plan",
    "source_intake": "Source intake and trust gates",
    "clue_trace": "Clue trace",
    "draft_output": "Draft or artifact outputs",
    "verification": "Verification",
    "done": "Done",
}

_LONG_TASK_STAGE_STATUSES = {"pending", "in_progress", "completed", "blocked", "failed"}

def _agent_long_task_stage_update_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_long_task.stage.update",
        title="Update Long Task Stage State",
        description_for_model=(
            "Persist durable stage-machine state for long writing or investigation work. "
            "Use after planning, internal evidence search, gap detection, external discovery planning, source intake, clue tracing, draft output, or verification. "
            "This writes only the current agent session state artifact and can be replayed safely with idempotency_key."
        ),
        input_schema={
            "type": "object",
            "required": ["stage"],
            "properties": {
                "project_key": {"type": "string"},
                "artifact_name": {"type": "string"},
                "task_id": {"type": "string"},
                "task_kind": {"type": "string", "enum": ["investigation", "writing", "mixed"], "default": "mixed"},
                "stage": {"type": "string", "enum": list(_LONG_TASK_STAGE_ORDER)},
                "stage_status": {"type": "string", "enum": sorted(_LONG_TASK_STAGE_STATUSES), "default": "in_progress"},
                "summary": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "gap_list": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "external_discovery_plan": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "source_intake": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "clue_refs": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "draft_refs": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "next_actions": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "metadata": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="allow",
        concurrency="serial",
        timeout_seconds=10,
        result_budget=7000,
        project_service_id="agent_long_task.stage.update",
        metadata={"auto_allow_session_write": True, "contract_version": "agent_long_task.stage.v1"},
    )

def _agent_long_task_stage_update_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        stage = _normalize_long_task_stage(tool_call.arguments.get("stage"))
        if isinstance(stage, Failure):
            return _runtime_failure_result(tool_call, stage)
        stage_status = _normalize_long_task_stage_status(tool_call.arguments.get("stage_status"))
        if isinstance(stage_status, Failure):
            return _runtime_failure_result(tool_call, stage_status)
        project_key = _resolve_project_key(tool_call, request) or str(request.project_key or "").strip() or None
        artifact_name = str(tool_call.arguments.get("artifact_name") or "agent_long_task.state.json").strip() or "agent_long_task.state.json"
        task_id = str(tool_call.arguments.get("task_id") or "").strip() or None
        task_kind = str(tool_call.arguments.get("task_kind") or "mixed").strip().lower()
        if task_kind not in {"investigation", "writing", "mixed"}:
            task_kind = "mixed"
        existing_artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        existing_content = dict((existing_artifact or {}).get("content_json") or {})
        idempotency_key = str(tool_call.arguments.get("idempotency_key") or "").strip()
        replay_keys = [str(item or "") for item in list(existing_content.get("replay_keys") or []) if str(item or "").strip()]
        replayed = bool(idempotency_key and idempotency_key in replay_keys)
        if replayed:
            updated_content = _normalize_long_task_state(existing_content, session_id=request.session_id, project_key=project_key, task_kind=task_kind)
        else:
            if idempotency_key:
                replay_keys.append(idempotency_key)
            updated_content = _update_long_task_state(
                existing_content=existing_content,
                session_id=request.session_id,
                project_key=project_key,
                task_kind=task_kind,
                task_id=task_id,
                tool_call=tool_call,
                stage=stage,
                stage_status=stage_status,
                replay_keys=replay_keys[-80:],
            )
        artifact = service.store.upsert_artifact(
            {
                "session_id": request.session_id,
                "name": artifact_name,
                "artifact_type": "agent_long_task_state",
                "mime_type": "application/json",
                "content_text": json.dumps(updated_content, ensure_ascii=False, sort_keys=True, default=str),
                "content_json": updated_content,
                "metadata": {
                    "project_key": project_key,
                    "task_kind": task_kind,
                    "contract_version": "agent_long_task.stage.v1",
                    "auto_written_by": "agent_core",
                    "replayed": replayed,
                },
            }
        )
        if task_id:
            _attach_long_task_state_to_task(
                service=service,
                session_id=request.session_id,
                task_id=task_id,
                artifact_name=artifact_name,
                state=updated_content,
                stage=stage,
                stage_status=stage_status,
            )
        service.store.append_event(
            request.session_id,
            event_type="agent_long_task.stage.updated",
            task_id=task_id,
            payload={
                "artifact_name": artifact_name,
                "stage": stage,
                "stage_status": stage_status,
                "current_stage": updated_content.get("current_stage"),
                "replayed": replayed,
            },
        )
        state = _compact_long_task_state(updated_content)
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Updated long-task stage {stage} as {stage_status}; current_stage={state.get('current_stage')}.",
            structured_content={
                "contract_version": "agent_long_task.stage.v1",
                "project_key": project_key,
                "artifact_name": artifact_name,
                "artifact_id": artifact.get("artifact_id"),
                "state": state,
                "replayed": replayed,
            },
            artifact_refs=(str(artifact.get("artifact_id") or artifact_name),),
        )

    return handler

def _agent_long_task_stage_read_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_long_task.stage.read",
        title="Read Long Task Stage State",
        description_for_model=(
            "Read durable long writing/investigation stage-machine state from the current session. "
            "Use before continuing a long task after page switch, hard refresh, or a follow-up like 'continue'."
        ),
        input_schema={
            "type": "object",
            "properties": {"artifact_name": {"type": "string"}},
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=7000,
        project_service_id="agent_long_task.stage.read",
        metadata={"contract_version": "agent_long_task.stage.v1"},
    )

def _agent_long_task_stage_read_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        artifact_name = str(tool_call.arguments.get("artifact_name") or "agent_long_task.state.json").strip() or "agent_long_task.state.json"
        artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        if artifact is None:
            state = _seed_long_task_state(session_id=request.session_id, project_key=request.project_key, task_kind="mixed", replay_keys=[])
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"No long-task stage artifact named {artifact_name} exists yet.",
                structured_content={
                    "contract_version": "agent_long_task.stage.v1",
                    "artifact_name": artifact_name,
                    "missing_artifact": True,
                    "state": _compact_long_task_state(state),
                },
            )
        content = _normalize_long_task_state(
            dict(artifact.get("content_json") or {}),
            session_id=request.session_id,
            project_key=request.project_key,
            task_kind=str((artifact.get("metadata") or {}).get("task_kind") or "mixed"),
        )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Read long-task stage state from {artifact_name}: current_stage={content.get('current_stage')}.",
            structured_content={
                "contract_version": "agent_long_task.stage.v1",
                "artifact_name": artifact_name,
                "missing_artifact": False,
                "artifact_id": artifact.get("artifact_id"),
                "state": _compact_long_task_state(content),
            },
            artifact_refs=(str(artifact.get("artifact_id") or artifact_name),),
        )

    return handler

def _agent_session_resume_bundle_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_session.resume_bundle",
        title="Agent Session Resume Bundle",
        description_for_model=(
            "Read a compact resume bundle for the current session, including active tasks, recent messages, artifacts, approvals, and status. "
            "Use this before continuing long-running work or resolving ambiguous follow-up instructions."
        ),
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 30}},
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=5000,
        project_service_id="agent_session.resume_bundle",
    )

def _agent_session_resume_bundle_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        limit = max(1, min(30, int(tool_call.arguments.get("limit") or 10)))
        try:
            bundle = service.get_session_bundle(request.session_id)
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to read session resume bundle: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        tasks = list(bundle.get("tasks") or [])
        artifacts = list(bundle.get("artifacts") or [])
        active_tasks = [task for task in tasks if str(task.get("status") or "") not in {"completed", "failed", "canceled", "expired"}]
        long_task_states = [
            _compact_long_task_state(_normalize_long_task_state(dict(item.get("content_json") or {}), session_id=request.session_id, project_key=request.project_key, task_kind=str((item.get("metadata") or {}).get("task_kind") or "mixed")))
            for item in artifacts
            if str(item.get("artifact_type") or "") == "agent_long_task_state"
        ]
        content = {
            "contract_version": "agent_session.resume_bundle.v1",
            "session": _compact_session(dict(bundle.get("session") or {})),
            "active_tasks": [_compact_task(task) for task in active_tasks[:limit]],
            "recent_tasks": [_compact_task(task) for task in tasks[-limit:]],
            "recent_messages": _compact_json_value(list(bundle.get("messages") or [])[-limit:], max_items=limit, max_depth=4),
            "recent_artifacts": _compact_json_value(artifacts[-limit:], max_items=limit, max_depth=4),
            "long_task_states": _compact_json_value(long_task_states[-limit:], max_items=limit, max_depth=5),
            "pending_approvals": _compact_json_value(
                [item for item in list(bundle.get("approvals") or []) if str(item.get("status") or "") in {"pending", "requested"}],
                max_items=limit,
                max_depth=4,
            ),
            "counts": {
                "tasks": len(tasks),
                "active_tasks": len(active_tasks),
                "messages": len(list(bundle.get("messages") or [])),
                "artifacts": len(artifacts),
                "long_task_states": len(long_task_states),
                "approvals": len(list(bundle.get("approvals") or [])),
            },
        }
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Read resume bundle with {len(active_tasks)} active task(s).",
            structured_content=content,
        )

    return handler

def _ingest_url_pool_submit_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="ingest.url_pool.submit",
        title="Submit URL-Pool Ingest",
        description_for_model=(
            "Submit an approved URL candidate to the existing URL-pool/source-library ingestion frontdoor. "
            "Use this after source.candidate.review returns an approved URL-pool ingest_payload, or when the user explicitly asks to collect a concrete external URL. "
            "Prefer async_mode=true for interactive chat so the turn returns with a task id instead of waiting for network extraction."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "url": {"type": "string"},
                "query_terms": {"type": "array", "items": {"type": "string"}},
                "strict_mode": {"type": "boolean"},
                "async_mode": {"type": "boolean", "description": "Default true. Queue ingestion and return a task id."},
                "search_options": {"type": "object", "additionalProperties": True},
                "source_name": {"type": "string"},
                "metadata": {"type": "object", "additionalProperties": True},
                "candidate_review_key": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "artifact_name": {"type": "string"},
                "ingest_payload": {
                    "type": "object",
                    "description": "The url_pool ingest_payload returned by source.candidate.review.",
                    "additionalProperties": True,
                },
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_external",
        permission="allow",
        concurrency="serial",
        timeout_seconds=20,
        result_budget=8000,
        project_service_id="ingest.url_pool.submit",
        metadata={
            "contract_version": "ingest.url_pool.submit.v1",
            "uses_existing_frontdoor": "services.ingest.url_pool.ingest_url_via_source_library_frontdoor",
            "preferred_after_tool": "source.candidate.review",
        },
    )

def _ingest_url_pool_submit_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        raw_payload = tool_call.arguments.get("ingest_payload")
        ingest_payload = dict(raw_payload or {}) if isinstance(raw_payload, dict) else {}
        project_key = str(
            tool_call.arguments.get("project_key")
            or ingest_payload.get("project_key")
            or request.project_key
            or ""
        ).strip()
        if not project_key:
            return _missing_project_result(tool_call)

        url = str(tool_call.arguments.get("url") or ingest_payload.get("url") or "").strip()
        if not url:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="url is required for URL-pool ingestion.",
                error={"code": "missing_url", "message": "url is required"},
                structured_content={"arguments": dict(tool_call.arguments or {})},
            )

        query_terms = _normalize_string_list(tool_call.arguments.get("query_terms") or ingest_payload.get("query_terms"))
        strict_mode = bool(tool_call.arguments.get("strict_mode") or ingest_payload.get("strict_mode") or False)
        async_mode = bool(tool_call.arguments.get("async_mode", ingest_payload.get("async_mode", True)))
        search_options = tool_call.arguments.get("search_options", ingest_payload.get("search_options"))
        search_options = dict(search_options) if isinstance(search_options, dict) else None
        metadata = dict(ingest_payload.get("metadata") or {})
        if isinstance(tool_call.arguments.get("metadata"), dict):
            metadata.update(dict(tool_call.arguments.get("metadata") or {}))
        source_name = str(
            tool_call.arguments.get("source_name")
            or ingest_payload.get("source_name")
            or metadata.get("title")
            or url
        ).strip()
        artifact_name = str(tool_call.arguments.get("artifact_name") or "ingest.url_pool_submissions.json").strip() or "ingest.url_pool_submissions.json"
        candidate_review_key = str(tool_call.arguments.get("candidate_review_key") or metadata.get("review_key") or "").strip()
        idempotency_key = str(tool_call.arguments.get("idempotency_key") or "").strip() or _stable_hash(
            {
                "project_key": project_key,
                "url": url,
                "query_terms": query_terms,
                "strict_mode": strict_mode,
                "search_options": search_options,
                "candidate_review_key": candidate_review_key,
            }
        )

        if _session_abort_requested(service=service, session_id=request.session_id):
            return _abort_requested_result(
                service=service,
                request=request,
                tool_call=tool_call,
                emit=emit,
                skipped_items=[url],
                dispatched_count=0,
            )

        existing_artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        existing_content = dict((existing_artifact or {}).get("content_json") or {})
        submissions = [dict(item) for item in list(existing_content.get("submissions") or []) if isinstance(item, dict)]
        replayed_submission = next((item for item in submissions if str(item.get("idempotency_key") or "") == idempotency_key), None)
        if replayed_submission:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"URL-pool ingest submission was already queued for {url}.",
                ui_summary=f"URL-pool ingest already queued: {url}",
                structured_content={
                    "contract_version": "ingest.url_pool.submit.v1",
                    "project_key": project_key,
                    "url": url,
                    "replayed": True,
                    "submission": _compact_json_value(replayed_submission, max_items=18, max_depth=5),
                },
                artifact_refs=(str((existing_artifact or {}).get("artifact_id") or artifact_name),),
            )

        task_search_options = dict(search_options or {})
        deterministic_task_id = f"agent-url-pool-{_stable_hash({'project_key': project_key, 'url': url, 'idempotency_key': idempotency_key})[:24]}"
        agent_submission_marker = {
            "session_id": request.session_id,
            "artifact_name": artifact_name,
            "idempotency_key": idempotency_key,
            "candidate_review_key": candidate_review_key,
            "project_key": project_key,
            "url": url,
            "task_id": deterministic_task_id,
            "source_call_id": tool_call.call_id,
        }
        task_search_options["_agent_core_url_pool_submission"] = agent_submission_marker

        try:
            if async_mode:
                from app.services.tasks import task_ingest_url_via_source_library

                task_args = (url, query_terms or None, strict_mode, project_key, task_search_options)
                if hasattr(task_ingest_url_via_source_library, "apply_async"):
                    async_result = task_ingest_url_via_source_library.apply_async(args=task_args, task_id=deterministic_task_id)
                else:
                    async_result = task_ingest_url_via_source_library.delay(*task_args)
                dispatch_result = {
                    "task_id": str(getattr(async_result, "id", "") or ""),
                    "status": "queued",
                    "async": True,
                    "task_result_status": "queued",
                    "params": {
                        "url": url,
                        "query_terms": query_terms or None,
                        "strict_mode": strict_mode,
                        **({"search_options": search_options} if isinstance(search_options, dict) else {}),
                    },
                    "effective_payload": {
                        "url": url,
                        "project_key": project_key,
                        "query_terms": query_terms or None,
                        "strict_mode": strict_mode,
                        "async_mode": True,
                        "agent_session_id": request.session_id,
                    },
                }
            else:
                with bind_project(project_key):
                    from app.services.ingest.url_pool import ingest_url_via_source_library_frontdoor

                    dispatch_result = ingest_url_via_source_library_frontdoor(
                        url=url,
                        project_key=project_key,
                        query_terms=query_terms or None,
                        strict_mode=strict_mode,
                        search_options=task_search_options,
                        frontdoor_options={"enabled": True},
                        entrypoint="agent_core.ingest.url_pool.submit",
                        source_name=source_name or "agent_core_url_pool_submit",
                        enable_extraction=True,
                    )
                    if isinstance(dispatch_result, dict):
                        dispatch_result.setdefault(
                            "effective_payload",
                            {
                                "url": url,
                                "project_key": project_key,
                                "query_terms": query_terms or None,
                                "strict_mode": strict_mode,
                                "async_mode": False,
                                "agent_session_id": request.session_id,
                            },
                        )
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"URL-pool ingest submission failed: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
                structured_content={
                    "contract_version": "ingest.url_pool.submit.v1",
                    "project_key": project_key,
                    "url": url,
                    "async_mode": async_mode,
                    "search_options": search_options,
                },
            )

        if _session_abort_requested(service=service, session_id=request.session_id):
            return _abort_requested_result(
                service=service,
                request=request,
                tool_call=tool_call,
                emit=emit,
                skipped_items=[url],
                dispatched_count=1,
                structured_content={
                    "contract_version": "ingest.url_pool.submit.v1",
                    "project_key": project_key,
                    "url": url,
                    "async_mode": async_mode,
                    "dispatch_result": _compact_json_value(dispatch_result, max_items=20, max_depth=5),
                },
            )

        task_id = str((dispatch_result or {}).get("task_id") or "").strip() if isinstance(dispatch_result, dict) else ""
        submission = {
            "idempotency_key": idempotency_key,
            "project_key": project_key,
            "url": url,
            "task_id": task_id,
            "query_terms": query_terms,
            "strict_mode": strict_mode,
            "async_mode": async_mode,
            "source_name": source_name,
            "metadata": metadata,
            "candidate_review_key": candidate_review_key,
            "dispatch_result": _compact_json_value(dispatch_result, max_items=20, max_depth=5),
            "submitted_at": _utcnow_iso(),
            "source_call_id": tool_call.call_id,
        }
        submissions = [item for item in submissions if str(item.get("idempotency_key") or "") != idempotency_key]
        submissions.append(submission)
        updated_content = {
            **existing_content,
            "contract_version": "ingest.url_pool.submit.v1",
            "project_key": project_key,
            "updated_at": _utcnow_iso(),
            "submissions": submissions[-100:],
            "counts": {
                "submitted": len(submissions),
                "async": sum(1 for item in submissions if bool(item.get("async_mode"))),
                "sync": sum(1 for item in submissions if not bool(item.get("async_mode"))),
            },
        }
        artifact = service.store.upsert_artifact(
            {
                "session_id": request.session_id,
                "name": artifact_name,
                "artifact_type": "url_pool_ingest_submission_state",
                "mime_type": "application/json",
                "content_text": json.dumps(updated_content, ensure_ascii=False, sort_keys=True, default=str),
                "content_json": updated_content,
                "metadata": {
                    "project_key": project_key,
                    "contract_version": "ingest.url_pool.submit.v1",
                    "auto_written_by": "agent_core",
                    "idempotency_key": idempotency_key,
                },
            }
        )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"Submitted URL-pool ingest for {url}. Project={project_key}. "
                f"async_mode={async_mode}; task_id={task_id or 'not returned'}."
            ),
            ui_summary=f"Submitted URL-pool ingest: {url}",
            structured_content={
                "contract_version": "ingest.url_pool.submit.v1",
                "project_key": project_key,
                "url": url,
                "async_mode": async_mode,
                "task_id": task_id,
                "dispatch_result": _compact_json_value(dispatch_result, max_items=20, max_depth=5),
                "submission": _compact_json_value(submission, max_items=20, max_depth=5),
                "artifact": _compact_json_value(artifact, max_items=16, max_depth=4),
                "replayed": False,
                "next_gate": "inspect_ingest_status_or_source_artifacts",
            },
            artifact_refs=(str(artifact.get("artifact_id") or artifact_name),),
        )

    return handler

def _ingest_url_pool_status_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="ingest.url_pool.status",
        title="Read URL-Pool Ingest Status",
        description_for_model=(
            "Read the status of a URL-pool submission from the current Agent session, recent ingest jobs, and already stored project documents/sources. "
            "Use this before replacing pending writing evidence with verified citations from an approved URL candidate."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "url": {"type": "string"},
                "task_id": {"type": "string"},
                "artifact_name": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=9000,
        project_service_id="ingest.url_pool.status",
        metadata={"contract_version": "ingest.url_pool.status.v1", "after_tool": "ingest.url_pool.submit"},
    )

def _ingest_url_pool_status_handler(
    service: AgentSessionService,
    searcher: Callable[..., dict[str, Any]],
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        artifact_name = str(tool_call.arguments.get("artifact_name") or "ingest.url_pool_submissions.json").strip() or "ingest.url_pool_submissions.json"
        limit = max(1, min(20, int(tool_call.arguments.get("limit") or 8)))
        explicit_url = str(tool_call.arguments.get("url") or "").strip()
        explicit_task_id = str(tool_call.arguments.get("task_id") or "").strip()

        artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        artifact_content = dict((artifact or {}).get("content_json") or {})
        submissions = [dict(item) for item in list(artifact_content.get("submissions") or []) if isinstance(item, dict)]
        if explicit_url:
            submissions = [item for item in submissions if str(item.get("url") or "").strip() == explicit_url] or submissions
        if explicit_task_id:
            submissions = [
                item
                for item in submissions
                if explicit_task_id in json.dumps(item, ensure_ascii=False, default=str)
            ] or submissions
        latest_submission = submissions[-1] if submissions else {}
        url = explicit_url or str(latest_submission.get("url") or "").strip()
        dispatch = dict(latest_submission.get("dispatch_result") or {}) if isinstance(latest_submission.get("dispatch_result"), dict) else {}
        task_id = explicit_task_id or str(dispatch.get("task_id") or latest_submission.get("task_id") or "").strip()
        task_event_artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == "ingest.url_pool_task_events.json"), None)
        task_event_content = dict((task_event_artifact or {}).get("content_json") or {})
        all_task_events = [dict(item) for item in list(task_event_content.get("events") or []) if isinstance(item, dict)]
        latest_submission_key = str(latest_submission.get("idempotency_key") or "").strip()
        task_events = [
            item
            for item in all_task_events
            if (
                (url and str(item.get("url") or "").strip() == url)
                or (task_id and str(item.get("task_id") or "").strip() == task_id)
                or (latest_submission_key and str(item.get("idempotency_key") or "").strip() == latest_submission_key)
            )
        ][-limit:]
        latest_task_event = task_events[-1] if task_events else {}
        latest_task_event_status = str(latest_task_event.get("status") or "").strip().lower()

        job_matches: list[dict[str, Any]] = []
        try:
            from app.services.job_logger import list_jobs

            needle_values = [item for item in (url, task_id) if item]
            for job in list_jobs(limit=max(20, limit * 4)):
                haystack = json.dumps(job, ensure_ascii=False, default=str)
                if any(needle in haystack for needle in needle_values):
                    job_matches.append(job)
        except Exception as exc:  # noqa: BLE001
            job_error = {"code": exc.__class__.__name__, "message": str(exc)}
        else:
            job_error = None

        stored_result: dict[str, Any] = {}
        if url:
            try:
                stored_result = searcher(project_key=project_key, query=url, limit=limit, datasets=["documents", "sources"])
            except Exception as exc:  # noqa: BLE001
                stored_result = {
                    "contract_version": "project.structured_data.search.v1",
                    "project_key": project_key,
                    "query": url,
                    "items": [],
                    "total_matches": 0,
                    "errors": [{"dataset": "documents|sources", "type": exc.__class__.__name__, "message": str(exc)}],
                }

        evidence_items = list(stored_result.get("items") or []) if isinstance(stored_result, dict) else []
        verified = bool(evidence_items)
        latest_job_status = str((job_matches[0] if job_matches else {}).get("status") or "").strip().lower()
        pending = not verified and latest_task_event_status not in {"failed", "canceled", "cancelled"} and (
            latest_task_event_status != "completed"
            and (bool(task_id) or latest_job_status in {"", "queued", "running", "pending", "started"})
        )
        if verified:
            next_gate = "verified_evidence_ready_for_writing"
            writing_guidance = "Verified project evidence is available; writing may replace pending language with cited evidence."
        elif latest_task_event_status == "failed":
            next_gate = "url_pool_ingest_failed_review_error_or_retry"
            writing_guidance = "The URL-pool ingest task failed; keep writing language pending and inspect the task error before retrying."
        elif latest_task_event_status in {"canceled", "cancelled"}:
            next_gate = "url_pool_ingest_canceled_resume_or_retry"
            writing_guidance = "The URL-pool ingest task was canceled; do not treat it as collected evidence. Use task.continue or retry collection if the user wants to resume."
        elif latest_task_event_status == "completed":
            next_gate = "ingest_completed_without_verified_project_record"
            writing_guidance = "The URL-pool task completed, but no stored project document/source matched the URL yet; keep writing evidence pending and inspect ingest output."
        else:
            next_gate = "wait_for_ingest_completion_or_retry_status"
            writing_guidance = "No stored document/source evidence found yet; keep writing language marked as pending or retry status later."
        payload = {
            "contract_version": "ingest.url_pool.status.v1",
            "project_key": project_key,
            "url": url,
            "task_id": task_id,
            "artifact_name": artifact_name,
            "submission": _compact_json_value(latest_submission, max_items=20, max_depth=5),
            "artifact_found": bool(artifact),
            "task_events": _compact_json_value(task_events, max_items=limit, max_depth=5),
            "latest_task_event": _compact_json_value(latest_task_event, max_items=12, max_depth=4),
            "task_event_artifact_found": bool(task_event_artifact),
            "job_matches": _compact_json_value(job_matches[:limit], max_items=limit, max_depth=4),
            "job_error": job_error,
            "stored_evidence": _compact_json_value(stored_result, max_items=20, max_depth=5),
            "verified": verified,
            "pending": pending,
            "evidence_items": _compact_json_value(evidence_items[:limit], max_items=limit, max_depth=4),
            "next_gate": next_gate,
            "writing_guidance": writing_guidance,
        }
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"URL-pool status for {url or task_id or 'latest submission'}: "
                f"verified={verified}, pending={pending}, job_matches={len(job_matches)}."
            ),
            structured_content=payload,
            artifact_refs=(str((artifact or {}).get("artifact_id") or artifact_name),) if artifact else (),
        )

    return handler

def _source_history_read_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="source.history.read",
        title="Read Source Candidate History",
        description_for_model=(
            "Read recent source-candidate decisions and URL-pool submissions from the current Agent session, "
            "optionally including recent sessions in the same project. Use this before continuing a long investigation, "
            "checking prior candidate decisions, or writing with previously approved/collected sources."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "include_recent_sessions": {"type": "boolean"},
                "session_limit": {"type": "integer", "minimum": 1, "maximum": 10},
                "item_limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=10000,
        project_service_id="source.history.read",
        metadata={"contract_version": "source.history.read.v1", "no_external_io": True, "no_project_write": True},
    )

def _source_history_read_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        include_recent_sessions = bool(tool_call.arguments.get("include_recent_sessions"))
        session_limit = max(1, min(10, int(tool_call.arguments.get("session_limit") or 5)))
        item_limit = max(1, min(50, int(tool_call.arguments.get("item_limit") or 20)))

        session_ids: list[str] = [request.session_id]
        session_meta_by_id: dict[str, dict[str, Any]] = {}
        try:
            current_session = service.get_session(request.session_id)
            session_meta_by_id[request.session_id] = current_session
        except Exception:
            current_session = {"session_id": request.session_id, "project_key": project_key}
            session_meta_by_id[request.session_id] = current_session

        if include_recent_sessions:
            for session in service.list_sessions(limit=max(session_limit * 3, session_limit)):
                sid = str(session.get("session_id") or "").strip()
                if not sid or sid in session_ids:
                    continue
                if str(session.get("project_key") or "").strip() != project_key:
                    continue
                session_ids.append(sid)
                session_meta_by_id[sid] = session
                if len(session_ids) >= session_limit:
                    break

        sessions: list[dict[str, Any]] = []
        totals = {"sessions": 0, "reviews": 0, "approved": 0, "deferred": 0, "rejected": 0, "submissions": 0, "task_events": 0}
        for sid in session_ids[:session_limit]:
            meta = session_meta_by_id.get(sid) or {"session_id": sid}
            try:
                artifacts = service.list_artifacts(sid)
            except Exception:
                artifacts = []
            reviews: list[dict[str, Any]] = []
            submissions: list[dict[str, Any]] = []
            task_events: list[dict[str, Any]] = []
            for artifact in artifacts:
                content = dict(artifact.get("content_json") or {}) if isinstance(artifact.get("content_json"), dict) else {}
                name = str(artifact.get("name") or "").strip()
                contract = str(content.get("contract_version") or "").strip()
                if name == "source.candidate_reviews.json" or contract == "source.candidate.review.v1":
                    reviews.extend([dict(item) for item in list(content.get("reviews") or []) if isinstance(item, dict)])
                if name == "ingest.url_pool_submissions.json" or contract == "ingest.url_pool.submit.v1":
                    submissions.extend([dict(item) for item in list(content.get("submissions") or []) if isinstance(item, dict)])
                if name == "ingest.url_pool_task_events.json" or contract == "ingest.url_pool.task_event.v1":
                    task_events.extend([dict(item) for item in list(content.get("events") or []) if isinstance(item, dict)])

            reviews = _sort_source_history_items(reviews, keys=("reviewed_at", "updated_at"))[-item_limit:]
            submissions = _sort_source_history_items(submissions, keys=("submitted_at", "updated_at"))[-item_limit:]
            task_events = _sort_source_history_items(task_events, keys=("recorded_at", "updated_at"))[-item_limit:]
            counts = {
                "reviews": len(reviews),
                "approved": sum(1 for item in reviews if str(item.get("decision") or "") == "approved"),
                "deferred": sum(1 for item in reviews if str(item.get("decision") or "") == "deferred"),
                "rejected": sum(1 for item in reviews if str(item.get("decision") or "") == "rejected"),
                "submissions": len(submissions),
                "task_events": len(task_events),
            }
            if counts["reviews"] or counts["submissions"] or counts["task_events"] or sid == request.session_id:
                sessions.append(
                    {
                        "session_id": sid,
                        "is_current_session": sid == request.session_id,
                        "goal": str(meta.get("goal") or ""),
                        "updated_at": str(meta.get("updated_at") or ""),
                        "counts": counts,
                        "reviews": _compact_json_value(reviews, max_items=item_limit, max_depth=5),
                        "submissions": _compact_json_value(submissions, max_items=item_limit, max_depth=5),
                        "task_events": _compact_json_value(task_events, max_items=item_limit, max_depth=5),
                    }
                )
                totals["sessions"] += 1
                for key in ("reviews", "approved", "deferred", "rejected", "submissions", "task_events"):
                    totals[key] += counts[key]

        next_gate = "resume_reviewed_sources_or_check_url_pool_status" if totals["reviews"] or totals["submissions"] else "run_source_discovery_or_search_first"
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"Read source history: sessions={totals['sessions']}, reviews={totals['reviews']}, "
                f"submissions={totals['submissions']}."
            ),
            structured_content={
                "contract_version": "source.history.read.v1",
                "project_key": project_key,
                "session_id": request.session_id,
                "include_recent_sessions": include_recent_sessions,
                "totals": totals,
                "sessions": _compact_json_value(sessions, max_items=session_limit, max_depth=6),
                "next_gate": next_gate,
                "guidance": (
                    "Use approved reviews and URL-pool submissions as prior context. Call ingest.url_pool.status before treating queued sources as verified writing evidence."
                    if totals["reviews"] or totals["submissions"]
                    else "No prior source history was found in the checked sessions; start with internal context, source.discovery.plan, and source.web.search when external material is needed."
                ),
            },
        )

    return handler

def _sort_source_history_items(items: list[dict[str, Any]], *, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: next((str(item.get(key) or "") for key in keys if str(item.get(key) or "").strip()), ""),
    )

def _agent_investigation_leads_append_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_investigation.leads.append",
        title="Append Investigation Leads",
        description_for_model=(
            "Append multi-round investigation state to the current agent session artifact trail. "
            "Use this after tracing leads across local data, graph nodes, source-library records, or source-discovery plans. "
            "It records clue nodes/edges, pending questions, followed leads, rejected leads, and citations without external I/O."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "artifact_name": {"type": "string"},
                "goal": {"type": "string"},
                "summary": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "clue_nodes": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "clue_edges": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "pending_questions": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]},
                },
                "followed_leads": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]},
                },
                "rejected_leads": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]},
                },
                "citations": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]},
                },
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="allow",
        concurrency="serial",
        timeout_seconds=10,
        result_budget=7000,
        project_service_id="agent_investigation.leads.append",
        metadata={"contract_version": "agent_investigation.leads.v1", "auto_allow_session_write": True},
    )

def _agent_investigation_leads_append_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        artifact_name = str(tool_call.arguments.get("artifact_name") or "investigation.leads.json").strip()
        if not artifact_name:
            artifact_name = "investigation.leads.json"
        existing_artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        existing_content = dict((existing_artifact or {}).get("content_json") or {})
        idempotency_key = str(tool_call.arguments.get("idempotency_key") or "").strip()
        replay_keys = [str(item or "") for item in list(existing_content.get("replay_keys") or []) if str(item or "").strip()]
        replayed = bool(idempotency_key and idempotency_key in replay_keys)

        sections = {
            "clue_nodes": _dedupe_artifact_records(existing_content.get("clue_nodes"), tool_call.arguments.get("clue_nodes")),
            "clue_edges": _dedupe_artifact_records(existing_content.get("clue_edges"), tool_call.arguments.get("clue_edges")),
            "pending_questions": _dedupe_artifact_records(existing_content.get("pending_questions"), tool_call.arguments.get("pending_questions")),
            "followed_leads": _dedupe_artifact_records(existing_content.get("followed_leads"), tool_call.arguments.get("followed_leads")),
            "rejected_leads": _dedupe_artifact_records(existing_content.get("rejected_leads"), tool_call.arguments.get("rejected_leads")),
            "citations": _dedupe_artifact_records(existing_content.get("citations"), tool_call.arguments.get("citations")),
        }
        if replayed:
            sections = {
                key: _normalize_artifact_records(existing_content.get(key))
                for key in sections
            }
        elif idempotency_key:
            replay_keys.append(idempotency_key)

        summary = str(tool_call.arguments.get("summary") or "").strip()
        goal = str(tool_call.arguments.get("goal") or existing_content.get("goal") or request.message or "").strip()
        updated_content = {
            **existing_content,
            "contract_version": "agent_investigation.leads.v1",
            "project_key": project_key,
            "goal": goal,
            "summary": summary or existing_content.get("summary") or "",
            "updated_at": _utcnow_iso(),
            "source_call_id": tool_call.call_id,
            "replay_keys": replay_keys[-50:],
            **sections,
        }
        artifact = service.store.upsert_artifact(
            {
                "session_id": request.session_id,
                "name": artifact_name,
                "artifact_type": "agent_investigation_state",
                "mime_type": "application/json",
                "content_text": json.dumps(updated_content, ensure_ascii=False, sort_keys=True, default=str),
                "content_json": updated_content,
                "metadata": {
                    "project_key": project_key,
                    "contract_version": "agent_investigation.leads.v1",
                    "auto_written_by": "agent_core",
                    "replayed": replayed,
                },
            }
        )
        counts = {key: len(value) for key, value in sections.items()}
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Recorded investigation state in {artifact_name}: {counts}.",
            structured_content={
                "contract_version": "agent_investigation.leads.v1",
                "project_key": project_key,
                "artifact": _compact_json_value(artifact, max_items=16, max_depth=4),
                "counts": counts,
                "replayed": replayed,
            },
            artifact_refs=(str(artifact.get("artifact_id") or artifact_name),),
        )

    return handler

def _agent_investigation_trace_read_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_investigation.trace.read",
        title="Read Investigation Trace",
        description_for_model=(
            "Read the current investigation state artifact and expand clue nodes/edges into a bounded multi-hop trace. "
            "Use this before follow-up investigation, evidence synthesis, or writing from previously collected leads."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "artifact_name": {
                    "type": "string",
                    "description": "Investigation artifact name. Defaults to investigation.leads.json.",
                },
                "focus_node_id": {
                    "type": "string",
                    "description": "Optional clue node id to expand from. If omitted, returns a compact whole-artifact trace.",
                },
                "max_hops": {"type": "integer", "minimum": 0, "maximum": 5, "default": 2},
                "max_items": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=7000,
        project_service_id="agent_investigation.trace.read",
        metadata={"contract_version": "agent_investigation.trace.v1"},
    )

def _agent_investigation_trace_read_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        artifact_name = str(tool_call.arguments.get("artifact_name") or "investigation.leads.json").strip()
        if not artifact_name:
            artifact_name = "investigation.leads.json"
        focus_node_id = str(tool_call.arguments.get("focus_node_id") or "").strip()
        max_hops = _bounded_int(tool_call.arguments.get("max_hops"), default=2, minimum=0, maximum=5)
        max_items = _bounded_int(tool_call.arguments.get("max_items"), default=30, minimum=1, maximum=100)

        artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        if artifact is None:
            payload = {
                "contract_version": "agent_investigation.trace.v1",
                "project_key": project_key,
                "artifact_name": artifact_name,
                "missing_artifact": True,
                "focus_node_id": focus_node_id or None,
                "max_hops": max_hops,
                "nodes": [],
                "edges": [],
                "followed_leads": [],
                "rejected_leads": [],
                "citations": [],
                "pending_questions": [],
                "counts": {"nodes": 0, "edges": 0, "pending_questions": 0, "followed_leads": 0, "citations": 0},
                "trace_summary": "No investigation artifact exists yet; start by appending leads.",
            }
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"No investigation artifact named {artifact_name} exists yet.",
                structured_content=payload,
            )

        content = dict(artifact.get("content_json") or {})
        payload = _build_investigation_trace_payload(
            project_key=project_key,
            artifact_name=artifact_name,
            artifact_content=content,
            focus_node_id=focus_node_id,
            max_hops=max_hops,
            max_items=max_items,
        )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"Read investigation trace from {artifact_name}: "
                f"{payload['counts']['nodes']} node(s), {payload['counts']['edges']} edge(s)."
            ),
            structured_content=payload,
            artifact_refs=(str(artifact.get("artifact_id") or artifact_name),),
        )

    return handler

def _writing_document_list_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="writing.document.list",
        title="List Writing Documents",
        description_for_model="List writing workbench documents for the current project. Use before reading or editing a draft when the target document is unclear.",
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=4000,
        project_service_id="writing.document.list",
    )

def _writing_document_list_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        limit = max(1, min(100, int(tool_call.arguments.get("limit") or 20)))
        try:
            with bind_project(project_key):
                documents = list_documents(project_key=project_key, limit=limit)
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to list writing documents: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        compact = [_compact_writing_document(item, include_body=False) for item in documents]
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Found {len(compact)} writing document(s).",
            structured_content={
                "contract_version": "writing.document.list.v1",
                "project_key": project_key,
                "documents": compact,
                "total_returned": len(compact),
            },
        )

    return handler

def _writing_document_read_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="writing.document.read",
        title="Read Writing Document",
        description_for_model=(
            "Read one writing workbench document, including version and etag. "
            "Use this before writing so insert tools can pass base_version/if_match."
        ),
        input_schema={
            "type": "object",
            "required": ["doc_id"],
            "properties": {
                "project_key": {"type": "string"},
                "doc_id": {"type": "integer", "minimum": 1},
                "max_chars": {"type": "integer", "minimum": 200, "maximum": 50000},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=8000,
        project_service_id="writing.document.read",
    )

def _writing_document_read_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        doc_id = _safe_int(tool_call.arguments.get("doc_id"))
        if not doc_id:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="doc_id is required to read a writing document.",
                error={"code": "missing_doc_id", "message": "doc_id is required"},
            )
        max_chars = max(200, min(50000, int(tool_call.arguments.get("max_chars") or 8000)))
        try:
            with bind_project(project_key):
                document = get_document(doc_id=doc_id, project_key=project_key)
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to read writing document {doc_id}: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        compact = _compact_writing_document(document, include_body=True, max_chars=max_chars)
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Read writing document {doc_id} version {compact.get('version')}.",
            structured_content={
                "contract_version": "writing.document.read.v1",
                "project_key": project_key,
                "document": compact,
            },
        )

    return handler

def _writing_document_section_read_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="writing.document.section.read",
        title="Read Writing Document Section",
        description_for_model=(
            "Read one section or line range from a writing workbench document. "
            "Use this when the user brings a selected passage into context or asks to edit from a specific position."
        ),
        input_schema={
            "type": "object",
            "required": ["doc_id"],
            "properties": {
                "project_key": {"type": "string"},
                "doc_id": {"type": "integer", "minimum": 1},
                "heading": {"type": "string"},
                "block_id": {"type": "string"},
                "line_start": {"type": "integer", "minimum": 1},
                "line_end": {"type": "integer", "minimum": 1},
                "max_chars": {"type": "integer", "minimum": 200, "maximum": 20000},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=7000,
        project_service_id="writing.document.section.read",
    )

def _writing_document_section_read_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        doc_id = _safe_int(tool_call.arguments.get("doc_id"))
        if not doc_id:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="doc_id is required to read a writing document section.",
                error={"code": "missing_doc_id", "message": "doc_id is required"},
            )
        try:
            with bind_project(project_key):
                document = get_document(doc_id=doc_id, project_key=project_key)
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to read writing document section {doc_id}: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        body = str(document.get("body_md") or "")
        max_chars = max(200, min(20000, int(tool_call.arguments.get("max_chars") or 5000)))
        section = _extract_writing_section(
            body,
            heading=str(tool_call.arguments.get("heading") or "").strip(),
            block_id=str(tool_call.arguments.get("block_id") or "").strip(),
            line_start=_safe_int(tool_call.arguments.get("line_start")),
            line_end=_safe_int(tool_call.arguments.get("line_end")),
            max_chars=max_chars,
        )
        compact_doc = _compact_writing_document(document, include_body=False)
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Read section from writing document {doc_id}: lines {section.get('line_start')}-{section.get('line_end')}.",
            structured_content={
                "contract_version": "writing.document.section.read.v1",
                "project_key": project_key,
                "document": compact_doc,
                "section": section,
            },
        )

    return handler

def _writing_document_create_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="writing.document.create",
        title="Create Writing Document",
        description_for_model=(
            "Create a formal writing workbench document for the current project. "
            "Use this when the user asks to establish/register a draft, turn an artifact/report into a writing document, "
            "or start a new canvas-backed document before later anchored edits."
        ),
        input_schema={
            "type": "object",
            "required": ["title"],
            "properties": {
                "project_key": {"type": "string"},
                "title": {"type": "string", "minLength": 1, "maxLength": 500},
                "body_md": {"type": "string", "description": "Initial markdown body for the document."},
                "content_md": {"type": "string", "description": "Alias for body_md when the model has already drafted markdown."},
                "dry_run": {"type": "boolean"},
                "source_refs": {"type": "array", "items": {"type": "string"}},
                "provenance": {"type": "object", "additionalProperties": True},
                "metadata_json": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="ask",
        concurrency="serial",
        timeout_seconds=15,
        result_budget=7000,
        project_service_id="writing.document.create",
        metadata={"contract_version": "writing.document.create.v1"},
    )

def _writing_document_create_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        title = str(tool_call.arguments.get("title") or "").strip()
        if not title:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="title is required to create a writing document.",
                error={"code": "missing_title", "message": "title is required"},
            )
        body_md = str(tool_call.arguments.get("body_md") or tool_call.arguments.get("content_md") or "")
        if len(body_md) > 50000:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="body_md is too large for one writing document create operation.",
                error={"code": "body_too_large", "message": "body_md must be <= 50000 characters"},
            )
        source_refs = _normalize_string_list(tool_call.arguments.get("source_refs"))
        provenance = dict(tool_call.arguments.get("provenance") or {})
        metadata_json = dict(tool_call.arguments.get("metadata_json") or {})
        metadata_json.update(
            {
                "created_by": "agent_core",
                "agent_core_call_id": tool_call.call_id,
                "source_refs": source_refs,
                "provenance": _compact_json_value(provenance, max_items=20, max_depth=4),
                "agent_document_contract": "writing.document.create.v1",
            }
        )
        if bool(tool_call.arguments.get("dry_run")):
            preview_document = {
                "id": None,
                "project_key": project_key,
                "title": title,
                "body_md": body_md,
                "status": "draft",
                "version": 1,
                "etag": None,
                "metadata_json": metadata_json,
            }
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"Prepared writing document create preview: {title}.",
                structured_content={
                    "contract_version": "writing.document.create.v1",
                    "project_key": project_key,
                    "dry_run": True,
                    "document": _compact_writing_document(preview_document, include_body=True),
                    "source_refs": source_refs,
                    "provenance": provenance,
                },
            )
        try:
            with bind_project(project_key):
                saved = create_document(
                    project_key=project_key,
                    title=title,
                    body_md=body_md,
                    updated_by_user_id="agent_core",
                    metadata_json=metadata_json,
                )
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to create writing document: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        doc_id = _safe_int(saved.get("id"))
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Created writing document {doc_id}: {saved.get('title') or title}.",
            ui_summary=f"Created writing document {doc_id}: {saved.get('title') or title}.",
            structured_content={
                "contract_version": "writing.document.create.v1",
                "project_key": project_key,
                "doc_id": doc_id,
                "document": _compact_writing_document(saved, include_body=False),
                "source_refs": source_refs,
                "provenance": provenance,
            },
        )

    return handler

def _writing_document_insert_paragraph_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="writing.document.insert_paragraph",
        title="Insert Paragraph Into Writing Document",
        description_for_model=(
            "Insert, prepend, append, or replace text in a writing workbench document. "
            "Use after reading the document. It mutates project writing state and must satisfy version-lock or explicit allow_latest boundaries. "
            "For existing documents, pass base_version/if_match from writing.document.read, or set allow_latest=true when the user explicitly wants to edit the latest server version. "
            "When no doc_id is available, provide title to create a new draft document after the write approval boundary."
        ),
        input_schema={
            "type": "object",
            "required": ["content_md"],
            "properties": {
                "project_key": {"type": "string"},
                "doc_id": {"type": "integer", "minimum": 1},
                "title": {"type": "string"},
                "content_md": {"type": "string"},
                "operation": {
                    "type": "string",
                    "enum": [
                        "append",
                        "prepend",
                        "after_heading",
                        "replace_text",
                        "replace_range",
                        "insert_at_offset",
                        "insert_after_text",
                        "insert_before_text",
                    ],
                    "default": "append",
                },
                "anchor_heading": {"type": "string"},
                "anchor_text": {"type": "string"},
                "range_start": {"type": "integer", "minimum": 0},
                "range_end": {"type": "integer", "minimum": 0},
                "cursor_offset": {"type": "integer", "minimum": 0},
                "selection_snapshot": {"type": "object", "additionalProperties": True},
                "base_version": {"type": "integer", "minimum": 1},
                "if_match": {"type": "string"},
                "allow_latest": {"type": "boolean"},
                "create_if_missing": {"type": "boolean"},
                "dry_run": {"type": "boolean"},
                "idempotency_key": {"type": "string"},
                "source_refs": {"type": "array", "items": {"type": "string"}},
                "provenance": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="ask",
        concurrency="serial",
        timeout_seconds=15,
        result_budget=7000,
        project_service_id="writing.document.insert_paragraph",
        metadata={"contract_version": "writing.document.insert_paragraph.v1"},
    )

def _writing_document_insert_paragraph_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        content_md = str(tool_call.arguments.get("content_md") or "").strip()
        if not content_md:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="content_md is required for writing document insertion.",
                error={"code": "missing_content", "message": "content_md is required"},
            )
        if len(content_md) > 20000:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="content_md is too large for one insert operation.",
                error={"code": "content_too_large", "message": "content_md must be <= 20000 characters"},
            )

        doc_id = _safe_int(tool_call.arguments.get("doc_id"))
        operation = str(tool_call.arguments.get("operation") or "append").strip() or "append"
        dry_run = bool(tool_call.arguments.get("dry_run"))
        allow_latest = bool(tool_call.arguments.get("allow_latest"))
        base_version = _safe_int(tool_call.arguments.get("base_version"))
        if_match = str(tool_call.arguments.get("if_match") or "").strip() or None
        create_if_missing = bool(tool_call.arguments.get("create_if_missing"))
        title = str(tool_call.arguments.get("title") or "").strip()
        if not doc_id and title:
            create_if_missing = True

        try:
            with bind_project(project_key):
                if doc_id:
                    current = get_document(doc_id=doc_id, project_key=project_key)
                elif create_if_missing:
                    current = {
                        "id": None,
                        "title": title or "Untitled",
                        "body_md": "",
                        "version": 1,
                        "etag": None,
                    }
                else:
                    return CoreToolResult(
                        call_id=tool_call.call_id,
                        tool_name=tool_call.tool_name,
                        status="failed",
                        model_summary="doc_id is required unless create_if_missing=true.",
                        error={"code": "missing_doc_id", "message": "doc_id is required unless create_if_missing=true"},
                    )

                old_body = str(current.get("body_md") or "")
                replayed_update = _find_replayed_agent_writing_update(
                    metadata=current.get("metadata_json"),
                    tool_call=tool_call,
                    current=current,
                    content_md=content_md,
                    operation=operation,
                )
                if replayed_update is not None:
                    return CoreToolResult(
                        call_id=tool_call.call_id,
                        tool_name=tool_call.tool_name,
                        status="completed",
                        model_summary=(
                            f"Writing document edit already applied for idempotency key "
                            f"{replayed_update.get('idempotency_key') or replayed_update.get('call_id')}; no duplicate paragraph inserted."
                        ),
                        ui_summary=f"Writing update already applied: {current.get('title') or doc_id or title}.",
                        structured_content={
                            "contract_version": "writing.document.insert_paragraph.v1",
                            "project_key": project_key,
                            "doc_id": doc_id or current.get("id"),
                            "document": _compact_writing_document(current, include_body=False),
                            "operation": operation,
                            "replayed": True,
                            "diff": {
                                "added_lines": 0,
                                "removed_lines": 0,
                                "old_line_count": len(old_body.splitlines()),
                                "new_line_count": len(old_body.splitlines()),
                                "diff_excerpt": "",
                                "diff_truncated": False,
                            },
                            "source_refs": _normalize_string_list(tool_call.arguments.get("source_refs")),
                            "provenance": dict(tool_call.arguments.get("provenance") or {}),
                            "agent_update": replayed_update,
                        },
                    )
                new_body = _apply_writing_body_operation(
                    old_body,
                    operation=operation,
                    content_md=content_md,
                    anchor_heading=str(tool_call.arguments.get("anchor_heading") or "").strip(),
                    anchor_text=str(tool_call.arguments.get("anchor_text") or "").strip(),
                    range_start=_safe_nonnegative_int(tool_call.arguments.get("range_start")),
                    range_end=_safe_nonnegative_int(tool_call.arguments.get("range_end")),
                    cursor_offset=_safe_nonnegative_int(tool_call.arguments.get("cursor_offset")),
                )
                if isinstance(new_body, Failure):
                    return _runtime_failure_result(tool_call, new_body)
                if len(new_body) > 50000:
                    return CoreToolResult(
                        call_id=tool_call.call_id,
                        tool_name=tool_call.tool_name,
                        status="failed",
                        model_summary="The updated writing document would exceed the 50000 character limit.",
                        error={"code": "document_too_large", "message": "updated document would exceed 50000 characters"},
                    )

                diff = _body_diff_summary(old_body, new_body)
                agent_update = _build_agent_writing_update(
                    tool_call=tool_call,
                    current=current,
                    new_body=new_body,
                    operation=operation,
                    content_md=content_md,
                    diff=diff,
                )
                if dry_run:
                    return CoreToolResult(
                        call_id=tool_call.call_id,
                        tool_name=tool_call.tool_name,
                        status="completed",
                        model_summary=f"Prepared writing document edit preview: +{diff['added_lines']} -{diff['removed_lines']} lines.",
                        structured_content={
                            "contract_version": "writing.document.insert_paragraph.v1",
                            "project_key": project_key,
                            "doc_id": doc_id,
                            "dry_run": True,
                            "operation": operation,
                            "diff": diff,
                            "source_refs": _normalize_string_list(tool_call.arguments.get("source_refs")),
                            "provenance": dict(tool_call.arguments.get("provenance") or {}),
                            "agent_update": agent_update,
                        },
                    )

                if doc_id:
                    current_version = int(current.get("version") or 1)
                    current_etag = str(current.get("etag") or "").strip() or None
                    if not base_version and not if_match and not allow_latest:
                        return CoreToolResult(
                            call_id=tool_call.call_id,
                            tool_name=tool_call.tool_name,
                            status="failed",
                            model_summary=(
                                "Writing mutation needs base_version/if_match from writing.document.read, "
                                "or allow_latest=true for an explicit latest-version edit."
                            ),
                            structured_content={
                                "contract_version": "writing.document.insert_paragraph.v1",
                                "project_key": project_key,
                                "doc_id": doc_id,
                                "current_version": current_version,
                                "current_etag": current_etag,
                                "retry_arguments": {
                                    **dict(tool_call.arguments or {}),
                                    "base_version": current_version,
                                    "if_match": current_etag,
                                },
                            },
                            error={"code": "version_lock_required", "message": "base_version or if_match required"},
                            retry_hint="Call writing.document.read first, then retry with base_version and if_match.",
                        )
                    saved = save_document_with_conflict(
                        doc_id=doc_id,
                        project_key=project_key,
                        body_md=new_body,
                        title=str(tool_call.arguments.get("title") or "").strip() or None,
                        base_version=base_version or (current_version if allow_latest else None),
                        if_match=if_match or (current_etag if allow_latest else None),
                        updated_by_user_id="agent_core",
                        metadata_json=_append_agent_writing_update(
                            current.get("metadata_json"),
                            agent_update,
                        ),
                    )
                else:
                    metadata_json = _append_agent_writing_update(
                        {
                            "created_by": "agent_core",
                            "agent_core_call_id": tool_call.call_id,
                            "source_refs": _normalize_string_list(tool_call.arguments.get("source_refs")),
                            "provenance": dict(tool_call.arguments.get("provenance") or {}),
                        },
                        agent_update,
                    )
                    saved = create_document(
                        project_key=project_key,
                        title=str(tool_call.arguments.get("title") or current.get("title") or "Untitled").strip() or "Untitled",
                        body_md=new_body,
                        updated_by_user_id="agent_core",
                        metadata_json=metadata_json,
                    )
                    doc_id = int(saved.get("id") or 0)
        except WritingVersionConflictError as exc:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Writing document version conflict: current version is {exc.current_version}.",
                structured_content={"conflict": exc.server_snapshot},
                error={"code": "writing_version_conflict", "message": str(exc), "current_version": exc.current_version},
                retry_hint="Read the document again and retry against the current version.",
            )
        except ValueError as exc:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=str(exc),
                error={"code": "invalid_writing_operation", "message": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to update writing document: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )

        document_title = str((saved or {}).get("title") or current.get("title") or tool_call.arguments.get("title") or "Untitled").strip()
        inserted_excerpt = " ".join(str(content_md or "").split())[:180]
        source_ref_count = len(_normalize_string_list(tool_call.arguments.get("source_refs")))
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"Updated writing document {doc_id} ({document_title}): operation={operation}, "
                f"+{diff['added_lines']} -{diff['removed_lines']} lines, source_refs={source_ref_count}. "
                f"Inserted excerpt: {inserted_excerpt}"
            ),
            ui_summary=f"Updated writing document {doc_id}: {document_title}.",
            structured_content={
                "contract_version": "writing.document.insert_paragraph.v1",
                "project_key": project_key,
                "doc_id": doc_id,
                "document": _compact_writing_document(saved, include_body=False),
                "operation": operation,
                "diff": diff,
                "source_refs": _normalize_string_list(tool_call.arguments.get("source_refs")),
                "provenance": dict(tool_call.arguments.get("provenance") or {}),
                "agent_update": agent_update,
            },
        )

    return handler

def _writing_document_citations_upsert_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="writing.document.citations.upsert",
        title="Attach Material Citations To Writing Document",
        description_for_model=(
            "Attach material-card citations to a writing workbench document. "
            "Use this after reading or creating a document when the user asks to add cited material cards, citation cards, "
            "reference cards, source cards, or selected evidence into the writing workbench citation tray. "
            "This writes the formal citation table used by the writing workbench; source_refs on prose edits are only provenance hints."
        ),
        input_schema={
            "type": "object",
            "required": ["doc_id"],
            "properties": {
                "project_key": {"type": "string"},
                "doc_id": {"type": "integer", "minimum": 1},
                "mode": {"type": "string", "enum": ["append", "replace"], "default": "append"},
                "dry_run": {"type": "boolean"},
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "card_id": {"type": "string"},
                            "source_doc_id": {"type": "integer", "minimum": 1},
                            "source_uri": {"type": "string"},
                            "source_title": {"type": "string"},
                            "quote_text": {"type": "string"},
                            "position_anchor": {"type": "string"},
                            "metadata_json": {"type": "object", "additionalProperties": True},
                        },
                        "additionalProperties": True,
                    },
                },
                "material_cards": {
                    "type": "array",
                    "items": {"type": "object", "additionalProperties": True},
                    "description": "Alias for citations when the model has material card previews with id/title/url/snippet fields.",
                },
                "source_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Fallback citation references such as record:94, artifact ids, document ids, or URLs.",
                },
                "position_anchor": {"type": "string"},
                "provenance": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="ask",
        concurrency="serial",
        timeout_seconds=15,
        result_budget=7000,
        project_service_id="writing.document.citations.upsert",
        metadata={"contract_version": "writing.document.citations.upsert.v1"},
    )

def _writing_document_citations_upsert_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        doc_id = _safe_int(tool_call.arguments.get("doc_id"))
        if not doc_id:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="doc_id is required to attach writing citations.",
                error={"code": "missing_doc_id", "message": "doc_id is required"},
            )
        incoming = _normalize_writing_citation_inputs(tool_call.arguments)
        if not incoming:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="At least one citation, material card, or source_ref is required.",
                error={"code": "missing_citations", "message": "citations, material_cards, or source_refs required"},
            )
        mode = str(tool_call.arguments.get("mode") or "append").strip().lower()
        if mode not in {"append", "replace"}:
            mode = "append"
        dry_run = bool(tool_call.arguments.get("dry_run"))
        try:
            with bind_project(project_key):
                existing = [] if mode == "replace" else list_citations(doc_id=doc_id, project_key=project_key)
                merged = _merge_writing_citations(existing, incoming)
                saved = merged if dry_run else upsert_citations(doc_id=doc_id, project_key=project_key, citations=merged)
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to attach writing citations: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )

        added_count = max(0, len(saved) - len(existing))
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Attached {added_count} writing citation(s) to document {doc_id}; total citations={len(saved)}.",
            ui_summary=f"Updated writing citations for document {doc_id}: {len(saved)} refs.",
            structured_content={
                "contract_version": "writing.document.citations.upsert.v1",
                "project_key": project_key,
                "doc_id": doc_id,
                "mode": mode,
                "dry_run": dry_run,
                "added_count": added_count,
                "total_count": len(saved),
                "citations": _compact_json_value(saved, max_items=20, max_depth=4),
            },
        )

    return handler

def _normalize_writing_citation_inputs(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    root_anchor = str(arguments.get("position_anchor") or "").strip() or None
    provenance = dict(arguments.get("provenance") or {})
    out: list[dict[str, Any]] = []
    for item in list(arguments.get("citations") or []) + list(arguments.get("material_cards") or []):
        if not isinstance(item, dict):
            continue
        card_id = str(item.get("card_id") or item.get("id") or item.get("source_id") or "").strip() or None
        source_uri = str(item.get("source_uri") or item.get("url") or item.get("uri") or "").strip() or None
        source_title = str(item.get("source_title") or item.get("title") or item.get("label") or card_id or source_uri or "").strip() or None
        quote_text = str(item.get("quote_text") or item.get("quote") or item.get("snippet") or item.get("summary") or "").strip() or None
        source_doc_id = _safe_int(item.get("source_doc_id") or item.get("doc_id"))
        position_anchor = str(item.get("position_anchor") or item.get("anchor") or root_anchor or "").strip() or None
        metadata_json = dict(item.get("metadata_json") or {})
        if provenance:
            metadata_json.setdefault("provenance", provenance)
        if not any([card_id, source_doc_id, source_uri, source_title, quote_text]):
            continue
        out.append(
            _prune_empty_citation(
                {
                    "card_id": card_id,
                    "source_doc_id": source_doc_id,
                    "source_uri": source_uri,
                    "source_title": source_title,
                    "quote_text": quote_text,
                    "position_anchor": position_anchor,
                    "metadata_json": metadata_json,
                }
            )
        )
    for ref in _normalize_string_list(arguments.get("source_refs")):
        ref_metadata: dict[str, Any] = {"source_ref": ref}
        if provenance:
            ref_metadata["provenance"] = provenance
        if ref.startswith(("http://", "https://")):
            citation = {
                "card_id": ref,
                "source_uri": ref,
                "source_title": ref,
                "position_anchor": root_anchor,
                "metadata_json": ref_metadata,
            }
        else:
            citation = {
                "card_id": ref,
                "source_title": ref,
                "position_anchor": root_anchor,
                "metadata_json": ref_metadata,
            }
        out.append(_prune_empty_citation(citation))
    return _merge_writing_citations([], out)

def _prune_empty_citation(citation: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in citation.items() if value not in (None, "", [], {})}

def _merge_writing_citations(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in list(existing or []) + list(incoming or []):
        if not isinstance(item, dict):
            continue
        normalized = _prune_empty_citation(
            {
                "source_doc_id": _safe_int(item.get("source_doc_id")),
                "source_uri": str(item.get("source_uri") or "").strip() or None,
                "source_title": str(item.get("source_title") or item.get("title") or "").strip() or None,
                "quote_text": str(item.get("quote_text") or item.get("quote") or "").strip() or None,
                "position_anchor": str(item.get("position_anchor") or "").strip() or None,
                "card_id": str(item.get("card_id") or item.get("id") or "").strip() or None,
                "metadata_json": dict(item.get("metadata_json") or {}) if isinstance(item.get("metadata_json"), dict) else {},
            }
        )
        identity = _writing_citation_identity(normalized)
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(normalized)
    return merged

def _writing_citation_identity(item: dict[str, Any]) -> tuple[str, str]:
    for key in ("card_id", "source_uri", "source_doc_id"):
        value = item.get(key)
        if value not in (None, ""):
            return key, str(value)
    fallback = "|".join(
        [
            str(item.get("source_title") or ""),
            str(item.get("quote_text") or ""),
            str(item.get("position_anchor") or ""),
        ]
    )
    return "content", _stable_hash(fallback)

def _compact_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task.get("task_id"),
        "parent_task_id": task.get("parent_task_id"),
        "subject": task.get("subject"),
        "description": task.get("description"),
        "task_type": task.get("task_type"),
        "phase": task.get("phase"),
        "status": task.get("status"),
        "priority": task.get("priority"),
        "blocked_by": list(task.get("blocked_by") or []),
        "blocks": list(task.get("blocks") or []),
        "read_set": list(task.get("read_set") or []),
        "write_set": list(task.get("write_set") or []),
        "artifact_targets": list((task.get("task_spec") or {}).get("artifact_targets") or []),
        "result_summary": task.get("result_summary"),
        "result_payload": _compact_json_value(task.get("result_payload"), max_items=8, max_depth=3),
        "summary_label": task.get("summary_label"),
        "last_activity": task.get("last_activity"),
        "metadata": _compact_json_value(task.get("metadata"), max_items=8, max_depth=3),
    }

def _normalize_long_task_stage(value: Any) -> str | Failure:
    stage = str(value or "").strip().lower()
    if stage not in _LONG_TASK_STAGE_ORDER:
        return agent_runtime_failures.fail(
            "long_task_stage_invalid",
            f"unsupported long-task stage: {stage or value}",
            {"value": value},
        )
    return stage

def _normalize_long_task_stage_status(value: Any) -> str | Failure:
    status = str(value or "in_progress").strip().lower() or "in_progress"
    if status not in _LONG_TASK_STAGE_STATUSES:
        return agent_runtime_failures.fail(
            "long_task_stage_status_invalid",
            f"unsupported long-task stage status: {status}",
            {"value": value},
        )
    return status

def _seed_long_task_state(
    *,
    session_id: str,
    project_key: str | None,
    task_kind: str,
    replay_keys: list[str],
) -> dict[str, Any]:
    now = _utcnow_iso()
    return {
        "contract_version": "agent_long_task.stage.v1",
        "session_id": session_id,
        "project_key": project_key,
        "task_kind": task_kind if task_kind in {"investigation", "writing", "mixed"} else "mixed",
        "created_at": now,
        "updated_at": now,
        "current_stage": "plan",
        "replay_keys": replay_keys[-80:],
        "stages": [
            {
                "stage": stage,
                "label": _LONG_TASK_STAGE_LABELS[stage],
                "status": "pending",
                "summary": "",
                "updated_at": None,
                "evidence_refs": [],
                "gap_list": [],
                "external_discovery_plan": [],
                "source_intake": [],
                "clue_refs": [],
                "draft_refs": [],
                "next_actions": [],
                "metadata": {},
            }
            for stage in _LONG_TASK_STAGE_ORDER
        ],
    }

def _normalize_long_task_state(
    content: dict[str, Any],
    *,
    session_id: str,
    project_key: str | None,
    task_kind: str,
) -> dict[str, Any]:
    seeded = _seed_long_task_state(
        session_id=session_id,
        project_key=str(content.get("project_key") or project_key or "").strip() or None,
        task_kind=str(content.get("task_kind") or task_kind or "mixed").strip().lower(),
        replay_keys=[str(item or "") for item in list(content.get("replay_keys") or []) if str(item or "").strip()],
    )
    existing_by_stage = {
        str(item.get("stage") or "").strip(): dict(item)
        for item in list(content.get("stages") or [])
        if isinstance(item, dict)
    }
    normalized_stages: list[dict[str, Any]] = []
    for seeded_stage in seeded["stages"]:
        stage_name = str(seeded_stage.get("stage") or "")
        merged = {**seeded_stage, **existing_by_stage.get(stage_name, {})}
        merged["stage"] = stage_name
        merged["label"] = _LONG_TASK_STAGE_LABELS.get(stage_name, stage_name)
        merged["status"] = str(merged.get("status") or "pending").strip().lower()
        if merged["status"] not in _LONG_TASK_STAGE_STATUSES:
            merged["status"] = "pending"
        for key in ("evidence_refs", "gap_list", "external_discovery_plan", "source_intake", "clue_refs", "draft_refs", "next_actions"):
            merged[key] = _normalize_artifact_records(merged.get(key))
        merged["metadata"] = dict(merged.get("metadata") or {}) if isinstance(merged.get("metadata"), dict) else {}
        normalized_stages.append(merged)
    seeded.update(
        {
            **content,
            "contract_version": "agent_long_task.stage.v1",
            "session_id": session_id,
            "project_key": str(content.get("project_key") or project_key or "").strip() or None,
            "task_kind": str(content.get("task_kind") or task_kind or "mixed").strip().lower() if str(content.get("task_kind") or task_kind or "mixed").strip().lower() in {"investigation", "writing", "mixed"} else "mixed",
            "stages": normalized_stages,
            "current_stage": _derive_long_task_current_stage(normalized_stages, preferred=str(content.get("current_stage") or "")),
        }
    )
    return seeded

def _update_long_task_state(
    *,
    existing_content: dict[str, Any],
    session_id: str,
    project_key: str | None,
    task_kind: str,
    task_id: str | None,
    tool_call: CoreToolCall,
    stage: str,
    stage_status: str,
    replay_keys: list[str],
) -> dict[str, Any]:
    state = _normalize_long_task_state(existing_content, session_id=session_id, project_key=project_key, task_kind=task_kind)
    now = _utcnow_iso()
    stages = list(state.get("stages") or [])
    stage_index = _LONG_TASK_STAGE_ORDER.index(stage)
    for index, item in enumerate(stages):
        if index < stage_index and str(item.get("status") or "pending") == "pending":
            item["status"] = "completed"
            item["summary"] = item.get("summary") or f"Completed before {stage}."
            item["updated_at"] = item.get("updated_at") or now
            item["completed_at"] = item.get("completed_at") or now
        if str(item.get("stage") or "") != stage:
            continue
        item["status"] = stage_status
        item["summary"] = str(tool_call.arguments.get("summary") or item.get("summary") or "").strip()
        item["updated_at"] = now
        item["task_id"] = task_id or item.get("task_id")
        item["source_call_id"] = tool_call.call_id
        if stage_status == "completed":
            item["completed_at"] = now
        for key in ("evidence_refs", "gap_list", "external_discovery_plan", "source_intake", "clue_refs", "draft_refs", "next_actions"):
            item[key] = _dedupe_artifact_records(item.get(key), tool_call.arguments.get(key))
        metadata = dict(item.get("metadata") or {})
        metadata.update(dict(tool_call.arguments.get("metadata") or {}))
        item["metadata"] = metadata
        break
    state.update(
        {
            "updated_at": now,
            "project_key": project_key,
            "task_kind": task_kind,
            "last_stage": stage,
            "last_stage_status": stage_status,
            "source_call_id": tool_call.call_id,
            "replay_keys": replay_keys[-80:],
            "stages": stages,
            "current_stage": _derive_long_task_current_stage(stages, preferred=stage if stage_status != "completed" else ""),
        }
    )
    return state

def _derive_long_task_current_stage(stages: list[dict[str, Any]], *, preferred: str = "") -> str:
    if preferred in _LONG_TASK_STAGE_ORDER:
        preferred_status = next((str(item.get("status") or "") for item in stages if str(item.get("stage") or "") == preferred), "")
        if preferred_status in {"pending", "in_progress", "blocked", "failed"}:
            return preferred
    for stage in _LONG_TASK_STAGE_ORDER:
        status = next((str(item.get("status") or "pending") for item in stages if str(item.get("stage") or "") == stage), "pending")
        if status != "completed":
            return stage
    return "done"

def _compact_long_task_state(state: dict[str, Any]) -> dict[str, Any]:
    stages = list(state.get("stages") or [])
    completed = [str(item.get("stage") or "") for item in stages if str(item.get("status") or "") == "completed"]
    blocked = [str(item.get("stage") or "") for item in stages if str(item.get("status") or "") in {"blocked", "failed"}]
    stage_summaries = []
    for item in stages:
        stage_summaries.append(
            {
                "stage": item.get("stage"),
                "label": item.get("label"),
                "status": item.get("status"),
                "summary": item.get("summary") or "",
                "task_id": item.get("task_id"),
                "updated_at": item.get("updated_at"),
                "counts": {
                    "evidence_refs": len(list(item.get("evidence_refs") or [])),
                    "gap_list": len(list(item.get("gap_list") or [])),
                    "external_discovery_plan": len(list(item.get("external_discovery_plan") or [])),
                    "source_intake": len(list(item.get("source_intake") or [])),
                    "clue_refs": len(list(item.get("clue_refs") or [])),
                    "draft_refs": len(list(item.get("draft_refs") or [])),
                    "next_actions": len(list(item.get("next_actions") or [])),
                },
                "evidence_refs": _compact_json_value(item.get("evidence_refs"), max_items=5, max_depth=3),
                "gap_list": _compact_json_value(item.get("gap_list"), max_items=5, max_depth=3),
                "external_discovery_plan": _compact_json_value(item.get("external_discovery_plan"), max_items=5, max_depth=3),
                "source_intake": _compact_json_value(item.get("source_intake"), max_items=5, max_depth=3),
                "clue_refs": _compact_json_value(item.get("clue_refs"), max_items=5, max_depth=3),
                "draft_refs": _compact_json_value(item.get("draft_refs"), max_items=5, max_depth=3),
                "next_actions": _compact_json_value(item.get("next_actions"), max_items=5, max_depth=3),
            }
        )
    return {
        "contract_version": "agent_long_task.stage.v1",
        "session_id": state.get("session_id"),
        "project_key": state.get("project_key"),
        "task_kind": state.get("task_kind"),
        "current_stage": state.get("current_stage"),
        "completed_stages": completed,
        "blocked_stages": blocked,
        "updated_at": state.get("updated_at"),
        "stage_summaries": stage_summaries,
        "next_actions": _collect_long_task_next_actions(stages),
    }

def _collect_long_task_next_actions(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in stages:
        for action in _normalize_artifact_records(item.get("next_actions")):
            action.setdefault("stage", item.get("stage"))
            out.append(action)
            if len(out) >= 12:
                return out
    return out

def _attach_long_task_state_to_task(
    *,
    service: AgentSessionService,
    session_id: str,
    task_id: str,
    artifact_name: str,
    state: dict[str, Any],
    stage: str,
    stage_status: str,
) -> None:
    try:
        task = service.store.get_task(session_id, task_id)
    except Exception:
        return
    metadata = dict(task.get("metadata") or {})
    metadata["long_task_state_artifact"] = artifact_name
    metadata["long_task_current_stage"] = state.get("current_stage")
    metadata["long_task_last_stage"] = stage
    result_payload = dict(task.get("result_payload") or {})
    result_payload["long_task_stage_state"] = _compact_long_task_state(state)
    recent_activities = list(task.get("recent_activities") or [])
    recent_activities.append(f"{stage}:{stage_status}")
    service.store.update_task(
        session_id,
        task_id,
        {
            "metadata": metadata,
            "result_payload": result_payload,
            "last_activity": f"long-task stage {stage} {stage_status}",
            "recent_activities": recent_activities[-8:],
        },
    )

def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = default
    return max(minimum, min(maximum, resolved))

def _normalize_artifact_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    raw_items = value if isinstance(value, list) else []
    for raw in raw_items:
        if isinstance(raw, dict):
            item = dict(raw)
        else:
            text = str(raw or "").strip()
            if not text:
                continue
            item = {"text": text}
        item.setdefault("record_id", _stable_hash(item))
        records.append(item)
    return records

def _dedupe_artifact_records(existing: Any, incoming: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*_normalize_artifact_records(existing), *_normalize_artifact_records(incoming)]:
        key = str(item.get("record_id") or item.get("id") or item.get("url") or item.get("title") or item.get("text") or _stable_hash(item))
        if key in seen:
            continue
        seen.add(key)
        normalized = dict(item)
        normalized["record_id"] = key
        out.append(normalized)
    return out

def _build_investigation_trace_payload(
    *,
    project_key: str,
    artifact_name: str,
    artifact_content: dict[str, Any],
    focus_node_id: str,
    max_hops: int,
    max_items: int,
) -> dict[str, Any]:
    nodes_by_id, node_order = _normalize_investigation_nodes(artifact_content.get("clue_nodes"))
    edges = _normalize_investigation_edges(artifact_content.get("clue_edges"), nodes_by_id=nodes_by_id, node_order=node_order)
    focus = str(focus_node_id or "").strip()
    if focus:
        selected_node_ids = _trace_investigation_node_ids(
            focus_node_id=focus,
            node_order=node_order,
            edges=edges,
            max_hops=max_hops,
            max_items=max_items,
        )
    else:
        selected_node_ids = node_order[:max_items]

    selected_node_set = set(selected_node_ids)
    selected_edges = [
        edge
        for edge in edges
        if str(edge.get("source") or "") in selected_node_set and str(edge.get("target") or "") in selected_node_set
    ][:max_items]
    selected_nodes = [nodes_by_id[node_id] for node_id in selected_node_ids if node_id in nodes_by_id][:max_items]
    pending_questions = _normalize_artifact_records(artifact_content.get("pending_questions"))[:max_items]
    followed_leads = _normalize_artifact_records(artifact_content.get("followed_leads"))[:max_items]
    rejected_leads = _normalize_artifact_records(artifact_content.get("rejected_leads"))[:max_items]
    citations = _normalize_artifact_records(artifact_content.get("citations"))[:max_items]
    focus_found = bool(not focus or focus in nodes_by_id)
    trace_summary = _summarize_investigation_trace(
        goal=str(artifact_content.get("goal") or "").strip(),
        focus_node_id=focus,
        focus_found=focus_found,
        node_count=len(selected_nodes),
        edge_count=len(selected_edges),
        pending_questions=pending_questions,
    )
    return {
        "contract_version": "agent_investigation.trace.v1",
        "project_key": project_key,
        "artifact_name": artifact_name,
        "artifact_contract_version": artifact_content.get("contract_version"),
        "missing_artifact": False,
        "focus_node_id": focus or None,
        "focus_found": focus_found,
        "max_hops": max_hops,
        "max_items": max_items,
        "goal": artifact_content.get("goal") or "",
        "summary": artifact_content.get("summary") or "",
        "nodes": _compact_json_value(selected_nodes, max_items=max_items, max_depth=4),
        "edges": _compact_json_value(selected_edges, max_items=max_items, max_depth=4),
        "followed_leads": _compact_json_value(followed_leads, max_items=max_items, max_depth=4),
        "rejected_leads": _compact_json_value(rejected_leads, max_items=max_items, max_depth=4),
        "citations": _compact_json_value(citations, max_items=max_items, max_depth=4),
        "pending_questions": _compact_json_value(pending_questions, max_items=max_items, max_depth=4),
        "available_node_ids": node_order[:max_items],
        "counts": {
            "nodes": len(selected_nodes),
            "edges": len(selected_edges),
            "all_nodes": len(node_order),
            "all_edges": len(edges),
            "pending_questions": len(pending_questions),
            "followed_leads": len(followed_leads),
            "rejected_leads": len(rejected_leads),
            "citations": len(citations),
        },
        "trace_summary": trace_summary,
        "next_steps": _derive_investigation_next_steps(pending_questions, followed_leads, citations, focus_found=focus_found),
    }

def _normalize_investigation_nodes(value: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    node_order: list[str] = []
    for index, raw in enumerate(_normalize_artifact_records(value), start=1):
        node_id = _first_text_value(raw, ("id", "node_id", "entity_id", "record_id", "url", "title", "label", "name", "text"))
        if not node_id:
            node_id = f"node-{index}"
        node = dict(raw)
        node["id"] = node_id
        node.setdefault("label", _first_text_value(node, ("label", "title", "name", "text")) or node_id)
        if node_id in nodes_by_id:
            nodes_by_id[node_id].update({key: value for key, value in node.items() if value not in (None, "", [])})
            continue
        nodes_by_id[node_id] = node
        node_order.append(node_id)
    return nodes_by_id, node_order

def _normalize_investigation_edges(
    value: Any,
    *,
    nodes_by_id: dict[str, dict[str, Any]],
    node_order: list[str],
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_normalize_artifact_records(value), start=1):
        source = _first_text_value(raw, ("source", "source_id", "from", "from_id", "start", "subject", "subject_id"))
        target = _first_text_value(raw, ("target", "target_id", "to", "to_id", "end", "object", "object_id"))
        if not source or not target:
            continue
        for node_id in (source, target):
            if node_id not in nodes_by_id:
                nodes_by_id[node_id] = {"id": node_id, "label": node_id, "inferred_from_edge": True}
                node_order.append(node_id)
        relation = _first_text_value(raw, ("relation", "label", "type", "predicate", "text")) or "related_to"
        edge_id = _first_text_value(raw, ("id", "edge_id", "record_id")) or f"{source}->{relation}->{target}"
        if edge_id in seen:
            continue
        seen.add(edge_id)
        edge = dict(raw)
        edge.update({"id": edge_id, "source": source, "target": target, "relation": relation})
        edges.append(edge)
    return edges

def _trace_investigation_node_ids(
    *,
    focus_node_id: str,
    node_order: list[str],
    edges: list[dict[str, Any]],
    max_hops: int,
    max_items: int,
) -> list[str]:
    if focus_node_id not in set(node_order):
        return []
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_order}
    for edge in edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if not source or not target:
            continue
        adjacency.setdefault(source, []).append(target)
        adjacency.setdefault(target, []).append(source)

    selected: list[str] = []
    visited: set[str] = {focus_node_id}
    queue: deque[tuple[str, int]] = deque([(focus_node_id, 0)])
    while queue and len(selected) < max_items:
        node_id, hops = queue.popleft()
        selected.append(node_id)
        if hops >= max_hops:
            continue
        for neighbor in adjacency.get(node_id, []):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            queue.append((neighbor, hops + 1))
    return selected

def _first_text_value(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, (dict, list)):
            continue
        text = str(value or "").strip()
        if text:
            return text
    return ""

def _summarize_investigation_trace(
    *,
    goal: str,
    focus_node_id: str,
    focus_found: bool,
    node_count: int,
    edge_count: int,
    pending_questions: list[dict[str, Any]],
) -> str:
    if focus_node_id and not focus_found:
        return f"Focus node {focus_node_id} was not found in the investigation artifact."
    scope = f"from focus node {focus_node_id}" if focus_node_id else "from the whole investigation artifact"
    question_text = _first_text_value(pending_questions[0], ("text", "question", "title")) if pending_questions else ""
    suffix = f" Next unresolved question: {question_text}" if question_text else ""
    prefix = f"Goal: {goal}. " if goal else ""
    return f"{prefix}Expanded {node_count} node(s) and {edge_count} edge(s) {scope}.{suffix}"

def _derive_investigation_next_steps(
    pending_questions: list[dict[str, Any]],
    followed_leads: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    *,
    focus_found: bool,
) -> list[str]:
    if not focus_found:
        return ["Pick one available_node_id as focus_node_id or append the missing clue node first."]
    steps: list[str] = []
    if pending_questions:
        steps.append("Use pending_questions to drive the next project-data search or external source-discovery plan.")
    if followed_leads and not citations:
        steps.append("Validate followed_leads with citations before writing derived claims.")
    if citations:
        steps.append("Use citations and selected trace nodes as source_refs/provenance when updating the writing workbench.")
    if not steps:
        steps.append("Append new clue nodes or edges after the next investigation pass.")
    return steps

def _compact_writing_document(document: dict[str, Any], *, include_body: bool, max_chars: int = 8000) -> dict[str, Any]:
    body = str(document.get("body_md") or "")
    compact = {
        "id": document.get("id"),
        "project_key": document.get("project_key"),
        "title": document.get("title"),
        "status": document.get("status"),
        "version": document.get("version"),
        "etag": document.get("etag"),
        "updated_at": document.get("updated_at"),
        "created_at": document.get("created_at"),
        "updated_by_user_id": document.get("updated_by_user_id"),
        "body_length": len(body),
        "block_anchors": _writing_block_anchors(body),
        "metadata_json": _compact_json_value(document.get("metadata_json"), max_items=8, max_depth=3),
    }
    if include_body:
        compact["body_md"] = body[:max_chars]
        compact["body_truncated"] = len(body) > max_chars
    return compact

def _writing_block_anchors(body_md: str, *, max_blocks: int = 80) -> list[dict[str, Any]]:
    lines = str(body_md or "").splitlines()
    blocks: list[dict[str, Any]] = []
    start_line: int | None = None
    buffer: list[str] = []

    def flush(end_line: int) -> None:
        nonlocal start_line, buffer
        text = "\n".join(buffer).strip()
        if not text or start_line is None:
            start_line = None
            buffer = []
            return
        first_line = buffer[0].strip()
        kind = "heading" if first_line.startswith("#") else "paragraph"
        heading_level = len(first_line) - len(first_line.lstrip("#")) if kind == "heading" else None
        blocks.append(
            {
                "block_id": f"block-{_stable_hash({'start': start_line, 'text': text})}",
                "kind": kind,
                "heading_level": heading_level,
                "line_start": start_line,
                "line_end": end_line,
                "preview": _first_nonempty_line(text),
                "content_hash": _stable_hash({"text": text}),
            }
        )
        start_line = None
        buffer = []

    for index, line in enumerate(lines, start=1):
        if line.strip():
            if start_line is None:
                start_line = index
            buffer.append(line)
            continue
        flush(index - 1)
        if len(blocks) >= max_blocks:
            return blocks[:max_blocks]
    flush(len(lines))
    return blocks[:max_blocks]

def _extract_writing_section(
    body_md: str,
    *,
    heading: str = "",
    block_id: str = "",
    line_start: int | None = None,
    line_end: int | None = None,
    max_chars: int = 5000,
) -> dict[str, Any]:
    lines = str(body_md or "").splitlines()
    anchors = _writing_block_anchors(body_md, max_blocks=500)
    selected_start = line_start if line_start and line_start > 0 else None
    selected_end = line_end if line_end and line_end > 0 else None
    if block_id:
        anchor = next((item for item in anchors if str(item.get("block_id") or "") == block_id), None)
        if anchor:
            selected_start = int(anchor.get("line_start") or 1)
            selected_end = int(anchor.get("line_end") or selected_start)
    if heading and selected_start is None:
        lowered = heading.lower()
        heading_anchor = next(
            (
                item
                for item in anchors
                if item.get("kind") == "heading" and lowered in str(item.get("preview") or "").lower()
            ),
            None,
        )
        if heading_anchor:
            selected_start = int(heading_anchor.get("line_start") or 1)
            selected_end = len(lines)
            heading_level = int(heading_anchor.get("heading_level") or 1)
            for candidate in anchors:
                candidate_start = int(candidate.get("line_start") or 0)
                candidate_level = int(candidate.get("heading_level") or 0)
                if candidate_start > selected_start and candidate.get("kind") == "heading" and candidate_level <= heading_level:
                    selected_end = max(selected_start, candidate_start - 1)
                    break
    if selected_start is None:
        selected_start = 1
    if selected_end is None:
        selected_end = min(len(lines), selected_start + 80)
    selected_start = max(1, min(selected_start, max(1, len(lines) or 1)))
    selected_end = max(selected_start, min(selected_end, max(1, len(lines) or 1)))
    text = "\n".join(lines[selected_start - 1 : selected_end])
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return {
        "heading": heading or None,
        "block_id": block_id or None,
        "line_start": selected_start,
        "line_end": selected_end,
        "content_md": text,
        "content_truncated": truncated,
        "body_line_count": len(lines),
    }

def _first_nonempty_line(value: str, *, max_chars: int = 240) -> str:
    for line in str(value or "").splitlines():
        normalized = line.strip()
        if normalized:
            return normalized[:max_chars]
    return str(value or "").strip()[:max_chars]

def _find_anchor_line(body_md: str, content_md: str) -> int | None:
    body = str(body_md or "")
    content = str(content_md or "").strip()
    candidates = [content, _first_nonempty_line(content)]
    for candidate in candidates:
        if not candidate:
            continue
        offset = body.find(candidate)
        if offset >= 0:
            return body[:offset].count("\n") + 1
    return None

def _build_agent_writing_update(
    *,
    tool_call: CoreToolCall,
    current: dict[str, Any],
    new_body: str,
    operation: str,
    content_md: str,
    diff: dict[str, Any],
) -> dict[str, Any]:
    old_version = _safe_int(current.get("version"))
    old_body = str(current.get("body_md") or "")
    selection_snapshot = _normalize_selection_snapshot(tool_call.arguments.get("selection_snapshot"))
    selection_text = str(selection_snapshot.get("selected_text") or selection_snapshot.get("text") or "").strip()
    explicit_anchor_text = str(tool_call.arguments.get("anchor_text") or "").strip()
    anchor_text = selection_text or explicit_anchor_text or _first_nonempty_line(content_md)
    content_hash = _stable_hash({"content_md": content_md})
    idempotency_key = _agent_writing_idempotency_key(tool_call=tool_call, current=current, content_md=content_md, operation=operation)
    anchor_id = f"agent-{_stable_hash({'idempotency_key': idempotency_key, 'content_hash': content_hash})}"
    inserted_text = str(content_md or "").strip()
    replaced_text = _extract_replaced_writing_text(
        old_body,
        operation=operation,
        anchor_text=explicit_anchor_text or selection_text,
        range_start=_safe_nonnegative_int(tool_call.arguments.get("range_start")),
        range_end=_safe_nonnegative_int(tool_call.arguments.get("range_end")),
    )
    provenance = dict(tool_call.arguments.get("provenance") or {})
    if selection_snapshot:
        provenance.setdefault("selection_snapshot", selection_snapshot)
    return {
        "id": anchor_id,
        "anchor_id": anchor_id,
        "call_id": tool_call.call_id,
        "idempotency_key": idempotency_key,
        "tool_name": tool_call.tool_name,
        "actor": "agent_core",
        "operation": operation,
        "created_at": _utcnow_iso(),
        "doc_id": current.get("id"),
        "title": current.get("title"),
        "old_version": old_version,
        "new_version": 1 if current.get("id") is None else ((old_version + 1) if old_version else None),
        "content_hash": content_hash,
        "inserted_text": inserted_text[:2000],
        "inserted_text_truncated": len(inserted_text) > 2000,
        "replaced_text": replaced_text[:2000],
        "replaced_text_truncated": len(replaced_text) > 2000,
        "summary": f"{operation} via AgentCore: +{diff.get('added_lines')} -{diff.get('removed_lines')} lines",
        "diff": _compact_json_value(diff, max_items=8, max_depth=3, max_string=1200),
        "source_refs": _normalize_string_list(tool_call.arguments.get("source_refs")),
        "provenance": _compact_json_value(provenance, max_items=20, max_depth=4),
        "locator": {
            "anchor_id": anchor_id,
            "anchor_text": anchor_text,
            "anchor_heading": str(tool_call.arguments.get("anchor_heading") or "").strip() or None,
            "anchor_line": _find_anchor_line(new_body, content_md),
            "range_start": _safe_nonnegative_int(tool_call.arguments.get("range_start")),
            "range_end": _safe_nonnegative_int(tool_call.arguments.get("range_end")),
            "cursor_offset": _safe_nonnegative_int(tool_call.arguments.get("cursor_offset")),
            "selection_snapshot": selection_snapshot or None,
            "content_hash": content_hash,
        },
    }

def _agent_writing_idempotency_key(
    *,
    tool_call: CoreToolCall,
    current: dict[str, Any],
    content_md: str,
    operation: str,
) -> str:
    explicit = str(tool_call.arguments.get("idempotency_key") or "").strip()
    provenance = dict(tool_call.arguments.get("provenance") or {})
    explicit = explicit or str(provenance.get("idempotency_key") or "").strip()
    if explicit:
        return explicit[:240]
    selection_snapshot = _normalize_selection_snapshot(tool_call.arguments.get("selection_snapshot"))
    return _stable_hash(
        {
            "session_anchor": provenance.get("session_id") or provenance.get("message_id"),
            "doc_id": current.get("id") or tool_call.arguments.get("doc_id") or tool_call.arguments.get("title"),
            "operation": operation,
            "anchor_heading": str(tool_call.arguments.get("anchor_heading") or "").strip(),
            "anchor_text": str(tool_call.arguments.get("anchor_text") or "").strip(),
            "range_start": _safe_nonnegative_int(tool_call.arguments.get("range_start")),
            "range_end": _safe_nonnegative_int(tool_call.arguments.get("range_end")),
            "cursor_offset": _safe_nonnegative_int(tool_call.arguments.get("cursor_offset")),
            "selection": selection_snapshot,
            "content_hash": _stable_hash({"content_md": content_md}),
        }
    )

def _find_replayed_agent_writing_update(
    *,
    metadata: Any,
    tool_call: CoreToolCall,
    current: dict[str, Any],
    content_md: str,
    operation: str,
) -> dict[str, Any] | None:
    if not isinstance(metadata, dict):
        return None
    idempotency_key = _agent_writing_idempotency_key(tool_call=tool_call, current=current, content_md=content_md, operation=operation)
    for item in reversed([dict(entry) for entry in list(metadata.get("agent_updates") or []) if isinstance(entry, dict)]):
        if str(item.get("call_id") or "") == tool_call.call_id:
            return item
        if idempotency_key and str(item.get("idempotency_key") or "") == idempotency_key:
            return item
    return None

def _extract_replaced_writing_text(
    body_md: str,
    *,
    operation: str,
    anchor_text: str,
    range_start: int | None,
    range_end: int | None,
) -> str:
    body = str(body_md or "")
    normalized_operation = str(operation or "").strip()
    if normalized_operation == "replace_range" and range_start is not None and range_end is not None:
        if 0 <= range_start <= range_end <= len(body):
            return body[range_start:range_end]
        return ""
    if normalized_operation == "replace_text" and anchor_text:
        index = body.find(anchor_text)
        if index >= 0:
            return body[index : index + len(anchor_text)]
    return ""

def _append_agent_writing_update(metadata: Any, update: dict[str, Any], *, max_items: int = 30) -> dict[str, Any]:
    next_metadata = dict(metadata or {}) if isinstance(metadata, dict) else {}
    existing = [
        dict(item)
        for item in list(next_metadata.get("agent_updates") or [])
        if isinstance(item, dict)
    ]
    next_updates = [*existing, dict(update)][-max_items:]
    next_metadata["agent_updates"] = next_updates
    next_metadata["last_agent_update"] = dict(update)
    next_metadata["agent_update_count"] = len(next_updates)
    return next_metadata

def _apply_writing_body_operation(
    body_md: str,
    *,
    operation: str,
    content_md: str,
    anchor_heading: str,
    anchor_text: str,
    range_start: int | None = None,
    range_end: int | None = None,
    cursor_offset: int | None = None,
) -> str | Failure:
    operation = str(operation or "append").strip()
    content = str(content_md or "").strip()
    body = str(body_md or "")
    if operation == "append":
        return _join_markdown_blocks(body, content)
    if operation == "prepend":
        return _join_markdown_blocks(content, body)
    if operation == "after_heading":
        if not anchor_heading:
            return agent_runtime_failures.fail(
                "writing_anchor_required",
                "anchor_heading is required for after_heading",
                {"operation": operation, "anchor": "heading"},
            )
        lines = body.splitlines()
        for index, line in enumerate(lines):
            if _heading_matches(line, anchor_heading):
                insert_at = index + 1
                while insert_at < len(lines) and not lines[insert_at].strip():
                    insert_at += 1
                updated = lines[:insert_at] + ["", content, ""] + lines[insert_at:]
                return "\n".join(updated).strip() + "\n"
        return agent_runtime_failures.fail(
            "writing_anchor_not_found",
            f"anchor heading not found: {anchor_heading}",
            {"operation": operation, "anchor": "heading", "value": anchor_heading},
        )
    if operation == "replace_text":
        if not anchor_text:
            return agent_runtime_failures.fail(
                "writing_anchor_required",
                "anchor_text is required for replace_text",
                {"operation": operation, "anchor": "text"},
            )
        if anchor_text not in body:
            return agent_runtime_failures.fail(
                "writing_anchor_not_found",
                "anchor_text was not found in the document",
                {"operation": operation, "anchor": "text"},
            )
        return body.replace(anchor_text, content, 1)
    if operation == "replace_range":
        if range_start is None or range_end is None:
            return agent_runtime_failures.fail(
                "writing_range_invalid",
                "range_start and range_end are required for replace_range",
                {"operation": operation},
            )
        range_failure = _validate_body_range(body, range_start, range_end)
        if isinstance(range_failure, Failure):
            return range_failure
        return _splice_markdown_range(body, range_start, range_end, content)
    if operation == "insert_at_offset":
        if cursor_offset is None:
            return agent_runtime_failures.fail(
                "writing_cursor_offset_required",
                "cursor_offset is required for insert_at_offset",
                {"operation": operation},
            )
        range_failure = _validate_body_range(body, cursor_offset, cursor_offset)
        if isinstance(range_failure, Failure):
            return range_failure
        return _splice_markdown_range(body, cursor_offset, cursor_offset, content)
    if operation == "insert_after_text":
        if not anchor_text:
            return agent_runtime_failures.fail(
                "writing_anchor_required",
                "anchor_text is required for insert_after_text",
                {"operation": operation, "anchor": "text"},
            )
        index = body.find(anchor_text)
        if index < 0:
            return agent_runtime_failures.fail(
                "writing_anchor_not_found",
                "anchor_text was not found in the document",
                {"operation": operation, "anchor": "text"},
            )
        insert_at = index + len(anchor_text)
        return _join_markdown_blocks(body[:insert_at], _join_markdown_blocks(content, body[insert_at:]))
    if operation == "insert_before_text":
        if not anchor_text:
            return agent_runtime_failures.fail(
                "writing_anchor_required",
                "anchor_text is required for insert_before_text",
                {"operation": operation, "anchor": "text"},
            )
        index = body.find(anchor_text)
        if index < 0:
            return agent_runtime_failures.fail(
                "writing_anchor_not_found",
                "anchor_text was not found in the document",
                {"operation": operation, "anchor": "text"},
            )
        return _join_markdown_blocks(_join_markdown_blocks(body[:index], content), body[index:])
    return agent_runtime_failures.fail(
        "writing_operation_unsupported",
        f"unsupported writing operation: {operation}",
        {"operation": operation},
    )

def _validate_body_range(body: str, start: int, end: int) -> Failure | None:
    if start < 0 or end < 0:
        return agent_runtime_failures.fail(
            "writing_range_invalid",
            "range offsets must be >= 0",
            {"start": start, "end": end},
        )
    if start > end:
        return agent_runtime_failures.fail(
            "writing_range_invalid",
            "range_start must be <= range_end",
            {"start": start, "end": end},
        )
    body_len = len(str(body or ""))
    if end > body_len:
        return agent_runtime_failures.fail(
            "writing_range_invalid",
            "range_end is outside the document",
            {"start": start, "end": end, "body_length": body_len},
        )
    return None

def _splice_markdown_range(body: str, start: int, end: int, content: str) -> str:
    raw_body = str(body or "")
    inserted = str(content or "").strip()
    before = raw_body[:start]
    after = raw_body[end:]
    if not before:
        return _join_markdown_blocks(inserted, after)
    if not after:
        return _join_markdown_blocks(before, inserted)
    return _join_markdown_blocks(_join_markdown_blocks(before, inserted), after)

def _normalize_selection_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("text", "selected_text", "start", "end", "line", "active_heading", "before", "after"):
        if key not in value:
            continue
        item = value.get(key)
        if isinstance(item, str):
            item = item[:1400]
        out[key] = item
    return out

def _join_markdown_blocks(first: str, second: str) -> str:
    left = str(first or "").strip()
    right = str(second or "").strip()
    if not left:
        return f"{right}\n" if right else ""
    if not right:
        return f"{left}\n"
    return f"{left}\n\n{right}\n"

def _heading_matches(line: str, anchor_heading: str) -> bool:
    left = str(line or "").strip().lstrip("#").strip().lower()
    right = str(anchor_heading or "").strip().lstrip("#").strip().lower()
    return bool(left and right and left == right)

def _body_diff_summary(old_body: str, new_body: str) -> dict[str, Any]:
    old_lines = str(old_body or "").splitlines()
    new_lines = str(new_body or "").splitlines()
    diff_lines = list(difflib.unified_diff(old_lines, new_lines, fromfile="before.md", tofile="after.md", lineterm="", n=3))
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    return {
        "added_lines": added,
        "removed_lines": removed,
        "old_line_count": len(old_lines),
        "new_line_count": len(new_lines),
        "diff_excerpt": "\n".join(diff_lines[:120]),
        "diff_truncated": len(diff_lines) > 120,
    }

def _run_agent_batch_submit_tool(
    *,
    tool_call: CoreToolCall,
    request: AgentCoreRequest,
) -> CoreToolResult:
    project_key = _resolve_project_key(tool_call, request)
    if not project_key:
        return _missing_project_result(tool_call)
    idempotency_key = str(tool_call.arguments.get("idempotency_key") or "").strip() or None

    jobs = _agent_batch_structured_jobs(tool_call.arguments)
    if not jobs:
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="failed",
            model_summary="agent_batch.submit requires structured jobs.",
            error={"code": "missing_agent_batch_work", "message": "jobs are required"},
        )

    try:
        from app.api.agent_batch import AgentBatchItemSubmit, AgentBatchSubmitBatch, AgentBatchSubmitRequest, submit_agent_batch_job

        payload = AgentBatchSubmitRequest(
            project_key=project_key,
            batch=AgentBatchSubmitBatch(jobs=[AgentBatchItemSubmit(**dict(item or {})) for item in jobs]),
            idempotency_key=idempotency_key,
            priority=tool_call.arguments.get("priority"),
            rule_set_id=tool_call.arguments.get("rule_set_id"),
            rule_set=dict(tool_call.arguments.get("rule_set") or {}),
        )
        response = submit_agent_batch_job(payload)
    except Exception as exc:  # noqa: BLE001
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="failed",
            model_summary=f"agent_batch structured submit failed: {exc}",
            error={"code": exc.__class__.__name__, "message": str(exc)},
        )

    data = dict(response.get("data") or {}) if isinstance(response, dict) else {}
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="completed",
        model_summary=f"Submitted {len(jobs)} agent_batch job item(s).",
        ui_summary=f"Submitted agent_batch job {data.get('job_id') or ''}".strip(),
        structured_content={
            "contract_version": "agent_batch.submit.v1",
            "mode": "structured_jobs",
            "project_key": project_key,
            "job_id": data.get("job_id"),
            "status": data.get("status"),
            "accepted_count": data.get("accepted_count"),
            "rejected_count": data.get("rejected_count"),
            "result": _compact_json_value(data, max_items=30, max_depth=5),
        },
    )

def _agent_batch_structured_jobs(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    raw_jobs = arguments.get("jobs")
    if raw_jobs is None and isinstance(arguments.get("batch"), dict):
        raw_jobs = dict(arguments.get("batch") or {}).get("jobs")
    return [dict(item or {}) for item in list(raw_jobs or []) if isinstance(item, dict)]



def _workflow_graph_run_handler(
    service: AgentSessionService,
    tool_call: CoreToolCall,
            tool_spec: CoreToolSpec,
            request: AgentCoreRequest,
            emit: Callable[[CoreEvent], None],
        ) -> CoreToolResult:
            project_key = _resolve_project_key(tool_call, request)
            graph_id = str(tool_call.arguments.get("graph_id") or "").strip()
            inputs = tool_call.arguments.get("inputs")
            if inputs is None:
                inputs = tool_call.arguments.get("input")
            if not project_key:
                return _missing_project_result(tool_call)
            if not graph_id:
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary="graph_id is required for workflow_graph.run.",
                    error={"code": "missing_graph_id", "message": "graph_id is required"},
                )
            if not isinstance(inputs, dict):
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary="inputs must be an object for workflow_graph.run.",
                    error={"code": "invalid_inputs", "message": "inputs must be an object"},
                )
            if _session_abort_requested(service=service, session_id=request.session_id):
                return _abort_requested_result(
                    service=service,
                    request=request,
                    tool_call=tool_call,
                    emit=emit,
                    skipped_items=[graph_id],
                    dispatched_count=0,
                )
            invoked = invoke_skill(
                skill_id="workflow_graph.run",
                payload={"graph_id": graph_id, "input": dict(inputs), "project_key": project_key},
                context={
                    "actor_role": "business_capability_wrapper",
                    "permissions": ["workflow_graph.run"],
                    "agent_session_id": request.session_id,
                    "agent_task_id": str((request.context or {}).get("root_task_id") or "").strip() or None,
                    "approval_granted": True,
                    "consumer": "agent_core.workflow_graph.run",
                    "trace_id": tool_call.call_id,
                },
            )
            result = invoked.get("result") if isinstance(invoked, dict) else invoked
            run_id = str((result or {}).get("run_id") or "").strip() if isinstance(result, dict) else ""
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"Started workflow graph run {run_id or graph_id}.",
                ui_summary=f"Started workflow graph: {graph_id}",
                structured_content={
                    "contract_version": "workflow_graph.run.agent_core.v1",
                    "project_key": project_key,
                    "graph_id": graph_id,
                    "result": _compact_json_value(result, max_items=30, max_depth=5),
                    "skill_meta": {
                        "owner": invoked.get("owner") if isinstance(invoked, dict) else None,
                        "execution_profile": invoked.get("execution_profile") if isinstance(invoked, dict) else None,
                    },
                },
            )

def _report_generate_handler(
    service: AgentSessionService,
    capability_id: str,
    tool_call: CoreToolCall,
            tool_spec: CoreToolSpec,
            request: AgentCoreRequest,
            emit: Callable[[CoreEvent], None],
        ) -> CoreToolResult:
            project_key = _resolve_project_key(tool_call, request)
            topic = str(tool_call.arguments.get("topic") or request.message or "").strip()
            output_path = str(tool_call.arguments.get("output_path") or "").strip()
            if not topic:
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary="topic is required for report.generate.",
                    error={"code": "missing_topic", "message": "topic is required"},
                )
            if not output_path:
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary="output_path is required for report.generate.",
                    error={"code": "missing_output_path", "message": "output_path is required"},
                )
            if _session_abort_requested(service=service, session_id=request.session_id):
                return _abort_requested_result(
                    service=service,
                    request=request,
                    tool_call=tool_call,
                    emit=emit,
                    skipped_items=[output_path],
                    dispatched_count=0,
                )
            raw_sources = tool_call.arguments.get("sources")
            sources = [dict(item or {}) for item in list(raw_sources or []) if isinstance(item, dict)]
            if not sources:
                sources = [
                    {
                        "id": "S1",
                        "title": "Current agent session context",
                        "url": f"agent-session://{request.session_id}",
                        "publisher": "agent_session",
                        "evidence": request.message,
                    }
                ]
            section_titles = [str(item) for item in list(tool_call.arguments.get("section_titles") or []) if str(item or "").strip()]
            try:
                from app.services.llm_report_generator import build_structured_report, evaluate_report_gate, render_markdown

                report = build_structured_report(topic=topic[:200], sources=sources, section_titles=section_titles or None)
                markdown = render_markdown(report)
                gate = evaluate_report_gate(report)
                artifact = service.store.upsert_artifact(
                    {
                        "session_id": request.session_id,
                        "task_id": str((request.context or {}).get("root_task_id") or "").strip() or None,
                        "artifact_type": "report.generate.markdown",
                        "name": output_path,
                        "mime_type": "text/markdown",
                        "content_text": markdown,
                        "content_json": {"report": report.to_dict(), "quality_gate": gate},
                        "metadata": {
                            "turn_id": request.turn_id,
                            "capability_id": capability_id,
                            "project_key": project_key,
                            "output_path": output_path,
                            "agent_core_call_id": tool_call.call_id,
                        },
                    }
                )
            except Exception as exc:  # noqa: BLE001
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary=f"report.generate failed: {exc}",
                    error={"code": exc.__class__.__name__, "message": str(exc)},
                )
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"Generated report draft artifact {output_path}.",
                ui_summary=f"Generated report: {output_path}",
                structured_content={
                    "contract_version": "report.generate.agent_core.v1",
                    "project_key": project_key,
                    "topic": topic[:200],
                    "output_path": output_path,
                    "artifact_id": artifact.get("artifact_id"),
                    "quality_gate": gate,
                    "artifact": _compact_json_value(artifact, max_items=16, max_depth=4),
                },
                artifact_refs=(str(artifact.get("artifact_id") or output_path),),
            )

@dataclass(frozen=True, slots=True)
class AuthoringToolContext:
    """Injected runtime objects used by the authored static tool catalog."""

    service: AgentSessionService
    structured_data_searcher: Callable[..., dict[str, Any]] | None = None


def _structured_data_searcher(context: AuthoringToolContext) -> Callable[..., dict[str, Any]]:
    return context.structured_data_searcher or query_project_structured_data


def _authoring_source(
    *,
    tool_spec: CoreToolSpec,
    handler: Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult],
    scope_source: str,
    permission_source: str,
    failure_family: str,
    readback_semantics: str,
    governed_dispatch_ref: str | None = None,
) -> ProjectToolAuthorSource:
    return ProjectToolAuthorSource(
        binding_id=f"facility.{tool_spec.name}",
        version="1",
        tool_spec=tool_spec,
        handler=handler,
        executor_ref=tool_spec.name,
        scope_source=scope_source,
        permission_source=permission_source,
        failure_family=failure_family,
        readback_semantics=readback_semantics,
        governed_dispatch_ref=governed_dispatch_ref,
    )


def authoring_task_session_sources(context: AuthoringToolContext) -> tuple[ProjectToolAuthorSource, ...]:
    """Return the four tools registered before the query/discovery family."""

    service = context.service
    return (
        _authoring_source(
            tool_spec=_agent_task_plan_append_spec(),
            handler=_agent_task_plan_append_handler(service),
            scope_source="AgentCoreRequest.project_key and durable session task artifacts",
            permission_source="CoreToolSpec.permission and AgentSessionService artifact ownership",
            failure_family="CoreToolResult.status/error from the original durable task-plan handler",
            readback_semantics="agent.task.plan.append artifact and task list persisted by AgentSessionService",
        ),
        _authoring_source(
            tool_spec=_agent_long_task_stage_update_spec(),
            handler=_agent_long_task_stage_update_handler(service),
            scope_source="AgentCoreRequest.project_key and session-owned long-task state artifact",
            permission_source="CoreToolSpec.permission and AgentSessionService artifact ownership",
            failure_family="CoreToolResult.status/error plus agent_runtime_failures stage validation",
            readback_semantics="agent.long_task.stage state artifact and compact task projection",
        ),
        _authoring_source(
            tool_spec=_agent_long_task_stage_read_spec(),
            handler=_agent_long_task_stage_read_handler(service),
            scope_source="request.session_id and AgentCoreRequest.project_key",
            permission_source="CoreToolSpec.permission and AgentSessionService artifact ownership",
            failure_family="CoreToolResult.status/error from the original long-task state reader",
            readback_semantics="normalized agent.long_task.stage state artifact",
        ),
        _authoring_source(
            tool_spec=_agent_session_resume_bundle_spec(),
            handler=_agent_session_resume_bundle_handler(service),
            scope_source="request.session_id, request.project_key, and session-owned artifacts",
            permission_source="CoreToolSpec.permission and AgentSessionService read boundary",
            failure_family="CoreToolResult.status/error from the original resume-bundle reader",
            readback_semantics="compact current session, tasks, active tasks, and long-task state",
        ),
    )


def authoring_ingest_writing_batch_sources(context: AuthoringToolContext) -> tuple[ProjectToolAuthorSource, ...]:
    """Return tools registered after query/discovery and source review."""

    service = context.service
    searcher = _structured_data_searcher(context)
    return (
        _authoring_source(
            tool_spec=_ingest_url_pool_submit_spec(),
            handler=_ingest_url_pool_submit_handler(service),
            scope_source="AgentCoreRequest.project_key and approved URL ingest payload",
            permission_source="CoreToolSpec.permission plus governed source-library frontdoor/task dispatch boundary",
            failure_family="CoreToolResult.status/error; task execution failures remain owned by ingest task/runtime",
            readback_semantics="deterministic submission artifact plus ingest.url_pool.status and task-event readback",
            governed_dispatch_ref=(
                "services.ingest.url_pool.ingest_url_via_source_library_frontdoor"
            ),
        ),
        _authoring_source(
            tool_spec=_ingest_url_pool_status_spec(),
            handler=_ingest_url_pool_status_handler(service, searcher),
            scope_source="AgentCoreRequest.project_key and session-owned ingest artifacts/tasks",
            permission_source="CoreToolSpec.permission and AgentSessionService/task observation read boundary",
            failure_family="CoreToolResult.status/error from the original URL-pool status observer",
            readback_semantics="submission, task event, and task search projections without reclassifying task state",
        ),
        _authoring_source(
            tool_spec=_source_history_read_spec(),
            handler=_source_history_read_handler(service),
            scope_source="AgentCoreRequest.project_key and session-owned source history artifacts",
            permission_source="CoreToolSpec.permission and AgentSessionService artifact read boundary",
            failure_family="CoreToolResult.status/error from the original source-history reader",
            readback_semantics="reviewed, submitted, and task-event source history with bounded items",
        ),
        _authoring_source(
            tool_spec=_agent_investigation_leads_append_spec(),
            handler=_agent_investigation_leads_append_handler(service),
            scope_source="AgentCoreRequest.project_key and session-owned investigation artifact",
            permission_source="CoreToolSpec.permission and AgentSessionService artifact ownership",
            failure_family="CoreToolResult.status/error from the original investigation append handler",
            readback_semantics="deduplicated investigation trace artifact persisted by AgentSessionService",
        ),
        _authoring_source(
            tool_spec=_agent_investigation_trace_read_spec(),
            handler=_agent_investigation_trace_read_handler(service),
            scope_source="AgentCoreRequest.project_key and session-owned investigation artifact",
            permission_source="CoreToolSpec.permission and AgentSessionService artifact read boundary",
            failure_family="CoreToolResult.status/error from the original investigation trace reader",
            readback_semantics="bounded node/edge trace, summary, and next-step projection",
        ),
        _authoring_source(
            tool_spec=_writing_document_list_spec(),
            handler=_writing_document_list_handler(),
            scope_source="AgentCoreRequest.project_key",
            permission_source="CoreToolSpec.permission and active writing document read boundary",
            failure_family="CoreToolResult.status/error from the original writing list reader",
            readback_semantics="active writing document list without document bodies",
        ),
        _authoring_source(
            tool_spec=_writing_document_read_spec(),
            handler=_writing_document_read_handler(),
            scope_source="AgentCoreRequest.project_key and requested doc_id",
            permission_source="CoreToolSpec.permission and active writing document read boundary",
            failure_family="CoreToolResult.status/error from the original writing document reader",
            readback_semantics="bounded current document body and metadata from the writing service",
        ),
        _authoring_source(
            tool_spec=_writing_document_section_read_spec(),
            handler=_writing_document_section_read_handler(),
            scope_source="AgentCoreRequest.project_key, doc_id, and requested section coordinates",
            permission_source="CoreToolSpec.permission and active writing document read boundary",
            failure_family="CoreToolResult.status/error and writing section range validation",
            readback_semantics="selected writing section and block anchors derived from the persisted body",
        ),
        _authoring_source(
            tool_spec=_writing_document_create_spec(),
            handler=_writing_document_create_handler(),
            scope_source="AgentCoreRequest.project_key and requested writing document fields",
            permission_source="CoreToolSpec.permission and writing document service write boundary",
            failure_family="CoreToolResult.status/error from the original writing create handler",
            readback_semantics="preview when dry_run; otherwise persisted document id and compact projection",
        ),
        _authoring_source(
            tool_spec=_writing_document_insert_paragraph_spec(),
            handler=_writing_document_insert_paragraph_handler(),
            scope_source="AgentCoreRequest.project_key, doc_id, base_version, and requested body operation",
            permission_source="CoreToolSpec.permission and writing document optimistic-concurrency write boundary",
            failure_family="CoreToolResult.status/error plus WritingVersionConflictError and body-operation failures",
            readback_semantics="optimistic save plus agent update metadata, replay observation, and persisted compact document",
        ),
        _authoring_source(
            tool_spec=_writing_document_citations_upsert_spec(),
            handler=_writing_document_citations_upsert_handler(),
            scope_source="AgentCoreRequest.project_key and requested doc_id",
            permission_source="CoreToolSpec.permission and writing citation service write boundary",
            failure_family="CoreToolResult.status/error from the original citation normalization/save handler",
            readback_semantics="dry-run merge when dry_run; otherwise citation service persisted readback",
        ),
        _authoring_source(
            tool_spec=_agent_batch_submit_spec(),
            handler=_agent_batch_submit_handler(),
            scope_source="AgentCoreRequest.project_key and explicit structured agent_batch jobs",
            permission_source="CoreToolSpec.permission and agent_batch.submit API approval boundary",
            failure_family="CoreToolResult.status/error; batch execution failures remain owned by agent_batch runtime",
            readback_semantics="submitted batch/task identities only; tool completion is not batch completion",
        ),
    )


def authoring_tool_sources(context: AuthoringToolContext) -> tuple[ProjectToolAuthorSource, ...]:
    """Return both static families in their original relative order."""

    return (
        *authoring_task_session_sources(context),
        *authoring_ingest_writing_batch_sources(context),
    )


def _capability_metadata_projection(
    capability: Mapping[str, Any],
    *,
    input_schema: dict[str, Any],
) -> CoreToolSpec:
    """Project only the authored workflow/report capability declarations."""

    capability_id = str(capability.get("capability_id") or "").strip()
    approval_level = str(capability.get("approval_level") or "none").strip()
    concurrency_class = str(capability.get("concurrency_class") or "read_only").strip()
    risks = list(capability.get("risks") or [])
    return CoreToolSpec(
        name=capability_id,
        title=str(capability.get("name") or capability_id),
        description_for_model=str(capability.get("description") or capability_id),
        input_schema=input_schema,
        source="legacy_adapter",
        risk=_risk_from_metadata(
            approval_level=approval_level,
            concurrency_class=concurrency_class,
            risks=risks,
        ),
        permission=_permission_from_approval(approval_level),
        concurrency=_concurrency_from_class(concurrency_class),
        project_service_id=capability_id,
        metadata={"legacy_capability": dict(capability)},
    )


def _workflow_graph_run_spec(capability: Mapping[str, Any]) -> CoreToolSpec:
    return _capability_metadata_projection(
        capability,
        input_schema={
            "type": "object",
            "required": ["graph_id", "inputs"],
            "properties": {
                "graph_id": {"type": "string"},
                "inputs": {"type": "object", "additionalProperties": True},
                "input": {"type": "object", "additionalProperties": True},
                "project_key": {"type": "string"},
            },
            "additionalProperties": False,
        },
    )


def _report_generate_spec(capability: Mapping[str, Any]) -> CoreToolSpec:
    return _capability_metadata_projection(
        capability,
        input_schema={
            "type": "object",
            "required": ["topic", "output_path"],
            "properties": {
                "topic": {"type": "string"},
                "output_path": {"type": "string"},
                "project_key": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "section_titles": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
    )


def authoring_capability_sources(
    service: AgentSessionService,
    capabilities: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> tuple[ProjectToolAuthorSource, ...]:
    """Return workflow/report sources while preserving caller capability order."""

    sources: list[ProjectToolAuthorSource] = []
    for capability in capabilities:
        capability_id = str(capability.get("capability_id") or "").strip()
        if capability_id == "workflow_graph.run":
            def workflow_handler(
                tool_call: CoreToolCall,
                tool_spec: CoreToolSpec,
                request: AgentCoreRequest,
                emit: Callable[[CoreEvent], None],
            ) -> CoreToolResult:
                return _workflow_graph_run_handler(
                    service, tool_call, tool_spec, request, emit
                )

            sources.append(_authoring_source(
                tool_spec=_workflow_graph_run_spec(capability),
                handler=workflow_handler,
                scope_source="AgentCoreRequest.project_key and requested workflow graph_id",
                permission_source="CoreToolSpec.permission plus workflow_graph.run skill dispatch boundary",
                failure_family="CoreToolResult.status/error; workflow execution failures remain owned by workflow runtime",
                readback_semantics="graph run identity/result projection; workflow runtime remains the completion authority",
            ))
        elif capability_id == "report.generate":
            def report_handler(
                tool_call: CoreToolCall,
                tool_spec: CoreToolSpec,
                request: AgentCoreRequest,
                emit: Callable[[CoreEvent], None],
            ) -> CoreToolResult:
                return _report_generate_handler(
                    service,
                    "report.generate",
                    tool_call,
                    tool_spec,
                    request,
                    emit,
                )

            sources.append(_authoring_source(
                tool_spec=_report_generate_spec(capability),
                handler=report_handler,
                scope_source="AgentCoreRequest.project_key, requested topic, and output_path artifact name",
                permission_source="CoreToolSpec.permission plus report generation and session artifact write boundary",
                failure_family="CoreToolResult.status/error from report generation, quality gate, or artifact persistence",
                readback_semantics="durable report markdown artifact with structured report and quality-gate readback",
            ))
    return tuple(sources)
