"""P3 C3 deterministic replay and legacy/successor shadow parity."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.successor_migration import legacy_collect_runtime as lc
from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities import collect_c3_interpreters as ci
from app.successor_runtime.capabilities import collect_c3_program as cp
from app.successor_runtime.language.algebra import freeze_json_object

from .test_p3_c3_contracts import (
    PROJECT_KEY,
    REGISTRY_REVISION,
    SCOPE_DIGEST,
    _catalog,
    _compiled_c3_1,
    _element_payload,
    _plan,
    _program_c3_1,
    _registry,
    _request_ref,
    _scope,
    _snapshot,
)
from .test_p3_c3_micro import _failed, _receipt, _sequence, _succeeded

pytestmark = pytest.mark.unit

DEPLOYMENT_DIGEST = c3.deployment_catalog_digest()


def _bindings_c3_1() -> tuple[Any, Any]:
    bundle = c3.build_collect_c3_bundle()
    contract_digest = bundle.operation_c3_1.ref.contract_digest
    legacy = lc.build_legacy_collect_c3_1_binding(
        contract_digest=contract_digest,
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    successor = lc.build_successor_collect_c3_1_binding(
        contract_digest=contract_digest,
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    return legacy, successor


def _bindings_c3_2() -> tuple[Any, Any]:
    bundle = c3.build_collect_c3_bundle()
    contract_digest = bundle.operation_c3_2.ref.contract_digest
    legacy = lc.build_legacy_collect_c3_2_binding(
        contract_digest=contract_digest,
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    successor = lc.build_successor_collect_c3_2_binding(
        contract_digest=contract_digest,
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    return legacy, successor


def _fold_program_and_plan(
    payload: c3.CollectFoldPayload,
) -> tuple[Any, Any, Any, Any]:
    program = cp.build_collect_c3_2_program(
        payload=payload,
        catalog=_catalog(),
        program_id="c3-2.replay.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = cp.compile_collect_c3_program(
        program,
        _catalog(),
        operation_contracts=_registry(),
    )
    return (
        program,
        plan,
        program.root.operation.contract_ref,
        program.root.operation.payload_ref,
    )


class _SuccessorFixtureRunner:
    def run(self, element: c3.CollectBatchElement) -> c3.CollectElementOutcome:
        return _succeeded(
            element.input_index,
            inserted=len(element.query_terms),
            links=tuple(f"https://example.com/{term}" for term in element.query_terms),
        )


class _LegacyShadowRunner:
    def run(self, request: Any) -> Any:
        from app.services.collect_runtime.contracts import CollectResult

        terms = list(request.query_terms or [])
        return CollectResult(
            flow="collect",
            channel=request.channel,
            status="completed",
            inserted=len(terms),
            meta={"raw": {"links": [f"https://example.com/{term}" for term in terms]}},
        )


def _semantic_outcome(outcome: c3.CollectElementOutcome) -> tuple[Any, ...]:
    return (
        outcome.input_index,
        outcome.status,
        outcome.counts.to_plain(),
        outcome.links,
    )


def test_replay_program_plan_and_fold_are_deterministic() -> None:
    plan = _plan()
    first = _element_payload(plan)
    second = _element_payload(plan)
    assert _program_c3_1(first).program_digest == _program_c3_1(second).program_digest
    assert _compiled_c3_1(first).plan_digest == _compiled_c3_1(second).plan_digest

    outcome = _succeeded(0, inserted=2, links=("https://a",))
    sequence = _sequence(outcome)
    fold_payload = c3.build_collect_fold_payload(
        parent_request_ref=_request_ref(),
        ordered_outcomes=sequence,
    )
    aggregate = c3.fold_ordered_results(
        sequence,
        aggregation_policy_ref=c3.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        observation_profile_ref=c3.COLLECT_FOLD_OBSERVATION_PROFILE,
    )
    replay_aggregate = c3.fold_ordered_results(
        sequence,
        aggregation_policy_ref=c3.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        observation_profile_ref=c3.COLLECT_FOLD_OBSERVATION_PROFILE,
    )
    assert aggregate.aggregate_digest == replay_aggregate.aggregate_digest
    assert _fold_program_and_plan(fold_payload)[0].program_digest == (
        _fold_program_and_plan(fold_payload)[0].program_digest
    )


def test_legacy_trace_matches_successor_pure_plan() -> None:
    plan = _plan(options={"batch_parallelism": 2, "batch_fail_fast": True})
    payload = _element_payload(
        plan,
        snapshot=_snapshot(options={"batch_parallelism": 2, "batch_fail_fast": True}),
    )
    adapter = lc.LegacyCollectBatchTraverseAdapter()
    trace = adapter._trace(payload, trace_id="c3-1.trace.parity")
    assert trace.disposition == plan.disposition
    assert trace.term_batches == [
        list(element.query_terms) for element in plan.elements
    ]
    assert trace.per_batch_limit == plan.per_batch_limit
    assert trace.requested_parallelism == plan.requested_parallelism
    assert trace.effective_parallelism == plan.effective_parallelism
    assert trace.fail_fast is (
        plan.failure_policy == "FAIL_FAST_WITH_PARTIAL_OBSERVATION"
    )
    assert adapter.resolves == 0
    replay = adapter._trace(payload, trace_id="c3-1.trace.parity")
    assert replay.trace_digest == trace.trace_digest


def test_successor_legacy_element_shadow_parity() -> None:
    plan = _plan(options={"batch_parallelism": 2})
    payload = _element_payload(
        plan,
        index=0,
        snapshot=_snapshot(options={"batch_parallelism": 2}),
    )
    program = _program_c3_1(payload)
    compiled = _compiled_c3_1(payload)
    contract_ref = program.root.operation.contract_ref
    payload_ref = program.root.operation.payload_ref
    legacy_binding, successor_binding = _bindings_c3_1()

    successor_outcome = ci.CollectTraversalSuccessorInterpreter().interpret(
        program=program,
        plan=compiled,
        contract_ref=contract_ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=_catalog(),
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        binding=successor_binding,
        runner=_SuccessorFixtureRunner(),
    )
    assert successor_outcome.disposition == "SUCCEEDED"

    adapter = lc.LegacyCollectBatchTraverseAdapter()
    legacy_result = adapter.resolve(
        payload=payload,
        program=program,
        plan=compiled,
        contract_ref=contract_ref,
        payload_ref=payload_ref,
        project_scope=_scope(),
        catalog=_catalog(),
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        binding=legacy_binding,
        runner=_LegacyShadowRunner(),
    )
    assert legacy_result.disposition == "SUCCEEDED"
    legacy_observation = legacy_result.value.observation
    successor_family = ci.run_ordered_traversal(plan, _SuccessorFixtureRunner())
    assert isinstance(successor_family, c3.OrderedTraversalCompleted)
    assert [
        _semantic_outcome(outcome) for outcome in legacy_observation.ordered_outcomes
    ] == [
        _semantic_outcome(outcome)
        for outcome in successor_family.observation.ordered_outcomes
    ]
    assert (
        legacy_observation.effective_parallelism
        == successor_family.observation.effective_parallelism
    )
    assert adapter.resolves == 1


def test_successor_legacy_fold_shadow_parity() -> None:
    queued = _receipt(
        job_id="job-1",
        kind="DISPATCH_ACKNOWLEDGEMENT",
        status="queued",
    )
    readback = _receipt(
        job_id="job-2",
        kind="AUTHORITATIVE_READBACK",
        status="completed",
        raw="3" * 64,
    )
    first = _succeeded(0, inserted=2, links=("https://a", "https://b"), receipt=queued)
    second = _failed(1, message="batch exploded", terms=("t5",))
    third = _succeeded(
        2,
        inserted=3,
        links=("https://b", "https://c"),
        receipt=readback,
    )
    sequence = _sequence(first, second, third)
    fold_payload = c3.build_collect_fold_payload(
        parent_request_ref=_request_ref(),
        ordered_outcomes=sequence,
    )
    program, plan, contract_ref, payload_ref = _fold_program_and_plan(fold_payload)
    legacy_binding, successor_binding = _bindings_c3_2()

    successor_aggregate = ci.CollectFoldSuccessorInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=payload_ref,
        payload=fold_payload,
        project_scope=_scope(),
        catalog=_catalog(),
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        binding=successor_binding,
    )
    adapter = lc.LegacyCollectResultFoldAdapter()
    legacy_aggregate = adapter.fold(
        fold_payload,
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=payload_ref,
        project_scope=_scope(),
        catalog=_catalog(),
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        binding=legacy_binding,
    )
    assert successor_aggregate.disposition == "SUCCEEDED"
    assert legacy_aggregate.disposition == "SUCCEEDED"
    assert isinstance(successor_aggregate.value, c3.CollectAggregatePartial)
    assert isinstance(legacy_aggregate.value, c3.CollectAggregatePartial)
    assert (
        successor_aggregate.value.aggregate_counts
        == legacy_aggregate.value.aggregate_counts
    )
    assert successor_aggregate.value.links == legacy_aggregate.value.links
    assert [error.message for error in successor_aggregate.value.errors] == [
        error.message for error in legacy_aggregate.value.errors
    ]
    assert adapter.folds == 1


def test_legacy_and_successor_bindings_are_distinct_and_exact() -> None:
    legacy, successor = _bindings_c3_1()
    assert lc.bindings_are_distinct(legacy, successor)
    assert legacy.binding_digest == legacy.binding_digest
    assert successor.binding_digest == successor.binding_digest
    legacy2, successor2 = _bindings_c3_2()
    assert lc.bindings_are_distinct(legacy2, successor2)


def _composed_shadow_fixture() -> dict[str, Any]:
    bundle = c3.build_collect_c3_bundle()
    catalog = c3.build_collect_c3_catalog(bundle)
    registry = c3.build_collect_c3_registry(bundle)
    request_ref = c3.build_collect_request_ref(
        request_id="c3-shadow-request",
        project_key=PROJECT_KEY,
        channel="search.market",
    )
    snapshot = c3.CollectLegacyRequestSnapshot(
        schema_version=c3.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow="collect",
        channel="search.market",
        project_key=PROJECT_KEY,
        query_terms=("t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"),
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
    family_plan = c3.build_collect_batch_plan(
        request_ref=request_ref,
        snapshot=snapshot,
        plan_id="shadow.family-plan",
        resource_policy=policy,
        authority_scope_ref="project:demo_proj",
    )
    element_payloads = tuple(
        c3.collect_batch_element_payload_from_dicts(
            request_ref=request_ref.to_plain(),
            request_snapshot=snapshot.to_plain(),
            element=family_plan.elements[index].to_plain(),
            resource_policy=policy.to_plain(),
            authority_scope_ref="project:demo_proj",
        )
        for index in range(len(family_plan.elements))
    )
    program = cp.build_collect_c3_composed_program(
        element_payloads=element_payloads,
        catalog=catalog,
        program_id="c3-shadow.composed",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    from app.successor_runtime.language.compile import compile_program

    plan = compile_program(
        program,
        catalog,
        operation_contracts=registry,
        transform_registry=cp.build_collect_c3_transform_registry(),
    )
    fold_ref = bundle.operation_c3_2.ref
    legacy_binding = lc.build_legacy_collect_c3_2_binding(
        contract_digest=fold_ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    successor_binding = lc.build_successor_collect_c3_2_binding(
        contract_digest=fold_ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    return {
        "program": program,
        "plan": plan,
        "catalog": catalog,
        "legacy_binding": legacy_binding,
        "successor_binding": successor_binding,
        "element_payloads": element_payloads,
    }


def _receipt_for(index: int) -> c3.CollectAttemptReceipt:
    return c3.CollectAttemptReceipt(
        schema_version=c3.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
        receipt_kind="AUTHORITATIVE_READBACK",
        provider_type="search.market",
        provider_job_id=f"shadow-job-{index}",
        provider_status="completed",
        attempt_count=1,
        observed_at="2026-09-01T00:00:00Z",
        raw_digest=f"{index + 6:064x}",
        authoritative_readback=True,
        receipt_digest="",
    )


def test_composed_same_program_legacy_successor_shadow_parity() -> None:
    fixture = _composed_shadow_fixture()
    receipts = (_receipt_for(0), _receipt_for(1))
    legacy_outcome = lc.LegacyComposedCollectInterpreter().interpret(
        program=fixture["program"],
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["legacy_binding"],
        element_payloads=fixture["element_payloads"],
        receipts=receipts,
    )
    successor_outcome = ci.ComposedCollectSuccessorInterpreter().interpret(
        program=fixture["program"],
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["successor_binding"],
        element_payloads=fixture["element_payloads"],
        receipts=receipts,
    )
    assert legacy_outcome.disposition == "SUCCEEDED"
    assert successor_outcome.disposition == "SUCCEEDED"
    assert (
        legacy_outcome.value.aggregate_digest
        == successor_outcome.value.aggregate_digest
    )
    assert legacy_outcome.value.program_digest == fixture["program"].program_digest
    assert legacy_outcome.value.plan_digest == fixture["plan"].plan_digest
    assert legacy_outcome.value.element_count == 2
    assert legacy_outcome.value.provider_calls == 0
    assert lc.bindings_are_distinct(
        fixture["legacy_binding"], fixture["successor_binding"]
    )


def test_composed_binding_swap_fails_closed() -> None:
    fixture = _composed_shadow_fixture()
    swapped_legacy = ci.ComposedCollectSuccessorInterpreter().interpret(
        program=fixture["program"],
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["legacy_binding"],
        element_payloads=fixture["element_payloads"],
    )
    swapped_successor = lc.LegacyComposedCollectInterpreter().interpret(
        program=fixture["program"],
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["successor_binding"],
        element_payloads=fixture["element_payloads"],
    )
    assert swapped_legacy.disposition == "FAILED"
    assert swapped_legacy.code == "ASSIGNMENT_BINDING_MISMATCH"
    assert swapped_successor.disposition == "FAILED"
    assert swapped_successor.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_composed_fixture_and_program_mutation_parity_or_rejection() -> None:
    fixture = _composed_shadow_fixture()
    original = fixture["element_payloads"]
    mutated_element = c3.CollectBatchElement(
        schema_version=c3.COLLECT_BATCH_ELEMENT_SCHEMA_REF,
        element_id=original[1].element.element_id,
        input_index=original[1].element.input_index,
        query_terms=("mutated-term",),
        per_batch_limit=original[1].element.per_batch_limit,
        traversal_policy=original[1].element.traversal_policy,
        failure_policy=original[1].element.failure_policy,
        element_digest="",
    )
    mutated_payload = c3.collect_batch_element_payload_from_dicts(
        request_ref=original[1].parent_request_ref.to_plain(),
        request_snapshot=original[1].request_snapshot.to_plain(),
        element=mutated_element.to_plain(),
        resource_policy=original[1].resource_policy.to_plain(),
        authority_scope_ref=original[1].authority_scope_ref,
    )
    mutated_payloads = (original[0], mutated_payload)
    legacy_mutated = lc.LegacyComposedCollectInterpreter().interpret(
        program=fixture["program"],
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["legacy_binding"],
        element_payloads=mutated_payloads,
    )
    successor_mutated = ci.ComposedCollectSuccessorInterpreter().interpret(
        program=fixture["program"],
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["successor_binding"],
        element_payloads=mutated_payloads,
    )
    assert legacy_mutated.disposition == "SUCCEEDED"
    assert successor_mutated.disposition == "SUCCEEDED"
    assert (
        legacy_mutated.value.aggregate_digest
        == successor_mutated.value.aggregate_digest
    )

    program_metadata = dict(fixture["program"].metadata)
    program_metadata.pop("payload_content_digest", None)
    malformed_program = dataclasses.replace(
        fixture["program"],
        metadata=freeze_json_object(program_metadata),
        program_digest="",
    ).with_digest()
    legacy_rejected = lc.LegacyComposedCollectInterpreter().interpret(
        program=malformed_program,
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["legacy_binding"],
        element_payloads=original,
    )
    successor_rejected = ci.ComposedCollectSuccessorInterpreter().interpret(
        program=malformed_program,
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["successor_binding"],
        element_payloads=original,
    )
    assert legacy_rejected.disposition == "FAILED"
    assert successor_rejected.disposition == "FAILED"
    assert legacy_rejected.code == "ASSIGNMENT_BINDING_MISMATCH"
    assert successor_rejected.code == "ASSIGNMENT_BINDING_MISMATCH"
