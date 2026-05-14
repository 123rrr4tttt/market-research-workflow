from __future__ import annotations

from dataclasses import asdict
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4

from app.services.agent_sessions import get_agent_session_service

from .compiler import compile_workflow_graph
from .curated_service import WorkflowGraphCuratedService
from .runtime import WorkflowGraphRuntime
from .store import (
    InMemoryCompiledGraphStore,
    SqlCompiledGraphStore,
    build_compiled_graph_store,
    build_run_store,
)
from .templates import WorkflowGraphTemplateService


class WorkflowGraphCompilerService:
    """Compiler facade with in-memory compiled graph registry."""

    def __init__(
        self,
        *,
        store: InMemoryCompiledGraphStore | SqlCompiledGraphStore | None = None,
    ) -> None:
        self._compiled: dict[str, dict[str, Any]] = {}
        self._lock = RLock()
        self._store = store or build_compiled_graph_store()
        self._templates = WorkflowGraphTemplateService()

    def compile(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("compile payload must be a mapping")
        dsl_payload = payload.get("dsl")
        template_id = str(payload.get("template_id") or "").strip()
        requested_version_id = str(payload.get("version_id") or "").strip() or None
        resolved_version_id: str | None = None
        if template_id:
            dsl_payload, resolved_version_id = self._templates.resolve_version_dsl(
                template_id=template_id,
                version_id=requested_version_id,
            )
        elif not isinstance(dsl_payload, Mapping):
            dsl_payload = payload
        if not isinstance(dsl_payload, Mapping):
            raise ValueError("dsl payload must be a mapping")

        compiled = compile_workflow_graph(dsl_payload)
        raw_graph_id = payload.get("graph_id")
        graph_id = str(raw_graph_id).strip() if raw_graph_id is not None else ""
        if not graph_id or graph_id.lower() == "none":
            graph_id = uuid4().hex

        nodes = dsl_payload.get("nodes") or []
        normalized_nodes: dict[str, dict[str, Any]] = {}
        for item in nodes:
            if not isinstance(item, Mapping):
                continue
            node_id = str(item.get("node_id") or item.get("id") or "").strip()
            if not node_id:
                continue
            node_type = str(item.get("node_type") or "").strip()
            config = item.get("config")
            if not isinstance(config, Mapping):
                config = item.get("params") if isinstance(item.get("params"), Mapping) else {}
            depends_on = list(compiled.incoming_edges.get(node_id, ()))
            normalized_nodes[node_id] = {
                "id": node_id,
                "node_type": node_type,
                "params": dict(config),
                "depends_on": depends_on,
            }

        compiled_record = {
            "graph_id": graph_id,
            "version": compiled.version,
            "options": dict(compiled.options),
            "checksum": compiled.checksum,
            "topo_order": list(compiled.topo_order),
            "outgoing_edges": {k: list(v) for k, v in compiled.outgoing_edges.items()},
            "incoming_edges": {k: list(v) for k, v in compiled.incoming_edges.items()},
            "nodes": normalized_nodes,
            "dsl": dict(dsl_payload),
            "compiled": asdict(compiled),
        }
        with self._lock:
            self._compiled[graph_id] = compiled_record
        self._store.save_compiled(compiled_record)
        response = {
            "graph_id": graph_id,
            "version": compiled.version,
            "checksum": compiled.checksum,
            "topo_order": list(compiled.topo_order),
            "warnings": [],
        }
        if template_id:
            response["template_id"] = template_id
            response["version_id"] = resolved_version_id
        return response

    def get_compiled(self, graph_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._compiled.get(str(graph_id))
        if row is None:
            row = self._store.get_compiled(str(graph_id))
            with self._lock:
                self._compiled[str(graph_id)] = row
        return row

    def list_compiled(self, limit: int = 20) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        try:
            for row in self._store.list_compiled(limit=limit):
                graph_id = str(row.get("graph_id") or "").strip()
                if graph_id:
                    merged[graph_id] = dict(row)
        except Exception:  # noqa: BLE001
            merged = {}
        with self._lock:
            for row in self._compiled.values():
                graph_id = str(row.get("graph_id") or "").strip()
                if graph_id:
                    merged.setdefault(graph_id, dict(row))
        return list(merged.values())[: max(1, int(limit or 20))]

    def list_templates(self) -> dict[str, Any]:
        return self._templates.list_templates()

    def create_template(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._templates.create_template(payload)

    def get_template(self, template_id: str) -> dict[str, Any]:
        return self._templates.get_template(template_id)

    def patch_template(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._templates.patch_template(template_id, payload)

    def delete_template(self, template_id: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._templates.delete_template(template_id, payload)

    def list_template_versions(self, template_id: str) -> dict[str, Any]:
        return self._templates.list_versions(template_id)

    def create_template_version(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._templates.create_version(template_id, payload)

    def get_template_version(self, template_id: str, version_id: str) -> dict[str, Any]:
        return self._templates.get_version(template_id, version_id)

    def activate_template_version(
        self,
        template_id: str,
        version_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._templates.activate_version(template_id, version_id, payload)


class WorkflowGraphRuntimeService:
    """Runtime facade that executes compiled workflow graphs."""

    def __init__(self) -> None:
        self._engine = WorkflowGraphRuntime(store=build_run_store())

    def run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        graph_id = str(payload.get("graph_id") or "").strip()
        if not graph_id:
            raise ValueError("graph_id is required")

        compiled = compiler.get_compiled(graph_id)
        run_input = payload.get("input") or payload.get("inputs") or {}
        if not isinstance(run_input, Mapping):
            raise ValueError("input must be a mapping")

        workflow = {
            "workflow_id": graph_id,
            "topo_order": list(compiled.get("topo_order") or []),
            "nodes": dict(compiled.get("nodes") or {}),
        }
        run_id = str(payload.get("run_id") or "").strip() or None
        snapshot = self._engine.run(workflow, inputs=dict(run_input), run_id=run_id)
        run = snapshot.get("run") or {}
        session_bundle = get_agent_session_service().project_workflow_graph_run(
            graph_id=graph_id,
            run_id=str(run.get("run_id") or ""),
            workflow=workflow,
            inputs=dict(run_input),
            snapshot=snapshot,
            project_key=str(payload.get("project_key") or "").strip() or None,
        )
        session = dict(session_bundle.get("session") or {})
        return {
            "run_id": run.get("run_id"),
            "status": run.get("status"),
            "node_statuses": run.get("node_statuses") or {},
            "session_id": session.get("session_id"),
            "current_phase": session.get("current_phase"),
            "root_task_id": session.get("root_task_id"),
            "compat_mode": False,
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        out = dict(self._engine.store.get_run(str(run_id)))
        session = get_agent_session_service().find_session_by_logical_task_list_key(str(run_id))
        if session:
            out["session_id"] = session.get("session_id")
            out["current_phase"] = session.get("current_phase")
            out["root_task_id"] = session.get("root_task_id")
        return out

    def get_run_events(self, run_id: str) -> dict[str, Any]:
        items = list(self._engine.store.get_events(str(run_id)))
        session = get_agent_session_service().find_session_by_logical_task_list_key(str(run_id))
        if session:
            session_events = get_agent_session_service().list_events(str(session.get("session_id") or ""))
            for event in session_events:
                items.append(
                    {
                        "ts": event.get("ts"),
                        "type": f"agent_session.{event.get('event_type')}",
                        "node_id": None,
                        "payload": dict(event.get("payload") or {}),
                    }
                )
        return {"items": items, "session_id": session.get("session_id") if session else None}

    def get_run_agent_session(self, run_id: str) -> dict[str, Any]:
        session = get_agent_session_service().find_session_by_logical_task_list_key(str(run_id))
        if session is None:
            raise KeyError(f"agent session not found for run: {run_id}")
        return get_agent_session_service().get_session_bundle(str(session.get("session_id") or ""))

    def replay_run(self, run_id: str, replay_mode: str = "events_only") -> dict[str, Any]:
        resolved_mode = str(replay_mode or "events_only").strip().lower() or "events_only"
        if resolved_mode not in {"events_only", "stateful"}:
            raise ValueError("replay_mode must be events_only or stateful")

        snapshot = self._engine.store.snapshot(str(run_id))
        replay_consistency = _build_replay_consistency_report(snapshot)

        if resolved_mode == "stateful":
            run = snapshot.get("run") or {}
            events = list(snapshot.get("events") or [])
            return {
                "run_id": str(run.get("run_id") or run_id),
                "status": str(run.get("status") or "queued"),
                "node_statuses": dict(run.get("node_statuses") or {}),
                "events_count": len(events),
                "events": events,
                "results": dict(snapshot.get("results") or {}),
                "replay_mode": "stateful",
                "replay_consistency": replay_consistency,
            }

        events = list(self._engine.store.get_events(str(run_id)))
        node_statuses: dict[str, str] = {}
        run_status = "queued"
        for event in events:
            event_type = str(event.get("type") or "")
            node_id = str(event.get("node_id") or "").strip()
            if event_type == "run.running":
                run_status = "running"
            elif event_type == "run.succeeded":
                run_status = "succeeded"
            elif event_type == "run.failed":
                run_status = "failed"
            elif event_type == "node.running" and node_id:
                node_statuses[node_id] = "running"
            elif event_type == "node.succeeded" and node_id:
                node_statuses[node_id] = "succeeded"
            elif event_type == "node.failed" and node_id:
                node_statuses[node_id] = "failed"
        return {
            "run_id": str(run_id),
            "status": run_status,
            "node_statuses": node_statuses,
            "events_count": len(events),
            "replay_mode": "events_only",
            "replay_consistency": replay_consistency,
        }


def _build_replay_consistency_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    run = snapshot.get("run") or {}
    events = list(snapshot.get("events") or [])
    derived_status = "queued"
    derived_node_statuses: dict[str, str] = {}
    issues: list[dict[str, Any]] = []

    for event in events:
        event_type = str(event.get("type") or "")
        node_id = str(event.get("node_id") or "").strip()
        if event_type == "run.running":
            derived_status = "running"
        elif event_type == "run.succeeded":
            derived_status = "succeeded"
        elif event_type == "run.failed":
            derived_status = "failed"
        elif event_type == "node.running" and node_id:
            derived_node_statuses[node_id] = "running"
        elif event_type == "node.succeeded" and node_id:
            derived_node_statuses[node_id] = "succeeded"
        elif event_type == "node.failed" and node_id:
            derived_node_statuses[node_id] = "failed"

    stored_status = str(run.get("status") or "queued")
    if stored_status != derived_status:
        issues.append(
            {
                "code": "run_status_mismatch",
                "message": f"stored run status '{stored_status}' does not match replayed status '{derived_status}'",
                "details": {"stored_status": stored_status, "replayed_status": derived_status},
            }
        )

    stored_node_statuses = dict(run.get("node_statuses") or {})
    for node_id in sorted(set(stored_node_statuses) | set(derived_node_statuses)):
        stored_node_status = str(stored_node_statuses.get(node_id) or "")
        derived_node_status = str(derived_node_statuses.get(node_id) or "")
        if stored_node_status != derived_node_status:
            issues.append(
                {
                    "code": "node_status_mismatch",
                    "message": f"stored node status for '{node_id}' does not match replayed status",
                    "details": {
                        "node_id": node_id,
                        "stored_status": stored_node_status,
                        "replayed_status": derived_node_status,
                    },
                }
            )

    return {
        "contract_version": "workflow_graph.replay_consistency.v1",
        "consistent": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "stored_status": stored_status,
        "replayed_status": derived_status,
    }


compiler = WorkflowGraphCompilerService()
runtime = WorkflowGraphRuntimeService()
curated = WorkflowGraphCuratedService()

__all__ = [
    "compiler",
    "runtime",
    "curated",
    "WorkflowGraphCompilerService",
    "WorkflowGraphRuntimeService",
    "WorkflowGraphCuratedService",
]
