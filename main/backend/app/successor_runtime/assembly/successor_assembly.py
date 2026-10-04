"""Serial I1 successor composition root over the PostgreSQL first specimen.

This module is the I1 serial integration boundary.  It installs every family
assembly returned by the family builders into the existing
``compose_postgres_first_specimen_runtime`` graph via ``additional_handlers``
and records a fail-closed 27-cell coverage matrix.  It intentionally does not
mount an app route, start a node, call a live provider or perform a canonical
write; those are separate authority milestones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from sqlalchemy.engine import Engine

from app.successor_runtime.capabilities.batch_task_native_contribution import (
    ASSEMBLY_CELL_IDS as BATCH_CELL_IDS,
)

# Coverage comes from author declarations, independently of assembled results.
from app.successor_runtime.capabilities.workflow_native_contribution import (
    ASSEMBLY_CELL_IDS as WORKFLOW_CELL_IDS,
)
from app.successor_runtime.capabilities.acquisition_native_contribution import (
    ASSEMBLY_CELL_IDS as ACQUISITION_CELL_IDS,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    ASSEMBLY_CELL_IDS as SOURCE_CELL_IDS,
)
from app.successor_runtime.runtime.task_observation_native_contribution import (
    ASSEMBLY_CELL_IDS as TASK_CELL_IDS,
)
from app.successor_runtime.runtime.projection_native_contribution import (
    ASSEMBLY_CELL_IDS as PROJECTION_CELL_IDS,
)
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
    AcquisitionAssemblyOptions,
    BatchTaskAssemblyOptions,
    TaskObservationAssemblyOptions,
    KnowledgeAssemblyOptions,
    ProjectionAssemblyOptions,
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
from .workflow_assembly import build_workflow_assembly
from .source_assembly import build_source_assembly
from .acquisition_batch_assembly import build_acquisition_batch_assembly, build_deterministic_element_payloads
from .batch_task_assembly import (
    build_batch_task_assembly,
    build_deterministic_plan_payload,
    build_deterministic_retry_payload,
)
from .task_observation_assembly import build_task_observation_assembly, build_deterministic_reconciliation_binding
from .material_ingest_assembly import ASSEMBLY_CELL_IDS as MATERIAL_CELL_IDS
from .material_ingest_assembly import build_material_ingest_assembly, build_deterministic_material_ingest_rollback_options
from .knowledge_assembly import ASSEMBLY_CELL_IDS as KNOWLEDGE_CELL_IDS
from .knowledge_assembly import (
    build_knowledge_assembly,
    build_deterministic_knowledge_delivery_closure,
    build_deterministic_knowledge_payloads,
)
from .projection_assembly import build_projection_assembly, build_deterministic_facade_closure
from .s1_horizontal_port_assembly import (
    S1HorizontalPortContract,
    build_s1_horizontal_port_registry,
)
from .s2c_ops_domain_surface_assembly import (
    S2cOpsDomainSurfaceContract,
    build_s2c_ops_domain_surface_registry,
)

ALL_I1_CELLS = frozenset(
    (*WORKFLOW_CELL_IDS, *SOURCE_CELL_IDS, *ACQUISITION_CELL_IDS,
     *BATCH_CELL_IDS, *TASK_CELL_IDS, *MATERIAL_CELL_IDS,
     *KNOWLEDGE_CELL_IDS, *PROJECTION_CELL_IDS)
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
        build_workflow_assembly(),
        build_source_assembly(
            uow_factory=uow_factory,
            project_scope_digest=scope_digest,
            projector_source_keys=family_options.projector_source_keys,
        ),
        build_acquisition_batch_assembly(
            uow_factory=uow_factory,
            project_scope_digest=scope_digest,
            options=family_options.c3,
        ),
        build_batch_task_assembly(
            uow_factory=uow_factory,
            project_scope_digest=scope_digest,
            options=family_options.c4,
        ),
        build_task_observation_assembly(
            options=family_options.c5,
            projector_source_keys=family_options.projector_source_keys,
        ),
        build_material_ingest_assembly(options=family_options.c7),
        build_knowledge_assembly(
            engine=engine,
            project_scope_digest=scope_digest,
            options=family_options.c8,
            projector_source_keys=family_options.projector_source_keys,
        ),
        build_projection_assembly(
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
            "I1 assembly cell coverage must be exactly 27 cells; "
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


def build_local_offline_fixture_options() -> Annotated[
    FamilyAssemblyOptions,
    "kit:prepared-command effect_boundary=successor_runtime.successor_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
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
            cell_id: ProjectorSourceKey(
                source_ref=f"run:local-assembly:{cell_id}:001",
                source_incarnation=f"incarnation:local-assembly:{cell_id}:001",
            )
            for cell_id in (
                SOURCE_CELL_IDS[3], TASK_CELL_IDS[0], TASK_CELL_IDS[2],
                TASK_CELL_IDS[3], KNOWLEDGE_CELL_IDS[3], PROJECTION_CELL_IDS[2],
            )
        },
        c3=AcquisitionAssemblyOptions(
            element_payloads=build_deterministic_element_payloads(),
        ),
        c4=BatchTaskAssemblyOptions(
            plan_payload=build_deterministic_plan_payload(scope_digest),
            retry_payload=build_deterministic_retry_payload(scope_digest),
        ),
        c5=TaskObservationAssemblyOptions(
            reconciliation_binding=build_deterministic_reconciliation_binding(
                scope_digest
            )
        ),
        c7=build_deterministic_material_ingest_rollback_options(scope_digest),
        c8=KnowledgeAssemblyOptions(
            **build_deterministic_knowledge_payloads(scope_digest),
            **build_deterministic_knowledge_delivery_closure(scope_digest),
        ),
        c9=ProjectionAssemblyOptions(facade=build_deterministic_facade_closure()),
    )


__all__ = [
    "ALL_I1_CELLS",
    "SuccessorAssembly",
    "assemble_successor_runtime",
    "build_local_offline_fixture_options",
]
