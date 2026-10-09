from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest
from functorial_kit import Failure

from app.successor_runtime.language.checksum import sha256_hex
from app.successor_runtime.runtime.replay import (
    ReplayEvent,
    active_child_failure_decision_digest,
    RuntimeReplayError,
    RuntimeReplayProjection,
    projection_digest,
    replay_runtime_events,
)
from app.successor_runtime.runtime.transitions import (
    EffectDisposition,
    RunState,
    StepState,
)

DIGEST = sha256_hex("p0d-replay")


def _event(
    seq: int,
    event_type: str,
    schema_version: str,
    *,
    step_id: str | None = None,
    attempt_id: str | None = None,
    metadata: dict[str, object] | None = None,
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> ReplayEvent:
    return ReplayEvent.from_content(
        project_key="project-a",
        run_id="run-a",
        run_incarnation="run-incarnation-a",
        seq=seq,
        event_type=event_type,
        schema_version=schema_version,
        step_id=step_id,
        attempt_id=attempt_id,
        metadata=metadata or {},
        payload_ref=payload_ref,
        payload_digest=payload_digest,
        authority_digest=DIGEST,
    )


def _required_failure_events() -> tuple[ReplayEvent, ...]:
    events = [
        _event(
            1,
            "ProgramAccepted",
            "mrw.runtime.event.program_accepted.v1",
            metadata={"program_id": "program-a", "program_digest": DIGEST},
        ),
        _event(
            2,
            "PlanCompiled",
            "mrw.runtime.event.plan_compiled.v1",
            metadata={"plan_id": "plan-a", "plan_digest": DIGEST},
        ),
        _event(
            3,
            "QualificationActivated",
            "mrw.runtime.event.qualification_activated.v1",
            metadata={
                "qualification_id": "qualification-a",
                "qualification_digest": DIGEST,
                "decision": "QUALIFIED",
                "reducer_event_code": "PlanCompiled",
            },
        ),
        _event(
            4,
            "DeliveryReady",
            "mrw.runtime.event.delivery_ready.v1",
            step_id="step-a",
            metadata={"assignment_digest": DIGEST},
        ),
        _event(
            5,
            "StepClaimed",
            "mrw.runtime.event.step_claimed.v1",
            step_id="step-a",
            attempt_id="attempt-a",
            metadata={
                "work_item_id": "work-a",
                "assignment_kind": "INTERPRET",
                "reconciliation_attempt_id": None,
            },
        ),
        _event(
            6,
            "EffectStarted",
            "mrw.runtime.event.effect_started.v1",
            step_id="step-a",
            attempt_id="attempt-a",
            metadata={"work_item_id": "work-a"},
        ),
    ]
    failed = _event(
        7,
        "EffectFailed",
        "mrw.runtime.event.effect_failed.v1",
        step_id="step-a",
        attempt_id="attempt-a",
        metadata={
            "status": "FAILED",
            "failure_policy_decision_digest": DIGEST,
            "required_step_failed": True,
            "required_step_failed_event_revision": 8,
        },
    )
    events.append(failed)
    events.append(
        _event(
            8,
            "RequiredStepFailed",
            "mrw.runtime.event.required_step_failed.v1",
            step_id="step-a",
            attempt_id="attempt-a",
            metadata={
                "status": "FAILED",
                "source_revision": 7,
                "source_event_digest": failed.event_digest,
                "failure_policy_decision_digest": DIGEST,
            },
        )
    )
    return tuple(events)


def _real_happy_event_shape() -> tuple[ReplayEvent, ...]:
    return (
        _event(
            1,
            "ProgramAccepted",
            "mrw.runtime.event.program_accepted.v1",
            metadata={"program_id": "program-a", "program_digest": DIGEST},
        ),
        _event(
            2,
            "CompileSucceeded",
            "mrw.runtime.event.compile-succeeded.v1",
            metadata={"plan_digest": DIGEST},
        ),
        _event(
            3,
            "PlanCompiled",
            "mrw.runtime.event.plan_compiled.v1",
            metadata={"plan_id": "plan-a", "plan_digest": DIGEST},
        ),
        _event(
            4,
            "QualificationActivated",
            "mrw.runtime.event.qualification_activated.v1",
            metadata={
                "qualification_id": "qualification-a",
                "qualification_digest": DIGEST,
                "decision": "QUALIFIED",
                "reducer_event_code": "PlanCompiled",
            },
        ),
        _event(
            5,
            "StepActivated",
            "mrw.runtime.event.step_activated.v1",
            step_id="step-a",
            metadata={
                "assignment_digest": DIGEST,
                "activation_digest": DIGEST,
                "input_closure_digest": DIGEST,
            },
        ),
        _event(
            6,
            "StepClaimed",
            "mrw.runtime.event.step_claimed.v1",
            step_id="step-a",
            attempt_id="attempt-a",
            metadata={
                "assignment_kind": "INTERPRET",
                "reconciliation_attempt_id": None,
            },
        ),
        _event(
            7,
            "EffectStarted",
            "mrw.runtime.event.effect_started.v1",
            step_id="step-a",
            attempt_id="attempt-a",
        ),
        _event(
            8,
            "RuntimeValueProduced",
            "mrw.runtime.event.effect_succeeded.v1",
            step_id="step-a",
            attempt_id="attempt-a",
        ),
        _event(
            9,
            "RunCompletionDerived",
            "mrw.runtime.event.run_completion_derived.v1",
            metadata={"required_step_ids": ["step-a"]},
        ),
    )


def _copy_event(event: ReplayEvent, **changes: object) -> ReplayEvent:
    content = {
        "project_key": event.project_key,
        "run_id": event.run_id,
        "run_incarnation": event.run_incarnation,
        "seq": event.seq,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "step_id": event.step_id,
        "attempt_id": event.attempt_id,
        "metadata": event.metadata,
        "payload_ref": event.payload_ref,
        "payload_digest": event.payload_digest,
        "authority_digest": event.authority_digest,
    }
    content.update(changes)
    return ReplayEvent.from_content(**content)


def test_explicit_required_failure_is_ordered_event_only_authority() -> None:
    projection = replay_runtime_events(_required_failure_events())

    assert projection.run_state is RunState.FAILED
    assert projection.steps == (("step-a", StepState.FAILED),)
    assert projection.required_failure_step_ids == ("step-a",)
    assert projection.observed_event_types[-2:] == (
        "EffectFailed",
        "RequiredStepFailed",
    )
    assert projection.pending_required_failure is None


def test_replay_is_deterministic_and_projection_codec_round_trips() -> None:
    first = replay_runtime_events(_required_failure_events())
    second = replay_runtime_events(_required_failure_events())
    decoded = RuntimeReplayProjection.from_json(first.to_json())

    assert first == second == decoded
    assert projection_digest(first) == projection_digest(second)


def test_replay_projection_bad_scalar_helpers_return_typed_failure_and_preserve_legacy_error() -> None:
    projection = replay_runtime_events(_required_failure_events())
    invalid_fields = (
        ("last_seq", "not-an-integer", "integer field is invalid"),
        (
            "required_failure_step_ids",
            {"bad": "string collection"},
            "string collection is invalid",
        ),
    )

    for field, value, message in invalid_fields:
        payload = projection.to_json()
        payload[field] = value

        result = RuntimeReplayProjection.from_json_result(payload)

        assert isinstance(result, Failure)
        assert result.family == "successor.runtime.failure"
        assert result.code == "REPLAY_PROJECTION_INVALID"
        assert result.context and result.context["public_exception"] == "RuntimeReplayError"
        with pytest.raises(RuntimeReplayError, match=message):
            RuntimeReplayProjection.from_json(payload)


def test_real_compile_and_activation_events_have_strict_typed_semantics() -> None:
    projection = replay_runtime_events(_real_happy_event_shape())

    assert projection.run_state is RunState.COMPLETED
    assert projection.program_digest == DIGEST
    assert projection.plan_digest == DIGEST
    assert projection.steps == (("step-a", StepState.SUCCEEDED),)
    assert projection.step_activation_bindings == (
        ("step-a", DIGEST, DIGEST, DIGEST),
    )
    assert projection.observed_event_types[:5] == (
        "ProgramAccepted",
        "CompileSucceeded",
        "PlanCompiled",
        "QualificationActivated",
        "StepActivated",
    )


def test_compile_plan_binding_and_activation_are_fail_closed() -> None:
    events = _real_happy_event_shape()
    drifted_plan = (
        events[0],
        events[1],
        _copy_event(
            events[2],
            metadata={"plan_id": "plan-a", "plan_digest": sha256_hex("other-plan")},
        ),
    )
    with pytest.raises(RuntimeReplayError, match="plan digest binding drift"):
        replay_runtime_events(drifted_plan)

    missing_activation = (
        events[0],
        _copy_event(events[2], seq=2),
        _copy_event(events[3], seq=3),
        _copy_event(events[5], seq=4),
    )
    with pytest.raises(RuntimeReplayError, match="existing READY step"):
        replay_runtime_events(missing_activation)

    missing_activation_digest = (
        *events[:4],
        _copy_event(
            events[4],
            metadata={
                "assignment_digest": DIGEST,
                "input_closure_digest": DIGEST,
            },
        ),
    )
    with pytest.raises(RuntimeReplayError, match="activation_digest"):
        replay_runtime_events(missing_activation_digest)


def test_lease_expiry_reconcile_readback_is_a_closed_event_only_stream() -> None:
    events = list(_real_happy_event_shape()[:7])
    events.extend(
        (
            _event(
                8,
                "LeaseExpiredOutcomeUnknown",
                "mrw.runtime.event.lease_expired.v1",
                step_id="step-a",
                attempt_id="attempt-a",
                metadata={
                    "work_item_id": "work-a",
                    "reconcile_work_item_id": "reconcile-a",
                    "reason_code": "LEASE_EXPIRED_OUTCOME_UNKNOWN",
                },
            ),
            _event(
                9,
                "StepClaimed",
                "mrw.runtime.event.step_claimed.v1",
                step_id="step-a",
                attempt_id="recovery-attempt-1",
                metadata={
                    "work_item_id": "reconcile-a",
                    "assignment_kind": "RECONCILE",
                    "reconciliation_attempt_id": "attempt-a",
                },
            ),
            _event(
                10,
                "LeaseExpiredOutcomeUnknown",
                "mrw.runtime.event.lease_expired.v1",
                step_id="step-a",
                attempt_id="attempt-a",
                metadata={
                    "work_item_id": "reconcile-a",
                    "reconcile_work_item_id": "reconcile-b",
                    "reason_code": "LEASE_EXPIRED_OUTCOME_UNKNOWN",
                },
            ),
            _event(
                11,
                "StepClaimed",
                "mrw.runtime.event.step_claimed.v1",
                step_id="step-a",
                attempt_id="recovery-attempt-2",
                metadata={
                    "work_item_id": "reconcile-b",
                    "assignment_kind": "RECONCILE",
                    "reconciliation_attempt_id": "attempt-a",
                },
            ),
            _event(
                12,
                "ReadbackUnavailable",
                "mrw.runtime.event.authoritative_readback.v1",
                step_id="step-a",
                attempt_id="attempt-a",
            ),
            _event(
                13,
                "ReconcileRequested",
                "mrw.runtime.event.step_claimed.v1",
                step_id="step-a",
                attempt_id="recovery-attempt-3",
                metadata={
                    "work_item_id": "reconcile-c",
                    "assignment_kind": "RECONCILE",
                    "reconciliation_attempt_id": "attempt-a",
                },
            ),
            _event(
                14,
                "AuthoritativeReadbackSucceeded",
                "mrw.runtime.event.authoritative_readback.v1",
                step_id="step-a",
                attempt_id="attempt-a",
                metadata={"status": "SUCCEEDED"},
            ),
            _event(
                15,
                "RunCompletionDerived",
                "mrw.runtime.event.run_completion_derived.v1",
                metadata={"required_step_ids": ["step-a"]},
            ),
        )
    )

    projection = replay_runtime_events(events)

    assert projection.run_state is RunState.COMPLETED
    assert projection.steps == (("step-a", StepState.SUCCEEDED),)
    assert projection.attempts[0][1].value == "SUCCEEDED"
    assert projection.observed_event_types[-8:] == (
        "LeaseExpiredOutcomeUnknown",
        "StepClaimed",
        "LeaseExpiredOutcomeUnknown",
        "StepClaimed",
        "ReadbackUnavailable",
        "ReconcileRequested",
        "AuthoritativeReadbackSucceeded",
        "RunCompletionDerived",
    )


def test_terminal_attempt_lease_expiry_preserves_and_checks_disposition() -> None:
    active = replay_runtime_events(_real_happy_event_shape()[:7])
    terminal_initial = replace(
        active,
        attempts=(("attempt-a", EffectDisposition.SUCCEEDED),),
    )
    events = (
        _event(
            8,
            "LeaseExpiredReconcileRequired",
            "mrw.runtime.event.lease_expired.v1",
            step_id="step-a",
            attempt_id="attempt-a",
            metadata={
                "work_item_id": "work-a",
                "reconcile_work_item_id": "reconcile-a",
                "reason_code": "LEASE_EXPIRED_TERMINAL_ATTEMPT_RECONCILE",
            },
        ),
        _event(
            9,
            "StepClaimed",
            "mrw.runtime.event.step_claimed.v1",
            step_id="step-a",
            attempt_id="recovery-attempt-terminal",
            metadata={
                "work_item_id": "reconcile-a",
                "assignment_kind": "RECONCILE",
                "reconciliation_attempt_id": "attempt-a",
            },
        ),
        _event(
            10,
            "AuthoritativeReadbackSucceeded",
            "mrw.runtime.event.authoritative_readback.v1",
            step_id="step-a",
            attempt_id="attempt-a",
        ),
    )

    projection = replay_runtime_events(events, initial=terminal_initial)
    assert projection.steps == (("step-a", StepState.SUCCEEDED),)
    assert projection.attempts == terminal_initial.attempts

    contradictory = _copy_event(
        events[-1], event_type="AuthoritativeReadbackFailed"
    )
    with pytest.raises(RuntimeReplayError, match="contradicts"):
        replay_runtime_events((*events[:-1], contradictory), initial=terminal_initial)


def test_recovery_claim_selects_exact_target_among_historical_attempts() -> None:
    active = replay_runtime_events(_real_happy_event_shape()[:7])
    recovering = replace(
        active,
        steps=(("step-a", StepState.RECONCILING),),
        attempts=(
            ("attempt-a", EffectDisposition.OUTCOME_UNKNOWN),
            ("attempt-historical", EffectDisposition.FAILED),
        ),
        attempt_step_bindings=(
            ("attempt-a", "step-a"),
            ("attempt-historical", "step-a"),
        ),
    )
    claim = _event(
        8,
        "StepClaimed",
        "mrw.runtime.event.step_claimed.v1",
        step_id="step-a",
        attempt_id="recovery-exact",
        metadata={
            "assignment_kind": "RECONCILE",
            "reconciliation_attempt_id": "attempt-a",
        },
    )

    projected = replay_runtime_events((claim,), initial=recovering)
    assert projected.recovery_claim_bindings == (
        ("recovery-exact", "step-a", "attempt-a"),
    )

    ambiguous_fallback = _copy_event(
        claim,
        metadata={
            "assignment_kind": "RECONCILE",
            "reconciliation_attempt_id": "absent-attempt",
        },
    )
    with pytest.raises(RuntimeReplayError, match="binding drift"):
        replay_runtime_events((ambiguous_fallback,), initial=recovering)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda events: (events[0], *events[2:]), "sequence gap"),
        (
            lambda events: (
                events[0],
                _copy_event(events[1], project_key="project-b"),
                *events[2:],
            ),
            "source identity changed",
        ),
        (
            lambda events: (
                events[0],
                replace(events[1], schema_version="mrw.runtime.event.unknown.v1"),
                *events[2:],
            ),
            "type/schema pair",
        ),
        (
            lambda events: (
                events[0],
                replace(events[1], event_digest="0" * 64),
                *events[2:],
            ),
            "event digest mismatch",
        ),
        (
            lambda events: (*events[:-1],),
            "immediately following RequiredStepFailed",
        ),
        (
            lambda events: (
                *events[:-1],
                replace(
                    events[-1],
                    metadata={
                        **events[-1].metadata,
                        "source_event_digest": DIGEST,
                    },
                    event_digest=events[-1].event_digest,
                ),
            ),
            "event digest mismatch",
        ),
    ],
)
def test_replay_fails_closed_on_sequence_schema_identity_or_digest_drift(
    mutation: Callable[[tuple[ReplayEvent, ...]], tuple[ReplayEvent, ...]],
    match: str,
) -> None:
    with pytest.raises(RuntimeReplayError, match=match):
        replay_runtime_events(mutation(_required_failure_events()))


