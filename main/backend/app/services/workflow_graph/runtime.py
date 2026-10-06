from __future__ import annotations

from typing import NoReturn, TypeGuard

from functorial_kit import Failure

from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.language.program import ProgramSpec
from app.successor_runtime.language.transforms import TransformRegistry
from app.successor_runtime.runtime.activation import BoundStepValue, activate_plan_result

from .contracts import (
    WorkflowGraphCompileError,
    WorkflowIntegrityIssueValue,
    WorkflowIntegrityReportValue,
    WorkflowJsonObject,
    WorkflowJsonValue,
    WorkflowNodeResult,
    WorkflowNodeResults,
    WorkflowRuntimeGraph,
    WorkflowRuntimeNode,
    WorkflowRunSnapshot,
    build_workflow_graph_integrity_report,
    raise_workflow_graph_legacy,
    workflow_graph_failure,
)
from .executors.kernel import WorkflowNodeType
from .executors.kernel import NodeExecutionContext, execute_node, to_workflow_graph_failure
from .schema import try_parse_workflow_json_object
from .store import InMemoryRunStore, SqlRunStore


class WorkflowGraphPlatformInterpreter:
    """Interpret one exact Program/Plan against its typed workflow projection."""

    def __init__(self, *, store: InMemoryRunStore | SqlRunStore | None = None) -> None:
        self.store = store or InMemoryRunStore()

    def run(
        self,
        *,
        program: ProgramSpec,
        plan: ExecutionPlan,
        workflow: WorkflowRuntimeGraph,
        inputs: WorkflowJsonObject | None = None,
        run_id: str | None = None,
        project_key: str | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
    ) -> WorkflowRunSnapshot:
        nodes = _normalize_nodes(workflow.get("nodes"))
        topo_order = _resolve_topo_order(workflow=workflow, nodes=nodes)
        integrity = _build_runtime_integrity_report(
            workflow=workflow,
            nodes=nodes,
            topo_order=topo_order,
        )
        metadata: WorkflowJsonObject = {
            "workflow_id": workflow.get("workflow_id"),
            "project_key": str(project_key or "").strip() or None,
            "trace_id": str(trace_id or "").strip() or None,
            "session_id": str(session_id or "").strip() or None,
            "program_digest": workflow.get("program_digest"),
            "plan_digest": workflow.get("plan_digest"),
        }
        resolved_run_id = self.store.create_run(
            run_id=run_id,
            topo_order=topo_order,
            metadata=metadata,
        )
        topo_values: list[WorkflowJsonValue] = list(topo_order)
        queued_payload: WorkflowJsonObject = {
            "topo_order": topo_values,
            "program_digest": workflow.get("program_digest"),
            "plan_digest": workflow.get("plan_digest"),
        }
        self.store.append_event(resolved_run_id, event_type="run.queued", payload=queued_payload)
        self.store.set_run_status(resolved_run_id, "running")
        self.store.append_event(resolved_run_id, event_type="run.running")

        if not integrity["valid"]:
            integrity_payload = _json_object(integrity) or {}
            return self._fail_run(
                resolved_run_id,
                payload={
                    "reason_code": "workflow_integrity_failed",
                    "reason": "workflow graph integrity check failed",
                    "integrity": integrity_payload,
                },
            )

        completed: tuple[BoundStepValue, ...] = ()
        run_inputs = dict(inputs or {})
        registries = (
            TransformRegistry(registry_id="workflow.transforms"),
            TransformRegistry(registry_id="workflow.merges"),
            TransformRegistry(registry_id="workflow.discriminators"),
        )
        while True:
            activation_result = activate_plan_result(
                run_id=resolved_run_id,
                program=program,
                plan=plan,
                completed_outputs=completed,
                transform_registry=registries[0],
                merge_registry=registries[1],
                discriminator_registry=registries[2],
            )
            if isinstance(activation_result, Failure):
                return self._fail_run(
                    resolved_run_id,
                    payload={
                        "reason_code": "workflow_activation_failed",
                        "reason": str(activation_result.message),
                    },
                )
            if not activation_result.activations:
                break

            for activation in activation_result.activations:
                node_id = _node_id_from_payload_ref(activation.payload_ref.value_id)
                node = nodes.get(node_id)
                if activation.step_kind != "EFFECT" or node is None:
                    return self._fail_run(
                        resolved_run_id,
                        payload={
                            "reason_code": "workflow_activation_binding_invalid",
                            "reason": f"activation is not a known workflow node: {node_id}",
                            "step_id": activation.step_id,
                        },
                    )

                self.store.ensure_node(resolved_run_id, node_id)
                self.store.set_node_status(resolved_run_id, node_id, "running")
                self.store.append_event(
                    resolved_run_id,
                    event_type="node.running",
                    node_id=node_id,
                    payload={"activation_digest": activation.activation_digest},
                )
                try:
                    result = self._execute_node(
                        node=node,
                        run_id=resolved_run_id,
                        inputs=run_inputs,
                    )
                except Exception as exc:  # noqa: BLE001
                    self._fail_node_and_run(resolved_run_id, node_id, exc)
                    return self.store.snapshot(resolved_run_id)

                self.store.set_node_result(resolved_run_id, node_id, result)
                self.store.set_node_status(resolved_run_id, node_id, "succeeded")
                self.store.append_event(
                    resolved_run_id,
                    event_type="node.succeeded",
                    node_id=node_id,
                )
                completed = completed + (
                    BoundStepValue(activation.step_id, activation.payload_ref, result),
                )

        self.store.set_run_status(resolved_run_id, "succeeded")
        self.store.append_event(resolved_run_id, event_type="run.succeeded")
        return self.store.snapshot(resolved_run_id)

    def _execute_node(
        self,
        *,
        node: WorkflowRuntimeNode,
        run_id: str,
        inputs: WorkflowJsonObject,
    ) -> WorkflowNodeResult:
        node_id = node["id"].strip()
        node_type = _node_type(node["node_type"])
        all_results = self.store.get_results(run_id)
        upstream_results: WorkflowJsonObject = {}
        for upstream_id in node["depends_on"]:
            upstream_result = all_results.get(upstream_id)
            if upstream_result is not None:
                upstream_results[upstream_id] = upstream_result
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
        context = NodeExecutionContext(
            node_id=node_id,
            node_type=node_type,
            params=node["params"],
            inputs=resolved_inputs,
            input_trace=io_trace,
            upstream_results=upstream_results,
            correlation_id=run_id,
        )
        effect = execute_node(context)
        if effect.status == "FAILED" and effect.failure is not None:
            failure = to_workflow_graph_failure(effect)
            if failure is not None:
                raise_workflow_graph_legacy(failure, exception_type=WorkflowGraphCompileError)
        return _normalize_node_result(
            node_id=node_id,
            node_type=node_type,
            result=effect.legacy_payload,
            io_trace=io_trace,
        )

    def _fail_run(self, run_id: str, *, payload: WorkflowJsonObject) -> WorkflowRunSnapshot:
        self.store.set_run_status(run_id, "failed")
        self.store.append_event(run_id, event_type="run.failed", payload=payload)
        return self.store.snapshot(run_id)

    def _fail_node_and_run(self, run_id: str, node_id: str, exc: Exception) -> None:
        self.store.set_node_status(run_id, node_id, "failed")
        self.store.set_run_status(run_id, "failed")
        failure_fields = _exception_failure_fields(exc)
        error_payload: WorkflowJsonObject = {"error": str(exc)}
        error_payload.update(failure_fields)
        self.store.append_event(
            run_id,
            event_type="node.failed",
            node_id=node_id,
            payload=error_payload,
        )
        run_payload: WorkflowJsonObject = {"node_id": node_id}
        run_payload.update(error_payload)
        self.store.append_event(run_id, event_type="run.failed", payload=run_payload)


