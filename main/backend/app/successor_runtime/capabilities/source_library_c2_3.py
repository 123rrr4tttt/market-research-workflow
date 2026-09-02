"""Frozen typed contracts and capability bundle for the C2.3 provider-effect atom.

DTOs/contracts live in ``source_library_c2_shared``; this module owns the
operation contract, profiles, codec and catalog/registry assembly and
re-exports the shared vocabulary for capability consumers.  No legacy service
import, network, credential bytes, filesystem, database or provider execution
is performed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.successor_runtime.capabilities import source_library_c2_shared as _shared
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.codecs import PayloadCodec, codec_digest
from app.successor_runtime.capabilities.contracts import OperationContract
from app.successor_runtime.capabilities.profiles import (
    AuthorityProfile,
    ContractProfileRef,
    EffectProfile,
    FailureProfile,
    InterpreterProfile,
    ObservationProfile,
    ResourceProfile,
    SemanticProfile,
)
from app.successor_runtime.language.algebra import freeze_json_object
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    make_operation_contract,
)
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "C2_3_DEFAULT_RESOURCE_POLICY",
    "C2_3_FAILURE_CODES",
    "C2_3_MAX_ARTIFACT_BYTES",
    "C2_3_MAX_RETRY_BUDGET",
    "C2_3_RESOURCE_POLICY_REF",
    "C2_3_TIMEOUT_SECONDS",
    "CANCELLED_PROVIDER_EFFECT_CODE",
    "SOURCE_LIBRARY_C2_3_CATALOG_ID",
    "SOURCE_LIBRARY_C2_3_CATALOG_VERSION",
    "SOURCE_LIBRARY_C2_3_KIND",
    "SOURCE_LIBRARY_C2_3_OPERATION_ID",
    "SOURCE_LIBRARY_C2_3_OWNER",
    "SOURCE_LIBRARY_C2_3_PAYLOAD_CODEC_ID",
    "SOURCE_LIBRARY_C2_3_PAYLOAD_SCHEMA",
    "SOURCE_LIBRARY_C2_3_SEMANTIC_IDENTITY",
    "SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE",
    "AcceptedProviderEffect",
    "AuthoritativeProviderReadback",
    "CancelReceipt",
    "CancelledProviderEffect",
    "CapturedSourceRecordRef",
    "CompletedProviderEffect",
    "CredentialDecisionReceipt",
    "CredentialRef",
    "FailedProviderEffect",
    "NonStartProof",
    "NonStartUnprovable",
    "OrderedProviderFailure",
    "OutcomeUnknownProviderEffect",
    "PartiallyCompletedProviderEffect",
    "ProviderAttemptRef",
    "ProviderEffectOutcome",
    "ProviderEffectRequest",
    "ProviderReadbackResult",
    "ProviderReceipt",
    "ProviderResourcePolicy",
    "ReadbackTerminal",
    "ReadbackUnavailable",
    "ReadbackWaiting",
    "ReconciledProviderEffect",
    "RejectedProviderEffect",
    "StagedArtifactRef",
    "build_source_library_c2_3_bundle",
    "build_source_library_c2_3_catalog",
    "build_source_library_c2_3_registry",
    "provider_effect_outcomes_equal",
    "provider_effect_request_from_plain",
    "provider_receipt_digest",
]

_SHARED_EXPORTS = (
    "AcceptedProviderEffect",
    "AuthoritativeProviderReadback",
    "C2_3_DEFAULT_RESOURCE_POLICY",
    "C2_3_FAILURE_CODES",
    "C2_3_MAX_ARTIFACT_BYTES",
    "C2_3_MAX_RETRY_BUDGET",
    "C2_3_RESOURCE_POLICY_REF",
    "C2_3_TIMEOUT_SECONDS",
    "CANCELLED_PROVIDER_EFFECT_CODE",
    "CancelReceipt",
    "CancelledProviderEffect",
    "CapturedSourceRecordRef",
    "CompletedProviderEffect",
    "CredentialDecisionReceipt",
    "CredentialRef",
    "FailedProviderEffect",
    "NonStartProof",
    "NonStartUnprovable",
    "OrderedProviderFailure",
    "OutcomeUnknownProviderEffect",
    "PartiallyCompletedProviderEffect",
    "ProviderAttemptRef",
    "ProviderEffectOutcome",
    "ProviderEffectRequest",
    "ProviderReadbackResult",
    "ProviderReceipt",
    "ProviderResourcePolicy",
    "ReadbackTerminal",
    "ReadbackUnavailable",
    "ReadbackWaiting",
    "ReconciledProviderEffect",
    "RejectedProviderEffect",
    "SOURCE_LIBRARY_C2_3_CATALOG_ID",
    "SOURCE_LIBRARY_C2_3_CATALOG_VERSION",
    "SOURCE_LIBRARY_C2_3_KIND",
    "SOURCE_LIBRARY_C2_3_OPERATION_ID",
    "SOURCE_LIBRARY_C2_3_OWNER",
    "SOURCE_LIBRARY_C2_3_PAYLOAD_CODEC_ID",
    "SOURCE_LIBRARY_C2_3_PAYLOAD_SCHEMA",
    "SOURCE_LIBRARY_C2_3_SEMANTIC_IDENTITY",
    "SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE",
    "StagedArtifactRef",
    "provider_effect_outcomes_equal",
    "provider_receipt_digest",
)

AcceptedProviderEffect = _shared.AcceptedProviderEffect
AuthoritativeProviderReadback = _shared.AuthoritativeProviderReadback
C2_3_DEFAULT_RESOURCE_POLICY = _shared.C2_3_DEFAULT_RESOURCE_POLICY
C2_3_FAILURE_CODES = _shared.C2_3_FAILURE_CODES
C2_3_MAX_ARTIFACT_BYTES = _shared.C2_3_MAX_ARTIFACT_BYTES
C2_3_MAX_RETRY_BUDGET = _shared.C2_3_MAX_RETRY_BUDGET
C2_3_RESOURCE_POLICY_REF = _shared.C2_3_RESOURCE_POLICY_REF
C2_3_TIMEOUT_SECONDS = _shared.C2_3_TIMEOUT_SECONDS
CANCELLED_PROVIDER_EFFECT_CODE = _shared.CANCELLED_PROVIDER_EFFECT_CODE
CancelReceipt = _shared.CancelReceipt
CancelledProviderEffect = _shared.CancelledProviderEffect
CapturedSourceRecordRef = _shared.CapturedSourceRecordRef
CompletedProviderEffect = _shared.CompletedProviderEffect
CredentialDecisionReceipt = _shared.CredentialDecisionReceipt
CredentialRef = _shared.CredentialRef
FailedProviderEffect = _shared.FailedProviderEffect
NonStartProof = _shared.NonStartProof
NonStartUnprovable = _shared.NonStartUnprovable
OrderedProviderFailure = _shared.OrderedProviderFailure
OutcomeUnknownProviderEffect = _shared.OutcomeUnknownProviderEffect
PartiallyCompletedProviderEffect = _shared.PartiallyCompletedProviderEffect
ProviderAttemptRef = _shared.ProviderAttemptRef
ProviderEffectOutcome = _shared.ProviderEffectOutcome
ProviderEffectRequest = _shared.ProviderEffectRequest
ProviderReadbackResult = _shared.ProviderReadbackResult
ProviderReceipt = _shared.ProviderReceipt
ProviderResourcePolicy = _shared.ProviderResourcePolicy
ReadbackTerminal = _shared.ReadbackTerminal
ReadbackUnavailable = _shared.ReadbackUnavailable
ReadbackWaiting = _shared.ReadbackWaiting
ReconciledProviderEffect = _shared.ReconciledProviderEffect
RejectedProviderEffect = _shared.RejectedProviderEffect
SOURCE_LIBRARY_C2_3_CATALOG_ID = _shared.SOURCE_LIBRARY_C2_3_CATALOG_ID
SOURCE_LIBRARY_C2_3_CATALOG_VERSION = _shared.SOURCE_LIBRARY_C2_3_CATALOG_VERSION
SOURCE_LIBRARY_C2_3_KIND = _shared.SOURCE_LIBRARY_C2_3_KIND
SOURCE_LIBRARY_C2_3_OPERATION_ID = _shared.SOURCE_LIBRARY_C2_3_OPERATION_ID
SOURCE_LIBRARY_C2_3_OWNER = _shared.SOURCE_LIBRARY_C2_3_OWNER
SOURCE_LIBRARY_C2_3_PAYLOAD_CODEC_ID = _shared.SOURCE_LIBRARY_C2_3_PAYLOAD_CODEC_ID
SOURCE_LIBRARY_C2_3_PAYLOAD_SCHEMA = _shared.SOURCE_LIBRARY_C2_3_PAYLOAD_SCHEMA
SOURCE_LIBRARY_C2_3_SEMANTIC_IDENTITY = _shared.SOURCE_LIBRARY_C2_3_SEMANTIC_IDENTITY
SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE = (
    _shared.SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE
)
StagedArtifactRef = _shared.StagedArtifactRef
provider_effect_outcomes_equal = _shared.provider_effect_outcomes_equal
provider_receipt_digest = _shared.provider_receipt_digest

# Schema refs and type constants needed by the profile/operation assembly.
AUTHENTICATED_PROJECT_SCOPE_TYPE = _shared.AUTHENTICATED_PROJECT_SCOPE_TYPE
AuthenticatedProjectScope = _shared.AuthenticatedProjectScope
CHANNEL_CATALOG_SNAPSHOT_TYPE = _shared.CHANNEL_CATALOG_SNAPSHOT_TYPE
SOURCE_EXECUTION_REQUEST_SCHEMA_REF = _shared.SOURCE_EXECUTION_REQUEST_SCHEMA_REF
CREDENTIAL_REF_SCHEMA = _shared.CREDENTIAL_REF_SCHEMA
PROVIDER_EFFECT_REQUEST_SCHEMA = _shared.PROVIDER_EFFECT_REQUEST_SCHEMA
PROVIDER_RECEIPT_SCHEMA = _shared.PROVIDER_RECEIPT_SCHEMA
AUTHORITATIVE_READBACK_SCHEMA = _shared.AUTHORITATIVE_READBACK_SCHEMA
NON_START_PROOF_SCHEMA = _shared.NON_START_PROOF_SCHEMA
CAPTURED_SOURCE_RECORD_REF_SCHEMA = _shared.CAPTURED_SOURCE_RECORD_REF_SCHEMA
STAGED_ARTIFACT_REF_SCHEMA = _shared.STAGED_ARTIFACT_REF_SCHEMA
RESOURCE_POLICY_SCHEMA = _shared.RESOURCE_POLICY_SCHEMA
CANCEL_RECEIPT_SCHEMA = _shared.CANCEL_RECEIPT_SCHEMA
SOURCE_LIBRARY_C2_3_PAYLOAD_TYPE = ObjectType("ProviderEffectRequest.v1")
SOURCE_LIBRARY_C2_3_OUTCOME_TYPE = ObjectType("ProviderEffectOutcome.v1")


def _profile_ref(
    profile_id: str, profile_version: str, digest: str
) -> ContractProfileRef:
    return ContractProfileRef(
        profile_id=profile_id,
        profile_version=profile_version,
        profile_digest=digest,
    )


def _semantic_profile() -> SemanticProfile:
    payload = {
        "semantic_profile_id": "mrw.successor.source-library.c2-3.semantic.v1",
        "semantic_profile_version": "1.0.0",
        "reads": (
            SOURCE_EXECUTION_REQUEST_SCHEMA_REF,
            CREDENTIAL_REF_SCHEMA,
            PROVIDER_EFFECT_REQUEST_SCHEMA,
            PROVIDER_RECEIPT_SCHEMA,
            AUTHORITATIVE_READBACK_SCHEMA,
        ),
        "creates": (
            PROVIDER_RECEIPT_SCHEMA,
            CAPTURED_SOURCE_RECORD_REF_SCHEMA,
            STAGED_ARTIFACT_REF_SCHEMA,
            AUTHORITATIVE_READBACK_SCHEMA,
            NON_START_PROOF_SCHEMA,
        ),
        "creates_relations": (),
        "declared_loss": (),
        "observation_profile_ref": SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE,
    }
    digest = content_digest(payload)
    return SemanticProfile(**payload, profile_digest=digest)


def _effect_profile() -> EffectProfile:
    payload = {
        "effect_profile_id": "mrw.successor.source-library.c2-3.effect.v1",
        "effect_profile_version": "1.0.0",
        "execution_class": "EFFECTFUL",
        "external_visibility": "INTERNAL_ONLY",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": ("after_attempt_created", "before_terminal_readback"),
        "internal_export_only": True,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "mrw.successor.source-library.c2-3.idempotency.v1",
    }
    digest = content_digest(payload)
    return EffectProfile(**payload, profile_digest=digest)


def _resource_profile() -> ResourceProfile:
    payload = {
        "resource_profile_id": "mrw.successor.source-library.c2-3.resource.v1",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("fixture", "receipt_only"),
        "concurrency_key": "source-library:c2-3",
        "budget_units": "provider-effect-attempt",
        "default_soft_limit_seconds": 60,
        "default_hard_limit_seconds": C2_3_TIMEOUT_SECONDS,
        "node_profile_selector": "fixture-or-receipt-only",
        "budget_ref": C2_3_RESOURCE_POLICY_REF,
        "deadline_policy_ref": "mrw.successor.source-library.c2-3.deadline.v1",
        "node_profile_requirements": ("no_live_provider", "no_credential_bytes"),
        "units": 1,
    }
    digest = content_digest(payload)
    return ResourceProfile(**payload, profile_digest=digest)


def _failure_profile() -> FailureProfile:
    payload = {
        "failure_profile_id": "mrw.successor.source-library.c2-3.failure.v1",
        "failure_profile_version": "1.0.0",
        "typed_failures": tuple(sorted(C2_3_FAILURE_CODES)),
        "retryable": False,
        "degraded_acceptable": True,
        "unknown_outcome_supported": True,
        "readback_or_compensation": "authoritative_readback_or_reconcile",
        "failure_union_ref": "mrw.functorial-successor.failures.c2-3.v1",
        "retryable_failure_kinds": (),
        "readback_profile_ref": "mrw.successor.source-library.c2-3.readback.v1",
        "compensation_profile_ref": "mrw.successor.source-library.c2-3.reconcile.v1",
    }
    digest = content_digest(payload)
    return FailureProfile(**payload, profile_digest=digest)


def _authority_profile() -> AuthorityProfile:
    payload = {
        "authority_profile_id": "mrw.successor.source-library.c2-3.authority.v1",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": SOURCE_LIBRARY_C2_3_OWNER,
        "revalidation_points": ("claim_time", "readback_time"),
        "authority_epoch": 1,
    }
    digest = content_digest(payload)
    return AuthorityProfile(**payload, profile_digest=digest)


def _interpreter_profile() -> InterpreterProfile:
    payload = {
        "interpreter_profile_id": "mrw.successor.source-library.c2-3.interpreter.v1",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": (SOURCE_LIBRARY_C2_3_KIND,),
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": "successor-native.source_library.c2_3.provider_effect",
                "version": "1.0.0",
                "stage": "fixture-or-receipt-only",
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.redacted-fixture.v1",
        "resource_profile_ref": "mrw.successor.source-library.c2-3.resource.v1",
        "credential_requirements_ref": "mrw.successor.source-library.c2-3.credential-ref.v1",
        "cancellation_profile_ref": "attempt_cancel",
        "idempotency_profile_ref": "request_digest",
        "authoritative_readback_profile_ref": "mrw.successor.source-library.c2-3.readback.v1",
        "receipt_codec_ref": PROVIDER_RECEIPT_SCHEMA,
    }
    digest = content_digest(payload)
    return InterpreterProfile(**payload, profile_digest=digest)


def _observation_profile() -> ObservationProfile:
    payload = {
        "observation_profile_id": SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE,
        "observation_profile_version": "1.0.0",
        "dimensions": (
            "project_scope",
            "item_revision",
            "item_incarnation",
            "item_content_digest",
            "catalog_revision",
            "catalog_incarnation",
            "catalog_digest",
            "request_digest",
            "receipt_digest",
            "provider",
            "provider_status",
            "provider_job_id",
            "credential_decision",
            "records",
            "staged_artifacts",
            "readback_provenance",
            "outcome_digest",
        ),
        "compatible_with_legacy": False,
        "observation_schema_ref": "mrw.successor.source-library.c2-3.observation.v1",
    }
    digest = content_digest(payload)
    return ObservationProfile(**payload, profile_digest=digest)


def provider_effect_request_from_plain(
    value: dict[str, Any],
) -> ProviderEffectRequest:
    """Rebuild the exact request from its canonical plain projection."""

    scope_plain = dict(value["project_scope"])
    scope = AuthenticatedProjectScope(
        project_key=scope_plain["project_key"],
        registry_revision=int(scope_plain["registry_revision"]),
        resolved_schema=scope_plain["resolved_schema"],
        incarnation=scope_plain["incarnation"],
        scope_digest=scope_plain["scope_digest"],
    )
    refs = tuple(
        CredentialRef(
            ref=ref["ref"],
            provider=ref["provider"],
            grant_scope=ref["grant_scope"],
            required=bool(ref["required"]),
            schema_version=ref.get("schema_version", CREDENTIAL_REF_SCHEMA),
        )
        for ref in value.get("credential_refs") or []
    )
    policy_plain = dict(value["policy"])
    policy = ProviderResourcePolicy(
        resource_class=policy_plain["resource_class"],
        concurrency_key=policy_plain["concurrency_key"],
        timeout_seconds=int(policy_plain["timeout_seconds"]),
        retry_budget=int(policy_plain["retry_budget"]),
        artifact_byte_ceiling=int(policy_plain["artifact_byte_ceiling"]),
        rate_limit_budget=int(policy_plain["rate_limit_budget"]),
        reservation_lease_seconds=int(policy_plain["reservation_lease_seconds"]),
        schema_version=policy_plain.get("schema_version", RESOURCE_POLICY_SCHEMA),
    )
    return ProviderEffectRequest(
        schema_version=value.get("schema_version", SOURCE_LIBRARY_C2_3_PAYLOAD_SCHEMA),
        operation_kind=value.get("operation_kind", SOURCE_LIBRARY_C2_3_KIND),
        request_id=value["request_id"],
        idempotency_key=value["idempotency_key"],
        project_scope=scope,
        item_key=value["item_key"],
        item_revision=int(value["item_revision"]),
        item_incarnation=value["item_incarnation"],
        item_content_digest=value["item_content_digest"],
        channel_key=value["channel_key"],
        provider=value["provider"],
        provider_config_ref=value["provider_config_ref"],
        effect_payload_codec_ref=value["effect_payload_codec_ref"],
        effect_payload_digest=value["effect_payload_digest"],
        effect_payload=freeze_json_object(value["effect_payload"]),
        credential_refs=refs,
        policy=policy,
        catalog_revision=int(value["catalog_revision"]),
        catalog_incarnation=value["catalog_incarnation"],
        catalog_digest=value["catalog_digest"],
        terminal_output_only=bool(value.get("terminal_output_only", True)),
        request_digest=value.get("request_digest", ""),
    )


def _payload_codec(contract_ref: Any) -> PayloadCodec:
    return PayloadCodec(
        codec_id=SOURCE_LIBRARY_C2_3_PAYLOAD_CODEC_ID,
        codec_version="1.0.0",
        contract_ref=contract_ref,
        payload_type_id=SOURCE_LIBRARY_C2_3_PAYLOAD_TYPE.type_id,
        encode=lambda value: value.to_plain(),
        decode=provider_effect_request_from_plain,
        codec_digest=codec_digest(
            SOURCE_LIBRARY_C2_3_PAYLOAD_CODEC_ID,
            "1.0.0",
            contract_ref,
            SOURCE_LIBRARY_C2_3_PAYLOAD_TYPE.type_id,
        ),
    )


@dataclass(frozen=True, slots=True)
class SourceLibraryC2_3CapabilityBundle:
    bundle_id: str
    operation: OperationContract
    codecs: tuple[PayloadCodec, ...]
    profiles: dict[str, object]

    def payload_codec(self) -> PayloadCodec:
        return self.codecs[0]


def build_source_library_c2_3_bundle() -> SourceLibraryC2_3CapabilityBundle:
    semantic = _semantic_profile()
    effect = _effect_profile()
    resource = _resource_profile()
    failure = _failure_profile()
    authority = _authority_profile()
    interpreter = _interpreter_profile()
    observation = _observation_profile()
    operation = make_operation_contract(
        kind=SOURCE_LIBRARY_C2_3_KIND,
        contract_version="1.0.0",
        input_type=SOURCE_LIBRARY_C2_3_PAYLOAD_TYPE,
        output_type=SOURCE_LIBRARY_C2_3_OUTCOME_TYPE,
        return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
        semantic_profile_ref=_profile_ref(
            semantic.semantic_profile_id,
            semantic.semantic_profile_version,
            semantic.profile_digest,
        ),
        effect_profile_ref=_profile_ref(
            effect.effect_profile_id,
            effect.effect_profile_version,
            effect.profile_digest,
        ),
        resource_profile_ref=_profile_ref(
            resource.resource_profile_id,
            resource.resource_profile_version,
            resource.profile_digest,
        ),
        failure_profile_ref=_profile_ref(
            failure.failure_profile_id,
            failure.failure_profile_version,
            failure.profile_digest,
        ),
        authority_profile_ref=_profile_ref(
            authority.authority_profile_id,
            authority.authority_profile_version,
            authority.profile_digest,
        ),
        interpreter_compatibility_ref=_profile_ref(
            interpreter.interpreter_profile_id,
            interpreter.interpreter_profile_version,
            interpreter.profile_digest,
        ),
        observation_profile_ref=_profile_ref(
            observation.observation_profile_id,
            observation.observation_profile_version,
            observation.profile_digest,
        ),
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=SOURCE_LIBRARY_C2_3_OWNER,
    )
    codec = _payload_codec(operation.ref)
    return SourceLibraryC2_3CapabilityBundle(
        bundle_id="mrw.functorial-successor.source-library.c2-3",
        operation=operation,
        codecs=(codec,),
        profiles={
            "semantic": semantic,
            "effect": effect,
            "resource": resource,
            "failure": failure,
            "authority": authority,
            "interpreter": interpreter,
            "observation": observation,
        },
    )


def build_source_library_c2_3_catalog(
    bundle: SourceLibraryC2_3CapabilityBundle,
) -> OperationContractCatalogSnapshot:
    return OperationContractCatalogSnapshot(
        catalog_id=SOURCE_LIBRARY_C2_3_CATALOG_ID,
        catalog_version=SOURCE_LIBRARY_C2_3_CATALOG_VERSION,
        entries=(
            (
                bundle.operation.ref.kind,
                bundle.operation.ref.contract_version,
                bundle.operation.ref.contract_digest,
                bundle.operation.owner_capability_id,
            ),
        ),
    )


def build_source_library_c2_3_registry(
    bundle: SourceLibraryC2_3CapabilityBundle,
) -> OperationContractRegistry:
    return OperationContractRegistry(
        build_source_library_c2_3_catalog(bundle),
        (bundle.operation,),
    )
