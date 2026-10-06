from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from threading import RLock
from typing import Annotated, Any, NotRequired, TypeGuard, TypeVar, TypedDict
from uuid import uuid4
import logging

from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from functorial_kit import Failure

from app.models.base import Base, SessionLocal, engine
from app.contracts.json import JSONObject as JsonObject
from app.models.entities import (
    AgentApproval as _AgentApprovalModel,
    AgentArtifact as _AgentArtifactModel,
    AgentEvent as _AgentEventModel,
    AgentMessage as _AgentMessageModel,
    AgentSession as _AgentSessionModel,
    AgentTask as _AgentTaskModel,
)
from app.settings.config import settings
from mrw_functorial_kit.core.agent_service_semantics import agent_session_failures

logger = logging.getLogger("app.services.agent_sessions.store")

# These legacy declarative models expose ``Column[T]`` as instance attributes to
# static checkers.  Keep that dynamic ORM boundary here; the six record
# TypedDicts below are the canonical values returned to every consumer.
AgentSession: Any = _AgentSessionModel
AgentTask: Any = _AgentTaskModel
AgentMessage: Any = _AgentMessageModel
AgentArtifact: Any = _AgentArtifactModel
AgentEvent: Any = _AgentEventModel
AgentApproval: Any = _AgentApprovalModel

TimestampValue = datetime | str | None
_T = TypeVar("_T")


class AgentSessionRecord(TypedDict):
    session_id: str
    source: str
    project_key: str | None
    entrypoint_type: str
    goal: str
    status: str
    current_phase: str
    compat_mode: bool
    compat_job_id: str | None
    logical_task_list_key: str | None
    root_task_id: str | None
    metadata: JsonObject
    final_summary: str | None
    final_result: JsonObject
    created_at: str | None
    updated_at: str | None


class AgentSessionPayload(TypedDict, total=False):
    session_id: str
    source: str
    project_key: str | None
    entrypoint_type: str
    goal: str
    status: str
    current_phase: str
    compat_mode: bool
    compat_job_id: str | None
    logical_task_list_key: str | None
    root_task_id: str | None
    metadata: JsonObject
    final_summary: str | None
    final_result: JsonObject
    created_at: TimestampValue
    updated_at: TimestampValue


class AgentTaskRecord(TypedDict):
    task_id: str
    session_id: str
    parent_task_id: str | None
    subject: str
    description: str | None
    task_type: str
    phase: str
    status: str
    execution_mode: str
    owner: str | None
    blocked_by: list[str]
    blocks: list[str]
    priority: int
    write_set: list[str]
    read_set: list[str]
    task_spec: JsonObject
    metadata: JsonObject
    result_summary: str | None
    result_payload: JsonObject
    tool_use_count: int
    token_usage: int
    last_activity: str | None
    recent_activities: list[str]
    summary_label: str | None
    lease_until: str | None
    claimed_at: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str | None
    updated_at: str | None


class AgentTaskPayload(TypedDict, total=False):
    task_id: str
    session_id: str
    parent_task_id: str | None
    subject: str
    description: str | None
    task_type: str
    phase: str
    status: str
    execution_mode: str
    owner: str | None
    blocked_by: list[str]
    blocks: list[str]
    priority: int
    write_set: list[str]
    read_set: list[str]
    task_spec: JsonObject
    metadata: JsonObject
    result_summary: str | None
    result_payload: JsonObject
    tool_use_count: int
    token_usage: int
    last_activity: str | None
    recent_activities: list[str]
    summary_label: str | None
    lease_until: TimestampValue
    claimed_at: TimestampValue
    started_at: TimestampValue
    completed_at: TimestampValue
    created_at: TimestampValue
    updated_at: TimestampValue


class AgentMessageRecord(TypedDict):
    session_id: str
    task_id: str | None
    role: str
    actor: str | None
    content: str
    metadata: JsonObject
    created_at: str | None


class AgentMessagePayload(TypedDict, total=False):
    session_id: str
    task_id: str | None
    role: str
    actor: str | None
    content: str
    metadata: JsonObject
    created_at: TimestampValue


class AgentArtifactRecord(TypedDict):
    artifact_id: str
    session_id: str
    task_id: str | None
    artifact_type: str
    name: str
    mime_type: str | None
    content_text: str | None
    content_json: JsonObject
    metadata: JsonObject
    created_at: str | None
    updated_at: str | None
    project_key: NotRequired[str]


class AgentArtifactPayload(TypedDict, total=False):
    artifact_id: str
    session_id: str
    task_id: str | None
    artifact_type: str
    name: str
    mime_type: str | None
    content_text: str | None
    content_json: JsonObject
    metadata: JsonObject
    created_at: TimestampValue
    updated_at: TimestampValue
    project_key: str


class AgentEventRecord(TypedDict):
    session_id: str
    seq: int
    event_type: str
    task_id: str | None
    payload: JsonObject
    ts: str | None


class AgentEventPayload(TypedDict, total=False):
    session_id: str
    seq: int
    event_type: str
    task_id: str | None
    payload: JsonObject
    ts: TimestampValue


class AgentTaskTransitionMutation(TypedDict):
    task_id: str
    expected_statuses: list[str]
    expected_owner: str | None
    changes: AgentTaskPayload


class AgentTaskTransitionResult(TypedDict):
    task: AgentTaskRecord
    related_tasks: list[AgentTaskRecord]
    session: AgentSessionRecord
    events: list[AgentEventRecord]


class AgentSessionTransitionResult(TypedDict):
    session: AgentSessionRecord
    events: list[AgentEventRecord]


class AgentApprovalTransitionMutation(TypedDict):
    expected_statuses: list[str]
    expected_binding_payload: NotRequired[JsonObject]
    expected_requester_actor: NotRequired[str]
    payload: AgentApprovalPayload


class AgentSessionCommandResult(TypedDict):
    session: AgentSessionRecord
    tasks: list[AgentTaskRecord]
    messages: list[AgentMessageRecord]
    artifacts: list[AgentArtifactRecord]
    approval: AgentApprovalRecord | None
    events: list[AgentEventRecord]


class AgentApprovalRecord(TypedDict):
    approval_id: str
    binding_hash: str
    binding_payload: JsonObject
    requester_session_id: str | None
    requester_task_id: str | None
    requester_actor: str
    approved_by: str | None
    approved_at: TimestampValue
    expires_at: TimestampValue
    status: str
    audit_log: list[JsonObject]
    metadata: JsonObject
    created_at: str | None
    updated_at: str | None


class AgentApprovalPayload(TypedDict, total=False):
    approval_id: str
    binding_hash: str
    binding_payload: JsonObject
    requester_session_id: str | None
    requester_task_id: str | None
    requester_actor: str
    approved_by: str | None
    approved_at: TimestampValue
    expires_at: TimestampValue
    status: str
    audit_log: list[JsonObject]
    metadata: JsonObject
    created_at: TimestampValue
    updated_at: TimestampValue


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if value is None:
        return None
    return str(value)


def _clone(value: _T) -> _T:
    return deepcopy(value)


def _artifact_sort_key(item: AgentArtifactRecord) -> tuple[str, str]:
    return (str(item.get("name") or ""), str(item.get("artifact_id") or ""))


def _failure(code: str, message: str, **context: object) -> Failure:
    return agent_session_failures.fail(code, message, context or None)


def _json_object_failure(value: object, *, field: str) -> Failure | None:
    if not isinstance(value, dict):
        return _failure("json_value_invalid", f"{field} must be a JSON object", field=field)
    try:
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        return _failure(
            "json_value_invalid",
            f"{field} contains a non-JSON value",
            field=field,
            error=str(exc),
        )
    if decoded != value:
        return _failure(
            "json_value_invalid",
            f"{field} contains a non-canonical JSON value",
            field=field,
        )
    return None


def _is_json_object(value: object, *, field: str) -> TypeGuard[JsonObject]:
    return _json_object_failure(value, field=field) is None


def validate_json_object(value: object, *, field: str) -> JsonObject | Failure:
    failure = _json_object_failure(value, field=field)
    if failure is not None:
        return failure
    if not _is_json_object(value, field=field):
        return _failure("json_value_invalid", f"{field} contains a non-JSON value", field=field)
    return value


def _is_string_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _json_fields_failure(payload: object, fields: tuple[str, ...]) -> Failure | None:
    if not _is_string_object_dict(payload):
        return _failure("json_value_invalid", "payload must be an object")
    for field in fields:
        if field in payload:
            failure = _json_object_failure(payload[field], field=field)
            if failure is not None:
                return failure
    return None


def _transition_precondition_failure(
    *,
    session_id: str,
    task_id: str,
    status: str,
    owner: str | None,
) -> Failure:
    return _failure(
        "task_transition_conflict",
        "task changed before the transition could be committed",
        session_id=session_id,
        task_id=task_id,
        status=status,
        owner=owner,
    )


def _backend_operation_failure(operation: str, exc: BaseException) -> Failure:
    return _failure(
        "backend_unavailable",
        f"agent session database operation failed: {operation}",
        operation=operation,
        error=str(exc),
        error_type=exc.__class__.__name__,
    )


def _consume_status_failure(approval_id: str, status: str) -> Failure:
    status = str(status or "")
    if status == "consumed":
        return _failure(
            "status_invalid",
            "approval grant was already consumed",
            approval_id=approval_id,
            status=status,
            host_code="host_approval_grant_consumed",
        )
    if status == "failed":
        return _failure(
            "status_invalid",
            "approval was rejected",
            approval_id=approval_id,
            status=status,
            host_code="host_approval_rejected",
        )
    return _failure(
        "status_invalid",
        "approval is not approved",
        approval_id=approval_id,
        status=status,
        host_code="host_approval_pending",
    )


def _confirmation_status_failure(approval_id: str, status: str) -> Failure:
    return _failure(
        "status_invalid",
        "approval is not pending",
        approval_id=approval_id,
        status=str(status or ""),
        host_code="host_confirmation_not_pending",
    )


def _session_command_failure(
    session_id: str,
    *,
    session_create: AgentSessionPayload | None,
    session_changes: AgentSessionPayload,
    task_creates: list[AgentTaskPayload],
    task_mutations: list[AgentTaskTransitionMutation],
    message_creates: list[AgentMessagePayload],
    artifact_upserts: list[AgentArtifactPayload],
    approval_mutation: AgentApprovalTransitionMutation | None,
    events: list[AgentEventPayload],
) -> Failure | None:
    if session_create is not None and str(session_create.get("session_id") or "") != session_id:
        return _failure("session_id_required", "session command identity does not match session payload")
    if session_create is not None and (
        failure := _json_fields_failure(session_create, ("metadata", "final_result"))
    ) is not None:
        return failure
    if len({item["task_id"] for item in task_mutations}) != len(task_mutations):
        return _failure("task_transition_conflict", "session command contains duplicate task mutations")
    if len({str(item.get("task_id") or "") for item in task_creates}) != len(task_creates):
        return _failure("task_transition_conflict", "session command contains duplicate task creations")
    if (failure := _json_fields_failure(session_changes, ("metadata", "final_result"))) is not None:
        return failure
    for payload in task_creates:
        if str(payload.get("session_id") or "") != session_id:
            return _failure("task_identity_required", "task command identity does not match session")
        if (failure := _json_fields_failure(payload, ("task_spec", "metadata", "result_payload"))) is not None:
            return failure
    for mutation in task_mutations:
        if (failure := _json_fields_failure(
            mutation["changes"], ("task_spec", "metadata", "result_payload")
        )) is not None:
            return failure
    for payload in message_creates:
        if str(payload.get("session_id") or "") != session_id:
            return _failure("session_id_required", "message command identity does not match session")
        if (failure := _json_fields_failure(payload, ("metadata",))) is not None:
            return failure
    for payload in artifact_upserts:
        if str(payload.get("session_id") or "") != session_id:
            return _failure("artifact_identity_required", "artifact command identity does not match session")
        if (failure := _json_fields_failure(payload, ("content_json", "metadata"))) is not None:
            return failure
    if approval_mutation is not None:
        payload = approval_mutation["payload"]
        if "expected_binding_payload" in approval_mutation and (
            failure := _json_object_failure(
                approval_mutation["expected_binding_payload"],
                field="expected_binding_payload",
            )
        ) is not None:
            return failure
        if (failure := _json_fields_failure(payload, ("binding_payload", "metadata"))) is not None:
            return failure
        if "audit_log" in payload and (
            failure := _json_object_failure({"audit_log": payload.get("audit_log") or []}, field="audit_log")
        ) is not None:
            return failure
    for event in events:
        if (failure := _json_fields_failure(event, ("payload",))) is not None:
            return failure
    return None


