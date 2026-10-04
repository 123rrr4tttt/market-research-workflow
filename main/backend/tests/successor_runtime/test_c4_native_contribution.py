"""Focused native C4 catalog laws: slot order, codec identity, effect boundary."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

from app.successor_runtime.assembly.base import (
    BatchTaskAssemblyOptions as BatchTaskAssemblyOptions,
)
from app.successor_runtime.capabilities import batch_task
from app.successor_runtime.capabilities.batch_task_native_contribution import (
    ASSEMBLY_CELL_IDS,
    BATCH_TASK_FAILURES,
    BatchTaskAssemblyContext,
    DEFAULT_BATCH_TASK_NATIVE_SOURCE,
    compile_batch_task_native_contribution,
    validate_batch_task_native_binding,
)
from functorial_kit.core.failure import Failure
from mrw_functorial_kit.contributions.batch import (
    batch_law_witnesses as batch_task_law_witnesses,
    batch_native_catalog as batch_task_native_catalog,
)


def _native():
    native = compile_batch_task_native_contribution(DEFAULT_BATCH_TASK_NATIVE_SOURCE)
    assert not isinstance(native, Failure)
    return native


def test_default_c4_native_source_preserves_ordered_slots_and_codecs() -> None:
    native = _native()
    definition = native.definition
    assert definition.source.slots == ("PLAN", "RETRY", "SUBMIT")
    assert [operation.ref.kind for operation in definition.bundle.operations] == [
        batch_task.BATCH_PLAN_KIND,
        batch_task.RETRY_REDUCE_KIND,
        batch_task.SUBMISSION_KIND,
    ]
    assert [
        operation.codec.codec_id for operation in definition.operations
    ] == [
        batch_task.BATCH_PLAN_PAYLOAD_CODEC_ID,
        batch_task.RETRY_REDUCER_PAYLOAD_CODEC_ID,
        batch_task.SUBMISSION_PAYLOAD_CODEC_ID,
    ]
    assert native.projection.id == definition.contribution_id
    assert definition.source.contribution_id == "mrw.batch.task.native.v2"
    assert definition.source.owner == batch_task.BATCH_TASK_OWNER == "batch.task.v2"
    assert definition.source.bundle_id == batch_task.BATCH_TASK_BUNDLE_ID
    assert BATCH_TASK_FAILURES is batch_task.BATCH_TASK_FAILURES
    assert ASSEMBLY_CELL_IDS == (
        "batch.task.build_plan.v2",
        "batch.task.reduce_retry.v2",
        "batch.task.submit.v2",
    )
    submission = definition.operation_by_slot("SUBMIT")
    assert submission is not None
    assert submission.source.receipt_codec_id == batch_task.SUBMISSION_RECEIPT_CODEC_ID
    assert (
        submission.source.receipt_provenance_schema
        == batch_task.SUBMISSION_RECEIPT_PROVENANCE_SCHEMA
    )


def test_c4_native_definition_rejects_order_drift() -> None:
    reversed_source = dataclasses.replace(
        DEFAULT_BATCH_TASK_NATIVE_SOURCE,
        operations=(
            DEFAULT_BATCH_TASK_NATIVE_SOURCE.operations[2],
            DEFAULT_BATCH_TASK_NATIVE_SOURCE.operations[1],
            DEFAULT_BATCH_TASK_NATIVE_SOURCE.operations[0],
        ),
    )
    assert isinstance(compile_batch_task_native_contribution(reversed_source), Failure)


def _context(definition, scope_digest: str = "0" * 64):
    return BatchTaskAssemblyContext(
        uow_factory=lambda: None,
        project_scope_digest=scope_digest,
        definition=definition,
        options=BatchTaskAssemblyOptions(),
    )


def test_non_default_c4_context_reaches_real_handlers_and_bindings() -> None:
    source = dataclasses.replace(
        DEFAULT_BATCH_TASK_NATIVE_SOURCE,
        deployment_catalog_digest="f" * 64,
        program_id="program:batch-task-non-default",
    )
    native = compile_batch_task_native_contribution(source)
    assert not isinstance(native, Failure)
    binding = native.assemble(
        _context(native.definition, scope_digest="e" * 64)
    )
    assert not isinstance(binding, Failure)
    assert binding.assembly_context.project_scope_digest == "e" * 64
    assert binding.assembly_context.uow_factory is not None
    assert binding.family_assembly.handlers[-1].uow_factory is binding.assembly_context.uow_factory
    assert all(
        handler.deployment_catalog_digest == "f" * 64
        for handler in binding.family_assembly.handlers
    )


def test_c4_native_validator_rejects_handler_digest_tamper() -> None:
    native = _native()
    binding = native.assemble(_context(native.definition))
    assert not isinstance(binding, Failure)
    tampered_assembly = dataclasses.replace(
        binding.family_assembly,
        handlers=tuple(
            SimpleNamespace(
                handler_binding_digest=handler.handler_binding_digest,
                deployment_catalog_digest="d" * 64,
            )
            for handler in binding.family_assembly.handlers
        ),
    )
    rejected = validate_batch_task_native_binding(
        binding.definition,
        dataclasses.replace(
            binding,
            family_assembly=tampered_assembly,
        ),
    )
    assert getattr(rejected, "issues", None)


def test_c4_native_assembly_keeps_fixture_closure_and_submit_terminal() -> None:
    native = _native()
    binding = native.assemble(_context(native.definition))
    assert not isinstance(binding, Failure)
    cells = binding.family_assembly.cells
    assert tuple(cell.cell_id for cell in cells) == ASSEMBLY_CELL_IDS
    assert binding.family_assembly.family_id == batch_task.BATCH_TASK_FAMILY_ID
    assert [cell.operation_contract_refs[0] for cell in cells] == [
        batch_task.BATCH_PLAN_KIND,
        batch_task.RETRY_REDUCE_KIND,
        batch_task.SUBMISSION_KIND,
    ]
    assert cells[0].status == "FIXTURE_CLOSURE_REQUIRED"
    assert cells[1].status == "FIXTURE_CLOSURE_REQUIRED"
    assert cells[2].status == "INSTALLED"
    assert "QUALITY_PROMOTION_HANDLER_INSTALLED_READBACK_ONLY" not in cells[-1].note


def test_c4_catalog_law_runs_and_catalog_has_one_native_contribution() -> None:
    assert len(batch_task_native_catalog) == 1
    for witness in batch_task_law_witnesses:
        witness.run()
