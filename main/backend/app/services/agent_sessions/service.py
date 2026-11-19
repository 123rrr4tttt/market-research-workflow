from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from functorial_kit import Failure
from mrw_functorial_kit.core.agent_service_semantics import agent_session_failures
from sqlalchemy.engine import Engine

from app.services.agent_runtime import (
    build_summary_label,
    build_task_progress_summary,
    find_unresolved_dependencies,
    resolve_session_status,
)
from .store import (
    AgentEventPayload,
    AgentEventRecord,
    AgentArtifactPayload,
    AgentApprovalPayload,
    AgentApprovalTransitionMutation,
    AgentMessagePayload,
    AgentSessionPayload,
    AgentSessionRecord,
    AgentSessionStore,
    AgentTaskPayload,
    AgentTaskTransitionMutation,
    InMemoryAgentSessionStore,
    JsonObject,
    SqlAgentSessionStore,
    build_agent_session_store,
    validate_json_object,
)

TASK_STATUSES = frozenset({"pending", "claimed", "in_progress", "blocked", "completed", "failed", "canceled", "expired"})
TASK_PHASES = frozenset({"conversation", "research", "synthesis", "implementation", "verification", "maintenance"})
EXECUTION_MODES = frozenset({"worker", "system"})
FINAL_TASK_STATUSES = frozenset({"completed", "failed", "canceled", "expired"})
FAILURE_PACKAGE_SCHEMA_VERSION = "agent_failure_package.v1"
_HOST_CONFIRMATION_ID_RE = r"approval:(?P<approval_id>[A-Za-z0-9._:-]+)"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16]}"


def _failure(code: str, message: str, **context: Any) -> Failure:
    return agent_session_failures.fail(code, message, context or None)


def _host_failure(code: str, **context: Any) -> Failure:
    family_code = "session_not_found" if code.endswith("session_mismatch") else "status_invalid"
    return _failure(family_code, code.replace("_", " "), host_code=code, **context)


def _confirmation_failure(failure: Failure) -> Failure:
    context = dict(failure.context or {})
    host_code = str(context.get("host_code") or "")
    approval_id = context.get("approval_id")
    if failure.code == "approval_not_found":
        return _failure("approval_not_found", failure.message, approval_id=approval_id)
    if host_code == "host_confirmation_scope_mismatch":
        return _host_failure("host_confirmation_scope_mismatch", approval_id=approval_id)
    return _host_failure("host_confirmation_not_pending", approval_id=approval_id, status=context.get("status"))


def _reconcile_confirmation(
    approval: dict[str, Any],
    requested_decision: str,
    approval_id: str,
) -> dict[str, Any] | Failure:
    metadata = dict(approval.get("metadata") or {})
    previous_decision = str(dict(metadata.get("host_confirmation") or {}).get("decision") or "").strip()
    if not previous_decision:
        return _host_failure("host_confirmation_not_pending", approval_id=approval_id, status=approval.get("status"))
    if previous_decision != requested_decision:
        return _host_failure(
            "host_confirmation_decision_conflict",
            approval_id=approval_id,
            previous_decision=previous_decision,
            requested_decision=requested_decision,
        )
    out = dict(approval)
    out["requested_status"] = "approved" if requested_decision == "approved" else "failed"
    out["final_status"] = str(approval.get("status") or "")
    out["action_status"] = "already_final"
    out["resolution_status"] = "already_final"
    return out


def _normalize_status(value: str, *, allowed: frozenset[str], default: str) -> str | Failure:
    candidate = str(value or "").strip().lower()
    if not candidate:
        return default
    if candidate not in allowed:
        return _failure("status_invalid", f"unsupported status: {candidate}", value=candidate)
    return candidate


def _normalize_phase(value: str | None) -> str | Failure:
    candidate = str(value or "").strip().lower() or "research"
    if candidate not in TASK_PHASES:
        return _failure("phase_invalid", f"unsupported phase: {candidate}", value=candidate)
    return candidate


def _normalize_execution_mode(value: str | None) -> str | Failure:
    candidate = str(value or "").strip().lower() or "worker"
    if candidate not in EXECUTION_MODES:
        return _failure("execution_mode_invalid", f"unsupported execution_mode: {candidate}", value=candidate)
    return candidate


