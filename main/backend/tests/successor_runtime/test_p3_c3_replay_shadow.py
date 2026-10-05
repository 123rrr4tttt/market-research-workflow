"""P3 C3 deterministic replay and retired historical observation contracts."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from app.successor_runtime.capabilities import acquisition_batch as acquisition
from app.successor_runtime.capabilities import acquisition_batch_interpreters as ci
from app.successor_runtime.capabilities import acquisition_batch_program as cp
from app.successor_runtime.language.algebra import freeze_json_object
from app.successor_runtime.runtime.assignments import InterpreterBinding

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

DEPLOYMENT_DIGEST = acquisition.deployment_catalog_digest()
_FRAGMENT_PATH = (
    Path(__file__).resolve().parents[4]
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C3.json"
)
_C3_1_TRACE_DIGEST = (
    "44ae32544f010fcf6ba0335ea6dd17cd14d90389c0dc1c9f11b088b9653ac9e6"
)
_C3_1_SHADOW_DIGEST = (
    "3b96bc4e3d538f156e8184f8338a231edd6f902855e2711ff2135e73bcfbad3a"
)
_C3_2_AGGREGATE_DIGEST = (
    "1f7360b77bacd26819a762984dbb656eadff05c4cc2be9b6dc736095b5ea5856"
)


def _binding(
    *,
    contract_digest: str,
    interpreter_profile_digest: str,
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=interpreter_profile_digest,
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        runtime_protocol_version="mrw.runtime.protocol.v1",
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=1,
        authority_requirement_digest=ci.authority_requirement_digest(),
    )


def _bindings_c3_1() -> tuple[InterpreterBinding, InterpreterBinding]:
    bundle = acquisition.build_acquisition_batch_bundle()
    contract_digest = bundle.execute_element_operation.ref.contract_digest
    return (
        _binding(
            contract_digest=contract_digest,
            interpreter_profile_digest=(
                ci.legacy_execute_element_interpreter_profile_digest()
            ),
        ),
        _binding(
            contract_digest=contract_digest,
            interpreter_profile_digest=(
                ci.successor_execute_element_interpreter_profile_digest()
            ),
        ),
    )


def _bindings_c3_2() -> tuple[InterpreterBinding, InterpreterBinding]:
    bundle = acquisition.build_acquisition_batch_bundle()
    contract_digest = bundle.fold_ordered_results_operation.ref.contract_digest
    return (
        _binding(
            contract_digest=contract_digest,
            interpreter_profile_digest=(
                ci.legacy_fold_ordered_results_interpreter_profile_digest()
            ),
        ),
        _binding(
            contract_digest=contract_digest,
            interpreter_profile_digest=(
                ci.successor_fold_ordered_results_interpreter_profile_digest()
            ),
        ),
    )


def _bindings_are_distinct(
    legacy: InterpreterBinding, successor: InterpreterBinding
) -> bool:
    return (
        legacy.interpreter_profile_digest != successor.interpreter_profile_digest
        and legacy.binding_digest != successor.binding_digest
    )


def _fold_program_and_plan(
    payload: acquisition.CollectFoldPayload,
) -> tuple[Any, Any, Any, Any]:
    program = cp.build_collect_fold_ordered_results_program(
        payload=payload,
        catalog=_catalog(),
        program_id="c3-2.replay.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = cp.compile_collect_program(
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
    def run(
        self, element: acquisition.CollectBatchElement
    ) -> acquisition.CollectElementOutcome:
        return _succeeded(
            element.input_index,
            inserted=len(element.query_terms),
            links=tuple(
                f"https://example.com/{term}" for term in element.query_terms
            ),
        )


def _retired_fragment() -> dict[str, Any]:
    return json.loads(_FRAGMENT_PATH.read_text(encoding="utf-8"))


def _receipt_for(index: int) -> acquisition.CollectAttemptReceipt:
    return acquisition.CollectAttemptReceipt(
        schema_version=acquisition.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
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


def test_replay_program_plan_and_fold_are_deterministic() -> None:
    plan = _plan()
    payload = _element_payload(plan)
    assert _program_c3_1(payload).program_digest == (
        _program_c3_1(_element_payload(plan)).program_digest
    )
    assert _compiled_c3_1(payload).plan_digest == (
        _compiled_c3_1(_element_payload(plan)).plan_digest
    )

    outcome = _succeeded(0, inserted=2, links=("https://a",))
    sequence = _sequence(outcome)
    fold_payload = acquisition.build_collect_fold_payload(
        parent_request_ref=_request_ref(),
        ordered_outcomes=sequence,
    )
    aggregate = acquisition.fold_ordered_results(
        sequence,
        aggregation_policy_ref=acquisition.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        observation_profile_ref=acquisition.COLLECT_FOLD_OBSERVATION_PROFILE,
    )
    replay_aggregate = acquisition.fold_ordered_results(
        sequence,
        aggregation_policy_ref=acquisition.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        observation_profile_ref=acquisition.COLLECT_FOLD_OBSERVATION_PROFILE,
    )
    assert aggregate.aggregate_digest == replay_aggregate.aggregate_digest
    assert _fold_program_and_plan(fold_payload)[0].program_digest == (
        _fold_program_and_plan(fold_payload)[0].program_digest
    )


def test_retired_legacy_observations_are_fixed_evidence_not_executable() -> None:
    cells = {
        cell["cell_id"]: cell for cell in _retired_fragment()["cells"]
    }
    assert cells["C3.1"]["legacy_observation"] == {
        "interpreter_id": "legacy.collect_runtime.batch_traverse.v1",
        "trace_digest": _C3_1_TRACE_DIGEST,
        "composed_shadow_digest": _C3_1_SHADOW_DIGEST,
        "provider_calls": 0,
    }
    assert cells["C3.2"]["legacy_observation"] == {
        "interpreter_id": "legacy.collect_runtime.result_fold.v1",
        "aggregate_digest": _C3_2_AGGREGATE_DIGEST,
        "provider_calls": 0,
    }


def test_successor_element_interpreter_preserves_plan_semantics() -> None:
    plan = _plan(options={"batch_parallelism": 2})
    payload = _element_payload(
        plan,
        index=0,
        snapshot=_snapshot(options={"batch_parallelism": 2}),
    )
    program = _program_c3_1(payload)
    compiled = _compiled_c3_1(payload)
    _legacy_binding, successor_binding = _bindings_c3_1()
    result = ci.CollectTraversalSuccessorInterpreter().interpret(
        program=program,
        plan=compiled,
        contract_ref=program.root.operation.contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=_catalog(),
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        binding=successor_binding,
        runner=_SuccessorFixtureRunner(),
    )
    assert result.disposition == "SUCCEEDED"
    family = ci.run_ordered_traversal(plan, _SuccessorFixtureRunner())
    assert isinstance(family, acquisition.OrderedTraversalCompleted)
    assert result.value == family.observation.ordered_outcomes[0]


def test_successor_fold_preserves_partial_receipt_facts() -> None:
    queued = _receipt(job_id="job-1", kind="DISPATCH_ACKNOWLEDGEMENT", status="queued")
    readback = _receipt(
        job_id="job-2",
        kind="AUTHORITATIVE_READBACK",
        status="completed",
        raw="3" * 64,
    )
    sequence = _sequence(
        _succeeded(0, inserted=2, links=("https://a", "https://b"), receipt=queued),
        _failed(1, message="batch exploded", terms=("t5",)),
        _succeeded(
            2,
            inserted=3,
            links=("https://b", "https://c"),
            receipt=readback,
        ),
    )
    fold_payload = acquisition.build_collect_fold_payload(
        parent_request_ref=_request_ref(),
        ordered_outcomes=sequence,
    )
    program, plan, contract_ref, payload_ref = _fold_program_and_plan(fold_payload)
    _legacy_binding, successor_binding = _bindings_c3_2()
    result = ci.CollectFoldSuccessorInterpreter().interpret(
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
    assert result.disposition == "SUCCEEDED"
    assert isinstance(result.value, acquisition.CollectAggregatePartial)
    assert [error.message for error in result.value.errors] == ["batch exploded"]


def test_historical_and_successor_bindings_are_distinct_and_exact() -> None:
    legacy, successor = _bindings_c3_1()
    assert _bindings_are_distinct(legacy, successor)
    assert legacy.binding_digest == legacy.binding_digest
    assert successor.binding_digest == successor.binding_digest
    legacy2, successor2 = _bindings_c3_2()
    assert _bindings_are_distinct(legacy2, successor2)


def _composed_shadow_fixture() -> dict[str, Any]:
    bundle = acquisition.build_acquisition_batch_bundle()
    catalog = acquisition.build_acquisition_batch_catalog(bundle)
    registry = acquisition.build_acquisition_batch_registry(bundle)
    request_ref = acquisition.build_collect_request_ref(
        request_id="c3-shadow-request",
        project_key=PROJECT_KEY,
        channel="search.market",
    )
    snapshot = acquisition.CollectLegacyRequestSnapshot(
        schema_version=acquisition.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow="collect",
        channel="search.market",
        project_key=PROJECT_KEY,
        query_terms=("t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"),
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
    family_plan = acquisition.build_collect_batch_plan(
        request_ref=request_ref,
        snapshot=snapshot,
        plan_id="shadow.family-plan",
        resource_policy=policy,
        authority_scope_ref="project:demo_proj",
    )
    element_payloads = tuple(
        acquisition.collect_batch_element_payload_from_dicts(
            request_ref=request_ref.to_plain(),
            request_snapshot=snapshot.to_plain(),
            element=family_plan.elements[index].to_plain(),
            resource_policy=policy.to_plain(),
            authority_scope_ref="project:demo_proj",
        )
        for index in range(len(family_plan.elements))
    )
    program = cp.build_acquisition_batch_composed_program(
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
        transform_registry=cp.build_acquisition_batch_transform_registry(),
    )
    _legacy_binding, successor_binding = _bindings_c3_2()
    return {
        "program": program,
        "plan": plan,
        "catalog": catalog,
        "legacy_binding": _legacy_binding,
        "successor_binding": successor_binding,
        "element_payloads": element_payloads,
    }


def test_composed_successor_replay_is_deterministic() -> None:
    fixture = _composed_shadow_fixture()
    outcome = ci.ComposedCollectSuccessorInterpreter().interpret(
        program=fixture["program"],
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["successor_binding"],
        element_payloads=fixture["element_payloads"],
    )
    replay = ci.ComposedCollectSuccessorInterpreter().interpret(
        program=fixture["program"],
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["successor_binding"],
        element_payloads=fixture["element_payloads"],
    )
    assert outcome.disposition == "SUCCEEDED"
    assert replay.disposition == "SUCCEEDED"
    assert outcome.value.aggregate_digest == replay.value.aggregate_digest
    assert outcome.value.aggregate_counts.inserted == 8


def test_composed_historical_binding_swap_fails_closed() -> None:
    fixture = _composed_shadow_fixture()
    result = ci.ComposedCollectSuccessorInterpreter().interpret(
        program=fixture["program"],
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["legacy_binding"],
        element_payloads=fixture["element_payloads"],
    )
    assert result.disposition == "FAILED"
    assert result.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_composed_malformed_program_binding_is_rejected() -> None:
    fixture = _composed_shadow_fixture()
    program_metadata = dict(fixture["program"].metadata)
    program_metadata.pop("payload_content_digest", None)
    malformed_program = dataclasses.replace(
        fixture["program"],
        metadata=freeze_json_object(program_metadata),
        program_digest="",
    ).with_digest()
    result = ci.ComposedCollectSuccessorInterpreter().interpret(
        program=malformed_program,
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["successor_binding"],
        element_payloads=fixture["element_payloads"],
    )
    assert result.disposition == "FAILED"
    assert result.code == "ASSIGNMENT_BINDING_MISMATCH"
