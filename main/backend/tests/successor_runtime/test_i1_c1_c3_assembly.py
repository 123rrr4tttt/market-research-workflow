"""Non-PostgreSQL structural assertions for the I1 C1/C2/C3 assemblies."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from app.successor_migration.legacy_collect_runtime import (
    build_successor_collect_c3_2_binding,
)
from app.successor_migration.legacy_source_library import (
    build_successor_source_library_c2_1_binding,
)
from app.successor_runtime.assembly.base import (
    C3AssemblyOptions,
    ProjectorSourceKey,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.c1_assembly import build_c1_assembly
from app.successor_runtime.assembly.c2_assembly import build_c2_assembly
from app.successor_runtime.assembly.c3_assembly import (
    build_c3_assembly,
    build_deterministic_element_payloads,
)
from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities import source_library_c2_1 as c21
from app.successor_runtime.capabilities import source_library_c2_2 as c22
from app.successor_runtime.capabilities import source_library_c2_3 as c23
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


def _uow_factory() -> object:
    return None


def _scope_digest() -> str:
    return local_assembly_scope_digest()


def _c3_element_payloads(project_key: str = "project:c3-assembly-test"):
    request_ref = c3.build_collect_request_ref(
        request_id="request:c3-assembly-test",
        project_key=project_key,
        channel="search.market",
    )
    snapshot = c3.CollectLegacyRequestSnapshot(
        schema_version=c3.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow="collect",
        channel="search.market",
        project_key=project_key,
        query_terms=("t1", "t2"),
        urls=(),
        limit=80,
        options=c3.freeze_json_object({}),
        source_context=c3.freeze_json_object({}),
        snapshot_digest="",
    )
    policy = c3.CollectResourcePolicy(
        schema_ref=c3.COLLECT_RESOURCE_POLICY_SCHEMA_REF,
        max_parallelism=2,
        deadline_seconds=60,
        cancellation="COORDINATED",
        backpressure=True,
        provider_concurrency_key="search.market",
        policy_digest="",
    )
    plan = c3.build_collect_batch_plan(
        request_ref=request_ref,
        snapshot=snapshot,
        plan_id="plan:c3-assembly-test",
        resource_policy=policy,
        authority_scope_ref="project:c3-assembly-test",
    )
    return tuple(
        c3.collect_batch_element_payload_from_dicts(
            request_ref=request_ref,
            request_snapshot=snapshot,
            element=plan.elements[index],
            resource_policy=policy,
            authority_scope_ref="project:c3-assembly-test",
        )
        for index in range(len(plan.elements))
    )


def test_c1_assembly_installs_kernel_wiring_for_c12_and_c13() -> None:
    assembly = build_c1_assembly()

    assert assembly.family_id == "C1"
    assert assembly.coverage() == {
        "C1.1": "INSTALLED",
        "C1.2": "INSTALLED",
        "C1.3": "INSTALLED",
    }
    assert len(assembly.handlers) == 1
    c11 = assembly.cell("C1.1")
    assert c11.handler_binding_digest == assembly.handlers[0].handler_binding_digest
    assert c11.rollback_binding_refs
    kernel = {wiring.cell_id: wiring for wiring in assembly.kernel_wiring}
    assert set(kernel) == {"C1.2", "C1.3"}
    assert kernel["C1.2"].kernel_id == "mrw.successor.runtime.c1-2.node.v1"
    assert kernel["C1.3"].kernel_id == "mrw.successor.store.c1-3.replay.v1"
    for cell_id in ("C1.2", "C1.3"):
        assert (
            assembly.cell(cell_id).handler_binding_digest
            == kernel[cell_id].binding_digest
        )
        assert kernel[cell_id].binding_refs
    rollback = {item.cell_id: item.status for item in assembly.rollback_bindings}
    assert rollback == {
        "C1.1": "PRESENT",
        "C1.2": "PRESENT",
        "C1.3": "PRESENT",
    }


def _c1_1_binding(handler: object) -> InterpreterBinding:
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
    binding = _c1_1_binding(handler)
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work:i1-c1-1:001",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="i1-local-c1",
        run_id="run:i1-c1-1:001",
        step_id="step:c1-1:compile",
        step_role=CompiledStepRole.EFFECT,
        capability_id="workflow_graph.c1.1",
        operation_contract_ref=OperationContractRef(
            kind="workflow.vector_search.v1",
            contract_version="1",
            contract_digest=handler.operation_contract_digest,
        ),
        operation_contract_digest=handler.operation_contract_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            "mrw.successor.c1.legacy-dsl.v1",
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
    assembly = build_c1_assembly()
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
    assert failed.failure_code == "C1_DSL_MALFORMED_PAYLOAD"
    assert failed.reconciliation_hint is None


def test_c2_assembly_installs_one_exact_handler_per_installed_cell() -> None:
    assembly = build_c2_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=_scope_digest(),
    )

    assert assembly.family_id == "C2"
    assert assembly.coverage() == {
        "C2.1": "INSTALLED",
        "C2.2": "INSTALLED",
        "C2.3": "INSTALLED",
        "C2.4": "PROJECTOR_WIRING_DECLARED",
    }
    assert len(assembly.handlers) == 3
    assert len({handler.handler_binding_digest for handler in assembly.handlers}) == 3
    handler_digests = {handler.handler_binding_digest for handler in assembly.handlers}
    for cell_id in ("C2.1", "C2.2", "C2.3"):
        cell = assembly.cell(cell_id)
        assert cell.status == "INSTALLED"
        assert cell.handler_binding_digest in handler_digests
    assert len(assembly.projector_wiring) == 1
    assert assembly.projector_wiring[0].cell_id == "C2.4"
    assert assembly.projector_wiring[0].source_kind == "RUNTIME_JOURNAL"
    assert "LIVE_PROVIDER_DIMENSION_UNRESOLVED" in assembly.cell("C2.3").note


def test_c2_assembly_registers_projector_with_per_run_source_key() -> None:
    assembly = build_c2_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=_scope_digest(),
        projector_source_keys={
            "C2.4": ProjectorSourceKey(
                source_ref="run:i1-local:C2.4:001",
                source_incarnation="incarnation:i1-local:C2.4:001",
            )
        },
    )
    cell = assembly.cell("C2.4")
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
    assembly = build_c2_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=project_scope_digest,
    )
    by_cell = {handler.handler_binding_digest: handler for handler in assembly.handlers}

    c2_1_ref = c21.build_source_library_c2_1_catalog(
        c21.build_source_library_c2_1_bundle()
    ).lookup(c21.SOURCE_LIBRARY_C2_1_KIND)
    assert c2_1_ref is not None
    c2_1_binding = build_successor_source_library_c2_1_binding(
        contract_digest=c2_1_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
    )
    assert c2_1_binding.binding_digest in by_cell

    c2_2_ref = c22.build_source_library_c2_2_catalog(
        c22.build_source_library_c2_2_bundle()
    ).lookup(c22.SOURCE_LIBRARY_C2_2_PROTOCOL_SEARCH_KIND)
    assert c2_2_ref is not None
    c2_2_binding = build_successor_c2_2_binding(
        contract_digest=c2_2_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
    )
    assert c2_2_binding.binding_digest in by_cell

    c2_3_ref = c23.build_source_library_c2_3_catalog(
        c23.build_source_library_c2_3_bundle()
    ).lookup(c23.SOURCE_LIBRARY_C2_3_KIND)
    assert c2_3_ref is not None
    c2_3_binding = build_successor_c2_3_binding(
        contract_digest=c2_3_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
    )
    assert c2_3_binding.binding_digest in by_cell


def test_c3_assembly_without_payloads_requires_fixture_closure() -> None:
    assembly = build_c3_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=_scope_digest(),
    )

    assert assembly.family_id == "C3"
    assert assembly.coverage() == {
        "C3.1": "FIXTURE_CLOSURE_REQUIRED",
        "C3.2": "FIXTURE_CLOSURE_REQUIRED",
    }
    assert assembly.handlers == ()
    for cell in assembly.cells:
        assert cell.handler_binding_digest is None


def test_c3_assembly_with_payloads_installs_shared_composed_handler() -> None:
    project_scope_digest = _scope_digest()
    assembly = build_c3_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=project_scope_digest,
        options=C3AssemblyOptions(
            element_payloads=_c3_element_payloads(),
        ),
    )

    assert assembly.family_id == "C3"
    assert assembly.coverage() == {
        "C3.1": "INSTALLED",
        "C3.2": "INSTALLED",
    }
    assert len(assembly.handlers) == 1
    handler = assembly.handlers[0]
    assert (
        handler.handler_binding_digest == assembly.cell("C3.1").handler_binding_digest
    )
    assert (
        handler.handler_binding_digest == assembly.cell("C3.2").handler_binding_digest
    )

    bundle = c3.build_collect_c3_bundle()
    fold_ref = bundle.operation_c3_2.ref
    expected_binding = build_successor_collect_c3_2_binding(
        contract_digest=fold_ref.contract_digest,
        deployment_catalog_digest=c3.deployment_catalog_digest(),
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )
    assert handler.handler_binding_digest == expected_binding.binding_digest
    assert handler.provider_calls == 0


def test_c3_assembly_installs_with_production_fixture_builder() -> None:
    project_scope_digest = _scope_digest()
    assembly = build_c3_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=project_scope_digest,
        options=C3AssemblyOptions(
            element_payloads=build_deterministic_element_payloads(),
        ),
    )
    assert assembly.coverage() == {
        "C3.1": "INSTALLED",
        "C3.2": "INSTALLED",
    }
    assert len(assembly.handlers) == 1
    assert assembly.handlers[0].provider_calls == 0
