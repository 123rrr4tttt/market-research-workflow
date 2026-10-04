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
from typing import Annotated, Any, Literal, NoReturn, TypeAlias, get_args, get_origin

from functorial_kit import Failure

from app.successor_runtime.capabilities.checksum import (
    content_digest,
    require_hex64,
)
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
from app.successor_runtime.language.algebra import (
    FrozenJsonObject,
    FrozenJsonValue,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)

__all__ = [
    "AUTHENTICATED_PROJECT_SCOPE_TYPE",
    "CHANNEL_CATALOG_SNAPSHOT_TYPE",
    "RESOURCE_CEILING",
    "SOURCE_EXECUTION_REQUEST_SCHEMA",
    "SOURCE_EXECUTION_REQUEST_TYPE",
    "SOURCE_ITEM_DEFINITION_SCHEMA",
    "SOURCE_ITEM_DEFINITION_TYPE",
    "SOURCE_RESOLUTION_KIND",
    "SOURCE_RESOLUTION_HISTORICAL_PAYLOAD_CODEC_ID",
    "SOURCE_RESOLUTION_HISTORICAL_PAYLOAD_SCHEMA",
    "SOURCE_RESOLUTION_OPERATION_ID",
    "SOURCE_RESOLUTION_OWNER",
    "SOURCE_RESOLUTION_PAYLOAD_CODEC_ID",
    "SOURCE_RESOLUTION_PAYLOAD_SCHEMA",
    "SOURCE_RESOLUTION_PAYLOAD_TYPE",
    "SOURCE_RESOLUTION_RESULT_TYPE",
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
    "SourceResolutionCapabilityBundle",
    "SourceMode",
    "SourceRejection",
    "SourceResolutionObservation",
    "SourceResolutionPayload",
    "SourceResolutionResult",
    "SourceTaxonomy",
    "VersionedSchema",
    "VersionedWarning",
    "build_channel_catalog_snapshot",
    "build_source_resolution_bundle",
    "build_source_resolution_catalog",
    "build_source_resolution_registry",
    "deployment_catalog_digest",
    "decode_historical_source_resolution_payload",
    "observations_equal",
    "payload_from_dicts",
    "try_payload_from_dicts",
    "project_scope_digest",
    "resource_ceiling_digest",
    "source_item_definition_content_digest",
    "source_item_definition_from_dict",
    "versioned_warning_from_legacy_string",
]


from app.successor_runtime.capabilities import source_contracts as contracts

SOURCE_RESOLUTION_KIND = contracts.SOURCE_RESOLUTION_KIND
SOURCE_RESOLUTION_OWNER = contracts.SOURCE_RESOLUTION_OWNER
SOURCE_RESOLUTION_OPERATION_ID = contracts.SOURCE_RESOLUTION_OPERATION_ID
SOURCE_RESOLUTION_PAYLOAD_SCHEMA = contracts.SOURCE_RESOLUTION_PAYLOAD_SCHEMA
SOURCE_RESOLUTION_HISTORICAL_PAYLOAD_SCHEMA = contracts.SOURCE_RESOLUTION_HISTORICAL_PAYLOAD_SCHEMA
SOURCE_RESOLUTION_PAYLOAD_CODEC_ID = contracts.SOURCE_RESOLUTION_PAYLOAD_CODEC_ID
SOURCE_RESOLUTION_HISTORICAL_PAYLOAD_CODEC_ID = contracts.SOURCE_RESOLUTION_HISTORICAL_PAYLOAD_CODEC_ID
SOURCE_RESOLUTION_CATALOG_ID = contracts.SOURCE_RESOLUTION_CATALOG_ID
SOURCE_RESOLUTION_CATALOG_VERSION = "1.0.0"
SOURCE_RESOLUTION_OBSERVATION_PROFILE = "mrw.source.resolve-execution-request.observation.v2"
SOURCE_RESOLUTION_SEMANTIC_IDENTITY = "source-library.resolve-execution-request"

