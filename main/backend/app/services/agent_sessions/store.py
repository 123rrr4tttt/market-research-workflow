from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4
import logging

from sqlalchemy import func, text

from app.models.base import Base, SessionLocal, engine
from app.models.entities import (
    AgentApproval,
    AgentArtifact,
    AgentEvent,
    AgentMessage,
    AgentSession,
    AgentTask,
)
from app.settings.config import settings

logger = logging.getLogger("app.services.agent_sessions.store")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if value is None:
        return None
    return str(value)


def _clone(value: Any) -> Any:
    return deepcopy(value)


def _artifact_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item.get("name") or ""), str(item.get("artifact_id") or ""))


class InMemoryAgentSessionStore:
    """Thread-safe fallback store for agent sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, dict[str, dict[str, Any]]] = {}
        self._messages: dict[str, list[dict[str, Any]]] = {}
        self._artifacts: dict[str, dict[str, dict[str, Any]]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._approvals: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("session_id is required")
        with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"session already exists: {session_id}")
            item = _clone(payload)
            now = _as_iso(_utcnow())
            item.setdefault("created_at", now)
            item.setdefault("updated_at", now)
            item.setdefault("metadata", {})
            item.setdefault("final_result", {})
            self._sessions[session_id] = item
            self._tasks[session_id] = {}
            self._messages[session_id] = []
            self._artifacts[session_id] = {}
            self._events[session_id] = []
            return _clone(item)

    def update_session(self, session_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            session = self._must_get_session_ref(session_id)
            session.update(_clone(changes))
            session["updated_at"] = _as_iso(_utcnow())
            return _clone(session)

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            return _clone(self._must_get_session_ref(session_id))

    def list_sessions(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            items = sorted(
                self._sessions.values(),
                key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
                reverse=True,
            )
            return [_clone(item) for item in items[: max(1, int(limit))]]

    def find_session_by_compat_job_id(self, compat_job_id: str) -> dict[str, Any] | None:
        target = str(compat_job_id or "").strip()
        if not target:
            return None
        with self._lock:
            for item in self._sessions.values():
                if str(item.get("compat_job_id") or "").strip() == target:
                    return _clone(item)
            return None

    def find_session_by_logical_task_list_key(self, logical_task_list_key: str) -> dict[str, Any] | None:
        target = str(logical_task_list_key or "").strip()
        if not target:
            return None
        with self._lock:
            for item in self._sessions.values():
                if str(item.get("logical_task_list_key") or "").strip() == target:
                    return _clone(item)
            return None

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "").strip()
        task_id = str(payload.get("task_id") or "").strip()
        if not session_id or not task_id:
            raise ValueError("session_id and task_id are required")
        with self._lock:
            self._must_get_session_ref(session_id)
            item = _clone(payload)
            now = _as_iso(_utcnow())
            item.setdefault("created_at", now)
            item.setdefault("updated_at", now)
            item.setdefault("blocked_by", [])
            item.setdefault("blocks", [])
            item.setdefault("write_set", [])
            item.setdefault("read_set", [])
            item.setdefault("task_spec", {})
            item.setdefault("metadata", {})
            item.setdefault("result_payload", {})
            item.setdefault("recent_activities", [])
            self._tasks[session_id][task_id] = item
            return _clone(item)

    def get_task(self, session_id: str, task_id: str) -> dict[str, Any]:
        with self._lock:
            return _clone(self._must_get_task_ref(session_id, task_id))

    def update_task(self, session_id: str, task_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            item = self._must_get_task_ref(session_id, task_id)
            item.update(_clone(changes))
            item["updated_at"] = _as_iso(_utcnow())
            self._sessions[session_id]["updated_at"] = item["updated_at"]
            return _clone(item)

    def list_tasks(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._must_get_session_ref(session_id)
            items = sorted(
                self._tasks[session_id].values(),
                key=lambda item: str(item.get("created_at") or ""),
            )
            return [_clone(item) for item in items]

    def create_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("session_id is required")
        with self._lock:
            self._must_get_session_ref(session_id)
            item = _clone(payload)
            item.setdefault("created_at", _as_iso(_utcnow()))
            self._messages[session_id].append(item)
            return _clone(item)

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._must_get_session_ref(session_id)
            return [_clone(item) for item in self._messages[session_id]]

    def upsert_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        artifact_id = str(payload.get("artifact_id") or "").strip() or f"artifact-{uuid4().hex[:16]}"
        if not session_id or not name:
            raise ValueError("session_id and name are required")
        with self._lock:
            self._must_get_session_ref(session_id)
            existing = self._artifacts[session_id].get(name)
            item = _clone(existing or {})
            item.update(_clone(payload))
            item["artifact_id"] = artifact_id if not existing else str(existing.get("artifact_id") or artifact_id)
            item.setdefault("created_at", _as_iso(_utcnow()))
            item["updated_at"] = _as_iso(_utcnow())
            item.setdefault("content_json", {})
            item.setdefault("metadata", {})
            self._artifacts[session_id][name] = item
            return _clone(item)

    def list_artifacts(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._must_get_session_ref(session_id)
            return [_clone(item) for item in sorted(self._artifacts[session_id].values(), key=_artifact_sort_key)]

    def append_event(
        self,
        session_id: str,
        *,
        event_type: str,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._must_get_session_ref(session_id)
            seq = len(self._events[session_id]) + 1
            item = {
                "session_id": session_id,
                "seq": seq,
                "event_type": str(event_type),
                "task_id": str(task_id or "").strip() or None,
                "payload": _clone(payload or {}),
                "ts": _as_iso(_utcnow()),
            }
            self._events[session_id].append(item)
            self._sessions[session_id]["updated_at"] = item["ts"]
            return _clone(item)

    def list_events(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._must_get_session_ref(session_id)
            return [_clone(item) for item in self._events[session_id]]

    def create_or_update_approval(self, payload: dict[str, Any]) -> dict[str, Any]:
        approval_id = str(payload.get("approval_id") or "").strip()
        if not approval_id:
            raise ValueError("approval_id is required")
        with self._lock:
            existing = self._approvals.get(approval_id)
            item = _clone(existing or {})
            item.update(_clone(payload))
            item.setdefault("created_at", _as_iso(_utcnow()))
            item["updated_at"] = _as_iso(_utcnow())
            item.setdefault("binding_payload", {})
            item.setdefault("audit_log", [])
            item.setdefault("metadata", {})
            self._approvals[approval_id] = item
            return _clone(item)

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        with self._lock:
            item = self._approvals.get(str(approval_id or "").strip())
            if item is None:
                raise KeyError(f"approval not found: {approval_id}")
            return _clone(item)

    def list_approvals(self, *, session_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            out = []
            for item in self._approvals.values():
                if session_id and str(item.get("requester_session_id") or "").strip() != session_id:
                    continue
                out.append(_clone(item))
            return sorted(out, key=lambda item: str(item.get("updated_at") or ""), reverse=True)

    def _must_get_session_ref(self, session_id: str) -> dict[str, Any]:
        item = self._sessions.get(session_id)
        if item is None:
            raise KeyError(f"session not found: {session_id}")
        return item

    def _must_get_task_ref(self, session_id: str, task_id: str) -> dict[str, Any]:
        self._must_get_session_ref(session_id)
        item = self._tasks.get(session_id, {}).get(task_id)
        if item is None:
            raise KeyError(f"task not found: {task_id}")
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

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        with SessionLocal() as session:
            row = AgentSession(
                session_id=str(payload.get("session_id") or ""),
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

    def update_session(self, session_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        with SessionLocal() as session:
            row = self._must_get_session_row(session, session_id)
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

    def get_session(self, session_id: str) -> dict[str, Any]:
        with SessionLocal() as session:
            return _session_row_to_dict(self._must_get_session_row(session, session_id))

    def list_sessions(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rows = (
                session.query(AgentSession)
                .order_by(AgentSession.updated_at.desc(), AgentSession.created_at.desc())
                .limit(max(1, int(limit)))
                .all()
            )
            return [_session_row_to_dict(row) for row in rows]

    def find_session_by_compat_job_id(self, compat_job_id: str) -> dict[str, Any] | None:
        target = str(compat_job_id or "").strip()
        if not target:
            return None
        with SessionLocal() as session:
            row = session.query(AgentSession).filter(AgentSession.compat_job_id == target).one_or_none()
            return None if row is None else _session_row_to_dict(row)

    def find_session_by_logical_task_list_key(self, logical_task_list_key: str) -> dict[str, Any] | None:
        target = str(logical_task_list_key or "").strip()
        if not target:
            return None
        with SessionLocal() as session:
            row = session.query(AgentSession).filter(AgentSession.logical_task_list_key == target).one_or_none()
            return None if row is None else _session_row_to_dict(row)

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        with SessionLocal() as session:
            row = AgentTask(
                task_id=str(payload.get("task_id") or ""),
                session_id=str(payload.get("session_id") or ""),
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

    def get_task(self, session_id: str, task_id: str) -> dict[str, Any]:
        with SessionLocal() as session:
            return _task_row_to_dict(self._must_get_task_row(session, session_id, task_id))

    def update_task(self, session_id: str, task_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        with SessionLocal() as session:
            row = self._must_get_task_row(session, session_id, task_id)
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

    def list_tasks(self, session_id: str) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rows = (
                session.query(AgentTask)
                .filter(AgentTask.session_id == session_id)
                .order_by(AgentTask.created_at.asc(), AgentTask.id.asc())
                .all()
            )
            return [_task_row_to_dict(row) for row in rows]

    def create_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        with SessionLocal() as session:
            row = AgentMessage(
                session_id=str(payload.get("session_id") or ""),
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

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rows = (
                session.query(AgentMessage)
                .filter(AgentMessage.session_id == session_id)
                .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
                .all()
            )
            return [_message_row_to_dict(row) for row in rows]

    def upsert_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not session_id or not name:
            raise ValueError("session_id and name are required")
        with SessionLocal() as session:
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

    def list_artifacts(self, session_id: str) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rows = (
                session.query(AgentArtifact)
                .filter(AgentArtifact.session_id == session_id)
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
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as session:
            self._must_get_session_row(session, session_id)
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
                payload=dict(payload or {}),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _event_row_to_dict(row)

    def list_events(self, session_id: str) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rows = (
                session.query(AgentEvent)
                .filter(AgentEvent.session_id == session_id)
                .order_by(AgentEvent.seq.asc(), AgentEvent.id.asc())
                .all()
            )
            return [_event_row_to_dict(row) for row in rows]

    def create_or_update_approval(self, payload: dict[str, Any]) -> dict[str, Any]:
        approval_id = str(payload.get("approval_id") or "").strip()
        if not approval_id:
            raise ValueError("approval_id is required")
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

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        with SessionLocal() as session:
            row = session.query(AgentApproval).filter(AgentApproval.approval_id == approval_id).one_or_none()
            if row is None:
                raise KeyError(f"approval not found: {approval_id}")
            return _approval_row_to_dict(row)

    def list_approvals(self, *, session_id: str | None = None) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            query = session.query(AgentApproval)
            if session_id:
                query = query.filter(AgentApproval.requester_session_id == session_id)
            rows = query.order_by(AgentApproval.updated_at.desc(), AgentApproval.created_at.desc()).all()
            return [_approval_row_to_dict(row) for row in rows]

    @staticmethod
    def _must_get_session_row(session: Any, session_id: str) -> AgentSession:
        row = session.query(AgentSession).filter(AgentSession.session_id == session_id).one_or_none()
        if row is None:
            raise KeyError(f"session not found: {session_id}")
        return row

    @staticmethod
    def _must_get_task_row(session: Any, session_id: str, task_id: str) -> AgentTask:
        row = (
            session.query(AgentTask)
            .filter(AgentTask.session_id == session_id, AgentTask.task_id == task_id)
            .one_or_none()
        )
        if row is None:
            raise KeyError(f"task not found: {task_id}")
        return row


_STORE: InMemoryAgentSessionStore | SqlAgentSessionStore | None = None


def build_agent_session_store() -> InMemoryAgentSessionStore | SqlAgentSessionStore:
    global _STORE
    if _STORE is not None:
        return _STORE
    if bool(getattr(settings, "agent_session_db_store_enabled", True)):
        try:
            _STORE = SqlAgentSessionStore()
            return _STORE
        except Exception as exc:  # noqa: BLE001
            if bool(getattr(settings, "agent_session_db_store_fail_closed", False)):
                raise
            logger.warning("agent session db store unavailable, falling back to memory: %s", exc)
    _STORE = InMemoryAgentSessionStore()
    return _STORE


def reset_agent_session_store_for_tests(store: InMemoryAgentSessionStore | SqlAgentSessionStore | None = None) -> None:
    global _STORE
    _STORE = store


def _session_row_to_dict(row: AgentSession) -> dict[str, Any]:
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


def _task_row_to_dict(row: AgentTask) -> dict[str, Any]:
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


def _message_row_to_dict(row: AgentMessage) -> dict[str, Any]:
    return {
        "session_id": row.session_id,
        "task_id": row.task_id,
        "role": row.role,
        "actor": row.actor,
        "content": row.content,
        "metadata": dict(row.metadata_json or {}),
        "created_at": _as_iso(row.created_at),
    }


def _artifact_row_to_dict(row: AgentArtifact) -> dict[str, Any]:
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


def _event_row_to_dict(row: AgentEvent) -> dict[str, Any]:
    return {
        "session_id": row.session_id,
        "seq": int(row.seq or 0),
        "event_type": row.event_type,
        "task_id": row.task_id,
        "payload": dict(row.payload or {}),
        "ts": _as_iso(row.ts),
    }


def _approval_row_to_dict(row: AgentApproval) -> dict[str, Any]:
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
