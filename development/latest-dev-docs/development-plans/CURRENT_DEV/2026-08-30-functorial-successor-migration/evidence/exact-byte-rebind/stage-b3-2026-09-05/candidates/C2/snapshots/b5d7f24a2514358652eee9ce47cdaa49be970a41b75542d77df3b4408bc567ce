"""Frozen typed contracts and capability bundle for the four C2.2 planners.

DTOs/contracts live in ``source_library_c2_shared``; this module owns the four
operation contracts, profiles, codecs and catalog/registry assembly and
re-exports the shared planning/collection vocabulary.  C2.2 never executes
effects; provider dispatch is delegated to C2.3 ports.
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
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    make_operation_contract,
)

__all__ = [
    "C2_2_BATCH_SIZE",
    "C2_2_MAX_QUERY_TERMS",
    "C2_2_MAX_TASKS",
    "C2_2_MAX_URLS",
    "C2_2_PLANNING_FAILURE_CODES",
    "C2_2_RESOURCE_CEILING_REF",
    "SOURCE_LIBRARY_C2_2_CATALOG_ID",
    "SOURCE_LIBRARY_C2_2_CATALOG_VERSION",
    "SOURCE_LIBRARY_C2_2_OWNER",
    "SOURCE_LIBRARY_C2_2_PROTOCOL_SEARCH_KIND",
    "SOURCE_LIBRARY_C2_2_PROVIDER_HARVEST_KIND",
    "SOURCE_LIBRARY_C2_2_SITE_SEARCH_KIND",
    "SOURCE_LIBRARY_C2_2_URL_EXECUTION_KIND",
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
    "build_source_library_c2_2_bundle",
    "build_source_library_c2_2_catalog",
    "build_source_library_c2_2_registry",
    "source_collection_outcomes_equal",
    "source_mode_plan_digest",
]

_SHARED_EXPORTS = (
    "C2_2_BATCH_SIZE",
    "C2_2_MAX_QUERY_TERMS",
    "C2_2_MAX_TASKS",
    "C2_2_MAX_URLS",
    "C2_2_PLANNING_FAILURE_CODES",
    "C2_2_RESOURCE_CEILING_REF",
    "SOURCE_LIBRARY_C2_2_CATALOG_ID",
    "SOURCE_LIBRARY_C2_2_CATALOG_VERSION",
    "SOURCE_LIBRARY_C2_2_OWNER",
    "SOURCE_LIBRARY_C2_2_PROTOCOL_SEARCH_KIND",
    "SOURCE_LIBRARY_C2_2_PROVIDER_HARVEST_KIND",
    "SOURCE_LIBRARY_C2_2_SITE_SEARCH_KIND",
    "SOURCE_LIBRARY_C2_2_URL_EXECUTION_KIND",
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

C2_2_BATCH_SIZE = _shared.C2_2_BATCH_SIZE
C2_2_MAX_QUERY_TERMS = _shared.C2_2_MAX_QUERY_TERMS
C2_2_MAX_TASKS = _shared.C2_2_MAX_TASKS
C2_2_MAX_URLS = _shared.C2_2_MAX_URLS
C2_2_PLANNING_FAILURE_CODES = _shared.C2_2_PLANNING_FAILURE_CODES
C2_2_RESOURCE_CEILING_REF = _shared.C2_2_RESOURCE_CEILING_REF
SOURCE_LIBRARY_C2_2_CATALOG_ID = _shared.SOURCE_LIBRARY_C2_2_CATALOG_ID
SOURCE_LIBRARY_C2_2_CATALOG_VERSION = _shared.SOURCE_LIBRARY_C2_2_CATALOG_VERSION
SOURCE_LIBRARY_C2_2_OWNER = _shared.SOURCE_LIBRARY_C2_2_OWNER
SOURCE_LIBRARY_C2_2_PROTOCOL_SEARCH_KIND = (
    _shared.SOURCE_LIBRARY_C2_2_PROTOCOL_SEARCH_KIND
)
SOURCE_LIBRARY_C2_2_PROVIDER_HARVEST_KIND = (
    _shared.SOURCE_LIBRARY_C2_2_PROVIDER_HARVEST_KIND
)
SOURCE_LIBRARY_C2_2_SITE_SEARCH_KIND = _shared.SOURCE_LIBRARY_C2_2_SITE_SEARCH_KIND
SOURCE_LIBRARY_C2_2_URL_EXECUTION_KIND = _shared.SOURCE_LIBRARY_C2_2_URL_EXECUTION_KIND
SOURCE_MODE_PLANNING_OBSERVATION_PROFILE = (
    _shared.SOURCE_MODE_PLANNING_OBSERVATION_PROFILE
)
SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA = _shared.SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA
CollectionCancelled = _shared.CollectionCancelled
CollectionCompleted = _shared.CollectionCompleted
CollectionFailed = _shared.CollectionFailed
CollectionOutcomeUnknown = _shared.CollectionOutcomeUnknown
CollectionPartiallyCompleted = _shared.CollectionPartiallyCompleted
CollectionProviderAccepted = _shared.CollectionProviderAccepted
CollectionRejected = _shared.CollectionRejected
FallbackRule = _shared.FallbackRule
OrderedFailure = _shared.OrderedFailure
OrderedFoldPolicy = _shared.OrderedFoldPolicy
PlannedPlanning = _shared.PlannedPlanning
ProviderHandoff = _shared.ProviderHandoff
RejectedPlanning = _shared.RejectedPlanning
SourceCollectionOutcome = _shared.SourceCollectionOutcome
SourceCollectionTerminal = _shared.SourceCollectionTerminal
SourceModePlan = _shared.SourceModePlan
SourceModePlanningPayload = _shared.SourceModePlanningPayload
SourceModePlanningResult = _shared.SourceModePlanningResult
SourceModeTask = _shared.SourceModeTask
SourceTaskOutcome = _shared.SourceTaskOutcome
TerminalConstructionProfile = _shared.TerminalConstructionProfile
source_collection_outcomes_equal = _shared.source_collection_outcomes_equal
source_mode_plan_digest = _shared.source_mode_plan_digest

SOURCE_EXECUTION_REQUEST_SCHEMA_REF = _shared.SOURCE_EXECUTION_REQUEST_SCHEMA_REF
SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA = _shared.SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA
SOURCE_MODE_PLAN_SCHEMA = _shared.SOURCE_MODE_PLAN_SCHEMA
SOURCE_MODE_TASK_SCHEMA = _shared.SOURCE_MODE_TASK_SCHEMA
COLLECTION_TERMINAL_SCHEMA = _shared.COLLECTION_TERMINAL_SCHEMA
PROVIDER_HANDOFF_SCHEMA = _shared.PROVIDER_HANDOFF_SCHEMA
SOURCE_LIBRARY_C2_2_KINDS = _shared.SOURCE_LIBRARY_C2_2_KINDS
SOURCE_MODE_PLANNING_PAYLOAD_TYPE = _shared.SOURCE_MODE_PLANNING_PAYLOAD_TYPE
SOURCE_MODE_PLANNING_RESULT_TYPE = _shared.SOURCE_MODE_PLANNING_RESULT_TYPE


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
        "semantic_profile_id": "mrw.successor.source-library.c2-2.semantic.v1",
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
        "effect_profile_id": "mrw.successor.source-library.c2-2.effect.v1",
        "effect_profile_version": "1.0.0",
        "execution_class": "PURE_TRANSFORM",
        "external_visibility": "NONE",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": (),
        "internal_export_only": True,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "mrw.successor.source-library.c2-2.idempotency.v1",
    }
    digest = content_digest(payload, omit_fields=("profile_digest",))
    return EffectProfile(**payload, profile_digest=digest)


def _resource_profile() -> ResourceProfile:
    payload = {
        "resource_profile_id": "mrw.successor.source-library.c2-2.resource.v1",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("cpu_light",),
        "concurrency_key": "source-library:c2-2-planning",
        "budget_units": "source-mode-plan",
        "default_soft_limit_seconds": 5,
        "default_hard_limit_seconds": 30,
        "node_profile_selector": "pure-planning",
        "budget_ref": C2_2_RESOURCE_CEILING_REF,
        "deadline_policy_ref": "mrw.successor.source-library.c2-2.deadline.v1",
        "node_profile_requirements": ("no_effect", "no_network", "no_credential"),
        "units": 1,
    }
    digest = content_digest(payload, omit_fields=("profile_digest",))
    return ResourceProfile(**payload, profile_digest=digest)


def _failure_profile() -> FailureProfile:
    payload = {
        "failure_profile_id": "mrw.successor.source-library.c2-2.failure.v1",
        "failure_profile_version": "1.0.0",
        "typed_failures": tuple(sorted(C2_2_PLANNING_FAILURE_CODES)),
        "retryable": False,
        "degraded_acceptable": True,
        "unknown_outcome_supported": False,
        "readback_or_compensation": "replan_or_reject",
        "failure_union_ref": "mrw.functorial-successor.failures.c2-2.v1",
        "retryable_failure_kinds": (),
        "readback_profile_ref": None,
        "compensation_profile_ref": None,
    }
    digest = content_digest(payload, omit_fields=("profile_digest",))
    return FailureProfile(**payload, profile_digest=digest)


def _authority_profile() -> AuthorityProfile:
    payload = {
        "authority_profile_id": "mrw.successor.source-library.c2-2.authority.v1",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": SOURCE_LIBRARY_C2_2_OWNER,
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    digest = content_digest(payload, omit_fields=("profile_digest",))
    return AuthorityProfile(**payload, profile_digest=digest)


def _interpreter_profile() -> InterpreterProfile:
    payload = {
        "interpreter_profile_id": "mrw.successor.source-library.c2-2.interpreter.v1",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": SOURCE_LIBRARY_C2_2_KINDS,
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": "successor-native.source_library.c2_2.plan",
                "version": "1.0.0",
                "boundary": "pure planning only",
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.pure.v1",
        "resource_profile_ref": "mrw.successor.source-library.c2-2.resource.v1",
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
        "observation_schema_ref": ("mrw.successor.source-library.c2-2.observation.v1"),
    }
    digest = content_digest(payload, omit_fields=("profile_digest",))
    return ObservationProfile(**payload, profile_digest=digest)


def _payload_codec(contract_ref: Any, operation_kind: str) -> PayloadCodec:
    return PayloadCodec(
        codec_id=f"mrw.successor.source-library.c2-2.{operation_kind}.codec.v1",
        codec_version="1.0.0",
        contract_ref=contract_ref,
        payload_type_id=SOURCE_MODE_PLANNING_PAYLOAD_TYPE.type_id,
        encode=lambda value: value.to_plain(),
        decode=_shared.source_mode_planning_payload_from_plain,
        codec_digest=codec_digest(
            f"mrw.successor.source-library.c2-2.{operation_kind}.codec.v1",
            "1.0.0",
            contract_ref,
            SOURCE_MODE_PLANNING_PAYLOAD_TYPE.type_id,
        ),
    )


@dataclass(frozen=True, slots=True)
class SourceLibraryC2_2CapabilityBundle:
    bundle_id: str
    operations: tuple[OperationContract, ...]
    codecs: tuple[PayloadCodec, ...]
    profiles: dict[str, object]

    def payload_codec(self, kind: str) -> PayloadCodec:
        for codec in self.codecs:
            if kind in codec.codec_id:
                return codec
        raise KeyError(f"no C2.2 payload codec for {kind}")


def build_source_library_c2_2_bundle() -> SourceLibraryC2_2CapabilityBundle:
    semantic = _semantic_profile()
    effect = _effect_profile()
    resource = _resource_profile()
    failure = _failure_profile()
    authority = _authority_profile()
    interpreter = _interpreter_profile()
    observation = _observation_profile()
    profile_refs = {
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
        "authority": _profile_ref(
            authority.authority_profile_id,
            authority.authority_profile_version,
            authority.profile_digest,
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
    for kind in SOURCE_LIBRARY_C2_2_KINDS:
        operation = make_operation_contract(
            kind=kind,
            contract_version="1.0.0",
            input_type=SOURCE_MODE_PLANNING_PAYLOAD_TYPE,
            output_type=SOURCE_MODE_PLANNING_RESULT_TYPE,
            return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
            semantic_profile_ref=profile_refs["semantic"],
            effect_profile_ref=profile_refs["effect"],
            resource_profile_ref=profile_refs["resource"],
            failure_profile_ref=profile_refs["failure"],
            authority_profile_ref=profile_refs["authority"],
            interpreter_compatibility_ref=profile_refs["interpreter"],
            observation_profile_ref=profile_refs["observation"],
            allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
            owner_capability_id=SOURCE_LIBRARY_C2_2_OWNER,
        )
        operations.append(operation)
        codecs.append(_payload_codec(operation.ref, kind))
    return SourceLibraryC2_2CapabilityBundle(
        bundle_id="mrw.functorial-successor.source-library.c2-2",
        operations=tuple(operations),
        codecs=tuple(codecs),
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


def build_source_library_c2_2_catalog(
    bundle: SourceLibraryC2_2CapabilityBundle,
) -> OperationContractCatalogSnapshot:
    return OperationContractCatalogSnapshot(
        catalog_id=SOURCE_LIBRARY_C2_2_CATALOG_ID,
        catalog_version=SOURCE_LIBRARY_C2_2_CATALOG_VERSION,
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


def build_source_library_c2_2_registry(
    bundle: SourceLibraryC2_2CapabilityBundle,
) -> OperationContractRegistry:
    return OperationContractRegistry(
        build_source_library_c2_2_catalog(bundle),
        bundle.operations,
    )