AUTHENTICATED_PROJECT_SCOPE_TYPE = contracts.AUTHENTICATED_PROJECT_SCOPE_TYPE
CHANNEL_CATALOG_SNAPSHOT_TYPE = contracts.CHANNEL_CATALOG_SNAPSHOT_TYPE
RESOURCE_CEILING = contracts.RESOURCE_CEILING
SOURCE_EXECUTION_REQUEST_SCHEMA = contracts.SOURCE_EXECUTION_REQUEST_SCHEMA
SOURCE_EXECUTION_REQUEST_TYPE = contracts.SOURCE_EXECUTION_REQUEST_TYPE
SOURCE_ITEM_DEFINITION_SCHEMA = contracts.SOURCE_ITEM_DEFINITION_SCHEMA
SOURCE_ITEM_DEFINITION_TYPE = contracts.SOURCE_ITEM_DEFINITION_TYPE
SOURCE_RESOLUTION_PAYLOAD_TYPE = contracts.SOURCE_RESOLUTION_PAYLOAD_TYPE
SOURCE_RESOLUTION_RESULT_TYPE = contracts.SOURCE_RESOLUTION_RESULT_TYPE
SOURCE_MODE_SCHEMA = contracts.SOURCE_MODE_SCHEMA
SOURCE_MODE_TYPE = contracts.SOURCE_MODE_TYPE
SOURCE_REJECTION_SCHEMA = contracts.SOURCE_REJECTION_SCHEMA
SOURCE_REJECTION_TYPE = contracts.SOURCE_REJECTION_TYPE
SOURCE_RESOLUTION_OBSERVATION_SCHEMA = contracts.SOURCE_RESOLUTION_OBSERVATION_SCHEMA
SOURCE_RESOLUTION_RESULT_TYPE = contracts.SOURCE_RESOLUTION_RESULT_TYPE
SOURCE_TAXONOMY_SCHEMA = contracts.SOURCE_TAXONOMY_SCHEMA
SOURCE_TAXONOMY_TYPE = contracts.SOURCE_TAXONOMY_TYPE
SOURCE_WARNING_SCHEMA = contracts.SOURCE_WARNING_SCHEMA
SOURCE_WARNING_TYPE = contracts.SOURCE_WARNING_TYPE
AuthenticatedProjectScope = contracts.AuthenticatedProjectScope
ChannelCatalogEntry = contracts.ChannelCatalogEntry
ChannelCatalogSnapshot = contracts.ChannelCatalogSnapshot
FrontDoorConcurrencyPlan = contracts.FrontDoorConcurrencyPlan
FrontDoorConcurrencyStage = contracts.FrontDoorConcurrencyStage
FrontDoorProtocol = contracts.FrontDoorProtocol
NormalizedParamsSnapshot = contracts.NormalizedParamsSnapshot
ResourceCeiling = contracts.ResourceCeiling
SourceExecutionRequest = contracts.SourceExecutionRequest
SourceItemDefinition = contracts.SourceItemDefinition
SourceMode = contracts.SourceMode
SourceRejection = contracts.SourceRejection
SourceTaxonomy = contracts.SourceTaxonomy
VersionedSchema = contracts.VersionedSchema
VersionedWarning = contracts.VersionedWarning
build_channel_catalog_snapshot = contracts.build_channel_catalog_snapshot
project_scope_digest = contracts.project_scope_digest
resource_ceiling_digest = contracts.resource_ceiling_digest
source_item_definition_content_digest = contracts.source_item_definition_content_digest
source_item_definition_from_dict = contracts.source_item_definition_from_dict
versioned_warning_from_legacy_string = contracts.versioned_warning_from_legacy_string
SOURCE_ITEM_DEFINITION_SCHEMA_REF = contracts.SOURCE_ITEM_DEFINITION_SCHEMA_REF
SOURCE_TAXONOMY_SCHEMA_REF = contracts.SOURCE_TAXONOMY_SCHEMA_REF
SOURCE_MODE_SCHEMA_REF = contracts.SOURCE_MODE_SCHEMA_REF
SOURCE_EXECUTION_REQUEST_SCHEMA_REF = contracts.SOURCE_EXECUTION_REQUEST_SCHEMA_REF
SOURCE_WARNING_SCHEMA_REF = contracts.SOURCE_WARNING_SCHEMA_REF
SOURCE_REJECTION_SCHEMA_REF = contracts.SOURCE_REJECTION_SCHEMA_REF
SOURCE_RESOLUTION_OBSERVATION_SCHEMA_REF = contracts.SOURCE_RESOLUTION_OBSERVATION_SCHEMA_REF
RESOURCE_CEILING_SCHEMA_REF = contracts.RESOURCE_CEILING_SCHEMA_REF
DEPLOYMENT_CATALOG_SCHEMA_REF = contracts.DEPLOYMENT_CATALOG_SCHEMA_REF
SOURCE_MODES = contracts.SOURCE_MODES
SOURCE_WARNING_CODES = contracts.SOURCE_WARNING_CODES
SOURCE_REJECTION_CODES = contracts.SOURCE_REJECTION_CODES
channel_catalog_digest = contracts.channel_catalog_digest
SOURCE_RESOLUTION_PAYLOAD_TYPE = contracts.SOURCE_RESOLUTION_PAYLOAD_TYPE


