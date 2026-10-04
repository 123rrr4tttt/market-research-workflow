from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from app.services.agent_sessions.service import AgentSessionService, get_agent_session_service

from .capability_registry import (
    is_social_chat_goal,
    list_interactive_agent_capabilities,
)
from .conversation import AgentConversationAnswerer, ModelConversationAnswerer
from .control_tools import AgentControlToolRuntime
from .material_ontology import annotate_capability_result
from .read_only_tools import ReadOnlyAgentToolRuntime
from .run_loop import AgentRunLoop, AgentRunLoopBudget, AgentRunLoopContext, AgentRunLoopPlanner
from .session_memory import build_session_context_summary
from .tool_contract import READ_ONLY_TOOL_PROTOCOL, build_capability_call, build_stream_descriptor
from .tool_pool import AgentToolPoolAssembler, ToolPoolRequest, default_agent_runtime_feature_flags
from .turn_decision import AgentTurnDecisionPlanner, build_turn_decision_plan


BatchLoopRunner = Callable[..., dict[str, Any]]
SourceLibraryLister = Callable[[str | None], list[dict[str, Any]]]
StructuredDataSearcher = Callable[..., dict[str, Any]]
HighRiskCapabilityExecutor = Callable[..., dict[str, Any]]
FINAL_TASK_STATUSES = frozenset({"completed", "failed", "canceled", "expired"})
AGENT_BATCH_FALLBACK_CAPABILITY_ID = "agent_batch.nl_command.submit"
PROJECT_HIGH_RISK_CAPABILITY_IDS = frozenset({"ingest.source_library.run", "workflow_graph.run", "report.generate"})
HIGH_RISK_CAPABILITY_IDS = PROJECT_HIGH_RISK_CAPABILITY_IDS | frozenset({AGENT_BATCH_FALLBACK_CAPABILITY_ID})


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16]}"


def _stable_hash(value: Any, *, length: int = 16) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:length]


def _binding_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _merge_binding_payload(base: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in dict(overrides or {}).items():
        if key in {"inputs", "input", "override_params"} and isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**dict(merged.get(key) or {}), **dict(value)}
        else:
            merged[key] = value
    return merged


