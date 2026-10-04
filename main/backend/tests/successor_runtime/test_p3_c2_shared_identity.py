"""P3 C2 canonical identity tests: shared C2.1 types are c2_1's exact classes."""

from __future__ import annotations

from app.successor_runtime.capabilities import source_resolution as resolution
from app.successor_runtime.capabilities import source_contracts as contracts

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
