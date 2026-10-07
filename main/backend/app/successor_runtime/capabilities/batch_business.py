"""Typed business-wait operation that follows the broker dispatch ACK.

The dispatch Atom publishes an ``BatchTaskSingleDispatchAck``; the wait Atom
takes that ACK as its only semantic input and produces a precise typed
``BatchBusinessResult`` once the broker reports a terminal business outcome.
Waiting (``PENDING``) is not a result: the wait kernel raises
``OutcomeUncertain`` so the runtime enters the normal reconcile path instead
of manufacturing success from a broker ACK.

This module is capability-boundary only: it imports the frozen batch-task
dispatch vocabulary and defines the wait codec/type/profiles/contract, but
never imports legacy agent-batch services and never performs network, database,
provider or credential work.
"""

from __future__ import annotations

from typing import Annotated

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol, TypeAlias

from app.successor_runtime.capabilities import batch_task as batch_task
from app.successor_runtime.capabilities.checksum import (
    CanonicalJsonArray as CanonicalJsonArray,
    CanonicalJsonObject as CanonicalJsonObject,
    CanonicalJsonValue,
    content_digest,
)
from app.successor_runtime.capabilities.catalog import build_operation_catalog
from app.successor_runtime.capabilities.codecs import (
    PayloadCodec,
    dataclass_codec,
)
from app.successor_runtime.capabilities.profiles import (
    OperationProfiles,
    build_operation_profiles,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    OperationContract,
    OperationContractRef,
)
from app.successor_runtime.research.object_types import ObjectType


BUSINESS_WAIT_KIND = "batch.business.wait.v2"
BUSINESS_WAIT_OPERATION_ID = BUSINESS_WAIT_KIND
BUSINESS_WAIT_OWNER = batch_task.BATCH_TASK_OWNER
BUSINESS_WAIT_RESULT_SCHEMA = "mrw.batch.business.result.v2"
BUSINESS_WAIT_RESULT_CODEC_ID = "mrw.batch.business.result.codec.v2"
BUSINESS_WAIT_OBSERVATION_PROFILE = "mrw.batch.business.observation.v2"
BUSINESS_WAIT_CATALOG_ID = batch_task.BATCH_TASK_CATALOG_ID
BUSINESS_WAIT_CATALOG_VERSION = "1.0.0"
BUSINESS_WAIT_SEMANTIC_IDENTITY = "batch.business.wait"


BUSINESS_WAIT_RESULT_TYPE = ObjectType(
    "BatchBusinessResult.v1",
    codec_id=BUSINESS_WAIT_RESULT_CODEC_ID,
)