def test_strict_legacy_composite_decoder_requires_policy_digest() -> None:
    events = list(_required_failure_events()[:-2])
    events.append(
        _event(
            7,
            "EffectFailed",
            "mrw.runtime.event.effect_failed.v1",
            step_id="step-a",
            attempt_id="attempt-a",
            metadata={
                "status": "FAILED",
                "failure_policy_decision_digest": DIGEST,
                "required_step_failed": True,
            },
        )
    )

    projection = replay_runtime_events(events)

    assert projection.run_state is RunState.FAILED
    assert projection.required_failure_step_ids == ("step-a",)

    invalid = list(events)
    invalid[-1] = _event(
        7,
        "EffectFailed",
        "mrw.runtime.event.effect_failed.v1",
        step_id="step-a",
        attempt_id="attempt-a",
        metadata={"status": "FAILED", "required_step_failed": True},
    )
    with pytest.raises(RuntimeReplayError, match="failure_policy_decision_digest"):
        replay_runtime_events(invalid)


def test_successor_materialization_is_post_run_observation_not_step_replay() -> None:
    events = [
        _event(
            1,
            "ProgramAccepted",
            "mrw.runtime.event.program_accepted.v1",
            metadata={"program_id": "program-a", "program_digest": DIGEST},
        ),
        _event(
            2,
            "PlanCompiled",
            "mrw.runtime.event.plan_compiled.v1",
            metadata={"plan_id": "plan-a", "plan_digest": DIGEST},
        ),
        _event(
            3,
            "QualificationActivated",
            "mrw.runtime.event.qualification_activated.v1",
            metadata={
                "qualification_id": "qualification-a",
                "qualification_digest": DIGEST,
                "decision": "QUALIFIED",
            },
        ),
        _event(
            4,
            "DeliveryReady",
            "mrw.runtime.event.delivery_ready.v1",
            step_id="step-a",
            metadata={"assignment_digest": DIGEST},
        ),
        _event(
            5,
            "StepClaimed",
            "mrw.runtime.event.step_claimed.v1",
            step_id="step-a",
            attempt_id="effect-attempt-a",
            metadata={
                "assignment_kind": "INTERPRET",
                "reconciliation_attempt_id": None,
            },
        ),
        _event(
            6,
            "EffectStarted",
            "mrw.runtime.event.effect_started.v1",
            step_id="step-a",
            attempt_id="effect-attempt-a",
        ),
        _event(
            7,
            "RuntimeValueProduced",
            "mrw.runtime.event.effect_succeeded.v1",
            step_id="step-a",
            attempt_id="effect-attempt-a",
        ),
        _event(
            8,
            "RunCompletionDerived",
            "mrw.runtime.event.run_completion_derived.v1",
            metadata={"required_step_ids": ["step-a"]},
        ),
        _event(
            9,
            "SuccessorMaterialized",
            "mrw.runtime.event.successor_materialized.v1",
            metadata={
                "work_item_id": "materializer-work-a",
                "source_step_id": "step-a",
                "claim_attempt_id": DIGEST,
                "assignment_digest": DIGEST,
                "handler_binding_digest": DIGEST,
                "source_value_digest": DIGEST,
                "successor_run_id": "successor-run-a",
                "successor_program_digest": DIGEST,
                "successor_plan_digest": DIGEST,
                "result_digest": DIGEST,
                "terminal_observation_ref": f"materialization:sha256:{DIGEST}",
                "predecessor_run_state": "COMPLETED",
                "predecessor_step_state": "SUCCEEDED",
            },
            payload_ref=f"materialization:sha256:{DIGEST}",
            payload_digest=DIGEST,
        ),
    ]

    projection = replay_runtime_events(events)

    assert projection.run_state is RunState.COMPLETED
    assert projection.steps == (("step-a", StepState.SUCCEEDED),)
    assert len(projection.attempts) == 1
    assert projection.attempts[0][0] == "effect-attempt-a"
    assert projection.attempts[0][1].value == "SUCCEEDED"
    assert projection.observed_event_types[-1] == "SuccessorMaterialized"

    with pytest.raises(RuntimeReplayError, match="observational"):
        replay_runtime_events((*events[:-1], _copy_event(events[-1], step_id="step-a")))


