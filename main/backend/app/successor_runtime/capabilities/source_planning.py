"""Frozen typed contracts and capability bundle for the four C2.2 planners.

DTOs/contracts live in ``source_library_c2_shared``; this module owns the four
operation contracts, profiles, codecs and catalog/registry assembly and
re-exports the shared planning/collection vocabulary.  C2.2 never executes
effects; provider dispatch is delegated to C2.3 ports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from functorial_kit import Failure

from app.successor_runtime.capabilities import source_contracts as contracts
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
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    make_operation_contract,
)

__all__ = [
    "SOURCE_PLANNING_BATCH_SIZE",
    "SOURCE_PLANNING_MAX_QUERY_TERMS",
    "SOURCE_PLANNING_MAX_TASKS",
    "SOURCE_PLANNING_MAX_URLS",
    "SOURCE_PLANNING_FAILURE_CODES",
    "SOURCE_PLANNING_RESOURCE_CEILING_REF",
    "SOURCE_PLANNING_CATALOG_ID",
    "SOURCE_PLANNING_CATALOG_VERSION",
    "SOURCE_PLANNING_CODEC_IDS",
    "SOURCE_PLANNING_HISTORICAL_CODEC_IDS",
    "SOURCE_PLANNING_OWNERS",
    "SOURCE_PLANNING_PROTOCOL_SEARCH_OWNER",
    "SOURCE_PLANNING_PROVIDER_HARVEST_OWNER",
    "SOURCE_PLANNING_SITE_SEARCH_OWNER",
    "SOURCE_PLANNING_URL_EXECUTION_OWNER",
    "SOURCE_PLANNING_PROTOCOL_SEARCH_KIND",
    "SOURCE_PLANNING_PROVIDER_HARVEST_KIND",
    "SOURCE_PLANNING_SITE_SEARCH_KIND",
    "SOURCE_PLANNING_URL_EXECUTION_KIND",
    "SOURCE_MODE_PLANNING_OBSERVATION_PROFILE",
    "SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA",
    "CollectionCancelled",
    "CollectionCompleted",
    "CollectionFailed",
    "CollectionOutcomeUnknown",
    "CollectionPartiallyCompleted",
    "CollectionProviderAccepted",
    "CollectionRejected",
    "FallbackRule",
    "OrderedFailure",
    "OrderedFoldPolicy",
    "PlannedPlanning",
    "ProviderHandoff",
    "RejectedPlanning",
    "SourceCollectionOutcome",
    "SourceCollectionTerminal",
    "SourceModePlan",
    "SourceModePlanningPayload",
    "SourceModePlanningResult",
    "SourceModeTask",
    "SourceTaskOutcome",
    "TerminalConstructionProfile",
    "build_source_planning_bundle",
    "build_source_planning_catalog",
    "build_source_planning_registry",
    "source_collection_outcomes_equal",
    "source_mode_plan_digest",
]

_SHARED_EXPORTS = (
    "SOURCE_PLANNING_BATCH_SIZE",
    "SOURCE_PLANNING_MAX_QUERY_TERMS",
    "SOURCE_PLANNING_MAX_TASKS",
    "SOURCE_PLANNING_MAX_URLS",
    "SOURCE_PLANNING_FAILURE_CODES",
    "SOURCE_PLANNING_RESOURCE_CEILING_REF",
    "SOURCE_PLANNING_CATALOG_ID",
    "SOURCE_PLANNING_CATALOG_VERSION",
    "SOURCE_PLANNING_CODEC_IDS",
    "SOURCE_PLANNING_HISTORICAL_CODEC_IDS",
    "SOURCE_PLANNING_OWNERS",
    "SOURCE_PLANNING_PROTOCOL_SEARCH_KIND",
    "SOURCE_PLANNING_PROVIDER_HARVEST_KIND",
    "SOURCE_PLANNING_SITE_SEARCH_KIND",
    "SOURCE_PLANNING_URL_EXECUTION_KIND",
    "SOURCE_MODE_PLANNING_OBSERVATION_PROFILE",
    "SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA",
    "CollectionCancelled",
    "CollectionCompleted",
    "CollectionFailed",
    "CollectionOutcomeUnknown",
    "CollectionPartiallyCompleted",
    "CollectionProviderAccepted",
    "CollectionRejected",
    "FallbackRule",
    "OrderedFailure",
    "OrderedFoldPolicy",
    "PlannedPlanning",
    "ProviderHandoff",
    "RejectedPlanning",
    "SourceCollectionOutcome",
    "SourceCollectionTerminal",
    "SourceModePlan",
    "SourceModePlanningPayload",
    "SourceModePlanningResult",
    "SourceModeTask",
    "SourceTaskOutcome",
    "TerminalConstructionProfile",
    "source_collection_outcomes_equal",
    "source_mode_plan_digest",
)

SOURCE_PLANNING_BATCH_SIZE = contracts.SOURCE_PLANNING_BATCH_SIZE
SOURCE_PLANNING_MAX_QUERY_TERMS = contracts.SOURCE_PLANNING_MAX_QUERY_TERMS
SOURCE_PLANNING_MAX_TASKS = contracts.SOURCE_PLANNING_MAX_TASKS
SOURCE_PLANNING_MAX_URLS = contracts.SOURCE_PLANNING_MAX_URLS
SOURCE_PLANNING_FAILURE_CODES = contracts.SOURCE_PLANNING_FAILURE_CODES
SOURCE_PLANNING_RESOURCE_CEILING_REF = contracts.SOURCE_PLANNING_RESOURCE_CEILING_REF
SOURCE_PLANNING_CATALOG_ID = contracts.SOURCE_PLANNING_CATALOG_ID
SOURCE_PLANNING_CATALOG_VERSION = contracts.SOURCE_PLANNING_CATALOG_VERSION
SOURCE_PLANNING_OWNERS = contracts.SOURCE_PLANNING_OWNERS
SOURCE_PLANNING_CODEC_IDS = contracts.SOURCE_PLANNING_CODEC_IDS
SOURCE_PLANNING_HISTORICAL_CODEC_IDS = contracts.SOURCE_PLANNING_HISTORICAL_CODEC_IDS
SOURCE_PLANNING_PROTOCOL_SEARCH_OWNER = contracts.SOURCE_PLANNING_PROTOCOL_SEARCH_OWNER
SOURCE_PLANNING_PROVIDER_HARVEST_OWNER = contracts.SOURCE_PLANNING_PROVIDER_HARVEST_OWNER
SOURCE_PLANNING_SITE_SEARCH_OWNER = contracts.SOURCE_PLANNING_SITE_SEARCH_OWNER
SOURCE_PLANNING_URL_EXECUTION_OWNER = contracts.SOURCE_PLANNING_URL_EXECUTION_OWNER
SOURCE_PLANNING_PROTOCOL_SEARCH_KIND = contracts.SOURCE_PLANNING_PROTOCOL_SEARCH_KIND
SOURCE_PLANNING_PROVIDER_HARVEST_KIND = contracts.SOURCE_PLANNING_PROVIDER_HARVEST_KIND
SOURCE_PLANNING_SITE_SEARCH_KIND = contracts.SOURCE_PLANNING_SITE_SEARCH_KIND
SOURCE_PLANNING_URL_EXECUTION_KIND = contracts.SOURCE_PLANNING_URL_EXECUTION_KIND
SOURCE_MODE_PLANNING_OBSERVATION_PROFILE = contracts.SOURCE_MODE_PLANNING_OBSERVATION_PROFILE
SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA = contracts.SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA
CollectionCancelled = contracts.CollectionCancelled
CollectionCompleted = contracts.CollectionCompleted
CollectionFailed = contracts.CollectionFailed
CollectionOutcomeUnknown = contracts.CollectionOutcomeUnknown
CollectionPartiallyCompleted = contracts.CollectionPartiallyCompleted
CollectionProviderAccepted = contracts.CollectionProviderAccepted
CollectionRejected = contracts.CollectionRejected
FallbackRule = contracts.FallbackRule
OrderedFailure = contracts.OrderedFailure
OrderedFoldPolicy = contracts.OrderedFoldPolicy
PlannedPlanning = contracts.PlannedPlanning
ProviderHandoff = contracts.ProviderHandoff
RejectedPlanning = contracts.RejectedPlanning
SourceCollectionOutcome = contracts.SourceCollectionOutcome
SourceCollectionTerminal = contracts.SourceCollectionTerminal
SourceModePlan = contracts.SourceModePlan
SourceModePlanningPayload = contracts.SourceModePlanningPayload
SourceModePlanningResult = contracts.SourceModePlanningResult
SourceModeTask = contracts.SourceModeTask
SourceTaskOutcome = contracts.SourceTaskOutcome
TerminalConstructionProfile = contracts.TerminalConstructionProfile
source_collection_outcomes_equal = contracts.source_collection_outcomes_equal
source_mode_plan_digest = contracts.source_mode_plan_digest

SOURCE_EXECUTION_REQUEST_SCHEMA_REF = contracts.SOURCE_EXECUTION_REQUEST_SCHEMA_REF
SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA = contracts.SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA
SOURCE_MODE_PLAN_SCHEMA = contracts.SOURCE_MODE_PLAN_SCHEMA
SOURCE_MODE_TASK_SCHEMA = contracts.SOURCE_MODE_TASK_SCHEMA
COLLECTION_TERMINAL_SCHEMA = contracts.COLLECTION_TERMINAL_SCHEMA
PROVIDER_HANDOFF_SCHEMA = contracts.PROVIDER_HANDOFF_SCHEMA
SOURCE_PLANNING_KINDS = contracts.SOURCE_PLANNING_KINDS
SOURCE_MODE_PLANNING_PAYLOAD_TYPE = contracts.SOURCE_MODE_PLANNING_PAYLOAD_TYPE
SOURCE_MODE_PLANNING_RESULT_TYPE = contracts.SOURCE_MODE_PLANNING_RESULT_TYPE


def _profile_ref(profile_id: str, profile_version: str, digest: str) -> ContractProfileRef:
    return ContractProfileRef(
        profile_id=profile_id,
        profile_version=profile_version,
        profile_digest=digest,
    )


def _semantic_profile() -> SemanticProfile:
    payload = {
        "semantic_profile_id": "mrw.source.plan-source-mode.semantic.v2",
        "semantic_profile_version": "1.0.0",
        "reads": (
            SOURCE_EXECUTION_REQUEST_SCHEMA_REF,
            SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA,
        ),
        "creates": (SOURCE_MODE_PLAN_SCHEMA,),
        "creates_relations": (),
        "declared_loss": (),
        "observation_profile_ref": SOURCE_MODE_PLANNING_OBSERVATION_PROFILE,
    }
    digest = content_digest(payload, omit_fields=("profile_digest",))
    return SemanticProfile(**payload, profile_digest=digest)


def _effect_profile() -> EffectProfile:
    payload = {
        "effect_profile_id": "mrw.source.plan-source-mode.effect.v2",
        "effect_profile_version": "1.0.0",
        "execution_class": "PURE_TRANSFORM",
        "external_visibility": "NONE",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": (),
        "internal_export_only": True,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "mrw.source.plan-source-mode.idempotency.v2",
    }
    digest = content_digest(payload, omit_fields=("profile_digest",))
    return EffectProfile(**payload, profile_digest=digest)


def _resource_profile() -> ResourceProfile:
    payload = {
        "resource_profile_id": "mrw.source.plan-source-mode.resource.v2",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("cpu_light",),
        "concurrency_key": "source.plan-source-mode",
        "budget_units": "source-mode-plan",
        "default_soft_limit_seconds": 5,
        "default_hard_limit_seconds": 30,
        "node_profile_selector": "pure-planning",
        "budget_ref": SOURCE_PLANNING_RESOURCE_CEILING_REF,
        "deadline_policy_ref": "mrw.source.plan-source-mode.deadline.v2",
        "node_profile_requirements": ("no_effect", "no_network", "no_credential"),
        "units": 1,
    }
    digest = content_digest(payload, omit_fields=("profile_digest",))
    return ResourceProfile(**payload, profile_digest=digest)


def _failure_profile() -> FailureProfile:
    payload = {
        "failure_profile_id": "mrw.source.plan-source-mode.failure.v2",
        "failure_profile_version": "1.0.0",
        "typed_failures": tuple(sorted(SOURCE_PLANNING_FAILURE_CODES)),
        "retryable": False,
        "degraded_acceptable": True,
        "unknown_outcome_supported": False,
        "readback_or_compensation": "replan_or_reject",
        "failure_union_ref": "mrw.source.plan-source-mode.failures.v2",
        "retryable_failure_kinds": (),
        "readback_profile_ref": None,
        "compensation_profile_ref": None,
    }
    digest = content_digest(payload, omit_fields=("profile_digest",))
    return FailureProfile(**payload, profile_digest=digest)


def _authority_profile(owner: str) -> AuthorityProfile:
    payload = {
        "authority_profile_id": f"{owner}.authority",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": owner,
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    digest = content_digest(payload, omit_fields=("profile_digest",))
    return AuthorityProfile(**payload, profile_digest=digest)


def _interpreter_profile() -> InterpreterProfile:
    payload = {
        "interpreter_profile_id": "mrw.source.plan-source-mode.native.v2",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": SOURCE_PLANNING_KINDS,
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": "mrw.source.plan-source-mode.native",
                "version": "2.0.0",
                "boundary": "pure planning only",
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.pure.v1",
        "resource_profile_ref": "mrw.source.plan-source-mode.resource.v2",
        "credential_requirements_ref": None,
        "cancellation_profile_ref": "step_boundary",
        "idempotency_profile_ref": "execution_request_digest",
        "authoritative_readback_profile_ref": None,
        "receipt_codec_ref": SOURCE_MODE_PLANNING_OBSERVATION_PROFILE,
    }
    digest = content_digest(payload, omit_fields=("profile_digest",))
    return InterpreterProfile(**payload, profile_digest=digest)


def _observation_profile() -> ObservationProfile:
    payload = {
        "observation_profile_id": SOURCE_MODE_PLANNING_OBSERVATION_PROFILE,
        "observation_profile_version": "1.0.0",
        "dimensions": (
            "mode",
            "strategy",
            "ordered_task_ids",
            "route",
            "fallback",
            "catalog_identity",
            "execution_request_digest",
            "plan_digest",
        ),
        "compatible_with_legacy": False,
        "observation_schema_ref": SOURCE_MODE_PLANNING_OBSERVATION_PROFILE,
    }
    digest = content_digest(payload, omit_fields=("profile_digest",))
    return ObservationProfile(**payload, profile_digest=digest)


def _payload_codec(
    contract_ref: Any,
    *,
    codec_id: str,
) -> PayloadCodec:
    return PayloadCodec(
        codec_id=codec_id,
        codec_version="1.0.0",
        contract_ref=contract_ref,
        payload_type_id=SOURCE_MODE_PLANNING_PAYLOAD_TYPE.type_id,
        encode=lambda value: value.to_plain(),
        decode=contracts.source_mode_planning_payload_from_plain,
        codec_digest=codec_digest(
            codec_id,
            "1.0.0",
            contract_ref,
            SOURCE_MODE_PLANNING_PAYLOAD_TYPE.type_id,
        ),
    )


@dataclass(frozen=True, slots=True)
class SourcePlanningCapabilityBundle:
    bundle_id: str
    operations: tuple[OperationContract, ...]
    codecs: tuple[PayloadCodec, ...]
    profiles: dict[str, object]

    def payload_codec(self, kind: str) -> PayloadCodec:
        result = self.try_payload_codec(kind)
        if isinstance(result, Failure):
            _raise_payload_codec_compatibility(result)
        return result

    def try_payload_codec(self, kind: str) -> PayloadCodec | Failure:
        for codec in self.codecs:
            if codec.codec_id == SOURCE_PLANNING_CODEC_IDS.get(kind):
                return codec
        return contracts.source_contract_failure(
            "catalog_contract_invalid",
            f"no source planning payload codec for {kind}",
            operation="source.plan_source_mode.payload_codec",
            site="payload_codec",
            owner=SOURCE_PLANNING_OWNERS.get(kind, "source.plan_source_mode.v2"),
        )


def _raise_payload_codec_compatibility(failure: Failure) -> None:
    """Lift the retained ``payload_codec`` KeyError ABI at one boundary."""

    # kit:boundary owner=source.plan_source_mode.v2 class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source.contract.failure witness=test:test_w06_c2_total_core_failure_lifts
    raise KeyError(failure.message)


def build_source_planning_bundle() -> Annotated[
    SourcePlanningCapabilityBundle,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=C2.2_contract_constants witness=test:test_w06_successor_authority_metadata"
    ],
]:
    semantic = _semantic_profile()
    effect = _effect_profile()
    resource = _resource_profile()
    failure = _failure_profile()
    interpreter = _interpreter_profile()
    observation = _observation_profile()
    common_refs = {
        "semantic": _profile_ref(
            semantic.semantic_profile_id,
            semantic.semantic_profile_version,
            semantic.profile_digest,
        ),
        "effect": _profile_ref(
            effect.effect_profile_id,
            effect.effect_profile_version,
            effect.profile_digest,
        ),
        "resource": _profile_ref(
            resource.resource_profile_id,
            resource.resource_profile_version,
            resource.profile_digest,
        ),
        "failure": _profile_ref(
            failure.failure_profile_id,
            failure.failure_profile_version,
            failure.profile_digest,
        ),
        "interpreter": _profile_ref(
            interpreter.interpreter_profile_id,
            interpreter.interpreter_profile_version,
            interpreter.profile_digest,
        ),
        "observation": _profile_ref(
            observation.observation_profile_id,
            observation.observation_profile_version,
            observation.profile_digest,
        ),
    }
    operations: list[OperationContract] = []
    codecs: list[PayloadCodec] = []
    for kind in SOURCE_PLANNING_KINDS:
        authority = _authority_profile(SOURCE_PLANNING_OWNERS[kind])
        authority_ref = _profile_ref(
            authority.authority_profile_id,
            authority.authority_profile_version,
            authority.profile_digest,
        )
        operation = make_operation_contract(
            kind=kind,
            contract_version="1.0.0",
            input_type=SOURCE_MODE_PLANNING_PAYLOAD_TYPE,
            output_type=SOURCE_MODE_PLANNING_RESULT_TYPE,
            return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
            semantic_profile_ref=common_refs["semantic"],
            effect_profile_ref=common_refs["effect"],
            resource_profile_ref=common_refs["resource"],
            failure_profile_ref=common_refs["failure"],
            authority_profile_ref=authority_ref,
            interpreter_compatibility_ref=common_refs["interpreter"],
            observation_profile_ref=common_refs["observation"],
            allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
            owner_capability_id=SOURCE_PLANNING_OWNERS[kind],
        )
        operations.append(operation)
        codecs.append(
            _payload_codec(
                operation.ref,
                codec_id=SOURCE_PLANNING_CODEC_IDS[kind],
            )
        )
    return SourcePlanningCapabilityBundle(
        bundle_id="mrw.source.plan-source-mode.bundle.v2",
        operations=tuple(operations),
        codecs=tuple(codecs),
        profiles={
            "semantic": semantic,
            "effect": effect,
            "resource": resource,
            "failure": failure,
            "authority": _authority_profile(SOURCE_PLANNING_OWNERS[kind]),
            "interpreter": interpreter,
            "observation": observation,
        },
    )


def build_source_planning_catalog(
    bundle: SourcePlanningCapabilityBundle,
) -> Annotated[
    OperationContractCatalogSnapshot,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=C2.2_operation_bundle witness=test:test_w06_successor_authority_metadata"
    ],
]:
    return OperationContractCatalogSnapshot(
        catalog_id=SOURCE_PLANNING_CATALOG_ID,
        catalog_version=SOURCE_PLANNING_CATALOG_VERSION,
        entries=tuple(
            (
                operation.ref.kind,
                operation.ref.contract_version,
                operation.ref.contract_digest,
                operation.owner_capability_id,
            )
            for operation in bundle.operations
        ),
    )


def build_source_planning_registry(
    bundle: SourcePlanningCapabilityBundle,
) -> Annotated[
    OperationContractRegistry,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=C2.2_operation_bundle witness=test:test_w06_successor_authority_metadata"
    ],
]:
    return OperationContractRegistry(
        build_source_planning_catalog(bundle),
        bundle.operations,
    )
