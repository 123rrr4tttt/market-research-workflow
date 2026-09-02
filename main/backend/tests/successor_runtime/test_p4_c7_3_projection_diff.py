"""C7.3 canonical DocumentRef projection diff and rebuild tests."""

from __future__ import annotations

from app.successor_migration.document_repository_c7 import (
    CanonicalDocumentState,
)
from app.successor_migration.graph_projector_c7 import (
    GRAPH_PROJECTION_KIND,
    build_graph_projection,
    delete_graph_observation_digest,
    graph_named_observation_digest,
    project_graph_via_port,
    rebuild_graph_projection,
)
from app.successor_migration.projection_common_c7 import C7ProjectionOffset
from app.successor_migration.search_projector_c7 import (
    SEARCH_PROJECTION_KIND,
    build_search_projection,
    delete_search_observation_digest,
    project_search_via_port,
    rebuild_search_projection,
    search_named_observation_digest,
)
from app.successor_runtime.capabilities.ingest_c7_common import (
    ProjectionDiff,
)
from tests.successor_runtime.p4_c7_fixture import (
    PROJECT_KEY,
    canonical_commit_readback,
    document_ref,
    normalized,
)


class _FakeDocumentPort:
    def __init__(self, state: CanonicalDocumentState | None) -> None:
        self.state = state

    def read_document(self, object_id: str) -> CanonicalDocumentState | None:
        if self.state is None or self.state.object_id != object_id:
            return None
        return self.state


def test_search_projection_binds_document_ref_and_declares_loss() -> None:
    ref = document_ref()
    doc = normalized()
    projection = build_search_projection(ref, title=doc.title, text=doc.text)
    diff = projection.diff()
    assert isinstance(diff, ProjectionDiff)
    assert diff.projection_kind == SEARCH_PROJECTION_KIND
    assert diff.source_digest == ref.content_digest
    assert projection.projection["project_key"] == PROJECT_KEY
    assert projection.projection["object_id"] == ref.object_id
    assert projection.projection["revision"] == ref.revision
    assert projection.projection["incarnation"] == ref.incarnation
    assert ("full_text", "search projection keeps a bounded text snippet") in (
        diff.declared_loss
    )


def test_graph_projection_binds_document_ref_and_declares_loss() -> None:
    ref = document_ref()
    projection = build_graph_projection(
        ref,
        source_locator=ref.incarnation,
    )
    diff = projection.diff()
    assert diff.projection_kind == GRAPH_PROJECTION_KIND
    assert ("text", "graph projection drops the full text") in diff.declared_loss
    assert projection.projection["node_key"].startswith("ingest:")
    assert "text" not in projection.projection


def test_projector_offsets_are_independent_and_content_addressed() -> None:
    search = build_search_projection(
        document_ref(),
        title="T",
        text="Market grew",
    )
    graph = build_graph_projection(document_ref(), source_locator="locator")
    search_key = search.source.to_offset_key()
    graph_key = graph.source.to_offset_key()
    assert search_key["projector_id"] != graph_key["projector_id"]
    assert search_key["source_ref"] == graph_key["source_ref"]
    assert search_key["source_incarnation"] == graph_key["source_incarnation"]
    assert search.projection_digest != graph.projection_digest


def test_rebuild_is_deterministic_without_index_or_graph_effect() -> None:
    ref = document_ref()
    first = rebuild_search_projection(ref)
    second = rebuild_search_projection(document_ref())
    assert first.projection_digest == second.projection_digest
    graph_first = rebuild_graph_projection(ref)
    graph_second = rebuild_graph_projection(document_ref())
    assert graph_first.projection_digest == graph_second.projection_digest


def test_projectors_never_write_index_or_graph() -> None:
    search = build_search_projection(
        document_ref(),
        title="T",
        text="Market grew",
    )
    graph = build_graph_projection(document_ref(), source_locator="locator")
    assert search.projection.get("index_write") is None
    assert graph.projection.get("graph_write") is None


def test_project_via_canonical_read_port_syncs_offset_with_document() -> None:
    readback = canonical_commit_readback(committed_revision=4)
    state = CanonicalDocumentState(
        project_key=PROJECT_KEY,
        object_id=readback.object_id,
        revision=readback.committed_revision,
        incarnation=readback.committed_incarnation,
        content_digest=readback.content_digest,
        canonical_commit_ref=readback.canonical_commit_ref,
    )
    search, search_offset = project_search_via_port(
        _FakeDocumentPort(state),
        readback.object_id,
    )
    graph, graph_offset = project_graph_via_port(
        _FakeDocumentPort(state),
        readback.object_id,
    )
    assert search is not None and graph is not None
    assert search_offset is not None and graph_offset is not None
    assert isinstance(search_offset, C7ProjectionOffset)
    assert search_offset.source_revision == 4
    assert search_offset.source_digest == readback.content_digest
    assert graph_offset.source_revision == 4
    assert graph_offset.source_digest == readback.content_digest
    assert search_offset.source.to_offset_key() != graph_offset.source.to_offset_key()


def test_delete_and_rebuild_named_observation_digests_are_equivalent() -> None:
    ref = document_ref()
    assert delete_search_observation_digest(ref) == search_named_observation_digest(ref)
    assert delete_graph_observation_digest(ref) == graph_named_observation_digest(ref)
    assert search_named_observation_digest(ref) != graph_named_observation_digest(ref)


def test_missing_document_through_port_returns_deleted_observation() -> None:
    search, search_offset = project_search_via_port(
        _FakeDocumentPort(None),
        "missing",
    )
    graph, graph_offset = project_graph_via_port(
        _FakeDocumentPort(None),
        "missing",
    )
    assert search is None and search_offset is None
    assert graph is None and graph_offset is None
