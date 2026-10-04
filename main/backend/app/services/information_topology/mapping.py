"""Declared partial mappings with coverage and observation-relative fidelity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from functorial_kit import Failure

from .contracts import BoundRef, TopologyState, topology_failures
from .profiles import ProfileSpec, validate_state


@dataclass(frozen=True, slots=True)
class Correspondence:
    source: BoundRef
    targets: tuple[BoundRef, ...]


Transform = Callable[[TopologyState], tuple[TopologyState, tuple[Correspondence, ...]] | Failure]
Scope = Callable[[TopologyState], tuple[BoundRef, ...]]
ObservationWitness = Callable[[TopologyState, TopologyState, tuple[Correspondence, ...]], bool]


@dataclass(frozen=True, slots=True)
class MappingSpec:
    mapping_id: str
    source_profile_id: str
    source_profile_version: str
    target_profile_id: str
    target_profile_version: str
    source_scope: Scope
    transform: Transform
    fidelity_claim: str = "unverified"
    observation_witness: ObservationWitness | None = None


@dataclass(frozen=True, slots=True)
class MappingPreview:
    mapping_id: str
    output: TopologyState
    correspondences: tuple[Correspondence, ...]
    unmapped: tuple[BoundRef, ...]
    coverage: str
    fidelity: str


def preview_mapping(
    spec: MappingSpec,
    source_profile: ProfileSpec,
    target_profile: ProfileSpec,
    source: TopologyState,
) -> MappingPreview | Failure:
    """A pure preview; it never writes or infers new domain relations."""

    if (spec.source_profile_id, spec.source_profile_version) != (
        source_profile.profile_id, source_profile.version
    ) or (spec.target_profile_id, spec.target_profile_version) != (
        target_profile.profile_id, target_profile.version
    ):
        return topology_failures.fail("MAPPING_NOT_APPLICABLE", "mapping profile boundary differs")
    source_failure = validate_state(source_profile, source)
    if source_failure is not None:
        return source_failure
    promised_scope = spec.source_scope(source)
    source_refs = {element.ref for element in source.elements}
    if len(set(promised_scope)) != len(promised_scope) or any(ref not in source_refs for ref in promised_scope):
        return topology_failures.fail("MAPPING_NOT_APPLICABLE", "source scope contains duplicate or absent bound reference")
    transformed = spec.transform(source)
    if isinstance(transformed, Failure):
        return transformed
    output, correspondences = transformed
    target_failure = validate_state(target_profile, output)
    if target_failure is not None:
        return target_failure
    target_refs = {element.ref for element in output.elements}
    scope_set = set(promised_scope)
    covered: set[BoundRef] = set()
    for pair in correspondences:
        if (pair.source not in scope_set or pair.source in covered or not pair.targets or
                len(set(pair.targets)) != len(pair.targets) or
                any(target not in target_refs for target in pair.targets)):
            return topology_failures.fail("MAPPING_NOT_APPLICABLE", "correspondence leaves declared scope or target state")
        covered.add(pair.source)
    unmapped = tuple(ref for ref in promised_scope if ref not in covered)
    coverage = "total" if not unmapped else "partial"
    if spec.fidelity_claim not in {"lossless", "lossy", "unverified"}:
        return topology_failures.fail("MAPPING_NOT_APPLICABLE", "unknown fidelity claim")
    if spec.fidelity_claim == "lossy":
        fidelity = "lossy"
    elif spec.fidelity_claim == "lossless" and coverage == "total" and spec.observation_witness is not None:
        fidelity = "lossless" if spec.observation_witness(source, output, correspondences) else "lossy"
    else:
        fidelity = "unverified"
    return MappingPreview(spec.mapping_id, output, correspondences, unmapped, coverage, fidelity)
