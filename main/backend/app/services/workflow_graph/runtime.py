from __future__ import annotations

from collections.abc import Mapping, Set
from typing import Any, NoReturn, Protocol, runtime_checkable

from functorial_kit import Failure

from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.language.program import ProgramSpec
from app.successor_runtime.language.transforms import TransformRegistry
from app.successor_runtime.runtime.activation import (
    BoundStepValue,
    activate_plan_result,
)

from .contracts import (
    WorkflowGraphCompileError,
    build_workflow_graph_integrity_report,
    raise_workflow_graph_legacy,
    workflow_graph_failure,
)
from .executors.kernel import WorkflowNodeType
from .executors.kernel import NodeExecutionContext, execute_node, to_workflow_graph_failure
from .store import InMemoryRunStore, SqlRunStore


class WorkflowGraphPlatformInterpreter:
    """Run one bound Program/Plan through the shared activation interpreter."""

    def __init__(
        self,
        *,
        store: InMemoryRunStore | SqlRunStore | None = None,
    ) -> None:
        self.store = store or InMemoryRunStore()

    def run(
        self,
        *,
        program: ProgramSpec,
        plan: ExecutionPlan,
        workflow: dict[str, Any],
        inputs: dict[str, Any] | None = None,
        run_id: str | None = None,
        project_key: str | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        nodes = _normalize_nodes(workflow.get("nodes") or {})
        topo_order = _resolve_topo_order(workflow=workflow, nodes=nodes)
        integrity = _build_runtime_integrity_report(
            workflow=workflow,
            nodes=nodes,
            topo_order=topo_order,
        )
        resolved_run_id = self.store.create_run(
            run_id=run_id,
            topo_order=topo_order,
            metadata={
                "workflow_id": workflow.get("workflow_id"),
                "project_key": str(project_key or "").strip() or None,
                "trace_id": str(trace_id or "").strip() or None,
                "session_id": str(session_id or "").strip() or None,
                "program_digest": workflow.get("program_digest"),
                "plan_digest": workflow.get("plan_digest"),
            },
        )
        self.store.append_event(resolved_run_id, event_type="run.queued", payload={
            "topo_order": topo_order,
            "program_digest": workflow.get("program_digest"),
            "plan_digest": workflow.get("plan_digest"),
        })
        self.store.set_run_status(resolved_run_id, "running")
        self.store.append_event(resolved_run_id, event_type="run.running")

        if not integrity["valid"]:
            return self._fail_run(
                resolved_run_id,
                payload={
                    "reason_code": "workflow_integrity_failed",
                    "reason": "workflow graph integrity check failed",
                    "integrity": integrity,
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
                    return self._fail_run(resolved_run_id, payload={
                        "reason_code": "workflow_activation_binding_invalid",
                        "reason": f"activation is not a known workflow node: {node_id}",
                        "step_id": activation.step_id,
                    })

                self.store.ensure_node(resolved_run_id, node_id)
                self.store.set_node_status(resolved_run_id, node_id, "running")
                self.store.append_event(
                    resolved_run_id,
                    event_type="node.running",
                    node_id=node_id,
                    payload={"activation_digest": activation.activation_digest},
                )
                try:
                    result = self._execute_activation(
                        activation=activation,
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
                    BoundStepValue(
                        activation.step_id,
                        activation.payload_ref,
                        result,
                    ),
                )

        self.store.set_run_status(resolved_run_id, "succeeded")
        self.store.append_event(resolved_run_id, event_type="run.succeeded")
        return self.store.snapshot(resolved_run_id)

    def _execute_activation(
        self,
        *,
        activation: object,
        node: dict[str, Any],
        run_id: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        node_id = str(node.get("id") or "").strip()
        node_type = _node_type(node.get("node_type"))
        if not node_type:
            _raise_contract(f"node_type missing: {node_id or '<unknown>'}")

        all_results = self.store.get_results(run_id)
        upstream_ids = [str(x).strip() for x in _object_list(node.get("depends_on")) or [] if str(x).strip()]
        upstream_results = {nid: all_results[nid] for nid in upstream_ids if nid in all_results}
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
            params=dict(node.get("params") or {}),
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

    def _fail_run(self, run_id: str, *, payload: dict[str, Any]) -> dict[str, Any]:
        self.store.set_run_status(run_id, "failed")
        self.store.append_event(run_id, event_type="run.failed", payload=payload)
        return self.store.snapshot(run_id)

    def _fail_node_and_run(self, run_id: str, node_id: str, exc: Exception) -> None:
        self.store.set_node_status(run_id, node_id, "failed")
        self.store.set_run_status(run_id, "failed")
        failure_fields = _exception_failure_fields(exc)
        error_payload = {"error": str(exc), **failure_fields}
        self.store.append_event(
            run_id,
            event_type="node.failed",
            node_id=node_id,
            payload=error_payload,
        )
        self.store.append_event(
            run_id,
            event_type="run.failed",
            payload={"node_id": node_id, **error_payload},
        )


def _raise_contract(message: str) -> NoReturn:
    raise_workflow_graph_legacy(workflow_graph_failure(
        "contract_invalid",
        message,
        owner="workflow_graph.platform_interpreter",
        public_exception=WorkflowGraphCompileError,
        public_message=message,
        field="workflow",
        index=-1,
    ))


def _node_id_from_payload_ref(value_id: str) -> str:
    prefix = ":node:"
    suffix = ":payload"
    if prefix not in value_id or not value_id.endswith(suffix):
        return ""
    return value_id.split(prefix, 1)[1][: -len(suffix)]


@runtime_checkable
class _StringKeyMapping(Protocol):
    def keys(self) -> Set[str]: ...
    def __getitem__(self, key: str) -> Any: ...


@runtime_checkable
class _ObjectSequence(Protocol):
    def __len__(self) -> int: ...
    def __getitem__(self, index: int) -> object: ...


def _mapping(value: object) -> dict[str, Any] | None:
    if not isinstance(value, _StringKeyMapping):
        return None
    if not all(type(key) is str for key in value.keys()):
        return None
    return {key: value[key] for key in value.keys()}


def _object_list(value: object) -> list[object] | None:
    if not isinstance(value, _ObjectSequence):
        return None
    return [value[index] for index in range(len(value))]


def _object_dict(value: object) -> dict[str, Any] | None:
    return _mapping(value)


def _node_type(value: object) -> WorkflowNodeType:
    normalized = str(value or "").strip().lower()
    if normalized in {"vector_search", "llm_call", "join"}:
        if normalized == "vector_search":
            return "vector_search"
        if normalized == "llm_call":
            return "llm_call"
        return "join"
    _raise_contract(f"unsupported workflow node_type: {normalized or '<missing>'}")


def _exception_failure_fields(exc: Exception) -> dict[str, Any]:
    failure = getattr(exc, "workflow_failure", None)
    if failure is None or not getattr(failure, "failure", False):
        return {}
    family = getattr(failure, "family", "")
    code = getattr(failure, "code", "")
    raw_context = getattr(failure, "context", None)
    normalized_context = _mapping(raw_context)
    return {
        "failure_family": str(family),
        "failure_code": str(code),
        "failure_context": dict(normalized_context or {}),
    }


def _normalize_nodes(nodes: Any) -> dict[str, dict[str, Any]]:
    normalized_nodes = _object_dict(nodes)
    if normalized_nodes is not None:
        out: dict[str, dict[str, Any]] = {}
        for node_id, node_data in normalized_nodes.items():
            data = _object_dict(node_data) or {}
            data.setdefault("id", str(node_id))
            out[str(node_id)] = data
        return out
    node_items = _object_list(nodes)
    if node_items is not None:
        out = {}
        for node in node_items:
            data = _object_dict(node) or {}
            node_id = str(data.get("id") or "").strip()
            if not node_id:
                _raise_contract("node id is required")
            out[node_id] = data
        return out
    _raise_contract("workflow.nodes must be dict or list")


def _resolve_topo_order(
    *,
    workflow: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
) -> list[str]:
    topo_items = _object_list(workflow.get("topo_order")) or []
    topo = [str(item).strip() for item in topo_items if str(item).strip()]
    return topo or list(nodes.keys())


def _build_runtime_integrity_report(
    *,
    workflow: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    topo_order: list[str],
) -> dict[str, Any]:
    edges: list[tuple[str, str]] = []
    for node_id, node in nodes.items():
        for upstream in _object_list(node.get("depends_on")) or []:
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
    params = _object_dict(node.get("params"))
    if params is None:
        return dict(runtime_inputs)
    input_vars = _object_list(params.get("input_vars"))
    if input_vars is None:
        return dict(runtime_inputs)

    resolved = dict(runtime_inputs)
    for item in input_vars:
        input_item = _object_dict(item)
        if input_item is None:
            continue
        name = str(input_item.get("name") or "").strip()
        if not name:
            continue
        source = str(input_item.get("source") or "input").strip().lower()
        default_value = input_item.get("default_value")
        required = bool(input_item.get("required"))
        value = _resolve_input_value(
            item=input_item,
            source=source,
            runtime_inputs=runtime_inputs,
            all_results=all_results,
            upstream_results=upstream_results,
        )
        if value is None and default_value is not None and str(default_value).strip():
            value = default_value
        if value is None and required:
            message = f"required input missing: {name}"
            raise_workflow_graph_legacy(workflow_graph_failure(
                "required_input_missing", message,
                owner="workflow_graph.platform_interpreter",
                public_exception=WorkflowGraphCompileError,
                public_message=message,
                field="input", index=-1, name=name,
            ))
        if value is not None:
            resolved[name] = value
    return resolved


def _resolve_input_value(
    *,
    item: Mapping[str, object],
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
        node_payload = _object_dict(node_data)
        return node_payload.get(from_key) if node_payload is not None else None
    if source == "expression":
        expr = str(item.get("expr") or item.get("default_value") or "").strip()
        return _evaluate_expression(
            expr=expr,
            runtime_inputs=runtime_inputs,
            all_results=all_results,
            upstream_results=upstream_results,
        )
    name = str(item.get("name") or "").strip()
    return runtime_inputs.get(name) if name else None


def _build_input_trace(
    *,
    node: dict[str, Any],
    runtime_inputs: dict[str, Any],
    all_results: dict[str, Any],
    upstream_results: dict[str, Any],
) -> dict[str, Any]:
    params = _object_dict(node.get("params"))
    if params is None:
        return {}
    input_vars = _object_list(params.get("input_vars"))
    if input_vars is None:
        return {}
    trace: dict[str, Any] = {}
    for item in input_vars:
        input_item = _object_dict(item)
        if input_item is None:
            continue
        name = str(input_item.get("name") or "").strip()
        if not name:
            continue
        source = str(input_item.get("source") or "input").strip().lower()
        value = _resolve_input_value(
            item=input_item,
            source=source,
            runtime_inputs=runtime_inputs,
            all_results=all_results,
            upstream_results=upstream_results,
        )
        if value is None and input_item.get("default_value") not in (None, ""):
            value = input_item.get("default_value")
        trace[name] = {
            "source": source,
            "from_node": input_item.get("from_node"),
            "from_key": input_item.get("from_key"),
            "expr": input_item.get("expr"),
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
            payload = upstream_results.get(parts[1]) or all_results.get(parts[1])
            node_payload = _object_dict(payload)
            if node_payload is not None:
                return node_payload.get(".".join(parts[2:]))
            return None
    return runtime_inputs.get(text)


def _normalize_node_result(
    *,
    node_id: str,
    node_type: str,
    result: Any,
    io_trace: dict[str, Any],
) -> dict[str, Any]:
    node_result = _object_dict(result)
    if node_result is not None:
        out = dict(node_result)
        out.setdefault("data", dict(node_result))
        out.setdefault("error", None)
        meta = _object_dict(out.get("meta")) or {}
        meta.setdefault("node_id", node_id)
        meta.setdefault("node_type", node_type)
        out["meta"] = meta
        out.setdefault("io_trace", io_trace)
        return out
    return {
        "node_type": node_type,
        "data": result,
        "error": None,
        "meta": {"node_id": node_id, "node_type": node_type},
        "io_trace": io_trace,
    }
