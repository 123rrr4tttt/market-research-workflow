"""Human/authority/base-artifact gate for P0-C internal delivery.

The Program may describe an internal export, but description is not
authorization.  This gate re-reads all three mutable authorities inside one
UoW before it creates the canonical ``DeliveryIntent`` and a READY assignment.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol, cast

from app.successor_runtime.capabilities import persist_internal_export_payload
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.research.artifacts import (
    DELIVERY_CHANNEL,
    DELIVERY_FORMAT,
    DELIVERY_IRREVERSIBILITY_PROFILE,
    DeliveryIntent,
    artifact_identity_ref,
)
from app.successor_runtime.research.codec import canonical_bytes, sha256_hex
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import DELIVERY_INTENT_TYPE, ObjectType


DELIVERY_TEMPLATE_TYPE = ObjectType("DeliveryIntentTemplate.v1")


class DeliveryGateRejected(RuntimeError):
    """One exact approval, authority, or artifact binding is no longer current."""


@dataclass(frozen=True, slots=True)
class DeliveryIntentTemplate:
    value_id: str
    delivery_intent_id: str
    audience: str
    approval_ref: str
    authority_digest: str
    idempotency_key: str
    channel: str = DELIVERY_CHANNEL
    format: str = DELIVERY_FORMAT
    irreversibility_profile: str = DELIVERY_IRREVERSIBILITY_PROFILE

    def __post_init__(self) -> None:
        required = (
            self.value_id,
            self.delivery_intent_id,
            self.audience,
            self.approval_ref,
            self.idempotency_key,
        )
        if any(not value for value in required):
            raise ValueError("delivery template identities must be non-empty")
        if (
            len(self.authority_digest) != 64
            or any(char not in "0123456789abcdef" for char in self.authority_digest)
            or self.authority_digest == "0" * 64
        ):
            raise ValueError("delivery template requires a non-placeholder authority digest")
        if self.channel != DELIVERY_CHANNEL or self.format != DELIVERY_FORMAT:
            raise ValueError("first specimen permits only internal markdown export")
        if self.irreversibility_profile != DELIVERY_IRREVERSIBILITY_PROFILE:
            raise ValueError("delivery template irreversibility profile drift")

    def to_payload(self) -> dict[str, object]:
        return {
            "delivery_intent_id": self.delivery_intent_id,
            "audience": self.audience,
            "channel": self.channel,
            "format": self.format,
            "approval_refs": [self.approval_ref],
            "authority_digest": self.authority_digest,
            "idempotency_key": self.idempotency_key,
            "irreversibility_profile": self.irreversibility_profile,
        }

    def candidate(self, artifact_ref: str) -> DeliveryIntent:
        return DeliveryIntent(
            delivery_intent_id=self.delivery_intent_id,
            artifact_ref=artifact_ref,
            audience=self.audience,
            channel=self.channel,
            format=self.format,
            approval_refs=(self.approval_ref,),
            authority_digest=self.authority_digest,
            idempotency_key=self.idempotency_key,
            irreversibility_profile=self.irreversibility_profile,
        )


@dataclass(frozen=True, slots=True)
class DeliveryAuthoritySnapshot:
    capability_id: str
    authority_epoch: int
    authority_digest: str
    claim_policy_digest: str
    successor_claim_enabled: bool
    legacy_claim_enabled: bool

    def __post_init__(self) -> None:
        if self.authority_epoch < 0:
            raise ValueError("authority epoch must be non-negative")
        for name in ("authority_digest", "claim_policy_digest"):
            value = getattr(self, name)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{name} must be canonical sha256 hex")
        if self.successor_claim_enabled == self.legacy_claim_enabled:
            raise ValueError("delivery authority must select exactly one claim owner")


@dataclass(frozen=True, slots=True)
class DeliveryApprovalSnapshot:
    approval_id: str
    revision: int
    actor_id: str
    run_id: str
    step_id: str
    payload_digest: str
    authority_digest: str
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.revision < 0:
            raise ValueError("approval revision must be non-negative")
        if any(
            not value
            for value in (self.approval_id, self.actor_id, self.run_id, self.step_id)
        ):
            raise ValueError("approval exact identities must be non-empty")
        for name in ("payload_digest", "authority_digest"):
            value = getattr(self, name)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"approval {name} must be canonical sha256 hex")
        if self.expires_at.tzinfo is None:
            raise ValueError("approval expiry must be timezone-aware")


@dataclass(frozen=True, slots=True)
class DeliveryAssignmentParameters:
    runtime_protocol_version: str
    work_item_id: str
    run_id: str
    step_id: str
    capability_id: str
    operation_contract_ref: OperationContractRef
    return_contract_binding: object
    handler_binding: object
    recovery_binding: object
    program_digest: str
    plan_digest: str
    deployment_catalog_digest: str
    execution_epoch: int
    incarnation: str
    queue_eligibility_digest: str
    qualification_digest: str
    required_node_profile_selector: str
    resource_policy_digest: str
    fairness_key: str
    resource_class: str
    resource_units: int
    concurrency_key: str
    resource_policy_epoch: int
    expected_step_revision: int
    trace_id: str
    deadline_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.operation_contract_ref.kind != "delivery.internal_export.v1":
            raise ValueError("delivery assignment must bind delivery.internal_export.v1")
        if (
            getattr(self.handler_binding, "operation_contract_digest", None)
            != self.operation_contract_ref.contract_digest
        ):
            raise ValueError("delivery interpreter binds a different operation contract")
        if (
            getattr(self.recovery_binding, "interpreter_profile_digest", None)
            != getattr(self.handler_binding, "interpreter_profile_digest", None)
        ):
            raise ValueError("delivery recovery binding must close over the interpreter profile")
        if self.resource_units <= 0:
            raise ValueError("delivery resource_units must be positive")
        if any(
            not value
            for value in (
                self.required_node_profile_selector,
                self.fairness_key,
                self.resource_class,
                self.concurrency_key,
            )
        ):
            raise ValueError("delivery queue/resource bindings must be non-empty")
        for name in (
            "program_digest",
            "plan_digest",
            "deployment_catalog_digest",
            "queue_eligibility_digest",
            "qualification_digest",
            "resource_policy_digest",
        ):
            value = getattr(self, name)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"delivery {name} must be canonical sha256 hex")


@dataclass(frozen=True, slots=True)
class DeliveryGateCommand:
    scope: object
    template: DeliveryIntentTemplate
    artifact: ResearchObjectRef
    artifact_expected_revision: int
    artifact_expected_incarnation: str
    assignment: DeliveryAssignmentParameters
    value_incarnation: str
    intent_incarnation: str
    now: datetime

    def __post_init__(self) -> None:
        project_key = _project_key(self.scope)
        if self.artifact.project_key != project_key:
            raise ValueError("delivery artifact is outside RuntimeScope")
        if self.artifact.object_type.type_id != "ResearchArtifact.v1":
            raise ValueError("delivery gate requires a ResearchArtifact.v1 base")
        if self.artifact.revision != self.artifact_expected_revision:
            raise ValueError("artifact expected revision is not exact")
        if self.artifact.incarnation != self.artifact_expected_incarnation:
            raise ValueError("artifact expected incarnation is not exact")
        if self.assignment.run_id == "" or self.assignment.step_id == "":
            raise ValueError("delivery assignment run/step identity is required")


@dataclass(frozen=True, slots=True)
class DeliveryReadyPacket:
    intent: DeliveryIntent
    intent_ref: ResearchObjectRef
    intent_value_ref: ValueRef
    export_payload_ref: ValueRef
    artifact_ref: ResearchObjectRef
    approval: DeliveryApprovalSnapshot
    authority: DeliveryAuthoritySnapshot
    assignment: object
    recovery_binding: object
    qualification_digest: str
    required_node_profile_selector: str
    resource_policy_digest: str
    fairness_key: str
    resource_class: str
    resource_units: int
    concurrency_key: str
    ready_at: datetime
    state: str = "READY"


@dataclass(frozen=True, slots=True)
class DeliveryGateReceipt:
    packet: DeliveryReadyPacket
    runtime_receipt: object


class _UoW(Protocol):
    def __enter__(self) -> "_UoW": ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    def commit(self) -> None: ...


class DeliveryValuePort(Protocol):
    def put_exact(
        self,
        scope: object,
        *,
        value_id: str,
        object_type: str,
        codec_id: str,
        content: bytes,
        expected_digest: str,
        provenance_digest: str,
        expected_revision: int,
        expected_incarnation: str,
        source_ref: str | None = None,
        provenance: dict[str, object] | None = None,
    ) -> object: ...


class DeliveryLedgerPort(Protocol):
    def get_object(
        self,
        scope: object,
        object_id: str,
        *,
        expected_revision: int,
        expected_incarnation: str,
    ) -> ResearchObjectRef: ...

    def put_object(
        self,
        scope: object,
        ref: ResearchObjectRef,
        *,
        expected_revision: int,
        expected_incarnation: str,
    ) -> ResearchObjectRef: ...


class DeliveryApprovalPort(Protocol):
    def require_current(
        self,
        scope: object,
        approval_id: str,
        *,
        run_id: str,
        step_id: str,
        payload_digest: str,
        authority_digest: str,
        now: datetime,
    ) -> DeliveryApprovalSnapshot: ...


class DeliveryAuthorityPort(Protocol):
    def current_delivery_authority(
        self, scope: object, capability_id: str
    ) -> DeliveryAuthoritySnapshot: ...


class DeliveryRuntimePort(Protocol):
    def get_delivery_admission(
        self, scope: object, delivery_intent_id: str
    ) -> DeliveryGateReceipt | None: ...

    def admit_delivery(
        self, scope: object, packet: DeliveryReadyPacket
    ) -> object: ...


PortFactory = Callable[[_UoW], object]
AssignmentFactory = Callable[["DeliveryAssignmentRequest"], object]


@dataclass(frozen=True, slots=True)
class DeliveryAssignmentRequest:
    parameters: DeliveryAssignmentParameters
    project_key: str
    artifact_content_ref: str
    intent: DeliveryIntent
    intent_value_ref: ValueRef
    export_payload_ref: ValueRef
    authority: DeliveryAuthoritySnapshot


def _project_key(scope: object) -> str:
    project_scope = getattr(scope, "project_scope", None)
    project_key = getattr(project_scope, "project_key", None)
    if not isinstance(project_key, str) or not project_key:
        raise TypeError("delivery scope must expose a validated project_scope")
    return project_key


def _artifact_locator(ref: ResearchObjectRef) -> str:
    return artifact_identity_ref(ref.object_id, ref.revision, ref.content_digest)


def _value_ref(
    *,
    command: DeliveryGateCommand,
    content: bytes,
    provenance_digest: str,
) -> ValueRef:
    return ValueRef(
        value_id=command.template.delivery_intent_id,
        project_key=_project_key(command.scope),
        object_type=DELIVERY_INTENT_TYPE,
        codec_id=DELIVERY_INTENT_TYPE.codec_id,
        content_digest=hashlib.sha256(content).hexdigest(),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{command.template.delivery_intent_id}",
        byte_size=len(content),
        provenance_digest=provenance_digest,
    )


class DeliveryGate:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], _UoW],
        value_port: PortFactory,
        ledger_port: PortFactory,
        approval_port: PortFactory,
        authority_port: PortFactory,
        runtime_port: PortFactory,
        assignment_factory: AssignmentFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._value_port = value_port
        self._ledger_port = ledger_port
        self._approval_port = approval_port
        self._authority_port = authority_port
        self._runtime_port = runtime_port
        self._assignment_factory = assignment_factory

    def admit(self, command: DeliveryGateCommand) -> DeliveryGateReceipt:
        with self._uow_factory() as uow:
            values = self._value_port(uow)
            ledger = self._ledger_port(uow)
            approvals = self._approval_port(uow)
            authorities = self._authority_port(uow)
            runtime = self._runtime_port(uow)
            runtime = cast(DeliveryRuntimePort, runtime)
            existing = runtime.get_delivery_admission(
                command.scope, command.template.delivery_intent_id
            )
            if existing is not None:
                return existing

            ledger = cast(DeliveryLedgerPort, ledger)
            current_artifact = ledger.get_object(
                command.scope,
                command.artifact.object_id,
                expected_revision=command.artifact_expected_revision,
                expected_incarnation=command.artifact_expected_incarnation,
            )
            if current_artifact != command.artifact:
                raise DeliveryGateRejected("canonical base artifact drift")

            authorities = cast(DeliveryAuthorityPort, authorities)
            authority = authorities.current_delivery_authority(
                command.scope, command.assignment.capability_id
            )
            if not authority.successor_claim_enabled or authority.legacy_claim_enabled:
                raise DeliveryGateRejected("successor does not hold exclusive delivery claim")
            if authority.authority_digest != command.template.authority_digest:
                raise DeliveryGateRejected("delivery authority digest drift")
            if (
                getattr(
                    command.assignment.handler_binding,
                    "authority_requirement_digest",
                    None,
                )
                != authority.authority_digest
            ):
                raise DeliveryGateRejected("interpreter authority requirement drift")

            intent = command.template.candidate(_artifact_locator(current_artifact))
            assert intent.content_digest is not None
            approvals = cast(DeliveryApprovalPort, approvals)
            approval = approvals.require_current(
                command.scope,
                command.template.approval_ref,
                run_id=command.assignment.run_id,
                step_id=command.assignment.step_id,
                payload_digest=intent.content_digest,
                authority_digest=authority.authority_digest,
                now=command.now,
            )
            if (
                approval.approval_id != command.template.approval_ref
                or approval.payload_digest != intent.content_digest
                or approval.authority_digest != authority.authority_digest
            ):
                raise DeliveryGateRejected("human approval exact binding drift")

            exact = canonical_bytes(intent)
            provenance = {
                "artifact_ref": _artifact_locator(current_artifact),
                "artifact_content_digest": current_artifact.content_digest,
                "artifact_revision": current_artifact.revision,
                "artifact_incarnation": current_artifact.incarnation,
                "approval_ref": approval.approval_id,
                "approval_revision": approval.revision,
                "authority_digest": authority.authority_digest,
                "authority_epoch": authority.authority_epoch,
            }
            provenance_digest = sha256_hex(provenance)
            intent_value_ref = _value_ref(
                command=command,
                content=exact,
                provenance_digest=provenance_digest,
            )
            values = cast(DeliveryValuePort, values)
            values.put_exact(
                command.scope,
                value_id=intent_value_ref.value_id,
                object_type=DELIVERY_INTENT_TYPE.type_id,
                codec_id=DELIVERY_INTENT_TYPE.codec_id,
                content=exact,
                expected_digest=intent_value_ref.content_digest,
                provenance_digest=provenance_digest,
                expected_revision=0,
                expected_incarnation=command.value_incarnation,
                source_ref=current_artifact.content_ref,
                provenance=provenance,
            )
            intent_ref = ResearchObjectRef(
                object_id=intent.delivery_intent_id,
                object_type=DELIVERY_INTENT_TYPE,
                project_key=_project_key(command.scope),
                revision=1,
                incarnation=command.intent_incarnation,
                owner_binding_ref="ResearchLedger",
                content_ref=intent_value_ref.storage_ref,
                content_digest=intent_value_ref.content_digest,
                provenance_closure_digest=provenance_digest,
                lifecycle_state="ADMITTED",
            )
            ledger.put_object(
                command.scope,
                intent_ref,
                expected_revision=0,
                expected_incarnation=command.intent_incarnation,
            )

            export_payload_ref = persist_internal_export_payload(
                values,
                command.scope,
                project_key=_project_key(command.scope),
                run_id=command.assignment.run_id,
                intent=intent,
                artifact_ref=_artifact_locator(current_artifact),
                expected_incarnation=(
                    f"{command.value_incarnation}:internal-export-payload"
                ),
            )

            params = command.assignment
            assignment = self._assignment_factory(
                DeliveryAssignmentRequest(
                    parameters=params,
                    project_key=_project_key(command.scope),
                    artifact_content_ref=current_artifact.content_ref,
                    intent=intent,
                    intent_value_ref=intent_value_ref,
                    export_payload_ref=export_payload_ref,
                    authority=authority,
                )
            )
            _validate_ready_assignment(
                assignment,
                command,
                intent,
                intent_value_ref,
                export_payload_ref,
                authority,
            )
            packet = DeliveryReadyPacket(
                intent=intent,
                intent_ref=intent_ref,
                intent_value_ref=intent_value_ref,
                export_payload_ref=export_payload_ref,
                artifact_ref=current_artifact,
                approval=approval,
                authority=authority,
                assignment=assignment,
                recovery_binding=params.recovery_binding,
                qualification_digest=params.qualification_digest,
                required_node_profile_selector=params.required_node_profile_selector,
                resource_policy_digest=params.resource_policy_digest,
                fairness_key=params.fairness_key,
                resource_class=params.resource_class,
                resource_units=params.resource_units,
                concurrency_key=params.concurrency_key,
                ready_at=command.now,
            )
            runtime_receipt = runtime.admit_delivery(command.scope, packet)
            receipt = DeliveryGateReceipt(packet=packet, runtime_receipt=runtime_receipt)
            uow.commit()
            return receipt


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _validate_ready_assignment(
    assignment: object,
    command: DeliveryGateCommand,
    intent: DeliveryIntent,
    intent_value_ref: ValueRef,
    export_payload_ref: ValueRef,
    authority: DeliveryAuthoritySnapshot,
) -> None:
    expected = {
        "assignment_kind": "INTERPRET",
        "project_key": _project_key(command.scope),
        "run_id": command.assignment.run_id,
        "step_id": command.assignment.step_id,
        "program_digest": command.assignment.program_digest,
        "plan_digest": command.assignment.plan_digest,
        "payload_ref": export_payload_ref.storage_ref,
        "payload_digest": export_payload_ref.content_digest,
        "claim_authority_epoch": authority.authority_epoch,
        "claim_policy_digest": authority.claim_policy_digest,
    }
    mismatches = [
        field
        for field, value in expected.items()
        if _enum_value(getattr(assignment, field, None)) != value
    ]
    if mismatches:
        raise DeliveryGateRejected(
            "READY assignment exact binding drift: " + ", ".join(mismatches)
        )
    if not getattr(assignment, "assignment_digest", None):
        raise DeliveryGateRejected("READY assignment lacks exact digest")


__all__ = [
    "DeliveryApprovalSnapshot",
    "DeliveryAssignmentRequest",
    "DeliveryAssignmentParameters",
    "DeliveryAuthoritySnapshot",
    "DeliveryGate",
    "DeliveryGateCommand",
    "DeliveryGateReceipt",
    "DeliveryGateRejected",
    "DeliveryIntentTemplate",
    "DeliveryReadyPacket",
]
