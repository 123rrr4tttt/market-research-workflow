#!/usr/bin/env python3
"""Deterministic Wave9 gate for ingest long-cycle lifecycle contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.ingest.digestion_scaffold import check_long_cycle_lifecycle_contract
from app.services.ingest.digestion_scaffold import transition_long_cycle_persistent_task_record


def main() -> int:
    check = check_long_cycle_lifecycle_contract(
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
        scheduler_ref="dry-run.scheduler.ingest-long-cycle",
        persistent_ref="dry-run.persistent-task.ingest-lc",
        event_time="2026-03-08T11:00:00Z",
    )
    running = transition_long_cycle_persistent_task_record(
        check["persistent_task"],
        transition="dispatch",
        dispatch_ref="dry-run-dispatch-001",
        event_time="2026-03-08T11:02:00Z",
        actor="wave9_contract_checker",
        reason="deterministic dry-run dispatch",
    )
    completed = transition_long_cycle_persistent_task_record(
        running,
        transition="succeed",
        output_ref="dry-run://digestion/status/demo_proj/2026-03-08",
        event_time="2026-03-08T11:05:00Z",
        actor="wave9_contract_checker",
        reason="deterministic dry-run completion",
    )

    failures: list[str] = []
    if check["status"] != "pass":
        failures.append(f"expected pass, got {check['status']}")
    if not str(check["persistent_task"]["task_key"]).startswith("ingest-lc-"):
        failures.append("persistent task key does not use ingest-lc prefix")
    if running.status.value != "running":
        failures.append(f"expected running after dispatch, got {running.status.value}")
    if completed.status.value != "succeeded":
        failures.append(f"expected succeeded after completion, got {completed.status.value}")
    if completed.attempt_count != 1:
        failures.append(f"expected one dispatch attempt, got {completed.attempt_count}")
    if len(completed.lifecycle_events) != 3:
        failures.append(f"expected three lifecycle events, got {len(completed.lifecycle_events)}")
    expected_gaps = {
        "live_scheduler_dispatch_not_executed",
        "persistent_task_table_write_not_executed",
        "end_to_end_automation_run_not_executed",
    }
    if set(check["remaining_runtime_gaps"]) != expected_gaps:
        failures.append("remaining runtime gap boundary drifted")

    payload = {
        "status": "fail" if failures else "pass",
        "contract_status": "closed_narrow_lifecycle_contract" if not failures else "open_missing_contract_evidence",
        "failures": failures,
        "check": check,
        "completed_record": completed.model_dump(mode="json"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
