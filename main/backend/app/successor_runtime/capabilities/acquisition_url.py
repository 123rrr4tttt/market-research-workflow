"""Minimal single-URL acquisition declaration for the shared handler.

This module owns the typed endpoint identity (request/outcome DTOs), payload
codecs, and the exact operation contract.  It is not yet an installed
``PersistentOperationHandler`` consumer: the ``execute_single_url_kernel``
binding and the production worker branch are supplied by the composition owner
once the dispatcher is installed.  It never imports ``app.services``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Annotated, Literal, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.w05_capability_semantics import (
    successor_capability_contract_failures,
)

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


URL_SINGLE_URL_KIND = "acquisition.url.single_url.v1"
URL_SINGLE_URL_OWNER = "acquisition.url.single_url.v1"
URL_SINGLE_URL_REQUEST_CODEC_ID = "acquisition.url.single_url.v1.request"
URL_SINGLE_URL_OUTCOME_CODEC_ID = "acquisition.url.single_url.v1.outcome"
URL_SINGLE_URL_OBSERVATION_PROFILE = "acquisition.url.single_url.v1.observation"
URL_SINGLE_URL_LEGACY_CONTRACT_VERSION = "1.0.0"
URL_SINGLE_URL_CONTRACT_VERSION = "1.1.0"
_URL_SINGLE_URL_CONTRACT_WITNESS = (
    "test:test_single_url_program_builder_produces_exact_effect_closure"
)

URL_SINGLE_URL_REQUEST_TYPE = ObjectType(
    "UrlSingleUrlRequest.v1",
    codec_id=URL_SINGLE_URL_REQUEST_CODEC_ID,
)
URL_SINGLE_URL_OUTCOME_TYPE = ObjectType(
    "UrlSingleUrlOutcome.v1",
    codec_id=URL_SINGLE_URL_OUTCOME_CODEC_ID,
)


def _empty_object_dict() -> CanonicalJsonObject:
    return {}


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
class UrlSingleUrlOutcome:
    status: UrlSingleUrlStatus
    inserted: int
    updated: int
    skipped: int
    document_id: int | None = None
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


def _url_single_url_contract_failure(
    code: str,
    message: str,
    *,
    site: str,
) -> Failure:
    return successor_capability_contract_failures.fail(
        code,
        message,
        {
            "capability": URL_SINGLE_URL_OWNER,
            "public_exception": "ValueError",
            "public_message": message,
            "site": site,
            "witness": _URL_SINGLE_URL_CONTRACT_WITNESS,
        },
    )


def _raise_url_single_url_contract_failure(failure: Failure) -> NoReturn:
    # kit:boundary owner=acquisition.url.single_url class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.capability.contract_failure witness=test:test_single_url_program_builder_produces_exact_effect_closure
    raise ValueError(failure.message)


def _reject_url_single_url_contract(
    code: str,
    message: str,
    *,
    site: str,
) -> NoReturn:
    _raise_url_single_url_contract_failure(
        _url_single_url_contract_failure(code, message, site=site)
    )


def _build_url_single_url_contract(
    profiles: OperationProfiles,
    *,
    contract_version: str,
) -> OperationContract:
    return profiles.contract(
        kind=URL_SINGLE_URL_KIND,
        contract_version=contract_version,
        input_type=URL_SINGLE_URL_REQUEST_TYPE,
        output_type=URL_SINGLE_URL_OUTCOME_TYPE,
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
    )


def build_url_single_url_contract() -> Annotated[
    OperationContract,
    "kit:non-authoritative derived_as=view fact_source=URL_single_url_types+profiles+contract_constants witness=test:test_single_url_program_builder_produces_exact_effect_closure",
]:
    """Exact EFFECTFUL contract for one prepared single-URL acquisition."""

    return _build_url_single_url_contract(
        build_url_single_url_profiles(),
        contract_version=URL_SINGLE_URL_CONTRACT_VERSION,
    )


def _build_url_single_url_profile_version(
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
                "DOCUMENT_WRITE_FAILED",
            ),
            "retryable": False,
            "degraded_acceptable": False,
            "unknown_outcome_supported": readback_enabled,
            "readback_or_compensation": "readback" if readback_enabled else "none",
            "failure_union_ref": f"mrw.functorial-successor.failures.{URL_SINGLE_URL_KIND}.v1",
            "retryable_failure_kinds": (),
            "readback_profile_ref": (
                URL_SINGLE_URL_OBSERVATION_PROFILE if readback_enabled else None
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
                URL_SINGLE_URL_OBSERVATION_PROFILE if readback_enabled else None
            ),
            "receipt_codec_ref": URL_SINGLE_URL_OUTCOME_CODEC_ID,
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

    return _build_url_single_url_profile_version(
        version=URL_SINGLE_URL_LEGACY_CONTRACT_VERSION,
        readback_enabled=False,
    )


def build_url_single_url_profiles() -> Annotated[
    OperationProfiles,
    "kit:non-authoritative derived_as=view fact_source=URL_single_url_profile_constants+shared_operation_profile_rule witness=test:test_single_url_program_builder_produces_exact_effect_closure",
]:
    """Derive current profiles while preserving unchanged 1.0 family identities."""

    legacy = build_url_single_url_legacy_profiles()
    current = _build_url_single_url_profile_version(
        version=URL_SINGLE_URL_CONTRACT_VERSION,
        readback_enabled=True,
    )
    return OperationProfiles(
        semantic=legacy.semantic,
        effect=legacy.effect,
        resource=legacy.resource,
        failure=current.failure,
        authority=legacy.authority,
        interpreter=current.interpreter,
        observation=legacy.observation,
    )


def build_url_single_url_contracts() -> tuple[OperationContract, OperationContract]:
    """Return the legacy and current exact URL contracts in version order."""

    return build_url_single_url_legacy_contract(), build_url_single_url_contract()


def build_url_single_url_request_codec(
    contract_ref: OperationContractRef,
) -> Annotated[
    PayloadCodec[UrlSingleUrlRequest],
    "kit:non-authoritative derived_as=view fact_source=contract_ref+URL_single_url_request_schema witness=test:test_single_url_program_builder_produces_exact_effect_closure",
]:
    return dataclass_codec(
        codec_id=URL_SINGLE_URL_REQUEST_CODEC_ID,
        codec_version="1",
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
    return dataclass_codec(
        codec_id=URL_SINGLE_URL_OUTCOME_CODEC_ID,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=URL_SINGLE_URL_OUTCOME_TYPE.type_id,
        dto_cls=UrlSingleUrlOutcome,
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
    "URL_SINGLE_URL_OWNER",
    "UrlSingleUrlRequest",
    "UrlSingleUrlOutcome",
    "UrlSingleUrlProgram",
    "build_url_single_url_contract",
    "build_url_single_url_contracts",
    "build_url_single_url_legacy_contract",
    "build_url_single_url_legacy_profiles",
    "build_url_single_url_profiles",
    "build_url_single_url_request_codec",
    "build_url_single_url_outcome_codec",
    "build_url_single_url_program",
]
