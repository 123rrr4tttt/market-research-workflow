"""Family-local PostgreSQL canary + rollback for the C3 collect family.

The canary slice is bounded and local: it captures an exact fixture closure
(single-Atom Program/Plan, contract, payload ref, payload, catalog, binding)
plus the compiled TraverseOrdered family Program/Plan, validates both the
single-Atom closure and the traversal occurrence binding, and only then runs
the deterministic no-provider ordered traversal and fold.  It never enables a
live provider, never performs network/crawler/credential work, and never
claims Document adoption or evidence qualification.

Rollback switches only the future claim owner back to legacy: already
recorded successor journal facts remain readable and unchanged, and no
duplicate claim is created.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities import collect_c3_interpreters as ci
from app.successor_runtime.capabilities.checksum import (
    content_digest,
)
from app.successor_runtime.runtime.assignments import RuntimeAssignment, require_digest
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.approvals import ApprovalRepository
from app.successor_runtime.substrate.postgres.authority import (
    CapabilityAuthority,
    CapabilityAuthorityRepository,
)
from app.successor_runtime.substrate.postgres.models import project_tables
from app.successor_runtime.substrate.postgres.research_ledger import (
    ExactContentConflict,
    ProjectRecordNotFound,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    RuntimeJournalRepository,
    StaleRevisionError,
    _one_mapping,
    _table,
)
from app.successor_runtime.substrate.postgres.session import (
    ProjectScopeStale,
    ServerProjectScopeResolver,
)
from app.successor_runtime.substrate.postgres.values import ValueRepository

__all__ = [
    "AUTHORITY_EVENT_SCHEMA",
    "AUTHORITY_EVENT_TYPE",
    "C3CollectComposedRuntimeHandler",
    "C3CollectRollbackService",
    "CanaryPhase",
    "CanaryTransitionReceipt",
    "authority_digest",
    "select_future_owner",
]

AUTHORITY_EVENT_TYPE = "CapabilityAuthorityChanged"
AUTHORITY_EVENT_SCHEMA = "mrw.successor.collect.c3.authority-event.v1"


class CanaryPhase(StrEnum):
    """Collect capability claim states used by the bounded C3 canary."""

    OFF = "off"
    SHADOW = "shadow"
    CANARY = "canary"

    @property
    def mode(self) -> str:
        return self.value

    @property
    def successor_claim_enabled(self) -> bool:
        return self is CanaryPhase.CANARY

    @property
    def legacy_claim_enabled(self) -> bool:
        return self in {CanaryPhase.SHADOW, CanaryPhase.OFF}


def authority_digest(
    *,
    project_key: str,
    capability_id: str,
    mode: str,
    authority_epoch: int,
    successor_claim_enabled: bool,
    legacy_claim_enabled: bool,
    allowlist_digest: str,
    config_digest: str,
    effective_at: datetime,
    updated_by: str,
    approval_ref: str,
    rollback_target_ref: str,
    revision: int,
) -> str:
    """Content-addressed digest over one C3 collect capability authority row."""

    if successor_claim_enabled and legacy_claim_enabled:
        raise ValueError("legacy and successor claim authority cannot both be enabled")
    return content_digest(
        {
            "schema": "mrw.successor.collect.c3.authority.v1",
            "project_key": project_key,
            "capability_id": capability_id,
            "mode": mode,
            "authority_epoch": authority_epoch,
            "successor_claim_enabled": successor_claim_enabled,
            "legacy_claim_enabled": legacy_claim_enabled,
            "allowlist_digest": allowlist_digest,
            "config_digest": config_digest,
            "effective_at": effective_at.astimezone(UTC).isoformat(),
            "updated_by": updated_by,
            "approval_ref": approval_ref,
            "rollback_target_ref": rollback_target_ref,
            "revision": revision,
        }
    )


def select_future_owner(
    row: Mapping[str, Any],
) -> Literal["legacy", "successor", "none"]:
    """Return the single future claim owner selected by an authority row."""

    successor = bool(row["successor_claim_enabled"])
    legacy = bool(row["legacy_claim_enabled"])
    if successor and legacy:
        raise ExactBindingConflict(
            "capability authority cannot enable legacy and successor claims together"
        )
    if successor:
        return "successor"
    if legacy:
        return "legacy"
    return "none"


class _ScopeView:
    project_key: str
    registry_revision: int
    scope_digest: str

    def __init__(
        self, *, project_key: str, registry_revision: int, scope_digest: str
    ) -> None:
        self.project_key = project_key
        self.registry_revision = registry_revision
        self.scope_digest = scope_digest


class _DeterministicElementRunner:
    """No-provider element interpreter used by the C3 canary handler."""

    def run(self, element: c3.CollectBatchElement) -> c3.CollectElementOutcome:
        legacy_ref = "legacy:" + content_digest(
            {
                "schema": "mrw.successor.collect.c3.canary-element.v1",
                "element_id": element.element_id,
                "input_index": element.input_index,
            }
        )
        return c3.CollectElementSucceeded(
            schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
            element_id=element.element_id,
            input_index=element.input_index,
            counts=c3.CollectCounts(inserted=len(element.query_terms)),
            links=tuple(
                f"https://canary.example/{term}" for term in element.query_terms
            ),
            receipt=None,
            legacy_observation_ref=legacy_ref,
            outcome_digest="",
        )


class C3CollectComposedRuntimeHandler(RuntimeHandler):
    """Exact installed realization of the composed C3 family Program.

    The RuntimeAssignment binds the actual composed TraverseOrdered
    Program/Plan.  The handler validates the traversal materialization
    successor epoch and the fold atom contract inside that exact
    ExecutionPlan, store-rehydrates the canonical ordered element-payload
    sequence from the project value store (never a captured mutable tuple),
    and only then executes the deterministic ordered traversal and fold with
    ``provider_calls`` fixed at zero.  The terminal digest is the aggregate
    outcome digest, matching the composed plan output type.
    """

    def __init__(
        self,
        *,
        composed_program: Any,
        composed_plan: Any,
        catalog: Any,
        binding: Any,
        deployment_catalog_digest: str,
        uow_factory: Any,
    ) -> None:
        require_digest(
            getattr(binding, "binding_digest", ""),
            "C3 handler binding digest",
        )
        require_digest(deployment_catalog_digest, "C3 deployment catalog digest")
        self.composed_program = composed_program
        self.composed_plan = composed_plan
        self.catalog = catalog
        self.binding = binding
        self.deployment_catalog_digest = deployment_catalog_digest
        self.uow_factory = uow_factory
        self.handler_binding_digest = binding.binding_digest
        self.interpreter_profile_digest = binding.interpreter_profile_digest
        self.operation_contract_digest = binding.operation_contract_digest
        self.composed_program_digest = composed_program.program_digest
        self.composed_plan_digest = composed_plan.plan_digest
        self.provider_calls = 0
        self.executions = 0

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        if claim.assignment_digest != assignment.assignment_digest:
            raise DefiniteInterpreterFailure("CLAIM_ASSIGNMENT_BINDING_DRIFT")
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
        ):
            raise DefiniteInterpreterFailure("EXACT_C3_HANDLER_BINDING_DRIFT")
        if assignment.deployment_catalog_digest != self.deployment_catalog_digest:
            raise DefiniteInterpreterFailure("EXACT_C3_DEPLOYMENT_CATALOG_DRIFT")
        if (
            assignment.program_digest != self.composed_program_digest
            or assignment.plan_digest != self.composed_plan_digest
        ):
            raise DefiniteInterpreterFailure("EXACT_C3_COMPOSED_PROGRAM_EPOCH_DRIFT")
        with self.uow_factory() as uow:
            element_payloads, _scope = self.rehydrate_payload_closure(
                uow.connection,
                assignment,
            )
            outcome = ci.ComposedCollectSuccessorInterpreter().interpret(
                program=self.composed_program,
                plan=self.composed_plan,
                catalog=self.catalog,
                binding=self.binding,
                element_payloads=element_payloads,
                assignment=assignment,
            )
            if isinstance(outcome, ci.InterpreterFailure):
                raise DefiniteInterpreterFailure(outcome.code)
            terminal_digest = outcome.value.aggregate_digest
        self.executions += 1
        # provider_calls stays 0: the ordered traversal never dispatches a provider.
        return InterpreterOutcome.succeeded(terminal_digest)

    def rehydrate_payload_closure(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
    ) -> tuple[tuple[c3.CollectBatchElementPayload, ...], RuntimeScope]:
        """Load and bind the exact ordered element-payload sequence from stores."""

        try:
            ci.require_exact_composed_binding(
                program=self.composed_program,
                plan=self.composed_plan,
                catalog=self.catalog,
                assignment=assignment,
            )
        except ci.CollectBindingMismatch as exc:
            raise DefiniteInterpreterFailure(
                "EXACT_C3_COMPOSED_BINDING_DRIFT: " + str(exc)
            ) from exc
        metadata = dict(self.composed_program.metadata)
        resolver = ServerProjectScopeResolver(connection=connection)
        resolved = resolver.resolve_expected(
            assignment.project_key,
            self.composed_program.project_registry_revision,
            self.composed_program.project_scope_digest,
        )
        if isinstance(resolved, ProjectScopeStale):
            raise DefiniteInterpreterFailure("C3_PAYLOAD_SCOPE_STALE")
        scope = RuntimeScope(
            project_scope=resolved,
            actor_id=assignment.project_key,
        )
        tables = project_tables(MetaData(), resolved.resolved_schema)
        table = tables.successor_values
        row = _one_mapping(
            connection.execute(
                select(table).where(
                    table.c.project_key == assignment.project_key,
                    table.c.value_id == metadata["payload_value_id"],
                    table.c.revision == 1,
                    table.c.incarnation == metadata["payload_incarnation"],
                    table.c.content_digest == metadata["payload_content_digest"],
                    table.c.byte_size == metadata["payload_byte_size"],
                    table.c.object_type == metadata["payload_object_type"],
                    table.c.codec_id == metadata["payload_codec_id"],
                    table.c.source_ref == metadata["payload_storage_ref"],
                    table.c.provenance_digest == metadata["payload_provenance_digest"],
                )
            )
        )
        if row is None:
            raise DefiniteInterpreterFailure("C3_PAYLOAD_STORE_DRIFT")
        try:
            exact = ValueRepository(connection, tables).get_exact(
                scope.project_scope,
                str(metadata["payload_value_id"]),
                expected_revision=1,
                expected_incarnation=str(metadata["payload_incarnation"]),
                expected_digest=str(metadata["payload_content_digest"]),
            )
        except (ExactContentConflict, ProjectRecordNotFound) as exc:
            raise DefiniteInterpreterFailure("C3_PAYLOAD_STORE_DRIFT") from exc
        if len(exact) != int(metadata["payload_byte_size"]):
            raise DefiniteInterpreterFailure("C3_PAYLOAD_BYTE_SIZE_DRIFT")
        try:
            plain_sequence = json.loads(exact.decode("utf-8"))
            if not isinstance(plain_sequence, list):
                raise TypeError("family payload sequence must be a JSON array")
            element_payloads = tuple(
                c3.collect_batch_element_payload_from_dicts(
                    request_ref=item["parent_request_ref"],
                    request_snapshot=item["request_snapshot"],
                    element=item["element"],
                    resource_policy=item["resource_policy"],
                    authority_scope_ref=item["authority_scope_ref"],
                )
                for item in plain_sequence
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise DefiniteInterpreterFailure("C3_PAYLOAD_CODEC_DRIFT") from exc
        if len(element_payloads) != int(metadata["payload_element_count"]):
            raise DefiniteInterpreterFailure("C3_PAYLOAD_COUNT_DRIFT")
        expected_digests = tuple(metadata["payload_element_digests"])
        if tuple(payload.payload_digest for payload in element_payloads) != (
            expected_digests
        ):
            raise DefiniteInterpreterFailure("C3_PAYLOAD_ORDER_OR_DIGEST_DRIFT")
        return element_payloads, scope


@dataclass(frozen=True, slots=True)
class CanaryTransitionReceipt:
    transition_id: str
    run_id: str
    event_seq: int
    previous_run_revision: int
    run_revision: int
    authority_epoch: int
    authority_revision: int
    before_authority_digest: str
    after_authority_digest: str


class C3CollectRollbackService:
    """Future-owner-only rollback on the caller-owned connection."""

    def __init__(
        self,
        connection: Connection,
        scope: RuntimeScope,
        *,
        journal: RuntimeJournalRepository | None = None,
        approvals: ApprovalRepository | None = None,
        authority_repository: CapabilityAuthorityRepository | None = None,
    ) -> None:
        self.connection = connection
        self.scope = scope
        self.journal = journal or RuntimeJournalRepository(connection, scope)
        self.approvals = approvals or ApprovalRepository(connection, scope)
        self.authority_repository = (
            authority_repository or CapabilityAuthorityRepository(connection, scope)
        )

    def rollback_future_owner_only(
        self,
        *,
        transition_id: str,
        capability_id: str,
        run_id: str,
        step_id: str,
        work_item_id: str,
        program_digest: str,
        plan_digest: str,
        payload_digest: str,
        payload_ref: str,
        successor_binding_digest: str,
        expected_authority_epoch: int,
        expected_authority_revision: int,
        expected_run_revision: int,
        approval_ref: str,
        rollback_target_ref: str,
        allowlist_digest: str,
        config_digest: str,
        before_authority_digest: str,
        after_authority_digest: str,
        effective_at: datetime,
        now: datetime | None = None,
    ) -> CanaryTransitionReceipt:
        observed_at = now or datetime.now(UTC)
        if effective_at > observed_at:
            raise ExactBindingConflict("rollback effective_at is in the future")
        self.journal.load_run(run_id, for_update=True)
        row = self.authority_repository.load(capability_id, for_update=True)
        if (
            str(row["mode"]) != CanaryPhase.CANARY.mode
            or bool(row["successor_claim_enabled"]) is not True
            or bool(row["legacy_claim_enabled"]) is not False
        ):
            raise ExactBindingConflict("rollback source authority is not canary")
        if int(row["authority_epoch"]) != expected_authority_epoch:
            raise ExactBindingConflict("rollback authority epoch is stale")
        if int(row["revision"]) != expected_authority_revision:
            raise StaleRevisionError("rollback authority revision CAS failed")
        if str(row["rollback_target_ref"]) != rollback_target_ref:
            raise ExactBindingConflict("rollback target mismatch")
        before = authority_digest(
            project_key=str(row["project_key"]),
            capability_id=str(row["capability_id"]),
            mode=str(row["mode"]),
            authority_epoch=int(row["authority_epoch"]),
            successor_claim_enabled=bool(row["successor_claim_enabled"]),
            legacy_claim_enabled=bool(row["legacy_claim_enabled"]),
            allowlist_digest=str(row["allowlist_digest"]),
            config_digest=str(row["config_digest"]),
            effective_at=row["effective_at"],
            updated_by=str(row["updated_by"]),
            approval_ref=str(row["approval_ref"]),
            rollback_target_ref=str(row["rollback_target_ref"]),
            revision=int(row["revision"]),
        )
        if before != before_authority_digest:
            raise ExactBindingConflict("rollback before authority digest mismatch")

        next_epoch = expected_authority_epoch + 1
        next_revision = expected_authority_revision + 1
        after = authority_digest(
            project_key=self.scope.project_scope.project_key,
            capability_id=capability_id,
            mode=CanaryPhase.OFF.mode,
            authority_epoch=next_epoch,
            successor_claim_enabled=False,
            legacy_claim_enabled=True,
            allowlist_digest=allowlist_digest,
            config_digest=config_digest,
            effective_at=effective_at,
            updated_by=self.scope.actor_id,
            approval_ref=approval_ref,
            rollback_target_ref=rollback_target_ref,
            revision=next_revision,
        )
        if after != after_authority_digest:
            raise ExactBindingConflict("rollback after authority digest mismatch")

        self._require_exact_work_binding(
            capability_id=capability_id,
            work_item_id=work_item_id,
            run_id=run_id,
            step_id=step_id,
            program_digest=program_digest,
            plan_digest=plan_digest,
            payload_digest=payload_digest,
            successor_binding_digest=successor_binding_digest,
        )
        self.approvals.require_current(
            approval_ref,
            run_id=run_id,
            step_id=step_id,
            payload_digest=payload_digest,
            authority_digest=after_authority_digest,
            now=observed_at,
        )

        self.authority_repository.revise(
            CapabilityAuthority(
                capability_id=capability_id,
                mode=CanaryPhase.OFF.mode,
                authority_epoch=next_epoch,
                successor_claim_enabled=False,
                legacy_claim_enabled=True,
                allowlist_digest=allowlist_digest,
                config_digest=config_digest,
                effective_at=effective_at,
                approval_ref=approval_ref,
                rollback_target_ref=rollback_target_ref,
            ),
            expected_revision=expected_authority_revision,
        )
        event: dict[str, Any] = {
            "event_type": AUTHORITY_EVENT_TYPE,
            "schema_version": AUTHORITY_EVENT_SCHEMA,
            "step_id": step_id,
            "event_metadata_json": {
                "transition_id": transition_id,
                "state": "CAPABILITY_AUTHORITY_CHANGED",
                "previous_state": CanaryPhase.CANARY.mode,
                "next_state": CanaryPhase.OFF.mode,
                "capability_id": capability_id,
                "authority_epoch": next_epoch,
                "previous_revision": expected_authority_revision,
                "target_revision": next_revision,
                "approval_ref": approval_ref,
                "rollback_target_ref": rollback_target_ref,
                "payload_digest": payload_digest,
                "program_digest": program_digest,
                "plan_digest": plan_digest,
                "successor_binding_digest": successor_binding_digest,
                "before_authority_digest": before,
                "after_authority_digest": after,
                "future_owner_ref": "legacy",
            },
            "payload_ref": payload_ref,
            "payload_digest": payload_digest,
            "authority_digest": after,
        }
        receipt = self.journal.append_transition(
            run_id=run_id,
            expected_revision=expected_run_revision,
            snapshot_values={},
            events=(event,),
        )
        return CanaryTransitionReceipt(
            transition_id=transition_id,
            run_id=run_id,
            event_seq=receipt.first_event_seq or 0,
            previous_run_revision=receipt.previous_revision,
            run_revision=receipt.revision,
            authority_epoch=next_epoch,
            authority_revision=next_revision,
            before_authority_digest=before,
            after_authority_digest=after,
        )

    def _require_exact_work_binding(
        self,
        *,
        capability_id: str,
        work_item_id: str,
        run_id: str,
        step_id: str,
        program_digest: str,
        plan_digest: str,
        payload_digest: str,
        successor_binding_digest: str,
    ) -> None:
        table = _table("runtime_work_items")
        row = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == self.scope.project_scope.project_key,
                    table.c.work_item_id == work_item_id,
                )
            )
        )
        if row is None:
            raise RecordNotFound(f"rollback work item not found: {work_item_id}")
        required = {
            "run_id": run_id,
            "step_id": step_id,
            "capability_id": capability_id,
            "assignment_kind": "INTERPRET",
            "program_digest": program_digest,
            "plan_digest": plan_digest,
            "payload_digest": payload_digest,
            "handler_binding_digest": successor_binding_digest,
        }
        mismatches = [
            name for name, expected in required.items() if row.get(name) != expected
        ]
        if mismatches:
            raise ExactBindingConflict(
                "rollback work binding drift: " + ", ".join(mismatches)
            )
