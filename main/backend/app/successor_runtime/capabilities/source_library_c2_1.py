"""Frozen typed contracts for the C2.1 source-library resolve atom.

This module owns the canonical vocabulary used by the successor program and
interpreter files: object types, authenticated project scope, immutable
channel-catalog snapshot, source item/taxonomy/mode/execution-request DTOs,
versioned warning/rejection unions, payload codec and operation contract.

The module is capability-boundary only: it never imports legacy service
packages and never performs network, database, provider or credential work.
"""

from __future__ import annotations

import dataclasses
import typing
from dataclasses import dataclass, fields
from typing import Any, Literal, TypeAlias, get_args, get_origin

from app.successor_runtime.capabilities.checksum import (
    content_digest,
    require_hex64,
)
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
from app.successor_runtime.language.algebra import (
    FrozenJsonObject,
    FrozenJsonValue,
    freeze_json_object,
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
    "AUTHENTICATED_PROJECT_SCOPE_TYPE",
    "CHANNEL_CATALOG_SNAPSHOT_TYPE",
    "RESOURCE_CEILING",
    "SOURCE_EXECUTION_REQUEST_SCHEMA",
    "SOURCE_EXECUTION_REQUEST_TYPE",
    "SOURCE_ITEM_DEFINITION_SCHEMA",
    "SOURCE_ITEM_DEFINITION_TYPE",
    "SOURCE_LIBRARY_C2_1_KIND",
    "SOURCE_LIBRARY_C2_1_OPERATION_ID",
    "SOURCE_LIBRARY_C2_1_OWNER",
    "SOURCE_LIBRARY_C2_1_PAYLOAD_CODEC_ID",
    "SOURCE_LIBRARY_C2_1_PAYLOAD_SCHEMA",
    "SOURCE_LIBRARY_C2_1_PAYLOAD_TYPE",
    "SOURCE_LIBRARY_C2_1_RESULT_TYPE",
    "SOURCE_MODE_SCHEMA",
    "SOURCE_MODE_TYPE",
    "SOURCE_REJECTION_SCHEMA",
    "SOURCE_REJECTION_TYPE",
    "SOURCE_RESOLUTION_OBSERVATION_PROFILE",
    "SOURCE_RESOLUTION_OBSERVATION_SCHEMA",
    "SOURCE_RESOLUTION_RESULT_TYPE",
    "SOURCE_TAXONOMY_SCHEMA",
    "SOURCE_TAXONOMY_TYPE",
    "SOURCE_WARNING_SCHEMA",
    "SOURCE_WARNING_TYPE",
    "AuthenticatedProjectScope",
    "ChannelCatalogEntry",
    "ChannelCatalogSnapshot",
    "FrontDoorConcurrencyPlan",
    "FrontDoorConcurrencyStage",
    "FrontDoorProtocol",
    "FrozenJsonValue",
    "NormalizedParamsSnapshot",
    "RejectedResolution",
    "ResolvedResolution",
    "ResourceCeiling",
    "SourceExecutionRequest",
    "SourceItemDefinition",
    "SourceLibraryC2_1CapabilityBundle",
    "SourceMode",
    "SourceRejection",
    "SourceResolutionObservation",
    "SourceResolutionPayload",
    "SourceResolutionResult",
    "SourceTaxonomy",
    "VersionedSchema",
    "VersionedWarning",
    "build_channel_catalog_snapshot",
    "build_source_library_c2_1_bundle",
    "build_source_library_c2_1_catalog",
    "build_source_library_c2_1_registry",
    "deployment_catalog_digest",
    "observations_equal",
    "payload_from_dicts",
    "project_scope_digest",
    "resource_ceiling_digest",
    "source_item_definition_content_digest",
    "source_item_definition_from_dict",
    "versioned_warning_from_legacy_string",
]


SOURCE_LIBRARY_C2_1_KIND = "source_library.resolve_execution_request.v1"
SOURCE_LIBRARY_C2_1_OWNER = "source_library.c2_1.v1"
SOURCE_LIBRARY_C2_1_OPERATION_ID = "source_library.resolve_execution_request"
SOURCE_LIBRARY_C2_1_PAYLOAD_SCHEMA = "mrw.successor.source-library.c2-1.payload.v1"
SOURCE_LIBRARY_C2_1_PAYLOAD_CODEC_ID = (
    "mrw.successor.source-library.c2-1.payload.codec.v1"
)
SOURCE_LIBRARY_C2_1_CATALOG_ID = (
    "mrw.functorial-successor.source-library.c2-1.operations"
)
SOURCE_LIBRARY_C2_1_CATALOG_VERSION = "1.0.0"
SOURCE_RESOLUTION_OBSERVATION_PROFILE = (
    "mrw.successor.source-library.c2-1.observation.v1"
)
SOURCE_LIBRARY_C2_1_SEMANTIC_IDENTITY = "source-library.resolve-execution-request"
from app.successor_runtime.capabilities import source_library_c2_shared as _shared

