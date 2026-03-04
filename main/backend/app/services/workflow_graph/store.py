from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

TERMINAL_STATUSES = {"succeeded", "failed"}
NODE_STATUSES = {"queued", "running", "succeeded", "failed"}
RUN_STATUSES = {"queued", "running", "succeeded", "failed"}


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


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
