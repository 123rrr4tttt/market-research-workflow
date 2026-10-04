"""Explicit kit contribution catalog for the S1/S2c horizontal families."""

from __future__ import annotations

from functorial_kit.core.failure import is_failure

from app.successor_runtime.assembly.s1_horizontal_port_assembly import (
    build_s1_horizontal_port_registry,
)
from app.successor_runtime.assembly.s2c_ops_domain_surface_assembly import (
    build_s2c_ops_domain_surface_registry,
)

from mrw_functorial_kit.contributions.horizontal import (
    HorizontalNativeSource,
    compile_horizontal_native_contribution,
)

_s1_source = HorizontalNativeSource(
    family_id="s1_horizontal_port",
    ports=build_s1_horizontal_port_registry(),
    surfaces=(),
)
_s2c_source = HorizontalNativeSource(
    family_id="s2c_ops_domain_surface",
    ports=(),
    surfaces=build_s2c_ops_domain_surface_registry(),
)

_s1_compiled = compile_horizontal_native_contribution(_s1_source)
if is_failure(_s1_compiled):
    raise RuntimeError(f"invalid S1 horizontal native contribution: {_s1_compiled.message}")
_s2c_compiled = compile_horizontal_native_contribution(_s2c_source)
if is_failure(_s2c_compiled):
    raise RuntimeError(
        f"invalid S2c horizontal native contribution: {_s2c_compiled.message}"
    )

# Ordered native catalog: S1 ports first, then S2c surfaces.  This module has
# no runtime execution and registers no routes; project_catalog composition is
# owned by the mainline assembly owner.
horizontal_native_catalog = (_s1_compiled, _s2c_compiled)

__all__ = ["horizontal_native_catalog"]
