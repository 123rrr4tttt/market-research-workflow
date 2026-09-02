"""Concrete PostgreSQL run/effect lifecycle transitions for P0-C.

All methods execute on the caller-owned connection.  A terminal effect command
locks and updates the attempt, step, work item, reservation, event allocator,
and run snapshot in one transaction.  Releasing a lease is never treated as a
semantic success/failure transition.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import MetaData, insert, select, update
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    InterpreterBinding,
    MaterializerBinding,
    ProjectorBinding,
    RecoveryBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.reducer import (
    CompletionPolicy,
    RunSnapshot,
    StepSnapshot,
    completion_satisfied,
    reduce_run_completion,
    reduce_run_event,
    reduce_step,
)
from app.successor_runtime.runtime.replay import runtime_event_digest
from app.successor_runtime.runtime.transitions import (
    EffectDisposition,
    RunEvent,
    RunState,
    StepEvent,
    StepState,
)

from .failure_policy import PostgresFailurePolicyLoader
from .models import project_tables
from .runtime_failures import RuntimeFailureRepository
from .runtime_journal import (
    ExactBindingConflict,
    ExactQualificationBinding,
    RecordNotFound,
    StaleRevisionError,
    _one_mapping,
    _scope_key,
    _table,
    _utcnow,
    validate_qualification_row,
    validate_runtime_assignment_row,
)
from .terminal_authority import PostgresTerminalAuthorityVerifier


class EffectTerminalKind(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


@dataclass(frozen=True, slots=True)
class AssignmentEnvelope:
    assignment: RuntimeAssignment
    required_node_profile_selector: str
    authority_digest: str
    resource_policy_digest: str
    fairness_key: str
    qualification_digest: str | None = None
    resource_class: str | None = None
    resource_units: int | None = None
    concurrency_key: str | None = None
    provider_key: str | None = None
    recovery_binding: RecoveryBinding | None = None
    authoritative_readback_profile_ref: str | None = None
    delivery_intent_ref: str | None = None
    declared_priority: int = 0


@dataclass(frozen=True, slots=True)
class SubmitRun:
    run_id: str
    incarnation: str
    program_id: str
    program_digest: str
    program_storage_ref: str
    contract_version: str
    submission_authority_digest: str
    compile_work: AssignmentEnvelope
    due_at: datetime


@dataclass(frozen=True, slots=True)
class AttachPlan:
    run_id: str
    expected_run_revision: int
    plan_id: str
    plan_digest: str
    program_id: str
    program_digest: str
    project_storage_ref: str
    compiler_id: str
    compiler_version: str
    operation_catalog_id: str
    catalog_version: str
    catalog_digest: str
    effect_closure_digest: str
    authority_closure_digest: str
    resource_closure_digest: str
    qualify_work: AssignmentEnvelope
    due_at: datetime


@dataclass(frozen=True, slots=True)
class ActivateQualification:
    run_id: str
    expected_run_revision: int
    binding: ExactQualificationBinding


@dataclass(frozen=True, slots=True)
class ClaimedLifecycle:
    claim: ClaimBinding
    run_id: str
    step_id: str
    work_item_id: str
    attempt_id: str
    reservation_id: str
    expected_run_revision: int
    expected_step_revision: int
    expected_work_revision: int
    expected_attempt_revision: int
    expected_reservation_revision: int

    def __post_init__(self) -> None:
        expected = (
            self.claim.work_item_id,
            self.claim.attempt_id,
        )
        if expected != (self.work_item_id, self.attempt_id):
            raise ValueError("claimed lifecycle identity differs from ClaimBinding")
        if any(
            revision < 0
            for revision in (
                self.expected_run_revision,
                self.expected_step_revision,
                self.expected_work_revision,
                self.expected_attempt_revision,
                self.expected_reservation_revision,
            )
        ):
            raise ValueError("lifecycle expected revisions must be non-negative")


@dataclass(frozen=True, slots=True)
class TerminalOutcome:
    claimed: ClaimedLifecycle
    kind: EffectTerminalKind
    authority_digest: str
    output_digest: str | None = None
    receipt_ref: str | None = None
    receipt_digest: str | None = None
    failure_ref: str | None = None
    failure_digest: str | None = None
    staged_artifact_id: str | None = None
    expected_staged_revision: int | None = None
    admit_staged: bool = False
    step_event: StepEvent | None = None
    target_step_state: StepState | None = None
    event_type: str | None = None
    event_schema_version: str | None = None
    payload_ref: str | None = None
    payload_digest: str | None = None
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        if (self.payload_ref is None) != (self.payload_digest is None):
            raise ValueError("terminal event payload ref/digest must be an exact pair")
        if (self.receipt_ref is None) != (self.receipt_digest is None):
            raise ValueError("terminal receipt ref/digest must be an exact pair")
        if self.kind is EffectTerminalKind.SUCCEEDED and self.output_digest is None:
            raise ValueError("successful outcome requires output_digest")
        if self.kind is EffectTerminalKind.FAILED and self.failure_digest is None:
            raise ValueError("failed outcome requires failure_digest")
        if self.kind is EffectTerminalKind.FAILED and self.failure_ref is None:
            raise ValueError("failed outcome requires project-scoped failure_ref")
        if (self.staged_artifact_id is None) != (self.expected_staged_revision is None):
            raise ValueError("staged artifact identity/revision must be an exact pair")
        if self.admit_staged and self.staged_artifact_id is None:
            raise ValueError("admit_staged requires an exact staged artifact")


class TerminalAuthorityPort(Protocol):
    def require_current(
        self,
        *,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        authorization_digest: str,
        observed_at: datetime,
    ) -> None: ...


class TerminalFailurePort(Protocol):
    def verify_exact(self, scope: RuntimeScope, **kwargs: object) -> object: ...


class PersistedFailurePolicyPort(Protocol):
    def load_decision(self, run_id: str, step_id: str) -> object: ...


class RuntimeLifecycleRepository:
    def __init__(
        self,
        connection: Connection,
        scope: RuntimeScope,
        *,
        terminal_authority: TerminalAuthorityPort | None = None,
        terminal_failures: TerminalFailurePort | None = None,
        failure_policy: PersistedFailurePolicyPort | None = None,
    ) -> None:
        self.connection = connection
        self.scope = scope
        self._terminal_authority = terminal_authority or (
            PostgresTerminalAuthorityVerifier(connection)
        )
        self._terminal_failures = terminal_failures or RuntimeFailureRepository(
            connection,
            project_tables(MetaData(), scope.project_scope.resolved_schema),
        )
        self._failure_policy = failure_policy or PostgresFailurePolicyLoader(
            connection,
            scope,
        )

    def submit(self, command: SubmitRun) -> Mapping[str, Any]:
        project_key = _scope_key(self.scope)
        assignment = command.compile_work.assignment
        if (
            assignment.project_key != project_key
            or assignment.run_id != command.run_id
            or assignment.program_digest != command.program_digest
            or assignment.incarnation != command.incarnation
            or assignment.assignment_kind.value != "COMPILE"
        ):
            raise ExactBindingConflict("compile assignment differs from submitted run")
        programs = _table("runtime_program_refs")
        existing_ref = _one_mapping(
            self.connection.execute(
                select(programs).where(
                    programs.c.project_key == project_key,
                    programs.c.program_id == command.program_id,
                )
            )
        )
        program_values = {
            "project_key": project_key,
            "program_id": command.program_id,
            "program_digest": command.program_digest,
            "project_storage_ref": command.program_storage_ref,
            "contract_version": command.contract_version,
        }
        if existing_ref is not None:
            if any(existing_ref[key] != value for key, value in program_values.items()):
                raise ExactBindingConflict("runtime Program ref identity was rebound")
        else:
            now = _utcnow()
            self.connection.execute(
                insert(programs).values(
                    **program_values, created_at=now, updated_at=now
                )
            )

        runs = _table("runtime_runs")
        now = _utcnow()
        self.connection.execute(
            insert(runs).values(
                run_id=command.run_id,
                project_key=project_key,
                project_registry_revision=self.scope.project_scope.project_registry_revision,
                project_scope_digest=self.scope.project_scope.scope_digest,
                resolved_schema=self.scope.project_scope.resolved_schema,
                program_id=command.program_id,
                program_digest=command.program_digest,
                plan_id=None,
                plan_digest=None,
                state="SUBMITTED",
                revision=0,
                next_event_seq=2,
                execution_epoch=assignment.execution_epoch,
                incarnation=command.incarnation,
                submission_authority_digest=command.submission_authority_digest,
                qualification_digest=None,
                cancellation_requested=False,
                created_at=now,
                updated_at=now,
            )
        )
        events = _table("runtime_events")
        self.connection.execute(
            insert(events).values(
                project_key=project_key,
                run_id=command.run_id,
                seq=1,
                event_type="ProgramAccepted",
                schema_version="mrw.runtime.event.program_accepted.v1",
                event_metadata_json={
                    "program_id": command.program_id,
                    "program_digest": command.program_digest,
                },
                authority_digest=command.submission_authority_digest,
                created_at=now,
                updated_at=now,
            )
        )
        work_items = _table("runtime_work_items")
        self.connection.execute(
            insert(work_items).values(
                **_assignment_values(command.compile_work, due_at=command.due_at),
                created_at=now,
                updated_at=now,
            )
        )
        row = _one_mapping(
            self.connection.execute(
                select(runs).where(
                    runs.c.project_key == project_key, runs.c.run_id == command.run_id
                )
            )
        )
        assert row is not None
        return row

    def attach_plan(self, command: AttachPlan) -> Mapping[str, Any]:
        """Attach exact Plan and enqueue QUALIFY on the caller transaction.

        The current P0-B check constraint cannot persist the architecture's
        required intermediate ``COMPILING + plan + no qualification`` state.
        This method still emits the exact SQL/CAS contract so a corrected
        schema can run it; until that correction lands, a live PostgreSQL call
        fails closed at commit rather than inventing a qualification digest.
        """

        project_key = _scope_key(self.scope)
        assignment = command.qualify_work.assignment
        if (
            assignment.assignment_kind.value != "QUALIFY"
            or assignment.run_id != command.run_id
            or assignment.project_key != project_key
            or assignment.plan_digest != command.plan_digest
            or assignment.program_digest != command.program_digest
        ):
            raise ExactBindingConflict(
                "qualification assignment differs from exact Plan"
            )
        plans = _table("runtime_plan_refs")
        now = _utcnow()
        plan_values = {
            "plan_id": command.plan_id,
            "project_key": project_key,
            "plan_digest": command.plan_digest,
            "program_id": command.program_id,
            "program_digest": command.program_digest,
            "project_storage_ref": command.project_storage_ref,
            "compiler_id": command.compiler_id,
            "compiler_version": command.compiler_version,
            "operation_catalog_id": command.operation_catalog_id,
            "catalog_version": command.catalog_version,
            "catalog_digest": command.catalog_digest,
            "effect_closure_digest": command.effect_closure_digest,
            "authority_closure_digest": command.authority_closure_digest,
            "resource_closure_digest": command.resource_closure_digest,
        }
        existing_plan = _one_mapping(
            self.connection.execute(
                select(plans).where(
                    plans.c.project_key == project_key,
                    plans.c.plan_id == command.plan_id,
                )
            )
        )
        if existing_plan is not None and any(
            existing_plan[field] != value for field, value in plan_values.items()
        ):
            raise ExactBindingConflict("runtime Plan ref identity was rebound")
        if existing_plan is None:
            self.connection.execute(
                insert(plans).values(
                    **plan_values,
                    created_at=now,
                    updated_at=now,
                )
            )
        runs = _table("runtime_runs")
        locked = self._lock_run(command.run_id)
        if (
            int(locked["revision"]) != command.expected_run_revision
            or locked["program_id"] != command.program_id
            or locked["program_digest"] != command.program_digest
            or locked["state"] != "COMPILING"
        ):
            raise StaleRevisionError("attach Plan run binding/revision CAS failed")
        seq = int(locked["next_event_seq"])
        result = self.connection.execute(
            update(runs)
            .where(
                runs.c.project_key == project_key,
                runs.c.run_id == command.run_id,
                runs.c.revision == command.expected_run_revision,
                runs.c.state == "COMPILING",
            )
            .values(
                plan_id=command.plan_id,
                plan_digest=command.plan_digest,
                revision=command.expected_run_revision + 1,
                next_event_seq=seq + 1,
                updated_at=now,
            )
        )
        _require_one(result, "attach Plan run CAS failed")
        self.connection.execute(
            insert(_table("runtime_events")).values(
                project_key=project_key,
                run_id=command.run_id,
                seq=seq,
                event_type="PlanCompiled",
                schema_version="mrw.runtime.event.plan_compiled.v1",
                event_metadata_json={
                    "plan_id": command.plan_id,
                    "plan_digest": command.plan_digest,
                },
                authority_digest=command.qualify_work.authority_digest,
                created_at=now,
                updated_at=now,
            )
        )
        self.connection.execute(
            insert(_table("runtime_work_items")).values(
                **_assignment_values(command.qualify_work, due_at=command.due_at),
                created_at=now,
                updated_at=now,
            )
        )
        return {
            **locked,
            "plan_id": command.plan_id,
            "plan_digest": command.plan_digest,
            "revision": command.expected_run_revision + 1,
        }

    def activate_qualification(
        self, command: ActivateQualification
    ) -> Mapping[str, Any]:
        """Bind a persisted QualifiedPlan to its run and reduce run readiness."""

        binding = command.binding
        project_key = _scope_key(self.scope)
        if binding.project_key != project_key or binding.run_id != command.run_id:
            raise ExactBindingConflict("qualification activation scope/run mismatch")
        qualifications = _table("runtime_qualifications")
        qualification = _one_mapping(
            self.connection.execute(
                select(qualifications)
                .where(
                    qualifications.c.project_key == project_key,
                    qualifications.c.qualification_id == binding.qualification_id,
                )
                .with_for_update()
            )
        )
        if qualification is None:
            raise RecordNotFound(f"qualification not found: {binding.qualification_id}")
        persisted = validate_qualification_row(qualification)
        if (
            persisted.qualification_binding_digest
            != binding.qualification_binding_digest
        ):
            raise ExactBindingConflict("persisted qualification exact binding drift")

        run = self._lock_run(command.run_id)
        if (
            int(run["revision"]) != command.expected_run_revision
            or run["state"] != "COMPILING"
            or run["plan_id"] != binding.plan_id
            or run["plan_digest"] != binding.plan_digest
            or run["qualification_digest"] is not None
        ):
            raise StaleRevisionError("qualification activation run CAS failed")
        current = RunSnapshot(
            command.run_id,
            RunState.COMPILING,
            revision=command.expected_run_revision,
        )
        if binding.decision == "QUALIFIED":
            target = RunState.READY
            reducer_event = RunEvent.PLAN_COMPILED
        elif binding.decision == "AWAITING_APPROVAL":
            target = RunState.AWAITING_APPROVAL
            reducer_event = RunEvent.PLAN_COMPILED
        else:
            target = RunState.FAILED
            reducer_event = RunEvent.REQUIRED_STEP_FAILED
        reduced = reduce_run_event(current, reducer_event, target, guard=True)
        seq = int(run["next_event_seq"])
        now = _utcnow()
        runs = _table("runtime_runs")
        _require_one(
            self.connection.execute(
                update(runs)
                .where(
                    runs.c.project_key == project_key,
                    runs.c.run_id == command.run_id,
                    runs.c.revision == command.expected_run_revision,
                    runs.c.state == "COMPILING",
                    runs.c.plan_id == binding.plan_id,
                    runs.c.plan_digest == binding.plan_digest,
                    runs.c.qualification_digest.is_(None),
                )
                .values(
                    state=reduced.state.value,
                    qualification_digest=binding.qualified_plan.qualification_digest,
                    revision=reduced.revision,
                    next_event_seq=seq + 1,
                    finished_at=(now if reduced.state is RunState.FAILED else None),
                    updated_at=now,
                )
            ),
            "qualification activation run CAS failed",
        )
        self.connection.execute(
            insert(_table("runtime_events")).values(
                project_key=project_key,
                run_id=command.run_id,
                seq=seq,
                event_type="QualificationActivated",
                schema_version="mrw.runtime.event.qualification_activated.v1",
                event_metadata_json={
                    "qualification_id": binding.qualification_id,
                    "qualification_digest": binding.qualified_plan.qualification_digest,
                    "decision": binding.decision,
                    "reducer_event_code": reducer_event.value,
                },
                authority_digest=binding.authority_context_digest,
                created_at=now,
                updated_at=now,
            )
        )
        return {
            **run,
            "state": reduced.state.value,
            "qualification_digest": binding.qualified_plan.qualification_digest,
            "revision": reduced.revision,
            "next_event_seq": seq + 1,
        }

    def start_claim(
        self, claimed: ClaimedLifecycle, *, observed_at: datetime | None = None
    ) -> None:
        now = observed_at or _utcnow()
        rows = self._lock_claimed(claimed)
        run, step, work, attempt, reservation = rows
        if int(run["revision"]) != claimed.expected_run_revision:
            raise StaleRevisionError("claim start run revision drift")
        assignment = validate_runtime_assignment_row(work)
        claimed.claim.validate_against(assignment)
        _require_claim_rows(claimed, step, work, attempt, reservation, started=False)

        reduced = reduce_step(
            StepSnapshot(
                claimed.step_id,
                StepState(str(step["state"])),
                EffectDisposition(str(attempt["disposition"])),
                revision=int(step["revision"]),
            ),
            StepEvent.EFFECT_STARTED,
            StepState.RUNNING,
            guard=True,
        )
        _require_one(
            self.connection.execute(
                update(_table("runtime_effect_attempts"))
                .where(
                    _table("runtime_effect_attempts").c.project_key
                    == _scope_key(self.scope),
                    _table("runtime_effect_attempts").c.attempt_id
                    == claimed.attempt_id,
                    _table("runtime_effect_attempts").c.revision
                    == claimed.expected_attempt_revision,
                    _table("runtime_effect_attempts").c.disposition == "NOT_STARTED",
                    _table("runtime_effect_attempts").c.claim_binding_digest
                    == claimed.claim.binding_digest,
                )
                .values(
                    disposition="IN_FLIGHT",
                    started_at=now,
                    revision=claimed.expected_attempt_revision + 1,
                    updated_at=now,
                )
            ),
            "effect attempt start CAS failed",
        )
        self._update_step(
            claimed,
            expected_state="CLAIMED",
            target_state=reduced.state.value,
            expected_revision=claimed.expected_step_revision,
            now=now,
            started=True,
        )
        self._touch_work(
            claimed, expected_revision=claimed.expected_work_revision, now=now
        )
        run_state = str(run["state"])
        target_run_state = run_state
        if run_state == RunState.READY.value:
            target_run_state = reduce_run_event(
                RunSnapshot(claimed.run_id, RunState.READY, int(run["revision"])),
                RunEvent.FIRST_REQUIRED_STEP_READY,
                RunState.RUNNING,
                guard=True,
            ).state.value
        elif run_state == RunState.WAITING.value:
            target_run_state = reduce_run_event(
                RunSnapshot(claimed.run_id, RunState.WAITING, int(run["revision"])),
                RunEvent.REQUIRED_STEP_RUNNABLE,
                RunState.RUNNING,
                guard=True,
            ).state.value
        self._append_event_and_run(
            claimed.run_id,
            run,
            target_run_state=target_run_state,
            event_type="EffectStarted",
            schema_version="mrw.runtime.event.effect_started.v1",
            step_id=claimed.step_id,
            attempt_id=claimed.attempt_id,
            authority_digest=claimed.claim.authorization_digest,
            metadata={"work_item_id": claimed.work_item_id},
            now=now,
        )

    def commit_outcome(self, outcome: TerminalOutcome) -> None:
        now = outcome.observed_at or _utcnow()
        claimed = outcome.claimed
        run, step, work, attempt, reservation = self._lock_claimed(claimed)
        if int(run["revision"]) != claimed.expected_run_revision:
            raise StaleRevisionError("terminal run revision drift")
        assignment = validate_runtime_assignment_row(work)
        claimed.claim.validate_against(assignment)
        _require_claim_rows(claimed, step, work, attempt, reservation, started=True)
        self._terminal_authority.require_current(
            scope=self.scope,
            assignment=assignment,
            authorization_digest=claimed.claim.authorization_digest,
            observed_at=now,
        )
        if outcome.authority_digest != attempt["authorization_digest"]:
            raise ExactBindingConflict("terminal outcome authority binding drift")
        if outcome.kind is EffectTerminalKind.FAILED:
            assert outcome.failure_ref is not None
            assert outcome.failure_digest is not None
            self._terminal_failures.verify_exact(
                self.scope,
                assignment=assignment,
                claim=claimed.claim,
                failure_ref=outcome.failure_ref,
                failure_digest=outcome.failure_digest,
            )

        if (
            outcome.step_event is None
            or outcome.target_step_state is None
            or outcome.event_type is None
            or outcome.event_schema_version is None
        ):
            raise ExactBindingConflict(
                "terminal mutation lacks emitter-owned typed step event"
            )
        reduced = reduce_step(
            StepSnapshot(
                claimed.step_id,
                StepState(str(step["state"])),
                EffectDisposition(str(attempt["disposition"])),
                revision=int(step["revision"]),
            ),
            outcome.step_event,
            outcome.target_step_state,
            guard=True,
        )
        if reduced.effect_disposition.value != outcome.kind.value:
            raise ExactBindingConflict(
                "reducer terminal disposition differs from outcome"
            )

        attempts = _table("runtime_effect_attempts")
        attempt_values: dict[str, object] = {
            "disposition": reduced.effect_disposition.value,
            "receipt_ref": outcome.receipt_ref,
            "receipt_digest": outcome.receipt_digest,
            "failure_ref": outcome.failure_ref,
            "failure_digest": outcome.failure_digest,
            "finished_at": now,
            "revision": claimed.expected_attempt_revision + 1,
            "updated_at": now,
        }
        _require_one(
            self.connection.execute(
                update(attempts)
                .where(
                    attempts.c.project_key == _scope_key(self.scope),
                    attempts.c.attempt_id == claimed.attempt_id,
                    attempts.c.revision == claimed.expected_attempt_revision,
                    attempts.c.disposition == "IN_FLIGHT",
                    attempts.c.claim_binding_digest == claimed.claim.binding_digest,
                )
                .values(**attempt_values)
            ),
            "terminal effect attempt CAS failed",
        )
        self._update_step(
            claimed,
            expected_state=str(step["state"]),
            target_state=reduced.state.value,
            expected_revision=claimed.expected_step_revision,
            now=now,
            output_digest=outcome.output_digest,
            failure_digest=outcome.failure_digest,
            terminal=True,
        )
        self._terminal_work(
            claimed,
            expected_revision=claimed.expected_work_revision,
            state=(
                "FAILED" if outcome.kind is EffectTerminalKind.FAILED else "COMPLETED"
            ),
            failure_ref=outcome.failure_ref,
            now=now,
        )
        self._terminal_reservation(
            claimed,
            expected_revision=claimed.expected_reservation_revision,
            reason=f"SEMANTIC_{outcome.kind.value}",
            now=now,
        )
        if outcome.staged_artifact_id is not None:
            self._terminal_staged(outcome, now=now)

        run_state = str(run["state"])
        failure_policy_decision = None
        if outcome.kind is EffectTerminalKind.FAILED:
            failure_policy_decision = self._failure_policy.load_decision(
                claimed.run_id,
                claimed.step_id,
            )
            if getattr(failure_policy_decision, "emit_required_step_failed", False):
                target_run = reduce_run_event(
                    RunSnapshot(
                        claimed.run_id,
                        RunState(run_state),
                        int(run["revision"]),
                    ),
                    RunEvent.REQUIRED_STEP_FAILED,
                    RunState.FAILED,
                    guard=True,
                ).state.value
            else:
                target_run = run_state
        elif (
            outcome.kind is EffectTerminalKind.OUTCOME_UNKNOWN
            and run_state == "RUNNING"
        ):
            target_run = reduce_run_event(
                RunSnapshot(claimed.run_id, RunState.RUNNING, int(run["revision"])),
                RunEvent.RUN_WAITING_DERIVED,
                RunState.RECONCILING,
                guard=True,
            ).state.value
            self._activate_reconcile(
                claimed.attempt_id,
                expected_step_revision=reduced.revision,
                now=now,
            )
        else:
            target_run = run_state
        self._append_event_and_run(
            claimed.run_id,
            run,
            target_run_state=target_run,
            event_type=outcome.event_type,
            schema_version=outcome.event_schema_version,
            step_id=claimed.step_id,
            attempt_id=claimed.attempt_id,
            authority_digest=outcome.authority_digest,
            metadata={
                "work_item_id": claimed.work_item_id,
                "status": outcome.kind.value,
                "failure_policy_decision_digest": (
                    None
                    if failure_policy_decision is None
                    else failure_policy_decision.decision_digest
                ),
                "required_step_failed": (
                    False
                    if failure_policy_decision is None
                    else getattr(
                        failure_policy_decision,
                        "emit_required_step_failed",
                        False,
                    )
                ),
            },
            payload_ref=outcome.payload_ref,
            payload_digest=outcome.payload_digest,
            now=now,
        )

    def begin_commit(
        self,
        claimed: ClaimedLifecycle,
        *,
        observed_at: datetime | None = None,
    ) -> ClaimedLifecycle:
        """Advance one VERIFY_ADMIT claim to COMMITTING in this caller UoW."""

        now = observed_at or _utcnow()
        run, step, work, attempt, reservation = self._lock_claimed(claimed)
        if int(run["revision"]) != claimed.expected_run_revision:
            raise StaleRevisionError("commit preparation run revision drift")
        assignment = validate_runtime_assignment_row(work)
        claimed.claim.validate_against(assignment)
        if assignment.assignment_kind is not AssignmentKind.VERIFY_ADMIT:
            raise ExactBindingConflict("commit preparation requires VERIFY_ADMIT")
        _require_claim_rows(claimed, step, work, attempt, reservation, started=True)
        if str(step["state"]) != StepState.RUNNING.value:
            raise ExactBindingConflict("commit preparation requires RUNNING step")

        reduced = reduce_step(
            StepSnapshot(
                claimed.step_id,
                StepState.RUNNING,
                EffectDisposition(str(attempt["disposition"])),
                revision=int(step["revision"]),
            ),
            StepEvent.COMMIT_PREPARED,
            StepState.COMMITTING,
            guard=True,
        )
        self._update_step(
            claimed,
            expected_state=StepState.RUNNING.value,
            target_state=reduced.state.value,
            expected_revision=claimed.expected_step_revision,
            now=now,
        )
        self._touch_work(
            claimed,
            expected_revision=claimed.expected_work_revision,
            now=now,
        )
        self._append_event_and_run(
            claimed.run_id,
            run,
            target_run_state=str(run["state"]),
            event_type=StepEvent.COMMIT_PREPARED.value,
            schema_version="mrw.runtime.event.commit_prepared.v1",
            step_id=claimed.step_id,
            attempt_id=claimed.attempt_id,
            authority_digest=claimed.claim.authorization_digest,
            metadata={"work_item_id": claimed.work_item_id},
            now=now,
        )
        return replace(
            claimed,
            expected_run_revision=claimed.expected_run_revision + 1,
            expected_step_revision=claimed.expected_step_revision + 1,
            expected_work_revision=claimed.expected_work_revision + 1,
        )

    def complete_if_satisfied(
        self,
        run_id: str,
        *,
        required_step_ids: frozenset[str],
        authority_digest: str,
        observed_at: datetime | None = None,
    ) -> bool:
        """Derive the sole ordinary RUNNING -> COMPLETED transition."""

        if not required_step_ids:
            raise ExactBindingConflict("run completion requires explicit steps")
        now = observed_at or _utcnow()
        runs = _table("runtime_runs")
        run = _one_mapping(
            self.connection.execute(
                select(runs)
                .where(
                    runs.c.project_key == _scope_key(self.scope),
                    runs.c.run_id == run_id,
                )
                .with_for_update()
            )
        )
        if run is None:
            raise RecordNotFound(f"runtime run not found: {run_id}")
        if run["state"] == RunState.COMPLETED.value:
            return True

        steps_table = _table("runtime_steps")
        rows = tuple(
            self.connection.execute(
                select(steps_table)
                .where(
                    steps_table.c.project_key == _scope_key(self.scope),
                    steps_table.c.run_id == run_id,
                    steps_table.c.step_id.in_(tuple(sorted(required_step_ids))),
                )
                .with_for_update(read=True)
            ).mappings()
        )
        if {str(row["step_id"]) for row in rows} != required_step_ids:
            raise ExactBindingConflict("run completion step closure is incomplete")
        snapshots = tuple(
            StepSnapshot(
                step_id=str(row["step_id"]),
                state=StepState(str(row["state"])),
                effect_disposition=(
                    EffectDisposition.SUCCEEDED
                    if row["state"] == StepState.SUCCEEDED.value
                    else EffectDisposition.NOT_STARTED
                ),
                revision=int(row["revision"]),
            )
            for row in rows
        )
        policy = CompletionPolicy(required_step_ids=required_step_ids)
        if not completion_satisfied(snapshots, policy):
            return False
        if run["state"] != RunState.RUNNING.value:
            raise ExactBindingConflict(
                "satisfied run completion requires RUNNING source state"
            )
        reduced = reduce_run_completion(
            RunSnapshot(run_id, RunState.RUNNING, int(run["revision"])),
            snapshots,
            policy,
        )
        seq = int(run["next_event_seq"])
        updated = self.connection.execute(
            update(runs)
            .where(
                runs.c.project_key == _scope_key(self.scope),
                runs.c.run_id == run_id,
                runs.c.state == RunState.RUNNING.value,
                runs.c.revision == run["revision"],
                runs.c.next_event_seq == seq,
            )
            .values(
                state=reduced.state.value,
                revision=reduced.revision,
                next_event_seq=seq + 1,
                finished_at=now,
                updated_at=now,
            )
        )
        if getattr(updated, "rowcount", None) != 1:
            raise StaleRevisionError("run completion CAS failed")
        self.connection.execute(
            insert(_table("runtime_events")).values(
                project_key=_scope_key(self.scope),
                run_id=run_id,
                seq=seq,
                event_type=RunEvent.RUN_COMPLETION_DERIVED.value,
                schema_version="mrw.runtime.event.run_completion_derived.v1",
                step_id=None,
                attempt_id=None,
                event_metadata_json={
                    "required_step_ids": sorted(required_step_ids),
                    "completion_policy": "ALL_EFFECT_ADMISSION_STEPS_SUCCEEDED",
                },
                payload_ref=None,
                payload_digest=None,
                authority_digest=authority_digest,
                created_at=now,
                updated_at=now,
            )
        )
        return True

    def commit_succeeded(self, outcome: TerminalOutcome) -> None:
        if outcome.kind is not EffectTerminalKind.SUCCEEDED:
            raise ValueError("commit_succeeded requires SUCCEEDED outcome")
        self.commit_outcome(outcome)

    def commit_failed(self, outcome: TerminalOutcome) -> None:
        if outcome.kind is not EffectTerminalKind.FAILED:
            raise ValueError("commit_failed requires FAILED outcome")
        self.commit_outcome(outcome)

    def commit_outcome_unknown(self, outcome: TerminalOutcome) -> None:
        if outcome.kind is not EffectTerminalKind.OUTCOME_UNKNOWN:
            raise ValueError("commit_outcome_unknown requires OUTCOME_UNKNOWN outcome")
        self.commit_outcome(outcome)

    def finalize_admission(self, outcome: TerminalOutcome) -> None:
        if (
            outcome.kind is not EffectTerminalKind.SUCCEEDED
            or outcome.staged_artifact_id is None
            or not outcome.admit_staged
        ):
            raise ValueError("admission finalization requires admitted staged success")
        self.commit_outcome(outcome)

    def _lock_run(self, run_id: str) -> Mapping[str, Any]:
        table = _table("runtime_runs")
        row = _one_mapping(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.run_id == run_id,
                )
                .with_for_update()
            )
        )
        if row is None:
            raise RecordNotFound(f"runtime run not found: {run_id}")
        return row

    def _lock_claimed(self, claimed: ClaimedLifecycle) -> tuple[Mapping[str, Any], ...]:
        project_key = _scope_key(self.scope)
        if claimed.claim.lease_expires_at <= _utcnow():
            raise ExactBindingConflict("claim lease has expired")
        run = self._lock_run(claimed.run_id)
        lookups = (
            ("runtime_steps", ("run_id", claimed.run_id), ("step_id", claimed.step_id)),
            ("runtime_work_items", ("work_item_id", claimed.work_item_id)),
            ("runtime_effect_attempts", ("attempt_id", claimed.attempt_id)),
            (
                "runtime_resource_reservations",
                ("reservation_id", claimed.reservation_id),
            ),
        )
        rows: list[Mapping[str, Any]] = [run]
        for name, *pairs in lookups:
            table = _table(name)
            statement = select(table).where(table.c.project_key == project_key)
            for column, value in pairs:
                statement = statement.where(getattr(table.c, column) == value)
            row = _one_mapping(self.connection.execute(statement.with_for_update()))
            if row is None:
                raise RecordNotFound(f"claimed lifecycle row not found: {name}")
            rows.append(row)
        return tuple(rows)

    def _update_step(
        self,
        claimed: ClaimedLifecycle,
        *,
        expected_state: str,
        target_state: str,
        expected_revision: int,
        now: datetime,
        started: bool = False,
        terminal: bool = False,
        output_digest: str | None = None,
        failure_digest: str | None = None,
    ) -> None:
        table = _table("runtime_steps")
        values: dict[str, object] = {
            "state": target_state,
            "revision": expected_revision + 1,
            "updated_at": now,
        }
        if started:
            values["started_at"] = now
        if terminal:
            values.update(
                output_digest=output_digest,
                failure_digest=failure_digest,
                finished_at=now,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
            )
        _require_one(
            self.connection.execute(
                update(table)
                .where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.run_id == claimed.run_id,
                    table.c.step_id == claimed.step_id,
                    table.c.state == expected_state,
                    table.c.revision == expected_revision,
                    table.c.lease_token == claimed.claim.lease_token,
                )
                .values(**values)
            ),
            "step lifecycle CAS failed",
        )

    def _touch_work(
        self, claimed: ClaimedLifecycle, *, expected_revision: int, now: datetime
    ) -> None:
        table = _table("runtime_work_items")
        _require_one(
            self.connection.execute(
                update(table)
                .where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.work_item_id == claimed.work_item_id,
                    table.c.state == "CLAIMED",
                    table.c.revision == expected_revision,
                    table.c.lease_token == claimed.claim.lease_token,
                    table.c.claim_binding_digest == claimed.claim.binding_digest,
                )
                .values(revision=expected_revision + 1, updated_at=now)
            ),
            "work-item start CAS failed",
        )

    def _terminal_work(
        self,
        claimed: ClaimedLifecycle,
        *,
        expected_revision: int,
        state: str,
        failure_ref: str | None,
        now: datetime,
    ) -> None:
        table = _table("runtime_work_items")
        _require_one(
            self.connection.execute(
                update(table)
                .where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.work_item_id == claimed.work_item_id,
                    table.c.state == "CLAIMED",
                    table.c.revision == expected_revision,
                    table.c.lease_token == claimed.claim.lease_token,
                    table.c.claim_binding_digest == claimed.claim.binding_digest,
                )
                .values(
                    state=state,
                    wait_reason=None,
                    lease_token=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    last_failure_ref=failure_ref,
                    revision=expected_revision + 1,
                    updated_at=now,
                )
            ),
            "terminal work-item CAS failed",
        )

    def _terminal_reservation(
        self,
        claimed: ClaimedLifecycle,
        *,
        expected_revision: int,
        reason: str,
        now: datetime,
    ) -> None:
        table = _table("runtime_resource_reservations")
        _require_one(
            self.connection.execute(
                update(table)
                .where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.reservation_id == claimed.reservation_id,
                    table.c.attempt_id == claimed.attempt_id,
                    table.c.state == "ACTIVE",
                    table.c.revision == expected_revision,
                    table.c.lease_token == claimed.claim.lease_token,
                )
                .values(
                    state="RELEASED",
                    released_at=now,
                    release_reason=reason,
                    revision=expected_revision + 1,
                    updated_at=now,
                )
            ),
            "terminal resource reservation CAS failed",
        )

    def _terminal_staged(self, outcome: TerminalOutcome, *, now: datetime) -> None:
        table = _table("runtime_staged_artifacts")
        assert outcome.staged_artifact_id is not None
        assert outcome.expected_staged_revision is not None
        expected_state = "VERIFIED" if outcome.admit_staged else "STAGED"
        target_state = "ADMITTED" if outcome.admit_staged else "VERIFIED"
        _require_one(
            self.connection.execute(
                update(table)
                .where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.artifact_id == outcome.staged_artifact_id,
                    table.c.run_id == outcome.claimed.run_id,
                    table.c.revision == outcome.expected_staged_revision,
                    table.c.state == expected_state,
                )
                .values(
                    state=target_state,
                    receipt_ref=outcome.receipt_ref,
                    revision=outcome.expected_staged_revision + 1,
                    updated_at=now,
                )
            ),
            "terminal staged artifact CAS failed",
        )

    def _activate_reconcile(
        self,
        attempt_id: str,
        *,
        expected_step_revision: int,
        now: datetime,
    ) -> None:
        table = _table("runtime_work_items")
        row = _one_mapping(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.assignment_kind == "RECONCILE",
                    table.c.reconciliation_attempt_id == attempt_id,
                    table.c.state == "PENDING",
                )
                .with_for_update()
            )
        )
        if row is None:
            raise ExactBindingConflict("OUTCOME_UNKNOWN lacks durable reconcile work")
        assignment = validate_runtime_assignment_row(row)
        if assignment.expected_step_revision != expected_step_revision:
            raise ExactBindingConflict(
                "durable reconcile assignment does not bind the reduced step revision"
            )
        _require_one(
            self.connection.execute(
                update(table)
                .where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.work_item_id == row["work_item_id"],
                    table.c.state == "PENDING",
                    table.c.revision == row["revision"],
                )
                .values(
                    state="READY",
                    due_at=now,
                    revision=int(row["revision"]) + 1,
                    updated_at=now,
                )
            ),
            "reconcile activation CAS failed",
        )

    def _append_event_and_run(
        self,
        run_id: str,
        run: Mapping[str, Any],
        *,
        target_run_state: str,
        event_type: str,
        schema_version: str,
        step_id: str,
        attempt_id: str,
        authority_digest: str,
        metadata: Mapping[str, object],
        now: datetime,
        payload_ref: str | None = None,
        payload_digest: str | None = None,
    ) -> None:
        runs = _table("runtime_runs")
        seq = int(run["next_event_seq"])
        revision = int(run["revision"])
        event_metadata = dict(metadata)
        required_step_failed = event_metadata.get("required_step_failed") is True
        if required_step_failed:
            if event_type != StepEvent.EFFECT_FAILED.value:
                raise ExactBindingConflict(
                    "RequiredStepFailed must follow an exact EffectFailed event"
                )
            policy_digest = event_metadata.get("failure_policy_decision_digest")
            if not isinstance(policy_digest, str) or len(policy_digest) != 64:
                raise ExactBindingConflict(
                    "required failure lacks persisted policy decision digest"
                )
            event_metadata["required_step_failed_event_revision"] = seq + 1
        event_count = 2 if required_step_failed else 1
        _require_one(
            self.connection.execute(
                update(runs)
                .where(
                    runs.c.project_key == _scope_key(self.scope),
                    runs.c.run_id == run_id,
                    runs.c.revision == revision,
                    runs.c.next_event_seq == seq,
                    runs.c.state == run["state"],
                )
                .values(
                    state=target_run_state,
                    revision=revision + 1,
                    next_event_seq=seq + event_count,
                    finished_at=(
                        now
                        if target_run_state in {"FAILED", "CANCELLED", "SUPERSEDED"}
                        else None
                    ),
                    updated_at=now,
                )
            ),
            "run/event allocator CAS failed",
        )
        self.connection.execute(
            insert(_table("runtime_events")).values(
                project_key=_scope_key(self.scope),
                run_id=run_id,
                seq=seq,
                event_type=event_type,
                schema_version=schema_version,
                step_id=step_id,
                attempt_id=attempt_id,
                event_metadata_json=event_metadata,
                payload_ref=payload_ref,
                payload_digest=payload_digest,
                authority_digest=authority_digest,
                created_at=now,
                updated_at=now,
            )
        )
        if required_step_failed:
            source_event_digest = runtime_event_digest(
                project_key=_scope_key(self.scope),
                run_id=run_id,
                run_incarnation=str(run["incarnation"]),
                seq=seq,
                event_type=event_type,
                schema_version=schema_version,
                step_id=step_id,
                attempt_id=attempt_id,
                metadata=event_metadata,
                payload_ref=payload_ref,
                payload_digest=payload_digest,
                authority_digest=authority_digest,
            )
            self.connection.execute(
                insert(_table("runtime_events")).values(
                    project_key=_scope_key(self.scope),
                    run_id=run_id,
                    seq=seq + 1,
                    event_type=RunEvent.REQUIRED_STEP_FAILED.value,
                    schema_version="mrw.runtime.event.required_step_failed.v1",
                    step_id=step_id,
                    attempt_id=attempt_id,
                    event_metadata_json={
                        "status": "FAILED",
                        "source_revision": seq,
                        "source_event_digest": source_event_digest,
                        "failure_policy_decision_digest": event_metadata[
                            "failure_policy_decision_digest"
                        ],
                    },
                    payload_ref=None,
                    payload_digest=None,
                    authority_digest=authority_digest,
                    created_at=now,
                    updated_at=now,
                )
            )


def _assignment_values(
    envelope: AssignmentEnvelope, *, due_at: datetime
) -> dict[str, object]:
    assignment = envelope.assignment
    handler = assignment.handler_binding
    interpreter_profile_digest = (
        handler.interpreter_profile_digest
        if isinstance(handler, (InterpreterBinding, RecoveryBinding))
        else None
    )
    values: dict[str, object] = {
        "work_item_id": assignment.work_item_id,
        "project_key": assignment.project_key,
        "run_id": assignment.run_id,
        "step_id": assignment.step_id,
        "assignment_kind": assignment.assignment_kind.value,
        "capability_id": assignment.capability_id,
        "operation_contract_digest": assignment.operation_contract_digest,
        "assignment_digest": assignment.assignment_digest,
        "assignment_binding_json": assignment.model_dump(mode="json"),
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
        "required_node_profile_selector": envelope.required_node_profile_selector,
        "program_digest": assignment.program_digest,
        "plan_digest": assignment.plan_digest,
        "qualification_digest": envelope.qualification_digest,
        "expected_step_revision": assignment.expected_step_revision,
        "reconciliation_attempt_id": assignment.reconciliation_attempt_id,
        "payload_ref": assignment.payload_ref,
        "payload_digest": assignment.payload_digest,
        "authority_digest": envelope.authority_digest,
        "resource_policy_digest": envelope.resource_policy_digest,
        "resource_policy_epoch": assignment.resource_policy_epoch,
        "queue_eligibility_digest": assignment.queue_eligibility_digest,
        "resource_class": envelope.resource_class,
        "resource_units": envelope.resource_units,
        "concurrency_key": envelope.concurrency_key,
        "provider_key": envelope.provider_key,
        "recovery_handler_binding_ref": (
            None
            if envelope.recovery_binding is None
            else f"handler-binding:sha256:{envelope.recovery_binding.binding_digest}"
        ),
        "recovery_handler_binding_digest": (
            None
            if envelope.recovery_binding is None
            else envelope.recovery_binding.binding_digest
        ),
        "recovery_binding_json": (
            None
            if envelope.recovery_binding is None
            else envelope.recovery_binding.model_dump(mode="json")
        ),
        "authoritative_readback_profile_ref": envelope.authoritative_readback_profile_ref,
        "delivery_intent_ref": envelope.delivery_intent_ref,
        "fairness_key": envelope.fairness_key,
        "state": "READY",
        "wait_reason": None,
        "declared_priority": envelope.declared_priority,
        "enqueued_at": due_at,
        "due_at": due_at,
        "attempt_count": 0,
        "revision": 0,
        "deadline_at": assignment.deadline_at,
    }
    if isinstance(handler, ProjectorBinding):
        values.update(
            source_ref=handler.source_ref,
            source_digest=handler.source_digest,
            declared_loss_profile_ref=handler.declared_loss_profile_ref,
        )
    if isinstance(handler, MaterializerBinding):
        values.update(
            predecessor_plan_digest=handler.predecessor_plan_digest,
            source_value_digest=handler.source_value_digest,
            target_domain_contract_snapshot_digest=handler.target_domain_contract_snapshot_digest,
        )
    validate_runtime_assignment_row(values)
    return values


def _require_claim_rows(
    claimed: ClaimedLifecycle,
    step: Mapping[str, Any],
    work: Mapping[str, Any],
    attempt: Mapping[str, Any],
    reservation: Mapping[str, Any],
    *,
    started: bool,
) -> None:
    expected_disposition = "IN_FLIGHT" if started else "NOT_STARTED"
    revisions = (
        (step, claimed.expected_step_revision),
        (work, claimed.expected_work_revision),
        (attempt, claimed.expected_attempt_revision),
        (reservation, claimed.expected_reservation_revision),
    )
    if any(int(row["revision"]) != expected for row, expected in revisions):
        raise StaleRevisionError("claimed lifecycle expected revision drift")
    if (
        step["state"] not in ({"RUNNING", "COMMITTING"} if started else {"CLAIMED"})
        or work["state"] != "CLAIMED"
        or attempt["disposition"] != expected_disposition
        or reservation["state"] != "ACTIVE"
        or step["lease_token"] != claimed.claim.lease_token
        or work["lease_token"] != claimed.claim.lease_token
        or reservation["lease_token"] != claimed.claim.lease_token
        or work["claim_binding_digest"] != claimed.claim.binding_digest
        or attempt["claim_binding_digest"] != claimed.claim.binding_digest
        or attempt["attempt_id"] != claimed.attempt_id
        or reservation["attempt_id"] != claimed.attempt_id
        or claimed.claim.execution_reservation_ref != claimed.reservation_id
        or reservation["reservation_digest"]
        != claimed.claim.execution_reservation_digest
        or attempt["authorization_digest"] != claimed.claim.authorization_digest
        or attempt["assignment_digest"] != claimed.claim.assignment_digest
        or attempt["handler_binding_digest"] != claimed.claim.handler_binding_digest
        or attempt["handler_realization_digest"]
        != claimed.claim.handler_realization_digest
        or attempt["run_id"] != claimed.run_id
        or attempt["step_id"] != claimed.step_id
        or reservation["run_id"] != claimed.run_id
        or reservation["step_id"] != claimed.step_id
        or reservation["work_item_id"] != claimed.work_item_id
    ):
        raise ExactBindingConflict("claimed lifecycle exact binding drift")


def _require_one(result: Any, message: str) -> None:
    if getattr(result, "rowcount", None) != 1:
        raise StaleRevisionError(message)


__all__ = [
    "ActivateQualification",
    "AssignmentEnvelope",
    "AttachPlan",
    "ClaimedLifecycle",
    "EffectTerminalKind",
    "RuntimeLifecycleRepository",
    "SubmitRun",
    "TerminalOutcome",
]
