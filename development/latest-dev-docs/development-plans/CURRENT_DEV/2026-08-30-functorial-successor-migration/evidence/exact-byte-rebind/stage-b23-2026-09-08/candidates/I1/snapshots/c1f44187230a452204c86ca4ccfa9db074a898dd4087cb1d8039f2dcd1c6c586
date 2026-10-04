from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.successor_runtime.capabilities.fixture import (
    build_fixture_capability_bundle,
)
from app.successor_runtime.language.algebra import (
    AlgebraRef,
    OperationSpec,
    ValueRef,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.checksum import sha256_hex
from app.successor_runtime.language.combinators import default_registries
from app.successor_runtime.language.compile import CompileFailure, compile_program
from app.successor_runtime.language.plan import traversal_shape_digest
from app.successor_runtime.language.program import (
    ProgramSpec,
    atom_node,
    traverse_ordered_node,
)
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.activation import (
    ActivationError,
    ProgramInput,
    activate_plan,
)
from app.successor_runtime.substrate.postgres.plans import decode_plan
from app.successor_runtime.substrate.postgres.research_ledger import (
    ExactContentConflict,
)

pytestmark = pytest.mark.unit

PROJECT_KEY = "p3-traversal-foundation"
PROJECT_SCOPE_DIGEST = "1" * 64


def _closure(
    *,
    policy: str,
    elements: tuple[dict[str, str], ...],
) -> tuple[
    ProgramSpec,
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
    ProgramInput,
]:
    bundle = build_fixture_capability_bundle()
    operation = bundle.operation
    catalog = OperationContractCatalogSnapshot(
        catalog_id="mrw.p3.traversal.fixture.catalog",
        catalog_version="1",
        entries=(
            (
                operation.ref.kind,
                operation.ref.contract_version,
                operation.ref.contract_digest,
                operation.owner_capability_id,
            ),
        ),
    )
    registry = OperationContractRegistry(catalog, (operation,))
    input_ref = ValueRef(
        value_id="value:p3:traversal:element-input",
        project_key=PROJECT_KEY,
        object_type=operation.input_type,
        codec_id=operation.input_type.codec_id,
        content_digest="2" * 64,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref="project-value:p3:traversal:element-input",
        byte_size=1,
        provenance_digest="3" * 64,
    )
    payload_ref = replace(
        input_ref,
        value_id="value:p3:traversal:element-payload",
        storage_ref="project-value:p3:traversal:element-payload",
        content_digest="4" * 64,
    )
    atom = atom_node(
        OperationSpec(
            operation_id="fixture.echo.traversal-element",
            contract_ref=operation.ref,
            input_refs=(input_ref,),
            payload_ref=payload_ref,
            allowed_overrides=freeze_json_object({}),
        ),
        operation.input_type,
        operation.output_type,
    )
    root = traverse_ordered_node(atom, policy)
    shape_digest = traversal_shape_digest(elements)
    metadata: dict[str, object] = {
        "schema": "mrw.p3.traversal.fixture.v1",
        "traversal_policy": policy,
    }
    if policy == "STATIC_SHAPE":
        metadata.update(
            traversal_shape_digest=shape_digest,
            traversal_element_count=len(elements),
        )
    program = ProgramSpec(
        program_id=f"program:p3:traversal:{policy.lower()}",
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=PROJECT_KEY,
        project_registry_revision=1,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
        semantic_identity="p3.traversal.foundation",
        input_type=root.input_type,
        output_type=root.output_type,
        root=root,
        algebra_refs=(AlgebraRef("mrw.successor.language.algebra", "1"),),
        transform_refs=(),
        observation_profile="mrw.p3.traversal.observation.v1",
        metadata=freeze_json_object(metadata),
        program_digest="",
    ).with_digest()
    sequence_bytes = canonical_bytes(list(elements))
    sequence_digest = sha256_hex(list(elements))
    sequence_ref = ValueRef(
        value_id="value:p3:traversal:sequence",
        project_key=PROJECT_KEY,
        object_type=program.input_type,
        codec_id=program.input_type.codec_id,
        content_digest=sequence_digest,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref="project-value:p3:traversal:sequence",
        byte_size=len(sequence_bytes),
        provenance_digest="5" * 64,
    )
    return program, catalog, registry, ProgramInput(sequence_ref, elements)


@pytest.mark.parametrize("policy", ["STATIC_SHAPE", "MATERIALIZED_SHAPE"])
def test_traverse_compiles_to_one_ordered_successor_materialization(
    policy: str,
) -> None:
    elements = ({"value": "a"}, {"value": "b"})
    program, catalog, registry, program_input = _closure(
        policy=policy,
        elements=elements,
    )
    plan = compile_program(program, catalog, operation_contracts=registry)
    assert len(plan.ordered_steps) == 1
    step = plan.ordered_steps[0]
    assert step.step_kind == "TRANSFORM"
    assert step.transform_ref is not None
    assert step.transform_ref.name == "mrw.traverse_ordered.materialize"
    assert plan.control_root.node_kind == "traverse_ordered"
    assert dict(plan.control_root.attributes)["traversal_policy"] == policy

    registries = default_registries()
    activated = activate_plan(
        run_id=f"run:p3:traversal:{policy.lower()}",
        program=program,
        plan=plan,
        program_input=program_input,
        transform_registry=registries.transforms,
        merge_registry=registries.merges,
        discriminator_registry=registries.discriminators,
    )
    assert activated.activations == ()
    assert activated.materializations == ()
    assert len(activated.traversal_materializations) == 1
    materialization = activated.traversal_materializations[0]
    assert materialization.traversal_policy == policy
    assert materialization.element_count == 2
    assert materialization.element_digests == tuple(
        sha256_hex(item) for item in elements
    )
    assert (
        materialization.input_sequence_digest == program_input.value_ref.content_digest
    )


def test_static_shape_requires_compile_binding_and_rejects_aba() -> None:
    elements = ({"value": "a"}, {"value": "b"})
    program, catalog, registry, program_input = _closure(
        policy="STATIC_SHAPE",
        elements=elements,
    )
    missing = replace(
        program,
        metadata=freeze_json_object({"traversal_policy": "STATIC_SHAPE"}),
        program_digest="",
    ).with_digest()
    with pytest.raises(CompileFailure) as exc_info:
        compile_program(missing, catalog, operation_contracts=registry)
    assert exc_info.value.code == "TRAVERSAL_SHAPE_BINDING_REQUIRED"

    plan = compile_program(program, catalog, operation_contracts=registry)
    mutated_elements = ({"value": "a"}, {"value": "mutated"})
    mutated_digest = sha256_hex(list(mutated_elements))
    mutated_ref = replace(
        program_input.value_ref,
        content_digest=mutated_digest,
        byte_size=len(canonical_bytes(list(mutated_elements))),
    )
    registries = default_registries()
    with pytest.raises(ActivationError, match="STATIC_SHAPE traversal input drift"):
        activate_plan(
            run_id="run:p3:traversal:aba",
            program=program,
            plan=plan,
            program_input=ProgramInput(mutated_ref, mutated_elements),
            transform_registry=registries.transforms,
            merge_registry=registries.merges,
            discriminator_registry=registries.discriminators,
        )


def test_materialized_shape_digest_is_order_sensitive_and_deterministic() -> None:
    elements = ({"value": "a"}, {"value": "b"})
    program, catalog, registry, program_input = _closure(
        policy="MATERIALIZED_SHAPE",
        elements=elements,
    )
    plan = compile_program(program, catalog, operation_contracts=registry)
    registries = default_registries()

    def materialize(value: ProgramInput):
        return activate_plan(
            run_id="run:p3:traversal:materialized",
            program=program,
            plan=plan,
            program_input=value,
            transform_registry=registries.transforms,
            merge_registry=registries.merges,
            discriminator_registry=registries.discriminators,
        ).traversal_materializations[0]

    first = materialize(program_input)
    assert materialize(program_input) == first

    reversed_elements = tuple(reversed(elements))
    reversed_ref = replace(
        program_input.value_ref,
        content_digest=sha256_hex(list(reversed_elements)),
    )
    reversed_result = materialize(ProgramInput(reversed_ref, reversed_elements))
    assert reversed_result.shape_digest != first.shape_digest
    assert reversed_result.element_digests == tuple(reversed(first.element_digests))


def test_plan_digest_and_store_decode_bind_traversal_transform_ref() -> None:
    program, catalog, registry, _program_input = _closure(
        policy="MATERIALIZED_SHAPE",
        elements=({"value": "a"},),
    )
    plan = compile_program(program, catalog, operation_contracts=registry)
    step = plan.ordered_steps[0]
    assert step.transform_ref is not None
    forged_step = replace(
        step,
        transform_ref=replace(step.transform_ref, digest="f" * 64),
    )
    forged = replace(plan, ordered_steps=(forged_step,))

    from app.successor_runtime.language.plan import with_plan_digest

    assert with_plan_digest(forged).plan_digest != plan.plan_digest
    with pytest.raises(ExactContentConflict):
        decode_plan(json.loads(canonical_bytes(forged)))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("codec_id", "wrong.traversal.codec.v1", "input codec drift"),
        ("byte_size", 999999, "input byte-size drift"),
    ],
)
def test_traversal_input_codec_and_byte_size_are_exact(
    field: str,
    value: object,
    message: str,
) -> None:
    program, catalog, registry, program_input = _closure(
        policy="MATERIALIZED_SHAPE",
        elements=({"value": "a"},),
    )
    plan = compile_program(program, catalog, operation_contracts=registry)
    mutated_ref = replace(program_input.value_ref, **{field: value})
    registries = default_registries()
    with pytest.raises(ActivationError, match=message):
        activate_plan(
            run_id="run:p3:traversal:input-drift",
            program=program,
            plan=plan,
            program_input=ProgramInput(mutated_ref, program_input.value),
            transform_registry=registries.transforms,
            merge_registry=registries.merges,
            discriminator_registry=registries.discriminators,
        )
