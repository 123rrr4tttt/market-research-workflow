from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any, Mapping

from functorial_kit import Failure

from app.services.workflow_graph.contracts import (
    ALLOWED_NODE_TYPES,
    CompiledWorkflowGraph,
    WorkflowGraphCompileError,
    WorkflowGraphDSL,
    raise_workflow_graph_legacy,
    workflow_graph_failure,
)
from app.services.workflow_graph.schema import try_parse_workflow_graph_dsl


def _compile_failure(
    code: str,
    message: str,
    *,
    field: str,
    index: int = -1,
    **details: Any,
) -> Failure:
    return workflow_graph_failure(
        code,
        message,
        owner="workflow_graph.compiler",
        public_exception=WorkflowGraphCompileError,
        public_message=message,
        field=field,
        index=index,
        **details,
    )


def try_compile_workflow_graph(payload: Mapping[str, Any] | WorkflowGraphDSL) -> CompiledWorkflowGraph | Failure:
    if isinstance(payload, WorkflowGraphDSL):
        dsl = payload
    else:
        parsed = try_parse_workflow_graph_dsl(payload)
        if isinstance(parsed, Failure):
            return parsed
        dsl = parsed

    node_ids: list[str] = []
    node_id_set: set[str] = set()
    for index, node in enumerate(dsl.nodes):
        if node.node_id in node_id_set:
            return _compile_failure(
                "contract_invalid",
                f"duplicate node_id: {node.node_id}",
                field="node_id",
                index=index,
            )
        if node.node_type not in ALLOWED_NODE_TYPES:
            return _compile_failure(
                "contract_invalid",
                f"invalid node_type '{node.node_type}' for node '{node.node_id}'",
                field="node_type",
                index=index,
            )
        node_ids.append(node.node_id)
        node_id_set.add(node.node_id)

    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    incoming: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}

    for index, edge in enumerate(dsl.edges):
        if edge.from_node not in node_id_set:
            return _compile_failure(
                "integrity_invalid",
                f"edge references missing node: {edge.from_node}",
                field="edge.from",
                index=index,
            )
        if edge.to_node not in node_id_set:
            return _compile_failure(
                "integrity_invalid",
                f"edge references missing node: {edge.to_node}",
                field="edge.to",
                index=index,
            )
        outgoing[edge.from_node].append(edge.to_node)
        incoming[edge.to_node].append(edge.from_node)
        indegree[edge.to_node] += 1

    queue = deque([node_id for node_id in node_ids if indegree[node_id] == 0])
    topo_order: list[str] = []

    while queue:
        current = queue.popleft()
        topo_order.append(current)
        for child in outgoing[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(topo_order) != len(node_ids):
        return _compile_failure(
            "integrity_invalid",
            "workflow graph contains a cycle",
            field="edges",
            index=-1,
        )

    outgoing_tuple = {node_id: tuple(targets) for node_id, targets in outgoing.items()}
    incoming_tuple = {node_id: tuple(sources) for node_id, sources in incoming.items()}

    checksum_payload = {
        "version": dsl.version,
        "options": dsl.options,
        "topo_order": topo_order,
        "outgoing_edges": outgoing_tuple,
        "incoming_edges": incoming_tuple,
    }
    encoded = json.dumps(checksum_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    checksum = hashlib.sha256(encoded).hexdigest()

    return CompiledWorkflowGraph(
        version=dsl.version,
        options=dsl.options,
        topo_order=tuple(topo_order),
        outgoing_edges=outgoing_tuple,
        incoming_edges=incoming_tuple,
        checksum=checksum,
    )


def compile_workflow_graph(payload: Mapping[str, Any] | WorkflowGraphDSL) -> CompiledWorkflowGraph:
    result = try_compile_workflow_graph(payload)
    if isinstance(result, Failure):
        raise_workflow_graph_legacy(result, exception_type=WorkflowGraphCompileError)
    return result
