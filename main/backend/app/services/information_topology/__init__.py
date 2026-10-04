"""Shared information-structure contracts; module facts retain their native owners."""

from .contracts import (
    BoundRef,
    Element,
    ElementRef,
    Endpoint,
    PatchOperation,
    TopologyState,
    TopologyView,
    ViewSpec,
    topology_failures,
    topology_state_codec,
)
from .mapping import Correspondence, MappingPreview, MappingSpec, preview_mapping
from .bindings import ProjectBoundSemantics, ProjectSemanticBinding, resolve_project_semantics
from .profiles import (
    AttributeRule, EndpointRule, ProfileSpec, TypeRule, apply_patch, decode_state,
    encode_state, project_view, validate_state,
)

__all__ = [
    "AttributeRule", "BoundRef", "Correspondence", "Element", "ElementRef", "Endpoint",
    "EndpointRule", "MappingPreview", "MappingSpec", "PatchOperation", "ProfileSpec",
    "ProjectBoundSemantics", "ProjectSemanticBinding",
    "TopologyState", "TopologyView", "TypeRule", "ViewSpec", "apply_patch", "decode_state",
    "encode_state", "preview_mapping", "project_view", "topology_failures", "topology_state_codec",
    "resolve_project_semantics", "validate_state",
]
