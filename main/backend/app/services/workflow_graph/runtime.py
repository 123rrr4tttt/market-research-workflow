from __future__ import annotations

from typing import Any

from .executors.base import BaseNodeExecutor, NodeExecutionContext
from .executors.join import JoinExecutor
from .executors.llm_call import LLMCallExecutor
from .executors.vector_search import VectorSearchExecutor
from .store import InMemoryRunStore


class WorkflowGraphRuntime:
    def __init__(
        self,
        *,
        store: InMemoryRunStore | None = None,
        executors: list[BaseNodeExecutor] | None = None,
    ) -> None:
        self.store = store or InMemoryRunStore()
        self._executors: dict[str, BaseNodeExecutor] = {}
        for executor in (executors or [VectorSearchExecutor(), LLMCallExecutor(), JoinExecutor()]):
            self.register_executor(executor)

    def register_executor(self, executor: BaseNodeExecutor) -> None:
        if not executor.node_type:
            raise ValueError("executor.node_type must not be empty")
        self._executors[executor.node_type] = executor

    def run(
        self,
        workflow: dict[str, Any],
        *,
        inputs: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        nodes = _normalize_nodes(workflow.get("nodes") or {})
        topo_order = _resolve_topo_order(workflow=workflow, nodes=nodes)

        resolved_run_id = self.store.create_run(
            run_id=run_id,
            topo_order=topo_order,
            metadata={"workflow_id": workflow.get("workflow_id")},
        )
        self.store.append_event(
            resolved_run_id,
            event_type="run.queued",
            payload={"topo_order": topo_order},
        )
        self.store.set_run_status(resolved_run_id, "running")
        self.store.append_event(resolved_run_id, event_type="run.running")

        run_inputs = dict(inputs or {})

        for node_id in topo_order:
            node = nodes.get(node_id)
            if node is None:
                self.store.set_run_status(resolved_run_id, "failed")
                self.store.append_event(
                    resolved_run_id,
                    event_type="run.failed",
                    payload={"reason": f"node_missing_in_graph:{node_id}"},
                )
                return self.store.snapshot(resolved_run_id)

            self.store.ensure_node(resolved_run_id, node_id)
            self.store.set_node_status(resolved_run_id, node_id, "running")
            self.store.append_event(resolved_run_id, event_type="node.running", node_id=node_id)

            try:
                result = self._execute_node(
                    node=node,
                    run_id=resolved_run_id,
                    workflow=workflow,
                    inputs=run_inputs,
                )
                self.store.set_node_result(resolved_run_id, node_id, result)
                self.store.set_node_status(resolved_run_id, node_id, "succeeded")
                self.store.append_event(resolved_run_id, event_type="node.succeeded", node_id=node_id)
            except Exception as exc:  # noqa: BLE001
                self.store.set_node_status(resolved_run_id, node_id, "failed")
                self.store.set_run_status(resolved_run_id, "failed")
                self.store.append_event(
                    resolved_run_id,
                    event_type="node.failed",
                    node_id=node_id,
                    payload={"error": str(exc)},
                )
                self.store.append_event(
                    resolved_run_id,
                    event_type="run.failed",
                    payload={"node_id": node_id, "error": str(exc)},
                )
                return self.store.snapshot(resolved_run_id)

        self.store.set_run_status(resolved_run_id, "succeeded")
        self.store.append_event(resolved_run_id, event_type="run.succeeded")
        return self.store.snapshot(resolved_run_id)

    def _execute_node(
        self,
        *,
        node: dict[str, Any],
        run_id: str,
        workflow: dict[str, Any],
        inputs: dict[str, Any],
    ) -> Any:
        node_id = str(node.get("id") or "").strip()
        node_type = str(node.get("node_type") or "").strip().lower()
        if not node_type:
            raise ValueError(f"node_type missing: {node_id or '<unknown>'}")

        executor = self._executors.get(node_type)
        if executor is None:
            raise ValueError(f"unsupported node_type: {node_type}")

        all_results = self.store.get_results(run_id)
        upstream_node_ids = [str(x).strip() for x in (node.get("depends_on") or []) if str(x).strip()]
        upstream_results = {nid: all_results[nid] for nid in upstream_node_ids if nid in all_results}

        ctx = NodeExecutionContext(
            run_id=run_id,
            node_id=node_id,
            workflow=workflow,
            inputs=inputs,
            results=all_results,
            upstream_results=upstream_results,
        )
        return executor.execute(node, ctx)


def _normalize_nodes(nodes: Any) -> dict[str, dict[str, Any]]:
    if isinstance(nodes, dict):
        out: dict[str, dict[str, Any]] = {}
        for node_id, node_data in nodes.items():
            data = dict(node_data or {})
            data.setdefault("id", str(node_id))
            out[str(node_id)] = data
        return out

    if isinstance(nodes, list):
        out = {}
        for node in nodes:
            data = dict(node or {})
            node_id = str(data.get("id") or "").strip()
            if not node_id:
                raise ValueError("node id is required")
            out[node_id] = data
        return out

    raise ValueError("workflow.nodes must be dict or list")


def _resolve_topo_order(*, workflow: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> list[str]:
    topo = [str(x).strip() for x in (workflow.get("topo_order") or []) if str(x).strip()]
    if topo:
        return topo
    return list(nodes.keys())