def _raise_contract(message: str) -> NoReturn:
    raise_workflow_graph_legacy(
        workflow_graph_failure(
            "contract_invalid",
            message,
            owner="workflow_graph.platform_interpreter",
            public_exception=WorkflowGraphCompileError,
            public_message=message,
            field="workflow",
            index=-1,
        )
    )


def _node_id_from_payload_ref(value_id: str) -> str:
    prefix = ":node:"
    suffix = ":payload"
    if prefix not in value_id or not value_id.endswith(suffix):
        return ""
    return value_id.split(prefix, 1)[1][: -len(suffix)]


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _json_object(value: object) -> WorkflowJsonObject | None:
    parsed = try_parse_workflow_json_object(value, field="runtime")
    return None if isinstance(parsed, Failure) else parsed


def _json_list(value: object) -> list[object] | None:
    return value if _is_object_list(value) else None


def _node_type(value: object) -> WorkflowNodeType:
    normalized = str(value or "").strip().lower()
    if normalized == "vector_search":
        return "vector_search"
    if normalized == "llm_call":
        return "llm_call"
    if normalized == "join":
        return "join"
    _raise_contract(f"unsupported workflow node_type: {normalized or '<missing>'}")


def _exception_failure_fields(exc: Exception) -> WorkflowJsonObject:
    candidate: object = getattr(exc, "workflow_failure", None)
    if not isinstance(candidate, Failure):
        return {}
    context = _json_object(candidate.context) or {}
    return {
        "failure_family": str(candidate.family),
        "failure_code": str(candidate.code),
        "failure_context": context,
    }


