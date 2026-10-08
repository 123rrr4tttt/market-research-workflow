"""The ordered native catalog for retrieval declarations.

The candidate definition is compiled once from its authoritative source.
Consumers and the project contribution catalog share this object;
importing this module does not assemble or execute either flow.

The semantics entry registers the already-authored information-topology and
project-retrieval failure families plus the topology-state codec; it reuses the
service declarations and adds no second copy of their codes or wire keys.
"""

from __future__ import annotations

from functorial_kit.core.failure import Failure
from functorial_kit.contributions import ContributionSpec, define_contribution

from app.successor_runtime.capabilities import (
    DEFAULT_CANDIDATE_NATIVE_SOURCE,
    compile_candidate_native_contribution,
)
from app.successor_runtime.capabilities.retrieval_common import (
    project_retrieval_failures,
    topology_failures,
    topology_state_codec,
)


retrieval_candidate_native = compile_candidate_native_contribution(
    DEFAULT_CANDIDATE_NATIVE_SOURCE
)
if isinstance(retrieval_candidate_native, Failure):
    # kit:boundary owner=retrieval_native_catalog.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_project_catalog_contains_retrieval_native_projection_objects
    raise RuntimeError(
        f"invalid default retrieval candidate contribution: {retrieval_candidate_native.message}"
    )

retrieval_semantics_native = define_contribution(
    ContributionSpec[None, None](
        id="mrw.retrieval.semantics.native.v1",
        owner="successor_runtime.capabilities.retrieval_semantics_native",
        failures=(topology_failures, project_retrieval_failures),
        codecs=(topology_state_codec,),
    )
)

retrieval_native_catalog = (
    retrieval_candidate_native,
    retrieval_semantics_native,
)
retrieval_contribution_catalog = tuple(
    native.projection for native in (retrieval_candidate_native,)
) + (
    retrieval_semantics_native,
)

__all__ = [
    "retrieval_candidate_native",
    "retrieval_native_catalog",
    "retrieval_semantics_native",
    "retrieval_contribution_catalog",
]
