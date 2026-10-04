"""PostgreSQL due-work claim with explicit fair share and claim-time binding.

``FOR UPDATE SKIP LOCKED`` supplies row-level mutual exclusion only.  The due
query separately interleaves project/fairness and capability buckets, while
bounded aging affects order inside each bucket.  The caller owns the
transaction and this repository never commits or rolls back.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import (
    MetaData,
    and_,
    cast,
    delete,
    func,
    insert,
    literal,
    or_,
    select,
    update,
)
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import Select
from sqlalchemy.types import Integer

from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    RecoveryBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding, derive_attempt_id
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
    RuntimeScope,
)
from app.successor_runtime.runtime.qualification import QualifiedPlan
from app.successor_runtime.runtime.reducer import StepSnapshot, reduce_step
from app.successor_runtime.runtime.resources import (
    ExecutionReservation,
    FairSharePolicy,
    QueueEligibility,
    ResourceClass,
    assignment_requires_reservation,
)
from app.successor_runtime.runtime.transitions import (
    EffectDisposition,
    StepEvent,
    StepState,
)

from .models import project_tables
from .plans import decode_plan
from .resources import ResourceReservationRepository
from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
    _mapping_rows,
    _one_mapping,
    _table,
    _utcnow,
    validate_authorization_row,
    validate_qualification_row,
    validate_runtime_assignment_row,
)
from .runtime_lifecycle import AssignmentEnvelope, _assignment_values


class ClaimConflict(StaleRevisionError):
    pass


class ClaimBindingMismatch(ExactBindingConflict):
    pass


@dataclass(frozen=True, slots=True)
class NodeClaimContext:
    node_id: str
    node_profile_digest: str
    deployment_catalog_digest: str
    runtime_protocol_version: str
    authority_snapshot_digest: str
    interpreter_profile_digests: frozenset[str] = frozenset()
    lease_seconds: int = 45
    reservation_seconds: int = 60

    def __post_init__(self) -> None:
        if not all(
            (
                self.node_id,
                self.node_profile_digest,
                self.deployment_catalog_digest,
                self.runtime_protocol_version,
                self.authority_snapshot_digest,
            )
        ):
            raise ValueError("node claim context requires exact bindings")
        if self.lease_seconds <= 0 or self.reservation_seconds <= 0:
            raise ValueError("claim lease durations must be positive")


@dataclass(frozen=True, slots=True)
class ClaimRecord:
    work_item_id: str
    project_key: str
    run_id: str
    step_id: str | None
    assignment_digest: str
    attempt_id: str | None
    lease_token: str
    lease_expires_at: Any
    reservation_id: str | None
    assignment: RuntimeAssignment
    claim_binding: ClaimBinding


def due_claim_statement(
    context: NodeClaimContext,
    *,
    now: Any,
    limit: int,
    fairness: FairSharePolicy,
    cursor: int = 0,
) -> Select[Any]:
    """Build the PostgreSQL fair candidate lock query.

    Both project/fairness and capability row numbers participate in the outer
    order.  ``SKIP LOCKED`` is kept as the last mutual-exclusion mechanism and
    is never represented as the fairness policy itself.
    """

    work = _table("runtime_work_items")
    claimed_work = work.alias("claimed_work")
    project_active = (
        select(func.count())
        .select_from(claimed_work)
        .where(
            claimed_work.c.state == "CLAIMED",
            claimed_work.c.project_key == work.c.project_key,
        )
        .correlate(work)
        .scalar_subquery()
    )
    capability_active = (
        select(func.count())
        .select_from(claimed_work)
        .where(
            claimed_work.c.state == "CLAIMED",
            claimed_work.c.project_key == work.c.project_key,
            claimed_work.c.capability_id == work.c.capability_id,
        )
        .correlate(work)
        .scalar_subquery()
    )
    age_seconds = func.greatest(
        literal(0), func.extract("epoch", now - work.c.enqueued_at)
    )
    age_steps = cast(func.floor(age_seconds / fairness.aging_quantum_seconds), Integer)
    age_boost = func.least(
        fairness.max_aging_boost, age_steps * fairness.aging_increment
    )
    effective = work.c.declared_priority + age_boost
    eligible = (
        select(
            work.c.work_item_id.label("candidate_id"),
            work.c.project_key,
            work.c.fairness_key,
            work.c.capability_id,
            effective.label("effective_priority"),
            project_active.label("project_active"),
            capability_active.label("capability_active"),
            work.c.due_at,
            work.c.enqueue_seq,
        )
        .where(
            or_(
                work.c.state == "READY",
                and_(
                    work.c.state == "WAITING",
                    work.c.wait_reason == "RESOURCE_LIMIT",
                ),
            ),
            work.c.declared_priority <= fairness.max_declared_priority,
            project_active < fairness.max_project_active,
            capability_active < fairness.max_capability_active,
            work.c.due_at <= now,
            or_(work.c.deadline_at.is_(None), work.c.deadline_at > now),
            work.c.required_node_profile_selector == context.node_profile_digest,
            work.c.deployment_catalog_digest == context.deployment_catalog_digest,
            work.c.runtime_protocol_version == context.runtime_protocol_version,
            or_(
                work.c.interpreter_profile_digest.is_(None),
                work.c.interpreter_profile_digest.in_(
                    tuple(context.interpreter_profile_digests) or ("__none__",)
                ),
            ),
            or_(work.c.lease_token.is_(None), work.c.lease_expires_at <= now),
        )
        .cte("eligible_due")
    )
    capability_keys = (
        select(
            eligible.c.fairness_key,
            eligible.c.project_key,
            eligible.c.capability_id,
            eligible.c.capability_active,
        )
        .distinct()
        .cte("capability_keys")
    )
    capability_order = select(
        capability_keys.c.fairness_key,
        capability_keys.c.project_key,
        capability_keys.c.capability_id,
        func.row_number()
        .over(
            partition_by=(
                capability_keys.c.project_key,
                capability_keys.c.fairness_key,
            ),
            order_by=(
                capability_keys.c.capability_active,
                capability_keys.c.capability_id,
            ),
        )
        .label("capability_ordinal"),
        func.count()
        .over(
            partition_by=(
                capability_keys.c.project_key,
                capability_keys.c.fairness_key,
            )
        )
        .label("capability_count"),
    ).cte("capability_order")
    project_keys = (
        select(
            eligible.c.fairness_key,
            eligible.c.project_key,
            eligible.c.project_active,
        )
        .distinct()
        .cte("project_keys")
    )
    project_order = select(
        project_keys.c.fairness_key,
        project_keys.c.project_key,
        func.row_number()
        .over(
            order_by=(
                project_keys.c.project_active,
                project_keys.c.project_key,
                project_keys.c.fairness_key,
            )
        )
        .label("project_ordinal"),
        func.count().over().label("project_count"),
    ).cte("project_order")
    ranked = (
        select(
            eligible,
            func.row_number()
            .over(
                partition_by=(
                    eligible.c.project_key,
                    eligible.c.fairness_key,
                    eligible.c.capability_id,
                ),
                order_by=(
                    eligible.c.effective_priority.desc(),
                    eligible.c.due_at,
                    eligible.c.enqueue_seq,
                    eligible.c.candidate_id,
                ),
            )
            .label("capability_item_turn"),
            func.mod(
                capability_order.c.capability_ordinal
                - 1
                - cursor
                + capability_order.c.capability_count * (cursor + 1),
                capability_order.c.capability_count,
            ).label("rotated_capability"),
            func.mod(
                project_order.c.project_ordinal
                - 1
                - cursor
                + project_order.c.project_count * (cursor + 1),
                project_order.c.project_count,
            ).label("rotated_project"),
        )
        .join(
            capability_order,
            and_(
                capability_order.c.fairness_key == eligible.c.fairness_key,
                capability_order.c.project_key == eligible.c.project_key,
                capability_order.c.capability_id == eligible.c.capability_id,
            ),
        )
        .join(
            project_order,
            and_(
                project_order.c.fairness_key == eligible.c.fairness_key,
                project_order.c.project_key == eligible.c.project_key,
            ),
        )
        .cte("ranked_due")
    )
    capability_interleaved = select(
        ranked,
        func.floor(
            (ranked.c.capability_item_turn - 1) / fairness.capability_quantum
        ).label("capability_wave"),
        func.mod(
            ranked.c.capability_item_turn - 1,
            fairness.capability_quantum,
        ).label("capability_position"),
    ).cte("capability_interleaved")
    project_interleaved = select(
        capability_interleaved,
        func.row_number()
        .over(
            partition_by=(
                capability_interleaved.c.project_key,
                capability_interleaved.c.fairness_key,
            ),
            order_by=(
                capability_interleaved.c.capability_wave,
                capability_interleaved.c.rotated_capability,
                capability_interleaved.c.capability_position,
                capability_interleaved.c.effective_priority.desc(),
                capability_interleaved.c.due_at,
                capability_interleaved.c.enqueue_seq,
                capability_interleaved.c.candidate_id,
            ),
        )
        .label("project_item_turn"),
    ).cte("project_interleaved")
    statement = (
        select(work)
        .join(
            project_interleaved,
            project_interleaved.c.candidate_id == work.c.work_item_id,
        )
        .order_by(
            func.floor(
                (project_interleaved.c.project_item_turn - 1) / fairness.project_quantum
            ),
            project_interleaved.c.rotated_project,
            func.mod(
                project_interleaved.c.project_item_turn - 1,
                fairness.project_quantum,
            ),
            project_interleaved.c.effective_priority.desc(),
            project_interleaved.c.due_at,
            project_interleaved.c.enqueue_seq,
            project_interleaved.c.candidate_id,
        )
        .limit(limit)
        .with_for_update(of=work, skip_locked=True)
    )
    return statement


class WorkItemClaimRepository:
    """Atomic work/step/attempt/reservation/event claim owner."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self.resources = ResourceReservationRepository(connection)

    def claim_due(
        self,
        control_scope: ControlPlaneScope,
        context: NodeClaimContext,
        *,
        limit: int,
        fairness: FairSharePolicy | None = None,
        cursor: int | None = None,
        now: Any | None = None,
    ) -> tuple[ClaimRecord, ...]:
        control_scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)
        if limit <= 0:
            return ()
        observed_at = now or _utcnow()
        policy = fairness or FairSharePolicy()
        effective_cursor = (
            int(observed_at.timestamp()) // policy.claim_cycle_seconds
            if cursor is None
            else cursor
        )
        if effective_cursor < 0:
            raise ValueError("fairness cursor must be non-negative")
        self._require_active_node(context)
        rows = _mapping_rows(
            self.connection.execute(
                due_claim_statement(
                    context,
                    now=observed_at,
                    limit=limit,
                    fairness=policy,
                    cursor=effective_cursor,
                )
            )
        )
        claimed: list[ClaimRecord] = []
        for row in rows:
            record = self._claim_locked(
                row,
                control_scope=control_scope,
                context=context,
                fairness=policy,
                now=observed_at,
            )
            if record is not None:
                claimed.append(record)
        return tuple(claimed)

    def _require_active_node(self, context: NodeClaimContext) -> None:
        nodes = _table("runtime_nodes")
        row = _one_mapping(
            self.connection.execute(
                select(nodes)
                .where(nodes.c.node_id == context.node_id)
                .with_for_update()
            )
        )
        if row is None:
            raise RecordNotFound(f"runtime node not found: {context.node_id}")
        exact = (
            row["state"] == "ACTIVE"
            and row["node_profile_digest"] == context.node_profile_digest
            and row["deployment_catalog_digest"] == context.deployment_catalog_digest
            and row["runtime_protocol_version"] == context.runtime_protocol_version
        )
        if not exact:
            raise ClaimBindingMismatch("node profile/deployment binding mismatch")

    def _claim_locked(
        self,
        work: Mapping[str, Any],
        *,
        control_scope: ControlPlaneScope,
        context: NodeClaimContext,
        fairness: FairSharePolicy,
        now: Any,
    ) -> ClaimRecord | None:
        claimable_state = work["state"] == "READY" or (
            work["state"] == "WAITING" and work["wait_reason"] == "RESOURCE_LIMIT"
        )
        if (
            not claimable_state
            or work["deadline_at"] is not None
            and work["deadline_at"] <= now
        ):
            raise ClaimConflict("locked work item is no longer claimable")
        assignment = validate_runtime_assignment_row(work)
        _authority, authorization, step, run = self._require_exact_bindings(
            work,
            assignment=assignment,
            control_scope=control_scope,
            context=context,
            now=now,
        )
        if not self._fair_capacity_available(work, fairness=fairness):
            self._record_resource_wait(work, now)
            return None
        lease_token = secrets.token_urlsafe(32)
        lease_expires_at = now + timedelta(seconds=context.lease_seconds)
        reservation: ExecutionReservation | None = None

        kind = AssignmentKind(str(work["assignment_kind"]))
        authorization_digest = (
            str(authorization["authorization_digest"])
            if authorization is not None
            else str(work["authority_digest"])
        )
        attempt_id = derive_attempt_id(
            assignment,
            authorization_digest=authorization_digest,
            handler_realization_digest=assignment.handler_binding_digest,
        )
        eligibility: QueueEligibility | None = None
        policy_row: Mapping[str, Any] | None = None
        if assignment_requires_reservation(kind):
            if step is None or authorization is None or work["step_id"] is None:
                raise ClaimBindingMismatch("effect claim lacks step authorization")
            eligibility, policy_row = self._eligibility(work, step)
            reservation = ExecutionReservation.create(
                work_item_id=str(work["work_item_id"]),
                project_key=str(work["project_key"]),
                run_id=str(work["run_id"]),
                step_id=str(work["step_id"]),
                attempt_id=attempt_id,
                execution_epoch=int(step["execution_epoch"]),
                eligibility=eligibility,
                lease_token=lease_token,
                lease_expires_at=now + timedelta(seconds=context.reservation_seconds),
            )
        claim_binding = self._claim_binding(
            assignment,
            context=context,
            attempt_id=attempt_id,
            authorization_digest=authorization_digest,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            reservation=reservation,
        )
        if assignment_requires_reservation(kind):
            assert step is not None and authorization is not None
            assert eligibility is not None and policy_row is not None
            self._insert_attempt(
                work,
                run,
                step,
                authorization,
                claim_binding,
                now,
            )
            outcome = self.resources.try_reserve(
                reservation,  # type: ignore[arg-type]
                eligibility,
                capability_id=str(work["capability_id"]),
                node_id=context.node_id,
                resource_policy_id=str(policy_row["resource_policy_id"]),
                now=now,
            )
            if not outcome.decision.granted:
                # The failed statement has no capacity side effect.  The item
                # receives only a bounded wait observation.  The provisional
                # attempt insert is removed in this same transaction, so no
                # effect attempt or execution slot exists for RESOURCE_LIMIT.
                attempts = _table("runtime_effect_attempts")
                self.connection.execute(
                    delete(attempts).where(attempts.c.attempt_id == attempt_id)
                )
                self._record_resource_wait(work, now)
                return None

        self._claim_work_cas(
            work,
            context,
            claim_binding=claim_binding,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            now=now,
        )
        if step is not None:
            self._claim_step_and_append_event(
                work,
                step,
                run,
                context=context,
                attempt_id=attempt_id,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                authority_digest=authorization_digest,
                now=now,
            )
        if assignment_requires_reservation(kind):
            assert step is not None
            self._insert_lease_expiry_reconcile(
                work,
                assignment=assignment,
                step=step,
                attempt_id=attempt_id,
                lease_expires_at=lease_expires_at,
                now=now,
            )
        return ClaimRecord(
            work_item_id=str(work["work_item_id"]),
            project_key=str(work["project_key"]),
            run_id=str(work["run_id"]),
            step_id=None if work["step_id"] is None else str(work["step_id"]),
            assignment_digest=str(work["assignment_digest"]),
            attempt_id=attempt_id,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            reservation_id=None if reservation is None else reservation.reservation_id,
            assignment=assignment,
            claim_binding=claim_binding,
        )

    def _require_exact_bindings(
        self,
        work: Mapping[str, Any],
        *,
        assignment: RuntimeAssignment,
        control_scope: ControlPlaneScope,
        context: NodeClaimContext,
        now: Any,
    ) -> tuple[
        Mapping[str, Any],
        Mapping[str, Any] | None,
        Mapping[str, Any] | None,
        Mapping[str, Any],
    ]:
        runs = _table("runtime_runs")
        run = _one_mapping(
            self.connection.execute(
                select(runs)
                .where(
                    runs.c.project_key == work["project_key"],
                    runs.c.run_id == work["run_id"],
                )
                .with_for_update()
            )
        )
        if run is None or run["cancellation_requested"]:
            raise ClaimBindingMismatch("run is absent or cancellation was requested")
        self._require_run_execution_binding(work, run)
        if (
            run["incarnation"] != assignment.incarnation
            or run["program_digest"] != assignment.program_digest
            or int(run["execution_epoch"]) != assignment.execution_epoch
        ):
            raise ClaimBindingMismatch("assignment run incarnation/epoch/content drift")
        scopes = _table("project_scope_registry")
        scope = _one_mapping(
            self.connection.execute(
                select(scopes)
                .where(
                    scopes.c.project_key == run["project_key"],
                    scopes.c.registry_revision == run["project_registry_revision"],
                    scopes.c.state == "ACTIVE",
                )
                .with_for_update()
            )
        )
        if (
            scope is None
            or scope["scope_digest"] != run["project_scope_digest"]
            or scope["resolved_schema"] != run["resolved_schema"]
        ):
            raise ClaimBindingMismatch("run project-scope registry binding is stale")
        qualified_plan = self._require_exact_qualified_plan(
            work,
            assignment=assignment,
            run=run,
            resolved_schema=str(scope["resolved_schema"]),
            now=now,
        )

        authorities = _table("runtime_capability_authority")
        authority = _one_mapping(
            self.connection.execute(
                select(authorities)
                .where(
                    authorities.c.project_key == work["project_key"],
                    authorities.c.capability_id == work["capability_id"],
                )
                .with_for_update()
            )
        )
        if (
            authority is None
            or not authority["successor_claim_enabled"]
            or authority["legacy_claim_enabled"]
            or int(authority["authority_epoch"]) != control_scope.authority_epoch
        ):
            raise ClaimBindingMismatch("capability claim authority is stale")

        if work["step_id"] is None:
            return authority, None, None, run
        steps = _table("runtime_steps")
        step = _one_mapping(
            self.connection.execute(
                select(steps)
                .where(
                    steps.c.project_key == work["project_key"],
                    steps.c.run_id == work["run_id"],
                    steps.c.step_id == work["step_id"],
                )
                .with_for_update()
            )
        )
        kind = AssignmentKind(str(work["assignment_kind"]))
        expected_step_states = (
            {"RECONCILING", "WAITING_EXTERNAL"}
            if kind is AssignmentKind.RECONCILE
            else {"READY"}
        )
        if step is None or step["state"] not in expected_step_states:
            raise ClaimConflict("step revision/state no longer permits claim")
        if work["expected_step_revision"] is None or int(
            work["expected_step_revision"]
        ) != int(step["revision"]):
            raise ClaimBindingMismatch("work item expected step revision drift")
        if (
            int(step["execution_epoch"]) != assignment.execution_epoch
            or step["input_digest"] != assignment.input_closure_digest
        ):
            raise ClaimBindingMismatch("assignment step epoch/input closure drift")
        auths = _table("runtime_step_authorizations")
        authorization = _one_mapping(
            self.connection.execute(
                select(auths)
                .where(
                    auths.c.project_key == work["project_key"],
                    auths.c.run_id == work["run_id"],
                    auths.c.step_id == work["step_id"],
                    auths.c.capability_id == work["capability_id"],
                    auths.c.claim_owner == "successor",
                    auths.c.claim_authority_epoch == authority["authority_epoch"],
                    auths.c.operation_contract_digest
                    == work["operation_contract_digest"],
                    auths.c.authorization_digest == work["authority_digest"],
                    or_(auths.c.expires_at.is_(None), auths.c.expires_at > now),
                )
                .with_for_update()
            )
        )
        if authorization is None:
            raise ClaimBindingMismatch("exact current step authorization not found")
        authorization_binding = validate_authorization_row(authorization)
        if qualified_plan is not None:
            frozen_step_binding = qualified_plan.step_binding(str(work["step_id"]))
            if frozen_step_binding != authorization_binding:
                raise ClaimBindingMismatch(
                    "current step authorization is not the QualifiedPlan member"
                )
        if step["claim_policy_digest"] != authorization["claim_policy_digest"] or int(
            step["claim_authority_epoch"]
        ) != int(authorization["claim_authority_epoch"]):
            raise ClaimBindingMismatch("step authorization epoch/policy drift")
        if (
            authorization_binding.binding_digest != work["authority_digest"]
            or (
                kind is not AssignmentKind.RECONCILE
                and authorization_binding.interpreter_binding_digest
                != assignment.handler_binding_digest
            )
            or authorization_binding.deployment_catalog_digest
            != assignment.deployment_catalog_digest
            or authorization_binding.resource_policy_epoch
            != assignment.resource_policy_epoch
            or authorization_binding.queue_eligibility_digest
            != assignment.queue_eligibility_digest
            or authorization_binding.project_registry_revision
            != run["project_registry_revision"]
            or authorization_binding.project_scope_digest != run["project_scope_digest"]
            or authorization_binding.claim_authority_epoch
            != assignment.claim_authority_epoch
            or authorization_binding.claim_policy_digest
            != assignment.claim_policy_digest
        ):
            raise ClaimBindingMismatch("assignment/authorization exact binding drift")
        if kind is AssignmentKind.RECONCILE:
            attempts = _table("runtime_effect_attempts")
            original_attempt = _one_mapping(
                self.connection.execute(
                    select(attempts)
                    .where(
                        attempts.c.project_key == work["project_key"],
                        attempts.c.run_id == work["run_id"],
                        attempts.c.step_id == work["step_id"],
                        attempts.c.attempt_id == work["reconciliation_attempt_id"],
                        attempts.c.disposition == "OUTCOME_UNKNOWN",
                    )
                    .with_for_update()
                )
            )
            if original_attempt is None:
                raise ClaimBindingMismatch(
                    "RECONCILE requires the exact OUTCOME_UNKNOWN attempt"
                )
            if (
                original_attempt["handler_binding_digest"]
                != authorization_binding.interpreter_binding_digest
            ):
                raise ClaimBindingMismatch(
                    "RECONCILE original interpreter/authorization drift"
                )
        return authority, authorization, step, run

    def _require_exact_qualified_plan(
        self,
        work: Mapping[str, Any],
        *,
        assignment: RuntimeAssignment,
        run: Mapping[str, Any],
        resolved_schema: str,
        now: Any,
    ) -> QualifiedPlan | None:
        kind = assignment.assignment_kind
        if kind not in {
            AssignmentKind.INTERPRET,
            AssignmentKind.VERIFY_ADMIT,
            AssignmentKind.RECONCILE,
        }:
            return None

        plan_refs = _table("runtime_plan_refs")
        plan_ref = _one_mapping(
            self.connection.execute(
                select(plan_refs)
                .where(
                    plan_refs.c.project_key == work["project_key"],
                    plan_refs.c.plan_id == run["plan_id"],
                    plan_refs.c.plan_digest == run["plan_digest"],
                    plan_refs.c.program_id == run["program_id"],
                    plan_refs.c.program_digest == run["program_digest"],
                )
                .with_for_update()
            )
        )
        if plan_ref is None:
            raise ClaimBindingMismatch("exact public ExecutionPlan ref not found")

        tables = project_tables(MetaData(), resolved_schema)
        plan_table = tables.research_execution_plans
        plan_row = _one_mapping(
            self.connection.execute(
                select(plan_table)
                .where(
                    plan_table.c.project_key == work["project_key"],
                    plan_table.c.plan_id == run["plan_id"],
                    plan_table.c.plan_digest == run["plan_digest"],
                    plan_table.c.program_id == run["program_id"],
                    plan_table.c.program_digest == run["program_digest"],
                )
                .with_for_update()
            )
        )
        if plan_row is None:
            raise ClaimBindingMismatch("project exact ExecutionPlan not found")
        try:
            exact_plan = decode_plan(dict(plan_row["plan_json"]))
        except Exception as exc:
            raise ClaimBindingMismatch(
                "project ExecutionPlan content digest drift"
            ) from exc
        plan_columns = (
            "plan_id",
            "plan_digest",
            "program_id",
            "program_digest",
            "compiler_id",
            "compiler_version",
            "catalog_digest",
            "effect_closure_digest",
            "authority_closure_digest",
            "resource_closure_digest",
        )
        if any(plan_ref[column] != plan_row[column] for column in plan_columns):
            raise ClaimBindingMismatch("public/project ExecutionPlan ref drift")
        if (
            exact_plan.plan_id != run["plan_id"]
            or exact_plan.plan_digest != assignment.plan_digest
        ):
            raise ClaimBindingMismatch("assignment ExecutionPlan digest drift")

        qualifications = _table("runtime_qualifications")
        qualification = _one_mapping(
            self.connection.execute(
                select(qualifications)
                .where(
                    qualifications.c.project_key == work["project_key"],
                    qualifications.c.run_id == work["run_id"],
                    qualifications.c.plan_id == run["plan_id"],
                    qualifications.c.plan_digest == run["plan_digest"],
                    qualifications.c.qualification_digest
                    == run["qualification_digest"],
                    qualifications.c.decision == "QUALIFIED",
                )
                .with_for_update()
            )
        )
        if qualification is None:
            raise ClaimBindingMismatch("exact QUALIFIED plan binding not found")
        qualification_binding = validate_qualification_row(qualification)
        context = qualification_binding.authority_context
        qualified_plan = qualification_binding.qualified_plan
        if (
            qualified_plan.qualification_digest != work["qualification_digest"]
            or context.project_key != work["project_key"]
            or context.resolved_schema != resolved_schema
            or context.project_registry_revision != run["project_registry_revision"]
            or context.project_scope_digest != run["project_scope_digest"]
            or context.expires_at <= now
        ):
            raise ClaimBindingMismatch("qualification authority/plan binding drift")

        self._require_qualified_plan_closure(
            exact_plan,
            qualified_plan,
            project_key=str(work["project_key"]),
            run_id=str(work["run_id"]),
            project_registry_revision=int(run["project_registry_revision"]),
            project_scope_digest=str(run["project_scope_digest"]),
        )
        return qualified_plan

    @staticmethod
    def _require_qualified_plan_closure(
        exact_plan: Any,
        qualified_plan: QualifiedPlan,
        *,
        project_key: str,
        run_id: str,
        project_registry_revision: int,
        project_scope_digest: str,
    ) -> None:
        """Require exact per-step authorization closure for one plan."""

        authorizable_steps = {
            step.step_id: step
            for step in exact_plan.ordered_steps
            if step.step_kind in {"EFFECT", "ADMISSION"}
            and step.operation_contract_ref is not None
        }
        qualified_bindings = {
            binding.step_id: binding for binding in qualified_plan.step_bindings
        }
        if set(qualified_bindings) != set(authorizable_steps):
            raise ClaimBindingMismatch(
                "QualifiedPlan step authorization closure differs from exact ExecutionPlan"
            )
        if qualified_plan.awaiting_approval_steps or qualified_plan.denied_steps:
            raise ClaimBindingMismatch(
                "QUALIFIED plan cannot retain awaiting or denied steps"
            )
        for step_id, step in authorizable_steps.items():
            binding = qualified_bindings[step_id]
            contract_ref = step.operation_contract_ref
            assert contract_ref is not None
            if (
                binding.run_id != run_id
                or binding.project_key != project_key
                or binding.operation_kind != contract_ref.kind
                or binding.operation_contract_digest != contract_ref.contract_digest
                or binding.project_registry_revision != project_registry_revision
                or binding.project_scope_digest != project_scope_digest
            ):
                raise ClaimBindingMismatch(
                    f"QualifiedPlan step binding drift for {step_id}"
                )

    @staticmethod
    def _require_run_execution_binding(
        work: Mapping[str, Any], run: Mapping[str, Any]
    ) -> None:
        """Reject executable work detached from an admitted immutable plan."""

        kind = AssignmentKind(str(work["assignment_kind"]))
        if kind in {
            AssignmentKind.INTERPRET,
            AssignmentKind.VERIFY_ADMIT,
            AssignmentKind.RECONCILE,
        }:
            allowed_states = (
                {"RECONCILING"}
                if kind is AssignmentKind.RECONCILE
                else {"READY", "RUNNING", "WAITING"}
            )
            if run["state"] not in allowed_states:
                raise ClaimBindingMismatch(
                    f"{kind.value} cannot claim run state {run['state']}"
                )
            required = (
                run["plan_id"],
                run["plan_digest"],
                run["qualification_digest"],
                work["program_digest"],
                work["plan_digest"],
                work["qualification_digest"],
            )
            if any(value is None for value in required):
                raise ClaimBindingMismatch(
                    f"{kind.value} requires immutable plan and qualification binding"
                )
            if (
                work["program_digest"] != run["program_digest"]
                or work["plan_digest"] != run["plan_digest"]
                or work["qualification_digest"] != run["qualification_digest"]
            ):
                raise ClaimBindingMismatch(
                    f"{kind.value} run plan/qualification binding drift"
                )
        elif kind is AssignmentKind.MATERIALIZE_SUCCESSOR:
            if run["state"] != "COMPLETED":
                raise ClaimBindingMismatch(
                    "MATERIALIZE_SUCCESSOR requires a completed predecessor run"
                )
            required = (
                run["plan_id"],
                run["plan_digest"],
                run["qualification_digest"],
                work["program_digest"],
                work["plan_digest"],
                work["payload_ref"],
                work["payload_digest"],
            )
            if any(value is None for value in required):
                raise ClaimBindingMismatch(
                    "MATERIALIZE_SUCCESSOR requires exact predecessor and source bindings"
                )
            if (
                work["program_digest"] != run["program_digest"]
                or work["plan_digest"] != run["plan_digest"]
                or work["predecessor_plan_digest"] != run["plan_digest"]
                or work["source_value_digest"] != work["payload_digest"]
            ):
                raise ClaimBindingMismatch(
                    "MATERIALIZE_SUCCESSOR predecessor/source binding drift"
                )

    def _fair_capacity_available(
        self,
        work: Mapping[str, Any],
        *,
        fairness: FairSharePolicy,
    ) -> bool:
        """Recheck active ceilings under the locked project-scope row."""

        table = _table("runtime_work_items")
        max_project_active = fairness.max_project_active
        max_capability_active = fairness.max_capability_active
        if assignment_requires_reservation(str(work["assignment_kind"])):
            policies = _table("runtime_resource_policies")
            policy = _one_mapping(
                self.connection.execute(
                    select(policies)
                    .where(
                        policies.c.project_key == work["project_key"],
                        policies.c.capability_id == work["capability_id"],
                        policies.c.resource_class == work["resource_class"],
                        policies.c.policy_epoch == work["resource_policy_epoch"],
                        policies.c.policy_digest == work["resource_policy_digest"],
                    )
                    .with_for_update()
                )
            )
            if policy is None:
                raise ClaimBindingMismatch("exact resource/fairness policy is stale")
            max_project_active = min(
                max_project_active, int(policy["max_project_active"])
            )
            max_capability_active = min(
                max_capability_active, int(policy["max_capability_active"])
            )
        project_active = int(
            self.connection.scalar(
                select(func.count())
                .select_from(table)
                .where(
                    table.c.state == "CLAIMED",
                    table.c.project_key == work["project_key"],
                )
            )
            or 0
        )
        capability_active = int(
            self.connection.scalar(
                select(func.count())
                .select_from(table)
                .where(
                    table.c.state == "CLAIMED",
                    table.c.project_key == work["project_key"],
                    table.c.capability_id == work["capability_id"],
                )
            )
            or 0
        )
        return (
            project_active < max_project_active
            and capability_active < max_capability_active
        )

    @staticmethod
    def _claim_binding(
        assignment: RuntimeAssignment,
        *,
        context: NodeClaimContext,
        attempt_id: str,
        authorization_digest: str,
        lease_token: str,
        lease_expires_at: Any,
        reservation: ExecutionReservation | None,
    ) -> ClaimBinding:
        claim = ClaimBinding.bind(
            assignment,
            authorization_digest=authorization_digest,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            node_id=context.node_id,
            node_profile_digest=context.node_profile_digest,
            interpreter_profile_digest=(
                assignment.handler_binding.interpreter_profile_digest
                if hasattr(assignment.handler_binding, "interpreter_profile_digest")
                else None
            ),
            authority_digest=authorization_digest,
            execution_reservation_ref=(
                None if reservation is None else reservation.reservation_id
            ),
            execution_reservation_digest=(
                None if reservation is None else reservation.reservation_digest
            ),
        )
        if claim.attempt_id != attempt_id:
            raise ClaimBindingMismatch("ClaimBinding attempt derivation drift")
        return claim

    def _insert_attempt(
        self,
        work: Mapping[str, Any],
        run: Mapping[str, Any],
        step: Mapping[str, Any],
        authorization: Mapping[str, Any],
        claim_binding: ClaimBinding,
        now: Any,
    ) -> None:
        table = _table("runtime_effect_attempts")
        try:
            self.connection.execute(
                insert(table).values(
                    attempt_id=claim_binding.attempt_id,
                    project_key=work["project_key"],
                    run_id=work["run_id"],
                    step_id=work["step_id"],
                    execution_epoch=step["execution_epoch"],
                    incarnation=run["incarnation"],
                    assignment_digest=work["assignment_digest"],
                    handler_binding_digest=work["handler_binding_digest"],
                    handler_realization_digest=work["handler_binding_digest"],
                    idempotency_key=f"attempt:sha256:{claim_binding.attempt_id}",
                    authorization_digest=authorization["authorization_digest"],
                    input_digest=step["input_digest"],
                    claim_binding_json=claim_binding.model_dump(mode="json"),
                    claim_binding_digest=claim_binding.binding_digest,
                    delivery_intent_ref=work["delivery_intent_ref"],
                    disposition="NOT_STARTED",
                    created_at=now,
                    updated_at=now,
                )
            )
        except IntegrityError as exc:
            raise ClaimConflict("duplicate effect attempt claim") from exc

    def _eligibility(
        self, work: Mapping[str, Any], step: Mapping[str, Any]
    ) -> tuple[QueueEligibility, Mapping[str, Any]]:
        units_value = work["resource_units"]
        if units_value is None or int(units_value) != units_value:
            raise ClaimBindingMismatch("queue eligibility units must be an integer")
        eligibility = QueueEligibility(
            project_key=str(work["project_key"]),
            capability_id=str(work["capability_id"]),
            resource_class=ResourceClass(str(work["resource_class"])),
            units=int(units_value),
            policy_epoch=int(work["resource_policy_epoch"]),
            policy_digest=str(work["resource_policy_digest"]),
            concurrency_key=(
                None
                if work["concurrency_key"] is None
                else str(work["concurrency_key"])
            ),
            provider_key=(
                None if work["provider_key"] is None else str(work["provider_key"])
            ),
        )
        if eligibility.eligibility_digest != work["queue_eligibility_digest"]:
            raise ClaimBindingMismatch("frozen queue eligibility digest drift")
        if (
            step["resource_class"] != eligibility.resource_class.value
            or step["concurrency_key"] != eligibility.concurrency_key
        ):
            raise ClaimBindingMismatch(
                "step resource binding differs from qualification"
            )
        policies = _table("runtime_resource_policies")
        policy = _one_mapping(
            self.connection.execute(
                select(policies)
                .where(
                    policies.c.project_key == work["project_key"],
                    policies.c.capability_id == work["capability_id"],
                    policies.c.resource_class == eligibility.resource_class.value,
                    policies.c.policy_epoch == eligibility.policy_epoch,
                    policies.c.policy_digest == work["resource_policy_digest"],
                )
                .with_for_update()
            )
        )
        if policy is None:
            raise ClaimBindingMismatch("exact resource policy is stale")
        return eligibility, policy

    def _record_resource_wait(self, work: Mapping[str, Any], now: Any) -> None:
        table = _table("runtime_work_items")
        # The frozen schema represents an observation through WAITING, then a
        # bounded external retry transition returns it to READY.  No lease or
        # reservation has been acquired at this point.
        result = self.connection.execute(
            update(table)
            .where(
                table.c.work_item_id == work["work_item_id"],
                or_(
                    table.c.state == "READY",
                    and_(
                        table.c.state == "WAITING",
                        table.c.wait_reason == "RESOURCE_LIMIT",
                    ),
                ),
                table.c.revision == work["revision"],
                table.c.assignment_digest == work["assignment_digest"],
                table.c.lease_token.is_(None),
            )
            .values(
                state="WAITING",
                wait_reason="RESOURCE_LIMIT",
                due_at=now + timedelta(seconds=1),
                revision=int(work["revision"]) + 1,
                updated_at=now,
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise ClaimConflict("resource wait observation CAS failed")

    def _claim_work_cas(
        self,
        work: Mapping[str, Any],
        context: NodeClaimContext,
        claim_binding: ClaimBinding,
        lease_token: str,
        lease_expires_at: Any,
        now: Any,
    ) -> None:
        table = _table("runtime_work_items")
        result = self.connection.execute(
            update(table)
            .where(
                table.c.work_item_id == work["work_item_id"],
                or_(
                    table.c.state == "READY",
                    and_(
                        table.c.state == "WAITING",
                        table.c.wait_reason == "RESOURCE_LIMIT",
                    ),
                ),
                table.c.revision == work["revision"],
                table.c.assignment_digest == work["assignment_digest"],
                table.c.handler_binding_digest == work["handler_binding_digest"],
                or_(table.c.deadline_at.is_(None), table.c.deadline_at > now),
                or_(table.c.lease_token.is_(None), table.c.lease_expires_at <= now),
            )
            .values(
                state="CLAIMED",
                wait_reason=None,
                attempt_count=int(work["attempt_count"]) + 1,
                revision=int(work["revision"]) + 1,
                lease_token=lease_token,
                lease_owner=context.node_id,
                lease_expires_at=lease_expires_at,
                claim_attempt_id=claim_binding.attempt_id,
                claim_binding_json=claim_binding.model_dump(mode="json"),
                claim_binding_digest=claim_binding.binding_digest,
                updated_at=now,
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise ClaimConflict("duplicate/stale work-item claim CAS failed")

    def _insert_lease_expiry_reconcile(
        self,
        work: Mapping[str, Any],
        *,
        assignment: RuntimeAssignment,
        step: Mapping[str, Any],
        attempt_id: str,
        lease_expires_at: Any,
        now: Any,
    ) -> str:
        """Persist the exact recovery assignment before the effect may start."""

        recovery_raw = work["recovery_binding_json"]
        try:
            recovery = RecoveryBinding.model_validate(recovery_raw)
        except Exception as exc:
            raise ClaimBindingMismatch(
                "effect assignment lacks exact recovery binding"
            ) from exc
        recovery_ref = f"handler-binding:sha256:{recovery.binding_digest}"
        readback_ref = recovery.authoritative_readback_profile_ref
        if (
            work["recovery_handler_binding_ref"] != recovery_ref
            or work["recovery_handler_binding_digest"] != recovery.binding_digest
            or work["authoritative_readback_profile_ref"] != readback_ref
        ):
            raise ClaimBindingMismatch("effect assignment lacks exact recovery binding")
        work_item_id = f"reconcile:{attempt_id}"
        recovery_assignment = RuntimeAssignment(
            runtime_protocol_version=assignment.runtime_protocol_version,
            work_item_id=work_item_id,
            assignment_kind=AssignmentKind.RECONCILE,
            project_key=assignment.project_key,
            run_id=assignment.run_id,
            step_id=assignment.step_id,
            step_role=assignment.step_role,
            capability_id=assignment.capability_id,
            operation_contract_ref=assignment.operation_contract_ref,
            operation_contract_digest=assignment.operation_contract_digest,
            return_contract_binding=assignment.return_contract_binding,
            handler_binding_kind="RECOVERY",
            handler_binding_ref=recovery_ref,
            handler_binding_digest=recovery.binding_digest,
            handler_binding=recovery,
            program_digest=assignment.program_digest,
            plan_digest=assignment.plan_digest,
            deployment_catalog_digest=assignment.deployment_catalog_digest,
            execution_epoch=assignment.execution_epoch,
            incarnation=assignment.incarnation,
            input_refs=assignment.input_refs,
            input_closure_digest=assignment.input_closure_digest,
            payload_ref=assignment.payload_ref,
            payload_digest=assignment.payload_digest,
            queue_eligibility_digest=assignment.queue_eligibility_digest,
            resource_policy_epoch=assignment.resource_policy_epoch,
            claim_authority_epoch=assignment.claim_authority_epoch,
            claim_policy_digest=assignment.claim_policy_digest,
            # The ordinary started path moves READY r -> CLAIMED r+1 ->
            # RUNNING r+2 -> RECONCILING r+3.  Lease-expiry recovery may stop
            # earlier; its reaper supersedes this immutable trigger with a
            # revision-exact successor assignment before making it READY.
            expected_step_revision=int(step["revision"]) + 3,
            reconciliation_attempt_id=attempt_id,
            deadline_at=assignment.deadline_at,
            trace_id=assignment.trace_id,
        )
        table = _table("runtime_work_items")
        self.connection.execute(
            insert(table).values(
                work_item_id=work_item_id,
                project_key=work["project_key"],
                run_id=work["run_id"],
                step_id=work["step_id"],
                assignment_kind=AssignmentKind.RECONCILE.value,
                capability_id=work["capability_id"],
                operation_contract_digest=work["operation_contract_digest"],
                assignment_digest=recovery_assignment.assignment_digest,
                assignment_binding_json=recovery_assignment.model_dump(mode="json"),
                execution_epoch=recovery_assignment.execution_epoch,
                assignment_incarnation=recovery_assignment.incarnation,
                input_closure_digest=recovery_assignment.input_closure_digest,
                claim_authority_epoch=recovery_assignment.claim_authority_epoch,
                claim_policy_digest=recovery_assignment.claim_policy_digest,
                handler_binding_kind="RECOVERY",
                handler_binding_ref=recovery_ref,
                handler_binding_digest=recovery.binding_digest,
                deployment_catalog_digest=work["deployment_catalog_digest"],
                runtime_protocol_version=work["runtime_protocol_version"],
                interpreter_profile_digest=work["interpreter_profile_digest"],
                required_node_profile_selector=work["required_node_profile_selector"],
                program_digest=work["program_digest"],
                plan_digest=work["plan_digest"],
                qualification_digest=work["qualification_digest"],
                expected_step_revision=int(step["revision"]) + 3,
                reconciliation_attempt_id=attempt_id,
                payload_ref=recovery_assignment.payload_ref,
                payload_digest=recovery_assignment.payload_digest,
                delivery_intent_ref=work["delivery_intent_ref"],
                authority_digest=work["authority_digest"],
                resource_policy_digest=work["resource_policy_digest"],
                resource_policy_epoch=work["resource_policy_epoch"],
                queue_eligibility_digest=work["queue_eligibility_digest"],
                authoritative_readback_profile_ref=readback_ref,
                fairness_key=work["fairness_key"],
                state="PENDING",
                declared_priority=work["declared_priority"],
                enqueued_at=now,
                due_at=lease_expires_at,
                deadline_at=recovery_assignment.deadline_at,
                attempt_count=0,
                revision=0,
                created_at=now,
                updated_at=now,
            )
        )
        return work_item_id

    def heartbeat(
        self,
        control_scope: ControlPlaneScope,
        work_item_id: str,
        lease_token: str,
        *,
        expected_revision: int,
        new_expiry: Any,
    ) -> Mapping[str, Any]:
        """Extend a live claim only for the exact token and revision."""

        control_scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)
        table = _table("runtime_work_items")
        observed_at = _utcnow()
        locked = _one_mapping(
            self.connection.execute(
                select(table)
                .where(table.c.work_item_id == work_item_id)
                .with_for_update()
            )
        )
        if (
            locked is None
            or locked["state"] != "CLAIMED"
            or locked["lease_token"] != lease_token
            or int(locked["revision"]) != expected_revision
            or locked["lease_expires_at"] <= observed_at
        ):
            raise ClaimConflict("work-item heartbeat token/revision CAS failed")
        previous_claim = ClaimBinding.model_validate(locked["claim_binding_json"])
        claim_content = previous_claim.model_dump(mode="python")
        claim_content.pop("binding_digest")
        claim_content["lease_expires_at"] = new_expiry
        provisional = ClaimBinding.model_construct(
            **claim_content,
            binding_digest="0" * 64,
        )
        renewed_claim = ClaimBinding(
            **claim_content,
            binding_digest=canonical_digest(
                provisional,
                exclude_fields={"binding_digest"},
            ),
        )
        result = self.connection.execute(
            update(table)
            .where(
                table.c.work_item_id == work_item_id,
                table.c.state == "CLAIMED",
                table.c.lease_token == lease_token,
                table.c.revision == expected_revision,
                table.c.lease_expires_at > observed_at,
            )
            .values(
                lease_expires_at=new_expiry,
                claim_binding_json=renewed_claim.model_dump(mode="json"),
                claim_binding_digest=renewed_claim.binding_digest,
                revision=expected_revision + 1,
                updated_at=observed_at,
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise ClaimConflict("work-item heartbeat token/revision CAS failed")

        steps = _table("runtime_steps")
        if locked["step_id"] is not None:
            step_result = self.connection.execute(
                update(steps)
                .where(
                    steps.c.project_key == locked["project_key"],
                    steps.c.run_id == locked["run_id"],
                    steps.c.step_id == locked["step_id"],
                    steps.c.lease_token == lease_token,
                    steps.c.state.in_(
                        (
                            "CLAIMED",
                            "RUNNING",
                            "COMMITTING",
                            "RECONCILING",
                            "CANCEL_REQUESTED",
                        )
                    ),
                )
                .values(
                    lease_expires_at=new_expiry,
                    heartbeat_at=observed_at,
                    updated_at=observed_at,
                )
            )
            if getattr(step_result, "rowcount", None) != 1:
                raise ClaimConflict("step heartbeat lease binding drift")

        reservations = _table("runtime_resource_reservations")
        self.connection.execute(
            update(reservations)
            .where(
                reservations.c.project_key == locked["project_key"],
                reservations.c.work_item_id == work_item_id,
                reservations.c.lease_token == lease_token,
                reservations.c.state == "ACTIVE",
            )
            .values(
                lease_expires_at=new_expiry,
                revision=reservations.c.revision + 1,
                updated_at=observed_at,
            )
        )
        if locked["claim_attempt_id"] is not None:
            attempts = _table("runtime_effect_attempts")
            self.connection.execute(
                update(attempts)
                .where(
                    attempts.c.project_key == locked["project_key"],
                    attempts.c.attempt_id == locked["claim_attempt_id"],
                    attempts.c.claim_binding_digest == previous_claim.binding_digest,
                    attempts.c.disposition.in_(("NOT_STARTED", "IN_FLIGHT")),
                )
                .values(
                    claim_binding_json=renewed_claim.model_dump(mode="json"),
                    claim_binding_digest=renewed_claim.binding_digest,
                    revision=attempts.c.revision + 1,
                    updated_at=observed_at,
                )
            )
            self.connection.execute(
                update(table)
                .where(
                    table.c.assignment_kind == AssignmentKind.RECONCILE.value,
                    table.c.reconciliation_attempt_id == locked["claim_attempt_id"],
                    table.c.state == "PENDING",
                )
                .values(due_at=new_expiry, updated_at=observed_at)
            )
        row = _one_mapping(
            self.connection.execute(
                select(table).where(table.c.work_item_id == work_item_id)
            )
        )
        assert row is not None
        return row

    def release(
        self,
        scope: RuntimeScope,
        work_item_id: str,
        lease_token: str,
        *,
        expected_revision: int,
        terminal_state: str,
        now: Any | None = None,
    ) -> Mapping[str, Any]:
        """Release a claim; stale or duplicate releases fail closed."""

        if terminal_state not in {"READY", "COMPLETED", "FAILED", "CANCELLED"}:
            raise ValueError("invalid work-item release state")
        observed_at = now or _utcnow()
        table = _table("runtime_work_items")
        project_key = scope.project_scope.project_key
        locked = _one_mapping(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == project_key,
                    table.c.work_item_id == work_item_id,
                )
                .with_for_update()
            )
        )
        if locked is None:
            raise RecordNotFound(f"runtime work item not found: {work_item_id}")
        if terminal_state == "READY" and assignment_requires_reservation(
            str(locked["assignment_kind"])
        ):
            raise ClaimConflict(
                "effect assignment cannot return to READY without NonStartProof"
            )
        result = self.connection.execute(
            update(table)
            .where(
                table.c.project_key == project_key,
                table.c.work_item_id == work_item_id,
                table.c.state == "CLAIMED",
                table.c.lease_token == lease_token,
                table.c.revision == expected_revision,
            )
            .values(
                state=terminal_state,
                wait_reason=None,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                revision=expected_revision + 1,
                updated_at=observed_at,
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise ClaimConflict("work-item release token/revision CAS failed")
        if locked["step_id"] is not None:
            step_state = {
                "READY": "READY",
                "COMPLETED": "SUCCEEDED",
                "FAILED": "FAILED",
                "CANCELLED": "CANCELLED",
            }[terminal_state]
            steps = _table("runtime_steps")
            self.connection.execute(
                update(steps)
                .where(
                    steps.c.project_key == locked["project_key"],
                    steps.c.run_id == locked["run_id"],
                    steps.c.step_id == locked["step_id"],
                    steps.c.lease_token == lease_token,
                )
                .values(
                    state=step_state,
                    lease_token=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    finished_at=(observed_at if terminal_state != "READY" else None),
                    revision=steps.c.revision + 1,
                    updated_at=observed_at,
                )
            )
        reservations = _table("runtime_resource_reservations")
        self.connection.execute(
            update(reservations)
            .where(
                reservations.c.project_key == locked["project_key"],
                reservations.c.work_item_id == work_item_id,
                reservations.c.lease_token == lease_token,
                reservations.c.state == "ACTIVE",
            )
            .values(
                state="RELEASED",
                released_at=observed_at,
                release_reason=f"WORK_ITEM_{terminal_state}",
                revision=reservations.c.revision + 1,
                updated_at=observed_at,
            )
        )
        if locked["claim_attempt_id"] is not None:
            self.connection.execute(
                update(table)
                .where(
                    table.c.assignment_kind == AssignmentKind.RECONCILE.value,
                    table.c.reconciliation_attempt_id == locked["claim_attempt_id"],
                    table.c.state == "PENDING",
                )
                .values(
                    state="CANCELLED",
                    updated_at=observed_at,
                    revision=table.c.revision + 1,
                )
            )
        row = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == project_key,
                    table.c.work_item_id == work_item_id,
                )
            )
        )
        assert row is not None
        return row

    def reap_expired(
        self,
        control_scope: ControlPlaneScope,
        *,
        now: Any,
        limit: int = 128,
    ) -> tuple[str, ...]:
        """Converge expired claims without treating lease loss as NOT_STARTED."""

        control_scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)
        if limit <= 0:
            return ()
        table = _table("runtime_work_items")
        locked = _mapping_rows(
            self.connection.execute(
                select(table)
                .where(table.c.state == "CLAIMED", table.c.lease_expires_at <= now)
                .order_by(table.c.lease_expires_at, table.c.work_item_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        reaped: list[str] = []
        for row in locked:
            kind = AssignmentKind(str(row["assignment_kind"]))
            if assignment_requires_reservation(kind):
                self._reap_effect_claim(row, now=now)
            else:
                self._requeue_non_effect_claim(row, now=now)
            reaped.append(str(row["work_item_id"]))
        return tuple(reaped)

    def _reap_effect_claim(self, work: Mapping[str, Any], *, now: Any) -> None:
        attempt_id = work["claim_attempt_id"]
        if not attempt_id or not work["lease_token"] or work["step_id"] is None:
            raise ClaimBindingMismatch(
                "expired effect claim lacks exact claim identity"
            )

        table = _table("runtime_work_items")
        reconcile = _one_mapping(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == work["project_key"],
                    table.c.run_id == work["run_id"],
                    table.c.step_id == work["step_id"],
                    table.c.assignment_kind == AssignmentKind.RECONCILE.value,
                    table.c.reconciliation_attempt_id == attempt_id,
                    table.c.state == "PENDING",
                )
                .with_for_update()
            )
        )
        if reconcile is None:
            raise ClaimBindingMismatch(
                "expired effect claim has no durable exact RECONCILE assignment"
            )

        attempts = _table("runtime_effect_attempts")
        attempt = _one_mapping(
            self.connection.execute(
                select(attempts)
                .where(
                    attempts.c.project_key == work["project_key"],
                    attempts.c.attempt_id == attempt_id,
                )
                .with_for_update()
            )
        )
        if (
            attempt is None
            or attempt["assignment_digest"] != work["assignment_digest"]
            or attempt["handler_binding_digest"] != work["handler_binding_digest"]
        ):
            raise ClaimBindingMismatch("expired effect attempt exact binding drift")
        outcome_unknown = attempt["disposition"] in {"NOT_STARTED", "IN_FLIGHT"}
        if outcome_unknown:
            self.connection.execute(
                update(attempts)
                .where(
                    attempts.c.project_key == work["project_key"],
                    attempts.c.attempt_id == attempt_id,
                    attempts.c.revision == attempt["revision"],
                    attempts.c.disposition.in_(("NOT_STARTED", "IN_FLIGHT")),
                )
                .values(
                    disposition="OUTCOME_UNKNOWN",
                    revision=int(attempt["revision"]) + 1,
                    updated_at=now,
                )
            )
        elif attempt["disposition"] not in {
            "OUTCOME_UNKNOWN",
            "SUCCEEDED",
            "FAILED",
        }:
            raise ClaimBindingMismatch("expired effect attempt disposition is invalid")

        steps = _table("runtime_steps")
        step = _one_mapping(
            self.connection.execute(
                select(steps)
                .where(
                    steps.c.project_key == work["project_key"],
                    steps.c.run_id == work["run_id"],
                    steps.c.step_id == work["step_id"],
                )
                .with_for_update()
            )
        )
        if (
            step is None
            or step["state"] not in {"CLAIMED", "RUNNING"}
            or step["lease_token"] != work["lease_token"]
        ):
            raise ClaimBindingMismatch("expired effect step lease binding drift")
        if step["state"] == "RUNNING":
            reduced = reduce_step(
                StepSnapshot(
                    step_id=str(step["step_id"]),
                    state=StepState.RUNNING,
                    effect_disposition=EffectDisposition(str(attempt["disposition"])),
                    revision=int(step["revision"]),
                ),
                StepEvent.EFFECT_RECEIPT_LOST,
                StepState.RECONCILING,
                guard=True,
            )
            next_step_revision = reduced.revision
            next_step_state = reduced.state.value
        else:
            # P0-B pre-start lease expiry predates the P0-C lifecycle start
            # transition.  It still converges through exact readback without
            # inventing an EffectStarted observation.
            next_step_revision = int(step["revision"]) + 1
            next_step_state = StepState.RECONCILING.value
        validate_runtime_assignment_row(reconcile)
        step_result = self.connection.execute(
            update(steps)
            .where(
                steps.c.project_key == work["project_key"],
                steps.c.run_id == work["run_id"],
                steps.c.step_id == work["step_id"],
                steps.c.revision == step["revision"],
                steps.c.state == step["state"],
                steps.c.lease_token == work["lease_token"],
            )
            .values(
                state=next_step_state,
                revision=next_step_revision,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        if getattr(step_result, "rowcount", None) != 1:
            raise ClaimConflict("expired effect step CAS failed")

        reservations = _table("runtime_resource_reservations")
        self.connection.execute(
            update(reservations)
            .where(
                reservations.c.project_key == work["project_key"],
                reservations.c.work_item_id == work["work_item_id"],
                reservations.c.attempt_id == attempt_id,
                reservations.c.lease_token == work["lease_token"],
                reservations.c.state == "ACTIVE",
            )
            .values(
                state="EXPIRED",
                released_at=now,
                release_reason="LEASE_EXPIRED_OUTCOME_UNKNOWN",
                revision=reservations.c.revision + 1,
                updated_at=now,
            )
        )

        reconcile_work_item_id = self._supersede_reconcile_trigger(
            reconcile,
            next_step_revision=next_step_revision,
            now=now,
        )

        original_result = self.connection.execute(
            update(table)
            .where(
                table.c.work_item_id == work["work_item_id"],
                table.c.state == "CLAIMED",
                table.c.revision == work["revision"],
                table.c.lease_token == work["lease_token"],
                table.c.lease_expires_at <= now,
            )
            .values(
                state="WAITING",
                wait_reason="BACKOFF",
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                last_failure_ref=f"reconcile-work-item:{reconcile_work_item_id}",
                revision=int(work["revision"]) + 1,
                updated_at=now,
            )
        )
        if getattr(original_result, "rowcount", None) != 1:
            raise ClaimConflict("expired effect work-item CAS failed")
        self._append_lease_expired_event(
            work,
            attempt_id=str(attempt_id),
            reconcile_work_item_id=reconcile_work_item_id,
            outcome_unknown=outcome_unknown
            or attempt["disposition"] == "OUTCOME_UNKNOWN",
            now=now,
        )

    def _supersede_reconcile_trigger(
        self,
        trigger: Mapping[str, Any],
        *,
        next_step_revision: int,
        now: Any,
    ) -> str:
        """Bind recovery to the new step revision via a successor assignment."""

        trigger_assignment = validate_runtime_assignment_row(trigger)
        successor_work_item_id = (
            f"reconcile:{trigger_assignment.reconciliation_attempt_id}:"
            f"revision:{next_step_revision}"
        )
        assignment_values = trigger_assignment.model_dump(mode="python")
        assignment_values.update(
            work_item_id=successor_work_item_id,
            expected_step_revision=next_step_revision,
        )
        successor = RuntimeAssignment(**assignment_values)
        table = _table("runtime_work_items")
        superseded = self.connection.execute(
            update(table)
            .where(
                table.c.work_item_id == trigger["work_item_id"],
                table.c.state == "PENDING",
                table.c.revision == trigger["revision"],
            )
            .values(
                state="SUPERSEDED",
                last_failure_ref=f"successor-work-item:{successor_work_item_id}",
                revision=int(trigger["revision"]) + 1,
                updated_at=now,
            )
        )
        if getattr(superseded, "rowcount", None) != 1:
            raise ClaimConflict("durable RECONCILE trigger supersede CAS failed")
        self.connection.execute(
            insert(table).values(
                work_item_id=successor.work_item_id,
                project_key=successor.project_key,
                run_id=successor.run_id,
                step_id=successor.step_id,
                assignment_kind=successor.assignment_kind.value,
                capability_id=successor.capability_id,
                operation_contract_digest=successor.operation_contract_digest,
                assignment_digest=successor.assignment_digest,
                assignment_binding_json=successor.model_dump(mode="json"),
                execution_epoch=successor.execution_epoch,
                assignment_incarnation=successor.incarnation,
                input_closure_digest=successor.input_closure_digest,
                claim_authority_epoch=successor.claim_authority_epoch,
                claim_policy_digest=successor.claim_policy_digest,
                handler_binding_kind=successor.handler_binding_kind.value,
                handler_binding_ref=successor.handler_binding_ref,
                handler_binding_digest=successor.handler_binding_digest,
                deployment_catalog_digest=successor.deployment_catalog_digest,
                runtime_protocol_version=successor.runtime_protocol_version,
                interpreter_profile_digest=trigger["interpreter_profile_digest"],
                required_node_profile_selector=trigger[
                    "required_node_profile_selector"
                ],
                program_digest=successor.program_digest,
                plan_digest=successor.plan_digest,
                qualification_digest=trigger["qualification_digest"],
                expected_step_revision=successor.expected_step_revision,
                reconciliation_attempt_id=successor.reconciliation_attempt_id,
                payload_ref=successor.payload_ref,
                payload_digest=successor.payload_digest,
                delivery_intent_ref=trigger["delivery_intent_ref"],
                authority_digest=trigger["authority_digest"],
                resource_policy_digest=trigger["resource_policy_digest"],
                resource_policy_epoch=successor.resource_policy_epoch,
                queue_eligibility_digest=successor.queue_eligibility_digest,
                authoritative_readback_profile_ref=trigger[
                    "authoritative_readback_profile_ref"
                ],
                fairness_key=trigger["fairness_key"],
                state="READY",
                declared_priority=trigger["declared_priority"],
                enqueued_at=now,
                due_at=now,
                attempt_count=0,
                revision=0,
                deadline_at=successor.deadline_at,
                last_failure_ref=f"superseded-trigger:{trigger['work_item_id']}",
                created_at=now,
                updated_at=now,
            )
        )
        return successor_work_item_id

    def _requeue_non_effect_claim(self, work: Mapping[str, Any], *, now: Any) -> None:
        table = _table("runtime_work_items")
        step: Mapping[str, Any] | None = None
        next_step_revision: int | None = None
        if work["step_id"] is not None:
            steps = _table("runtime_steps")
            step = _one_mapping(
                self.connection.execute(
                    select(steps)
                    .where(
                        steps.c.project_key == work["project_key"],
                        steps.c.run_id == work["run_id"],
                        steps.c.step_id == work["step_id"],
                    )
                    .with_for_update()
                )
            )
            if step is None or step["lease_token"] != work["lease_token"]:
                raise ClaimBindingMismatch("expired non-effect step lease drift")
            next_step_revision = int(step["revision"]) + 1
        if (
            work["assignment_kind"] == AssignmentKind.RECONCILE.value
            and step is not None
            and next_step_revision is not None
        ):
            self._supersede_expired_reconcile_claim(
                work,
                step=step,
                next_step_revision=next_step_revision,
                now=now,
            )
            return
        result = self.connection.execute(
            update(table)
            .where(
                table.c.work_item_id == work["work_item_id"],
                table.c.state == "CLAIMED",
                table.c.revision == work["revision"],
                table.c.lease_token == work["lease_token"],
                table.c.lease_expires_at <= now,
            )
            .values(
                state="READY",
                wait_reason=None,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                expected_step_revision=next_step_revision,
                revision=int(work["revision"]) + 1,
                updated_at=now,
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise ClaimConflict("expired non-effect work-item CAS failed")
        if step is not None:
            steps = _table("runtime_steps")
            target_state = (
                "RECONCILING"
                if work["assignment_kind"] == AssignmentKind.RECONCILE.value
                else "READY"
            )
            self.connection.execute(
                update(steps)
                .where(
                    steps.c.project_key == work["project_key"],
                    steps.c.run_id == work["run_id"],
                    steps.c.step_id == work["step_id"],
                    steps.c.lease_token == work["lease_token"],
                    steps.c.revision == step["revision"],
                )
                .values(
                    state=target_state,
                    lease_token=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    revision=next_step_revision,
                    updated_at=now,
                )
            )

    def _supersede_expired_reconcile_claim(
        self,
        work: Mapping[str, Any],
        *,
        step: Mapping[str, Any],
        next_step_revision: int,
        now: Any,
    ) -> None:
        assignment = validate_runtime_assignment_row(work)
        binding = assignment.handler_binding
        if not isinstance(binding, RecoveryBinding):
            raise ClaimBindingMismatch(
                "expired RECONCILE work lacks exact RecoveryBinding"
            )
        successor_id = "reconcile:sha256:" + canonical_digest(
            {
                "schema_version": "mrw.expired-reconciliation-successor.v1",
                "prior_work_item_id": assignment.work_item_id,
                "target_attempt_id": assignment.reconciliation_attempt_id,
                "expected_step_revision": next_step_revision,
            }
        )
        values = assignment.model_dump(mode="python")
        values.update(
            work_item_id=successor_id,
            expected_step_revision=next_step_revision,
        )
        successor = RuntimeAssignment(**values)
        envelope = AssignmentEnvelope(
            assignment=successor,
            required_node_profile_selector=str(work["required_node_profile_selector"]),
            authority_digest=str(work["authority_digest"]),
            resource_policy_digest=str(work["resource_policy_digest"]),
            fairness_key=str(work["fairness_key"]),
            qualification_digest=str(work["qualification_digest"]),
            resource_class=work["resource_class"],
            resource_units=work["resource_units"],
            concurrency_key=work["concurrency_key"],
            provider_key=work["provider_key"],
            recovery_binding=binding,
            authoritative_readback_profile_ref=(
                binding.authoritative_readback_profile_ref
            ),
            delivery_intent_ref=work["delivery_intent_ref"],
            declared_priority=int(work["declared_priority"]),
        )
        successor_values = _assignment_values(envelope, due_at=now)
        table = _table("runtime_work_items")
        replaced = self.connection.execute(
            update(table)
            .where(
                table.c.project_key == work["project_key"],
                table.c.work_item_id == work["work_item_id"],
                table.c.state == "CLAIMED",
                table.c.revision == work["revision"],
                table.c.lease_token == work["lease_token"],
                table.c.lease_expires_at <= now,
            )
            .values(
                state="SUPERSEDED",
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                last_failure_ref=f"successor-work-item:{successor_id}",
                revision=int(work["revision"]) + 1,
                updated_at=now,
            )
        )
        if getattr(replaced, "rowcount", None) != 1:
            raise ClaimConflict("expired RECONCILE work supersede CAS failed")
        self.connection.execute(insert(table).values(**successor_values))
        steps = _table("runtime_steps")
        released = self.connection.execute(
            update(steps)
            .where(
                steps.c.project_key == work["project_key"],
                steps.c.run_id == work["run_id"],
                steps.c.step_id == work["step_id"],
                steps.c.state == "RECONCILING",
                steps.c.revision == step["revision"],
                steps.c.lease_token == work["lease_token"],
            )
            .values(
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                revision=next_step_revision,
                updated_at=now,
            )
        )
        if getattr(released, "rowcount", None) != 1:
            raise ClaimConflict("expired RECONCILE step release CAS failed")
        self._append_lease_expired_event(
            work,
            attempt_id=str(work["reconciliation_attempt_id"]),
            reconcile_work_item_id=successor_id,
            outcome_unknown=True,
            now=now,
        )

    def _append_lease_expired_event(
        self,
        work: Mapping[str, Any],
        *,
        attempt_id: str,
        reconcile_work_item_id: str,
        outcome_unknown: bool,
        now: Any,
    ) -> None:
        runs = _table("runtime_runs")
        run = _one_mapping(
            self.connection.execute(
                select(runs)
                .where(
                    runs.c.project_key == work["project_key"],
                    runs.c.run_id == work["run_id"],
                )
                .with_for_update()
            )
        )
        if run is None:
            raise RecordNotFound(f"runtime run not found: {work['run_id']}")
        seq = int(run["next_event_seq"])
        result = self.connection.execute(
            update(runs)
            .where(
                runs.c.project_key == work["project_key"],
                runs.c.run_id == work["run_id"],
                runs.c.revision == run["revision"],
                runs.c.next_event_seq == seq,
            )
            .values(
                state="RECONCILING",
                revision=int(run["revision"]) + 1,
                next_event_seq=seq + 1,
                updated_at=now,
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise ClaimConflict("lease-expiry event run CAS failed")
        events = _table("runtime_events")
        event_type = (
            "LeaseExpiredOutcomeUnknown"
            if outcome_unknown
            else "LeaseExpiredReconcileRequired"
        )
        reason_code = (
            "LEASE_EXPIRED_OUTCOME_UNKNOWN"
            if outcome_unknown
            else "LEASE_EXPIRED_TERMINAL_ATTEMPT_RECONCILE"
        )
        self.connection.execute(
            insert(events).values(
                project_key=work["project_key"],
                run_id=work["run_id"],
                seq=seq,
                event_type=event_type,
                schema_version="mrw.runtime.event.lease_expired.v1",
                step_id=work["step_id"],
                attempt_id=attempt_id,
                event_metadata_json={
                    "work_item_id": work["work_item_id"],
                    "reconcile_work_item_id": reconcile_work_item_id,
                    "reason_code": reason_code,
                },
                authority_digest=work["authority_digest"],
                created_at=now,
                updated_at=now,
            )
        )

    def _claim_step_and_append_event(
        self,
        work: Mapping[str, Any],
        step: Mapping[str, Any],
        run: Mapping[str, Any],
        *,
        context: NodeClaimContext,
        attempt_id: str | None,
        lease_token: str,
        lease_expires_at: Any,
        authority_digest: str,
        now: Any,
    ) -> None:
        steps = _table("runtime_steps")
        revision = int(step["revision"])
        kind = AssignmentKind(str(work["assignment_kind"]))
        expected_state = str(step["state"])
        claimed_state = "CLAIMED"
        if kind is AssignmentKind.RECONCILE:
            claimed_state = "RECONCILING"
            if expected_state == "WAITING_EXTERNAL":
                reduced = reduce_step(
                    StepSnapshot(
                        step_id=str(step["step_id"]),
                        state=StepState.WAITING_EXTERNAL,
                        effect_disposition=EffectDisposition.OUTCOME_UNKNOWN,
                        revision=revision,
                    ),
                    StepEvent.RECONCILE_REQUESTED,
                    StepState.RECONCILING,
                    guard=True,
                )
                claimed_state = reduced.state.value
            elif expected_state != "RECONCILING":
                raise ClaimBindingMismatch(
                    "RECONCILE claim source state is not recoverable"
                )
        result = self.connection.execute(
            update(steps)
            .where(
                steps.c.project_key == work["project_key"],
                steps.c.run_id == work["run_id"],
                steps.c.step_id == work["step_id"],
                steps.c.revision == revision,
                steps.c.state == expected_state,
            )
            .values(
                state=claimed_state,
                revision=revision + 1,
                attempt_count=int(step["attempt_count"]) + 1,
                lease_token=lease_token,
                lease_owner=context.node_id,
                lease_expires_at=lease_expires_at,
                heartbeat_at=now,
                updated_at=now,
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise ClaimConflict("step expected-revision CAS failed")

        runs = _table("runtime_runs")
        seq = int(run["next_event_seq"])
        run_revision = int(run["revision"])
        advanced = self.connection.execute(
            update(runs)
            .where(
                runs.c.project_key == work["project_key"],
                runs.c.run_id == work["run_id"],
                runs.c.revision == run_revision,
                runs.c.next_event_seq == seq,
            )
            .values(
                next_event_seq=seq + 1,
                revision=run_revision + 1,
                updated_at=now,
            )
        )
        if getattr(advanced, "rowcount", None) != 1:
            raise ClaimConflict("StepClaimed event sequence CAS failed")
        events = _table("runtime_events")
        event_type = (
            StepEvent.RECONCILE_REQUESTED.value
            if kind is AssignmentKind.RECONCILE and expected_state == "WAITING_EXTERNAL"
            else "StepClaimed"
        )
        self.connection.execute(
            insert(events).values(
                project_key=work["project_key"],
                run_id=work["run_id"],
                seq=seq,
                event_type=event_type,
                schema_version="mrw.runtime.event.step_claimed.v1",
                step_id=work["step_id"],
                attempt_id=attempt_id,
                event_metadata_json={
                    "work_item_id": work["work_item_id"],
                    "node_id": context.node_id,
                    "lease_token_ref": f"lease-token:sha256:{canonical_digest((lease_token,))}",
                    "assignment_kind": kind.value,
                    "reconciliation_attempt_id": (
                        work["reconciliation_attempt_id"]
                        if kind is AssignmentKind.RECONCILE
                        else None
                    ),
                },
                authority_digest=authority_digest,
                created_at=now,
                updated_at=now,
            )
        )


__all__ = [
    "ClaimBindingMismatch",
    "ClaimConflict",
    "ClaimRecord",
    "NodeClaimContext",
    "WorkItemClaimRepository",
    "due_claim_statement",
]
