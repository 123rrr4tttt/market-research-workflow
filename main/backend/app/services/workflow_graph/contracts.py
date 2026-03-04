from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

ALLOWED_NODE_TYPES = frozenset({"vector_search", "llm_call", "join"})


class WorkflowGraphCompileError(ValueError):
    """Raised when workflow graph DSL compilation fails."""


@dataclass(frozen=True)
class WorkflowNode:
    node_id: str
    node_type: str
    config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowEdge:
    from_node: str
    to_node: str


@dataclass(frozen=True)
class WorkflowGraphDSL:
    version: str
    options: Mapping[str, Any]
    nodes: tuple[WorkflowNode, ...]
    edges: tuple[WorkflowEdge, ...]


@dataclass(frozen=True)
class CompiledWorkflowGraph:
    version: str
    options: Mapping[str, Any]
    topo_order: tuple[str, ...]
    outgoing_edges: Mapping[str, tuple[str, ...]]
    incoming_edges: Mapping[str, tuple[str, ...]]
    checksum: str
