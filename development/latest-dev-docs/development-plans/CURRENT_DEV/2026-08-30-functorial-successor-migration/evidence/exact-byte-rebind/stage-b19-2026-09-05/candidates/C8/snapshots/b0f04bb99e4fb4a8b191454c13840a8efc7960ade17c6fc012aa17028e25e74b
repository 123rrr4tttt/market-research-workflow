"""Legacy graph projection replay adapter for the C8.4 declared-loss cell.

The adapter replays ``project_graph_by_node_types`` on a captured in-memory
graph and observes node/edge survival.  It never touches persistence or the
graph export path.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.services.graph.models import (
    Graph,
)
from app.services.graph.models import (
    GraphEdge as LegacyGraphEdge,
)
from app.services.graph.models import (
    GraphNode as LegacyGraphNode,
)
from app.services.graph.projection import project_graph_by_node_types

__all__ = [
    "LEGACY_GRAPH_PROJECTION_INTERPRETER_ID",
    "LegacyC8GraphAdapter",
]

LEGACY_GRAPH_PROJECTION_INTERPRETER_ID = "legacy.graph.project_by_node_types.v1"


class LegacyC8GraphAdapter:
    """Deterministic replay of legacy node-type graph projection."""

    interpreter_id = LEGACY_GRAPH_PROJECTION_INTERPRETER_ID

    def __init__(self) -> None:
        self.projection_calls = 0

    def project(
        self,
        nodes: Mapping[str, LegacyGraphNode],
        edges: Iterable[LegacyGraphEdge],
        node_types: Iterable[str] | None,
    ) -> dict[str, Any]:
        graph = Graph()
        graph.nodes.update(nodes)
        graph.edges = list(edges)
        projected = project_graph_by_node_types(graph, node_types)
        self.projection_calls += 1
        return {
            "interpreter_id": self.interpreter_id,
            "node_keys": sorted(projected.nodes),
            "edge_types": [edge.type for edge in projected.edges],
            "unchanged": projected is graph,
            "projection_calls": self.projection_calls,
            "provider_calls": 0,
            "store_writes": 0,
        }
