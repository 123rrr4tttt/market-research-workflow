#!/usr/bin/env python3
"""Wave18 gate for ingest long-cycle scheduler handoff traces."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ingest.digestion_scaffold import JsonlLongCycleTaskRepository  # noqa: E402
from app.services.ingest.digestion_scaffold import check_long_cycle_scheduler_handoff_trace_contract  # noqa: E402


EVIDENCE_FILE = (
    REPO_ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-03-07-ingest-digestion-and-long-cycle-automation"
    / "08_wave18-long-cycle-scheduler-handoff-trace-2026-05-22.md"
)
REQUIRED_EVIDENCE_MARKERS = (
    "contract_version: ingest.long_cycle_scheduler_handoff_trace_check.v1",
    "durable_event_readback: true",
    "dispatch_intent_matches_readback: true",
    "live_dispatch: false",
    "live_db_write: false",
    "closure_claim: false",
    "live_scheduler_closure_validated: false",
)


def main() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="ingest-lc-handoff-") as tmp_dir:
        repository = JsonlLongCycleTaskRepository(
            storage_dir=tmp_dir,
            repository_ref="jsonl://wave18-long-cycle-scheduler-handoff",
            logical_table="long_cycle_persistent_tasks",
        )
        check = check_long_cycle_scheduler_handoff_trace_contract(
            repository=repository,
            task_goal="Digest weekly report inputs",
            project_key="demo_proj",
            entrypoint="ingest.raw_import",
            source_locator="file:///tmp/weekly-report.md",
            content_format="markdown",
            content_length=8000,
            processed_time="2026-03-08T11:00:00Z",
            candidate_windows=["7d", "30d"],
            selected_window="7d",
            cadence="weekly",
            scheduler_ref="contract.scheduler.ingest-long-cycle",
            persistent_ref=repository.repository_ref,
            event_time="2026-03-08T11:00:00Z",
            run_at="2026-03-08T11:02:00Z",
        )

    expected_trace_sequence = [
        "dispatch_intent_created",
        "scheduler_handoff_recorded",
        "durable_event_readback",
        "terminal_output_readback",
    ]
    expected_event_sequence = ["mark_ready", "dispatch", "succeed"]
    dispatch_intent = check["dispatch_intent"]
    readback = check["repository_readback"]
    dispatch_ref = f"contract-dispatch://{dispatch_intent['dispatch_key']}"

    if check["status"] != "pass":
        failures.append(f"expected pass, got {check['status']}: {check['blockers']}")
    if check["contract_version"] != "ingest.long_cycle_scheduler_handoff_trace_check.v1":
        failures.append("scheduler handoff trace contract version drifted")
    if check["handoff_trace_sequence"] != expected_trace_sequence:
        failures.append(f"handoff trace sequence drifted: {check['handoff_trace_sequence']}")
    if readback["readback_event_sequence"] != expected_event_sequence:
        failures.append(f"durable event sequence drifted: {readback['readback_event_sequence']}")
    if check["dispatch_ref"] != dispatch_ref:
        failures.append("dispatch ref no longer derives from dispatch intent key")
    if check["durable_event_readback"] is not True:
        failures.append("durable dispatch event readback was not validated")
    if check["dispatch_intent_matches_readback"] is not True:
        failures.append("dispatch intent no longer matches durable readback event")
    if check["live_dispatch"] is not False:
        failures.append("handoff trace must not claim live scheduler dispatch")
    if check["live_db_write"] is not False:
        failures.append("handoff trace must not claim live DB writes")
    if check["closure_claim"] is not False:
        failures.append("handoff trace must not claim production closure")
    if check["live_scheduler_closure_validated"] is not False:
        failures.append("live scheduler closure must remain unvalidated")
    if "live_scheduler_handoff_not_validated" not in check["remaining_runtime_gaps"]:
        failures.append("remaining gaps must preserve live scheduler handoff boundary")
    if "end_to_end_automation_run_not_executed" not in check["remaining_runtime_gaps"]:
        failures.append("remaining gaps must preserve end-to-end automation boundary")

    if not EVIDENCE_FILE.is_file():
        failures.append(f"missing evidence file: {EVIDENCE_FILE.relative_to(REPO_ROOT)}")
    else:
        evidence_text = EVIDENCE_FILE.read_text(encoding="utf-8")
        for marker in REQUIRED_EVIDENCE_MARKERS:
            if marker not in evidence_text:
                failures.append(f"evidence file missing marker {marker!r}")

    payload = {
        "status": "fail" if failures else "pass",
        "contract_status": (
            "closed_narrow_scheduler_handoff_trace_contract"
            if not failures
            else "open_scheduler_handoff_trace_gap"
        ),
        "failures": failures,
        "check": check,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
