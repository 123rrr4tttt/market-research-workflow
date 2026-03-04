from __future__ import annotations

from dataclasses import asdict
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4

from .compiler import compile_workflow_graph
from .runtime import WorkflowGraphRuntime


class WorkflowGraphCompilerService:
    """Compiler facade with in-memory compiled graph registry."""

    def __init__(self) -> None:
        self._compiled: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def compile(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        dsl_payload = payload.get("dsl") if isinstance(payload, Mapping) else payload
        if not isinstance(dsl_payload, Mapping):
            raise ValueError("dsl payload must be a mapping")

        compiled = compile_workflow_graph(dsl_payload)
        raw_graph_id = payload.get("graph_id") if isinstance(payload, Mapping) else None
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
        return {
            "graph_id": graph_id,
            "version": compiled.version,
            "checksum": compiled.checksum,
            "topo_order": list(compiled.topo_order),
            "warnings": [],
        }

    def get_compiled(self, graph_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._compiled.get(str(graph_id))
        if row is None:
            raise KeyError(f"compiled graph not found: {graph_id}")
        return row


class WorkflowGraphRuntimeService:
    """Runtime facade that executes compiled workflow graphs."""

    def __init__(self) -> None:
        self._engine = WorkflowGraphRuntime()

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


compiler = WorkflowGraphCompilerService()
runtime = WorkflowGraphRuntimeService()

__all__ = [
    "compiler",
    "runtime",
    "WorkflowGraphCompilerService",
    "WorkflowGraphRuntimeService",
]
