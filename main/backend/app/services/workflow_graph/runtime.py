"""Typed workflow node kernel over the canonical durable runtime context.

The successor Runtime owns scheduling, persistence, retries, state transitions,
and readback. This module resolves one already-activated node occurrence and
invokes the existing node kernel exactly once.
"""

from __future__ import annotations

from typing import NoReturn, TypeGuard

from functorial_kit import Failure

from app.successor_runtime.capabilities.workflow_native_contribution import (
    WorkflowExecutionContext,
    advance_workflow_execution_context,
    validate_workflow_execution_context,
)

from .contracts import (
    WorkflowGraphCompileError,
    WorkflowJsonObject,
    WorkflowJsonValue,
    WorkflowNodeResult,
    WorkflowNodeResults,
    WorkflowRuntimeNode,
    raise_workflow_graph_legacy,
    workflow_graph_failure,
)
from .executors.kernel import (
    NodeExecutionContext,
    WorkflowNodeType,
    execute_node,
    to_workflow_graph_failure,
)
from .schema import try_parse_workflow_json_object


class WorkflowNodeSettledFailure(WorkflowGraphCompileError):
    """A kernel-declared failure whose external effect is known to be settled."""

    @property
    def failure_code(self) -> str:
        failure = getattr(self, "workflow_failure", None)
        if isinstance(failure, Failure):
            return str(failure.code)
        return "workflow_node_failed"


def invoke_workflow_runtime_node(
    context: WorkflowExecutionContext,
) -> WorkflowExecutionContext:
    """Execute the current occurrence and transport its typed result once."""

    declaration = validate_workflow_execution_context(context)
    node_id = str(declaration["node_id"])
    node_type = _node_type(declaration["node_type"])
    params = _json_object(declaration.get("params")) or {}
    depends_raw = _json_list(declaration.get("depends_on")) or []
    node: WorkflowRuntimeNode = {
        "id": node_id,
        "node_type": node_type,
        "params": params,
        "depends_on": [
            value.strip()
            for value in depends_raw
            if isinstance(value, str) and value.strip()
        ],
    }
    all_results: WorkflowNodeResults = {}
    for result_node_id, raw_result in context.results.items():
        result = _json_object(raw_result)
        if result is None:
            _raise_contract(f"workflow result '{result_node_id}' must be an object")
        all_results[result_node_id] = result
    upstream_results: WorkflowJsonObject = {
        upstream_id: all_results[upstream_id]
        for upstream_id in node["depends_on"]
        if upstream_id in all_results
    }
    resolved_inputs = _resolve_node_inputs(
        node=node,
        runtime_inputs=context.inputs,
        all_results=all_results,
        upstream_results=upstream_results,
    )
    io_trace = _build_input_trace(
        node=node,
        runtime_inputs=context.inputs,
        all_results=all_results,
        upstream_results=upstream_results,
    )
    effect = execute_node(
        NodeExecutionContext(
            node_id=node_id,
            node_type=node_type,
            params=params,
            inputs=resolved_inputs,
            input_trace=io_trace,
            upstream_results=upstream_results,
            correlation_id=context.trace_id,
        )
    )
    if effect.status == "FAILED":
        failure = to_workflow_graph_failure(effect)
        if failure is None:
            _raise_contract(f"workflow node failed without a typed failure: {node_id}")
        settled_failure = Failure(
            family=failure.family,
            code=failure.code,
            message=failure.message,
            context={
                **dict(failure.context or {}),
                "public_exception": WorkflowNodeSettledFailure.__name__,
            },
        )
        raise_workflow_graph_legacy(
            settled_failure,
            exception_type=WorkflowNodeSettledFailure,
        )
    result = _normalize_node_result(
        node_id=node_id,
        node_type=node_type,
        result=effect.legacy_payload,
        io_trace=io_trace,
    )
    return advance_workflow_execution_context(
        context,
        node_id=node_id,
        result=result,
    )


def _raise_contract(message: str) -> NoReturn:
    raise_workflow_graph_legacy(
        workflow_graph_failure(
            "contract_invalid",
            message,
            owner="workflow_graph.runtime.kernel",
            public_exception=WorkflowGraphCompileError,
            public_message=message,
            field="workflow",
            index=-1,
        )
    )


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
                    owner="workflow_graph.runtime.kernel",
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
        return runtime_inputs.get(text[len("$input.") :])
    if text.startswith("$context."):
        return runtime_inputs.get(text[len("$context.") :])
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


__all__ = ["WorkflowNodeSettledFailure", "invoke_workflow_runtime_node"]
