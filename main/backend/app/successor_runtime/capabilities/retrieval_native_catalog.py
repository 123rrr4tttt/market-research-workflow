"""The ordered native catalog for retrieval declarations.

The candidate and flow definitions are compiled once from their authoritative
sources. Consumers and the project contribution catalog share these objects;
importing this module does not assemble or execute either flow.

The semantics entry registers the already-authored information-topology and
project-retrieval failure families plus the topology-state codec; it reuses the
service declarations and adds no second copy of their codes or wire keys.
"""

from __future__ import annotations

from functorial_kit.core.failure import Failure

from app.successor_runtime.capabilities import (
    DEFAULT_CANDIDATE_NATIVE_SOURCE,
    DEFAULT_RETRIEVAL_FLOW_SOURCE,
    DEFAULT_RETRIEVAL_SEMANTICS_SOURCE,
    compile_candidate_native_contribution,
    compile_retrieval_flow_native,
    compile_retrieval_semantics_native,
)


retrieval_candidate_native = compile_candidate_native_contribution(
    DEFAULT_CANDIDATE_NATIVE_SOURCE
)
if isinstance(retrieval_candidate_native, Failure):
    # kit:boundary owner=retrieval_native_catalog.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_project_catalog_contains_retrieval_native_projection_objects
    raise RuntimeError(
        f"invalid default retrieval candidate contribution: {retrieval_candidate_native.message}"
    )

retrieval_flow_native = compile_retrieval_flow_native(DEFAULT_RETRIEVAL_FLOW_SOURCE)
if isinstance(retrieval_flow_native, Failure):
    # kit:boundary owner=retrieval_native_catalog.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_project_catalog_contains_retrieval_native_projection_objects
    raise RuntimeError(
        f"invalid default retrieval flow contribution: {retrieval_flow_native.message}"
    )

retrieval_semantics_native = compile_retrieval_semantics_native(
    DEFAULT_RETRIEVAL_SEMANTICS_SOURCE
)
if isinstance(retrieval_semantics_native, Failure):
    # kit:boundary owner=retrieval_native_catalog.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_retrieval_semantics_projection_reuses_authoritative_declarations
    raise RuntimeError(
        f"invalid default retrieval semantics contribution: {retrieval_semantics_native.message}"
    )

retrieval_native_catalog = (
    retrieval_candidate_native,
    retrieval_flow_native,
    retrieval_semantics_native,
)
retrieval_contribution_catalog = tuple(
    native.projection for native in retrieval_native_catalog
)

__all__ = [
    "retrieval_candidate_native",
    "retrieval_flow_native",
    "retrieval_native_catalog",
    "retrieval_semantics_native",
    "retrieval_contribution_catalog",
]
