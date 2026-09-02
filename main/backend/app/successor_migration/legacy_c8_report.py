"""Captured report staging observation for the C8.3 admission/delivery cell.

The legacy report admission/delivery locator is not yet bound.  This adapter
records the missing locator and zero effect counts instead of guessing a donor
file or claiming adoption.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "LEGACY_REPORT_INTERPRETER_ID",
    "UNBOUND_C8_3_REPORT_LOCATOR",
    "LegacyC8ReportAdapter",
]

LEGACY_REPORT_INTERPRETER_ID = "legacy.report.admission_delivery.v1"
UNBOUND_C8_3_REPORT_LOCATOR = "UNBOUND_C8_3_REPORT_ADMISSION_DELIVERY_LOCATOR"


class LegacyC8ReportAdapter:
    """Observation-only adapter; no legacy report donor is guessed."""

    interpreter_id = LEGACY_REPORT_INTERPRETER_ID
    locator: str | None = None

    def __init__(self) -> None:
        self.admission_calls = 0
        self.export_calls = 0
        self.delivery_calls = 0

    def observe_staging(self, artifact: Any) -> dict[str, Any]:
        return {
            "interpreter_id": self.interpreter_id,
            "locator": UNBOUND_C8_3_REPORT_LOCATOR,
            "availability": "READ_ONLY_UNAVAILABLE",
            "reads_only": True,
            "adoption": False,
            "status": "staged_only",
            "report_id": artifact.report_id,
            "artifact_digest": artifact.artifact_digest,
            "admission_calls": self.admission_calls,
            "export_calls": self.export_calls,
            "delivery_calls": self.delivery_calls,
            "provider_calls": 0,
            "store_writes": 0,
        }
