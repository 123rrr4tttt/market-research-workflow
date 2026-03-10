from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

GRAPH_OBJECT_KINDS = frozenset(
    {
        "template_graph",
        "generated_graph_snapshot",
        "curated_business_graph",
    }
)

TEMP_NODE_ID_PREFIXES = ("draft-", "tmp-", "temp-")

SYSTEM_MANAGED_NODE_FIELDS = frozenset(
    {
        "project_key",
        "revision",
        "version",
        "created_at",
        "updated_at",
        "deleted_at",
        "created_by",
        "updated_by",
    }
)

SYSTEM_MANAGED_EDGE_FIELDS = frozenset(
    {
        "project_key",
        "revision",
        "version",
        "created_at",
        "updated_at",
        "deleted_at",
        "created_by",
        "updated_by",
    }
)


class WorkflowGraphEditContractError(ValueError):
    """Raised when graph edit-contract boundary validation fails."""


@dataclass(frozen=True)
class GraphEditNodeContract:
    node_id: str
    node_type: str
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEditEdgeContract:
    from_node_id: str
    to_node_id: str
    edge_type: str
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEditDraftContract:
    object_kind: str
    nodes: tuple[GraphEditNodeContract, ...]
    edges: tuple[GraphEditEdgeContract, ...]


def is_temporary_node_id(node_id: str) -> bool:
    normalized = str(node_id or "").strip().lower()
    if not normalized:
        return False
    return any(normalized.startswith(prefix) for prefix in TEMP_NODE_ID_PREFIXES)


def parse_graph_edit_draft_contract(
    payload: Mapping[str, Any],
    *,
    object_kind: str | None = None,
) -> GraphEditDraftContract:
    if not isinstance(payload, Mapping):
        raise WorkflowGraphEditContractError("dsl must be a mapping")

    resolved_object_kind = (
        str(
            object_kind
            or payload.get("object_kind")
            or payload.get("graph_object_kind")
            or "template_graph"
        )
        .strip()
        .lower()
    )
    if resolved_object_kind not in GRAPH_OBJECT_KINDS:
        raise WorkflowGraphEditContractError(
            f"unsupported object_kind '{resolved_object_kind}', expected one of {sorted(GRAPH_OBJECT_KINDS)}"
        )

    nodes_raw = payload.get("nodes", [])
    if not isinstance(nodes_raw, list):
        raise WorkflowGraphEditContractError("nodes must be a list")
    edges_raw = payload.get("edges", [])
    if not isinstance(edges_raw, list):
        raise WorkflowGraphEditContractError("edges must be a list")

    nodes: list[GraphEditNodeContract] = []
    node_id_set: set[str] = set()
    for idx, item in enumerate(nodes_raw):
        if not isinstance(item, Mapping):
            raise WorkflowGraphEditContractError(f"node at index {idx} must be a mapping")
        _reject_system_fields(item, SYSTEM_MANAGED_NODE_FIELDS, kind="node", idx=idx)
        node_id = _extract_node_id(item)
        node_type = _extract_node_type(item)
        if not node_id:
            raise WorkflowGraphEditContractError(f"node_id at index {idx} must be a non-empty string")
        if not node_type:
            raise WorkflowGraphEditContractError(
                f"node_type/type at index {idx} must be a non-empty string"
            )
        if node_id in node_id_set:
            raise WorkflowGraphEditContractError(f"duplicate node_id: {node_id}")
        if resolved_object_kind == "curated_business_graph" and is_temporary_node_id(node_id):
            raise WorkflowGraphEditContractError(
                f"temporary node_id '{node_id}' is not allowed for curated_business_graph"
            )
        node_id_set.add(node_id)
        nodes.append(GraphEditNodeContract(node_id=node_id, node_type=node_type, raw=item))

    edges: list[GraphEditEdgeContract] = []
    edge_key_set: set[tuple[str, str, str]] = set()
    for idx, item in enumerate(edges_raw):
        if not isinstance(item, Mapping):
            raise WorkflowGraphEditContractError(f"edge at index {idx} must be a mapping")
        _reject_system_fields(item, SYSTEM_MANAGED_EDGE_FIELDS, kind="edge", idx=idx)
        from_node_id = _extract_endpoint_node_id(item, "from")
        to_node_id = _extract_endpoint_node_id(item, "to")
        edge_type = _extract_edge_type(item)

        if not from_node_id:
            raise WorkflowGraphEditContractError(
                f"edge.from at index {idx} must include a non-empty node id"
            )
        if not to_node_id:
            raise WorkflowGraphEditContractError(
                f"edge.to at index {idx} must include a non-empty node id"
            )
        if from_node_id not in node_id_set:
            raise WorkflowGraphEditContractError(
                f"edge at index {idx} references missing source node '{from_node_id}'"
            )
        if to_node_id not in node_id_set:
            raise WorkflowGraphEditContractError(
                f"edge at index {idx} references missing target node '{to_node_id}'"
            )

        edge_key = (from_node_id, to_node_id, edge_type)
        if edge_key in edge_key_set:
            raise WorkflowGraphEditContractError(
                f"duplicate edge: {from_node_id}->{to_node_id} ({edge_type})"
            )
        edge_key_set.add(edge_key)
        edges.append(
            GraphEditEdgeContract(
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                edge_type=edge_type,
                raw=item,
            )
        )

    return GraphEditDraftContract(
        object_kind=resolved_object_kind,
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


def _extract_node_id(item: Mapping[str, Any]) -> str:
    return str(item.get("node_id") or item.get("id") or item.get("key") or "").strip()


def _extract_node_type(item: Mapping[str, Any]) -> str:
    return str(item.get("node_type") or item.get("type") or "").strip()


def _extract_edge_type(item: Mapping[str, Any]) -> str:
    value = str(item.get("edge_type") or item.get("type") or item.get("predicate") or "").strip()
    return value or "RELATED_TO"


def _extract_endpoint_node_id(item: Mapping[str, Any], field: str) -> str:
    endpoint = item.get(field)
    if isinstance(endpoint, Mapping):
        return str(endpoint.get("node_id") or endpoint.get("id") or endpoint.get("key") or "").strip()
    if isinstance(endpoint, str):
        return endpoint.strip()
    alias = str(item.get(f"{field}_node_id") or item.get(f"{field}_id") or "").strip()
    return alias


def _reject_system_fields(
    item: Mapping[str, Any],
    forbidden: frozenset[str],
    *,
    kind: str,
    idx: int,
) -> None:
    hit = sorted(str(key) for key in item.keys() if str(key) in forbidden)
    if hit:
        raise WorkflowGraphEditContractError(
            f"{kind} at index {idx} contains system-managed fields: {', '.join(hit)}"
        )