class InteractiveAgentRuntime:
    """Session-ledger first interactive agent wrapper.

    The runtime intentionally reuses agent_batch for autonomous project work and
    keeps direct high-risk capability execution behind existing project gates.
    """

    contract_version = "interactive_agent.turn.v1"

    def __init__(self, *, service: AgentSessionService | None = None) -> None:
        self.service = service or get_agent_session_service()

    def list_capabilities(self) -> list[dict[str, Any]]:
        return list_interactive_agent_capabilities()

    def run_turn(
        self,
        *,
        message: str,
        project_key: str | None,
        session_id: str | None = None,
        idempotency_key: str | None = None,
        dry_run: bool = False,
        enable_bounded_retry: bool = True,
        enable_limited_branching: bool = True,
        batch_loop_runner: BatchLoopRunner,
        parser_fallback: Callable[[str], dict[str, Any]],
        submitter: Callable[[list[dict[str, Any]], str | None, str | None], dict[str, Any]],
        executor_snapshot: Callable[[], dict[str, Any]],
        source_library_lister: SourceLibraryLister | None = None,
        structured_data_searcher: StructuredDataSearcher | None = None,
        run_loop_planner: AgentRunLoopPlanner | None = None,
        turn_decision_planner: AgentTurnDecisionPlanner | None = None,
        conversation_answerer: AgentConversationAnswerer | None = None,
        require_high_risk_approval: bool = False,
    ) -> dict[str, Any]:
        command = str(message or "").strip()
        if not command:
            raise ValueError("message is required")

        turn_id = _new_id("turn")
        session, created_tasks, user_message_created = self._ensure_session(
            session_id=session_id,
            project_key=project_key,
            message=command,
            turn_id=turn_id,
        )
        resolved_session_id = str(session["session_id"])
        task_blueprints = self._build_turn_blueprints(command=command, turn_id=turn_id)
        if created_tasks:
            task_ids = {str(task.get("metadata", {}).get("interactive_turn_role") or ""): str(task.get("task_id") or "") for task in created_tasks}
        else:
            appended = self.service.append_task_blueprints(
                resolved_session_id,
                goal=command,
                task_blueprints=task_blueprints,
            )
            task_ids = {str(task.get("metadata", {}).get("interactive_turn_role") or ""): str(task.get("task_id") or "") for task in appended}

        if not user_message_created:
            self.service.create_message(
                resolved_session_id,
                role="user",
                actor="interactive_user",
                content=command,
                metadata={"interactive_turn_id": turn_id, "project_key": project_key},
            )

        self.service.store.append_event(
            resolved_session_id,
            event_type="interactive_agent.turn_started",
            payload={"turn_id": turn_id, "project_key": project_key, "dry_run": bool(dry_run)},
        )

        plan_task_id = task_ids["plan"]
        execute_task_id = task_ids["execute"]
        final_task_id = task_ids["final"]
        plan = self._build_plan(
            command=command,
            project_key=project_key,
            turn_id=turn_id,
            dry_run=dry_run,
            turn_decision_planner=turn_decision_planner,
        )
        self._complete_plan_task(resolved_session_id, plan_task_id, plan)

        idempotency = str(idempotency_key or "").strip()
        if not idempotency:
            idempotency = f"interactive-agent:{resolved_session_id}:{_stable_hash({'message': command})}"

        selected_capability_ids = self._selected_capability_ids(plan)
        agent_mode = str(plan.get("goal_class") or "conversation")
        capability_calls: list[dict[str, Any]] = []
        loop_result: dict[str, Any] = {}
        run_loop_result: dict[str, Any] = {}

        self.service.claim_task(resolved_session_id, execute_task_id, owner="interactive_agent")
        read_only_runtime = ReadOnlyAgentToolRuntime(
            service=self.service,
            source_library_lister=source_library_lister,
            structured_data_searcher=structured_data_searcher,
        )
        read_only_capability_ids = [
            capability_id
            for capability_id in selected_capability_ids
            if capability_id in read_only_runtime.supported_tool_names()
        ]
        if read_only_capability_ids:
            run_loop = AgentRunLoop(
                tool_runtime=read_only_runtime,
                planner=run_loop_planner,
                budget=AgentRunLoopBudget(),
                event_sink=lambda event: self._record_run_loop_event(
                    resolved_session_id,
                    execute_task_id,
                    event,
                ),
            )
            run_loop_result = run_loop.run(
                AgentRunLoopContext(
                    turn_id=turn_id,
                    session_id=resolved_session_id,
                    project_key=project_key,
                    message=command,
                    selected_capability_ids=tuple(read_only_capability_ids),
                    agent_mode=agent_mode,
                )
            )
            for call in list(run_loop_result.get("capability_calls") or []):
                annotated_call = annotate_capability_result(dict(call or {}))
                capability_calls.append(annotated_call)
                self._record_capability_call(resolved_session_id, execute_task_id, annotated_call)

        control_runtime = AgentControlToolRuntime(service=self.service)
        control_capability_ids = [
            capability_id
            for capability_id in selected_capability_ids
            if capability_id in control_runtime.supported_tool_names()
        ]
        for capability_id in control_capability_ids:
            self.service.store.append_event(
                resolved_session_id,
                event_type="interactive_agent.tool_call_started",
                task_id=execute_task_id,
                payload={
                    "turn_id": turn_id,
                    "capability_id": capability_id,
                    "tool_name": capability_id,
                    "protocol": "session_control",
                    "stream_state": "started",
                },
            )
            control_call = control_runtime.execute(
                capability_id,
                session_id=resolved_session_id,
                turn_id=turn_id,
                input_payload=self._build_control_tool_input(
                    capability_id=capability_id,
                    command=command,
                    session_id=resolved_session_id,
                ),
            )
            control_call = annotate_capability_result(control_call)
            capability_calls.append(control_call)
            self._record_capability_call(resolved_session_id, execute_task_id, control_call)
            self.service.store.append_event(
                resolved_session_id,
                event_type="interactive_agent.tool_call_result",
                task_id=execute_task_id,
                payload={
                    "turn_id": turn_id,
                    "capability_id": capability_id,
                    "tool_name": capability_id,
                    "protocol": "session_control",
                    "stream_state": control_call.get("stream_state") or control_call.get("status"),
                    "status": control_call.get("status"),
                    "summary": control_call.get("summary"),
                    "error": control_call.get("error"),
                },
            )

        selected_project_high_risk_capability_ids = [
            capability_id
            for capability_id in selected_capability_ids
            if capability_id in PROJECT_HIGH_RISK_CAPABILITY_IDS
        ]
        selected_high_risk_capability_ids = list(selected_project_high_risk_capability_ids)
        if (
            bool(require_high_risk_approval)
            and not selected_project_high_risk_capability_ids
            and AGENT_BATCH_FALLBACK_CAPABILITY_ID in selected_capability_ids
        ):
            selected_high_risk_capability_ids.append(AGENT_BATCH_FALLBACK_CAPABILITY_ID)
        should_run_batch = AGENT_BATCH_FALLBACK_CAPABILITY_ID in selected_capability_ids and not (
            bool(require_high_risk_approval) and selected_high_risk_capability_ids
        )
        if should_run_batch:
            try:
                loop_result = batch_loop_runner(
                    command=command,
                    project_key=project_key,
                    idempotency_key=idempotency,
                    dry_run=bool(dry_run),
                    enable_bounded_retry=bool(enable_bounded_retry),
                    enable_limited_branching=bool(enable_limited_branching),
                    parser_fallback=parser_fallback,
                    submitter=submitter,
                    executor_snapshot=executor_snapshot,
                )
            except Exception as exc:
                return self._fail_turn(
                    session_id=resolved_session_id,
                    execute_task_id=execute_task_id,
                    final_task_id=final_task_id,
                    turn_id=turn_id,
                    message=command,
                    error=exc,
                    plan=plan,
                    capability_calls=capability_calls,
                )

            capability_call = self._build_capability_call(
                capability_id=AGENT_BATCH_FALLBACK_CAPABILITY_ID,
                turn_id=turn_id,
                idempotency_key=idempotency,
                loop_result=loop_result,
            )
            capability_call = annotate_capability_result(capability_call)
            capability_calls.append(capability_call)
            self.service.store.upsert_artifact(
                {
                    "session_id": resolved_session_id,
                    "task_id": execute_task_id,
                    "artifact_type": "interactive_agent.loop_result",
                    "name": f"interactive_agent.loop_result.{turn_id}.json",
                    "mime_type": "application/json",
                    "content_json": loop_result,
                    "metadata": {"turn_id": turn_id, "capability_id": capability_call["capability_id"]},
                }
            )
            self._record_capability_call(resolved_session_id, execute_task_id, capability_call)

        approval_requests: list[dict[str, Any]] = []
        for capability_id in selected_high_risk_capability_ids:
            approval_request = None
            if not dry_run and not should_run_batch:
                approval_request = self._request_capability_approval(
                    session_id=resolved_session_id,
                    task_id=execute_task_id,
                    turn_id=turn_id,
                    command=command,
                    project_key=project_key,
                    capability_id=capability_id,
                    capability_calls=capability_calls,
                )
                approval_requests.append(approval_request)
            call = self._build_delegated_capability_call(
                capability_id=capability_id,
                turn_id=turn_id,
                delegated=should_run_batch and not dry_run,
                dry_run=dry_run,
                approval_request=approval_request,
            )
            call = annotate_capability_result(call)
            capability_calls.append(call)
            self._record_capability_call(resolved_session_id, execute_task_id, call)

        execute_summary = self._summarize_capability_calls(capability_calls)
        execute_status = "blocked" if approval_requests else "completed"
        self.service.release_task(
            resolved_session_id,
            execute_task_id,
            status=execute_status,
            result_summary=execute_summary,
            result_payload={
                "agent_mode": agent_mode,
                "capability_calls": capability_calls,
                "loop_result": loop_result,
                "run_loop": run_loop_result,
                "approval_requests": approval_requests,
            },
            activity="waiting for high-risk capability approval" if approval_requests else "interactive agent capabilities dispatched",
        )

        context_summary = build_session_context_summary(
            self.service.get_session_bundle(resolved_session_id),
            latest_user_instruction=command,
            project_key=project_key,
        )
        suggested_next_actions = self._build_suggested_next_actions(plan=plan, capability_calls=capability_calls, agent_mode=agent_mode)
        final_answer = self._build_final_answer(
            command=command,
            plan=plan,
            loop_result=loop_result,
            run_loop_result=run_loop_result,
            dry_run=dry_run,
            capability_calls=capability_calls,
            agent_mode=agent_mode,
            suggested_next_actions=suggested_next_actions,
            context_summary=context_summary,
            conversation_answerer=conversation_answerer,
        )
        final_payload = {
            "turn_id": turn_id,
            "final_answer": final_answer,
            "agent_mode": agent_mode,
            "capability_calls": capability_calls,
            "suggested_next_actions": suggested_next_actions,
            "plan": plan,
            "run_loop": run_loop_result,
            "approval_requests": approval_requests,
            "context_summary": context_summary,
            "stream": build_stream_descriptor(session_id=resolved_session_id),
        }
        self.service.store.upsert_artifact(
            {
                "session_id": resolved_session_id,
                "task_id": final_task_id,
                "artifact_type": "interactive_agent.final_answer",
                "name": f"interactive_agent.final_answer.{turn_id}.md",
                "mime_type": "text/markdown",
                "content_text": final_answer,
                "metadata": {"turn_id": turn_id},
            }
        )
        if approval_requests:
            self.service.release_task(
                resolved_session_id,
                final_task_id,
                status="blocked",
                result_summary=final_answer[:240],
                result_payload=final_payload,
                activity="waiting for approval before final completion",
            )
        else:
            final_task = self.service.store.get_task(resolved_session_id, final_task_id)
            if str(final_task.get("status") or "") in FINAL_TASK_STATUSES:
                self.service.store.update_task(
                    resolved_session_id,
                    final_task_id,
                    {
                        "result_summary": final_answer[:240],
                        "result_payload": final_payload,
                        "last_activity": "final answer emitted after session control",
                    },
                )
                self.service.store.append_event(
                    resolved_session_id,
                    event_type="interactive_agent.final_task_preserved",
                    task_id=final_task_id,
                    payload={
                        "turn_id": turn_id,
                        "status": final_task.get("status"),
                        "reason": "final task was already terminal after session control",
                    },
                )
            else:
                self.service.claim_task(resolved_session_id, final_task_id, owner="interactive_agent")
                self.service.release_task(
                    resolved_session_id,
                    final_task_id,
                    status="completed",
                    result_summary=final_answer[:240],
                    result_payload=final_payload,
                    activity="final answer emitted",
                )
        self.service.create_message(
            resolved_session_id,
            role="assistant",
            actor="interactive_agent",
            task_id=final_task_id,
            content=final_answer,
            metadata=final_payload,
        )
        self.service.store.append_event(
            resolved_session_id,
            event_type="interactive_agent.final_answer",
            task_id=final_task_id,
            payload={"turn_id": turn_id, "summary": final_answer[:240]},
        )
        if any(
            str(call.get("capability_id") or "") == "task.cancel" and str(call.get("status") or "") == "completed"
            for call in capability_calls
        ):
            self.service.store.update_session(resolved_session_id, {"status": "canceled"})
        self.service._refresh_memory_artifacts(resolved_session_id, force=True)
        bundle = self.service.get_session_bundle(resolved_session_id)
        return {
            "contract_version": self.contract_version,
            "turn": {
                "turn_id": turn_id,
                "created_at": _utcnow_iso(),
                "message": command,
                "dry_run": bool(dry_run),
                "idempotency_key": idempotency,
            },
            "session": bundle["session"],
            "tasks": bundle["tasks"],
            "messages": bundle["messages"],
            "events": bundle["events"],
            "artifacts": bundle["artifacts"],
            "approvals": bundle["approvals"],
            "agent_mode": agent_mode,
            "plan": plan,
            "capability_calls": capability_calls,
            "suggested_next_actions": suggested_next_actions,
            "loop_result": loop_result,
            "run_loop": run_loop_result,
            "approval_requests": approval_requests,
            "context_summary": context_summary,
            "stream": build_stream_descriptor(session_id=resolved_session_id),
            "final_answer": final_answer,
        }

    def continue_approved_capability(
        self,
        *,
        approval_id: str,
        approved_by: str = "user",
        binding_payload_overrides: dict[str, Any] | None = None,
        high_risk_executor: HighRiskCapabilityExecutor | None = None,
    ) -> dict[str, Any]:
        resolved_approval_id = str(approval_id or "").strip()
        if not resolved_approval_id:
            raise ValueError("approval_id is required")
        approval = self.service.store.get_approval(resolved_approval_id)
        overrides = dict(binding_payload_overrides or {})
        if overrides:
            binding_payload = _merge_binding_payload(dict(approval.get("binding_payload") or {}), overrides)
            audit_log = list(approval.get("audit_log") or [])
            audit_log.append(
                {
                    "at": _utcnow_iso(),
                    "action": "binding_overridden",
                    "actor": str(approved_by or "unknown").strip() or "unknown",
                    "override_keys": sorted(overrides.keys()),
                }
            )
            approval = self.service.store.create_or_update_approval(
                {
                    **approval,
                    "binding_hash": _binding_hash(binding_payload),
                    "binding_payload": binding_payload,
                    "audit_log": audit_log,
                }
            )
            requester_session_id = str(approval.get("requester_session_id") or "").strip()
            if requester_session_id:
                self.service.store.append_event(
                    requester_session_id,
                    event_type="approval.binding_overridden",
                    task_id=approval.get("requester_task_id"),
                    payload={
                        "approval_id": resolved_approval_id,
                        "override_keys": sorted(overrides.keys()),
                    },
                )
        if str(approval.get("status") or "") == "pending":
            approval = self.service.resolve_approval(resolved_approval_id, approved_by=approved_by, approved=True)
        if str(approval.get("status") or "") != "approved":
            raise ValueError("approval must be approved before continue")

        binding_payload = dict(approval.get("binding_payload") or {})
        if str(binding_payload.get("contract_version") or "") != "interactive_agent.high_risk_approval.v1":
            raise ValueError("approval is not an interactive agent high-risk approval")
        session_id = str(approval.get("requester_session_id") or binding_payload.get("session_id") or "").strip()
        execute_task_id = str(approval.get("requester_task_id") or "").strip()
        turn_id = str(binding_payload.get("turn_id") or "").strip()
        capability_id = str(binding_payload.get("capability_id") or "").strip()
        command = str(binding_payload.get("command") or "").strip()
        project_key = str(binding_payload.get("project_key") or "").strip() or None
        if not session_id or not execute_task_id or not turn_id or not capability_id:
            raise ValueError("approval binding is missing required resume fields")

        execute_task = self.service.store.get_task(session_id, execute_task_id)
        execute_payload = dict(execute_task.get("result_payload") or {})
        existing_continuation = dict(execute_payload.get("approval_continuation") or {})
        if existing_continuation.get("approval_id") == resolved_approval_id and str(execute_task.get("status") or "") in FINAL_TASK_STATUSES:
            bundle = self.service.get_session_bundle(session_id)
            return {
                "contract_version": self.contract_version,
                "approval": approval,
                "session": bundle["session"],
                "tasks": bundle["tasks"],
                "messages": bundle["messages"],
                "events": bundle["events"],
                "artifacts": bundle["artifacts"],
                "approvals": bundle["approvals"],
                "capability_call": existing_continuation.get("capability_call") or {},
                "continued": False,
            }

        if str(execute_task.get("status") or "") in {"canceled", "expired"}:
            self.service.store.update_task(
                session_id,
                execute_task_id,
                {
                    "status": "pending",
                    "lease_until": None,
                    "completed_at": None,
                    "last_activity": "approval continuation restored terminal execute task",
                },
            )
            self.service.store.append_event(
                session_id,
                event_type="interactive_agent.approval_resume_restored_task",
                task_id=execute_task_id,
                payload={"approval_id": resolved_approval_id, "capability_id": capability_id},
            )
        self.service.claim_task(session_id, execute_task_id, owner="interactive_agent")
        self.service.store.append_event(
            session_id,
            event_type="interactive_agent.tool_call_started",
            task_id=execute_task_id,
            payload={
                "turn_id": turn_id,
                "approval_id": resolved_approval_id,
                "capability_id": capability_id,
                "tool_name": capability_id,
                "protocol": "approval_gated",
                "stream_state": "started",
            },
        )
        executor = high_risk_executor or self._execute_approved_high_risk_capability
        capability_call = executor(
            approval=approval,
            binding_payload=binding_payload,
            turn_id=turn_id,
            session_id=session_id,
            task_id=execute_task_id,
            capability_id=capability_id,
            command=command,
            project_key=project_key,
        )
        capability_call = dict(capability_call or {})
        capability_call.setdefault("turn_id", turn_id)
        capability_call.setdefault("capability_id", capability_id)
        capability_call.setdefault("tool_name", capability_id)
        capability_call.setdefault("approval_id", resolved_approval_id)
        capability_call.setdefault("protocol", "approval_gated")
        capability_call.setdefault("status", "completed")
        capability_call.setdefault("summary", "approved capability continued")
        capability_call = annotate_capability_result(capability_call)
        self.service.store.append_event(
            session_id,
            event_type="interactive_agent.tool_call_result",
            task_id=execute_task_id,
            payload=capability_call,
        )
        self._record_capability_call(session_id, execute_task_id, capability_call)

        previous_calls = [dict(item or {}) for item in list(execute_payload.get("capability_calls") or [])]
        previous_calls = [
            call
            for call in previous_calls
            if str(call.get("approval_id") or "") != resolved_approval_id
            and str(call.get("capability_id") or "") != capability_id
        ]
        capability_calls = [*previous_calls, capability_call]
        execution_completed = str(capability_call.get("status") or "") in {"completed", "delegated"}
        execute_status = "completed" if execution_completed else "failed"
        execute_summary = self._summarize_capability_calls(capability_calls)
        execute_payload.update(
            {
                "capability_calls": capability_calls,
                "approval_continuation": {
                    "approval_id": resolved_approval_id,
                    "capability_id": capability_id,
                    "continued_at": _utcnow_iso(),
                    "capability_call": capability_call,
                },
            }
        )
        self.service.release_task(
            session_id,
            execute_task_id,
            status=execute_status,
            result_summary=execute_summary,
            result_payload=execute_payload,
            activity="approved high-risk capability continued",
        )

        final_answer = self._build_approval_continuation_answer(
            capability_id=capability_id,
            approval_id=resolved_approval_id,
            capability_call=capability_call,
            execution_completed=execution_completed,
        )
        final_payload = {
            "turn_id": turn_id,
            "final_answer": final_answer,
            "capability_calls": capability_calls,
            "approval": approval,
            "stream": build_stream_descriptor(session_id=session_id),
        }
        final_task_id = self._find_turn_task_id(session_id=session_id, turn_id=turn_id, role="final")
        if final_task_id:
            self.service.store.upsert_artifact(
                {
                    "session_id": session_id,
                    "task_id": final_task_id,
                    "artifact_type": "interactive_agent.final_answer",
                    "name": f"interactive_agent.final_answer.{turn_id}.approval_continue.md",
                    "mime_type": "text/markdown",
                    "content_text": final_answer,
                    "metadata": {"turn_id": turn_id, "approval_id": resolved_approval_id},
                }
            )
            if execution_completed:
                self.service.claim_task(session_id, final_task_id, owner="interactive_agent")
            self.service.release_task(
                session_id,
                final_task_id,
                status="completed" if execution_completed else "failed",
                result_summary=final_answer[:240],
                result_payload=final_payload,
                activity="approval continuation final answer emitted",
            )
        self.service.create_message(
            session_id,
            role="assistant",
            actor="interactive_agent",
            task_id=final_task_id,
            content=final_answer,
            metadata=final_payload,
        )
        self.service.store.append_event(
            session_id,
            event_type="interactive_agent.approval_continued",
            task_id=execute_task_id,
            payload={
                "turn_id": turn_id,
                "approval_id": resolved_approval_id,
                "capability_id": capability_id,
                "status": capability_call.get("status"),
            },
        )
        self.service.store.append_event(
            session_id,
            event_type="interactive_agent.final_answer",
            task_id=final_task_id,
            payload={"turn_id": turn_id, "summary": final_answer[:240]},
        )
        self.service._refresh_memory_artifacts(session_id, force=True)
        bundle = self.service.get_session_bundle(session_id)
        return {
            "contract_version": self.contract_version,
            "approval": approval,
            "session": bundle["session"],
            "tasks": bundle["tasks"],
            "messages": bundle["messages"],
            "events": bundle["events"],
            "artifacts": bundle["artifacts"],
            "approvals": bundle["approvals"],
            "capability_call": capability_call,
            "continued": True,
            "stream": build_stream_descriptor(session_id=session_id),
            "final_answer": final_answer,
        }

    def _ensure_session(
        self,
        *,
        session_id: str | None,
        project_key: str | None,
        message: str,
        turn_id: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
        resolved_session_id = str(session_id or "").strip()
        if resolved_session_id:
            session = self.service.get_session(resolved_session_id)
            existing_project = str(session.get("project_key") or "").strip()
            incoming_project = str(project_key or "").strip()
            if existing_project and incoming_project and existing_project != incoming_project:
                raise ValueError("session project_key does not match request project_key")
            return session, [], False

        blueprints = self._build_turn_blueprints(command=message, turn_id=turn_id)
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="interactive_agent",
            goal=message,
            project_key=project_key,
            initial_context={"message": message},
            metadata={
                "interactive_agent": {
                    "contract_version": self.contract_version,
                    "created_from": "agent_chat",
                    "initial_turn_id": turn_id,
                }
            },
            task_blueprints=blueprints,
        )
        return dict(bundle["session"]), list(bundle["tasks"]), True

    def _build_turn_blueprints(self, *, command: str, turn_id: str) -> list[dict[str, Any]]:
        plan_task_id = _new_id("task")
        execute_task_id = _new_id("task")
        final_task_id = _new_id("task")
        return [
            {
                "task_id": plan_task_id,
                "subject": "Plan interactive capabilities",
                "description": "Select governed project capabilities for the user turn.",
                "task_type": "interactive_plan",
                "phase": "research",
                "execution_mode": "worker",
                "priority": 1,
                "read_set": ["capability.registry"],
                "write_set": [],
                "metadata": {"interactive_turn_id": turn_id, "interactive_turn_role": "plan"},
                "task_spec": {
                    "task_type": "interactive_plan",
                    "goal": command,
                    "context": {"turn_id": turn_id},
                    "target_scope": "capability.registry",
                    "write_set": [],
                    "completion_criteria": ["Select capabilities and guardrails for the turn."],
                    "verification_steps": ["Confirm high-risk capabilities remain approval-gated."],
                    "artifact_targets": ["interactive_agent.plan.json"],
                },
            },
            {
                "task_id": execute_task_id,
                "subject": "Execute selected project capability",
                "description": "Run the selected governed project capability.",
                "task_type": "capability_execution",
                "phase": "implementation",
                "execution_mode": "worker",
                "priority": 2,
                "blocked_by": [plan_task_id],
                "read_set": ["capability.registry"],
                "write_set": [f"interactive_agent.turn:{turn_id}"],
                "metadata": {
                    "interactive_turn_id": turn_id,
                    "interactive_turn_role": "execute",
                    "concurrency_class": "write_shared",
                },
                "task_spec": {
                    "task_type": "capability_execution",
                    "goal": command,
                    "context": {"turn_id": turn_id},
                    "target_scope": turn_id,
                    "write_set": [f"interactive_agent.turn:{turn_id}"],
                    "completion_criteria": ["Execute or dispatch the selected capability through existing project gates."],
                    "verification_steps": ["Persist capability result and linked job/run identifiers."],
                    "artifact_targets": ["interactive_agent.loop_result.json"],
                },
            },
            {
                "task_id": final_task_id,
                "subject": "Emit final answer",
                "description": "Summarize what the agent did and how the user can continue watching it.",
                "task_type": "final_answer",
                "phase": "verification",
                "execution_mode": "worker",
                "priority": 3,
                "blocked_by": [execute_task_id],
                "read_set": [f"interactive_agent.turn:{turn_id}"],
                "write_set": [],
                "metadata": {"interactive_turn_id": turn_id, "interactive_turn_role": "final"},
                "task_spec": {
                    "task_type": "final_answer",
                    "goal": command,
                    "context": {"turn_id": turn_id},
                    "target_scope": turn_id,
                    "write_set": [],
                    "completion_criteria": ["Return a user-facing answer backed by session artifacts."],
                    "verification_steps": ["Confirm the event stream contains plan, execution, and final-answer events."],
                    "artifact_targets": ["interactive_agent.final_answer.md"],
                },
            },
        ]

    def _build_plan(
        self,
        *,
        command: str,
        project_key: str | None,
        turn_id: str,
        dry_run: bool,
        turn_decision_planner: AgentTurnDecisionPlanner | None = None,
    ) -> dict[str, Any]:
        tool_pool = AgentToolPoolAssembler().assemble(
            ToolPoolRequest(
                project_key=project_key,
                agent_mode="undecided",
                feature_flags=default_agent_runtime_feature_flags(),
            )
        )
        turn_decision, capabilities = build_turn_decision_plan(
            message=command,
            project_key=project_key,
            planner=turn_decision_planner,
            tool_pool=tool_pool,
        )
        goal_class = str(turn_decision.get("agent_mode") or "conversation")
        action = str(turn_decision.get("action") or "")
        if action == "answer_direct":
            strategy = "answer-direct-fast-path"
        elif action == "ask_clarification":
            strategy = "clarification-first"
        elif goal_class in {"conversation", "read_only"}:
            strategy = "read-only-fast-path"
        elif action == "request_approval":
            strategy = "approval-gated-execution"
        else:
            strategy = "session-ledger-first"
        return {
            "contract_version": "interactive_agent.plan.v1",
            "turn_id": turn_id,
            "goal": command,
            "project_key": project_key,
            "dry_run": bool(dry_run),
            "strategy": strategy,
            "goal_class": goal_class,
            "turn_decision": turn_decision,
            "selected_capabilities": capabilities,
            "tool_pool_summary": {
                "counts": dict(tool_pool.get("counts") or {}),
                "model_context": "available_to_turn_decision",
            },
            "guardrails": {
                "canonical_state": "agent_sessions",
                "write_policy": "write_shared_conflict_check",
                "high_risk_execution": "approval_gated_by_existing_skill_or_agent_batch_policy",
                "routing_hints_policy": "classify_goal is hint-only; turn_decision selects answer/tool/approval path",
                "event_stream": "/api/v1/agent-sessions/{session_id}/stream",
            },
        }

    def _complete_plan_task(self, session_id: str, task_id: str, plan: dict[str, Any]) -> None:
        self.service.claim_task(session_id, task_id, owner="interactive_agent")
        self.service.store.upsert_artifact(
            {
                "session_id": session_id,
                "task_id": task_id,
                "artifact_type": "interactive_agent.plan",
                "name": f"interactive_agent.plan.{plan['turn_id']}.json",
                "mime_type": "application/json",
                "content_json": plan,
                "metadata": {"turn_id": plan["turn_id"]},
            }
        )
        self.service.release_task(
            session_id,
            task_id,
            status="completed",
            result_summary=f"Selected {len(plan['selected_capabilities'])} capabilities",
            result_payload=plan,
            activity="capability plan completed",
        )
        self.service.store.append_event(
            session_id,
            event_type="interactive_agent.capability_planned",
            task_id=task_id,
            payload={
                "turn_id": plan["turn_id"],
                "capability_ids": [item["capability_id"] for item in plan["selected_capabilities"]],
                "turn_decision": plan.get("turn_decision"),
            },
        )

    @staticmethod
    def _selected_capability_ids(plan: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for item in list(plan.get("selected_capabilities") or []):
            capability_id = str(dict(item or {}).get("capability_id") or "").strip()
            if capability_id and capability_id not in out:
                out.append(capability_id)
        return out

    def _record_capability_call(self, session_id: str, task_id: str, call: dict[str, Any]) -> None:
        call = annotate_capability_result(call)
        capability_id = str(call.get("capability_id") or "unknown")
        turn_id = str(call.get("turn_id") or "")
        call_hash = _stable_hash(call, length=10)
        self.service.store.upsert_artifact(
            {
                "session_id": session_id,
                "task_id": task_id,
                "artifact_type": "interactive_agent.capability_call",
                "name": f"interactive_agent.capability_call.{turn_id}.{capability_id}.{call_hash}.json",
                "mime_type": "application/json",
                "content_json": call,
                "metadata": {
                    "turn_id": turn_id,
                    "capability_id": capability_id,
                    "status": call.get("status"),
                },
            }
        )
        self.service.store.append_event(
            session_id,
            event_type="interactive_agent.capability_executed",
            task_id=task_id,
            payload=call,
        )

    def _record_run_loop_event(self, session_id: str, task_id: str, event: dict[str, Any]) -> None:
        event_type = str(event.get("event_type") or "").strip()
        if not event_type:
            return
        payload = dict(event.get("payload") or {})
        self.service.store.append_event(
            session_id,
            event_type=event_type,
            task_id=task_id,
            payload=payload,
        )

    def _record_capability_call_started(
        self,
        session_id: str,
        task_id: str,
        *,
        turn_id: str,
        capability_id: str,
    ) -> None:
        self.service.store.append_event(
            session_id,
            event_type="interactive_agent.tool_call_started",
            task_id=task_id,
            payload={
                "turn_id": turn_id,
                "capability_id": capability_id,
                "tool_name": capability_id,
                "protocol": READ_ONLY_TOOL_PROTOCOL,
                "stream_state": "started",
            },
        )

    def _build_read_only_capability_call(
        self,
        *,
        capability_id: str,
        turn_id: str,
        session_id: str,
        project_key: str | None,
        command: str,
        read_only_runtime: ReadOnlyAgentToolRuntime,
    ) -> dict[str, Any]:
        try:
            if capability_id == "agent_runtime.capability.catalog":
                return read_only_runtime.capability_catalog(turn_id=turn_id)
            if capability_id == "agent_runtime.tool_pool.list":
                return read_only_runtime.tool_pool_list(turn_id=turn_id, project_key=project_key)
            if capability_id == "agent_runtime.tool.search":
                return read_only_runtime.tool_search(
                    turn_id=turn_id,
                    project_key=project_key,
                    query=command,
                )
            if capability_id == "agent_session.context.read":
                return read_only_runtime.session_context(session_id=session_id, turn_id=turn_id)
            if capability_id == "project.summary.read":
                return read_only_runtime.project_summary(project_key=project_key, session_id=session_id, turn_id=turn_id)
            if capability_id == "project.structured_data.search":
                return read_only_runtime.project_structured_data_search(
                    project_key=project_key,
                    turn_id=turn_id,
                    query=command,
                )
            if capability_id == "project.context.bundle":
                return read_only_runtime.project_context_bundle(
                    project_key=project_key,
                    session_id=session_id,
                    turn_id=turn_id,
                    query=command,
                )
            if capability_id == "source_library.item.list":
                return read_only_runtime.source_library_list(project_key=project_key, turn_id=turn_id)
            if capability_id == "source_library.item.search":
                return read_only_runtime.source_library_search(project_key=project_key, turn_id=turn_id, query=command)
            if capability_id == "source_library.item.inspect":
                return read_only_runtime.source_library_inspect(
                    project_key=project_key,
                    turn_id=turn_id,
                    item_key=self._extract_source_item_key(command),
                )
            if capability_id == "agent_artifact.search":
                return read_only_runtime.artifact_search(session_id=session_id, turn_id=turn_id, query=command)
            if capability_id == "agent_artifact.read":
                return read_only_runtime.artifact_read(session_id=session_id, turn_id=turn_id, artifact_ref=None)
        except Exception as exc:  # noqa: BLE001
            return build_capability_call(
                turn_id=turn_id,
                capability_id=capability_id,
                protocol=READ_ONLY_TOOL_PROTOCOL,
                status="failed",
                summary=f"read-only tool failed: {exc}",
                error={"type": exc.__class__.__name__, "message": str(exc)},
                result={},
            )
        return build_capability_call(
            turn_id=turn_id,
            capability_id=capability_id,
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status="skipped",
            summary="read-only capability is not implemented in this runtime",
            result={},
        )

    @staticmethod
    def _extract_source_item_key(command: str) -> str | None:
        for token in str(command or "").replace("，", " ").replace(",", " ").split():
            cleaned = token.strip("`'\"：:；;。()[]{}")
            if "." in cleaned and len(cleaned) >= 3:
                return cleaned
        return None

    def _request_capability_approval(
        self,
        *,
        session_id: str,
        task_id: str,
        turn_id: str,
        command: str,
        project_key: str | None,
        capability_id: str,
        capability_calls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        approval_id = f"approval-{_stable_hash({'turn_id': turn_id, 'capability_id': capability_id}, length=18)}"
        preview_payload = self._build_execution_preview_payload(
            capability_id=capability_id,
            command=command,
            project_key=project_key,
            approval_id=approval_id,
            capability_calls=capability_calls or [],
        )
        execution_payload = dict(preview_payload.get("execution_payload") or {})
        binding_payload = {
            "contract_version": "interactive_agent.high_risk_approval.v1",
            "turn_id": turn_id,
            "capability_id": capability_id,
            "command": command,
            "project_key": project_key,
            "item_key": execution_payload.get("item_key"),
            "graph_id": execution_payload.get("graph_id"),
            "inputs": dict(execution_payload.get("inputs") or {}),
            "override_params": dict(execution_payload.get("override_params") or {}),
            "time_window": execution_payload.get("time_window"),
            "max_items": execution_payload.get("max_items"),
            "source_scope": execution_payload.get("source_scope"),
            "dry_run": False,
            "explain_only": False,
            "approval_required": True,
            "resume_token": f"{session_id}:{task_id}:{approval_id}",
            "preview_payload": preview_payload,
            "execution_payload": execution_payload,
            "resume_context": dict(preview_payload.get("resume_context") or {}),
        }
        self.service.store.append_event(
            session_id,
            event_type="interactive_agent.approval_preview",
            task_id=task_id,
            payload={
                "turn_id": turn_id,
                "approval_id": approval_id,
                "capability_id": capability_id,
                "preview_payload": preview_payload,
            },
        )
        approval_request = self.service.request_approval(
            session_id=session_id,
            task_id=task_id,
            requester_actor="interactive_agent",
            binding_payload=binding_payload,
            metadata={
                "approval_id": approval_id,
                "force_approval": True,
                "capability_id": capability_id,
                "turn_id": turn_id,
                "requires_confirmation": True,
                "scope_summary": preview_payload.get("scope_summary"),
            },
        )
        self.service.store.append_event(
            session_id,
            event_type="interactive_agent.execution_payload_snapshotted",
            task_id=task_id,
            payload={
                "turn_id": turn_id,
                "approval_id": approval_id,
                "capability_id": capability_id,
                "execution_payload": execution_payload,
                "resume_context": binding_payload["resume_context"],
            },
        )
        return approval_request

    def _build_execution_preview_payload(
        self,
        *,
        capability_id: str,
        command: str,
        project_key: str | None,
        approval_id: str,
        capability_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        candidates = self._source_library_candidates_from_calls(capability_calls)
        time_window = self._extract_assignment_value(command, keys=("time_window", "window", "时间窗"))
        max_items_raw = self._extract_assignment_value(command, keys=("max_items", "limit", "最大条数"))
        try:
            max_items = int(max_items_raw) if max_items_raw else None
        except ValueError:
            max_items = None
        if capability_id == AGENT_BATCH_FALLBACK_CAPABILITY_ID:
            scope_summary = {
                "capability_id": capability_id,
                "project_key": project_key,
                "command_preview": command[:240],
                "source_scope": "agent_batch_fallback",
            }
            execution_payload = {
                "capability_id": capability_id,
                "project_key": project_key,
                "command": command,
                "dry_run": False,
                "enable_bounded_retry": True,
                "enable_limited_branching": True,
                "risk_level": "medium",
                "approval_level": "medium",
                "budget": {"timeout_seconds": 900, "max_tasks": 8},
            }
            return {
                "contract_version": "interactive_agent.execution_preview.v1",
                "approval_id": approval_id,
                "capability_id": capability_id,
                "requires_confirmation": True,
                "candidates": [],
                "scope_summary": scope_summary,
                "execution_payload": execution_payload,
                "resume_context": {
                    "resume_token": f"{approval_id}:agent_batch.nl_command.submit",
                    "phase": "approval_wait",
                    "run_identifier": None,
                    "replay_capability_id": capability_id,
                },
                "impact": {
                    "writes": ["agent_batch_jobs", "agent_session_events", "project_artifacts"],
                    "external_network": True,
                    "cost_risk": True,
                },
            }
        if capability_id == "ingest.source_library.run":
            item_key = self._extract_source_item_key(command)
            if not item_key and candidates:
                item_key = str(candidates[0].get("item_key") or "").strip() or None
            override_params: dict[str, Any] = {}
            if time_window:
                override_params["time_window"] = time_window
            if max_items is not None:
                override_params["max_items"] = max_items
            scope_summary = {
                "capability_id": capability_id,
                "project_key": project_key,
                "candidate_count": len(candidates),
                "selected_item_key": item_key,
                "time_window": time_window,
                "max_items": max_items,
                "source_scope": "source_library",
            }
            execution_payload = {
                "capability_id": capability_id,
                "project_key": project_key,
                "item_key": item_key,
                "override_params": override_params,
                "time_window": time_window,
                "max_items": max_items,
                "source_scope": "source_library",
                "risk_level": "high",
                "approval_level": "high",
                "budget": {"timeout_seconds": 900, "max_items": max_items or 10},
            }
            resume_context = {
                "resume_token": f"{approval_id}:ingest.source_library.run",
                "phase": "approval_wait",
                "run_identifier": None,
                "replay_capability_id": capability_id,
            }
            return {
                "contract_version": "interactive_agent.execution_preview.v1",
                "approval_id": approval_id,
                "capability_id": capability_id,
                "requires_confirmation": True,
                "candidates": candidates[:8],
                "scope_summary": scope_summary,
                "execution_payload": execution_payload,
                "resume_context": resume_context,
                "impact": {
                    "writes": ["source_library_results", "ingest_artifacts", "agent_session_events"],
                    "external_network": True,
                    "cost_risk": True,
                },
            }
        if capability_id == "report.generate":
            topic = self._extract_assignment_value(command, keys=("topic", "主题")) or command.strip()
            output_path = (
                self._extract_assignment_value(command, keys=("output_path", "path", "输出路径", "文件"))
                or f"agent_reports/{approval_id}.md"
            )
            scope_summary = {
                "capability_id": capability_id,
                "project_key": project_key,
                "topic": topic[:200],
                "output_path": output_path,
                "source_scope": "session_artifacts",
            }
            execution_payload = {
                "capability_id": capability_id,
                "project_key": project_key,
                "topic": topic[:200],
                "section_titles": [],
                "sources": [],
                "output_path": output_path,
                "risk_level": "high",
                "approval_level": "high",
                "budget": {"timeout_seconds": 120, "max_sources": 20},
            }
            return {
                "contract_version": "interactive_agent.execution_preview.v1",
                "approval_id": approval_id,
                "capability_id": capability_id,
                "requires_confirmation": True,
                "candidates": [],
                "scope_summary": scope_summary,
                "execution_payload": execution_payload,
                "resume_context": {
                    "resume_token": f"{approval_id}:report.generate",
                    "phase": "approval_wait",
                    "run_identifier": None,
                    "replay_capability_id": capability_id,
                },
                "impact": {
                    "writes": [output_path, "agent_session_artifacts", "agent_session_events"],
                    "external_network": False,
                    "cost_risk": True,
                },
            }
        graph_id = self._extract_workflow_graph_id(command=command, binding_payload={})
        scope_summary = {
            "capability_id": capability_id,
            "project_key": project_key,
            "graph_id": graph_id,
            "source_scope": "workflow_graph",
        }
        execution_payload = {
            "capability_id": capability_id,
            "project_key": project_key,
            "graph_id": graph_id,
            "inputs": {},
            "risk_level": "high",
            "approval_level": "high",
            "budget": {"timeout_seconds": 900},
        }
        return {
            "contract_version": "interactive_agent.execution_preview.v1",
            "approval_id": approval_id,
            "capability_id": capability_id,
            "requires_confirmation": True,
            "candidates": [],
            "scope_summary": scope_summary,
            "execution_payload": execution_payload,
            "resume_context": {
                "resume_token": f"{approval_id}:workflow_graph.run",
                "phase": "approval_wait",
                "run_identifier": None,
                "replay_capability_id": capability_id,
            },
            "impact": {
                "writes": ["workflow_graph_runs", "agent_session_events"],
                "external_network": False,
                "cost_risk": True,
            },
        }

    @staticmethod
    def _source_library_candidates_from_calls(capability_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for call in capability_calls:
            if str(call.get("capability_id") or "") not in {"source_library.item.list", "source_library.item.search"}:
                continue
            for item in list(dict(call.get("result") or {}).get("items") or []):
                if not isinstance(item, dict):
                    continue
                key = str(item.get("item_key") or item.get("name") or "").strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                candidates.append(dict(item))
        return candidates

    @staticmethod
    def _extract_assignment_value(command: str, *, keys: tuple[str, ...]) -> str | None:
        tokens = str(command or "").replace("，", " ").replace(",", " ").split()
        lowered_keys = {key.lower() for key in keys}
        for index, token in enumerate(tokens):
            cleaned = token.strip("`'\"；;。()[]{}")
            if "=" in cleaned:
                key, value = cleaned.split("=", 1)
                if key.strip().lower() in lowered_keys and value.strip():
                    return value.strip().strip("`'\"；;。()[]{}")
            if cleaned.strip(":：").lower() in lowered_keys and index + 1 < len(tokens):
                return tokens[index + 1].strip("`'\"：:；;。()[]{}")
        return None

    def _execute_approved_high_risk_capability(
        self,
        *,
        approval: dict[str, Any],
        binding_payload: dict[str, Any],
        turn_id: str,
        session_id: str,
        task_id: str,
        capability_id: str,
        command: str,
        project_key: str | None,
    ) -> dict[str, Any]:
        del approval
        approval_id = str(binding_payload.get("resume_token") or "").split(":")[-1] or None
        try:
            if capability_id == "workflow_graph.run":
                execution_payload = dict(binding_payload.get("execution_payload") or {})
                graph_id = self._extract_workflow_graph_id(command=command, binding_payload={**binding_payload, **execution_payload})
                if not graph_id:
                    raise ValueError("graph_id is required to continue workflow_graph.run")
                from app.services.workflow_graph import runtime as workflow_graph_runtime

                inputs = dict(execution_payload.get("inputs") or binding_payload.get("inputs") or binding_payload.get("input") or {})
                result = workflow_graph_runtime.run(
                    {
                        "graph_id": graph_id,
                        "input": inputs,
                        "project_key": project_key,
                    }
                )
                return build_capability_call(
                    turn_id=turn_id,
                    capability_id=capability_id,
                    protocol="approval_gated",
                    status="completed",
                    summary=f"workflow graph run started: {result.get('run_id') or graph_id}",
                    result=result,
                    extra={"approval_id": approval_id, "graph_id": graph_id, "run_id": result.get("run_id")},
                )
            if capability_id == "ingest.source_library.run":
                execution_payload = dict(binding_payload.get("execution_payload") or {})
                item_key = (
                    str(binding_payload.get("item_key") or "").strip()
                    or str(execution_payload.get("item_key") or "").strip()
                    or self._extract_source_item_key(command)
                )
                if not item_key:
                    raise ValueError("item_key is required to continue ingest.source_library.run")
                from app.services.collect_runtime import run_source_library_item_compat

                override_params = dict(execution_payload.get("override_params") or binding_payload.get("override_params") or {})
                result = run_source_library_item_compat(
                    item_key=item_key,
                    project_key=project_key,
                    override_params=override_params,
                )
                return build_capability_call(
                    turn_id=turn_id,
                    capability_id=capability_id,
                    protocol="approval_gated",
                    status="completed",
                    summary=f"source-library item executed: {item_key}",
                    result={"item_key": item_key, "output": result},
                    extra={
                        "approval_id": approval_id,
                        "item_key": item_key,
                        "run_identifier": result.get("run_id") or result.get("job_id") or item_key if isinstance(result, dict) else item_key,
                        "resume_context": dict(binding_payload.get("resume_context") or {}),
                    },
                )
            if capability_id == "report.generate":
                execution_payload = dict(binding_payload.get("execution_payload") or {})
                topic = (
                    str(binding_payload.get("topic") or "").strip()
                    or str(execution_payload.get("topic") or "").strip()
                    or command.strip()
                )
                output_path = (
                    str(binding_payload.get("output_path") or "").strip()
                    or str(execution_payload.get("output_path") or "").strip()
                )
                if not topic:
                    raise ValueError("topic is required to continue report.generate")
                if not output_path:
                    raise ValueError("output_path is required to continue report.generate")
                sources = list(binding_payload.get("sources") or execution_payload.get("sources") or [])
                if not sources:
                    sources = [
                        {
                            "id": "S1",
                            "title": "Current agent session context",
                            "url": f"agent-session://{session_id}",
                            "publisher": "agent_session",
                            "evidence": command,
                        }
                    ]
                section_titles = list(binding_payload.get("section_titles") or execution_payload.get("section_titles") or [])
                from app.services.llm_report_generator import build_structured_report, evaluate_report_gate, render_markdown

                report = build_structured_report(
                    topic=topic[:200],
                    sources=[dict(item or {}) for item in sources],
                    section_titles=[str(item) for item in section_titles] or None,
                )
                markdown = render_markdown(report)
                gate = evaluate_report_gate(report)
                artifact = self.service.store.upsert_artifact(
                    {
                        "session_id": session_id,
                        "task_id": task_id,
                        "artifact_type": "report.generate.markdown",
                        "name": output_path,
                        "mime_type": "text/markdown",
                        "content_text": markdown,
                        "content_json": {"report": report.to_dict(), "quality_gate": gate},
                        "metadata": {
                            "turn_id": turn_id,
                            "capability_id": capability_id,
                            "approval_id": approval_id,
                            "project_key": project_key,
                            "output_path": output_path,
                        },
                    }
                )
                return build_capability_call(
                    turn_id=turn_id,
                    capability_id=capability_id,
                    protocol="approval_gated",
                    status="completed",
                    summary=f"report draft generated: {output_path}",
                    result={
                        "topic": topic[:200],
                        "output_path": output_path,
                        "artifact_id": artifact.get("artifact_id"),
                        "quality_gate": gate,
                    },
                    extra={
                        "approval_id": approval_id,
                        "artifact_id": artifact.get("artifact_id"),
                        "run_identifier": artifact.get("artifact_id") or output_path,
                        "resume_context": dict(binding_payload.get("resume_context") or {}),
                    },
                )
            if capability_id == AGENT_BATCH_FALLBACK_CAPABILITY_ID:
                execution_payload = dict(binding_payload.get("execution_payload") or {})
                command_to_run = str(execution_payload.get("command") or binding_payload.get("command") or command).strip()
                if not command_to_run:
                    raise ValueError("command is required to continue agent_batch.nl_command.submit")
                from app.api.agent_batch import _submit_jobs_from_loop_tasks
                from app.services.agent_batch.agent_loop import run_agent_batch_nl_command_loop
                from app.services.agent_batch.executor_health import inspect_executor_health
                from app.services.agent_batch.planner import plan_batch_search_command

                result = run_agent_batch_nl_command_loop(
                    command=command_to_run,
                    project_key=project_key,
                    idempotency_key=f"interactive-agent-approved:{approval_id}:{_stable_hash({'command': command_to_run})}",
                    dry_run=bool(execution_payload.get("dry_run", False)),
                    enable_bounded_retry=bool(execution_payload.get("enable_bounded_retry", True)),
                    enable_limited_branching=bool(execution_payload.get("enable_limited_branching", True)),
                    parser_fallback=plan_batch_search_command,
                    submitter=_submit_jobs_from_loop_tasks,
                    executor_snapshot=inspect_executor_health,
                )
                submit = dict(result.get("submit") or {})
                job_id = submit.get("job_id")
                summary = f"agent_batch fallback submitted: {job_id}" if job_id else "agent_batch fallback completed"
                return build_capability_call(
                    turn_id=turn_id,
                    capability_id=capability_id,
                    protocol="approval_gated",
                    status="completed",
                    summary=summary,
                    result=result,
                    extra={
                        "approval_id": approval_id,
                        "job_id": job_id,
                        "loop_id": result.get("loop_id"),
                        "run_identifier": job_id or result.get("loop_id"),
                        "resume_context": dict(binding_payload.get("resume_context") or {}),
                    },
                )
            return build_capability_call(
                turn_id=turn_id,
                capability_id=capability_id,
                protocol="approval_gated",
                status="skipped",
                summary="approved capability has no direct executor yet",
                result={"capability_id": capability_id},
                extra={"approval_id": approval_id},
            )
        except Exception as exc:  # noqa: BLE001
            return build_capability_call(
                turn_id=turn_id,
                capability_id=capability_id,
                protocol="approval_gated",
                status="failed",
                summary=f"approved capability failed: {exc}",
                error={"type": exc.__class__.__name__, "message": str(exc)},
                result={},
                extra={"approval_id": approval_id},
            )

    def _find_turn_task_id(self, *, session_id: str, turn_id: str, role: str) -> str | None:
        for task in self.service.list_tasks(session_id):
            metadata = dict(task.get("metadata") or {})
            if str(metadata.get("interactive_turn_id") or "") != turn_id:
                continue
            if str(metadata.get("interactive_turn_role") or "") == role:
                return str(task.get("task_id") or "").strip() or None
        return None

    @staticmethod
    def _build_control_tool_input(*, capability_id: str, command: str, session_id: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"session_id": session_id, "reason": command}
        if capability_id == "task.retry":
            task_id = InteractiveAgentRuntime._extract_task_id(command)
            if task_id:
                payload["task_id"] = task_id
        return payload

    @staticmethod
    def _extract_task_id(command: str) -> str | None:
        for token in str(command or "").replace("，", " ").replace(",", " ").split():
            cleaned = token.strip("`'\"：:；;。()[]{}")
            if cleaned.startswith(("ast-", "task-", "t-")):
                return cleaned
        return None

    @staticmethod
    def _build_approval_continuation_answer(
        *,
        capability_id: str,
        approval_id: str,
        capability_call: dict[str, Any],
        execution_completed: bool,
    ) -> str:
        status = str(capability_call.get("status") or "-")
        summary = str(capability_call.get("summary") or "-")
        lines = [
            f"审批已处理：{approval_id}。",
            f"继续执行能力：{capability_id}。",
            f"执行状态：{status}。",
            f"结果摘要：{summary}",
        ]
        if not execution_completed and capability_call.get("error"):
            error = dict(capability_call.get("error") or {})
            lines.append(f"错误：{error.get('message') or error.get('type') or 'unknown'}")
            lines.append("当前 session 已保留失败状态，可修正参数后重试或重新发起审批。")
        else:
            lines.append("执行结果已经写入当前 agent session 的 tasks/events/artifacts。")
        return "\n".join(lines)

    @staticmethod
    def _extract_workflow_graph_id(*, command: str, binding_payload: dict[str, Any]) -> str | None:
        for key in ("graph_id", "workflow_graph_id", "workflow_id"):
            value = str(binding_payload.get(key) or "").strip()
            if value:
                return value
        tokens = str(command or "").replace("，", " ").replace(",", " ").split()
        markers = {"graph", "workflow_graph", "workflow", "工作流"}
        for index, token in enumerate(tokens):
            cleaned = token.strip("`'\"：:；;。()[]{}").lower()
            if cleaned in markers:
                for raw_candidate in tokens[index + 1 : index + 4]:
                    candidate = raw_candidate.strip("`'\"：:；;。()[]{}")
                    if candidate and candidate.lower() not in markers:
                        return candidate
            if cleaned in markers and index + 1 < len(tokens):
                candidate = tokens[index + 1].strip("`'\"：:；;。()[]{}")
                if candidate and candidate.lower() not in markers:
                    return candidate
        for token in tokens:
            cleaned = token.strip("`'\"：:；;。()[]{}")
            if "_" in cleaned and len(cleaned) >= 3:
                return cleaned
        return None

    @staticmethod
    def _build_delegated_capability_call(
        *,
        capability_id: str,
        turn_id: str,
        delegated: bool,
        dry_run: bool,
        approval_request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if dry_run:
            status = "skipped"
            summary = "dry-run: high-risk capability was selected but not executed"
        elif approval_request:
            status = "needs_approval"
            summary = f"approval requested: {approval_request.get('approval_id')}"
        elif delegated:
            status = "delegated"
            summary = "delegated to the governed agent_batch execution path"
        else:
            status = "needs_approval"
            summary = "high-risk capability selected; direct execution requires an approval-gated executor"
        return {
            "contract_version": "interactive_agent.capability_call.v1",
            "turn_id": turn_id,
            "capability_id": capability_id,
            "status": status,
            "summary": summary,
            "approval_id": approval_request.get("approval_id") if approval_request else None,
            "result": {
                "delegated_to": "agent_batch.nl_command.submit" if delegated else None,
                "approval": approval_request,
            },
        }

    @staticmethod
    def _summarize_capability_calls(calls: list[dict[str, Any]]) -> str:
        if not calls:
            return "No capability calls were required"
        completed = sum(1 for call in calls if str(call.get("status") or "") in {"completed", "delegated"})
        failed = sum(1 for call in calls if str(call.get("status") or "") == "failed")
        blocked = sum(1 for call in calls if str(call.get("status") or "") == "needs_approval")
        return f"Capability dispatch complete: total={len(calls)}, completed_or_delegated={completed}, failed={failed}, needs_approval={blocked}"

    def _build_capability_call(
        self,
        *,
        capability_id: str,
        turn_id: str,
        idempotency_key: str,
        loop_result: dict[str, Any],
    ) -> dict[str, Any]:
        submit = dict(loop_result.get("submit") or {})
        plan = dict(loop_result.get("plan") or {})
        summary = "agent_batch nl-command completed"
        if submit.get("job_id"):
            summary = f"agent_batch job dispatched: {submit.get('job_id')}"
        return {
            "contract_version": "interactive_agent.capability_call.v1",
            "turn_id": turn_id,
            "capability_id": capability_id,
            "status": "completed",
            "idempotency_key": idempotency_key,
            "summary": summary,
            "job_id": submit.get("job_id"),
            "accepted_count": submit.get("accepted_count"),
            "rejected_count": submit.get("rejected_count"),
            "loop_id": loop_result.get("loop_id"),
            "plan_summary": {
                "intent": plan.get("intent"),
                "task_count": len(list(plan.get("tasks") or [])),
                "retrieval_mode": (plan.get("search_brief") or {}).get("retrieval_mode"),
            },
        }

    @staticmethod
    def _build_suggested_next_actions(
        *,
        plan: dict[str, Any],
        capability_calls: list[dict[str, Any]],
        agent_mode: str,
    ) -> list[str]:
        call_ids = {str(call.get("capability_id") or "") for call in capability_calls}
        if agent_mode == "conversation" and not capability_calls:
            return []
        if agent_mode in {"conversation", "read_only"}:
            return [
                "如果要从只读查看切换到执行，请直接说明采集、分析或生成目标。",
                "输入“当前状态”可读取本会话任务、事件和工件。",
                "也可以点名 source_library item_key、artifact 名称或项目范围继续追问。",
            ]
        actions = ["继续补充约束或说“继续”，我会复用当前 session 上下文。"]
        if "source_library.item.list" in call_ids:
            actions.append("如果来源库候选不合适，可以点名 item_key 或要求切换采集来源。")
        if any(str(call.get("status") or "") == "needs_approval" for call in capability_calls):
            actions.append("存在需要审批的高风险能力，可先确认执行边界后再继续。")
        selected = [str(item.get("capability_id") or "") for item in list(plan.get("selected_capabilities") or [])]
        if "workflow_graph.run" in selected:
            actions.append("若要实际跑 workflow，请补充 graph_id 和输入参数。")
        return actions

    def _build_final_answer(
        self,
        *,
        command: str,
        plan: dict[str, Any],
        loop_result: dict[str, Any],
        run_loop_result: dict[str, Any],
        dry_run: bool,
        capability_calls: list[dict[str, Any]],
        agent_mode: str,
        suggested_next_actions: list[str],
        context_summary: dict[str, Any] | None = None,
        conversation_answerer: AgentConversationAnswerer | None = None,
    ) -> str:
        turn_decision = dict(plan.get("turn_decision") or {})
        direct_answer = str(turn_decision.get("direct_answer") or "").strip()
        clarifying_question = str(turn_decision.get("clarifying_question") or "").strip()
        decision_action = str(turn_decision.get("action") or "").strip()
        answer_source = str(turn_decision.get("answer_source") or "direct").strip()
        requires_model_answer = bool(turn_decision.get("requires_model_answer"))
        if agent_mode == "conversation" and not capability_calls and decision_action == "answer_direct" and direct_answer:
            return direct_answer
        if (
            agent_mode == "conversation"
            and not capability_calls
            and decision_action == "answer_direct"
            and (requires_model_answer or answer_source == "model")
        ):
            try:
                answer_payload = (conversation_answerer or ModelConversationAnswerer()).answer(
                    message=command,
                    project_key=str(plan.get("project_key") or "").strip() or None,
                    context_summary=dict(context_summary or {}),
                    turn_decision=turn_decision,
                )
                model_answer = str(answer_payload.get("answer") or "").strip()
                if model_answer:
                    return model_answer
            except Exception as exc:  # noqa: BLE001
                return self._model_answer_failure_message(exc)
        if agent_mode == "conversation" and not capability_calls and decision_action == "ask_clarification":
            return clarifying_question or direct_answer or "请补充你希望我直接回答、读取现有项目上下文，还是执行受审批保护的任务。"
        if agent_mode == "conversation" and not capability_calls and decision_action == "decline_or_safe_complete":
            return direct_answer or "这个请求当前不能安全执行；我可以改为只读解释或帮你收窄执行边界。"
        if agent_mode == "conversation" and is_social_chat_goal(command):
            return (
                "你好。我在这里，可以直接用普通对话回答问题，也可以在需要时读取当前项目、来源库、workflow、"
                "artifact 和会话状态。只有你明确要求采集、生成、执行或写入时，我才会进入审批或任务执行流程。"
            )

        submit = dict(loop_result.get("submit") or {})
        model_final_answer = str(dict(run_loop_result or {}).get("model_final_answer") or "").strip()
        selected_ids = [str(item.get("capability_id") or "") for item in list(plan.get("selected_capabilities") or [])]
        if model_final_answer:
            lines = [
                model_final_answer,
            ]
        else:
            opening = "我已基于当前会话完成本轮处理。"
            if agent_mode in {"conversation", "read_only"}:
                opening = "我已基于当前会话和只读工具完成查询。"
            elif any(str(call.get("status") or "") == "needs_approval" for call in capability_calls):
                opening = "我已把需要确认的执行边界整理成审批请求。"
            lines = [opening]
        if agent_mode == "conversation":
            lines.append("本轮是工具/状态类对话，没有提交项目执行 job。")
        elif agent_mode == "read_only":
            lines.append("本轮只读取能力、项目、来源库或会话上下文，没有提交项目执行任务。")
        elif dry_run:
            lines.append("当前是 dry-run，只完成计划和能力解析，没有提交外部执行。")
        elif any(str(call.get("status") or "") == "needs_approval" for call in capability_calls):
            lines.append("本轮已生成高风险能力审批请求，等待确认后再继续执行。")
        elif submit.get("job_id"):
            lines.append(f"已通过 agent_batch 调用项目执行链路，job_id={submit.get('job_id')}。")
        else:
            lines.append("已完成计划解析；本轮未产生可提交的批处理 job。")

        fact_lines = self._build_read_only_fact_lines(capability_calls)
        if fact_lines:
            lines.append("读取结果:")
            lines.extend(f"- {item}" for item in fact_lines)

        if capability_calls:
            lines.append("工具调用轨迹:")
            for call in capability_calls:
                lines.append(
                    f"- {call.get('capability_id')}: {call.get('status')}; {call.get('summary') or '-'}"
                )

        accepted = submit.get("accepted_count")
        rejected = submit.get("rejected_count")
        if accepted is not None or rejected is not None:
            lines.append(f"调度结果: accepted={accepted or 0}, rejected={rejected or 0}。")
        if suggested_next_actions:
            lines.append("可继续:")
            lines.extend(f"- {item}" for item in suggested_next_actions)
        lines.append("后续进度可通过当前 agent session 的 tasks/events/artifacts 或 SSE stream 继续观察。")
        return "\n".join(lines)

    @staticmethod
    def _model_answer_failure_message(exc: Exception) -> str:
        if exc.__class__.__name__ == "TimeoutExpired":
            return "模型自由回答暂时超时。你可以继续提问；如果问题涉及当前项目数据、来源库、artifact 或 workflow，我会优先改走只读检索工具。"
        return "模型自由回答暂时不可用。你可以继续提问；涉及项目上下文的问题我会优先使用只读检索工具。"

    @staticmethod
    def _build_read_only_fact_lines(capability_calls: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []
        for call in capability_calls:
            capability_id = str(call.get("capability_id") or "")
            result = dict(call.get("result") or {})
            if capability_id == "agent_runtime.capability.catalog":
                items = list(result.get("items") or [])
                names = [str(item.get("capability_id") or "") for item in items[:6] if isinstance(item, dict)]
                if names:
                    lines.append(f"当前 agent 暴露 {len(items)} 个能力，示例: {', '.join(names)}。")
            elif capability_id == "agent_runtime.tool_pool.list":
                counts = dict(result.get("counts") or {})
                groups = dict(result.get("groups") or {})
                approval_required = counts.get("approval_required") or 0
                core_preview = ", ".join(
                    str(item.get("capability_id") or item.get("tool_name") or "-")
                    for item in list(groups.get("core") or [])[:6]
                    if isinstance(item, dict)
                )
                lines.append(
                    f"工具池: core={counts.get('core') or 0}, deferred={counts.get('deferred') or 0}, "
                    f"disabled={counts.get('disabled') or 0}, approval_required={approval_required}"
                    + (f"，核心示例: {core_preview}" if core_preview else "")
                    + "。"
                )
            elif capability_id == "agent_runtime.tool.search":
                items = [item for item in list(result.get("items") or []) if isinstance(item, dict)]
                preview = ", ".join(str(item.get("capability_id") or item.get("tool_name") or "-") for item in items[:6])
                lines.append(
                    f"工具搜索匹配 total={result.get('total') or 0}"
                    + (f"，示例: {preview}" if preview else "")
                    + "。"
                )
            elif capability_id == "agent_session.context.read":
                lines.append(
                    "当前会话上下文: "
                    f"tasks={result.get('task_count') or 0}, "
                    f"events={result.get('event_count') or 0}, "
                    f"artifacts={result.get('artifact_count') or 0}。"
                )
                tool_results = [item for item in list(result.get("recent_tool_results") or []) if isinstance(item, dict)]
                failed_tool_results = [
                    item
                    for item in tool_results
                    if str(item.get("status") or "").lower() in {"failed", "error"}
                ]
                for item in failed_tool_results[-3:]:
                    error = dict(item.get("error") or {})
                    lines.append(
                        f"最近失败工具 {item.get('capability_id') or item.get('tool_name') or '-'}: "
                        f"{error.get('message') or item.get('summary') or 'unknown error'}。"
                    )
                if tool_results and not failed_tool_results:
                    latest = tool_results[-1]
                    lines.append(
                        f"最近工具结果 {latest.get('capability_id') or latest.get('tool_name') or '-'}: "
                        f"{latest.get('status') or '-'}; {latest.get('summary') or '-'}。"
                    )
            elif capability_id == "project.summary.read":
                source = dict(result.get("source_library") or {})
                channels = dict(source.get("channels") or {})
                channel_preview = ", ".join(f"{key}:{value}" for key, value in list(channels.items())[:5])
                lines.append(
                    f"项目 {result.get('project_key') or '-'} 来源库: total={source.get('total') or 0}, "
                    f"enabled={source.get('enabled') or 0}"
                    + (f", channels={channel_preview}" if channel_preview else "")
                    + "。"
                )
            elif capability_id == "project.structured_data.search":
                inventory = [item for item in list(result.get("inventory") or []) if isinstance(item, dict)]
                preview = ", ".join(
                    f"{item.get('dataset')}={item.get('total_rows') if item.get('total_rows') is not None else item.get('sample_count')}"
                    for item in inventory[:8]
                    if item.get("dataset")
                )
                samples = [item for item in list(result.get("items") or []) if isinstance(item, dict)]
                sample_preview = ", ".join(str(item.get("title") or item.get("record_id") or "-") for item in samples[:4])
                lines.append(
                    f"结构化数据模式={result.get('query_mode') or 'search'}，datasets={preview or '暂无可见样本'}，"
                    f"stored_rows={result.get('total_stored_rows') or 0}，samples={result.get('total_matches') or 0}"
                    + (f"，示例: {sample_preview}" if sample_preview else "")
                    + "。"
                )
            elif capability_id == "project.context.bundle":
                categories = dict(result.get("material_categories") or {})
                existing = dict(categories.get("internal_existing") or {})
                generated = dict(categories.get("internal_generated") or {})
                source_catalog = dict(categories.get("source_catalog") or {})
                missing = list(result.get("missing_evidence") or [])
                lines.append(
                    "项目材料上下文: "
                    f"内部已有 structured_datasets={existing.get('structured_datasets') or 0}, "
                    f"stored_rows={existing.get('stored_rows') or 0}, "
                    f"writing_docs={existing.get('writing_documents') or 0}; "
                    f"内部生成 artifacts={generated.get('artifacts') or 0}; "
                    f"来源库/采集入口 items={source_catalog.get('items') or 0}"
                    + (f"，缺口={len(missing)}" if missing else "")
                    + "。"
                )
            elif capability_id in {"source_library.item.list", "source_library.item.search"}:
                items = [item for item in list(result.get("items") or []) if isinstance(item, dict)]
                preview = ", ".join(
                    str(item.get("item_key") or item.get("name") or "-")
                    for item in items[:6]
                )
                lines.append(
                    f"来源库匹配 total={result.get('total') or 0}"
                    + (f"，示例: {preview}" if preview else "")
                    + "。"
                )
            elif capability_id == "source_library.item.inspect":
                item = result.get("item")
                if isinstance(item, dict):
                    lines.append(f"来源库条目 {item.get('item_key') or '-'}: channel={item.get('channel_key') or '-'}。")
            elif capability_id == "agent_artifact.search":
                lines.append(f"当前会话产物匹配 total={result.get('total') or 0}。")
            elif capability_id == "agent_artifact.read":
                artifact = result.get("artifact")
                if isinstance(artifact, dict):
                    lines.append(f"读取产物: {artifact.get('name') or artifact.get('artifact_type') or artifact.get('artifact_id') or '-'}。")
            elif capability_id == "workflow_graph.list":
                lines.append(
                    "Workflow graph: "
                    f"compiled={result.get('total_compiled') or 0}, "
                    f"templates={result.get('total_templates') or 0}。"
                )
            elif capability_id == "workflow_graph.inspect":
                graph = result.get("graph")
                if isinstance(graph, dict):
                    lines.append(
                        f"Workflow graph {graph.get('graph_id') or result.get('graph_id') or '-'}: "
                        f"nodes={graph.get('node_count') or 0}, "
                        f"edges={graph.get('edge_count') or 0}, "
                        f"version={graph.get('version') or '-'}。"
                    )
                elif str(call.get("status") or "") == "failed":
                    error = dict(call.get("error") or {})
                    lines.append(
                        f"Workflow graph {result.get('graph_id') or '-'} inspect failed: "
                        f"{error.get('message') or call.get('summary') or 'unknown error'}。"
                    )
            elif capability_id == "ingest.status.read":
                counts = dict(result.get("job_status_counts") or {})
                count_preview = ", ".join(f"{key}:{value}" for key, value in sorted(counts.items())[:5])
                lines.append(
                    f"Ingest/source-library recent status: jobs={len(list(result.get('recent_jobs') or []))}, "
                    f"session_tasks={len(list(result.get('recent_session_tasks') or []))}"
                    + (f", status={count_preview}" if count_preview else "")
                    + "。"
                )
        return lines

    def _fail_turn(
        self,
        *,
        session_id: str,
        execute_task_id: str,
        final_task_id: str,
        turn_id: str,
        message: str,
        error: Exception,
        plan: dict[str, Any] | None = None,
        capability_calls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        error_payload = {"turn_id": turn_id, "error": str(error), "error_type": error.__class__.__name__}
        calls = list(capability_calls or [])
        self.service.release_task(
            session_id,
            execute_task_id,
            status="failed",
            result_summary=f"Capability execution failed: {error}",
            result_payload={**error_payload, "capability_calls": calls},
            activity="capability execution failed",
        )
        final_answer = f"交互式 agent 已创建会话，但执行项目能力时失败: {error}"
        self.service.release_task(
            session_id,
            final_task_id,
            status="failed",
            result_summary=final_answer,
            result_payload={"turn_id": turn_id, "message": message, "error": error_payload, "capability_calls": calls},
            activity="final answer failed",
        )
        self.service.create_message(
            session_id,
            role="assistant",
            actor="interactive_agent",
            task_id=final_task_id,
            content=final_answer,
            metadata={"turn_id": turn_id, "error": error_payload, "capability_calls": calls},
        )
        self.service.store.append_event(
            session_id,
            event_type="interactive_agent.failed",
            task_id=execute_task_id,
            payload=error_payload,
        )
        bundle = self.service.get_session_bundle(session_id)
        return {
            "contract_version": self.contract_version,
            "turn": {"turn_id": turn_id, "message": message, "failed": True},
            "session": bundle["session"],
            "tasks": bundle["tasks"],
            "messages": bundle["messages"],
            "events": bundle["events"],
            "artifacts": bundle["artifacts"],
            "approvals": bundle["approvals"],
            "agent_mode": "execute",
            "plan": plan or {},
            "capability_calls": calls,
            "suggested_next_actions": ["修正约束后重试，或先查看 session events/artifacts 定位失败点。"],
            "loop_result": {},
            "final_answer": final_answer,
        }
