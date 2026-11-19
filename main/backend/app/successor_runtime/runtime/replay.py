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
from typing import Callable, Generic, Literal, Protocol, TypeGuard, TypeVar, overload

from functorial_kit import Failure

from app.successor_runtime.language.checksum import is_sha256_hex, sha256_hex
from app.successor_runtime.runtime.transitions import (
    EffectDisposition,
    STEP_TRANSITIONS,
    TERMINAL_RUN_STATES,
    RunEvent,
    RunState,
    StepEvent,
    StepState,
)

from .failure_policy import raise_runtime_failure, runtime_failure


class RuntimeReplayError(ValueError):
    """The journal cannot be interpreted without weakening frozen semantics."""


_ReplayValue = TypeVar("_ReplayValue")
class _PublicJournalRow(Protocol):
    @overload
    def __getitem__(self, key: Literal["seq"]) -> int: ...

    @overload
    def __getitem__(
        self, key: Literal["event_metadata_json"]
    ) -> Mapping[str, object]: ...

    @overload
    def __getitem__(
        self,
        key: Literal[
            "project_key",
            "run_id",
            "event_type",
            "schema_version",
            "authority_digest",
        ],
    ) -> str: ...

    @overload
    def __getitem__(
        self,
        key: Literal[
            "step_id",
            "attempt_id",
            "payload_ref",
            "payload_digest",
        ],
    ) -> str | None: ...


def _replay_failure(
    code: str | object,
    message: object | None = None,
    *,
    site: str = "successor_runtime.runtime.replay",
) -> Failure:
    if message is None:
        code, message = "REPLAY_STATE_INVALID", code
    failure_code = code if isinstance(code, str) else "REPLAY_STATE_INVALID"
    return runtime_failure(failure_code, message, RuntimeReplayError, site=site)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_object_sequence(value: object) -> TypeGuard[tuple[object, ...] | list[object]]:
    return isinstance(value, (tuple, list))


def _is_string_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    if not _is_object_mapping(value):
        return False
    return all(isinstance(key, str) for key in value)


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _coerce_int(value: object) -> int:
    if isinstance(value, (str, bytes, bytearray, int, float)):
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            pass
    # kit:boundary owner=successor.runtime.replay.projection_codec class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_replay_projection_bad_scalar_helpers_return_typed_failure_and_preserve_legacy_error
    raise_runtime_failure(
        _replay_failure(
            "REPLAY_PROJECTION_INVALID",
            "runtime projection integer field is invalid",
            site="successor_runtime.runtime.replay.RuntimeReplayProjection.from_json",
        ),
        RuntimeReplayError,
    )


def _string_tuple(value: object) -> tuple[str, ...]:
    if not _is_object_sequence(value):
        # kit:boundary owner=successor.runtime.replay.projection_codec class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_replay_projection_bad_scalar_helpers_return_typed_failure_and_preserve_legacy_error
        raise_runtime_failure(
            _replay_failure(
                "REPLAY_PROJECTION_INVALID",
                "runtime projection string collection is invalid",
                site="successor_runtime.runtime.replay.RuntimeReplayProjection.from_json",
            ),
            RuntimeReplayError,
        )
    return tuple(str(item) for item in value)


def _is_nonempty_unique_string_list(value: object) -> TypeGuard[list[str]]:
    if not _is_object_list(value) or not value:
        return False
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            return False
        strings.append(item)
    return len(set(strings)) == len(strings)


def _is_optional_digest_sequence(
    value: object,
) -> TypeGuard[tuple[str | None, ...] | list[str | None]]:
    if not _is_object_sequence(value):
        return False
    return all(
        item is None or (isinstance(item, str) and is_sha256_hex(item))
        for item in value
    )


