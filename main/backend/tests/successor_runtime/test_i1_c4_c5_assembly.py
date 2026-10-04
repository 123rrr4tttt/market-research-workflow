"""Non-PostgreSQL structural tests for the I1 C4/C5 family assemblies."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

from app.successor_runtime.assembly.base import (
    BatchTaskAssemblyOptions,
    TaskObservationAssemblyOptions,
    ProjectorSourceKey,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.batch_task_assembly import (
    build_batch_task_assembly,
    build_deterministic_plan_payload,
    build_deterministic_retry_payload,
)
from app.successor_runtime.assembly.task_observation_assembly import (
    TASK_EFFECT_RECONCILE_DURABLE_ATTEMPT_NODE_NOT_PROVEN,
    TASK_OBSERVATION_FAMILY_ID,
    build_task_observation_assembly,
    build_deterministic_reconciliation_binding,
    validate_task_observation_assembly_native_definition,
)
from app.successor_runtime.capabilities import batch_task as c4
from app.successor_runtime.capabilities.batch_task_native_contribution import (
    ASSEMBLY_CELL_IDS as BATCH_TASK_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.runtime.task_observation_native_contribution import (
    ASSEMBLY_CELL_IDS as TASK_OBSERVATION_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.runtime.task_observation_native_contribution import (
    DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE,
    NON_DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE,
    compile_task_observation_native_contribution,
)
from app.successor_runtime.substrate.postgres.batch_task_submission_handler import (
    BatchTaskSubmissionStoreRehydratedHandler,
)
from app.successor_runtime.substrate.postgres.batch_task_canary_handlers import (
    BatchTaskPlanRuntimeHandler,
    BatchTaskRetryRuntimeHandler,
)
from app.successor_runtime.substrate.projections.agent_session import (
    AGENT_SESSION_PROJECTOR_ID,
)
from functorial_kit.core.failure import Failure

from .p3_c4_fixture import SCOPE_DIGEST, plan_payload, retry_payload

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
TASK_PROJECTOR_CELLS = (
    TASK_SESSION_PROJECTION_CELL,
    TASK_RUN_PROJECTION_CELL,
    TASK_PROCESS_PROJECTION_CELL,
)


def test_c5_assembly_accepts_typed_native_definition_and_rejects_tamper() -> None:
    native = compile_task_observation_native_contribution(DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE)
    assert not isinstance(native, Failure)
    assembly = build_task_observation_assembly(
        options=TaskObservationAssemblyOptions(
            reconciliation_binding=build_deterministic_reconciliation_binding(local_assembly_scope_digest())
        ),
        native_definition=native.definition,
    )
    validate_task_observation_assembly_native_definition(native.definition, assembly)
    assert assembly.cell(TASK_EFFECT_RECONCILIATION_CELL).status == "INSTALLED"

    tampered_definition = dataclasses.replace(
        native.definition,
        source=dataclasses.replace(
            native.definition.source,
            registry_metadata_is_execution_evidence=True,
        ),
    )
    try:
        validate_task_observation_assembly_native_definition(tampered_definition, assembly)
    except ValueError as exc:
        assert "forbidden authority" in str(exc)
    else:
        raise AssertionError("tampered C5 native definition was accepted")


def test_c5_assembly_registers_native_projector_source_key() -> None:
    native = compile_task_observation_native_contribution(NON_DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE)
    assert not isinstance(native, Failure)
    assembly = build_task_observation_assembly(native_definition=native.definition)
    assert assembly.cell(TASK_RUN_PROJECTION_CELL).status == "INSTALLED"
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 1
    contract = assembly.projector_registry.projectors[0]
    key = NON_DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.projector_key_map[TASK_RUN_PROJECTION_CELL]
    assert contract.key.source_ref == key.source_ref
    assert contract.key.source_incarnation == key.source_incarnation
    assert assembly.cell(TASK_RUN_PROJECTION_CELL).handler_binding_digest == (
        assembly.projector_wiring[1].registration_digest(contract)
    )


def _uow_factory() -> Callable[[], object]:
    def factory() -> object:
        raise AssertionError("assembly construction must not open a unit of work")

    return factory


def test_c4_assembly_default_is_fail_closed_for_canaries() -> None:
    assembly = build_batch_task_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=SCOPE_DIGEST,
        options=None,
    )

    assert assembly.family_id == c4.BATCH_TASK_FAMILY_ID
    assert assembly.coverage() == {
        BATCH_PLAN_CELL: "FIXTURE_CLOSURE_REQUIRED",
        BATCH_RETRY_CELL: "FIXTURE_CLOSURE_REQUIRED",
        BATCH_SUBMIT_CELL: "INSTALLED",
    }
    assert len(assembly.handlers) == 1
    assert isinstance(assembly.handlers[0], BatchTaskSubmissionStoreRehydratedHandler)
    installed = [cell for cell in assembly.cells if cell.status == "INSTALLED"]
    assert installed == [assembly.cell(BATCH_SUBMIT_CELL)]
    assert installed[0].handler_binding_digest == (assembly.handlers[0].handler_binding_digest)
    assert all(cell.handler_binding_digest is None for cell in assembly.cells if cell.status != "INSTALLED")
    assert all(rollback.status == "PRESENT" for rollback in assembly.rollback_bindings)


def test_c4_assembly_installs_canary_handlers_with_payloads() -> None:
    options = BatchTaskAssemblyOptions(
        plan_payload=plan_payload(),
        retry_payload=retry_payload(),
    )
    assembly = build_batch_task_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=SCOPE_DIGEST,
        options=options,
    )

    assert assembly.coverage() == {
        BATCH_PLAN_CELL: "INSTALLED",
        BATCH_RETRY_CELL: "INSTALLED",
        BATCH_SUBMIT_CELL: "INSTALLED",
    }
    assert len(assembly.handlers) == 3
    kinds = {type(handler) for handler in assembly.handlers}
    assert kinds == {
        BatchTaskPlanRuntimeHandler,
        BatchTaskRetryRuntimeHandler,
        BatchTaskSubmissionStoreRehydratedHandler,
    }
    digests = [handler.handler_binding_digest for handler in assembly.handlers]
    assert len(set(digests)) == len(digests)
    installed_digests = {cell.handler_binding_digest for cell in assembly.cells if cell.status == "INSTALLED"}
    assert installed_digests == set(digests)


def test_c4_assembly_installs_with_production_fixture_builder() -> None:
    scope_digest = local_assembly_scope_digest()
    options = BatchTaskAssemblyOptions(
        plan_payload=build_deterministic_plan_payload(scope_digest),
        retry_payload=build_deterministic_retry_payload(scope_digest),
    )
    assembly = build_batch_task_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=scope_digest,
        options=options,
    )
    assert assembly.coverage() == {
        BATCH_PLAN_CELL: "INSTALLED",
        BATCH_RETRY_CELL: "INSTALLED",
        BATCH_SUBMIT_CELL: "INSTALLED",
    }
    assert len(assembly.handlers) == 3


def test_c4_assembly_rejects_payload_scope_drift() -> None:
    drifted_scope = "0" * 64
    options = BatchTaskAssemblyOptions(plan_payload=plan_payload())
    try:
        build_batch_task_assembly(
            uow_factory=_uow_factory(),
            project_scope_digest=drifted_scope,
            options=options,
        )
    except ValueError as exc:
        assert "scope digest" in str(exc)
    else:
        raise AssertionError("payload scope drift must fail closed")


def test_c5_assembly_declares_projector_wiring_and_c52_gap() -> None:
    assembly = build_task_observation_assembly()

    assert assembly.family_id == TASK_OBSERVATION_FAMILY_ID
    assert assembly.coverage() == {
        TASK_SESSION_PROJECTION_CELL: "PROJECTOR_WIRING_DECLARED",
        TASK_EFFECT_RECONCILIATION_CELL: "FIXTURE_CLOSURE_REQUIRED",
        TASK_RUN_PROJECTION_CELL: "PROJECTOR_WIRING_DECLARED",
        TASK_PROCESS_PROJECTION_CELL: "PROJECTOR_WIRING_DECLARED",
    }
    assert len(assembly.projector_wiring) == 3
    assert tuple(wiring.cell_id for wiring in assembly.projector_wiring) == (TASK_PROJECTOR_CELLS)
    assert all("source key" in wiring.note for wiring in assembly.projector_wiring)
    reconciliation = assembly.cell(TASK_EFFECT_RECONCILIATION_CELL)
    assert "FIXTURE_CLOSURE_REQUIRED" in reconciliation.note
    assert "options.reconciliation_binding" in reconciliation.note
    assert TASK_EFFECT_RECONCILE_DURABLE_ATTEMPT_NODE_NOT_PROVEN in reconciliation.note
    assert reconciliation.handler_binding_digest is None
    assert all(rollback.status == "PRESENT" for rollback in assembly.rollback_bindings)


def test_c5_assembly_installs_reconciliation_route_with_binding() -> None:
    scope_digest = local_assembly_scope_digest()
    assembly = build_task_observation_assembly(
        options=TaskObservationAssemblyOptions(reconciliation_binding=build_deterministic_reconciliation_binding(scope_digest))
    )
    cell = assembly.cell(TASK_EFFECT_RECONCILIATION_CELL)
    assert cell.status == "INSTALLED"
    assert cell.handler_binding_digest == assembly.handlers[0].handler_binding_digest
    assert TASK_EFFECT_RECONCILE_DURABLE_ATTEMPT_NODE_NOT_PROVEN in cell.note
    assert tuple(wiring.cell_id for wiring in assembly.projector_wiring) == (TASK_PROJECTOR_CELLS)


def test_c5_assembly_registers_projectors_with_per_run_source_keys() -> None:
    assembly = build_task_observation_assembly(
        projector_source_keys={
            TASK_SESSION_PROJECTION_CELL: ProjectorSourceKey(
                source_ref=f"run:i1-local:{TASK_SESSION_PROJECTION_CELL}:001",
                source_incarnation=(f"incarnation:i1-local:{TASK_SESSION_PROJECTION_CELL}:001"),
            ),
            TASK_RUN_PROJECTION_CELL: ProjectorSourceKey(
                source_ref=f"run:i1-local:{TASK_RUN_PROJECTION_CELL}:001",
                source_incarnation=(f"incarnation:i1-local:{TASK_RUN_PROJECTION_CELL}:001"),
            ),
            TASK_PROCESS_PROJECTION_CELL: ProjectorSourceKey(
                source_ref=f"run:i1-local:{TASK_PROCESS_PROJECTION_CELL}:001",
                source_incarnation=(f"incarnation:i1-local:{TASK_PROCESS_PROJECTION_CELL}:001"),
            ),
        }
    )
    for cell_id in TASK_PROJECTOR_CELLS:
        cell = assembly.cell(cell_id)
        assert cell.status == "INSTALLED", cell_id
        assert cell.handler_binding_digest is not None
        assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in cell.note
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 3
    by_cell = {wiring.cell_id: wiring for wiring in assembly.projector_wiring}
    registered = {
        wiring.cell_id: wiring.registration_digest(contract)
        for wiring in assembly.projector_wiring
        for contract in assembly.projector_registry.projectors
        if contract.projection_id == wiring.projection_id
    }
    for cell_id in TASK_PROJECTOR_CELLS:
        assert assembly.cell(cell_id).handler_binding_digest == registered[cell_id]
    assert by_cell[TASK_SESSION_PROJECTION_CELL].projector_id == (AGENT_SESSION_PROJECTOR_ID)


def test_c5_assembly_supports_partial_projector_registration() -> None:
    assembly = build_task_observation_assembly(
        projector_source_keys={
            TASK_SESSION_PROJECTION_CELL: ProjectorSourceKey(
                source_ref=f"run:i1-local:{TASK_SESSION_PROJECTION_CELL}:001",
                source_incarnation=(f"incarnation:i1-local:{TASK_SESSION_PROJECTION_CELL}:001"),
            )
        }
    )
    assert assembly.cell(TASK_SESSION_PROJECTION_CELL).status == "INSTALLED"
    assert assembly.cell(TASK_RUN_PROJECTION_CELL).status == "PROJECTOR_WIRING_DECLARED"
    assert assembly.cell(TASK_PROCESS_PROJECTION_CELL).status == ("PROJECTOR_WIRING_DECLARED")
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 1


def test_c4_c5_combined_coverage_and_family_discipline() -> None:
    assemblies = (
        build_batch_task_assembly(
            uow_factory=_uow_factory(),
            project_scope_digest=SCOPE_DIGEST,
        ),
        build_task_observation_assembly(),
    )
    cells = tuple(cell for assembly in assemblies for cell in assembly.cells)

    expected_cell_order = (
        *BATCH_TASK_ASSEMBLY_CELL_IDS,
        *TASK_OBSERVATION_ASSEMBLY_CELL_IDS,
    )
    assert len(cells) == len(expected_cell_order)
    assert tuple(cell.cell_id for cell in cells) == expected_cell_order
    assert tuple(cell.family_id for cell in cells) == (
        *((c4.BATCH_TASK_FAMILY_ID,) * len(BATCH_TASK_ASSEMBLY_CELL_IDS)),
        *((TASK_OBSERVATION_FAMILY_ID,) * len(TASK_OBSERVATION_ASSEMBLY_CELL_IDS)),
    )
