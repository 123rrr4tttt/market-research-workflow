"""Compatibility exports for the runtime-owned pure projection contracts.

The contract and validation authority lives in ``runtime.projection_contracts``.
Existing outer-layer consumers retain this import path while they migrate; all
names below are the same class and function objects as the runtime authority.
"""

from app.successor_runtime.runtime.projection_contracts import (
    REBUILD_MODES,
    ContractViolation,
    OffsetExpectation,
    ProjectionOffset,
    ProjectionRebuild,
    ProjectionRebuildReceipt,
    ProjectorContract,
    ProjectorKey,
    ProjectorRegistry,
    RebuildMode,
    ValidationResult,
    rebuild_plan_digest,
    validate_offset_advance,
    validate_offset_expectation,
    validate_offset_snapshot,
    validate_projection_offset,
    validate_projector_contract,
    validate_projector_key,
    validate_rebuild,
    validate_rebuild_receipt,
    validate_registry,
    validate_registry_revision_advance,
)

__all__ = [
    "REBUILD_MODES",
    "ContractViolation",
    "OffsetExpectation",
    "ProjectionOffset",
    "ProjectionRebuild",
    "ProjectionRebuildReceipt",
    "ProjectorContract",
    "ProjectorKey",
    "ProjectorRegistry",
    "RebuildMode",
    "ValidationResult",
    "rebuild_plan_digest",
    "validate_offset_advance",
    "validate_offset_expectation",
    "validate_offset_snapshot",
    "validate_projection_offset",
    "validate_projector_contract",
    "validate_projector_key",
    "validate_rebuild",
    "validate_rebuild_receipt",
    "validate_registry",
    "validate_registry_revision_advance",
]