@pytest.mark.parametrize("started", [False, True])
def test_cancellation_replay_preserves_inflight_cleanup(started: bool) -> None:
    prefix = _required_failure_events()[:6 if started else 4]
    target = "CANCEL_REQUESTED" if started else "CANCELLED"
    events = (*prefix,
        _event(len(prefix) + 1, "CancellationRequested", "mrw.runtime.event.cancellation_requested.v1", metadata={"reason": "explicit_cancel"}),
        _event(len(prefix) + 2, "CancellationRequested", "mrw.runtime.event.cancellation_requested.v1", step_id="step-a", metadata={"state": target}),
    )
    projection = replay_runtime_events(events)
    assert projection.run_state is (RunState.CANCELLING if started else RunState.CANCELLED)
    assert dict(projection.steps)["step-a"].value == target
    if started:
        malformed = (*events[:-1], _event(len(prefix) + 2, "CancellationRequested",
            "mrw.runtime.event.cancellation_requested.v1", step_id="step-a", metadata={"state": "CANCELLED"}))
        with pytest.raises(RuntimeReplayError):
            replay_runtime_events(malformed)


def test_active_children_replay_waits_then_settles_exact_traversal() -> None:
    step_id = "traversal-step-a"
    events = (
        _event(1, "ProgramAccepted", "mrw.runtime.event.program_accepted.v1",
               metadata={"program_id": "program-a", "program_digest": DIGEST}),
        _event(2, "PlanCompiled", "mrw.runtime.event.plan_compiled.v1",
               metadata={"plan_id": "plan-a", "plan_digest": DIGEST}),
        _event(3, "QualificationActivated", "mrw.runtime.event.qualification_activated.v1",
               metadata={"qualification_id": "qualification-a", "qualification_digest": DIGEST,
                         "decision": "QUALIFIED", "reducer_event_code": "PlanCompiled"}),
        _event(4, "TraversalMaterializationRequested",
               "mrw.runtime.event.traversal_materialization_requested.v1",
               metadata={"source_step_id": step_id, "input_ref": "project-value:sequence",
                         "traversal_policy": "MATERIALIZED_SHAPE", "input_sequence_digest": DIGEST,
                         "element_program_digest": DIGEST, "element_count": 2,
                         "element_digests": [DIGEST, DIGEST], "shape_digest": DIGEST,
                         "binding_digest": DIGEST, "materialization_digest": DIGEST}),
        *tuple(
            _event(5 + index, "ActiveChildMaterialized",
                   "mrw.runtime.event.active_child_materialized.v1",
                   metadata={"source_step_id": step_id, "child_run_id": f"child-{index}",
                             "root_value_identity": "retrieval-budget:root",
                             "root_value_ref": "project-value:budget", "result_step_id": "result",
                             "input_ref": f"project-value:invocation-{index}",
                             "input_digest": DIGEST,
                             "materialization_digest": DIGEST, "element_index": index,
                             "element_digest": DIGEST, "child_program_digest": DIGEST,
                             "root_value_digest": DIGEST})
            for index in range(2)
        ),
        _event(7, "ActiveChildrenSettled", "mrw.runtime.event.active_children_settled.v1",
               metadata={"source_step_id": step_id, "child_count": 2,
                         "child_run_ids": ["child-0", "child-1"],
                         "child_result_digests": [DIGEST, None],
                         "result_digest": DIGEST},
               payload_ref="project-value:aggregate", payload_digest=DIGEST),
        _event(8, "RunCompletionDerived", "mrw.runtime.event.run_completion_derived.v1",
               metadata={"required_step_ids": [step_id]}),
    )

    projection = replay_runtime_events(events)

    assert projection.run_state is RunState.COMPLETED
    assert projection.steps == ((step_id, StepState.SUCCEEDED),)
    assert projection.traversal_bindings == ((step_id, DIGEST, (DIGEST, DIGEST)),)
    assert tuple(item[2] for item in projection.active_child_bindings) == (
        "child-0", "child-1",
    )

    wrong_child = list(events)
    wrong_child[4] = _event(
        5,
        "ActiveChildMaterialized",
        "mrw.runtime.event.active_child_materialized.v1",
        metadata={**dict(events[4].metadata), "element_digest": sha256_hex("wrong")},
    )
    with pytest.raises(RuntimeReplayError, match="lineage binding drift"):
        replay_runtime_events(wrong_child)

    incomplete_settlement = list(events)
    incomplete_settlement[6] = _event(
        7,
        "ActiveChildrenSettled",
        "mrw.runtime.event.active_children_settled.v1",
        metadata={
            **dict(events[6].metadata),
            "child_run_ids": ["child-0"],
        },
        payload_ref="project-value:aggregate",
        payload_digest=DIGEST,
    )
    with pytest.raises(RuntimeReplayError, match="child closure drift"):
        replay_runtime_events(incomplete_settlement)

    for replacement in (
        {"child_count": True},
        {"child_run_ids": ["child-1", "child-0"]},
        {"child_result_digests": [DIGEST]},
        {"child_result_digests": [DIGEST, "not-a-digest"]},
        {"result_digest": sha256_hex("different-result")},
    ):
        malformed = list(events)
        malformed[6] = _event(
            7, "ActiveChildrenSettled", "mrw.runtime.event.active_children_settled.v1",
            metadata={**dict(events[6].metadata), **replacement},
            payload_ref="project-value:aggregate", payload_digest=DIGEST,
        )
        with pytest.raises(RuntimeReplayError):
            replay_runtime_events(malformed)


