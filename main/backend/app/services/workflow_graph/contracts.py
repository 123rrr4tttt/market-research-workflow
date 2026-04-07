from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

ALLOWED_NODE_TYPES = frozenset({"vector_search", "llm_call", "join"})


class WorkflowGraphCompileError(ValueError):
    """Raised when workflow graph DSL compilation fails."""


class WorkflowGraphIntegrityError(ValueError):
    """Raised when workflow graph integrity validation fails."""


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


@dataclass(frozen=True)
class WorkflowGraphIntegrityIssue:
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowGraphIntegrityReport:
    contract_version: str
    valid: bool
    issue_count: int
    issues: tuple[WorkflowGraphIntegrityIssue, ...]


def build_workflow_graph_integrity_report(
    *,
    node_ids: Iterable[str],
    edges: Iterable[tuple[str, str]],
    topo_order: Iterable[str] | None = None,
) -> WorkflowGraphIntegrityReport:
    normalized_node_ids = [str(node_id or "").strip() for node_id in node_ids if str(node_id or "").strip()]
    node_id_set = set(normalized_node_ids)
    issues: list[WorkflowGraphIntegrityIssue] = []

    adjacency: dict[str, list[str]] = {node_id: [] for node_id in normalized_node_ids}
    indegree: dict[str, int] = {node_id: 0 for node_id in normalized_node_ids}
    seen_edges: set[tuple[str, str]] = set()

    for from_node, to_node in edges:
        source = str(from_node or "").strip()
        target = str(to_node or "").strip()
        edge_key = (source, target)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        if source not in node_id_set:
            issues.append(
                WorkflowGraphIntegrityIssue(
                    code="missing_edge_source",
                    message=f"edge references missing source node '{source}'",
                    details={"from_node": source, "to_node": target},
                )
            )
            continue
        if target not in node_id_set:
            issues.append(
                WorkflowGraphIntegrityIssue(
                    code="missing_edge_target",
                    message=f"edge references missing target node '{target}'",
                    details={"from_node": source, "to_node": target},
                )
            )
            continue
        adjacency[source].append(target)
        indegree[target] += 1

    topo_items = [str(item or "").strip() for item in (topo_order or []) if str(item or "").strip()]
    if topo_items:
        seen_topo: set[str] = set()
        for node_id in topo_items:
            if node_id in seen_topo:
                issues.append(
                    WorkflowGraphIntegrityIssue(
                        code="duplicate_topo_order_node",
                        message=f"topo_order contains duplicate node '{node_id}'",
                        details={"node_id": node_id},
                    )
                )
                continue
            seen_topo.add(node_id)
            if node_id not in node_id_set:
                issues.append(
                    WorkflowGraphIntegrityIssue(
                        code="topo_order_unknown_node",
                        message=f"topo_order references unknown node '{node_id}'",
                        details={"node_id": node_id},
                    )
                )
        missing_from_topo = sorted(node_id_set - seen_topo)
        for node_id in missing_from_topo:
            issues.append(
                WorkflowGraphIntegrityIssue(
                    code="topo_order_missing_node",
                    message=f"topo_order is missing node '{node_id}'",
                    details={"node_id": node_id},
                )
            )
        topo_index = {node_id: idx for idx, node_id in enumerate(topo_items)}
        for source, targets in adjacency.items():
            source_idx = topo_index.get(source)
            if source_idx is None:
                continue
            for target in targets:
                target_idx = topo_index.get(target)
                if target_idx is None:
                    continue
                if source_idx >= target_idx:
                    issues.append(
                        WorkflowGraphIntegrityIssue(
                            code="topo_order_dependency_drift",
                            message=f"topo_order schedules '{target}' before dependency '{source}'",
                            details={"from_node": source, "to_node": target},
                        )
                    )
                    break

    reduced_indegree = dict(indegree)
    ready = [node_id for node_id in normalized_node_ids if reduced_indegree[node_id] == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for child in adjacency.get(current, []):
            reduced_indegree[child] -= 1
            if reduced_indegree[child] == 0:
                ready.append(child)
    if visited != len(node_id_set):
        cycle_nodes = sorted(node_id for node_id, degree in reduced_indegree.items() if degree > 0)
        issues.append(
            WorkflowGraphIntegrityIssue(
                code="workflow_cycle",
                message="workflow graph contains a cycle",
                details={"cycle_nodes": cycle_nodes},
            )
        )

    return WorkflowGraphIntegrityReport(
        contract_version="workflow_graph.integrity_report.v1",
        valid=not issues,
        issue_count=len(issues),
        issues=tuple(issues),
    )


def assert_workflow_graph_integrity(
    *,
    node_ids: Iterable[str],
    edges: Iterable[tuple[str, str]],
    topo_order: Iterable[str] | None = None,
    error_cls: type[Exception] = WorkflowGraphIntegrityError,
) -> WorkflowGraphIntegrityReport:
    report = build_workflow_graph_integrity_report(
        node_ids=node_ids,
        edges=edges,
        topo_order=topo_order,
    )
    if report.valid:
        return report
    first_issue = report.issues[0]
    raise error_cls(first_issue.message)
