"""Semantic ABI identity for the shared successor runtime kernel protocols."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any

from .capability_cell_spec import digest_json

ABI_SCHEMA = "mrw.functorial_successor.runtime_kernel_abi.v1"
ABI_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class RuntimeKernelABI:
    """Versions shared protocol semantics, never exact implementation bytes."""

    program_protocol_version: str
    plan_protocol_version: str
    handler_binding_protocol_version: str
    assignment_protocol_version: str
    reducer_protocol_version: str
    work_item_protocol_version: str
    semantic_digest: str = ""
    schema: str = ABI_SCHEMA
    version: str = ABI_VERSION

    def __post_init__(self) -> None:
        if self.schema != ABI_SCHEMA or self.version != ABI_VERSION:
            raise ValueError("unsupported RuntimeKernelABI schema/version")
        for field in (
            "program_protocol_version",
            "plan_protocol_version",
            "handler_binding_protocol_version",
            "assignment_protocol_version",
            "reducer_protocol_version",
            "work_item_protocol_version",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")
        expected = self.compute_semantic_digest()
        if self.semantic_digest and self.semantic_digest != expected:
            raise ValueError("RuntimeKernelABI semantic_digest mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("semantic_digest")
        return value

    def compute_semantic_digest(self) -> str:
        return digest_json(self.semantic_payload())

    def with_digest(self) -> RuntimeKernelABI:
        return replace(self, semantic_digest=self.compute_semantic_digest())

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        if not value["semantic_digest"]:
            value["semantic_digest"] = self.compute_semantic_digest()
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RuntimeKernelABI:
        return cls(**dict(value)).with_digest()
