from __future__ import annotations

from typing import Any

from .contracts import build_workflow_graph_integrity_report
from .executors.base import BaseNodeExecutor, NodeExecutionContext
from .executors.join import JoinExecutor
from .executors.llm_call import LLMCallExecutor
from .executors.vector_search import VectorSearchExecutor
from .store import InMemoryRunStore, SqlRunStore


class WorkflowGraphRuntime:
    def __init__(
        self,
        *,
        store: InMemoryRunStore | SqlRunStore | None = None,
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
        integrity = _build_runtime_integrity_report(workflow=workflow, nodes=nodes, topo_order=topo_order)

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

        if not integrity["valid"]:
            self.store.set_run_status(resolved_run_id, "failed")
            self.store.append_event(
                resolved_run_id,
                event_type="run.failed",
                payload={
                    "reason_code": "workflow_integrity_failed",
                    "reason": "workflow graph integrity check failed",
                    "integrity": integrity,
                },
            )
            return self.store.snapshot(resolved_run_id)

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
        resolved_inputs = _resolve_node_inputs(
            node=node,
            runtime_inputs=inputs,
            all_results=all_results,
            upstream_results=upstream_results,
        )
        io_trace = _build_input_trace(
            node=node,
            runtime_inputs=inputs,
            all_results=all_results,
            upstream_results=upstream_results,
        )

        ctx = NodeExecutionContext(
            run_id=run_id,
            node_id=node_id,
            workflow=workflow,
            inputs=resolved_inputs,
            input_trace=io_trace,
            results=all_results,
            upstream_results=upstream_results,
        )
        result = executor.execute(node, ctx)
        return _normalize_node_result(
            node_id=node_id,
            node_type=node_type,
            result=result,
            io_trace=io_trace,
        )


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


def _build_runtime_integrity_report(
    *,
    workflow: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    topo_order: list[str],
) -> dict[str, Any]:
    edges: list[tuple[str, str]] = []
    for node_id, node in nodes.items():
        depends_on = node.get("depends_on") or []
        for upstream in depends_on:
            upstream_id = str(upstream or "").strip()
            if upstream_id:
                edges.append((upstream_id, node_id))
    report = build_workflow_graph_integrity_report(
        node_ids=list(nodes.keys()),
        edges=edges,
        topo_order=topo_order,
    )
    return {
        "contract_version": report.contract_version,
        "valid": report.valid,
        "issue_count": report.issue_count,
        "issues": [
            {"code": issue.code, "message": issue.message, "details": dict(issue.details)}
            for issue in report.issues
        ],
        "workflow_id": workflow.get("workflow_id"),
    }


def _resolve_node_inputs(
    *,
    node: dict[str, Any],
    runtime_inputs: dict[str, Any],
    all_results: dict[str, Any],
    upstream_results: dict[str, Any],
) -> dict[str, Any]:
    params = node.get("params")
    if not isinstance(params, dict):
        return dict(runtime_inputs)

    input_vars = params.get("input_vars")
    if not isinstance(input_vars, list):
        return dict(runtime_inputs)

    resolved = dict(runtime_inputs)
    for item in input_vars:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        source = str(item.get("source") or "input").strip().lower()
        default_value = item.get("default_value")
        required = bool(item.get("required"))
        value = _resolve_input_value(
            item=item,
            source=source,
            runtime_inputs=runtime_inputs,
            all_results=all_results,
            upstream_results=upstream_results,
        )
        if value is None and default_value is not None and str(default_value).strip():
            value = default_value
        if value is None and required:
            raise ValueError(f"required input missing: {name}")
        if value is not None:
            resolved[name] = value
    return resolved


def _resolve_input_value(
    *,
    item: dict[str, Any],
    source: str,
    runtime_inputs: dict[str, Any],
    all_results: dict[str, Any],
    upstream_results: dict[str, Any],
) -> Any:
    if source == "constant":
        return item.get("default_value")

    if source == "node_output":
        from_node = str(item.get("from_node") or "").strip()
        from_key = str(item.get("from_key") or "").strip()
        node_data = upstream_results.get(from_node) or all_results.get(from_node)
        if node_data is None:
            return None
        if not from_key:
            return node_data
        if isinstance(node_data, dict):
            return node_data.get(from_key)
        return None
    if source == "expression":
        expr = str(item.get("expr") or item.get("default_value") or "").strip()
        return _evaluate_expression(
            expr=expr,
            runtime_inputs=runtime_inputs,
            all_results=all_results,
            upstream_results=upstream_results,
        )

    # input/context both read from runtime scope first; this keeps legacy behavior
    name = str(item.get("name") or "").strip()
    if name:
        return runtime_inputs.get(name)
    return None


def _build_input_trace(
    *,
    node: dict[str, Any],
    runtime_inputs: dict[str, Any],
    all_results: dict[str, Any],
    upstream_results: dict[str, Any],
) -> dict[str, Any]:
    params = node.get("params")
    if not isinstance(params, dict):
        return {}
    input_vars = params.get("input_vars")
    if not isinstance(input_vars, list):
        return {}
    trace: dict[str, Any] = {}
    for item in input_vars:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        source = str(item.get("source") or "input").strip().lower()
        value = _resolve_input_value(
            item=item,
            source=source,
            runtime_inputs=runtime_inputs,
            all_results=all_results,
            upstream_results=upstream_results,
        )
        if value is None and item.get("default_value") not in (None, ""):
            value = item.get("default_value")
        trace[name] = {
            "source": source,
            "from_node": item.get("from_node"),
            "from_key": item.get("from_key"),
            "expr": item.get("expr"),
            "resolved": value,
            "resolved_type": type(value).__name__ if value is not None else "none",
        }
    return trace


def _evaluate_expression(
    *,
    expr: str,
    runtime_inputs: dict[str, Any],
    all_results: dict[str, Any],
    upstream_results: dict[str, Any],
) -> Any:
    text = expr.strip()
    if not text:
        return None
    if text.startswith("={{") and text.endswith("}}"):
        text = text[3:-2].strip()
    if text.startswith("$input."):
        return runtime_inputs.get(text[len("$input."):])
    if text.startswith("$context."):
        return runtime_inputs.get(text[len("$context."):])
    if text.startswith("$node."):
        parts = text.split(".")
        if len(parts) >= 3:
            node_id = parts[1]
            key = ".".join(parts[2:])
            payload = upstream_results.get(node_id) or all_results.get(node_id)
            if isinstance(payload, dict):
                return payload.get(key)
            return None
    return runtime_inputs.get(text)


def _normalize_node_result(
    *,
    node_id: str,
    node_type: str,
    result: Any,
    io_trace: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(result, dict):
        out = dict(result)
        if "data" not in out:
            out["data"] = dict(result)
        out.setdefault("error", None)
        meta = out.get("meta")
        if not isinstance(meta, dict):
            meta = {}
        meta.setdefault("node_id", node_id)
        meta.setdefault("node_type", node_type)
        out["meta"] = meta
        out.setdefault("io_trace", io_trace)
        return out

    return {
        "value": result,
        "data": {"value": result},
        "error": None,
        "meta": {"node_id": node_id, "node_type": node_type},
        "io_trace": io_trace,
    }
