"""Shared assembly primitives retained by installed runtime contributions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from app.successor_runtime.runtime.assignments import InterpreterBinding

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


def sha256_hex(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def require_assembly_digest(value: str, label: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
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
    """Construct an exact runtime binding from caller-owned digests."""

    for value, label in (
        (operation_contract_digest, "successor binding operation contract digest"),
        (interpreter_profile_digest, "successor binding interpreter profile digest"),
        (deployment_catalog_digest, "successor binding deployment catalog digest"),
        (project_scope_digest, "successor binding project scope digest"),
        (authority_requirement_digest, "successor binding authority requirement digest"),
    ):
        require_assembly_digest(value, label)
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


__all__ = [
    "ASSEMBLY_STATUSES",
    "AssemblyStatus",
    "CellBinding",
    "require_assembly_digest",
    "sha256_hex",
    "successor_binding",
]
