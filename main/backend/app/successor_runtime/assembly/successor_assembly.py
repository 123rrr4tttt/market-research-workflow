"""Serial I1 successor composition root over the PostgreSQL first specimen.

This module is the I1 serial integration boundary.  It installs every family
assembly returned by the family builders into the existing
``compose_postgres_first_specimen_runtime`` graph via ``additional_handlers``
and records a fail-closed 30-cell coverage matrix.  It intentionally does not
mount an app route, start a node, call a live provider or perform a canonical
write; those are separate authority milestones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.engine import Engine

from app.successor_runtime.runtime.node import (
    Clock,
    DeploymentBinding,
    NodeIdentity,
    RuntimeNode,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import ControlPlaneScope
from app.successor_runtime.substrate.postgres.composition_root import (
    compose_postgres_first_specimen_runtime,
)
from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory
from app.successor_runtime.substrate.projections.registry import (
    ProjectorContract,
    ProjectorRegistry,
    validate_registry,
)

from .base import (
    PROJECTOR_REGISTRY_INCARNATION,
    C3AssemblyOptions,
    C4AssemblyOptions,
    C5AssemblyOptions,
    C6AssemblyOptions,
    C8AssemblyOptions,
    C9AssemblyOptions,
    CellBinding,
    FamilyAssembly,
    FamilyAssemblyOptions,
    KernelWiring,
    ProjectorSourceKey,
    ProjectorWiring,
    RollbackBindingDeclaration,
    local_assembly_scope_digest,
    merge_family_assemblies,
)
from .c1_assembly import build_c1_assembly
from .c2_assembly import build_c2_assembly
from .c3_assembly import build_c3_assembly, build_deterministic_element_payloads
from .c4_assembly import (
    build_c4_assembly,
    build_deterministic_plan_payload,
    build_deterministic_retry_payload,
)
from .c5_assembly import build_c5_assembly, build_deterministic_reconciliation_binding
from .c6_assembly import build_c6_assembly, build_deterministic_fixtures
from .c7_assembly import build_c7_assembly, build_deterministic_c7_rollback_options
from .c8_assembly import (
    build_c8_assembly,
    build_deterministic_c8_delivery_closure,
    build_deterministic_c8_payloads,
)
from .c9_assembly import build_c9_assembly, build_deterministic_facade_closure
from .s1_horizontal_port_assembly import (
    S1HorizontalPortContract,
    build_s1_horizontal_port_registry,
)
from .s2c_ops_domain_surface_assembly import (
    S2cOpsDomainSurfaceContract,
    build_s2c_ops_domain_surface_registry,
)

ALL_I1_CELLS = frozenset(
    {
        "C1.1",
        "C1.2",
        "C1.3",
        "C2.1",
        "C2.2",
        "C2.3",
        "C2.4",
        "C3.1",
        "C3.2",
        "C4.1",
        "C4.2",
        "C4.3",
        "C5.1",
        "C5.2",
        "C5.3",
        "C5.4",
        "C6.1",
        "C6.2",
        "C6.3",
        "C7.1",
        "C7.2",
        "C7.3",
        "C7.4",
        "C8.1",
        "C8.2",
        "C8.3",
        "C8.4",
        "C9.1",
        "C9.2",
        "C9.3",
    }
)


@dataclass(frozen=True, slots=True)
class SuccessorAssembly:
    """Inspectable I1 assembly; ``compose_node`` is the executable root."""

    engine: Engine
    project_scope_digest: str
    families: tuple[FamilyAssembly, ...]
    cells: tuple[CellBinding, ...]
    handlers: tuple[Any, ...]
    recovery_handlers: tuple[Any, ...]
    kernel_wiring: tuple[KernelWiring, ...]
    projector_wiring: tuple[ProjectorWiring, ...]
    rollback_bindings: tuple[RollbackBindingDeclaration, ...]
    projector_registry: ProjectorRegistry
    horizontal_ports: tuple[S1HorizontalPortContract, ...]
    domain_surfaces: tuple[S2cOpsDomainSurfaceContract, ...]

    def by_cell(self, cell_id: str) -> CellBinding:
        matches = tuple(item for item in self.cells if item.cell_id == cell_id)
        if len(matches) != 1:
            raise KeyError(f"assembly lacks one exact cell {cell_id}")
        return matches[0]

    def coverage(self) -> dict[str, str]:
        return {item.cell_id: item.status for item in self.cells}

    def coverage_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for item in self.cells:
            summary[item.status] = summary.get(item.status, 0) + 1
        return summary

    def compose_node(
        self,
        *,
        identity: NodeIdentity,
        profile: RuntimeNodeProfile,
        deployment: DeploymentBinding,
        protocol: RuntimeNodeProtocol,
        control_scope: ControlPlaneScope,
        clock: Clock | None = None,
    ) -> RuntimeNode:
        """Compose one local-only RuntimeNode with all installed handlers.

        No route is mounted and ``run_once`` is not started here.  The caller
        may only execute local/offline work under an explicit authority
        milestone.
        """

        return compose_postgres_first_specimen_runtime(
            engine=self.engine,
            identity=identity,
            profile=profile,
            deployment=deployment,
            protocol=protocol,
            control_scope=control_scope,
            installations=(),
            additional_handlers=self.handlers + self.recovery_handlers,
            clock=clock,
        ).node


def assemble_successor_runtime(
    *,
    engine: Engine,
    project_scope_digest: str | None = None,
    options: FamilyAssemblyOptions | None = None,
) -> SuccessorAssembly:
    """Build the serial I1 successor assembly over one PostgreSQL engine.

    ``project_scope_digest`` defaults to the deterministic LOCAL_ONLY assembly
    identity; production runs must supply the exact persisted project scope
    digest before any node execution.
    """

    scope_digest = project_scope_digest or local_assembly_scope_digest()
    family_options = options or FamilyAssemblyOptions()
    uow_factory = runtime_uow_factory(engine)
    families = (
        build_c1_assembly(),
        build_c2_assembly(
            uow_factory=uow_factory,
            project_scope_digest=scope_digest,
            projector_source_keys=family_options.projector_source_keys,
        ),
        build_c3_assembly(
            uow_factory=uow_factory,
            project_scope_digest=scope_digest,
            options=family_options.c3,
        ),
        build_c4_assembly(
            uow_factory=uow_factory,
            project_scope_digest=scope_digest,
            options=family_options.c4,
        ),
        build_c5_assembly(
            options=family_options.c5,
            projector_source_keys=family_options.projector_source_keys,
        ),
        build_c6_assembly(
            uow_factory=uow_factory,
            project_scope_digest=scope_digest,
            options=family_options.c6,
        ),
        build_c7_assembly(options=family_options.c7),
        build_c8_assembly(
            engine=engine,
            project_scope_digest=scope_digest,
            options=family_options.c8,
            projector_source_keys=family_options.projector_source_keys,
        ),
        build_c9_assembly(
            options=family_options.c9,
            projector_source_keys=family_options.projector_source_keys,
        ),
    )
    cells, handlers, recovery, kernel_wiring = merge_family_assemblies(families)
    observed = {item.cell_id for item in cells}
    missing = ALL_I1_CELLS - observed
    extra = observed - ALL_I1_CELLS
    if missing or extra:
        raise ValueError(
            "I1 assembly cell coverage must be exactly 30 cells; "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )
    projector_wiring = tuple(
        item for family in families for item in family.projector_wiring
    )
    rollback_bindings = tuple(
        item for family in families for item in family.rollback_bindings
    )
    projector_registry = _merge_projector_registries(families)
    return SuccessorAssembly(
        engine=engine,
        project_scope_digest=scope_digest,
        families=families,
        cells=cells,
        handlers=handlers,
        recovery_handlers=recovery,
        kernel_wiring=kernel_wiring,
        projector_wiring=projector_wiring,
        rollback_bindings=rollback_bindings,
        projector_registry=projector_registry,
        horizontal_ports=build_s1_horizontal_port_registry(),
        domain_surfaces=build_s2c_ops_domain_surface_registry(),
    )


def _merge_projector_registries(
    families: tuple[FamilyAssembly, ...],
) -> ProjectorRegistry:
    """Merge family projector registries into one validated assembly registry."""

    contracts: list[ProjectorContract] = []
    for family in families:
        if family.projector_registry is None:
            continue
        contracts.extend(family.projector_registry.projectors)
    registry = ProjectorRegistry(
        revision=0,
        incarnation=PROJECTOR_REGISTRY_INCARNATION,
        projectors=tuple(contracts),
    )
    validation = validate_registry(registry)
    if not validation.valid:
        raise ValueError(
            "merged projector registry invalid: "
            + "; ".join(item.message for item in validation.violations)
        )
    return registry


def build_local_offline_fixture_options() -> FamilyAssemblyOptions:
    """Deterministic LOCAL_ONLY closures for every installable fixture cell.

    All payloads and bindings use the default local-only assembly scope, so the
    returned options can be passed directly to ``assemble_successor_runtime``
    without a scope override.  No closure here touches a live provider, a
    canonical writer or the app router; each family cell keeps its authority
    notes when installed.
    """

    scope_digest = local_assembly_scope_digest()
    return FamilyAssemblyOptions(
        projector_source_keys={
            "C2.4": ProjectorSourceKey(
                source_ref="run:i1-local:C2.4:001",
                source_incarnation="incarnation:i1-local:C2.4:001",
            ),
            "C5.1": ProjectorSourceKey(
                source_ref="run:i1-local:C5.1:001",
                source_incarnation="incarnation:i1-local:C5.1:001",
            ),
            "C5.3": ProjectorSourceKey(
                source_ref="run:i1-local:C5.3:001",
                source_incarnation="incarnation:i1-local:C5.3:001",
            ),
            "C5.4": ProjectorSourceKey(
                source_ref="run:i1-local:C5.4:001",
                source_incarnation="incarnation:i1-local:C5.4:001",
            ),
            "C8.4": ProjectorSourceKey(
                source_ref="run:i1-local:C8.4:001",
                source_incarnation="incarnation:i1-local:C8.4:001",
            ),
            "C9.3": ProjectorSourceKey(
                source_ref="run:i1-local:C9.3:001",
                source_incarnation="incarnation:i1-local:C9.3:001",
            ),
        },
        c3=C3AssemblyOptions(
            element_payloads=build_deterministic_element_payloads(),
        ),
        c4=C4AssemblyOptions(
            plan_payload=build_deterministic_plan_payload(scope_digest),
            retry_payload=build_deterministic_retry_payload(scope_digest),
        ),
        c5=C5AssemblyOptions(
            reconciliation_binding=build_deterministic_reconciliation_binding(
                scope_digest
            )
        ),
        c6=C6AssemblyOptions(**build_deterministic_fixtures()),
        c7=build_deterministic_c7_rollback_options(scope_digest),
        c8=C8AssemblyOptions(
            **build_deterministic_c8_payloads(scope_digest),
            **build_deterministic_c8_delivery_closure(scope_digest),
        ),
        c9=C9AssemblyOptions(facade=build_deterministic_facade_closure()),
    )


__all__ = [
    "ALL_I1_CELLS",
    "SuccessorAssembly",
    "assemble_successor_runtime",
    "build_local_offline_fixture_options",
]