AUTHENTICATED_PROJECT_SCOPE_TYPE = _shared.AUTHENTICATED_PROJECT_SCOPE_TYPE
CHANNEL_CATALOG_SNAPSHOT_TYPE = _shared.CHANNEL_CATALOG_SNAPSHOT_TYPE
RESOURCE_CEILING = _shared.RESOURCE_CEILING
SOURCE_EXECUTION_REQUEST_SCHEMA = _shared.SOURCE_EXECUTION_REQUEST_SCHEMA
SOURCE_EXECUTION_REQUEST_TYPE = _shared.SOURCE_EXECUTION_REQUEST_TYPE
SOURCE_ITEM_DEFINITION_SCHEMA = _shared.SOURCE_ITEM_DEFINITION_SCHEMA
SOURCE_ITEM_DEFINITION_TYPE = _shared.SOURCE_ITEM_DEFINITION_TYPE
SOURCE_LIBRARY_C2_1_PAYLOAD_TYPE = _shared.SOURCE_LIBRARY_C2_1_PAYLOAD_TYPE
SOURCE_LIBRARY_C2_1_RESULT_TYPE = _shared.SOURCE_LIBRARY_C2_1_RESULT_TYPE
SOURCE_MODE_SCHEMA = _shared.SOURCE_MODE_SCHEMA
SOURCE_MODE_TYPE = _shared.SOURCE_MODE_TYPE
SOURCE_REJECTION_SCHEMA = _shared.SOURCE_REJECTION_SCHEMA
SOURCE_REJECTION_TYPE = _shared.SOURCE_REJECTION_TYPE
SOURCE_RESOLUTION_OBSERVATION_SCHEMA = _shared.SOURCE_RESOLUTION_OBSERVATION_SCHEMA
SOURCE_RESOLUTION_RESULT_TYPE = _shared.SOURCE_RESOLUTION_RESULT_TYPE
SOURCE_TAXONOMY_SCHEMA = _shared.SOURCE_TAXONOMY_SCHEMA
SOURCE_TAXONOMY_TYPE = _shared.SOURCE_TAXONOMY_TYPE
SOURCE_WARNING_SCHEMA = _shared.SOURCE_WARNING_SCHEMA
SOURCE_WARNING_TYPE = _shared.SOURCE_WARNING_TYPE
AuthenticatedProjectScope = _shared.AuthenticatedProjectScope
ChannelCatalogEntry = _shared.ChannelCatalogEntry
ChannelCatalogSnapshot = _shared.ChannelCatalogSnapshot
FrontDoorConcurrencyPlan = _shared.FrontDoorConcurrencyPlan
FrontDoorConcurrencyStage = _shared.FrontDoorConcurrencyStage
FrontDoorProtocol = _shared.FrontDoorProtocol
NormalizedParamsSnapshot = _shared.NormalizedParamsSnapshot
ResourceCeiling = _shared.ResourceCeiling
SourceExecutionRequest = _shared.SourceExecutionRequest
SourceItemDefinition = _shared.SourceItemDefinition
SourceMode = _shared.SourceMode
SourceRejection = _shared.SourceRejection
SourceTaxonomy = _shared.SourceTaxonomy
VersionedSchema = _shared.VersionedSchema
VersionedWarning = _shared.VersionedWarning
build_channel_catalog_snapshot = _shared.build_channel_catalog_snapshot
project_scope_digest = _shared.project_scope_digest
resource_ceiling_digest = _shared.resource_ceiling_digest
source_item_definition_content_digest = _shared.source_item_definition_content_digest
source_item_definition_from_dict = _shared.source_item_definition_from_dict
versioned_warning_from_legacy_string = _shared.versioned_warning_from_legacy_string
SOURCE_ITEM_DEFINITION_SCHEMA_REF = _shared.SOURCE_ITEM_DEFINITION_SCHEMA_REF
SOURCE_TAXONOMY_SCHEMA_REF = _shared.SOURCE_TAXONOMY_SCHEMA_REF
SOURCE_MODE_SCHEMA_REF = _shared.SOURCE_MODE_SCHEMA_REF
SOURCE_EXECUTION_REQUEST_SCHEMA_REF = _shared.SOURCE_EXECUTION_REQUEST_SCHEMA_REF
SOURCE_WARNING_SCHEMA_REF = _shared.SOURCE_WARNING_SCHEMA_REF
SOURCE_REJECTION_SCHEMA_REF = _shared.SOURCE_REJECTION_SCHEMA_REF
SOURCE_RESOLUTION_OBSERVATION_SCHEMA_REF = (
    _shared.SOURCE_RESOLUTION_OBSERVATION_SCHEMA_REF
)
RESOURCE_CEILING_SCHEMA_REF = _shared.RESOURCE_CEILING_SCHEMA_REF
DEPLOYMENT_CATALOG_SCHEMA_REF = _shared.DEPLOYMENT_CATALOG_SCHEMA_REF
SOURCE_MODES = _shared.SOURCE_MODES
SOURCE_WARNING_CODES = _shared.SOURCE_WARNING_CODES
SOURCE_REJECTION_CODES = _shared.SOURCE_REJECTION_CODES
channel_catalog_digest = _shared.channel_catalog_digest
SOURCE_RESOLUTION_PAYLOAD_TYPE = _shared.SOURCE_RESOLUTION_PAYLOAD_TYPE