def _raise_programmer_defect(message: str, exception_type: type[Exception] = ValueError) -> NoReturn:
    """Lift the frozen direct-constructor ABI at one explicit boundary."""

    # kit:boundary owner=source_library_c2_1.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
    raise exception_type(message)


def _raise_legacy_compatibility(message: str, exception_type: type[Exception] = ValueError) -> NoReturn:
    """Preserve the direct codec/ABI exception at one compatibility boundary."""

    # kit:boundary owner=source_library_c2_1.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source.contract.failure witness=test:test_w06_c2_total_core_failure_lifts
    raise exception_type(message)


def _contract_failure_code(message: str) -> str:
    lowered = message.lower()
    if "digest" in lowered:
        return "digest_contract_invalid"
    if any(token in lowered for token in ("scope", "project", "schema identifier")):
        return "scope_contract_invalid"
    if any(token in lowered for token in ("channel", "catalog", "entry")):
        return "catalog_contract_invalid"
    return "schema_contract_invalid"


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
            _raise_programmer_defect("SourceResolutionObservation.schema_version is not the frozen schema")
        expected = content_digest(self._digest_payload())
        if self.observation_digest == "":
            object.__setattr__(self, "observation_digest", expected)
        else:
            require_hex64(
                self.observation_digest,
                "SourceResolutionObservation.observation_digest",
            )
            if self.observation_digest != expected:
                _raise_programmer_defect("SourceResolutionObservation.observation_digest does not match content")

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema_version,
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

    schema_version: Literal[
        "mrw.source.resolve-execution-request.payload.v2",
        "mrw.successor.source-library.c2-1.payload.v1",
    ]
    operation_kind: Literal["source_library.resolve_execution_request.v1"]
    project_scope: AuthenticatedProjectScope
    catalog: ChannelCatalogSnapshot
    item: SourceItemDefinition
    params: FrozenJsonObject
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version not in {
            SOURCE_RESOLUTION_PAYLOAD_SCHEMA,
            SOURCE_RESOLUTION_HISTORICAL_PAYLOAD_SCHEMA,
        }:
            _raise_programmer_defect(f"unsupported payload schema {self.schema_version!r}")
        if self.operation_kind != SOURCE_RESOLUTION_KIND:
            _raise_programmer_defect(f"unsupported operation kind {self.operation_kind!r}")
        object.__setattr__(self, "params", freeze_json_object(dict(self.params)))
        expected = content_digest(self, omit_fields=("payload_digest",))
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
        else:
            require_hex64(self.payload_digest, "SourceResolutionPayload.payload_digest")
            if self.payload_digest != expected:
                _raise_programmer_defect("SourceResolutionPayload.payload_digest does not match content")

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

    result = try_payload_from_dicts(
        project_key=project_key,
        registry_revision=registry_revision,
        resolved_schema=resolved_schema,
        scope_incarnation=scope_incarnation,
        scope_digest=scope_digest,
        channels=channels,
        item=item,
        params=params,
    )
    if isinstance(result, Failure):
        contracts.raise_source_contract_failure(result, ValueError)
    return result


