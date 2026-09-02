"""Exact first-specimen Research Ledger admission realizations.

The module owns PostgreSQL effects, while runtime dispatch remains the exact
operation-digest registry in ``runtime.admission_coordinator``.  Candidate
classes validate the payload selected by a handler; they never choose a
handler themselves.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities.first_specimen import (
    FirstSpecimenCapabilityBundle,
)
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.research.artifacts import (
    DeliveryAttempt,
    DeliveryIntent,
    DeliveryReceiptRef,
    ResearchArtifact,
)
from app.successor_runtime.research.claims import Claim, Gap
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.research.evidence import EvidenceQualification
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import (
    CLAIM_TYPE,
    DELIVERY_INTENT_TYPE,
    DELIVERY_RECEIPT_REF_TYPE,
    GAP_TYPE,
    RESEARCH_ARTIFACT_TYPE,
)
from app.successor_runtime.research.relations import ResearchRelation
from app.successor_runtime.runtime.admission import CommitIntent, VerificationBinding
from app.successor_runtime.runtime.admission_coordinator import (
    AdmissionBindingError,
    AdmissionRegistration,
    CanonicalCommit,
    CanonicalCommitReadback,
    ExactAdmissionRegistry,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.ports import RuntimeScope

from .commit_intents import (
    CommitIntentBinding,
    CommitIntentRepository,
    CommitIntentStatus,
)
from .research_ledger import (
    ProjectRecordNotFound,
    ResearchLedgerRepository,
    assert_table_scope,
    object_ref_text,
    one_mapping,
    project_table,
)
from .values import ReceiptRepository


class ResearchAdmissionMode(StrEnum):
    EVIDENCE_RELATION = "EVIDENCE_RELATION"
    CLAIM_OR_GAP_OBJECT = "CLAIM_OR_GAP_OBJECT"
    ARTIFACT_OBJECT = "ARTIFACT_OBJECT"
    DELIVERY_RECEIPT_EXTERNAL_REF = "DELIVERY_RECEIPT_EXTERNAL_REF"


@dataclass(frozen=True, slots=True)
class EvidenceRelationCandidate:
    qualification: EvidenceQualification
    source_ref: ResearchObjectRef
    target_ref: ResearchObjectRef
    expected_revision: int
    expected_incarnation: str


@dataclass(frozen=True, slots=True)
class ResearchObjectCandidate:
    ref: ResearchObjectRef
    payload: Claim | Gap | ResearchArtifact
    expected_revision: int
    expected_incarnation: str


@dataclass(frozen=True, slots=True)
class DeliveryIntentCandidate:
    """Canonical Research Ledger intent, separate from runtime attempt/receipt."""

    ref: ResearchObjectRef
    intent: DeliveryIntent
    expected_revision: int
    expected_incarnation: str


@dataclass(frozen=True, slots=True)
class DeliveryReceiptCandidate:
    """Project receipt plus its bounded Ledger external ref and relation."""

    ref: ResearchObjectRef
    receipt: DeliveryReceiptRef
    receipt_content: bytes | dict[str, Any]
    artifact_ref: ResearchObjectRef
    delivered_as: ResearchRelation
    expected_revision: int
    expected_incarnation: str
    expected_relation_revision: int
    expected_relation_incarnation: str


class JournalCommand(Protocol):
    def execute(self, connection: Connection) -> object: ...


@dataclass(frozen=True, slots=True)
class AtomicResearchAdmissionCommand:
    """CW07 same-database command: canonical mutation and event share a UoW."""

    registration: AdmissionRegistration
    assignment: RuntimeAssignment
    scope: RuntimeScope
    intent: CommitIntent
    candidate: object
    binding: VerificationBinding
    journal_command: JournalCommand

    def execute(self, connection: Connection) -> CanonicalCommit:
        handler = self.registration.handler
        if not isinstance(handler, ResearchAdmissionHandler):
            raise AdmissionBindingError(
                "atomic Research Ledger command requires its exact PostgreSQL handler"
            )
        ref = self.assignment.operation_contract_ref
        if (
            ref is None
            or self.assignment.assignment_kind is not AssignmentKind.VERIFY_ADMIT
            or ref != self.registration.operation_contract_ref
            or self.assignment.operation_contract_digest != ref.contract_digest
        ):
            raise AdmissionBindingError(
                "atomic Research Ledger command operation contract drift"
            )
        if connection is not handler.connection:
            raise AdmissionBindingError(
                "atomic Research Ledger admission requires the exact UoW connection"
            )
        commit = handler.commit(
            self.scope,
            self.intent,
            self.candidate,
            self.binding,
        )
        # No internal commit: if the journal command fails, the enclosing UoW
        # rolls back both the canonical row and event/snapshot mutation.
        self.journal_command.execute(connection)
        return commit


class ResearchAdmissionHandler:
    atomic_with_caller_uow = True
    """One exact operation-contract realization for Research Ledger admission."""

    def __init__(
        self,
        *,
        connection: Connection,
        tables: Any,
        operation_contract_ref: OperationContractRef,
        mode: ResearchAdmissionMode,
    ) -> None:
        self.connection = connection
        self.tables = tables
        self.operation_contract_ref = operation_contract_ref
        self.mode = mode
        self.ledger = ResearchLedgerRepository(connection, tables)
        self.receipts = ReceiptRepository(connection, tables)
        self.canonical_owner = {
            ResearchAdmissionMode.EVIDENCE_RELATION: "ResearchLedger",
            ResearchAdmissionMode.CLAIM_OR_GAP_OBJECT: "ResearchLedger",
            ResearchAdmissionMode.ARTIFACT_OBJECT: (
                "ResearchLedger_plus_project_artifact_store"
            ),
            ResearchAdmissionMode.DELIVERY_RECEIPT_EXTERNAL_REF: (
                "project_receipt_store"
            ),
        }[mode]

    def commit(
        self,
        scope: RuntimeScope,
        intent: CommitIntent,
        candidate: object,
        _binding: VerificationBinding,
    ) -> CanonicalCommit:
        self._require_intent(scope, intent)
        if self.mode is ResearchAdmissionMode.EVIDENCE_RELATION:
            canonical = self._commit_evidence(scope, intent, candidate)
        elif self.mode is ResearchAdmissionMode.CLAIM_OR_GAP_OBJECT:
            canonical = self._commit_object(
                scope,
                intent,
                candidate,
                allowed_payloads=(Claim, Gap),
                allowed_types=(CLAIM_TYPE.type_id, GAP_TYPE.type_id),
            )
        elif self.mode is ResearchAdmissionMode.ARTIFACT_OBJECT:
            canonical = self._commit_object(
                scope,
                intent,
                candidate,
                allowed_payloads=(ResearchArtifact,),
                allowed_types=(RESEARCH_ARTIFACT_TYPE.type_id,),
            )
        else:
            canonical = self._commit_delivery_receipt(scope, intent, candidate)
        return canonical

    def readback(
        self,
        scope: RuntimeScope,
        intent: CommitIntent,
        candidate: object,
    ) -> CanonicalCommitReadback:
        self._require_intent(scope, intent)
        try:
            if self.mode is ResearchAdmissionMode.EVIDENCE_RELATION:
                commit = self._readback_evidence(scope, intent, candidate)
            elif self.mode is ResearchAdmissionMode.DELIVERY_RECEIPT_EXTERNAL_REF:
                commit = self._readback_delivery(scope, intent, candidate)
            else:
                commit = self._readback_object(scope, intent, candidate)
        except ProjectRecordNotFound:
            return CanonicalCommitReadback.absent(
                observation={
                    "project_key": scope.project_scope.project_key,
                    "operation_contract_digest": (
                        self.operation_contract_ref.contract_digest
                    ),
                    "object_id": intent.object_id,
                    "canonical": "ABSENT",
                }
            )
        return CanonicalCommitReadback.found(commit)

    def _commit_evidence(
        self,
        scope: RuntimeScope,
        intent: CommitIntent,
        candidate: object,
    ) -> CanonicalCommit:
        if not isinstance(candidate, EvidenceRelationCandidate):
            raise AdmissionBindingError("evidence operation requires relation candidate")
        qualification = candidate.qualification
        if (
            qualification.qualification_id != intent.object_id
            or qualification.qualification_digest != intent.content_digest
        ):
            raise AdmissionBindingError("evidence qualification identity/content drift")
        self.ledger.put_evidence_qualification(
            scope,
            qualification,
            source_ref=candidate.source_ref,
            target_ref=candidate.target_ref,
            expected_revision=candidate.expected_revision,
            expected_incarnation=candidate.expected_incarnation,
        )
        return _canonical_commit(
            intent,
            canonical_ref=(
                f"canonical:research-relation:{qualification.qualification_id}:"
                f"{qualification.revision}"
            ),
            revision=qualification.revision,
            incarnation=qualification.incarnation,
        )

    def _commit_object(
        self,
        scope: RuntimeScope,
        intent: CommitIntent,
        candidate: object,
        *,
        allowed_payloads: tuple[type[Any], ...],
        allowed_types: tuple[str, ...],
    ) -> CanonicalCommit:
        if not isinstance(candidate, ResearchObjectCandidate):
            raise AdmissionBindingError("operation requires research object candidate")
        if not isinstance(candidate.payload, allowed_payloads):
            raise AdmissionBindingError("candidate payload is wrong for exact operation")
        ref = candidate.ref
        if ref.object_type.type_id not in allowed_types:
            raise AdmissionBindingError("candidate object type is wrong for exact operation")
        payload_digest = getattr(candidate.payload, "content_digest", None)
        if (
            ref.object_id != intent.object_id
            or ref.content_digest != intent.content_digest
            or payload_digest != ref.content_digest
        ):
            raise AdmissionBindingError("research object identity/content drift")
        self.ledger.put_object(
            scope,
            ref,
            expected_revision=candidate.expected_revision,
            expected_incarnation=candidate.expected_incarnation,
        )
        return _canonical_commit(
            intent,
            canonical_ref=f"canonical:research-object:{ref.object_id}:{ref.revision}",
            revision=ref.revision,
            incarnation=ref.incarnation,
        )

    def _commit_delivery_receipt(
        self,
        scope: RuntimeScope,
        intent: CommitIntent,
        candidate: object,
    ) -> CanonicalCommit:
        if not isinstance(candidate, DeliveryReceiptCandidate):
            raise AdmissionBindingError("delivery operation requires receipt candidate")
        ref = candidate.ref
        receipt = candidate.receipt
        if ref.object_type.type_id != DELIVERY_RECEIPT_REF_TYPE.type_id:
            raise AdmissionBindingError("delivery result must be DeliveryReceiptRef")
        if (
            ref.object_id != intent.object_id
            or ref.content_digest != intent.content_digest
            or receipt.content_digest != ref.content_digest
            or receipt.receipt_ref != ref.object_id
        ):
            raise AdmissionBindingError("delivery receipt identity/content drift")
        if (
            candidate.delivered_as.source_ref != candidate.artifact_ref
            or candidate.delivered_as.target_ref != ref
            or candidate.delivered_as.relation_type != "delivered_as"
        ):
            raise AdmissionBindingError("delivery relation endpoint drift")
        self.receipts.put_exact(
            scope,
            receipt_id=ref.object_id,
            receipt_digest=receipt.receipt_digest,
            delivery_intent_ref=receipt.delivery_intent_ref,
            attempt_ref=receipt.attempt_ref,
            provider_locator=receipt.provider_locator,
            content=candidate.receipt_content,
            outcome_time=receipt.outcome_time,
        )
        self.ledger.put_object(
            scope,
            ref,
            expected_revision=candidate.expected_revision,
            expected_incarnation=candidate.expected_incarnation,
        )
        self.ledger.put_relation(
            scope,
            candidate.delivered_as,
            expected_revision=candidate.expected_relation_revision,
            expected_incarnation=candidate.expected_relation_incarnation,
        )
        return _canonical_commit(
            intent,
            canonical_ref=f"canonical:delivery-receipt:{ref.object_id}:{ref.revision}",
            revision=ref.revision,
            incarnation=ref.incarnation,
        )

    def _readback_object(
        self,
        scope: RuntimeScope,
        intent: CommitIntent,
        candidate: object,
    ) -> CanonicalCommit:
        if not isinstance(candidate, ResearchObjectCandidate):
            raise AdmissionBindingError("object readback requires exact candidate")
        if self.mode is ResearchAdmissionMode.CLAIM_OR_GAP_OBJECT:
            self._validate_object_candidate(
                intent,
                candidate,
                allowed_payloads=(Claim, Gap),
                allowed_types=(CLAIM_TYPE.type_id, GAP_TYPE.type_id),
            )
        elif self.mode is ResearchAdmissionMode.ARTIFACT_OBJECT:
            self._validate_object_candidate(
                intent,
                candidate,
                allowed_payloads=(ResearchArtifact,),
                allowed_types=(RESEARCH_ARTIFACT_TYPE.type_id,),
            )
        ref = self.ledger.get_object(
            scope,
            intent.object_id,
            expected_revision=intent.expected_base_revision + 1,
            expected_incarnation=intent.expected_incarnation,
        )
        if ref != candidate.ref or ref.content_digest != intent.content_digest:
            raise AdmissionBindingError("canonical object readback drift")
        return _canonical_commit(
            intent,
            canonical_ref=f"canonical:research-object:{ref.object_id}:{ref.revision}",
            revision=ref.revision,
            incarnation=ref.incarnation,
        )

    def _readback_evidence(
        self,
        scope: RuntimeScope,
        intent: CommitIntent,
        candidate: object,
    ) -> CanonicalCommit:
        if not isinstance(candidate, EvidenceRelationCandidate):
            raise AdmissionBindingError("relation readback requires exact candidate")
        qualification = candidate.qualification
        table = project_table(self.tables, "research_relations")
        project_key = assert_table_scope(table, scope)
        row = one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == project_key,
                    table.c.relation_id == intent.object_id,
                    table.c.revision == intent.expected_base_revision + 1,
                    table.c.incarnation == intent.expected_incarnation,
                )
            )
        )
        if row is None:
            raise ProjectRecordNotFound("evidence relation readback absent")
        expected = {
            "relation_type": {
                "SUPPORTS": "supports",
                "CONTRADICTS": "contradicts",
                "CONTEXT": "derived_from",
                "INSUFFICIENT": "opens",
            }[qualification.direction],
            "direction": qualification.direction,
            "scope_ref": qualification.scope_statement_ref,
            "uncertainty_profile_ref": qualification.uncertainty_profile_ref,
            "provenance_closure_digest": qualification.provenance_closure_digest,
            "source_object_ref": object_ref_text(candidate.source_ref),
            "target_object_ref": object_ref_text(candidate.target_ref),
            "validity_json": {
                "valid_from": qualification.validity.valid_from.isoformat()
                if qualification.validity.valid_from
                else None,
                "valid_to": qualification.validity.valid_to.isoformat()
                if qualification.validity.valid_to
                else None,
                "source_time": qualification.source_time.isoformat()
                if qualification.source_time
                else None,
                "observed_at": qualification.observed_at.isoformat()
                if qualification.observed_at
                else None,
                "claim_ref": qualification.claim_ref,
                "verifier_profile_ref": qualification.verifier_profile_ref,
            },
            "state": qualification.state,
        }
        if any(row[key] != value for key, value in expected.items()):
            raise AdmissionBindingError("evidence relation readback drift")
        return _canonical_commit(
            intent,
            canonical_ref=(
                f"canonical:research-relation:{qualification.qualification_id}:"
                f"{qualification.revision}"
            ),
            revision=qualification.revision,
            incarnation=qualification.incarnation,
        )

    def _readback_delivery(
        self,
        scope: RuntimeScope,
        intent: CommitIntent,
        candidate: object,
    ) -> CanonicalCommit:
        if not isinstance(candidate, DeliveryReceiptCandidate):
            raise AdmissionBindingError("delivery readback requires exact candidate")
        ref = self.ledger.get_object(
            scope,
            intent.object_id,
            expected_revision=intent.expected_base_revision + 1,
            expected_incarnation=intent.expected_incarnation,
        )
        receipt_table = project_table(self.tables, "successor_receipts")
        project_key = assert_table_scope(receipt_table, scope)
        receipt = one_mapping(
            self.connection.execute(
                select(receipt_table).where(
                    receipt_table.c.project_key == project_key,
                    receipt_table.c.receipt_id == ref.object_id,
                    receipt_table.c.receipt_digest
                    == candidate.receipt.receipt_digest,
                )
            )
        )
        if receipt is None or ref != candidate.ref:
            raise ProjectRecordNotFound("exact delivery receipt readback absent")
        exact_receipt = (
            bytes(receipt["receipt_bytes"])
            if receipt["receipt_bytes"] is not None
            else canonical_bytes(receipt["receipt_json"])
        )
        expected_receipt = (
            candidate.receipt_content
            if isinstance(candidate.receipt_content, bytes)
            else canonical_bytes(candidate.receipt_content)
        )
        if (
            exact_receipt != expected_receipt
            or hashlib.sha256(exact_receipt).hexdigest()
            != candidate.receipt.receipt_digest
            or receipt["delivery_intent_ref"]
            != candidate.receipt.delivery_intent_ref
            or receipt["attempt_ref"] != candidate.receipt.attempt_ref
            or receipt["provider_locator"] != candidate.receipt.provider_locator
        ):
            raise AdmissionBindingError("delivery receipt authoritative readback drift")
        relation_table = project_table(self.tables, "research_relations")
        delivered = one_mapping(
            self.connection.execute(
                select(relation_table).where(
                    relation_table.c.project_key == project_key,
                    relation_table.c.relation_id
                    == candidate.delivered_as.relation_id,
                    relation_table.c.revision
                    == candidate.delivered_as.revision,
                    relation_table.c.incarnation
                    == candidate.delivered_as.incarnation,
                )
            )
        )
        if delivered is None:
            raise ProjectRecordNotFound("delivered_as readback absent")
        expected_relation = {
            "relation_type": "delivered_as",
            "source_object_ref": object_ref_text(candidate.artifact_ref),
            "target_object_ref": object_ref_text(candidate.ref),
            "provenance_closure_digest": (
                candidate.delivered_as.provenance_closure_digest
            ),
            "state": candidate.delivered_as.state,
        }
        if any(
            delivered[key] != value for key, value in expected_relation.items()
        ):
            raise AdmissionBindingError("delivered_as authoritative readback drift")
        return _canonical_commit(
            intent,
            canonical_ref=f"canonical:delivery-receipt:{ref.object_id}:{ref.revision}",
            revision=ref.revision,
            incarnation=ref.incarnation,
        )

    def _require_intent(self, scope: RuntimeScope, intent: CommitIntent) -> None:
        if intent.canonical_owner != self.canonical_owner:
            raise AdmissionBindingError("commit intent canonical owner drift")
        if (
            intent.project_key != scope.project_scope.project_key
            or intent.project_registry_revision
            != scope.project_scope.project_registry_revision
            or intent.project_scope_digest != scope.project_scope.scope_digest
        ):
            raise AdmissionBindingError("commit intent project scope drift")

    @staticmethod
    def _validate_object_candidate(
        intent: CommitIntent,
        candidate: ResearchObjectCandidate,
        *,
        allowed_payloads: tuple[type[Any], ...],
        allowed_types: tuple[str, ...],
    ) -> None:
        if not isinstance(candidate.payload, allowed_payloads):
            raise AdmissionBindingError("candidate payload is wrong for exact operation")
        ref = candidate.ref
        if ref.object_type.type_id not in allowed_types:
            raise AdmissionBindingError("candidate object type is wrong for exact operation")
        if (
            ref.object_id != intent.object_id
            or ref.content_digest != intent.content_digest
            or getattr(candidate.payload, "content_digest", None) != ref.content_digest
        ):
            raise AdmissionBindingError("research object identity/content drift")


class DeliveryIntentAdmission:
    """Admit the intent object without confusing it with DeliveryAttempt/receipt."""

    def __init__(self, ledger: ResearchLedgerRepository) -> None:
        self.ledger = ledger

    def put_exact(
        self, scope: RuntimeScope, candidate: DeliveryIntentCandidate
    ) -> ResearchObjectRef:
        if candidate.ref.object_type.type_id != DELIVERY_INTENT_TYPE.type_id:
            raise AdmissionBindingError("delivery intent owner requires DeliveryIntent.v1")
        if (
            candidate.intent.content_digest != candidate.ref.content_digest
            or candidate.intent.delivery_intent_id != candidate.ref.object_id
            or candidate.ref.owner_binding_ref != "ResearchLedger"
        ):
            raise AdmissionBindingError("delivery intent exact owner/content drift")
        return self.ledger.put_object(
            scope,
            candidate.ref,
            expected_revision=candidate.expected_revision,
            expected_incarnation=candidate.expected_incarnation,
        )

    def reject_runtime_attempt(self, value: DeliveryAttempt) -> None:
        raise AdmissionBindingError(
            f"{type(value).__name__} is Execution Journal-owned, not Research Ledger-owned"
        )


class PostgresCommitIntentAdapter:
    """Adapt the P0-B repository to the infrastructure-free coordinator Port."""

    def __init__(self, repository: CommitIntentRepository) -> None:
        self.repository = repository

    def prepare(self, binding: object) -> Mapping[str, Any]:
        if not isinstance(binding, CommitIntentBinding):
            raise TypeError("Postgres commit intent requires CommitIntentBinding")
        return self.repository.prepare(binding)

    def load(self, commit_intent_id: str) -> Mapping[str, Any]:
        return self.repository.load(commit_intent_id)

    def mark_committed(
        self,
        commit_intent_id: str,
        *,
        expected_revision: int,
        canonical_commit_ref: str,
        receipt_digest: str,
    ) -> Mapping[str, Any]:
        return self.repository.record_result(
            commit_intent_id,
            expected_revision=expected_revision,
            status=CommitIntentStatus.COMMITTED,
            canonical_commit_ref=canonical_commit_ref,
            receipt_digest=receipt_digest,
        )

    def mark_outcome_unknown(
        self, commit_intent_id: str, *, expected_revision: int
    ) -> Mapping[str, Any]:
        return self.repository.record_result(
            commit_intent_id,
            expected_revision=expected_revision,
            status=CommitIntentStatus.UNKNOWN,
        )


def commit_binding_from_assignment(
    *, assignment: RuntimeAssignment, intent: CommitIntent
) -> CommitIntentBinding:
    if assignment.step_id is None:
        raise AdmissionBindingError("commit intent requires step-scoped assignment")
    return CommitIntentBinding(
        commit_intent_id=intent.commit_intent_id,
        run_id=assignment.run_id,
        step_id=assignment.step_id,
        capability_id=assignment.capability_id,
        canonical_owner_ref=intent.canonical_owner,
        object_identity_ref=intent.object_id,
        expected_base_revision=intent.expected_base_revision,
        expected_base_incarnation=intent.expected_incarnation,
        content_digest=intent.content_digest,
        event_digest=intent.ordered_event_closure_digest,
        verification_digest=intent.verification_binding_digest,
        authority_digest=intent.authority_digest,
        idempotency_key=intent.idempotency_key,
    )


def build_first_specimen_admission_registry(
    *,
    connection: Connection,
    tables: Any,
    bundle: FirstSpecimenCapabilityBundle,
) -> ExactAdmissionRegistry:
    modes = {
        "evidence.qualify.v1": ResearchAdmissionMode.EVIDENCE_RELATION,
        "claim.form_or_open_gap.v1": ResearchAdmissionMode.CLAIM_OR_GAP_OBJECT,
        "artifact.compose_markdown.v1": ResearchAdmissionMode.ARTIFACT_OBJECT,
        "delivery.internal_export.v1": (
            ResearchAdmissionMode.DELIVERY_RECEIPT_EXTERNAL_REF
        ),
    }
    registrations = []
    for kind, mode in modes.items():
        contract = bundle.operation_by_kind(kind)
        handler = ResearchAdmissionHandler(
            connection=connection,
            tables=tables,
            operation_contract_ref=contract.ref,
            mode=mode,
        )
        registrations.append(
            AdmissionRegistration(
                operation_contract_ref=contract.ref,
                handler=handler,
            )
        )
    return ExactAdmissionRegistry(registrations)


def _canonical_commit(
    intent: CommitIntent,
    *,
    canonical_ref: str,
    revision: int,
    incarnation: str,
) -> CanonicalCommit:
    body = {
        "schema_version": "mrw.research-admission.receipt.v1",
        "commit_intent_id": intent.commit_intent_id,
        "canonical_owner": intent.canonical_owner,
        "project_key": intent.project_key,
        "object_id": intent.object_id,
        "canonical_ref": canonical_ref,
        "canonical_revision": revision,
        "canonical_incarnation": incarnation,
        "content_digest": intent.content_digest,
    }
    return CanonicalCommit(
        **body,
        receipt_digest=canonical_digest(body),
    )


__all__ = [
    "AtomicResearchAdmissionCommand",
    "DeliveryIntentAdmission",
    "DeliveryIntentCandidate",
    "DeliveryReceiptCandidate",
    "EvidenceRelationCandidate",
    "PostgresCommitIntentAdapter",
    "ResearchAdmissionHandler",
    "ResearchAdmissionMode",
    "ResearchObjectCandidate",
    "build_first_specimen_admission_registry",
    "commit_binding_from_assignment",
]