def test_empty_active_children_replay_settles_exact_zero_cardinality() -> None:
    step_id = "empty-traversal-step"
    events = (
        _event(
            1,
            "ProgramAccepted",
            "mrw.runtime.event.program_accepted.v1",
            metadata={"program_id": "program-a", "program_digest": DIGEST},
        ),
        _event(
            2,
            "PlanCompiled",
            "mrw.runtime.event.plan_compiled.v1",
            metadata={"plan_id": "plan-a", "plan_digest": DIGEST},
        ),
        _event(
            3,
            "QualificationActivated",
            "mrw.runtime.event.qualification_activated.v1",
            metadata={
                "qualification_id": "qualification-a",
                "qualification_digest": DIGEST,
                "decision": "QUALIFIED",
                "reducer_event_code": "PlanCompiled",
            },
        ),
        _event(
            4,
            "TraversalMaterializationRequested",
            "mrw.runtime.event.traversal_materialization_requested.v1",
            metadata={
                "source_step_id": step_id,
                "input_ref": "project-value:empty-sequence",
                "traversal_policy": "MATERIALIZED_SHAPE",
                "input_sequence_digest": DIGEST,
                "element_program_digest": DIGEST,
                "element_count": 0,
                "element_digests": [],
                "shape_digest": DIGEST,
                "binding_digest": DIGEST,
                "materialization_digest": DIGEST,
            },
        ),
        _event(
            5,
            "ActiveChildrenSettled",
            "mrw.runtime.event.active_children_settled.v1",
            metadata={
                "source_step_id": step_id,
                "child_count": 0,
                "child_run_ids": [],
                "child_result_digests": [],
                "result_digest": DIGEST,
            },
            payload_ref="project-value:empty-aggregate",
            payload_digest=DIGEST,
        ),
        _event(
            6,
            "RunCompletionDerived",
            "mrw.runtime.event.run_completion_derived.v1",
            metadata={"required_step_ids": [step_id]},
        ),
    )

    projection = replay_runtime_events(events)

    assert projection.run_state is RunState.COMPLETED
    assert projection.steps == ((step_id, StepState.SUCCEEDED),)
    assert projection.traversal_bindings == ((step_id, DIGEST, ()),)
    assert projection.active_child_bindings == ()

    malformed = list(events)
    malformed[4] = _copy_event(
        events[4],
        metadata={**dict(events[4].metadata), "child_run_ids": ["invented-child"]},
    )
    with pytest.raises(RuntimeReplayError, match="child closure drift"):
        replay_runtime_events(malformed)


