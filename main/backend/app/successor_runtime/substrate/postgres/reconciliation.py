"""Atomic PostgreSQL adoption of authoritative reconciliation readback.

The owner mutates only public runtime control facts.  It never executes the
original effect and never inserts an effect attempt.  All exact-identity
checks, compare-and-swap updates, and the authoritative observation event run
on the caller-owned connection and therefore share one ``RuntimeUnitOfWork``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    RecoveryBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import RuntimeClaim
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.reconciliation import (
    ReconciliationHandlerOutcome,
    ReconciliationState,
)
from app.successor_runtime.runtime.reducer import (
    RunSnapshot,
    StepSnapshot,
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
from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
    _one_mapping,
    _table,
    validate_runtime_assignment_row,
)
from .runtime_lifecycle import AssignmentEnvelope, _assignment_values
from .session import ProjectScopeStale, ServerProjectScopeResolver
from .terminal_authority import PostgresTerminalAuthorityVerifier


class ReconciliationAdoptionError(ExactBindingConflict):
    """Authoritative readback cannot adopt the exact durable target."""


class PostgresReconciliationOwner:
    """Sole atomic owner for one claimed ``RECONCILE`` adoption."""

    def __init__(
        self,
        connection: Connection,
        *,
        terminal_authority: Any = None,
        failure_policy: Any = None,
    ) -> None:
        self.connection = connection
        self._terminal_authority = terminal_authority
        self._failure_policy = failure_policy

    def adopt(
        self,
        *,
        claim: RuntimeClaim,
        outcome: ReconciliationHandlerOutcome,
        actor_id: str,
        observed_at: datetime,
    ) -> None:
        """Validate and adopt a resolved/waiting authoritative observation."""

        if observed_at.tzinfo is None:
            raise ValueError("reconciliation observed_at must be timezone-aware")
        claim.validate_exact()
        assignment = claim.assignment
        if assignment.assignment_kind is not AssignmentKind.RECONCILE:
            raise ReconciliationAdoptionError(
                "Postgres reconciliation owner requires RECONCILE assignment"
            )
        binding = assignment.handler_binding
        if not isinstance(binding, RecoveryBinding):
            raise ReconciliationAdoptionError(
                "RECONCILE assignment lacks exact RecoveryBinding"
            )
        if claim.claim_binding.execution_reservation_ref is not None:
            raise ReconciliationAdoptionError(
                "RECONCILE claim must not own an execution reservation"
            )
        if claim.claim_binding.node_id != actor_id:
            raise PermissionError("reconciliation actor does not own the claim")
        if outcome.result.attempt_id != assignment.reconciliation_attempt_id:
            raise ReconciliationAdoptionError(
                "reconciliation outcome targets a different original attempt"
            )

        current_work = self._one_locked(
            "runtime_work_items",
            project_key=assignment.project_key,
            work_item_id=assignment.work_item_id,
        )
        durable_assignment = validate_runtime_assignment_row(current_work)
        durable_claim = self._stored_claim(current_work)
        if (
            durable_assignment != assignment
            or durable_claim != claim.claim_binding
            or current_work["state"] != "CLAIMED"
            or int(current_work["revision"]) != claim.work_item_revision
            or current_work["lease_token"] != claim.claim_binding.lease_token
            or current_work["claim_binding_digest"]
            != claim.claim_binding.binding_digest
            or current_work["reconciliation_attempt_id"]
            != assignment.reconciliation_attempt_id
            or current_work["handler_binding_digest"] != binding.binding_digest
            or current_work["authoritative_readback_profile_ref"]
            != binding.authoritative_readback_profile_ref
        ):
            raise ReconciliationAdoptionError(
                "claimed RECONCILE work differs from RuntimeClaim"
            )

        run = self._one_locked(
            "runtime_runs",
            project_key=assignment.project_key,
            run_id=assignment.run_id,
        )
        step = self._one_locked(
            "runtime_steps",
            project_key=assignment.project_key,
            run_id=assignment.run_id,
            step_id=assignment.step_id,
        )
        target_attempt = self._one_locked(
            "runtime_effect_attempts",
            project_key=assignment.project_key,
            attempt_id=assignment.reconciliation_attempt_id,
        )
        original_claim = self._stored_claim(target_attempt)
        original_work = self._one_locked(
            "runtime_work_items",
            project_key=assignment.project_key,
            work_item_id=original_claim.work_item_id,
        )
        original_assignment = validate_runtime_assignment_row(original_work)
        self._require_exact_graph(
            claim=claim,
            binding=binding,
            current_work=current_work,
            run=run,
            step=step,
            target_attempt=target_attempt,
            original_claim=original_claim,
            original_work=original_work,
            original_assignment=original_assignment,
        )
        self._require_current_terminal_authority(
            run=run,
            assignment=original_assignment,
            authorization_digest=claim.claim_binding.authorization_digest,
            actor_id=actor_id,
            observed_at=observed_at,
        )

        if outcome.result.state is ReconciliationState.RESOLVED:
            self._adopt_resolved(
                claim=claim,
                outcome=outcome,
                current_work=current_work,
                run=run,
                step=step,
                target_attempt=target_attempt,
                original_work=original_work,
                observed_at=observed_at,
            )
            return
        if outcome.result.state is ReconciliationState.WAITING:
            self._adopt_waiting(
                claim=claim,
                outcome=outcome,
                current_work=current_work,
                run=run,
                step=step,
                target_attempt=target_attempt,
                observed_at=observed_at,
            )
            return
        raise ReconciliationAdoptionError(
            "NOT_STARTED_PROVEN successor materialization is outside P0 adoption"
        )

    def _require_current_terminal_authority(
        self,
        *,
        run: Mapping[str, Any],
        assignment: RuntimeAssignment,
        authorization_digest: str,
        actor_id: str,
        observed_at: datetime,
    ) -> None:
        if self._terminal_authority is not None:
            self._terminal_authority.require_current(
                assignment=assignment,
                authorization_digest=authorization_digest,
                observed_at=observed_at,
            )
            return
        resolver = ServerProjectScopeResolver(connection=self.connection)
        scope_ref = resolver.resolve_expected(
            assignment.project_key,
            int(run["project_registry_revision"]),
            str(run["project_scope_digest"]),
        )
        if (
            isinstance(scope_ref, ProjectScopeStale)
            or resolver.resolve(assignment.project_key) != scope_ref
            or scope_ref.resolved_schema != run["resolved_schema"]
        ):
            raise ReconciliationAdoptionError(
                "reconciliation terminal project scope is stale"
            )
        PostgresTerminalAuthorityVerifier(self.connection).require_current(
            scope=RuntimeScope(project_scope=scope_ref, actor_id=actor_id),
            assignment=assignment,
            authorization_digest=authorization_digest,
            observed_at=observed_at,
        )

    def _require_exact_graph(
        self,
        *,
        claim: RuntimeClaim,
        binding: RecoveryBinding,
        current_work: Mapping[str, Any],
        run: Mapping[str, Any],
        step: Mapping[str, Any],
        target_attempt: Mapping[str, Any],
        original_claim: ClaimBinding,
        original_work: Mapping[str, Any],
        original_assignment: RuntimeAssignment,
    ) -> None:
        assignment = claim.assignment
        if (
            run["incarnation"] != assignment.incarnation
            or run["program_digest"] != assignment.program_digest
            or int(run["execution_epoch"]) != assignment.execution_epoch
            or run["state"] not in {"RECONCILING", "WAITING"}
        ):
            raise ReconciliationAdoptionError("RECONCILE run binding/state drift")
        if (
            step["state"] != "RECONCILING"
            or step["lease_token"] != claim.claim_binding.lease_token
            or step["lease_owner"] != claim.claim_binding.node_id
            or int(step["revision"]) != int(current_work["expected_step_revision"]) + 1
            or int(step["execution_epoch"]) != assignment.execution_epoch
            or step["input_digest"] != assignment.input_closure_digest
        ):
            raise ReconciliationAdoptionError("RECONCILE step binding/state drift")
        if (
            target_attempt["run_id"] != assignment.run_id
            or target_attempt["step_id"] != assignment.step_id
            or target_attempt["attempt_id"] != assignment.reconciliation_attempt_id
            or target_attempt["disposition"] != EffectDisposition.OUTCOME_UNKNOWN.value
            or target_attempt["assignment_digest"] != original_work["assignment_digest"]
            or target_attempt["handler_binding_digest"]
            != original_work["handler_binding_digest"]
            or target_attempt["claim_binding_digest"] != original_claim.binding_digest
        ):
            raise ReconciliationAdoptionError(
                "RECONCILE target is not the exact OUTCOME_UNKNOWN attempt"
            )
        if (
            original_assignment.assignment_kind
            not in {
                AssignmentKind.INTERPRET,
                AssignmentKind.VERIFY_ADMIT,
            }
            or original_assignment.project_key != assignment.project_key
            or original_assignment.run_id != assignment.run_id
            or original_assignment.step_id != assignment.step_id
            or original_assignment.execution_epoch != assignment.execution_epoch
            or original_assignment.incarnation != assignment.incarnation
            or original_assignment.operation_contract_digest
            != assignment.operation_contract_digest
            or original_assignment.input_closure_digest
            != assignment.input_closure_digest
            or original_claim.assignment_digest != original_assignment.assignment_digest
            or original_claim.handler_binding_digest
            != original_assignment.handler_binding_digest
            or original_claim.attempt_id != target_attempt["attempt_id"]
            or original_claim.interpreter_profile_digest
            != binding.interpreter_profile_digest
            or original_work["state"] not in {"WAITING", "COMPLETED"}
        ):
            raise ReconciliationAdoptionError(
                "original work/attempt/recovery binding graph drift"
            )

    def _adopt_resolved(
        self,
        *,
        claim: RuntimeClaim,
        outcome: ReconciliationHandlerOutcome,
        current_work: Mapping[str, Any],
        run: Mapping[str, Any],
        step: Mapping[str, Any],
        target_attempt: Mapping[str, Any],
        original_work: Mapping[str, Any],
        observed_at: datetime,
    ) -> None:
        result = outcome.result
        readback = result.readback
        if readback is None or readback.attempt_id != target_attempt["attempt_id"]:
            raise ReconciliationAdoptionError(
                "resolved reconciliation lacks exact authoritative readback"
            )
        if readback.disposition is not result.disposition:
            raise ReconciliationAdoptionError(
                "resolved readback disposition differs from result"
            )
        success = result.disposition is EffectDisposition.SUCCEEDED
        if not success and result.disposition is not EffectDisposition.FAILED:
            raise ReconciliationAdoptionError(
                "resolved reconciliation must be SUCCEEDED or FAILED"
            )
        if success and (
            outcome.output_digest is None
            or readback.receipt_digest is None
            or readback.provider_locator is None
        ):
            raise ReconciliationAdoptionError(
                "resolved success lacks exact output/receipt/provider evidence"
            )
        if not success and readback.failure_digest is None:
            raise ReconciliationAdoptionError(
                "resolved failure lacks exact failure evidence"
            )

        attempt_values: dict[str, object | None] = {
            "disposition": result.disposition.value,
            "external_ref": readback.provider_locator,
            "receipt_ref": outcome.receipt_ref if success else None,
            "receipt_digest": readback.receipt_digest if success else None,
            "failure_ref": (
                None
                if success
                else f"authoritative-failure:sha256:{readback.failure_digest}"
            ),
            "failure_digest": None if success else readback.failure_digest,
            "finished_at": observed_at,
            "revision": int(target_attempt["revision"]) + 1,
            "updated_at": observed_at,
        }
        self._cas(
            update(_table("runtime_effect_attempts"))
            .where(
                _table("runtime_effect_attempts").c.project_key
                == claim.assignment.project_key,
                _table("runtime_effect_attempts").c.attempt_id
                == target_attempt["attempt_id"],
                _table("runtime_effect_attempts").c.revision
                == target_attempt["revision"],
                _table("runtime_effect_attempts").c.disposition
                == EffectDisposition.OUTCOME_UNKNOWN.value,
                _table("runtime_effect_attempts").c.claim_binding_digest
                == target_attempt["claim_binding_digest"],
            )
            .values(**attempt_values),
            "authoritative target-attempt adoption CAS failed",
        )

        original_state = "COMPLETED" if success else "FAILED"
        step_event = (
            StepEvent.AUTHORITATIVE_READBACK_SUCCEEDED
            if success
            else StepEvent.AUTHORITATIVE_READBACK_FAILED
        )
        target_step_state = StepState.SUCCEEDED if success else StepState.FAILED
        reduced_step = reduce_step(
            StepSnapshot(
                step_id=str(step["step_id"]),
                state=StepState.RECONCILING,
                effect_disposition=EffectDisposition.OUTCOME_UNKNOWN,
                revision=int(step["revision"]),
            ),
            step_event,
            target_step_state,
            guard=True,
        )
        failure_policy_decision = None
        if success:
            reduced_run = reduce_run_event(
                RunSnapshot(
                    run_id=str(run["run_id"]),
                    state=RunState(str(run["state"])),
                    revision=int(run["revision"]),
                ),
                RunEvent.REQUIRED_STEP_RUNNABLE,
                RunState.RUNNING,
                guard=True,
            )
        else:
            failure_policy_decision = self._load_failure_policy_decision(
                run=run,
                step_id=str(step["step_id"]),
                actor_id=claim.claim_binding.node_id,
            )
            if getattr(failure_policy_decision, "emit_required_step_failed", False):
                reduced_run = reduce_run_event(
                    RunSnapshot(
                        run_id=str(run["run_id"]),
                        state=RunState(str(run["state"])),
                        revision=int(run["revision"]),
                    ),
                    RunEvent.REQUIRED_STEP_FAILED,
                    RunState.FAILED,
                    guard=True,
                )
            else:
                reduced_run = RunSnapshot(
                    run_id=str(run["run_id"]),
                    state=RunState(str(run["state"])),
                    revision=int(run["revision"]) + 1,
                )
        failure_ref = attempt_values["failure_ref"]
        self._cas(
            update(_table("runtime_work_items"))
            .where(
                _table("runtime_work_items").c.project_key
                == claim.assignment.project_key,
                _table("runtime_work_items").c.work_item_id
                == original_work["work_item_id"],
                _table("runtime_work_items").c.revision == original_work["revision"],
                _table("runtime_work_items").c.state == original_work["state"],
                _table("runtime_work_items").c.assignment_digest
                == original_work["assignment_digest"],
            )
            .values(
                state=original_state,
                wait_reason=None,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                last_failure_ref=failure_ref,
                revision=int(original_work["revision"]) + 1,
                updated_at=observed_at,
            ),
            "original work terminal adoption CAS failed",
        )
        self._cas(
            update(_table("runtime_steps"))
            .where(
                _table("runtime_steps").c.project_key == claim.assignment.project_key,
                _table("runtime_steps").c.run_id == claim.assignment.run_id,
                _table("runtime_steps").c.step_id == claim.assignment.step_id,
                _table("runtime_steps").c.revision == step["revision"],
                _table("runtime_steps").c.state == "RECONCILING",
                _table("runtime_steps").c.lease_token
                == claim.claim_binding.lease_token,
            )
            .values(
                state=reduced_step.state.value,
                output_digest=outcome.output_digest if success else None,
                failure_digest=None if success else readback.failure_digest,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                finished_at=observed_at,
                revision=reduced_step.revision,
                updated_at=observed_at,
            ),
            "reconciled step terminal CAS failed",
        )
        self._terminal_recovery_work(
            claim=claim,
            current_work=current_work,
            observed_at=observed_at,
        )
        self._append_event_and_run(
            claim=claim,
            run=run,
            target_run_state=reduced_run.state.value,
            event_type=step_event.value,
            outcome=outcome,
            original_work_item_id=str(original_work["work_item_id"]),
            observed_at=observed_at,
            failure_policy_decision_digest=(
                None
                if failure_policy_decision is None
                else failure_policy_decision.decision_digest
            ),
            required_step_failed=(
                False
                if failure_policy_decision is None
                else getattr(
                    failure_policy_decision,
                    "emit_required_step_failed",
                    False,
                )
            ),
        )

    def _load_failure_policy_decision(
        self,
        *,
        run: Mapping[str, Any],
        step_id: str,
        actor_id: str,
    ) -> object:
        if self._failure_policy is not None:
            return self._failure_policy.load_decision(str(run["run_id"]), step_id)
        resolver = ServerProjectScopeResolver(connection=self.connection)
        scope_ref = resolver.resolve_expected(
            str(run["project_key"]),
            int(run["project_registry_revision"]),
            str(run["project_scope_digest"]),
        )
        if (
            isinstance(scope_ref, ProjectScopeStale)
            or resolver.resolve(str(run["project_key"])) != scope_ref
            or scope_ref.resolved_schema != run["resolved_schema"]
        ):
            raise ReconciliationAdoptionError("failed readback project scope is stale")
        return PostgresFailurePolicyLoader(
            self.connection,
            RuntimeScope(project_scope=scope_ref, actor_id=actor_id),
        ).load_decision(str(run["run_id"]), step_id)

    def _adopt_waiting(
        self,
        *,
        claim: RuntimeClaim,
        outcome: ReconciliationHandlerOutcome,
        current_work: Mapping[str, Any],
        run: Mapping[str, Any],
        step: Mapping[str, Any],
        target_attempt: Mapping[str, Any],
        observed_at: datetime,
    ) -> None:
        result = outcome.result
        if result.disposition is not EffectDisposition.OUTCOME_UNKNOWN:
            raise ReconciliationAdoptionError(
                "WAITING reconciliation must retain OUTCOME_UNKNOWN"
            )
        # Intentionally no UPDATE of runtime_effect_attempts: unavailable
        # evidence is still OUTCOME_UNKNOWN.  A new immutable due assignment,
        # rather than an in-place assignment mutation, owns the next readback.
        if target_attempt["disposition"] != EffectDisposition.OUTCOME_UNKNOWN.value:
            raise ReconciliationAdoptionError("WAITING target attempt changed")
        reduced = reduce_step(
            StepSnapshot(
                step_id=str(step["step_id"]),
                state=StepState.RECONCILING,
                effect_disposition=EffectDisposition.OUTCOME_UNKNOWN,
                revision=int(step["revision"]),
            ),
            StepEvent.READBACK_UNAVAILABLE,
            StepState.WAITING_EXTERNAL,
            guard=True,
        )
        next_due = observed_at + timedelta(seconds=1)
        assignment = claim.assignment
        binding = assignment.handler_binding
        assert isinstance(binding, RecoveryBinding)
        successor_work_id = "reconcile:sha256:" + canonical_digest(
            {
                "schema_version": "mrw.reconciliation-successor-work.v1",
                "target_attempt_id": assignment.reconciliation_attempt_id,
                "prior_work_item_id": assignment.work_item_id,
                "expected_step_revision": reduced.revision,
                "observation_digest": (
                    None
                    if result.readback is None
                    else result.readback.observation_digest
                ),
            }
        )
        successor_values = assignment.model_dump(mode="python")
        successor_values.update(
            work_item_id=successor_work_id,
            expected_step_revision=reduced.revision,
        )
        successor = RuntimeAssignment(**successor_values)
        envelope = AssignmentEnvelope(
            assignment=successor,
            required_node_profile_selector=str(
                current_work["required_node_profile_selector"]
            ),
            authority_digest=str(current_work["authority_digest"]),
            resource_policy_digest=str(current_work["resource_policy_digest"]),
            fairness_key=str(current_work["fairness_key"]),
            qualification_digest=str(current_work["qualification_digest"]),
            resource_class=current_work["resource_class"],
            resource_units=current_work["resource_units"],
            concurrency_key=current_work["concurrency_key"],
            provider_key=current_work["provider_key"],
            recovery_binding=binding,
            authoritative_readback_profile_ref=(
                binding.authoritative_readback_profile_ref
            ),
            delivery_intent_ref=current_work["delivery_intent_ref"],
            declared_priority=int(current_work["declared_priority"]),
        )
        next_work_values = _assignment_values(envelope, due_at=next_due)
        self._cas(
            update(_table("runtime_steps"))
            .where(
                _table("runtime_steps").c.project_key == claim.assignment.project_key,
                _table("runtime_steps").c.run_id == claim.assignment.run_id,
                _table("runtime_steps").c.step_id == claim.assignment.step_id,
                _table("runtime_steps").c.revision == step["revision"],
                _table("runtime_steps").c.state == "RECONCILING",
                _table("runtime_steps").c.lease_token
                == claim.claim_binding.lease_token,
            )
            .values(
                state=reduced.state.value,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                revision=reduced.revision,
                updated_at=observed_at,
            ),
            "reconciliation waiting step CAS failed",
        )
        self._cas(
            update(_table("runtime_work_items"))
            .where(
                _table("runtime_work_items").c.project_key
                == claim.assignment.project_key,
                _table("runtime_work_items").c.work_item_id
                == claim.assignment.work_item_id,
                _table("runtime_work_items").c.revision == current_work["revision"],
                _table("runtime_work_items").c.state == "CLAIMED",
                _table("runtime_work_items").c.lease_token
                == claim.claim_binding.lease_token,
            )
            .values(
                state="SUPERSEDED",
                wait_reason=None,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                last_failure_ref=f"successor-work-item:{successor_work_id}",
                revision=int(current_work["revision"]) + 1,
                updated_at=observed_at,
            ),
            "reconciliation waiting work CAS failed",
        )
        self.connection.execute(
            insert(_table("runtime_work_items")).values(**next_work_values)
        )
        self._append_event_and_run(
            claim=claim,
            run=run,
            target_run_state=str(run["state"]),
            event_type=StepEvent.READBACK_UNAVAILABLE.value,
            outcome=outcome,
            original_work_item_id=self._stored_claim(target_attempt).work_item_id,
            observed_at=observed_at,
        )

    def _terminal_recovery_work(
        self,
        *,
        claim: RuntimeClaim,
        current_work: Mapping[str, Any],
        observed_at: datetime,
    ) -> None:
        self._cas(
            update(_table("runtime_work_items"))
            .where(
                _table("runtime_work_items").c.project_key
                == claim.assignment.project_key,
                _table("runtime_work_items").c.work_item_id
                == claim.assignment.work_item_id,
                _table("runtime_work_items").c.revision == current_work["revision"],
                _table("runtime_work_items").c.state == "CLAIMED",
                _table("runtime_work_items").c.lease_token
                == claim.claim_binding.lease_token,
            )
            .values(
                state="COMPLETED",
                wait_reason=None,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                last_failure_ref=None,
                revision=int(current_work["revision"]) + 1,
                updated_at=observed_at,
            ),
            "reconciliation work completion CAS failed",
        )

    def _append_event_and_run(
        self,
        *,
        claim: RuntimeClaim,
        run: Mapping[str, Any],
        target_run_state: str,
        event_type: str,
        outcome: ReconciliationHandlerOutcome,
        original_work_item_id: str,
        observed_at: datetime,
        failure_policy_decision_digest: str | None = None,
        required_step_failed: bool = False,
    ) -> None:
        seq = int(run["next_event_seq"])
        if required_step_failed and event_type != StepEvent.AUTHORITATIVE_READBACK_FAILED.value:
            raise ReconciliationAdoptionError(
                "RequiredStepFailed must follow AuthoritativeReadbackFailed"
            )
        if required_step_failed and (
            not isinstance(failure_policy_decision_digest, str)
            or len(failure_policy_decision_digest) != 64
        ):
            raise ReconciliationAdoptionError(
                "required readback failure lacks persisted policy decision digest"
            )
        event_count = 2 if required_step_failed else 1
        self._cas(
            update(_table("runtime_runs"))
            .where(
                _table("runtime_runs").c.project_key == claim.assignment.project_key,
                _table("runtime_runs").c.run_id == claim.assignment.run_id,
                _table("runtime_runs").c.revision == run["revision"],
                _table("runtime_runs").c.next_event_seq == seq,
                _table("runtime_runs").c.state == run["state"],
            )
            .values(
                state=target_run_state,
                revision=int(run["revision"]) + 1,
                next_event_seq=seq + event_count,
                updated_at=observed_at,
            ),
            "authoritative readback run/event CAS failed",
        )
        readback = outcome.result.readback
        event_metadata = {
            "recovery_work_item_id": claim.assignment.work_item_id,
            "original_work_item_id": original_work_item_id,
            "reconciliation_claim_attempt_id": claim.claim_binding.attempt_id,
            "status": outcome.result.state.value,
            "disposition": outcome.result.disposition.value,
            "observation_digest": (
                None if readback is None else readback.observation_digest
            ),
            "provider_locator": (
                None if readback is None else readback.provider_locator
            ),
            "receipt_digest": (
                None if readback is None else readback.receipt_digest
            ),
            "failure_digest": (
                None if readback is None else readback.failure_digest
            ),
            "output_digest": outcome.output_digest,
            "wait_reason": outcome.result.wait_reason,
            "failure_policy_decision_digest": failure_policy_decision_digest,
            "required_step_failed": required_step_failed,
        }
        if required_step_failed:
            event_metadata["required_step_failed_event_revision"] = seq + 1
        self.connection.execute(
            insert(_table("runtime_events")).values(
                project_key=claim.assignment.project_key,
                run_id=claim.assignment.run_id,
                seq=seq,
                event_type=event_type,
                schema_version="mrw.runtime.event.authoritative_readback.v1",
                step_id=claim.assignment.step_id,
                attempt_id=claim.assignment.reconciliation_attempt_id,
                event_metadata_json=event_metadata,
                authority_digest=claim.claim_binding.authorization_digest,
                created_at=observed_at,
                updated_at=observed_at,
            )
        )
        if required_step_failed:
            source_event_digest = runtime_event_digest(
                project_key=claim.assignment.project_key,
                run_id=claim.assignment.run_id,
                run_incarnation=str(run["incarnation"]),
                seq=seq,
                event_type=event_type,
                schema_version="mrw.runtime.event.authoritative_readback.v1",
                step_id=claim.assignment.step_id,
                attempt_id=claim.assignment.reconciliation_attempt_id,
                metadata=event_metadata,
                payload_ref=None,
                payload_digest=None,
                authority_digest=claim.claim_binding.authorization_digest,
            )
            self.connection.execute(
                insert(_table("runtime_events")).values(
                    project_key=claim.assignment.project_key,
                    run_id=claim.assignment.run_id,
                    seq=seq + 1,
                    event_type=RunEvent.REQUIRED_STEP_FAILED.value,
                    schema_version="mrw.runtime.event.required_step_failed.v1",
                    step_id=claim.assignment.step_id,
                    attempt_id=claim.assignment.reconciliation_attempt_id,
                    event_metadata_json={
                        "status": "FAILED",
                        "source_revision": seq,
                        "source_event_digest": source_event_digest,
                        "failure_policy_decision_digest": (
                            failure_policy_decision_digest
                        ),
                    },
                    authority_digest=claim.claim_binding.authorization_digest,
                    created_at=observed_at,
                    updated_at=observed_at,
                )
            )

    def _one_locked(self, table_name: str, **identity: object) -> Mapping[str, Any]:
        table = _table(table_name)
        statement = select(table)
        for name, value in identity.items():
            statement = statement.where(getattr(table.c, name) == value)
        row = _one_mapping(self.connection.execute(statement.with_for_update()))
        if row is None:
            rendered = ", ".join(f"{key}={value!r}" for key, value in identity.items())
            raise RecordNotFound(f"{table_name} row not found: {rendered}")
        return row

    @staticmethod
    def _stored_claim(row: Mapping[str, Any]) -> ClaimBinding:
        payload = row.get("claim_binding_json")
        if payload is None:
            raise ReconciliationAdoptionError("durable row lacks exact ClaimBinding")
        try:
            return ClaimBinding.model_validate(payload)
        except Exception as exc:
            raise ReconciliationAdoptionError(
                "durable ClaimBinding is malformed"
            ) from exc

    def _cas(self, statement: Any, message: str) -> None:
        result = self.connection.execute(statement)
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError(message)


__all__ = [
    "PostgresReconciliationOwner",
    "ReconciliationAdoptionError",
]
