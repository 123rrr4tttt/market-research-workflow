from __future__ import annotations

from dataclasses import dataclass

from .models import Graph


@dataclass(frozen=True)
class GraphDiffSummary:
    node_count_diff: int
    edge_count_diff: int
    node_type_overlap_ratio: float


def compare_graphs(a_graph: Graph, b_graph: Graph) -> GraphDiffSummary:
    a_types = {n.type for n in a_graph.nodes.values()}
    b_types = {n.type for n in b_graph.nodes.values()}
    union = a_types | b_types
    overlap = a_types & b_types
    ratio = (len(overlap) / len(union)) if union else 1.0
    return GraphDiffSummary(
        node_count_diff=len(b_graph.nodes) - len(a_graph.nodes),
        edge_count_diff=len(b_graph.edges) - len(a_graph.edges),
        node_type_overlap_ratio=ratio,
    )