@dataclass(frozen=True, slots=True)
class SourceResolutionObservation:
    """Canonical observation over exactly the five named C2.1 dimensions."""

    observation_profile: str
    project_scope: AuthenticatedProjectScope
    item_revision: int
    item_incarnation: str
    item_content_digest: str
    catalog_revision: int
    catalog_incarnation: str
    catalog_digest: str
    normalized_params: NormalizedParamsSnapshot
    source_mode: SourceMode
    taxonomy: SourceTaxonomy
    warnings: tuple[VersionedWarning, ...]
    protocol: FrontDoorProtocol
    schema_version: str = SOURCE_RESOLUTION_OBSERVATION_SCHEMA_REF
    observation_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SOURCE_RESOLUTION_OBSERVATION_SCHEMA_REF:
            raise ValueError(
                "SourceResolutionObservation.schema_version is not the frozen schema"
            )
        expected = content_digest(self._digest_payload())
        if self.observation_digest == "":
            object.__setattr__(self, "observation_digest", expected)
        else:
            require_hex64(
                self.observation_digest,
                "SourceResolutionObservation.observation_digest",
            )
            if self.observation_digest != expected:
                raise ValueError(
                    "SourceResolutionObservation.observation_digest does not match content"
                )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": "mrw.successor.source-library.c2-1.observation.v1",
            "schema_version": self.schema_version,
            "observation_profile": self.observation_profile,
            "project_scope": self.project_scope.to_plain(),
            "item_revision": self.item_revision,
            "item_incarnation": self.item_incarnation,
            "item_content_digest": self.item_content_digest,
            "catalog_revision": self.catalog_revision,
            "catalog_incarnation": self.catalog_incarnation,
            "catalog_digest": self.catalog_digest,
            "normalized_params": self.normalized_params.to_plain(),
            "source_mode": self.source_mode.to_plain(),
            "taxonomy": self.taxonomy.to_plain(),
            "warnings": [warning.to_plain() for warning in self.warnings],
            "protocol": self.protocol.to_plain(),
        }

    def to_plain(self) -> dict[str, Any]:
        return {**self._digest_payload(), "observation_digest": self.observation_digest}


def observations_equal(
    left: SourceResolutionObservation,
    right: SourceResolutionObservation,
) -> bool:
    """Compare exact identity bindings, schema/profile and semantic dimensions."""

    return (
        left.schema_version == right.schema_version
        and left.observation_profile == right.observation_profile
        and left.project_scope == right.project_scope
        and left.item_revision == right.item_revision
        and left.item_incarnation == right.item_incarnation
        and left.item_content_digest == right.item_content_digest
        and left.catalog_revision == right.catalog_revision
        and left.catalog_incarnation == right.catalog_incarnation
        and left.catalog_digest == right.catalog_digest
        and left.normalized_params == right.normalized_params
        and left.source_mode == right.source_mode
        and left.taxonomy == right.taxonomy
        and left.warnings == right.warnings
        and left.protocol == right.protocol
    )


