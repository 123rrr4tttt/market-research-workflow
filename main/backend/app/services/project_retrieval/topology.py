"""Reuse the canonical topology repository in a worker process."""
from __future__ import annotations

from typing import Annotated

from app.models.base import SessionLocal
from app.services.information_topology.catalog import profile_catalog
from app.services.information_topology.io.retrieval import (
    RepositoryRetrievalStore,
    RetrievalStructureIO,
    resolve_domain_vocabulary,
)
from app.services.information_topology.repository import InformationTopologyRepository
from app.services.information_topology.service import InformationTopologyDependencies, InformationTopologyService


def build_topology_service() -> Annotated[
    InformationTopologyService,
    "kit:non-authoritative derived_as=composition fact_source=profile_catalog+repository+retrieval_io+session_factory witness=test:test_build_topology_service_only_assembles_existing_dependencies",
]:
    profiles = dict(profile_catalog())
    repository = InformationTopologyRepository(profiles)
    io = RetrievalStructureIO(
        vocabulary_resolver=resolve_domain_vocabulary,
        store=RepositoryRetrievalStore(repository),
        session_factory=SessionLocal,
    )
    return InformationTopologyService(InformationTopologyDependencies(
        profiles=profiles, mappings={}, io=io, repository=repository,
        session_factory=SessionLocal,
    ))