def _normalize_string_list(values: Iterable[object] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in out:
            out.append(item)
    return out


def _open_record(value: Mapping[str, Any]) -> dict[str, Any]:
    return dict(value)


def _open_records(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [_open_record(value) for value in values]


def _hash_binding(binding: dict[str, Any]) -> str:
    body = json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class AgentSessionService:
    store: AgentSessionStore

    def __init__(self, *, store: InMemoryAgentSessionStore | SqlAgentSessionStore | None = None) -> None:
        resolved_store = store if store is not None else build_agent_session_store()
        if isinstance(resolved_store, Failure):
            self._initialization_failure: Failure | None = resolved_store
            return
        self._initialization_failure = None
        self.store = resolved_store

    def _store_failure(self) -> Failure | None:
        return self._initialization_failure

    def list_sessions(self, *, limit: int = 50) -> list[dict[str, Any]] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        out: list[dict[str, Any]] = []
        for item in self.store.list_sessions(limit=limit):
            session_id = str(item.get("session_id") or "")
            tasks = self.store.list_tasks(session_id) if session_id else []
            if isinstance(tasks, Failure):
                return tasks
            events = self.store.list_events(session_id) if session_id else []
            if isinstance(events, Failure):
                return events
            artifacts = self.store.list_artifacts(session_id) if session_id else []
            if isinstance(artifacts, Failure):
                return artifacts
            out.append(
                self._decorate_session(
                    _open_record(item),
                    tasks=_open_records(tasks),
                    task_count=len(tasks),
                    event_count=len(events),
                    artifact_count=len(artifacts),
                    approval_count=len(self.store.list_approvals(session_id=session_id)) if session_id else 0,
                )
            )
        return out

    def get_session(self, session_id: str) -> dict[str, Any] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        tasks = self.store.list_tasks(session_id)
        if isinstance(tasks, Failure):
            return tasks
        session = self.store.get_session(session_id)
        if isinstance(session, Failure):
            return session
        return self._decorate_session(
            _open_record(session), tasks=_open_records(tasks), task_count=len(tasks)
        )

    def list_tasks(self, session_id: str) -> list[dict[str, Any]] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        rows = self.store.list_tasks(session_id)
        if isinstance(rows, Failure):
            return rows
        tasks = [self._decorate_task(_open_record(task)) for task in rows]
        return tasks

    def list_events(self, session_id: str) -> list[AgentEventRecord] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        rows = self.store.list_events(session_id)
        return rows

    def list_artifacts(self, session_id: str) -> list[dict[str, Any]] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        rows = self.store.list_artifacts(session_id)
        return rows if isinstance(rows, Failure) else _open_records(rows)

    def list_messages(self, session_id: str) -> list[dict[str, Any]] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        rows = self.store.list_messages(session_id)
        return rows if isinstance(rows, Failure) else _open_records(rows)

    def list_approvals(self, *, session_id: str | None = None) -> list[dict[str, Any]] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        return _open_records(self.store.list_approvals(session_id=session_id))

    def get_session_summary(self, session_id: str) -> dict[str, Any] | Failure:
        session = self.get_session(session_id)
        if isinstance(session, Failure):
            return session
        tasks = self.list_tasks(session_id)
        if isinstance(tasks, Failure):
            return tasks
        messages = self.list_messages(session_id)
        if isinstance(messages, Failure):
            return messages
        events = self.list_events(session_id)
        if isinstance(events, Failure):
            return events
        artifacts = self.list_artifacts(session_id)
        if isinstance(artifacts, Failure):
            return artifacts
        approvals = self.list_approvals(session_id=session_id)
        if isinstance(approvals, Failure):
            return approvals

        task_counts: dict[str, int] = {}
        completed_results: list[dict[str, Any]] = []
        for task in tasks:
            status = str(task.get("status") or "unknown")
            task_counts[status] = task_counts.get(status, 0) + 1
            if status == "completed":
                completed_results.append(
                    {
                        "task_id": task.get("task_id"),
                        "phase": task.get("phase"),
                        "summary": task.get("result_summary") or task.get("summary_label"),
                    }
                )

        approval_counts: dict[str, int] = {}
        for approval in approvals:
            status = str(approval.get("status") or "unknown")
            approval_counts[status] = approval_counts.get(status, 0) + 1

        latest = messages[-1] if messages else None
        latest_message = None
        if latest is not None:
            latest_message = {
                "message_id": latest.get("message_id"),
                "role": latest.get("role"),
                "actor": latest.get("actor"),
                "created_at": latest.get("created_at"),
                "content": latest.get("content"),
            }
        return {
            "session_id": session.get("session_id"),
            "goal": session.get("goal"),
            "status": session.get("status"),
            "current_phase": session.get("current_phase"),
            "progress": session.get("progress"),
            "task_counts": task_counts,
            "artifact_count": len(artifacts),
            "approval_counts": approval_counts,
            "latest_message": latest_message,
            "completed_results": completed_results,
        }

    def export_failure_package(
        self,
        session_id: str,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        session_id = str(session_id or "").strip()
        task_id = str(task_id or "").strip() or None
        run_id = str(run_id or "").strip() or None
        try:
            session = self.store.get_session(session_id)
            tasks = self.store.list_tasks(session_id)
            events = self.store.list_events(session_id)
        except KeyError:
            return self._empty_failure_package(
                session_id=session_id,
                task_id=task_id,
                run_id=run_id,
                export_status="not_found",
                reason_code="session_not_found",
            )
        if isinstance(session, Failure):
            return self._empty_failure_package(
                session_id=session_id,
                task_id=task_id,
                run_id=run_id,
                export_status="not_found",
                reason_code=session.code,
            )
        if isinstance(tasks, Failure):
            return self._empty_failure_package(
                session_id=session_id,
                task_id=task_id,
                run_id=run_id,
                export_status="not_found",
                reason_code=tasks.code,
            )
        if isinstance(events, Failure):
            return self._empty_failure_package(
                session_id=session_id,
                task_id=task_id,
                run_id=run_id,
                export_status="not_found",
                reason_code=events.code,
            )

        session_record = _open_record(session)
        task_records = _open_records(tasks)
        event_records = _open_records(events)

        selected_task = self._select_failure_package_task(task_records, task_id=task_id, run_id=run_id)
        if selected_task is None and task_id:
            return self._empty_failure_package(
                session_id=session_id,
                task_id=task_id,
                run_id=run_id,
                export_status="not_found",
                reason_code="task_not_found",
                project_key=session_record.get("project_key"),
            )
        if selected_task is None and run_id and self._session_run_id(session_record) != run_id:
            return self._empty_failure_package(
                session_id=session_id,
                task_id=task_id,
                run_id=run_id,
                export_status="not_found",
                reason_code="run_not_found",
                project_key=session_record.get("project_key"),
            )

        failed_tasks = [task for task in task_records if str(task.get("status") or "") == "failed"]
        package_tasks = [selected_task] if selected_task is not None else failed_tasks
        session_failed = str(session_record.get("status") or "") == "failed"
        if selected_task is not None and str(selected_task.get("status") or "") != "failed":
            return self._empty_failure_package(
                session_id=session_id,
                task_id=str(selected_task.get("task_id") or task_id or ""),
                run_id=run_id or self._task_run_id(selected_task) or self._session_run_id(session_record),
                export_status="not_failed",
                reason_code="task_not_failed",
                project_key=session_record.get("project_key"),
            )
        if not package_tasks and not session_failed:
            return self._empty_failure_package(
                session_id=session_id,
                task_id=task_id,
                run_id=run_id or self._session_run_id(session_record),
                export_status="not_failed",
                reason_code="session_not_failed",
                project_key=session_record.get("project_key"),
            )

        scoped_events = self._scope_failure_events(event_records, tasks=package_tasks)
        last_event = scoped_events[-1] if scoped_events else (event_records[-1] if event_records else None)
        resolved_run_id = (
            run_id
            or self._first_non_empty([self._task_run_id(task) for task in package_tasks])
            or self._session_run_id(session_record)
        )
        resolved_task_id = str(package_tasks[0].get("task_id") or "") if len(package_tasks) == 1 else task_id
        trace_id = self._first_non_empty(
            [self._task_trace_id(task) for task in package_tasks]
            + [self._event_trace_id(event) for event in reversed(scoped_events)]
            + [self._session_trace_id(session_record)]
        )
        errors = self._collect_failure_errors(package_tasks, scoped_events=scoped_events, session=session_record)
        failed_steps = [self._failure_step_from_task(task) for task in package_tasks]
        if not failed_steps and session_failed:
            failed_steps.append(
                {
                    "scope": "session",
                    "status": str(session_record.get("status") or ""),
                    "summary": str(session_record.get("final_summary") or "").strip() or None,
                }
            )

        failure_package = {
            "session_id": session_id,
            "run_id": resolved_run_id,
            "task_id": resolved_task_id,
            "project_key": session_record.get("project_key"),
            "trace_id": trace_id,
            "failed_steps": failed_steps,
            "errors": errors,
            "retry_hint": self._build_failure_retry_hint(
                session_id=session_id,
                task=package_tasks[0] if len(package_tasks) == 1 else None,
            ),
            "last_event": last_event,
            "export_schema_version": FAILURE_PACKAGE_SCHEMA_VERSION,
        }
        return {
            "export_status": "ok",
            "reason_code": None,
            "failure_package": failure_package,
        }

    def find_session_by_compat_job_id(self, compat_job_id: str) -> AgentSessionRecord | None | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        item = self.store.find_session_by_compat_job_id(compat_job_id)
        return item

    def find_session_by_logical_task_list_key(
        self, logical_task_list_key: str
    ) -> AgentSessionRecord | None | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        item = self.store.find_session_by_logical_task_list_key(logical_task_list_key)
        return item

    def create_session(
        self,
        *,
        source: str,
        entrypoint_type: str,
        goal: str,
        project_key: str | None = None,
        initial_context: dict[str, Any] | None = None,
        compat_mode: bool = False,
        compat_job_id: str | None = None,
        logical_task_list_key: str | None = None,
        metadata: dict[str, Any] | None = None,
        task_blueprints: Sequence[Mapping[str, Any]] | None = None,
        _command_artifacts: list[AgentArtifactPayload] | None = None,
        _command_events: list[AgentEventPayload] | None = None,
    ) -> dict[str, Any] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        session_id = _new_id("as")
        session_metadata = dict(metadata or {})
        if initial_context:
            session_metadata.setdefault("initial_context", dict(initial_context))
        blueprints = list(task_blueprints or [])
        normalized_blueprints = self._materialize_blueprints(goal=goal, blueprints=blueprints)
        if isinstance(normalized_blueprints, Failure):
            return normalized_blueprints
        root_task_id = str(normalized_blueprints[0].get("task_id") or "") if normalized_blueprints else None
        session_payload: AgentSessionPayload = {
            "session_id": session_id,
            "source": str(source or "user").strip() or "user",
            "project_key": (project_key or "").strip() or None,
            "entrypoint_type": str(entrypoint_type or "chat").strip() or "chat",
            "goal": str(goal or "").strip(),
            "status": "pending",
            "current_phase": (
                str(normalized_blueprints[0].get("phase") or "research")
                if normalized_blueprints
                else "conversation"
            ),
            "compat_mode": bool(compat_mode),
            "compat_job_id": (compat_job_id or "").strip() or None,
            "logical_task_list_key": (logical_task_list_key or session_id).strip() or session_id,
            "root_task_id": root_task_id,
            "metadata": session_metadata,
            "final_result": {},
        }
        for blueprint in normalized_blueprints:
            blueprint["session_id"] = session_id
        command_artifacts = list(_command_artifacts or [])
        for artifact in command_artifacts:
            artifact["session_id"] = session_id
        creation_events: list[AgentEventPayload] = [
            {
                "event_type": "session.created",
                "payload": {
                    "source": session_payload["source"],
                    "entrypoint_type": session_payload["entrypoint_type"],
                    "compat_mode": session_payload["compat_mode"],
                    "root_task_id": session_payload["root_task_id"],
                },
            },
            *[
                {
                    "event_type": "task.created",
                    "task_id": str(task.get("task_id") or ""),
                    "payload": {
                        "phase": str(task.get("phase") or ""),
                        "task_type": str(task.get("task_type") or ""),
                        "blocked_by": list(task.get("blocked_by") or []),
                        "write_set": list(task.get("write_set") or []),
                    },
                }
                for task in normalized_blueprints
            ],
        ]
        created = self.store.commit_session_command(
            session_id,
            session_create=session_payload,
            expected_session_statuses=None,
            session_changes=self._derive_session_changes(
                _open_record(session_payload),
                [_open_record(task) for task in normalized_blueprints],
            ),
            task_creates=normalized_blueprints,
            task_mutations=[],
            message_creates=[
                {
                    "session_id": session_id,
                    "role": "user",
                    "actor": "session_entrypoint",
                    "content": str(goal or "").strip(),
                    "metadata": {"entrypoint_type": entrypoint_type, "source": source},
                }
            ],
            artifact_upserts=command_artifacts,
            approval_mutation=None,
            events=[*creation_events, *list(_command_events or [])],
        )
        if isinstance(created, Failure):
            return created
        return self.get_session_bundle(session_id)

    def get_session_bundle(self, session_id: str) -> dict[str, Any] | Failure:
        session = self.get_session(session_id)
        if isinstance(session, Failure):
            return session
        tasks = self.list_tasks(session_id)
        if isinstance(tasks, Failure):
            return tasks
        messages = self.list_messages(session_id)
        if isinstance(messages, Failure):
            return messages
        artifacts = self.list_artifacts(session_id)
        if isinstance(artifacts, Failure):
            return artifacts
        events = self.list_events(session_id)
        if isinstance(events, Failure):
            return events
        approvals = self.list_approvals(session_id=session_id)
        if isinstance(approvals, Failure):
            return approvals
        return {
            "session": session,
            "tasks": tasks,
            "messages": messages,
            "artifacts": artifacts,
            "events": events,
            "approvals": approvals,
        }

    def create_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        actor: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        session = self.store.get_session(session_id)
        if isinstance(session, Failure):
            return session
        message_metadata = validate_json_object(metadata or {}, field="message.metadata")
        if isinstance(message_metadata, Failure):
            return message_metadata
        message_payload: AgentMessagePayload = {
            "session_id": session_id,
            "task_id": task_id,
            "role": str(role or "assistant").strip() or "assistant",
            "actor": str(actor or role or "assistant").strip() or "assistant",
            "content": str(content or "").strip(),
            "metadata": message_metadata,
        }
        committed = self.store.commit_session_command(
            session_id,
            session_create=None,
            expected_session_statuses=[str(session.get("status") or "")],
            session_changes={},
            task_creates=[],
            task_mutations=[],
            message_creates=[message_payload],
            artifact_upserts=[],
            approval_mutation=None,
            events=[
                {
                    "event_type": "message.created",
                    "task_id": task_id,
                    "payload": {
                        "role": message_payload["role"],
                        "actor": message_payload["actor"],
                    },
                }
            ],
        )
        if isinstance(committed, Failure):
            return committed
        return _open_record(committed["messages"][0])

    def create_host_user_message(
        self,
        context: Any,
        *,
        content: str,
        approval_id: str | None = None,
        attachments: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | Failure:
        """Record a user message at the trusted host input boundary only."""

        if (failure := self._store_failure()) is not None:
            return failure

        from app.services.agent_core.host_authorization import (
            HOST_AUTHORIZATION_CONTRACT_VERSION,
            validate_context,
        )

        context_failure = validate_context(context)
        if isinstance(context_failure, Failure):
            return context_failure
        metadata: dict[str, Any] = {
            "contract_version": HOST_AUTHORIZATION_CONTRACT_VERSION,
            "host_message": {
                "project_key": context.project_key,
                "session_id": context.session_id,
                "host_thread_id": context.host_thread_id,
                "turn_id": context.turn_id,
                "user_message_id": context.user_message_id,
            },
        }
        if attachments:
            metadata["host_message"]["attachments"] = [dict(item) for item in attachments]
        if approval_id is not None:
            metadata["host_confirmation"] = {"approval_id": str(approval_id).strip()}
        return self.create_message(
            context.session_id,
            role="user",
            content=str(content or "").strip(),
            actor=f"trusted_host:{context.host_thread_id}",
            metadata=metadata,
        )

    def record_host_tool_confirmation(
        self,
        context: Any,
        *,
        approval_id: str,
        content: str,
        approved: bool = True,
    ) -> dict[str, Any] | Failure:
        """Resolve one host approval from an explicitly associated user message."""

        if (failure := self._store_failure()) is not None:
            return failure

        from app.services.agent_core.host_authorization import (
            HOST_AUTHORIZATION_CONTRACT_VERSION,
            validate_context,
        )

        normalized_approval_id = str(approval_id or "").strip()
        if not normalized_approval_id:
            return _failure("approval_id_required", "approval_id is required")
        context_failure = validate_context(context)
        if isinstance(context_failure, Failure):
            return context_failure
        approval = self.store.get_approval(normalized_approval_id)
        if isinstance(approval, Failure):
            return approval
        if str(approval.get("requester_session_id") or "") != context.session_id:
            return _host_failure("host_confirmation_session_mismatch", approval_id=normalized_approval_id)
        binding = dict(approval.get("binding_payload") or {})
        if (
            binding.get("project_key") != context.project_key
            or binding.get("session_id") != context.session_id
            or binding.get("host_thread_id") != context.host_thread_id
            or approval.get("requester_actor") != f"trusted_host:{context.host_thread_id}"
        ):
            return _host_failure("host_confirmation_scope_mismatch", approval_id=normalized_approval_id)
        text = str(content or "").strip()
        match = re.search(_HOST_CONFIRMATION_ID_RE, text)
        if match is None or match.group("approval_id") != normalized_approval_id:
            return _host_failure("host_confirmation_action_invalid", approval_id=normalized_approval_id)
        if not approved and not re.search(r"\b(?:reject|deny|拒绝)\b", text, flags=re.IGNORECASE):
            return _host_failure("host_rejection_decision_invalid", approval_id=normalized_approval_id)
        requested_decision = "approved" if approved else "rejected"

        if str(approval.get("status") or "") != "pending":
            return _reconcile_confirmation(_open_record(approval), requested_decision, normalized_approval_id)

        approved_by = f"trusted_host:{context.host_thread_id}"
        confirmation_metadata = validate_json_object(
            {
                "contract_version": HOST_AUTHORIZATION_CONTRACT_VERSION,
                "host_confirmation": {
                    "approval_id": normalized_approval_id,
                    "user_message_id": context.user_message_id,
                    "host_thread_id": context.host_thread_id,
                    "turn_id": context.turn_id,
                    "decision": requested_decision,
                },
            },
            field="approval.confirmation.metadata",
        )
        if isinstance(confirmation_metadata, Failure):
            return confirmation_metadata
        approval_metadata = dict(approval.get("metadata") or {})
        approval_metadata.update(confirmation_metadata)
        normalized_approval_metadata = validate_json_object(
            approval_metadata,
            field="approval.metadata",
        )
        if isinstance(normalized_approval_metadata, Failure):
            return normalized_approval_metadata
        audit_entry = validate_json_object(
            {
                "at": _utcnow().isoformat(),
                "action": "approved" if approved else "rejected",
                "actor": approved_by,
            },
            field="approval.audit_log.entry",
        )
        if isinstance(audit_entry, Failure):
            return audit_entry
        audit_log: list[JsonObject] = [
            *list(approval.get("audit_log") or []),
            audit_entry,
        ]
        confirmed_status = "approved" if approved else "failed"
        approval_payload: AgentApprovalPayload = {
            **approval,
            "status": confirmed_status,
            "approved_by": approved_by,
            "approved_at": _utcnow(),
            "metadata": normalized_approval_metadata,
            "audit_log": audit_log,
        }
        requester_session_id = str(approval.get("requester_session_id") or "").strip()
        if not requester_session_id:
            return _host_failure("host_confirmation_session_mismatch", approval_id=normalized_approval_id)
        session = self.store.get_session(requester_session_id)
        if isinstance(session, Failure):
            return session
        tasks = self.store.list_tasks(requester_session_id)
        if isinstance(tasks, Failure):
            return tasks
        requester_task_id = str(approval.get("requester_task_id") or "").strip() or None
        post_tasks = _open_records(tasks)
        mutations: list[AgentTaskTransitionMutation] = []
        for index, task in enumerate(tasks):
            is_wait = (
                str(task.get("task_type") or "") == "approval_wait"
                and str(dict(task.get("metadata") or {}).get("approval_id") or "") == normalized_approval_id
            )
            is_gated = requester_task_id is not None and task["task_id"] == requester_task_id
            if not is_wait and not is_gated:
                continue
            if is_wait:
                changes: AgentTaskPayload = {
                    "status": "completed" if approved else "failed",
                    "completed_at": _utcnow(),
                    "lease_until": None,
                    "last_activity": f"approval {normalized_approval_id} {'approved' if approved else 'rejected'}",
                    "recent_activities": [f"approval {normalized_approval_id} {'approved' if approved else 'rejected'}"],
                }
            elif approved:
                unresolved = find_unresolved_dependencies(_open_record(task), _open_records(tasks))
                changes = {
                    "status": "blocked" if unresolved else "pending",
                    "last_activity": f"approval {normalized_approval_id} approved",
                    "recent_activities": [f"approval {normalized_approval_id} approved"],
                }
            else:
                changes = {
                    "status": "failed",
                    "completed_at": _utcnow(),
                    "last_activity": f"approval {normalized_approval_id} rejected",
                    "recent_activities": [f"approval {normalized_approval_id} rejected"],
                }
            projected_task = {**_open_record(task), **changes}
            changes["summary_label"] = build_summary_label(projected_task)
            post_tasks[index].update(changes)
            mutations.append(
                {
                    "task_id": task["task_id"],
                    "expected_statuses": [str(task.get("status") or "")],
                    "expected_owner": task.get("owner"),
                    "changes": changes,
                }
            )
        message_metadata = validate_json_object(
            {
                "contract_version": HOST_AUTHORIZATION_CONTRACT_VERSION,
                "host_message": {
                    "project_key": context.project_key,
                    "session_id": context.session_id,
                    "host_thread_id": context.host_thread_id,
                    "turn_id": context.turn_id,
                    "user_message_id": context.user_message_id,
                },
                "host_confirmation": {"approval_id": normalized_approval_id},
            },
            field="host_confirmation.message.metadata",
        )
        if isinstance(message_metadata, Failure):
            return message_metadata
        committed = self.store.commit_session_command(
            requester_session_id,
            session_create=None,
            expected_session_statuses=[str(session.get("status") or "")],
            session_changes=self._derive_session_changes(_open_record(session), post_tasks),
            task_creates=[],
            task_mutations=mutations,
            message_creates=[
                {
                    "session_id": requester_session_id,
                    "role": "user",
                    "actor": approved_by,
                    "content": text,
                    "metadata": message_metadata,
                }
            ],
            artifact_upserts=[],
            approval_mutation={
                "expected_statuses": ["pending"],
                "expected_binding_payload": approval["binding_payload"],
                "expected_requester_actor": approved_by,
                "payload": approval_payload,
            },
            events=[
                {
                    "event_type": "message.created",
                    "payload": {"role": "user", "actor": approved_by},
                },
                {
                    "event_type": f"approval.{confirmed_status}",
                    "task_id": requester_task_id,
                    "payload": {
                        "approval_id": normalized_approval_id,
                        "approved_by": approved_by,
                    },
                },
            ],
        )
        if isinstance(committed, Failure):
            fresh = self.store.get_approval(normalized_approval_id)
            if not isinstance(fresh, Failure) and str(fresh.get("status") or "") != "pending":
                return _reconcile_confirmation(_open_record(fresh), requested_decision, normalized_approval_id)
            return _confirmation_failure(committed)
        confirmed = committed["approval"]
        if confirmed is None:
            return _failure("approval_not_found", "approval confirmation did not return a record")
        row = dict(confirmed)
        row["requested_status"] = "approved" if approved else "failed"
        row["final_status"] = str(row.get("status") or "")
        row["action_status"] = "resolved"
        row["resolution_status"] = "resolved"
        return row

    def append_task_blueprints(
        self,
        session_id: str,
        *,
        goal: str | None = None,
        task_blueprints: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        session = self.store.get_session(session_id)
        if isinstance(session, Failure):
            return session
        materialized = self._materialize_blueprints(
            goal=str(goal or session.get("goal") or "").strip(),
            blueprints=list(task_blueprints or []),
        )
        if isinstance(materialized, Failure):
            return materialized
        for blueprint in materialized:
            blueprint["session_id"] = session_id
        existing_tasks = self.store.list_tasks(session_id)
        if isinstance(existing_tasks, Failure):
            return existing_tasks
        post_tasks = [*_open_records(existing_tasks), *[_open_record(item) for item in materialized]]
        committed = self.store.commit_session_command(
            session_id,
            session_create=None,
            expected_session_statuses=[str(session.get("status") or "")],
            session_changes=self._derive_session_changes(_open_record(session), post_tasks),
            task_creates=materialized,
            task_mutations=[],
            message_creates=[],
            artifact_upserts=[],
            approval_mutation=None,
            events=[
                {
                    "event_type": "task.created",
                    "task_id": str(task.get("task_id") or ""),
                    "payload": {
                        "phase": str(task.get("phase") or ""),
                        "task_type": str(task.get("task_type") or ""),
                        "blocked_by": list(task.get("blocked_by") or []),
                        "write_set": list(task.get("write_set") or []),
                    },
                }
                for task in materialized
            ],
        )
        if isinstance(committed, Failure):
            return committed
        return [self._decorate_task(_open_record(task)) for task in committed["tasks"]]

    def cancel_run(
        self,
        run_id: str,
        *,
        actor_id: str,
        project_key: str,
        engine: Engine | None = None,
        reason: str = "explicit_cancel",
    ) -> Mapping[str, Any] | Failure:
        """Request platform cancellation through the current runtime command."""

        from app.successor_runtime.runtime.ports import RuntimeScope
        from app.successor_runtime.substrate.postgres.runtime_journal import (
            RuntimeJournalRepository,
        )
        from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
            RequestCancel,
            RuntimeLifecycleRepository,
        )
        from app.successor_runtime.substrate.postgres.session import (
            ServerProjectScopeResolver,
        )

        if engine is None:
            from app.models.base import engine as default_engine

            engine = default_engine
        with engine.begin() as connection:
            project_scope = ServerProjectScopeResolver(
                connection=connection
            ).resolve(project_key)
            scope = RuntimeScope(project_scope=project_scope, actor_id=actor_id)
            run = RuntimeJournalRepository(connection, scope).load_run(
                run_id, for_update=True
            )
            return RuntimeLifecycleRepository(connection, scope).request_cancel(
                RequestCancel(
                    run_id=run_id,
                    expected_run_revision=int(run["revision"]),
                    reason=reason,
                )
            )

    def read_run_cancellation(
        self,
        run_id: str,
        *,
        project_key: str,
        actor_id: str,
        engine: Engine | None = None,
    ) -> bool:
        """Read cancellation from the canonical run and its journal projection."""

        from app.successor_runtime.runtime.ports import RuntimeScope
        from app.successor_runtime.substrate.postgres.runtime_journal import (
            RuntimeJournalRepository,
        )
        from app.successor_runtime.substrate.postgres.session import (
            ServerProjectScopeResolver,
        )
        from app.successor_runtime.substrate.projections.agent_session import (
            PostgresAgentSessionReadAdapter,
            SessionStatus,
        )
        from app.successor_runtime.substrate.projections.runtime_run import (
            RuntimeJournalSource,
        )

        if engine is None:
            from app.models.base import engine as default_engine

            engine = default_engine
        with engine.connect() as connection:
            project_scope = ServerProjectScopeResolver(connection=connection).resolve(
                project_key
            )
            scope = RuntimeScope(project_scope=project_scope, actor_id=actor_id)
            run = RuntimeJournalRepository(connection, scope).load_run(run_id)
            snapshot = PostgresAgentSessionReadAdapter(connection, scope).load(
                RuntimeJournalSource(
                    run_id=run_id,
                    run_incarnation=str(run["incarnation"]),
                    source_ref=f"runtime-run:{run_id}",
                )
            )
        return (
            bool(run["cancellation_requested"])
            or str(run["state"]) in {"CANCELLING", "CANCELLED"}
            or snapshot.status is SessionStatus.CANCELED
            or "CancellationRequested" in snapshot.observed_event_types
            or any(task.step_state.value == "CANCEL_REQUESTED" for task in snapshot.tasks)
        )

    def create_or_update_approval(
        self,
        *,
        approval_id: str,
        binding_payload: dict[str, Any],
        requester_session_id: str | None,
        requester_task_id: str | None,
        requester_actor: str,
        expires_at: datetime | None,
        status: str = "pending",
        approved_by: str | None = None,
        approved_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        audit_log: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        normalized_status = _normalize_status(status, allowed=TASK_STATUSES | {"approved", "pending"}, default="pending")
        if isinstance(normalized_status, Failure):
            return normalized_status
        binding = validate_json_object(binding_payload, field="approval.binding_payload")
        if isinstance(binding, Failure):
            return binding
        approval_metadata = validate_json_object(metadata or {}, field="approval.metadata")
        if isinstance(approval_metadata, Failure):
            return approval_metadata
        normalized_audit_log: list[JsonObject] = []
        for index, entry in enumerate(audit_log or []):
            normalized_entry = validate_json_object(
                entry,
                field=f"approval.audit_log.{index}",
            )
            if isinstance(normalized_entry, Failure):
                return normalized_entry
            normalized_audit_log.append(normalized_entry)
        approval_payload: AgentApprovalPayload = {
            "approval_id": str(approval_id or "").strip(),
            "binding_hash": _hash_binding(binding_payload),
            "binding_payload": binding,
            "requester_session_id": requester_session_id,
            "requester_task_id": requester_task_id,
            "requester_actor": str(requester_actor or "unknown").strip() or "unknown",
            "approved_by": approved_by,
            "approved_at": approved_at,
            "expires_at": expires_at,
            "status": normalized_status,
            "metadata": approval_metadata,
            "audit_log": normalized_audit_log,
        }
        return self._commit_approval_request(
            approval_payload,
            extra_events=[
                {
                    "event_type": f"approval.{normalized_status}",
                    "task_id": requester_task_id,
                    "payload": {
                        "approval_id": approval_payload["approval_id"],
                        "expires_at": str(expires_at or "") or None,
                    },
                }
            ],
        )

    def request_approval(
        self,
        *,
        session_id: str,
        task_id: str,
        binding_payload: dict[str, Any],
        requester_actor: str,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        task = self.store.get_task(session_id, task_id)
        if isinstance(task, Failure):
            return task
        approval_id = str((metadata or {}).get("approval_id") or _new_id("approval")).strip()
        gated_metadata: JsonObject | None = None
        if not self._requires_approval_for_task(_open_record(task)):
            task_metadata = dict(task.get("metadata") or {})
            if dict(metadata or {}).get("force_approval"):
                task_metadata["concurrency_class"] = "write_external"
                validated_task_metadata = validate_json_object(
                    task_metadata,
                    field="approval.gated_task.metadata",
                )
                if isinstance(validated_task_metadata, Failure):
                    return validated_task_metadata
                gated_metadata = validated_task_metadata
        binding = validate_json_object(binding_payload, field="approval.binding_payload")
        if isinstance(binding, Failure):
            return binding
        approval_metadata = validate_json_object(metadata or {}, field="approval.metadata")
        if isinstance(approval_metadata, Failure):
            return approval_metadata
        audit_entry = validate_json_object(
            {
                "action": "requested",
                "actor": requester_actor,
                "at": _utcnow().isoformat(),
            },
            field="approval.audit_log.entry",
        )
        if isinstance(audit_entry, Failure):
            return audit_entry
        approval_payload: AgentApprovalPayload = {
            "approval_id": approval_id,
            "binding_hash": _hash_binding(binding_payload),
            "binding_payload": binding,
            "requester_session_id": session_id,
            "requester_task_id": task_id,
            "requester_actor": str(requester_actor or "unknown").strip() or "unknown",
            "expires_at": expires_at,
            "status": "pending",
            "metadata": approval_metadata,
            "audit_log": [audit_entry],
        }
        row = self._commit_approval_request(
            approval_payload,
            extra_events=[
                {
                    "event_type": "approval.pending",
                    "task_id": task_id,
                    "payload": {
                        "approval_id": approval_id,
                        "expires_at": str(expires_at or "") or None,
                    },
                },
                {
                    "event_type": "approval.requested",
                    "task_id": task_id,
                    "payload": {
                        "approval_id": approval_id,
                        "binding_hash": approval_payload["binding_hash"],
                    },
                },
            ],
            gated_metadata=gated_metadata,
        )
        return row

    def resolve_approval(
        self,
        approval_id: str,
        *,
        approved_by: str,
        approved: bool = True,
    ) -> dict[str, Any] | Failure:
        if (failure := self._store_failure()) is not None:
            return failure
        current = self.store.get_approval(approval_id)
        if isinstance(current, Failure):
            return current
        requested_status = "approved" if approved else "failed"
        current_status = str(current.get("status") or "").strip().lower()
        if current_status in {"approved", "failed"}:
            out = dict(current)
            out["requested_status"] = requested_status
            out["final_status"] = current_status
            out["action_status"] = "already_final" if current_status == requested_status else "conflict"
            out["resolution_status"] = out["action_status"]
            return out
        audit_log = list(current.get("audit_log") or [])
        audit_log.append(
            {
                "at": _utcnow().isoformat(),
                "action": "approved" if approved else "rejected",
                "actor": str(approved_by or "unknown").strip() or "unknown",
            }
        )
        approval_payload: AgentApprovalPayload = {
            **current,
            "status": requested_status,
            "approved_by": str(approved_by or "unknown").strip() or "unknown",
            "approved_at": _utcnow(),
            "audit_log": audit_log,
        }
        requester_session_id = str(current.get("requester_session_id") or "").strip() or None
        if requester_session_id:
            session = self.store.get_session(requester_session_id)
            if isinstance(session, Failure):
                return session
            tasks = self.store.list_tasks(requester_session_id)
            if isinstance(tasks, Failure):
                return tasks
            post_tasks = _open_records(tasks)
            mutations: list[AgentTaskTransitionMutation] = []
            requester_task_id = str(current.get("requester_task_id") or "").strip() or None
            for index, task in enumerate(tasks):
                is_wait = (
                    str(task.get("task_type") or "") == "approval_wait"
                    and str(dict(task.get("metadata") or {}).get("approval_id") or "") == approval_id
                )
                is_gated = requester_task_id is not None and task["task_id"] == requester_task_id
                if not is_wait and not is_gated:
                    continue
                if is_wait:
                    changes: AgentTaskPayload = {
                        "status": "completed" if approved else "failed",
                        "completed_at": _utcnow(),
                        "lease_until": None,
                        "last_activity": f"approval {approval_id} {'approved' if approved else 'rejected'}",
                        "recent_activities": [f"approval {approval_id} {'approved' if approved else 'rejected'}"],
                    }
                elif approved:
                    unresolved = find_unresolved_dependencies(_open_record(task), _open_records(tasks))
                    changes = {
                        "status": "blocked" if unresolved else "pending",
                        "last_activity": f"approval {approval_id} approved",
                        "recent_activities": [f"approval {approval_id} approved"],
                    }
                else:
                    changes = {
                        "status": "failed",
                        "completed_at": _utcnow(),
                        "last_activity": f"approval {approval_id} rejected",
                        "recent_activities": [f"approval {approval_id} rejected"],
                    }
                projected_task = {**_open_record(task), **changes}
                changes["summary_label"] = build_summary_label(projected_task)
                post_tasks[index].update(changes)
                mutations.append(
                    {
                        "task_id": task["task_id"],
                        "expected_statuses": [str(task.get("status") or "")],
                        "expected_owner": task.get("owner"),
                        "changes": changes,
                    }
                )
            committed = self.store.commit_session_command(
                requester_session_id,
                session_create=None,
                expected_session_statuses=[str(session.get("status") or "")],
                session_changes=self._derive_session_changes(_open_record(session), post_tasks),
                task_creates=[],
                task_mutations=mutations,
                message_creates=[],
                artifact_upserts=[],
                approval_mutation={
                    "expected_statuses": [current_status],
                    "expected_binding_payload": current["binding_payload"],
                    "expected_requester_actor": current["requester_actor"],
                    "payload": approval_payload,
                },
                events=[
                    {
                        "event_type": f"approval.{requested_status}",
                        "task_id": requester_task_id,
                        "payload": {
                            "approval_id": approval_id,
                            "approved_by": approval_payload["approved_by"],
                        },
                    }
                ],
            )
            if isinstance(committed, Failure):
                return committed
            row = committed["approval"]
            if row is None:
                return _failure("approval_not_found", f"approval not found: {approval_id}", approval_id=approval_id)
        else:
            stored = self.store.create_or_update_approval(approval_payload)
            if isinstance(stored, Failure):
                return stored
            row = stored
        row = dict(row)
        row["requested_status"] = requested_status
        row["final_status"] = str(row.get("status") or "")
        row["action_status"] = "resolved"
        row["resolution_status"] = "resolved"
        return row

    @staticmethod
    def _empty_failure_package(
        *,
        session_id: str,
        task_id: str | None = None,
        run_id: str | None = None,
        export_status: str,
        reason_code: str,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        return {
            "export_status": export_status,
            "reason_code": reason_code,
            "failure_package": None,
            "empty_package": {
                "session_id": session_id,
                "run_id": run_id,
                "task_id": task_id,
                "project_key": project_key,
                "export_schema_version": FAILURE_PACKAGE_SCHEMA_VERSION,
            },
        }

    def _select_failure_package_task(
        self,
        tasks: list[dict[str, Any]],
        *,
        task_id: str | None,
        run_id: str | None,
    ) -> dict[str, Any] | None:
        if task_id:
            return next(
                (
                    task
                    for task in tasks
                    if str(task.get("task_id") or "") == task_id
                    or str(dict(task.get("metadata") or {}).get("task_id") or "") == task_id
                ),
                None,
            )
        if run_id:
            return next((task for task in tasks if self._task_matches_run_id(task, run_id)), None)
        return None

    @classmethod
    def _task_matches_run_id(cls, task: dict[str, Any], run_id: str) -> bool:
        return run_id in {
            str(value or "").strip()
            for value in (
                cls._task_run_id(task),
                dict(task.get("metadata") or {}).get("workflow_run_id"),
                dict(task.get("metadata") or {}).get("run_id"),
                dict(task.get("result_payload") or {}).get("workflow_run_id"),
                dict(task.get("result_payload") or {}).get("run_id"),
            )
            if str(value or "").strip()
        }

    @staticmethod
    def _first_non_empty(values: list[Any]) -> str | None:
        for value in values:
            candidate = str(value or "").strip()
            if candidate:
                return candidate
        return None

    @classmethod
    def _session_run_id(cls, session: dict[str, Any]) -> str | None:
        metadata = dict(session.get("metadata") or {})
        workflow_graph = dict(metadata.get("workflow_graph") or {})
        agent_batch = dict(metadata.get("agent_batch") or {})
        return cls._first_non_empty(
            [
                workflow_graph.get("run_id"),
                agent_batch.get("run_id"),
                session.get("logical_task_list_key"),
                session.get("compat_job_id"),
            ]
        )

    @classmethod
    def _session_trace_id(cls, session: dict[str, Any]) -> str | None:
        metadata = dict(session.get("metadata") or {})
        initial_context = dict(metadata.get("initial_context") or {})
        return cls._first_non_empty([metadata.get("trace_id"), initial_context.get("trace_id")])

    @classmethod
    def _task_run_id(cls, task: dict[str, Any]) -> str | None:
        metadata = dict(task.get("metadata") or {})
        result_payload = dict(task.get("result_payload") or {})
        task_spec = dict(task.get("task_spec") or {})
        context = dict(task_spec.get("context") or {})
        workflow_node = dict(metadata.get("workflow_graph_node") or {})
        return cls._first_non_empty(
            [
                metadata.get("run_id"),
                metadata.get("workflow_run_id"),
                workflow_node.get("run_id"),
                result_payload.get("run_id"),
                result_payload.get("workflow_run_id"),
                context.get("run_id"),
            ]
        )

    @classmethod
    def _task_trace_id(cls, task: dict[str, Any]) -> str | None:
        metadata = dict(task.get("metadata") or {})
        result_payload = dict(task.get("result_payload") or {})
        task_spec = dict(task.get("task_spec") or {})
        context = dict(task_spec.get("context") or {})
        return cls._first_non_empty(
            [
                metadata.get("trace_id"),
                result_payload.get("trace_id"),
                context.get("trace_id"),
            ]
        )

    @staticmethod
    def _event_trace_id(event: dict[str, Any]) -> str | None:
        payload = dict(event.get("payload") or {})
        return str(payload.get("trace_id") or "").strip() or None

    @staticmethod
    def _scope_failure_events(events: list[dict[str, Any]], *, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        task_ids = {str(task.get("task_id") or "") for task in tasks if str(task.get("task_id") or "")}
        if not task_ids:
            return list(events)
        return [event for event in events if str(event.get("task_id") or "") in task_ids]

    def _collect_failure_errors(
        self,
        tasks: list[dict[str, Any]],
        *,
        scoped_events: list[dict[str, Any]],
        session: dict[str, Any],
    ) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        for task in tasks:
            task_id = str(task.get("task_id") or "")
            result_payload = dict(task.get("result_payload") or {})
            for key in ("error", "errors", "exception", "error_code", "reason", "reason_code"):
                if key not in result_payload:
                    continue
                value: Any = result_payload.get(key)
                items: list[Any] = value
                if isinstance(value, list):
                    for item in items:
                        errors.append({"source": f"task.result_payload.{key}", "task_id": task_id, "detail": item})
                else:
                    errors.append({"source": f"task.result_payload.{key}", "task_id": task_id, "detail": value})
            result_summary = str(task.get("result_summary") or "").strip()
            if result_summary:
                errors.append({"source": "task.result_summary", "task_id": task_id, "message": result_summary})
        for event in scoped_events:
            payload = dict(event.get("payload") or {})
            for key in ("error", "errors", "exception", "reason", "reason_code"):
                if key in payload:
                    errors.append(
                        {
                            "source": f"event.payload.{key}",
                            "task_id": event.get("task_id"),
                            "event_type": event.get("event_type"),
                            "detail": payload.get(key),
                        }
                    )
        final_result = dict(session.get("final_result") or {})
        if not errors and final_result:
            errors.append({"source": "session.final_result", "detail": final_result})
        return errors

    @classmethod
    def _failure_step_from_task(cls, task: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": task.get("task_id"),
            "subject": task.get("subject"),
            "phase": task.get("phase"),
            "status": task.get("status"),
            "summary": task.get("result_summary"),
            "last_activity": task.get("last_activity"),
            "completed_at": task.get("completed_at"),
            "run_id": cls._task_run_id(task),
            "trace_id": cls._task_trace_id(task),
        }

    @staticmethod
    def _build_failure_retry_hint(*, session_id: str, task: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "retryable": False,
            "reason": "runtime_owner_required" if task is not None else "session_level_failure",
            "next_action": "inspect_runtime_run" if task is not None else "inspect_failed_steps",
        }

    def _commit_approval_request(
        self,
        approval_payload: AgentApprovalPayload,
        *,
        extra_events: list[AgentEventPayload],
        gated_metadata: JsonObject | None = None,
    ) -> dict[str, Any] | Failure:
        requester_session_id = str(approval_payload.get("requester_session_id") or "").strip()
        if not requester_session_id:
            row = self.store.create_or_update_approval(approval_payload)
            return row if isinstance(row, Failure) else _open_record(row)
        session = self.store.get_session(requester_session_id)
        if isinstance(session, Failure):
            return session
        tasks = self.store.list_tasks(requester_session_id)
        if isinstance(tasks, Failure):
            return tasks
        approval_id = str(approval_payload.get("approval_id") or "").strip()
        existing_approval = self.store.get_approval(approval_id)
        expected_approval_statuses: list[str] = []
        if not isinstance(existing_approval, Failure):
            expected_approval_statuses = [str(existing_approval.get("status") or "")]
        elif existing_approval.code != "approval_not_found":
            return existing_approval
        requester_task_id = str(approval_payload.get("requester_task_id") or "").strip() or None
        task_creates: list[AgentTaskPayload] = []
        task_mutations: list[AgentTaskTransitionMutation] = []
        post_tasks = _open_records(tasks)
        existing_wait = next(
            (
                task
                for task in tasks
                if str(task.get("task_type") or "") == "approval_wait"
                and str(dict(task.get("metadata") or {}).get("approval_id") or "") == approval_id
            ),
            None,
        )
        command_events = list(extra_events)
        if requester_task_id and existing_wait is None:
            gated_index = next(
                (
                    index
                    for index, task in enumerate(tasks)
                    if task["task_id"] == requester_task_id
                ),
                None,
            )
            if gated_index is None:
                gated_task = None
            else:
                gated_task = tasks[gated_index]
            if (
                gated_task is not None
                and gated_index is not None
                and str(gated_task.get("status") or "") not in FINAL_TASK_STATUSES
            ):
                gated_changes: AgentTaskPayload = {
                    "status": "blocked",
                    "last_activity": f"waiting for approval {approval_id}",
                    "recent_activities": [f"waiting for approval {approval_id}"],
                    "summary_label": f"{gated_task['subject']} [blocked]",
                }
                if gated_metadata is not None:
                    gated_changes["metadata"] = gated_metadata
                task_mutations.append(
                    {
                        "task_id": requester_task_id,
                        "expected_statuses": [str(gated_task.get("status") or "")],
                        "expected_owner": gated_task.get("owner"),
                        "changes": gated_changes,
                    }
                )
                post_tasks[gated_index].update(gated_changes)
            wait_task_id = _new_id("task")
            if gated_task is None:
                wait_task_id = ""
            else:
                wait_task: AgentTaskPayload = {
                    "session_id": requester_session_id,
                    "task_id": wait_task_id,
                    "parent_task_id": requester_task_id,
                    "subject": f"Approval wait: {approval_id}",
                    "description": "Formal approval_wait blocker task projected into the task bus.",
                    "task_type": "approval_wait",
                    "phase": str(gated_task.get("phase") or "maintenance"),
                    "status": "in_progress" if str(approval_payload.get("status") or "") == "pending" else "completed",
                    "execution_mode": "system",
                    "blocked_by": [],
                    "blocks": [requester_task_id],
                    "priority": max(0, int(gated_task.get("priority") or 5) - 1),
                    "write_set": [],
                    "read_set": list(gated_task.get("write_set") or []),
                    "task_spec": {
                        "task_type": "approval_wait",
                        "goal": f"Wait for approval {approval_id}",
                        "context": {
                            "approval_id": approval_id,
                            "requester_task_id": requester_task_id,
                        },
                        "target_scope": requester_task_id,
                        "write_set": [],
                        "completion_criteria": ["Approval is resolved explicitly."],
                        "verification_steps": ["Confirm approval outcome is reflected in the gated task state."],
                        "artifact_targets": [],
                    },
                    "metadata": {
                        "approval_id": approval_id,
                        "gated_task_id": requester_task_id,
                    },
                    "last_activity": f"approval {approval_id} requested",
                    "recent_activities": [f"approval {approval_id} requested"],
                    "summary_label": f"Approval wait: {approval_id}",
                }
                task_creates.append(wait_task)
                post_tasks.append(_open_record(wait_task))
                command_events.append(
                    {
                        "event_type": "approval.waiting",
                        "task_id": wait_task_id,
                        "payload": {
                            "approval_id": approval_id,
                            "gated_task_id": requester_task_id,
                        },
                    }
                )
        approval_mutation: AgentApprovalTransitionMutation = {
            "expected_statuses": expected_approval_statuses,
            "payload": approval_payload,
        }
        if not isinstance(existing_approval, Failure):
            approval_mutation["expected_binding_payload"] = existing_approval["binding_payload"]
            approval_mutation["expected_requester_actor"] = existing_approval["requester_actor"]
        committed = self.store.commit_session_command(
            requester_session_id,
            session_create=None,
            expected_session_statuses=[str(session.get("status") or "")],
            session_changes=self._derive_session_changes(_open_record(session), post_tasks),
            task_creates=task_creates,
            task_mutations=task_mutations,
            message_creates=[],
            artifact_upserts=[],
            approval_mutation=approval_mutation,
            events=command_events,
        )
        if isinstance(committed, Failure):
            return committed
        approval = committed["approval"]
        if approval is None:
            return _failure("approval_not_found", f"approval not found: {approval_id}", approval_id=approval_id)
        return _open_record(approval)

    def _materialize_blueprints(
        self, *, goal: str, blueprints: Sequence[Mapping[str, Any]]
    ) -> list[AgentTaskPayload] | Failure:
        materialized: list[AgentTaskPayload] = []
        prev_task_id: str | None = None
        for blueprint in blueprints:
            task_id = str(blueprint.get("task_id") or _new_id("task")).strip()
            blocked_by = _normalize_string_list(blueprint.get("blocked_by"))
            blocked_refs = _normalize_string_list(blueprint.get("blocked_by_refs"))
            if "prev" in blocked_refs and prev_task_id:
                blocked_by.append(prev_task_id)
            phase = _normalize_phase(blueprint.get("phase"))
            if isinstance(phase, Failure):
                return phase
            status = _normalize_status(str(blueprint.get("status") or ("blocked" if blocked_by else "pending")), allowed=TASK_STATUSES, default="pending")
            if isinstance(status, Failure):
                return status
            if blocked_by and status == "pending":
                status = "blocked"
            execution_mode = _normalize_execution_mode(blueprint.get("execution_mode"))
            if isinstance(execution_mode, Failure):
                return execution_mode
            default_task_spec: dict[str, Any] = {
                "task_type": str(blueprint.get("task_type") or phase),
                "goal": goal,
                "context": {},
                "target_scope": "session",
                "write_set": _normalize_string_list(blueprint.get("write_set")),
                "completion_criteria": list(blueprint.get("completion_criteria") or []),
                "verification_steps": list(blueprint.get("verification_steps") or []),
                "artifact_targets": list(blueprint.get("artifact_targets") or []),
            }
            task_spec_source: Any = blueprint.get("task_spec") or default_task_spec
            task_spec: dict[str, Any] = dict(task_spec_source)
            task: AgentTaskPayload = {
                "task_id": task_id,
                "parent_task_id": blueprint.get("parent_task_id"),
                "subject": str(blueprint.get("subject") or blueprint.get("task_type") or phase).strip(),
                "description": blueprint.get("description"),
                "task_type": str(blueprint.get("task_type") or phase).strip(),
                "phase": phase,
                "status": status,
                "execution_mode": execution_mode,
                "owner": blueprint.get("owner"),
                "blocked_by": blocked_by,
                "blocks": [],
                "priority": int(blueprint.get("priority") or 5),
                "write_set": _normalize_string_list(blueprint.get("write_set")),
                "read_set": _normalize_string_list(blueprint.get("read_set")),
                "task_spec": task_spec,
                "metadata": dict(blueprint.get("metadata") or {}),
                "result_summary": blueprint.get("result_summary"),
                "result_payload": dict(blueprint.get("result_payload") or {}),
                "tool_use_count": int(blueprint.get("tool_use_count") or 0),
                "token_usage": int(blueprint.get("token_usage") or 0),
                "last_activity": blueprint.get("last_activity"),
                "recent_activities": list(blueprint.get("recent_activities") or []),
                "summary_label": blueprint.get("summary_label"),
            }
            task["summary_label"] = task["summary_label"] or build_summary_label(_open_record(task))
            materialized.append(task)
            prev_task_id = task_id
        task_ids = {str(item.get("task_id") or "") for item in materialized}
        for item in materialized:
            item["blocked_by"] = [dep for dep in list(item.get("blocked_by") or []) if dep in task_ids]
        blockers: dict[str, list[str]] = {str(item.get("task_id") or ""): [] for item in materialized}
        for item in materialized:
            for dep in list(item.get("blocked_by") or []):
                blockers.setdefault(str(dep), []).append(str(item.get("task_id") or ""))
        for item in materialized:
            item["blocks"] = blockers.get(str(item.get("task_id") or ""), [])
        return materialized

    @staticmethod
    def _derive_session_changes(
        session: dict[str, Any], tasks: list[dict[str, Any]]
    ) -> AgentSessionPayload:
        if str(session.get("compat_job_id") or "").strip():
            return {}
        if not tasks:
            return {}
        status, _ = resolve_session_status(tasks)
        final_summary = session.get("final_summary")
        if status == "completed":
            verification = next((task for task in reversed(tasks) if task.get("phase") == "verification"), None)
            final_summary = str((verification or {}).get("result_summary") or final_summary or "").strip() or None
        return {
            "status": status,
            "final_summary": final_summary,
        }

    @staticmethod
    def _requires_approval_for_task(task: dict[str, Any]) -> bool:
        metadata = dict(task.get("metadata") or {})
        candidate = str(
            metadata.get("concurrency_class")
            or dict(task.get("task_spec") or {}).get("concurrency_class")
            or ("write_shared" if list(task.get("write_set") or []) else "read_only")
        ).strip().lower()
        return candidate in {"write_external", "privileged"}

    @staticmethod
    def _decorate_session(
        session: dict[str, Any],
        *,
        tasks: list[dict[str, Any]] | None = None,
        task_count: int | None = None,
        event_count: int | None = None,
        artifact_count: int | None = None,
        approval_count: int | None = None,
    ) -> dict[str, Any]:
        item = dict(session)
        metadata = dict(item.get("metadata") or {})
        session_id = str(item.get("session_id") or "")
        item["compat_projection_version"] = metadata.get("compat_projection_version")
        if task_count is None and session_id:
            task_count = None
        item["task_count"] = task_count
        item["event_count"] = event_count
        item["artifact_count"] = artifact_count
        item["approval_count"] = approval_count
        lead_task = None
        for bucket in ("in_progress", "claimed", "pending", "blocked"):
            lead_task = next((task for task in list(tasks or []) if str(task.get("status") or "") == bucket), None)
            if lead_task is not None:
                break
        item["progress"] = build_task_progress_summary(lead_task) if lead_task is not None else {}
        return item

    @staticmethod
    def _decorate_task(task: dict[str, Any]) -> dict[str, Any]:
        item = dict(task)
        item["progress"] = build_task_progress_summary(task)
        return item

_service_instance: AgentSessionService | None = None


def get_agent_session_service() -> AgentSessionService:
    global _service_instance
    if _service_instance is None:
        _service_instance = AgentSessionService()
    return _service_instance


def reset_agent_session_service_for_tests(service: AgentSessionService | None = None) -> None:
    global _service_instance
    _service_instance = service
