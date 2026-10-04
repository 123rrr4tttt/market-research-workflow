"""Native C7 source/catalog and offline inert assembly tests."""

from __future__ import annotations

import dataclasses

import pytest
from functorial_kit.contribution_verification import VerificationChanges
from functorial_kit.core.failure import Failure

from app.successor_runtime.assembly.base import local_assembly_scope_digest
from app.successor_runtime.capabilities import material_ingest_common as c7
from app.successor_runtime.capabilities import material_ingest_movements as c7m
from app.successor_runtime.capabilities.material_native_contribution import (
    ASSEMBLY_CELL_IDS,
    MaterialAssemblyContext,
    DEFAULT_MATERIAL_NATIVE_SOURCE,
    compile_material_native_contribution,
)
from app.successor_runtime.capabilities.material_ingest_program import (
    compile_material_ingest_program,
)
from mrw_functorial_kit.contributions.material import (
    material_law_witnesses,
    material_native_catalog,
    material_verification_law_witnesses,
    material_verification_plan,
    material_verification_plan_for,
    material_verification_registration,
    contribution_catalog,
)
from mrw_functorial_kit.core.material_semantics import (
    MATERIAL_INGEST_TERMINAL_FAILURE_CODES,
    material_digestion_alternatives,
    material_ingest_failures,
    material_ingest_terminal_outcomes,
)


def test_catalog_contains_c7_native_contribution_in_source_order() -> None:
    assert tuple(native.projection.id for native in material_native_catalog) == (
        "mrw.material.ingest.native.v2",
    )
    assert tuple(item.id for item in contribution_catalog.contributions) == tuple(
        native.projection.id for native in material_native_catalog
    )


def test_default_source_declares_four_modes_and_separated_boundaries() -> None:
    source = DEFAULT_MATERIAL_NATIVE_SOURCE
    assert source.movement_alternatives == c7m.MATERIAL_INGEST_ALTERNATIVES
    assert len({source.canonical_writer_ref, source.production_admission_ref, source.projector_driver_ref}) == 3
    assert source.canonical_write_authorized is False
    assert source.canonical_commit_executed is False


def test_failure_and_vocabulary_identity_come_from_kit_semantics() -> None:
    bundle = c7.build_material_ingest_bundle()
    failure_profile = bundle.profiles["failure"]
    assert DEFAULT_MATERIAL_NATIVE_SOURCE.failure_codes == tuple(failure_profile.typed_failures)  # type: ignore[union-attr]
    assert material_digestion_alternatives.members == DEFAULT_MATERIAL_NATIVE_SOURCE.movement_alternatives
    assert len(material_ingest_terminal_outcomes.members) > 0
    assert tuple(MATERIAL_INGEST_TERMINAL_FAILURE_CODES) == c7m.MATERIAL_INGEST_TERMINAL_FAILURE_CODES
    assert set(MATERIAL_INGEST_TERMINAL_FAILURE_CODES) < set(material_ingest_failures.codes)


def test_projection_reuses_material_semantic_authorities() -> None:
    compiled = compile_material_native_contribution(DEFAULT_MATERIAL_NATIVE_SOURCE)
    assert not isinstance(compiled, Failure)
    assert material_digestion_alternatives in compiled.projection.vocabularies
    assert material_ingest_terminal_outcomes in compiled.projection.vocabularies
    assert material_ingest_failures in compiled.projection.failures


@pytest.mark.parametrize(
    "witness",
    material_law_witnesses,
    ids=[witness.id for witness in material_law_witnesses],
)
def test_catalog_laws_are_inert_and_pass(witness) -> None:
    witness.run()


def test_verification_plan_derives_from_same_catalog_and_unknown_changes_expand() -> None:
    expected = tuple(native.projection.id for native in material_native_catalog)
    assert material_verification_plan.selection.contribution_ids == expected
    unknown = material_verification_plan_for(VerificationChanges(unknown=True))
    assert unknown.selection.mode == "full"
    assert "unknown_changes" in unknown.selection.reasons
    assert unknown.selection.contribution_ids == expected
    assert material_verification_registration is not None
    for witness in material_verification_law_witnesses:
        witness.run()


def _offline_context() -> MaterialAssemblyContext:
    return MaterialAssemblyContext(project_scope_digest=local_assembly_scope_digest())


