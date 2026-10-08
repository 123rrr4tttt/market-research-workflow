"""Integration witnesses for the shared native retrieval catalog objects."""

from __future__ import annotations

from functorial_kit.contributions import Contribution, ContributionCatalog

from app.services.information_topology.contracts import topology_failures, topology_state_codec
from app.successor_runtime.capabilities.retrieval_common import project_retrieval_failures
from app.services.discovery.adapters import DefaultDiscoveryAdapter
from app.successor_runtime.capabilities.retrieval_native_catalog import (
    retrieval_candidate_native,
    retrieval_contribution_catalog,
    retrieval_native_catalog,
    retrieval_semantics_native,
)
from contributions.project_catalog import project_contribution_catalog


def test_project_catalog_contains_retrieval_native_projection_objects() -> None:
    assert retrieval_native_catalog == (
        retrieval_candidate_native,
        retrieval_semantics_native,
    )
    assert retrieval_contribution_catalog == (
        retrieval_candidate_native.projection,
        retrieval_semantics_native,
    )
    assert retrieval_contribution_catalog[-1] is retrieval_semantics_native
    assert project_contribution_catalog[-2:] == retrieval_contribution_catalog
    assert project_contribution_catalog[-2] is retrieval_candidate_native.projection
    assert project_contribution_catalog[-1] is retrieval_semantics_native
    assert all(isinstance(item, Contribution) for item in retrieval_contribution_catalog)
    ContributionCatalog(contributions=retrieval_contribution_catalog)


def test_retrieval_semantics_projection_reuses_authoritative_declarations() -> None:
    assert retrieval_semantics_native.failures == (topology_failures, project_retrieval_failures)
    assert retrieval_semantics_native.failures[0] is topology_failures
    assert retrieval_semantics_native.failures[1] is project_retrieval_failures
    assert retrieval_semantics_native.codecs == (topology_state_codec,)
    assert retrieval_semantics_native.codecs[0] is topology_state_codec


def test_default_discovery_adapter_uses_catalog_native_definition() -> None:
    adapter = DefaultDiscoveryAdapter()
    assert adapter._candidate_binding.definition is retrieval_candidate_native.definition
