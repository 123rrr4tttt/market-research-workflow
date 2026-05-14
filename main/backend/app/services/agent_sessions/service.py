from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from app.services.agent_runtime import (
    CoordinatorRuntime,
    SessionMemoryRuntime,
    assert_no_write_conflict,
    build_summary_label,
    build_task_progress_summary,
    collect_expired_task_ids,
    find_unresolved_dependencies,
    requires_approval_for_task,
    resolve_session_status,
)
from .store import build_agent_session_store

SESSION_STATUSES = frozenset({"pending", "active", "blocked", "completed", "failed", "canceled"})
TASK_STATUSES = frozenset({"pending", "claimed", "in_progress", "blocked", "completed", "failed", "canceled", "expired"})
TASK_PHASES = frozenset({"conversation", "research", "synthesis", "implementation", "verification", "maintenance"})
EXECUTION_MODES = frozenset({"coordinator", "worker", "system"})
FINAL_TASK_STATUSES = frozenset({"completed", "failed", "canceled", "expired"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16]}"


def _normalize_status(value: str, *, allowed: frozenset[str], default: str) -> str:
    candidate = str(value or "").strip().lower()
    if not candidate:
        return default
    if candidate not in allowed:
        raise ValueError(f"unsupported status: {candidate}")
    return candidate


def _normalize_phase(value: str | None) -> str:
    candidate = str(value or "").strip().lower() or "research"
    if candidate not in TASK_PHASES:
        raise ValueError(f"unsupported phase: {candidate}")
    return candidate


def _normalize_execution_mode(value: str | None) -> str:
    candidate = str(value or "").strip().lower() or "worker"
    if candidate not in EXECUTION_MODES:
        raise ValueError(f"unsupported execution_mode: {candidate}")
    return candidate


