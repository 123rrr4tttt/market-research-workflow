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
from sqlalchemy.engine import Connection, RowMapping

from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
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
from app.successor_runtime.runtime.replay import (
    ReplayEvent, active_child_failure_decision_digest, replay_runtime_events, runtime_event_digest,
)
from app.successor_runtime.runtime.transitions import (
    EffectDisposition,
    RunEvent,
    RunState,
    STEP_TRANSITIONS,
    StepEvent,
    StepState,
    TERMINAL_RUN_STATES,
    TERMINAL_STEP_STATES,
)
from app.successor_runtime.runtime.failure_policy import FailurePolicyDecision

from .failure_policy import PostgresFailurePolicyLoader
from .models import project_tables
from .runtime_failures import RuntimeFailureRepository
from .runtime_journal import (
    ExactBindingConflict,
    ExactQualificationBinding,
    RecordNotFound,
    RuntimeJournalRepository,
    StaleRevisionError,
    one_mapping,
    runtime_scope_key,
    runtime_table,
    utc_now,
    assignment_index_values,
    validate_authorization_row,
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
    compile_work: AssignmentEnvelope | None
    due_at: datetime
    execution_epoch: int = 0


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
    qualify_work: AssignmentEnvelope | None
    due_at: datetime
    compilation_authority_digest: str | None = None


@dataclass(frozen=True, slots=True)
class ActivateQualification:
    run_id: str
    expected_run_revision: int
    binding: ExactQualificationBinding


@dataclass(frozen=True, slots=True)
class RequestCancel:
    """Explicit cancellation of a live run, scoped by the caller's actor."""

    run_id: str
    expected_run_revision: int
    reason: str | None = None


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
    def load_decision(self, run_id: str, step_id: str) -> FailurePolicyDecision: ...


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

    def submit(self, command: SubmitRun) -> RowMapping:
        project_key = runtime_scope_key(self.scope)
        assignment = command.compile_work.assignment if command.compile_work else None
        if assignment is not None and (
            assignment.project_key != project_key
            or assignment.run_id != command.run_id
            or assignment.program_digest != command.program_digest
            or assignment.incarnation != command.incarnation
            or assignment.assignment_kind.value != "COMPILE"
        ):
            raise ExactBindingConflict("compile assignment differs from submitted run")
        programs = runtime_table("runtime_program_refs")
        existing_ref = one_mapping(
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
            now = utc_now()
            self.connection.execute(
                insert(programs).values(
                    **program_values, created_at=now, updated_at=now
                )
            )

        runs = runtime_table("runtime_runs")
        now = utc_now()
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
                execution_epoch=(
                    assignment.execution_epoch if assignment else command.execution_epoch
                ),
                incarnation=command.incarnation,
                submission_authority_digest=command.submission_authority_digest,
                qualification_digest=None,
                cancellation_requested=False,
                created_at=now,
                updated_at=now,
            )
        )
        events = runtime_table("runtime_events")
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
        if command.compile_work is not None:
            work_items = runtime_table("runtime_work_items")
            self.connection.execute(
                insert(work_items).values(
                    **assignment_values(command.compile_work, due_at=command.due_at),
                    created_at=now,
                    updated_at=now,
                )
            )
        row = one_mapping(
            self.connection.execute(
                select(runs).where(
                    runs.c.project_key == project_key, runs.c.run_id == command.run_id
                )
            )
        )
        assert row is not None
        return row

    def attach_plan(self, command: AttachPlan) -> Mapping[str, Any]:
        """Attach a compiled Plan, optionally enqueueing asynchronous qualification.

        A caller that compiles and qualifies on this transaction supplies its
        actual compilation authority and no work item. It must still persist
        and activate the exact qualification through the existing owner.
        """

        project_key = runtime_scope_key(self.scope)
        assignment = command.qualify_work.assignment if command.qualify_work else None
        if assignment is not None and (
            assignment.assignment_kind.value != "QUALIFY"
            or assignment.run_id != command.run_id
            or assignment.project_key != project_key
            or assignment.plan_digest != command.plan_digest
            or assignment.program_digest != command.program_digest
        ):
            raise ExactBindingConflict(
                "qualification assignment differs from exact Plan"
            )
        authority_digest = (
            command.qualify_work.authority_digest
            if command.qualify_work else command.compilation_authority_digest
        )
        if not authority_digest:
            raise ExactBindingConflict("compiled Plan requires explicit authority")
        plans = runtime_table("runtime_plan_refs")
        now = utc_now()
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
        existing_plan = one_mapping(
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
        runs = runtime_table("runtime_runs")
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
            insert(runtime_table("runtime_events")).values(
                project_key=project_key,
                run_id=command.run_id,
                seq=seq,
                event_type="PlanCompiled",
                schema_version="mrw.runtime.event.plan_compiled.v1",
                event_metadata_json={
                    "plan_id": command.plan_id,
                    "plan_digest": command.plan_digest,
                },
                authority_digest=authority_digest,
                created_at=now,
                updated_at=now,
            )
        )
        if command.qualify_work is not None:
            self.connection.execute(
                insert(runtime_table("runtime_work_items")).values(
                    **assignment_values(command.qualify_work, due_at=command.due_at),
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
        project_key = runtime_scope_key(self.scope)
        if binding.project_key != project_key or binding.run_id != command.run_id:
            raise ExactBindingConflict("qualification activation scope/run mismatch")
        qualifications = runtime_table("runtime_qualifications")
        qualification = one_mapping(
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
        now = utc_now()
        runs = runtime_table("runtime_runs")
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
            insert(runtime_table("runtime_events")).values(
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
        now = observed_at or utc_now()
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
                update(runtime_table("runtime_effect_attempts"))
                .where(
                    runtime_table("runtime_effect_attempts").c.project_key
                    == runtime_scope_key(self.scope),
                    runtime_table("runtime_effect_attempts").c.attempt_id
                    == claimed.attempt_id,
                    runtime_table("runtime_effect_attempts").c.revision
                    == claimed.expected_attempt_revision,
                    runtime_table("runtime_effect_attempts").c.disposition == "NOT_STARTED",
                    runtime_table("runtime_effect_attempts").c.claim_binding_digest
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
        now = outcome.observed_at or utc_now()
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

        attempts = runtime_table("runtime_effect_attempts")
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
                    attempts.c.project_key == runtime_scope_key(self.scope),
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
                    else failure_policy_decision.emit_required_step_failed
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

        now = observed_at or utc_now()
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
        journal_succeeded_step_ids: frozenset[str] = frozenset(),
        observed_at: datetime | None = None,
    ) -> bool:
        """Derive the sole ordinary RUNNING -> COMPLETED transition."""

        if not required_step_ids:
            raise ExactBindingConflict("run completion requires explicit steps")
        if not journal_succeeded_step_ids.issubset(required_step_ids):
            raise ExactBindingConflict("journal completion steps exceed required closure")
        now = observed_at or utc_now()
        runs = runtime_table("runtime_runs")
        run = one_mapping(
            self.connection.execute(
                select(runs)
                .where(
                    runs.c.project_key == runtime_scope_key(self.scope),
                    runs.c.run_id == run_id,
                )
                .with_for_update()
            )
        )
        if run is None:
            raise RecordNotFound(f"runtime run not found: {run_id}")
        if run["state"] == RunState.COMPLETED.value:
            return True

        if journal_succeeded_step_ids:
            events = runtime_table("runtime_events")
            rows = tuple(
                self.connection.execute(
                    select(events)
                    .where(
                        events.c.project_key == runtime_scope_key(self.scope),
                        events.c.run_id == run_id,
                        events.c.event_type == "ActiveChildrenSettled",
                    )
                    .with_for_update(read=True)
                ).mappings()
            )
            witnessed: set[str] = set()
            for row in rows:
                metadata = row["event_metadata_json"]
                step_id = metadata.get("source_step_id")
                if step_id not in journal_succeeded_step_ids:
                    continue
                if (
                    not isinstance(step_id, str)
                    or step_id in witnessed
                    or row["schema_version"]
                    != "mrw.runtime.event.active_children_settled.v1"
                    or row["payload_ref"] is None
                    or row["payload_digest"] is None
                    or metadata.get("result_digest") != row["payload_digest"]
                    or row["authority_digest"] != authority_digest
                ):
                    raise ExactBindingConflict(
                        "journal completion witness is not one exact settlement"
                    )
                witnessed.add(step_id)
            if witnessed != set(journal_succeeded_step_ids):
                raise ExactBindingConflict("journal completion witness is absent")

        steps_table = runtime_table("runtime_steps")
        persisted_step_ids = required_step_ids - journal_succeeded_step_ids
        rows = (
            tuple(
                self.connection.execute(
                    select(steps_table)
                    .where(
                        steps_table.c.project_key == runtime_scope_key(self.scope),
                        steps_table.c.run_id == run_id,
                        steps_table.c.step_id.in_(tuple(sorted(persisted_step_ids))),
                    )
                    .with_for_update(read=True)
                ).mappings()
            )
            if persisted_step_ids
            else ()
        )
        if frozenset(str(row["step_id"]) for row in rows) != persisted_step_ids:
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
        ) + tuple(
            StepSnapshot(
                step_id=step_id,
                state=StepState.SUCCEEDED,
                effect_disposition=EffectDisposition.SUCCEEDED,
                revision=0,
            )
            for step_id in sorted(journal_succeeded_step_ids)
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
                runs.c.project_key == runtime_scope_key(self.scope),
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
            insert(runtime_table("runtime_events")).values(
                project_key=runtime_scope_key(self.scope),
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

    def fail_active_child(
        self, *, parent_run_id: str, source_step_id: str, child_run_id: str,
        observed_at: datetime | None = None,
    ) -> None:
        """Propagate a journal-proven required child failure without a fake effect."""
        from .runtime_activation import (
            active_child_rows,
            require_program_plan_run,
            traversal_plan_step,
        )
        from .plans import PlanRepository
        from .programs import ProgramRepository

        now = observed_at or utc_now()
        journal = RuntimeJournalRepository(self.connection, self.scope)
        parent = dict(journal.load_run(parent_run_id, for_update=True))
        child = dict(journal.load_run(child_run_id, for_update=True))
        tables = project_tables(MetaData(), str(parent["resolved_schema"]))
        program = ProgramRepository(self.connection, tables).get(
            self.scope, str(parent["program_id"]), expected_digest=str(parent["program_digest"]))
        plan = PlanRepository(self.connection, tables).get(self.scope, str(parent["plan_digest"]))
        require_program_plan_run(program, plan, parent)
        traversal_plan_step(plan, source_step_id)
        events = runtime_table("runtime_events")

        def replay(run: Mapping[str, Any]) -> tuple[ReplayEvent, ...]:
            rows = self.connection.execute(select(events).where(
                events.c.project_key == runtime_scope_key(self.scope),
                events.c.run_id == run["run_id"],
            ).order_by(events.c.seq)).mappings().all()
            return tuple(
                ReplayEvent.from_public_row(row, run_incarnation=str(run["incarnation"]))
                for row in rows
            )

        parent_events, child_events = replay(parent), replay(child)
        parent_projection = replay_runtime_events(parent_events)
        child_projection = replay_runtime_events(child_events)
        if child["state"] != "FAILED" or child_projection.run_state is not RunState.FAILED:
            raise ExactBindingConflict("active child has no journal-proven runtime failure")
        causes = tuple(event for event in child_events if event.event_type == "RequiredStepFailed")
        if len(causes) != 1:
            raise ExactBindingConflict("active child failure cause is absent or ambiguous")
        cause = causes[0]
        if cause.step_id is not None:
            authz = runtime_table("runtime_step_authorizations")
            authority = one_mapping(self.connection.execute(select(authz).where(
                authz.c.project_key == runtime_scope_key(self.scope), authz.c.run_id == child_run_id,
                authz.c.step_id == cause.step_id,
                authz.c.authorization_digest == cause.authority_digest,
            )))
            if authority is None:
                raise ExactBindingConflict("active child failure authority is absent")
            validate_authorization_row(dict(authority))
        elif cause.authority_digest != child["submission_authority_digest"]:
            raise ExactBindingConflict("nested child failure authority drift")
        relations = active_child_rows(self.connection, project_key=runtime_scope_key(self.scope),
                                      parent_run_id=parent_run_id, source_step_id=source_step_id)
        matches = tuple(row["event_metadata_json"] for row in relations
                        if row["event_metadata_json"].get("child_run_id") == child_run_id)
        if len(matches) != 1:
            raise ExactBindingConflict("active child failure lineage is absent or ambiguous")
        relation = matches[0]
        index = relation["element_index"]
        for row in relations[:index]:
            prior = journal.load_run(str(row["event_metadata_json"]["child_run_id"]), for_update=True)
            if prior["state"] != "COMPLETED":
                raise ExactBindingConflict("active child failed outside the completed ordered prefix")
        metadata = {
            "source_step_id": source_step_id, "child_run_id": child_run_id,
            "element_index": index, "materialization_digest": relation["materialization_digest"],
            "source_revision": cause.seq, "source_event_digest": cause.event_digest,
        }
        metadata["failure_policy_decision_digest"] = active_child_failure_decision_digest(metadata)
        if parent["state"] == "FAILED":
            if (parent_projection.run_state is RunState.FAILED
                    and parent_events[-1].schema_version == "mrw.runtime.event.required_step_failed.active_child.v2"
                    and dict(parent_events[-1].metadata) == metadata):
                return
            raise ExactBindingConflict("parent failure has a different causal binding")
        if parent["state"] != "WAITING" or parent_projection.run_state is not RunState.WAITING:
            raise ExactBindingConflict("active child failure requires a waiting parent")
        event = ReplayEvent.from_content(
            project_key=runtime_scope_key(self.scope), run_id=parent_run_id,
            run_incarnation=str(parent["incarnation"]), seq=int(parent["next_event_seq"]),
            event_type="RequiredStepFailed", schema_version="mrw.runtime.event.required_step_failed.active_child.v2",
            step_id=None, attempt_id=None, metadata=metadata, payload_ref=None, payload_digest=None,
            authority_digest=str(parent["submission_authority_digest"]),
        )
        replay_runtime_events((event,), initial=parent_projection)
        self._cancel_active_children(parent_run_id, now=now)
        self._cancel_queued_work_items(parent_run_id, now=now)
        journal.append_transition(
            run_id=parent_run_id, expected_revision=int(parent["revision"]),
            snapshot_values={"state": "FAILED", "finished_at": now},
            events=({"event_type": event.event_type, "schema_version": event.schema_version,
                     "event_metadata_json": metadata, "authority_digest": event.authority_digest},),
        )

    def request_cancel(
        self, command: RequestCancel, *, observed_at: datetime | None = None
    ) -> Mapping[str, Any]:
        """Request cancellation of a live run and its non-terminal steps.

        The caller's actor must exactly match the persisted step authorization
        actor and the backing grant must not be revoked.  Not-yet-started steps
        become ``CANCELLED``; in-flight steps become ``CANCEL_REQUESTED`` so an
        unknown effect outcome is never fabricated as terminal.
        """

        now = observed_at or utc_now()
        journal = RuntimeJournalRepository(self.connection, self.scope)
        run = journal.load_run(command.run_id, for_update=True)
        if int(run["revision"]) != command.expected_run_revision:
            raise StaleRevisionError(
                "cancel run revision CAS failed: "
                f"expected {command.expected_run_revision}, found {run['revision']}"
            )
        if run["state"] in TERMINAL_RUN_STATES:
            raise ExactBindingConflict("runtime run is already terminal")
        self._require_cancel_authority(command.run_id, now=now)

        step_events: list[Mapping[str, Any]] = []
        cancelled_steps = 0
        cleanup_required = False
        for step in self._load_cancel_steps(command.run_id):
            state = StepState(str(step["state"]))
            if state in TERMINAL_STEP_STATES:
                continue
            allowed = STEP_TRANSITIONS.get(
                (state, StepEvent.CANCELLATION_REQUESTED), frozenset()
            )
            if len(allowed) != 1:
                raise ExactBindingConflict(
                    f"step state does not support cancellation: {state.value}"
                )
            target = next(iter(allowed))
            reduced = reduce_step(
                StepSnapshot(
                    str(step["step_id"]),
                    state,
                    EffectDisposition.NOT_STARTED,
                    revision=int(step["revision"]),
                ),
                StepEvent.CANCELLATION_REQUESTED,
                target,
                guard=True,
            )
            self._cancel_step_row(step, reduced.state, now=now)
            if reduced.state is StepState.CANCEL_REQUESTED:
                cleanup_required = True
            else:
                cancelled_steps += 1
            step_events.append(
                {
                    "event_type": StepEvent.CANCELLATION_REQUESTED.value,
                    "schema_version": "mrw.runtime.event.cancellation_requested.v1",
                    "step_id": str(step["step_id"]),
                    "attempt_id": None,
                    "event_metadata_json": {"state": reduced.state.value},
                    "payload_ref": None,
                    "payload_digest": None,
                    "authority_digest": run["submission_authority_digest"],
                }
            )

        self._cancel_queued_work_items(command.run_id, now=now)
        if self._cancel_active_children(command.run_id, now=now):
            cleanup_required = True

        target_run_state = (
            RunState.CANCELLING if cleanup_required else RunState.CANCELLED
        )
        reduced_run = reduce_run_event(
            RunSnapshot(
                command.run_id,
                RunState(str(run["state"])),
                int(run["revision"]),
            ),
            RunEvent.CANCELLATION_REQUESTED,
            target_run_state,
            guard=True,
        )
        receipt = journal.append_transition(
            run_id=command.run_id,
            expected_revision=command.expected_run_revision,
            snapshot_values={
                "cancellation_requested": True,
                "state": reduced_run.state.value,
            },
            events=[
                {
                    "event_type": RunEvent.CANCELLATION_REQUESTED.value,
                    "schema_version": "mrw.runtime.event.cancellation_requested.v1",
                    "step_id": None,
                    "attempt_id": None,
                    "event_metadata_json": {
                        "reason": command.reason or "explicit_cancel"
                    },
                    "payload_ref": None,
                    "payload_digest": None,
                    "authority_digest": run["submission_authority_digest"],
                },
                *step_events,
            ],
        )
        if target_run_state == RunState.CANCELLED.value:
            self._settle_active_parent_cancellations(command.run_id, now=now)
        return {
            "run_id": command.run_id,
            "state": reduced_run.state.value,
            "revision": receipt.revision,
            "cancelled_step_count": cancelled_steps,
            "cleanup_required": cleanup_required,
        }

    def _require_cancel_authority(self, run_id: str, *, now: datetime) -> None:
        from app.successor_runtime.substrate.postgres.authority_provider import (
            PostgresAuthorityProvider,
        )

        authz = runtime_table("runtime_step_authorizations")
        authz_result = self.connection.execute(
            select(authz)
            .where(
                authz.c.project_key == runtime_scope_key(self.scope),
                authz.c.run_id == run_id,
            )
            .order_by(authz.c.step_id)
            .with_for_update(read=True)
        )
        rows = tuple(
            dict(row) for row in authz_result.mappings()
        )
        if not rows:
            raise ExactBindingConflict("cancel requires at least one step authorization")
        provider = PostgresAuthorityProvider(self.connection, self.scope)
        for row in rows:
            binding = validate_authorization_row(row)
            if binding.actor_id != self.scope.actor_id:
                raise ExactBindingConflict("cancel actor differs from step authorization")
            provider.current_step_binding(
                run_id,
                binding.step_id,
                now=now,
            )

    def _load_cancel_steps(self, run_id: str) -> tuple[Mapping[str, Any], ...]:
        steps = runtime_table("runtime_steps")
        steps_result = self.connection.execute(
            select(steps)
            .where(
                steps.c.project_key == runtime_scope_key(self.scope),
                steps.c.run_id == run_id,
            )
            .order_by(steps.c.step_id)
            .with_for_update()
        )
        return tuple(
            dict(row) for row in steps_result.mappings()
        )

    def _cancel_step_row(
        self, step: Mapping[str, Any], state: StepState, *, now: datetime
    ) -> None:
        steps = runtime_table("runtime_steps")
        values: dict[str, object] = {
            "state": state.value,
            "revision": int(step["revision"]) + 1,
            "updated_at": now,
        }
        if state in TERMINAL_STEP_STATES:
            values.update(
                finished_at=now,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
            )
        _require_one(
            self.connection.execute(
                update(steps)
                .where(
                    steps.c.project_key == runtime_scope_key(self.scope),
                    steps.c.run_id == step["run_id"],
                    steps.c.step_id == step["step_id"],
                    steps.c.state == step["state"],
                    steps.c.revision == int(step["revision"]),
                )
                .values(**values)
            ),
            "cancel step CAS failed",
        )

    def _cancel_queued_work_items(self, run_id: str, *, now: datetime) -> None:
        work_items = runtime_table("runtime_work_items")
        self.connection.execute(
            update(work_items)
            .where(
                work_items.c.project_key == runtime_scope_key(self.scope),
                work_items.c.run_id == run_id,
                work_items.c.state.in_(("PENDING", "READY", "WAITING")),
            )
            .values(
                state="CANCELLED",
                wait_reason=None,
                revision=work_items.c.revision + 1,
                updated_at=now,
            )
        )

    def commit_non_start_cancellation(
        self,
        *,
        run_id: str,
        step_id: str,
        attempt_id: str,
        authority_digest: str,
    ) -> None:
        """Record one Node-before-handler cancellation and settle the run."""

        journal = RuntimeJournalRepository(self.connection, self.scope)
        run = journal.load_run(run_id, for_update=True)
        if run["state"] != RunState.CANCELLING.value:
            raise ExactBindingConflict(
                "non-start cancellation requires CANCELLING run"
            )
        events: list[Mapping[str, Any]] = [
            {
                "event_type": StepEvent.CLEANUP_OR_READBACK_CONFIRMED.value,
                "schema_version": "mrw.runtime.event.cancellation_cleanup_confirmed.v1",
                "step_id": step_id,
                "attempt_id": attempt_id,
                "event_metadata_json": {
                    "state": StepState.CANCELLED.value,
                    "reason": "NODE_BEFORE_HANDLER",
                },
                "payload_ref": None,
                "payload_digest": None,
                "authority_digest": authority_digest,
            }
        ]
        target_state = RunState.CANCELLING.value
        if not self._has_non_terminal_steps(run_id) and not self._has_live_active_children(
            run_id
        ):
            target_state = RunState.CANCELLED.value
            events.append(
                {
                    "event_type": RunEvent.REQUIRED_CLEANUP_SETTLED.value,
                    "schema_version": "mrw.runtime.event.cancellation_cleanup_settled.v1",
                    "step_id": None,
                    "attempt_id": None,
                    "event_metadata_json": {"state": RunState.CANCELLED.value},
                    "payload_ref": None,
                    "payload_digest": None,
                    "authority_digest": authority_digest,
                }
            )
        journal.append_transition(
            run_id=run_id,
            expected_revision=int(run["revision"]),
            snapshot_values={"state": target_state},
            events=events,
        )
        if target_state == RunState.CANCELLED.value:
            self._settle_active_parent_cancellations(run_id, now=utc_now())

    def _has_non_terminal_steps(self, run_id: str) -> bool:
        steps = runtime_table("runtime_steps")
        terminal_values = tuple(state.value for state in TERMINAL_STEP_STATES)
        row = one_mapping(
            self.connection.execute(
                select(steps)
                .where(
                    steps.c.project_key == runtime_scope_key(self.scope),
                    steps.c.run_id == run_id,
                    steps.c.state.notin_(terminal_values),
                )
                .limit(1)
            )
        )
        return row is not None

    def _cancel_active_children(self, run_id: str, *, now: datetime) -> bool:
        events = runtime_table("runtime_events")
        rows = self.connection.execute(
            select(events.c.event_metadata_json)
            .where(
                events.c.project_key == runtime_scope_key(self.scope),
                events.c.run_id == run_id,
                events.c.event_type == "ActiveChildMaterialized",
            )
            .order_by(events.c.seq)
        ).mappings().all()
        child_ids = tuple(
            str(row["event_metadata_json"]["child_run_id"]) for row in rows
        )
        if len(child_ids) != len(set(child_ids)) or run_id in child_ids:
            raise ExactBindingConflict("active child cancellation lineage is invalid")
        cleanup_required = False
        journal = RuntimeJournalRepository(self.connection, self.scope)
        for child_id in child_ids:
            child = journal.load_run(child_id, for_update=True)
            if str(child["state"]) in {state.value for state in TERMINAL_RUN_STATES}:
                continue
            result = self.request_cancel(
                RequestCancel(
                    run_id=child_id,
                    expected_run_revision=int(child["revision"]),
                    reason=f"active_parent_cancelled:{run_id}",
                ),
                observed_at=now,
            )
            cleanup_required = cleanup_required or result["state"] == "CANCELLING"
        return cleanup_required

    def _settle_active_parent_cancellations(
        self, child_run_id: str, *, now: datetime
    ) -> None:
        events = runtime_table("runtime_events")
        rows = self.connection.execute(
            select(events.c.run_id)
            .where(
                events.c.project_key == runtime_scope_key(self.scope),
                events.c.event_type == "ActiveChildMaterialized",
                events.c.event_metadata_json["child_run_id"].astext == child_run_id,
            )
            .order_by(events.c.run_id)
        ).mappings().all()
        journal = RuntimeJournalRepository(self.connection, self.scope)
        for row in rows:
            parent_id = str(row["run_id"])
            parent = journal.load_run(parent_id, for_update=True)
            if parent["state"] != RunState.CANCELLING.value:
                continue
            if self._has_non_terminal_steps(parent_id) or self._has_live_active_children(
                parent_id
            ):
                continue
            journal.append_transition(
                run_id=parent_id,
                expected_revision=int(parent["revision"]),
                snapshot_values={"state": RunState.CANCELLED.value},
                events=(
                    {
                        "event_type": RunEvent.REQUIRED_CLEANUP_SETTLED.value,
                        "schema_version": "mrw.runtime.event.cancellation_cleanup_settled.v1",
                        "event_metadata_json": {"state": RunState.CANCELLED.value},
                        "authority_digest": parent["submission_authority_digest"],
                    },
                ),
            )
            self._settle_active_parent_cancellations(parent_id, now=now)

    def _has_live_active_children(self, parent_run_id: str) -> bool:
        events = runtime_table("runtime_events")
        runs = runtime_table("runtime_runs")
        rows = self.connection.execute(
            select(events.c.event_metadata_json).where(
                events.c.project_key == runtime_scope_key(self.scope),
                events.c.run_id == parent_run_id,
                events.c.event_type == "ActiveChildMaterialized",
            )
        ).mappings().all()
        terminal = {state.value for state in TERMINAL_RUN_STATES}
        for row in rows:
            child_id = str(row["event_metadata_json"]["child_run_id"])
            child = one_mapping(
                self.connection.execute(
                    select(runs.c.state).where(
                        runs.c.project_key == runtime_scope_key(self.scope),
                        runs.c.run_id == child_id,
                    )
                )
            )
            if child is None or str(child["state"]) not in terminal:
                return True
        return False

    def _lock_run(self, run_id: str) -> RowMapping:
        table = runtime_table("runtime_runs")
        row = one_mapping(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == runtime_scope_key(self.scope),
                    table.c.run_id == run_id,
                )
                .with_for_update()
            )
        )
        if row is None:
            raise RecordNotFound(f"runtime run not found: {run_id}")
        return row

    def _lock_claimed(self, claimed: ClaimedLifecycle) -> tuple[RowMapping, ...]:
        project_key = runtime_scope_key(self.scope)
        if claimed.claim.lease_expires_at <= utc_now():
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
        rows: list[RowMapping] = [run]
        for name, *pairs in lookups:
            table = runtime_table(name)
            statement = select(table).where(table.c.project_key == project_key)
            for column, value in pairs:
                statement = statement.where(getattr(table.c, column) == value)
            row = one_mapping(self.connection.execute(statement.with_for_update()))
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
        table = runtime_table("runtime_steps")
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
                    table.c.project_key == runtime_scope_key(self.scope),
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
        table = runtime_table("runtime_work_items")
        _require_one(
            self.connection.execute(
                update(table)
                .where(
                    table.c.project_key == runtime_scope_key(self.scope),
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
        table = runtime_table("runtime_work_items")
        _require_one(
            self.connection.execute(
                update(table)
                .where(
                    table.c.project_key == runtime_scope_key(self.scope),
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
        table = runtime_table("runtime_resource_reservations")
        _require_one(
            self.connection.execute(
                update(table)
                .where(
                    table.c.project_key == runtime_scope_key(self.scope),
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
        table = runtime_table("runtime_staged_artifacts")
        assert outcome.staged_artifact_id is not None
        assert outcome.expected_staged_revision is not None
        expected_state = "VERIFIED" if outcome.admit_staged else "STAGED"
        target_state = "ADMITTED" if outcome.admit_staged else "VERIFIED"
        _require_one(
            self.connection.execute(
                update(table)
                .where(
                    table.c.project_key == runtime_scope_key(self.scope),
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
        table = runtime_table("runtime_work_items")
        row = one_mapping(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == runtime_scope_key(self.scope),
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
                    table.c.project_key == runtime_scope_key(self.scope),
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
        run: RowMapping,
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
        runs = runtime_table("runtime_runs")
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
                    runs.c.project_key == runtime_scope_key(self.scope),
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
            insert(runtime_table("runtime_events")).values(
                project_key=runtime_scope_key(self.scope),
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
                project_key=runtime_scope_key(self.scope),
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
                insert(runtime_table("runtime_events")).values(
                    project_key=runtime_scope_key(self.scope),
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


def assignment_values(
    envelope: AssignmentEnvelope, *, due_at: datetime
) -> dict[str, object]:
    recovery = envelope.recovery_binding
    values: dict[str, object] = dict(assignment_index_values(envelope.assignment))
    values.update(
        required_node_profile_selector=envelope.required_node_profile_selector,
        qualification_digest=envelope.qualification_digest,
        authority_digest=envelope.authority_digest,
        resource_policy_digest=envelope.resource_policy_digest,
        resource_class=envelope.resource_class,
        resource_units=envelope.resource_units,
        concurrency_key=envelope.concurrency_key,
        provider_key=envelope.provider_key,
        recovery_handler_binding_ref=None if recovery is None else f"handler-binding:sha256:{recovery.binding_digest}",
        recovery_handler_binding_digest=None if recovery is None else recovery.binding_digest,
        recovery_binding_json=None if recovery is None else recovery.model_dump(mode="json"),
        authoritative_readback_profile_ref=envelope.authoritative_readback_profile_ref,
        delivery_intent_ref=envelope.delivery_intent_ref,
        fairness_key=envelope.fairness_key,
        state="READY",
        wait_reason=None,
        declared_priority=envelope.declared_priority,
        enqueued_at=due_at,
        due_at=due_at,
        attempt_count=0,
        revision=0,
    )
    validate_runtime_assignment_row(values)
    return values


def _require_claim_rows(
    claimed: ClaimedLifecycle,
    step: RowMapping,
    work: RowMapping,
    attempt: RowMapping,
    reservation: RowMapping,
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
    "RequestCancel",
    "RuntimeLifecycleRepository",
    "SubmitRun",
    "TerminalOutcome",
    "assignment_values",
]
