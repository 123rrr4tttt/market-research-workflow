"""Caller-owned PostgreSQL admission of a human-approved delivery work item."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities.first_specimen_delivery_gate import (
    DeliveryAssignmentRequest,
    DeliveryReadyPacket,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.ports import RuntimeScope

from .models import PUBLIC_TABLES
from .research_ledger import one_mapping
from .runtime_journal import (
    ExactBindingConflict,
    StaleRevisionError,
    validate_authorization_row,
)
from .runtime_lifecycle import AssignmentEnvelope, _assignment_values


class PostgresDeliveryRuntimePort:
    """Persist one exact READY delivery assignment inside DeliveryGate's UoW."""

    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def get_delivery_admission(
        self, scope: object, delivery_intent_id: str
    ) -> None:
        self._require_scope(scope)
        if not delivery_intent_id:
            raise ValueError("delivery_intent_id is required")
        # DeliveryGate repeats all exact readback and absent-or-exact writes.
        # Returning no process-local packet keeps restart behavior honest.
        return None

    def admit_delivery(
        self, scope: object, packet: DeliveryReadyPacket
    ) -> Mapping[str, Any]:
        self._require_scope(scope)
        assignment = RuntimeAssignment.model_validate(
            packet.assignment.model_dump(mode="json", exclude_none=False)
        )
        if (
            assignment.assignment_kind is not AssignmentKind.INTERPRET
            or assignment.project_key != self.scope.project_scope.project_key
            or assignment.payload_ref != packet.export_payload_ref.storage_ref
            or assignment.payload_digest != packet.export_payload_ref.content_digest
            or assignment.claim_authority_epoch != packet.authority.authority_epoch
        ):
            raise ExactBindingConflict("delivery READY assignment exact binding drift")

        runs = PUBLIC_TABLES["runtime_runs"]
        run = one_mapping(
            self.connection.execute(
                select(runs)
                .where(
                    runs.c.project_key == assignment.project_key,
                    runs.c.run_id == assignment.run_id,
                )
                .with_for_update()
            )
        )
        if run is None:
            raise ExactBindingConflict("delivery run is absent")
        if (
            run["program_digest"] != assignment.program_digest
            or run["plan_digest"] != assignment.plan_digest
            or run["qualification_digest"] != packet.qualification_digest
            or run["incarnation"] != assignment.incarnation
        ):
            raise ExactBindingConflict("delivery run/Plan/qualification drift")

        authorizations = PUBLIC_TABLES["runtime_step_authorizations"]
        authorization_row = one_mapping(
            self.connection.execute(
                select(authorizations).where(
                    authorizations.c.project_key == assignment.project_key,
                    authorizations.c.run_id == assignment.run_id,
                    authorizations.c.step_id == assignment.step_id,
                    authorizations.c.claim_authority_epoch
                    == assignment.claim_authority_epoch,
                )
            )
        )
        if authorization_row is None:
            raise ExactBindingConflict("delivery step authorization is absent")
        authorization = validate_authorization_row(authorization_row)
        if (
            authorization.operation_contract_digest
            != assignment.operation_contract_digest
            or authorization.interpreter_binding_digest
            != assignment.handler_binding_digest
            or authorization.claim_policy_digest != assignment.claim_policy_digest
            or authorization.queue_eligibility_digest
            != assignment.queue_eligibility_digest
            or packet.approval.approval_id not in authorization.approval_refs
        ):
            raise ExactBindingConflict("delivery authorization/artifact binding drift")

        steps = PUBLIC_TABLES["runtime_steps"]
        work = PUBLIC_TABLES["runtime_work_items"]
        existing_step = one_mapping(
            self.connection.execute(
                select(steps).where(
                    steps.c.project_key == assignment.project_key,
                    steps.c.run_id == assignment.run_id,
                    steps.c.step_id == assignment.step_id,
                )
            )
        )
        existing_work = one_mapping(
            self.connection.execute(
                select(work).where(
                    work.c.project_key == assignment.project_key,
                    work.c.work_item_id == assignment.work_item_id,
                )
            )
        )
        if existing_step is None and existing_work is not None:
            raise ExactBindingConflict("delivery work exists without its runtime step")

        envelope = AssignmentEnvelope(
            assignment=assignment,
            required_node_profile_selector=packet.required_node_profile_selector,
            authority_digest=authorization.binding_digest,
            resource_policy_digest=packet.resource_policy_digest,
            fairness_key=packet.fairness_key,
            qualification_digest=packet.qualification_digest,
            resource_class=packet.resource_class,
            resource_units=packet.resource_units,
            concurrency_key=packet.concurrency_key,
            recovery_binding=packet.recovery_binding,
            authoritative_readback_profile_ref=(
                packet.recovery_binding.authoritative_readback_profile_ref
            ),
        )
        now = packet.ready_at
        work_values = _assignment_values(envelope, due_at=now)
        if existing_step is not None and existing_work is not None:
            expected = {
                "state": "READY",
                "operation_kind": assignment.operation_contract_ref.kind,
                "input_digest": assignment.input_closure_digest,
                "claim_authority_epoch": assignment.claim_authority_epoch,
                "claim_policy_digest": assignment.claim_policy_digest,
            }
            if any(existing_step[key] != value for key, value in expected.items()):
                raise ExactBindingConflict("existing delivery step drift")
            if (
                existing_work is None
                or existing_work["assignment_digest"] != assignment.assignment_digest
                or existing_work["state"] != "READY"
            ):
                raise ExactBindingConflict("existing delivery work drift")
            return existing_work
        step_values = dict(
                project_key=assignment.project_key,
                run_id=assignment.run_id,
                step_id=assignment.step_id,
                operation_id="delivery.internal_export",
                operation_kind=assignment.operation_contract_ref.kind,
                operation_version=assignment.operation_contract_ref.contract_version,
                state="READY",
                revision=assignment.expected_step_revision or 0,
                execution_epoch=assignment.execution_epoch,
                input_digest=assignment.input_closure_digest,
                effect_class="LOCAL_SUCCESSOR_NATIVE",
                resource_class=packet.resource_class,
                concurrency_key=packet.concurrency_key,
                capability_id=assignment.capability_id,
                claim_owner="successor",
                claim_authority_epoch=assignment.claim_authority_epoch,
                claim_policy_digest=assignment.claim_policy_digest,
                attempt_count=0,
                max_attempts=(
                    1
                    if existing_step is None
                    else int(existing_step["max_attempts"])
                ),
        )
        if existing_step is None:
            self.connection.execute(insert(steps).values(**step_values))
        else:
            fixed = (
                "project_key",
                "run_id",
                "step_id",
                "operation_id",
                "operation_kind",
                "operation_version",
                "execution_epoch",
                "effect_class",
                "resource_class",
                "concurrency_key",
                "capability_id",
                "claim_owner",
                "claim_authority_epoch",
                "claim_policy_digest",
                "max_attempts",
            )
            if (
                existing_step["state"] != "PENDING"
                or int(existing_step["revision"]) != 0
                or any(existing_step[key] != step_values[key] for key in fixed)
            ):
                raise ExactBindingConflict("delivery PENDING step identity drift")
            changed = self.connection.execute(
                update(steps)
                .where(
                    steps.c.project_key == assignment.project_key,
                    steps.c.run_id == assignment.run_id,
                    steps.c.step_id == assignment.step_id,
                    steps.c.state == "PENDING",
                    steps.c.revision == 0,
                )
                .values(
                    state="READY",
                    input_digest=assignment.input_closure_digest,
                    updated_at=now,
                )
            )
            if getattr(changed, "rowcount", None) != 1:
                raise StaleRevisionError("delivery PENDING step activation CAS failed")
        self.connection.execute(insert(work).values(**work_values))
        seq = int(run["next_event_seq"])
        self.connection.execute(
            insert(PUBLIC_TABLES["runtime_events"]).values(
                project_key=assignment.project_key,
                run_id=assignment.run_id,
                seq=seq,
                event_type="DeliveryReady",
                schema_version="mrw.runtime.event.delivery_ready.v1",
                step_id=assignment.step_id,
                event_metadata_json={
                    "work_item_id": assignment.work_item_id,
                    "assignment_digest": assignment.assignment_digest,
                    "payload_digest": assignment.payload_digest,
                    "approval_ref": packet.approval.approval_id,
                },
                authority_digest=authorization.binding_digest,
                created_at=now,
                updated_at=now,
            )
        )
        updated = self.connection.execute(
            update(runs)
            .where(
                runs.c.project_key == assignment.project_key,
                runs.c.run_id == assignment.run_id,
                runs.c.revision == int(run["revision"]),
                runs.c.next_event_seq == seq,
            )
            .values(
                revision=int(run["revision"]) + 1,
                next_event_seq=seq + 1,
                updated_at=now,
            )
        )
        if getattr(updated, "rowcount", None) != 1:
            raise StaleRevisionError("delivery event allocator CAS failed")
        return one_mapping(
            self.connection.execute(
                select(work).where(
                    work.c.project_key == assignment.project_key,
                    work.c.work_item_id == assignment.work_item_id,
                )
            )
        ) or {}

    def _require_scope(self, scope: object) -> None:
        if scope != self.scope:
            raise ExactBindingConflict("delivery runtime scope drift")