@pytest.mark.parametrize("started", [False, True])
def test_node_nonstart_cleanup_replay_settles_exact_attempt(started: bool) -> None:
    events = list(_required_failure_events()[:6 if started else 5])
    for kind, schema, step_id, attempt_id, metadata in (
        ("CancellationRequested", "cancellation_requested", None, None, {"reason": "explicit_cancel"}),
        ("CancellationRequested", "cancellation_requested", "step-a", None, {"state": "CANCEL_REQUESTED"}),
        ("CleanupOrReadbackConfirmed", "cancellation_cleanup_confirmed", "step-a", "attempt-a",
         {"state": "CANCELLED", "reason": "NODE_BEFORE_HANDLER"}),
        ("RequiredCleanupAndReadbackSettled", "cancellation_cleanup_settled", None, None, {"state": "CANCELLED"}),
    ):
        events.append(_event(len(events) + 1, kind, f"mrw.runtime.event.{schema}.v1",
                             step_id=step_id, attempt_id=attempt_id, metadata=metadata))
    projection = replay_runtime_events(events)
    assert projection.run_state is RunState.CANCELLED
    assert dict(projection.steps)["step-a"] is StepState.CANCELLED
    assert dict(projection.attempts)["attempt-a"] is EffectDisposition.NOT_STARTED

    for mutation in ({"attempt_id": "different-attempt"},
                     {"metadata": {"state": "CANCELLED", "reason": "BROKER_REVOKE_REQUESTED"}}):
        invalid = (*events[:-2], _copy_event(events[-2], **mutation), events[-1])
        with pytest.raises(RuntimeReplayError, match="exact cancelled attempt|attempt/step binding drift"):
            replay_runtime_events(invalid)
    premature = (*events[:-2], _event(len(events) - 1, "RequiredCleanupAndReadbackSettled",
        "mrw.runtime.event.cancellation_cleanup_settled.v1", metadata={"state": "CANCELLED"}))
    with pytest.raises(RuntimeReplayError, match="remain pending"):
        replay_runtime_events(premature)


