"""Graph projection helpers.

Ensemble-first standardization:
- Build graph with all available node types in current flow.
- Project graph by node-type combinations for specific graph views.
"""
from __future__ import annotations

from typing import Iterable

from .models import Graph


def project_graph_by_node_types(graph: Graph, node_types: Iterable[str] | None) -> Graph:
    """Project a graph using selected node types.

    Keeps:
    - nodes where node.type is in node_types
    - edges whose both endpoints survive

    If node_types is empty/None, returns original graph.
    """
    allowed = {str(t).strip() for t in (node_types or []) if str(t).strip()}
    if not allowed:
        return graph

    projected = Graph(schema_version=graph.schema_version)
    for node_key, node in graph.nodes.items():
        if str(node.type).strip() in allowed:
            projected.nodes[node_key] = node

    for edge in graph.edges:
        from_key = f"{edge.from_node.type}:{edge.from_node.id}"
        to_key = f"{edge.to_node.type}:{edge.to_node.id}"
        if from_key in projected.nodes and to_key in projected.nodes:
            projected.edges.append(edge)
    return projected

