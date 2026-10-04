"""Non-PostgreSQL structural assertions for the I1 C1/C2/C3 assemblies."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from app.successor_migration.legacy_source_library import (
    build_successor_source_library_c2_1_binding,
)
from app.successor_runtime.assembly.base import (
    AcquisitionAssemblyOptions,
    ProjectorSourceKey,
    local_assembly_scope_digest,
    successor_binding,
)
from app.successor_runtime.assembly.workflow_assembly import build_workflow_assembly
from app.successor_runtime.assembly.source_assembly import build_source_assembly
from app.successor_runtime.assembly.acquisition_batch_assembly import (
    ACQUISITION_BATCH_FAMILY_ID,
    build_acquisition_batch_assembly,
    build_deterministic_element_payloads,
)
from app.successor_runtime.capabilities import acquisition_batch as acquisition
from app.successor_runtime.capabilities import source_resolution as c21
from app.successor_runtime.capabilities import source_planning as c22
from app.successor_runtime.capabilities import source_provider_acquisition as c23
from app.successor_runtime.capabilities.workflow_native_contribution import (
    ASSEMBLY_CELL_IDS as WORKFLOW_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.capabilities.workflow_native_contribution import (
    DEFAULT_WORKFLOW_NATIVE_SOURCE,
)
from app.successor_runtime.capabilities.acquisition_native_contribution import (
    ASSEMBLY_CELL_IDS as ACQUISITION_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.capabilities.acquisition_batch_interpreters import (
    authority_requirement_digest,
    successor_fold_ordered_results_interpreter_profile_digest,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    ASSEMBLY_CELL_IDS as SOURCE_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    SOURCE_FAMILY_ID,
)
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    InterpreterOutcome,
    NodeIdentity,
    RuntimeExecutionContext,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.source_library_c2_23_canary import (
    build_successor_c2_2_binding,
    build_successor_c2_3_binding,
)

(
    WORKFLOW_COMPILE_CELL,
    WORKFLOW_RUNTIME_OBSERVE_CELL,
    WORKFLOW_STATE_RESTORE_CELL,
) = WORKFLOW_ASSEMBLY_CELL_IDS
(
    SOURCE_RESOLVE_CELL,
    SOURCE_PLAN_CELL,
    SOURCE_PROVIDER_EFFECT_CELL,
    SOURCE_TERMINAL_PROJECTION_CELL,
) = SOURCE_ASSEMBLY_CELL_IDS


def _uow_factory() -> object:
    return None


def _scope_digest() -> str:
    return local_assembly_scope_digest()


def _c3_element_payloads(project_key: str = "project:c3-assembly-test"):
    request_ref = acquisition.build_collect_request_ref(
        request_id="request:c3-assembly-test",
        project_key=project_key,
        channel="search.market",
    )
    snapshot = acquisition.CollectLegacyRequestSnapshot(
        schema_version=acquisition.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow="collect",
        channel="search.market",
        project_key=project_key,
        query_terms=("t1", "t2"),
        urls=(),
        limit=80,
        options=acquisition.freeze_json_object({}),
        source_context=acquisition.freeze_json_object({}),
        snapshot_digest="",
    )
    policy = acquisition.CollectResourcePolicy(
        schema_ref=acquisition.COLLECT_RESOURCE_POLICY_SCHEMA_REF,
        max_parallelism=2,
        deadline_seconds=60,
        cancellation="COORDINATED",
        backpressure=True,
        provider_concurrency_key="search.market",
        policy_digest="",
    )
    plan = acquisition.build_collect_batch_plan(
        request_ref=request_ref,
        snapshot=snapshot,
        plan_id="plan:c3-assembly-test",
        resource_policy=policy,
        authority_scope_ref="project:c3-assembly-test",
    )
    return tuple(
        acquisition.collect_batch_element_payload_from_dicts(
            request_ref=request_ref,
            request_snapshot=snapshot,
            element=plan.elements[index],
            resource_policy=policy,
            authority_scope_ref="project:c3-assembly-test",
        )
        for index in range(len(plan.elements))
    )


def test_c1_assembly_installs_kernel_wiring_for_c12_and_c13() -> None:
    assembly = build_workflow_assembly()

    assert assembly.family_id == DEFAULT_WORKFLOW_NATIVE_SOURCE.family_id
    assert tuple(assembly.coverage()) == WORKFLOW_ASSEMBLY_CELL_IDS
    assert set(assembly.coverage().values()) == {"INSTALLED"}
    assert len(assembly.handlers) == 1
    compile_cell = assembly.cell(WORKFLOW_COMPILE_CELL)
    assert compile_cell.handler_binding_digest == assembly.handlers[0].handler_binding_digest
    assert compile_cell.rollback_binding_refs
    kernel = {wiring.cell_id: wiring for wiring in assembly.kernel_wiring}
    assert tuple(kernel) == (
        WORKFLOW_RUNTIME_OBSERVE_CELL,
        WORKFLOW_STATE_RESTORE_CELL,
    )
    assert kernel[WORKFLOW_RUNTIME_OBSERVE_CELL].kernel_id == (DEFAULT_WORKFLOW_NATIVE_SOURCE.cells[1].kernel_id)
    assert kernel[WORKFLOW_STATE_RESTORE_CELL].kernel_id == (DEFAULT_WORKFLOW_NATIVE_SOURCE.cells[2].kernel_id)
    for cell_id in WORKFLOW_ASSEMBLY_CELL_IDS[1:]:
        assert assembly.cell(cell_id).handler_binding_digest == kernel[cell_id].binding_digest
        assert kernel[cell_id].binding_refs
    rollback = {item.cell_id: item.status for item in assembly.rollback_bindings}
    assert rollback == dict.fromkeys(WORKFLOW_ASSEMBLY_CELL_IDS, "PRESENT")


def _workflow_compile_binding(handler: object) -> InterpreterBinding:
    binding = InterpreterBinding.from_content(
        operation_contract_digest=handler.operation_contract_digest,
        interpreter_profile_digest=handler.interpreter_profile_digest,
        deployment_catalog_digest=handler.deployment_catalog_digest,
        runtime_protocol_version="1",
        project_scope_digest=local_assembly_scope_digest(),
        resource_policy_epoch=1,
        authority_requirement_digest=handler.authority_requirement_digest,
    )
    assert binding.binding_digest == handler.handler_binding_digest
    return binding


def _c1_1_assignment(handler: object) -> RuntimeAssignment:
    binding = _workflow_compile_binding(handler)
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work:i1-c1-1:001",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="i1-local-c1",
        run_id="run:i1-c1-1:001",
        step_id="step:c1-1:compile",
        step_role=CompiledStepRole.EFFECT,
        capability_id=WORKFLOW_COMPILE_CELL,
        operation_contract_ref=OperationContractRef(
            kind="workflow.vector_search.v1",
            contract_version="1",
            contract_digest=handler.operation_contract_digest,
        ),
        operation_contract_digest=handler.operation_contract_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            "mrw.workflow.definition.compile.v2",
            ReturnContract(
                success_modes=("SUCCEEDED",),
                failure_modes=("FAILED",),
                admission_required=False,
                wait_modes=("WAIT",),
                cancel_modes=("CANCELED",),
            ),
        ),
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=binding.binding_digest,
        deployment_catalog_digest=handler.deployment_catalog_digest,
        execution_epoch=1,
        incarnation="inc:i1-c1-1:001",
        input_refs=(),
        queue_eligibility_digest=("0" * 64),
        resource_policy_epoch=1,
        claim_authority_epoch=1,
        claim_policy_digest=("0" * 64),
        expected_step_revision=0,
        trace_id="trace:i1-c1-1:001",
    )


def _c1_1_claim(handler: object, assignment: RuntimeAssignment) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest=("0" * 64),
        lease_token="lease:i1-c1-1",
        lease_expires_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
        node_id="node:i1-c1-1",
        node_profile_digest=("0" * 64),
        authority_digest=("0" * 64),
        interpreter_profile_digest=handler.interpreter_profile_digest,
    )


def _c1_1_context() -> RuntimeExecutionContext:
    return RuntimeExecutionContext(
        node=NodeIdentity(
            node_id="node:i1-c1-1",
            incarnation="node-inc:i1-c1-1",
            started_at=datetime(2026, 9, 2, 0, 0, tzinfo=UTC),
        ),
        observed_at=datetime(2026, 9, 2, 0, 0, tzinfo=UTC),
    )


def test_c1_1_route_returns_typed_succeeded_and_failed_outcomes() -> None:
    assembly = build_workflow_assembly()
    handler = assembly.handlers[0]
    assignment = _c1_1_assignment(handler)
    claim = _c1_1_claim(handler, assignment)
    context = _c1_1_context()

    succeeded = handler.execute(assignment, claim, context)
    assert isinstance(succeeded, InterpreterOutcome)
    assert succeeded.disposition is EffectDisposition.SUCCEEDED
    assert succeeded.result_digest is not None

    malformed = replace(handler, payload={"nodes": "not-a-list"})
    malformed_assignment = _c1_1_assignment(malformed)
    malformed_claim = _c1_1_claim(malformed, malformed_assignment)
    failed = malformed.execute(malformed_assignment, malformed_claim, context)
    assert isinstance(failed, InterpreterOutcome)
    assert failed.disposition is EffectDisposition.FAILED
    assert failed.failure_code == "WORKFLOW_DSL_MALFORMED_PAYLOAD"
    assert failed.reconciliation_hint is None


def test_c2_assembly_installs_one_exact_handler_per_installed_cell() -> None:
    assembly = build_source_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=_scope_digest(),
    )

    assert assembly.family_id == SOURCE_FAMILY_ID
    assert assembly.coverage() == {
        SOURCE_RESOLVE_CELL: "INSTALLED",
        SOURCE_PLAN_CELL: "INSTALLED",
        SOURCE_PROVIDER_EFFECT_CELL: "INSTALLED",
        SOURCE_TERMINAL_PROJECTION_CELL: "PROJECTOR_WIRING_DECLARED",
    }
    assert len(assembly.handlers) == 6
    assert len({handler.handler_binding_digest for handler in assembly.handlers}) == 6
    handler_digests = {handler.handler_binding_digest for handler in assembly.handlers}
    for cell_id in SOURCE_ASSEMBLY_CELL_IDS[:3]:
        cell = assembly.cell(cell_id)
        assert cell.status == "INSTALLED"
        assert cell.handler_binding_digest in handler_digests
    assert len(assembly.projector_wiring) == 1
    assert assembly.projector_wiring[0].cell_id == SOURCE_TERMINAL_PROJECTION_CELL
    assert assembly.projector_wiring[0].source_kind == "RUNTIME_JOURNAL"
    assert "LIVE_PROVIDER_DIMENSION_UNRESOLVED" in assembly.cell(SOURCE_PROVIDER_EFFECT_CELL).note


def test_c2_assembly_registers_projector_with_per_run_source_key() -> None:
    assembly = build_source_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=_scope_digest(),
        projector_source_keys={
            SOURCE_TERMINAL_PROJECTION_CELL: ProjectorSourceKey(
                source_ref=f"run:i1-local:{SOURCE_TERMINAL_PROJECTION_CELL}:001",
                source_incarnation=(f"incarnation:i1-local:{SOURCE_TERMINAL_PROJECTION_CELL}:001"),
            )
        },
    )
    cell = assembly.cell(SOURCE_TERMINAL_PROJECTION_CELL)
    assert cell.status == "INSTALLED"
    assert cell.handler_binding_digest is not None
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 1
    wiring = assembly.projector_wiring[0]
    contract = assembly.projector_registry.projectors[0]
    assert cell.handler_binding_digest == wiring.registration_digest(contract)
    assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in cell.note


def test_c2_installed_digests_match_existing_binding_builders() -> None:
    project_scope_digest = _scope_digest()
    deployment_catalog_digest = c21.deployment_catalog_digest()
    assembly = build_source_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=project_scope_digest,
    )
    by_cell = {handler.handler_binding_digest: handler for handler in assembly.handlers}

    c2_1_ref = c21.build_source_resolution_catalog(c21.build_source_resolution_bundle()).lookup(
        c21.SOURCE_RESOLUTION_KIND
    )
    assert c2_1_ref is not None
    c2_1_binding = build_successor_source_library_c2_1_binding(
        contract_digest=c2_1_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
        runtime_protocol_version="1",
    )
    assert c2_1_binding.binding_digest in by_cell

    c2_2_catalog = c22.build_source_planning_catalog(
        c22.build_source_planning_bundle()
    )
    for kind in c22.SOURCE_PLANNING_KINDS:
        c2_2_ref = c2_2_catalog.lookup(kind)
        assert c2_2_ref is not None
        c2_2_binding = build_successor_c2_2_binding(
            contract_digest=c2_2_ref.contract_digest,
            deployment_catalog_digest=deployment_catalog_digest,
            project_scope_digest=project_scope_digest,
            runtime_protocol_version="1",
        )
        assert c2_2_binding.binding_digest in by_cell

    c2_3_ref = c23.build_source_provider_acquisition_catalog(c23.build_source_provider_acquisition_bundle()).lookup(
        c23.SOURCE_PROVIDER_ACQUISITION_KIND
    )
    assert c2_3_ref is not None
    c2_3_binding = build_successor_c2_3_binding(
        contract_digest=c2_3_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
        runtime_protocol_version="1",
    )
    assert c2_3_binding.binding_digest in by_cell


def test_c3_assembly_without_payloads_requires_fixture_closure() -> None:
    assembly = build_acquisition_batch_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=_scope_digest(),
    )

    assert assembly.family_id == ACQUISITION_BATCH_FAMILY_ID
    assert assembly.coverage() == {
        ACQUISITION_ASSEMBLY_CELL_IDS[0]: "FIXTURE_CLOSURE_REQUIRED",
        ACQUISITION_ASSEMBLY_CELL_IDS[1]: "FIXTURE_CLOSURE_REQUIRED",
    }
    assert assembly.handlers == ()
    for cell in assembly.cells:
        assert cell.handler_binding_digest is None


def test_c3_assembly_with_payloads_installs_shared_composed_handler() -> None:
    project_scope_digest = _scope_digest()
    assembly = build_acquisition_batch_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=project_scope_digest,
        options=AcquisitionAssemblyOptions(
            element_payloads=_c3_element_payloads(),
        ),
    )

    assert assembly.family_id == ACQUISITION_BATCH_FAMILY_ID
    assert assembly.coverage() == {
        ACQUISITION_ASSEMBLY_CELL_IDS[0]: "INSTALLED",
        ACQUISITION_ASSEMBLY_CELL_IDS[1]: "INSTALLED",
    }
    assert len(assembly.handlers) == 1
    handler = assembly.handlers[0]
    assert handler.handler_binding_digest == assembly.cell(ACQUISITION_ASSEMBLY_CELL_IDS[0]).handler_binding_digest
    assert handler.handler_binding_digest == assembly.cell(ACQUISITION_ASSEMBLY_CELL_IDS[1]).handler_binding_digest

    bundle = acquisition.build_acquisition_batch_bundle()
    fold_ref = bundle.fold_ordered_results_operation.ref
    expected_binding = successor_binding(
        operation_contract_digest=fold_ref.contract_digest,
        interpreter_profile_digest=successor_fold_ordered_results_interpreter_profile_digest(),
        deployment_catalog_digest=acquisition.deployment_catalog_digest(),
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=authority_requirement_digest(fold_ref.kind),
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )
    assert handler.handler_binding_digest == expected_binding.binding_digest
    assert handler.provider_calls == 0


def test_c3_assembly_installs_with_production_fixture_builder() -> None:
    project_scope_digest = _scope_digest()
    assembly = build_acquisition_batch_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=project_scope_digest,
        options=AcquisitionAssemblyOptions(
            element_payloads=build_deterministic_element_payloads(),
        ),
    )
    assert assembly.coverage() == {
        ACQUISITION_ASSEMBLY_CELL_IDS[0]: "INSTALLED",
        ACQUISITION_ASSEMBLY_CELL_IDS[1]: "INSTALLED",
    }
    assert len(assembly.handlers) == 1
    assert assembly.handlers[0].provider_calls == 0