class InMemoryAgentSessionStore:
    """Thread-safe fallback store for agent sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSessionRecord] = {}
        self._tasks: dict[str, dict[str, AgentTaskRecord]] = {}
        self._messages: dict[str, list[AgentMessageRecord]] = {}
        self._artifacts: dict[str, dict[str, AgentArtifactRecord]] = {}
        self._project_artifacts: dict[str, dict[str, AgentArtifactRecord]] = {}
        self._events: dict[str, list[AgentEventRecord]] = {}
        self._approvals: dict[str, AgentApprovalRecord] = {}
        self._lock = RLock()

    def create_session(self, payload: AgentSessionPayload) -> AgentSessionRecord | Failure:
        if (failure := _json_fields_failure(payload, ("metadata", "final_result"))) is not None:
            return failure
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id:
            return _failure("session_id_required", "session_id is required", session_id=session_id)
        with self._lock:
            if session_id in self._sessions:
                return _failure("session_already_exists", f"session already exists: {session_id}", session_id=session_id)
            now = _as_iso(_utcnow())
            item: AgentSessionRecord = {
                "session_id": session_id,
                "source": str(payload.get("source") or "user"),
                "project_key": payload.get("project_key"),
                "entrypoint_type": str(payload.get("entrypoint_type") or "chat"),
                "goal": str(payload.get("goal") or ""),
                "status": str(payload.get("status") or "pending"),
                "current_phase": str(payload.get("current_phase") or "research"),
                "compat_mode": bool(payload.get("compat_mode")),
                "compat_job_id": payload.get("compat_job_id"),
                "logical_task_list_key": payload.get("logical_task_list_key"),
                "root_task_id": payload.get("root_task_id"),
                "metadata": _clone(payload.get("metadata") or {}),
                "final_summary": payload.get("final_summary"),
                "final_result": _clone(payload.get("final_result") or {}),
                "created_at": _as_iso(payload.get("created_at")) or now,
                "updated_at": _as_iso(payload.get("updated_at")) or now,
            }
            self._sessions[session_id] = item
            self._tasks[session_id] = {}
            self._messages[session_id] = []
            self._artifacts[session_id] = {}
            self._events[session_id] = []
            return _clone(item)

    def update_session(self, session_id: str, changes: AgentSessionPayload) -> AgentSessionRecord | Failure:
        if (failure := _json_fields_failure(changes, ("metadata", "final_result"))) is not None:
            return failure
        with self._lock:
            session = self._must_get_session_ref(session_id)
            if isinstance(session, Failure):
                return session
            if "source" in changes:
                session["source"] = changes.get("source") or "user"
            if "project_key" in changes:
                session["project_key"] = changes.get("project_key")
            if "entrypoint_type" in changes:
                session["entrypoint_type"] = changes.get("entrypoint_type") or "chat"
            if "goal" in changes:
                session["goal"] = changes.get("goal") or ""
            if "status" in changes:
                session["status"] = changes.get("status") or session["status"]
            if "current_phase" in changes:
                session["current_phase"] = changes.get("current_phase") or session["current_phase"]
            if "compat_mode" in changes:
                session["compat_mode"] = bool(changes.get("compat_mode"))
            if "compat_job_id" in changes:
                session["compat_job_id"] = changes.get("compat_job_id")
            if "logical_task_list_key" in changes:
                session["logical_task_list_key"] = changes.get("logical_task_list_key")
            if "root_task_id" in changes:
                session["root_task_id"] = changes.get("root_task_id")
            if "metadata" in changes:
                session["metadata"] = _clone(changes.get("metadata") or {})
            if "final_summary" in changes:
                session["final_summary"] = changes.get("final_summary")
            if "final_result" in changes:
                session["final_result"] = _clone(changes.get("final_result") or {})
            if "created_at" in changes:
                session["created_at"] = _as_iso(changes.get("created_at"))
            session["updated_at"] = _as_iso(_utcnow())
            return _clone(session)

    def get_session(self, session_id: str) -> AgentSessionRecord | Failure:
        with self._lock:
            session = self._must_get_session_ref(session_id)
            return _clone(session)

    def list_sessions(self, *, limit: int = 50) -> list[AgentSessionRecord]:
        with self._lock:
            items = sorted(
                self._sessions.values(),
                key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
                reverse=True,
            )
            return [_clone(item) for item in items[: max(1, int(limit))]]

    def find_session_by_compat_job_id(self, compat_job_id: str) -> AgentSessionRecord | None:
        target = str(compat_job_id or "").strip()
        if not target:
            return None
        with self._lock:
            for item in self._sessions.values():
                if str(item.get("compat_job_id") or "").strip() == target:
                    return _clone(item)
            return None

    def find_session_by_native_thread_id(self, thread_id: str) -> AgentSessionRecord | None | Failure:
        target = str(thread_id or "").strip()
        if not target:
            return None
        with self._lock:
            matches = [
                item for item in self._sessions.values()
                if item.get("source") == "codex_webui_host"
                and item.get("entrypoint_type") == "codex_native_thread"
                and dict(item.get("metadata") or {}).get("native_thread_id") == target
            ]
            if len(matches) > 1:
                return _failure("session_already_exists", "native thread has multiple MRW session bindings", thread_id=target)
            return _clone(matches[0]) if matches else None

    def find_session_by_logical_task_list_key(self, logical_task_list_key: str) -> AgentSessionRecord | None:
        target = str(logical_task_list_key or "").strip()
        if not target:
            return None
        with self._lock:
            for item in self._sessions.values():
                if str(item.get("logical_task_list_key") or "").strip() == target:
                    return _clone(item)
            return None

    def create_task(self, payload: AgentTaskPayload) -> AgentTaskRecord | Failure:
        if (failure := _json_fields_failure(payload, ("task_spec", "metadata", "result_payload"))) is not None:
            return failure
        session_id = str(payload.get("session_id") or "").strip()
        task_id = str(payload.get("task_id") or "").strip()
        if not session_id or not task_id:
            return _failure("task_identity_required", "session_id and task_id are required", session_id=session_id, task_id=task_id)
        with self._lock:
            session = self._must_get_session_ref(session_id)
            if isinstance(session, Failure):
                return session
            now = _as_iso(_utcnow())
            item: AgentTaskRecord = {
                "task_id": task_id,
                "session_id": session_id,
                "parent_task_id": payload.get("parent_task_id"),
                "subject": str(payload.get("subject") or ""),
                "description": payload.get("description"),
                "task_type": str(payload.get("task_type") or ""),
                "phase": str(payload.get("phase") or "research"),
                "status": str(payload.get("status") or "pending"),
                "execution_mode": str(payload.get("execution_mode") or "worker"),
                "owner": payload.get("owner"),
                "blocked_by": _clone(payload.get("blocked_by") or []),
                "blocks": _clone(payload.get("blocks") or []),
                "priority": int(payload.get("priority") or 5),
                "write_set": _clone(payload.get("write_set") or []),
                "read_set": _clone(payload.get("read_set") or []),
                "task_spec": _clone(payload.get("task_spec") or {}),
                "metadata": _clone(payload.get("metadata") or {}),
                "result_summary": payload.get("result_summary"),
                "result_payload": _clone(payload.get("result_payload") or {}),
                "tool_use_count": int(payload.get("tool_use_count") or 0),
                "token_usage": int(payload.get("token_usage") or 0),
                "last_activity": payload.get("last_activity"),
                "recent_activities": _clone(payload.get("recent_activities") or []),
                "summary_label": payload.get("summary_label"),
                "lease_until": _as_iso(payload.get("lease_until")),
                "claimed_at": _as_iso(payload.get("claimed_at")),
                "started_at": _as_iso(payload.get("started_at")),
                "completed_at": _as_iso(payload.get("completed_at")),
                "created_at": _as_iso(payload.get("created_at")) or now,
                "updated_at": _as_iso(payload.get("updated_at")) or now,
            }
            self._tasks[session_id][task_id] = item
            return _clone(item)

    def get_task(self, session_id: str, task_id: str) -> AgentTaskRecord | Failure:
        with self._lock:
            return _clone(self._must_get_task_ref(session_id, task_id))

    def update_task(self, session_id: str, task_id: str, changes: AgentTaskPayload) -> AgentTaskRecord | Failure:
        if (failure := _json_fields_failure(changes, ("task_spec", "metadata", "result_payload"))) is not None:
            return failure
        with self._lock:
            item = self._must_get_task_ref(session_id, task_id)
            if isinstance(item, Failure):
                return item
            if "parent_task_id" in changes:
                item["parent_task_id"] = changes.get("parent_task_id")
            if "subject" in changes:
                item["subject"] = changes.get("subject") or item["subject"]
            if "description" in changes:
                item["description"] = changes.get("description")
            if "task_type" in changes:
                item["task_type"] = changes.get("task_type") or item["task_type"]
            if "phase" in changes:
                item["phase"] = changes.get("phase") or item["phase"]
            if "status" in changes:
                item["status"] = changes.get("status") or item["status"]
            if "execution_mode" in changes:
                item["execution_mode"] = changes.get("execution_mode") or item["execution_mode"]
            if "owner" in changes:
                item["owner"] = changes.get("owner")
            if "blocked_by" in changes:
                item["blocked_by"] = _clone(changes.get("blocked_by") or [])
            if "blocks" in changes:
                item["blocks"] = _clone(changes.get("blocks") or [])
            if "priority" in changes:
                item["priority"] = int(changes.get("priority") or item["priority"] or 5)
            if "write_set" in changes:
                item["write_set"] = _clone(changes.get("write_set") or [])
            if "read_set" in changes:
                item["read_set"] = _clone(changes.get("read_set") or [])
            if "task_spec" in changes:
                item["task_spec"] = _clone(changes.get("task_spec") or {})
            if "metadata" in changes:
                item["metadata"] = _clone(changes.get("metadata") or {})
            if "result_summary" in changes:
                item["result_summary"] = changes.get("result_summary")
            if "result_payload" in changes:
                item["result_payload"] = _clone(changes.get("result_payload") or {})
            if "tool_use_count" in changes:
                item["tool_use_count"] = int(changes.get("tool_use_count") or 0)
            if "token_usage" in changes:
                item["token_usage"] = int(changes.get("token_usage") or 0)
            if "last_activity" in changes:
                item["last_activity"] = changes.get("last_activity")
            if "recent_activities" in changes:
                item["recent_activities"] = _clone(changes.get("recent_activities") or [])
            if "summary_label" in changes:
                item["summary_label"] = changes.get("summary_label")
            if "lease_until" in changes:
                item["lease_until"] = _as_iso(changes.get("lease_until"))
            if "claimed_at" in changes:
                item["claimed_at"] = _as_iso(changes.get("claimed_at"))
            if "started_at" in changes:
                item["started_at"] = _as_iso(changes.get("started_at"))
            if "completed_at" in changes:
                item["completed_at"] = _as_iso(changes.get("completed_at"))
            if "created_at" in changes:
                item["created_at"] = _as_iso(changes.get("created_at"))
            item["updated_at"] = _as_iso(_utcnow())
            self._sessions[session_id]["updated_at"] = item["updated_at"]
            return _clone(item)

    def transition_task(
        self,
        session_id: str,
        *,
        primary: AgentTaskTransitionMutation,
        related: list[AgentTaskTransitionMutation],
        session_changes: AgentSessionPayload,
        events: list[AgentEventPayload],
    ) -> AgentTaskTransitionResult | Failure:
        mutations = [primary, *related]
        if len({item["task_id"] for item in mutations}) != len(mutations):
            return _failure("task_transition_conflict", "task transition contains duplicate task mutations")
        if (failure := _json_fields_failure(session_changes, ("metadata", "final_result"))) is not None:
            return failure
        for mutation in mutations:
            if (failure := _json_fields_failure(
                mutation["changes"], ("task_spec", "metadata", "result_payload")
            )) is not None:
                return failure
        for event in events:
            if (failure := _json_fields_failure(event, ("payload",))) is not None:
                return failure
        with self._lock:
            session = self._must_get_session_ref(session_id)
            if isinstance(session, Failure):
                return session
            task_refs: dict[str, AgentTaskRecord] = {}
            for mutation in mutations:
                task = self._must_get_task_ref(session_id, mutation["task_id"])
                if isinstance(task, Failure):
                    return task
                if (
                    task["status"] not in mutation["expected_statuses"]
                    or task.get("owner") != mutation["expected_owner"]
                ):
                    return _transition_precondition_failure(
                        session_id=session_id,
                        task_id=mutation["task_id"],
                        status=task["status"],
                        owner=task.get("owner"),
                    )
                task_refs[mutation["task_id"]] = task

            session_before = _clone(session)
            tasks_before = {task_id: _clone(task) for task_id, task in task_refs.items()}
            events_before = _clone(self._events[session_id])
            updated_tasks: dict[str, AgentTaskRecord] = {}
            created_events: list[AgentEventRecord] = []
            for mutation in mutations:
                updated = self.update_task(session_id, mutation["task_id"], mutation["changes"])
                if isinstance(updated, Failure):
                    self._sessions[session_id] = session_before
                    self._tasks[session_id].update(tasks_before)
                    self._events[session_id] = events_before
                    return updated
                updated_tasks[mutation["task_id"]] = updated
            updated_session = self.update_session(session_id, session_changes)
            if isinstance(updated_session, Failure):
                self._sessions[session_id] = session_before
                self._tasks[session_id].update(tasks_before)
                self._events[session_id] = events_before
                return updated_session
            for event in events:
                created = self.append_event(
                    session_id,
                    event_type=event.get("event_type") or "task.updated",
                    task_id=event.get("task_id"),
                    payload=event.get("payload") or {},
                )
                if isinstance(created, Failure):
                    self._sessions[session_id] = session_before
                    self._tasks[session_id].update(tasks_before)
                    self._events[session_id] = events_before
                    return created
                created_events.append(created)
            return {
                "task": updated_tasks[primary["task_id"]],
                "related_tasks": [updated_tasks[item["task_id"]] for item in related],
                "session": updated_session,
                "events": created_events,
            }

    def transition_session(
        self,
        session_id: str,
        *,
        expected_statuses: list[str],
        session_changes: AgentSessionPayload,
        events: list[AgentEventPayload],
    ) -> AgentSessionTransitionResult | Failure:
        if (failure := _json_fields_failure(session_changes, ("metadata", "final_result"))) is not None:
            return failure
        for event in events:
            if (failure := _json_fields_failure(event, ("payload",))) is not None:
                return failure
        with self._lock:
            session = self._must_get_session_ref(session_id)
            if isinstance(session, Failure):
                return session
            if session["status"] not in expected_statuses:
                return _failure(
                    "status_invalid",
                    "session changed before the transition could be committed",
                    session_id=session_id,
                    status=session["status"],
                )
            session_before = _clone(session)
            events_before = _clone(self._events[session_id])
            updated = self.update_session(session_id, session_changes)
            if isinstance(updated, Failure):
                return updated
            created_events: list[AgentEventRecord] = []
            for event in events:
                created = self.append_event(
                    session_id,
                    event_type=event.get("event_type") or "session.updated",
                    task_id=event.get("task_id"),
                    payload=event.get("payload") or {},
                )
                if isinstance(created, Failure):
                    self._sessions[session_id] = session_before
                    self._events[session_id] = events_before
                    return created
                created_events.append(created)
            return {"session": updated, "events": created_events}

    def commit_session_command(
        self,
        session_id: str,
        *,
        session_create: AgentSessionPayload | None,
        expected_session_statuses: list[str] | None,
        session_changes: AgentSessionPayload,
        task_creates: list[AgentTaskPayload],
        task_mutations: list[AgentTaskTransitionMutation],
        message_creates: list[AgentMessagePayload],
        artifact_upserts: list[AgentArtifactPayload],
        approval_mutation: AgentApprovalTransitionMutation | None,
        events: list[AgentEventPayload],
    ) -> AgentSessionCommandResult | Failure:
        failure = _session_command_failure(
            session_id,
            session_create=session_create,
            session_changes=session_changes,
            task_creates=task_creates,
            task_mutations=task_mutations,
            message_creates=message_creates,
            artifact_upserts=artifact_upserts,
            approval_mutation=approval_mutation,
            events=events,
        )
        if failure is not None:
            return failure

        with self._lock:
            sessions_before = _clone(self._sessions)
            tasks_before = _clone(self._tasks)
            messages_before = _clone(self._messages)
            artifacts_before = _clone(self._artifacts)
            events_before = _clone(self._events)
            approvals_before = _clone(self._approvals)

            def rollback(failure: Failure) -> Failure:
                self._sessions = sessions_before
                self._tasks = tasks_before
                self._messages = messages_before
                self._artifacts = artifacts_before
                self._events = events_before
                self._approvals = approvals_before
                return failure

            if session_create is not None:
                created_session = self.create_session(session_create)
                if isinstance(created_session, Failure):
                    return rollback(created_session)
            else:
                current_session = self._must_get_session_ref(session_id)
                if isinstance(current_session, Failure):
                    return current_session
                if (
                    expected_session_statuses is not None
                    and current_session["status"] not in expected_session_statuses
                ):
                    return _failure(
                        "status_invalid",
                        "session changed before the command could be committed",
                        session_id=session_id,
                        status=current_session["status"],
                    )

            affected_tasks: list[AgentTaskRecord] = []
            for payload in task_creates:
                created_task = self.create_task(payload)
                if isinstance(created_task, Failure):
                    return rollback(created_task)
                affected_tasks.append(created_task)
            for mutation in task_mutations:
                current_task = self._must_get_task_ref(session_id, mutation["task_id"])
                if isinstance(current_task, Failure):
                    return rollback(current_task)
                if (
                    current_task["status"] not in mutation["expected_statuses"]
                    or current_task.get("owner") != mutation["expected_owner"]
                ):
                    return rollback(
                        _transition_precondition_failure(
                            session_id=session_id,
                            task_id=mutation["task_id"],
                            status=current_task["status"],
                            owner=current_task.get("owner"),
                        )
                    )
                updated_task = self.update_task(
                    session_id,
                    mutation["task_id"],
                    mutation["changes"],
                )
                if isinstance(updated_task, Failure):
                    return rollback(updated_task)
                affected_tasks.append(updated_task)

            created_messages: list[AgentMessageRecord] = []
            for payload in message_creates:
                created_message = self.create_message(payload)
                if isinstance(created_message, Failure):
                    return rollback(created_message)
                created_messages.append(created_message)

            updated_artifacts: list[AgentArtifactRecord] = []
            for payload in artifact_upserts:
                updated_artifact = self.upsert_artifact(payload)
                if isinstance(updated_artifact, Failure):
                    return rollback(updated_artifact)
                updated_artifacts.append(updated_artifact)

            updated_approval: AgentApprovalRecord | None = None
            if approval_mutation is not None:
                approval_payload = approval_mutation["payload"]
                approval_id = str(approval_payload.get("approval_id") or "").strip()
                existing_approval = self._approvals.get(approval_id)
                expected_statuses = approval_mutation["expected_statuses"]
                if existing_approval is not None and (
                    expected_statuses
                    and str(existing_approval.get("status") or "") not in expected_statuses
                ):
                    return rollback(
                        _confirmation_status_failure(
                            approval_id,
                            str(existing_approval.get("status") or ""),
                        )
                    )
                if (
                    existing_approval is not None
                    and "expected_binding_payload" in approval_mutation
                    and existing_approval["binding_payload"]
                    != approval_mutation["expected_binding_payload"]
                ):
                    return rollback(
                        _failure(
                            "status_invalid",
                            "approval binding changed before the command could be committed",
                            approval_id=approval_id,
                            host_code="host_approval_binding_mismatch",
                        )
                    )
                if (
                    existing_approval is not None
                    and "expected_requester_actor" in approval_mutation
                    and existing_approval["requester_actor"]
                    != approval_mutation["expected_requester_actor"]
                ):
                    return rollback(
                        _failure(
                            "status_invalid",
                            "approval requester changed before the command could be committed",
                            approval_id=approval_id,
                            host_code="host_confirmation_scope_mismatch",
                        )
                    )
                if existing_approval is None and expected_statuses:
                    return rollback(
                        _failure(
                            "approval_not_found",
                            f"approval not found: {approval_id}",
                            approval_id=approval_id,
                        )
                    )
                approval_result = self.create_or_update_approval(approval_payload)
                if isinstance(approval_result, Failure):
                    return rollback(approval_result)
                updated_approval = approval_result

            updated_session = self.update_session(session_id, session_changes)
            if isinstance(updated_session, Failure):
                return rollback(updated_session)

            created_events: list[AgentEventRecord] = []
            for event in events:
                created_event = self.append_event(
                    session_id,
                    event_type=event.get("event_type") or "session.updated",
                    task_id=event.get("task_id"),
                    payload=event.get("payload") or {},
                )
                if isinstance(created_event, Failure):
                    return rollback(created_event)
                created_events.append(created_event)
            return {
                "session": updated_session,
                "tasks": affected_tasks,
                "messages": created_messages,
                "artifacts": updated_artifacts,
                "approval": updated_approval,
                "events": created_events,
            }

    def list_tasks(self, session_id: str) -> list[AgentTaskRecord] | Failure:
        with self._lock:
            session = self._must_get_session_ref(session_id)
            if isinstance(session, Failure):
                return session
            items = sorted(
                self._tasks[session_id].values(),
                key=lambda item: str(item.get("created_at") or ""),
            )
            return [_clone(item) for item in items]

    def create_message(self, payload: AgentMessagePayload) -> AgentMessageRecord | Failure:
        if (failure := _json_fields_failure(payload, ("metadata",))) is not None:
            return failure
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id:
            return _failure("session_id_required", "session_id is required", session_id=session_id)
        with self._lock:
            session = self._must_get_session_ref(session_id)
            if isinstance(session, Failure):
                return session
            item: AgentMessageRecord = {
                "session_id": session_id,
                "task_id": payload.get("task_id"),
                "role": str(payload.get("role") or "assistant"),
                "actor": payload.get("actor"),
                "content": str(payload.get("content") or ""),
                "metadata": _clone(payload.get("metadata") or {}),
                "created_at": _as_iso(payload.get("created_at")) or _as_iso(_utcnow()),
            }
            self._messages[session_id].append(item)
            return _clone(item)

    def list_messages(self, session_id: str) -> list[AgentMessageRecord] | Failure:
        with self._lock:
            session = self._must_get_session_ref(session_id)
            if isinstance(session, Failure):
                return session
            return [_clone(item) for item in self._messages[session_id]]

    def upsert_artifact(self, payload: AgentArtifactPayload) -> AgentArtifactRecord | Failure:
        if (failure := _json_fields_failure(payload, ("content_json", "metadata"))) is not None:
            return failure
        session_id = str(payload.get("session_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        artifact_id = str(payload.get("artifact_id") or "").strip() or f"artifact-{uuid4().hex[:16]}"
        if not session_id or not name:
            return _failure("artifact_identity_required", "session_id and name are required", session_id=session_id, name=name)
        with self._lock:
            session = self._must_get_session_ref(session_id)
            if isinstance(session, Failure):
                return session
            existing = self._artifacts[session_id].get(name)
            now = _as_iso(_utcnow())
            item: AgentArtifactRecord = {
                "artifact_id": artifact_id if not existing else existing["artifact_id"],
                "session_id": session_id,
                "task_id": payload.get("task_id", existing.get("task_id") if existing else None),
                "artifact_type": str(payload.get("artifact_type") or (existing["artifact_type"] if existing else "")),
                "name": name,
                "mime_type": payload.get("mime_type", existing.get("mime_type") if existing else None),
                "content_text": payload.get("content_text", existing.get("content_text") if existing else None),
                "content_json": _clone(payload.get("content_json") or {}),
                "metadata": _clone(payload.get("metadata") or {}),
                "created_at": existing["created_at"] if existing else (_as_iso(payload.get("created_at")) or now),
                "updated_at": now,
            }
            self._artifacts[session_id][name] = item
            return _clone(item)

    def list_artifacts(self, session_id: str) -> list[AgentArtifactRecord] | Failure:
        with self._lock:
            session = self._must_get_session_ref(session_id)
            if isinstance(session, Failure):
                return session
            return [_clone(item) for item in sorted(self._artifacts[session_id].values(), key=_artifact_sort_key)]

    def upsert_project_artifact(self, payload: AgentArtifactPayload) -> AgentArtifactRecord | Failure:
        if (failure := _json_fields_failure(payload, ("content_json", "metadata"))) is not None:
            return failure
        project_key = str(payload.get("project_key") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not project_key or not name:
            return _failure("artifact_identity_required", "project_key and name are required")
        with self._lock:
            bucket = self._project_artifacts.setdefault(project_key, {})
            existing = bucket.get(name)
            now = _as_iso(_utcnow())
            item: AgentArtifactRecord = {
                "artifact_id": existing["artifact_id"] if existing else str(payload.get("artifact_id") or f"artifact-{uuid4().hex[:16]}"),
                "session_id": str(payload.get("session_id") or (existing["session_id"] if existing else "")),
                "task_id": payload.get("task_id", existing.get("task_id") if existing else None),
                "artifact_type": str(payload.get("artifact_type") or (existing["artifact_type"] if existing else "agent_macro.registration_package")),
                "name": name,
                "mime_type": payload.get("mime_type", existing.get("mime_type") if existing else None),
                "content_text": payload.get("content_text", existing.get("content_text") if existing else None),
                "content_json": _clone(payload.get("content_json") or {}),
                "metadata": _clone(payload.get("metadata") or {}),
                "created_at": existing["created_at"] if existing else (_as_iso(payload.get("created_at")) or now),
                "updated_at": now,
                "project_key": project_key,
            }
            bucket[name] = item
            return _clone(item)

    def get_project_artifact(self, *, project_key: str, name: str) -> AgentArtifactRecord | None:
        with self._lock:
            item = self._project_artifacts.get(str(project_key or ""), {}).get(str(name or ""))
            if item is None:
                return None
            return _clone(item)

    def list_project_artifacts(self, *, project_key: str) -> list[AgentArtifactRecord] | Failure:
        project = str(project_key or "").strip()
        if not project:
            return _failure("artifact_identity_required", "project_key is required")
        with self._lock:
            return [
                _clone(item)
                for item in sorted(self._project_artifacts.get(project, {}).values(), key=_artifact_sort_key)
            ]

    def append_event(
        self,
        session_id: str,
        *,
        event_type: str,
        task_id: str | None = None,
        payload: JsonObject | None = None,
    ) -> AgentEventRecord | Failure:
        event_payload = payload or {}
        if (failure := _json_object_failure(event_payload, field="payload")) is not None:
            return failure
        with self._lock:
            session = self._must_get_session_ref(session_id)
            if isinstance(session, Failure):
                return session
            seq = len(self._events[session_id]) + 1
            item: AgentEventRecord = {
                "session_id": session_id,
                "seq": seq,
                "event_type": str(event_type),
                "task_id": str(task_id or "").strip() or None,
                "payload": _clone(event_payload),
                "ts": _as_iso(_utcnow()),
            }
            self._events[session_id].append(item)
            self._sessions[session_id]["updated_at"] = item["ts"]
            return _clone(item)

    def list_events(self, session_id: str) -> list[AgentEventRecord] | Failure:
        with self._lock:
            session = self._must_get_session_ref(session_id)
            if isinstance(session, Failure):
                return session
            return [_clone(item) for item in self._events[session_id]]

    def create_or_update_approval(self, payload: AgentApprovalPayload) -> AgentApprovalRecord | Failure:
        if (failure := _json_fields_failure(payload, ("binding_payload", "metadata"))) is not None:
            return failure
        if "audit_log" in payload and (
            failure := _json_object_failure({"audit_log": payload.get("audit_log") or []}, field="audit_log")
        ) is not None:
            return failure
        approval_id = str(payload.get("approval_id") or "").strip()
        if not approval_id:
            return _failure("approval_id_required", "approval_id is required", approval_id=approval_id)
        with self._lock:
            existing = self._approvals.get(approval_id)
            now = _as_iso(_utcnow())
            item: AgentApprovalRecord = {
                "approval_id": approval_id,
                "binding_hash": str(payload.get("binding_hash") or (existing["binding_hash"] if existing else "")),
                "binding_payload": _clone(payload.get("binding_payload") or {}),
                "requester_session_id": payload.get("requester_session_id", existing.get("requester_session_id") if existing else None),
                "requester_task_id": payload.get("requester_task_id", existing.get("requester_task_id") if existing else None),
                "requester_actor": str(payload.get("requester_actor") or (existing["requester_actor"] if existing else "unknown")),
                "approved_by": payload.get("approved_by", existing.get("approved_by") if existing else None),
                "approved_at": payload.get("approved_at", existing.get("approved_at") if existing else None),
                "expires_at": payload.get("expires_at", existing.get("expires_at") if existing else None),
                "status": str(payload.get("status") or (existing["status"] if existing else "pending")),
                "audit_log": _clone(payload.get("audit_log") or []),
                "metadata": _clone(payload.get("metadata") or {}),
                "created_at": existing["created_at"] if existing else (_as_iso(payload.get("created_at")) or now),
                "updated_at": now,
            }
            self._approvals[approval_id] = item
            return _clone(item)

    def get_approval(self, approval_id: str) -> AgentApprovalRecord | Failure:
        with self._lock:
            item = self._approvals.get(str(approval_id or "").strip())
            if item is None:
                return _failure("approval_not_found", f"approval not found: {approval_id}", approval_id=approval_id)
            return _clone(item)

    def list_approvals(self, *, session_id: str | None = None) -> list[AgentApprovalRecord]:
        with self._lock:
            out: list[AgentApprovalRecord] = []
            for item in self._approvals.values():
                if session_id and str(item.get("requester_session_id") or "").strip() != session_id:
                    continue
                out.append(_clone(item))
            return sorted(out, key=lambda item: str(item.get("updated_at") or ""), reverse=True)

    def consume_host_approval(
        self,
        approval_id: str,
        *,
        expected_binding_payload: JsonObject | None = None,
        consumed_metadata: JsonObject | None = None,
        consumed_audit_log: list[JsonObject] | None = None,
    ) -> AgentApprovalRecord | Failure:
        for field, value in (
            ("expected_binding_payload", expected_binding_payload),
            ("consumed_metadata", consumed_metadata),
        ):
            if value is not None and (failure := _json_object_failure(value, field=field)) is not None:
                return failure
        if consumed_audit_log is not None and (
            failure := _json_object_failure(
                {"consumed_audit_log": consumed_audit_log},
                field="consumed_audit_log",
            )
        ) is not None:
            return failure
        approval_id = str(approval_id or "").strip()
        if not approval_id:
            return _failure("approval_id_required", "approval_id is required")
        with self._lock:
            existing = self._approvals.get(approval_id)
            if existing is None:
                return _failure("approval_not_found", f"approval not found: {approval_id}", approval_id=approval_id)
            if expected_binding_payload is not None and dict(existing.get("binding_payload") or {}) != dict(
                expected_binding_payload or {}
            ):
                return _failure(
                    "status_invalid",
                    "approval binding does not match the expected action",
                    approval_id=approval_id,
                    host_code="host_approval_binding_mismatch",
                )
            status = str(existing.get("status") or "")
            if status != "approved":
                return _consume_status_failure(approval_id, status)
            item = _clone(existing)
            item["status"] = "consumed"
            metadata = dict(item.get("metadata") or {})
            if consumed_metadata is not None:
                metadata.update(_clone(consumed_metadata))
            item["metadata"] = metadata
            if consumed_audit_log is not None:
                item["audit_log"] = [*list(item.get("audit_log") or []), *_clone(consumed_audit_log)]
            item["updated_at"] = _as_iso(_utcnow())
            self._approvals[approval_id] = item
            return _clone(item)

    def confirm_host_approval(
        self,
        approval_id: str,
        *,
        expected_binding_payload: JsonObject | None = None,
        expected_requester_actor: str | None = None,
        approved: bool = True,
        approved_by: str = "",
        approved_at: datetime | None = None,
        confirmation_metadata: JsonObject | None = None,
        audit_log: list[JsonObject] | None = None,
    ) -> AgentApprovalRecord | Failure:
        for field, value in (
            ("expected_binding_payload", expected_binding_payload),
            ("confirmation_metadata", confirmation_metadata),
        ):
            if value is not None and (failure := _json_object_failure(value, field=field)) is not None:
                return failure
        if audit_log is not None and (
            failure := _json_object_failure({"audit_log": audit_log}, field="audit_log")
        ) is not None:
            return failure
        approval_id = str(approval_id or "").strip()
        if not approval_id:
            return _failure("approval_id_required", "approval_id is required")
        with self._lock:
            existing = self._approvals.get(approval_id)
            if existing is None:
                return _failure("approval_not_found", f"approval not found: {approval_id}", approval_id=approval_id)
            if expected_binding_payload is not None and dict(existing.get("binding_payload") or {}) != dict(
                expected_binding_payload or {}
            ):
                return _failure(
                    "status_invalid",
                    "approval binding does not match the expected confirmation",
                    approval_id=approval_id,
                    host_code="host_confirmation_scope_mismatch",
                )
            if expected_requester_actor is not None and str(existing.get("requester_actor") or "") != str(
                expected_requester_actor
            ):
                return _failure(
                    "status_invalid",
                    "approval requester does not match the expected confirmation",
                    approval_id=approval_id,
                    host_code="host_confirmation_scope_mismatch",
                )
            if str(existing.get("status") or "") != "pending":
                return _confirmation_status_failure(approval_id, str(existing.get("status") or ""))
            item = _clone(existing)
            item["status"] = "approved" if approved else "failed"
            item["approved_by"] = str(approved_by or "").strip() or item.get("approved_by")
            if approved_at is not None:
                item["approved_at"] = approved_at
            metadata = dict(item.get("metadata") or {})
            if confirmation_metadata is not None:
                metadata.update(_clone(confirmation_metadata))
            item["metadata"] = metadata
            if audit_log is not None:
                item["audit_log"] = [*list(item.get("audit_log") or []), *_clone(audit_log)]
            item["updated_at"] = _as_iso(_utcnow())
            self._approvals[approval_id] = item
            return _clone(item)

    def _must_get_session_ref(self, session_id: str) -> AgentSessionRecord | Failure:
        item = self._sessions.get(session_id)
        if item is None:
            return _failure("session_not_found", f"session not found: {session_id}", session_id=session_id)
        return item

    def _must_get_task_ref(self, session_id: str, task_id: str) -> AgentTaskRecord | Failure:
        session = self._must_get_session_ref(session_id)
        if isinstance(session, Failure):
            return session
        item = self._tasks.get(session_id, {}).get(task_id)
        if item is None:
            return _failure("task_not_found", f"task not found: {task_id}", session_id=session_id, task_id=task_id)
        return item


class SqlAgentSessionStore:
    """DB-backed store for Claude-style agent sessions."""

    def __init__(self) -> None:
        with engine.begin() as conn:
            conn.execute(text('SET search_path TO "public"'))
            Base.metadata.create_all(
                bind=conn,
                tables=[
                    AgentSession.__table__,
                    AgentTask.__table__,
                    AgentMessage.__table__,
                    AgentArtifact.__table__,
                    AgentEvent.__table__,
                    AgentApproval.__table__,
                ],
                checkfirst=True,
            )

    def create_session(self, payload: AgentSessionPayload) -> AgentSessionRecord | Failure:
        if (failure := _json_fields_failure(payload, ("metadata", "final_result"))) is not None:
            return failure
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id:
            return _failure("session_id_required", "session_id is required", session_id=session_id)
        with SessionLocal() as session:
            if session.query(AgentSession).filter(AgentSession.session_id == session_id).one_or_none() is not None:
                return _failure("session_already_exists", f"session already exists: {session_id}", session_id=session_id)
            row = AgentSession(
                session_id=session_id,
                source=str(payload.get("source") or "user"),
                project_key=payload.get("project_key"),
                entrypoint_type=str(payload.get("entrypoint_type") or "chat"),
                goal=str(payload.get("goal") or ""),
                status=str(payload.get("status") or "pending"),
                current_phase=str(payload.get("current_phase") or "research"),
                compat_mode=bool(payload.get("compat_mode")),
                compat_job_id=payload.get("compat_job_id"),
                logical_task_list_key=payload.get("logical_task_list_key"),
                root_task_id=payload.get("root_task_id"),
                metadata_json=dict(payload.get("metadata") or {}),
                final_summary=payload.get("final_summary"),
                final_result=dict(payload.get("final_result") or {}),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _session_row_to_dict(row)

    def update_session(self, session_id: str, changes: AgentSessionPayload) -> AgentSessionRecord | Failure:
        if (failure := _json_fields_failure(changes, ("metadata", "final_result"))) is not None:
            return failure
        with SessionLocal() as session:
            row = self._must_get_session_row(session, session_id)
            if isinstance(row, Failure):
                return row
            if "source" in changes:
                row.source = str(changes["source"] or "user")
            if "project_key" in changes:
                row.project_key = changes["project_key"]
            if "entrypoint_type" in changes:
                row.entrypoint_type = str(changes["entrypoint_type"] or "chat")
            if "goal" in changes:
                row.goal = str(changes["goal"] or "")
            if "status" in changes:
                row.status = str(changes["status"] or row.status)
            if "current_phase" in changes:
                row.current_phase = str(changes["current_phase"] or row.current_phase)
            if "compat_mode" in changes:
                row.compat_mode = bool(changes["compat_mode"])
            if "compat_job_id" in changes:
                row.compat_job_id = changes["compat_job_id"]
            if "logical_task_list_key" in changes:
                row.logical_task_list_key = changes["logical_task_list_key"]
            if "root_task_id" in changes:
                row.root_task_id = changes["root_task_id"]
            if "metadata" in changes:
                row.metadata_json = dict(changes["metadata"] or {})
            if "final_summary" in changes:
                row.final_summary = changes["final_summary"]
            if "final_result" in changes:
                row.final_result = dict(changes["final_result"] or {})
            session.commit()
            session.refresh(row)
            return _session_row_to_dict(row)

    def get_session(self, session_id: str) -> AgentSessionRecord | Failure:
        with SessionLocal() as session:
            row = self._must_get_session_row(session, session_id)
            return row if isinstance(row, Failure) else _session_row_to_dict(row)

    def list_sessions(self, *, limit: int = 50) -> list[AgentSessionRecord]:
        with SessionLocal() as session:
            rows = (
                session.query(AgentSession)
                .order_by(AgentSession.updated_at.desc(), AgentSession.created_at.desc())
                .limit(max(1, int(limit)))
                .all()
            )
            return [_session_row_to_dict(row) for row in rows]

    def find_session_by_compat_job_id(self, compat_job_id: str) -> AgentSessionRecord | None:
        target = str(compat_job_id or "").strip()
        if not target:
            return None
        with SessionLocal() as session:
            row = session.query(AgentSession).filter(AgentSession.compat_job_id == target).one_or_none()
            return None if row is None else _session_row_to_dict(row)

    def find_session_by_native_thread_id(self, thread_id: str) -> AgentSessionRecord | None | Failure:
        target = str(thread_id or "").strip()
        if not target:
            return None
        with SessionLocal() as session:
            rows = (
                session.query(AgentSession)
                .filter(
                    AgentSession.source == "codex_webui_host",
                    AgentSession.entrypoint_type == "codex_native_thread",
                    AgentSession.metadata_json["native_thread_id"].as_string() == target,
                )
                .limit(2)
                .all()
            )
            if len(rows) > 1:
                return _failure("session_already_exists", "native thread has multiple MRW session bindings", thread_id=target)
            return _session_row_to_dict(rows[0]) if rows else None

    def find_session_by_logical_task_list_key(self, logical_task_list_key: str) -> AgentSessionRecord | None:
        target = str(logical_task_list_key or "").strip()
        if not target:
            return None
        with SessionLocal() as session:
            row = session.query(AgentSession).filter(AgentSession.logical_task_list_key == target).one_or_none()
            return None if row is None else _session_row_to_dict(row)

    def create_task(self, payload: AgentTaskPayload) -> AgentTaskRecord | Failure:
        if (failure := _json_fields_failure(payload, ("task_spec", "metadata", "result_payload"))) is not None:
            return failure
        session_id = str(payload.get("session_id") or "").strip()
        task_id = str(payload.get("task_id") or "").strip()
        if not session_id or not task_id:
            return _failure("task_identity_required", "session_id and task_id are required", session_id=session_id, task_id=task_id)
        with SessionLocal() as session:
            parent = self._must_get_session_row(session, session_id)
            if isinstance(parent, Failure):
                return parent
            row = AgentTask(
                task_id=task_id,
                session_id=session_id,
                parent_task_id=payload.get("parent_task_id"),
                subject=str(payload.get("subject") or ""),
                description=payload.get("description"),
                task_type=str(payload.get("task_type") or ""),
                phase=str(payload.get("phase") or "research"),
                status=str(payload.get("status") or "pending"),
                execution_mode=str(payload.get("execution_mode") or "worker"),
                owner=payload.get("owner"),
                blocked_by=list(payload.get("blocked_by") or []),
                blocks=list(payload.get("blocks") or []),
                priority=int(payload.get("priority") or 5),
                write_set=list(payload.get("write_set") or []),
                read_set=list(payload.get("read_set") or []),
                task_spec=dict(payload.get("task_spec") or {}),
                metadata_json=dict(payload.get("metadata") or {}),
                result_summary=payload.get("result_summary"),
                result_payload=dict(payload.get("result_payload") or {}),
                tool_use_count=int(payload.get("tool_use_count") or 0),
                token_usage=int(payload.get("token_usage") or 0),
                last_activity=payload.get("last_activity"),
                recent_activities=list(payload.get("recent_activities") or []),
                summary_label=payload.get("summary_label"),
                lease_until=payload.get("lease_until"),
                claimed_at=payload.get("claimed_at"),
                started_at=payload.get("started_at"),
                completed_at=payload.get("completed_at"),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _task_row_to_dict(row)

    def transition_task(
        self,
        session_id: str,
        *,
        primary: AgentTaskTransitionMutation,
        related: list[AgentTaskTransitionMutation],
        session_changes: AgentSessionPayload,
        events: list[AgentEventPayload],
    ) -> AgentTaskTransitionResult | Failure:
        mutations = [primary, *related]
        task_ids = [item["task_id"] for item in mutations]
        if len(set(task_ids)) != len(task_ids):
            return _failure("task_transition_conflict", "task transition contains duplicate task mutations")
        if (failure := _json_fields_failure(session_changes, ("metadata", "final_result"))) is not None:
            return failure
        for mutation in mutations:
            if (failure := _json_fields_failure(
                mutation["changes"], ("task_spec", "metadata", "result_payload")
            )) is not None:
                return failure
        for event in events:
            if (failure := _json_fields_failure(event, ("payload",))) is not None:
                return failure

        with SessionLocal() as session:
            try:
                parent = (
                    session.query(AgentSession)
                    .filter(AgentSession.session_id == session_id)
                    .with_for_update()
                    .one_or_none()
                )
                if parent is None:
                    return _failure("session_not_found", f"session not found: {session_id}", session_id=session_id)
                rows = (
                    session.query(AgentTask)
                    .filter(AgentTask.session_id == session_id, AgentTask.task_id.in_(sorted(task_ids)))
                    .order_by(AgentTask.task_id.asc())
                    .with_for_update()
                    .all()
                )
                rows_by_id = {str(row.task_id): row for row in rows}
                for mutation in mutations:
                    row = rows_by_id.get(mutation["task_id"])
                    if row is None:
                        return _failure(
                            "task_not_found",
                            f"task not found: {mutation['task_id']}",
                            session_id=session_id,
                            task_id=mutation["task_id"],
                        )
                    if (
                        str(row.status or "") not in mutation["expected_statuses"]
                        or row.owner != mutation["expected_owner"]
                    ):
                        return _transition_precondition_failure(
                            session_id=session_id,
                            task_id=mutation["task_id"],
                            status=str(row.status or ""),
                            owner=row.owner,
                        )

                for mutation in mutations:
                    row = rows_by_id[mutation["task_id"]]
                    changes = mutation["changes"]
                    if "parent_task_id" in changes:
                        row.parent_task_id = changes["parent_task_id"]
                    if "subject" in changes:
                        row.subject = str(changes["subject"] or row.subject)
                    if "description" in changes:
                        row.description = changes["description"]
                    if "task_type" in changes:
                        row.task_type = str(changes["task_type"] or row.task_type)
                    if "phase" in changes:
                        row.phase = str(changes["phase"] or row.phase)
                    if "status" in changes:
                        row.status = str(changes["status"] or row.status)
                    if "execution_mode" in changes:
                        row.execution_mode = str(changes["execution_mode"] or row.execution_mode)
                    if "owner" in changes:
                        row.owner = changes["owner"]
                    if "blocked_by" in changes:
                        row.blocked_by = list(changes["blocked_by"] or [])
                    if "blocks" in changes:
                        row.blocks = list(changes["blocks"] or [])
                    if "priority" in changes:
                        row.priority = int(changes["priority"] or row.priority or 5)
                    if "write_set" in changes:
                        row.write_set = list(changes["write_set"] or [])
                    if "read_set" in changes:
                        row.read_set = list(changes["read_set"] or [])
                    if "task_spec" in changes:
                        row.task_spec = dict(changes["task_spec"] or {})
                    if "metadata" in changes:
                        row.metadata_json = dict(changes["metadata"] or {})
                    if "result_summary" in changes:
                        row.result_summary = changes["result_summary"]
                    if "result_payload" in changes:
                        row.result_payload = dict(changes["result_payload"] or {})
                    if "tool_use_count" in changes:
                        row.tool_use_count = int(changes["tool_use_count"] or 0)
                    if "token_usage" in changes:
                        row.token_usage = int(changes["token_usage"] or 0)
                    if "last_activity" in changes:
                        row.last_activity = changes["last_activity"]
                    if "recent_activities" in changes:
                        row.recent_activities = list(changes["recent_activities"] or [])
                    if "summary_label" in changes:
                        row.summary_label = changes["summary_label"]
                    if "lease_until" in changes:
                        row.lease_until = changes["lease_until"]
                    if "claimed_at" in changes:
                        row.claimed_at = changes["claimed_at"]
                    if "started_at" in changes:
                        row.started_at = changes["started_at"]
                    if "completed_at" in changes:
                        row.completed_at = changes["completed_at"]

                if "source" in session_changes:
                    parent.source = str(session_changes["source"] or "user")
                if "project_key" in session_changes:
                    parent.project_key = session_changes["project_key"]
                if "entrypoint_type" in session_changes:
                    parent.entrypoint_type = str(session_changes["entrypoint_type"] or "chat")
                if "goal" in session_changes:
                    parent.goal = str(session_changes["goal"] or "")
                if "status" in session_changes:
                    parent.status = str(session_changes["status"] or parent.status)
                if "current_phase" in session_changes:
                    parent.current_phase = str(session_changes["current_phase"] or parent.current_phase)
                if "compat_mode" in session_changes:
                    parent.compat_mode = bool(session_changes["compat_mode"])
                if "compat_job_id" in session_changes:
                    parent.compat_job_id = session_changes["compat_job_id"]
                if "logical_task_list_key" in session_changes:
                    parent.logical_task_list_key = session_changes["logical_task_list_key"]
                if "root_task_id" in session_changes:
                    parent.root_task_id = session_changes["root_task_id"]
                if "metadata" in session_changes:
                    parent.metadata_json = dict(session_changes["metadata"] or {})
                if "final_summary" in session_changes:
                    parent.final_summary = session_changes["final_summary"]
                if "final_result" in session_changes:
                    parent.final_result = dict(session_changes["final_result"] or {})

                seq = int(
                    session.query(func.coalesce(func.max(AgentEvent.seq), 0))
                    .filter(AgentEvent.session_id == session_id)
                    .scalar()
                    or 0
                )
                event_rows: list[object] = []
                for offset, event in enumerate(events, start=1):
                    event_row = AgentEvent(
                        session_id=session_id,
                        seq=seq + offset,
                        event_type=str(event.get("event_type") or "task.updated"),
                        task_id=str(event.get("task_id") or "").strip() or None,
                        payload=dict(event.get("payload") or {}),
                    )
                    session.add(event_row)
                    event_rows.append(event_row)
                parent.updated_at = _utcnow()
                session.flush()
                result: AgentTaskTransitionResult = {
                    "task": _task_row_to_dict(rows_by_id[primary["task_id"]]),
                    "related_tasks": [_task_row_to_dict(rows_by_id[item["task_id"]]) for item in related],
                    "session": _session_row_to_dict(parent),
                    "events": [_event_row_to_dict(row) for row in event_rows],
                }
                session.commit()
                return result
            except SQLAlchemyError as exc:
                session.rollback()
                return _backend_operation_failure("transition_task", exc)

    def transition_session(
        self,
        session_id: str,
        *,
        expected_statuses: list[str],
        session_changes: AgentSessionPayload,
        events: list[AgentEventPayload],
    ) -> AgentSessionTransitionResult | Failure:
        if (failure := _json_fields_failure(session_changes, ("metadata", "final_result"))) is not None:
            return failure
        for event in events:
            if (failure := _json_fields_failure(event, ("payload",))) is not None:
                return failure
        with SessionLocal() as session:
            try:
                parent = (
                    session.query(AgentSession)
                    .filter(AgentSession.session_id == session_id)
                    .with_for_update()
                    .one_or_none()
                )
                if parent is None:
                    return _failure("session_not_found", f"session not found: {session_id}", session_id=session_id)
                if str(parent.status or "") not in expected_statuses:
                    return _failure(
                        "status_invalid",
                        "session changed before the transition could be committed",
                        session_id=session_id,
                        status=str(parent.status or ""),
                    )
                if "status" in session_changes:
                    parent.status = str(session_changes["status"] or parent.status)
                if "current_phase" in session_changes:
                    parent.current_phase = str(session_changes["current_phase"] or parent.current_phase)
                if "final_summary" in session_changes:
                    parent.final_summary = session_changes["final_summary"]
                if "final_result" in session_changes:
                    parent.final_result = dict(session_changes["final_result"] or {})
                if "metadata" in session_changes:
                    parent.metadata_json = dict(session_changes["metadata"] or {})
                seq = int(
                    session.query(func.coalesce(func.max(AgentEvent.seq), 0))
                    .filter(AgentEvent.session_id == session_id)
                    .scalar()
                    or 0
                )
                event_rows: list[object] = []
                for offset, event in enumerate(events, start=1):
                    row = AgentEvent(
                        session_id=session_id,
                        seq=seq + offset,
                        event_type=str(event.get("event_type") or "session.updated"),
                        task_id=str(event.get("task_id") or "").strip() or None,
                        payload=dict(event.get("payload") or {}),
                    )
                    session.add(row)
                    event_rows.append(row)
                parent.updated_at = _utcnow()
                session.flush()
                result: AgentSessionTransitionResult = {
                    "session": _session_row_to_dict(parent),
                    "events": [_event_row_to_dict(row) for row in event_rows],
                }
                session.commit()
                return result
            except SQLAlchemyError as exc:
                session.rollback()
                return _backend_operation_failure("transition_session", exc)

    def commit_session_command(
        self,
        session_id: str,
        *,
        session_create: AgentSessionPayload | None,
        expected_session_statuses: list[str] | None,
        session_changes: AgentSessionPayload,
        task_creates: list[AgentTaskPayload],
        task_mutations: list[AgentTaskTransitionMutation],
        message_creates: list[AgentMessagePayload],
        artifact_upserts: list[AgentArtifactPayload],
        approval_mutation: AgentApprovalTransitionMutation | None,
        events: list[AgentEventPayload],
    ) -> AgentSessionCommandResult | Failure:
        failure = _session_command_failure(
            session_id,
            session_create=session_create,
            session_changes=session_changes,
            task_creates=task_creates,
            task_mutations=task_mutations,
            message_creates=message_creates,
            artifact_upserts=artifact_upserts,
            approval_mutation=approval_mutation,
            events=events,
        )
        if failure is not None:
            return failure

        with SessionLocal() as session:
            try:
                if session_create is not None:
                    parent = (
                        session.query(AgentSession)
                        .filter(AgentSession.session_id == session_id)
                        .one_or_none()
                    )
                    if parent is not None:
                        return _failure(
                            "session_already_exists",
                            f"session already exists: {session_id}",
                            session_id=session_id,
                        )
                    parent = AgentSession(
                        session_id=session_id,
                        source=str(session_create.get("source") or "user"),
                        project_key=session_create.get("project_key"),
                        entrypoint_type=str(session_create.get("entrypoint_type") or "chat"),
                        goal=str(session_create.get("goal") or ""),
                        status=str(session_create.get("status") or "pending"),
                        current_phase=str(session_create.get("current_phase") or "research"),
                        compat_mode=bool(session_create.get("compat_mode")),
                        compat_job_id=session_create.get("compat_job_id"),
                        logical_task_list_key=session_create.get("logical_task_list_key"),
                        root_task_id=session_create.get("root_task_id"),
                        metadata_json=dict(session_create.get("metadata") or {}),
                        final_summary=session_create.get("final_summary"),
                        final_result=dict(session_create.get("final_result") or {}),
                    )
                    session.add(parent)
                    session.flush()
                else:
                    parent = (
                        session.query(AgentSession)
                        .filter(AgentSession.session_id == session_id)
                        .with_for_update()
                        .one_or_none()
                    )
                    if parent is None:
                        return _failure(
                            "session_not_found",
                            f"session not found: {session_id}",
                            session_id=session_id,
                        )
                    if (
                        expected_session_statuses is not None
                        and str(parent.status or "") not in expected_session_statuses
                    ):
                        return _failure(
                            "status_invalid",
                            "session changed before the command could be committed",
                            session_id=session_id,
                            status=str(parent.status or ""),
                        )

                mutation_ids = sorted(item["task_id"] for item in task_mutations)
                locked_rows = (
                    session.query(AgentTask)
                    .filter(
                        AgentTask.session_id == session_id,
                        AgentTask.task_id.in_(mutation_ids),
                    )
                    .order_by(AgentTask.task_id.asc())
                    .with_for_update()
                    .all()
                    if mutation_ids
                    else []
                )
                locked_by_id = {str(row.task_id): row for row in locked_rows}
                for mutation in task_mutations:
                    row = locked_by_id.get(mutation["task_id"])
                    if row is None:
                        return _failure(
                            "task_not_found",
                            f"task not found: {mutation['task_id']}",
                            session_id=session_id,
                            task_id=mutation["task_id"],
                        )
                    if (
                        str(row.status or "") not in mutation["expected_statuses"]
                        or row.owner != mutation["expected_owner"]
                    ):
                        return _transition_precondition_failure(
                            session_id=session_id,
                            task_id=mutation["task_id"],
                            status=str(row.status or ""),
                            owner=row.owner,
                        )

                approval_row = None
                approval_payload: AgentApprovalPayload | None = None
                if approval_mutation is not None:
                    approval_payload = approval_mutation["payload"]
                    approval_id = str(approval_payload.get("approval_id") or "").strip()
                    approval_row = (
                        session.query(AgentApproval)
                        .filter(AgentApproval.approval_id == approval_id)
                        .with_for_update()
                        .one_or_none()
                    )
                    expected_approval_statuses = approval_mutation["expected_statuses"]
                    if approval_row is None and expected_approval_statuses:
                        return _failure(
                            "approval_not_found",
                            f"approval not found: {approval_id}",
                            approval_id=approval_id,
                        )
                    if (
                        approval_row is not None
                        and expected_approval_statuses
                        and str(approval_row.status or "") not in expected_approval_statuses
                    ):
                        return _confirmation_status_failure(
                            approval_id,
                            str(approval_row.status or ""),
                        )
                    if (
                        approval_row is not None
                        and "expected_binding_payload" in approval_mutation
                        and dict(approval_row.binding_payload or {})
                        != approval_mutation["expected_binding_payload"]
                    ):
                        return _failure(
                            "status_invalid",
                            "approval binding changed before the command could be committed",
                            approval_id=approval_id,
                            host_code="host_approval_binding_mismatch",
                        )
                    if (
                        approval_row is not None
                        and "expected_requester_actor" in approval_mutation
                        and str(approval_row.requester_actor or "")
                        != approval_mutation["expected_requester_actor"]
                    ):
                        return _failure(
                            "status_invalid",
                            "approval requester changed before the command could be committed",
                            approval_id=approval_id,
                            host_code="host_confirmation_scope_mismatch",
                        )

                affected_rows: list[object] = []
                for payload in task_creates:
                    task_id = str(payload.get("task_id") or "").strip()
                    if not task_id:
                        return _failure(
                            "task_identity_required",
                            "session_id and task_id are required",
                            session_id=session_id,
                            task_id=task_id,
                        )
                    existing = (
                        session.query(AgentTask)
                        .filter(AgentTask.task_id == task_id)
                        .one_or_none()
                    )
                    if existing is not None:
                        return _failure(
                            "task_transition_conflict",
                            f"task already exists: {task_id}",
                            task_id=task_id,
                        )
                    row = AgentTask(
                        task_id=task_id,
                        session_id=session_id,
                        parent_task_id=payload.get("parent_task_id"),
                        subject=str(payload.get("subject") or ""),
                        description=payload.get("description"),
                        task_type=str(payload.get("task_type") or ""),
                        phase=str(payload.get("phase") or "research"),
                        status=str(payload.get("status") or "pending"),
                        execution_mode=str(payload.get("execution_mode") or "worker"),
                        owner=payload.get("owner"),
                        blocked_by=list(payload.get("blocked_by") or []),
                        blocks=list(payload.get("blocks") or []),
                        priority=int(payload.get("priority") or 5),
                        write_set=list(payload.get("write_set") or []),
                        read_set=list(payload.get("read_set") or []),
                        task_spec=dict(payload.get("task_spec") or {}),
                        metadata_json=dict(payload.get("metadata") or {}),
                        result_summary=payload.get("result_summary"),
                        result_payload=dict(payload.get("result_payload") or {}),
                        tool_use_count=int(payload.get("tool_use_count") or 0),
                        token_usage=int(payload.get("token_usage") or 0),
                        last_activity=payload.get("last_activity"),
                        recent_activities=list(payload.get("recent_activities") or []),
                        summary_label=payload.get("summary_label"),
                        lease_until=payload.get("lease_until"),
                        claimed_at=payload.get("claimed_at"),
                        started_at=payload.get("started_at"),
                        completed_at=payload.get("completed_at"),
                    )
                    session.add(row)
                    affected_rows.append(row)

                for mutation in task_mutations:
                    row = locked_by_id[mutation["task_id"]]
                    changes = mutation["changes"]
                    if "parent_task_id" in changes:
                        row.parent_task_id = changes["parent_task_id"]
                    if "subject" in changes:
                        row.subject = str(changes["subject"] or row.subject)
                    if "description" in changes:
                        row.description = changes["description"]
                    if "task_type" in changes:
                        row.task_type = str(changes["task_type"] or row.task_type)
                    if "phase" in changes:
                        row.phase = str(changes["phase"] or row.phase)
                    if "status" in changes:
                        row.status = str(changes["status"] or row.status)
                    if "execution_mode" in changes:
                        row.execution_mode = str(changes["execution_mode"] or row.execution_mode)
                    if "owner" in changes:
                        row.owner = changes["owner"]
                    if "blocked_by" in changes:
                        row.blocked_by = list(changes["blocked_by"] or [])
                    if "blocks" in changes:
                        row.blocks = list(changes["blocks"] or [])
                    if "priority" in changes:
                        row.priority = int(changes["priority"] or row.priority or 5)
                    if "write_set" in changes:
                        row.write_set = list(changes["write_set"] or [])
                    if "read_set" in changes:
                        row.read_set = list(changes["read_set"] or [])
                    if "task_spec" in changes:
                        row.task_spec = dict(changes["task_spec"] or {})
                    if "metadata" in changes:
                        row.metadata_json = dict(changes["metadata"] or {})
                    if "result_summary" in changes:
                        row.result_summary = changes["result_summary"]
                    if "result_payload" in changes:
                        row.result_payload = dict(changes["result_payload"] or {})
                    if "tool_use_count" in changes:
                        row.tool_use_count = int(changes["tool_use_count"] or 0)
                    if "token_usage" in changes:
                        row.token_usage = int(changes["token_usage"] or 0)
                    if "last_activity" in changes:
                        row.last_activity = changes["last_activity"]
                    if "recent_activities" in changes:
                        row.recent_activities = list(changes["recent_activities"] or [])
                    if "summary_label" in changes:
                        row.summary_label = changes["summary_label"]
                    if "lease_until" in changes:
                        row.lease_until = changes["lease_until"]
                    if "claimed_at" in changes:
                        row.claimed_at = changes["claimed_at"]
                    if "started_at" in changes:
                        row.started_at = changes["started_at"]
                    if "completed_at" in changes:
                        row.completed_at = changes["completed_at"]
                    affected_rows.append(row)

                message_rows: list[object] = []
                for payload in message_creates:
                    row = AgentMessage(
                        session_id=session_id,
                        task_id=payload.get("task_id"),
                        role=str(payload.get("role") or "system"),
                        actor=payload.get("actor"),
                        content=str(payload.get("content") or ""),
                        metadata_json=dict(payload.get("metadata") or {}),
                    )
                    session.add(row)
                    message_rows.append(row)

                artifact_rows: list[object] = []
                for payload in artifact_upserts:
                    name = str(payload.get("name") or "").strip()
                    if not name:
                        return _failure(
                            "artifact_identity_required",
                            "session_id and name are required",
                            session_id=session_id,
                            name=name,
                        )
                    row = (
                        session.query(AgentArtifact)
                        .filter(
                            AgentArtifact.session_id == session_id,
                            AgentArtifact.name == name,
                        )
                        .with_for_update()
                        .one_or_none()
                    )
                    if row is None:
                        row = AgentArtifact(
                            artifact_id=str(payload.get("artifact_id") or f"artifact-{uuid4().hex[:16]}"),
                            session_id=session_id,
                            task_id=payload.get("task_id"),
                            artifact_type=str(payload.get("artifact_type") or "generic"),
                            name=name,
                            mime_type=payload.get("mime_type"),
                            content_text=payload.get("content_text"),
                            content_json=dict(payload.get("content_json") or {}),
                            metadata_json=dict(payload.get("metadata") or {}),
                        )
                        session.add(row)
                    else:
                        row.task_id = payload.get("task_id", row.task_id)
                        row.artifact_type = str(payload.get("artifact_type") or row.artifact_type)
                        row.mime_type = payload.get("mime_type", row.mime_type)
                        row.content_text = payload.get("content_text", row.content_text)
                        row.content_json = dict(payload.get("content_json") or {})
                        row.metadata_json = dict(payload.get("metadata") or {})
                    artifact_rows.append(row)

                if approval_payload is not None:
                    if approval_row is None:
                        approval_row = AgentApproval(
                            approval_id=str(approval_payload.get("approval_id") or ""),
                            binding_hash=str(approval_payload.get("binding_hash") or ""),
                            binding_payload=dict(approval_payload.get("binding_payload") or {}),
                            requester_session_id=approval_payload.get("requester_session_id"),
                            requester_task_id=approval_payload.get("requester_task_id"),
                            requester_actor=str(approval_payload.get("requester_actor") or "unknown"),
                            approved_by=approval_payload.get("approved_by"),
                            approved_at=approval_payload.get("approved_at"),
                            expires_at=approval_payload.get("expires_at"),
                            status=str(approval_payload.get("status") or "pending"),
                            audit_log=list(approval_payload.get("audit_log") or []),
                            metadata_json=dict(approval_payload.get("metadata") or {}),
                        )
                        session.add(approval_row)
                    else:
                        approval_row.binding_hash = str(approval_payload.get("binding_hash") or approval_row.binding_hash)
                        approval_row.binding_payload = dict(approval_payload.get("binding_payload") or {})
                        approval_row.requester_session_id = approval_payload.get(
                            "requester_session_id", approval_row.requester_session_id
                        )
                        approval_row.requester_task_id = approval_payload.get(
                            "requester_task_id", approval_row.requester_task_id
                        )
                        approval_row.requester_actor = str(
                            approval_payload.get("requester_actor") or approval_row.requester_actor or "unknown"
                        )
                        approval_row.approved_by = approval_payload.get("approved_by", approval_row.approved_by)
                        approval_row.approved_at = approval_payload.get("approved_at", approval_row.approved_at)
                        approval_row.expires_at = approval_payload.get("expires_at", approval_row.expires_at)
                        approval_row.status = str(approval_payload.get("status") or approval_row.status)
                        approval_row.audit_log = list(approval_payload.get("audit_log") or [])
                        approval_row.metadata_json = dict(approval_payload.get("metadata") or {})

                if "source" in session_changes:
                    parent.source = str(session_changes["source"] or "user")
                if "project_key" in session_changes:
                    parent.project_key = session_changes["project_key"]
                if "entrypoint_type" in session_changes:
                    parent.entrypoint_type = str(session_changes["entrypoint_type"] or "chat")
                if "goal" in session_changes:
                    parent.goal = str(session_changes["goal"] or "")
                if "status" in session_changes:
                    parent.status = str(session_changes["status"] or parent.status)
                if "current_phase" in session_changes:
                    parent.current_phase = str(session_changes["current_phase"] or parent.current_phase)
                if "compat_mode" in session_changes:
                    parent.compat_mode = bool(session_changes["compat_mode"])
                if "compat_job_id" in session_changes:
                    parent.compat_job_id = session_changes["compat_job_id"]
                if "logical_task_list_key" in session_changes:
                    parent.logical_task_list_key = session_changes["logical_task_list_key"]
                if "root_task_id" in session_changes:
                    parent.root_task_id = session_changes["root_task_id"]
                if "metadata" in session_changes:
                    parent.metadata_json = dict(session_changes["metadata"] or {})
                if "final_summary" in session_changes:
                    parent.final_summary = session_changes["final_summary"]
                if "final_result" in session_changes:
                    parent.final_result = dict(session_changes["final_result"] or {})

                seq = int(
                    session.query(func.coalesce(func.max(AgentEvent.seq), 0))
                    .filter(AgentEvent.session_id == session_id)
                    .scalar()
                    or 0
                )
                event_rows: list[object] = []
                for offset, event in enumerate(events, start=1):
                    row = AgentEvent(
                        session_id=session_id,
                        seq=seq + offset,
                        event_type=str(event.get("event_type") or "session.updated"),
                        task_id=str(event.get("task_id") or "").strip() or None,
                        payload=dict(event.get("payload") or {}),
                    )
                    session.add(row)
                    event_rows.append(row)
                parent.updated_at = _utcnow()
                session.flush()
                result: AgentSessionCommandResult = {
                    "session": _session_row_to_dict(parent),
                    "tasks": [_task_row_to_dict(row) for row in affected_rows],
                    "messages": [_message_row_to_dict(row) for row in message_rows],
                    "artifacts": [_artifact_row_to_dict(row) for row in artifact_rows],
                    "approval": _approval_row_to_dict(approval_row) if approval_row is not None else None,
                    "events": [_event_row_to_dict(row) for row in event_rows],
                }
                session.commit()
                return result
            except SQLAlchemyError as exc:
                session.rollback()
                return _backend_operation_failure("commit_session_command", exc)

    def get_task(self, session_id: str, task_id: str) -> AgentTaskRecord | Failure:
        with SessionLocal() as session:
            row = self._must_get_task_row(session, session_id, task_id)
            return row if isinstance(row, Failure) else _task_row_to_dict(row)

    def update_task(self, session_id: str, task_id: str, changes: AgentTaskPayload) -> AgentTaskRecord | Failure:
        if (failure := _json_fields_failure(changes, ("task_spec", "metadata", "result_payload"))) is not None:
            return failure
        with SessionLocal() as session:
            row = self._must_get_task_row(session, session_id, task_id)
            if isinstance(row, Failure):
                return row
            if "parent_task_id" in changes:
                row.parent_task_id = changes["parent_task_id"]
            if "subject" in changes:
                row.subject = str(changes["subject"] or row.subject)
            if "description" in changes:
                row.description = changes["description"]
            if "task_type" in changes:
                row.task_type = str(changes["task_type"] or row.task_type)
            if "phase" in changes:
                row.phase = str(changes["phase"] or row.phase)
            if "status" in changes:
                row.status = str(changes["status"] or row.status)
            if "execution_mode" in changes:
                row.execution_mode = str(changes["execution_mode"] or row.execution_mode)
            if "owner" in changes:
                row.owner = changes["owner"]
            if "blocked_by" in changes:
                row.blocked_by = list(changes["blocked_by"] or [])
            if "blocks" in changes:
                row.blocks = list(changes["blocks"] or [])
            if "priority" in changes:
                row.priority = int(changes["priority"] or row.priority or 5)
            if "write_set" in changes:
                row.write_set = list(changes["write_set"] or [])
            if "read_set" in changes:
                row.read_set = list(changes["read_set"] or [])
            if "task_spec" in changes:
                row.task_spec = dict(changes["task_spec"] or {})
            if "metadata" in changes:
                row.metadata_json = dict(changes["metadata"] or {})
            if "result_summary" in changes:
                row.result_summary = changes["result_summary"]
            if "result_payload" in changes:
                row.result_payload = dict(changes["result_payload"] or {})
            if "tool_use_count" in changes:
                row.tool_use_count = int(changes["tool_use_count"] or 0)
            if "token_usage" in changes:
                row.token_usage = int(changes["token_usage"] or 0)
            if "last_activity" in changes:
                row.last_activity = changes["last_activity"]
            if "recent_activities" in changes:
                row.recent_activities = list(changes["recent_activities"] or [])
            if "summary_label" in changes:
                row.summary_label = changes["summary_label"]
            if "lease_until" in changes:
                row.lease_until = changes["lease_until"]
            if "claimed_at" in changes:
                row.claimed_at = changes["claimed_at"]
            if "started_at" in changes:
                row.started_at = changes["started_at"]
            if "completed_at" in changes:
                row.completed_at = changes["completed_at"]
            session.commit()
            session.refresh(row)
            return _task_row_to_dict(row)

    def list_tasks(self, session_id: str) -> list[AgentTaskRecord] | Failure:
        with SessionLocal() as session:
            parent = self._must_get_session_row(session, session_id)
            if isinstance(parent, Failure):
                return parent
            rows = (
                session.query(AgentTask)
                .filter(AgentTask.session_id == session_id)
                .order_by(AgentTask.created_at.asc(), AgentTask.id.asc())
                .all()
            )
            return [_task_row_to_dict(row) for row in rows]

    def create_message(self, payload: AgentMessagePayload) -> AgentMessageRecord | Failure:
        if (failure := _json_fields_failure(payload, ("metadata",))) is not None:
            return failure
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id:
            return _failure("session_id_required", "session_id is required", session_id=session_id)
        with SessionLocal() as session:
            parent = self._must_get_session_row(session, session_id)
            if isinstance(parent, Failure):
                return parent
            row = AgentMessage(
                session_id=session_id,
                task_id=payload.get("task_id"),
                role=str(payload.get("role") or "system"),
                actor=payload.get("actor"),
                content=str(payload.get("content") or ""),
                metadata_json=dict(payload.get("metadata") or {}),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _message_row_to_dict(row)

    def list_messages(self, session_id: str) -> list[AgentMessageRecord] | Failure:
        with SessionLocal() as session:
            parent = self._must_get_session_row(session, session_id)
            if isinstance(parent, Failure):
                return parent
            rows = (
                session.query(AgentMessage)
                .filter(AgentMessage.session_id == session_id)
                .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
                .all()
            )
            return [_message_row_to_dict(row) for row in rows]

    def upsert_artifact(self, payload: AgentArtifactPayload) -> AgentArtifactRecord | Failure:
        if (failure := _json_fields_failure(payload, ("content_json", "metadata"))) is not None:
            return failure
        session_id = str(payload.get("session_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not session_id or not name:
            return _failure("artifact_identity_required", "session_id and name are required", session_id=session_id, name=name)
        with SessionLocal() as session:
            parent = self._must_get_session_row(session, session_id)
            if isinstance(parent, Failure):
                return parent
            row = (
                session.query(AgentArtifact)
                .filter(AgentArtifact.session_id == session_id, AgentArtifact.name == name)
                .one_or_none()
            )
            if row is None:
                row = AgentArtifact(
                    artifact_id=str(payload.get("artifact_id") or f"artifact-{uuid4().hex[:16]}"),
                    session_id=session_id,
                    task_id=payload.get("task_id"),
                    artifact_type=str(payload.get("artifact_type") or "generic"),
                    name=name,
                    mime_type=payload.get("mime_type"),
                    content_text=payload.get("content_text"),
                    content_json=dict(payload.get("content_json") or {}),
                    metadata_json=dict(payload.get("metadata") or {}),
                )
                session.add(row)
            else:
                row.task_id = payload.get("task_id", row.task_id)
                row.artifact_type = str(payload.get("artifact_type") or row.artifact_type)
                row.mime_type = payload.get("mime_type", row.mime_type)
                row.content_text = payload.get("content_text", row.content_text)
                row.content_json = dict(payload.get("content_json") or {})
                row.metadata_json = dict(payload.get("metadata") or {})
            session.commit()
            session.refresh(row)
            return _artifact_row_to_dict(row)

    def list_artifacts(self, session_id: str) -> list[AgentArtifactRecord] | Failure:
        with SessionLocal() as session:
            parent = self._must_get_session_row(session, session_id)
            if isinstance(parent, Failure):
                return parent
            rows = (
                session.query(AgentArtifact)
                .filter(AgentArtifact.session_id == session_id)
                .order_by(AgentArtifact.name.asc(), AgentArtifact.updated_at.asc())
                .all()
            )
            return [_artifact_row_to_dict(row) for row in rows]

    def upsert_project_artifact(self, payload: AgentArtifactPayload) -> AgentArtifactRecord | Failure:
        if (failure := _json_fields_failure(payload, ("content_json", "metadata"))) is not None:
            return failure
        project_key = str(payload.get("project_key") or "").strip()
        name = str(payload.get("name") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        if not project_key or not name or not session_id:
            return _failure("artifact_identity_required", "project_key, name and session_id are required")
        with SessionLocal() as session:
            row = None
            for candidate in session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "agent_macro.registration_package").all():
                metadata = dict(candidate.metadata_json or {})
                if metadata.get("project_key") == project_key and candidate.name == name:
                    row = candidate
                    break
            if row is None:
                row = AgentArtifact(
                    artifact_id=str(payload.get("artifact_id") or f"artifact-{uuid4().hex[:16]}"),
                    session_id=session_id,
                    task_id=payload.get("task_id"),
                    artifact_type=str(payload.get("artifact_type") or "agent_macro.registration_package"),
                    name=name,
                    mime_type=payload.get("mime_type"),
                    content_text=payload.get("content_text"),
                    content_json=dict(payload.get("content_json") or {}),
                    metadata_json={**dict(payload.get("metadata") or {}), "project_key": project_key, "project_scope": True},
                )
                session.add(row)
            else:
                row.content_text = payload.get("content_text", row.content_text)
                row.content_json = dict(payload.get("content_json") or {})
                row.metadata_json = {**dict(payload.get("metadata") or {}), "project_key": project_key, "project_scope": True}
            session.commit()
            session.refresh(row)
            return _artifact_row_to_dict(row)

    def get_project_artifact(self, *, project_key: str, name: str) -> AgentArtifactRecord | None:
        with SessionLocal() as session:
            for row in session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "agent_macro.registration_package").all():
                metadata = dict(row.metadata_json or {})
                if metadata.get("project_key") == str(project_key or "") and row.name == str(name or ""):
                    return _artifact_row_to_dict(row)
        return None

    def list_project_artifacts(self, *, project_key: str) -> list[AgentArtifactRecord] | Failure:
        project = str(project_key or "").strip()
        if not project:
            return _failure("artifact_identity_required", "project_key is required")
        with SessionLocal() as session:
            rows = (
                session.query(AgentArtifact)
                .filter(
                    AgentArtifact.artifact_type == "agent_macro.registration_package",
                    AgentArtifact.metadata_json["project_key"].as_string() == project,
                    AgentArtifact.metadata_json["project_scope"].as_boolean().is_(True),
                )
                .order_by(AgentArtifact.name.asc(), AgentArtifact.updated_at.asc())
                .all()
            )
            return [_artifact_row_to_dict(row) for row in rows]

    def append_event(
        self,
        session_id: str,
        *,
        event_type: str,
        task_id: str | None = None,
        payload: JsonObject | None = None,
    ) -> AgentEventRecord | Failure:
        event_payload = payload or {}
        if (failure := _json_object_failure(event_payload, field="payload")) is not None:
            return failure
        with SessionLocal() as session:
            try:
                parent = (
                    session.query(AgentSession)
                    .filter(AgentSession.session_id == session_id)
                    .with_for_update()
                    .one_or_none()
                )
                if parent is None:
                    return _failure("session_not_found", f"session not found: {session_id}", session_id=session_id)
                seq = int(
                    session.query(func.coalesce(func.max(AgentEvent.seq), 0))
                    .filter(AgentEvent.session_id == session_id)
                    .scalar()
                    or 0
                ) + 1
                row = AgentEvent(
                    session_id=session_id,
                    seq=seq,
                    event_type=str(event_type),
                    task_id=str(task_id or "").strip() or None,
                    payload=dict(event_payload),
                )
                parent.updated_at = _utcnow()
                session.add(row)
                session.flush()
                result = _event_row_to_dict(row)
                session.commit()
                return result
            except SQLAlchemyError as exc:
                session.rollback()
                return _backend_operation_failure("append_event", exc)

    def list_events(self, session_id: str) -> list[AgentEventRecord] | Failure:
        with SessionLocal() as session:
            parent = self._must_get_session_row(session, session_id)
            if isinstance(parent, Failure):
                return parent
            rows = (
                session.query(AgentEvent)
                .filter(AgentEvent.session_id == session_id)
                .order_by(AgentEvent.seq.asc(), AgentEvent.id.asc())
                .all()
            )
            return [_event_row_to_dict(row) for row in rows]

    def create_or_update_approval(self, payload: AgentApprovalPayload) -> AgentApprovalRecord | Failure:
        if (failure := _json_fields_failure(payload, ("binding_payload", "metadata"))) is not None:
            return failure
        if "audit_log" in payload and (
            failure := _json_object_failure({"audit_log": payload.get("audit_log") or []}, field="audit_log")
        ) is not None:
            return failure
        approval_id = str(payload.get("approval_id") or "").strip()
        if not approval_id:
            return _failure("approval_id_required", "approval_id is required", approval_id=approval_id)
        with SessionLocal() as session:
            row = session.query(AgentApproval).filter(AgentApproval.approval_id == approval_id).one_or_none()
            if row is None:
                row = AgentApproval(
                    approval_id=approval_id,
                    binding_hash=str(payload.get("binding_hash") or ""),
                    binding_payload=dict(payload.get("binding_payload") or {}),
                    requester_session_id=payload.get("requester_session_id"),
                    requester_task_id=payload.get("requester_task_id"),
                    requester_actor=str(payload.get("requester_actor") or "unknown"),
                    approved_by=payload.get("approved_by"),
                    approved_at=payload.get("approved_at"),
                    expires_at=payload.get("expires_at"),
                    status=str(payload.get("status") or "pending"),
                    audit_log=list(payload.get("audit_log") or []),
                    metadata_json=dict(payload.get("metadata") or {}),
                )
                session.add(row)
            else:
                row.binding_hash = str(payload.get("binding_hash") or row.binding_hash)
                row.binding_payload = dict(payload.get("binding_payload") or {})
                row.requester_session_id = payload.get("requester_session_id", row.requester_session_id)
                row.requester_task_id = payload.get("requester_task_id", row.requester_task_id)
                row.requester_actor = str(payload.get("requester_actor") or row.requester_actor or "unknown")
                row.approved_by = payload.get("approved_by", row.approved_by)
                row.approved_at = payload.get("approved_at", row.approved_at)
                row.expires_at = payload.get("expires_at", row.expires_at)
                row.status = str(payload.get("status") or row.status)
                row.audit_log = list(payload.get("audit_log") or [])
                row.metadata_json = dict(payload.get("metadata") or {})
            session.commit()
            session.refresh(row)
            return _approval_row_to_dict(row)

    def get_approval(self, approval_id: str) -> AgentApprovalRecord | Failure:
        with SessionLocal() as session:
            row = session.query(AgentApproval).filter(AgentApproval.approval_id == approval_id).one_or_none()
            if row is None:
                return _failure("approval_not_found", f"approval not found: {approval_id}", approval_id=approval_id)
            return _approval_row_to_dict(row)

    def list_approvals(self, *, session_id: str | None = None) -> list[AgentApprovalRecord]:
        with SessionLocal() as session:
            query = session.query(AgentApproval)
            if session_id:
                query = query.filter(AgentApproval.requester_session_id == session_id)
            rows = query.order_by(AgentApproval.updated_at.desc(), AgentApproval.created_at.desc()).all()
            return [_approval_row_to_dict(row) for row in rows]

    def consume_host_approval(
        self,
        approval_id: str,
        *,
        expected_binding_payload: JsonObject | None = None,
        consumed_metadata: JsonObject | None = None,
        consumed_audit_log: list[JsonObject] | None = None,
    ) -> AgentApprovalRecord | Failure:
        for field, value in (
            ("expected_binding_payload", expected_binding_payload),
            ("consumed_metadata", consumed_metadata),
        ):
            if value is not None and (failure := _json_object_failure(value, field=field)) is not None:
                return failure
        if consumed_audit_log is not None and (
            failure := _json_object_failure(
                {"consumed_audit_log": consumed_audit_log},
                field="consumed_audit_log",
            )
        ) is not None:
            return failure
        approval_id = str(approval_id or "").strip()
        if not approval_id:
            return _failure("approval_id_required", "approval_id is required")
        with SessionLocal() as session:
            row = session.query(AgentApproval).filter(AgentApproval.approval_id == approval_id).one_or_none()
            if row is None:
                return _failure("approval_not_found", f"approval not found: {approval_id}", approval_id=approval_id)
            if expected_binding_payload is not None and dict(row.binding_payload or {}) != dict(
                expected_binding_payload or {}
            ):
                return _failure(
                    "status_invalid",
                    "approval binding does not match the expected action",
                    approval_id=approval_id,
                    host_code="host_approval_binding_mismatch",
                )
            if str(row.status or "") != "approved":
                return _consume_status_failure(approval_id, str(row.status or ""))
            metadata = dict(row.metadata_json or {})
            if consumed_metadata is not None:
                metadata.update(_clone(consumed_metadata))
            audit_log = [*list(row.audit_log or []), *list(consumed_audit_log or [])]
            updated = (
                session.query(AgentApproval)
                .filter(AgentApproval.approval_id == approval_id, AgentApproval.status == "approved")
                .update(
                    {
                        "status": "consumed",
                        "metadata_json": metadata,
                        "audit_log": audit_log,
                        "updated_at": _utcnow(),
                    },
                    synchronize_session=False,
                )
            )
            if updated == 0:
                session.rollback()
                fresh = session.query(AgentApproval).filter(AgentApproval.approval_id == approval_id).one_or_none()
                if fresh is None:
                    return _failure("approval_not_found", f"approval not found: {approval_id}", approval_id=approval_id)
                return _consume_status_failure(approval_id, str(fresh.status or ""))
            session.commit()
            fresh = session.query(AgentApproval).filter(AgentApproval.approval_id == approval_id).one()
            return _approval_row_to_dict(fresh)

    def confirm_host_approval(
        self,
        approval_id: str,
        *,
        expected_binding_payload: JsonObject | None = None,
        expected_requester_actor: str | None = None,
        approved: bool = True,
        approved_by: str = "",
        approved_at: datetime | None = None,
        confirmation_metadata: JsonObject | None = None,
        audit_log: list[JsonObject] | None = None,
    ) -> AgentApprovalRecord | Failure:
        for field, value in (
            ("expected_binding_payload", expected_binding_payload),
            ("confirmation_metadata", confirmation_metadata),
        ):
            if value is not None and (failure := _json_object_failure(value, field=field)) is not None:
                return failure
        if audit_log is not None and (
            failure := _json_object_failure({"audit_log": audit_log}, field="audit_log")
        ) is not None:
            return failure
        approval_id = str(approval_id or "").strip()
        if not approval_id:
            return _failure("approval_id_required", "approval_id is required")
        with SessionLocal() as session:
            row = session.query(AgentApproval).filter(AgentApproval.approval_id == approval_id).one_or_none()
            if row is None:
                return _failure("approval_not_found", f"approval not found: {approval_id}", approval_id=approval_id)
            if expected_binding_payload is not None and dict(row.binding_payload or {}) != dict(
                expected_binding_payload or {}
            ):
                return _failure(
                    "status_invalid",
                    "approval binding does not match the expected confirmation",
                    approval_id=approval_id,
                    host_code="host_confirmation_scope_mismatch",
                )
            if expected_requester_actor is not None and str(row.requester_actor or "") != str(
                expected_requester_actor
            ):
                return _failure(
                    "status_invalid",
                    "approval requester does not match the expected confirmation",
                    approval_id=approval_id,
                    host_code="host_confirmation_scope_mismatch",
                )
            if str(row.status or "") != "pending":
                return _confirmation_status_failure(approval_id, str(row.status or ""))
            metadata = dict(row.metadata_json or {})
            if confirmation_metadata is not None:
                metadata.update(_clone(confirmation_metadata))
            audit = [*list(row.audit_log or []), *list(audit_log or [])]
            updated = (
                session.query(AgentApproval)
                .filter(AgentApproval.approval_id == approval_id, AgentApproval.status == "pending")
                .update(
                    {
                        "status": "approved" if approved else "failed",
                        "approved_by": str(approved_by or "").strip() or "unknown",
                        "approved_at": approved_at if approved_at is not None else _utcnow(),
                        "metadata_json": metadata,
                        "audit_log": audit,
                        "updated_at": _utcnow(),
                    },
                    synchronize_session=False,
                )
            )
            if updated == 0:
                session.rollback()
                fresh = session.query(AgentApproval).filter(AgentApproval.approval_id == approval_id).one_or_none()
                if fresh is None:
                    return _failure("approval_not_found", f"approval not found: {approval_id}", approval_id=approval_id)
                return _confirmation_status_failure(approval_id, str(fresh.status or ""))
            session.commit()
            fresh = session.query(AgentApproval).filter(AgentApproval.approval_id == approval_id).one()
            return _approval_row_to_dict(fresh)

    @staticmethod
    def _must_get_session_row(session: Session, session_id: str) -> Any | Failure:
        row = session.query(AgentSession).filter(AgentSession.session_id == session_id).one_or_none()
        if row is None:
            return _failure("session_not_found", f"session not found: {session_id}", session_id=session_id)
        return row

    @staticmethod
    def _must_get_task_row(session: Session, session_id: str, task_id: str) -> Any | Failure:
        row = (
            session.query(AgentTask)
            .filter(AgentTask.session_id == session_id, AgentTask.task_id == task_id)
            .one_or_none()
        )
        if row is None:
            return _failure("task_not_found", f"task not found: {task_id}", session_id=session_id, task_id=task_id)
        return row


_store_instance: InMemoryAgentSessionStore | SqlAgentSessionStore | None = None

AgentSessionStore = InMemoryAgentSessionStore | SqlAgentSessionStore


def build_agent_session_store() -> Annotated[
    InMemoryAgentSessionStore | SqlAgentSessionStore | Failure,
    "kit:canonical-read canonical_owner=app.services.agent_sessions.store "
    "witness=test:test_w02_agent_authority_metadata"
]:
    global _store_instance
    if _store_instance is not None:
        return _store_instance
    if bool(getattr(settings, "agent_session_db_store_enabled", True)):
        try:
            _store_instance = SqlAgentSessionStore()
            return _store_instance
        except Exception as exc:  # noqa: BLE001
            logger.error("agent session db store unavailable: %s", exc)
            return _failure("backend_unavailable", "agent session database backend unavailable", error=str(exc))
    _store_instance = InMemoryAgentSessionStore()
    return _store_instance


def reset_agent_session_store_for_tests(store: InMemoryAgentSessionStore | SqlAgentSessionStore | None = None) -> None:
    global _store_instance
    _store_instance = store


def _session_row_to_dict(row: Any) -> AgentSessionRecord:
    return {
        "session_id": row.session_id,
        "source": row.source,
        "project_key": row.project_key,
        "entrypoint_type": row.entrypoint_type,
        "goal": row.goal,
        "status": row.status,
        "current_phase": row.current_phase,
        "compat_mode": bool(row.compat_mode),
        "compat_job_id": row.compat_job_id,
        "logical_task_list_key": row.logical_task_list_key,
        "root_task_id": row.root_task_id,
        "metadata": dict(row.metadata_json or {}),
        "final_summary": row.final_summary,
        "final_result": dict(row.final_result or {}),
        "created_at": _as_iso(row.created_at),
        "updated_at": _as_iso(row.updated_at),
    }


def _task_row_to_dict(row: Any) -> AgentTaskRecord:
    return {
        "task_id": row.task_id,
        "session_id": row.session_id,
        "parent_task_id": row.parent_task_id,
        "subject": row.subject,
        "description": row.description,
        "task_type": row.task_type,
        "phase": row.phase,
        "status": row.status,
        "execution_mode": row.execution_mode,
        "owner": row.owner,
        "blocked_by": list(row.blocked_by or []),
        "blocks": list(row.blocks or []),
        "priority": int(row.priority or 0),
        "write_set": list(row.write_set or []),
        "read_set": list(row.read_set or []),
        "task_spec": dict(row.task_spec or {}),
        "metadata": dict(row.metadata_json or {}),
        "result_summary": row.result_summary,
        "result_payload": dict(row.result_payload or {}),
        "tool_use_count": int(row.tool_use_count or 0),
        "token_usage": int(row.token_usage or 0),
        "last_activity": row.last_activity,
        "recent_activities": list(row.recent_activities or []),
        "summary_label": row.summary_label,
        "lease_until": _as_iso(row.lease_until),
        "claimed_at": _as_iso(row.claimed_at),
        "started_at": _as_iso(row.started_at),
        "completed_at": _as_iso(row.completed_at),
        "created_at": _as_iso(row.created_at),
        "updated_at": _as_iso(row.updated_at),
    }


def _message_row_to_dict(row: Any) -> AgentMessageRecord:
    return {
        "session_id": row.session_id,
        "task_id": row.task_id,
        "role": row.role,
        "actor": row.actor,
        "content": row.content,
        "metadata": dict(row.metadata_json or {}),
        "created_at": _as_iso(row.created_at),
    }


def _artifact_row_to_dict(row: Any) -> AgentArtifactRecord:
    return {
        "artifact_id": row.artifact_id,
        "session_id": row.session_id,
        "task_id": row.task_id,
        "artifact_type": row.artifact_type,
        "name": row.name,
        "mime_type": row.mime_type,
        "content_text": row.content_text,
        "content_json": dict(row.content_json or {}),
        "metadata": dict(row.metadata_json or {}),
        "created_at": _as_iso(row.created_at),
        "updated_at": _as_iso(row.updated_at),
    }


def _event_row_to_dict(row: Any) -> AgentEventRecord:
    return {
        "session_id": row.session_id,
        "seq": int(row.seq or 0),
        "event_type": row.event_type,
        "task_id": row.task_id,
        "payload": dict(row.payload or {}),
        "ts": _as_iso(row.ts),
    }


def _approval_row_to_dict(row: Any) -> AgentApprovalRecord:
    return {
        "approval_id": row.approval_id,
        "binding_hash": row.binding_hash,
        "binding_payload": dict(row.binding_payload or {}),
        "requester_session_id": row.requester_session_id,
        "requester_task_id": row.requester_task_id,
        "requester_actor": row.requester_actor,
        "approved_by": row.approved_by,
        "approved_at": _as_iso(row.approved_at),
        "expires_at": _as_iso(row.expires_at),
        "status": row.status,
        "audit_log": list(row.audit_log or []),
        "metadata": dict(row.metadata_json or {}),
        "created_at": _as_iso(row.created_at),
        "updated_at": _as_iso(row.updated_at),
    }
