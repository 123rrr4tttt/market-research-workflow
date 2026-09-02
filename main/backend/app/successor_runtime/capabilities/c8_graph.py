"""Declared-loss graph projection and context adapter for C8.

P4 ahead-of-time family-local scaffold: graph context keeps edges only when
both endpoints are present, and every dropped node or omitted edge is declared
with explicit loss and provenance.  No provider, export or store code is
called.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from app.successor_runtime.capabilities.c8_common import (
    C8ProjectionError,
    CanonicalRef,
    GraphLossProfile,
    GraphOccurrence,
    GraphProjectionGeneration,
    KnowledgeItem,
    Provenance,
    ReadHandle,
    ReadHandleRegistry,
    SourceClosureEntry,
    TestOnlySealedValue,
    build_read_handle,
    c8_canonical_digest,
    graph_occurrence_digest,
    source_closure_entry,
    validate_canonical_ref,
)

__all__ = [
    "GRAPH_CONTEXT_PROJECTION",
    "GRAPH_PROJECTION_SCHEMA",
    "GraphContext",
    "GraphEdge",
    "GraphLossProfile",
    "GraphNode",
    "GraphOccurrence",
    "GraphProjectionGeneration",
    "build_graph_context_from_items",
    "project_graph_context",
    "project_graph_occurrences",
    "project_graph_occurrences_test_only",
    "project_successor_graph",
]

GRAPH_PROJECTION_SCHEMA = "mrw.successor.c8.graph-context.v1"
GRAPH_CONTEXT_PROJECTION = "graph.context_adapter"
GRAPH_REFERENCE_EDGE_TYPE = "references"


@dataclass(frozen=True, slots=True)
class GraphNode:
    key: str
    project_key: str
    node_type: str
    canonical_identity: str
    handle: ReadHandle


@dataclass(frozen=True, slots=True)
class GraphEdge:
    edge_type: str
    from_key: str
    to_key: str
    present: bool
    omitted_reason: str | None = None


@dataclass(frozen=True, slots=True)
class GraphContext:
    graph_id: str
    project_key: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    omitted_edges: tuple[GraphEdge, ...]
    declared_loss: tuple[str, ...]
    provenance: Provenance
    source_identities: tuple[str, ...] = ()
    source_digests: tuple[str, ...] = ()
    source_closure: tuple[SourceClosureEntry, ...] = ()
    projection_digest: str = ""
    schema_version: str = GRAPH_PROJECTION_SCHEMA


def _edge_loss(edge: GraphEdge) -> str:
    return f"edge:{edge.edge_type}:{edge.from_key}:{edge.to_key}"


def _closure_for_nodes(nodes: tuple[GraphNode, ...]) -> tuple[SourceClosureEntry, ...]:
    return tuple(
        source_closure_entry(
            identity=node.canonical_identity,
            digest=node.handle.canonical_digest,
            revision=node.handle.canonical_revision,
            incarnation=node.handle.canonical_incarnation,
            handle_id=node.handle.handle_id,
        )
        for node in nodes
    )


def _projection_digest(
    *,
    graph_id: str,
    project_key: str,
    nodes: tuple[GraphNode, ...],
    edges: tuple[GraphEdge, ...],
    omitted_edges: tuple[GraphEdge, ...],
    declared_loss: tuple[str, ...],
    source_closure: tuple[SourceClosureEntry, ...],
) -> str:
    return c8_canonical_digest(
        {
            "graph_id": graph_id,
            "project_key": project_key,
            "nodes": [
                {
                    "key": node.key,
                    "node_type": node.node_type,
                    "handle_id": node.handle.handle_id,
                }
                for node in nodes
            ],
            "edges": [
                {
                    "edge_type": edge.edge_type,
                    "from_key": edge.from_key,
                    "to_key": edge.to_key,
                }
                for edge in edges
            ],
            "omitted_edges": [
                {
                    "edge_type": edge.edge_type,
                    "from_key": edge.from_key,
                    "to_key": edge.to_key,
                }
                for edge in omitted_edges
            ],
            "declared_loss": list(declared_loss),
            "source_closure": [
                {
                    "identity": entry.identity,
                    "digest": entry.digest,
                    "revision": entry.revision,
                    "incarnation": entry.incarnation,
                    "handle_id": entry.handle_id,
                }
                for entry in source_closure
            ],
        }
    )


def project_successor_graph(
    *,
    graph_id: str,
    project_key: str,
    nodes: tuple[GraphNode, ...],
    edges: tuple[GraphEdge, ...],
    node_types: tuple[str, ...] | None,
    provenance: Provenance,
) -> GraphContext:
    closure = _closure_for_nodes(nodes)
    allowed = {str(item).strip() for item in (node_types or ()) if str(item).strip()}
    if not allowed:
        return GraphContext(
            graph_id=graph_id,
            project_key=project_key,
            nodes=nodes,
            edges=edges,
            omitted_edges=(),
            declared_loss=(),
            provenance=provenance,
            source_identities=tuple(node.canonical_identity for node in nodes),
            source_digests=tuple(node.handle.canonical_digest for node in nodes),
            source_closure=closure,
            projection_digest=_projection_digest(
                graph_id=graph_id,
                project_key=project_key,
                nodes=nodes,
                edges=edges,
                omitted_edges=(),
                declared_loss=(),
                source_closure=closure,
            ),
        )
    kept_nodes = [node for node in nodes if node.node_type in allowed]
    kept_keys = {node.key for node in kept_nodes}
    kept_edges: list[GraphEdge] = []
    omitted_edges: list[GraphEdge] = []
    edge_loss: list[str] = []
    for edge in edges:
        if edge.from_key in kept_keys and edge.to_key in kept_keys:
            kept_edges.append(
                GraphEdge(
                    edge_type=edge.edge_type,
                    from_key=edge.from_key,
                    to_key=edge.to_key,
                    present=True,
                )
            )
            continue
        omitted_edges.append(
            GraphEdge(
                edge_type=edge.edge_type,
                from_key=edge.from_key,
                to_key=edge.to_key,
                present=False,
                omitted_reason="endpoint node omitted by node-type projection",
            )
        )
        edge_loss.append(_edge_loss(edge))
    node_loss = [f"node:{node.key}" for node in nodes if node.node_type not in allowed]
    return GraphContext(
        graph_id=graph_id,
        project_key=project_key,
        nodes=tuple(kept_nodes),
        edges=tuple(kept_edges),
        omitted_edges=tuple(omitted_edges),
        declared_loss=tuple(node_loss + edge_loss),
        provenance=provenance,
        source_identities=tuple(node.canonical_identity for node in nodes),
        source_digests=tuple(node.handle.canonical_digest for node in nodes),
        source_closure=closure,
        projection_digest=_projection_digest(
            graph_id=graph_id,
            project_key=project_key,
            nodes=tuple(kept_nodes),
            edges=tuple(kept_edges),
            omitted_edges=tuple(omitted_edges),
            declared_loss=tuple(node_loss + edge_loss),
            source_closure=closure,
        ),
    )


def project_graph_context(
    context: GraphContext,
    node_types: tuple[str, ...] | None,
) -> GraphContext:
    """Second projection keeps inherited declared loss and omitted edges."""

    projected = project_successor_graph(
        graph_id=context.graph_id,
        project_key=context.project_key,
        nodes=context.nodes,
        edges=context.edges,
        node_types=node_types,
        provenance=context.provenance,
    )
    merged_omitted = tuple(
        dict.fromkeys(context.omitted_edges + projected.omitted_edges)
    )
    merged_loss = tuple(dict.fromkeys(context.declared_loss + projected.declared_loss))
    return GraphContext(
        graph_id=projected.graph_id,
        project_key=projected.project_key,
        nodes=projected.nodes,
        edges=projected.edges,
        omitted_edges=merged_omitted,
        declared_loss=merged_loss,
        provenance=projected.provenance,
        source_identities=context.source_identities,
        source_digests=context.source_digests,
        source_closure=context.source_closure,
        projection_digest=_projection_digest(
            graph_id=projected.graph_id,
            project_key=projected.project_key,
            nodes=projected.nodes,
            edges=projected.edges,
            omitted_edges=merged_omitted,
            declared_loss=merged_loss,
            source_closure=context.source_closure,
        ),
    )


def build_graph_context_from_items(
    *,
    graph_id: str,
    project_key: str,
    items: tuple[KnowledgeItem, ...],
    registry: ReadHandleRegistry,
    node_types: tuple[str, ...] | None = None,
) -> GraphContext:
    present = {item.key for item in items}
    nodes: list[GraphNode] = []
    all_edges: list[GraphEdge] = []
    first_ref: CanonicalRef | None = None
    for item in items:
        ref = validate_canonical_ref(item, project_key=project_key)
        if first_ref is None:
            first_ref = ref
        handle = registry.register(
            build_read_handle(
                domain="graph",
                object_key=item.key,
                project_key=item.project_key,
                canonical_ref=ref,
                field_mask=("key", "primary_type_node_key"),
            )
        )
        nodes.append(
            GraphNode(
                key=item.key,
                project_key=item.project_key,
                node_type=item.primary_type_node_key,
                canonical_identity=ref.identity,
                handle=handle,
            )
        )
        for target in item.evidence_refs:
            all_edges.append(
                GraphEdge(
                    edge_type=GRAPH_REFERENCE_EDGE_TYPE,
                    from_key=item.key,
                    to_key=target,
                    present=target in present,
                    omitted_reason=(
                        None
                        if target in present
                        else "target item missing from captured items"
                    ),
                )
            )
    closure = _closure_for_nodes(tuple(nodes))
    base = GraphContext(
        graph_id=graph_id,
        project_key=project_key,
        nodes=tuple(nodes),
        edges=tuple(edge for edge in all_edges if edge.present),
        omitted_edges=tuple(edge for edge in all_edges if not edge.present),
        declared_loss=tuple(_edge_loss(edge) for edge in all_edges if not edge.present),
        provenance=Provenance(
            projection_name=GRAPH_CONTEXT_PROJECTION,
            canonical_identity=first_ref.identity if first_ref else "",
            canonical_digest=first_ref.content_digest if first_ref else "",
            canonical_revision=first_ref.revision if first_ref else 1,
            canonical_incarnation=(
                first_ref.incarnation if first_ref else "knowledge-generation-1"
            ),
        ),
        source_identities=tuple(node.canonical_identity for node in nodes),
        source_digests=tuple(node.handle.canonical_digest for node in nodes),
        source_closure=closure,
        projection_digest=_projection_digest(
            graph_id=graph_id,
            project_key=project_key,
            nodes=tuple(nodes),
            edges=tuple(edge for edge in all_edges if edge.present),
            omitted_edges=tuple(edge for edge in all_edges if not edge.present),
            declared_loss=tuple(
                _edge_loss(edge) for edge in all_edges if not edge.present
            ),
            source_closure=closure,
        ),
    )
    if node_types is None:
        return base
    return project_graph_context(base, node_types)


def project_graph_occurrences(
    *,
    generation_id: str,
    project_key: str,
    occurrences: tuple[GraphOccurrence, ...],
    loss_profile: GraphLossProfile,
    loss_profile_registry: object,
    loss_witness: object,
    provenance_digest: str,
    node_types: tuple[str, ...] | None = None,
) -> GraphProjectionGeneration:
    if isinstance(loss_witness, TestOnlySealedValue):
        raise C8ProjectionError("production graph projection rejects TEST_ONLY witness")
    return project_graph_occurrences_test_only(
        generation_id=generation_id,
        project_key=project_key,
        occurrences=occurrences,
        loss_profile=loss_profile,
        loss_profile_registry=loss_profile_registry,
        loss_witness=loss_witness,
        provenance_digest=provenance_digest,
        node_types=node_types,
    )


def project_graph_occurrences_test_only(
    *,
    generation_id: str,
    project_key: str,
    occurrences: tuple[GraphOccurrence, ...],
    loss_profile: GraphLossProfile,
    loss_profile_registry: object,
    loss_witness: object,
    provenance_digest: str,
    node_types: tuple[str, ...] | None = None,
) -> GraphProjectionGeneration:
    registered_profile = loss_profile_registry.resolve(loss_profile.profile_id)
    if registered_profile is None or registered_profile != loss_profile:
        raise C8ProjectionError("graph loss profile is not a registered exact entry")
    if loss_witness._secret is not loss_profile_registry._authority._secret:
        raise C8ProjectionError("graph loss profile witness is not authentic")
    if (
        loss_witness.profile_id != loss_profile.profile_id
        or loss_witness.profile_digest != loss_profile.profile_digest
    ):
        raise C8ProjectionError("graph loss profile witness mismatch")
    seen_ids: set[str] = set()
    seen_pairs: set[tuple[str, str, str]] = set()
    kept: list[GraphOccurrence] = []
    losses: list[str] = []
    allowed = set(node_types or ())
    for occurrence in occurrences:
        if occurrence.occurrence_id in seen_ids:
            raise C8ProjectionError(
                f"graph occurrence collision: {occurrence.occurrence_id}"
            )
        seen_ids.add(occurrence.occurrence_id)
        original_digest = graph_occurrence_digest(occurrence)
        if (
            occurrence.occurrence_digest
            and occurrence.occurrence_digest != original_digest
        ):
            raise C8ProjectionError("graph occurrence digest mismatch")
        source_identity = occurrence.source_identity
        target_identity = occurrence.target_identity
        if occurrence.edge_type in loss_profile.redaction:
            source_identity = "redacted"
            target_identity = "redacted"
            losses.append(f"redaction:{occurrence.occurrence_id}")
        if loss_profile.casefold:
            source_identity = source_identity.casefold()
            target_identity = target_identity.casefold()
            losses.append(f"casefold:{occurrence.occurrence_id}")
        normalized = dataclasses.replace(
            occurrence,
            source_identity=source_identity,
            target_identity=target_identity,
            occurrence_digest="",
        )
        normalized = dataclasses.replace(
            normalized,
            occurrence_digest=graph_occurrence_digest(normalized),
        )
        if occurrence.edge_type in loss_profile.filter:
            losses.append(f"filter:{occurrence.edge_type}:{occurrence.occurrence_id}")
            continue
        if occurrence.edge_type in loss_profile.truncation and occurrence.position > 1:
            losses.append(
                f"truncation:{occurrence.edge_type}:{occurrence.occurrence_id}"
            )
            continue
        if allowed and not (source_identity in allowed and target_identity in allowed):
            losses.append(f"filter:node_type:{occurrence.occurrence_id}")
            continue
        pair = (occurrence.edge_type, source_identity, target_identity)
        if loss_profile.duplicate_collapse and pair in seen_pairs:
            losses.append(f"duplicate_collapse:{occurrence.occurrence_id}")
            continue
        seen_pairs.add(pair)
        kept.append(normalized)
    for field in loss_profile.omitted_fields:
        losses.append(f"omitted_field:{field}")
    return GraphProjectionGeneration(
        generation_id=generation_id,
        project_key=project_key,
        occurrences=tuple(kept),
        declared_loss=tuple(losses),
        provenance_digest=provenance_digest,
        authority_kind=loss_profile_registry.authority_id,
        authority_digest=loss_profile_registry.authority_digest,
        loss_profile_registry_id=loss_profile_registry.registry_id,
        loss_profile_registry_digest=loss_profile_registry.registry_digest,
    )