def try_payload_from_dicts(
    *,
    project_key: str,
    registry_revision: int,
    resolved_schema: str,
    scope_incarnation: str,
    scope_digest: str,
    channels: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    item: dict[str, Any],
    params: dict[str, Any],
) -> SourceResolutionPayload | Failure:
    """Total payload construction preserving the legacy public ABI via lift."""

    try:
        scope = AuthenticatedProjectScope(
            project_key=project_key,
            registry_revision=registry_revision,
            resolved_schema=resolved_schema,
            incarnation=scope_incarnation,
            scope_digest=scope_digest,
        )
        catalog = ChannelCatalogSnapshot(
            schema_version=contracts.CHANNEL_CATALOG_SCHEMA_REF,
            revision=1,
            incarnation="channel-catalog-incarnation-1",
            digest="",
            entries=tuple(ChannelCatalogEntry(**dict(channel)) for channel in channels),
        )
        return SourceResolutionPayload(
            schema_version=SOURCE_RESOLUTION_PAYLOAD_SCHEMA,
            operation_kind=SOURCE_RESOLUTION_KIND,
            project_scope=scope,
            catalog=catalog,
            item=source_item_definition_from_dict(item),
            params=freeze_json_object(dict(params)),
            payload_digest="",
        )
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
        return contracts.source_contract_failure(
            _contract_failure_code(str(exc)),
            str(exc),
            operation="source.resolve_execution_request.payload_from_dicts",
            site="payload_from_dicts",
            owner=SOURCE_RESOLUTION_OWNER,
        )


def deployment_catalog_digest() -> str:
    """Immutable deployment catalog identity distinct from the operation catalog."""

    return content_digest(
        {
            "schema": DEPLOYMENT_CATALOG_SCHEMA_REF,
            "capability_kind": SOURCE_RESOLUTION_KIND,
            "canonical_owner": SOURCE_RESOLUTION_OWNER,
            "interpreter_family": "source.resolve-execution-request",
            "legacy_interpreter": "legacy.source_library.c2_1.resolve.v1",
            "current_interpreter": "mrw.source.resolve-execution-request.native.v2",
        }
    )


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {item.name: _plain(getattr(value, item.name)) for item in dataclasses.fields(value)}
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
        return tuple(_rebuild_value(item, args[index]) for index, item in enumerate(value))
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
        _raise_legacy_compatibility(f"{cls.__name__} codec rejected payload fields: missing={missing} extra={extra}")
    hints = typing.get_type_hints(cls)
    kwargs = {item.name: _rebuild_value(value[item.name], hints.get(item.name, item.type)) for item in fields(cls)}
    return cls(**kwargs)


def _encode_payload(value: Any) -> dict[str, Any]:
    codec_id = SOURCE_RESOLUTION_PAYLOAD_CODEC_ID
    if not isinstance(value, SourceResolutionPayload):
        _raise_legacy_compatibility(
            f"{codec_id} codec expected SourceResolutionPayload, got {type(value).__name__}",
            TypeError,
        )
    result = _plain(value)
    if not isinstance(result, dict):
        _raise_legacy_compatibility("payload codec produced a non-object encoding", TypeError)
    return result


def _decode_payload(value: dict[str, Any]) -> SourceResolutionPayload:
    if not isinstance(value, dict):
        _raise_legacy_compatibility("payload codec requires a JSON object", TypeError)
    schema_version = value.get("schema_version", SOURCE_RESOLUTION_PAYLOAD_SCHEMA)
    if schema_version == SOURCE_RESOLUTION_HISTORICAL_PAYLOAD_SCHEMA:
        _raise_legacy_compatibility(
            "historical resolution payload requires the historical decoder",
            ValueError,
        )
    return _decode_plain(SourceResolutionPayload, value)


def decode_historical_source_resolution_payload(
    value: dict[str, Any],
) -> SourceResolutionPayload:
    """Read exact historical resolution bytes without rehashing the record."""

    if not isinstance(value, dict):
        _raise_legacy_compatibility(
            "historical resolution payload codec requires a JSON object",
            TypeError,
        )
    if value.get("schema_version") != SOURCE_RESOLUTION_HISTORICAL_PAYLOAD_SCHEMA:
        _raise_legacy_compatibility(
            "historical resolution decoder requires the exact C2 payload schema",
            ValueError,
        )
    return _decode_plain(SourceResolutionPayload, value)


def _contract_declaration(
    profiles: dict[str, object],
) -> contracts.SourceSingleOperationContractDeclaration:
    return contracts.SourceSingleOperationContractDeclaration(
        kind=SOURCE_RESOLUTION_KIND,
        owner_capability_id=SOURCE_RESOLUTION_OWNER,
        input_type=SOURCE_RESOLUTION_PAYLOAD_TYPE,
        output_type=SOURCE_RESOLUTION_RESULT_TYPE,
        codec=contracts.SourcePayloadCodecDeclaration(
            codec_id=SOURCE_RESOLUTION_PAYLOAD_CODEC_ID,
            codec_version="1",
            payload_type_id=SOURCE_RESOLUTION_PAYLOAD_TYPE.type_id,
            encode=_encode_payload,
            decode=_decode_payload,
        ),
        profiles=profiles,
    )


