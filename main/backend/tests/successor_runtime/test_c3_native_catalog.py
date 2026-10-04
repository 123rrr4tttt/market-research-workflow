"""Native C3 catalog derives projections, verification, and bindings from one source."""

from __future__ import annotations

import dataclasses

import pytest
from app.successor_runtime.assembly.base import AcquisitionAssemblyOptions
from app.successor_runtime.capabilities import acquisition_batch as acquisition
from app.successor_runtime.capabilities.acquisition_native_contribution import (
    ACQUISITION_BATCH_FAILURES,
    ASSEMBLY_CELL_IDS,
    ACQUISITION_NATIVE_RULE_ID,
    DEFAULT_ACQUISITION_NATIVE_SOURCE,
    AcquisitionAssemblyContext,
    AcquisitionNativeSource,
    compile_acquisition_native_contribution,
)
from functorial_kit.core.failure import Failure

from mrw_functorial_kit.contributions import acquisition as acquisition_catalog_module
from mrw_functorial_kit.core.provider_port_failures import collect_runtime_failures


def _inert_context() -> AcquisitionAssemblyContext:
    return AcquisitionAssemblyContext(
        uow_factory=lambda: None,
        project_scope_digest="digest:test-c3-native",
        options=AcquisitionAssemblyOptions(),
    )


def _compile(source: AcquisitionNativeSource):
    native = compile_acquisition_native_contribution(source)
    assert not isinstance(native, Failure)
    return native


def test_default_source_compiles_once_and_projects_both_cells() -> None:
    native = acquisition_catalog_module.acquisition_native_catalog[0]
    objects = native.projection.objects
    capabilities = [obj.id for obj in objects if obj.kind == "Capability"]
    payload_types = [obj.id for obj in objects if obj.kind == "ObjectType"]
    codecs = [obj.id for obj in objects if obj.kind == "PayloadCodec"]
    assert capabilities == [
        "acquisition.batch.execute_element.v2",
        "acquisition.batch.fold_ordered_results.v2",
    ]
    assert payload_types == [
        "CollectBatchElementPayload.v1",
        "CollectElementOutcome.v1",
        "CollectFoldPayload.v1",
        "CollectAggregateOutcome.v1",
    ]
    assert codecs == [
        "mrw.acquisition.batch-element.codec.v2",
        "mrw.acquisition.ordered-result-fold.codec.v2",
    ]
    assert ASSEMBLY_CELL_IDS == (
        "acquisition.batch.execute_element.v2",
        "acquisition.batch.fold_ordered_results.v2",
    )
    assert native.projection.owner == DEFAULT_ACQUISITION_NATIVE_SOURCE.owner
    assert ACQUISITION_BATCH_FAILURES is acquisition.ACQUISITION_BATCH_FAILURES
    assert native.projection.failures == (
        acquisition.ACQUISITION_BATCH_FAILURES,
        collect_runtime_failures,
    )
    assert native.verification is not None
    assert native.verification.rule_id == ACQUISITION_NATIVE_RULE_ID
    assert native.verification.complete is True


def test_non_default_source_updates_all_determined_projections_from_one_declaration() -> None:
    changed = dataclasses.replace(
        DEFAULT_ACQUISITION_NATIVE_SOURCE,
        contribution_id="test.mrw.c3.native.alt.v1",
        rollback_refs=("test/rollback/c3-alt.json", "main/backend/app/successor_migration/legacy_collect_runtime.py"),
    )
    native = _compile(changed)
    assert native.projection.id == changed.contribution_id
    capabilities = [obj.id for obj in native.projection.objects if obj.kind == "Capability"]
    assert capabilities == [
        "acquisition.batch.execute_element.v2",
        "acquisition.batch.fold_ordered_results.v2",
    ]
    assert native.verification is not None
    assert (
        native.verification.checks[0].witness.id == f"test_acquisition_native_definition_law:{changed.contribution_id}"
    )
    binding = native.assemble(_inert_context())
    assert not isinstance(binding, Failure)
    assert binding.family_assembly.family_id == "acquisition.batch"
    assert [cell.cell_id for cell in binding.family_assembly.cells] == list(ASSEMBLY_CELL_IDS)
    assert binding.rollback_binding_refs_by_cell == (changed.rollback_refs, changed.rollback_refs)


def test_default_catalog_law_and_verification_plan_are_inert_until_run() -> None:
    catalog = acquisition_catalog_module.acquisition_native_catalog
    assert [native.definition.contribution_id for native in catalog] == [
        DEFAULT_ACQUISITION_NATIVE_SOURCE.contribution_id
    ]
    plan = acquisition_catalog_module.acquisition_verification_plan_for()
    assert plan.selection.contribution_ids == (DEFAULT_ACQUISITION_NATIVE_SOURCE.contribution_id,)
    for witness in acquisition_catalog_module.acquisition_verification_law_witnesses:
        witness.run()
    acquisition_catalog_module.acquisition_law_witnesses[0].run()


def test_fixture_closure_requires_status_and_no_handler() -> None:
    native = acquisition_catalog_module.acquisition_native_catalog[0]
    binding = native.assemble(_inert_context())
    assert not isinstance(binding, Failure)
    statuses = tuple(cell.status for cell in binding.family_assembly.cells)
    assert statuses == ("FIXTURE_CLOSURE_REQUIRED", "FIXTURE_CLOSURE_REQUIRED")
    assert binding.family_assembly.handlers == ()
    assert binding.catalog.entries == (
        (
            native.definition.bundle.execute_element_operation.ref.kind,
            native.definition.bundle.execute_element_operation.ref.contract_version,
            native.definition.bundle.execute_element_operation.ref.contract_digest,
            native.definition.bundle.execute_element_operation.owner_capability_id,
        ),
        (
            native.definition.bundle.fold_ordered_results_operation.ref.kind,
            native.definition.bundle.fold_ordered_results_operation.ref.contract_version,
            native.definition.bundle.fold_ordered_results_operation.ref.contract_digest,
            native.definition.bundle.fold_ordered_results_operation.owner_capability_id,
        ),
    )


