"""PostgreSQL runtime journal repository.

The repository deliberately owns neither a session nor a transaction.  A caller
passes the :class:`~sqlalchemy.engine.Connection` that is already enlisted in a
``RuntimeUnitOfWork``.  A transition command set updates the operational run
snapshot, appends events, and creates successor work items on that same
connection.  It never calls ``commit`` or ``rollback``.

The public control plane contains only lifecycle facts and opaque references.
Program/plan/value/event payload bytes belong to the validated project store.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, model_validator
from sqlalchemy import Table, insert, select, update
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import (
    Digest,
    FrozenContract,
    InterpreterBinding,
    MaterializerBinding,
    ProjectorBinding,
    RecoveryBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.authority_grants import (
    AuthorityOperationScope,
    AuthorityResourceCeiling,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.qualification import (
    AuthorityContext,
    QualifiedPlan,
    StepAuthorizationBinding,
)

from .models import PUBLIC_TABLES


class ControlRepositoryError(RuntimeError):
    """Base error for fail-closed public-control repository operations."""


class RecordNotFound(ControlRepositoryError):
    pass


class StaleRevisionError(ControlRepositoryError):
    pass


class ExactBindingConflict(ControlRepositoryError):
    pass


class PublicPayloadViolation(ControlRepositoryError):
    pass


class ExactQualificationBinding(FrozenContract):
    """Content-addressed public control fact for one plan qualification."""

    schema_version: Literal["mrw.runtime.qualification.binding.v1"] = (
        "mrw.runtime.qualification.binding.v1"
    )
    qualification_id: str = Field(min_length=1)
    project_key: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    plan_digest: Digest
    authority_context: AuthorityContext
    authority_context_digest: Digest
    qualified_plan: QualifiedPlan
    decision: Literal["QUALIFIED", "REJECTED", "AWAITING_APPROVAL"]
    qualification_binding_digest: Digest

    @model_validator(mode="after")
    def validate_digest(self) -> "ExactQualificationBinding":
        if self.authority_context.context_digest != self.authority_context_digest:
            raise ValueError("qualification authority context digest drift")
        if (
            self.qualified_plan.plan_digest != self.plan_digest
            or self.qualified_plan.authority_context_digest
            != self.authority_context_digest
        ):
            raise ValueError("qualification plan/context binding drift")
        for binding in self.qualified_plan.step_bindings:
            if binding.project_key != self.project_key or binding.run_id != self.run_id:
                raise ValueError("qualification contains cross-scope step binding")
        if self.decision == "QUALIFIED" and (
            self.qualified_plan.awaiting_approval_steps
            or self.qualified_plan.denied_steps
        ):
            raise ValueError("QUALIFIED plan cannot contain awaiting or denied steps")
        expected = canonical_digest(
            self, exclude_fields={"qualification_binding_digest"}
        )
        if self.qualification_binding_digest != expected:
            raise ValueError("qualification binding digest mismatch")
        return self

    @classmethod
    def from_content(cls, **content: object) -> "ExactQualificationBinding":
        provisional = cls.model_construct(
            **content,
            qualification_binding_digest="0" * 64,
        )
        return cls(
            **content,
            qualification_binding_digest=canonical_digest(
                provisional,
                exclude_fields={"qualification_binding_digest"},
            ),
        )


_FORBIDDEN_CONTROL_KEYS = frozenset(
    {
        "bytes",
        "content",
        "document",
        "exact_bytes",
        "inline_json",
        "payload",
        "plan_json",
        "program_json",
        "prompt",
        "query",
        "spec_json",
        "text",
        "value_json",
    }
)

_CONTROL_METADATA_KEY_SUFFIXES = (
    "_code",
    "_digest",
    "_epoch",
    "_id",
    "_ref",
    "_revision",
    "_state",
)
_CONTROL_METADATA_EXACT_KEYS = frozenset(
    {"decision", "reason", "state", "status", "wait_reason"}
)
_MAX_CONTROL_SCALAR_CHARS = 4096
_OPAQUE_LOCATOR_PATTERN = re.compile(
    r"^(?:value|project-value|runtime-blob|blob|canonical|artifact|receipt|staged|external|source):"
    r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$"
)


def _require_opaque_locator(value: Any, *, path: str) -> str:
    if not isinstance(value, str) or _OPAQUE_LOCATOR_PATTERN.fullmatch(value) is None:
        raise PublicPayloadViolation(
            f"public control reference is not a bounded opaque locator: {path}"
        )
    return value


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _table(name: str) -> Table:
    try:
        return PUBLIC_TABLES[name]
    except KeyError as exc:  # pragma: no cover - integration configuration error
        raise RuntimeError(f"missing P0-B public table: {name}") from exc


def _scope_key(scope: RuntimeScope) -> str:
    project_key = scope.project_scope.project_key
    if not project_key:
        raise ValueError("RuntimeScope has no project key")
    return project_key


def _as_mapping(row: Any) -> Mapping[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, Mapping):
        return row
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return mapping
    raise TypeError("database row does not expose a mapping")


def _one_mapping(result: Any) -> Mapping[str, Any] | None:
    mappings = getattr(result, "mappings", None)
    if callable(mappings):
        return _as_mapping(mappings().one_or_none())
    return _as_mapping(result.one_or_none())


def _mapping_rows(result: Any) -> tuple[Mapping[str, Any], ...]:
    mappings = getattr(result, "mappings", None)
    rows = mappings().all() if callable(mappings) else result.all()
    return tuple(_as_mapping(row) or {} for row in rows)


def _assert_no_payload_bytes(value: Any, *, path: str = "control") -> None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise PublicPayloadViolation(f"public control row contains payload bytes at {path}")
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_CONTROL_KEYS:
                raise PublicPayloadViolation(
                    f"public control row contains forbidden payload field: {path}.{key}"
                )
            if normalized == "event_metadata_json":
                _validate_event_metadata(child, path=f"{path}.{key}")
                continue
            if normalized == "payload_ref":
                if child is not None:
                    _require_opaque_locator(child, path=f"{path}.{key}")
                continue
            if normalized == "claim_binding_json":
                if child is None:
                    continue
                _validate_typed_control_json(
                    ClaimBinding,
                    child,
                    path=f"{path}.{key}",
                )
                continue
            if normalized == "assignment_binding_json":
                _validate_typed_control_json(
                    RuntimeAssignment,
                    child,
                    path=f"{path}.{key}",
                )
                continue
            if normalized == "qualification_binding_json":
                _validate_typed_control_json(
                    ExactQualificationBinding,
                    child,
                    path=f"{path}.{key}",
                )
                continue
            if normalized == "qualified_plan_json":
                _validate_typed_control_json(
                    QualifiedPlan,
                    child,
                    path=f"{path}.{key}",
                )
                continue
            if normalized == "authorization_binding_json":
                _validate_typed_control_json(
                    StepAuthorizationBinding,
                    child,
                    path=f"{path}.{key}",
                )
                continue
            if normalized == "recovery_binding_json":
                _validate_typed_control_json(
                    RecoveryBinding,
                    child,
                    path=f"{path}.{key}",
                )
                continue
            if normalized == "operation_scope_json":
                _validate_typed_control_json(
                    AuthorityOperationScope,
                    child,
                    path=f"{path}.{key}",
                )
                continue
            if normalized == "resource_ceiling_json":
                _validate_typed_control_json(
                    AuthorityResourceCeiling,
                    child,
                    path=f"{path}.{key}",
                )
                continue
            if isinstance(child, (Mapping, tuple, list, set, frozenset)):
                raise PublicPayloadViolation(
                    f"public control row contains untyped nested value: {path}.{key}"
                )
            _assert_no_payload_bytes(child, path=f"{path}.{key}")
    elif isinstance(value, (tuple, list, set, frozenset)):
        for index, child in enumerate(value):
            _assert_no_payload_bytes(child, path=f"{path}[{index}]")


def _validate_event_metadata(value: Any, *, path: str) -> None:
    if not isinstance(value, Mapping):
        raise PublicPayloadViolation(f"event metadata must be an object: {path}")
    for key, child in value.items():
        normalized = str(key).strip().lower()
        if not normalized or not (
            normalized in _CONTROL_METADATA_EXACT_KEYS
            or normalized.endswith(_CONTROL_METADATA_KEY_SUFFIXES)
        ):
            raise PublicPayloadViolation(
                f"event metadata key is not lifecycle/ref/id/digest data: {path}.{key}"
            )
        if child is not None and not isinstance(child, (str, int, float, bool)):
            raise PublicPayloadViolation(
                f"event metadata value must be a bounded scalar: {path}.{key}"
            )
        if isinstance(child, str) and len(child) > _MAX_CONTROL_SCALAR_CHARS:
            raise PublicPayloadViolation(
                f"event metadata scalar exceeds bound: {path}.{key}"
            )


def _validate_typed_control_json(
    model: type[FrozenContract], value: Any, *, path: str
) -> FrozenContract:
    if not isinstance(value, Mapping):
        raise PublicPayloadViolation(f"typed control binding must be an object: {path}")
    try:
        return model.model_validate(value)
    except Exception as exc:
        raise PublicPayloadViolation(f"invalid typed control binding at {path}") from exc


def _project_values(scope: RuntimeScope, values: Mapping[str, Any]) -> dict[str, Any]:
    projected = dict(values)
    supplied = projected.pop("project_key", _scope_key(scope))
    if supplied != _scope_key(scope):
        raise ExactBindingConflict("row project_key does not match RuntimeScope")
    projected["project_key"] = supplied
    _assert_no_payload_bytes(projected)
    return projected


def validate_runtime_assignment_row(values: Mapping[str, Any]) -> RuntimeAssignment:
    """Parse, rehash, and compare every duplicated assignment column."""

    raw = values.get("assignment_binding_json")
    if not isinstance(raw, Mapping):
        raise ExactBindingConflict("work item lacks exact assignment_binding_json")
    try:
        assignment = RuntimeAssignment.model_validate(raw)
    except Exception as exc:
        raise ExactBindingConflict("invalid exact RuntimeAssignment binding") from exc
    canonical = assignment.model_dump(mode="json")
    if dict(raw) != canonical:
        raise ExactBindingConflict("RuntimeAssignment binding is not canonical")
    if values.get("assignment_digest") != assignment.assignment_digest:
        raise ExactBindingConflict("RuntimeAssignment digest mismatch")
    if assignment.payload_ref is not None:
        _require_opaque_locator(
            assignment.payload_ref,
            path="assignment_binding_json.payload_ref",
        )
    for index, input_ref in enumerate(assignment.input_refs):
        _require_opaque_locator(
            input_ref,
            path=f"assignment_binding_json.input_refs[{index}]",
        )

    handler = assignment.handler_binding
    interpreter_profile_digest = (
        handler.interpreter_profile_digest
        if isinstance(handler, (InterpreterBinding, RecoveryBinding))
        else None
    )
    expected: dict[str, Any] = {
        "work_item_id": assignment.work_item_id,
        "project_key": assignment.project_key,
        "run_id": assignment.run_id,
        "step_id": assignment.step_id,
        "assignment_kind": assignment.assignment_kind.value,
        "capability_id": assignment.capability_id,
        "operation_contract_digest": assignment.operation_contract_digest,
        "assignment_digest": assignment.assignment_digest,
        "execution_epoch": assignment.execution_epoch,
        "assignment_incarnation": assignment.incarnation,
        "input_closure_digest": assignment.input_closure_digest,
        "claim_authority_epoch": assignment.claim_authority_epoch,
        "claim_policy_digest": assignment.claim_policy_digest,
        "handler_binding_kind": assignment.handler_binding_kind.value,
        "handler_binding_ref": assignment.handler_binding_ref,
        "handler_binding_digest": assignment.handler_binding_digest,
        "deployment_catalog_digest": assignment.deployment_catalog_digest,
        "runtime_protocol_version": assignment.runtime_protocol_version,
        "interpreter_profile_digest": interpreter_profile_digest,
        "program_digest": assignment.program_digest,
        "plan_digest": assignment.plan_digest,
        "expected_step_revision": assignment.expected_step_revision,
        "reconciliation_attempt_id": assignment.reconciliation_attempt_id,
        "payload_ref": assignment.payload_ref,
        "payload_digest": assignment.payload_digest,
        "resource_policy_epoch": assignment.resource_policy_epoch,
        "queue_eligibility_digest": assignment.queue_eligibility_digest,
        "deadline_at": assignment.deadline_at,
    }
    if isinstance(handler, ProjectorBinding):
        expected.update(
            source_ref=handler.source_ref,
            source_digest=handler.source_digest,
            declared_loss_profile_ref=handler.declared_loss_profile_ref,
        )
    if isinstance(handler, MaterializerBinding):
        expected.update(
            predecessor_plan_digest=handler.predecessor_plan_digest,
            source_value_digest=handler.source_value_digest,
            target_domain_contract_snapshot_digest=(
                handler.target_domain_contract_snapshot_digest
            ),
        )
    if isinstance(handler, RecoveryBinding):
        expected["authoritative_readback_profile_ref"] = (
            handler.authoritative_readback_profile_ref
        )
    if assignment.assignment_kind.value in {"INTERPRET", "VERIFY_ADMIT"}:
        recovery_raw = values.get("recovery_binding_json")
        if not isinstance(recovery_raw, Mapping):
            raise ExactBindingConflict("effect assignment lacks exact recovery binding")
        try:
            recovery = RecoveryBinding.model_validate(recovery_raw)
        except Exception as exc:
            raise ExactBindingConflict("invalid exact recovery binding") from exc
        if dict(recovery_raw) != recovery.model_dump(mode="json"):
            raise ExactBindingConflict("recovery binding is not canonical")
        expected_recovery_ref = (
            f"handler-binding:sha256:{recovery.binding_digest}"
        )
        if (
            values.get("recovery_handler_binding_ref") != expected_recovery_ref
            or values.get("recovery_handler_binding_digest")
            != recovery.binding_digest
            or values.get("authoritative_readback_profile_ref")
            != recovery.authoritative_readback_profile_ref
            or recovery.interpreter_profile_digest != interpreter_profile_digest
        ):
            raise ExactBindingConflict("effect recovery binding drift")
    mismatches = [
        column
        for column, expected_value in expected.items()
        if values.get(column) != expected_value
    ]
    if mismatches:
        raise ExactBindingConflict(
            "RuntimeAssignment duplicated-column drift: " + ", ".join(mismatches)
        )
    return assignment


def validate_qualification_row(
    values: Mapping[str, Any],
) -> ExactQualificationBinding:
    raw = values.get("qualification_binding_json")
    if not isinstance(raw, Mapping):
        raise ExactBindingConflict("qualification row lacks exact binding JSON")
    try:
        binding = ExactQualificationBinding.model_validate(raw)
    except Exception as exc:
        raise ExactBindingConflict("invalid exact qualification binding") from exc
    canonical = binding.model_dump(mode="json")
    if dict(raw) != canonical:
        raise ExactBindingConflict("qualification binding is not canonical")
    expected = {
        "qualification_id": binding.qualification_id,
        "project_key": binding.project_key,
        "run_id": binding.run_id,
        "plan_id": binding.plan_id,
        "plan_digest": binding.plan_digest,
        "authority_context_digest": binding.authority_context_digest,
        "decision": binding.decision,
        "qualification_digest": binding.qualified_plan.qualification_digest,
        "qualification_binding_digest": binding.qualification_binding_digest,
        "qualified_plan_json": binding.qualified_plan.model_dump(mode="json"),
    }
    mismatches = [
        column
        for column, expected_value in expected.items()
        if values.get(column) != expected_value
    ]
    if mismatches:
        raise ExactBindingConflict(
            "qualification duplicated-column drift: " + ", ".join(mismatches)
        )
    return binding


def validate_authorization_row(
    values: Mapping[str, Any],
) -> StepAuthorizationBinding:
    raw = values.get("authorization_binding_json")
    if not isinstance(raw, Mapping):
        raise ExactBindingConflict("authorization row lacks exact binding JSON")
    try:
        binding = StepAuthorizationBinding.model_validate(raw)
    except Exception as exc:
        raise ExactBindingConflict("invalid exact step authorization binding") from exc
    canonical = binding.model_dump(mode="json")
    if dict(raw) != canonical:
        raise ExactBindingConflict("step authorization binding is not canonical")
    expected = {
        "project_key": binding.project_key,
        "run_id": binding.run_id,
        "step_id": binding.step_id,
        "operation_kind": binding.operation_kind,
        "operation_contract_digest": binding.operation_contract_digest,
        "capability_id": binding.capability_id,
        "claim_owner": binding.claim_owner,
        "claim_authority_epoch": binding.claim_authority_epoch,
        "claim_policy_digest": binding.claim_policy_digest,
        "payload_digest": binding.payload_digest,
        "actor_id": binding.actor_id,
        "project_registry_revision": binding.project_registry_revision,
        "project_scope_digest": binding.project_scope_digest,
        "grant_epoch": binding.grant_epoch,
        "expires_at": binding.expires_at,
        "authorization_digest": binding.binding_digest,
        "interpreter_binding_digest": binding.interpreter_binding_digest,
        "deployment_catalog_digest": binding.deployment_catalog_digest,
        "authority_source_bindings_json": [
            item.model_dump(mode="json")
            for item in binding.authority_source_bindings
        ],
        "grants_digest": binding.grants_digest,
        "approval_refs_json": list(binding.approval_refs),
        "resource_ceiling_digest": binding.resource_ceiling_digest,
        "resource_policy_epoch": binding.resource_policy_epoch,
        "queue_eligibility_digest": binding.queue_eligibility_digest,
        "canonical_base_revision": binding.canonical_base_revision,
        "canonical_incarnation": binding.canonical_incarnation,
    }
    mismatches = [
        column
        for column, expected_value in expected.items()
        if values.get(column) != expected_value
    ]
    if mismatches:
        raise ExactBindingConflict(
            "authorization duplicated-column drift: " + ", ".join(mismatches)
        )
    return binding


@dataclass(frozen=True, slots=True)
class JournalTransitionReceipt:
    run_id: str
    previous_revision: int
    revision: int
    first_event_seq: int | None
    last_event_seq: int | None
    event_count: int
    work_item_count: int


@dataclass(frozen=True, slots=True)
class JournalCommandSet:
    """One atomic journal transition to execute inside the caller's UoW."""

    scope: RuntimeScope
    run_id: str
    expected_revision: int
    snapshot_values: Mapping[str, Any]
    events: tuple[Mapping[str, Any], ...]
    work_items: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if self.expected_revision < 0:
            raise ValueError("expected_revision must be non-negative")
        _assert_no_payload_bytes(self.snapshot_values, path="snapshot")
        _assert_no_payload_bytes(self.events, path="events")
        _assert_no_payload_bytes(self.work_items, path="work_items")
        for work_item in self.work_items:
            values = _project_values(self.scope, work_item)
            values.setdefault("run_id", self.run_id)
            validate_runtime_assignment_row(values)

    def execute(self, connection: Connection) -> JournalTransitionReceipt:
        """Lock, validate, allocate sequence numbers, and apply all commands.

        The run row is the allocator.  ``MAX(seq) + 1`` is intentionally never
        queried; ``next_event_seq`` advances only while the run row is locked.
        Any later command failure leaves rollback to the enclosing UoW.
        """

        runs = _table("runtime_runs")
        events_table = _table("runtime_events")
        work_items_table = _table("runtime_work_items")
        project_key = _scope_key(self.scope)
        locked = _one_mapping(
            connection.execute(
                select(runs.c.revision, runs.c.next_event_seq)
                .where(runs.c.project_key == project_key, runs.c.run_id == self.run_id)
                .with_for_update()
            )
        )
        if locked is None:
            raise RecordNotFound(f"runtime run not found: {self.run_id}")
        actual_revision = int(locked["revision"])
        if actual_revision != self.expected_revision:
            raise StaleRevisionError(
                f"stale runtime run revision: expected {self.expected_revision}, "
                f"found {actual_revision}"
            )

        first_seq = int(locked["next_event_seq"]) if self.events else None
        next_seq = int(locked["next_event_seq"]) + len(self.events)
        snapshot = _project_values(self.scope, self.snapshot_values)
        for immutable in ("run_id", "revision", "next_event_seq"):
            snapshot.pop(immutable, None)
        now = _utcnow()
        snapshot.update(
            revision=self.expected_revision + 1,
            next_event_seq=next_seq,
            updated_at=now,
        )
        updated = connection.execute(
            update(runs)
            .where(
                runs.c.project_key == project_key,
                runs.c.run_id == self.run_id,
                runs.c.revision == self.expected_revision,
            )
            .values(**snapshot)
        )
        if getattr(updated, "rowcount", None) != 1:
            raise StaleRevisionError("runtime run CAS update affected no row")

        for offset, event in enumerate(self.events):
            event_values = _project_values(self.scope, event)
            supplied_run = event_values.pop("run_id", self.run_id)
            if supplied_run != self.run_id:
                raise ExactBindingConflict("event run_id does not match transition run")
            if "seq" in event_values:
                raise ExactBindingConflict("event seq is allocated by the locked run row")
            event_values.update(
                run_id=self.run_id,
                seq=(first_seq or 0) + offset,
                created_at=event_values.get("created_at", now),
                updated_at=event_values.get("updated_at", now),
            )
            connection.execute(insert(events_table).values(**event_values))

        for work_item in self.work_items:
            values = _project_values(self.scope, work_item)
            values.setdefault("run_id", self.run_id)
            assignment = validate_runtime_assignment_row(values)
            values["assignment_binding_json"] = assignment.model_dump(mode="json")
            supplied_run = values.pop("run_id", self.run_id)
            if supplied_run != self.run_id:
                raise ExactBindingConflict("work item run_id does not match transition run")
            # enqueue_seq is a PostgreSQL identity.  Application-side sequence
            # computation would reintroduce a cross-node race.
            if values.get("enqueue_seq") is not None:
                raise ExactBindingConflict("enqueue_seq must be allocated by PostgreSQL")
            values.pop("enqueue_seq", None)
            values.update(
                run_id=self.run_id,
                created_at=values.get("created_at", now),
                updated_at=values.get("updated_at", now),
            )
            connection.execute(insert(work_items_table).values(**values))

        last_seq = None if first_seq is None else first_seq + len(self.events) - 1
        return JournalTransitionReceipt(
            run_id=self.run_id,
            previous_revision=self.expected_revision,
            revision=self.expected_revision + 1,
            first_event_seq=first_seq,
            last_event_seq=last_seq,
            event_count=len(self.events),
            work_item_count=len(self.work_items),
        )