def _semantic_profile() -> SemanticProfile:
    values = {
        "semantic_profile_id": ("mrw.source.resolve-execution-request.semantic.v2"),
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
        "effect_profile_id": ("mrw.source.resolve-execution-request.effect.v2"),
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
        "resource_profile_id": ("mrw.source.resolve-execution-request.resource.v2"),
        "resource_profile_version": "1.0.0",
        "resource_classes": ("cpu",),
        "concurrency_key": "project",
        "budget_units": "operation",
        "default_soft_limit_seconds": 30,
        "default_hard_limit_seconds": 60,
        "node_profile_selector": "any",
        "budget_ref": ("mrw.source.resolve-execution-request.budget.v2:" + RESOURCE_CEILING.ceiling_digest),
        "deadline_policy_ref": "mrw.source.resolve-execution-request.deadline.v2",
        "node_profile_requirements": ("any",),
        "units": 1,
    }
    return ResourceProfile(**values, profile_digest=content_digest(values))


def _failure_profile() -> FailureProfile:
    values = {
        "failure_profile_id": ("mrw.source.resolve-execution-request.failure.v2"),
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
        "failure_union_ref": "mrw.source.resolve-execution-request.failures.v2",
        "retryable_failure_kinds": (),
        "readback_profile_ref": None,
        "compensation_profile_ref": None,
    }
    return FailureProfile(**values, profile_digest=content_digest(values))


def _authority_profile() -> AuthorityProfile:
    values = {
        "authority_profile_id": ("mrw.source.resolve-execution-request.authority.v2"),
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": SOURCE_RESOLUTION_OWNER,
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    return AuthorityProfile(**values, profile_digest=content_digest(values))


def _interpreter_profile() -> InterpreterProfile:
    values = {
        "interpreter_profile_id": "mrw.source.resolve-execution-request.native.v2",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": (SOURCE_RESOLUTION_KIND,),
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": "mrw.source.resolve-execution-request.native",
                "version": "2.0.0",
                "donor": "item_resolver.resolve+resolver._normalize_search_params",
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.pure.v1",
        "resource_profile_ref": ("mrw.source.resolve-execution-request.resource.v2"),
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
        "observation_schema_ref": SOURCE_RESOLUTION_OBSERVATION_SCHEMA_REF,
    }
    return ObservationProfile(**values, profile_digest=content_digest(values))


@dataclass(frozen=True, slots=True)
class SourceResolutionCapabilityBundle:
    bundle_id: str
    operation: OperationContract
    codecs: tuple[PayloadCodec, ...]
    profiles: dict[str, object]

    def payload_codec(self) -> PayloadCodec:
        return self.codecs[0]


def build_source_resolution_bundle() -> Annotated[
    SourceResolutionCapabilityBundle,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=C2.1_contract_constants witness=test:test_w06_successor_authority_metadata"
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
    return SourceResolutionCapabilityBundle(
        bundle_id="mrw.source.resolve-execution-request.bundle.v2",
        operation=parts.operation,
        codecs=parts.codecs,
        profiles=parts.profiles,
    )


def build_source_resolution_catalog(
    bundle: SourceResolutionCapabilityBundle,
) -> Annotated[
    OperationContractCatalogSnapshot,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=C2.1_operation_bundle witness=test:test_w06_successor_authority_metadata"
    ],
]:
    return contracts.build_source_operation_catalog(
        contracts.SourceSingleOperationParts(
            operation=bundle.operation,
            codecs=bundle.codecs,
            profiles=bundle.profiles,
        ),
        catalog_id=SOURCE_RESOLUTION_CATALOG_ID,
        catalog_version=SOURCE_RESOLUTION_CATALOG_VERSION,
    )


def build_source_resolution_registry(
    bundle: SourceResolutionCapabilityBundle,
) -> Annotated[
    OperationContractRegistry,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=C2.1_operation_bundle witness=test:test_w06_successor_authority_metadata"
    ],
]:
    return contracts.build_source_operation_registry(
        build_source_resolution_catalog(bundle),
        bundle.operation,
    )