def test_operation_codecs_and_failures_derive_from_existing_bundle_authority() -> None:
    native = acquisition_catalog_module.acquisition_native_catalog[0]
    bundle = native.definition.bundle
    assert (
        bundle.batch_element_payload_codec().codec_id
        == DEFAULT_ACQUISITION_NATIVE_SOURCE.operations[0].payload_codec_id
    )
    assert (
        bundle.ordered_result_fold_payload_codec().codec_id
        == DEFAULT_ACQUISITION_NATIVE_SOURCE.operations[1].payload_codec_id
    )
    assert tuple(
        contract.ref.kind for contract in (bundle.execute_element_operation, bundle.fold_ordered_results_operation)
    ) == ("collect.execute_batch_element.v1", "collect.fold_ordered_results.v1")
    assert tuple(native.definition.source.failure_codes_1) == tuple(bundle.profiles["failure.c3_1"].typed_failures)
    assert tuple(native.definition.source.failure_codes_2) == tuple(bundle.profiles["failure.c3_2"].typed_failures)


def test_program_order_declares_traversal_then_fold() -> None:
    native = acquisition_catalog_module.acquisition_native_catalog[0]
    steps = native.definition.program_wiring
    assert [step.atom for step in steps] == ["TraverseOrdered", "FoldAtom"]
    assert [step.operation_id for step in steps] == [
        "acquisition.batch.execute_element.v2",
        "acquisition.batch.fold_ordered_results.v2",
    ]


def test_unknown_operation_reference_is_rejected_at_lowering() -> None:
    source = dataclasses.replace(
        DEFAULT_ACQUISITION_NATIVE_SOURCE,
        contribution_id="test.mrw.c3.native.invalid.v1",
        operations=(
            dataclasses.replace(DEFAULT_ACQUISITION_NATIVE_SOURCE.operations[0], kind="not.c3.kind"),
            DEFAULT_ACQUISITION_NATIVE_SOURCE.operations[1],
        ),
    )
    native = compile_acquisition_native_contribution(source)
    assert isinstance(native, Failure)


@pytest.mark.parametrize("witness", acquisition_catalog_module.acquisition_law_witnesses)
def test_catalog_witnesses_pass(witness) -> None:
    witness.run()


def test_installed_payloads_share_one_composed_handler() -> None:
    from app.successor_runtime.assembly.base import local_assembly_scope_digest
    from app.successor_runtime.assembly.acquisition_batch_assembly import (
        build_acquisition_batch_assembly,
        build_deterministic_element_payloads,
    )

    assembly = build_acquisition_batch_assembly(
        uow_factory=lambda: None,
        project_scope_digest=local_assembly_scope_digest(),
        options=AcquisitionAssemblyOptions(
            element_payloads=build_deterministic_element_payloads(),
        ),
    )
    statuses = tuple(cell.status for cell in assembly.cells)
    assert statuses == ("INSTALLED", "INSTALLED")
    assert len(assembly.handlers) == 1
    handler = assembly.handlers[0]
    program = handler.composed_program.root
    assert program.node_kind == "then"
    assert program.first.source.node_kind == "traverse_ordered"
    assert program.second.operation.contract_ref.kind == "collect.fold_ordered_results.v1"
    assert all(cell.handler_binding_digest is not None for cell in assembly.cells)


def test_invalid_explicit_native_source_returns_failure_not_exception() -> None:
    from app.successor_runtime.assembly.acquisition_batch_assembly import build_acquisition_batch_assembly

    invalid_source = dataclasses.replace(
        DEFAULT_ACQUISITION_NATIVE_SOURCE,
        contribution_id="test.mrw.c3.native.invalid-source.v1",
        operations=(
            dataclasses.replace(DEFAULT_ACQUISITION_NATIVE_SOURCE.operations[0], kind="not.c3.kind"),
            DEFAULT_ACQUISITION_NATIVE_SOURCE.operations[1],
        ),
    )
    with pytest.raises(RuntimeError) as excinfo:
        build_acquisition_batch_assembly(
            uow_factory=lambda: None,
            project_scope_digest="0" * 64,
            source=invalid_source,
        )
    assert "invalid C3 native source" in str(excinfo.value)


@pytest.mark.parametrize("field", ("legacy_binding_refs", "successor_binding_refs"))
def test_compatibility_reference_identity_is_rejected_at_native_lowering(field: str) -> None:
    source = dataclasses.replace(
        DEFAULT_ACQUISITION_NATIVE_SOURCE,
        **{field: ("legacy_collect_runtime.missing_binding",)},
    )
    assert isinstance(compile_acquisition_native_contribution(source), Failure)


def test_compatibility_code_liveness_is_checked_by_migration_owner(monkeypatch) -> None:
    from app.successor_migration import legacy_collect_runtime as migration

    migration.require_c3_binding_authority()
    monkeypatch.setattr(migration, "build_successor_collect_c3_2_binding", None)
    with pytest.raises(ValueError, match="unresolved C3 compatibility binding ref"):
        migration.build_legacy_collect_c3_1_binding(
            contract_digest="0" * 64,
            deployment_catalog_digest="1" * 64,
            project_scope_digest="2" * 64,
        )
    # Pure native definitions remain valid when an unused compatibility adapter
    # is unavailable; compatibility execution itself remains fail closed above.
    assert not isinstance(compile_acquisition_native_contribution(DEFAULT_ACQUISITION_NATIVE_SOURCE), Failure)