@dataclass(frozen=True, slots=True)
class ResolvedResolution:
    request: SourceExecutionRequest
    observation_digest: str

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": "resolved",
            "request": self.request.to_plain(),
            "observation_digest": self.observation_digest,
        }


@dataclass(frozen=True, slots=True)
class RejectedResolution:
    rejection: SourceRejection

    def to_plain(self) -> dict[str, Any]:
        return {"kind": "rejected", "rejection": self.rejection.to_plain()}


SourceResolutionResult: TypeAlias = ResolvedResolution | RejectedResolution


@dataclass(frozen=True, slots=True)
class SourceResolutionPayload:
    """Exact-bound Atom payload; raw dictionaries live only at this boundary."""

    schema_version: Literal["mrw.successor.source-library.c2-1.payload.v1"]
    operation_kind: Literal["source_library.resolve_execution_request.v1"]
    project_scope: AuthenticatedProjectScope
    catalog: ChannelCatalogSnapshot
    item: SourceItemDefinition
    params: FrozenJsonObject
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SOURCE_LIBRARY_C2_1_PAYLOAD_SCHEMA:
            raise ValueError(f"unsupported payload schema {self.schema_version!r}")
        if self.operation_kind != SOURCE_LIBRARY_C2_1_KIND:
            raise ValueError(f"unsupported operation kind {self.operation_kind!r}")
        object.__setattr__(self, "params", freeze_json_object(dict(self.params)))
        expected = content_digest(self, omit_fields=("payload_digest",))
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
        else:
            require_hex64(self.payload_digest, "SourceResolutionPayload.payload_digest")
            if self.payload_digest != expected:
                raise ValueError(
                    "SourceResolutionPayload.payload_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_kind": self.operation_kind,
            "project_scope": self.project_scope.to_plain(),
            "catalog": self.catalog.to_plain(),
            "item": self.item.to_plain(),
            "params": dict(self.params),
            "payload_digest": self.payload_digest,
        }


def payload_from_dicts(
    *,
    project_key: str,
    registry_revision: int,
    resolved_schema: str,
    scope_incarnation: str,
    scope_digest: str,
    channels: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    item: dict[str, Any],
    params: dict[str, Any],
) -> SourceResolutionPayload:
    """Build the exact-bound payload from validated plain dictionaries."""

    scope = AuthenticatedProjectScope(
        project_key=project_key,
        registry_revision=registry_revision,
        resolved_schema=resolved_schema,
        incarnation=scope_incarnation,
        scope_digest=scope_digest,
    )
    catalog = ChannelCatalogSnapshot(
        schema_version="mrw.successor.source-library.channel-catalog.v1",
        revision=1,
        incarnation="channel-catalog-incarnation-1",
        digest="",
        entries=tuple(ChannelCatalogEntry(**dict(channel)) for channel in channels),
    )
    return SourceResolutionPayload(
        schema_version=SOURCE_LIBRARY_C2_1_PAYLOAD_SCHEMA,
        operation_kind=SOURCE_LIBRARY_C2_1_KIND,
        project_scope=scope,
        catalog=catalog,
        item=source_item_definition_from_dict(item),
        params=freeze_json_object(dict(params)),
        payload_digest="",
    )


def deployment_catalog_digest() -> str:
    """Immutable deployment catalog identity distinct from the operation catalog."""

    return content_digest(
        {
            "schema": DEPLOYMENT_CATALOG_SCHEMA_REF,
            "capability_kind": SOURCE_LIBRARY_C2_1_KIND,
            "canonical_owner": SOURCE_LIBRARY_C2_1_OWNER,
            "interpreter_family": "source-library-c2-1",
            "legacy_interpreter": "legacy.source_library.c2_1.resolve.v1",
            "successor_interpreter": "successor.source_library.c2_1.resolve.v1",
        }
    )


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            item.name: _plain(getattr(value, item.name))
            for item in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _rebuild_value(value: Any, hint: Any) -> Any:
    if value is None or hint is Any:
        return value
    origin = get_origin(hint)
    if origin is tuple:
        args = get_args(hint)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_rebuild_value(item, args[0]) for item in value)
        return tuple(
            _rebuild_value(item, args[index]) for index, item in enumerate(value)
        )
    if origin is list:
        return [_rebuild_value(item, get_args(hint)[0]) for item in value]
    if dataclasses.is_dataclass(hint):
        return _decode_plain(hint, value)
    return value


