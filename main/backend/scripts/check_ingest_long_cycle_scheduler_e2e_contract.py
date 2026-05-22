#!/usr/bin/env python3
"""Deterministic Wave11 gate for ingest long-cycle scheduler E2E contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.ingest.digestion_scaffold import check_long_cycle_scheduler_e2e_contract


def main() -> int:
    check = check_long_cycle_scheduler_e2e_contract(
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
        persistent_ref="fake-db://long_cycle_persistent_tasks",
        event_time="2026-03-08T11:00:00Z",
        run_at="2026-03-08T11:02:00Z",
    )

    failures: list[str] = []
    if check["status"] != "pass":
        failures.append(f"expected pass, got {check['status']}")
    if check["dispatch_intent"]["live_dispatch"] is not False:
        failures.append("dispatch intent must remain contract-only")
    if check["dispatch_intent"]["selected_window"] != "7d":
        failures.append("dispatch intent did not preserve selected window")
    if check["completed_record"]["status"] != "succeeded":
        failures.append(f"expected completed record, got {check['completed_record']['status']}")
    write_statuses = [item["status_after"] for item in check["persistence_writes"]]
    if write_statuses != ["ready", "running", "succeeded"]:
        failures.append(f"unexpected fake repository write statuses: {write_statuses}")
    if any(item["live_db_write"] for item in check["persistence_writes"]):
        failures.append("fake repository writes must not claim live DB mutation")
    expected_closed = {
        "scheduler_dispatch_intent",
        "fake_repository_db_table_write_abstraction",
        "persistent_task_ready_running_succeeded_lifecycle",
        "dispatch_output_refs_recorded",
    }
    if set(check["closed_slice"]) != expected_closed:
        failures.append("closed scheduler E2E slice drifted")
    expected_gaps = {
        "live_scheduler_dispatch_not_executed",
        "live_persistent_task_table_write_not_executed",
        "production_worker_task_not_executed",
        "end_to_end_automation_run_not_executed",
    }
    if set(check["remaining_runtime_gaps"]) != expected_gaps:
        failures.append("remaining runtime gap boundary drifted")

    payload = {
        "status": "fail" if failures else "pass",
        "contract_status": "closed_narrow_scheduler_e2e_contract" if not failures else "open_scheduler_e2e_contract_gap",
        "failures": failures,
        "check": check,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
