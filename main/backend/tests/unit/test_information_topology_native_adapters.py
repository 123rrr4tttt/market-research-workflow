from dataclasses import dataclass, field

import pytest
from functorial_kit import Failure

from app.services.information_topology.adapters.native import (
    adapt_clue_chain_state,
    adapt_document,
    adapt_graph,
    adapt_typed_knowledge,
    adapt_writing_document,
    clue_retrieval_correspondence,
)
from app.services.information_topology.contracts import BoundRef, ElementRef
from app.services.information_topology.modules.retrieval import DomainVocabulary, make_retrieval_profile
from app.services.information_topology.adapters.native import resolve_retrieval_domain
from app.services.information_topology.modules.graph_view import graph_view_profile, make_graph_view_spec
from app.services.information_topology.profiles import project_view, validate_state


@dataclass
class Node:
    type: str
    id: str
    properties: dict = field(default_factory=dict)


@dataclass
class Edge:
    type: str
    from_node: Node
    to_node: Node
    properties: dict = field(default_factory=dict)


@dataclass
class Graph:
    nodes: dict
    edges: list
    schema_version: str = "v1"


class VocabularyReader:
    def __init__(self, by_revision):
        self.by_revision = by_revision
        self.calls = []

    def read_domain_vocabulary(self, *, source_ref, observed_revision, content_digest):
        self.calls.append((source_ref, observed_revision, content_digest))
        return self.by_revision.get((source_ref.local_id, observed_revision), Failure("information_topology", "STALE_REFERENCE", "history unavailable"))


def vocabulary(name, ref, *, node_types=("现场", "组织")):
    return DomainVocabulary(name, node_types, ("关联",), ("治理",), ("概况",), ("材料池",), ("A",), ref)


def test_native_adapters_bind_identity_and_report_source_version_capability():
    document = adapt_document({"id": 12, "title": "Paper", "doc_type": "report", "updated_at": None}, project_key="p")
    assert document.revision_capability == "schema_only"
    assert document.state.elements[0].ref.ref.local_id == "12"

    writing = adapt_writing_document({"id": 8, "head_version": 3, "etag": "abc", "title": "Draft"}, project_key="p")
    assert writing.revision_capability == "versioned"
    assert writing.state.elements[0].ref.observed_revision == "3"

    typed = adapt_typed_knowledge({"project_key": "p", "object_type": "concept", "identity_ref": "concept:x",
                                   "object_key": "x", "updated_at": "2026-09-01"}, project_key="p")
    assert typed.state.elements[0].ref.ref.local_id == "concept:x"
    assert isinstance(adapt_typed_knowledge({"project_key": "other", "identity_ref": "x"}, project_key="p"), Failure)
    with pytest.raises(ValueError, match="project_key and native identity"):
        adapt_document({"id": 12}, project_key="")
    with pytest.raises(ValueError, match="project_key and native identity"):
        adapt_document({"id": ""}, project_key="p")


def test_clue_state_is_a_read_only_observation_and_mapping_requires_same_project():
    observed = adapt_clue_chain_state({"contract_version": "clue_chain.state.v1", "base_version": 4, "chains": {
        "c1": {"chain": {"chain_id": "c1", "status": "running"}}}}, project_key="p")
    assert observed.revision_capability == "versioned"
    assert observed.state.elements[0].attributes["status"] == "running"
    a = BoundRef(ElementRef("p", "clue_chains", "chains", "chain", "c1"), "4")
    b = BoundRef(ElementRef("p", "retrieval", "graph", "clue", "c1"), "2")
    assert clue_retrieval_correspondence(a, b).targets == (b,)
    with pytest.raises(ValueError):
        clue_retrieval_correspondence(a, BoundRef(ElementRef("q", "retrieval", "graph", "clue", "c1"), "2"))


def test_graph_adapter_preserves_relation_origin_and_endpoints_and_ignores_ui_state():
    left, right = Node("Article", "a", {"group": "one"}), Node("Topic", "t", {"group": "one"})
    graph = Graph({"Article:a": left, "Topic:t": right}, [Edge("MENTIONS", left, right, {"weight": 2})])
    observed = adapt_graph(graph, project_key="p", view_state={"selection": ["fake"], "x": 50, "expanded": True})
    assert observed.revision_capability == "schema_only"
    assert validate_state(graph_view_profile, observed.state) is None
    relation = next(item for item in observed.state.elements if item.ref.ref.type_id == "graph_relation")
    assert relation.attributes["origin_ref"]["type_id"] == "MENTIONS"
    assert [endpoint.role for endpoint in relation.endpoints] == ["source", "target"]
    view = project_view(graph_view_profile, observed.state, make_graph_view_spec(group_by="group"), {"graph": "v1"})
    assert not isinstance(view, Failure)
    assert len(view.members) == 2 and len(view.relations) == 1
    assert set(view.organization["groups"]) == {"one"}
    assert "selection" not in view.organization
    with pytest.raises(ValueError, match="group_by"):
        make_graph_view_spec(group_by=" ")


def test_retrieval_domain_resolver_binds_two_domains_and_exact_observed_version():
    ref_a = BoundRef(ElementRef("p", "documents", "briefs", "domain_brief", "alpha"), "r1", "digest-a")
    ref_b = BoundRef(ElementRef("p", "documents", "briefs", "domain_brief", "beta"), "r1", "digest-b")
    vocab_a, vocab_b = vocabulary("alpha", ref_a), vocabulary("beta", ref_b, node_types=("现场", "机构"))
    profile_a, profile_b = make_retrieval_profile(vocab_a), make_retrieval_profile(vocab_b)
    reader = VocabularyReader({("alpha", "r1"): vocab_a, ("beta", "r1"): vocab_b})

    resolved_a = resolve_retrieval_domain(reader, ref_a, project_key="p",
        expected_profile_id=profile_a.profile_id, expected_profile_version=profile_a.version)
    assert not isinstance(resolved_a, Failure)
    assert resolved_a.profile.profile_id == profile_a.profile_id
    assert reader.calls == [(ref_a.ref, "r1", "digest-a")]

    resolved_b = resolve_retrieval_domain(reader, ref_b, project_key="p",
        expected_profile_id=profile_b.profile_id, expected_profile_version=profile_b.version)
    assert not isinstance(resolved_b, Failure)
    assert resolved_b.profile.profile_id != resolved_a.profile.profile_id

    # A profile version from another observation is rejected after resolution.
    mismatch = resolve_retrieval_domain(reader, ref_b, project_key="p",
        expected_profile_id=profile_a.profile_id, expected_profile_version=profile_a.version)
    assert isinstance(mismatch, Failure) and mismatch.code == "STALE_REFERENCE"

    # Exact historical lookup is required; a current-only reader returns typed STALE_REFERENCE.
    old_ref = BoundRef(ref_a.ref, "r0", "digest-old")
    historical = resolve_retrieval_domain(reader, old_ref, project_key="p",
        expected_profile_id=profile_a.profile_id, expected_profile_version=profile_a.version)
    assert isinstance(historical, Failure) and historical.code == "STALE_REFERENCE"
