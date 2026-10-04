"""Pure C1 Slice A/B/C acceptance over existing Program/Plan builders."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.successor_runtime.capabilities import build_first_specimen_bundle
from app.successor_runtime.capabilities import c8_program as c8p
from app.successor_runtime.capabilities.c1_slice_acceptance import (
    C1AcceptanceError,
    C1NamedStepObservation,
    C1RollbackBeforeAfter,
    C1RuntimeEvidenceRefs,
    C1StepStatus,
    accept_c1_slice,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.normalize import normalize_program
from app.successor_runtime.research.object_types import CANONICAL_CODEC_ID, ObjectType
from tests.successor_runtime.p4_c7_fixture import (
    program_and_plan as c7_program_and_plan,
)

PROJECT_KEY = "c1-slice-acceptance"
SCOPE_DIGEST = content_digest({"project": PROJECT_KEY, "scope": 1})


def _observation_digest(name: str, status: C1StepStatus) -> str:
    return content_digest({"name": name, "status": status.value})


def _observations(plan, status: C1StepStatus = C1StepStatus.SUCCESS):
    return tuple(
        C1NamedStepObservation(
            name=f"step-{index}:{step.step_kind.lower()}",
            step_id=step.step_id,
            status=status,
            result_digest=_observation_digest(f"step-{index}", status),
            evidence_ref=f"evidence:c1:step-{index}:{status.value}",
        )
        for index, step in enumerate(plan.ordered_steps)
    )


def _runtime_evidence() -> C1RuntimeEvidenceRefs:
    return C1RuntimeEvidenceRefs(
        runtime_evidence_refs=("runtime:c1:receipt",),
        journal_refs=("journal:c1:run",),
        readback_refs=("readback:c1:run",),
        replay_refs=("replay:c1:run",),
    )


def _rollback() -> C1RollbackBeforeAfter:
    return C1RollbackBeforeAfter(
        rollback_ref="rollback:c1:future-owner",
        before_authority_epoch=7,
        after_authority_epoch=8,
        before_journal_refs=("journal:c1:run",),
        after_journal_refs=("journal:c1:run",),
        before_readback_refs=("readback:c1:run",),
        after_readback_refs=("readback:c1:run",),
    )


def _accept(slice_id, program, plan, *, observations=None):
    captured = observations or _observations(plan)
    return accept_c1_slice(
        in_slice_id=slice_id,
        in_program=program,
        in_plan=plan,
        in_legacy_step_observations=captured,
        in_successor_step_observations=captured,
        in_runtime_evidence=_runtime_evidence(),
        in_rollback_before_after=_rollback(),
    )


def _c8_writing_program_plan():
    bundle = c8p.build_c8_bundle()
    catalog = c8p.build_c8_catalog(bundle)
    program = c8p.build_c8_program(
        cell_id="C8.2",
        payload=c8p.C8WritingComposeInput(
            project_key=PROJECT_KEY,
            knowledge_item_key="knowledge:c1",
            selection_hash="selection:c1",
            selection_text="C1 bounded writing",
            demand_fields=("canonical_statement", "evidence_refs"),
        ),
        catalog=catalog,
        program_id="program:c1:slice-b",
        project_key=PROJECT_KEY,
        project_registry_revision=1,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = c8p.compile_c8_program(
        program,
        catalog,
        operation_contracts=c8p.build_c8_registry(bundle),
    )
    return program, plan


def _value_ref(
    *,
    program_id: str,
    suffix: str,
    object_type: ObjectType,
    codec_id: str,
) -> ValueRef:
    value_id = f"{program_id}:payload:{suffix}"
    storage_ref = f"project-value:{value_id}"
    return ValueRef(
        value_id=value_id,
        project_key=PROJECT_KEY,
        object_type=object_type,
        codec_id=codec_id,
        content_digest=content_digest({"storage_ref": storage_ref}),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=storage_ref,
        byte_size=1,
        provenance_digest=content_digest({"provenance": storage_ref}),
    )


def _c8_delivery_program_plan():
    first_specimen = build_first_specimen_bundle()
    delivery_operation = first_specimen.operation_by_kind(
        c8p.DELIVERY_INTERNAL_EXPORT_KIND
    )
    delivery_codec = first_specimen.codec_by_kind(c8p.DELIVERY_INTERNAL_EXPORT_KIND)
    bundle = c8p.build_c8_delivery_bridge_bundle(
        delivery_operation,
        delivery_codec,
    )
    catalog = c8p.build_c8_catalog(bundle)
    program_id = "program:c1:slice-c"
    program = normalize_program(
        c8p.build_c8_delivery_bridge_program(
            delivery_operation=delivery_operation,
            delivery_codec=delivery_codec,
            delivery_payload_ref=_value_ref(
                program_id=program_id,
                suffix="internal-export-input",
                object_type=ObjectType("InternalExportInput.v1"),
                codec_id=delivery_codec.codec_id,
            ),
            artifact_input_ref=_value_ref(
                program_id=program_id,
                suffix="research-artifact",
                object_type=c8p.C8_RESEARCH_ARTIFACT_TYPE,
                codec_id=CANONICAL_CODEC_ID,
            ),
            intent_input_ref=_value_ref(
                program_id=program_id,
                suffix="delivery-intent",
                object_type=c8p.C8_DELIVERY_INTENT_TYPE,
                codec_id=CANONICAL_CODEC_ID,
            ),
            stage_payload=c8p.C8ReportStageInput(
                project_key=PROJECT_KEY,
                report_id="report:c1",
                topic="C1 report delivery acceptance",
                source_keys=("knowledge:c1",),
            ),
            catalog=catalog,
            program_id=program_id,
            project_key=PROJECT_KEY,
            project_registry_revision=1,
            project_scope_digest=SCOPE_DIGEST,
        )
    )
    plan = c8p.compile_c8_delivery_bridge_program(
        program,
        catalog,
        operation_contracts=c8p.build_c8_registry(bundle),
    )
    return program, plan


def test_slice_a_uses_real_c7_ingest_admission_shape_and_exact_closure() -> None:
    program, plan, *_ = c7_program_and_plan()
    acceptance = _accept("A", program, plan)

    assert acceptance.accepted
    assert acceptance.ordered_operation_kinds == ("ingest_index.stage_candidate.v1",)
    assert acceptance.ordered_step_kinds == ("EFFECT", "ADMISSION")
    assert acceptance.ordered_assignment_kinds == ("INTERPRET", "VERIFY_ADMIT")
    assert acceptance.program_digest == program.program_digest
    assert acceptance.plan_digest == plan.plan_digest
    assert acceptance.control_root_digest == plan.control_root.control_digest
    assert len(acceptance.catalog_digest) == 64
    assert len(acceptance.source_map_digest) == 64
    assert len(acceptance.dependency_index_digest) == 64


def test_slice_b_preserves_ordered_writing_composition_without_projectors() -> None:
    program, plan = _c8_writing_program_plan()
    acceptance = _accept("B", program, plan)

    assert acceptance.accepted
    assert acceptance.ordered_operation_kinds == (
        "c8.writing.compose.v1",
        "c8.writing.stage.v1",
    )
    assert acceptance.ordered_step_kinds == ("EFFECT", "EFFECT")
    assert all(
        token not in kind
        for kind in acceptance.ordered_operation_kinds
        for token in (".graph.", ".ui.", ".api.", "projector")
    )


def test_slice_c_keeps_delivery_separately_admitted_and_excludes_api_ui() -> None:
    program, plan = _c8_delivery_program_plan()
    acceptance = _accept("C", program, plan)

    assert acceptance.accepted
    assert acceptance.ordered_operation_kinds == (
        "c8.report.stage.v1",
        "c8.report.verify.v1",
        "c8.report.admission.v1",
        "c8.delivery_intent_prepare.v1",
        "delivery.internal_export.v1",
    )
    assert acceptance.ordered_step_kinds[-2:] == ("EFFECT", "ADMISSION")
    assert plan.ordered_steps[-2].return_contract.admission_required is True
    assert "delivery_requires_separate_current_authority" in (
        acceptance.declared_differences
    )


def test_identity_and_digest_sensitivity_are_bounded_to_exact_inputs() -> None:
    program, plan = _c8_writing_program_plan()
    observations = _observations(plan)
    first = _accept("B", program, plan, observations=observations)
    identity = _accept("B", program, plan, observations=observations)
    assert identity == first
    assert identity.acceptance_digest == first.acceptance_digest

    changed_first = replace(
        observations[0],
        result_digest=content_digest({"changed": observations[0].result_digest}),
    )
    changed = _accept(
        "B",
        program,
        plan,
        observations=(changed_first,) + observations[1:],
    )
    assert changed.accepted
    assert changed.acceptance_digest != first.acceptance_digest
    assert changed.legacy_observation_digest != first.legacy_observation_digest


def test_stale_plan_fails_closed_before_any_acceptance_receipt() -> None:
    program, plan = _c8_writing_program_plan()
    stale = replace(plan, plan_digest="f" * 64)
    with pytest.raises(C1AcceptanceError, match="stale plan_digest"):
        _accept("B", program, stale)


def test_rollback_only_advances_future_owner_epoch_and_retains_refs() -> None:
    with pytest.raises(C1AcceptanceError, match="retain exact journal"):
        C1RollbackBeforeAfter(
            rollback_ref="rollback:c1:bad",
            before_authority_epoch=7,
            after_authority_epoch=8,
            before_journal_refs=("journal:c1:run",),
            after_journal_refs=("journal:c1:other",),
            before_readback_refs=("readback:c1:run",),
            after_readback_refs=("readback:c1:run",),
        )
