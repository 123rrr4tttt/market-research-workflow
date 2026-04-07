from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4
import logging

from sqlalchemy import func, text

from app.models.base import Base, SessionLocal, engine
from app.models.entities import WorkflowGraphEvent, WorkflowGraphRun
from app.settings.config import settings

TERMINAL_STATUSES = {"succeeded", "failed"}
NODE_STATUSES = {"queued", "running", "succeeded", "failed"}
RUN_STATUSES = {"queued", "running", "succeeded", "failed"}

logger = logging.getLogger("app.services.workflow_graph.store")


class InMemoryRunStore:
    """Thread-safe in-memory store for workflow runs/events/results."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def create_run(
        self,
        *,
        run_id: str | None = None,
        topo_order: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        with self._lock:
            resolved_run_id = str(run_id or uuid4().hex)
            now = _utcnow()
            node_statuses = {node_id: "queued" for node_id in (topo_order or [])}
            self._runs[resolved_run_id] = {
                "run_id": resolved_run_id,
                "status": "queued",
                "created_at": now,
                "updated_at": now,
                "node_statuses": node_statuses,
                "metadata": deepcopy(metadata or {}),
            }
            self._events[resolved_run_id] = []
            self._results[resolved_run_id] = {}
            return resolved_run_id

    def ensure_node(self, run_id: str, node_id: str) -> None:
        with self._lock:
            run = self._must_get_run_ref(run_id)
            run["node_statuses"].setdefault(node_id, "queued")
            run["updated_at"] = _utcnow()

    def set_run_status(self, run_id: str, status: str) -> None:
        if status not in RUN_STATUSES:
            raise ValueError(f"unsupported run status: {status}")
        with self._lock:
            run = self._must_get_run_ref(run_id)
            run["status"] = status
            run["updated_at"] = _utcnow()

    def set_node_status(self, run_id: str, node_id: str, status: str) -> None:
        if status not in NODE_STATUSES:
            raise ValueError(f"unsupported node status: {status}")
        with self._lock:
            run = self._must_get_run_ref(run_id)
            run["node_statuses"][node_id] = status
            run["updated_at"] = _utcnow()

    def set_node_result(self, run_id: str, node_id: str, result: Any) -> None:
        with self._lock:
            self._must_get_run_ref(run_id)
            self._results[run_id][node_id] = deepcopy(result)

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._must_get_run_ref(run_id)
            event = {
                "ts": _utcnow(),
                "type": str(event_type),
                "node_id": node_id,
                "payload": deepcopy(payload or {}),
            }
            self._events[run_id].append(event)
            return deepcopy(event)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._must_get_run_ref(run_id))

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._must_get_run_ref(run_id)
            return deepcopy(self._events[run_id])

    def get_results(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            self._must_get_run_ref(run_id)
            return deepcopy(self._results[run_id])

    def snapshot(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            return {
                "run": self.get_run(run_id),
                "events": self.get_events(run_id),
                "results": self.get_results(run_id),
            }

    def _must_get_run_ref(self, run_id: str) -> dict[str, Any]:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        return run


class SqlRunStore:
    """DB-backed store for workflow graph runs/events/results."""

    def __init__(self) -> None:
        with engine.begin() as conn:
            conn.execute(text('SET search_path TO "public"'))
            Base.metadata.create_all(
                bind=conn,
                tables=[WorkflowGraphRun.__table__, WorkflowGraphEvent.__table__],
                checkfirst=True,
            )

    def create_run(
        self,
        *,
        run_id: str | None = None,
        topo_order: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        resolved_run_id = str(run_id or uuid4().hex)
        node_statuses = {node_id: "queued" for node_id in (topo_order or [])}
        with SessionLocal() as session:
            row = session.query(WorkflowGraphRun).filter(WorkflowGraphRun.run_id == resolved_run_id).one_or_none()
            if row is None:
                row = WorkflowGraphRun(
                    run_id=resolved_run_id,
                    workflow_id=str((metadata or {}).get("workflow_id") or "") or None,
                    status="queued",
                    node_statuses=node_statuses,
                    metadata_json=dict(metadata or {}),
                    results={},
                )
                session.add(row)
            else:
                row.status = "queued"
                row.node_statuses = node_statuses
                row.metadata_json = dict(metadata or {})
                row.results = {}
            session.commit()
        return resolved_run_id

    def ensure_node(self, run_id: str, node_id: str) -> None:
        with SessionLocal() as session:
            row = self._must_get_run_row(session, run_id)
            status_map = dict(row.node_statuses or {})
            status_map.setdefault(node_id, "queued")
            row.node_statuses = status_map
            session.commit()

    def set_run_status(self, run_id: str, status: str) -> None:
        if status not in RUN_STATUSES:
            raise ValueError(f"unsupported run status: {status}")
        with SessionLocal() as session:
            row = self._must_get_run_row(session, run_id)
            row.status = status
            session.commit()

    def set_node_status(self, run_id: str, node_id: str, status: str) -> None:
        if status not in NODE_STATUSES:
            raise ValueError(f"unsupported node status: {status}")
        with SessionLocal() as session:
            row = self._must_get_run_row(session, run_id)
            status_map = dict(row.node_statuses or {})
            status_map[node_id] = status
            row.node_statuses = status_map
            session.commit()

    def set_node_result(self, run_id: str, node_id: str, result: Any) -> None:
        with SessionLocal() as session:
            row = self._must_get_run_row(session, run_id)
            results = dict(row.results or {})
            results[node_id] = deepcopy(result)
            row.results = results
            session.commit()

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as session:
            self._must_get_run_row(session, run_id)
            seq = int(
                session.query(func.coalesce(func.max(WorkflowGraphEvent.seq), 0))
                .filter(WorkflowGraphEvent.run_id == run_id)
                .scalar()
                or 0
            ) + 1
            row = WorkflowGraphEvent(
                run_id=run_id,
                seq=seq,
                event_type=str(event_type),
                node_id=node_id,
                payload=deepcopy(payload or {}),
            )
            session.add(row)
            session.commit()
            return {
                "ts": _to_iso(row.ts),
                "seq": seq,
                "type": row.event_type,
                "node_id": row.node_id,
                "payload": deepcopy(row.payload or {}),
            }

    def get_run(self, run_id: str) -> dict[str, Any]:
        with SessionLocal() as session:
            row = self._must_get_run_row(session, run_id)
            return {
                "run_id": row.run_id,
                "status": row.status,
                "created_at": _to_iso(row.created_at),
                "updated_at": _to_iso(row.updated_at),
                "node_statuses": deepcopy(row.node_statuses or {}),
                "metadata": deepcopy(row.metadata_json or {}),
            }

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            self._must_get_run_row(session, run_id)
            rows = (
                session.query(WorkflowGraphEvent)
                .filter(WorkflowGraphEvent.run_id == run_id)
                .order_by(WorkflowGraphEvent.seq.asc())
                .all()
            )
            return [
                {
                    "ts": _to_iso(row.ts),
                    "seq": int(row.seq or 0),
                    "type": row.event_type,
                    "node_id": row.node_id,
                    "payload": deepcopy(row.payload or {}),
                }
                for row in rows
            ]

    def get_results(self, run_id: str) -> dict[str, Any]:
        with SessionLocal() as session:
            row = self._must_get_run_row(session, run_id)
            return deepcopy(row.results or {})

    def snapshot(self, run_id: str) -> dict[str, Any]:
        return {
            "run": self.get_run(run_id),
            "events": self.get_events(run_id),
            "results": self.get_results(run_id),
        }

    @staticmethod
    def _must_get_run_row(session: Any, run_id: str) -> WorkflowGraphRun:
        row = session.query(WorkflowGraphRun).filter(WorkflowGraphRun.run_id == run_id).one_or_none()
        if row is None:
            raise KeyError(f"run not found: {run_id}")
        return row


def build_run_store() -> InMemoryRunStore | SqlRunStore:
    """Construct runtime store with fail-closed option."""
    if not bool(getattr(settings, "workflow_graph_db_store_enabled", True)):
        return InMemoryRunStore()
    try:
        return SqlRunStore()
    except Exception as exc:  # noqa: BLE001
        if bool(getattr(settings, "workflow_graph_db_store_fail_closed", True)):
            raise RuntimeError(f"workflow graph db store unavailable (fail-closed): {exc}") from exc
        logger.warning("workflow graph db store disabled by runtime error, fallback to memory: %s", exc)
        return InMemoryRunStore()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return _utcnow()