def _legacy_lift(value: _ReplayValue | Failure) -> _ReplayValue:
    if isinstance(value, Failure):
        raise_runtime_failure(value, RuntimeReplayError)
    return value


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

    @classmethod
    def from_public_row(
        cls, row: _PublicJournalRow, *, run_incarnation: str
    ) -> ReplayEvent:
        """Project one already scope/run-filtered public event row."""

        try:
            return cls.from_content(
                project_key=str(row["project_key"]),
                run_id=str(row["run_id"]),
                run_incarnation=str(run_incarnation),
                seq=int(row["seq"]),
                event_type=str(row["event_type"]),
                schema_version=str(row["schema_version"]),
                step_id=None if row["step_id"] is None else str(row["step_id"]),
                attempt_id=None if row["attempt_id"] is None else str(row["attempt_id"]),
                metadata=dict(row["event_metadata_json"]),
                payload_ref=None if row["payload_ref"] is None else str(row["payload_ref"]),
                payload_digest=None if row["payload_digest"] is None else str(row["payload_digest"]),
                authority_digest=str(row["authority_digest"]),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise_runtime_failure(
                _replay_failure("REPLAY_EVENT_INVALID", f"invalid public journal row: {exc}"),
                RuntimeReplayError,
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
    traversal_bindings: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    active_child_bindings: tuple[tuple[str, int, str, str, str], ...] = ()
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
        if tuple(sorted(self.traversal_bindings)) != self.traversal_bindings:
            return _replay_failure(
                "REPLAY_PROJECTION_INVALID", "projection traversal bindings are not ordered"
            )
        traversal_by_step: dict[str, tuple[str, tuple[str, ...]]] = {}
        for step_id, materialization_digest, element_digests in self.traversal_bindings:
            if (
                not step_id
                or step_id in traversal_by_step
                or not is_sha256_hex(materialization_digest)
                or any(not is_sha256_hex(item) for item in element_digests)
            ):
                return _replay_failure(
                    "REPLAY_PROJECTION_INVALID", "projection traversal binding is invalid"
                )
            traversal_by_step[step_id] = (materialization_digest, element_digests)
        if tuple(sorted(self.active_child_bindings)) != self.active_child_bindings:
            return _replay_failure(
                "REPLAY_PROJECTION_INVALID", "projection active-child bindings are not ordered"
            )
        child_ids: set[str] = set()
        positions: set[tuple[str, int]] = set()
        for step_id, index, child_run_id, element_digest, materialization_digest in self.active_child_bindings:
            traversal = traversal_by_step.get(step_id)
            if (
                traversal is None
                or type(index) is not int
                or index < 0
                or index >= len(traversal[1])
                or traversal[0] != materialization_digest
                or traversal[1][index] != element_digest
                or not child_run_id
                or child_run_id in child_ids
                or (step_id, index) in positions
            ):
                return _replay_failure(
                    "REPLAY_PROJECTION_INVALID", "projection active-child lineage is invalid"
                )
            child_ids.add(child_run_id)
            positions.add((step_id, index))

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
            "traversal_bindings": [
                {
                    "source_step_id": step_id,
                    "materialization_digest": materialization_digest,
                    "element_digests": list(element_digests),
                }
                for step_id, materialization_digest, element_digests in self.traversal_bindings
            ],
            "active_child_bindings": [
                {
                    "source_step_id": step_id,
                    "element_index": index,
                    "child_run_id": child_run_id,
                    "element_digest": element_digest,
                    "materialization_digest": materialization_digest,
                }
                for step_id, index, child_run_id, element_digest, materialization_digest in self.active_child_bindings
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
    def _decode_json(
        cls, value: Mapping[str, object]
    ) -> RuntimeReplayProjection | Failure:
        if value.get("schema") != "mrw.runtime.run-projection.v1":
            return _replay_failure(
                "REPLAY_PROJECTION_INVALID", "runtime projection schema mismatch"
            )
        raw_steps = value.get("steps")
        raw_activation_bindings = value.get("step_activation_bindings")
        raw_attempts = value.get("attempts")
        raw_attempt_step_bindings = value.get("attempt_step_bindings")
        raw_recovery_claim_bindings = value.get("recovery_claim_bindings")
        raw_traversal_bindings = value.get("traversal_bindings", [])
        raw_active_child_bindings = value.get("active_child_bindings", [])
        if (
            not _is_object_list(raw_steps)
            or not _is_object_list(raw_activation_bindings)
            or not _is_object_list(raw_attempts)
            or not _is_object_list(raw_attempt_step_bindings)
            or not _is_object_list(raw_recovery_claim_bindings)
            or not _is_object_list(raw_traversal_bindings)
            or not _is_object_list(raw_active_child_bindings)
        ):
            return _replay_failure(
                "REPLAY_PROJECTION_INVALID", "runtime projection state collections are invalid"
            )
        pending = value.get("pending_required_failure")
        pending_tuple = None
        if pending is not None:
            if not _is_string_object_mapping(pending):
                return _replay_failure(
                    "REPLAY_PROJECTION_INVALID", "pending required failure is invalid"
                )
            pending_tuple = (
                _coerce_int(pending["expected_seq"]),
                str(pending["step_id"]),
                str(pending["attempt_id"]),
                str(pending["source_event_digest"]),
            )
        decoded_traversal_bindings: list[tuple[str, str, tuple[str, ...]]] = []
        for raw_binding in raw_traversal_bindings:
            if not _is_string_object_mapping(raw_binding):
                continue
            raw_digests = raw_binding.get("element_digests")
            if not _is_object_list(raw_digests):
                continue
            decoded_traversal_bindings.append(
                (
                    str(raw_binding["source_step_id"]),
                    str(raw_binding["materialization_digest"]),
                    tuple(str(digest) for digest in raw_digests),
                )
            )
        return cls(
            project_key=str(value["project_key"]),
            run_id=str(value["run_id"]),
            run_incarnation=str(value["run_incarnation"]),
            run_state=RunState(str(value["run_state"])),
            last_seq=_coerce_int(value["last_seq"]),
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
                    if _is_string_object_mapping(item)
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
                    if _is_string_object_mapping(item)
                )
            ),
            attempts=tuple(
                sorted(
                    (
                        str(item["attempt_id"]),
                        EffectDisposition(str(item["disposition"])),
                    )
                    for item in raw_attempts
                    if _is_string_object_mapping(item)
                )
            ),
            attempt_step_bindings=tuple(
                sorted(
                    (str(item["attempt_id"]), str(item["step_id"]))
                    for item in raw_attempt_step_bindings
                    if _is_string_object_mapping(item)
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
                    if _is_string_object_mapping(item)
                )
            ),
            traversal_bindings=tuple(sorted(decoded_traversal_bindings)),
            active_child_bindings=tuple(
                sorted(
                    (
                        str(item["source_step_id"]),
                        _coerce_int(item["element_index"]),
                        str(item["child_run_id"]),
                        str(item["element_digest"]),
                        str(item["materialization_digest"]),
                    )
                    for item in raw_active_child_bindings
                    if _is_string_object_mapping(item)
                )
            ),
            required_failure_step_ids=_string_tuple(
                value.get("required_failure_step_ids", [])
            ),
            observed_event_types=_string_tuple(
                value.get("observed_event_types", [])
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
        projection = _apply_event_rules(projection, event)
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


def active_child_failure_decision_digest(metadata: Mapping[str, object]) -> str:
    """Bind the ordered-required-child policy to its exact causal observation."""
    return sha256_hex({"policy": "ordered_required_child.v2", **{
        key: metadata.get(key) for key in (
            "source_step_id", "child_run_id", "element_index", "materialization_digest",
            "source_revision", "source_event_digest",
        )
    }})


def projection_digest(projection: RuntimeReplayProjection) -> str:
    return sha256_hex(projection.to_json())


@dataclass(slots=True)
class _RunWork:
    run_state: RunState
    plan_digest: str | None
    failures: list[str]
    pending: tuple[int, str, str, str] | None


@dataclass(slots=True)
class _ActivationWork:
    steps: dict[str, StepState]
    activation_bindings: dict[str, tuple[str, str, str]]
    run: _RunWork


@dataclass(slots=True)
class _EffectWork:
    steps: dict[str, StepState]
    attempts: dict[str, EffectDisposition]
    attempt_steps: dict[str, str]
    recovery_claims: dict[str, tuple[str, str]]
    run: _RunWork


@dataclass(slots=True)
class _ClosureWork:
    steps: dict[str, StepState]
    attempts: dict[str, EffectDisposition]
    attempt_steps: dict[str, str]
    traversals: dict[str, tuple[str, tuple[str, ...]]]
    active_children: dict[tuple[str, int], tuple[str, str, str]]
    run: _RunWork


@dataclass(slots=True)
class _TraversalWork:
    steps: dict[str, StepState]
    traversals: dict[str, tuple[str, tuple[str, ...]]]
    active_children: dict[tuple[str, int], tuple[str, str, str]]
    run: _RunWork


_RunReducer = Callable[[ReplayEvent, _RunWork], None | Failure]
_BootstrapReducer = Callable[
    [ReplayEvent, RuntimeReplayProjection | None],
    RuntimeReplayProjection | Failure,
]
_ActivationReducer = Callable[[ReplayEvent, _ActivationWork], None | Failure]
_EffectReducer = Callable[[ReplayEvent, _EffectWork], None | Failure]
_ClosureReducer = Callable[[ReplayEvent, _ClosureWork], None | Failure]
_TraversalReducer = Callable[[ReplayEvent, _TraversalWork], None | Failure]
_ClosedReplayWork = (
    _RunWork
    | _ActivationWork
    | _EffectWork
    | _ClosureWork
    | _TraversalWork
)
_ReplayWork = TypeVar("_ReplayWork", bound=_ClosedReplayWork)


def _reduce_program_accepted(
    event: ReplayEvent, projection: RuntimeReplayProjection | None
) -> RuntimeReplayProjection | Failure:
    if projection is not None:
        return _replay_failure(f"no pure replay reducer for {event.event_type!r}")
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


def _bind_compiled_plan(event: ReplayEvent, work: _RunWork) -> None | Failure:
    identity = _require_run_identity(event)
    if isinstance(identity, Failure):
        return identity
    event_plan_digest = _require_metadata_digest(event, "plan_digest")
    if isinstance(event_plan_digest, Failure):
        return event_plan_digest
    if work.run_state not in {RunState.SUBMITTED, RunState.COMPILING}:
        return _replay_failure(
            f"{event.event_type} has an invalid replay source state"
        )
    if work.plan_digest is not None and work.plan_digest != event_plan_digest:
        return _replay_failure(f"{event.event_type} plan digest binding drift")
    work.plan_digest = event_plan_digest
    # CompileSucceeded is the real full-chain bootstrap edge. PlanCompiled remains
    # the strict decoder for older journals that omitted it.
    work.run_state = RunState.COMPILING
    return None


def _reduce_compile_succeeded(event: ReplayEvent, work: _RunWork) -> None | Failure:
    return _bind_compiled_plan(event, work)


def _reduce_plan_compiled(event: ReplayEvent, work: _RunWork) -> None | Failure:
    return _bind_compiled_plan(event, work)


def _reduce_qualification_activated(
    event: ReplayEvent, work: _RunWork
) -> None | Failure:
    identity = _require_run_identity(event)
    if isinstance(identity, Failure):
        return identity
    if work.run_state is not RunState.COMPILING:
        return _replay_failure("QualificationActivated requires COMPILING")
    qualification_digest = _require_metadata_digest(
        event, "qualification_digest"
    )
    if isinstance(qualification_digest, Failure):
        return qualification_digest
    decision = event.metadata.get("decision")
    if decision == "QUALIFIED":
        work.run_state = RunState.READY
    elif decision == "AWAITING_APPROVAL":
        work.run_state = RunState.AWAITING_APPROVAL
    elif decision == "REJECTED":
        work.run_state = RunState.FAILED
    else:
        return _replay_failure("qualification decision is not frozen")
    return None


def _reduce_delivery_ready(
    event: ReplayEvent, work: _ActivationWork
) -> None | Failure:
    step_id = _require_step(event)
    if isinstance(step_id, Failure):
        return step_id
    assignment_digest = _require_metadata_digest(event, "assignment_digest")
    if isinstance(assignment_digest, Failure):
        return assignment_digest
    if event.attempt_id is not None:
        return _replay_failure("DeliveryReady cannot bind an effect attempt")
    if step_id in work.steps:
        return _replay_failure("DeliveryReady step is already activated")
    work.steps[step_id] = StepState.READY
    return None


def _reduce_step_activated(
    event: ReplayEvent, work: _ActivationWork
) -> None | Failure:
    step_id = _require_step(event)
    if isinstance(step_id, Failure):
        return step_id
    if event.attempt_id is not None:
        return _replay_failure("StepActivated cannot bind an effect attempt")
    if work.run.run_state not in {
        RunState.READY,
        RunState.RUNNING,
        RunState.WAITING,
    }:
        return _replay_failure("StepActivated has an invalid run source state")
    if step_id in work.steps or step_id in work.activation_bindings:
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
    work.steps[step_id] = StepState.READY
    work.activation_bindings[step_id] = (
        assignment_digest,
        activation_digest,
        input_closure_digest,
    )
    return None


def _reduce_step_claimed(event: ReplayEvent, work: _EffectWork) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    current = work.steps.get(step_id)
    if current is StepState.RECONCILING:
        target_attempt_id = event.metadata.get("reconciliation_attempt_id")
        if (
            event.metadata.get("assignment_kind") != "RECONCILE"
            or not isinstance(target_attempt_id, str)
            or work.attempt_steps.get(target_attempt_id) != step_id
            or work.attempts.get(target_attempt_id)
            not in {
                EffectDisposition.OUTCOME_UNKNOWN,
                EffectDisposition.SUCCEEDED,
                EffectDisposition.FAILED,
            }
            or attempt_id in work.attempts
            or attempt_id in work.recovery_claims
        ):
            return _replay_failure(
                "recovery claim/original attempt binding drift"
            )
        work.recovery_claims[attempt_id] = (step_id, target_attempt_id)
        return None
    if current is not StepState.READY:
        return _replay_failure("StepClaimed requires an existing READY step")
    assignment_kind = _require_metadata_string(event, "assignment_kind")
    if isinstance(assignment_kind, Failure):
        return assignment_kind
    if (
        assignment_kind == "RECONCILE"
        or event.metadata.get("reconciliation_attempt_id") is not None
    ):
        return _replay_failure("ordinary StepClaimed has recovery metadata")
    if attempt_id in work.attempts or attempt_id in work.attempt_steps:
        return _replay_failure("StepClaimed attempt identity is reused")
    work.steps[step_id] = StepState.CLAIMED
    work.attempts[attempt_id] = EffectDisposition.NOT_STARTED
    work.attempt_steps[attempt_id] = step_id
    return None


def _reduce_reconcile_requested(
    event: ReplayEvent, work: _EffectWork
) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, recovery_attempt_id = effect_identity
    if work.steps.get(step_id) is not StepState.WAITING_EXTERNAL:
        return _replay_failure("ReconcileRequested requires WAITING_EXTERNAL")
    target_attempt_id = event.metadata.get("reconciliation_attempt_id")
    if (
        event.metadata.get("assignment_kind") != "RECONCILE"
        or not isinstance(target_attempt_id, str)
        or work.attempt_steps.get(target_attempt_id) != step_id
        or work.attempts.get(target_attempt_id)
        not in {
            EffectDisposition.OUTCOME_UNKNOWN,
            EffectDisposition.SUCCEEDED,
            EffectDisposition.FAILED,
        }
        or recovery_attempt_id in work.attempts
        or recovery_attempt_id in work.recovery_claims
    ):
        return _replay_failure("ReconcileRequested recovery claim is reused")
    work.recovery_claims[recovery_attempt_id] = (step_id, target_attempt_id)
    work.steps[step_id] = StepState.RECONCILING
    return None


def _reduce_effect_started(event: ReplayEvent, work: _EffectWork) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    if work.steps.get(step_id) is not StepState.CLAIMED:
        return _replay_failure("EffectStarted requires CLAIMED")
    if work.attempts.get(attempt_id) is not EffectDisposition.NOT_STARTED:
        return _replay_failure("EffectStarted attempt is not NOT_STARTED")
    work.steps[step_id] = StepState.RUNNING
    work.attempts[attempt_id] = EffectDisposition.IN_FLIGHT
    if work.run.run_state in {
        RunState.READY,
        RunState.WAITING,
        RunState.RECONCILING,
    }:
        work.run.run_state = RunState.RUNNING
    elif work.run.run_state is not RunState.RUNNING:
        return _replay_failure("EffectStarted has an invalid run source state")
    return None


def _reduce_commit_prepared(event: ReplayEvent, work: _EffectWork) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    state_check = _require_step_attempt_state(
        work.steps,
        work.attempts,
        step_id,
        attempt_id,
        StepState.RUNNING,
        EffectDisposition.IN_FLIGHT,
    )
    if isinstance(state_check, Failure):
        return state_check
    work.steps[step_id] = StepState.COMMITTING
    return None


def _reduce_effect_succeeded(event: ReplayEvent, work: _EffectWork) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    state_check = _require_step_attempt_state(
        work.steps,
        work.attempts,
        step_id,
        attempt_id,
        StepState.RUNNING,
        EffectDisposition.IN_FLIGHT,
    )
    if isinstance(state_check, Failure):
        return state_check
    work.steps[step_id] = StepState.SUCCEEDED
    work.attempts[attempt_id] = EffectDisposition.SUCCEEDED
    return None


def _reduce_commit_readback_confirmed(
    event: ReplayEvent, work: _EffectWork
) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    state_check = _require_step_attempt_state(
        work.steps,
        work.attempts,
        step_id,
        attempt_id,
        StepState.COMMITTING,
        EffectDisposition.IN_FLIGHT,
    )
    if isinstance(state_check, Failure):
        return state_check
    work.steps[step_id] = StepState.SUCCEEDED
    work.attempts[attempt_id] = EffectDisposition.SUCCEEDED
    return None


def _reduce_effect_failed(event: ReplayEvent, work: _EffectWork) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    state_check = _require_step_attempt_state(
        work.steps,
        work.attempts,
        step_id,
        attempt_id,
        StepState.RUNNING,
        EffectDisposition.IN_FLIGHT,
    )
    if isinstance(state_check, Failure):
        return state_check
    work.steps[step_id] = StepState.FAILED
    work.attempts[attempt_id] = EffectDisposition.FAILED
    if event.metadata.get("required_step_failed") is True:
        policy_digest = _require_metadata_digest(
            event, "failure_policy_decision_digest"
        )
        if isinstance(policy_digest, Failure):
            return policy_digest
        successor_seq = event.metadata.get("required_step_failed_event_revision")
        if successor_seq is None:
            # The exact v1 composite plus a persisted policy digest remains the
            # only historical route that derives the run edge immediately.
            work.run.run_state = RunState.FAILED
            if step_id not in work.run.failures:
                work.run.failures.append(step_id)
        elif _coerce_int(successor_seq) == event.seq + 1:
            work.run.pending = (
                event.seq + 1,
                step_id,
                attempt_id,
                event.event_digest,
            )
        else:
            return _replay_failure("required failure successor seq drift")
        if not policy_digest:
            return _replay_failure("required failure policy digest is absent")
    return None


def _reduce_effect_receipt_lost(
    event: ReplayEvent, work: _EffectWork
) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    state_check = _require_step_attempt_state(
        work.steps,
        work.attempts,
        step_id,
        attempt_id,
        StepState.RUNNING,
        EffectDisposition.IN_FLIGHT,
    )
    if isinstance(state_check, Failure):
        return state_check
    work.steps[step_id] = StepState.RECONCILING
    work.attempts[attempt_id] = EffectDisposition.OUTCOME_UNKNOWN
    work.run.run_state = RunState.RECONCILING
    return None


def _reduce_lease_expired_outcome_unknown(
    event: ReplayEvent, work: _EffectWork
) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    if event.metadata.get("reason_code") != "LEASE_EXPIRED_OUTCOME_UNKNOWN":
        return _replay_failure(f"{event.event_type} reason code drift")
    work_item_id = _require_metadata_string(event, "work_item_id")
    if isinstance(work_item_id, Failure):
        return work_item_id
    reconcile_work_item_id = _require_metadata_string(
        event, "reconcile_work_item_id"
    )
    if isinstance(reconcile_work_item_id, Failure):
        return reconcile_work_item_id
    current_step = work.steps.get(step_id)
    current_attempt = work.attempts.get(attempt_id)
    if (
        current_step is StepState.CLAIMED
        and current_attempt is EffectDisposition.NOT_STARTED
    ) or (
        current_step is StepState.RUNNING
        and current_attempt is EffectDisposition.IN_FLIGHT
    ):
        work.attempts[attempt_id] = EffectDisposition.OUTCOME_UNKNOWN
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
        # A recovery-claim lease expiry only replaces recovery work. It cannot
        # rewrite the original attempt disposition.
        pass
    else:
        return _replay_failure(
            "LeaseExpiredOutcomeUnknown source state/disposition drift"
        )
    work.steps[step_id] = StepState.RECONCILING
    work.run.run_state = RunState.RECONCILING
    return None


def _reduce_lease_expired_reconcile_required(
    event: ReplayEvent, work: _EffectWork
) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    if (
        event.metadata.get("reason_code")
        != "LEASE_EXPIRED_TERMINAL_ATTEMPT_RECONCILE"
    ):
        return _replay_failure(f"{event.event_type} reason code drift")
    work_item_id = _require_metadata_string(event, "work_item_id")
    if isinstance(work_item_id, Failure):
        return work_item_id
    reconcile_work_item_id = _require_metadata_string(
        event, "reconcile_work_item_id"
    )
    if isinstance(reconcile_work_item_id, Failure):
        return reconcile_work_item_id
    if not (
        work.steps.get(step_id) in {StepState.CLAIMED, StepState.RUNNING}
        and work.attempts.get(attempt_id)
        in {EffectDisposition.SUCCEEDED, EffectDisposition.FAILED}
    ):
        return _replay_failure(
            "LeaseExpiredReconcileRequired requires a terminal attempt on an active step"
        )
    work.steps[step_id] = StepState.RECONCILING
    work.run.run_state = RunState.RECONCILING
    return None


def _reduce_readback_unavailable(
    event: ReplayEvent, work: _EffectWork
) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    if work.steps.get(step_id) is not StepState.RECONCILING:
        return _replay_failure("ReadbackUnavailable requires RECONCILING")
    if work.attempts.get(attempt_id) not in {
        EffectDisposition.OUTCOME_UNKNOWN,
        EffectDisposition.SUCCEEDED,
        EffectDisposition.FAILED,
    }:
        return _replay_failure("readback target is not recoverable")
    work.steps[step_id] = StepState.WAITING_EXTERNAL
    return None


def _reduce_authoritative_readback_succeeded(
    event: ReplayEvent, work: _EffectWork
) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    if work.steps.get(step_id) is not StepState.RECONCILING:
        return _replay_failure("authoritative readback requires RECONCILING")
    current_disposition = work.attempts.get(attempt_id)
    if current_disposition not in {
        EffectDisposition.OUTCOME_UNKNOWN,
        EffectDisposition.SUCCEEDED,
    }:
        return _replay_failure(
            "authoritative readback contradicts the terminal attempt"
        )
    work.steps[step_id] = StepState.SUCCEEDED
    work.attempts[attempt_id] = EffectDisposition.SUCCEEDED
    work.run.run_state = RunState.RUNNING
    return None


def _reduce_authoritative_readback_failed(
    event: ReplayEvent, work: _EffectWork
) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    if work.steps.get(step_id) is not StepState.RECONCILING:
        return _replay_failure("authoritative readback requires RECONCILING")
    current_disposition = work.attempts.get(attempt_id)
    if current_disposition not in {
        EffectDisposition.OUTCOME_UNKNOWN,
        EffectDisposition.FAILED,
    }:
        return _replay_failure(
            "authoritative readback contradicts the terminal attempt"
        )
    work.steps[step_id] = StepState.FAILED
    work.attempts[attempt_id] = EffectDisposition.FAILED
    if event.metadata.get("required_step_failed") is True:
        policy_digest = _require_metadata_digest(
            event, "failure_policy_decision_digest"
        )
        if isinstance(policy_digest, Failure):
            return policy_digest
        successor_seq = event.metadata.get("required_step_failed_event_revision")
        if successor_seq is None:
            work.run.run_state = RunState.FAILED
            if step_id not in work.run.failures:
                work.run.failures.append(step_id)
        elif _coerce_int(successor_seq) == event.seq + 1:
            work.run.pending = (
                event.seq + 1,
                step_id,
                attempt_id,
                event.event_digest,
            )
        else:
            return _replay_failure("readback failure successor seq drift")
    return None


def _reduce_required_step_failed(
    event: ReplayEvent, work: _EffectWork
) -> None | Failure:
    effect_identity = _require_effect_identity(event)
    if isinstance(effect_identity, Failure):
        return effect_identity
    step_id, attempt_id = effect_identity
    source_digest = _require_metadata_digest(event, "source_event_digest")
    if isinstance(source_digest, Failure):
        return source_digest
    policy_digest = _require_metadata_digest(
        event, "failure_policy_decision_digest"
    )
    if isinstance(policy_digest, Failure):
        return policy_digest
    if work.run.pending != (
        event.seq,
        step_id,
        attempt_id,
        source_digest,
    ):
        return _replay_failure("RequiredStepFailed cause binding mismatch")
    work.run.run_state = RunState.FAILED
    if step_id not in work.run.failures:
        work.run.failures.append(step_id)
    work.run.pending = None
    return None


def _reduce_cancellation_requested(
    event: ReplayEvent, work: _ClosureWork
) -> None | Failure:
    if event.attempt_id is not None:
        return _replay_failure(
            "cancellation command cannot impersonate an effect attempt"
        )
    if event.step_id is None:
        if work.run.run_state in TERMINAL_RUN_STATES:
            return _replay_failure("cancellation requires a live run")
        in_flight = any(
            StepState.CANCEL_REQUESTED
            in STEP_TRANSITIONS.get(
                (state, StepEvent.CANCELLATION_REQUESTED), frozenset()
            )
            for state in work.steps.values()
        )
        work.run.run_state = (
            RunState.CANCELLING if in_flight else RunState.CANCELLED
        )
        return None
    if work.run.run_state not in {RunState.CANCELLING, RunState.CANCELLED}:
        return _replay_failure(
            "step cancellation requires the run cancellation command"
        )
    previous = work.steps.get(event.step_id)
    if previous is None:
        return _replay_failure("cancellation references an unknown step")
    allowed = STEP_TRANSITIONS.get(
        (previous, StepEvent.CANCELLATION_REQUESTED), frozenset()
    )
    target = event.metadata.get("state")
    if len(allowed) != 1 or target != next(iter(allowed)).value:
        return _replay_failure(
            "step cancellation target contradicts current effect state"
        )
    work.steps[event.step_id] = next(iter(allowed))
    return None


def _reduce_cleanup_confirmed(
    event: ReplayEvent, work: _ClosureWork
) -> None | Failure:
    identity = _require_effect_identity(event)
    if isinstance(identity, Failure):
        return identity
    step_id, attempt_id = identity
    if (
        work.run.run_state is not RunState.CANCELLING
        or work.steps.get(step_id) is not StepState.CANCEL_REQUESTED
        or event.metadata.get("state") != StepState.CANCELLED.value
        or event.metadata.get("reason") != "NODE_BEFORE_HANDLER"
        or work.attempt_steps.get(attempt_id) != step_id
        or work.attempts.get(attempt_id)
        not in {
            EffectDisposition.NOT_STARTED,
            EffectDisposition.IN_FLIGHT,
        }
    ):
        return _replay_failure(
            "non-start cleanup requires the exact cancelled attempt and node proof"
        )
    work.steps[step_id] = StepState.CANCELLED
    work.attempts[attempt_id] = EffectDisposition.NOT_STARTED
    return None


def _reduce_required_cleanup_settled(
    event: ReplayEvent, work: _ClosureWork
) -> None | Failure:
    identity = _require_run_identity(event)
    if isinstance(identity, Failure):
        return identity
    if (
        work.run.run_state is not RunState.CANCELLING
        or event.metadata.get("state") != RunState.CANCELLED.value
        or any(
            state
            not in {
                StepState.CANCELLED,
                StepState.SUCCEEDED,
                StepState.FAILED,
                StepState.SKIPPED_BY_DECISION,
            }
            for state in work.steps.values()
        )
        or any(
            disposition
            in {
                EffectDisposition.IN_FLIGHT,
                EffectDisposition.OUTCOME_UNKNOWN,
            }
            for disposition in work.attempts.values()
        )
    ):
        return _replay_failure(
            "cancellation cannot settle while effects or cleanup remain pending"
        )
    work.run.run_state = RunState.CANCELLED
    return None


def _reduce_run_completion_derived(
    event: ReplayEvent, work: _ClosureWork
) -> None | Failure:
    identity = _require_run_identity(event)
    if isinstance(identity, Failure):
        return identity
    if work.run.run_state is not RunState.RUNNING:
        return _replay_failure("RunCompletionDerived requires RUNNING")
    required_step_ids = event.metadata.get("required_step_ids")
    if not _is_nonempty_unique_string_list(required_step_ids):
        return _replay_failure(
            "RunCompletionDerived requires unique required_step_ids"
        )
    if set(required_step_ids) != set(work.steps) or any(
        work.steps[step_id] is not StepState.SUCCEEDED
        for step_id in required_step_ids
    ):
        return _replay_failure(
            "RunCompletionDerived required step closure is not exactly succeeded"
        )
    work.run.run_state = RunState.COMPLETED
    return None


def _reduce_active_child_required_failure(
    event: ReplayEvent, work: _ClosureWork
) -> None | Failure:
    source_step = event.metadata.get("source_step_id")
    index = event.metadata.get("element_index")
    revision = event.metadata.get("source_revision")
    if (
        work.run.run_state is not RunState.WAITING
        or event.step_id is not None
        or event.attempt_id is not None
        or work.run.pending is not None
        or not isinstance(source_step, str)
        or not isinstance(index, int)
        or isinstance(index, bool)
        or index < 0
        or not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision < 1
    ):
        return _replay_failure(
            "active child failure requires an exact waiting traversal"
        )
    child = work.active_children.get((source_step, index))
    traversal = work.traversals.get(source_step)
    if (
        child is None
        or traversal is None
        or child[0] != event.metadata.get("child_run_id")
        or child[2] != event.metadata.get("materialization_digest")
        or traversal[0] != child[2]
        or any(
            (source_step, position) not in work.active_children
            for position in range(len(traversal[1]))
        )
    ):
        return _replay_failure("active child failure lineage binding drift")
    for key in ("source_event_digest", "failure_policy_decision_digest"):
        checked = _require_metadata_digest(event, key)
        if isinstance(checked, Failure):
            return checked
    if (
        event.metadata["failure_policy_decision_digest"]
        != active_child_failure_decision_digest(event.metadata)
    ):
        return _replay_failure("active child failure cause binding drift")
    work.run.run_state = RunState.FAILED
    work.run.failures.append(source_step)
    return None


def _reduce_successor_materialized(
    event: ReplayEvent, work: _ClosureWork
) -> None | Failure:
    if work.run.run_state is not RunState.COMPLETED:
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
        or work.steps.get(source_step_id) is not StepState.SUCCEEDED
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
    return None


def _reduce_traversal_materialization_requested(
    event: ReplayEvent, work: _TraversalWork
) -> None | Failure:
    if work.run.run_state not in {
        RunState.READY,
        RunState.RUNNING,
        RunState.WAITING,
    }:
        return _replay_failure(
            "TraversalMaterializationRequested requires a live parent run"
        )
    if event.step_id is not None or event.attempt_id is not None:
        return _replay_failure(
            "TraversalMaterializationRequested is a run observation"
        )
    for key in ("source_step_id", "input_ref", "traversal_policy"):
        value = event.metadata.get(key)
        if not isinstance(value, str) or not value:
            return _replay_failure(
                "TraversalMaterializationRequested identity is incomplete"
            )
    for key in (
        "input_sequence_digest",
        "element_program_digest",
        "shape_digest",
        "binding_digest",
        "materialization_digest",
    ):
        digest = _require_metadata_digest(event, key)
        if isinstance(digest, Failure):
            return digest
    element_count = event.metadata.get("element_count")
    raw_element_digests = event.metadata.get("element_digests")
    element_digests = (
        raw_element_digests
        if _is_object_sequence(raw_element_digests)
        else None
    )
    if (
        not isinstance(element_count, int)
        or isinstance(element_count, bool)
        or element_count < 0
        or element_digests is None
        or len(element_digests) != element_count
        or any(
            not isinstance(item, str) or len(item) != 64 for item in element_digests
        )
    ):
        return _replay_failure(
            "TraversalMaterializationRequested element binding drift"
        )
    source_step_id = _require_metadata_string(event, "source_step_id")
    materialization_digest = _require_metadata_digest(
        event, "materialization_digest"
    )
    if isinstance(source_step_id, Failure):
        return source_step_id
    if isinstance(materialization_digest, Failure):
        return materialization_digest
    if source_step_id in work.traversals:
        return _replay_failure(
            "TraversalMaterializationRequested source step is duplicated"
        )
    work.traversals[source_step_id] = (
        materialization_digest,
        tuple(item for item in element_digests if isinstance(item, str)),
    )
    work.run.run_state = RunState.WAITING
    return None


def _reduce_active_child_materialized(
    event: ReplayEvent, work: _TraversalWork
) -> None | Failure:
    if work.run.run_state is not RunState.WAITING:
        return _replay_failure("ActiveChildMaterialized requires WAITING parent")
    if event.step_id is not None or event.attempt_id is not None:
        return _replay_failure("ActiveChildMaterialized is a run observation")
    for key in (
        "source_step_id",
        "child_run_id",
        "root_value_identity",
        "root_value_ref",
        "result_step_id",
        "input_ref",
    ):
        value = event.metadata.get(key)
        if not isinstance(value, str) or not value:
            return _replay_failure(
                "ActiveChildMaterialized identity is incomplete"
            )
    for key in (
        "materialization_digest",
        "element_digest",
        "child_program_digest",
        "root_value_digest",
        "input_digest",
    ):
        digest = _require_metadata_digest(event, key)
        if isinstance(digest, Failure):
            return digest
    index = event.metadata.get("element_index")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        return _replay_failure("ActiveChildMaterialized index is invalid")
    source_step_id = _require_metadata_string(event, "source_step_id")
    materialization_digest = _require_metadata_digest(
        event, "materialization_digest"
    )
    element_digest = _require_metadata_digest(event, "element_digest")
    child_run_id = _require_metadata_string(event, "child_run_id")
    if isinstance(source_step_id, Failure):
        return source_step_id
    if isinstance(materialization_digest, Failure):
        return materialization_digest
    if isinstance(element_digest, Failure):
        return element_digest
    if isinstance(child_run_id, Failure):
        return child_run_id
    traversal = work.traversals.get(source_step_id)
    if (
        traversal is None
        or traversal[0] != materialization_digest
        or index >= len(traversal[1])
        or traversal[1][index] != element_digest
        or (source_step_id, index) in work.active_children
        or child_run_id
        in {binding[0] for binding in work.active_children.values()}
    ):
        return _replay_failure("ActiveChildMaterialized lineage binding drift")
    work.active_children[(source_step_id, index)] = (
        child_run_id,
        element_digest,
        materialization_digest,
    )
    return None


def _reduce_active_children_settled(
    event: ReplayEvent, work: _TraversalWork
) -> None | Failure:
    if work.run.run_state is not RunState.WAITING:
        return _replay_failure("ActiveChildrenSettled requires WAITING parent")
    if event.step_id is not None or event.attempt_id is not None:
        return _replay_failure("ActiveChildrenSettled is a run observation")
    source_step_id = event.metadata.get("source_step_id")
    child_count = event.metadata.get("child_count")
    if (
        not isinstance(source_step_id, str)
        or not source_step_id
        or not isinstance(child_count, int)
        or isinstance(child_count, bool)
        or child_count < 0
        or event.payload_ref is None
        or event.payload_digest is None
    ):
        return _replay_failure("ActiveChildrenSettled binding is incomplete")
    result_digest = _require_metadata_digest(event, "result_digest")
    if isinstance(result_digest, Failure):
        return result_digest
    if event.payload_digest != result_digest:
        return _replay_failure("ActiveChildrenSettled payload digest drift")
    child_run_ids = event.metadata.get("child_run_ids")
    child_result_digests = event.metadata.get("child_result_digests")
    traversal = work.traversals.get(source_step_id)
    ordered_children = tuple(
        work.active_children.get((source_step_id, index))
        for index in range(child_count)
    )
    if (
        traversal is None
        or child_count != len(traversal[1])
        or any(item is None for item in ordered_children)
        or not _is_object_sequence(child_run_ids)
        or tuple(child_run_ids)
        != tuple(
            item[0] for item in ordered_children if item is not None
        )
        or not _is_optional_digest_sequence(child_result_digests)
        or len(child_result_digests) != child_count
    ):
        return _replay_failure("ActiveChildrenSettled child closure drift")
    if source_step_id in work.steps:
        return _replay_failure("ActiveChildrenSettled source step is duplicated")
    work.steps[source_step_id] = StepState.SUCCEEDED
    work.run.run_state = RunState.RUNNING
    return None


def _copy_activation_bindings(
    projection: RuntimeReplayProjection,
) -> dict[str, tuple[str, str, str]]:
    return {
        step_id: (assignment_digest, activation_digest, input_closure_digest)
        for (
            step_id,
            assignment_digest,
            activation_digest,
            input_closure_digest,
        ) in projection.step_activation_bindings
    }


def _copy_recovery_claims(
    projection: RuntimeReplayProjection,
) -> dict[str, tuple[str, str]]:
    return {
        recovery_attempt_id: (step_id, reconciliation_attempt_id)
        for recovery_attempt_id, step_id, reconciliation_attempt_id in projection.recovery_claim_bindings
    }


def _copy_traversals(
    projection: RuntimeReplayProjection,
) -> dict[str, tuple[str, tuple[str, ...]]]:
    return {
        step_id: (materialization_digest, element_digests)
        for step_id, materialization_digest, element_digests in projection.traversal_bindings
    }


def _copy_active_children(
    projection: RuntimeReplayProjection,
) -> dict[tuple[str, int], tuple[str, str, str]]:
    return {
        (step_id, index): (child_run_id, element_digest, materialization_digest)
        for step_id, index, child_run_id, element_digest, materialization_digest in projection.active_child_bindings
    }


def _run_work_from(projection: RuntimeReplayProjection) -> _RunWork:
    return _RunWork(
        run_state=projection.run_state,
        plan_digest=projection.plan_digest,
        failures=list(projection.required_failure_step_ids),
        pending=projection.pending_required_failure,
    )


def _activation_work_from(
    projection: RuntimeReplayProjection,
) -> _ActivationWork:
    return _ActivationWork(
        steps=dict(projection.steps),
        activation_bindings=_copy_activation_bindings(projection),
        run=_run_work_from(projection),
    )


def _effect_work_from(projection: RuntimeReplayProjection) -> _EffectWork:
    return _EffectWork(
        steps=dict(projection.steps),
        attempts=dict(projection.attempts),
        attempt_steps=dict(projection.attempt_step_bindings),
        recovery_claims=_copy_recovery_claims(projection),
        run=_run_work_from(projection),
    )


def _closure_work_from(projection: RuntimeReplayProjection) -> _ClosureWork:
    return _ClosureWork(
        steps=dict(projection.steps),
        attempts=dict(projection.attempts),
        attempt_steps=dict(projection.attempt_step_bindings),
        traversals=_copy_traversals(projection),
        active_children=_copy_active_children(projection),
        run=_run_work_from(projection),
    )


def _traversal_work_from(projection: RuntimeReplayProjection) -> _TraversalWork:
    return _TraversalWork(
        steps=dict(projection.steps),
        traversals=_copy_traversals(projection),
        active_children=_copy_active_children(projection),
        run=_run_work_from(projection),
    )


def _freeze_replay_work(
    projection: RuntimeReplayProjection,
    event: ReplayEvent,
    work: _ClosedReplayWork,
) -> RuntimeReplayProjection | Failure:
    run = work if isinstance(work, _RunWork) else work.run
    steps = projection.steps
    activation_bindings = projection.step_activation_bindings
    attempts = projection.attempts
    attempt_steps = projection.attempt_step_bindings
    recovery_claims = projection.recovery_claim_bindings
    traversals = projection.traversal_bindings
    active_children = projection.active_child_bindings

    if not isinstance(work, _RunWork):
        steps = tuple(sorted(work.steps.items()))
    if isinstance(work, _ActivationWork):
        activation_bindings = tuple(
            sorted(
                (step_id, assignment_digest, activation_digest, input_closure_digest)
                for step_id, (
                    assignment_digest,
                    activation_digest,
                    input_closure_digest,
                ) in work.activation_bindings.items()
            )
        )
    if isinstance(work, (_EffectWork, _ClosureWork)):
        attempts = tuple(sorted(work.attempts.items()))
        attempt_steps = tuple(sorted(work.attempt_steps.items()))
    if isinstance(work, _EffectWork):
        recovery_claims = tuple(
            sorted(
                (recovery_attempt_id, step_id, target_attempt_id)
                for recovery_attempt_id, (
                    step_id,
                    target_attempt_id,
                ) in work.recovery_claims.items()
            )
        )
    if isinstance(work, (_ClosureWork, _TraversalWork)):
        traversals = tuple(
            sorted(
                (step_id, materialization_digest, element_digests)
                for step_id, (
                    materialization_digest,
                    element_digests,
                ) in work.traversals.items()
            )
        )
        active_children = tuple(
            sorted(
                (step_id, index, child_run_id, element_digest, materialization_digest)
                for (step_id, index), (
                    child_run_id,
                    element_digest,
                    materialization_digest,
                ) in work.active_children.items()
            )
        )

    return _projection_result(
        project_key=projection.project_key,
        run_id=projection.run_id,
        run_incarnation=projection.run_incarnation,
        run_state=run.run_state,
        last_seq=event.seq,
        event_chain_digest=_chain_digest(
            projection.event_chain_digest, event.event_digest
        ),
        program_digest=projection.program_digest,
        plan_digest=run.plan_digest,
        steps=steps,
        step_activation_bindings=activation_bindings,
        attempts=attempts,
        attempt_step_bindings=attempt_steps,
        recovery_claim_bindings=recovery_claims,
        traversal_bindings=traversals,
        active_child_bindings=active_children,
        required_failure_step_ids=tuple(sorted(run.failures)),
        observed_event_types=projection.observed_event_types + (event.event_type,),
        pending_required_failure=run.pending,
    )


@dataclass(frozen=True, slots=True)
class _BootstrapEventRule:
    event_type: str
    schema_version: str
    reducer: _BootstrapReducer

    @property
    def key(self) -> tuple[str, str]:
        return self.event_type, self.schema_version

    def apply_event(
        self, event: ReplayEvent, projection: RuntimeReplayProjection | None
    ) -> RuntimeReplayProjection | Failure:
        return self.reducer(event, projection)


@dataclass(frozen=True, slots=True)
class _FieldEventRule(Generic[_ReplayWork]):
    event_type: str
    schema_version: str
    selector: Callable[[RuntimeReplayProjection], _ReplayWork]
    reducer: Callable[[ReplayEvent, _ReplayWork], None | Failure]
    enforces_existing_attempt_binding: bool = True

    @property
    def key(self) -> tuple[str, str]:
        return self.event_type, self.schema_version

    def apply_event(
        self, event: ReplayEvent, projection: RuntimeReplayProjection
    ) -> RuntimeReplayProjection | Failure:
        work = self.selector(projection)
        outcome = self.reducer(event, work)
        if isinstance(outcome, Failure):
            return outcome
        return _freeze_replay_work(projection, event, work)


_ReplayEventRule = (
    _BootstrapEventRule
    | _FieldEventRule[_RunWork]
    | _FieldEventRule[_ActivationWork]
    | _FieldEventRule[_EffectWork]
    | _FieldEventRule[_ClosureWork]
    | _FieldEventRule[_TraversalWork]
)


def _bootstrap_rule(
    event_type: str, schema_version: str, reducer: _BootstrapReducer
) -> _BootstrapEventRule:
    return _BootstrapEventRule(event_type, schema_version, reducer)


def _run_rule(
    event_type: str, schema_version: str, reducer: _RunReducer
) -> _FieldEventRule[_RunWork]:
    return _FieldEventRule(
        event_type,
        schema_version,
        _run_work_from,
        reducer,
    )


def _activation_rule(
    event_type: str,
    schema_version: str,
    reducer: _ActivationReducer,
) -> _FieldEventRule[_ActivationWork]:
    return _FieldEventRule(
        event_type,
        schema_version,
        _activation_work_from,
        reducer,
    )


def _effect_rule(
    event_type: str,
    schema_version: str,
    reducer: _EffectReducer,
    *,
    enforces_existing_attempt_binding: bool = True,
) -> _FieldEventRule[_EffectWork]:
    return _FieldEventRule(
        event_type,
        schema_version,
        _effect_work_from,
        reducer,
        enforces_existing_attempt_binding,
    )


def _closure_rule(
    event_type: str,
    schema_version: str,
    reducer: _ClosureReducer,
) -> _FieldEventRule[_ClosureWork]:
    return _FieldEventRule(
        event_type,
        schema_version,
        _closure_work_from,
        reducer,
    )


def _traversal_rule(
    event_type: str,
    schema_version: str,
    reducer: _TraversalReducer,
) -> _FieldEventRule[_TraversalWork]:
    return _FieldEventRule(
        event_type,
        schema_version,
        _traversal_work_from,
        reducer,
    )


_EVENT_RULES: tuple[_ReplayEventRule, ...] = (
    _bootstrap_rule(
        "ProgramAccepted",
        "mrw.runtime.event.program_accepted.v1",
        _reduce_program_accepted,
    ),
    _run_rule(
        "CompileSucceeded",
        "mrw.runtime.event.compile-succeeded.v1",
        _reduce_compile_succeeded,
    ),
    _run_rule(
        "PlanCompiled",
        "mrw.runtime.event.plan_compiled.v1",
        _reduce_plan_compiled,
    ),
    _run_rule(
        "QualificationActivated",
        "mrw.runtime.event.qualification_activated.v1",
        _reduce_qualification_activated,
    ),
    _activation_rule(
        "DeliveryReady",
        "mrw.runtime.event.delivery_ready.v1",
        _reduce_delivery_ready,
    ),
    _activation_rule(
        "StepActivated",
        "mrw.runtime.event.step_activated.v1",
        _reduce_step_activated,
    ),
    _effect_rule(
        StepEvent.STEP_CLAIMED.value,
        "mrw.runtime.event.step_claimed.v1",
        _reduce_step_claimed,
        enforces_existing_attempt_binding=False,
    ),
    _effect_rule(
        StepEvent.RECONCILE_REQUESTED.value,
        "mrw.runtime.event.step_claimed.v1",
        _reduce_reconcile_requested,
        enforces_existing_attempt_binding=False,
    ),
    _effect_rule(
        StepEvent.EFFECT_STARTED.value,
        "mrw.runtime.event.effect_started.v1",
        _reduce_effect_started,
    ),
    _effect_rule(
        StepEvent.COMMIT_PREPARED.value,
        "mrw.runtime.event.commit_prepared.v1",
        _reduce_commit_prepared,
    ),
    _effect_rule(
        StepEvent.RUNTIME_VALUE_PRODUCED.value,
        "mrw.runtime.event.effect_succeeded.v1",
        _reduce_effect_succeeded,
    ),
    _effect_rule(
        StepEvent.OUTCOME_STAGED.value,
        "mrw.runtime.event.effect_succeeded.v1",
        _reduce_effect_succeeded,
    ),
    _effect_rule(
        StepEvent.COMMIT_READBACK_CONFIRMED.value,
        "mrw.runtime.event.commit_readback_confirmed.v1",
        _reduce_commit_readback_confirmed,
    ),
    _effect_rule(
        StepEvent.EFFECT_FAILED.value,
        "mrw.runtime.event.effect_failed.v1",
        _reduce_effect_failed,
    ),
    _effect_rule(
        StepEvent.EFFECT_RECEIPT_LOST.value,
        "mrw.runtime.event.outcome_unknown.v1",
        _reduce_effect_receipt_lost,
    ),
    _effect_rule(
        "LeaseExpiredOutcomeUnknown",
        "mrw.runtime.event.lease_expired.v1",
        _reduce_lease_expired_outcome_unknown,
    ),
    _effect_rule(
        "LeaseExpiredReconcileRequired",
        "mrw.runtime.event.lease_expired.v1",
        _reduce_lease_expired_reconcile_required,
    ),
    _effect_rule(
        StepEvent.READBACK_UNAVAILABLE.value,
        "mrw.runtime.event.authoritative_readback.v1",
        _reduce_readback_unavailable,
    ),
    _effect_rule(
        StepEvent.AUTHORITATIVE_READBACK_SUCCEEDED.value,
        "mrw.runtime.event.authoritative_readback.v1",
        _reduce_authoritative_readback_succeeded,
    ),
    _effect_rule(
        StepEvent.AUTHORITATIVE_READBACK_FAILED.value,
        "mrw.runtime.event.authoritative_readback.v1",
        _reduce_authoritative_readback_failed,
    ),
    _effect_rule(
        RunEvent.REQUIRED_STEP_FAILED.value,
        "mrw.runtime.event.required_step_failed.v1",
        _reduce_required_step_failed,
    ),
    _closure_rule(
        RunEvent.REQUIRED_STEP_FAILED.value,
        "mrw.runtime.event.required_step_failed.active_child.v2",
        _reduce_active_child_required_failure,
    ),
    _closure_rule(
        RunEvent.CANCELLATION_REQUESTED.value,
        "mrw.runtime.event.cancellation_requested.v1",
        _reduce_cancellation_requested,
    ),
    _closure_rule(
        StepEvent.CLEANUP_OR_READBACK_CONFIRMED.value,
        "mrw.runtime.event.cancellation_cleanup_confirmed.v1",
        _reduce_cleanup_confirmed,
    ),
    _closure_rule(
        RunEvent.REQUIRED_CLEANUP_SETTLED.value,
        "mrw.runtime.event.cancellation_cleanup_settled.v1",
        _reduce_required_cleanup_settled,
    ),
    _closure_rule(
        RunEvent.RUN_COMPLETION_DERIVED.value,
        "mrw.runtime.event.run_completion_derived.v1",
        _reduce_run_completion_derived,
    ),
    _traversal_rule(
        "TraversalMaterializationRequested",
        "mrw.runtime.event.traversal_materialization_requested.v1",
        _reduce_traversal_materialization_requested,
    ),
    _traversal_rule(
        "ActiveChildMaterialized",
        "mrw.runtime.event.active_child_materialized.v1",
        _reduce_active_child_materialized,
    ),
    _traversal_rule(
        "ActiveChildrenSettled",
        "mrw.runtime.event.active_children_settled.v1",
        _reduce_active_children_settled,
    ),
    _closure_rule(
        "SuccessorMaterialized",
        "mrw.runtime.event.successor_materialized.v1",
        _reduce_successor_materialized,
    ),
)

_EVENT_RULES_BY_KEY: Mapping[tuple[str, str], _ReplayEventRule] = MappingProxyType(
    {rule.key: rule for rule in _EVENT_RULES}
)

_EVENT_SCHEMAS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        event_type: frozenset(
            rule.schema_version
            for rule in _EVENT_RULES
            if rule.event_type == event_type
        )
        for event_type in dict.fromkeys(rule.event_type for rule in _EVENT_RULES)
    }
)




def _apply_event_rules(
    projection: RuntimeReplayProjection | None, event: ReplayEvent
) -> RuntimeReplayProjection | Failure:
    rule = _EVENT_RULES_BY_KEY.get((event.event_type, event.schema_version))
    if rule is None:
        return _replay_failure(f"no pure replay reducer for {event.event_type!r}")
    if projection is None:
        if event.seq != 1 or event.event_type != "ProgramAccepted":
            return _replay_failure(
                "runtime journal must begin with ProgramAccepted seq=1"
            )
        if not isinstance(rule, _BootstrapEventRule):
            return _replay_failure(
                "runtime journal must begin with ProgramAccepted seq=1"
            )
        return rule.apply_event(event, projection)
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

    if isinstance(rule, _BootstrapEventRule):
        return rule.apply_event(event, projection)
    if (
        event.attempt_id is not None
        and rule.enforces_existing_attempt_binding
        and dict(projection.attempt_step_bindings).get(event.attempt_id)
        != event.step_id
    ):
        return _replay_failure("event attempt/step binding drift")
    return rule.apply_event(event, projection)


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
