from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from app.successor_runtime.language.checksum import sha256_hex
from app.successor_runtime.runtime.replay import (
    ReplayEvent,
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
