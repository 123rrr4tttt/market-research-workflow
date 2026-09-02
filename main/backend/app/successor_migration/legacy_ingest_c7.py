"""Sibling legacy adapter for the P4 C7 ingest-index replay.

The adapter replays the actual legacy frontdoor postprocess pipeline with
``run_writer=False``, so the legacy writer is provably zero-call.  Provider
extraction is also disabled, leaving ``provider_calls == 0``.  Frozen P1
locators for C7 are exposed so the evidence fragment binds them exactly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.ingest.frontdoor_ingress import (
    build_frontdoor_ingress_envelope as _legacy_build_frontdoor_ingress_envelope,
)
from app.services.ingest.postprocess_frontdoor import (
    run_postprocess_frontdoor as _legacy_run_postprocess_frontdoor,
)
from app.successor_runtime.capabilities.ingest_c7_common import (
    AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED,
    C7IngestSubmission,
    content_digest,
)

__all__ = [
    "LEGACY_INGEST_C7_WRITER_DISABLED",
    "P1_C7_FRAGMENT_PATH",
    "LegacyIngestC7Replay",
    "LegacyIngestWriterDisabledError",
    "capture_legacy_ingest_c7_fixture",
    "frozen_p1_cell_locators",
]


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
P1_C7_FRAGMENT_PATH = (
    REPOSITORY_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/p1-fragments/C7.json"
)

LEGACY_INGEST_C7_WRITER_DISABLED = True


class LegacyIngestWriterDisabledError(RuntimeError):
    """Raised if any caller asks the C7 replay to persist a document."""


def frozen_p1_cell_locators() -> dict[str, dict[str, object]]:
    """Return frozen P1 C7 locator paths/status keyed by P1 cell id."""

    cells = json.loads(P1_C7_FRAGMENT_PATH.read_text(encoding="utf-8"))
    return {
        str(cell["cell"]): {
            "locator_paths": list(cell.get("locator_paths") or ()),
            "locator_status": str(cell.get("locator_status") or ""),
        }
        for cell in cells
        if str(cell.get("cell") or "").startswith("C7.")
    }


class LegacyIngestC7Replay:
    """Actual postprocess replay with a zero-call writer spy."""

    interpreter_id = "legacy.ingest_index.postprocess_frontdoor.replay.v1"

    def __init__(self) -> None:
        self.writer_calls = 0
        self.replay_calls = 0

    def capture(
        self,
        submission: C7IngestSubmission,
    ) -> dict[str, Any]:
        """Run the actual postprocess pipeline with writer/extraction disabled."""

        self.replay_calls += 1
        payload = dict(submission.raw_payload or {})
        collection_payload = {
            "document_candidate": {
                "uri": submission.source_locator,
                "title": str(payload.get("title") or ""),
                "content": str(payload.get("text") or ""),
            },
            "dispatch_plan": {"run_writer": False, "run_extraction": False},
            "extraction_plan": {"enabled": False},
        }
        envelope = _legacy_build_frontdoor_ingress_envelope(
            ingress_type="raw_import",
            entrypoint="ingest.raw_import",
            source_mode="raw_import",
            project_key=submission.project_key,
            source_ref={"locator": submission.source_locator},
            collection_payload=collection_payload,
            raw_snapshot=payload,
        )
        result = _legacy_run_postprocess_frontdoor(
            ingress_envelope=envelope,
            run_writer=False,
        )
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        dispatch = (
            data.get("dispatch_plan")
            if isinstance(data.get("dispatch_plan"), dict)
            else {}
        )
        return {
            "schema": "mrw.successor.legacy-ingest-c7.postprocess.v1",
            "status": AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED,
            "interpreter_id": self.interpreter_id,
            "postprocess_status": str(result.get("status") or ""),
            "postprocess_admission": str(data.get("admission") or ""),
            "writer_result_present": data.get("writer_result") is not None,
            "run_writer": bool(dispatch.get("run_writer")),
            "run_extraction": bool(dispatch.get("run_extraction")),
            "writer_enabled": False,
            "writer_calls": self.writer_calls,
            "provider_calls": 0,
            "authority": False,
            "fixture_digest": content_digest(
                {
                    "postprocess_status": result.get("status"),
                    "postprocess_admission": data.get("admission"),
                    "writer_result_present": data.get("writer_result") is not None,
                    "run_writer": bool(dispatch.get("run_writer")),
                    "writer_calls": 0,
                    "provider_calls": 0,
                }
            ),
        }

    def persist(self, *args: Any, **kwargs: Any) -> None:
        """Hard-disabled legacy writer; any call is a scaffold violation."""

        self.writer_calls += 1
        raise LegacyIngestWriterDisabledError(
            "C7 ahead-of-time scaffolding never writes documents"
        )


def capture_legacy_ingest_c7_fixture(
    submission: C7IngestSubmission,
) -> tuple[dict[str, Any], LegacyIngestC7Replay]:
    replay = LegacyIngestC7Replay()
    fixture = replay.capture(submission)
    return fixture, replay
