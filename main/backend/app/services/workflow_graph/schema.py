from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TypeGuard

from functorial_kit import Failure

from app.services.workflow_graph.contracts import (
    WorkflowEdge,
    WorkflowGraphCompileError,
    WorkflowGraphDSL,
    WorkflowJsonObject,
    WorkflowJsonValue,
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


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def try_parse_workflow_json_value(
    value: object,
    *,
    field: str,
    index: int = -1,
) -> WorkflowJsonValue | Failure:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return _schema_failure(f"{field} contains a non-finite number", index=index, field=field)
    if _is_object_mapping(value):
        normalized: WorkflowJsonObject = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                return _schema_failure(f"{field} keys must be strings", index=index, field=field)
            parsed = try_parse_workflow_json_value(raw_value, field=f"{field}.{raw_key}", index=index)
            if isinstance(parsed, Failure):
                return parsed
            normalized[raw_key] = parsed
        return normalized
    if _is_object_list(value):
        normalized_items: list[WorkflowJsonValue] = []
        for item_index, raw_item in enumerate(value):
            parsed = try_parse_workflow_json_value(raw_item, field=f"{field}[{item_index}]", index=index)
            if isinstance(parsed, Failure):
                return parsed
            normalized_items.append(parsed)
        return normalized_items
    return _schema_failure(
        f"{field} contains a non-JSON value of type {type(value).__name__}",
        index=index,
        field=field,
    )


def try_parse_workflow_json_object(
    value: object,
    *,
    field: str,
    index: int = -1,
) -> WorkflowJsonObject | Failure:
    parsed = try_parse_workflow_json_value(value, field=field, index=index)
    if isinstance(parsed, Failure):
        return parsed
    if not isinstance(parsed, dict):
        return _schema_failure(f"{field} must be a mapping", index=index, field=field)
    return parsed


def try_parse_workflow_graph_dsl(payload: object) -> WorkflowGraphDSL | Failure:
    normalized = try_parse_workflow_json_object(payload, field="dsl")
    if isinstance(normalized, Failure):
        return normalized

    version = normalized.get("version", "1.0")
    if not isinstance(version, str) or not version.strip():
        return _schema_failure("version must be a non-empty string", index=-1, field="version")

    options_raw = normalized.get("options", {})
    if not isinstance(options_raw, dict):
        return _schema_failure("options must be a mapping", index=-1, field="options")

    nodes_raw = normalized.get("nodes", [])
    if not isinstance(nodes_raw, list):
        return _schema_failure("nodes must be a list", index=-1, field="nodes")

    edges_raw = normalized.get("edges", [])
    if not isinstance(edges_raw, list):
        return _schema_failure("edges must be a list", index=-1, field="edges")

    nodes: list[WorkflowNode] = []
    for idx, item in enumerate(nodes_raw):
        if not isinstance(item, dict):
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
        if not isinstance(config, dict):
            return _schema_failure(f"config for node '{node_id}' must be a mapping", index=idx, field="config")

        nodes.append(WorkflowNode(node_id=node_id, node_type=node_type, config=config))

    edges: list[WorkflowEdge] = []
    for idx, item in enumerate(edges_raw):
        if not isinstance(item, dict):
            return _schema_failure(f"edge at index {idx} must be a mapping", index=idx, field="edges")
        from_node = (
            item.get("from_node_id")
            or item.get("from")
            or item.get("from_node")
            or item.get("source")
        )
        to_node = (
            item.get("to_node_id")
            or item.get("to")
            or item.get("to_node")
            or item.get("target")
        )

        if not isinstance(from_node, str) or not from_node.strip():
            return _schema_failure(f"edge.from at index {idx} must be a non-empty string", index=idx, field="edge.from")
        if not isinstance(to_node, str) or not to_node.strip():
            return _schema_failure(f"edge.to at index {idx} must be a non-empty string", index=idx, field="edge.to")
        edges.append(WorkflowEdge(from_node=from_node, to_node=to_node))

    return WorkflowGraphDSL(
        version=version,
        options=options_raw,
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


def parse_workflow_graph_dsl(payload: object) -> WorkflowGraphDSL:
    result = try_parse_workflow_graph_dsl(payload)
    if isinstance(result, Failure):
        raise_workflow_graph_legacy(result, exception_type=WorkflowGraphCompileError)
    return result