class BusinessTaskState(StrEnum):
    """Closed business terminal/waiting state independent of broker wording."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PENDING = "PENDING"
    REVOKED = "REVOKED"
    UNKNOWN = "UNKNOWN"
    NOT_STARTED = "NOT_STARTED"


@dataclass(frozen=True, slots=True)
class BusinessTaskObservation:
    """One typed broker observation with the real JSON output or failure error."""

    task_id: str
    state: BusinessTaskState
    result: CanonicalJsonValue | None = None
    traceback: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.task_id:
            # kit:boundary owner=batch.business class=PROGRAMMER_DEFECT failure_family=none witness=test:test_business_result_rejects_invalid_identity_and_digest
            raise ValueError("business task observation requires task_id")


@dataclass(frozen=True, slots=True)
class BusinessCancelObservation:
    """Typed broker cancellation request; terminal state stays with readback."""

    task_id: str
    state: Literal["REVOKE_REQUESTED", "REVOKE_FAILED"]
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.task_id:
            # kit:boundary owner=batch.business class=PROGRAMMER_DEFECT failure_family=none witness=test:test_business_result_rejects_invalid_identity_and_digest
            raise ValueError("business cancel observation requires task_id")


class BrokerBusinessReadback(Protocol):
    """Capability-limited broker observer: read and cancel only, no dispatch."""

    def read_task(self, task_id: str) -> BusinessTaskObservation: ...

    def cancel_task(self, task_id: str) -> BusinessCancelObservation: ...


@dataclass(frozen=True, slots=True)
class BatchBusinessResult:
    """Precise typed terminal produced by the business wait Atom."""

    schema_version: Literal["mrw.batch.business.result.v2"]
    operation_kind: Literal["batch.business.wait.v2"]
    task_id: str
    provider_locator: str
    receipt_digest: str
    output: CanonicalJsonValue = None
    result_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != BUSINESS_WAIT_RESULT_SCHEMA:
            # kit:boundary owner=batch.business class=PROGRAMMER_DEFECT failure_family=none witness=test:test_business_result_rejects_invalid_identity_and_digest
            raise ValueError("unsupported business result schema")
        if self.operation_kind != BUSINESS_WAIT_KIND:
            # kit:boundary owner=batch.business class=PROGRAMMER_DEFECT failure_family=none witness=test:test_business_result_rejects_invalid_identity_and_digest
            raise ValueError("unsupported business result operation kind")
        for name in ("task_id", "provider_locator", "receipt_digest"):
            if not getattr(self, name):
                # kit:boundary owner=batch.business class=PROGRAMMER_DEFECT failure_family=none witness=test:test_business_result_rejects_invalid_identity_and_digest
                raise ValueError(f"business result requires {name}")
        if self.result_digest == "":
            object.__setattr__(
                self,
                "result_digest",
                content_digest(self, omit_fields=("result_digest",)),
            )
        elif self.result_digest != content_digest(
            self, omit_fields=("result_digest",)
        ):
            # kit:boundary owner=batch.business class=PROGRAMMER_DEFECT failure_family=none witness=test:test_business_result_rejects_invalid_identity_and_digest
            raise ValueError("business result result_digest does not match content")


BusinessWaitInput: TypeAlias = batch_task.BatchTaskSingleDispatchAck


def build_batch_business_result(
    ack: batch_task.BatchTaskSingleDispatchAck,
    output: CanonicalJsonValue | None = None,
) -> Annotated[BatchBusinessResult, 'kit:non-authoritative derived_as=view fact_source=batch_business_typed_contract_and_observation witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift']:
    """Derive the precise terminal result from the accepted dispatch ACK."""

    return build_batch_business_result_from_ack_fields(
        task_id=ack.celery_task_id,
        ack_digest=ack.ack_digest,
        output=output,
    )


def build_batch_business_result_from_ack_fields(
    *,
    task_id: str,
    ack_digest: str,
    output: CanonicalJsonValue | None = None,
) -> Annotated[BatchBusinessResult, 'kit:non-authoritative derived_as=view fact_source=batch_business_typed_contract_and_observation witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift']:
    """Derive the precise terminal result from ACK identity fields only."""

    provider_locator = f"celery-task:{task_id}"
    receipt_digest = content_digest(
        {
            "schema_version": "mrw.batch.business-receipt.v1",
            "task_id": task_id,
            "provider_locator": provider_locator,
            "ack_digest": ack_digest,
            "output": output,
        }
    )
    return BatchBusinessResult(
        schema_version=BUSINESS_WAIT_RESULT_SCHEMA,
        operation_kind=BUSINESS_WAIT_KIND,
        task_id=task_id,
        provider_locator=provider_locator,
        output=output,
        receipt_digest=receipt_digest,
    )


def build_batch_business_wait_input_codec(
    contract_ref: OperationContractRef,
) -> Annotated[PayloadCodec[BusinessWaitInput], 'kit:non-authoritative derived_as=view fact_source=batch_business_typed_contract_and_observation witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift']:
    """The wait Atom consumes the dispatch ACK through its exact frozen codec."""

    return batch_task.build_batch_task_single_dispatch_ack_codec(contract_ref)


def build_batch_business_wait_result_codec(
    contract_ref: OperationContractRef,
) -> Annotated[PayloadCodec[BatchBusinessResult], 'kit:non-authoritative derived_as=view fact_source=batch_business_typed_contract_and_observation witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift']:
    """Flat typed codec for the business-wait terminal result."""

    return dataclass_codec(
        codec_id=BUSINESS_WAIT_RESULT_CODEC_ID,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=BUSINESS_WAIT_RESULT_TYPE.type_id,
        dto_cls=BatchBusinessResult,
    )


def build_batch_business_wait_profiles() -> Annotated[OperationProfiles, 'kit:non-authoritative derived_as=view fact_source=batch_business_typed_contract_and_observation witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift']:
    """Shared-rule profiles: a read-only business terminal, not a new dispatch."""

    return build_operation_profiles(
        identity="batch.business.wait",
        version="1.0.0",
        semantic={
            "reads": ("BatchTaskSingleDispatchAck.v1",),
            "creates": ("BatchBusinessResult.v1",),
            "creates_relations": (),
            "declared_loss": (),
            "observation_profile_ref": BUSINESS_WAIT_OBSERVATION_PROFILE,
        },
        effect={
            "execution_class": "EFFECTFUL",
            "external_visibility": "INTERNAL_ONLY",
            "network_required": True,
            "irreversible": False,
            "cancellation_points": ("claim_time",),
            "internal_export_only": False,
            "human_approval_required": False,
            "external_acquisition": False,
            "idempotency_profile_ref": batch_task.BATCH_TASK_IDEMPOTENCY_PROFILE,
        },
        resource={
            "resource_classes": ("NETWORK_IO",),
            "concurrency_key": "batch.business.wait",
            "budget_units": "units",
            "default_soft_limit_seconds": 5,
            "default_hard_limit_seconds": 30,
            "node_profile_selector": "any",
            "budget_ref": batch_task.BATCH_TASK_BUDGET_PROFILE,
            "deadline_policy_ref": batch_task.BATCH_TASK_DEADLINE_POLICY,
            "node_profile_requirements": ("any",),
            "units": 1,
        },
        failure={
            "typed_failures": (
                "BUSINESS_TASK_FAILURE",
                "BUSINESS_TASK_REVOKED",
                "BUSINESS_READBACK_UNAVAILABLE",
            ),
            "retryable": False,
            "degraded_acceptable": False,
            "unknown_outcome_supported": True,
            "readback_or_compensation": "readback",
            "failure_union_ref": batch_task.BATCH_TASK_FAILURE_UNION,
            "retryable_failure_kinds": (),
            "readback_profile_ref": BUSINESS_WAIT_OBSERVATION_PROFILE,
            "compensation_profile_ref": None,
        },
        authority={
            "grant_scopes": ("project",),
            "approval_required": False,
            "approval_kinds": (),
            "credential_refs": (),
            "canonical_owner": BUSINESS_WAIT_OWNER,
            "revalidation_points": ("claim_time",),
            "authority_epoch": 1,
        },
        interpreter={
            "interpreter_profile_id": "batch.business.wait.native",
            "supported_contract_kinds": (BUSINESS_WAIT_KIND,),
            "supported_contract_refs": (),
            "dependency_digest": content_digest(
                {
                    "interpreter": "batch.business.wait.native",
                    "version": "1.0.0",
                    "boundary": "business readback only; no redispatch",
                }
            ),
            "security_profile_ref": batch_task.BATCH_TASK_SECURITY_PROFILE,
            "resource_profile_ref": "batch.business.wait.resource@1.0.0",
            "credential_requirements_ref": None,
            "cancellation_profile_ref": "claim_time",
            "idempotency_profile_ref": batch_task.BATCH_TASK_IDEMPOTENCY_PROFILE,
            "authoritative_readback_profile_ref": None,
            "receipt_codec_ref": BUSINESS_WAIT_RESULT_CODEC_ID,
        },
        observation={
            "observation_profile_id": BUSINESS_WAIT_OBSERVATION_PROFILE,
            "dimensions": ("task_id", "attempt_id", "provider_locator"),
            "compatible_with_legacy": False,
            "observation_schema_ref": BUSINESS_WAIT_OBSERVATION_PROFILE,
        },
    )


def build_batch_business_wait_contract() -> Annotated[OperationContract, 'kit:non-authoritative derived_as=view fact_source=batch_business_typed_contract_and_observation witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift']:
    """The explicit wait step: ACK in, precise typed business result out."""

    return build_batch_business_wait_profiles().contract(
        kind=BUSINESS_WAIT_KIND,
        contract_version="1.0.0",
        input_type=batch_task.DISPATCH_SINGLE_ACK_TYPE,
        output_type=BUSINESS_WAIT_RESULT_TYPE,
        return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=BUSINESS_WAIT_OWNER,
    )


def build_batch_business_wait_catalog(
    contract: OperationContract | None = None,
) -> Annotated[OperationContractCatalogSnapshot, 'kit:non-authoritative derived_as=view fact_source=batch_business_typed_contract_and_observation witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift']:
    operation = contract or build_batch_business_wait_contract()
    return build_operation_catalog(
        (operation,),
        catalog_id=BUSINESS_WAIT_CATALOG_ID,
        catalog_version=BUSINESS_WAIT_CATALOG_VERSION,
    )


def build_batch_business_wait_registry(
    contract: OperationContract | None = None,
) -> Annotated[OperationContractRegistry, 'kit:non-authoritative derived_as=view fact_source=batch_business_typed_contract_and_observation witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift']:
    operation = contract or build_batch_business_wait_contract()
    return OperationContractRegistry(
        build_batch_business_wait_catalog(operation),
        (operation,),
    )


__all__ = [
    "BUSINESS_WAIT_CATALOG_ID",
    "BUSINESS_WAIT_CATALOG_VERSION",
    "BUSINESS_WAIT_KIND",
    "BUSINESS_WAIT_OBSERVATION_PROFILE",
    "BUSINESS_WAIT_OPERATION_ID",
    "BUSINESS_WAIT_OWNER",
    "BUSINESS_WAIT_RESULT_CODEC_ID",
    "BUSINESS_WAIT_RESULT_SCHEMA",
    "BUSINESS_WAIT_RESULT_TYPE",
    "BUSINESS_WAIT_SEMANTIC_IDENTITY",
    "BatchBusinessResult",
    "BrokerBusinessReadback",
    "BusinessCancelObservation",
    "BusinessTaskObservation",
    "BusinessTaskState",
    "BusinessWaitInput",
    "build_batch_business_result",
    "build_batch_business_result_from_ack_fields",
    "build_batch_business_wait_catalog",
    "build_batch_business_wait_contract",
    "build_batch_business_wait_input_codec",
    "build_batch_business_wait_profiles",
    "build_batch_business_wait_registry",
    "build_batch_business_wait_result_codec",
]