def build_delivery_runtime_assignment(
    request: DeliveryAssignmentRequest,
) -> RuntimeAssignment:
    """Build the exact post-approval delivery assignment."""

    params = request.parameters
    handler = params.handler_binding
    return RuntimeAssignment(
        runtime_protocol_version=params.runtime_protocol_version,
        work_item_id=params.work_item_id,
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=request.project_key,
        run_id=params.run_id,
        step_id=params.step_id,
        step_role=CompiledStepRole.EFFECT,
        capability_id=params.capability_id,
        operation_contract_ref=params.operation_contract_ref,
        operation_contract_digest=params.operation_contract_ref.contract_digest,
        return_contract_binding=params.return_contract_binding,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{handler.binding_digest}",
        handler_binding_digest=handler.binding_digest,
        handler_binding=handler,
        program_digest=params.program_digest,
        plan_digest=params.plan_digest,
        deployment_catalog_digest=params.deployment_catalog_digest,
        execution_epoch=params.execution_epoch,
        incarnation=params.incarnation,
        input_refs=(
            request.artifact_content_ref,
            request.intent_value_ref.storage_ref,
        ),
        input_closure_digest=canonical_digest(
            (
                request.artifact_content_ref,
                request.intent_value_ref.storage_ref,
            )
        ),
        payload_ref=request.export_payload_ref.storage_ref,
        payload_digest=request.export_payload_ref.content_digest,
        queue_eligibility_digest=params.queue_eligibility_digest,
        resource_policy_epoch=params.resource_policy_epoch,
        claim_authority_epoch=request.authority.authority_epoch,
        claim_policy_digest=request.authority.claim_policy_digest,
        expected_step_revision=params.expected_step_revision,
        deadline_at=params.deadline_at,
        trace_id=params.trace_id,
    )


__all__ = [
    "PostgresDeliveryRuntimePort",
    "build_delivery_runtime_assignment",
]