def _decode_plain(cls: type[Any], value: dict[str, Any]) -> Any:
    expected = {item.name for item in fields(cls)}
    if not isinstance(value, dict) or set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise ValueError(
            f"{cls.__name__} codec rejected payload fields: "
            f"missing={missing} extra={extra}"
        )
    hints = typing.get_type_hints(cls)
    kwargs = {
        item.name: _rebuild_value(value[item.name], hints.get(item.name, item.type))
        for item in fields(cls)
    }
    return cls(**kwargs)


def _payload_codec(contract_ref: Any) -> PayloadCodec:
    codec_id = SOURCE_LIBRARY_C2_1_PAYLOAD_CODEC_ID
    codec_version = "1"

    def encode(value: Any) -> dict[str, Any]:
        if not isinstance(value, SourceResolutionPayload):
            raise TypeError(
                f"{codec_id} codec expected SourceResolutionPayload, got {type(value).__name__}"
            )
        result = _plain(value)
        if not isinstance(result, dict):
            raise TypeError("payload codec produced a non-object encoding")
        return result

    def decode(value: dict[str, Any]) -> SourceResolutionPayload:
        if not isinstance(value, dict):
            raise TypeError("payload codec requires a JSON object")
        return _decode_plain(SourceResolutionPayload, value)

    return PayloadCodec(
        codec_id=codec_id,
        codec_version=codec_version,
        contract_ref=contract_ref,
        payload_type_id=SOURCE_RESOLUTION_PAYLOAD_TYPE.type_id,
        encode=encode,
        decode=decode,
        codec_digest=codec_digest(
            codec_id=codec_id,
            codec_version=codec_version,
            contract_ref=contract_ref,
            payload_type_id=SOURCE_RESOLUTION_PAYLOAD_TYPE.type_id,
        ),
    )


def _profile_ref(
    profile_id: str, profile_version: str, digest: str
) -> ContractProfileRef:
    return ContractProfileRef(
        profile_id=profile_id,
        profile_version=profile_version,
        profile_digest=digest,
    )


def _semantic_profile() -> SemanticProfile:
    values = {
        "semantic_profile_id": ("source_library.resolve_execution_request.v1.semantic"),
        "semantic_profile_version": "1.0.0",
        "reads": (
            "AuthenticatedProjectScope.v1",
            "ChannelCatalogSnapshot.v1",
            "SourceItemDefinition.v1",
        ),
        "creates": ("SourceExecutionRequest.v1", "SourceResolutionResult.v1"),
        "creates_relations": (),
        "declared_loss": (),
        "observation_profile_ref": SOURCE_RESOLUTION_OBSERVATION_PROFILE,
    }
    return SemanticProfile(**values, profile_digest=content_digest(values))


def _effect_profile() -> EffectProfile:
    values = {
        "effect_profile_id": ("source_library.resolve_execution_request.v1.effect"),
        "effect_profile_version": "1.0.0",
        "execution_class": "PURE_TRANSFORM",
        "external_visibility": "NONE",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": ("step_boundary",),
        "internal_export_only": False,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "logical_request_id",
    }
    return EffectProfile(**values, profile_digest=content_digest(values))


def _resource_profile() -> ResourceProfile:
    values = {
        "resource_profile_id": ("source_library.resolve_execution_request.v1.resource"),
        "resource_profile_version": "1.0.0",
        "resource_classes": ("cpu",),
        "concurrency_key": "project",
        "budget_units": "operation",
        "default_soft_limit_seconds": 30,
        "default_hard_limit_seconds": 60,
        "node_profile_selector": "any",
        "budget_ref": (
            "mrw.functorial-successor.budget.c2-1.v1:" + RESOURCE_CEILING.ceiling_digest
        ),
        "deadline_policy_ref": "mrw.functorial-successor.deadline.c2-1.v1",
        "node_profile_requirements": ("any",),
        "units": 1,
    }
    return ResourceProfile(**values, profile_digest=content_digest(values))


def _failure_profile() -> FailureProfile:
    values = {
        "failure_profile_id": ("source_library.resolve_execution_request.v1.failure"),
        "failure_profile_version": "1.0.0",
        "typed_failures": (
            "INVALID_INPUT",
            "INVALID_ITEM",
            "DISABLED_ITEM",
            "INVALID_MODE",
            "FORBIDDEN_INTERNAL_ADAPTER",
            "ASSIGNMENT_BINDING_MISMATCH",
            "INTERPRETER_UNAVAILABLE",
            "RESOURCE_CEILING_EXCEEDED",
        ),
        "retryable": False,
        "degraded_acceptable": False,
        "unknown_outcome_supported": False,
        "readback_or_compensation": "none",
        "failure_union_ref": "mrw.functorial-successor.failures.c2-1.v1",
        "retryable_failure_kinds": (),
        "readback_profile_ref": None,
        "compensation_profile_ref": None,
    }
    return FailureProfile(**values, profile_digest=content_digest(values))