def _active_child_failure_events() -> tuple[ReplayEvent, ...]:
    events = _required_failure_events()[:3]
    request = _event(4, "TraversalMaterializationRequested",
        "mrw.runtime.event.traversal_materialization_requested.v1",
        metadata={"source_step_id": "traverse", "input_ref": "project-value:input",
                  "traversal_policy": "MATERIALIZED_SHAPE", "input_sequence_digest": DIGEST,
                  "element_program_digest": DIGEST, "element_count": 2,
                  "element_digests": [DIGEST, DIGEST], "shape_digest": DIGEST,
                  "binding_digest": DIGEST, "materialization_digest": DIGEST})
    children = tuple(_event(5 + index, "ActiveChildMaterialized",
        "mrw.runtime.event.active_child_materialized.v1",
        metadata={"source_step_id": "traverse", "child_run_id": f"child-{index}",
                  "root_value_identity": "budget", "root_value_ref": "project-value:budget",
                  "result_step_id": "result", "input_ref": f"project-value:input-{index}",
                  "input_digest": DIGEST, "materialization_digest": DIGEST,
                  "element_index": index, "element_digest": DIGEST,
                  "child_program_digest": DIGEST, "root_value_digest": DIGEST}) for index in range(2))
    metadata = {"source_step_id": "traverse", "child_run_id": "child-0", "element_index": 0,
                "materialization_digest": DIGEST, "source_revision": 9, "source_event_digest": DIGEST}
    metadata["failure_policy_decision_digest"] = active_child_failure_decision_digest(metadata)
    failure = _event(7, "RequiredStepFailed", "mrw.runtime.event.required_step_failed.active_child.v2",
                     metadata=metadata)
    return (*events, request, *children, failure)