class RuntimeJournalRepository:
    """Project-scoped access to append-only runtime lifecycle facts."""

    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def commands(
        self,
        *,
        run_id: str,
        expected_revision: int,
        snapshot_values: Mapping[str, Any],
        events: Sequence[Mapping[str, Any]],
        work_items: Sequence[Mapping[str, Any]] = (),
    ) -> JournalCommandSet:
        return JournalCommandSet(
            scope=self.scope,
            run_id=run_id,
            expected_revision=expected_revision,
            snapshot_values=dict(snapshot_values),
            events=tuple(dict(event) for event in events),
            work_items=tuple(dict(item) for item in work_items),
        )

    def append_transition(self, **kwargs: Any) -> JournalTransitionReceipt:
        return self.commands(**kwargs).execute(self.connection)

    def load_run(self, run_id: str, *, for_update: bool = False) -> Mapping[str, Any]:
        runs = _table("runtime_runs")
        statement = select(runs).where(
            runs.c.project_key == _scope_key(self.scope), runs.c.run_id == run_id
        )
        if for_update:
            statement = statement.with_for_update()
        row = _one_mapping(self.connection.execute(statement))
        if row is None:
            raise RecordNotFound(f"runtime run not found: {run_id}")
        return row

    def load_events(self, run_id: str, *, after_seq: int = 0) -> tuple[Mapping[str, Any], ...]:
        if after_seq < 0:
            raise ValueError("after_seq must be non-negative")
        events = _table("runtime_events")
        return _mapping_rows(
            self.connection.execute(
                select(events)
                .where(
                    events.c.project_key == _scope_key(self.scope),
                    events.c.run_id == run_id,
                    events.c.seq > after_seq,
                )
                .order_by(events.c.seq)
            )
        )


__all__ = [
    "ControlRepositoryError",
    "ExactQualificationBinding",
    "ExactBindingConflict",
    "JournalCommandSet",
    "JournalTransitionReceipt",
    "PublicPayloadViolation",
    "RecordNotFound",
    "RuntimeJournalRepository",
    "StaleRevisionError",
    "validate_authorization_row",
    "validate_qualification_row",
    "validate_runtime_assignment_row",
]