def _authority_profile() -> AuthorityProfile:
    values = {
        "authority_profile_id": (
            "source_library.resolve_execution_request.v1.authority"
        ),
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": SOURCE_LIBRARY_C2_1_OWNER,
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    return AuthorityProfile(**values, profile_digest=content_digest(values))


def _interpreter_profile() -> InterpreterProfile:
    values = {
        "interpreter_profile_id": "successor.source_library.c2_1.resolve.v1",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": (SOURCE_LIBRARY_C2_1_KIND,),
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": "successor-native.source_library.c2_1.resolve",
                "version": "1.0.0",
                "donor": "item_resolver.resolve+resolver._normalize_search_params",
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.pure.v1",
        "resource_profile_ref": (
            "source_library.resolve_execution_request.v1.resource"
        ),
        "credential_requirements_ref": None,
        "cancellation_profile_ref": "step_boundary",
        "idempotency_profile_ref": "logical_request_id",
        "authoritative_readback_profile_ref": None,
        "receipt_codec_ref": SOURCE_RESOLUTION_OBSERVATION_PROFILE,
    }
    return InterpreterProfile(**values, profile_digest=content_digest(values))


def _observation_profile() -> ObservationProfile:
    values = {
        "observation_profile_id": SOURCE_RESOLUTION_OBSERVATION_PROFILE,
        "observation_profile_version": "1.0.0",
        "dimensions": (
            "schema_version",
            "observation_profile",
            "project_scope",
            "item_revision",
            "item_incarnation",
            "item_content_digest",
            "catalog_revision",
            "catalog_incarnation",
            "catalog_digest",
            "normalized_params",
            "selected_source_mode",
            "taxonomy",
            "ordered_warning_codes_and_payload",
            "front_door_protocol",
            "observation_digest",
        ),
        "compatible_with_legacy": True,
        "observation_schema_ref": ("mrw.successor.source-library.c2-1.observation.v1"),
    }
    return ObservationProfile(**values, profile_digest=content_digest(values))


@dataclass(frozen=True, slots=True)
class SourceLibraryC2_1CapabilityBundle:
    bundle_id: str
    operation: OperationContract
    codecs: tuple[PayloadCodec, ...]
    profiles: dict[str, object]

    def payload_codec(self) -> PayloadCodec:
        return self.codecs[0]


def build_source_library_c2_1_bundle() -> SourceLibraryC2_1CapabilityBundle:
    semantic = _semantic_profile()
    effect = _effect_profile()
    resource = _resource_profile()
    failure = _failure_profile()
    authority = _authority_profile()
    interpreter = _interpreter_profile()
    observation = _observation_profile()
    operation = make_operation_contract(
        kind=SOURCE_LIBRARY_C2_1_KIND,
        contract_version="1.0.0",
        input_type=SOURCE_RESOLUTION_PAYLOAD_TYPE,
        output_type=SOURCE_RESOLUTION_RESULT_TYPE,
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
        owner_capability_id=SOURCE_LIBRARY_C2_1_OWNER,
    )
    codec = _payload_codec(operation.ref)
    return SourceLibraryC2_1CapabilityBundle(
        bundle_id="mrw.functorial-successor.source-library.c2-1",
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


def build_source_library_c2_1_catalog(
    bundle: SourceLibraryC2_1CapabilityBundle,
) -> OperationContractCatalogSnapshot:
    return OperationContractCatalogSnapshot(
        catalog_id=SOURCE_LIBRARY_C2_1_CATALOG_ID,
        catalog_version=SOURCE_LIBRARY_C2_1_CATALOG_VERSION,
        entries=(
            (
                bundle.operation.ref.kind,
                bundle.operation.ref.contract_version,
                bundle.operation.ref.contract_digest,
                bundle.operation.owner_capability_id,
            ),
        ),
    )


def build_source_library_c2_1_registry(
    bundle: SourceLibraryC2_1CapabilityBundle,
) -> OperationContractRegistry:
    return OperationContractRegistry(
        build_source_library_c2_1_catalog(bundle),
        (bundle.operation,),
    )
