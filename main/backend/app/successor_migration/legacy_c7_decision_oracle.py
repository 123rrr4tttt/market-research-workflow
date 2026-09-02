"""Legacy C7 digestion selector oracle for parity evidence.

The oracle calls the frozen legacy ``digestion_scaffold`` selector only.  It
never executes branch ports, provider effects, writers or database work, and
it exposes legacy dual-flag conflicts so target parity cannot silently
normalize them.
"""

from __future__ import annotations

from typing import Any

from app.contracts.ingest_digestion import (
    DigestionStage,
)
from app.services.ingest.digestion_scaffold import (
    select_digestion_decision,
)
from app.successor_runtime.capabilities.checksum import content_digest

__all__ = [
    "LegacyC7DecisionOracle",
    "legacy_c7_decision_oracle",
]


class LegacyC7DecisionOracle:
    """Deterministic read-only facade over the frozen legacy selector."""

    interpreter_id = "legacy.ingest_digestion.scaffold.select_digestion_decision.v1"

    def __init__(self) -> None:
        self.calls = 0
        self.provider_calls = 0

    def decide(
        self,
        *,
        input_kind: str,
        content_format: str,
        content_length: int | None = None,
    ) -> dict[str, Any]:
        """Return one stable legacy decision trace without executing it."""

        self.calls += 1
        decision = select_digestion_decision(
            input_kind=input_kind,
            content_format=content_format,
            content_length=content_length,
        )
        stage = str(decision.stage.value)
        flags = {
            "extract_required": bool(decision.extract_required),
            "chunking_required": bool(decision.chunking_required),
            "summarize_required": bool(decision.summarize_required),
        }
        selected_flags = [name for name, enabled in flags.items() if enabled]
        trace = {
            "schema": "mrw.successor.ingest-c7.legacy-decision-oracle.v1",
            "interpreter_id": self.interpreter_id,
            "stage": stage,
            "reason": str(decision.reason),
            "content_length": max(0, int(content_length or 0)),
            **flags,
            "pass_through": stage == DigestionStage.PASS_THROUGH.value,
            "dual_flag_conflict": len(selected_flags) > 1,
            "selected_flags": selected_flags,
            "provider_calls": self.provider_calls,
            "authority": False,
        }
        trace["trace_digest"] = content_digest(trace)
        return trace


def legacy_c7_decision_oracle() -> LegacyC7DecisionOracle:
    """Create a fresh zero-call legacy decision oracle."""

    return LegacyC7DecisionOracle()
