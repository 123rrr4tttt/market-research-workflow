"""Compatibility re-export of the canonical information-topology contracts.

The authoritative identity, structural values and canonical wire codec now live
in the pure capability shared-contract module so the retrieval semantics
contribution can register them without importing a service implementation.
"""

from app.successor_runtime.capabilities.retrieval_common import (
    BoundRef,
    Element,
    ElementRef,
    Endpoint,
    PatchOperation,
    TopologyState,
    TopologyView,
    ViewProjection,
    ViewSpec,
    topology_failures,
    topology_state_codec,
)

__all__ = [
    "BoundRef",
    "Element",
    "ElementRef",
    "Endpoint",
    "PatchOperation",
    "TopologyState",
    "TopologyView",
    "ViewProjection",
    "ViewSpec",
    "topology_failures",
    "topology_state_codec",
]
