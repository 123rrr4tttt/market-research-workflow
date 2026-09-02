"""Sibling legacy projector adapter for C2.4 terminal/compat projection.

This is the only file allowed to call the legacy terminal DTO donor
``terminal_output.to_terminal_output_dto``.  It deliberately never calls the
collect-runtime postprocessor, never generates UUIDs and never touches
writer-capable or admission paths.  The legacy DTO is only a parity donor
over frozen fixture payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.source_library.terminal_output import to_terminal_output_dto
from app.successor_runtime.capabilities.checksum import content_digest

__all__ = [
    "LegacySourceLibraryC2_4Adapter",
    "LegacyTerminalTrace",
]


LEGACY_C2_4_INTERPRETER_ID = "legacy.source_library.c2_4.terminal_compat.v1"


@dataclass(frozen=True, slots=True)
class LegacyTerminalTrace:
    trace_id: str
    terminal_dto: dict[str, Any]
    raw_snapshot_ref: str | None
    trace_digest: str = ""

    def __post_init__(self) -> None:
        if self.trace_digest == "":
            object.__setattr__(
                self,
                "trace_digest",
                content_digest(
                    {
                        "schema": "mrw.successor.source-library.c2-4.legacy-trace.v1",
                        "trace_id": self.trace_id,
                        "terminal_dto": self.terminal_dto,
                        "raw_snapshot_ref": self.raw_snapshot_ref,
                    }
                ),
            )


class LegacySourceLibraryC2_4Adapter:
    """Pure legacy DTO replay; no postprocess, UUID or writer call."""

    interpreter_id = LEGACY_C2_4_INTERPRETER_ID

    def __init__(self) -> None:
        self.traces: list[LegacyTerminalTrace] = []
        self.postprocess_calls: list[str] = []

    def replay(
        self,
        result_payload: dict[str, Any] | None,
        *,
        trace_id: str = "legacy.c2_4.terminal_compat",
        raw_snapshot_ref: str | None = None,
    ) -> LegacyTerminalTrace:
        dto = to_terminal_output_dto(result_payload)
        trace = LegacyTerminalTrace(
            trace_id=trace_id,
            terminal_dto=dto,
            raw_snapshot_ref=raw_snapshot_ref,
        )
        self.traces.append(trace)
        return trace
