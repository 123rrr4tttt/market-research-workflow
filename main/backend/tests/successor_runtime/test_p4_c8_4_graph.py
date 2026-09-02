"""P4 C8.4 declared-loss graph projection tests."""

from __future__ import annotations

import dataclasses

import pytest

from app.successor_runtime.capabilities.c8_graph import (
    GRAPH_CONTEXT_PROJECTION,
    build_graph_context_from_items,
    project_graph_context,
)
from app.successor_runtime.capabilities.c8_typed_knowledge import (
    C8ProjectionError,
    item_digest,
)

from .p4_c8_fixture import PROJECT_KEY, captured_item, new_registry


def test_context_keeps_edges_only_for_present_nodes() -> None:
    first = captured_item(
        key="ki:a",
        evidence_refs=("ki:b", "ki:c"),
    )
    second = captured_item(
        key="ki:b",
        evidence_refs=(),
    )
    context = build_graph_context_from_items(
        graph_id="graph-1",
        project_key=PROJECT_KEY,
        items=(first, second),
        registry=new_registry(),
    )
    assert {node.key for node in context.nodes} == {"ki:a", "ki:b"}
    assert [edge.to_key for edge in context.edges] == ["ki:b"]
    assert [edge.to_key for edge in context.omitted_edges] == ["ki:c"]
    assert context.omitted_edges[0].omitted_reason is not None
    assert "edge:references:ki:a:ki:c" in context.declared_loss
    assert context.provenance.projection_name == GRAPH_CONTEXT_PROJECTION
    assert context.source_identities == (
        f"knowledge:{PROJECT_KEY}:ki:a",
        f"knowledge:{PROJECT_KEY}:ki:b",
    )
    assert len(context.source_digests) == 2
    assert context.projection_digest
    assert len(context.source_closure) == 2
    assert context.source_closure[0].handle_id
    assert context.provenance.canonical_revision == 1
    assert context.provenance.canonical_incarnation == (first.canonical_ref.incarnation)


def test_node_type_projection_declares_dropped_nodes_and_edges() -> None:
    topic = captured_item(
        key="ki:topic",
        evidence_refs=("ki:post",),
        node_type="Topic",
    )
    post = captured_item(
        key="ki:post",
        evidence_refs=(),
        node_type="Post",
    )
    context = build_graph_context_from_items(
        graph_id="graph-2",
        project_key=PROJECT_KEY,
        items=(topic, post),
        registry=new_registry(),
        node_types=("Topic",),
    )
    assert {node.key for node in context.nodes} == {"ki:topic"}
    assert len(context.source_closure) == 2
    assert {entry.identity for entry in context.source_closure} == {
        f"knowledge:{PROJECT_KEY}:ki:topic",
        f"knowledge:{PROJECT_KEY}:ki:post",
    }
    assert context.edges == ()
    assert len(context.omitted_edges) == 1
    assert context.omitted_edges[0].omitted_reason is not None
    assert "node:ki:post" in context.declared_loss
    assert "edge:references:ki:topic:ki:post" in context.declared_loss


def test_empty_node_types_keeps_full_context_without_declared_loss() -> None:
    item = captured_item(evidence_refs=())
    context = build_graph_context_from_items(
        graph_id="graph-3",
        project_key=PROJECT_KEY,
        items=(item,),
        registry=new_registry(),
        node_types=(),
    )
    assert {node.key for node in context.nodes} == {item.key}
    assert context.declared_loss == ()
    assert context.omitted_edges == ()


def test_graph_provenance_binds_canonical_identity_and_digest() -> None:
    item = captured_item()
    context = build_graph_context_from_items(
        graph_id="graph-4",
        project_key=PROJECT_KEY,
        items=(item,),
        registry=new_registry(),
    )
    assert context.provenance.canonical_identity == (
        f"knowledge:{PROJECT_KEY}:{item.key}"
    )
    assert context.provenance.canonical_digest == item.canonical_ref.content_digest
    assert context.provenance.canonical_digest == item_digest(item)


def test_second_projection_keeps_inherited_loss_and_omitted_edges() -> None:
    first = captured_item(
        key="ki:a",
        evidence_refs=("ki:b", "ki:missing"),
        node_type="Topic",
    )
    second = captured_item(
        key="ki:b",
        evidence_refs=(),
        node_type="Topic",
    )
    base = build_graph_context_from_items(
        graph_id="graph-5",
        project_key=PROJECT_KEY,
        items=(first, second),
        registry=new_registry(),
    )
    assert "edge:references:ki:a:ki:missing" in base.declared_loss

    projected_once = build_graph_context_from_items(
        graph_id="graph-5",
        project_key=PROJECT_KEY,
        items=(first, second),
        registry=new_registry(),
        node_types=("Topic",),
    )
    projected_twice = project_graph_context(projected_once, ("Topic",))
    assert "edge:references:ki:a:ki:missing" in projected_once.declared_loss
    assert "edge:references:ki:a:ki:missing" in projected_twice.declared_loss
    assert projected_twice.omitted_edges == projected_once.omitted_edges
    assert projected_twice.source_identities == projected_once.source_identities
    assert projected_twice.source_closure == projected_once.source_closure
    assert projected_twice.projection_digest


def test_graph_rejects_item_with_stale_canonical_ref() -> None:
    item = captured_item()
    other_body = captured_item(statement="different statement")
    stale = dataclasses.replace(
        item,
        canonical_ref=dataclasses.replace(
            item.canonical_ref,
            content_digest=item_digest(other_body),
        ),
    )
    with pytest.raises(C8ProjectionError, match="body digest"):
        build_graph_context_from_items(
            graph_id="graph-6",
            project_key=PROJECT_KEY,
            items=(stale,),
            registry=new_registry(),
        )
