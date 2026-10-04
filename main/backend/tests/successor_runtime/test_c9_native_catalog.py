"""Focused C9 native-contribution laws for slot identity and CAS failure identity."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from app.successor_runtime.runtime.projection_native_contribution import (
    ASSEMBLY_CELL_IDS,
    PROJECTION_READ_MODEL_SLOT_ID,
    PROJECTION_COMMAND_QUERY_SLOT_ID,
    PROJECTION_CLIENT_CONTRACT_SLOT_ID,
    DEFAULT_PROJECTION_NATIVE_SOURCE,
    NON_DEFAULT_PROJECTION_NATIVE_SOURCE,
    PROJECTION_FAMILY_ID,
    PROJECTION_PROCESSING_FAILURES,
    PROJECTION_SOURCE_ANCHOR_OBJECT_SUFFIX,
    PROJECTION_SOURCE_VIEWS_OBJECT_SUFFIX,
    ProjectionNativeDefinition,
    ProjectionNativeSource,
    ProjectionObservationContext,
    compile_projection_native_contribution,
)
from app.successor_runtime.substrate.projections import registry as offsets
from functorial_kit.contributions import compose_contributions
from functorial_kit.core.failure import Failure

from mrw_functorial_kit.core.projection_semantics import (
    projection_processing_failures,
)
from mrw_functorial_kit.core.w06_semantics import (
    projection_evidence_surface_failures,
)

ROOT = Path(__file__).parents[4]
PROJECT_ROOT = ROOT


def _native(source: ProjectionNativeSource):
    result = compile_projection_native_contribution(source)
    assert not isinstance(result, Failure)
    return result


def test_three_slots_have_fixed_order_and_identity() -> None:
    native = _native(DEFAULT_PROJECTION_NATIVE_SOURCE)
    definition = native.definition
    objects = definition.contribution_objects()
    assert definition.slot_ids == (
        PROJECTION_COMMAND_QUERY_SLOT_ID,
        PROJECTION_CLIENT_CONTRACT_SLOT_ID,
        PROJECTION_READ_MODEL_SLOT_ID,
    )
    assert tuple(item.id for item in objects) == (
        f"{DEFAULT_PROJECTION_NATIVE_SOURCE.contribution_id}.command-query",
        f"{DEFAULT_PROJECTION_NATIVE_SOURCE.contribution_id}.client-contract",
        f"{DEFAULT_PROJECTION_NATIVE_SOURCE.contribution_id}.read-model",
        (
            f"{DEFAULT_PROJECTION_NATIVE_SOURCE.contribution_id}"
            f"{PROJECTION_SOURCE_VIEWS_OBJECT_SUFFIX}"
        ),
        (
            f"{DEFAULT_PROJECTION_NATIVE_SOURCE.contribution_id}"
            f"{PROJECTION_SOURCE_ANCHOR_OBJECT_SUFFIX}"
        ),
    )
    assert objects[-2].references == (objects[2].id, objects[-1].id)
    assert objects[-1].references == (objects[2].id,)
    assert DEFAULT_PROJECTION_NATIVE_SOURCE.family_id == PROJECTION_FAMILY_ID
    assert DEFAULT_PROJECTION_NATIVE_SOURCE.cell_ids == ASSEMBLY_CELL_IDS
    assert DEFAULT_PROJECTION_NATIVE_SOURCE.projection_contract == (
        "projection.material-closure.v2"
    )
    assert DEFAULT_PROJECTION_NATIVE_SOURCE.anchor.projector_id == (
        "projection.material-closure.v2"
    )
    assert DEFAULT_PROJECTION_NATIVE_SOURCE.anchor.projector_version == "2.0.0"
    assert DEFAULT_PROJECTION_NATIVE_SOURCE.anchor.source_kind == "projection_source"
    assert DEFAULT_PROJECTION_NATIVE_SOURCE.anchor.projection_schema_ref == (
        "mrw.projection.material-closure-candidate.v2"
    )
    assert definition.facade_command.command_id == DEFAULT_PROJECTION_NATIVE_SOURCE.facade.command_id
    assert definition.frontend_projection[0][0] == DEFAULT_PROJECTION_NATIVE_SOURCE.frontend.contract_ref
    assert definition.projector_key == offsets.ProjectorKey(
        projector_id=DEFAULT_PROJECTION_NATIVE_SOURCE.anchor.projector_id,
        projector_version=DEFAULT_PROJECTION_NATIVE_SOURCE.anchor.projector_version,
        source_kind=DEFAULT_PROJECTION_NATIVE_SOURCE.anchor.source_kind,
        source_ref=DEFAULT_PROJECTION_NATIVE_SOURCE.anchor.source_ref,
        source_incarnation=DEFAULT_PROJECTION_NATIVE_SOURCE.anchor.source_incarnation,
    )


def test_facade_projection_and_anchor_are_not_fused_fact_sources() -> None:
    native = _native(DEFAULT_PROJECTION_NATIVE_SOURCE)
    definition: ProjectionNativeDefinition = native.definition
    assert definition.facade_validation.valid
    assert definition.facade_command.execute is False
    assert definition.facade_query.read_only is True
    assert definition.source.frontend.contract_ref.endswith("deriveSuccessorUiObservation")
    assert definition.frontend_projection != definition.slot_ids
    assert definition.current_offset.key == definition.projector_key
    source_text = (ROOT / "main/backend/app/successor_runtime/runtime/projection_native_contribution.py").read_text()
    assert "frontend-modern/src/lib/api/domains/successor-runtime.ts" in source_text
    assert "substrate/projections/registry.py" in source_text
    assert "runtime/facade_contracts.py" in source_text


def test_frontend_observation_projection_follows_frontend_contract() -> None:
    binding = _native(DEFAULT_PROJECTION_NATIVE_SOURCE).assemble(None)
    assert not isinstance(binding, Failure)
    cases = (
        (ProjectionObservationContext("not_started"), "NOT_STARTED"),
        (ProjectionObservationContext("in_flight"), "IN_FLIGHT"),
        (ProjectionObservationContext("settled", envelope_status="ok"), "SUCCEEDED"),
        (ProjectionObservationContext("settled", client_error=True), "FAILED"),
        (ProjectionObservationContext("settled", envelope_status="waiting"), "IN_FLIGHT"),
        (ProjectionObservationContext("settled", envelope_status="error", typed_rejection=True), "REJECTED_TYPED"),
        (ProjectionObservationContext("settled", envelope_status="error"), "OUTCOME_UNKNOWN"),
    )
    assert {observation for _, observation in cases} == set(DEFAULT_PROJECTION_NATIVE_SOURCE.frontend.states)
    for context, expected in cases:
        assert binding.derive_frontend_observation(context) == expected


def _next_offset(definition: ProjectionNativeDefinition) -> offsets.ProjectionOffset:
    return dataclasses.replace(definition.next_offset, revision=definition.current_offset.revision + 1)


def test_cas_advance_identity_and_failure_aba_stale_rebuild() -> None:
    binding = _native(DEFAULT_PROJECTION_NATIVE_SOURCE).assemble(None)
    assert not isinstance(binding, Failure)
    definition = binding.definition
    assert binding.validate_anchor_transition(_next_offset(definition), definition.cas_expectation).valid

    aba_offset = dataclasses.replace(
        definition.current_offset,
        revision=definition.current_offset.revision + 1,
        source_digest="2" * 64,
    )
    result = binding.validate_anchor_transition(aba_offset, definition.cas_expectation, stored_offset=aba_offset)
    codes = {item.code for item in result.violations}
    assert {"OFFSET_ABA_DETECTED", "SOURCE_REVISION_DIGEST_CONFLICT"} <= codes

    stale_offset = dataclasses.replace(_next_offset(definition), source_revision=0)
    result = binding.validate_anchor_transition(stale_offset, definition.cas_expectation)
    codes = {item.code for item in result.violations}
    assert "SOURCE_REVISION_REGRESSION" in codes

    rebuild_offset = dataclasses.replace(
        _next_offset(definition),
        projection_generation=definition.current_offset.projection_generation + 1,
    )
    result = binding.validate_anchor_transition(rebuild_offset, definition.cas_expectation)
    codes = {item.code for item in result.violations}
    assert {"OFFSET_GENERATION_CHANGE_FORBIDDEN"} <= codes


def test_default_and_non_default_sources_keep_separate_identity() -> None:
    default = _native(DEFAULT_PROJECTION_NATIVE_SOURCE)
    non_default = _native(NON_DEFAULT_PROJECTION_NATIVE_SOURCE)
    assert default.definition.contribution_id != non_default.definition.contribution_id
    assert default.definition.projector_key != non_default.definition.projector_key
    assert default.definition.facade_command.command_id != non_default.definition.facade_command.command_id
    assert tuple(native.projection.id for native in (default, non_default)) == (
        DEFAULT_PROJECTION_NATIVE_SOURCE.contribution_id,
        NON_DEFAULT_PROJECTION_NATIVE_SOURCE.contribution_id,
    )


def test_invalid_source_fails_without_silent_default_substitution() -> None:
    source = dataclasses.replace(
        NON_DEFAULT_PROJECTION_NATIVE_SOURCE,
        contribution_id="mrw.successor.c9.native.invalid.v1",
        frontend=dataclasses.replace(NON_DEFAULT_PROJECTION_NATIVE_SOURCE.frontend, states=("INVENTED",)),
    )
    result = compile_projection_native_contribution(source)
    assert isinstance(result, Failure)
    assert any(i["message"] == "frontend state union drift" for i in result.context["issues"])


def test_project_catalog_contains_projection_business_catalog() -> None:
    from contributions.project_catalog import project_contribution_catalog
    from mrw_functorial_kit.contributions import projection as kit

    assert [native.projection.id for native in kit.projection_native_catalog] == [
        DEFAULT_PROJECTION_NATIVE_SOURCE.contribution_id
    ]
    assert tuple(kit.projection_contribution_catalog) == tuple(
        item
        for item in project_contribution_catalog
        if item.id.startswith("mrw.projection.")
    )


def test_native_uses_single_projection_processing_failure_authority() -> None:
    assert PROJECTION_PROCESSING_FAILURES is projection_processing_failures
    assert PROJECTION_PROCESSING_FAILURES.name == "projection.processing.failure"
    assert PROJECTION_PROCESSING_FAILURES.codes == (
        "SOURCE_UNAVAILABLE",
        "SOURCE_DRIFT",
        "SOURCE_INCARNATION_STALE",
        "OFFSET_STALE",
        "PROJECTION_OFFSET_CLOSURE_DRIFT",
        "EXTERNAL_INDEX_EFFECT_FAILED",
        "REBUILD_FAILED",
    )
    native = _native(DEFAULT_PROJECTION_NATIVE_SOURCE)
    assert tuple(family.name for family in native.projection.failures) == (
        "projection.processing.failure",
        "projection.evidence-surface.failure",
    )
    assert native.projection.failures[1] is projection_evidence_surface_failures


def test_catalog_projects_current_projection_source_sketches() -> None:
    from mrw_functorial_kit.contributions import projection as kit

    native = kit.projection_native_catalog[0]

    assert tuple(sketch.object_id for sketch in native.projection.sketches) == (
        (
            f"{DEFAULT_PROJECTION_NATIVE_SOURCE.contribution_id}"
            f"{PROJECTION_SOURCE_VIEWS_OBJECT_SUFFIX}"
        ),
        (
            f"{DEFAULT_PROJECTION_NATIVE_SOURCE.contribution_id}"
            f"{PROJECTION_SOURCE_ANCHOR_OBJECT_SUFFIX}"
        ),
    )
    views, anchor = tuple(sketch.entry for sketch in native.projection.sketches)
    assert [obj["name"] for obj in views["objects"]] == [
        "mrw.projection.project-source-closure.v2",
        "mrw.projection.task-view.v2",
        "mrw.projection.knowledge-view.v2",
        "mrw.projection.material-view.v2",
    ]
    assert [obj["name"] for obj in anchor["objects"]] == [
        "mrw.projection.project-source-closure.v2",
        "mrw.projection.project-source-manifest.v2",
        "projection.project-source-identity.v2",
        "ProjectionOffsetKey",
    ]
    assert views["failures"] == ["projection.processing.failure"]
    assert anchor["failures"] == ["projection.processing.failure"]
    assert views["derived"] == {
        "authoritative": False,
        "derived_as": "view",
    }
    assert anchor["derived"] == {
        "authoritative": False,
        "derived_as": "anchor",
    }


def test_native_projection_sketches_compose_with_declared_owner_objects() -> None:
    from mrw_functorial_kit.contributions import projection as kit

    native = kit.projection_native_catalog[0]
    composed = compose_contributions((native.projection,))

    assert not isinstance(composed, Failure)
    assert tuple(composed.sketches) == tuple(
        sketch.entry for sketch in native.projection.sketches
    )
