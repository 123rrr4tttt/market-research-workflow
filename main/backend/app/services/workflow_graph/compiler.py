from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any, Mapping

from app.services.workflow_graph.contracts import (
    ALLOWED_NODE_TYPES,
    CompiledWorkflowGraph,
    WorkflowGraphCompileError,
    WorkflowGraphDSL,
)
from app.services.workflow_graph.schema import parse_workflow_graph_dsl


def compile_workflow_graph(payload: Mapping[str, Any] | WorkflowGraphDSL) -> CompiledWorkflowGraph:
    dsl = payload if isinstance(payload, WorkflowGraphDSL) else parse_workflow_graph_dsl(payload)

    node_ids: list[str] = []
    node_id_set: set[str] = set()
    for node in dsl.nodes:
        if node.node_id in node_id_set:
            raise WorkflowGraphCompileError(f"duplicate node_id: {node.node_id}")
        if node.node_type not in ALLOWED_NODE_TYPES:
            raise WorkflowGraphCompileError(
                f"invalid node_type '{node.node_type}' for node '{node.node_id}'"
            )
        node_ids.append(node.node_id)
        node_id_set.add(node.node_id)

    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    incoming: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}

    for edge in dsl.edges:
        if edge.from_node not in node_id_set:
            raise WorkflowGraphCompileError(f"edge references missing node: {edge.from_node}")
        if edge.to_node not in node_id_set:
            raise WorkflowGraphCompileError(f"edge references missing node: {edge.to_node}")
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
        raise WorkflowGraphCompileError("workflow graph contains a cycle")

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
