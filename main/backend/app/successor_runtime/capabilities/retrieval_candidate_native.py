"""One native candidate discovery declaration and its reusable lowering rule.

The declaration owns identity, endpoint types and the default provider policy.
The existing search kernel remains the only executor; the concrete discovery
callable is supplied by the service composition owner at assembly, so this
module stays free of any ``app.services`` dependency.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
import json
from typing import Annotated, Literal, TypeVar, cast

from functorial_kit.contribution_compiler import NativeContributionRule, compile_native_contribution
from functorial_kit.contributions import ContributionObject, contribution_failures
from functorial_kit.core.canonical import codec_failures
from functorial_kit.core.codec import Codec, define_codec
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)

from app.successor_runtime.capabilities.checksum import (
    CanonicalJsonArray,
    CanonicalJsonObject,
    CanonicalJsonValue,
    canonical_json,
    content_digest,
    dataclass_field_names,
    sha256_hex,
)
from app.successor_runtime.capabilities.codecs import PayloadCodec, dataclass_codec
from app.successor_runtime.capabilities.catalog import build_operation_catalog
from app.successor_runtime.capabilities.retrieval_common import (
    CANDIDATE_BUNDLE_TYPE,
    CANDIDATE_REQUEST_TYPE,
    Candidate,
    CandidateBundle,
    CandidateOccurrence,
    CandidateRequestFailure,
    CandidateSearchRequest,
    ProviderObservation,
    RetrievalBudgetState,
    RetrievalCandidateAttemptOutcome,
    RetrievalCandidateInvocation,
    StopReason,
    raise_retrieval_contract_error,
)
from app.successor_runtime.language.algebra import OperationSpec, ValueRef, freeze_json_object
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.object_contracts import (
    SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF,
    OperationContract,
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.capabilities.profiles import OperationProfiles, build_operation_profiles
from app.successor_runtime.language.program import (
    ProgramNode,
    atom_node,
    zip_ordered_node,
)
from app.successor_runtime.language.transforms import MergeRef, TransformRegistry
from app.successor_runtime.research.object_types import ObjectType


SUPPORTED_PROVIDERS = frozenset({"auto", "ddg", "google", "serper", "serpstack", "serpapi", "searxng", "yacy"})


@dataclass(frozen=True, slots=True)
class CandidateNativeSource:
    contribution_id: str
    operation_id: str
    owner: str
    default_provider: str = "auto"
    input_type: ObjectType = CANDIDATE_REQUEST_TYPE
    output_type: ObjectType = CANDIDATE_BUNDLE_TYPE


DEFAULT_CANDIDATE_NATIVE_SOURCE = CandidateNativeSource(
    contribution_id="mrw.retrieval.candidate.native.v1",
    operation_id="retrieval.candidate.discover.v1",
    owner="services.search.candidate_search",
)


RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND = "retrieval.candidate.discover.v3"
RETRIEVAL_CANDIDATE_DISCOVER_V3_VERSION = "3"
RETRIEVAL_CANDIDATE_DISCOVER_V3_OWNER = "services.search.candidate_search"
RETRIEVAL_CANDIDATE_OBSERVATION_PROFILE = "mrw.retrieval.candidate.observation.v3"
RETRIEVAL_CANDIDATE_REQUEST_CODEC_ID = "retrieval.candidate.discover.v3.request.v3"
RETRIEVAL_CANDIDATE_BUNDLE_CODEC_ID = "retrieval.candidate.discover.v3.bundle.v3"
RETRIEVAL_CANDIDATE_ATTEMPT_CODEC_ID = "retrieval.candidate.discover.v3.attempt-outcome.v1"
RETRIEVAL_CANDIDATE_INVOCATION_CODEC_ID = "retrieval.candidate.discover.v3.invocation.v1"
RETRIEVAL_BUDGET_CODEC_ID = "retrieval.budget-state.v1"

# The v3 contract binds each endpoint ObjectType to its exact payload codec so
# the shared value read/publish paths resolve bytes by ObjectType.codec_id.
# V3 has a distinct durable identity because it replaces the provisional v2
# direct request endpoint with a budget-bound invocation endpoint.  Reusing v2
# would silently reinterpret already-persisted contracts.
RETRIEVAL_CANDIDATE_REQUEST_V3_TYPE = replace(
    CANDIDATE_REQUEST_TYPE,
    codec_id=RETRIEVAL_CANDIDATE_REQUEST_CODEC_ID,
    canonical_codec_version=RETRIEVAL_CANDIDATE_DISCOVER_V3_VERSION,
)
RETRIEVAL_CANDIDATE_BUNDLE_V3_TYPE = replace(
    CANDIDATE_BUNDLE_TYPE,
    codec_id=RETRIEVAL_CANDIDATE_BUNDLE_CODEC_ID,
    canonical_codec_version=RETRIEVAL_CANDIDATE_DISCOVER_V3_VERSION,
)
RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE = ObjectType(
    "RetrievalCandidateAttemptOutcome.v1",
    codec_id=RETRIEVAL_CANDIDATE_ATTEMPT_CODEC_ID,
    canonical_codec_version="1",
)
RETRIEVAL_CANDIDATE_INVOCATION_TYPE = ObjectType(
    "RetrievalCandidateInvocation.v1",
    codec_id=RETRIEVAL_CANDIDATE_INVOCATION_CODEC_ID,
    canonical_codec_version="1",
)
RETRIEVAL_BUDGET_STATE_TYPE = ObjectType(
    "RetrievalBudgetState.v1",
    codec_id=RETRIEVAL_BUDGET_CODEC_ID,
    canonical_codec_version="1",
)
RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE = ObjectType(
    "sequence:RetrievalCandidateAttemptOutcome.v1",
    codec_id="mrw.successor.sequence_codec.v1",
    canonical_codec_version="1",
)


def _build_profiles(kind: str, owner: str) -> OperationProfiles:
    dependency_digest = content_digest(
        {
            "interpreter": "services.search.candidate_search.discover_candidates",
            "version": "3.0.0",
            "boundary": "provider search kernel; candidates only, no document write or ingest",
        }
    )
    return build_operation_profiles(
        identity=kind,
        semantic={
            "reads": (
                RETRIEVAL_CANDIDATE_INVOCATION_TYPE.type_id,
                RETRIEVAL_BUDGET_STATE_TYPE.type_id,
            ),
            "creates": (RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE.type_id,),
            "creates_relations": (),
            "declared_loss": (),
            "observation_profile_ref": RETRIEVAL_CANDIDATE_OBSERVATION_PROFILE,
        },
        effect={
            "execution_class": "EFFECTFUL",
            "external_visibility": "INTERNAL_ONLY",
            "network_required": True,
            "irreversible": False,
            "cancellation_points": ("step_boundary",),
            "internal_export_only": True,
            "human_approval_required": False,
            "external_acquisition": False,
            "idempotency_profile_ref": "logical_request_id",
        },
        resource={
            "resource_classes": ("NETWORK_IO",),
            "concurrency_key": "project:provider",
            "budget_units": "query",
            "default_soft_limit_seconds": 20,
            "default_hard_limit_seconds": 20,
            "node_profile_selector": "any",
            "budget_ref": RETRIEVAL_BUDGET_STATE_TYPE.type_id,
            "deadline_policy_ref": f"{kind}.deadline-policy",
            "node_profile_requirements": ("any",),
            "units": 1,
        },
        failure={
            "typed_failures": ("INVALID_INPUT", "INTERPRETER_UNAVAILABLE", "ASSIGNMENT_BINDING_MISMATCH"),
            "retryable": False,
            "degraded_acceptable": True,
            "unknown_outcome_supported": False,
            "readback_or_compensation": "readback",
            "failure_union_ref": f"{kind}.failures",
            "retryable_failure_kinds": (),
            "readback_profile_ref": RETRIEVAL_CANDIDATE_OBSERVATION_PROFILE,
            "compensation_profile_ref": None,
        },
        authority={
            "grant_scopes": ("project",),
            "approval_required": False,
            "approval_kinds": (),
            "credential_refs": (),
            "canonical_owner": owner,
            "revalidation_points": ("claim_time",),
            "authority_epoch": 1,
        },
        interpreter={
            "supported_contract_kinds": (kind,),
            "supported_contract_refs": (),
            "dependency_digest": dependency_digest,
            "security_profile_ref": "mrw.retrieval.candidate.security.v3",
            "resource_profile_ref": f"{kind}.resource",
            "credential_requirements_ref": None,
            "cancellation_profile_ref": "step_boundary",
            "idempotency_profile_ref": "logical_request_id",
            "authoritative_readback_profile_ref": None,
            "receipt_codec_ref": RETRIEVAL_CANDIDATE_OBSERVATION_PROFILE,
        },
        observation={
            "observation_profile_id": RETRIEVAL_CANDIDATE_OBSERVATION_PROFILE,
            "dimensions": (
                "provider",
                "route",
                "keyword",
                "status",
                "returned_count",
                "failure_kind",
                "candidate_uri",
                "relevance_score",
            ),
            "compatible_with_legacy": True,
            "observation_schema_ref": RETRIEVAL_CANDIDATE_OBSERVATION_PROFILE,
        },
    )


def build_retrieval_candidate_operation_contract(
    owner: str = RETRIEVAL_CANDIDATE_DISCOVER_V3_OWNER,
    profiles: OperationProfiles | None = None,
) -> Annotated[
    OperationContract,
    "kit:non-authoritative derived_as=view fact_source=candidate_v3_endpoint_types+operation_profiles witness=test:test_operation_contract_is_v3_network_effect_without_document_write",
]:
    if profiles is None:
        profiles = _build_profiles(RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND, owner)
    return profiles.contract(
        kind=RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND,
        contract_version=RETRIEVAL_CANDIDATE_DISCOVER_V3_VERSION,
        input_type=RETRIEVAL_CANDIDATE_INVOCATION_TYPE,
        output_type=RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE,
        return_contract_ref=SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF,
        allowed_override_schema_ref="mrw.retrieval.candidate.override.none.v3",
        owner_capability_id=owner,
    )


_T = TypeVar("_T")


def _require_object(raw: CanonicalJsonValue, label: str) -> CanonicalJsonObject:
    if not isinstance(raw, dict):
        raise_retrieval_contract_error(TypeError, f'{label} must be an object')
    return raw


def _require_array(raw: CanonicalJsonValue, label: str) -> list[CanonicalJsonValue]:
    if not isinstance(raw, list):
        raise_retrieval_contract_error(TypeError, f'{label} must be an array')
    return raw


def _reconstruct_leaf(cls: type[_T], raw: CanonicalJsonValue, label: str) -> _T:
    obj = _require_object(raw, label)
    allowed = dataclass_field_names(cls)
    return cls(**{k: v for k, v in obj.items() if k in allowed})


def _require_stop_reason(raw: CanonicalJsonValue) -> StopReason:
    if not isinstance(raw, str):
        raise_retrieval_contract_error(TypeError, f'invalid stop_reason: {raw!r}')
    if (
        raw == "limit_reached"
        or raw == "candidates_observed"
        or raw == "no_candidates_observed"
        or raw == "not_attempted"
    ):
        return raw
    raise_retrieval_contract_error(TypeError, f'invalid stop_reason: {raw!r}')


def _reconstruct_candidate_bundle(value: CanonicalJsonObject) -> CandidateBundle:
    request = _reconstruct_leaf(CandidateSearchRequest, value["request"], "request")
    candidates = tuple(
        _reconstruct_leaf(Candidate, item, "candidate") for item in _require_array(value["candidates"], "candidates")
    )
    occurrences = tuple(
        _reconstruct_leaf(CandidateOccurrence, item, "occurrence")
        for item in _require_array(value["occurrences"], "occurrences")
    )
    observations = tuple(
        _reconstruct_leaf(ProviderObservation, item, "observation")
        for item in _require_array(value["observations"], "observations")
    )
    failure_raw = value.get("request_failure")
    request_failure = None
    if failure_raw is not None:
        request_failure = _reconstruct_leaf(CandidateRequestFailure, failure_raw, "request_failure")
    return CandidateBundle(
        request=request,
        candidates=candidates,
        occurrences=occurrences,
        observations=observations,
        stop_reason=_require_stop_reason(value["stop_reason"]),
        request_failure=request_failure,
    )


def build_retrieval_candidate_bundle_codec(
    contract_ref: OperationContractRef,
) -> Annotated[
    PayloadCodec[CandidateBundle],
    "kit:non-authoritative derived_as=view fact_source=candidate_bundle_schema+contract_ref witness=test:test_bundle_codec_roundtrips_nested_types_and_rejects_non_object",
]:
    base = dataclass_codec(
        codec_id=RETRIEVAL_CANDIDATE_BUNDLE_CODEC_ID,
        codec_version=RETRIEVAL_CANDIDATE_DISCOVER_V3_VERSION,
        contract_ref=contract_ref,
        payload_type_id=RETRIEVAL_CANDIDATE_BUNDLE_V3_TYPE.type_id,
        dto_cls=CandidateBundle,
    )

    return PayloadCodec(
        codec_id=base.codec_id,
        codec_version=base.codec_version,
        contract_ref=contract_ref,
        payload_type_id=base.payload_type_id,
        encode=base.encode_payload,
        decode=_reconstruct_candidate_bundle,
        codec_digest=base.codec_digest,
    )


def build_retrieval_candidate_attempt_codec(
    contract_ref: OperationContractRef,
) -> Annotated[
    PayloadCodec[RetrievalCandidateAttemptOutcome],
    "kit:non-authoritative derived_as=view fact_source=candidate_attempt_schema+contract_ref witness=test:test_attempt_outcome_codec_roundtrips_completed_bundle",
]:
    base = dataclass_codec(
        codec_id=RETRIEVAL_CANDIDATE_ATTEMPT_CODEC_ID,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE.type_id,
        dto_cls=RetrievalCandidateAttemptOutcome,
    )

    def decode(value: CanonicalJsonObject) -> RetrievalCandidateAttemptOutcome:
        bundle_raw = value.get("bundle")
        bundle = None
        if bundle_raw is not None:
            bundle = _reconstruct_candidate_bundle(_require_object(bundle_raw, "bundle"))
        state = _require_text(value.get("state"), "state")
        if state not in {"completed", "failed", "cancelled"}:
            raise_retrieval_contract_error(TypeError, 'candidate attempt state is invalid')
        return RetrievalCandidateAttemptOutcome(
            query_id=_require_text(value.get("query_id"), "query_id"),
            route_id=_require_text(value.get("route_id"), "route_id"),
            query_kind=_require_query_kind(value.get("query_kind")),
            query_ordinal=_require_int(value.get("query_ordinal"), "query_ordinal"),
            followup_round=_require_int(value.get("followup_round"), "followup_round"),
            budget_id=_require_text(value.get("budget_id"), "budget_id"),
            state=cast(Literal["completed", "failed", "cancelled"], state),
            bundle=bundle,
            error_code=_optional_text(value.get("error_code"), "error_code"),
            error_message=_optional_text(value.get("error_message"), "error_message"),
            terminal_ref=_optional_text(value.get("terminal_ref"), "terminal_ref"),
            terminal_digest=_optional_text(value.get("terminal_digest"), "terminal_digest"),
        )

    return PayloadCodec(
        codec_id=base.codec_id,
        codec_version=base.codec_version,
        contract_ref=contract_ref,
        payload_type_id=base.payload_type_id,
        encode=base.encode_payload,
        decode=decode,
        codec_digest=base.codec_digest,
    )


def build_retrieval_candidate_request_codec(
    contract_ref: OperationContractRef,
) -> Annotated[
    PayloadCodec[CandidateSearchRequest],
    "kit:non-authoritative derived_as=view fact_source=candidate_request_schema+contract_ref witness=test:test_request_codec_roundtrips",
]:
    return dataclass_codec(
        codec_id=RETRIEVAL_CANDIDATE_REQUEST_CODEC_ID,
        codec_version=RETRIEVAL_CANDIDATE_DISCOVER_V3_VERSION,
        contract_ref=contract_ref,
        payload_type_id=RETRIEVAL_CANDIDATE_REQUEST_V3_TYPE.type_id,
        dto_cls=CandidateSearchRequest,
    )


def build_retrieval_budget_codec(
    contract_ref: OperationContractRef,
) -> Annotated[
    PayloadCodec[RetrievalBudgetState],
    "kit:non-authoritative derived_as=view fact_source=retrieval_budget_schema+contract_ref witness=test:test_invocation_and_budget_codecs_roundtrip_typed_values",
]:
    return dataclass_codec(
        codec_id=RETRIEVAL_BUDGET_CODEC_ID,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=RETRIEVAL_BUDGET_STATE_TYPE.type_id,
        dto_cls=RetrievalBudgetState,
    )


def build_retrieval_candidate_invocation_codec(
    contract_ref: OperationContractRef,
) -> Annotated[
    PayloadCodec[RetrievalCandidateInvocation],
    "kit:non-authoritative derived_as=view fact_source=candidate_invocation_schema+request_schema+contract_ref witness=test:test_invocation_and_budget_codecs_roundtrip_typed_values",
]:
    base = dataclass_codec(
        codec_id=RETRIEVAL_CANDIDATE_INVOCATION_CODEC_ID,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=RETRIEVAL_CANDIDATE_INVOCATION_TYPE.type_id,
        dto_cls=RetrievalCandidateInvocation,
    )

    def decode(value: CanonicalJsonObject) -> RetrievalCandidateInvocation:
        request_raw = _require_object(value.get("request"), "request")
        request = _reconstruct_leaf(CandidateSearchRequest, request_raw, "request")
        return RetrievalCandidateInvocation(
            query_id=_require_text(value.get("query_id"), "query_id"),
            route_id=_require_text(value.get("route_id"), "route_id"),
            query_kind=_require_query_kind(value.get("query_kind")),
            query_ordinal=_require_int(value.get("query_ordinal"), "query_ordinal"),
            followup_round=_require_int(value.get("followup_round"), "followup_round"),
            budget_id=_require_text(value.get("budget_id"), "budget_id"),
            request=request,
        )

    return PayloadCodec(
        codec_id=base.codec_id,
        codec_version=base.codec_version,
        contract_ref=contract_ref,
        payload_type_id=base.payload_type_id,
        encode=base.encode_payload,
        decode=decode,
        codec_digest=base.codec_digest,
    )


def _require_text(value: CanonicalJsonValue, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise_retrieval_contract_error(TypeError, f'{label} must be a nonempty string')
    return value


def _optional_text(value: CanonicalJsonValue, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise_retrieval_contract_error(TypeError, f'{label} must be null or a nonempty string')
    return value


def _require_int(value: CanonicalJsonValue, label: str) -> int:
    if type(value) is not int:
        raise_retrieval_contract_error(TypeError, f'{label} must be an integer')
    return value


def _require_query_kind(value: CanonicalJsonValue) -> Literal["initial", "followup"]:
    text = _require_text(value, "query_kind")
    if text not in {"initial", "followup"}:
        raise_retrieval_contract_error(TypeError, 'query_kind must be initial or followup')
    return cast(Literal["initial", "followup"], text)


@dataclass(frozen=True, slots=True)
class CandidateProgramAtomWiring:
    operation_id: str
    operation_kind: str
    payload_codec_id: str
    input_type: ObjectType
    output_type: ObjectType
    return_contract_ref: str


@dataclass(frozen=True, slots=True)
class CandidateRuntimeDefinition:
    operation_contract: OperationContract
    request_codec: PayloadCodec[CandidateSearchRequest]
    invocation_codec: PayloadCodec[RetrievalCandidateInvocation]
    budget_codec: PayloadCodec[RetrievalBudgetState]
    bundle_codec: PayloadCodec[CandidateBundle]
    output_codec: PayloadCodec[RetrievalCandidateAttemptOutcome]
    program_atom: CandidateProgramAtomWiring
    profiles: OperationProfiles

    def build_catalog(
        self,
        *,
        catalog_id: str = "mrw.retrieval.candidate.operations",
        catalog_version: str = "3",
    ) -> OperationContractCatalogSnapshot:
        return build_operation_catalog(
            (self.operation_contract,),
            catalog_id=catalog_id,
            catalog_version=catalog_version,
        )

    def build_registry(self, catalog: OperationContractCatalogSnapshot) -> OperationContractRegistry:
        return OperationContractRegistry(catalog=catalog, contracts=(self.operation_contract,))

    def validate_bound_inputs(
        self,
        invocation: RetrievalCandidateInvocation,
        bound_inputs: tuple[tuple[ValueRef, bytes], ...],
    ) -> None:
        """Validate the exact static root budget and invocation before search."""

        if len(bound_inputs) != 2:
            raise_retrieval_contract_error(ValueError, 'candidate operation requires exactly budget and invocation inputs')
        (budget_ref, budget_bytes), (invocation_ref, invocation_bytes) = bound_inputs
        if budget_ref.object_type != RETRIEVAL_BUDGET_STATE_TYPE or budget_ref.codec_id != self.budget_codec.codec_id:
            raise_retrieval_contract_error(ValueError, 'candidate budget input type or codec drift')
        if (
            invocation_ref.object_type != RETRIEVAL_CANDIDATE_INVOCATION_TYPE
            or invocation_ref.codec_id != self.invocation_codec.codec_id
        ):
            raise_retrieval_contract_error(ValueError, 'candidate invocation input type or codec drift')
        if budget_ref.project_key != invocation_ref.project_key:
            raise_retrieval_contract_error(ValueError, 'candidate bound inputs cross project scope')
        budget_payload = _decode_canonical_object_bytes(budget_bytes, "candidate budget")
        invocation_payload = _decode_canonical_object_bytes(invocation_bytes, "candidate invocation")
        budget = self.budget_codec.decode_payload(budget_payload)
        bound_invocation = self.invocation_codec.decode_payload(invocation_payload)
        if bound_invocation != invocation and not _dynamic_invocation_matches_template(
            invocation,
            bound_invocation,
        ):
            raise_retrieval_contract_error(ValueError, 'candidate semantic invocation differs from its bound input')
        for ref, content in bound_inputs:
            if ref.byte_size != len(content) or ref.content_digest != sha256_hex(content):
                raise_retrieval_contract_error(ValueError, 'candidate bound input bytes differ from ValueRef')
        invocation.validate_budget(budget)


def _dynamic_invocation_matches_template(
    invocation: RetrievalCandidateInvocation,
    template: RetrievalCandidateInvocation,
) -> bool:
    """Admit only the explicit static follow-up slot filled by a prior Effect.

    The template qualifies project, route, round, budget and provider policy.
    Only the planner-owned query identity and topic may arrive dynamically.
    """

    if not (
        template.query_id.startswith("dynamic-followup:")
        and template.request.topic == "__runtime_planned_followup__"
    ):
        return False
    return (
        invocation.query_kind == template.query_kind == "followup"
        and invocation.route_id == template.route_id
        and invocation.query_ordinal == template.query_ordinal
        and invocation.followup_round == template.followup_round
        and invocation.budget_id == template.budget_id
        and invocation.request.language == template.request.language
        and 0 < invocation.request.max_results <= template.request.max_results
        and invocation.request.provider == template.request.provider
        and invocation.request.days_back == template.request.days_back
        and invocation.request.exclude_existing == template.request.exclude_existing
        and invocation.request.start_offset == template.request.start_offset
        and invocation.request.keywords == template.request.keywords
        and invocation.request.project_ref == template.request.project_ref
        and invocation.request.source_ref == template.request.source_ref
        and invocation.request.facet_ref == template.request.facet_ref
        and invocation.query_id.strip() != ""
        and invocation.request.topic.strip() != ""
    )


def build_retrieval_candidate_runtime_definition(
    owner: str = RETRIEVAL_CANDIDATE_DISCOVER_V3_OWNER,
) -> Annotated[
    CandidateRuntimeDefinition,
    "kit:non-authoritative derived_as=composition fact_source=candidate_v3_contract+codecs+profiles+atom_wiring witness=test:test_runtime_definition_builds_catalog_and_registry",
]:
    kind = RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND
    profiles = _build_profiles(kind, owner)
    operation_contract = build_retrieval_candidate_operation_contract(owner=owner, profiles=profiles)
    request_codec = build_retrieval_candidate_request_codec(operation_contract.ref)
    invocation_codec = build_retrieval_candidate_invocation_codec(operation_contract.ref)
    budget_codec = build_retrieval_budget_codec(operation_contract.ref)
    bundle_codec = build_retrieval_candidate_bundle_codec(operation_contract.ref)
    output_codec = build_retrieval_candidate_attempt_codec(operation_contract.ref)
    program_atom = CandidateProgramAtomWiring(
        operation_id=RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND,
        operation_kind=RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND,
        payload_codec_id=invocation_codec.codec_id,
        input_type=RETRIEVAL_CANDIDATE_INVOCATION_TYPE,
        output_type=RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE,
        return_contract_ref=SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF,
    )
    return CandidateRuntimeDefinition(
        operation_contract=operation_contract,
        request_codec=request_codec,
        invocation_codec=invocation_codec,
        budget_codec=budget_codec,
        bundle_codec=bundle_codec,
        output_codec=output_codec,
        program_atom=program_atom,
        profiles=profiles,
    )


def _candidate_value_ref(
    encoded: bytes,
    *,
    program_id: str,
    project_key: str,
    codec_id: str,
    object_type: ObjectType,
    value_suffix: str,
) -> ValueRef:
    value_id = "retrieval-candidate-value:" + content_digest(
        {
            "schema": "mrw.retrieval.candidate.value-identity.v1",
            "program_id": program_id,
            "project_key": project_key,
            "value_suffix": value_suffix,
            "content_digest": sha256_hex(encoded),
        }
    )
    provenance_digest = content_digest(
        {
            "schema": "mrw.retrieval.candidate.payload-provenance.v3",
            "program_id": program_id,
            "project_key": project_key,
            "content_digest": sha256_hex(encoded),
        }
    )
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=object_type,
        codec_id=codec_id,
        content_digest=sha256_hex(encoded),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(encoded),
        provenance_digest=provenance_digest,
    )


def _retrieval_budget_value_ref(
    encoded: bytes,
    *,
    budget: RetrievalBudgetState,
    codec_id: str,
) -> ValueRef:
    """Name one immutable budget state independently of any child Program."""

    digest = sha256_hex(encoded)
    identity_digest = content_digest(
        {
            "schema": "mrw.retrieval.budget-state.value-identity.v1",
            "budget_id": budget.budget_id,
            "project_key": budget.project_key,
            "content_digest": digest,
        }
    )
    value_id = f"retrieval-budget-value:{identity_digest}"
    return ValueRef(
        value_id=value_id,
        project_key=budget.project_key,
        object_type=RETRIEVAL_BUDGET_STATE_TYPE,
        codec_id=codec_id,
        content_digest=digest,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(encoded),
        provenance_digest=content_digest(
            {
                "schema": "mrw.retrieval.budget-state.payload-provenance.v1",
                "budget_id": budget.budget_id,
                "project_key": budget.project_key,
                "content_digest": digest,
            }
        ),
    )


def _decode_canonical_object_bytes(content: bytes, label: str) -> CanonicalJsonObject:
    try:
        decoded: CanonicalJsonValue = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise_retrieval_contract_error(ValueError, f'{label} bytes are not canonical JSON', cause=exc)
    if not isinstance(decoded, dict) or canonical_json(decoded).encode("utf-8") != content:
        raise_retrieval_contract_error(ValueError, f'{label} bytes are not a canonical object')
    return decoded


def _candidate_return_contract(return_contract_ref: str) -> ReturnContract:
    return ReturnContract(
        success_modes=("SUCCEEDED",),
        failure_modes=("FAILED",),
        admission_required=False,
        wait_modes=("WAIT",),
        cancel_modes=("CANCELED",),
    )


def complete_retrieval_candidate_attempt(
    invocation: RetrievalCandidateInvocation,
    bundle: CandidateBundle,
) -> RetrievalCandidateAttemptOutcome:
    """Wrap an executed search kernel result in the durable terminal union."""

    return RetrievalCandidateAttemptOutcome.completed(invocation, bundle)


def _collect_candidate_attempt_pair(
    left: CanonicalJsonValue,
    right: CanonicalJsonValue,
) -> CanonicalJsonArray:
    return [left, right]


def _append_candidate_attempt(
    left: CanonicalJsonArray,
    right: CanonicalJsonValue,
) -> CanonicalJsonArray:
    return [*left, right]


def _register_candidate_attempt_merges(
    registry: TransformRegistry,
) -> tuple[MergeRef, MergeRef]:
    pair = registry.register_merge(
        name="mrw.retrieval.candidate.collect-attempt-pair",
        version="1.0.0",
        left_type=RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE,
        right_type=RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE,
        output_type=RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE,
        func=_collect_candidate_attempt_pair,
    )
    append = registry.register_merge(
        name="mrw.retrieval.candidate.append-attempt",
        version="1.0.0",
        left_type=RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE,
        right_type=RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE,
        output_type=RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE,
        func=_append_candidate_attempt,
    )
    return pair, append


def build_retrieval_candidate_merge_registry() -> Annotated[
    TransformRegistry,
    "kit:non-authoritative derived_as=program fact_source=candidate_attempt_sequence_merge_rules witness=test:test_candidate_prefix_orders_atoms_with_one_shared_budget",
]:
    registry = TransformRegistry(
        registry_id="mrw.retrieval.candidate-attempt.merge.v1",
        registry_version="1",
    )
    _register_candidate_attempt_merges(registry)
    return registry


@dataclass(frozen=True, slots=True)
class RetrievalCandidatePrefix:
    """Ordered candidate atoms and exact values embedded by the retrieval root."""

    root: ProgramNode
    values: tuple[tuple[ValueRef, bytes], ...]
    budget_ref: ValueRef


def _retrieval_budget_binding(
    runtime: CandidateRuntimeDefinition,
    budget: RetrievalBudgetState,
) -> tuple[ValueRef, bytes]:
    budget_bytes = canonical_json(runtime.budget_codec.encode_payload(budget)).encode("utf-8")
    return (
        _retrieval_budget_value_ref(
            budget_bytes,
            budget=budget,
            codec_id=runtime.budget_codec.codec_id,
        ),
        budget_bytes,
    )


def build_retrieval_candidate_prefix(
    *,
    invocations: tuple[RetrievalCandidateInvocation, ...],
    budget: RetrievalBudgetState,
    program_id: str,
    project_key: str,
    runtime: CandidateRuntimeDefinition | None = None,
) -> Annotated[
    RetrievalCandidatePrefix,
    "kit:prepared-command effect_boundary=successor_program_interpreter witness=test:test_candidate_prefix_orders_atoms_with_one_shared_budget",
]:
    """Build one real Effect for N=1 or an ordered ``ZipOrdered`` prefix."""

    if not invocations:
        raise_retrieval_contract_error(ValueError, 'candidate prefix requires at least one invocation')
    if not all(
        value.strip()
        for value in (
            program_id,
            project_key,
        )
    ):
        raise_retrieval_contract_error(ValueError, 'candidate prefix identities must be nonempty')
    if project_key != budget.project_key:
        raise_retrieval_contract_error(ValueError, 'candidate prefix crosses retrieval budget project')
    if len(invocations) > budget.remaining_queries:
        raise_retrieval_contract_error(ValueError, 'candidate prefix exceeds remaining query budget')
    expected_ordinals = tuple(
        range(
            budget.queries_attempted + 1,
            budget.queries_attempted + len(invocations) + 1,
        )
    )
    if tuple(item.query_ordinal for item in invocations) != expected_ordinals:
        raise_retrieval_contract_error(ValueError, 'candidate prefix query ordinals are not contiguous')
    if len({item.query_id for item in invocations}) != len(invocations):
        raise_retrieval_contract_error(ValueError, 'candidate prefix query identities must be unique')
    definition = runtime or build_retrieval_candidate_runtime_definition()
    budget_binding = _retrieval_budget_binding(definition, budget)
    occurrences: list[RetrievalCandidateAtom] = []
    for index, invocation in enumerate(invocations):
        invocation.validate_budget(budget)
        occurrence_digest = content_digest(
            {
                "schema": "mrw.retrieval.candidate.fixed-occurrence.v1",
                "budget_id": budget.budget_id,
                "query_id": invocation.query_id,
                "query_ordinal": invocation.query_ordinal,
                "index": index,
            }
        )
        occurrences.append(
            build_retrieval_candidate_atom(
                invocation=invocation,
                budget=budget,
                program_id=f"{program_id}:occurrence:{index + 1}",
                project_key=project_key,
                runtime=definition,
                budget_binding=budget_binding,
                operation_id=(
                    f"{definition.program_atom.operation_id}:occurrence:{index + 1}:{occurrence_digest[:12]}"
                ),
            )
        )
    merge_registry = TransformRegistry(
        registry_id="mrw.retrieval.candidate-attempt.merge.v1",
        registry_version="1",
    )
    pair_ref, append_ref = _register_candidate_attempt_merges(merge_registry)
    roots = [item.root for item in occurrences]
    root: ProgramNode = roots[0]
    for index, atom in enumerate(roots[1:], start=1):
        root = zip_ordered_node(
            left=root,
            right=atom,
            merge_ref=pair_ref if index == 1 else append_ref,
            output_type=RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE,
        )
    values_by_ref: dict[ValueRef, bytes] = {}
    for occurrence in occurrences:
        for ref, content in occurrence.values:
            previous = values_by_ref.setdefault(ref, content)
            if previous != content:
                raise_retrieval_contract_error(ValueError, 'candidate prefix value identity collision')
    return RetrievalCandidatePrefix(
        root=root,
        values=tuple(values_by_ref.items()),
        budget_ref=occurrences[0].budget_ref,
    )


@dataclass(frozen=True, slots=True)
class RetrievalCandidateAtom:
    """One candidate Effect atom and its exact bound values."""

    root: ProgramNode
    values: tuple[tuple[ValueRef, bytes], ...]
    invocation_ref: ValueRef
    budget_ref: ValueRef


def build_retrieval_candidate_atom(
    *,
    invocation: RetrievalCandidateInvocation,
    budget: RetrievalBudgetState,
    program_id: str,
    project_key: str,
    runtime: CandidateRuntimeDefinition,
    operation_id: str | None = None,
    budget_binding: tuple[ValueRef, bytes] | None = None,
) -> Annotated[
    RetrievalCandidateAtom,
    "kit:prepared-command effect_boundary=successor_program_interpreter witness=test:test_candidate_atom_binds_exact_typed_values",
]:
    if not program_id.strip():
        raise_retrieval_contract_error(ValueError, 'candidate atom identity must be nonempty')
    if project_key != budget.project_key:
        raise_retrieval_contract_error(ValueError, 'candidate atom crosses retrieval budget project')
    invocation.validate_budget(budget)
    wiring = runtime.program_atom
    invocation_bytes = canonical_json(runtime.invocation_codec.encode_payload(invocation)).encode("utf-8")
    invocation_ref = _candidate_value_ref(
        invocation_bytes,
        program_id=program_id,
        project_key=project_key,
        codec_id=wiring.payload_codec_id,
        object_type=wiring.input_type,
        value_suffix="retrieval-candidate-invocation",
    )
    if budget_binding is None:
        budget_ref, budget_bytes = _retrieval_budget_binding(runtime, budget)
    else:
        budget_ref, budget_bytes = budget_binding
        bound_budget = runtime.budget_codec.decode_payload(
            _decode_canonical_object_bytes(budget_bytes, "retrieval budget")
        )
        if (
            bound_budget != budget
            or budget_ref.object_type != RETRIEVAL_BUDGET_STATE_TYPE
            or budget_ref.codec_id != runtime.budget_codec.codec_id
            or budget_ref.project_key != project_key
            or budget_ref.byte_size != len(budget_bytes)
            or budget_ref.content_digest != sha256_hex(budget_bytes)
        ):
            raise_retrieval_contract_error(
                ValueError,
                "candidate atom budget binding differs from its immutable root budget",
            )
    operation = OperationSpec(
        operation_id=operation_id or wiring.operation_id,
        contract_ref=runtime.operation_contract.ref,
        input_refs=(budget_ref, invocation_ref),
        payload_ref=invocation_ref,
        allowed_overrides=freeze_json_object({}),
    )
    root = atom_node(
        operation,
        input_type=wiring.input_type,
        output_type=wiring.output_type,
        return_contract=_candidate_return_contract(wiring.return_contract_ref),
    )
    return RetrievalCandidateAtom(
        root=root,
        values=((budget_ref, budget_bytes), (invocation_ref, invocation_bytes)),
        invocation_ref=invocation_ref,
        budget_ref=budget_ref,
    )


@dataclass(frozen=True, slots=True)
class CandidateNativeDefinition:
    source: CandidateNativeSource
    request_codec: PayloadCodec[CandidateSearchRequest]
    registry_codec: Codec[CandidateSearchRequest]
    runtime: CandidateRuntimeDefinition

    @property
    def contribution_id(self) -> str:
        return self.source.contribution_id


@dataclass(frozen=True, slots=True)
class CandidateAssemblyContext:
    """Concrete search callable supplied by the service composition owner."""

    discover: Callable[[CandidateSearchRequest], CandidateBundle]


@dataclass(frozen=True, slots=True)
class CandidateSearchBinding:
    definition: CandidateNativeDefinition
    _discover: Callable[[CandidateSearchRequest], CandidateBundle]

    def discover(self, request: CandidateSearchRequest) -> CandidateBundle:
        effective = request
        if request.provider == "auto" and self.definition.source.default_provider != "auto":
            effective = replace(request, provider=self.definition.source.default_provider)
        return self._discover(effective)


def lower_candidate_native_source(source: CandidateNativeSource) -> CandidateNativeDefinition | Failure:
    issues: list[dict[str, str]] = []
    for field_name in ("contribution_id", "operation_id", "owner"):
        if not getattr(source, field_name).strip():
            issues.append({"code": "invalid_spec", "path": f"$.source.{field_name}", "message": "must be nonempty"})
    if source.default_provider not in SUPPORTED_PROVIDERS:
        issues.append(
            {"code": "invalid_spec", "path": "$.source.default_provider", "message": "unsupported search provider"}
        )
    if source.input_type != CANDIDATE_REQUEST_TYPE or source.output_type != CANDIDATE_BUNDLE_TYPE:
        issues.append(
            {"code": "invalid_spec", "path": "$.source.endpoints", "message": "candidate endpoint type mismatch"}
        )
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID", "candidate discovery definition invalid", {"issues": tuple(issues)}
        )
    digest = content_digest(
        {"operation_id": source.operation_id, "input": source.input_type.type_id, "output": source.output_type.type_id}
    )
    contract_ref = OperationContractRef(source.operation_id, "1", digest)
    codec = dataclass_codec(
        codec_id=f"{source.operation_id}.request.v1",
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=source.input_type.type_id,
        dto_cls=CandidateSearchRequest,
    )

    def parse_wire(value: Mapping[str, object]) -> CandidateSearchRequest | Failure:
        raw_payload = value.get("payload")
        if not isinstance(raw_payload, dict):
            return codec_failures.fail("CODEC_INVALID_FIELD", "candidate request payload must be an object")
        try:
            # The kit registry parse contract hands back an untyped wire mapping;
            # decode_payload re-validates the canonical JSON shape below.
            return codec.decode_payload(cast(CanonicalJsonObject, raw_payload))
        except (TypeError, ValueError) as exc:
            return codec_failures.fail("CODEC_INVALID_FIELD", str(exc))

    if source.operation_id == "retrieval.candidate.discover.v1":
        # The default identity is literal so the kit's source/registry scan can
        # compare it with the catalog-derived registry entry.
        registry_codec = define_codec(
            name="retrieval.candidate.discover.v1.request.v1",
            discriminant="CandidateSearchRequest.v1",
            keys=("kind", "payload"),
            parse=parse_wire,
            to_wire=lambda value: {"kind": source.input_type.type_id, "payload": codec.encode_payload(value)},
        )
    else:
        registry_codec = define_codec(
            name=codec.codec_id,
            discriminant=source.input_type.type_id,
            keys=("kind", "payload"),
            parse=parse_wire,
            to_wire=lambda value: {"kind": source.input_type.type_id, "payload": codec.encode_payload(value)},
        )
    return CandidateNativeDefinition(
        source,
        codec,
        registry_codec,
        build_retrieval_candidate_runtime_definition(owner=source.owner),
    )


def project_candidate_native_definition(definition: CandidateNativeDefinition) -> ProjectedContributionSpec:
    source = definition.source
    return ProjectedContributionSpec(
        id=source.contribution_id,
        owner=source.owner,
        objects=(
            ContributionObject(source.input_type.type_id, "ObjectType", source.owner),
            ContributionObject(source.output_type.type_id, "ObjectType", source.owner, (source.input_type.type_id,)),
            ContributionObject(
                source.operation_id, "Capability", source.owner, (source.input_type.type_id, source.output_type.type_id)
            ),
            ContributionObject(
                definition.request_codec.codec_id,
                "PayloadCodec",
                source.owner,
                (source.operation_id, source.input_type.type_id),
            ),
        ),
        codecs=(definition.registry_codec,),
    )


def assemble_candidate_native_definition(
    definition: CandidateNativeDefinition,
    context: CandidateAssemblyContext,
) -> CandidateSearchBinding:
    return CandidateSearchBinding(definition, context.discover)


def validate_candidate_native_binding(
    definition: CandidateNativeDefinition, candidate: object
) -> BindingAccepted[CandidateSearchBinding] | BindingRejected:
    if isinstance(candidate, CandidateSearchBinding) and candidate.definition == definition:
        return BindingAccepted(candidate)
    return BindingRejected((NativeBindingIssue("$.binding", "candidate search binding definition mismatch"),))


CANDIDATE_NATIVE_CONTRIBUTION_RULE = NativeContributionRule[
    CandidateNativeSource, CandidateNativeDefinition, CandidateAssemblyContext, CandidateSearchBinding
](
    lower=lower_candidate_native_source,
    project=project_candidate_native_definition,
    assemble=assemble_candidate_native_definition,
    validate_binding=validate_candidate_native_binding,
)


def compile_candidate_native_contribution(source: CandidateNativeSource):
    return compile_native_contribution(source, CANDIDATE_NATIVE_CONTRIBUTION_RULE)