def test_offline_binding_keeps_inert_assembly_without_canonical_write() -> None:
    compiled = compile_material_native_contribution(DEFAULT_MATERIAL_NATIVE_SOURCE)
    assert not isinstance(compiled, Failure)
    binding = compiled.assemble(_offline_context())
    assert not isinstance(binding, Failure)
    from app.successor_runtime.capabilities.material_native_contribution import (
        validate_material_native_binding,
    )

    validated = validate_material_native_binding(compiled.definition, binding)
    assert not isinstance(validated, Failure)
    assert tuple(cell.cell_id for cell in binding.family_assembly.cells) == (
        ASSEMBLY_CELL_IDS
    )
    assert compiled.definition.source.canonical_commit_executed is False


def test_non_default_source_compiles_without_durable_authority() -> None:
    source = dataclasses.replace(
        DEFAULT_MATERIAL_NATIVE_SOURCE,
        contribution_id="mrw.material.ingest.native.alt.v2",
    )
    compiled = compile_material_native_contribution(source)
    assert not isinstance(compiled, Failure)
    assert compiled.projection.id == "mrw.material.ingest.native.alt.v2"  # type: ignore[union-attr]
    assert compiled.projection.owner == "material.ingest.v2"  # type: ignore[union-attr]


def test_exact_c7_1_program_compiles_from_native_catalog_offline() -> None:
    compiled = compile_material_native_contribution(DEFAULT_MATERIAL_NATIVE_SOURCE)
    assert not isinstance(compiled, Failure)
    submission = c7.MaterialIngestSubmission(
        idempotency_key="c7-native-program-test",
        project_key="c7-native-program-test",
        source_locator="native://program-test",
    )
    program = compiled.definition  # type: ignore[union-attr]
    from app.successor_runtime.capabilities.material_native_contribution import (
        build_material_native_program,
    )

    spec = build_material_native_program(
        program,
        submission,
        program_id="mrw.material.ingest.native.program.test.v2",
        project_scope_digest=local_assembly_scope_digest(),
    )
    compiled_plan = compile_material_ingest_program(
        spec,
        program.catalog,  # type: ignore[arg-type]
        operation_contracts=program.registry,  # type: ignore[arg-type]
    )
    assert compiled_plan.ordered_steps, "compiled program must keep its exact C7.1 step"


def test_non_default_context_flows_into_program_and_assembly() -> None:
    compiled = compile_material_native_contribution(DEFAULT_MATERIAL_NATIVE_SOURCE)
    assert not isinstance(compiled, Failure)
    context_scope = "a" * 64
    submission = c7.MaterialIngestSubmission(
        idempotency_key="c7-native-context-test",
        project_key="c7-native-context-test",
        source_locator="native://context-test",
    )
    from app.successor_runtime.capabilities.material_native_contribution import (
        build_material_native_program,
    )

    spec = build_material_native_program(
        compiled.definition,  # type: ignore[union-attr]
        submission,
        program_id="mrw.material.ingest.native.program.context.v2",
        project_scope_digest=context_scope,
    )
    assert spec.project_scope_digest == context_scope
    assert dict(spec.metadata)["project_scope_digest"] == context_scope

    from app.successor_runtime.capabilities.material_native_contribution import (
        assemble_material_native_definition,
        validate_material_native_binding,
    )

    context = MaterialAssemblyContext(project_scope_digest=context_scope)
    binding = assemble_material_native_definition(compiled.definition, context)
    assert not isinstance(binding, Failure)
    assert binding.family_assembly.family_id == DEFAULT_MATERIAL_NATIVE_SOURCE.bundle_id
    assert tuple(binding.family_assembly.coverage()) == ASSEMBLY_CELL_IDS
    from app.successor_runtime.assembly.material_ingest_assembly import (
        build_material_ingest_assembly,
        build_deterministic_material_ingest_rollback_options,
    )

    scoped = build_material_ingest_assembly(
        options=build_deterministic_material_ingest_rollback_options(context_scope),
        project_scope_digest=context_scope,
        native_definition=compiled.definition,
    )
    local_scope = local_assembly_scope_digest()
    local = build_material_ingest_assembly(
        options=build_deterministic_material_ingest_rollback_options(local_scope),
        project_scope_digest=local_scope,
        native_definition=compiled.definition,
    )
    assert tuple(
        handler.handler_binding_digest for handler in scoped.handlers
    ) != tuple(handler.handler_binding_digest for handler in local.handlers)
    accepted = validate_material_native_binding(compiled.definition, binding)
    assert not isinstance(accepted, Failure)