def _normalize_string_list(values: Any) -> list[str]:
    out: list[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in out:
            out.append(item)
    return out


def _short_json(value: Any, *, limit: int = 240) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        encoded = str(value)
    if len(encoded) <= limit:
        return encoded
    return f"{encoded[: limit - 3]}..."


def _hash_binding(binding: dict[str, Any]) -> str:
    body = json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class AgentSessionService:
    def __init__(self, *, store: Any | None = None) -> None:
        self.store = store or build_agent_session_store()
        self.coordinator_runtime = CoordinatorRuntime()
        self.memory_runtime = SessionMemoryRuntime()

    def list_sessions(self, *, limit: int = 50) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in self.store.list_sessions(limit=limit):
            session_id = str(item.get("session_id") or "")
            tasks = self.store.list_tasks(session_id) if session_id else []
            out.append(
                self._decorate_session(
                    item,
                    tasks=tasks,
                    task_count=len(tasks),
                    event_count=len(self.store.list_events(session_id)) if session_id else 0,
                    artifact_count=len(self.store.list_artifacts(session_id)) if session_id else 0,
                    approval_count=len(self.store.list_approvals(session_id=session_id)) if session_id else 0,
                )
            )
        return out

    def get_session(self, session_id: str) -> dict[str, Any]:
        tasks = self.store.list_tasks(session_id)
        return self._decorate_session(self.store.get_session(session_id), tasks=tasks, task_count=len(tasks))

    def list_tasks(self, session_id: str) -> list[dict[str, Any]]:
        tasks = [self._decorate_task(task) for task in self.store.list_tasks(session_id)]
        return tasks

    def list_events(self, session_id: str) -> list[dict[str, Any]]:
        return list(self.store.list_events(session_id))

    def list_artifacts(self, session_id: str) -> list[dict[str, Any]]:
        return list(self.store.list_artifacts(session_id))

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        return list(self.store.list_messages(session_id))

    def list_approvals(self, *, session_id: str | None = None) -> list[dict[str, Any]]:
        return list(self.store.list_approvals(session_id=session_id))

    def find_session_by_compat_job_id(self, compat_job_id: str) -> dict[str, Any] | None:
        item = self.store.find_session_by_compat_job_id(compat_job_id)
        if item is None:
            return None
        tasks = self.store.list_tasks(str(item.get("session_id") or ""))
        return self._decorate_session(item, tasks=tasks, task_count=len(tasks))

    def find_session_by_logical_task_list_key(self, logical_task_list_key: str) -> dict[str, Any] | None:
        item = self.store.find_session_by_logical_task_list_key(logical_task_list_key)
        if item is None:
            return None
        tasks = self.store.list_tasks(str(item.get("session_id") or ""))
        return self._decorate_session(item, tasks=tasks, task_count=len(tasks))

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
        task_blueprints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        session_id = _new_id("as")
        session_metadata = dict(metadata or {})
        if initial_context:
            session_metadata.setdefault("initial_context", dict(initial_context))
        blueprints = list(task_blueprints or self._build_default_task_blueprints(goal))
        normalized_blueprints = self._materialize_blueprints(goal=goal, blueprints=blueprints)
        root_task_id = str(normalized_blueprints[0]["task_id"] or "")
        session = self.store.create_session(
            {
                "session_id": session_id,
                "source": str(source or "user").strip() or "user",
                "project_key": (project_key or "").strip() or None,
                "entrypoint_type": str(entrypoint_type or "chat").strip() or "chat",
                "goal": str(goal or "").strip(),
                "status": "pending",
                "current_phase": normalized_blueprints[0]["phase"],
                "compat_mode": bool(compat_mode),
                "compat_job_id": (compat_job_id or "").strip() or None,
                "logical_task_list_key": (logical_task_list_key or session_id).strip() or session_id,
                "root_task_id": root_task_id,
                "metadata": session_metadata,
                "final_result": {},
            }
        )
        for blueprint in normalized_blueprints:
            self.store.create_task({"session_id": session_id, **blueprint})
        self.store.create_message(
            {
                "session_id": session_id,
                "role": "user",
                "actor": "session_entrypoint",
                "content": str(goal or "").strip(),
                "metadata": {"entrypoint_type": entrypoint_type, "source": source},
            }
        )
        self._bootstrap_memory_artifacts(session)
        self.store.append_event(
            session_id,
            event_type="session.created",
            payload={
                "source": session["source"],
                "entrypoint_type": session["entrypoint_type"],
                "compat_mode": bool(session["compat_mode"]),
                "root_task_id": session["root_task_id"],
            },
        )
        for task in self.store.list_tasks(session_id):
            self.store.append_event(
                session_id,
                event_type="task.created",
                task_id=task["task_id"],
                payload={
                    "phase": task["phase"],
                    "task_type": task["task_type"],
                    "blocked_by": list(task["blocked_by"] or []),
                    "write_set": list(task["write_set"] or []),
                },
            )
        self._refresh_memory_artifacts(session_id, force=True)
        return self.get_session_bundle(session_id)

    def get_session_bundle(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        return {
            "session": session,
            "tasks": self.list_tasks(session_id),
            "messages": self.list_messages(session_id),
            "artifacts": self.list_artifacts(session_id),
            "events": self.list_events(session_id),
            "approvals": self.list_approvals(session_id=session_id),
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
    ) -> dict[str, Any]:
        self.store.get_session(session_id)
        row = self.store.create_message(
            {
                "session_id": session_id,
                "task_id": task_id,
                "role": str(role or "assistant").strip() or "assistant",
                "actor": str(actor or role or "assistant").strip() or "assistant",
                "content": str(content or "").strip(),
                "metadata": dict(metadata or {}),
            }
        )
        self.store.append_event(
            session_id,
            event_type="message.created",
            task_id=task_id,
            payload={"role": row.get("role"), "actor": row.get("actor")},
        )
        self._maybe_refresh_memory(session_id)
        return row

    def append_task_blueprints(
        self,
        session_id: str,
        *,
        goal: str | None = None,
        task_blueprints: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        session = self.store.get_session(session_id)
        materialized = self._materialize_blueprints(
            goal=str(goal or session.get("goal") or "").strip(),
            blueprints=list(task_blueprints or []),
        )
        created: list[dict[str, Any]] = []
        for blueprint in materialized:
            task = self.store.create_task({"session_id": session_id, **blueprint})
            self.store.append_event(
                session_id,
                event_type="task.created",
                task_id=task["task_id"],
                payload={
                    "phase": task["phase"],
                    "task_type": task["task_type"],
                    "blocked_by": list(task["blocked_by"] or []),
                    "write_set": list(task["write_set"] or []),
                },
            )
            created.append(self._decorate_task(task))
        self._sync_session_state(session_id)
        self._refresh_memory_artifacts(session_id, force=True)
        return created

    def claim_task(self, session_id: str, task_id: str, *, owner: str, lease_seconds: int = 300) -> dict[str, Any]:
        self.reclaim_expired_tasks(session_id)
        task = self.store.get_task(session_id, task_id)
        tasks = self.store.list_tasks(session_id)
        if task["status"] not in {"pending", "blocked"}:
            raise ValueError(f"task not claimable from status={task['status']}")
        unresolved = find_unresolved_dependencies(task, tasks)
        if unresolved:
            raise ValueError("task dependencies are not completed")
        assert_no_write_conflict(tasks, task_id, list(task.get("write_set") or []))
        now = _utcnow()
        updated = self.store.update_task(
            session_id,
            task_id,
            {
                "status": "claimed",
                "owner": str(owner or "").strip() or "coordinator",
                "lease_until": now + timedelta(seconds=max(30, int(lease_seconds or 300))),
                "claimed_at": now,
                "started_at": task.get("started_at") or now,
                "last_activity": "task claimed",
            },
        )
        updated = self.store.update_task(session_id, task_id, {"summary_label": build_summary_label(updated)})
        self._sync_session_state(session_id)
        self.store.append_event(
            session_id,
            event_type="task.claimed",
            task_id=task_id,
            payload={"owner": updated.get("owner"), "lease_until": updated.get("lease_until")},
        )
        return self._decorate_task(updated)

    def heartbeat_task(
        self,
        session_id: str,
        task_id: str,
        *,
        lease_seconds: int = 300,
        activity: str | None = None,
        tool_use_count: int | None = None,
        token_usage: int | None = None,
    ) -> dict[str, Any]:
        task = self.store.get_task(session_id, task_id)
        now = _utcnow()
        recent_activities = list(task.get("recent_activities") or [])
        if activity:
            recent_activities.append(str(activity))
            recent_activities = recent_activities[-8:]
        updated = self.store.update_task(
            session_id,
            task_id,
            {
                "status": "in_progress" if task["status"] in {"claimed", "in_progress"} else task["status"],
                "lease_until": now + timedelta(seconds=max(30, int(lease_seconds or 300))),
                "started_at": task.get("started_at") or now,
                "last_activity": activity or task.get("last_activity"),
                "recent_activities": recent_activities,
                "tool_use_count": int(tool_use_count) if tool_use_count is not None else int(task.get("tool_use_count") or 0),
                "token_usage": int(token_usage) if token_usage is not None else int(task.get("token_usage") or 0),
            },
        )
        updated = self.store.update_task(session_id, task_id, {"summary_label": build_summary_label(updated)})
        self.store.append_event(
            session_id,
            event_type="task.heartbeat",
            task_id=task_id,
            payload={
                "lease_until": updated.get("lease_until"),
                "activity": updated.get("last_activity"),
                "tool_use_count": updated.get("tool_use_count"),
                "token_usage": updated.get("token_usage"),
            },
        )
        self._maybe_refresh_memory(session_id)
        return self._decorate_task(updated)

    def release_task(
        self,
        session_id: str,
        task_id: str,
        *,
        status: str,
        result_summary: str | None = None,
        result_payload: dict[str, Any] | None = None,
        tool_use_count: int | None = None,
        token_usage: int | None = None,
        activity: str | None = None,
    ) -> dict[str, Any]:
        normalized_status = _normalize_status(status, allowed=TASK_STATUSES, default="completed")
        task = self.store.get_task(session_id, task_id)
        recent_activities = list(task.get("recent_activities") or [])
        if activity:
            recent_activities.append(str(activity))
            recent_activities = recent_activities[-8:]
        changes: dict[str, Any] = {
            "status": normalized_status,
            "result_summary": result_summary or task.get("result_summary"),
            "result_payload": dict(result_payload or task.get("result_payload") or {}),
            "tool_use_count": int(tool_use_count) if tool_use_count is not None else int(task.get("tool_use_count") or 0),
            "token_usage": int(token_usage) if token_usage is not None else int(task.get("token_usage") or 0),
            "last_activity": activity or task.get("last_activity"),
            "recent_activities": recent_activities,
            "lease_until": None,
        }
        if normalized_status in FINAL_TASK_STATUSES:
            changes["completed_at"] = _utcnow()
        updated = self.store.update_task(session_id, task_id, changes)
        updated = self.store.update_task(session_id, task_id, {"summary_label": build_summary_label(updated)})
        if normalized_status == "completed":
            self._unblock_dependents(session_id, task_id)
        self._sync_session_state(session_id)
        self.store.append_event(
            session_id,
            event_type=f"task.{normalized_status}",
            task_id=task_id,
            payload={
                "result_summary": updated.get("result_summary"),
                "summary_label": updated.get("summary_label"),
                "progress": build_task_progress_summary(updated),
            },
        )
        self._maybe_refresh_memory(session_id)
        return self._decorate_task(updated)

    def retry_task(self, session_id: str, task_id: str) -> dict[str, Any]:
        task = self.store.get_task(session_id, task_id)
        updated = self.store.update_task(
            session_id,
            task_id,
            {
                "status": "pending",
                "result_summary": None,
                "result_payload": {},
                "lease_until": None,
                "completed_at": None,
                "last_activity": "task retried",
                "recent_activities": ["task retried"],
                "summary_label": f"{task['subject']} [pending]",
            },
        )
        for item in self.store.list_tasks(session_id):
            if task_id in list(item.get("blocked_by") or []):
                self.store.update_task(
                    session_id,
                    item["task_id"],
                    {
                        "status": "blocked",
                        "completed_at": None,
                        "summary_label": f"{item['subject']} [blocked]",
                    },
                )
        self._sync_session_state(session_id)
        self.store.append_event(session_id, event_type="task.retried", task_id=task_id, payload={"task_id": task_id})
        return self._decorate_task(updated)

    def reclaim_expired_tasks(self, session_id: str) -> list[dict[str, Any]]:
        tasks = self.store.list_tasks(session_id)
        expired_task_ids = collect_expired_task_ids(tasks)
        reclaimed: list[dict[str, Any]] = []
        for task_id in expired_task_ids:
            updated = self.store.update_task(
                session_id,
                task_id,
                {
                    "status": "expired",
                    "lease_until": None,
                    "last_activity": "lease expired",
                    "recent_activities": ["lease expired"],
                    "completed_at": _utcnow(),
                },
            )
            updated = self.store.update_task(session_id, task_id, {"summary_label": build_summary_label(updated)})
            self.store.append_event(
                session_id,
                event_type="task.expired",
                task_id=task_id,
                payload={"reason": "lease_timeout"},
            )
            reclaimed.append(self._decorate_task(updated))
        if reclaimed:
            self._sync_session_state(session_id)
            self._maybe_refresh_memory(session_id)
        return reclaimed

    def cancel_session(self, session_id: str) -> dict[str, Any]:
        for task in self.store.list_tasks(session_id):
            if str(task.get("status") or "") not in FINAL_TASK_STATUSES:
                self.store.update_task(
                    session_id,
                    task["task_id"],
                    {
                        "status": "canceled",
                        "lease_until": None,
                        "completed_at": _utcnow(),
                        "summary_label": f"{task['subject']} [canceled]",
                    },
                )
        session = self.store.update_session(session_id, {"status": "canceled"})
        self.store.append_event(session_id, event_type="session.canceled", payload={"session_id": session_id})
        self._refresh_memory_artifacts(session_id, force=True)
        return self._decorate_session(session)

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
    ) -> dict[str, Any]:
        row = self.store.create_or_update_approval(
            {
                "approval_id": str(approval_id or "").strip(),
                "binding_hash": _hash_binding(binding_payload),
                "binding_payload": dict(binding_payload or {}),
                "requester_session_id": requester_session_id,
                "requester_task_id": requester_task_id,
                "requester_actor": str(requester_actor or "unknown").strip() or "unknown",
                "approved_by": approved_by,
                "approved_at": approved_at,
                "expires_at": expires_at,
                "status": _normalize_status(status, allowed=SESSION_STATUSES | {"approved", "pending"}, default="pending"),
                "metadata": dict(metadata or {}),
                "audit_log": list(audit_log or []),
            }
        )
        if requester_session_id:
            self._ensure_approval_wait_task(
                requester_session_id=requester_session_id,
                requester_task_id=requester_task_id,
                approval=row,
            )
            self.store.append_event(
                requester_session_id,
                event_type=f"approval.{row['status']}",
                task_id=requester_task_id,
                payload={"approval_id": row["approval_id"], "expires_at": row.get("expires_at")},
            )
        return row

    def request_approval(
        self,
        *,
        session_id: str,
        task_id: str,
        binding_payload: dict[str, Any],
        requester_actor: str,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task = self.store.get_task(session_id, task_id)
        approval_id = str((metadata or {}).get("approval_id") or _new_id("approval")).strip()
        if not requires_approval_for_task(task):
            task_metadata = dict(task.get("metadata") or {})
            if dict(metadata or {}).get("force_approval"):
                task_metadata["concurrency_class"] = "write_external"
                self.store.update_task(session_id, task_id, {"metadata": task_metadata})
        row = self.create_or_update_approval(
            approval_id=approval_id,
            binding_payload=dict(binding_payload or {}),
            requester_session_id=session_id,
            requester_task_id=task_id,
            requester_actor=requester_actor,
            expires_at=expires_at,
            status="pending",
            metadata=dict(metadata or {}),
            audit_log=[{"action": "requested", "actor": requester_actor, "at": _utcnow().isoformat()}],
        )
        self.store.append_event(
            session_id,
            event_type="approval.requested",
            task_id=task_id,
            payload={"approval_id": row["approval_id"], "binding_hash": row["binding_hash"]},
        )
        self._sync_session_state(session_id)
        return row

    def resolve_approval(self, approval_id: str, *, approved_by: str, approved: bool = True) -> dict[str, Any]:
        current = self.store.get_approval(approval_id)
        audit_log = list(current.get("audit_log") or [])
        audit_log.append(
            {
                "at": _utcnow().isoformat(),
                "action": "approved" if approved else "rejected",
                "actor": str(approved_by or "unknown").strip() or "unknown",
            }
        )
        row = self.store.create_or_update_approval(
            {
                **current,
                "status": "approved" if approved else "failed",
                "approved_by": str(approved_by or "unknown").strip() or "unknown",
                "approved_at": _utcnow(),
                "audit_log": audit_log,
            }
        )
        requester_session_id = str(row.get("requester_session_id") or "").strip() or None
        if requester_session_id:
            requester_task_id = str(row.get("requester_task_id") or "").strip() or None
            self._apply_approval_resolution(
                session_id=requester_session_id,
                requester_task_id=requester_task_id,
                approval=row,
                approved=approved,
            )
            self.store.append_event(
                requester_session_id,
                event_type=f"approval.{row['status']}",
                task_id=row.get("requester_task_id"),
                payload={"approval_id": approval_id, "approved_by": row.get("approved_by")},
            )
        return row

    def run_coordinator_pass(self, session_id: str) -> dict[str, Any]:
        return self.coordinator_runtime.run_pass(self, session_id)

    def project_agent_batch_compat(
        self,
        *,
        command: str,
        project_key: str | None,
        request_payload: dict[str, Any],
        loop_result: dict[str, Any],
    ) -> dict[str, Any]:
        submit = dict(loop_result.get("submit") or {})
        compat_job_id = str(submit.get("job_id") or "").strip() or None
        plan = dict(loop_result.get("plan") or {})
        task_blueprints = self._build_agent_batch_compat_blueprints(command=command, loop_result=loop_result)
        metadata = {
            "compat_projection_version": "claude-agent.v1",
            "agent_batch": {
                "job_id": compat_job_id,
                "dry_run": bool(loop_result.get("dry_run") or request_payload.get("dry_run")),
                "enable_bounded_retry": bool(request_payload.get("enable_bounded_retry")),
                "enable_limited_branching": bool(request_payload.get("enable_limited_branching")),
            },
            "loop_result": {
                "parsed": dict(loop_result.get("parsed") or {}),
                "executor": dict(loop_result.get("executor") or {}),
                "plan": {
                    "intent": plan.get("intent"),
                    "strategy": plan.get("strategy"),
                    "loop": dict(plan.get("loop") or {}),
                    "search_brief": dict(plan.get("search_brief") or {}),
                    "search_critic": dict(plan.get("search_critic") or {}),
                    "search_retry": dict(plan.get("search_retry") or {}),
                    "branching": dict(plan.get("branching") or {}),
                },
                "completion": dict(loop_result.get("completion") or {}),
            },
        }
        bundle = self.create_session(
            source="agent_batch",
            entrypoint_type="nl_command",
            goal=str(command or "").strip(),
            project_key=project_key,
            initial_context=request_payload,
            compat_mode=True,
            compat_job_id=compat_job_id,
            metadata=metadata,
            task_blueprints=task_blueprints,
        )
        session_id = bundle["session"]["session_id"]
        self.store.upsert_artifact(
            {
                "session_id": session_id,
                "artifact_type": "compat.loop_result",
                "name": "compat.loop_result.json",
                "mime_type": "application/json",
                "content_json": loop_result,
                "metadata": {"source": "agent_batch.nl_command"},
            }
        )
        search_brief = dict(plan.get("search_brief") or {})
        if search_brief:
            self.store.upsert_artifact(
                {
                    "session_id": session_id,
                    "artifact_type": "research_summary_json",
                    "name": "search_brief.json",
                    "mime_type": "application/json",
                    "content_json": search_brief,
                    "metadata": {"source": "agent_batch.plan.search_brief"},
                }
            )
        self.store.append_event(
            session_id,
            event_type="compat.projected",
            payload={"compat_job_id": compat_job_id, "command": command, "task_count": len(task_blueprints)},
        )
        self._refresh_memory_artifacts(session_id, force=True)
        return self.get_session_bundle(session_id)

    def project_agent_batch_job_submission(
        self,
        *,
        job_id: str,
        project_key: str | None,
        request_payload: dict[str, Any],
        accepted_items: list[dict[str, Any]],
        rejected_items: list[dict[str, Any]],
        rule_set_id: str | None = None,
    ) -> dict[str, Any]:
        existing = self.find_session_by_compat_job_id(job_id)
        if existing is not None:
            return self.get_session_bundle(str(existing["session_id"]))

        task_blueprints = self._build_agent_batch_job_blueprints(
            job_id=job_id,
            accepted_items=accepted_items,
            rejected_items=rejected_items,
        )
        metadata = {
            "compat_projection_version": "agent_batch.jobs.v1",
            "agent_batch": {
                "job_id": job_id,
                "rule_set_id": rule_set_id,
                "accepted_count": len(accepted_items),
                "rejected_count": len(rejected_items),
            },
        }
        bundle = self.create_session(
            source="agent_batch",
            entrypoint_type="agent_batch.jobs",
            goal=f"Execute agent batch job {job_id}",
            project_key=project_key,
            initial_context=request_payload,
            compat_mode=True,
            compat_job_id=job_id,
            metadata=metadata,
            task_blueprints=task_blueprints,
        )
        session_id = str(bundle["session"]["session_id"])
        self.store.upsert_artifact(
            {
                "session_id": session_id,
                "artifact_type": "compat.job.submit",
                "name": "compat.job.submit.json",
                "mime_type": "application/json",
                "content_json": {
                    "job_id": job_id,
                    "request_payload": request_payload,
                    "accepted_items": accepted_items,
                    "rejected_items": rejected_items,
                    "rule_set_id": rule_set_id,
                },
                "metadata": {"source": "agent_batch.jobs"},
            }
        )
        self.store.append_event(
            session_id,
            event_type="compat.job_projected",
            payload={
                "compat_job_id": job_id,
                "accepted_count": len(accepted_items),
                "rejected_count": len(rejected_items),
            },
        )
        self._sync_session_state(session_id)
        self._refresh_memory_artifacts(session_id, force=True)
        return self.get_session_bundle(session_id)

    def project_agent_batch_job_state(
        self,
        *,
        compat_job_id: str,
        projected_items: list[dict[str, Any]],
        phase: str,
        progress: dict[str, Any],
    ) -> dict[str, Any] | None:
        existing = self.find_session_by_compat_job_id(compat_job_id)
        if existing is None:
            return None

        session_id = str(existing["session_id"])
        tasks = self.store.list_tasks(session_id)
        item_tasks = {
            str(dict(task.get("metadata") or {}).get("item_id") or ""): task
            for task in tasks
            if str(dict(task.get("metadata") or {}).get("compat_projection") or "") == "agent_batch.job_item"
        }
        verification_task = next(
            (
                task
                for task in tasks
                if str(dict(task.get("metadata") or {}).get("compat_projection") or "") == "agent_batch.job_verification"
            ),
            None,
        )
        for projected in projected_items:
            item_id = str(projected.get("item_id") or "").strip()
            if not item_id:
                continue
            task = item_tasks.get(item_id)
            if task is None:
                task = self.store.create_task(
                    self._build_agent_batch_job_item_blueprint(compat_job_id=compat_job_id, item=projected)
                    | {"session_id": session_id}
                )
                self.store.append_event(
                    session_id,
                    event_type="task.created",
                    task_id=task["task_id"],
                    payload={
                        "phase": task["phase"],
                        "task_type": task["task_type"],
                        "blocked_by": list(task.get("blocked_by") or []),
                        "write_set": list(task.get("write_set") or []),
                    },
                )
                item_tasks[item_id] = task
            snapshot = dict(projected.get("snapshot") or {})
            mapped_status = self._map_agent_batch_task_status(str(snapshot.get("status") or "pending"))
            changes = {
                "status": mapped_status,
                "result_summary": _short_json(
                    {
                        "task_status": snapshot.get("status"),
                        "run_id": projected.get("run_id"),
                        "workflow_run_id": projected.get("workflow_run_id"),
                    },
                    limit=180,
                ),
                "result_payload": {
                    "snapshot": snapshot,
                    "run_id": projected.get("run_id"),
                    "workflow_run_id": projected.get("workflow_run_id"),
                    "trace_id": projected.get("trace_id"),
                    "lane": projected.get("lane"),
                },
                "last_activity": f"compat job item {item_id} status={snapshot.get('status')}",
                "recent_activities": [f"compat job item {item_id} status={snapshot.get('status')}"],
                "lease_until": None,
            }
            if mapped_status in FINAL_TASK_STATUSES:
                changes["completed_at"] = _utcnow()
            updated = self.store.update_task(session_id, task["task_id"], changes)
            self.store.update_task(session_id, task["task_id"], {"summary_label": build_summary_label(updated)})
            self.store.append_event(
                session_id,
                event_type=f"task.{mapped_status}",
                task_id=task["task_id"],
                payload={
                    "compat_job_id": compat_job_id,
                    "item_id": item_id,
                    "run_id": projected.get("run_id"),
                    "workflow_run_id": projected.get("workflow_run_id"),
                },
            )

        if verification_task is not None:
            verification_status = self._map_agent_batch_job_phase_to_task_status(phase, progress=progress)
            updated = self.store.update_task(
                session_id,
                verification_task["task_id"],
                {
                    "status": verification_status,
                    "result_summary": _short_json({"phase": phase, "progress": progress}, limit=180),
                    "result_payload": {"phase": phase, "progress": progress},
                    "last_activity": f"compat job {compat_job_id} phase={phase}",
                    "recent_activities": [f"compat job {compat_job_id} phase={phase}"],
                    "lease_until": None,
                    "completed_at": _utcnow() if verification_status in FINAL_TASK_STATUSES else None,
                },
            )
            self.store.update_task(session_id, verification_task["task_id"], {"summary_label": build_summary_label(updated)})
        session = self.store.get_session(session_id)
        metadata = dict(session.get("metadata") or {})
        agent_batch_meta = dict(metadata.get("agent_batch") or {})
        last_projection = {"status": phase, "progress": dict(progress or {})}
        if dict(agent_batch_meta.get("last_projection") or {}) != last_projection:
            agent_batch_meta["last_projection"] = last_projection
            metadata["agent_batch"] = agent_batch_meta
            self.store.update_session(session_id, {"metadata": metadata})
            self.store.append_event(
                session_id,
                event_type="compat.job_state_projected",
                payload={"compat_job_id": compat_job_id, "phase": phase, "progress": progress},
            )
        self._sync_session_state(session_id)
        self._refresh_memory_artifacts(session_id, force=True)
        return self.get_session_bundle(session_id)

    def create_workflow_graph_session(
        self,
        *,
        graph_id: str,
        run_id: str | None,
        goal: str,
        project_key: str | None = None,
        initial_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.create_session(
            source="workflow_graph",
            entrypoint_type="workflow_graph",
            goal=goal,
            project_key=project_key,
            initial_context=initial_context,
            logical_task_list_key=(run_id or graph_id),
            metadata={"workflow_graph": {"graph_id": graph_id, "run_id": run_id}},
        )

    def project_workflow_graph_run(
        self,
        *,
        graph_id: str,
        run_id: str,
        workflow: dict[str, Any],
        inputs: dict[str, Any],
        snapshot: dict[str, Any],
        project_key: str | None = None,
    ) -> dict[str, Any]:
        existing = self.find_session_by_logical_task_list_key(run_id)
        if existing is None:
            task_blueprints = self._build_workflow_graph_task_blueprints(graph_id=graph_id, run_id=run_id, workflow=workflow)
            bundle = self.create_session(
                source="workflow_graph",
                entrypoint_type="workflow_graph.run",
                goal=f"Execute workflow graph {graph_id}",
                project_key=project_key,
                initial_context={"inputs": inputs},
                logical_task_list_key=run_id,
                metadata={"workflow_graph": {"graph_id": graph_id, "run_id": run_id, "inputs": inputs}},
                task_blueprints=task_blueprints,
            )
            session = dict(bundle["session"])
        else:
            session = existing
        session_id = str(session["session_id"])
        results = dict(snapshot.get("results") or {})
        run = dict(snapshot.get("run") or {})
        node_statuses = dict(run.get("node_statuses") or {})
        tasks = self.store.list_tasks(session_id)
        verification_task_id: str | None = None
        for task in tasks:
            metadata = dict(task.get("metadata") or {})
            workflow_node = metadata.get("workflow_graph_node")
            if metadata.get("workflow_graph_verification"):
                verification_task_id = task["task_id"]
                continue
            if not isinstance(workflow_node, dict):
                continue
            node_id = str(workflow_node.get("node_id") or "").strip()
            if not node_id:
                continue
            node_status = str(node_statuses.get(node_id) or task.get("status") or "")
            mapped_status = self._map_workflow_graph_status(node_status)
            result_payload = results.get(node_id)
            self.store.update_task(
                session_id,
                task["task_id"],
                {
                    "status": mapped_status,
                    "result_summary": _short_json(result_payload if result_payload is not None else {"status": node_status}, limit=180),
                    "result_payload": result_payload if isinstance(result_payload, dict) else {"result": result_payload} if result_payload is not None else {"status": node_status},
                    "completed_at": _utcnow() if mapped_status in FINAL_TASK_STATUSES else None,
                    "summary_label": f"{task['subject']} [{mapped_status}]",
                },
            )
        if verification_task_id:
            run_status = str(run.get("status") or "queued")
            verification_status = "completed" if run_status == "succeeded" else "failed" if run_status == "failed" else "pending"
            self.store.update_task(
                session_id,
                verification_task_id,
                {
                    "status": verification_status,
                    "result_summary": f"workflow run {run_id} status={run_status}",
                    "result_payload": {"run": run, "results": results},
                    "completed_at": _utcnow() if verification_status in FINAL_TASK_STATUSES else None,
                    "summary_label": f"Verification [{verification_status}]",
                },
            )
        self._sync_session_state(session_id)
        self.store.upsert_artifact(
            {
                "session_id": session_id,
                "artifact_type": "workflow_graph.snapshot",
                "name": "workflow_graph.snapshot.json",
                "mime_type": "application/json",
                "content_json": {"workflow": workflow, "inputs": inputs, "snapshot": snapshot},
                "metadata": {"source": "workflow_graph.runtime"},
            }
        )
        self.store.append_event(
            session_id,
            event_type="workflow_graph.run_projected",
            payload={"graph_id": graph_id, "run_id": run_id, "status": run.get("status")},
        )
        self._refresh_memory_artifacts(session_id, force=True)
        return self.get_session_bundle(session_id)

    def _ensure_approval_wait_task(
        self,
        *,
        requester_session_id: str,
        requester_task_id: str | None,
        approval: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not requester_task_id:
            return None
        approval_id = str(approval.get("approval_id") or "").strip()
        if not approval_id:
            return None
        existing = next(
            (
                task
                for task in self.store.list_tasks(requester_session_id)
                if str(task.get("task_type") or "") == "approval_wait"
                and str(dict(task.get("metadata") or {}).get("approval_id") or "") == approval_id
            ),
            None,
        )
        if existing is not None:
            return existing
        try:
            gated_task = self.store.get_task(requester_session_id, requester_task_id)
        except KeyError:
            return None
        if str(gated_task.get("status") or "") not in FINAL_TASK_STATUSES:
            self.store.update_task(
                requester_session_id,
                requester_task_id,
                {
                    "status": "blocked",
                    "last_activity": f"waiting for approval {approval_id}",
                    "recent_activities": [f"waiting for approval {approval_id}"],
                    "summary_label": f"{gated_task['subject']} [blocked]",
                },
            )
        task = self.store.create_task(
            {
                "session_id": requester_session_id,
                "task_id": _new_id("task"),
                "parent_task_id": requester_task_id,
                "subject": f"Approval wait: {approval_id}",
                "description": "Formal approval_wait blocker task projected into the task bus.",
                "task_type": "approval_wait",
                "phase": str(gated_task.get("phase") or "maintenance"),
                "status": "in_progress" if str(approval.get("status") or "") == "pending" else "completed",
                "execution_mode": "system",
                "blocked_by": [],
                "blocks": [requester_task_id],
                "priority": max(0, int(gated_task.get("priority") or 5) - 1),
                "write_set": [],
                "read_set": list(gated_task.get("write_set") or []),
                "task_spec": {
                    "task_type": "approval_wait",
                    "goal": f"Wait for approval {approval_id}",
                    "context": {"approval_id": approval_id, "requester_task_id": requester_task_id},
                    "target_scope": requester_task_id,
                    "write_set": [],
                    "completion_criteria": ["Approval is resolved explicitly."],
                    "verification_steps": ["Confirm approval outcome is reflected in the gated task state."],
                    "artifact_targets": ["memory.md", "scratchpad.md"],
                },
                "metadata": {
                    "approval_id": approval_id,
                    "gated_task_id": requester_task_id,
                },
                "last_activity": f"approval {approval_id} requested",
                "recent_activities": [f"approval {approval_id} requested"],
                "summary_label": f"Approval wait: {approval_id}",
            }
        )
        self.store.append_event(
            requester_session_id,
            event_type="approval.waiting",
            task_id=task["task_id"],
            payload={"approval_id": approval_id, "gated_task_id": requester_task_id},
        )
        return task

    def _apply_approval_resolution(
        self,
        *,
        session_id: str,
        requester_task_id: str | None,
        approval: dict[str, Any],
        approved: bool,
    ) -> None:
        approval_id = str(approval.get("approval_id") or "").strip()
        wait_tasks = [
            task
            for task in self.store.list_tasks(session_id)
            if str(task.get("task_type") or "") == "approval_wait"
            and str(dict(task.get("metadata") or {}).get("approval_id") or "") == approval_id
        ]
        for wait_task in wait_tasks:
            status = "completed" if approved else "failed"
            updated = self.store.update_task(
                session_id,
                wait_task["task_id"],
                {
                    "status": status,
                    "completed_at": _utcnow(),
                    "lease_until": None,
                    "last_activity": f"approval {approval_id} {'approved' if approved else 'rejected'}",
                    "recent_activities": [f"approval {approval_id} {'approved' if approved else 'rejected'}"],
                },
            )
            self.store.update_task(session_id, wait_task["task_id"], {"summary_label": build_summary_label(updated)})
        if requester_task_id:
            gated_task = self.store.get_task(session_id, requester_task_id)
            if approved:
                unresolved = find_unresolved_dependencies(gated_task, self.store.list_tasks(session_id))
                new_status = "blocked" if unresolved else "pending"
                updated = self.store.update_task(
                    session_id,
                    requester_task_id,
                    {
                        "status": new_status,
                        "last_activity": f"approval {approval_id} approved",
                        "recent_activities": [f"approval {approval_id} approved"],
                    },
                )
            else:
                updated = self.store.update_task(
                    session_id,
                    requester_task_id,
                    {
                        "status": "failed",
                        "completed_at": _utcnow(),
                        "last_activity": f"approval {approval_id} rejected",
                        "recent_activities": [f"approval {approval_id} rejected"],
                    },
                )
            self.store.update_task(session_id, requester_task_id, {"summary_label": build_summary_label(updated)})
        self._sync_session_state(session_id)

    def _build_default_task_blueprints(self, goal: str) -> list[dict[str, Any]]:
        return [
            {
                "subject": "Research",
                "description": "Collect the facts, context, and candidate approaches for the user goal.",
                "task_type": "research",
                "phase": "research",
                "execution_mode": "worker",
                "priority": 1,
                "write_set": [],
                "read_set": [],
                "task_spec": {
                    "task_type": "research",
                    "goal": goal,
                    "context": {},
                    "target_scope": "session",
                    "write_set": [],
                    "completion_criteria": ["Collect enough facts to decide the implementation path."],
                    "verification_steps": ["Cross-check inputs against source-of-truth context."],
                    "artifact_targets": ["scratchpad.md"],
                },
            },
            {
                "subject": "Synthesis",
                "description": "Coordinator consolidates research and produces the execution spec.",
                "task_type": "synthesis",
                "phase": "synthesis",
                "execution_mode": "coordinator",
                "priority": 2,
                "write_set": [],
                "read_set": [],
                "blocked_by_refs": ["prev"],
                "task_spec": {
                    "task_type": "synthesis",
                    "goal": goal,
                    "context": {},
                    "target_scope": "session",
                    "write_set": [],
                    "completion_criteria": ["Produce an explicit implementation spec."],
                    "verification_steps": ["Ensure synthesis is grounded in completed research."],
                    "artifact_targets": ["scratchpad.md", "memory.md"],
                },
            },
            {
                "subject": "Implementation",
                "description": "Execute the approved plan against the target scope.",
                "task_type": "implementation",
                "phase": "implementation",
                "execution_mode": "worker",
                "priority": 3,
                "write_set": ["session:default"],
                "read_set": [],
                "blocked_by_refs": ["prev"],
                "task_spec": {
                    "task_type": "implementation",
                    "goal": goal,
                    "context": {},
                    "target_scope": "session",
                    "write_set": ["session:default"],
                    "completion_criteria": ["Apply the agreed changes and produce concrete outputs."],
                    "verification_steps": ["List the exact checks needed after the change."],
                    "artifact_targets": ["final_report.md"],
                },
            },
            {
                "subject": "Verification",
                "description": "Verify the implemented result independently.",
                "task_type": "verification",
                "phase": "verification",
                "execution_mode": "worker",
                "priority": 4,
                "write_set": [],
                "read_set": ["session:default"],
                "blocked_by_refs": ["prev"],
                "task_spec": {
                    "task_type": "verification",
                    "goal": goal,
                    "context": {},
                    "target_scope": "session",
                    "write_set": [],
                    "completion_criteria": ["Produce verification evidence and call out residual risks."],
                    "verification_steps": ["Run the minimal checks and summarize the result."],
                    "artifact_targets": ["final_report.md"],
                },
            },
        ]

    def _materialize_blueprints(self, *, goal: str, blueprints: list[dict[str, Any]]) -> list[dict[str, Any]]:
        materialized: list[dict[str, Any]] = []
        prev_task_id: str | None = None
        for blueprint in blueprints:
            task_id = str(blueprint.get("task_id") or _new_id("task")).strip()
            blocked_by = _normalize_string_list(blueprint.get("blocked_by"))
            blocked_refs = _normalize_string_list(blueprint.get("blocked_by_refs"))
            if "prev" in blocked_refs and prev_task_id:
                blocked_by.append(prev_task_id)
            phase = _normalize_phase(blueprint.get("phase"))
            status = _normalize_status(str(blueprint.get("status") or ("blocked" if blocked_by else "pending")), allowed=TASK_STATUSES, default="pending")
            if blocked_by and status == "pending":
                status = "blocked"
            task = {
                "task_id": task_id,
                "parent_task_id": blueprint.get("parent_task_id"),
                "subject": str(blueprint.get("subject") or blueprint.get("task_type") or phase).strip(),
                "description": blueprint.get("description"),
                "task_type": str(blueprint.get("task_type") or phase).strip(),
                "phase": phase,
                "status": status,
                "execution_mode": _normalize_execution_mode(blueprint.get("execution_mode")),
                "owner": blueprint.get("owner"),
                "blocked_by": blocked_by,
                "blocks": [],
                "priority": int(blueprint.get("priority") or 5),
                "write_set": _normalize_string_list(blueprint.get("write_set")),
                "read_set": _normalize_string_list(blueprint.get("read_set")),
                "task_spec": dict(blueprint.get("task_spec") or {
                    "task_type": str(blueprint.get("task_type") or phase),
                    "goal": goal,
                    "context": {},
                    "target_scope": "session",
                    "write_set": _normalize_string_list(blueprint.get("write_set")),
                    "completion_criteria": list(blueprint.get("completion_criteria") or []),
                    "verification_steps": list(blueprint.get("verification_steps") or []),
                    "artifact_targets": list(blueprint.get("artifact_targets") or []),
                }),
                "metadata": dict(blueprint.get("metadata") or {}),
                "result_summary": blueprint.get("result_summary"),
                "result_payload": dict(blueprint.get("result_payload") or {}),
                "tool_use_count": int(blueprint.get("tool_use_count") or 0),
                "token_usage": int(blueprint.get("token_usage") or 0),
                "last_activity": blueprint.get("last_activity"),
                "recent_activities": list(blueprint.get("recent_activities") or []),
                "summary_label": blueprint.get("summary_label"),
            }
            task["summary_label"] = task["summary_label"] or build_summary_label(task)
            materialized.append(task)
            prev_task_id = task_id
        task_ids = {item["task_id"] for item in materialized}
        for item in materialized:
            item["blocked_by"] = [dep for dep in list(item.get("blocked_by") or []) if dep in task_ids]
        blockers = {item["task_id"]: [] for item in materialized}
        for item in materialized:
            for dep in list(item.get("blocked_by") or []):
                blockers.setdefault(dep, []).append(item["task_id"])
        for item in materialized:
            item["blocks"] = blockers.get(item["task_id"], [])
        return materialized

    def _build_agent_batch_compat_blueprints(self, *, command: str, loop_result: dict[str, Any]) -> list[dict[str, Any]]:
        plan = dict(loop_result.get("plan") or {})
        parsed = dict(loop_result.get("parsed") or {})
        submit = dict(loop_result.get("submit") or {})
        completion = dict(loop_result.get("completion") or {})
        plan_tasks = list(plan.get("tasks") or [])
        blueprints: list[dict[str, Any]] = []
        research_task_ids: list[str] = []
        for idx, item in enumerate(plan_tasks, start=1):
            task_id = _new_id("task")
            research_task_ids.append(task_id)
            query_terms = _normalize_string_list(item.get("query_terms"))
            channel = str(item.get("channel") or "research").strip() or "research"
            item_key = str(item.get("item_key") or "").strip()
            target_scope = item_key or ",".join(query_terms) or channel
            blueprints.append(
                {
                    "task_id": task_id,
                    "subject": f"Research {idx}: {channel}",
                    "description": f"Projected from agent_batch plan task {idx}.",
                    "task_type": "research",
                    "phase": "research",
                    "status": "completed",
                    "execution_mode": "worker",
                    "priority": idx,
                    "write_set": [],
                    "read_set": [f"agent_batch.plan:{channel}"],
                    "result_summary": f"Planned {channel} target {target_scope}".strip(),
                    "metadata": {"compat_projection": "agent_batch.plan_task", "channel": channel, "source_task": item},
                    "task_spec": {
                        "task_type": "research",
                        "goal": command,
                        "context": {"parsed": parsed},
                        "target_scope": target_scope,
                        "write_set": [],
                        "completion_criteria": ["Represent the planned research task in the session ledger."],
                        "verification_steps": ["Ensure projected task reflects the original plan task."],
                        "artifact_targets": ["search_brief.json", "scratchpad.md"],
                    },
                }
            )
        blueprints.append(
            {
                "task_id": _new_id("task"),
                "subject": "Synthesis",
                "description": "Projected from search_brief/search_critic/search_retry artifacts.",
                "task_type": "synthesis",
                "phase": "synthesis",
                "status": "completed",
                "execution_mode": "coordinator",
                "priority": 50,
                "blocked_by": research_task_ids,
                "result_summary": _short_json(
                    {
                        "search_brief": dict(plan.get("search_brief") or {}),
                        "search_critic": dict(plan.get("search_critic") or {}),
                        "search_retry": dict(plan.get("search_retry") or {}),
                    },
                    limit=180,
                ),
                "metadata": {"compat_projection": "agent_batch.plan_summary"},
                "task_spec": {
                    "task_type": "synthesis",
                    "goal": command,
                    "context": {"plan_loop": dict(plan.get("loop") or {})},
                    "target_scope": "agent_batch.plan",
                    "write_set": [],
                    "completion_criteria": ["Carry forward the synthesized search plan state."],
                    "verification_steps": ["Confirm search_brief and critic payloads are attached."],
                    "artifact_targets": ["search_brief.json", "scratchpad.md", "memory.md"],
                },
            }
        )
        implementation_status = "blocked"
        verification_status = "blocked"
        if submit:
            implementation_status = "completed" if bool(completion.get("completed")) else "in_progress"
            verification_status = "completed" if bool(completion.get("completed")) else "pending"
        blueprints.append(
            {
                "task_id": _new_id("task"),
                "subject": "Implementation",
                "description": "Projected from agent_batch dispatch job state.",
                "task_type": "implementation",
                "phase": "implementation",
                "status": implementation_status,
                "execution_mode": "worker",
                "priority": 60,
                "blocked_by_refs": ["prev"],
                "write_set": [f"agent_batch.job:{submit.get('job_id') or 'dry-run'}"],
                "read_set": [],
                "result_summary": f"job_id={submit.get('job_id') or 'n/a'} accepted={submit.get('accepted_count') or 0}",
                "metadata": {"compat_projection": "agent_batch.submit", "submit": submit},
                "task_spec": {
                    "task_type": "implementation",
                    "goal": command,
                    "context": {"submit": submit},
                    "target_scope": str(submit.get("job_id") or "agent_batch.dry_run"),
                    "write_set": [f"agent_batch.job:{submit.get('job_id') or 'dry-run'}"],
                    "completion_criteria": ["Track the batch dispatch state in the session task bus."],
                    "verification_steps": ["Inspect linked job progress and completion state."],
                    "artifact_targets": ["compat.loop_result.json", "scratchpad.md"],
                },
            }
        )
        blueprints.append(
            {
                "task_id": _new_id("task"),
                "subject": "Verification",
                "description": "Projected from agent_batch completion state.",
                "task_type": "verification",
                "phase": "verification",
                "status": verification_status,
                "execution_mode": "worker",
                "priority": 70,
                "blocked_by_refs": ["prev"],
                "write_set": [],
                "read_set": [f"agent_batch.job:{submit.get('job_id') or 'dry-run'}"],
                "result_summary": _short_json(completion, limit=180) if completion else None,
                "metadata": {"compat_projection": "agent_batch.completion", "completion": completion},
                "task_spec": {
                    "task_type": "verification",
                    "goal": command,
                    "context": {"completion": completion},
                    "target_scope": str(submit.get("job_id") or "agent_batch.dry_run"),
                    "write_set": [],
                    "completion_criteria": ["Reflect whether the projected compat job has completed verification."],
                    "verification_steps": ["Observe completion payload and task statuses."],
                    "artifact_targets": ["compat.loop_result.json", "memory.md", "scratchpad.md"],
                },
            }
        )
        return blueprints

    def _build_agent_batch_job_blueprints(
        self,
        *,
        job_id: str,
        accepted_items: list[dict[str, Any]],
        rejected_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        blueprints: list[dict[str, Any]] = []
        item_task_ids: list[str] = []
        for item in accepted_items:
            blueprint = self._build_agent_batch_job_item_blueprint(compat_job_id=job_id, item=item)
            blueprints.append(blueprint)
            item_task_ids.append(str(blueprint["task_id"]))
        verification_status = "blocked" if item_task_ids else "completed"
        blueprints.append(
            {
                "task_id": _new_id("task"),
                "subject": "Verification",
                "description": "Track projected agent_batch job completion state.",
                "task_type": "verification",
                "phase": "verification",
                "status": verification_status,
                "execution_mode": "worker",
                "priority": 90,
                "blocked_by": item_task_ids,
                "write_set": [],
                "read_set": [f"agent_batch.job:{job_id}"],
                "result_summary": f"accepted={len(accepted_items)} rejected={len(rejected_items)}",
                "metadata": {
                    "compat_projection": "agent_batch.job_verification",
                    "compat_job_id": job_id,
                },
                "task_spec": {
                    "task_type": "verification",
                    "goal": f"Verify projected agent_batch job {job_id}",
                    "context": {"accepted_items": accepted_items, "rejected_items": rejected_items},
                    "target_scope": job_id,
                    "write_set": [],
                    "completion_criteria": ["Reflect aggregate batch job completion state in the session ledger."],
                    "verification_steps": ["Observe projected item task states and aggregate progress."],
                    "artifact_targets": ["compat.job.submit.json", "memory.md", "scratchpad.md"],
                },
            }
        )
        return blueprints

    def _build_agent_batch_job_item_blueprint(self, *, compat_job_id: str, item: dict[str, Any]) -> dict[str, Any]:
        item_id = str(item.get("item_id") or _new_id("task")).strip()
        task_status = self._map_agent_batch_task_status(str((item.get("snapshot") or {}).get("status") or "pending"))
        return {
            "task_id": _new_id("task"),
            "subject": f"Dispatch {item_id}",
            "description": "Projected from /agent-batch/jobs direct submit path.",
            "task_type": "implementation",
            "phase": "implementation",
            "status": task_status,
            "execution_mode": "worker",
            "priority": max(1, int(item.get("index") or 1)),
            "write_set": [f"agent_batch.job:{compat_job_id}:item:{item_id}"],
            "read_set": [f"agent_batch.job:{compat_job_id}"],
            "result_summary": _short_json(
                {
                    "lane": item.get("lane"),
                    "channel": item.get("channel"),
                    "workflow_run_id": item.get("workflow_run_id"),
                },
                limit=180,
            ),
            "metadata": {
                "compat_projection": "agent_batch.job_item",
                "compat_job_id": compat_job_id,
                "item_id": item_id,
                "task_id": item.get("task_id"),
                "channel": item.get("channel"),
                "lane": item.get("lane"),
                "workflow_run_id": item.get("workflow_run_id"),
                "trace_id": item.get("trace_id"),
            },
            "task_spec": {
                "task_type": "implementation",
                "goal": f"Track dispatch item {item_id} for agent_batch job {compat_job_id}",
                "context": {"item": item},
                "target_scope": item.get("item_key") or item_id,
                "write_set": [f"agent_batch.job:{compat_job_id}:item:{item_id}"],
                "completion_criteria": ["Reflect task dispatch state from celery/runtime into the agent session ledger."],
                "verification_steps": ["Observe task snapshot and workflow run mapping."],
                "artifact_targets": ["compat.job.submit.json", "scratchpad.md"],
            },
        }

    def _build_workflow_graph_task_blueprints(self, *, graph_id: str, run_id: str, workflow: dict[str, Any]) -> list[dict[str, Any]]:
        topo_order = [str(item or "").strip() for item in list(workflow.get("topo_order") or []) if str(item or "").strip()]
        nodes = dict(workflow.get("nodes") or {})
        blueprints: list[dict[str, Any]] = []
        for index, node_id in enumerate(topo_order, start=1):
            node = dict(nodes.get(node_id) or {})
            task_id = self._workflow_graph_node_task_id(run_id=run_id, node_id=node_id)
            depends_on = [self._workflow_graph_node_task_id(run_id=run_id, node_id=dep) for dep in list(node.get("depends_on") or []) if str(dep or "").strip()]
            blueprints.append(
                {
                    "task_id": task_id,
                    "subject": f"Node {node_id}",
                    "description": f"Workflow graph node {node_id} projected into the agent task bus.",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "status": "blocked" if depends_on else "pending",
                    "execution_mode": "worker",
                    "priority": min(9, index),
                    "blocked_by": depends_on,
                    "write_set": [f"workflow_graph.node:{node_id}"],
                    "read_set": [f"workflow_graph.graph:{graph_id}"],
                    "metadata": {
                        "workflow_graph_node": {
                            "graph_id": graph_id,
                            "run_id": run_id,
                            "node_id": node_id,
                            "node_type": node.get("node_type"),
                        }
                    },
                    "task_spec": {
                        "task_type": "implementation",
                        "goal": f"Execute workflow graph node {node_id}",
                        "context": {"graph_id": graph_id, "run_id": run_id},
                        "target_scope": node_id,
                        "write_set": [f"workflow_graph.node:{node_id}"],
                        "completion_criteria": [f"Node {node_id} reaches a terminal status in the workflow runtime."],
                        "verification_steps": [f"Confirm node {node_id} status is reflected in the workflow snapshot."],
                        "artifact_targets": ["workflow_graph.snapshot.json", "scratchpad.md"],
                    },
                }
            )
        blueprints.append(
            {
                "task_id": self._workflow_graph_verification_task_id(run_id),
                "subject": "Verification",
                "description": "Final workflow graph run verification projected into the agent task bus.",
                "task_type": "verification",
                "phase": "verification",
                "status": "blocked" if topo_order else "pending",
                "execution_mode": "worker",
                "priority": 9,
                "blocked_by": [self._workflow_graph_node_task_id(run_id=run_id, node_id=node_id) for node_id in topo_order],
                "write_set": [],
                "read_set": [f"workflow_graph.run:{run_id}"],
                "metadata": {"workflow_graph_verification": True, "graph_id": graph_id, "run_id": run_id},
                "task_spec": {
                    "task_type": "verification",
                    "goal": f"Verify workflow graph run {run_id}",
                    "context": {"graph_id": graph_id, "run_id": run_id},
                    "target_scope": run_id,
                    "write_set": [],
                    "completion_criteria": [f"Reflect final workflow run state for {run_id}."],
                    "verification_steps": [f"Inspect run status and node statuses for {run_id}."],
                    "artifact_targets": ["workflow_graph.snapshot.json", "memory.md"],
                },
            }
        )
        return blueprints

    def _bootstrap_memory_artifacts(self, session: dict[str, Any]) -> None:
        session_id = session["session_id"]
        self.store.upsert_artifact(
            {
                "session_id": session_id,
                "artifact_type": "session_memory_markdown",
                "name": "memory.md",
                "mime_type": "text/markdown",
                "content_text": self.memory_runtime.render_memory(session, [], []),
                "metadata": {"managed_by": "agent_sessions.service"},
            }
        )
        self.store.upsert_artifact(
            {
                "session_id": session_id,
                "artifact_type": "session_scratchpad_markdown",
                "name": "scratchpad.md",
                "mime_type": "text/markdown",
                "content_text": self.memory_runtime.render_scratchpad(session, [], []),
                "metadata": {"managed_by": "agent_sessions.service"},
            }
        )

    def _refresh_memory_artifacts(self, session_id: str, *, force: bool = False) -> None:
        session = self.store.get_session(session_id)
        tasks = self.store.list_tasks(session_id)
        messages = self.store.list_messages(session_id)
        self.store.upsert_artifact(
            {
                "session_id": session_id,
                "artifact_type": "session_memory_markdown",
                "name": "memory.md",
                "mime_type": "text/markdown",
                "content_text": self.memory_runtime.render_memory(session, tasks, messages),
                "metadata": {"managed_by": "agent_sessions.service", "force": bool(force)},
            }
        )
        self.store.upsert_artifact(
            {
                "session_id": session_id,
                "artifact_type": "session_scratchpad_markdown",
                "name": "scratchpad.md",
                "mime_type": "text/markdown",
                "content_text": self.memory_runtime.render_scratchpad(session, tasks, messages),
                "metadata": {"managed_by": "agent_sessions.service", "force": bool(force)},
            }
        )
        if force:
            self.store.append_event(
                session_id,
                event_type="memory.updated",
                payload={"reason": "forced_refresh", "task_count": len(tasks)},
            )

    def _maybe_refresh_memory(self, session_id: str) -> None:
        tasks = self.store.list_tasks(session_id)
        events = self.store.list_events(session_id)
        thresholds_met, _ = self.memory_runtime.should_refresh(tasks=tasks, events=events)
        if thresholds_met:
            self._refresh_memory_artifacts(session_id, force=True)

    @staticmethod
    def _workflow_graph_node_task_id(*, run_id: str, node_id: str) -> str:
        digest = hashlib.sha1(
            f"{run_id}:{node_id}".encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:12]
        return f"wgn-{digest}"

    @staticmethod
    def _workflow_graph_verification_task_id(run_id: str) -> str:
        digest = hashlib.sha1(
            f"{run_id}:verification".encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:12]
        return f"wgv-{digest}"

    @staticmethod
    def _map_workflow_graph_status(status: str) -> str:
        normalized = str(status or "").strip().lower()
        if normalized in {"succeeded", "success"}:
            return "completed"
        if normalized in {"failed", "failure"}:
            return "failed"
        if normalized in {"running", "started"}:
            return "in_progress"
        if normalized in {"queued", "pending"}:
            return "pending"
        return "pending"

    @staticmethod
    def _map_agent_batch_task_status(status: str) -> str:
        normalized = str(status or "").strip().lower()
        if normalized in {"success", "succeeded"}:
            return "completed"
        if normalized in {"failure", "failed", "revoked"}:
            return "failed"
        if normalized in {"started", "running", "retry"}:
            return "in_progress"
        return "pending"

    @staticmethod
    def _map_agent_batch_job_phase_to_task_status(phase: str, *, progress: dict[str, Any]) -> str:
        normalized = str(phase or "").strip().lower()
        failed = int(progress.get("failed") or 0)
        running = int(progress.get("running") or 0) + int(progress.get("queued") or 0)
        if normalized == "completed":
            return "failed" if failed > 0 else "completed"
        if running > 0:
            return "blocked"
        return "pending"

    def _sync_session_state(self, session_id: str) -> dict[str, Any]:
        tasks = self.store.list_tasks(session_id)
        session = self.store.get_session(session_id)
        if not tasks:
            return self._decorate_session(session)
        status, current_phase = resolve_session_status(tasks)
        current_phase = current_phase or session.get("current_phase")
        final_summary = session.get("final_summary")
        if status == "completed":
            verification = next((task for task in reversed(tasks) if task.get("phase") == "verification"), None)
            final_summary = str((verification or {}).get("result_summary") or final_summary or "").strip() or None

        updated = self.store.update_session(
            session_id,
            {"status": status, "current_phase": current_phase, "final_summary": final_summary},
        )
        return self._decorate_session(updated, tasks=tasks, task_count=len(tasks))

    def _unblock_dependents(self, session_id: str, task_id: str) -> None:
        tasks = self.store.list_tasks(session_id)
        task_index = {task["task_id"]: task for task in tasks}
        for task in tasks:
            blocked_by = list(task.get("blocked_by") or [])
            if task_id not in blocked_by:
                continue
            unresolved = [dep for dep in blocked_by if self._task_status(tasks, dep) != "completed"]
            if unresolved:
                continue
            if task.get("status") == "blocked":
                updated = self.store.update_task(session_id, task["task_id"], {"status": "pending"})
                self.store.update_task(session_id, task["task_id"], {"summary_label": build_summary_label(updated)})
                self.store.append_event(
                    session_id,
                    event_type="task.unblocked",
                    task_id=task["task_id"],
                    payload={"unblocked_by": task_id},
                )

    @staticmethod
    def _task_status(tasks: list[dict[str, Any]], task_id: str) -> str | None:
        for task in tasks:
            if task["task_id"] == task_id:
                return str(task.get("status") or "")
        return None

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


_SERVICE: AgentSessionService | None = None


def get_agent_session_service() -> AgentSessionService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = AgentSessionService()
    return _SERVICE


def reset_agent_session_service_for_tests(service: AgentSessionService | None = None) -> None:
    global _SERVICE
    _SERVICE = service
