"""Frozen typed contracts and capability bundle for the C2.3 provider-effect atom.

DTOs/contracts live in ``source_library_c2_shared``; this module owns the
operation contract, profiles, codec and catalog/registry assembly and
re-exports the shared vocabulary for capability consumers.  No legacy service
import, network, credential bytes, filesystem, database or provider execution
is performed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal, NoReturn

from app.successor_runtime.capabilities import source_contracts as contracts
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.codecs import PayloadCodec
from app.successor_runtime.capabilities.contracts import OperationContract
from app.successor_runtime.capabilities.profiles import (
    AuthorityProfile,
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
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "SOURCE_PROVIDER_ACQUISITION_DEFAULT_RESOURCE_POLICY",
    "SOURCE_PROVIDER_ACQUISITION_FAILURE_CODES",
    "SOURCE_PROVIDER_ACQUISITION_MAX_ARTIFACT_BYTES",
    "SOURCE_PROVIDER_ACQUISITION_MAX_RETRY_BUDGET",
    "SOURCE_PROVIDER_ACQUISITION_RESOURCE_POLICY_REF",
    "SOURCE_PROVIDER_ACQUISITION_TIMEOUT_SECONDS",
    "CANCELLED_PROVIDER_EFFECT_CODE",
    "SOURCE_PROVIDER_ACQUISITION_CATALOG_ID",
    "SOURCE_PROVIDER_ACQUISITION_CATALOG_VERSION",
    "SOURCE_PROVIDER_ACQUISITION_KIND",
    "SOURCE_PROVIDER_ACQUISITION_OPERATION_ID",
    "SOURCE_PROVIDER_ACQUISITION_OWNER",
    "SOURCE_PROVIDER_ACQUISITION_PAYLOAD_CODEC_ID",
    "SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_CODEC_ID",
    "SOURCE_PROVIDER_ACQUISITION_PAYLOAD_SCHEMA",
    "SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_SCHEMA",
    "SOURCE_PROVIDER_ACQUISITION_SEMANTIC_IDENTITY",
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
    "build_source_provider_acquisition_bundle",
    "build_source_provider_acquisition_catalog",
    "build_source_provider_acquisition_registry",
    "provider_effect_outcomes_equal",
    "provider_effect_request_from_plain",
    "provider_receipt_digest",
    "provider_effect_request_from_historical_plain",
    "provider_receipt_from_plain",
    "provider_receipt_from_historical_plain",
]

_SHARED_EXPORTS = (
    "AcceptedProviderEffect",
    "AuthoritativeProviderReadback",
    "SOURCE_PROVIDER_ACQUISITION_DEFAULT_RESOURCE_POLICY",
    "SOURCE_PROVIDER_ACQUISITION_FAILURE_CODES",
    "SOURCE_PROVIDER_ACQUISITION_MAX_ARTIFACT_BYTES",
    "SOURCE_PROVIDER_ACQUISITION_MAX_RETRY_BUDGET",
    "SOURCE_PROVIDER_ACQUISITION_RESOURCE_POLICY_REF",
    "SOURCE_PROVIDER_ACQUISITION_TIMEOUT_SECONDS",
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
    "SOURCE_PROVIDER_ACQUISITION_CATALOG_ID",
    "SOURCE_PROVIDER_ACQUISITION_CATALOG_VERSION",
    "SOURCE_PROVIDER_ACQUISITION_KIND",
    "SOURCE_PROVIDER_ACQUISITION_OPERATION_ID",
    "SOURCE_PROVIDER_ACQUISITION_OWNER",
    "SOURCE_PROVIDER_ACQUISITION_PAYLOAD_CODEC_ID",
    "SOURCE_PROVIDER_ACQUISITION_PAYLOAD_SCHEMA",
    "SOURCE_PROVIDER_ACQUISITION_SEMANTIC_IDENTITY",
    "SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE",
    "StagedArtifactRef",
    "provider_effect_outcomes_equal",
    "provider_receipt_digest",
)

AcceptedProviderEffect = contracts.AcceptedProviderEffect
AuthoritativeProviderReadback = contracts.AuthoritativeProviderReadback
SOURCE_PROVIDER_ACQUISITION_DEFAULT_RESOURCE_POLICY = contracts.SOURCE_PROVIDER_ACQUISITION_DEFAULT_RESOURCE_POLICY
SOURCE_PROVIDER_ACQUISITION_FAILURE_CODES = contracts.SOURCE_PROVIDER_ACQUISITION_FAILURE_CODES
SOURCE_PROVIDER_ACQUISITION_MAX_ARTIFACT_BYTES = contracts.SOURCE_PROVIDER_ACQUISITION_MAX_ARTIFACT_BYTES
SOURCE_PROVIDER_ACQUISITION_MAX_RETRY_BUDGET = contracts.SOURCE_PROVIDER_ACQUISITION_MAX_RETRY_BUDGET
SOURCE_PROVIDER_ACQUISITION_RESOURCE_POLICY_REF = contracts.SOURCE_PROVIDER_ACQUISITION_RESOURCE_POLICY_REF
SOURCE_PROVIDER_ACQUISITION_TIMEOUT_SECONDS = contracts.SOURCE_PROVIDER_ACQUISITION_TIMEOUT_SECONDS
CANCELLED_PROVIDER_EFFECT_CODE = contracts.CANCELLED_PROVIDER_EFFECT_CODE
CancelReceipt = contracts.CancelReceipt
CancelledProviderEffect = contracts.CancelledProviderEffect
CapturedSourceRecordRef = contracts.CapturedSourceRecordRef
CompletedProviderEffect = contracts.CompletedProviderEffect
CredentialDecisionReceipt = contracts.CredentialDecisionReceipt
CredentialRef = contracts.CredentialRef
FailedProviderEffect = contracts.FailedProviderEffect
NonStartProof = contracts.NonStartProof
NonStartUnprovable = contracts.NonStartUnprovable
OrderedProviderFailure = contracts.OrderedProviderFailure
OutcomeUnknownProviderEffect = contracts.OutcomeUnknownProviderEffect
PartiallyCompletedProviderEffect = contracts.PartiallyCompletedProviderEffect
ProviderAttemptRef = contracts.ProviderAttemptRef
ProviderEffectOutcome = contracts.ProviderEffectOutcome
ProviderEffectRequest = contracts.ProviderEffectRequest
ProviderReadbackResult = contracts.ProviderReadbackResult
ProviderReceipt = contracts.ProviderReceipt
ProviderResourcePolicy = contracts.ProviderResourcePolicy
ReadbackTerminal = contracts.ReadbackTerminal
ReadbackUnavailable = contracts.ReadbackUnavailable
ReadbackWaiting = contracts.ReadbackWaiting
ReconciledProviderEffect = contracts.ReconciledProviderEffect
RejectedProviderEffect = contracts.RejectedProviderEffect
SOURCE_PROVIDER_ACQUISITION_CATALOG_ID = contracts.SOURCE_PROVIDER_ACQUISITION_CATALOG_ID
SOURCE_PROVIDER_ACQUISITION_CATALOG_VERSION = contracts.SOURCE_PROVIDER_ACQUISITION_CATALOG_VERSION
SOURCE_PROVIDER_ACQUISITION_KIND = contracts.SOURCE_PROVIDER_ACQUISITION_KIND
SOURCE_PROVIDER_ACQUISITION_OPERATION_ID = contracts.SOURCE_PROVIDER_ACQUISITION_OPERATION_ID
SOURCE_PROVIDER_ACQUISITION_OWNER = contracts.SOURCE_PROVIDER_ACQUISITION_OWNER
SOURCE_PROVIDER_ACQUISITION_PAYLOAD_CODEC_ID = contracts.SOURCE_PROVIDER_ACQUISITION_PAYLOAD_CODEC_ID
SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_CODEC_ID = (
    contracts.SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_CODEC_ID
)
SOURCE_PROVIDER_ACQUISITION_PAYLOAD_SCHEMA = contracts.SOURCE_PROVIDER_ACQUISITION_PAYLOAD_SCHEMA
SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_SCHEMA = contracts.SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_SCHEMA
SOURCE_PROVIDER_ACQUISITION_SEMANTIC_IDENTITY = contracts.SOURCE_PROVIDER_ACQUISITION_SEMANTIC_IDENTITY
SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE = contracts.SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE
StagedArtifactRef = contracts.StagedArtifactRef
provider_effect_outcomes_equal = contracts.provider_effect_outcomes_equal
provider_receipt_digest = contracts.provider_receipt_digest

# Schema refs and type constants needed by the profile/operation assembly.
AUTHENTICATED_PROJECT_SCOPE_TYPE = contracts.AUTHENTICATED_PROJECT_SCOPE_TYPE
AuthenticatedProjectScope = contracts.AuthenticatedProjectScope
CHANNEL_CATALOG_SNAPSHOT_TYPE = contracts.CHANNEL_CATALOG_SNAPSHOT_TYPE
SOURCE_EXECUTION_REQUEST_SCHEMA_REF = contracts.SOURCE_EXECUTION_REQUEST_SCHEMA_REF
CREDENTIAL_REF_SCHEMA = contracts.CREDENTIAL_REF_SCHEMA
PROVIDER_EFFECT_REQUEST_SCHEMA = contracts.PROVIDER_EFFECT_REQUEST_SCHEMA
PROVIDER_RECEIPT_SCHEMA = contracts.PROVIDER_RECEIPT_SCHEMA
AUTHORITATIVE_READBACK_SCHEMA = contracts.AUTHORITATIVE_READBACK_SCHEMA
NON_START_PROOF_SCHEMA = contracts.NON_START_PROOF_SCHEMA
CAPTURED_SOURCE_RECORD_REF_SCHEMA = contracts.CAPTURED_SOURCE_RECORD_REF_SCHEMA
STAGED_ARTIFACT_REF_SCHEMA = contracts.STAGED_ARTIFACT_REF_SCHEMA
RESOURCE_POLICY_SCHEMA = contracts.RESOURCE_POLICY_SCHEMA
CANCEL_RECEIPT_SCHEMA = contracts.CANCEL_RECEIPT_SCHEMA
SOURCE_PROVIDER_ACQUISITION_PAYLOAD_TYPE = ObjectType("ProviderEffectRequest.v1")
SOURCE_PROVIDER_ACQUISITION_OUTCOME_TYPE = ObjectType("ProviderEffectOutcome.v1")


def _semantic_profile() -> SemanticProfile:
    payload = {
        "semantic_profile_id": "mrw.source.provider-acquisition.semantic.v2",
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
        "effect_profile_id": "mrw.source.provider-acquisition.effect.v2",
        "effect_profile_version": "1.0.0",
        "execution_class": "EFFECTFUL",
        "external_visibility": "INTERNAL_ONLY",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": ("after_attempt_created", "before_terminal_readback"),
        "internal_export_only": True,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "mrw.source.provider-acquisition.idempotency.v2",
    }
    digest = content_digest(payload)
    return EffectProfile(**payload, profile_digest=digest)


def _resource_profile() -> ResourceProfile:
    payload = {
        "resource_profile_id": "mrw.source.provider-acquisition.resource.v2",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("fixture", "receipt_only"),
        "concurrency_key": "source.provider-acquisition",
        "budget_units": "provider-effect-attempt",
        "default_soft_limit_seconds": 60,
        "default_hard_limit_seconds": SOURCE_PROVIDER_ACQUISITION_TIMEOUT_SECONDS,
        "node_profile_selector": "fixture-or-receipt-only",
        "budget_ref": SOURCE_PROVIDER_ACQUISITION_RESOURCE_POLICY_REF,
        "deadline_policy_ref": "mrw.source.provider-acquisition.deadline.v2",
        "node_profile_requirements": ("no_live_provider", "no_credential_bytes"),
        "units": 1,
    }
    digest = content_digest(payload)
    return ResourceProfile(**payload, profile_digest=digest)


def _failure_profile() -> FailureProfile:
    payload = {
        "failure_profile_id": "mrw.source.provider-acquisition.failure.v2",
        "failure_profile_version": "1.0.0",
        "typed_failures": tuple(sorted(SOURCE_PROVIDER_ACQUISITION_FAILURE_CODES)),
        "retryable": False,
        "degraded_acceptable": True,
        "unknown_outcome_supported": True,
        "readback_or_compensation": "authoritative_readback_or_reconcile",
        "failure_union_ref": "mrw.source.provider-acquisition.failures.v2",
        "retryable_failure_kinds": (),
        "readback_profile_ref": "mrw.source.provider-acquisition.readback.v2",
        "compensation_profile_ref": "mrw.source.provider-acquisition.reconcile.v2",
    }
    digest = content_digest(payload)
    return FailureProfile(**payload, profile_digest=digest)


def _authority_profile() -> AuthorityProfile:
    payload = {
        "authority_profile_id": "mrw.source.provider-acquisition.authority.v2",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": SOURCE_PROVIDER_ACQUISITION_OWNER,
        "revalidation_points": ("claim_time", "readback_time"),
        "authority_epoch": 1,
    }
    digest = content_digest(payload)
    return AuthorityProfile(**payload, profile_digest=digest)


def _interpreter_profile() -> InterpreterProfile:
    payload = {
        "interpreter_profile_id": "mrw.source.provider-acquisition.native.v2",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": (SOURCE_PROVIDER_ACQUISITION_KIND,),
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": "mrw.source.provider-acquisition.native",
                "version": "2.0.0",
                "stage": "fixture-or-receipt-only",
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.redacted-fixture.v1",
        "resource_profile_ref": "mrw.source.provider-acquisition.resource.v2",
        "credential_requirements_ref": contracts.CREDENTIAL_REF_SCHEMA,
        "cancellation_profile_ref": "attempt_cancel",
        "idempotency_profile_ref": "request_digest",
        "authoritative_readback_profile_ref": "mrw.source.provider-acquisition.readback.v2",
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
        "observation_schema_ref": contracts.SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE,
    }
    digest = content_digest(payload)
    return ObservationProfile(**payload, profile_digest=digest)


def _reject_provider_codec(message: str, *, site: str) -> NoReturn:
    """Lift a typed codec failure through the retained decoder ABI."""

    contracts.raise_source_contract_failure(
        contracts.source_contract_failure(
            "schema_contract_invalid",
            message,
            operation="source.provider_acquisition.codec",
            site=site,
            owner=SOURCE_PROVIDER_ACQUISITION_OWNER,
            public_exception="ValueError",
        ),
        ValueError,
    )


def provider_effect_request_from_plain(
    value: dict[str, Any],
    *,
    _default_schema: str = SOURCE_PROVIDER_ACQUISITION_PAYLOAD_SCHEMA,
    _allow_historical: bool = False,
) -> ProviderEffectRequest:
    """Rebuild the exact request from its canonical plain projection."""

    schema_version = value.get("schema_version", _default_schema)
    if schema_version == SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_SCHEMA and not _allow_historical:
        _reject_provider_codec(
            "historical provider acquisition payload requires the historical decoder",
            site="provider_effect_request_from_plain",
        )

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
        schema_version=schema_version,
        operation_kind=value.get("operation_kind", SOURCE_PROVIDER_ACQUISITION_KIND),
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


def provider_effect_request_from_historical_plain(
    value: dict[str, Any],
) -> ProviderEffectRequest:
    """Read exact historical provider-effect bytes without rehashing."""

    if value.get("schema_version") != SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_SCHEMA:
        _reject_provider_codec(
            "historical provider acquisition decoder requires the exact C2 schema",
            site="provider_effect_request_from_historical_plain",
        )
    return provider_effect_request_from_plain(
        value,
        _default_schema=SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_SCHEMA,
        _allow_historical=True,
    )


def provider_receipt_from_plain(
    value: dict[str, Any],
    *,
    _allow_historical: bool = False,
) -> ProviderReceipt:
    """Decode a current receipt and reject historical bytes by default."""

    schema_version = value.get("schema_version", PROVIDER_RECEIPT_SCHEMA)
    if schema_version == contracts.PROVIDER_RECEIPT_HISTORICAL_SCHEMA:
        if not _allow_historical:
            _reject_provider_codec(
                "historical provider receipt requires the historical decoder",
                site="provider_receipt_from_plain",
            )
    elif schema_version != PROVIDER_RECEIPT_SCHEMA:
        _reject_provider_codec(
            f"unsupported provider receipt schema {schema_version!r}",
            site="provider_receipt_from_plain",
        )
    return ProviderReceipt(
        receipt_id=value["receipt_id"],
        provider=value["provider"],
        provider_job_id=value.get("provider_job_id"),
        provider_status=value["provider_status"],
        attempt_ref=value["attempt_ref"],
        observed_at=value["observed_at"],
        provider_job_uri=value.get("provider_job_uri"),
        schema_version=schema_version,
        receipt_digest=value.get("receipt_digest", ""),
    )


def provider_receipt_from_historical_plain(
    value: dict[str, Any],
) -> ProviderReceipt:
    """Read exact historical receipt bytes without rehashing or upgrading."""

    if value.get("schema_version") != contracts.PROVIDER_RECEIPT_HISTORICAL_SCHEMA:
        _reject_provider_codec(
            "historical provider receipt decoder requires the exact C2 schema",
            site="provider_receipt_from_historical_plain",
        )
    return provider_receipt_from_plain(value, _allow_historical=True)


def _contract_declaration(
    profiles: dict[str, object],
) -> contracts.SourceSingleOperationContractDeclaration:
    return contracts.SourceSingleOperationContractDeclaration(
        kind=SOURCE_PROVIDER_ACQUISITION_KIND,
        owner_capability_id=SOURCE_PROVIDER_ACQUISITION_OWNER,
        input_type=SOURCE_PROVIDER_ACQUISITION_PAYLOAD_TYPE,
        output_type=SOURCE_PROVIDER_ACQUISITION_OUTCOME_TYPE,
        codec=contracts.SourcePayloadCodecDeclaration(
            codec_id=SOURCE_PROVIDER_ACQUISITION_PAYLOAD_CODEC_ID,
            codec_version="1.0.0",
            payload_type_id=SOURCE_PROVIDER_ACQUISITION_PAYLOAD_TYPE.type_id,
            encode=lambda value: value.to_plain(),
            decode=provider_effect_request_from_plain,
        ),
        profiles=profiles,
    )


@dataclass(frozen=True, slots=True)
class SourceProviderAcquisitionCapabilityBundle:
    bundle_id: str
    operation: OperationContract
    codecs: tuple[PayloadCodec, ...]
    profiles: dict[str, object]

    def payload_codec(self) -> PayloadCodec:
        return self.codecs[0]


def build_source_provider_acquisition_bundle() -> Annotated[
    SourceProviderAcquisitionCapabilityBundle,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=C2.3_contract_constants witness=test:test_w06_successor_authority_metadata"
    ],
]:
    profiles = {
        "semantic": _semantic_profile(),
        "effect": _effect_profile(),
        "resource": _resource_profile(),
        "failure": _failure_profile(),
        "authority": _authority_profile(),
        "interpreter": _interpreter_profile(),
        "observation": _observation_profile(),
    }
    parts = contracts.build_source_operation_parts(_contract_declaration(profiles))
    return SourceProviderAcquisitionCapabilityBundle(
        bundle_id="mrw.source.provider-acquisition.bundle.v2",
        operation=parts.operation,
        codecs=parts.codecs,
        profiles=parts.profiles,
    )


def build_source_provider_acquisition_catalog(
    bundle: SourceProviderAcquisitionCapabilityBundle,
) -> Annotated[
    OperationContractCatalogSnapshot,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=C2.3_operation_bundle witness=test:test_w06_successor_authority_metadata"
    ],
]:
    return contracts.build_source_operation_catalog(
        contracts.SourceSingleOperationParts(
            operation=bundle.operation,
            codecs=bundle.codecs,
            profiles=bundle.profiles,
        ),
        catalog_id=SOURCE_PROVIDER_ACQUISITION_CATALOG_ID,
        catalog_version=SOURCE_PROVIDER_ACQUISITION_CATALOG_VERSION,
    )


def build_source_provider_acquisition_registry(
    bundle: SourceProviderAcquisitionCapabilityBundle,
) -> Annotated[
    OperationContractRegistry,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=C2.3_operation_bundle witness=test:test_w06_successor_authority_metadata"
    ],
]:
    return contracts.build_source_operation_registry(
        build_source_provider_acquisition_catalog(bundle),
        bundle.operation,
    )
