"""P3 C2 canonical identity tests: shared C2.1 types are c2_1's exact classes."""

from __future__ import annotations

import inspect
import typing
import types
from collections.abc import Mapping

from app.successor_runtime.capabilities import source_resolution as resolution
from app.successor_runtime.capabilities import source_contracts as contracts
from app.successor_runtime.capabilities import source_provider_acquisition as provider_acquisition

_CANONICAL_NAMES = (
    "AuthenticatedProjectScope",
    "ChannelCatalogEntry",
    "ChannelCatalogSnapshot",
    "FrontDoorConcurrencyPlan",
    "FrontDoorConcurrencyStage",
    "FrontDoorProtocol",
    "NormalizedParamsSnapshot",
    "SourceExecutionRequest",
    "SourceItemDefinition",
    "SourceMode",
    "SourceRejection",
    "SourceTaxonomy",
    "VersionedSchema",
    "VersionedWarning",
    "RESOURCE_CEILING",
    "channel_catalog_digest",
    "project_scope_digest",
    "resource_ceiling_digest",
    "source_item_definition_content_digest",
    "source_item_definition_from_dict",
    "versioned_warning_from_legacy_string",
)


def test_shared_c2_1_canonical_names_are_c2_1_identities() -> None:
    for name in _CANONICAL_NAMES:
        assert getattr(contracts, name) is getattr(resolution, name), name


def test_c2_1_payload_and_observation_types_remain_exact() -> None:
    assert resolution.SourceResolutionPayload.__name__ == "SourceResolutionPayload"
    assert resolution.SourceResolutionObservation.__name__ == "SourceResolutionObservation"
    assert resolution.ResolvedResolution.__name__ == "ResolvedResolution"
    assert resolution.RejectedResolution.__name__ == "RejectedResolution"


def test_public_type_bindings_have_no_erased_boundaries() -> None:
    generic_codec = contracts.SourcePayloadCodecDeclaration[resolution.SourceResolutionPayload]
    assert typing.get_args(generic_codec) == (resolution.SourceResolutionPayload,)
    codec_hints = typing.get_type_hints(
        contracts.SourcePayloadCodecDeclaration,
        localns={"SourcePayloadModel": resolution.SourceResolutionPayload},
    )
    encode_args, encode_result = typing.get_args(codec_hints["encode"])
    decode_args, decode_result = typing.get_args(codec_hints["decode"])
    assert encode_args == [resolution.SourceResolutionPayload]
    assert decode_result is resolution.SourceResolutionPayload
    assert typing.get_origin(encode_result) is dict
    assert typing.get_args(encode_result)[0] is str
    assert typing.get_origin(decode_args[0]) is dict
    assert typing.get_args(decode_args[0])[0] is str

    resolver_hints = typing.get_type_hints(contracts.CredentialResolverPort.resolve)
    gateway_hints = typing.get_type_hints(contracts.ProviderEffectGateway.execute)
    for authorization in (resolver_hints["authorization"], gateway_hints["authorization"]):
        assert typing.get_origin(authorization) in (typing.Union, types.UnionType)
        union_args = typing.get_args(authorization)
        assert type(None) in union_args
        mapping = next(item for item in union_args if typing.get_origin(item) is Mapping)
        assert typing.get_args(mapping)[0] is str

    profile_hints = typing.get_type_hints(contracts.SourceOperationProfiles)
    assert tuple(profile_hints) == (
        "semantic",
        "effect",
        "resource",
        "failure",
        "authority",
        "interpreter",
        "observation",
    )
    assert "getattr" not in inspect.getsource(contracts.build_source_operation_parts)


def test_public_operation_identities_are_versioned() -> None:
    resolution_bundle = resolution.build_source_resolution_bundle()
    provider_bundle = provider_acquisition.build_source_provider_acquisition_bundle()

    assert resolution_bundle.operation.ref.contract_digest == (
        "75985813967dab3c925ca5f64b24b275f0c69546076b4c5ebc8335c8aa20c616"
    )
    assert resolution_bundle.payload_codec().codec_digest == (
        "856080fb33135677f1b433cfcfdc3dd346f9707585d54273d0346736a164b352"
    )
    assert provider_bundle.operation.ref.contract_digest == (
        "627bdba3636568d4497ca291b919ea8388bf8ec6313e6e370f51eced9d5db794"
    )
    assert provider_bundle.payload_codec().codec_digest == (
        "8790558cabebc855dd55ac207895065a2d5a1e82d9728b663b8ca2999355eea9"
    )
