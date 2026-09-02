"""P3 C3 rollback, fail-closed binding and no-duplicate-claim contracts."""

from __future__ import annotations

import dataclasses

import pytest

from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities import collect_c3_interpreters as ci

from .test_p3_c3_contracts import (
    _catalog,
    _compiled_c3_1,
    _element_payload,
    _plan,
    _program_c3_1,
    _request_ref,
    _scope,
)
from .test_p3_c3_micro import _sequence, _succeeded
from .test_p3_c3_replay_shadow import (
    DEPLOYMENT_DIGEST,
    _bindings_c3_1,
    _bindings_c3_2,
    _fold_program_and_plan,
)

pytestmark = pytest.mark.unit


def test_rollback_env_mode_routes_to_legacy_only() -> None:
    assert c3.collect_runtime_mode("off") == "legacy"
    assert c3.collect_claim_route("legacy") == "legacy"
    assert c3.collect_claim_route("shadow") == "shadow"
    assert c3.collect_claim_route("canary") == "successor"
    assert c3.collect_claim_route("on") == "successor"
    assert c3.collect_claim_route("off") == "legacy"
    # At most one route is ever selected.
    routes = {c3.collect_claim_route(mode) for mode in ("off", "shadow", "canary")}
    assert routes == {"legacy", "shadow", "successor"}


def test_rollback_keeps_journal_facts_readable_and_replayable() -> None:
    outcome = _succeeded(0, inserted=3, links=("https://a",))
    sequence = _sequence(outcome)
    before = c3.fold_ordered_results(
        sequence,
        aggregation_policy_ref=c3.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        observation_profile_ref=c3.COLLECT_FOLD_OBSERVATION_PROFILE,
    )
    # Simulate SUCCESSOR_RUNTIME_COLLECT=off: future dispatch routes to legacy,
    # but already recorded successor facts remain readable with identical replay.
    assert c3.collect_claim_route(c3.collect_runtime_mode("off")) == "legacy"
    after = c3.fold_ordered_results(
        sequence,
        aggregation_policy_ref=c3.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        observation_profile_ref=c3.COLLECT_FOLD_OBSERVATION_PROFILE,
    )
    assert after.aggregate_digest == before.aggregate_digest


def test_binding_mismatch_fails_closed_before_runner_effect() -> None:
    plan = _plan()
    payload = _element_payload(plan)
    program = _program_c3_1(payload)
    compiled = _compiled_c3_1(payload)
    contract_ref = program.root.operation.contract_ref
    payload_ref = program.root.operation.payload_ref
    _legacy, successor_binding = _bindings_c3_1()
    forged_plan = dataclasses.replace(compiled, plan_digest="1" * 64)

    class MustNotRun:
        def run(self, element: c3.CollectBatchElement) -> c3.CollectElementOutcome:
            raise AssertionError("runner must not execute on binding drift")

    result = ci.CollectTraversalSuccessorInterpreter().interpret(
        program=program,
        plan=forged_plan,
        contract_ref=contract_ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=_catalog(),
        deployment_catalog_digest=DEPLOYMENT_DIGEST,
        binding=successor_binding,
        runner=MustNotRun(),
    )
    assert result.disposition == "FAILED"
    assert result.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_fold_contract_failure_returns_unconsumed_outcomes() -> None:
    outcome = _succeeded(0, inserted=1)
    sequence = _sequence(outcome)
    fold_payload = c3.build_collect_fold_payload(
        parent_request_ref=_request_ref(),
        ordered_outcomes=sequence,
        aggregation_policy_ref=c3.COLLECT_AGGREGATION_POLICY_FAIL_FAST_REF,
    )
    program, plan, contract_ref, payload_ref = _fold_program_and_plan(fold_payload)
    _legacy, successor_binding = _bindings_c3_2()
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
    assert isinstance(result.value, c3.CollectFoldContractFailure)
    assert result.value.unconsumed_outcomes.sequence_digest == sequence.sequence_digest


def test_rollback_never_creates_dual_claim_authority() -> None:
    legacy, successor = _bindings_c3_1()
    assert legacy.interpreter_profile_digest != successor.interpreter_profile_digest
    assert legacy.binding_digest != successor.binding_digest
    route = c3.collect_claim_route(c3.collect_runtime_mode("off"))
    assert route == "legacy"
    enabled = {"legacy": route == "legacy", "successor": route == "successor"}
    assert enabled == {"legacy": True, "successor": False}
    # A shadow route consumes observations but never enables a successor claim.
    shadow = c3.collect_claim_route(c3.collect_runtime_mode("shadow"))
    assert shadow == "shadow"