def _normalize_nodes(nodes: object) -> dict[str, WorkflowRuntimeNode]:
    normalized_nodes = _json_object(nodes)
    if normalized_nodes is not None:
        out: dict[str, WorkflowRuntimeNode] = {}
        for node_id, raw_node in normalized_nodes.items():
            data = _json_object(raw_node)
            if data is None:
                _raise_contract(f"workflow node '{node_id}' must be an object")
            out[node_id] = _runtime_node(data, fallback_id=node_id)
        return out
    node_items = _json_list(nodes)
    if node_items is not None:
        out = {}
        for raw_node in node_items:
            data = _json_object(raw_node)
            if data is None:
                _raise_contract("workflow node must be an object")
            node = _runtime_node(data)
            out[node["id"]] = node
        return out
    _raise_contract("workflow.nodes must be dict or list")


def _runtime_node(data: WorkflowJsonObject, *, fallback_id: str = "") -> WorkflowRuntimeNode:
    raw_id = data.get("id")
    node_id = (raw_id if isinstance(raw_id, str) else fallback_id).strip()
    raw_type = data.get("node_type")
    node_type = raw_type.strip() if isinstance(raw_type, str) else ""
    params = _json_object(data.get("params")) or {}
    depends_raw = _json_list(data.get("depends_on")) or []
    depends_on = [item.strip() for item in depends_raw if isinstance(item, str) and item.strip()]
    if not node_id:
        _raise_contract("node id is required")
    if not node_type:
        _raise_contract(f"node_type missing: {node_id}")
    return {"id": node_id, "node_type": node_type, "params": params, "depends_on": depends_on}


def _resolve_topo_order(
    *,
    workflow: WorkflowRuntimeGraph,
    nodes: dict[str, WorkflowRuntimeNode],
) -> list[str]:
    topo = [item.strip() for item in workflow.get("topo_order", []) if item.strip()]
    return topo or list(nodes.keys())


def _build_runtime_integrity_report(
    *,
    workflow: WorkflowRuntimeGraph,
    nodes: dict[str, WorkflowRuntimeNode],
    topo_order: list[str],
) -> WorkflowIntegrityReportValue:
    edges: list[tuple[str, str]] = []
    for node_id, node in nodes.items():
        edges.extend((upstream_id, node_id) for upstream_id in node["depends_on"])
    report = build_workflow_graph_integrity_report(
        node_ids=list(nodes.keys()),
        edges=edges,
        topo_order=topo_order,
    )
    issues: list[WorkflowIntegrityIssueValue] = [
        {"code": issue.code, "message": issue.message, "details": dict(issue.details)}
        for issue in report.issues
    ]
    return {
        "contract_version": report.contract_version,
        "valid": report.valid,
        "issue_count": report.issue_count,
        "issues": issues,
        "workflow_id": workflow.get("workflow_id"),
    }


