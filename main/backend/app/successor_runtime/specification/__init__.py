"""Deterministic capability-specification compiler for successor pilots.

The package describes and compiles mechanical evidence scaffolding only.  It
does not execute effects, infer domain semantics, or grant runtime authority.
"""

from .capability_cell_spec import (
    IDENTITY_COMPOSITION_REF,
    AuthorityCeiling,
    CapabilityCellSpec,
    ExactFileBinding,
    compose_ordered,
)
from .compiler import (
    COMPILER_VERSION,
    CapabilitySpecCompileError,
    build_manifest_bytes,
    compile_capability_spec,
)
from .runtime_kernel_abi import RuntimeKernelABI

__all__ = [
    "COMPILER_VERSION",
    "IDENTITY_COMPOSITION_REF",
    "AuthorityCeiling",
    "CapabilityCellSpec",
    "CapabilitySpecCompileError",
    "ExactFileBinding",
    "RuntimeKernelABI",
    "build_manifest_bytes",
    "compile_capability_spec",
    "compose_ordered",
]
