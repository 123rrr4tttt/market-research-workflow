from __future__ import annotations

from dataclasses import asdict
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4

from .compiler import compile_workflow_graph
from .curated_service import WorkflowGraphCuratedService
from .runtime import WorkflowGraphRuntime
from .store import build_run_store
from .templates import WorkflowGraphTemplateService


class WorkflowGraphCompilerService:
    """Compiler facade with in-memory compiled graph registry."""

    def __init__(self) -> None:
        self._compiled: dict[str, dict[str, Any]] = {}
        self._lock = RLock()
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
            raise KeyError(f"compiled graph not found: {graph_id}")
        return row

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
        return {
            "run_id": run.get("run_id"),
            "status": run.get("status"),
            "node_statuses": run.get("node_statuses") or {},
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._engine.store.get_run(str(run_id))

    def get_run_events(self, run_id: str) -> dict[str, Any]:
        return {"items": self._engine.store.get_events(str(run_id))}

    def replay_run(self, run_id: str) -> dict[str, Any]:
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