def _resolve_node_inputs(
    *,
    node: WorkflowRuntimeNode,
    runtime_inputs: WorkflowJsonObject,
    all_results: WorkflowNodeResults,
    upstream_results: WorkflowJsonObject,
) -> WorkflowJsonObject:
    input_vars = _json_list(node["params"].get("input_vars"))
    if input_vars is None:
        return dict(runtime_inputs)

    resolved = dict(runtime_inputs)
    for raw_item in input_vars:
        item = _json_object(raw_item)
        if item is None:
            continue
        raw_name = item.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name:
            continue
        raw_source = item.get("source")
        source = raw_source.strip().lower() if isinstance(raw_source, str) else "input"
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
            message = f"required input missing: {name}"
            raise_workflow_graph_legacy(
                workflow_graph_failure(
                    "required_input_missing",
                    message,
                    owner="workflow_graph.platform_interpreter",
                    public_exception=WorkflowGraphCompileError,
                    public_message=message,
                    field="input",
                    index=-1,
                    name=name,
                )
            )
        if value is not None:
            resolved[name] = value
    return resolved


def _resolve_input_value(
    *,
    item: WorkflowJsonObject,
    source: str,
    runtime_inputs: WorkflowJsonObject,
    all_results: WorkflowNodeResults,
    upstream_results: WorkflowJsonObject,
) -> WorkflowJsonValue:
    if source == "constant":
        return item.get("default_value")
    if source == "node_output":
        raw_from_node = item.get("from_node")
        raw_from_key = item.get("from_key")
        from_node = raw_from_node.strip() if isinstance(raw_from_node, str) else ""
        from_key = raw_from_key.strip() if isinstance(raw_from_key, str) else ""
        node_data: WorkflowJsonValue = upstream_results.get(from_node)
        if node_data is None:
            node_data = all_results.get(from_node)
        if node_data is None:
            return None
        if not from_key:
            return node_data
        return node_data.get(from_key) if isinstance(node_data, dict) else None
    if source == "expression":
        raw_expr = item.get("expr") or item.get("default_value") or ""
        return _evaluate_expression(
            expr=raw_expr if isinstance(raw_expr, str) else "",
            runtime_inputs=runtime_inputs,
            all_results=all_results,
            upstream_results=upstream_results,
        )
    raw_name = item.get("name")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    return runtime_inputs.get(name) if name else None


def _build_input_trace(
    *,
    node: WorkflowRuntimeNode,
    runtime_inputs: WorkflowJsonObject,
    all_results: WorkflowNodeResults,
    upstream_results: WorkflowJsonObject,
) -> WorkflowJsonObject:
    input_vars = _json_list(node["params"].get("input_vars"))
    if input_vars is None:
        return {}
    trace: WorkflowJsonObject = {}
    for raw_item in input_vars:
        item = _json_object(raw_item)
        if item is None:
            continue
        raw_name = item.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name:
            continue
        raw_source = item.get("source")
        source = raw_source.strip().lower() if isinstance(raw_source, str) else "input"
        value = _resolve_input_value(
            item=item,
            source=source,
            runtime_inputs=runtime_inputs,
            all_results=all_results,
            upstream_results=upstream_results,
        )
        default_value = item.get("default_value")
        if value is None and default_value not in (None, ""):
            value = default_value
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
    runtime_inputs: WorkflowJsonObject,
    all_results: WorkflowNodeResults,
    upstream_results: WorkflowJsonObject,
) -> WorkflowJsonValue:
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
            node_data = upstream_results.get(parts[1]) or all_results.get(parts[1])
            if isinstance(node_data, dict):
                return node_data.get(".".join(parts[2:]))
            return None
    return runtime_inputs.get(text)


def _normalize_node_result(
    *,
    node_id: str,
    node_type: WorkflowNodeType,
    result: WorkflowJsonObject,
    io_trace: WorkflowJsonObject,
) -> WorkflowNodeResult:
    out = dict(result)
    out.setdefault("data", dict(result))
    out.setdefault("error", None)
    meta = _json_object(out.get("meta")) or {}
    meta.setdefault("node_id", node_id)
    meta.setdefault("node_type", node_type)
    out["meta"] = meta
    out.setdefault("io_trace", io_trace)
    return out
