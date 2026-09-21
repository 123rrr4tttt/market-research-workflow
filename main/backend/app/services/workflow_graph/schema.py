from __future__ import annotations

from typing import Any, Mapping

from functorial_kit import Failure

from app.services.workflow_graph.contracts import (
    WorkflowEdge,
    WorkflowGraphCompileError,
    WorkflowGraphDSL,
    WorkflowNode,
    raise_workflow_graph_legacy,
    workflow_graph_failure,
)


def _schema_failure(message: str, *, index: int, field: str) -> Failure:
    return workflow_graph_failure(
        "contract_invalid",
        message,
        owner="workflow_graph.schema",
        public_exception=WorkflowGraphCompileError,
        public_message=message,
        index=index,
        field=field,
    )


def try_parse_workflow_graph_dsl(payload: Mapping[str, Any]) -> WorkflowGraphDSL | Failure:
    if not isinstance(payload, Mapping):
        return _schema_failure("workflow graph dsl must be a mapping", index=-1, field="dsl")

    version = payload.get("version", "1.0")
    if not isinstance(version, str) or not version.strip():
        return _schema_failure("version must be a non-empty string", index=-1, field="version")

    options_raw = payload.get("options", {})
    if not isinstance(options_raw, Mapping):
        return _schema_failure("options must be a mapping", index=-1, field="options")

    nodes_raw = payload.get("nodes", [])
    if not isinstance(nodes_raw, list):
        return _schema_failure("nodes must be a list", index=-1, field="nodes")

    edges_raw = payload.get("edges", [])
    if not isinstance(edges_raw, list):
        return _schema_failure("edges must be a list", index=-1, field="edges")

    nodes: list[WorkflowNode] = []
    for idx, item in enumerate(nodes_raw):
        if not isinstance(item, Mapping):
            return _schema_failure(f"node at index {idx} must be a mapping", index=idx, field="nodes")
        node_id = item.get("node_id") or item.get("id")
        node_type = item.get("node_type")
        config = item.get("config")
        if config is None:
            config = item.get("params", {})

        if not isinstance(node_id, str) or not node_id.strip():
            return _schema_failure(f"node_id at index {idx} must be a non-empty string", index=idx, field="node_id")
        if not isinstance(node_type, str) or not node_type.strip():
            return _schema_failure(f"node_type at index {idx} must be a non-empty string", index=idx, field="node_type")
        if not isinstance(config, Mapping):
            return _schema_failure(f"config for node '{node_id}' must be a mapping", index=idx, field="config")

        nodes.append(
            WorkflowNode(
                node_id=node_id,
                node_type=node_type,
                config=dict(config),
            )
        )

    edges: list[WorkflowEdge] = []
    for idx, item in enumerate(edges_raw):
        if not isinstance(item, Mapping):
            return _schema_failure(f"edge at index {idx} must be a mapping", index=idx, field="edges")
        from_node = item.get("from") or item.get("from_node") or item.get("source")
        to_node = item.get("to") or item.get("to_node") or item.get("target")

        if not isinstance(from_node, str) or not from_node.strip():
            return _schema_failure(f"edge.from at index {idx} must be a non-empty string", index=idx, field="edge.from")
        if not isinstance(to_node, str) or not to_node.strip():
            return _schema_failure(f"edge.to at index {idx} must be a non-empty string", index=idx, field="edge.to")

        edges.append(WorkflowEdge(from_node=from_node, to_node=to_node))

    return WorkflowGraphDSL(
        version=version,
        options=dict(options_raw),
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


def parse_workflow_graph_dsl(payload: Mapping[str, Any]) -> WorkflowGraphDSL:
    result = try_parse_workflow_graph_dsl(payload)
    if isinstance(result, Failure):
        raise_workflow_graph_legacy(result, exception_type=WorkflowGraphCompileError)
    return result
