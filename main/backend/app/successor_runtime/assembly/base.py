"""Shared contracts for the I1 successor family assembly builders.

The assembly layer is an explicit wiring boundary, not a new semantic
implementation.  Each family builder reuses existing capability programs,
handlers, store-rehydrated handlers, canary handlers, recovery bindings,
projection contracts and kernel mechanisms and records one ``CellBinding``
per capability cell.  Statuses are fail-closed: a cell is ``INSTALLED`` only
when a real ``RuntimeHandler`` with an exact binding digest, or an explicit
``KernelWiring`` declaration with an exact kernel digest, is included in the
family assembly; every other status is an explicit unresolved, design-only or
declared-gap classification.  No assembly here mounts an app route, starts a
node, calls a live provider or performs a canonical write.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from app.successor_runtime.runtime.assignments import InterpreterBinding
from app.successor_runtime.runtime.node import RuntimeHandler
from app.successor_runtime.substrate.projections.registry import (
    ProjectorContract,
    ProjectorKey,
    ProjectorRegistry,
    validate_projector_contract,
    validate_registry,
)

AssemblyStatus = Literal[
    "INSTALLED",
    "UNRESOLVED_WIRING",
    "UNWIRED_DECLARED",
    "DESIGN_ONLY",
    "FIXTURE_CLOSURE_REQUIRED",
    "LIVE_PROVIDER_NOT_AUTHORIZED",
    "ROLLBACK_BINDING_MISSING",
    "PROJECTOR_WIRING_DECLARED",
]

ASSEMBLY_STATUSES: frozenset[str] = frozenset(
    {
        "INSTALLED",
        "UNRESOLVED_WIRING",
        "UNWIRED_DECLARED",
        "DESIGN_ONLY",
        "FIXTURE_CLOSURE_REQUIRED",
        "LIVE_PROVIDER_NOT_AUTHORIZED",
        "ROLLBACK_BINDING_MISSING",
        "PROJECTOR_WIRING_DECLARED",
    }
)

LOCAL_ONLY_SCOPE_IDENTITY = "mrw.successor.assembly.local-only.scope.v1"
PROJECTOR_REGISTRY_INCARNATION = "mrw.successor.assembly.projector-registry.v1"


@dataclass(frozen=True, slots=True)
class ProjectorSourceKey:
    """Exact per-run projector/source identity supplied by the run owner."""

    source_ref: str
    source_incarnation: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_ref, str) or not self.source_ref.strip():
            raise ValueError("projector source_ref must be a non-empty string")
        if (
            not isinstance(self.source_incarnation, str)
            or not self.source_incarnation.strip()
        ):
            raise ValueError("projector source_incarnation must be a non-empty string")


def sha256_hex(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def local_assembly_scope_digest() -> str:
    """Deterministic local-only assembly scope identity.

    This is an explicit LOCAL_ONLY identity for offline assembly smoke and
    rehearsal evidence.  It is not a production scope and must be replaced by
    the caller with the exact persisted project scope digest before any run.
    """

    return sha256_hex(LOCAL_ONLY_SCOPE_IDENTITY)


def require_assembly_digest(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a sha256 hex digest")


def successor_binding(
    *,
    operation_contract_digest: str,
    interpreter_profile_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    authority_requirement_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    """Mechanical successor binding construction without legacy imports.

    This mirrors the exact fields used by the family canary binding builders
    while keeping the runtime tree free of legacy/migration imports.  It
    constructs only the immutable interpreter binding; it never adds semantic
    behavior.
    """

    require_assembly_digest(
        operation_contract_digest,
        "successor binding operation contract digest",
    )
    require_assembly_digest(
        interpreter_profile_digest,
        "successor binding interpreter profile digest",
    )
    require_assembly_digest(
        deployment_catalog_digest,
        "successor binding deployment catalog digest",
    )
    require_assembly_digest(
        project_scope_digest,
        "successor binding project scope digest",
    )
    require_assembly_digest(
        authority_requirement_digest,
        "successor binding authority requirement digest",
    )
    return InterpreterBinding.from_content(
        operation_contract_digest=operation_contract_digest,
        interpreter_profile_digest=interpreter_profile_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest,
    )


@dataclass(frozen=True, slots=True)
class CellBinding:
    """One capability cell's assembly status and exact wiring facts."""

    cell_id: str
    family_id: str
    status: AssemblyStatus
    operation_contract_refs: tuple[str, ...] = ()
    handler_binding_digest: str | None = None
    recovery_binding_ref: str | None = None
    rollback_binding_refs: tuple[str, ...] = ()
    required_wiring: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in ASSEMBLY_STATUSES:
            raise ValueError(f"unknown assembly status: {self.status}")
        if not self.cell_id or not self.family_id:
            raise ValueError("cell binding requires cell_id and family_id")
        if self.status == "INSTALLED":
            require_assembly_digest(
                self.handler_binding_digest or "",
                f"{self.cell_id} handler binding digest",
            )
        elif self.handler_binding_digest is not None:
            raise ValueError(
                f"{self.cell_id} non-installed status cannot carry a binding digest"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "family_id": self.family_id,
            "status": self.status,
            "operation_contract_refs": list(self.operation_contract_refs),
            "handler_binding_digest": self.handler_binding_digest,
            "recovery_binding_ref": self.recovery_binding_ref,
            "rollback_binding_refs": list(self.rollback_binding_refs),
            "required_wiring": list(self.required_wiring),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class ProjectorWiring:
    """Declared projector wiring for one exact projector identity.

    The assembly records which existing projector class implements a family
    projection.  Exact per-run source keys (source_ref, source_incarnation)
    are never invented here; a run must supply them before
    ``ProjectorRegistry.register`` can happen.
    """

    cell_id: str
    projector_id: str
    projector_version: str
    source_kind: str
    projection_id: str
    projection_schema_ref: str
    declared_loss: tuple[str, ...] = ()
    note: str = ""

    def to_contract(self, source_key: ProjectorSourceKey) -> ProjectorContract:
        """Bind one exact per-run source key to this declared projector."""

        return ProjectorContract(
            key=ProjectorKey(
                projector_id=self.projector_id,
                projector_version=self.projector_version,
                source_kind=self.source_kind,
                source_ref=source_key.source_ref,
                source_incarnation=source_key.source_incarnation,
            ),
            projection_id=self.projection_id,
            projection_schema_ref=self.projection_schema_ref,
            declared_loss=self.declared_loss,
        )

    def registration_digest(self, contract: ProjectorContract) -> str:
        """Deterministic digest for one exact registered projector contract."""

        payload = {
            "schema": "mrw.successor.assembly.projector-registration.v1",
            "contract": dataclasses.asdict(contract),
        }
        return sha256_hex(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "projector_id": self.projector_id,
            "projector_version": self.projector_version,
            "source_kind": self.source_kind,
            "projection_id": self.projection_id,
            "projection_schema_ref": self.projection_schema_ref,
            "declared_loss": list(self.declared_loss),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class KernelWiring:
    """Explicit wiring of an existing kernel mechanism to one capability cell.

    A kernel wiring declares that the cell is realized by an existing
    infrastructure mechanism (for example the RuntimeNode kernel or the replay
    adapter) that is installed by the composition root itself, not by a family
    ``RuntimeHandler``.  The exact kernel identity and binding digest are
    declared here so the cell can be ``INSTALLED`` without inventing a handler.
    """

    cell_id: str
    kernel_id: str
    kernel_version: str
    binding_digest: str
    binding_refs: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if not self.cell_id or not self.kernel_id or not self.kernel_version:
            raise ValueError("kernel wiring requires cell_id, kernel_id and version")
        require_assembly_digest(self.binding_digest, f"{self.cell_id} kernel digest")

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "kernel_id": self.kernel_id,
            "kernel_version": self.kernel_version,
            "binding_digest": self.binding_digest,
            "binding_refs": list(self.binding_refs),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class RollbackBindingDeclaration:
    """Per-cell rollback evidence or an explicit declared gap."""

    cell_id: str
    status: Literal["PRESENT", "DECLARED_GAP", "DECLARED_OPEN"]
    binding_refs: tuple[str, ...] = ()
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "status": self.status,
            "binding_refs": list(self.binding_refs),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class FamilyAssembly:
    """One family's reusable installation set and cell coverage matrix."""

    family_id: str
    cells: tuple[CellBinding, ...]
    handlers: tuple[RuntimeHandler, ...] = ()
    recovery_handlers: tuple[RuntimeHandler, ...] = ()
    kernel_wiring: tuple[KernelWiring, ...] = ()
    projector_wiring: tuple[ProjectorWiring, ...] = ()
    rollback_bindings: tuple[RollbackBindingDeclaration, ...] = ()
    projector_registry: ProjectorRegistry | None = None

    def __post_init__(self) -> None:
        if not self.family_id or not self.cells:
            raise ValueError("family assembly requires family_id and cells")
        for cell in self.cells:
            if cell.family_id != self.family_id:
                raise ValueError(
                    f"cell {cell.cell_id} does not belong to family {self.family_id}"
                )
        by_digest: dict[str, str] = {}
        for handler in self.handlers:
            digest = handler.handler_binding_digest
            require_assembly_digest(digest, f"{self.family_id} handler digest")
            owner = by_digest.get(digest)
            if owner is not None:
                raise ValueError(
                    f"duplicate handler binding digest {digest} in family "
                    f"{self.family_id} ({owner})"
                )
            by_digest[digest] = "handler"
        for handler in self.recovery_handlers:
            digest = handler.handler_binding_digest
            require_assembly_digest(digest, f"{self.family_id} recovery digest")
            owner = by_digest.get(digest)
            if owner is not None:
                raise ValueError(
                    f"duplicate recovery binding digest {digest} in family "
                    f"{self.family_id} ({owner})"
                )
            by_digest[digest] = "recovery"
        family_cell_ids = {cell.cell_id for cell in self.cells}
        for wiring in self.kernel_wiring:
            if wiring.cell_id not in family_cell_ids:
                raise ValueError(
                    f"kernel wiring {wiring.cell_id} does not belong to family "
                    f"{self.family_id}"
                )
            digest = wiring.binding_digest
            owner = by_digest.get(digest)
            if owner is not None:
                raise ValueError(
                    f"duplicate kernel wiring digest {digest} in family "
                    f"{self.family_id} ({owner})"
                )
            by_digest[digest] = f"kernel:{wiring.cell_id}"
        if self.projector_registry is not None:
            registry_validation = validate_registry(self.projector_registry)
            if not registry_validation.valid:
                raise ValueError(
                    f"{self.family_id} projector registry invalid: "
                    + "; ".join(item.message for item in registry_validation.violations)
                )
        projector_contracts: dict[str, ProjectorContract] = {}
        for wiring in self.projector_wiring:
            if self.projector_registry is None:
                continue
            matches = tuple(
                projector
                for projector in self.projector_registry.projectors
                if (
                    projector.key.projector_id == wiring.projector_id
                    and projector.key.projector_version == wiring.projector_version
                    and projector.key.source_kind == wiring.source_kind
                    and projector.projection_id == wiring.projection_id
                    and projector.projection_schema_ref == wiring.projection_schema_ref
                )
            )
            if len(matches) > 1:
                raise ValueError(
                    f"duplicate registered projector identity in family "
                    f"{self.family_id}"
                )
            if matches:
                contract = matches[0]
                contract_validation = validate_projector_contract(contract)
                if not contract_validation.valid:
                    raise ValueError(
                        f"{self.family_id} projector contract invalid: "
                        + "; ".join(
                            item.message for item in contract_validation.violations
                        )
                    )
                digest = wiring.registration_digest(contract)
                owner = by_digest.get(digest)
                if owner is not None:
                    raise ValueError(
                        f"duplicate projector registration digest {digest} in "
                        f"family {self.family_id} ({owner})"
                    )
                by_digest[digest] = f"projector:{wiring.cell_id}"
                projector_contracts[wiring.cell_id] = contract
        for wiring in self.projector_wiring:
            cell = next(
                (item for item in self.cells if item.cell_id == wiring.cell_id),
                None,
            )
            if cell is None:
                raise ValueError(
                    f"projector wiring {wiring.cell_id} does not belong to "
                    f"family {self.family_id}"
                )
            if cell.status == "INSTALLED":
                contract = projector_contracts.get(wiring.cell_id)
                if contract is None:
                    raise ValueError(
                        f"{wiring.cell_id} is INSTALLED but no registered "
                        "projector contract exists in the family registry"
                    )
                expected = wiring.registration_digest(contract)
                if cell.handler_binding_digest != expected:
                    raise ValueError(
                        f"{wiring.cell_id} binding digest does not match its "
                        "registered projector contract"
                    )
            elif cell.status == "PROJECTOR_WIRING_DECLARED":
                if wiring.cell_id in projector_contracts:
                    raise ValueError(
                        f"{wiring.cell_id} stays PROJECTOR_WIRING_DECLARED but "
                        "carries a registered projector contract"
                    )
        installed_handlers = {
            cell.cell_id: cell for cell in self.cells if cell.status == "INSTALLED"
        }
        for cell_id, cell in installed_handlers.items():
            assert cell.handler_binding_digest is not None
            if cell.handler_binding_digest not in by_digest:
                raise ValueError(
                    f"{cell_id} is INSTALLED but no handler or kernel wiring "
                    "carries its binding digest"
                )

    def cell(self, cell_id: str) -> CellBinding:
        matches = tuple(item for item in self.cells if item.cell_id == cell_id)
        if len(matches) != 1:
            raise KeyError(f"family {self.family_id} lacks one exact cell {cell_id}")
        return matches[0]

    def coverage(self) -> dict[str, str]:
        return {item.cell_id: item.status for item in self.cells}


@dataclass(frozen=True, slots=True)
class C5AssemblyOptions:
    """Optional run-bound C5.2 reconciliation route closure."""

    reconciliation_binding: Any | None = None
    note: str = "LOCAL_OFFLINE deterministic reconciliation route closure"


@dataclass(frozen=True, slots=True)
class C3AssemblyOptions:
    """Optional deterministic element payloads for the C3 composed handler."""

    element_payloads: tuple[Any, ...] = ()
    note: str = "LOCAL_OFFLINE deterministic no-provider fixture closure"


@dataclass(frozen=True, slots=True)
class C4AssemblyOptions:
    """Optional deterministic payloads for the C4.1/C4.2 canary handlers."""

    plan_payload: Any | None = None
    retry_payload: Any | None = None
    note: str = "LOCAL_OFFLINE deterministic fixture closure"


@dataclass(frozen=True, slots=True)
class C6AssemblyOptions:
    """Optional run-bound C6 fixture ports; never a production provider."""

    model_step_source: Any | None = None
    provider_port: Any | None = None
    raw_observation: Any | None = None
    tool_specimens: tuple[Any, ...] = ()
    permission_policy: Any | None = None
    redactor: Any | None = None
    note: str = "LOCAL_OFFLINE deterministic fixture closure only"


@dataclass(frozen=True, slots=True)
class C7AssemblyOptions:
    """Optional deterministic C7 rollback-route closures.

    Each field carries one exact pure-route fixture.  A cell is installed only
    when its route closure is supplied; absent routes fail closed with the
    missing dimensions listed in the cell note.
    """

    submission: Any | None = None
    commit_readback: Any | None = None
    projection_diff: Any | None = None
    reconciliation_decision: Any | None = None
    note: str = "LOCAL_OFFLINE deterministic rollback-route fixture closure"


@dataclass(frozen=True, slots=True)
class C8AssemblyOptions:
    """Optional dependencies for the existing C8.3 delivery bridge assembly."""

    bundle: Any | None = None
    activation_catalog: Any | None = None
    delivery_interpreter: Any | None = None
    c81_payload: Any | None = None
    c82_payload: Any | None = None
    note: str = "reuses build_postgres_c8_delivery_assembly unchanged"


@dataclass(frozen=True, slots=True)
class C9AssemblyOptions:
    """Optional run-bound C9 facade validation closure."""

    facade: Any | None = None
    note: str = "LOCAL_OFFLINE deterministic facade validation closure"


@dataclass(frozen=True, slots=True)
class FamilyAssemblyOptions:
    """Caller-controlled fixture/dependency closures for assembly builders."""

    c5: C5AssemblyOptions = C5AssemblyOptions()
    c3: C3AssemblyOptions = C3AssemblyOptions()
    c4: C4AssemblyOptions = C4AssemblyOptions()
    c6: C6AssemblyOptions = C6AssemblyOptions()
    c7: C7AssemblyOptions = C7AssemblyOptions()
    c8: C8AssemblyOptions = C8AssemblyOptions()
    c9: C9AssemblyOptions = C9AssemblyOptions()
    projector_source_keys: Mapping[str, ProjectorSourceKey] = field(
        default_factory=dict
    )


def merge_family_assemblies(
    families: tuple[FamilyAssembly, ...],
) -> tuple[
    tuple[CellBinding, ...],
    tuple[RuntimeHandler, ...],
    tuple[RuntimeHandler, ...],
    tuple[KernelWiring, ...],
]:
    """Merge family installations with exact-digest and coverage validation."""

    seen_cells: set[str] = set()
    cells: list[CellBinding] = []
    handlers: list[RuntimeHandler] = []
    recovery: list[RuntimeHandler] = []
    kernel_wiring: list[KernelWiring] = []
    digest_owner: dict[str, str] = {}
    for family in families:
        for cell in family.cells:
            if cell.cell_id in seen_cells:
                raise ValueError(f"duplicate cell coverage: {cell.cell_id}")
            seen_cells.add(cell.cell_id)
            cells.append(cell)
        for handler in family.handlers:
            digest = handler.handler_binding_digest
            owner = digest_owner.get(digest)
            if owner is not None:
                raise ValueError(
                    f"merged assembly duplicate handler digest {digest} ({owner})"
                )
            digest_owner[digest] = f"{family.family_id}:handler"
            handlers.append(handler)
        for handler in family.recovery_handlers:
            digest = handler.handler_binding_digest
            owner = digest_owner.get(digest)
            if owner is not None:
                raise ValueError(
                    f"merged assembly duplicate recovery digest {digest} ({owner})"
                )
            digest_owner[digest] = f"{family.family_id}:recovery"
            recovery.append(handler)
        for wiring in family.kernel_wiring:
            digest = wiring.binding_digest
            owner = digest_owner.get(digest)
            if owner is not None:
                raise ValueError(
                    f"merged assembly duplicate kernel digest {digest} ({owner})"
                )
            digest_owner[digest] = f"{family.family_id}:kernel:{wiring.cell_id}"
            kernel_wiring.append(wiring)
    return tuple(cells), tuple(handlers), tuple(recovery), tuple(kernel_wiring)


__all__ = [
    "ASSEMBLY_STATUSES",
    "LOCAL_ONLY_SCOPE_IDENTITY",
    "PROJECTOR_REGISTRY_INCARNATION",
    "AssemblyStatus",
    "C3AssemblyOptions",
    "C4AssemblyOptions",
    "C5AssemblyOptions",
    "C6AssemblyOptions",
    "C7AssemblyOptions",
    "C8AssemblyOptions",
    "C9AssemblyOptions",
    "CellBinding",
    "FamilyAssembly",
    "FamilyAssemblyOptions",
    "KernelWiring",
    "ProjectorSourceKey",
    "ProjectorWiring",
    "RollbackBindingDeclaration",
    "local_assembly_scope_digest",
    "merge_family_assemblies",
    "require_assembly_digest",
    "sha256_hex",
    "successor_binding",
]
