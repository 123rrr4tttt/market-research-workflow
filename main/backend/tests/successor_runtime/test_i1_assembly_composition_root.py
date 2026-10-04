"""I1 serial composition-root coverage and fail-closed smoke tests.

The assembly is local-only: this test never mounts a route, never starts a
node and never executes a work item.  It verifies that the 27-cell coverage
matrix is complete, installed handler digests are unique, unresolved cells
are explicitly declared and ``compose_node`` returns a real ``RuntimeNode``
with all installed handlers resolvable.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from app.successor_runtime.assembly import (
    build_local_offline_fixture_options,
    local_assembly_scope_digest,
    merge_family_assemblies,
)
from app.successor_runtime.assembly.workflow_assembly import build_workflow_assembly
from app.successor_runtime.assembly.material_ingest_assembly import (
    ASSEMBLY_CELL_IDS as MATERIAL_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.assembly.material_ingest_assembly import (
    build_material_ingest_assembly,
)
from app.successor_runtime.assembly.knowledge_assembly import (
    ASSEMBLY_CELL_IDS as KNOWLEDGE_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.assembly.projection_assembly import build_projection_assembly
from app.successor_runtime.assembly.successor_assembly import (
    ALL_I1_CELLS,
    SuccessorAssembly,
    assemble_successor_runtime,
)
from app.successor_runtime.capabilities.batch_task_native_contribution import (
    ASSEMBLY_CELL_IDS as BATCH_TASK_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.capabilities.workflow_native_contribution import (
    ASSEMBLY_CELL_IDS as WORKFLOW_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.capabilities.acquisition_native_contribution import (
    ASSEMBLY_CELL_IDS as ACQUISITION_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    ASSEMBLY_CELL_IDS as SOURCE_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.runtime.assignments import AssignmentKind
from app.successor_runtime.runtime.task_observation_native_contribution import (
    ASSEMBLY_CELL_IDS as TASK_OBSERVATION_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.runtime.projection_native_contribution import (
    ASSEMBLY_CELL_IDS as PROJECTION_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    NodeIdentity,
    RuntimeNode,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
)
from app.successor_runtime.substrate.postgres.composition_root import (
    ExactInstalledHandlerResolver,
)
from sqlalchemy import create_engine

pytestmark = pytest.mark.unit

EXPECTED_I1_CELL_ORDER = (
    *WORKFLOW_ASSEMBLY_CELL_IDS,
    *SOURCE_ASSEMBLY_CELL_IDS,
    *ACQUISITION_ASSEMBLY_CELL_IDS,
    *BATCH_TASK_ASSEMBLY_CELL_IDS,
    *TASK_OBSERVATION_ASSEMBLY_CELL_IDS,
    *MATERIAL_ASSEMBLY_CELL_IDS,
    *KNOWLEDGE_ASSEMBLY_CELL_IDS,
    *PROJECTION_ASSEMBLY_CELL_IDS,
)
EXPECTED_I1_CELLS = frozenset(EXPECTED_I1_CELL_ORDER)

(
    WORKFLOW_COMPILE_CELL,
    WORKFLOW_OBSERVE_CELL,
    WORKFLOW_RESTORE_CELL,
) = WORKFLOW_ASSEMBLY_CELL_IDS
(
    SOURCE_RESOLVE_CELL,
    SOURCE_PLAN_CELL,
    SOURCE_PROVIDER_EFFECT_CELL,
    SOURCE_TERMINAL_PROJECTION_CELL,
) = SOURCE_ASSEMBLY_CELL_IDS
(
    ACQUISITION_EXECUTE_CELL,
    ACQUISITION_ORDERED_FOLD_CELL,
) = ACQUISITION_ASSEMBLY_CELL_IDS
(
    BATCH_PLAN_CELL,
    BATCH_RETRY_CELL,
    BATCH_SUBMIT_CELL,
) = BATCH_TASK_ASSEMBLY_CELL_IDS
(
    TASK_SESSION_PROJECTION_CELL,
    TASK_EFFECT_RECONCILIATION_CELL,
    TASK_RUN_PROJECTION_CELL,
    TASK_PROCESS_PROJECTION_CELL,
) = TASK_OBSERVATION_ASSEMBLY_CELL_IDS
(
    PROJECTION_COMMAND_QUERY_CELL,
    PROJECTION_CLIENT_CONTRACT_CELL,
    PROJECTION_READ_MODEL_CELL,
) = PROJECTION_ASSEMBLY_CELL_IDS

PROJECTOR_CELLS = (
    SOURCE_TERMINAL_PROJECTION_CELL,
    TASK_SESSION_PROJECTION_CELL,
    TASK_RUN_PROJECTION_CELL,
    TASK_PROCESS_PROJECTION_CELL,
    KNOWLEDGE_ASSEMBLY_CELL_IDS[3],
    PROJECTION_READ_MODEL_CELL,
)
EXPLICIT_SOURCE_PROJECTOR_CELLS = PROJECTOR_CELLS[:-1]


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _engine():
    return create_engine("sqlite+pysqlite:///:memory:", future=True)


def _node_identity() -> NodeIdentity:
    return NodeIdentity(
        node_id="node:i1-composition-smoke",
        incarnation="node-inc:i1-composition-smoke",
        started_at=datetime(2026, 9, 2, 0, 0, tzinfo=UTC),
    )


def _node_args(assembly: SuccessorAssembly) -> dict[str, object]:
    profile_digests = frozenset(
        handler.interpreter_profile_digest
        for handler in assembly.handlers
        if handler.interpreter_profile_digest is not None
    )
    node_profile = _digest("i1-node-profile")
    deployment_catalog = _digest("i1-deployment-catalog")
    return {
        "identity": _node_identity(),
        "profile": RuntimeNodeProfile(
            profile_digest=node_profile,
            supported_assignment_kinds=frozenset({AssignmentKind.INTERPRET}),
            interpreter_profile_digests=profile_digests,
        ),
        "deployment": DeploymentBinding(
            catalog_digest=deployment_catalog,
            node_profile_digest=node_profile,
            runtime_protocol_version="1",
        ),
        "protocol": RuntimeNodeProtocol(version="1", claim_batch_size=1),
        "control_scope": ControlPlaneScope(
            system_actor_id="node:i1-composition-smoke",
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=1,
        ),
    }


def _default_assembly() -> SuccessorAssembly:
    return assemble_successor_runtime(engine=_engine())


def test_i1_composition_root_covers_exactly_twenty_seven_cells() -> None:
    assembly = _default_assembly()
    assert EXPECTED_I1_CELLS == ALL_I1_CELLS
    assert tuple(item.cell_id for item in assembly.cells) == EXPECTED_I1_CELL_ORDER
    assert len(EXPECTED_I1_CELL_ORDER) == 27
    assert len(EXPECTED_I1_CELLS) == len(EXPECTED_I1_CELL_ORDER)
    summary = assembly.coverage_summary()
    assert sum(summary.values()) == len(EXPECTED_I1_CELL_ORDER)


def test_i1_default_coverage_matrix_is_fail_closed() -> None:
    assembly = _default_assembly()
    coverage = assembly.coverage()
    for cell_id in WORKFLOW_ASSEMBLY_CELL_IDS:
        assert coverage[cell_id] == "INSTALLED"
    for cell_id in SOURCE_ASSEMBLY_CELL_IDS[:3]:
        assert coverage[cell_id] == "INSTALLED"
    assert coverage[BATCH_SUBMIT_CELL] == "INSTALLED"
    for cell_id in MATERIAL_ASSEMBLY_CELL_IDS:
        assert coverage[cell_id] == "UNWIRED_DECLARED"
    assert coverage[KNOWLEDGE_ASSEMBLY_CELL_IDS[2]] == "UNWIRED_DECLARED"
    assert coverage[PROJECTION_CLIENT_CONTRACT_CELL] == "INSTALLED"
    for cell_id in (
        *ACQUISITION_ASSEMBLY_CELL_IDS,
        BATCH_PLAN_CELL,
        BATCH_RETRY_CELL,
        TASK_EFFECT_RECONCILIATION_CELL,
    ):
        assert coverage[cell_id] == "FIXTURE_CLOSURE_REQUIRED"
    for cell_id in EXPLICIT_SOURCE_PROJECTOR_CELLS:
        assert coverage[cell_id] == "PROJECTOR_WIRING_DECLARED", cell_id
    assert coverage[PROJECTION_COMMAND_QUERY_CELL] == "INSTALLED"
    assert coverage[PROJECTION_READ_MODEL_CELL] == "INSTALLED"
    assert len(assembly.projector_registry.projectors) == 1
    read_model = assembly.by_cell(PROJECTION_READ_MODEL_CELL)
    assert read_model.handler_binding_digest is not None
    assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in read_model.note


def test_i1_closed_coverage_matrix_installs_fixture_gated_cells() -> None:
    assembly = assemble_successor_runtime(
        engine=_engine(),
        options=build_local_offline_fixture_options(),
    )
    coverage = assembly.coverage()
    for cell_id in EXPECTED_I1_CELL_ORDER:
        assert coverage[cell_id] == "INSTALLED", cell_id
    installed = {item.cell_id for item in assembly.cells if item.status == "INSTALLED"}
    assert installed == EXPECTED_I1_CELLS
    assert len(installed) == len(EXPECTED_I1_CELL_ORDER)
    for cell_id in PROJECTOR_CELLS:
        cell = assembly.by_cell(cell_id)
        assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in cell.note
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 6
    assert len({projector.key for projector in assembly.projector_registry.projectors}) == 6


def test_i1_installed_handlers_have_unique_exact_digests() -> None:
    assembly = assemble_successor_runtime(
        engine=_engine(),
        options=build_local_offline_fixture_options(),
    )
    cells, handlers, recovery, kernel_wiring = merge_family_assemblies(assembly.families)
    assert cells == assembly.cells
    assert handlers == assembly.handlers
    assert recovery == assembly.recovery_handlers
    assert kernel_wiring == assembly.kernel_wiring
    handler_digests = {handler.handler_binding_digest for handler in handlers}
    assert len(handler_digests) == len(handlers)
    kernel_digests = {wiring.binding_digest for wiring in kernel_wiring}
    assert len(kernel_digests) == len(kernel_wiring)
    assert kernel_digests.isdisjoint(handler_digests)
    projector_digests = {
        cell.handler_binding_digest
        for cell in assembly.cells
        if cell.status == "INSTALLED"
        and cell.handler_binding_digest not in handler_digests
        and cell.handler_binding_digest not in kernel_digests
    }
    assert len(projector_digests) == 6
    assert handler_digests.isdisjoint(projector_digests)
    assert kernel_digests.isdisjoint(projector_digests)
    installed = [item for item in assembly.cells if item.status == "INSTALLED"]
    assert installed
    for cell in installed:
        assert cell.handler_binding_digest in (handler_digests | kernel_digests | projector_digests)
    for family in assembly.families:
        for wiring in family.projector_wiring:
            cell = family.cell(wiring.cell_id)
            if cell.status != "INSTALLED":
                continue
            assert family.projector_registry is not None
            contract = next(
                projector
                for projector in family.projector_registry.projectors
                if projector.key.projector_id == wiring.projector_id and projector.projection_id == wiring.projection_id
            )
            assert cell.handler_binding_digest == wiring.registration_digest(contract)


def test_i1_unresolved_cells_never_carry_a_binding_digest() -> None:
    assembly = _default_assembly()
    for cell in assembly.cells:
        if cell.status != "INSTALLED":
            assert cell.handler_binding_digest is None
            assert cell.note, cell.cell_id


def test_i1_material_rollback_bindings_are_declared_gap_not_invented() -> None:
    c7 = build_material_ingest_assembly()
    for cell_id in MATERIAL_ASSEMBLY_CELL_IDS:
        declaration = next(item for item in c7.rollback_bindings if item.cell_id == cell_id)
        assert declaration.status == "DECLARED_GAP"


def test_i1_workflow_and_projection_builders_are_stable() -> None:
    c1 = build_workflow_assembly()
    c9 = build_projection_assembly()
    for cell_id in WORKFLOW_ASSEMBLY_CELL_IDS:
        assert c1.coverage()[cell_id] == "INSTALLED"
    assert c9.coverage()[PROJECTION_COMMAND_QUERY_CELL] == "INSTALLED"
    assert c9.coverage()[PROJECTION_CLIENT_CONTRACT_CELL] == "INSTALLED"
    assert c9.coverage()[PROJECTION_READ_MODEL_CELL] == "INSTALLED"


def test_i1_compose_node_returns_runtime_node_without_starting_it() -> None:
    assembly = _default_assembly()
    assert assembly.project_scope_digest == local_assembly_scope_digest()
    node = assembly.compose_node(**_node_args(assembly))  # type: ignore[arg-type]
    assert isinstance(node, RuntimeNode)
    assert node.identity.node_id == "node:i1-composition-smoke"
    assert isinstance(node.interpreters, ExactInstalledHandlerResolver)
    handler_digests = {handler.handler_binding_digest for handler in assembly.handlers}
    kernel_digests = {wiring.binding_digest for wiring in assembly.kernel_wiring}
    installed = {
        item.handler_binding_digest
        for item in assembly.cells
        if item.status == "INSTALLED" and item.handler_binding_digest in handler_digests | kernel_digests
    }
    assert installed <= set(node.interpreters._by_digest) | kernel_digests
    assert handler_digests <= set(node.interpreters._by_digest)


def test_i1_projector_registry_registration_is_assembly_only() -> None:
    assembly = assemble_successor_runtime(
        engine=_engine(),
        options=build_local_offline_fixture_options(),
    )
    registry = assembly.projector_registry
    assert registry is not None
    assert registry.revision == 0
    assert len(registry.projectors) == 6
    expected_cells = set(PROJECTOR_CELLS)
    assert {cell.cell_id for cell in assembly.cells if cell.status == "INSTALLED"} >= (expected_cells)
    for cell_id in expected_cells:
        cell = assembly.by_cell(cell_id)
        assert cell.handler_binding_digest is not None
        assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in cell.note


def test_i1_default_projector_keys_keep_only_authored_projection_read_model() -> None:
    assembly = _default_assembly()
    assert len(assembly.projector_registry.projectors) == 1
    for cell_id in EXPLICIT_SOURCE_PROJECTOR_CELLS:
        assert assembly.by_cell(cell_id).status == "PROJECTOR_WIRING_DECLARED"
        assert assembly.by_cell(cell_id).handler_binding_digest is None
    read_model = assembly.by_cell(PROJECTION_READ_MODEL_CELL)
    assert read_model.status == "INSTALLED"
    assert read_model.handler_binding_digest is not None
    wiring = next(item for item in assembly.projector_wiring if item.cell_id == PROJECTION_READ_MODEL_CELL)
    contract = assembly.projector_registry.projectors[0]
    assert read_model.handler_binding_digest == wiring.registration_digest(contract)
    assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in read_model.note


def test_i1_composition_does_not_mount_router_or_run_once() -> None:
    assembly = _default_assembly()
    assert not hasattr(assembly, "router")
    node = assembly.compose_node(**_node_args(assembly))  # type: ignore[arg-type]
    assert not hasattr(node, "run")  # run_once is invoked explicitly only
    assert hasattr(node, "run_once")