def test_active_child_failure_replay_preserves_run_level_cause() -> None:
    events = _active_child_failure_events()
    projection = replay_runtime_events(events)
    assert projection.run_state is RunState.FAILED
    assert projection.required_failure_step_ids == ("traverse",)
    assert events[-1].step_id is None and events[-1].attempt_id is None
    assert replay_runtime_events(events[:-1]).run_state is RunState.WAITING


@pytest.mark.parametrize(("key", "value"), [
    ("source_step_id", "other"), ("child_run_id", "child-1"), ("element_index", 1),
    ("element_index", True), ("materialization_digest", "a" * 64),
    ("source_revision", 0), ("source_event_digest", "b" * 64),
    ("failure_policy_decision_digest", "c" * 64),
])
def test_active_child_failure_replay_rejects_causal_drift(key: str, value: object) -> None:
    events = _active_child_failure_events()
    malformed = _event(7, "RequiredStepFailed", "mrw.runtime.event.required_step_failed.active_child.v2",
                       metadata={**events[-1].metadata, key: value})
    with pytest.raises(RuntimeReplayError):
        replay_runtime_events((*events[:-1], malformed))


def test_active_child_failure_cannot_impersonate_v1_effect_failure() -> None:
    events = _active_child_failure_events()
    malformed = _event(7, "RequiredStepFailed", "mrw.runtime.event.required_step_failed.v1",
                       metadata=dict(events[-1].metadata))
    with pytest.raises(RuntimeReplayError):
        replay_runtime_events((*events[:-1], malformed))


_PUBLIC_ROW: dict[str, object] = {"project_key": "project-a", "run_id": "run-a", "seq": 3, "event_type": "QualificationActivated", "schema_version": "mrw.runtime.event.qualification_activated.v1", "step_id": None, "attempt_id": None, "event_metadata_json": {"qualification_id": "qualification-a", "qualification_digest": DIGEST, "decision": "QUALIFIED", "reducer_event_code": "PlanCompiled"}, "payload_ref": None, "payload_digest": None, "authority_digest": DIGEST}


@pytest.mark.parametrize("mutation", [{"authority_digest": None}, {"payload_ref": "value:orphan"}])
def test_public_row_projection_rejects_drifted_columns(mutation: dict[str, object]) -> None:
    with pytest.raises(RuntimeReplayError):
        ReplayEvent.from_public_row({**_PUBLIC_ROW, **mutation}, run_incarnation="run-incarnation-a")


@pytest.mark.unit
def test_public_row_projection_rejects_non_mapping_metadata() -> None:
    with pytest.raises(RuntimeReplayError):
        ReplayEvent.from_public_row(
            {**_PUBLIC_ROW, "event_metadata_json": "not-a-mapping"},
            run_incarnation="run-incarnation-a",
        )
