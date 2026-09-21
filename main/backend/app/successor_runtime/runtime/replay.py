"""Pure, fail-closed replay of the successor runtime journal.

The operational ``runtime_runs`` and ``runtime_steps`` rows are useful CAS
snapshots, but they are not an input to this reducer.  A read model is derived
only from the ordered runtime event stream.  PostgreSQL projectors may persist
the returned projection, but cannot feed it back into runtime control.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeVar, cast

from functorial_kit import Failure

from app.successor_runtime.language.checksum import is_sha256_hex, sha256_hex
from app.successor_runtime.runtime.transitions import (
    EffectDisposition,
    RunEvent,
    RunState,
    StepEvent,
    StepState,
)

from .failure_policy import raise_runtime_failure, runtime_failure


class RuntimeReplayError(ValueError):
    """The journal cannot be interpreted without weakening frozen semantics."""


_ReplayValue = TypeVar("_ReplayValue")


def _replay_failure(
    code: str | object,
    message: object | None = None,
    *,
    site: str = "successor_runtime.runtime.replay",
) -> Failure:
    if message is None:
        code, message = "REPLAY_STATE_INVALID", code
    return runtime_failure(code, message, RuntimeReplayError, site=site)


def _legacy_lift(value: _ReplayValue | Failure) -> _ReplayValue:
    if isinstance(value, Failure):
        raise_runtime_failure(value, RuntimeReplayError)
    return value


_EVENT_SCHEMAS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "ProgramAccepted": frozenset({"mrw.runtime.event.program_accepted.v1"}),
        "CompileSucceeded": frozenset(
            {"mrw.runtime.event.compile-succeeded.v1"}
        ),
        "PlanCompiled": frozenset({"mrw.runtime.event.plan_compiled.v1"}),
        "QualificationActivated": frozenset(
            {"mrw.runtime.event.qualification_activated.v1"}
        ),
        "DeliveryReady": frozenset({"mrw.runtime.event.delivery_ready.v1"}),
        "StepActivated": frozenset({"mrw.runtime.event.step_activated.v1"}),
        StepEvent.STEP_CLAIMED.value: frozenset({"mrw.runtime.event.step_claimed.v1"}),
        StepEvent.RECONCILE_REQUESTED.value: frozenset(
            {"mrw.runtime.event.step_claimed.v1"}
        ),
        StepEvent.EFFECT_STARTED.value: frozenset(
            {"mrw.runtime.event.effect_started.v1"}
        ),
        StepEvent.EFFECT_FAILED.value: frozenset(
            {"mrw.runtime.event.effect_failed.v1"}
        ),
        StepEvent.RUNTIME_VALUE_PRODUCED.value: frozenset(
            {"mrw.runtime.event.effect_succeeded.v1"}
        ),
        StepEvent.OUTCOME_STAGED.value: frozenset(
            {"mrw.runtime.event.effect_succeeded.v1"}
        ),
        StepEvent.COMMIT_PREPARED.value: frozenset(
            {"mrw.runtime.event.commit_prepared.v1"}
        ),
        StepEvent.COMMIT_READBACK_CONFIRMED.value: frozenset(
            {"mrw.runtime.event.commit_readback_confirmed.v1"}
        ),
        StepEvent.EFFECT_RECEIPT_LOST.value: frozenset(
            {"mrw.runtime.event.outcome_unknown.v1"}
        ),
        StepEvent.AUTHORITATIVE_READBACK_SUCCEEDED.value: frozenset(
            {"mrw.runtime.event.authoritative_readback.v1"}
        ),
        StepEvent.AUTHORITATIVE_READBACK_FAILED.value: frozenset(
            {"mrw.runtime.event.authoritative_readback.v1"}
        ),
        StepEvent.READBACK_UNAVAILABLE.value: frozenset(
            {"mrw.runtime.event.authoritative_readback.v1"}
        ),
        RunEvent.REQUIRED_STEP_FAILED.value: frozenset(
            {"mrw.runtime.event.required_step_failed.v1"}
        ),
        RunEvent.RUN_COMPLETION_DERIVED.value: frozenset(
            {"mrw.runtime.event.run_completion_derived.v1"}
        ),
        "LeaseExpiredOutcomeUnknown": frozenset({"mrw.runtime.event.lease_expired.v1"}),
        "LeaseExpiredReconcileRequired": frozenset(
            {"mrw.runtime.event.lease_expired.v1"}
        ),
        "SuccessorMaterialized": frozenset(
            {"mrw.runtime.event.successor_materialized.v1"}
        ),
    }
)


def _validate_replay_event(event: ReplayEvent) -> None | Failure:
    try:
        if not event.project_key or not event.run_id or not event.run_incarnation:
            return _replay_failure("REPLAY_EVENT_INVALID", "event source identity is incomplete")
        if event.seq < 1:
            return _replay_failure("REPLAY_EVENT_INVALID", "event seq must be positive")
        allowed = _EVENT_SCHEMAS.get(event.event_type)
        if allowed is None or event.schema_version not in allowed:
            return _replay_failure(
                "REPLAY_EVENT_INVALID",
                "event type/schema pair is not in the frozen replay registry: "
                f"{event.event_type!r}/{event.schema_version!r}",
            )
        if (event.payload_ref is None) != (event.payload_digest is None):
            return _replay_failure(
                "REPLAY_EVENT_INVALID", "event payload ref/digest must be an exact pair"
            )
        for name, digest in (
            ("payload_digest", event.payload_digest),
            ("authority_digest", event.authority_digest),
            ("event_digest", event.event_digest),
        ):
            if digest is not None and not is_sha256_hex(digest):
                return _replay_failure(
                    "REPLAY_EVENT_INVALID", f"{name} is not a canonical SHA-256 digest"
                )
        canonical_metadata = dict(event.metadata)
        object.__setattr__(event, "metadata", MappingProxyType(canonical_metadata))
        expected = runtime_event_digest(
            project_key=event.project_key,
            run_id=event.run_id,
            run_incarnation=event.run_incarnation,
            seq=event.seq,
            event_type=event.event_type,
            schema_version=event.schema_version,
            step_id=event.step_id,
            attempt_id=event.attempt_id,
            metadata=canonical_metadata,
            payload_ref=event.payload_ref,
            payload_digest=event.payload_digest,
            authority_digest=event.authority_digest,
        )
        if event.event_digest != expected:
            return _replay_failure("REPLAY_EVENT_INVALID", "runtime event digest mismatch")
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        return _replay_failure("REPLAY_EVENT_INVALID", str(exc))
    return None


def runtime_event_digest(
    *,
    project_key: str,
    run_id: str,
    run_incarnation: str,
    seq: int,
    event_type: str,
    schema_version: str,
    step_id: str | None,
    attempt_id: str | None,
    metadata: Mapping[str, object],
    payload_ref: str | None,
    payload_digest: str | None,
    authority_digest: str,
) -> str:
    """Digest the complete replay-visible identity and event payload closure."""

    return sha256_hex(
        {
            "project_key": project_key,
            "run_id": run_id,
            "run_incarnation": run_incarnation,
            "seq": seq,
            "event_type": event_type,
            "schema_version": schema_version,
            "step_id": step_id,
            "attempt_id": attempt_id,
            "metadata": dict(metadata),
            "payload_ref": payload_ref,
            "payload_digest": payload_digest,
            "authority_digest": authority_digest,
        }
    )


@dataclass(frozen=True, slots=True)
class ReplayEvent:
    project_key: str
    run_id: str
    run_incarnation: str
    seq: int
    event_type: str
    schema_version: str
    step_id: str | None
    attempt_id: str | None
    metadata: Mapping[str, object]
    payload_ref: str | None
    payload_digest: str | None
    authority_digest: str
    event_digest: str

    def __post_init__(self) -> None:
        failure = _validate_replay_event(self)
        if isinstance(failure, Failure):
            raise_runtime_failure(failure, RuntimeReplayError)

    @classmethod
    def from_content(cls, **content: object) -> ReplayEvent:
        return _legacy_lift(cls.from_content_result(**content))

    @classmethod
    def from_content_result(cls, **content: object) -> ReplayEvent | Failure:
        """Construct an event as a closed replay result."""

        if "event_digest" in content:
            return _replay_failure(
                "REPLAY_EVENT_INVALID",
                "event_digest is derived, not caller supplied",
                site="successor_runtime.runtime.replay.ReplayEvent.from_content",
            )
        try:
            digest = runtime_event_digest(**content)  # type: ignore[arg-type]
            return cls(**content, event_digest=digest)  # type: ignore[arg-type]
        except (RuntimeReplayError, TypeError, ValueError, KeyError, AttributeError) as exc:
            return _replay_failure(
                "REPLAY_EVENT_INVALID",
                str(exc),
                site="successor_runtime.runtime.replay.ReplayEvent.from_content",
            )


@dataclass(frozen=True, slots=True)
class RuntimeReplayProjection:
    project_key: str
    run_id: str
    run_incarnation: str
    run_state: RunState
    last_seq: int
    event_chain_digest: str
    program_digest: str
    plan_digest: str | None = None
    steps: tuple[tuple[str, StepState], ...] = ()
    step_activation_bindings: tuple[tuple[str, str, str, str], ...] = ()
    attempts: tuple[tuple[str, EffectDisposition], ...] = ()
    attempt_step_bindings: tuple[tuple[str, str], ...] = ()
    recovery_claim_bindings: tuple[tuple[str, str, str], ...] = ()
    required_failure_step_ids: tuple[str, ...] = ()
    observed_event_types: tuple[str, ...] = ()
    pending_required_failure: tuple[int, str, str, str] | None = None

    def __post_init__(self) -> None:
        failure = self._validate()
        if isinstance(failure, Failure):
            raise_runtime_failure(failure, RuntimeReplayError)

    def _validate(self) -> None | Failure:
        if self.last_seq < 1:
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection must contain ProgramAccepted")
        if not is_sha256_hex(self.event_chain_digest):
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection event chain digest is invalid")
        if not is_sha256_hex(self.program_digest):
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection program digest is invalid")
        if self.plan_digest is not None and not is_sha256_hex(self.plan_digest):
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection plan digest is invalid")
        if tuple(sorted(self.steps)) != self.steps:
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection steps are not canonically ordered")
        if tuple(sorted(self.step_activation_bindings)) != self.step_activation_bindings:
            return _replay_failure(
                "REPLAY_PROJECTION_INVALID",
                "projection step activation bindings are not canonically ordered"
            )
        activation_step_ids: set[str] = set()
        for (
            step_id,
            assignment_digest,
            activation_digest,
            input_closure_digest,
        ) in self.step_activation_bindings:
            if not step_id or step_id in activation_step_ids:
                return _replay_failure(
                    "REPLAY_PROJECTION_INVALID",
                    "projection step activation identity is absent or duplicated"
                )
            activation_step_ids.add(step_id)
            if not all(
                is_sha256_hex(value)
                for value in (
                    assignment_digest,
                    activation_digest,
                    input_closure_digest,
                )
            ):
                return _replay_failure(
                    "REPLAY_PROJECTION_INVALID",
                    "projection step activation binding digest is invalid"
                )
        if tuple(sorted(self.attempts)) != self.attempts:
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection attempts are not canonically ordered")
        if tuple(sorted(self.attempt_step_bindings)) != self.attempt_step_bindings:
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection attempt bindings are not ordered")
        attempt_binding_ids = [item[0] for item in self.attempt_step_bindings]
        recovery_binding_ids = [item[0] for item in self.recovery_claim_bindings]
        projected_step_ids = {item[0] for item in self.steps}
        if len(attempt_binding_ids) != len(set(attempt_binding_ids)):
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection attempt binding identity is duplicated")
        if any(item[1] not in projected_step_ids for item in self.attempt_step_bindings):
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection attempt references an absent step")
        if {item[0] for item in self.attempts} != {
            item[0] for item in self.attempt_step_bindings
        }:
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection attempt/step closure is incomplete")
        if tuple(sorted(self.recovery_claim_bindings)) != self.recovery_claim_bindings:
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection recovery claim bindings are not ordered")
        if len(recovery_binding_ids) != len(set(recovery_binding_ids)):
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection recovery claim identity is duplicated")
        if any(
            item[1] not in projected_step_ids
            for item in self.recovery_claim_bindings
        ):
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection recovery claim references an absent step")
        attempt_binding_map = dict(self.attempt_step_bindings)
        if any(
            target_attempt_id not in attempt_binding_map
            or attempt_binding_map[target_attempt_id] != step_id
            for _, step_id, target_attempt_id in self.recovery_claim_bindings
        ):
            return _replay_failure("REPLAY_PROJECTION_INVALID", "projection recovery claim target closure is invalid")
        if set(attempt_binding_ids) & set(recovery_binding_ids):
            return _replay_failure("REPLAY_PROJECTION_INVALID", "effect attempt and recovery claim identities overlap")

    def to_json(self) -> dict[str, object]:
        return {
            "schema": "mrw.runtime.run-projection.v1",
            "project_key": self.project_key,
            "run_id": self.run_id,
            "run_incarnation": self.run_incarnation,
            "run_state": self.run_state.value,
            "last_seq": self.last_seq,
            "event_chain_digest": self.event_chain_digest,
            "program_digest": self.program_digest,
            "plan_digest": self.plan_digest,
            "steps": [
                {"step_id": step_id, "state": state.value}
                for step_id, state in self.steps
            ],
            "step_activation_bindings": [
                {
                    "step_id": step_id,
                    "assignment_digest": assignment_digest,
                    "activation_digest": activation_digest,
                    "input_closure_digest": input_closure_digest,
                }
                for (
                    step_id,
                    assignment_digest,
                    activation_digest,
                    input_closure_digest,
                ) in self.step_activation_bindings
            ],
            "attempts": [
                {"attempt_id": attempt_id, "disposition": disposition.value}
                for attempt_id, disposition in self.attempts
            ],
            "attempt_step_bindings": [
                {"attempt_id": attempt_id, "step_id": step_id}
                for attempt_id, step_id in self.attempt_step_bindings
            ],
            "recovery_claim_bindings": [
                {
                    "attempt_id": attempt_id,
                    "step_id": step_id,
                    "reconciliation_attempt_id": reconciliation_attempt_id,
                }
                for attempt_id, step_id, reconciliation_attempt_id in self.recovery_claim_bindings
            ],
            "required_failure_step_ids": list(self.required_failure_step_ids),
            "observed_event_types": list(self.observed_event_types),
            "pending_required_failure": (
                None
                if self.pending_required_failure is None
                else {
                    "expected_seq": self.pending_required_failure[0],
                    "step_id": self.pending_required_failure[1],
                    "attempt_id": self.pending_required_failure[2],
                    "source_event_digest": self.pending_required_failure[3],
                }
            ),
        }

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> RuntimeReplayProjection:
        return _legacy_lift(cls.from_json_result(value))

    @classmethod
    def from_json_result(
        cls, value: Mapping[str, object]
    ) -> RuntimeReplayProjection | Failure:
        """Decode a projection as a closed replay result."""

        try:
            return cls._decode_json(value)
        except (RuntimeReplayError, TypeError, ValueError, KeyError, AttributeError) as exc:
            return _replay_failure(
                "REPLAY_PROJECTION_INVALID",
                str(exc),
                site="successor_runtime.runtime.replay.RuntimeReplayProjection.from_json",
            )

    @classmethod
    def _decode_json(cls, value: Mapping[str, object]) -> RuntimeReplayProjection:
        if value.get("schema") != "mrw.runtime.run-projection.v1":
            return cast(RuntimeReplayProjection, _replay_failure(
                "REPLAY_PROJECTION_INVALID", "runtime projection schema mismatch"
            ))
        raw_steps = value.get("steps")
        raw_activation_bindings = value.get("step_activation_bindings")
        raw_attempts = value.get("attempts")
        raw_attempt_step_bindings = value.get("attempt_step_bindings")
        raw_recovery_claim_bindings = value.get("recovery_claim_bindings")
        if (
            not isinstance(raw_steps, list)
            or not isinstance(raw_activation_bindings, list)
            or not isinstance(raw_attempts, list)
            or not isinstance(raw_attempt_step_bindings, list)
            or not isinstance(raw_recovery_claim_bindings, list)
        ):
            return cast(RuntimeReplayProjection, _replay_failure(
                "REPLAY_PROJECTION_INVALID", "runtime projection state collections are invalid"
            ))
        pending = value.get("pending_required_failure")
        pending_tuple = None
        if pending is not None:
            if not isinstance(pending, Mapping):
                return cast(RuntimeReplayProjection, _replay_failure(
                    "REPLAY_PROJECTION_INVALID", "pending required failure is invalid"
                ))
            pending_tuple = (
                int(pending["expected_seq"]),
                str(pending["step_id"]),
                str(pending["attempt_id"]),
                str(pending["source_event_digest"]),
            )
        return cls(
            project_key=str(value["project_key"]),
            run_id=str(value["run_id"]),
            run_incarnation=str(value["run_incarnation"]),
            run_state=RunState(str(value["run_state"])),
            last_seq=int(value["last_seq"]),
            event_chain_digest=str(value["event_chain_digest"]),
            program_digest=str(value["program_digest"]),
            plan_digest=(
                None
                if value.get("plan_digest") is None
                else str(value["plan_digest"])
            ),
            steps=tuple(
                sorted(
                    (str(item["step_id"]), StepState(str(item["state"])))
                    for item in raw_steps
                    if isinstance(item, Mapping)
                )
            ),
            step_activation_bindings=tuple(
                sorted(
                    (
                        str(item["step_id"]),
                        str(item["assignment_digest"]),
                        str(item["activation_digest"]),
                        str(item["input_closure_digest"]),
                    )
                    for item in raw_activation_bindings
                    if isinstance(item, Mapping)
                )
            ),
            attempts=tuple(
                sorted(
                    (
                        str(item["attempt_id"]),
                        EffectDisposition(str(item["disposition"])),
                    )
                    for item in raw_attempts
                    if isinstance(item, Mapping)
                )
            ),
            attempt_step_bindings=tuple(
                sorted(
                    (str(item["attempt_id"]), str(item["step_id"]))
                    for item in raw_attempt_step_bindings
                    if isinstance(item, Mapping)
                )
            ),
            recovery_claim_bindings=tuple(
                sorted(
                    (
                        str(item["attempt_id"]),
                        str(item["step_id"]),
                        str(item["reconciliation_attempt_id"]),
                    )
                    for item in raw_recovery_claim_bindings
                    if isinstance(item, Mapping)
                )
            ),
            required_failure_step_ids=tuple(
                str(item) for item in value.get("required_failure_step_ids", [])
            ),
            observed_event_types=tuple(
                str(item) for item in value.get("observed_event_types", [])
            ),
            pending_required_failure=pending_tuple,
        )

def _replay_runtime_events_impl(
    events: Iterable[ReplayEvent],
    *,
    initial: RuntimeReplayProjection | None = None,
    require_closed_batch: bool = True,
) -> RuntimeReplayProjection | Failure:
    """Fold an ordered event batch, rejecting gaps and semantic drift."""

    projection = initial
    for event in events:
        projection = _apply_event(projection, event)
        if isinstance(projection, Failure):
            return projection
    if projection is None:
        return _replay_failure("REPLAY_EVENT_INVALID", "runtime replay requires at least one event")
    if require_closed_batch and projection.pending_required_failure is not None:
        return _replay_failure(
            "REPLAY_STATE_INVALID",
            "EffectFailed requires the immediately following RequiredStepFailed event"
        )
    return projection


def _projection_result(**values: object) -> RuntimeReplayProjection | Failure:
    try:
        return RuntimeReplayProjection(**values)  # type: ignore[arg-type]
    except (RuntimeReplayError, TypeError, ValueError, KeyError, AttributeError) as exc:
        return _replay_failure(
            "REPLAY_PROJECTION_INVALID",
            str(exc),
            site="successor_runtime.runtime.replay.RuntimeReplayProjection",
        )


def replay_runtime_events_result(
    events: Iterable[ReplayEvent],
    *,
    initial: RuntimeReplayProjection | None = None,
    require_closed_batch: bool = True,
) -> RuntimeReplayProjection | Failure:
    """Return a replay projection or a closed runtime failure value."""

    try:
        result = _replay_runtime_events_impl(
            events,
            initial=initial,
            require_closed_batch=require_closed_batch,
        )
        if isinstance(result, Failure) and result.code == "REPLAY_STATE_INVALID":
            message = result.message
            if "sequence" in message or "seq" in message:
                code = "REPLAY_SEQUENCE_INVALID"
            elif "binding" in message or "identity" in message:
                code = "REPLAY_BINDING_DRIFT"
            elif "event" in message and "state" not in message:
                code = "REPLAY_EVENT_INVALID"
            else:
                code = result.code
            if code != result.code:
                return _replay_failure(code, message, site="successor_runtime.runtime.replay.replay_runtime_events")
        return result
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        return _replay_failure(
            "REPLAY_EVENT_INVALID",
            str(exc),
            site="successor_runtime.runtime.replay.replay_runtime_events",
        )


def replay_runtime_events(
    events: Iterable[ReplayEvent],
    *,
    initial: RuntimeReplayProjection | None = None,
    require_closed_batch: bool = True,
) -> RuntimeReplayProjection:
    """Legacy exception ABI over :func:`replay_runtime_events_result`."""

    result = replay_runtime_events_result(
        events,
        initial=initial,
        require_closed_batch=require_closed_batch,
    )
    return _legacy_lift(result)


def projection_digest(projection: RuntimeReplayProjection) -> str:
    return sha256_hex(projection.to_json())


def _apply_event(
    projection: RuntimeReplayProjection | None, event: ReplayEvent
) -> RuntimeReplayProjection | Failure:
    if projection is None:
        if event.seq != 1 or event.event_type != "ProgramAccepted":
            return _replay_failure(
                "runtime journal must begin with ProgramAccepted seq=1"
            )
        identity = _require_run_identity(event)
        if isinstance(identity, Failure):
            return identity
        program_digest = _require_metadata_digest(event, "program_digest")
        if isinstance(program_digest, Failure):
            return program_digest
        return _projection_result(
            project_key=event.project_key,
            run_id=event.run_id,
            run_incarnation=event.run_incarnation,
            run_state=RunState.SUBMITTED,
            last_seq=1,
            event_chain_digest=_chain_digest("0" * 64, event.event_digest),
            program_digest=program_digest,
            observed_event_types=(event.event_type,),
        )
    if (
        event.project_key != projection.project_key
        or event.run_id != projection.run_id
        or event.run_incarnation != projection.run_incarnation
    ):
        return _replay_failure("runtime event source identity changed during replay")
    if event.seq != projection.last_seq + 1:
        return _replay_failure(
            f"runtime event sequence gap: expected {projection.last_seq + 1}, got {event.seq}"
        )
    if projection.pending_required_failure is not None:
        expected_seq, step_id, attempt_id, source_digest = (
            projection.pending_required_failure
        )
        if (
            event.event_type != RunEvent.REQUIRED_STEP_FAILED.value
            or event.seq != expected_seq
            or event.step_id != step_id
            or event.attempt_id != attempt_id
            or event.metadata.get("source_event_digest") != source_digest
        ):
            return _replay_failure(
                "required failure event is not the exact ordered successor"
            )

    steps = dict(projection.steps)
    attempts = dict(projection.attempts)
    attempt_steps = dict(projection.attempt_step_bindings)
    recovery_claims = {
        recovery_attempt_id: (step_id, reconciliation_attempt_id)
        for recovery_attempt_id, step_id, reconciliation_attempt_id in projection.recovery_claim_bindings
    }
    failures = list(projection.required_failure_step_ids)
    activation_bindings = {
        step_id: (assignment_digest, activation_digest, input_closure_digest)
        for (
            step_id,
            assignment_digest,
            activation_digest,
            input_closure_digest,
        ) in projection.step_activation_bindings
    }
    run_state = projection.run_state
    plan_digest = projection.plan_digest
    pending = projection.pending_required_failure
    if (
        event.attempt_id is not None
        and event.event_type
        not in {StepEvent.STEP_CLAIMED.value, StepEvent.RECONCILE_REQUESTED.value}
        and attempt_steps.get(event.attempt_id) != event.step_id
    ):
        return _replay_failure("event attempt/step binding drift")

    if event.event_type in {"CompileSucceeded", "PlanCompiled"}:
        identity = _require_run_identity(event)
        if isinstance(identity, Failure):
            return identity
        event_plan_digest = _require_metadata_digest(event, "plan_digest")
        if isinstance(event_plan_digest, Failure):
            return event_plan_digest
        if run_state not in {RunState.SUBMITTED, RunState.COMPILING}:
            return _replay_failure(
                f"{event.event_type} has an invalid replay source state"
            )
        if plan_digest is not None and plan_digest != event_plan_digest:
            return _replay_failure(
                f"{event.event_type} plan digest binding drift"
            )
        plan_digest = event_plan_digest
        # CompileSucceeded is the real full-chain bootstrap edge.  PlanCompiled
        # remains the sole strict decoder for older journals that omitted it.
        run_state = RunState.COMPILING
    elif event.event_type == "QualificationActivated":
        identity = _require_run_identity(event)
        if isinstance(identity, Failure):
            return identity
        if run_state is not RunState.COMPILING:
            return _replay_failure("QualificationActivated requires COMPILING")
        qualification_digest = _require_metadata_digest(event, "qualification_digest")
        if isinstance(qualification_digest, Failure):
            return qualification_digest
        decision = event.metadata.get("decision")
        if decision == "QUALIFIED":
            run_state = RunState.READY
        elif decision == "AWAITING_APPROVAL":
            run_state = RunState.AWAITING_APPROVAL
        elif decision == "REJECTED":
            run_state = RunState.FAILED
        else:
            return _replay_failure("qualification decision is not frozen")
    elif event.event_type == "DeliveryReady":
        step_id = _require_step(event)
        if isinstance(step_id, Failure):
            return step_id
        assignment_digest = _require_metadata_digest(event, "assignment_digest")
        if isinstance(assignment_digest, Failure):
            return assignment_digest
        if event.attempt_id is not None:
            return _replay_failure("DeliveryReady cannot bind an effect attempt")
        if step_id in steps:
            return _replay_failure("DeliveryReady step is already activated")
        steps[step_id] = StepState.READY
    elif event.event_type == "StepActivated":
        step_id = _require_step(event)
        if isinstance(step_id, Failure):
            return step_id
        if event.attempt_id is not None:
            return _replay_failure("StepActivated cannot bind an effect attempt")
        if run_state not in {RunState.READY, RunState.RUNNING, RunState.WAITING}:
            return _replay_failure("StepActivated has an invalid run source state")
        if step_id in steps or step_id in activation_bindings:
            return _replay_failure("StepActivated step identity is duplicated")
        assignment_digest = _require_metadata_digest(event, "assignment_digest")
        if isinstance(assignment_digest, Failure):
            return assignment_digest
        activation_digest = _require_metadata_digest(event, "activation_digest")
        if isinstance(activation_digest, Failure):
            return activation_digest
        input_closure_digest = _require_metadata_digest(
            event, "input_closure_digest"
        )
        if isinstance(input_closure_digest, Failure):
            return input_closure_digest
        steps[step_id] = StepState.READY
        activation_bindings[step_id] = (
            assignment_digest,
            activation_digest,
            input_closure_digest,
        )
    elif event.event_type == StepEvent.STEP_CLAIMED.value:
        effect_identity = _require_effect_identity(event)
        if isinstance(effect_identity, Failure):
            return effect_identity
        step_id, attempt_id = effect_identity
        current = steps.get(step_id)
        if (
            current is StepState.RECONCILING
        ):
            target_attempt_id = event.metadata.get("reconciliation_attempt_id")
            if (
                event.metadata.get("assignment_kind") != "RECONCILE"
                or not isinstance(target_attempt_id, str)
                or attempt_steps.get(target_attempt_id) != step_id
                or attempts.get(target_attempt_id)
                not in {
                    EffectDisposition.OUTCOME_UNKNOWN,
                    EffectDisposition.SUCCEEDED,
                    EffectDisposition.FAILED,
                }
                or attempt_id in attempts
                or attempt_id in recovery_claims
            ):
                return _replay_failure("recovery claim/original attempt binding drift")
            recovery_claims[attempt_id] = (step_id, target_attempt_id)
        elif current is not StepState.READY:
            return _replay_failure("StepClaimed requires an existing READY step")
        else:
            assignment_kind = _require_metadata_string(event, "assignment_kind")
            if isinstance(assignment_kind, Failure):
                return assignment_kind
            if assignment_kind == "RECONCILE" or event.metadata.get(
                "reconciliation_attempt_id"
            ) is not None:
                return _replay_failure("ordinary StepClaimed has recovery metadata")
            if attempt_id in attempts or attempt_id in attempt_steps:
                return _replay_failure("StepClaimed attempt identity is reused")
            steps[step_id] = StepState.CLAIMED
            attempts[attempt_id] = EffectDisposition.NOT_STARTED
            attempt_steps[attempt_id] = step_id
    elif event.event_type == StepEvent.RECONCILE_REQUESTED.value:
        effect_identity = _require_effect_identity(event)
        if isinstance(effect_identity, Failure):
            return effect_identity
        step_id, recovery_attempt_id = effect_identity
        if steps.get(step_id) is not StepState.WAITING_EXTERNAL:
            return _replay_failure("ReconcileRequested requires WAITING_EXTERNAL")
        target_attempt_id = event.metadata.get("reconciliation_attempt_id")
        if (
            event.metadata.get("assignment_kind") != "RECONCILE"
            or not isinstance(target_attempt_id, str)
            or attempt_steps.get(target_attempt_id) != step_id
            or attempts.get(target_attempt_id)
            not in {
                EffectDisposition.OUTCOME_UNKNOWN,
                EffectDisposition.SUCCEEDED,
                EffectDisposition.FAILED,
            }
            or recovery_attempt_id in attempts
            or recovery_attempt_id in recovery_claims
        ):
            return _replay_failure("ReconcileRequested recovery claim is reused")
        recovery_claims[recovery_attempt_id] = (step_id, target_attempt_id)
        steps[step_id] = StepState.RECONCILING
    elif event.event_type == StepEvent.EFFECT_STARTED.value:
        effect_identity = _require_effect_identity(event)
        if isinstance(effect_identity, Failure):
            return effect_identity
        step_id, attempt_id = effect_identity
        if steps.get(step_id) is not StepState.CLAIMED:
            return _replay_failure("EffectStarted requires CLAIMED")
        if attempts.get(attempt_id) is not EffectDisposition.NOT_STARTED:
            return _replay_failure("EffectStarted attempt is not NOT_STARTED")
        steps[step_id] = StepState.RUNNING
        attempts[attempt_id] = EffectDisposition.IN_FLIGHT
        if run_state in {RunState.READY, RunState.WAITING, RunState.RECONCILING}:
            run_state = RunState.RUNNING
        elif run_state is not RunState.RUNNING:
            return _replay_failure("EffectStarted has an invalid run source state")
    elif event.event_type == StepEvent.COMMIT_PREPARED.value:
        effect_identity = _require_effect_identity(event)
        if isinstance(effect_identity, Failure):
            return effect_identity
        step_id, attempt_id = effect_identity
        state_check = _require_step_attempt_state(
            steps,
            attempts,
            step_id,
            attempt_id,
            StepState.RUNNING,
            EffectDisposition.IN_FLIGHT,
        )
        if isinstance(state_check, Failure):
            return state_check
        steps[step_id] = StepState.COMMITTING
    elif event.event_type in {
        StepEvent.RUNTIME_VALUE_PRODUCED.value,
        StepEvent.OUTCOME_STAGED.value,
    }:
        effect_identity = _require_effect_identity(event)
        if isinstance(effect_identity, Failure):
            return effect_identity
        step_id, attempt_id = effect_identity
        state_check = _require_step_attempt_state(
            steps,
            attempts,
            step_id,
            attempt_id,
            StepState.RUNNING,
            EffectDisposition.IN_FLIGHT,
        )
        if isinstance(state_check, Failure):
            return state_check
        steps[step_id] = StepState.SUCCEEDED
        attempts[attempt_id] = EffectDisposition.SUCCEEDED
    elif event.event_type == StepEvent.COMMIT_READBACK_CONFIRMED.value:
        effect_identity = _require_effect_identity(event)
        if isinstance(effect_identity, Failure):
            return effect_identity
        step_id, attempt_id = effect_identity
        state_check = _require_step_attempt_state(
            steps,
            attempts,
            step_id,
            attempt_id,
            StepState.COMMITTING,
            EffectDisposition.IN_FLIGHT,
        )
        if isinstance(state_check, Failure):
            return state_check
        steps[step_id] = StepState.SUCCEEDED
        attempts[attempt_id] = EffectDisposition.SUCCEEDED
    elif event.event_type == StepEvent.EFFECT_FAILED.value:
        effect_identity = _require_effect_identity(event)
        if isinstance(effect_identity, Failure):
            return effect_identity
        step_id, attempt_id = effect_identity
        state_check = _require_step_attempt_state(
            steps,
            attempts,
            step_id,
            attempt_id,
            StepState.RUNNING,
            EffectDisposition.IN_FLIGHT,
        )
        if isinstance(state_check, Failure):
            return state_check
        steps[step_id] = StepState.FAILED
        attempts[attempt_id] = EffectDisposition.FAILED
        if event.metadata.get("required_step_failed") is True:
            policy_digest = _require_metadata_digest(
                event, "failure_policy_decision_digest"
            )
            if isinstance(policy_digest, Failure):
                return policy_digest
            successor_seq = event.metadata.get("required_step_failed_event_revision")
            if successor_seq is None:
                # Strict legacy composite decoder: only the exact v1 event plus
                # a persisted policy digest may derive the historical run edge.
                run_state = RunState.FAILED
                if step_id not in failures:
                    failures.append(step_id)
            elif int(successor_seq) == event.seq + 1:
                pending = (event.seq + 1, step_id, attempt_id, event.event_digest)
            else:
                return _replay_failure("required failure successor seq drift")
            if not policy_digest:
                return _replay_failure("required failure policy digest is absent")
    elif event.event_type == StepEvent.EFFECT_RECEIPT_LOST.value:
        effect_identity = _require_effect_identity(event)
        if isinstance(effect_identity, Failure):
            return effect_identity
        step_id, attempt_id = effect_identity
        state_check = _require_step_attempt_state(
            steps,
            attempts,
            step_id,
            attempt_id,
            StepState.RUNNING,
            EffectDisposition.IN_FLIGHT,
        )
        if isinstance(state_check, Failure):
            return state_check
        steps[step_id] = StepState.RECONCILING
        attempts[attempt_id] = EffectDisposition.OUTCOME_UNKNOWN
        run_state = RunState.RECONCILING
    elif event.event_type in {
        "LeaseExpiredOutcomeUnknown",
        "LeaseExpiredReconcileRequired",
    }:
        effect_identity = _require_effect_identity(event)
        if isinstance(effect_identity, Failure):
            return effect_identity
        step_id, attempt_id = effect_identity
        expected_reason = (
            "LEASE_EXPIRED_OUTCOME_UNKNOWN"
            if event.event_type == "LeaseExpiredOutcomeUnknown"
            else "LEASE_EXPIRED_TERMINAL_ATTEMPT_RECONCILE"
        )
        if event.metadata.get("reason_code") != expected_reason:
            return _replay_failure(f"{event.event_type} reason code drift")
        work_item_id = _require_metadata_string(event, "work_item_id")
        if isinstance(work_item_id, Failure):
            return work_item_id
        reconcile_work_item_id = _require_metadata_string(event, "reconcile_work_item_id")
        if isinstance(reconcile_work_item_id, Failure):
            return reconcile_work_item_id
        current_step = steps.get(step_id)
        current_attempt = attempts.get(attempt_id)
        if event.event_type == "LeaseExpiredOutcomeUnknown":
            if (
                current_step is StepState.CLAIMED
                and current_attempt is EffectDisposition.NOT_STARTED
            ) or (
                current_step is StepState.RUNNING
                and current_attempt is EffectDisposition.IN_FLIGHT
            ):
                attempts[attempt_id] = EffectDisposition.OUTCOME_UNKNOWN
            elif (
                current_step in {StepState.CLAIMED, StepState.RUNNING}
                and current_attempt is EffectDisposition.OUTCOME_UNKNOWN
            ):
                pass
            elif current_step is StepState.RECONCILING and current_attempt in {
                EffectDisposition.OUTCOME_UNKNOWN,
                EffectDisposition.SUCCEEDED,
                EffectDisposition.FAILED,
            }:
                # A recovery-claim lease expiry only replaces recovery work.
                # It cannot rewrite the original attempt disposition.
                pass
            else:
                return _replay_failure(
                    "LeaseExpiredOutcomeUnknown source state/disposition drift"
                )
        elif not (
            current_step in {StepState.CLAIMED, StepState.RUNNING}
            and current_attempt
            in {EffectDisposition.SUCCEEDED, EffectDisposition.FAILED}
        ):
            return _replay_failure(
                "LeaseExpiredReconcileRequired requires a terminal attempt on an active step"
            )
        steps[step_id] = StepState.RECONCILING
        run_state = RunState.RECONCILING
    elif event.event_type == StepEvent.READBACK_UNAVAILABLE.value:
        effect_identity = _require_effect_identity(event)
        if isinstance(effect_identity, Failure):
            return effect_identity
        step_id, attempt_id = effect_identity
        if steps.get(step_id) is not StepState.RECONCILING:
            return _replay_failure("ReadbackUnavailable requires RECONCILING")
        if attempts.get(attempt_id) not in {
            EffectDisposition.OUTCOME_UNKNOWN,
            EffectDisposition.SUCCEEDED,
            EffectDisposition.FAILED,
        }:
            return _replay_failure("readback target is not recoverable")
        steps[step_id] = StepState.WAITING_EXTERNAL
    elif event.event_type in {
        StepEvent.AUTHORITATIVE_READBACK_SUCCEEDED.value,
        StepEvent.AUTHORITATIVE_READBACK_FAILED.value,
    }:
        effect_identity = _require_effect_identity(event)
        if isinstance(effect_identity, Failure):
            return effect_identity
        step_id, attempt_id = effect_identity
        if steps.get(step_id) is not StepState.RECONCILING:
            return _replay_failure("authoritative readback requires RECONCILING")
        succeeded = event.event_type == StepEvent.AUTHORITATIVE_READBACK_SUCCEEDED.value
        expected_disposition = (
            EffectDisposition.SUCCEEDED if succeeded else EffectDisposition.FAILED
        )
        current_disposition = attempts.get(attempt_id)
        if current_disposition not in {
            EffectDisposition.OUTCOME_UNKNOWN,
            expected_disposition,
        }:
            return _replay_failure(
                "authoritative readback contradicts the terminal attempt"
            )
        steps[step_id] = StepState.SUCCEEDED if succeeded else StepState.FAILED
        attempts[attempt_id] = expected_disposition
        if succeeded:
            run_state = RunState.RUNNING
        elif event.metadata.get("required_step_failed") is True:
            policy_digest = _require_metadata_digest(event, "failure_policy_decision_digest")
            if isinstance(policy_digest, Failure):
                return policy_digest
            successor_seq = event.metadata.get("required_step_failed_event_revision")
            if successor_seq is None:
                run_state = RunState.FAILED
                if step_id not in failures:
                    failures.append(step_id)
            elif int(successor_seq) == event.seq + 1:
                pending = (event.seq + 1, step_id, attempt_id, event.event_digest)
            else:
                return _replay_failure("readback failure successor seq drift")
    elif event.event_type == RunEvent.REQUIRED_STEP_FAILED.value:
        effect_identity = _require_effect_identity(event)
        if isinstance(effect_identity, Failure):
            return effect_identity
        step_id, attempt_id = effect_identity
        source_digest = _require_metadata_digest(event, "source_event_digest")
        if isinstance(source_digest, Failure):
            return source_digest
        policy_digest = _require_metadata_digest(event, "failure_policy_decision_digest")
        if isinstance(policy_digest, Failure):
            return policy_digest
        if pending != (event.seq, step_id, attempt_id, source_digest):
            return _replay_failure("RequiredStepFailed cause binding mismatch")
        run_state = RunState.FAILED
        if step_id not in failures:
            failures.append(step_id)
        pending = None
    elif event.event_type == RunEvent.RUN_COMPLETION_DERIVED.value:
        identity = _require_run_identity(event)
        if isinstance(identity, Failure):
            return identity
        if run_state is not RunState.RUNNING:
            return _replay_failure("RunCompletionDerived requires RUNNING")
        required_step_ids = event.metadata.get("required_step_ids")
        if (
            not isinstance(required_step_ids, list)
            or not required_step_ids
            or any(not isinstance(item, str) or not item for item in required_step_ids)
            or len(set(required_step_ids)) != len(required_step_ids)
        ):
            return _replay_failure(
                "RunCompletionDerived requires unique required_step_ids"
            )
        if set(required_step_ids) != set(steps) or any(
            steps[step_id] is not StepState.SUCCEEDED for step_id in required_step_ids
        ):
            return _replay_failure(
                "RunCompletionDerived required step closure is not exactly succeeded"
            )
        run_state = RunState.COMPLETED
    elif event.event_type == "SuccessorMaterialized":
        if run_state is not RunState.COMPLETED:
            return _replay_failure(
                "SuccessorMaterialized requires a completed predecessor run"
            )
        if event.step_id is not None or event.attempt_id is not None:
            return _replay_failure(
                "SuccessorMaterialized is observational, not a step/effect transition"
            )
        source_step_id = event.metadata.get("source_step_id")
        successor_run_id = event.metadata.get("successor_run_id")
        terminal_ref = event.metadata.get("terminal_observation_ref")
        if (
            not isinstance(source_step_id, str)
            or not isinstance(successor_run_id, str)
            or not isinstance(terminal_ref, str)
            or steps.get(source_step_id) is not StepState.SUCCEEDED
            or event.metadata.get("predecessor_run_state") != "COMPLETED"
            or event.metadata.get("predecessor_step_state") != "SUCCEEDED"
            or event.payload_ref != terminal_ref
        ):
            return _replay_failure(
                "SuccessorMaterialized predecessor/successor observation drift"
            )
        for key in (
            "claim_attempt_id",
            "assignment_digest",
            "handler_binding_digest",
            "source_value_digest",
            "successor_program_digest",
            "successor_plan_digest",
            "result_digest",
        ):
            digest = _require_metadata_digest(event, key)
            if isinstance(digest, Failure):
                return digest
        if event.payload_digest != event.metadata.get("result_digest"):
            return _replay_failure(
                "SuccessorMaterialized payload/result digest drift"
            )
    else:
        return _replay_failure(f"no pure replay reducer for {event.event_type!r}")

    return _projection_result(
        project_key=projection.project_key,
        run_id=projection.run_id,
        run_incarnation=projection.run_incarnation,
        run_state=run_state,
        last_seq=event.seq,
        event_chain_digest=_chain_digest(
            projection.event_chain_digest, event.event_digest
        ),
        program_digest=projection.program_digest,
        plan_digest=plan_digest,
        steps=tuple(sorted(steps.items())),
        step_activation_bindings=tuple(
            sorted(
                (
                    step_id,
                    assignment_digest,
                    activation_digest,
                    input_closure_digest,
                )
                for step_id, (
                    assignment_digest,
                    activation_digest,
                    input_closure_digest,
                ) in activation_bindings.items()
            )
        ),
        attempts=tuple(sorted(attempts.items())),
        attempt_step_bindings=tuple(sorted(attempt_steps.items())),
        recovery_claim_bindings=tuple(
            sorted(
                (recovery_attempt_id, step_id, target_attempt_id)
                for recovery_attempt_id, (step_id, target_attempt_id) in recovery_claims.items()
            )
        ),
        required_failure_step_ids=tuple(sorted(failures)),
        observed_event_types=projection.observed_event_types + (event.event_type,),
        pending_required_failure=pending,
    )


def _require_step(event: ReplayEvent) -> str | Failure:
    if event.step_id is None:
        return _replay_failure(f"{event.event_type} requires step identity")
    return event.step_id


def _require_run_identity(event: ReplayEvent) -> None | Failure:
    if event.step_id is not None or event.attempt_id is not None:
        return _replay_failure(
            f"{event.event_type} is a run event, not a step/effect transition"
        )
    return None


def _require_effect_identity(event: ReplayEvent) -> tuple[str, str] | Failure:
    step_id = _require_step(event)
    if isinstance(step_id, Failure):
        return step_id
    if event.attempt_id is None:
        return _replay_failure(f"{event.event_type} requires attempt identity")
    return step_id, event.attempt_id


def _require_metadata_digest(event: ReplayEvent, key: str) -> str | Failure:
    value = event.metadata.get(key)
    if not isinstance(value, str) or not is_sha256_hex(value):
        return _replay_failure(f"{event.event_type} lacks canonical {key}")
    return value


def _require_metadata_string(event: ReplayEvent, key: str) -> str | Failure:
    value = event.metadata.get(key)
    if not isinstance(value, str) or not value:
        return _replay_failure(f"{event.event_type} lacks {key}")
    return value


def _require_step_attempt_state(
    steps: Mapping[str, StepState],
    attempts: Mapping[str, EffectDisposition],
    step_id: str,
    attempt_id: str,
    step_state: StepState,
    disposition: EffectDisposition,
) -> None | Failure:
    if steps.get(step_id) is not step_state:
        return _replay_failure(
            f"step {step_id!r} is not {step_state.value} for terminal event"
        )
    if attempts.get(attempt_id) is not disposition:
        return _replay_failure(
            f"attempt {attempt_id!r} is not {disposition.value} for terminal event"
        )
    return None


def _chain_digest(previous_digest: str, event_digest: str) -> str:
    return sha256_hex(
        {
            "schema": "mrw.runtime.event-chain.v1",
            "previous_digest": previous_digest,
            "event_digest": event_digest,
        }
    )


__all__ = [
    "ReplayEvent",
    "RuntimeReplayError",
    "replay_runtime_events_result",
    "RuntimeReplayProjection",
    "projection_digest",
    "replay_runtime_events",
    "runtime_event_digest",
]
