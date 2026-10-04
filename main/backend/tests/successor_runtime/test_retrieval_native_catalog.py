"""Integration witnesses for the shared native retrieval catalog objects."""

from __future__ import annotations

from app.services.information_topology.contracts import topology_failures, topology_state_codec
from app.services.project_retrieval.failures import project_retrieval_failures
from app.services.discovery.adapters import DefaultDiscoveryAdapter
from app.successor_runtime.capabilities.retrieval_native_catalog import (
    retrieval_candidate_native,
    retrieval_contribution_catalog,
    retrieval_flow_native,
    retrieval_native_catalog,
    retrieval_semantics_native,
)
from contributions.project_catalog import project_contribution_catalog


def test_project_catalog_contains_retrieval_native_projection_objects() -> None:
    assert retrieval_native_catalog == (
        retrieval_candidate_native,
        retrieval_flow_native,
        retrieval_semantics_native,
    )
    assert retrieval_contribution_catalog == tuple(
        item.projection for item in retrieval_native_catalog
    )
    assert project_contribution_catalog[-3:] == retrieval_contribution_catalog
    assert project_contribution_catalog[-3] is retrieval_candidate_native.projection
    assert project_contribution_catalog[-2] is retrieval_flow_native.projection
    assert project_contribution_catalog[-1] is retrieval_semantics_native.projection


def test_retrieval_semantics_projection_reuses_authoritative_declarations() -> None:
    projection = retrieval_semantics_native.projection
    assert projection.failures == (topology_failures, project_retrieval_failures)
    assert projection.failures[0] is topology_failures
    assert projection.failures[1] is project_retrieval_failures
    assert projection.codecs == (topology_state_codec,)
    assert projection.codecs[0] is topology_state_codec


def test_default_discovery_adapter_uses_catalog_native_definition() -> None:
    adapter = DefaultDiscoveryAdapter()
    assert adapter._candidate_binding.definition is retrieval_candidate_native.definition
