"""Minimal single-URL acquisition declaration for the shared handler.

This module owns the typed endpoint identity (request/outcome DTOs), payload
codecs, and the exact operation contract.  It is not yet an installed
``PersistentOperationHandler`` consumer: the ``execute_single_url_kernel``
binding and the production worker branch are supplied by the composition owner
once the dispatcher is installed.  It never imports ``app.services``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from typing import Annotated, Generic, Literal, NoReturn, TypeGuard, TypeVar, cast

from functorial_kit import Failure

from app.successor_runtime.capabilities.catalog import build_operation_catalog
from app.successor_runtime.capabilities.checksum import (
    CanonicalJsonArray,
    CanonicalJsonObject,
    CanonicalJsonValue,
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.capabilities.codecs import PayloadCodec, dataclass_codec
from app.successor_runtime.capabilities.profiles import (
    OperationProfiles,
    build_operation_profiles,
)
from app.successor_runtime.language.algebra import (
    AlgebraRef,
    OperationSpec,
    ValueRef,
    freeze_json_object,
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
from app.successor_runtime.language.program import ProgramSpec, atom_node
from app.successor_runtime.research.object_types import ObjectType
from mrw_functorial_kit.core.capability_contract_failure_semantics import (
    successor_capability_contract_failures,
)

URL_SINGLE_URL_KIND = "acquisition.url.single_url.v1"
URL_SINGLE_URL_OWNER = "acquisition.url.single_url.v1"
URL_SINGLE_URL_LEGACY_REQUEST_CODEC_ID = "acquisition.url.single_url.v1.request"
URL_SINGLE_URL_LEGACY_OUTCOME_CODEC_ID = "acquisition.url.single_url.v1.outcome"
URL_SINGLE_URL_REQUEST_CODEC_ID = "acquisition.url.single_url.v2.request"
URL_SINGLE_URL_OUTCOME_CODEC_ID = "acquisition.url.single_url.v2.outcome"
URL_SINGLE_URL_LEGACY_OBSERVATION_PROFILE = "acquisition.url.single_url.v1.observation"
URL_SINGLE_URL_OBSERVATION_PROFILE = "acquisition.url.single_url.v2.observation"
URL_SINGLE_URL_LEGACY_CONTRACT_VERSION = "1.0.0"
URL_SINGLE_URL_READBACK_LEGACY_CONTRACT_VERSION = "1.1.0"
URL_SINGLE_URL_CONTRACT_VERSION = "2.0.0"
_URL_SINGLE_URL_CONTRACT_WITNESS = (
    "test:test_single_url_program_builder_produces_exact_effect_closure"
)
_URL_SINGLE_URL_REQUEST_T = TypeVar("_URL_SINGLE_URL_REQUEST_T")
_URL_SINGLE_URL_OUTCOME_T = TypeVar("_URL_SINGLE_URL_OUTCOME_T")

URL_SINGLE_URL_LEGACY_REQUEST_TYPE = ObjectType(
    "UrlSingleUrlRequest.v1",
    codec_id=URL_SINGLE_URL_LEGACY_REQUEST_CODEC_ID,
)
URL_SINGLE_URL_LEGACY_OUTCOME_TYPE = ObjectType(
    "UrlSingleUrlOutcome.v1",
    codec_id=URL_SINGLE_URL_LEGACY_OUTCOME_CODEC_ID,
)
URL_SINGLE_URL_REQUEST_TYPE = ObjectType(
    "UrlSingleUrlRequest.v2",
    codec_id=URL_SINGLE_URL_REQUEST_CODEC_ID,
)
URL_SINGLE_URL_OUTCOME_TYPE = ObjectType(
    "UrlSingleUrlOutcome.v2",
    codec_id=URL_SINGLE_URL_OUTCOME_CODEC_ID,
)


def _empty_object_dict() -> CanonicalJsonObject:
    return {}


@dataclass(frozen=True, slots=True)
class LegacyUrlSingleUrlRequest:
    url: str
    project_key: str | None = None
    query_terms: tuple[str, ...] = ()
    extra_params: CanonicalJsonObject = field(default_factory=_empty_object_dict)
    enable_extraction: bool = True
    target: CanonicalJsonObject | None = None
    context: CanonicalJsonObject | None = None


@dataclass(frozen=True, slots=True)
class UrlSingleUrlRequest:
    url: str
    project_key: str | None = None
    query_terms: tuple[str, ...] = ()
    extra_params: CanonicalJsonObject = field(default_factory=_empty_object_dict)
    enable_extraction: bool = True
    target: CanonicalJsonObject | None = None
    context: CanonicalJsonObject | None = None


UrlSingleUrlStatus = Literal[
    "completed",
    "accepted",
    "partial",
    "failed",
    "cancelled",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class LegacyUrlSingleUrlOutcome:
    status: UrlSingleUrlStatus
    inserted: int
    updated: int
    skipped: int
    document_id: int | None = None
    error: str | None = None
    task_id: str | None = None
    readback: CanonicalJsonObject = field(default_factory=_empty_object_dict)


@dataclass(frozen=True, slots=True)
class UrlSingleUrlOutcome:
    status: UrlSingleUrlStatus
    inserted: int
    updated: int
    skipped: int
    material_id: int | None = None
    error: str | None = None
    task_id: str | None = None
    readback: CanonicalJsonObject = field(default_factory=_empty_object_dict)


@dataclass(frozen=True, slots=True)
class UrlSingleUrlProgram:
    """Exact single-effect Program closure for one prepared URL."""

    program: ProgramSpec
    catalog: OperationContractCatalogSnapshot
    registry: OperationContractRegistry
    request_ref: ValueRef
    values: tuple[tuple[ValueRef, bytes], ...]
    canonical_bindings: Mapping[str, tuple[int, str]]


@dataclass(frozen=True, slots=True)
class UrlSingleUrlContractVersion(
    Generic[_URL_SINGLE_URL_REQUEST_T, _URL_SINGLE_URL_OUTCOME_T]
):
    """Exact contract/ref and request/outcome codec association for one URL version."""

    contract: OperationContract
    request_type: ObjectType
    request_codec: PayloadCodec[_URL_SINGLE_URL_REQUEST_T]
    outcome_type: ObjectType
    outcome_codec: PayloadCodec[_URL_SINGLE_URL_OUTCOME_T]
    historical: bool

    def decode_request(self, exact: bytes) -> _URL_SINGLE_URL_REQUEST_T:
        return self.request_codec.decode_payload(
            _exact_payload_object(exact, payload_kind="request")
        )

    def decode_outcome(self, exact: bytes) -> _URL_SINGLE_URL_OUTCOME_T:
        return self.outcome_codec.decode_payload(
            _exact_payload_object(exact, payload_kind="output")
        )


def _canonical_json_value(value: object) -> CanonicalJsonValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if _is_object_list(value):
        return [_canonical_json_value(item) for item in value]
    if _is_string_key_dict(value):
        return {key: _canonical_json_value(item) for key, item in value.items()}
    _reject_url_single_url_contract(
        "codec_contract_invalid",
        "runtime output is not canonical JSON",
        site="_canonical_json_value.value",
        public_exception="TypeError",
    )


def _exact_payload_object(exact: bytes, *, payload_kind: str) -> CanonicalJsonObject:
    raw_value: object = json.loads(exact)
    canonical_root = _canonical_json_value(raw_value)
    if not _is_string_key_dict(canonical_root):
        _reject_url_single_url_contract(
            "codec_contract_invalid",
            f"URL runtime {payload_kind} root is not an object",
            site="_exact_payload_object.canonical_root",
            public_exception="TypeError",
        )
    return canonical_root


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_string_key_dict(
    value: object,
) -> TypeGuard[dict[str, CanonicalJsonValue]]:
    if not isinstance(value, dict):
        return False
    mapping = cast(Mapping[object, object], value)
    return all(isinstance(key, str) for key in mapping)


def _url_single_url_contract_failure(
    code: str,
    message: str,
    *,
    site: str,
    public_exception: Literal["TypeError", "ValueError"] = "ValueError",
) -> Failure:
    return successor_capability_contract_failures.fail(
        code,
        message,
        {
            "capability": URL_SINGLE_URL_OWNER,
            "public_exception": public_exception,
            "public_message": message,
            "site": site,
            "witness": _URL_SINGLE_URL_CONTRACT_WITNESS,
        },
    )


def _raise_url_single_url_contract_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    public_message = str(context.get("public_message") or failure.message)
    if context.get("public_exception") == "TypeError":
        # kit:boundary owner=acquisition.url.single_url class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.capability.contract_failure witness=test:test_single_url_program_builder_produces_exact_effect_closure
        raise TypeError(public_message)
    # kit:boundary owner=acquisition.url.single_url class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.capability.contract_failure witness=test:test_single_url_program_builder_produces_exact_effect_closure
    raise ValueError(public_message)


def _reject_url_single_url_contract(
    code: str,
    message: str,
    *,
    site: str,
    public_exception: Literal["TypeError", "ValueError"] = "ValueError",
) -> NoReturn:
    _raise_url_single_url_contract_failure(
        _url_single_url_contract_failure(
            code,
            message,
            site=site,
            public_exception=public_exception,
        )
    )


def _build_url_single_url_contract(
    profiles: OperationProfiles,
    *,
    contract_version: str,
    input_type: ObjectType,
    output_type: ObjectType,
) -> OperationContract:
    return profiles.contract(
        kind=URL_SINGLE_URL_KIND,
        contract_version=contract_version,
        input_type=input_type,
        output_type=output_type,
        return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=URL_SINGLE_URL_OWNER,
    )


def build_url_single_url_legacy_contract() -> Annotated[
    OperationContract,
    "kit:non-authoritative derived_as=view "
    "fact_source=URL_single_url_legacy_profiles+contract_constants "
    "witness=test:test_single_url_contract_versions_preserve_legacy_identity",
]:
    """Rebuild the frozen 1.0 contract used by already-compiled Programs."""

    return _build_url_single_url_contract(
        build_url_single_url_legacy_profiles(),
        contract_version=URL_SINGLE_URL_LEGACY_CONTRACT_VERSION,
        input_type=URL_SINGLE_URL_LEGACY_REQUEST_TYPE,
        output_type=URL_SINGLE_URL_LEGACY_OUTCOME_TYPE,
    )


def build_url_single_url_readback_legacy_contract() -> Annotated[
    OperationContract,
    "kit:non-authoritative derived_as=view "
    "fact_source=URL_single_url_1_1_profiles+frozen_v1_types "
    "witness=test:test_single_url_contract_versions_preserve_legacy_identity",
]:
    """Rebuild the frozen 1.1 readback contract without current v2 constants."""

    return _build_url_single_url_contract(
        build_url_single_url_readback_legacy_profiles(),
        contract_version=URL_SINGLE_URL_READBACK_LEGACY_CONTRACT_VERSION,
        input_type=URL_SINGLE_URL_LEGACY_REQUEST_TYPE,
        output_type=URL_SINGLE_URL_LEGACY_OUTCOME_TYPE,
    )


def build_url_single_url_contract() -> Annotated[
    OperationContract,
    "kit:non-authoritative derived_as=view fact_source=URL_single_url_types+profiles+contract_constants witness=test:test_single_url_program_builder_produces_exact_effect_closure",
]:
    """Exact EFFECTFUL contract for one prepared single-URL acquisition."""

    return _build_url_single_url_contract(
        build_url_single_url_profiles(),
        contract_version=URL_SINGLE_URL_CONTRACT_VERSION,
        input_type=URL_SINGLE_URL_REQUEST_TYPE,
        output_type=URL_SINGLE_URL_OUTCOME_TYPE,
    )


def _build_url_single_url_legacy_profile_version(
    *,
    version: str,
    readback_enabled: bool,
) -> OperationProfiles:
    interpreter_id = f"{URL_SINGLE_URL_KIND}.interpreter"
    return build_operation_profiles(
        identity=URL_SINGLE_URL_KIND,
        version=version,
        semantic={
            "reads": ("UrlSingleUrlRequest.v1",),
            "creates": ("UrlSingleUrlOutcome.v1",),
            "creates_relations": (),
            "declared_loss": (),
            "observation_profile_ref": URL_SINGLE_URL_LEGACY_OBSERVATION_PROFILE,
        },
        effect={
            "execution_class": "EFFECTFUL",
            "external_visibility": "INTERNAL_ONLY",
            "network_required": True,
            "irreversible": True,
            "cancellation_points": ("element_boundary", "step_boundary"),
            "internal_export_only": True,
            "human_approval_required": False,
            "external_acquisition": False,
            "idempotency_profile_ref": "logical_request_id",
        },
        resource={
            "resource_classes": ("NETWORK_IO",),
            "concurrency_key": "project:url",
            "budget_units": "element",
            "default_soft_limit_seconds": 120,
            "default_hard_limit_seconds": 300,
            "node_profile_selector": "any",
            "budget_ref": "mrw.acquisition.batch.budget.v2",
            "deadline_policy_ref": "mrw.acquisition.batch.deadline-policy.v2",
            "node_profile_requirements": ("any",),
            "units": 1,
        },
        failure={
            "typed_failures": (
                "INVALID_INPUT",
                "URL_POOL_EXECUTION_FAILED",
                "DOCUMENT_WRITE_FAILED",
            ),
            "retryable": False,
            "degraded_acceptable": False,
            "unknown_outcome_supported": readback_enabled,
            "readback_or_compensation": "readback" if readback_enabled else "none",
            "failure_union_ref": f"mrw.functorial-successor.failures.{URL_SINGLE_URL_KIND}.v1",
            "retryable_failure_kinds": (),
            "readback_profile_ref": (
                URL_SINGLE_URL_LEGACY_OBSERVATION_PROFILE if readback_enabled else None
            ),
            "compensation_profile_ref": None,
        },
        authority={
            "grant_scopes": ("project",),
            "approval_required": False,
            "approval_kinds": (),
            "credential_refs": (),
            "canonical_owner": URL_SINGLE_URL_OWNER,
            "revalidation_points": ("claim_time",),
            "authority_epoch": 1,
        },
        interpreter={
            "supported_contract_kinds": (URL_SINGLE_URL_KIND,),
            "supported_contract_refs": (),
            "dependency_digest": content_digest(
                {
                    "interpreter": interpreter_id,
                    "version": version,
                    "donor": "ingest.url_pool.execute_single_url_kernel",
                }
            ),
            "security_profile_ref": "mrw.functorial-successor.security.pure.v1",
            "resource_profile_ref": f"{URL_SINGLE_URL_KIND}.resource",
            "credential_requirements_ref": None,
            "cancellation_profile_ref": "element_boundary",
            "idempotency_profile_ref": "logical_request_id",
            "authoritative_readback_profile_ref": (
                URL_SINGLE_URL_LEGACY_OBSERVATION_PROFILE if readback_enabled else None
            ),
            "receipt_codec_ref": URL_SINGLE_URL_LEGACY_OUTCOME_CODEC_ID,
        },
        observation={
            "dimensions": ("url", "status", "inserted", "updated", "skipped", "document_id"),
            "compatible_with_legacy": True,
            "observation_schema_ref": "mrw.acquisition.url.single_url.observation.v1",
        },
    )


def build_url_single_url_legacy_profiles() -> Annotated[
    OperationProfiles,
    "kit:non-authoritative derived_as=view "
    "fact_source=URL_single_url_1_0_profile_constants+shared_operation_profile_rule "
    "witness=test:test_single_url_contract_versions_preserve_legacy_identity",
]:
    """Rebuild the exact 1.0 profiles referenced by persisted assignments."""

    return _build_url_single_url_legacy_profile_version(
        version=URL_SINGLE_URL_LEGACY_CONTRACT_VERSION,
        readback_enabled=False,
    )


def build_url_single_url_readback_legacy_profiles() -> Annotated[
    OperationProfiles,
    "kit:non-authoritative derived_as=view "
    "fact_source=frozen_URL_single_url_1_0_profiles+frozen_1_1_failure_and_interpreter "
    "witness=test:test_single_url_contract_versions_preserve_legacy_identity",
]:
    """Rebuild the exact frozen 1.1 profile family for historical reads."""

    legacy = build_url_single_url_legacy_profiles()
    readback_legacy = _build_url_single_url_legacy_profile_version(
        version=URL_SINGLE_URL_READBACK_LEGACY_CONTRACT_VERSION,
        readback_enabled=True,
    )
    return OperationProfiles(
        semantic=legacy.semantic,
        effect=legacy.effect,
        resource=legacy.resource,
        failure=readback_legacy.failure,
        authority=legacy.authority,
        interpreter=readback_legacy.interpreter,
        observation=legacy.observation,
    )


def build_url_single_url_profiles() -> Annotated[
    OperationProfiles,
    "kit:non-authoritative derived_as=view "
    "fact_source=URL_single_url_v2_profile_constants+shared_operation_profile_rule "
    "witness=test:test_single_url_program_builder_produces_exact_effect_closure",
]:
    """Derive the current material-native 2.0 profile family."""

    interpreter_id = f"{URL_SINGLE_URL_KIND}.interpreter"
    return build_operation_profiles(
        identity=URL_SINGLE_URL_KIND,
        version=URL_SINGLE_URL_CONTRACT_VERSION,
        semantic={
            "reads": ("UrlSingleUrlRequest.v2",),
            "creates": ("UrlSingleUrlOutcome.v2",),
            "creates_relations": (),
            "declared_loss": (),
            "observation_profile_ref": URL_SINGLE_URL_OBSERVATION_PROFILE,
        },
        effect={
            "execution_class": "EFFECTFUL",
            "external_visibility": "INTERNAL_ONLY",
            "network_required": True,
            "irreversible": True,
            "cancellation_points": ("element_boundary", "step_boundary"),
            "internal_export_only": True,
            "human_approval_required": False,
            "external_acquisition": False,
            "idempotency_profile_ref": "logical_request_id",
        },
        resource={
            "resource_classes": ("NETWORK_IO",),
            "concurrency_key": "project:url",
            "budget_units": "element",
            "default_soft_limit_seconds": 120,
            "default_hard_limit_seconds": 300,
            "node_profile_selector": "any",
            "budget_ref": "mrw.acquisition.batch.budget.v2",
            "deadline_policy_ref": "mrw.acquisition.batch.deadline-policy.v2",
            "node_profile_requirements": ("any",),
            "units": 1,
        },
        failure={
            "typed_failures": (
                "INVALID_INPUT",
                "URL_POOL_EXECUTION_FAILED",
                "MATERIAL_WRITE_FAILED",
            ),
            "retryable": False,
            "degraded_acceptable": False,
            "unknown_outcome_supported": True,
            "readback_or_compensation": "readback",
            "failure_union_ref": f"mrw.functorial-successor.failures.{URL_SINGLE_URL_KIND}.v2",
            "retryable_failure_kinds": (),
            "readback_profile_ref": URL_SINGLE_URL_OBSERVATION_PROFILE,
            "compensation_profile_ref": None,
        },
        authority={
            "grant_scopes": ("project",),
            "approval_required": False,
            "approval_kinds": (),
            "credential_refs": (),
            "canonical_owner": URL_SINGLE_URL_OWNER,
            "revalidation_points": ("claim_time",),
            "authority_epoch": 1,
        },
        interpreter={
            "supported_contract_kinds": (URL_SINGLE_URL_KIND,),
            "supported_contract_refs": (),
            "dependency_digest": content_digest(
                {
                    "interpreter": interpreter_id,
                    "version": URL_SINGLE_URL_CONTRACT_VERSION,
                    "donor": "ingest.url_pool.execute_single_url_kernel",
                }
            ),
            "security_profile_ref": "mrw.functorial-successor.security.pure.v1",
            "resource_profile_ref": f"{URL_SINGLE_URL_KIND}.resource",
            "credential_requirements_ref": None,
            "cancellation_profile_ref": "element_boundary",
            "idempotency_profile_ref": "logical_request_id",
            "authoritative_readback_profile_ref": URL_SINGLE_URL_OBSERVATION_PROFILE,
            "receipt_codec_ref": URL_SINGLE_URL_OUTCOME_CODEC_ID,
        },
        observation={
            "dimensions": ("url", "status", "inserted", "updated", "skipped", "material_id"),
            "compatible_with_legacy": False,
            "observation_schema_ref": "mrw.acquisition.url.single_url.observation.v2",
        },
    )


def _build_url_single_url_legacy_contract_version(
    contract: OperationContract,
) -> UrlSingleUrlContractVersion[LegacyUrlSingleUrlRequest, LegacyUrlSingleUrlOutcome]:
    return UrlSingleUrlContractVersion(
        contract=contract,
        request_type=URL_SINGLE_URL_LEGACY_REQUEST_TYPE,
        request_codec=build_url_single_url_legacy_request_codec(contract.ref),
        outcome_type=URL_SINGLE_URL_LEGACY_OUTCOME_TYPE,
        outcome_codec=build_url_single_url_legacy_outcome_codec(contract.ref),
        historical=True,
    )


def _build_url_single_url_current_contract_version(
    contract: OperationContract,
) -> UrlSingleUrlContractVersion[UrlSingleUrlRequest, UrlSingleUrlOutcome]:
    return UrlSingleUrlContractVersion(
        contract=contract,
        request_type=URL_SINGLE_URL_REQUEST_TYPE,
        request_codec=build_url_single_url_request_codec(contract.ref),
        outcome_type=URL_SINGLE_URL_OUTCOME_TYPE,
        outcome_codec=build_url_single_url_outcome_codec(contract.ref),
        historical=False,
    )


def build_url_single_url_contract_versions() -> Annotated[
    tuple[
        UrlSingleUrlContractVersion[LegacyUrlSingleUrlRequest, LegacyUrlSingleUrlOutcome],
        UrlSingleUrlContractVersion[LegacyUrlSingleUrlRequest, LegacyUrlSingleUrlOutcome],
        UrlSingleUrlContractVersion[UrlSingleUrlRequest, UrlSingleUrlOutcome],
    ],
    "kit:non-authoritative derived_as=view "
    "fact_source=frozen_URL_single_url_contracts+exact_request_outcome_codecs "
    "witness=test:test_single_url_contract_versions_preserve_legacy_identity",
]:
    """Return exact v1.0/v1.1/v2.0 contract and codec associations in version order."""

    return (
        _build_url_single_url_legacy_contract_version(
            build_url_single_url_legacy_contract()
        ),
        _build_url_single_url_legacy_contract_version(
            build_url_single_url_readback_legacy_contract()
        ),
        _build_url_single_url_current_contract_version(
            build_url_single_url_contract()
        ),
    )


def build_url_single_url_contract_version(
    contract_ref: OperationContractRef,
) -> Annotated[
    (
        UrlSingleUrlContractVersion[
            LegacyUrlSingleUrlRequest, LegacyUrlSingleUrlOutcome
        ]
        | UrlSingleUrlContractVersion[UrlSingleUrlRequest, UrlSingleUrlOutcome]
    ),
    "kit:non-authoritative derived_as=view "
    "fact_source=URL_single_url_contract_versions+exact_contract_ref "
    "witness=test:test_single_url_contract_versions_preserve_legacy_identity",
]:
    """Resolve one exact contract ref to its native request/outcome codecs."""

    for version in build_url_single_url_contract_versions():
        if contract_ref == version.contract.ref:
            return version
    _reject_url_single_url_contract(
        "codec_contract_invalid",
        "URL runtime input has an unknown exact operation contract ref",
        site="build_url_single_url_contract_version.contract_ref",
    )


def build_url_single_url_contracts() -> Annotated[
    tuple[OperationContract, OperationContract, OperationContract],
    "kit:non-authoritative derived_as=view "
    "fact_source=URL_single_url_contract_versions "
    "witness=test:test_single_url_contract_versions_preserve_legacy_identity",
]:
    """Return both frozen historical contracts and current v2 in version order."""

    versions = build_url_single_url_contract_versions()
    return (
        versions[0].contract,
        versions[1].contract,
        versions[2].contract,
    )


def build_url_single_url_request_codec(
    contract_ref: OperationContractRef,
) -> Annotated[
    PayloadCodec[UrlSingleUrlRequest],
    "kit:non-authoritative derived_as=view fact_source=contract_ref+URL_single_url_request_schema witness=test:test_single_url_program_builder_produces_exact_effect_closure",
]:
    if contract_ref != build_url_single_url_contract().ref:
        _reject_url_single_url_contract(
            "codec_contract_invalid",
            "URL single-URL v2 request codec requires the exact current contract ref",
            site="build_url_single_url_request_codec.contract_ref",
        )
    return dataclass_codec(
        codec_id=URL_SINGLE_URL_REQUEST_CODEC_ID,
        codec_version="2",
        contract_ref=contract_ref,
        payload_type_id=URL_SINGLE_URL_REQUEST_TYPE.type_id,
        dto_cls=UrlSingleUrlRequest,
    )


def build_url_single_url_outcome_codec(
    contract_ref: OperationContractRef,
) -> Annotated[
    PayloadCodec[UrlSingleUrlOutcome],
    "kit:non-authoritative derived_as=view fact_source=contract_ref+URL_single_url_outcome_schema witness=test:test_single_url_program_builder_produces_exact_effect_closure",
]:
    if contract_ref != build_url_single_url_contract().ref:
        _reject_url_single_url_contract(
            "codec_contract_invalid",
            "URL single-URL v2 outcome codec requires the exact current contract ref",
            site="build_url_single_url_outcome_codec.contract_ref",
        )
    return dataclass_codec(
        codec_id=URL_SINGLE_URL_OUTCOME_CODEC_ID,
        codec_version="2",
        contract_ref=contract_ref,
        payload_type_id=URL_SINGLE_URL_OUTCOME_TYPE.type_id,
        dto_cls=UrlSingleUrlOutcome,
    )


def build_url_single_url_legacy_request_codec(
    contract_ref: OperationContractRef,
) -> Annotated[
    PayloadCodec[LegacyUrlSingleUrlRequest],
    "kit:non-authoritative derived_as=view fact_source=exact_legacy_contract_ref+frozen_request_schema "
    "witness=test:test_single_url_contract_versions_preserve_legacy_identity",
]:
    """Build the exact v1 request reader for a frozen 1.0/1.1 contract ref."""

    if contract_ref not in {
        build_url_single_url_legacy_contract().ref,
        build_url_single_url_readback_legacy_contract().ref,
    }:
        _reject_url_single_url_contract(
            "codec_contract_invalid",
            "URL single-URL v1 request codec requires an exact legacy contract ref",
            site="build_url_single_url_legacy_request_codec.contract_ref",
        )
    return dataclass_codec(
        codec_id=URL_SINGLE_URL_LEGACY_REQUEST_CODEC_ID,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=URL_SINGLE_URL_LEGACY_REQUEST_TYPE.type_id,
        dto_cls=LegacyUrlSingleUrlRequest,
    )


def build_url_single_url_legacy_outcome_codec(
    contract_ref: OperationContractRef,
) -> Annotated[
    PayloadCodec[LegacyUrlSingleUrlOutcome],
    "kit:non-authoritative derived_as=view fact_source=exact_legacy_contract_ref+frozen_outcome_schema "
    "witness=test:test_single_url_contract_versions_preserve_legacy_identity",
]:
    """Build the exact v1 outcome reader for a frozen 1.0/1.1 contract ref."""

    if contract_ref not in {
        build_url_single_url_legacy_contract().ref,
        build_url_single_url_readback_legacy_contract().ref,
    }:
        _reject_url_single_url_contract(
            "codec_contract_invalid",
            "URL single-URL v1 outcome codec requires an exact legacy contract ref",
            site="build_url_single_url_legacy_outcome_codec.contract_ref",
        )
    return dataclass_codec(
        codec_id=URL_SINGLE_URL_LEGACY_OUTCOME_CODEC_ID,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=URL_SINGLE_URL_LEGACY_OUTCOME_TYPE.type_id,
        dto_cls=LegacyUrlSingleUrlOutcome,
    )


def build_url_single_url_program(
    *,
    request: UrlSingleUrlRequest,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    incarnation: str,
    extra_bound_inputs: tuple[tuple[ValueRef, bytes], ...] = (),
) -> Annotated[
    UrlSingleUrlProgram,
    "kit:non-authoritative derived_as=program fact_source=validated_request+project_scope+extra_bound_inputs+single_URL_contract witness=test:test_single_url_program_builder_produces_exact_effect_closure",
]:
    """Build and compile one durable single-URL acquisition Program."""

    normalized_program_id = str(program_id or "").strip()
    normalized_project_key = str(project_key or "").strip()
    if not normalized_program_id:
        _reject_url_single_url_contract(
            "schema_contract_invalid",
            "URL single-URL program requires program_id",
            site="build_url_single_url_program.program_id",
        )
    if not normalized_project_key:
        _reject_url_single_url_contract(
            "schema_contract_invalid",
            "URL single-URL program requires project_key",
            site="build_url_single_url_program.project_key",
        )
    if request.project_key != normalized_project_key:
        _reject_url_single_url_contract(
            "scope_contract_invalid",
            "URL single-URL request crosses the program project scope",
            site="build_url_single_url_program.request_project_key",
        )
    if not request.url.strip() or not request.url.strip().startswith(("http://", "https://")):
        _reject_url_single_url_contract(
            "schema_contract_invalid",
            "URL single-URL program requires an http(s) URL",
            site="build_url_single_url_program.url",
        )
    if not str(incarnation or "").strip():
        _reject_url_single_url_contract(
            "schema_contract_invalid",
            "URL single-URL program requires incarnation",
            site="build_url_single_url_program.incarnation",
        )

    contract = build_url_single_url_contract()
    catalog = build_operation_catalog(
        (contract,),
        catalog_id="mrw.acquisition.url.single-url.operations",
        catalog_version="1",
    )
    registry = OperationContractRegistry(catalog=catalog, contracts=(contract,))
    request_codec = build_url_single_url_request_codec(contract.ref)
    request_bytes = canonical_json(request_codec.encode_payload(request)).encode("utf-8")
    value_id = f"{normalized_program_id}:payload:url-single-url"
    provenance_digest = content_digest(
        {
            "schema": "mrw.acquisition.url.single-url.payload-provenance.v1",
            "program_id": normalized_program_id,
            "project_key": normalized_project_key,
            "content_digest": sha256_hex(request_bytes),
        }
    )
    request_ref = ValueRef(
        value_id=value_id,
        project_key=normalized_project_key,
        object_type=URL_SINGLE_URL_REQUEST_TYPE,
        codec_id=URL_SINGLE_URL_REQUEST_CODEC_ID,
        content_digest=sha256_hex(request_bytes),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(request_bytes),
        provenance_digest=provenance_digest,
    )
    seen_value_ids = {request_ref.value_id}
    validated_extra_inputs: list[tuple[ValueRef, bytes]] = []
    for ref, exact_bytes in extra_bound_inputs:
        if ref.project_key != normalized_project_key:
            _reject_url_single_url_contract(
                "scope_contract_invalid",
                "URL single-URL extra bound input crosses the program project scope",
                site="build_url_single_url_program.extra_bound_inputs.project_key",
            )
        if ref.value_id in seen_value_ids:
            _reject_url_single_url_contract(
                "program_binding_invalid",
                "URL single-URL bound inputs repeat a value_id",
                site="build_url_single_url_program.extra_bound_inputs.value_id",
            )
        if ref.byte_size != len(exact_bytes) or ref.content_digest != sha256_hex(exact_bytes):
            _reject_url_single_url_contract(
                "digest_contract_invalid",
                "URL single-URL bound input bytes differ from ValueRef",
                site="build_url_single_url_program.extra_bound_inputs.bytes",
            )
        seen_value_ids.add(ref.value_id)
        validated_extra_inputs.append((ref, exact_bytes))
    exact_extra_inputs = tuple(validated_extra_inputs)
    operation = OperationSpec(
        operation_id=URL_SINGLE_URL_KIND,
        contract_ref=contract.ref,
        input_refs=tuple(ref for ref, _ in exact_extra_inputs) + (request_ref,),
        payload_ref=request_ref,
        allowed_overrides=freeze_json_object({}),
    )
    root = atom_node(
        operation,
        input_type=URL_SINGLE_URL_REQUEST_TYPE,
        output_type=URL_SINGLE_URL_OUTCOME_TYPE,
    )
    metadata = freeze_json_object(
        {
            "schema": "mrw.acquisition.url.single-url.program-metadata.v1",
            "operation_kind": URL_SINGLE_URL_KIND,
            "project_registry_revision": project_registry_revision,
            "project_scope_digest": project_scope_digest,
            "payload_value_id": request_ref.value_id,
            "payload_storage_ref": request_ref.storage_ref,
            "payload_content_digest": request_ref.content_digest,
            "payload_provenance_digest": request_ref.provenance_digest,
            "canonical_owner": URL_SINGLE_URL_OWNER,
        }
    )
    program = ProgramSpec(
        program_id=normalized_program_id,
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=normalized_project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity=URL_SINGLE_URL_KIND,
        input_type=URL_SINGLE_URL_REQUEST_TYPE,
        output_type=URL_SINGLE_URL_OUTCOME_TYPE,
        root=root,
        algebra_refs=(AlgebraRef(algebra_id="mrw.successor.language.algebra", algebra_version="1"),),
        transform_refs=(),
        observation_profile=URL_SINGLE_URL_OBSERVATION_PROFILE,
        metadata=metadata,
        program_digest="",
    ).with_digest()

    from app.successor_runtime.language.compile import compile_program

    plan = compile_program(program, catalog, operation_contracts=registry)
    effects = tuple(step for step in plan.ordered_steps if step.step_kind == "EFFECT")
    if len(effects) != 1:
        _reject_url_single_url_contract(
            "program_binding_invalid",
            "URL single-URL Program must compile to one effect",
            site="build_url_single_url_program.compiled_effects",
        )
    return UrlSingleUrlProgram(
        program=program,
        catalog=catalog,
        registry=registry,
        request_ref=request_ref,
        values=exact_extra_inputs + ((request_ref, request_bytes),),
        canonical_bindings={effects[0].step_id: (0, incarnation)},
    )


__all__ = [
    "CanonicalJsonArray",
    "CanonicalJsonObject",
    "CanonicalJsonValue",
    "URL_SINGLE_URL_KIND",
    "URL_SINGLE_URL_CONTRACT_VERSION",
    "URL_SINGLE_URL_LEGACY_CONTRACT_VERSION",
    "URL_SINGLE_URL_READBACK_LEGACY_CONTRACT_VERSION",
    "URL_SINGLE_URL_OWNER",
    "URL_SINGLE_URL_LEGACY_REQUEST_TYPE",
    "URL_SINGLE_URL_LEGACY_OUTCOME_TYPE",
    "URL_SINGLE_URL_REQUEST_TYPE",
    "URL_SINGLE_URL_OUTCOME_TYPE",
    "LegacyUrlSingleUrlRequest",
    "LegacyUrlSingleUrlOutcome",
    "UrlSingleUrlRequest",
    "UrlSingleUrlOutcome",
    "UrlSingleUrlProgram",
    "UrlSingleUrlContractVersion",
    "build_url_single_url_contract_version",
    "build_url_single_url_contract_versions",
    "build_url_single_url_contract",
    "build_url_single_url_contracts",
    "build_url_single_url_legacy_contract",
    "build_url_single_url_legacy_profiles",
    "build_url_single_url_readback_legacy_contract",
    "build_url_single_url_readback_legacy_profiles",
    "build_url_single_url_profiles",
    "build_url_single_url_legacy_request_codec",
    "build_url_single_url_legacy_outcome_codec",
    "build_url_single_url_request_codec",
    "build_url_single_url_outcome_codec",
    "build_url_single_url_program",
]
