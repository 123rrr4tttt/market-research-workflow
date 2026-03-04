from __future__ import annotations

from typing import Any, Mapping

from app.services.workflow_graph.contracts import (
    WorkflowEdge,
    WorkflowGraphCompileError,
    WorkflowGraphDSL,
    WorkflowNode,
)


def parse_workflow_graph_dsl(payload: Mapping[str, Any]) -> WorkflowGraphDSL:
    if not isinstance(payload, Mapping):
        raise WorkflowGraphCompileError("workflow graph dsl must be a mapping")

    version = payload.get("version", "1.0")
    if not isinstance(version, str) or not version.strip():
        raise WorkflowGraphCompileError("version must be a non-empty string")

    options_raw = payload.get("options", {})
    if not isinstance(options_raw, Mapping):
        raise WorkflowGraphCompileError("options must be a mapping")

    nodes_raw = payload.get("nodes", [])
    if not isinstance(nodes_raw, list):
        raise WorkflowGraphCompileError("nodes must be a list")

    edges_raw = payload.get("edges", [])
    if not isinstance(edges_raw, list):
        raise WorkflowGraphCompileError("edges must be a list")

    nodes: list[WorkflowNode] = []
    for idx, item in enumerate(nodes_raw):
        if not isinstance(item, Mapping):
            raise WorkflowGraphCompileError(f"node at index {idx} must be a mapping")
        node_id = item.get("node_id") or item.get("id")
        node_type = item.get("node_type")
        config = item.get("config")
        if config is None:
            config = item.get("params", {})

        if not isinstance(node_id, str) or not node_id.strip():
            raise WorkflowGraphCompileError(f"node_id at index {idx} must be a non-empty string")
        if not isinstance(node_type, str) or not node_type.strip():
            raise WorkflowGraphCompileError(f"node_type at index {idx} must be a non-empty string")
        if not isinstance(config, Mapping):
            raise WorkflowGraphCompileError(f"config for node '{node_id}' must be a mapping")

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
            raise WorkflowGraphCompileError(f"edge at index {idx} must be a mapping")
        from_node = item.get("from") or item.get("from_node") or item.get("source")
        to_node = item.get("to") or item.get("to_node") or item.get("target")

        if not isinstance(from_node, str) or not from_node.strip():
            raise WorkflowGraphCompileError(f"edge.from at index {idx} must be a non-empty string")
        if not isinstance(to_node, str) or not to_node.strip():
            raise WorkflowGraphCompileError(f"edge.to at index {idx} must be a non-empty string")

        edges.append(WorkflowEdge(from_node=from_node, to_node=to_node))

    return WorkflowGraphDSL(
        version=version,
        options=dict(options_raw),
        nodes=tuple(nodes),
        edges=tuple(edges),
    )
