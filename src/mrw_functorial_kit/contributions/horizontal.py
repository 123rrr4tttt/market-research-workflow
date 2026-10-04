"""Native contribution rule for the ordered horizontal declaration families.

The source deliberately has no literal movement rows or schema strings.  It
references the existing successor assembly registries and contracts, then
projects them as inert kit contributions.  Compilation never starts a runtime,
registers a route, or grants authority beyond the read-only assembly ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.successor_runtime.assembly.s1_horizontal_port_assembly import (
    S1_HORIZONTAL_PORT_REGISTRY_SCHEMA,
    S1HorizontalPortContract,
)
from app.successor_runtime.assembly.s2c_ops_domain_surface_assembly import (
    S2C_DOMAIN_SURFACE_REGISTRY_SCHEMA,
    S2cOpsDomainSurfaceContract,
)
from functorial_kit.contribution_compiler import NativeContributionRule
from functorial_kit.contributions import ContributionObject, contribution_failures
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)

HORIZONTAL_RULE_ID = "mrw.horizontal.native-rule.v2"
_PORT_REGISTRY_OWNER = "runtime.horizontal-port-registry.v2"
_SURFACE_REGISTRY_OWNER = "runtime.horizontal-domain-surface-registry.v2"


@dataclass(frozen=True, slots=True)
class HorizontalNativeSource:
    """Ordered reference to an existing horizontal assembly registry."""

    family_id: str
    ports: tuple[S1HorizontalPortContract, ...]
    surfaces: tuple[S2cOpsDomainSurfaceContract, ...]

    def __post_init__(self) -> None:
        if not self.family_id.strip():
            raise ValueError("HorizontalNativeSource.family_id is required")
        if not self.ports and not self.surfaces:
            raise ValueError("HorizontalNativeSource requires port or surface contracts")
        ceilings = tuple(
            contract.authority_ceiling
            for contract in (*self.ports, *self.surfaces)
        )
        if any(ceiling != ceilings[0] for ceiling in ceilings):
            raise ValueError("HorizontalNativeSource requires one shared authority ceiling")


@dataclass(frozen=True, slots=True)
class HorizontalNativeBinding:
    """Inert read-only binding carrying the same ordered contracts."""

    definition: HorizontalNativeSource
    authority_ceiling: tuple[tuple[str, bool], ...]


def lower_horizontal_source(source: HorizontalNativeSource) -> HorizontalNativeSource | Failure:
    """Lower the referenced source without copying or mutating registry rows."""

    try:
        source.__post_init__()
    except ValueError as error:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID", str(error), {"source": source.family_id}
        )
    return source


def project_horizontal_definition(
    definition: HorizontalNativeSource,
) -> ProjectedContributionSpec | Failure:
    """Project ordered port/surface contracts onto the inert contribution protocol."""

    objects = tuple(
        ContributionObject(
            id=contract.port_id,
            kind="horizontal_port",
            owner=contract.business_owner,
            references=(contract.schema_ref, contract.module_ref, contract.test_ref),
        )
        for contract in definition.ports
    ) + tuple(
        ContributionObject(
            id=contract.surface_id,
            kind="horizontal_domain_surface",
            owner=contract.business_owner,
            references=(contract.schema_ref, *contract.module_refs, *contract.test_refs),
        )
        for contract in definition.surfaces
    )
    projection_id, projection_owner = (
        (S1_HORIZONTAL_PORT_REGISTRY_SCHEMA, _PORT_REGISTRY_OWNER)
        if definition.ports
        else (S2C_DOMAIN_SURFACE_REGISTRY_SCHEMA, _SURFACE_REGISTRY_OWNER)
    )
    return ProjectedContributionSpec(
        id=projection_id,
        owner=projection_owner,
        objects=objects,
        ports=(
            {
                "authority_ceiling": dict(
                    (definition.ports or definition.surfaces)[0].authority_ceiling
                )
            },
        ),
    )


def assemble_horizontal_definition(
    definition: HorizontalNativeSource,
    context: Any,
) -> HorizontalNativeBinding | Failure:
    """Return an inert binding; no runtime, scheduler, route, or DB effect occurs."""

    del context
    return HorizontalNativeBinding(
        definition=definition,
        authority_ceiling=definition.ports[0].authority_ceiling
        if definition.ports
        else definition.surfaces[0].authority_ceiling,
    )


def validate_horizontal_binding(
    definition: HorizontalNativeSource,
    candidate: object,
) -> BindingAccepted[HorizontalNativeBinding] | BindingRejected:
    if not isinstance(candidate, HorizontalNativeBinding):
        return BindingRejected(
            (NativeBindingIssue("$.binding", "expected HorizontalNativeBinding"),)
        )
    issues = tuple(
        issue
        for valid, path, message in (
            (
                candidate.definition == definition,
                "$.binding.definition",
                "definition drift",
            ),
            (
                candidate.authority_ceiling
                == (
                    definition.ports[0].authority_ceiling
                    if definition.ports
                    else definition.surfaces[0].authority_ceiling
                ),
                "$.binding.authority_ceiling",
                "authority ceiling drift",
            ),
        )
        if not valid
        for issue in (NativeBindingIssue(path, message),)
    )
    return BindingRejected(issues) if issues else BindingAccepted(candidate)


HORIZONTAL_NATIVE_CONTRIBUTION_RULE = NativeContributionRule[
    HorizontalNativeSource,
    HorizontalNativeSource,
    Any,
    HorizontalNativeBinding,
](
    lower=lower_horizontal_source,
    project=project_horizontal_definition,
    assemble=assemble_horizontal_definition,
    validate_binding=validate_horizontal_binding,
)


def compile_horizontal_native_contribution(
    source: HorizontalNativeSource,
):
    from functorial_kit.contribution_compiler import compile_native_contribution

    return compile_native_contribution(source, HORIZONTAL_NATIVE_CONTRIBUTION_RULE)


__all__ = [
    "HORIZONTAL_NATIVE_CONTRIBUTION_RULE",
    "HORIZONTAL_RULE_ID",
    "HorizontalNativeBinding",
    "HorizontalNativeSource",
    "compile_horizontal_native_contribution",
]
