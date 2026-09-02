"""Pure projector registry, exact offset and rebuild contracts (P4 C9).

Family-local substrate scaffold only.  ``ProjectorKey`` mirrors the field
surface of the durable ``ProjectionOffsetKey`` (projector id/version, source
kind/ref/incarnation) so the pure contract can be validated against the
PostgreSQL CAS repository without importing store code.  Offsets carry exact
source revision/digest, projection generation, offset revision and CAS
expectations; ABA, stale source and rebuild are first-class failure modes.
No database, network, provider or runtime execution code is imported.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from app.successor_runtime.runtime.ports import ProjectScopeRef

REBUILD_MODES: tuple[str, ...] = ("FULL", "INCREMENTAL")
RebuildMode = Literal["FULL", "INCREMENTAL"]
_HEX_DIGITS = frozenset("0123456789abcdef")

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


@dataclass(frozen=True)
class ProjectorKey:
    """Exact projector/source identity matching ``ProjectionOffsetKey``."""

    projector_id: str
    projector_version: str
    source_kind: str
    source_ref: str
    source_incarnation: str


@dataclass(frozen=True)
class ProjectorContract:
    """Read-only projector description bound to one exact source identity."""

    key: ProjectorKey
    projection_id: str
    projection_schema_ref: str
    declared_loss: tuple[str, ...] = ()
    read_only: Literal[True] = True


@dataclass(frozen=True)
class ProjectionOffset:
    """Durable offset row shape: generation, source revision/digest, CAS."""

    projection_offset_id: str
    key: ProjectorKey
    projection_generation: int
    source_revision: int
    source_digest: str
    offset_ref: str
    revision: int


@dataclass(frozen=True)
class OffsetExpectation:
    """Exact CAS expectation used by advance/delete/rebuild."""

    expected_revision: int
    expected_generation: int
    expected_source_revision: int
    expected_source_digest: str


@dataclass(frozen=True)
class ProjectionRebuild:
    """Pure rebuild plan; ``execute`` must remain False by contract."""

    rebuild_id: str
    key: ProjectorKey
    mode: RebuildMode
    expected: OffsetExpectation | None = None
    from_offset: int = 0
    source_revision: int | None = None
    source_digest: str | None = None
    closure_receipt: str | None = None
    declared_loss: tuple[str, ...] = ()
    execute: Literal[False] = False


@dataclass(frozen=True)
class ProjectionRebuildReceipt:
    """Observed rebuild closure: scope, rebuild/projection digests, time."""

    receipt_id: str
    rebuild_id: str
    project_scope_ref: ProjectScopeRef
    projection_id: str
    projection_digest: str
    source_revision: int
    source_digest: str
    projection_generation: int
    observed_at: str


@dataclass(frozen=True)
class ProjectorRegistry:
    revision: int
    incarnation: str
    projectors: tuple[ProjectorContract, ...] = ()

    def lookup(self, key: ProjectorKey) -> ProjectorContract | None:
        return next(
            (projector for projector in self.projectors if projector.key == key),
            None,
        )

    def by_projection(
        self,
        projection_id: str,
    ) -> tuple[ProjectorContract, ...]:
        return tuple(
            projector
            for projector in self.projectors
            if projector.projection_id == projection_id
        )

    def register(self, contract: ProjectorContract) -> ProjectorRegistry:
        return ProjectorRegistry(
            revision=self.revision,
            incarnation=self.incarnation,
            projectors=self.projectors + (contract,),
        )

    def advance_revision(self) -> ProjectorRegistry:
        return ProjectorRegistry(
            revision=self.revision + 1,
            incarnation=self.incarnation,
            projectors=self.projectors,
        )

    def digest(self) -> str:
        return _sha256_hex(_canonical_json(dataclasses.asdict(self)).encode("utf-8"))


@dataclass(frozen=True)
class ContractViolation:
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    violations: tuple[ContractViolation, ...] = ()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_sha256_hex(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX_DIGITS for character in value)
    )


def _result(violations: list[ContractViolation]) -> ValidationResult:
    return ValidationResult(
        valid=not violations,
        violations=tuple(violations),
    )


def _require_nonempty(
    value: str,
    name: str,
    violations: list[ContractViolation],
) -> None:
    if not isinstance(value, str) or not value.strip():
        violations.append(
            ContractViolation(
                code="FIELD_REQUIRED",
                message=f"{name} must be a non-empty string",
            )
        )


def _validate_scope(scope: ProjectScopeRef) -> ValidationResult:
    if not isinstance(scope, ProjectScopeRef):
        return _result(
            [
                ContractViolation(
                    code="PROJECT_SCOPE_REF_REQUIRED",
                    message="receipt must bind a server-resolved ProjectScopeRef",
                )
            ]
        )
    return _result([])


def validate_projector_key(key: ProjectorKey) -> ValidationResult:
    violations: list[ContractViolation] = []
    for name in (
        "projector_id",
        "projector_version",
        "source_kind",
        "source_ref",
        "source_incarnation",
    ):
        _require_nonempty(getattr(key, name), name, violations)
    return _result(violations)


def validate_projector_contract(contract: ProjectorContract) -> ValidationResult:
    violations: list[ContractViolation] = list(
        validate_projector_key(contract.key).violations
    )
    for name in ("projection_id", "projection_schema_ref"):
        _require_nonempty(getattr(contract, name), name, violations)
    if contract.read_only is not True:
        violations.append(
            ContractViolation(
                code="PROJECTOR_WRITE_FORBIDDEN",
                message="projectors are read-only",
            )
        )
    return _result(violations)


def validate_projection_offset(offset: ProjectionOffset) -> ValidationResult:
    violations: list[ContractViolation] = list(
        validate_projector_key(offset.key).violations
    )
    _require_nonempty(offset.projection_offset_id, "projection_offset_id", violations)
    _require_nonempty(offset.offset_ref, "offset_ref", violations)
    for name, value in (
        ("projection_generation", offset.projection_generation),
        ("source_revision", offset.source_revision),
        ("revision", offset.revision),
    ):
        if not isinstance(value, int) or value < 0:
            violations.append(
                ContractViolation(
                    code="OFFSET_POSITION_NEGATIVE",
                    message=f"{name} must be a non-negative integer",
                )
            )
    if not _is_sha256_hex(offset.source_digest):
        violations.append(
            ContractViolation(
                code="SOURCE_DIGEST_INVALID",
                message="source_digest must be canonical SHA-256 hex",
            )
        )
    return _result(violations)


def validate_offset_expectation(expectation: OffsetExpectation) -> ValidationResult:
    violations: list[ContractViolation] = []
    for name, value in (
        ("expected_revision", expectation.expected_revision),
        ("expected_generation", expectation.expected_generation),
        ("expected_source_revision", expectation.expected_source_revision),
    ):
        if not isinstance(value, int) or value < 0:
            violations.append(
                ContractViolation(
                    code="OFFSET_POSITION_NEGATIVE",
                    message=f"{name} must be a non-negative integer",
                )
            )
    if not _is_sha256_hex(expectation.expected_source_digest):
        violations.append(
            ContractViolation(
                code="SOURCE_DIGEST_INVALID",
                message="expected_source_digest must be canonical SHA-256 hex",
            )
        )
    return _result(violations)


def validate_offset_advance(
    current: ProjectionOffset,
    expectation: OffsetExpectation,
    next_offset: ProjectionOffset,
) -> ValidationResult:
    violations: list[ContractViolation] = list(
        validate_projection_offset(current).violations
    )
    violations.extend(validate_offset_expectation(expectation).violations)
    violations.extend(validate_projection_offset(next_offset).violations)
    if next_offset.key != current.key:
        violations.append(
            ContractViolation(
                code="OFFSET_KEY_MISMATCH",
                message="CAS advance must keep the exact projector/source key",
            )
        )
    if next_offset.projection_offset_id != current.projection_offset_id:
        violations.append(
            ContractViolation(
                code="OFFSET_ID_MISMATCH",
                message="CAS advance must preserve projection_offset_id",
            )
        )
    if current.revision != expectation.expected_revision:
        violations.append(
            ContractViolation(
                code="OFFSET_ABA_DETECTED",
                message="offset revision no longer matches the CAS expectation",
            )
        )
    if current.projection_generation != expectation.expected_generation:
        violations.append(
            ContractViolation(
                code="OFFSET_GENERATION_MISMATCH",
                message="projection generation no longer matches the expectation",
            )
        )
    if (
        current.source_revision != expectation.expected_source_revision
        or current.source_digest != expectation.expected_source_digest
    ):
        violations.append(
            ContractViolation(
                code="SOURCE_STALE",
                message="source revision/digest no longer matches the expectation",
            )
        )
    if next_offset.source_revision < expectation.expected_source_revision:
        violations.append(
            ContractViolation(
                code="SOURCE_REVISION_REGRESSION",
                message="source revision must not regress",
            )
        )
    if (
        next_offset.source_revision == expectation.expected_source_revision
        and next_offset.source_digest != expectation.expected_source_digest
    ):
        violations.append(
            ContractViolation(
                code="SOURCE_REVISION_DIGEST_CONFLICT",
                message="same source revision must not change source digest",
            )
        )
    if next_offset.projection_generation != current.projection_generation:
        violations.append(
            ContractViolation(
                code="OFFSET_GENERATION_CHANGE_FORBIDDEN",
                message="incremental advance must keep the projection generation",
            )
        )
    if next_offset.revision != expectation.expected_revision + 1:
        violations.append(
            ContractViolation(
                code="OFFSET_REVISION_ADVANCE_MISMATCH",
                message="CAS advance must bump the offset revision by exactly one",
            )
        )
    return _result(violations)


def validate_rebuild(
    rebuild: ProjectionRebuild,
    registry: ProjectorRegistry,
) -> ValidationResult:
    violations: list[ContractViolation] = list(
        validate_projector_key(rebuild.key).violations
    )
    _require_nonempty(rebuild.rebuild_id, "rebuild_id", violations)
    if rebuild.mode not in REBUILD_MODES:
        violations.append(
            ContractViolation(
                code="UNKNOWN_REBUILD_MODE",
                message="rebuild mode must be FULL or INCREMENTAL",
            )
        )
    if registry.lookup(rebuild.key) is None:
        violations.append(
            ContractViolation(
                code="PROJECTOR_NOT_REGISTERED",
                message="rebuild must reference a registered projector",
            )
        )
    if (rebuild.source_revision is None and rebuild.source_digest is not None) or (
        rebuild.source_revision is not None and rebuild.source_digest is None
    ):
        violations.append(
            ContractViolation(
                code="REBUILD_SOURCE_PAIR_INCOMPLETE",
                message="FULL rebuild source binding needs revision and digest together",
            )
        )
    if rebuild.source_revision is not None and rebuild.source_revision < 0:
        violations.append(
            ContractViolation(
                code="REBUILD_SOURCE_REVISION_NEGATIVE",
                message="source_revision must be non-negative",
            )
        )
    if rebuild.source_digest is not None and not _is_sha256_hex(rebuild.source_digest):
        violations.append(
            ContractViolation(
                code="SOURCE_DIGEST_INVALID",
                message="source_digest must be canonical SHA-256 hex",
            )
        )
    if rebuild.expected is not None:
        violations.extend(validate_offset_expectation(rebuild.expected).violations)
    if rebuild.mode == "INCREMENTAL" and rebuild.expected is None:
        violations.append(
            ContractViolation(
                code="REBUILD_EXPECTATION_REQUIRED",
                message="incremental rebuild requires an exact CAS expectation",
            )
        )
    if rebuild.mode == "FULL":
        has_source_binding = (
            rebuild.source_revision is not None and rebuild.source_digest is not None
        )
        has_closure_receipt = bool(rebuild.closure_receipt)
        if not has_source_binding and not has_closure_receipt:
            violations.append(
                ContractViolation(
                    code="REBUILD_SOURCE_BINDING_REQUIRED",
                    message=(
                        "FULL rebuild must bind exact source revision/digest "
                        "or a closure receipt"
                    ),
                )
            )
        if has_source_binding and has_closure_receipt:
            violations.append(
                ContractViolation(
                    code="REBUILD_BINDING_CONFLICT",
                    message=(
                        "FULL rebuild must use either source binding or closure "
                        "receipt, not both"
                    ),
                )
            )
    if rebuild.from_offset < 0:
        violations.append(
            ContractViolation(
                code="REBUILD_OFFSET_NEGATIVE",
                message="from_offset must be non-negative",
            )
        )
    if rebuild.execute is not False:
        violations.append(
            ContractViolation(
                code="REBUILD_EXECUTION_FORBIDDEN",
                message="rebuild contracts are pure plans and must never execute",
            )
        )
    return _result(violations)


def validate_rebuild_receipt(receipt: ProjectionRebuildReceipt) -> ValidationResult:
    violations: list[ContractViolation] = []
    for name in (
        "receipt_id",
        "rebuild_id",
        "projection_id",
        "observed_at",
    ):
        _require_nonempty(getattr(receipt, name), name, violations)
    violations.extend(_validate_scope(receipt.project_scope_ref).violations)
    for name, value in (
        ("source_revision", receipt.source_revision),
        ("projection_generation", receipt.projection_generation),
    ):
        if not isinstance(value, int) or value < 0:
            violations.append(
                ContractViolation(
                    code="RECEIPT_POSITION_NEGATIVE",
                    message=f"{name} must be non-negative",
                )
            )
    for name, value in (
        ("projection_digest", receipt.projection_digest),
        ("source_digest", receipt.source_digest),
    ):
        if not _is_sha256_hex(value):
            violations.append(
                ContractViolation(
                    code="SOURCE_DIGEST_INVALID",
                    message=f"{name} must be canonical SHA-256 hex",
                )
            )
    return _result(violations)


def validate_registry(registry: ProjectorRegistry) -> ValidationResult:
    violations: list[ContractViolation] = []
    if not isinstance(registry.revision, int) or registry.revision < 0:
        violations.append(
            ContractViolation(
                code="REGISTRY_REVISION_NEGATIVE",
                message="registry revision must be non-negative",
            )
        )
    _require_nonempty(registry.incarnation, "incarnation", violations)
    seen: set[ProjectorKey] = set()
    for projector in registry.projectors:
        violations.extend(validate_projector_contract(projector).violations)
        if projector.key in seen:
            violations.append(
                ContractViolation(
                    code="DUPLICATE_PROJECTOR_KEY",
                    message=f"duplicate projector key: {projector.key}",
                )
            )
        seen.add(projector.key)
    return _result(violations)


def validate_registry_revision_advance(
    current: ProjectorRegistry,
    next_registry: ProjectorRegistry,
) -> ValidationResult:
    violations: list[ContractViolation] = list(validate_registry(current).violations)
    violations.extend(validate_registry(next_registry).violations)
    if next_registry.revision != current.revision + 1:
        violations.append(
            ContractViolation(
                code="REGISTRY_REVISION_ADVANCE_MISMATCH",
                message="registry revision must advance by exactly one",
            )
        )
    if next_registry.incarnation != current.incarnation:
        violations.append(
            ContractViolation(
                code="REGISTRY_INCARNATION_CHANGE_FORBIDDEN",
                message="registry incarnation must stay stable",
            )
        )
    if next_registry.projectors != current.projectors:
        violations.append(
            ContractViolation(
                code="REGISTRY_PROJECTORS_CHANGE_FORBIDDEN",
                message="registry revision advance must not change projectors",
            )
        )
    return _result(violations)


def validate_offset_snapshot(
    registry: ProjectorRegistry,
    offsets: tuple[ProjectionOffset, ...],
) -> ValidationResult:
    violations: list[ContractViolation] = list(validate_registry(registry).violations)
    by_key = {offset.key: offset for offset in offsets}
    seen: set[ProjectorKey] = set()
    for offset in offsets:
        violations.extend(validate_projection_offset(offset).violations)
        if offset.key in seen:
            violations.append(
                ContractViolation(
                    code="DUPLICATE_OFFSET_KEY",
                    message="offset snapshot must contain one offset per projector",
                )
            )
        seen.add(offset.key)
    for projector in registry.projectors:
        if by_key.get(projector.key) is None:
            violations.append(
                ContractViolation(
                    code="OFFSET_MISSING",
                    message=f"missing offset for {projector.key.projector_id}",
                )
            )
    return _result(violations)


def rebuild_plan_digest(rebuild: ProjectionRebuild) -> str:
    return _sha256_hex(_canonical_json(dataclasses.asdict(rebuild)).encode("utf-8"))
