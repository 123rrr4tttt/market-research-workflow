"""P3 C3 typed contracts, plan rules, codec and blocked-traversal contracts."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

import pytest

from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities import collect_c3_interpreters as ci
from app.successor_runtime.capabilities import collect_c3_program as cp
from app.successor_runtime.language.algebra import ValueRef, freeze_json_object
from app.successor_runtime.language.checksum import sha256_hex
from app.successor_runtime.language.combinators import default_registries
from app.successor_runtime.language.plan import traversal_shape_digest
from app.successor_runtime.language.program import (
    ProgramSpec,
    traverse_ordered_node,
)
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.activation import ProgramInput, activate_plan

pytestmark = pytest.mark.unit

PROJECT_KEY = "demo_proj"
REGISTRY_REVISION = 5
SCOPE_DIGEST = "0" * 64


@dataclass(frozen=True, slots=True)
class SimpleScope:
    project_key: str
    registry_revision: int
    scope_digest: str


def _scope() -> SimpleScope:
    return SimpleScope(PROJECT_KEY, REGISTRY_REVISION, SCOPE_DIGEST)


def _bundle() -> c3.CollectC3CapabilityBundle:
    return c3.build_collect_c3_bundle()


def _catalog() -> Any:
    return c3.build_collect_c3_catalog(_bundle())


def _registry() -> Any:
    return c3.build_collect_c3_registry(_bundle())


def _request_ref(request_id: str = "req-1") -> c3.CollectRequestRef:
    return c3.build_collect_request_ref(
        request_id=request_id,
        project_key=PROJECT_KEY,
        channel="search.market",
    )


def _snapshot(
    *,
    terms: tuple[str, ...] = ("t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"),
    limit: int | None = 80,
    options: dict[str, Any] | None = None,
    source_context: dict[str, Any] | None = None,
    channel: str = "search.market",
) -> c3.CollectLegacyRequestSnapshot:
    return c3.CollectLegacyRequestSnapshot(
        schema_version=c3.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow="collect",
        channel=channel,
        project_key=PROJECT_KEY,
        query_terms=terms,
        urls=(),
        limit=limit,
        options=c3.freeze_json_object(dict(options or {})),
        source_context=c3.freeze_json_object(dict(source_context or {})),
        snapshot_digest="",
    )


def _policy(max_parallelism: int = 2) -> c3.CollectResourcePolicy:
    return c3.CollectResourcePolicy(
        schema_ref=c3.COLLECT_RESOURCE_POLICY_SCHEMA_REF,
        max_parallelism=max_parallelism,
        deadline_seconds=60,
        cancellation="COORDINATED",
        backpressure=True,
        provider_concurrency_key="search.market",
        policy_digest="",
    )


def _plan(
    *,
    plan_id: str = "c3.contracts.plan",
    static_elements: tuple[c3.CollectBatchElement, ...] | None = None,
    traversal_policy: str = "MATERIALIZED_SHAPE",
    options: dict[str, Any] | None = None,
    terms: tuple[str, ...] = ("t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"),
    limit: int | None = 80,
    channel: str = "search.market",
) -> c3.CollectBatchPlan:
    return c3.build_collect_batch_plan(
        request_ref=_request_ref(),
        snapshot=_snapshot(options=options, terms=terms, limit=limit, channel=channel),
        plan_id=plan_id,
        resource_policy=_policy(),
        authority_scope_ref="project:demo_proj",
        traversal_policy=traversal_policy,
        static_elements=static_elements,
    )


def _element_payload(
    plan: c3.CollectBatchPlan,
    *,
    index: int = 0,
    snapshot: c3.CollectLegacyRequestSnapshot | None = None,
) -> c3.CollectBatchElementPayload:
    element = plan.elements[index]
    return c3.collect_batch_element_payload_from_dicts(
        request_ref=_request_ref().to_plain(),
        request_snapshot=(snapshot or _snapshot()).to_plain(),
        element=element.to_plain(),
        resource_policy=_policy().to_plain(),
        authority_scope_ref="project:demo_proj",
    )


def _program_c3_1(payload: c3.CollectBatchElementPayload) -> Any:
    return cp.build_collect_c3_1_program(
        payload=payload,
        catalog=_catalog(),
        program_id="c3-1.contracts.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )


def _compiled_c3_1(payload: c3.CollectBatchElementPayload) -> Any:
    return cp.compile_collect_c3_program(
        _program_c3_1(payload),
        _catalog(),
        operation_contracts=_registry(),
    )


def test_operation_kinds_owners_and_catalog_are_exact() -> None:
    bundle = _bundle()
    catalog = _catalog()
    registry = _registry()
    assert c3.COLLECT_C3_1_KIND == "collect.execute_batch_element.v1"
    assert c3.COLLECT_C3_2_KIND == "collect.fold_ordered_results.v1"
    assert bundle.operation_c3_1.owner_capability_id == c3.COLLECT_C3_1_OWNER
    assert bundle.operation_c3_2.owner_capability_id == c3.COLLECT_C3_2_OWNER
    assert catalog.lookup(c3.COLLECT_C3_1_KIND) == bundle.operation_c3_1.ref
    assert catalog.lookup(c3.COLLECT_C3_2_KIND) == bundle.operation_c3_2.ref
    assert registry.resolve_required(bundle.operation_c3_1.ref).ref == (
        bundle.operation_c3_1.ref
    )
    assert registry.resolve_required(bundle.operation_c3_2.ref).ref == (
        bundle.operation_c3_2.ref
    )
    assert bundle.operation_c3_1.output_type == c3.COLLECT_C3_1_RESULT_TYPE
    assert c3.COLLECT_C3_1_RESULT_TYPE == c3.COLLECT_ELEMENT_OUTCOME_TYPE
    assert bundle.operation_c3_2.output_type == c3.COLLECT_FOLD_RESULT_TYPE


def test_schemas_and_profiles_are_frozen() -> None:
    bundle = _bundle()
    for name in (
        "COLLECT_REQUEST_SCHEMA",
        "COLLECT_REQUEST_SNAPSHOT_SCHEMA",
        "COLLECT_RESOURCE_POLICY_SCHEMA",
        "COLLECT_BATCH_ELEMENT_SCHEMA",
        "COLLECT_BATCH_PLAN_SCHEMA",
        "COLLECT_ELEMENT_OUTCOME_SCHEMA",
        "COLLECT_ATTEMPT_RECEIPT_SCHEMA",
        "COLLECT_AGGREGATE_OUTCOME_SCHEMA",
        "COLLECT_TRAVERSAL_OBSERVATION_SCHEMA",
    ):
        schema = getattr(c3, name)
        assert schema.schema_ref
        assert len(schema.schema_digest) == 64
    profiles = bundle.profiles
    assert profiles["effect.c3_1"].execution_class == "EFFECTFUL"
    assert profiles["effect.c3_2"].execution_class == "PURE_TRANSFORM"
    assert "FOLD_CONTRACT_FAILURE" in profiles["failure.c3_2"].typed_failures
    assert "TRAVERSAL_COMPILE_PENDING" in profiles["failure.c3_1"].typed_failures


def test_payload_codecs_round_trip_c3_1_and_c3_2() -> None:
    bundle = _bundle()
    plan = _plan()
    payload = _element_payload(plan)
    decoded = bundle.payload_codec_c3_1().decode_payload(
        bundle.payload_codec_c3_1().encode_payload(payload)
    )
    assert decoded.payload_digest == payload.payload_digest
    assert decoded.element.element_digest == payload.element.element_digest

    outcome = c3.CollectElementSucceeded(
        schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id="e0",
        input_index=0,
        counts=c3.CollectCounts(inserted=4),
        links=("https://example.com/a",),
        legacy_observation_ref="legacy:" + "0" * 64,
        outcome_digest="",
    )
    seq = c3.OrderedCollectElementOutcomeSequence(
        schema_version="mrw.successor.collect.c3.outcome-sequence.v1",
        parent_request_ref=_request_ref(),
        outcomes=(outcome,),
        sequence_digest="",
    )
    fold_payload = c3.build_collect_fold_payload(
        parent_request_ref=_request_ref(),
        ordered_outcomes=seq,
    )
    decoded_fold = bundle.payload_codec_c3_2().decode_payload(
        bundle.payload_codec_c3_2().encode_payload(fold_payload)
    )
    assert decoded_fold.payload_digest == fold_payload.payload_digest


def test_plan_rules_are_deterministic_legacy_compatible() -> None:
    assert (
        c3.should_auto_batch(_snapshot(terms=("a", "b", "c", "d", "e"), limit=20))
        is False
    )
    assert c3.should_auto_batch(_snapshot(terms=("a", "b", "c", "d", "e", "f"))) is True
    assert c3.should_auto_batch(_snapshot(terms=(), limit=60)) is True
    assert c3.should_auto_batch(_snapshot(channel="url_pool")) is False
    assert c3.split_query_terms(("t1", "t2", "t3", "t4", "t5")) == [
        ["t1", "t2", "t3", "t4", "t5"]
    ]
    assert c3.split_query_terms(("t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8")) == [
        ["t1", "t2", "t3", "t4"],
        ["t5", "t6", "t7", "t8"],
    ]
    assert c3.per_batch_limit_for(80, 2) == 40
    assert c3.per_batch_limit_for(9, 3) == 10
    assert (
        c3.resolve_auto_batch_parallelism(_snapshot(options={"batch_parallelism": 7}))
        == 7
    )
    assert (
        c3.resolve_auto_batch_fail_fast(_snapshot(options={"batch_fail_fast": "yes"}))
        is True
    )


def test_singleton_static_and_materialized_shape_identity() -> None:
    singleton = _plan(terms=("a", "b", "c", "d", "e"), limit=60)
    assert singleton.disposition == "SINGLETON_IDENTITY"
    assert len(singleton.elements) == 1
    assert singleton.elements[0].input_index == 0

    derived = _plan()
    assert derived.disposition == "TRAVERSE"
    static_elements = tuple(
        c3.CollectBatchElement(
            schema_version=element.schema_version,
            element_id=element.element_id,
            input_index=element.input_index,
            query_terms=element.query_terms,
            per_batch_limit=element.per_batch_limit,
            traversal_policy="STATIC_SHAPE",
            failure_policy=element.failure_policy,
            element_digest="",
        )
        for element in derived.elements
    )
    static = _plan(
        static_elements=static_elements,
        traversal_policy="STATIC_SHAPE",
    )
    assert [element.element_id for element in static.elements] == [
        element.element_id for element in derived.elements
    ]
    assert [element.query_terms for element in static.elements] == [
        element.query_terms for element in derived.elements
    ]
    assert static.per_batch_limit == derived.per_batch_limit
    assert static.plan_digest != derived.plan_digest
    assert static.traversal_policy == "STATIC_SHAPE"
    with pytest.raises(ValueError, match="STATIC_SHAPE"):
        wrong = (
            c3.CollectBatchElement(
                schema_version=c3.COLLECT_BATCH_ELEMENT_SCHEMA_REF,
                element_id=derived.elements[0].element_id,
                input_index=derived.elements[0].input_index,
                query_terms=("different",),
                per_batch_limit=derived.elements[0].per_batch_limit,
                traversal_policy="STATIC_SHAPE",
                failure_policy=derived.elements[0].failure_policy,
                element_digest="",
            ),
            derived.elements[1],
        )
        _plan(static_elements=wrong)


def test_bypass_and_element_identity_are_stable() -> None:
    bypass = _plan(
        channel="url_pool",
        terms=("a", "b", "c", "d", "e", "f", "g", "h"),
    )
    assert bypass.disposition == "BYPASSED"
    assert bypass.elements == ()
    assert bypass.batches_total == 0

    plan = _plan()
    rebuilt = c3.CollectBatchElement(
        schema_version=c3.COLLECT_BATCH_ELEMENT_SCHEMA_REF,
        element_id=plan.elements[0].element_id,
        input_index=plan.elements[0].input_index,
        query_terms=plan.elements[0].query_terms,
        per_batch_limit=plan.elements[0].per_batch_limit,
        traversal_policy=plan.elements[0].traversal_policy,
        failure_policy=plan.elements[0].failure_policy,
        element_digest="",
    )
    assert rebuilt.element_digest == plan.elements[0].element_digest


def test_plan_invariants_enforce_batches_policies_parent_and_order() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="batches_total"):
        dataclasses.replace(plan, batches_total=1)
    with pytest.raises(ValueError, match="contiguous"):
        dataclasses.replace(
            plan,
            elements=(plan.elements[1], plan.elements[0]),
        )
    with pytest.raises(ValueError, match="share traversal/failure policy"):
        dataclasses.replace(
            plan,
            elements=(
                dataclasses.replace(
                    plan.elements[0],
                    per_batch_limit=1,
                    element_digest="",
                ),
                plan.elements[1],
            ),
        )
    with pytest.raises(ValueError, match="parent plan identity"):
        dataclasses.replace(
            plan,
            elements=(
                dataclasses.replace(
                    plan.elements[0],
                    element_id="orphan:element:0",
                    element_digest="",
                ),
                plan.elements[1],
            ),
        )


def test_pure_fold_program_realizes_as_registered_transform() -> None:
    request_ref = _request_ref()
    outcome = c3.CollectElementSucceeded(
        schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id="e0",
        input_index=0,
        counts=c3.CollectCounts(inserted=1),
        legacy_observation_ref="legacy:" + "0" * 64,
        outcome_digest="",
    )
    sequence = c3.OrderedCollectElementOutcomeSequence(
        schema_version="mrw.successor.collect.c3.outcome-sequence.v1",
        parent_request_ref=request_ref,
        outcomes=(outcome,),
        sequence_digest="",
    )
    fold_payload = c3.build_collect_fold_payload(
        parent_request_ref=request_ref,
        ordered_outcomes=sequence,
    )
    program = cp.build_collect_c3_2_pure_fold_program(
        payload=fold_payload,
        catalog=_catalog(),
        program_id="c3-2.pure-fold",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    from app.successor_runtime.language.compile import compile_program

    plan = compile_program(
        program,
        _catalog(),
        operation_contracts=_registry(),
        transform_registry=cp.build_collect_c3_transform_registry(),
    )
    assert [step.step_kind for step in plan.ordered_steps] == ["TRANSFORM"]
    assert plan.ordered_steps[0].transform_ref.name == cp.COLLECT_FOLD_TRANSFORM_NAME
    assert plan.ordered_steps[0].effect_profile_ref == "PURE_TRANSFORM"
    assert plan.output_type.type_id == c3.COLLECT_FOLD_RESULT_TYPE.type_id


def test_composed_program_binds_traverse_epoch_and_fold_contract() -> None:
    plan = _plan()
    payloads = tuple(
        _element_payload(plan, index=index) for index in range(len(plan.elements))
    )
    program = cp.build_collect_c3_composed_program(
        element_payloads=payloads,
        catalog=_catalog(),
        program_id="c3.composed",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    from app.successor_runtime.language.compile import compile_program

    compiled = compile_program(
        program,
        _catalog(),
        operation_contracts=_registry(),
        transform_registry=cp.build_collect_c3_transform_registry(),
    )
    kinds = [
        (step.step_kind, step.transform_ref.name if step.transform_ref else None)
        for step in compiled.ordered_steps
    ]
    assert kinds == [
        ("TRANSFORM", "mrw.traverse_ordered.materialize"),
        ("TRANSFORM", "collect.sequence_to_fold_payload"),
        ("EFFECT", None),
    ]
    effect = next(
        step
        for step in compiled.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    )
    assert effect.operation_contract_ref.kind == c3.COLLECT_C3_2_KIND
    assert compiled.output_type.type_id == c3.COLLECT_FOLD_RESULT_TYPE.type_id
    assert compiled.input_type.type_id.startswith("sequence:")
    assert dict(program.metadata)["compiled_traversal"] is True


def test_single_atom_program_compiles_without_faking_traversal() -> None:
    plan = _plan()
    payload = _element_payload(plan)
    program = _program_c3_1(payload)
    compiled = _compiled_c3_1(payload)
    assert program.program_digest == program.digest()
    assert compiled.program_digest == program.program_digest
    effect_steps = [
        step for step in compiled.ordered_steps if step.step_kind == "EFFECT"
    ]
    assert len(effect_steps) == 1
    assert effect_steps[0].operation_contract_ref.kind == c3.COLLECT_C3_1_KIND
    assert not any(step.step_kind == "ADMISSION" for step in compiled.ordered_steps)
    assert dict(program.metadata)["compiled_traversal"] is False


def test_materialized_traversal_compiles_with_occurrence_binding() -> None:
    plan = _plan()
    payload = _element_payload(plan)
    declared = cp.build_declared_traversal_program(
        element_payload=payload,
        catalog=_catalog(),
        program_id="c3-1.declared",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    status = cp.compile_declared_traversal_program(
        declared,
        _catalog(),
        operation_contracts=_registry(),
    )
    assert status.compiled is True
    assert status.code == cp.TRAVERSAL_COMPILED_CODE
    assert status.plan_digest is not None
    assert status.program_digest == declared.program_digest
    compiled_plan = _compiled_traversal_plan(declared)
    binding = ci.require_exact_traversal_binding(
        program=declared,
        plan=compiled_plan,
        catalog=_catalog(),
    )
    assert len(str(binding["traversal_binding_digest"])) == 64


def _compiled_traversal_plan(declared: Any) -> Any:
    from app.successor_runtime.language.compile import compile_program

    return compile_program(
        declared,
        _catalog(),
        operation_contracts=_registry(),
    )


def test_static_traversal_requires_exact_shape_binding() -> None:
    plan = _plan()
    payload = _element_payload(plan)
    atom_program = _program_c3_1(payload)
    root = traverse_ordered_node(atom_program.root, traversal_policy="STATIC_SHAPE")
    blocked = ProgramSpec(
        program_id="c3-1.declared-static-blocked",
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        semantic_identity=c3.COLLECT_C3_1_SEMANTIC_IDENTITY,
        input_type=root.input_type,
        output_type=root.output_type,
        root=root,
        algebra_refs=atom_program.algebra_refs,
        transform_refs=(),
        observation_profile=c3.COLLECT_TRAVERSAL_OBSERVATION_PROFILE,
        metadata=freeze_json_object(
            {
                "schema": "mrw.successor.collect.c3.declared-traversal.v1",
                "operation_kind": c3.COLLECT_C3_1_KIND,
                "traversal_policy": "STATIC_SHAPE",
                "compiled_traversal": True,
                "program_id": "c3-1.declared-static-blocked",
                "element_program_digest": atom_program.program_digest,
            }
        ),
        program_digest="",
    ).with_digest()
    status = cp.compile_declared_traversal_program(
        blocked,
        _catalog(),
        operation_contracts=_registry(),
    )
    assert status.compiled is False
    assert status.code == "TRAVERSAL_SHAPE_BINDING_REQUIRED"


def test_static_traversal_with_exact_shape_metadata_compiles() -> None:
    plan = _plan()
    payload = _element_payload(plan)
    element_payloads = tuple(
        _element_payload(plan, index=index) for index in range(len(plan.elements))
    )
    shape_digest = traversal_shape_digest(element_payloads)
    declared = cp.build_declared_traversal_program(
        element_payload=payload,
        catalog=_catalog(),
        program_id="c3-1.declared-static",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        traversal_policy="STATIC_SHAPE",
        static_shape_digest=shape_digest,
        static_element_count=len(plan.elements),
    )
    status = cp.compile_declared_traversal_program(
        declared,
        _catalog(),
        operation_contracts=_registry(),
    )
    assert status.compiled is True
    assert status.code == cp.TRAVERSAL_COMPILED_CODE
    binding = ci.require_exact_traversal_binding(
        program=declared,
        plan=_compiled_traversal_plan(declared),
        catalog=_catalog(),
    )
    assert binding["traversal_element_count"] == len(plan.elements)

    sequence_bytes = canonical_bytes(list(element_payloads))
    sequence_ref = ValueRef(
        value_id="value:c3:static-traversal-elements",
        project_key=PROJECT_KEY,
        object_type=declared.input_type,
        codec_id=declared.input_type.codec_id,
        content_digest=sha256_hex(list(element_payloads)),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref="project-value:c3:static-traversal-elements",
        byte_size=len(sequence_bytes),
        provenance_digest="9" * 64,
    )
    registries = default_registries()
    activated = activate_plan(
        run_id="run:c3:static-traversal",
        program=declared,
        plan=_compiled_traversal_plan(declared),
        program_input=ProgramInput(sequence_ref, element_payloads),
        transform_registry=registries.transforms,
        merge_registry=registries.merges,
        discriminator_registry=registries.discriminators,
    )
    assert activated.traversal_materializations[0].shape_digest == shape_digest


def test_deployment_catalog_digest_is_distinct_from_operation_catalog() -> None:
    catalog = _catalog()
    deployment = c3.deployment_catalog_digest()
    assert len(deployment) == 64
    assert deployment != catalog.catalog_digest
    assert catalog.lookup(c3.COLLECT_C3_1_KIND).contract_digest != deployment


def test_collect_runtime_mode_is_fail_closed() -> None:
    assert c3.collect_runtime_mode("off") == "legacy"
    assert c3.collect_runtime_mode(None) == "legacy"
    assert c3.collect_runtime_mode("weird") == "legacy"
    assert c3.collect_runtime_mode("shadow") == "shadow"
    assert c3.collect_runtime_mode("canary") == "canary"
    assert c3.collect_runtime_mode("on") == "on"
