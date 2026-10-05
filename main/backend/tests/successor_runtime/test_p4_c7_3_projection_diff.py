"""Current-native C7 projection rebuild and offset identity tests."""

from __future__ import annotations

import dataclasses

from app.successor_runtime.substrate.postgres.c7_projector_driver import (
    C7_CANONICAL_SOURCE_KIND,
    C7_SEARCH_PROJECTOR_ID,
    C7_SEARCH_PROJECTOR_VERSION,
    c7_graph_declared_loss,
    c7_search_declared_loss,
    projection_offset_key,
    rebuild_c7_graph_projection,
    rebuild_c7_search_projection,
)
from tests.successor_runtime.p4_c7_fixture import document_ref


def test_search_rebuild_binds_document_ref_and_declares_loss() -> None:
    ref = document_ref()
    projection = rebuild_c7_search_projection(ref)
    assert projection.projection_kind == "search"
    assert projection.document_ref is ref
    assert projection.body["project_key"] == ref.project_key
    assert projection.body["object_id"] == ref.object_id
    assert projection.body["revision"] == ref.revision
    assert projection.body["incarnation"] == ref.incarnation
    assert projection.body["title"] == ""
    assert projection.body["text_snippet"] == ""
    assert projection.declared_loss == c7_search_declared_loss()


def test_graph_rebuild_binds_document_ref_and_declares_loss() -> None:
    ref = document_ref()
    projection = rebuild_c7_graph_projection(ref)
    assert projection.projection_kind == "graph"
    assert projection.document_ref is ref
    assert projection.body["node_key"] == f"ingest:{ref.project_key}:{ref.object_id}"
    assert projection.body["source_locator"] == ""
    assert projection.declared_loss == c7_graph_declared_loss()


def test_projection_rebuild_is_deterministic_without_index_or_graph_write() -> None:
    ref = document_ref()
    assert rebuild_c7_search_projection(ref).projection_digest == (
        rebuild_c7_search_projection(document_ref()).projection_digest
    )
    assert rebuild_c7_graph_projection(ref).projection_digest == (
        rebuild_c7_graph_projection(document_ref()).projection_digest
    )
    assert rebuild_c7_search_projection(ref).projection_digest != (
        rebuild_c7_graph_projection(ref).projection_digest
    )


def test_search_and_graph_offset_keys_share_source_but_not_projector() -> None:
    ref = document_ref()
    search = projection_offset_key("search", ref)
    graph = projection_offset_key("graph", ref)
    assert search.projector_id == C7_SEARCH_PROJECTOR_ID
    assert search.projector_version == C7_SEARCH_PROJECTOR_VERSION
    assert search.projector_id != graph.projector_id
    assert search.source_kind == graph.source_kind == C7_CANONICAL_SOURCE_KIND
    assert search.source_ref == graph.source_ref == f"document:{ref.object_id}"
    assert search.source_incarnation == graph.source_incarnation
    assert set(dataclasses.asdict(search)) == {
        "projector_id",
        "projector_version",
        "source_kind",
        "source_ref",
        "source_incarnation",
    }
